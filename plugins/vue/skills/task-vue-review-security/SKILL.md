---
name: task-vue-review-security
description: Vue / Nuxt security review: v-html XSS, CSP, Nitro endpoint auth, Pinia hydration leaks, env-var exposure, CSRF, open redirect, OWASP.
agent: vue-security-engineer
metadata:
  category: frontend
  tags: [vue, typescript, nuxt, vite, security, xss, csp, nitro, owasp, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Vue Security Review

Stack-specific delegate of `task-code-review-security` for Vue / Nuxt. Always runs at full depth - no quick/standard knob.

## When to Use

- Nuxt or Vite + Vue PR for security regressions
- Pre-deployment hardening on auth, file upload, payment, or PII routes
- Periodic CSP / Nitro endpoint validation drift sweep
- Audit of new Nitro route, middleware, or auth flow

**Not for:** performance (`task-vue-review-perf`), general review (`task-vue-review`), incident triage (`/task-oncall-start`), or the backend the Vue app calls (review that repo).

## Invocation

| Invocation                           | Meaning                                                                                |
| ------------------------------------ | -------------------------------------------------------------------------------------- |
| `/task-vue-review-security`          | Review current branch vs base; fails fast on trunk                                     |
| `/task-vue-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                             |
| `/task-vue-review-security pr-<N>`   | Review PR head in local branch `pr-<N>` (user fetches first)                           |

When called as subagent of `task-code-review-security` or `task-vue-review`, accept the parent's stack and pre-read diff/log; skip Steps 1-2.

## Severity Rubric

| Severity     | Definition                                                                                                                                                                  |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Working XSS on production path, secret in client bundle (`NUXT_PUBLIC_*` / `VITE_*` for privileged API), auth bypass on Nitro endpoint, mass exfiltration via SSR payload. Blocks merge. |
| **High**     | Missing input validation on mutating Nitro endpoint, missing auth on privileged endpoint, IDOR, open redirect via `navigateTo`/`sendRedirect`, CSRF on cookie-session form. Must fix before merge. |
| **Medium**   | Hardening gap with mitigating control (CSP missing nonce but no untrusted HTML rendered), weak rate limit, Sentry collecting PII without redaction. Fix this PR or next.   |
| **Low**      | Defense-in-depth, dependency advisory below actively-exploited threshold.                                                                                                   |

**Combined-finding rule.** If a realistic exploit requires both findings to land on the *same code path* (same Nitro handler, same component, same route group with shared middleware), file as one finding at the elevated severity and cite each component. If either is exploitable alone, file separately. When co-location is unclear from the diff, file separately and add `Note: verify same-handler co-location; merge if confirmed` to the lower-severity entry.

Archetypal compositions:

- Missing `requireUserSession` + mass-assignment via `prisma.user.update({ data: body })` on same handler -> **Critical** unauth admin override.
- Missing ownership check + Pinia hydration of full ORM row (`passwordHash`) on same page -> **Critical** account takeover via `__NUXT__.pinia`.
- `v-html` on user input + sanitizer disabled (`ADD_TAGS: ['script']`) in same component -> **Critical** working XSS.
- `NUXT_PUBLIC_API_KEY` + same key used to call admin API from browser -> **Critical** admin-API exposure.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Vue. If a parent workflow already detected Vue, skip re-detection. If not Vue, stop and direct user to `/task-code-review-security`.

Record `Framework: Nuxt 3 <version>` or `Vite + Vue Router <version>`. Subsequent steps branch on this - only Nuxt has Nitro server routes, server middleware, and `defineNuxtRouteMiddleware`.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` **once**; reuse for all subsequent steps. Surface fail-fast messages verbatim and stop. Never run state-changing git from this workflow. Skip entirely if parent provided pre-read artifacts.

### Step 3 - Read the Security Surface

Open the files that wire security so findings cite real lines.

**Nuxt 3:** changed `pages/**/*.vue`, `layouts/**/*.vue`, `app.vue`, `server/api/**`, `server/routes/**`, `server/middleware/**`, `middleware/**`; `nuxt.config.{js,ts,mjs}` (`routeRules.headers`, `nitro`, `image.domains`, `runtimeConfig`); auth module config (`nuxt-auth-utils` / `@sidebase/nuxt-auth` / Lucia / `iron-session`); components rendering untrusted HTML; forms posting to Nitro; `package.json` for sanitizers / CSRF libs; `.env*` for `NUXT_PUBLIC_*` referencing server secrets.

**Vite + Vue Router:** components rendering untrusted HTML; `index.html` (`<meta>` CSP), `vite.config` `server.headers`; token storage location; API client config (`withCredentials`, CSRF headers); `package.json` sanitizers; `.env*` for `VITE_*` referencing secrets.

When the diff removes a CSP rule, removes a sanitizer, or relaxes auth middleware, `git log -p` the prior revision to confirm prior protection.

### Step 4 - OWASP Triage (Vue Lens)

Triage pass only - produce one verdict per category (`yes` / `no signal in diff`). Findings go in Steps 5-9, not here.

| Risk                          | Vue-specific check                                                                                                                                                   |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Nitro endpoints check session before mutating; server middleware enforces auth; client `defineNuxtRouteMiddleware` backed by server check                            |
| Injection                     | `readValidatedBody(event, schema.parse)`; ORM parameterized; URL params validated                                                                                    |
| XSS                           | `{{ }}` auto-escapes; `v-html` only with `DOMPurify` / `sanitize-html`; markdown disables raw HTML; CSP `nonce` on scripts                                            |
| Cryptographic Failures        | `bcrypt` / `argon2` / `jose`; secrets in server-only `runtimeConfig`                                                                                                  |
| Security Misconfiguration     | CSP, HSTS, X-Content-Type-Options, Referrer-Policy, Permissions-Policy via `routeRules.headers` or `server/middleware/`; `image.domains` allowlist                    |
| SSRF                          | Server-side `$fetch(userUrl)` validates host against allowlist                                                                                                       |
| Insecure Design (A04)         | Default-deny: middleware allowlists public routes, not the inverse                                                                                                   |
| Vulnerable Components (A06)   | `npm/pnpm audit` clean; Dependabot active                                                                                                                            |
| Data Integrity Failures (A08) | `eval` / `new Function` any occurrence is Critical                                                                                                                   |
| Logging & Monitoring (A09)    | Sentry `beforeSend` strips PII; logs free of `password`, `token`, `authorization`                                                                                     |

### Step 5 - Authentication

**Nuxt 3 (server-side auth):**

- [ ] Auth library consistent (`nuxt-auth-utils` / `@sidebase/nuxt-auth` / Lucia / custom) - one path, not mixed
- [ ] `server/middleware/auth.ts` gates routes; Nitro endpoints call `getUserSession(event)` / `requireUserSession(event)` and throw `createError({ statusCode: 401 })`. Client `defineNuxtRouteMiddleware` is UX only - NEVER trust for authz
- [ ] **Middleware widening (Critical).** Diff adds a privileged path to a public allowlist or removes it from a protected list -> Critical unless every endpoint inside does its own session check
- [ ] Password auth uses `bcrypt` (cost >= 10) or `argon2`; flag `crypto.createHash('sha256')` or homebrew
- [ ] JWT: `jose.jwtVerify(token, key, { algorithms: ['HS256'|'RS256'], issuer, audience })`; never `alg: none`
- [ ] Cookies: `httpOnly: true`, `secure: true` in prod, `sameSite: 'lax'` (or `'strict'` for high-sensitivity). Flag tokens in `localStorage`
- [ ] Rate limit on `/api/auth/*` via `@upstash/ratelimit` / `nuxt-security`
- [ ] OAuth / magic-link: `state` / `nonce` validated; redirect allowlist; flag `sendRedirect(event, getQuery(event).returnTo)` without allowlist
- [ ] **`runtimeConfig` split.** Secrets in `runtimeConfig.<key>` (server-only); only non-secrets in `runtimeConfig.public.<key>`. `useRuntimeConfig().public.apiSecret` is Critical

**Vite + Vue Router (backend handles auth):**

- [ ] Tokens not in `localStorage` (prefer httpOnly cookie); if unavoidable, document XSS-recovery (rotation, short TTL)
- [ ] No client-side authorization decisions. `v-if="user.role==='admin'"` is UX; the backend must reject regardless. Flag client guards not backed by a server check
- [ ] Refresh token never in JS - rotate via httpOnly cookie POST

### Step 6 - Authorization

**Nuxt 3 Nitro endpoints:**

- [ ] **Authorization drift sweep.** Every new Nitro endpoint in the diff calls `requireUserSession` (or equivalent) - or has explicit `// public: <rationale>` comment
- [ ] **IDOR.** Endpoints accepting an `id` filter DB by `ownerId` / `tenantId` from the session, never just by param. Example: `prisma.order.findFirst({ where: { id, ownerId: session.user.id } })`. Authn alone is not authz
- [ ] Role from server-validated session, never from body / query / header / unverified JWT claim
- [ ] Multi-tenant: scope queries by `tenantId` from session, not URL
- [ ] **SSR leak via Pinia / `useState`.** Server-side fetched data flows through `__NUXT__` into client HTML. Full ORM rows (`passwordHash`, `mfaSecret`) serialize to every viewer. Project to DTO or use Prisma `select` / `omit` before placing in store

**Both frameworks:**

- [ ] Client route guards are UX; server must enforce authz independently
- [ ] **CSRF.** Cookie-session POST endpoints need CSRF token or `sameSite: 'strict'`/`'lax'` + Origin/Referer check. Nitro has no built-in CSRF - flag missing protection (use `nuxt-csurf` / `nuxt-security`)

### Step 7 - Input Validation and Nitro Endpoints

**Nuxt 3 Nitro endpoints (`server/api/**`):**

- [ ] Every endpoint uses `readValidatedBody(event, Schema.parse)` / `getValidatedQuery` / `getValidatedRouterParams`. Flag raw `readBody(event)` with ad-hoc field access
- [ ] Files: `readMultipartFormData`, validate `instanceof File`, size cap, MIME inferred from content (`file-type` package), never trust `file.type`
- [ ] Order: validate -> authz -> write -> cache. Never inverted
- [ ] Response is a DTO (Prisma `select`/`omit`), never raw ORM rows - they hydrate back into the Vue component and leak privileged fields
- [ ] Body-size override flagged unless justified

**Both frameworks:**

- [ ] Route params validated via Zod **in the Nitro endpoint** before ORM. Client-side validation is UX only
- [ ] `JSON.parse(userInput)` spread into `prisma.x.update({ data })` is mass-assignment + prototype pollution. Validate via Zod after parsing
- [ ] `v-html` on user-controlled string sanitized via `DOMPurify.sanitize(html)` (strict default allowlist) or `sanitize-html`

### Step 8 - Vue Vulnerability Patterns

- [ ] **`v-html` audit.** Every site has a sanitizer in the chain or a comment justifying trust (`"static markdown built at compile time"`)
- [ ] **Sanitizer config.** Default `DOMPurify.sanitize(html)` is safe. Flag `ADD_TAGS` containing `iframe`/`script`/`object`/`embed`/`style` and `ADD_ATTR` containing event handlers (`onload`, `onclick`, `onerror`) or URL attrs (`src`, `href`) when input is user-controlled
- [ ] **`:href="userUrl"` / `navigateTo` / `sendRedirect`.** Validate scheme is `http(s):` (block `javascript:`, `data:`, `vbscript:`); validate `url.startsWith('/') && !url.startsWith('//')` for internal redirects; otherwise allowlist hosts
- [ ] **`NUXT_PUBLIC_*` / `VITE_*` secret leak (Critical).** Any `useRuntimeConfig().public.*` or `import.meta.env.VITE_*` naming an API key, DB URL, or signing secret ships in every client bundle
- [ ] **Pinia / `useState` SSR hydration leak.** Server-side state populated with full ORM rows serializes into `window.__NUXT__`. Project to DTO before placing in store/state
- [ ] **CSP.** `default-src 'self'`; `script-src 'self' 'nonce-XXX' 'strict-dynamic'`; `frame-ancestors 'none'`; named CDN hosts only (wildcards flagged). Prefer response header (`routeRules.headers` / `server/middleware/`) over `<meta>` - meta cannot enforce `frame-ancestors` or `report-to`
- [ ] **`unsafe-eval` / `unsafe-inline` in `script-src`.** Not allowed; any occurrence is a finding. Vue 3 compiles templates at build time so `unsafe-eval` is not needed (Vue 2 runtime templates require it - flag the dependency)
- [ ] `eval` / `new Function(string)` any occurrence Critical; flag template engines using them (`lodash.template`)
- [ ] Prototype pollution: `Object.assign(target, JSON.parse(userInput))`, `{...defaults, ...userJson}` on untrusted data
- [ ] `window.addEventListener('message')` validates origin
- [ ] Third-party `<script>` / `useHead({ script: [...] })` justified; SRI `integrity` attribute for non-first-party
- [ ] **`image.domains` allowlist (Nuxt).** Wildcards (`'*.example.com'`) are findings - any takeoverable subdomain becomes XSS/phishing source. Pin hostnames
- [ ] `<iframe :src>` for external content uses `sandbox` with minimum allowlist; `<iframe :src="userInput">` requires host allowlist on top of sandbox
- [ ] External `target="_blank"` includes `rel="noopener noreferrer"`

### Step 9 - Data Protection

- [ ] Sentry Vue SDK `beforeSend` strips PII; `sendDefaultPii: false`; error boundaries don't log full props
- [ ] No tokens / passwords / PII in URLs - they hit logs, history, referer
- [ ] `localStorage` / `sessionStorage` not used for auth tokens
- [ ] HSTS via `routeRules.headers` or platform; HTTP redirected at edge
- [ ] Secrets sourced from secret store (Vault / Doppler / platform); `.env` gitignored; no literal API keys committed
- [ ] Source maps not publicly served (`sourcemap.client: false` for non-Sentry builds; Sentry plugin uploads and deletes)

### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write the assembled output to the report file before ending the session. Print the confirmation line to the console.

## Output Format

```markdown
## Vue Security Review Summary

**Stack Detected:** Vue <version> / TypeScript <version>
**Framework:** Nuxt 3 <version> | Vite + Vue Router <version>
**Auth:** nuxt-auth-utils | @sidebase/nuxt-auth | Lucia | iron-session | Custom | None (Vite + backend)
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment naming Vue-specific risks: `NUXT_PUBLIC_*` leak, missing Nitro validation, ORM rows in Pinia SSR payload, missing CSP, `v-html` on user input.]

## OWASP Triage

| Category                  | Verdict                 |
| ------------------------- | ----------------------- |
| Broken Access Control     | yes / no signal in diff |
| Injection                 | ...                     |
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
- **Issue:** [Vue-specific description, e.g., "Nitro `PUT /api/account` in server/api/account.put.ts spreads `body` into `prisma.user.update({ data: body })` without Zod - mass-assignment via `{ role: 'admin' }`"]
- **Attack scenario:** One of: (a) concrete exploit walkthrough; (b) "Regression risk: ..." for missing-control gaps; (c) "Topology-dependent: ..." for infra-flavored findings. Label which.
- **Severity rationale:** [tier] per rubric - [which clause applies]
- **Fix:** Specific Vue remediation with code (Zod schema for `readValidatedBody`, CSP `nonce`, `DOMPurify.sanitize` wrapper).

### High / Medium / Low

[Same structure. Omit sections with no findings. If all omitted, state "No security issues found."]

## Recommendations

[Prioritized hardening not tied to a specific finding - e.g., "Add `nonce`-based CSP via `nuxt-security`", "Replace `localStorage` token with httpOnly cookie".]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, threat-model exercise). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action]
2. **[Delegate]** [High] [scope] - [one-line action]

_Omit this section if no security issues found._
```

## Self-Check

- [ ] Steps 1-2: Vue stack + framework recorded; diff/log read once (or parent handle accepted); no state-changing git
- [ ] Step 3: security surface read; prior revision consulted when guards/middleware were removed
- [ ] Step 4: one OWASP verdict per category (`yes` / `no signal in diff`); not duplicated as findings
- [ ] Steps 5-6: auth library, middleware widening, password/JWT/cookie flags, `requireUserSession` + object-level ownership, Pinia/`useState` SSR ORM leak, CSRF audited
- [ ] Steps 7-8: `readValidatedBody`/`getValidatedQuery`/`getValidatedRouterParams` confirmed on changed endpoints; `v-html`/sanitizer/redirect/`NUXT_PUBLIC_*`/CSP/`image.domains`/iframe audited
- [ ] Step 9: PII in logs, token storage, HSTS, secrets source, source maps reviewed
- [ ] Step 10: report written; confirmation printed
- [ ] Severity rubric + Combined-finding rule applied; every finding has attack scenario, regression-risk, or topology-dependent framing
- [ ] Items invisible in the diff noted "could not verify from diff - flag for separate audit"
- [ ] Next Steps tagged `[Implement]`/`[Delegate]` and ordered Critical > High > Medium > Low

## Avoid

- State-changing git from this workflow.
- Findings without an attack scenario, regression rationale, or topology framing.
- Skipping clean OWASP categories - state "no signal in diff" explicitly.
- Generic advice when a Vue idiom applies.
- Treating client-side `v-if="user.role==='admin'"` as authorization.
