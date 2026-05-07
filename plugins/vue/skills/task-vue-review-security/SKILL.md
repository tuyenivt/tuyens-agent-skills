---
name: task-vue-review-security
description: Vue security review for XSS via `v-html`, CSP and `nonce`, Nitro server endpoint validation, server-side data exposure (Pinia hydration), env-var leakage (`NUXT_PUBLIC_` / `VITE_`), open redirect, auth on Nuxt server routes / middleware, CSRF on cookie-session apps, and Vue-aware OWASP. Detects Nuxt 3 vs Vite + Vue Router and applies the right idioms. Stack-specific override of task-code-review-security, invoked when stack-detect resolves to Vue.
agent: vue-security-engineer
metadata:
  category: frontend
  tags: [vue, typescript, nuxt, vite, security, xss, csp, nitro, owasp, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Vue Security Review

## Purpose

Vue-aware security review that names `v-html` (XSS surface), Content Security Policy and `nonce`, Nitro server-route validation (Zod / `h3` `readValidatedBody`), Pinia state SSR hydration leak (entire ORM rows passed to client serialize through `__NUXT__` payload), `NUXT_PUBLIC_*` / `VITE_*` env vars (compiled into client bundle), open-redirect risks, middleware-based auth (`defineNuxtRouteMiddleware` and Nitro `defineEventHandler` middleware), and Vue-specific risks (XSS via untrusted HTML, prototype pollution via spread, JSON serialization of secrets through SSR payload) directly instead of routing through the generic frontend security adapter. Produces findings with attack scenarios and concrete remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for Vue. The core workflow's contract (invocation, diff resolution, output format) is preserved.

## When to Use

- Reviewing a Nuxt or Vite + Vue PR for security regressions
- Pre-deployment hardening pass on auth, file upload, payment, or PII-handling routes
- Periodic CSP / Nitro endpoint validation drift sweep
- Auditing a new Nitro server route, new middleware, or new auth flow

**Not for:**

- Performance review (use `task-code-review-perf` or `task-vue-review-perf`)
- General code review (use `task-code-review` or `task-vue-review`)
- Production incident triage (use `/task-oncall-start`)
- Backend API security review for the API the Vue app calls (run that against the backend repo)

**Depth.** This workflow always runs at full depth - there is no `quick` / `standard` / `deep` knob. Security review has cliff-edged consequences (XSS → account takeover, exposed secrets) that do not benefit from a "light" mode.

## Severity Rubric

Use these definitions to keep severity consistent across runs - do not invent your own scale.

| Severity     | Definition                                                                                                                                                                                                                                                                                               |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Working XSS on a production code path (`v-html` on user input without sanitizer), secret committed to client bundle (`NUXT_PUBLIC_API_KEY` / `VITE_API_KEY` for a privileged API), authentication bypass on a Nitro endpoint, mass exfiltration via SSR payload returning entire ORM rows. Blocks merge. |
| **High**     | Missing input validation on a Nitro endpoint that mutates data, missing auth on a privileged Nitro endpoint, IDOR via path param without ownership check, open redirect via unchecked `navigateTo(userInput)` / `redirect`, CSRF on a cookie-session form. Must fix before merge.                        |
| **Medium**   | Hardening gap with mitigating control (CSP missing nonce but `unsafe-inline` for styles only and no untrusted HTML rendered), weak rate limit on auth route, Sentry collecting PII without redaction. Should fix this PR or the next one.                                                                |
| **Low**      | Defense-in-depth nice-to-have, dependency advisory below actively-exploited threshold, hardening recommendations without a concrete current attack scenario.                                                                                                                                             |

## Invocation

Mirrors `task-code-review-security`:

| Invocation                           | Meaning                                                                                               |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| `/task-vue-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-vue-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-vue-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-security` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Vue. If the detected stack is not Vue, stop and tell the user to invoke `/task-code-review-security` instead.

Detect framework: Nuxt 3 vs Vite + Vue Router. Record `Framework: ...` for the Summary block. Each step branches on this signal where the idiom differs - Nuxt has Nitro server routes, server middleware, and `defineNuxtRouteMiddleware` as server-side surfaces; Vite is purely client-side and the API lives in a separate backend.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-security` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Security Surface

Before applying the OWASP and authn/authz checklists, open the files that actually wire security so findings cite real lines:

**Nuxt 3 surface:**

- Every changed `pages/**/*.vue`, `layouts/**/*.vue`, `app.vue`
- Every changed `server/api/**/*.ts`, `server/routes/**/*.ts` (Nitro endpoints) - the request body / query / params surface
- `server/middleware/**/*.ts` - server-side auth, headers, rate limiting, redirect logic
- `middleware/**/*.ts` - client-side route guards (`defineNuxtRouteMiddleware`)
- `nuxt.config.{js,ts,mjs}` - `routeRules` (`headers` for CSP / HSTS / X-Frame-Options), `nitro` config, `image.domains`, `runtimeConfig` (server vs `public` split)
- Auth library config: `nuxt-auth-utils` / `@sidebase/nuxt-auth` / Lucia / custom session middleware
- Every component or page rendering untrusted HTML (`v-html`, MDX rendering, markdown render with raw HTML enabled)
- Every form posting to a Nitro endpoint and the server route body
- `package.json` for `@sidebase/nuxt-auth` / `nuxt-auth-utils` / `lucia` / `iron-session`, `dompurify` / `sanitize-html`, CSRF libraries
- `.env.example` / `.env` references - flag any `NUXT_PUBLIC_*` referencing what should be a server secret (`NUXT_PUBLIC_*` is exposed via `useRuntimeConfig().public` and ships in the client bundle)

**Vite + Vue Router surface:**

- Every component rendering untrusted HTML (`v-html`, MDX, markdown)
- `index.html` (CSP via `<meta>` if not server-set), `vite.config.{js,ts}` `server.headers` for dev CSP
- Auth: client-side session handling, token storage location (localStorage vs httpOnly cookie)
- API client config (Axios / fetch wrappers) - `withCredentials`, CSRF token handling, default headers
- `package.json` for sanitization libraries, `dompurify`, `marked` / `markdown-it` config; flag any `VITE_*` env var that names a privileged secret

When the diff removes a CSP rule, removes `dompurify`, or relaxes auth middleware, also `git log -p` the prior revision of those lines to confirm what was protected before.

### Step 4 - OWASP Triage (Vue Lens)

This step is a **triage pass**, not a separate findings list. Run through the OWASP categories below and produce a single output: a list of categories that show signal in this diff (e.g., `Broken Access Control: yes`, `XSS: yes`, `Cryptographic Failures: no signal in diff`). Steps 5-9 then produce the actual findings; do **not** repeat them here.

| Risk                          | Vue-specific check                                                                                                                                                                                                                        |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Nitro endpoints verify session before mutating; server middleware enforces auth on protected routes; client-side `defineNuxtRouteMiddleware` backed by server check                                                                       |
| Injection                     | Nitro endpoint validates input via Zod (`readValidatedBody(event, schema.parse)`); ORM queries parameterized; URL params validated                                                                                                        |
| XSS                           | Vue auto-escapes `{{ }}` interpolations; `v-html` only with sanitized HTML (`DOMPurify`, `sanitize-html`); markdown renderer disables raw HTML or sanitizes; CSP set with `nonce` for scripts                                             |
| Cryptographic Failures        | `bcrypt` / `argon2` for passwords (in any server route handling auth); `jose` / `nuxt-auth-utils` for JWT; never custom crypto; secrets sourced from server-only `runtimeConfig` not committed                                            |
| Security Misconfiguration     | CSP set via `nuxt.config.ts` `routeRules.headers` or `server/middleware/security.ts`; `Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` set; `image.domains` allowlists external image hosts |
| SSRF                          | Server-side `$fetch(userControlledUrl)` in Nitro endpoints validates host against allowlist                                                                                                                                               |
| Insecure Design (A04)         | Default-deny: `server/middleware/auth.ts` checks auth on all routes except an allowlist; not the inverse                                                                                                                                  |
| Vulnerable Components (A06)   | `npm audit` / `pnpm audit` clean for High/Critical; Dependabot active                                                                                                                                                                     |
| Data Integrity Failures (A08) | `JSON.parse` on untrusted bounded; `eval` / `new Function` flagged - any occurrence is critical                                                                                                                                           |
| Logging & Monitoring (A09)    | Sentry Vue SDK `beforeSend` strips PII; client logs do not include `password`, `token`, `authorization`. Server logs (Nitro endpoints) follow same rules                                                                                  |

### Step 5 - Authentication

**Nuxt 3 (server-side auth):**

- [ ] **Auth library chosen and consistent**: `nuxt-auth-utils` / `@sidebase/nuxt-auth` / Lucia / custom session - one path through the codebase, not mixed
- [ ] **Session check at every protected boundary**: `server/middleware/auth.ts` for route-level gating; Nitro endpoints call `getUserSession(event)` / `requireUserSession(event)` at the top and throw `createError({ statusCode: 401 })` on null; client-side `defineNuxtRouteMiddleware` is for UX, NEVER trust it for authorization
- [ ] **Server middleware widening**: a change that adds `/api/users/*` (or any privileged path) to a public allowlist - or removes it from a protected list - silently exempts the route from auth. Flag any middleware change that broadens the public surface as Critical unless the endpoint does its own session check inside
- [ ] **Password hashing**: when this app handles password auth (not just OAuth), `bcrypt` (cost ≥ 10) or `argon2` for the hash; flag `crypto.createHash('sha256')` or homebrew
- [ ] **JWT verification (when used)**: `jose.jwtVerify(token, key, { algorithms: ['HS256' | 'RS256'], issuer, audience })` - explicit `algorithms` allowlist; never accept `alg: none`. `nuxt-auth-utils` uses sealed cookies (`iron-webcrypto`) by default
- [ ] **Cookie config**: session cookies are `httpOnly: true`, `secure: true` in prod, `sameSite: 'lax'` (or `'strict'` for high-sensitivity flows); flag tokens stored in `localStorage` (XSS-readable). Nitro `setCookie(event, ...)` defaults are sensible but flag any explicit override that weakens
- [ ] **Brute-force protection**: rate limit on `/api/auth/*` Nitro endpoints via `@upstash/ratelimit` / `nuxt-security` rate limiter; not relying on a downstream API to do it
- [ ] **Magic-link / OAuth callback validation**: `state` / `nonce` validated; redirect URL allowlist; flag `await sendRedirect(event, getQuery(event).returnTo)` without allowlist (open redirect). `nuxt-auth-utils` OAuth handlers do this if used correctly - flag custom implementations that skip
- [ ] **`runtimeConfig` server vs public split**: secrets live in `runtimeConfig.<key>` (server-only); only non-secrets in `runtimeConfig.public.<key>`. Flag any `useRuntimeConfig().public.apiSecret` pattern as Critical

**Vite + Vue Router (client-side, backend handles auth):**

- [ ] **Tokens not in `localStorage`**: prefer `httpOnly` cookies set by the backend; if a token must live in JS, document the XSS-recovery story (token rotation, short TTL, refresh via httpOnly cookie)
- [ ] **No client-side authorization decisions**: `if (user.role === 'admin') showAdminButton` is fine for UX; `if (user.role === 'admin') fetchAdminData()` is **not** a security control - the backend must reject. Flag any client-side guard not backed by a server check
- [ ] **Refresh token flow**: refresh via httpOnly cookie POST to backend; never store refresh token in JS

### Step 6 - Authorization

**Nuxt 3 Nitro endpoints:**

- [ ] **Authorization drift sweep**: every new Nitro endpoint in the diff calls `await requireUserSession(event)` (or equivalent) at the top and rejects unauthenticated callers - or has an explicit `// public: rationale` comment for the rare public mutation
- [ ] **IDOR**: any Nitro endpoint accepting an `id` filters DB queries by `ownerId` / `tenantId` from the session - never just by the param. Example: `prisma.order.findFirst({ where: { id, ownerId: session.user.id } })`. A session check that only verifies the principal is authenticated is not enough - it must verify the principal can act on **this** resource
- [ ] **Role checks**: when endpoints are role-gated, the role comes from the **server-validated session**, never from a request body / search param / header / client-provided JWT claim that has not been verified server-side
- [ ] **Per-tenant isolation**: multi-tenant apps scope queries by `tenantId` derived from the session; not from the URL
- [ ] **SSR data leak via Pinia / `useState`**: server-side fetched data flows through `__NUXT__` payload into client HTML. If a Pinia store or `useState` holds an entire ORM row including server-only fields, those serialize into the page HTML visible to any client. Project to a DTO before placing in store / state

**Both frameworks:**

- [ ] **Client-side route guards mirror the server**: `defineNuxtRouteMiddleware` redirect / Vue Router `beforeEach` guard is for UX; the backend / Nitro endpoint must enforce authorization independently
- [ ] **CSRF**: for session-cookie auth (not bearer tokens), state-changing requests must include a CSRF token or use `sameSite: 'strict'` / `'lax'` cookies. Nitro does not have built-in CSRF protection like Next.js Server Actions do - flag cookie-session POST endpoints without an explicit CSRF token check or Origin / Referer header validation. `nuxt-csurf` / `nuxt-security` provide middleware

### Step 7 - Input Validation and Nitro Endpoints

**Nuxt 3 Nitro endpoints (`server/api/**/*.ts`):**

- [ ] **Every endpoint validates input**: `defineEventHandler(async (event) => { const body = await readValidatedBody(event, Schema.parse) })` - throws on invalid. Or use `safeParse` and `createError` for typed error response. Never trust the shape of `await readBody(event)` directly
- [ ] **`readValidatedBody` / `getValidatedQuery` / `getValidatedRouterParams`**: h3 helpers that combine read + Zod validation in one call. Flag raw `readBody(event)` followed by ad-hoc field access
- [ ] **Files: type / size / content validated**: `readMultipartFormData(event)` returns parts; validate `instanceof File`, `file.data.length < MAX`, MIME inferred from content (`file-type` package), never trust `file.type`
- [ ] **Authorization re-checked inside the handler**: see Step 6
- [ ] **Side effects after validation**: validation → authz → DB write → cache invalidation. Never the other way around
- [ ] **Returned data is the authoring surface for the client**: the response hydrates back into the Vue component - flag any privileged/internal fields included in the return value (project to DTO; use Prisma `select` / `omit`)
- [ ] **`request.json()` / body size**: Nitro caps body size by default; flag explicit raises without justification
- [ ] **Response shape is intentional**: return DTOs, not raw ORM rows; `Prisma.UserGetPayload<...>` types are not the API contract

**Both frameworks (when accepting any input from the URL):**

- [ ] **`URLSearchParams` / route params validated**: typed via Zod before use; flag direct `parseInt(route.params.id as string)` without bounds + null check. Dynamic Nuxt route segments (`pages/users/[id].vue` exposing `route.params.id`) are validated client-side at most for UX; the actual security surface is the Nitro endpoint that consumes the param - validate the shape (UUID, integer, slug pattern) there before passing to ORM
- [ ] **`JSON.parse(userInput)` flowing into ORM**: a Nitro endpoint that does `JSON.parse(body.config)` and then spreads / passes the result into Prisma is a mass-assignment + prototype-pollution surface. Validate via Zod after parsing; never `prisma.x.update({ data: parsedJson })` directly
- [ ] **No `v-html` on untrusted strings**: any usage of `v-html="x"` where `x` originates from user input, URL params, or external API must be sanitized via `DOMPurify.sanitize(html)` (or `sanitize-html` server-side) - strict allowlist; never `v-html="marked(userInput)"` without a sanitizer

### Step 8 - Common Vue Vulnerability Patterns

- [ ] **`v-html` audit**: every site must have either a sanitizer in the chain or a code comment justifying why the input is trusted (e.g., "static markdown from the repo, processed at build time"). Never `v-html="userMarkdown"` without `DOMPurify`
- [ ] **Sanitizer config not too permissive**: `DOMPurify.sanitize(html, { ADD_TAGS: ['iframe'], ADD_ATTR: ['onload'] })` defeats the purpose. Flag any `ADD_TAGS` containing `iframe` / `script` / `object` / `embed` / `style` without a documented allowlist; flag any `ADD_ATTR` containing event handlers (`onload`, `onclick`, `onerror`) or URL-bearing attrs (`src`, `href`) when the source is user-controllable. Default `DOMPurify.sanitize(html)` is the safe baseline
- [ ] **`:href="userControlledUrl"`**: validate scheme is `http(s):` (block `javascript:`, `data:`, `vbscript:`); `<NuxtLink>` and `<a :href>` both are vectors when href comes from user data. URL allowlist for cross-origin nav
- [ ] **Open redirect**: `await navigateTo(query.returnTo)` (Nuxt) / `router.push(returnTo)` (Vite) without allowlist or relative-path-only check is an open redirect. Validate: `url.startsWith('/') && !url.startsWith('//')` and not a protocol-relative URL. Same for Nitro `sendRedirect(event, query.next)`
- [ ] **`NUXT_PUBLIC_*` / `VITE_*` for secrets**: any `useRuntimeConfig().public.*` or `import.meta.env.VITE_*` that names an API key, database URL, or signing secret is a critical finding - those compile into the client bundle and ship to every browser. Server-only secrets live in `runtimeConfig.<key>` (Nuxt, accessed only on server) or platform secret stores
- [ ] **Pinia store SSR hydration leak**: a Pinia store populated server-side with `prisma.user.findUnique({ where: { id } })` serializes into `__NUXT__` payload (`window.__NUXT__.pinia`) on hydration. `passwordHash`, `mfaSecret`, etc. land in HTML. Project to a DTO at the data layer or before placing in the store - or use Prisma `select` / `omit`
- [ ] **`useState` SSR leak**: same risk as Pinia - `useState(key, () => fetchSensitive())` running server-side embeds the result in the SSR payload
- [ ] **CSP set with sensible defaults**: `default-src 'self'`; `script-src 'self' 'nonce-XXX' 'strict-dynamic'`; `style-src 'self' 'unsafe-inline'` (Tailwind / scoped styles accept; document the trade); `img-src 'self' data: <CDN>`; `connect-src 'self' <API>`; `frame-ancestors 'none'`. Nuxt 3 supports nonce via `nuxt-security` module or custom `server/middleware/csp.ts`
- [ ] **CSP delivery channel**: prefer HTTP response header (via `routeRules.headers` or `server/middleware/`) over `<meta http-equiv="Content-Security-Policy">`. The meta variant cannot enforce `frame-ancestors`, `report-uri` / `report-to`, or `sandbox`. Flag `<meta>`-delivered CSP on a server-rendered app as Medium unless the project documents why
- [ ] **CSP wildcards**: `default-src *` or `script-src *` is effectively no CSP. Any wildcard host in `script-src` / `connect-src` / `frame-src` is a finding; named CDN hosts only
- [ ] **`unsafe-eval` / `unsafe-inline` for scripts**: not allowed in production CSP for `script-src`; any presence is a finding. Vue 3 templates compile to render functions at build time so `unsafe-eval` is not required (unlike Vue 2 with runtime template compilation - if the app uses runtime templates flag the dependency on `unsafe-eval`)
- [ ] **`eval` / `new Function(string)` in client**: any occurrence is a critical finding; obfuscation libraries / template engines that use `new Function` (e.g., `lodash.template`) flagged
- [ ] **Prototype pollution via spread**: `Object.assign(target, JSON.parse(userInput))`, `{...defaults, ...userJson}` on data the client received - same risks as Node, in client code. Trust boundary is "data fetched from your API" vs "data from `URLSearchParams` / `postMessage` / external"
- [ ] **`window.addEventListener('message')` validates origin**: missing origin check is universal XSS via parent / iframe
- [ ] **Third-party scripts**: every `useHead({ script: [{ src: '...' }] })` / `<script src>` justified; SRI (`integrity` attribute) for any non-first-party script; analytics / chat widgets reviewed for what data they exfiltrate
- [ ] **Image / media `src` allowlist (Nuxt)**: `nuxt.config.ts` `image.domains` listed; flag changes that add a domain without justification (image proxy can be SSRF if not careful). Wildcards (`'*.example.com'`) are a finding - if any subdomain is takeoverable, it becomes an XSS / phishing source. Pin specific hostnames; if wildcard required, document subdomain governance
- [ ] **iframe sandbox**: any `<iframe>` rendering external content includes `sandbox="allow-scripts allow-same-origin..."` with the minimum allowlist; flag `<iframe :src>` without `sandbox`
- [ ] **iframe `src` from user input**: `<iframe :src="query.embed">` is a phishing / clickjacking surface even with `sandbox`. Validate against an allowlist of expected hosts
- [ ] **`window.opener` leak**: external `<a :href target="_blank">` includes `rel="noopener noreferrer"`; `<NuxtLink>` is fine for internal links

### Step 9 - Data Protection

- [ ] **PII in client logs / Sentry**: Sentry Vue SDK `beforeSend` strips known sensitive fields (`email`, `password`, `token`, `creditCard`); `Sentry.init({ sendDefaultPii: false })` (default but flag explicit `true`); error boundaries do not log entire props blobs
- [ ] **No tokens / passwords / PII in URLs**: search params and path params hit logs, browser history, referer headers; POST body to Nitro endpoint is the right channel
- [ ] **`localStorage` / `sessionStorage` not used for tokens**: XSS-readable; cookies (`httpOnly`) for session, in-memory state for short-lived UI tokens
- [ ] **TLS enforcement**: `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` set via `routeRules.headers` or hosting platform; HTTP redirected to HTTPS at the edge
- [ ] **Secrets management**: server `runtimeConfig` values come from a secret store (Vault / AWS Secrets Manager / Doppler / hosting platform secrets); flag any literal API key in `.env` checked into git; `.env` gitignored
- [ ] **Source maps in production**: hosting publishes source maps to Sentry but does not serve them publicly (`sourcemap.client: false` in `nuxt.config.ts` for non-Sentry builds; for Sentry, the plugin uploads then deletes)

## Rules

- Always validate at system boundaries: Nitro endpoint body / query / params, `URLSearchParams`, `postMessage`, external API responses
- Never disable Nitro endpoint validation / server middleware auth to silence a failing test - fix the test
- Never widen authorization (e.g., removing session check from a Nitro endpoint, dropping middleware on a route) without an explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Default-deny via server middleware allowlisting public routes; not denylisting protected ones

## Self-Check

**Verifiable from the diff (must check):**

- [ ] Stack confirmed as Vue; framework recorded before any framework-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); refs captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Security surface (auth config, server middleware, changed Nitro endpoints / pages, components rendering HTML, CSP / headers config) read directly before applying checklists; prior revision consulted when guards or middleware were removed
- [ ] OWASP triage (Step 4) produced one signal verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] **Authorization drift sweep**: every new Nitro endpoint in the diff calls `requireUserSession` and verifies object-level ownership when applicable
- [ ] Input validation reviewed for every changed Nitro endpoint; Zod via `readValidatedBody` / `getValidatedQuery` confirmed
- [ ] `v-html`, `:href` / redirect targets, open-redirect, `NUXT_PUBLIC_*` / `VITE_*`, `runtimeConfig` server vs public split audited when the diff touches them
- [ ] CSP / security headers / cookie config reviewed when server middleware or `nuxt.config.ts` `routeRules.headers` changed; CSP delivery channel (header vs `<meta>`), wildcards, and sanitizer config audited
- [ ] Server middleware allowlist exclusions audited: any path widened to public must have its own in-handler session check; otherwise Critical
- [ ] Dynamic route params validated via Zod before reaching ORM (in the Nitro endpoint, not just client-side); `JSON.parse(userInput)` into Prisma flagged as mass-assignment + prototype-pollution surface
- [ ] Image `image.domains` wildcards audited for subdomain-takeover risk
- [ ] iframe `:src` from user input audited (phishing / clickjacking, beyond `sandbox` presence)
- [ ] SSR payload leak reviewed: Pinia stores and `useState` populated server-side checked for entire ORM rows; DTOs / `select`-projected fields only
- [ ] Severity rubric applied consistently (Critical / High / Medium / Low matches the rubric, not invented)
- [ ] Every finding includes an attack scenario, "regression risk" rationale (for missing-control gaps), or "topology-dependent" framing (for infra-flavored findings)
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)

**Requires repo / infra access (check if visible, otherwise note as "could not verify from diff alone - flag for separate audit"):**

- [ ] Auth library config (`nuxt-auth-utils` / `@sidebase/nuxt-auth` / Lucia) reviewed - applies when auth module is in scope
- [ ] CSP / HSTS / security headers verified - applies when `nuxt.config.ts` `routeRules.headers` or middleware in scope
- [ ] Sentry Vue SDK `beforeSend` strips PII - skip if Sentry init module not in diff
- [ ] `pnpm audit` / `npm audit` clean - run separately; this workflow does not execute tools

## Output Format

```markdown
## Vue Security Review Summary

**Stack Detected:** Vue <version> / TypeScript <version>
**Framework:** Nuxt 3 <version> | Vite + Vue Router <version>
**Auth:** nuxt-auth-utils | @sidebase/nuxt-auth | Lucia | iron-session | Custom | None (Vite + backend handles auth)
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture, calling out any Vue-specific risks like `NUXT_PUBLIC_` secret leak, missing Nitro endpoint validation, ORM rows in Pinia SSR payload, missing CSP, `v-html` on user input.]

## OWASP Triage

| Category                  | Verdict                 |
| ------------------------- | ----------------------- |
| Broken Access Control     | yes / no signal in diff |
| Injection                 | yes / no signal in diff |
| XSS                       | ...                     |
| Cryptographic Failures    | ...                     |
| Security Misconfiguration | ...                     |
| SSRF                      | ...                     |
| Insecure Design           | ...                     |
| Vulnerable Components     | ...                     |
| Data Integrity Failures   | ...                     |
| Logging & Monitoring      | ...                     |

## Findings

### Critical

- **Location:** [file:line]
- **Issue:** [vulnerability described in Vue terms - e.g., "Nitro endpoint `PUT /api/account` in server/api/account.put.ts accepts `body` directly into `prisma.user.update({ data: body })` - mass-assignment lets a client submit `{ role: 'admin' }` and elevate privileges because there is no Zod schema enforcing the shape"]
- **Attack scenario:** [one of: (a) concrete exploit walkthrough; (b) "Regression risk: the next refactor silently removes one of these protections" - for missing-control gaps; (c) "Topology-dependent: depends on whether the CDN strips the X-Forwarded-Host header" - for infra-flavored findings. Pick one and label which.]
- **Severity rationale:** [tier] per rubric - [which clause from the Severity Rubric applies]
- **Fix:** [specific Vue remediation with code example - Zod schema for `readValidatedBody`, `nonce` in CSP, `DOMPurify.sanitize` wrapper, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `nonce`-based CSP via `nuxt-security` module", "Replace `localStorage` token with httpOnly cookie", "Migrate ad-hoc auth to `nuxt-auth-utils`"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, or threat-model exercise worth spawning a subagent for). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Wrap body with `await readValidatedBody(event, AccountUpdateSchema.parse)` at top of server/api/account.put.ts; whitelist `name`, `email`, `bio` only"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `pnpm audit` and upgrade flagged packages"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no security issues were found._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{role: 'admin'}` via JSON body and gains admin via mass assignment because the Nitro endpoint lacks a Zod schema")
- Skipping OWASP categories that appear clean - explicitly state "no signal in diff" per category
- Recommending generic security advice when a Vue idiom applies (say "validate Nitro body with `readValidatedBody`", not "add input validation")
- Approving `v-html` on user input without a sanitizer
- Approving `NUXT_PUBLIC_*` / `VITE_*` for any secret - those ship to every browser
- Approving `localStorage` for auth tokens - XSS-readable; httpOnly cookies are the right primitive
- Approving Pinia stores / `useState` populated with full ORM rows - SSR payload serializes them into HTML
- Approving `unsafe-eval` / `unsafe-inline` in production `script-src` CSP
- Approving `navigateTo(query.next)` without allowlist - open redirect
- Conflating security review with general code quality or performance review - delegate those to their workflows
- Treating client-side `v-if="user.role === 'admin'"` as authorization - it is UX only; the server must enforce
- Recommending JWT in `localStorage` because "it's stateless" - the XSS exposure is the real cost
