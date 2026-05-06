---
name: task-react-review-security
description: React security review for XSS via `dangerouslySetInnerHTML`, CSP and `nonce`, Server Action input validation, Server Component data exposure, env-var leakage (`NEXT_PUBLIC_`), open redirect, auth on Server Components / Route Handlers / middleware, CSRF on cookie-session apps, and React-aware OWASP. Detects Next.js App Router vs Vite + React Router and applies the right idioms. Stack-specific override of task-code-review-security, invoked when stack-detect resolves to React.
agent: react-security-engineer
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, security, xss, csp, server-actions, owasp, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# React Security Review

## Purpose

React-aware security review that names `dangerouslySetInnerHTML`, Content Security Policy and `nonce`, Server Action validation (Zod / `zod-form-data`), Server Component data leak risk (entire ORM rows passed to Client Components serialize through), `NEXT_PUBLIC_` env vars (compiled into client bundle), `next/link` open-redirect risks, middleware-based auth, and React-specific risks (XSS via untrusted HTML, prototype pollution via spread, JSON serialization of secrets) directly instead of routing through the generic frontend security adapter. Produces findings with attack scenarios and concrete remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for React. The core workflow's contract (invocation, diff resolution, output format) is preserved.

## When to Use

- Reviewing a Next.js or Vite + React PR for security regressions
- Pre-deployment hardening pass on auth, file upload, payment, or PII-handling routes
- Periodic CSP / Server Action validation drift sweep
- Auditing a new Server Action, new Route Handler, new middleware, or new auth flow

**Not for:**

- Performance review (use `task-code-review-perf` or `task-react-review-perf`)
- General code review (use `task-code-review` or `task-react-review`)
- Production incident triage (use `/task-oncall-start`)
- Backend API security review for the API the React app calls (run that against the backend repo)

**Depth.** This workflow always runs at full depth - there is no `quick` / `standard` / `deep` knob. Security review has cliff-edged consequences (XSS → account takeover, exposed secrets) that do not benefit from a "light" mode.

## Severity Rubric

Use these definitions to keep severity consistent across runs - do not invent your own scale.

| Severity     | Definition                                                                                                                                                                                                                                                                               |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Working XSS on a production code path, secret committed to client bundle (`NEXT_PUBLIC_API_KEY` for a privileged API), authentication bypass on a Route Handler / Server Action, mass exfiltration via Server Component returning entire ORM rows. Must fix before deploy; blocks merge. |
| **High**     | Missing input validation on a Server Action that mutates data, missing auth on a privileged Route Handler / Server Action, IDOR via path param without ownership check, open redirect via unchecked `redirect(userInput)`, CSRF on a cookie-session form. Must fix before merge.         |
| **Medium**   | Hardening gap with mitigating control (CSP missing nonce but `unsafe-inline` for styles only and no untrusted HTML rendered), weak rate limit on auth route, Sentry collecting PII without redaction. Should fix this PR or the next one.                                                |
| **Low**      | Defense-in-depth nice-to-have, dependency advisory below actively-exploited threshold, hardening recommendations without a concrete current attack scenario.                                                                                                                             |

## Invocation

Mirrors `task-code-review-security`:

| Invocation                             | Meaning                                                                                               |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-react-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-react-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-react-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-security` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm React. If the detected stack is not React, stop and tell the user to invoke `/task-code-review-security` instead.

Detect framework: Next.js (App Router / Pages Router) vs Vite + React Router. Record `Framework: ...` for the Summary block. Each step that follows branches on this signal where the idiom differs - Next.js has Server Components, Server Actions, middleware, and Route Handlers as server-side surfaces; Vite is purely client-side and the API lives in a separate backend.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-security` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Security Surface

Before applying the OWASP and authn/authz checklists, open the files that actually wire security so findings cite real lines:

**Next.js surface:**

- Every changed `app/**/page.tsx`, `app/**/layout.tsx`, `app/**/route.ts`, `app/**/actions.ts` (Server Actions are functions marked `"use server"` in any module)
- `middleware.ts` - auth checks, CSP / security headers, rate limiting, redirect logic
- `next.config.{js,ts,mjs}` - `headers()` (CSP, HSTS, X-Frame-Options), `redirects()`, `images.domains` / `remotePatterns`
- Auth library config: `auth.ts` / `lib/auth.ts` (NextAuth.js / Auth.js / Clerk / Lucia / Iron Session) - session strategy, JWT vs database, callback URLs
- Every component or Server Component that renders untrusted HTML (`dangerouslySetInnerHTML`, MDX rendering, markdown render with `rehype-raw`)
- Every `<form action={serverAction}>` and the Server Action body it points to
- `package.json` for `next-auth` / `@clerk/nextjs` / `lucia` / `iron-session`, `dompurify` / `sanitize-html`, `csrf` libraries
- `.env.example` / `.env.local` references - flag any `NEXT_PUBLIC_*` referencing what should be a server secret

**Vite + React Router surface:**

- Every component rendering untrusted HTML (`dangerouslySetInnerHTML`, MDX, markdown)
- `index.html` (CSP via `<meta>` if not server-set), `vite.config.{js,ts}` `server.headers` for dev CSP
- Auth: client-side session handling, token storage location (localStorage vs httpOnly cookie)
- API client config (Axios / fetch wrappers) - `withCredentials`, CSRF token handling, default headers
- `package.json` for sanitization libraries, `dompurify`, `marked` / `markdown-it` config

When the diff removes a CSP rule, removes `dompurify`, or relaxes auth middleware, also `git log -p` the prior revision of those lines to confirm what was protected before.

### Step 4 - OWASP Triage (React Lens)

This step is a **triage pass**, not a separate findings list. Run through the OWASP categories below and produce a single output: a list of categories that show signal in this diff (e.g., `Broken Access Control: yes`, `XSS: yes`, `Cryptographic Failures: no signal in diff`). Steps 5-9 then produce the actual findings; do **not** repeat them here.

| Risk                          | React-specific check                                                                                                                                                                                                                 |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Broken Access Control         | Server Actions / Route Handlers verify session before mutating; middleware enforces auth on protected routes; client-side route guards backed by server check                                                                        |
| Injection                     | Server Action / Route Handler validates input via Zod / `zod-form-data` `.strict()`; ORM queries parameterized; URL params validated                                                                                                 |
| XSS                           | React auto-escapes JSX text; `dangerouslySetInnerHTML` only with sanitized HTML (`DOMPurify`, `sanitize-html`); markdown renderer disables raw HTML or sanitizes; CSP set with `nonce` for scripts                                   |
| Cryptographic Failures        | `bcrypt` / `argon2` for passwords (in any server route handling auth); `jose` / Auth.js for JWT; never custom crypto; secrets sourced from env not committed                                                                         |
| Security Misconfiguration     | CSP set via `next.config.js` `headers()` or `middleware.ts`; `Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` set; `images.domains` / `remotePatterns` allowlists external image hosts |
| SSRF                          | Server-side `fetch(userControlledUrl)` in Server Components / Route Handlers / Server Actions validates host against allowlist                                                                                                       |
| Insecure Design (A04)         | Default-deny: `middleware.ts` checks auth on all routes except an allowlist; not the inverse                                                                                                                                         |
| Vulnerable Components (A06)   | `npm audit` / `pnpm audit` clean for High/Critical; Dependabot active                                                                                                                                                                |
| Data Integrity Failures (A08) | `JSON.parse` on untrusted bounded; `eval` / `new Function` flagged - any occurrence is critical                                                                                                                                      |
| Logging & Monitoring (A09)    | Sentry browser SDK `beforeSend` strips PII; client logs do not include `password`, `token`, `authorization`. Server logs (Server Actions / Route Handlers) follow same rules                                                         |

### Step 5 - Authentication

**Next.js (server-side auth):**

- [ ] **Auth library chosen and consistent**: Auth.js (NextAuth.js v5+) / Clerk / Lucia / `iron-session` - one path through the codebase, not mixed
- [ ] **Session check at every protected boundary**: `middleware.ts` for route-level gating; Server Components call `auth()` / `getServerSession()` at the top and redirect on null; Server Actions and Route Handlers call session check **inside** the handler (middleware does not run for Server Actions in some versions - verify). NEVER trust client-side `useSession` for authorization decisions
- [ ] **Password hashing**: when this app handles password auth (not just OAuth), `bcrypt` (cost ≥ 10) or `argon2` for the hash; flag `crypto.createHash('sha256')` or homebrew
- [ ] **JWT verification (when used)**: `jose.jwtVerify(token, key, { algorithms: ['HS256' | 'RS256'], issuer, audience })` - explicit `algorithms` allowlist; never accept `alg: none`
- [ ] **Cookie config**: session cookies are `httpOnly: true`, `secure: true` in prod, `sameSite: 'lax'` (or `'strict'` for high-sensitivity flows); flag tokens stored in `localStorage` (XSS-readable)
- [ ] **Brute-force protection**: rate limit on `/api/auth/*` Route Handlers via `@upstash/ratelimit` or similar; not relying on a downstream API to do it
- [ ] **Magic-link / OAuth callback validation**: `state` / `nonce` validated; redirect URL allowlist; flag `redirect(searchParams.get('returnTo'))` without allowlist (open redirect)

**Vite + React Router (client-side, backend handles auth):**

- [ ] **Tokens not in `localStorage`**: prefer `httpOnly` cookies set by the backend; if a token must live in JS, document the XSS-recovery story (token rotation, short TTL, refresh via httpOnly cookie)
- [ ] **No client-side authorization decisions**: `if (user.role === 'admin') showAdminButton` is fine for UX; `if (user.role === 'admin') fetchAdminData()` is **not** a security control - the backend must reject. Flag any client-side guard not backed by a server check
- [ ] **Refresh token flow**: refresh via httpOnly cookie POST to backend; never store refresh token in JS

### Step 6 - Authorization

**Next.js Server Actions and Route Handlers:**

- [ ] **Authorization drift sweep**: every new Server Action and Route Handler in the diff calls `await auth()` (or equivalent) at the top and rejects unauthenticated callers - or has an explicit `// public: rationale` comment for the rare public mutation
- [ ] **IDOR**: any Server Action / Route Handler accepting an `id` filters DB queries by `ownerId` / `tenantId` from the session - never just by the param. Example: `prisma.order.findFirst({ where: { id, ownerId: session.user.id } })`. An `auth()` check that only verifies the principal is authenticated is not enough - it must verify the principal can act on **this** resource
- [ ] **Role checks**: when actions are role-gated, the role comes from the **server-validated session**, never from a request body / search param / header / client-provided JWT claim that has not been verified server-side
- [ ] **Per-tenant isolation**: multi-tenant apps scope queries by `tenantId` derived from the session; not from the URL
- [ ] **Server Components are also authorization surfaces**: if a Server Component fetches sensitive data and renders it, it must perform the same auth checks - rendering on the server is not a free pass

**Both frameworks:**

- [ ] **Client-side route guards mirror the server**: `<RequireAuth>` wrapper / `redirect` in Server Component is for UX; the backend / Route Handler / Server Action must enforce authorization independently
- [ ] **CSRF**: for session-cookie auth (not bearer tokens), state-changing requests must include a CSRF token or use `sameSite: 'strict'` / `'lax'` cookies + same-origin Server Actions. Next.js Server Actions are protected by an Origin check + cryptographic action ID by default; flag bypasses

### Step 7 - Input Validation and Server Actions

**Next.js Server Actions:**

- [ ] **Every Server Action validates input**: `'use server'` function accepts `FormData` or typed args; first thing is `const parsed = SchemaZ.parse(formData)` (throws on invalid) or `safeParse` (return early). Never trust the shape of `FormData` / args
- [ ] **`zod-form-data` for FormData parsing**: typed parsing of `FormData` into a schema; raw `formData.get('email')` returns `string | File | null` and is easy to misuse
- [ ] **Files: type / size / content validated**: `instanceof File`, `file.size < MAX`, MIME inferred from content (`file-type` package), never trust `file.type`
- [ ] **Authorization re-checked inside the action**: see Step 6
- [ ] **Side effects after validation**: validation → authz → DB write → `revalidateTag` / `revalidatePath`. Never the other way around
- [ ] **Returned data is the authoring surface for the client**: a Server Action returns data that hydrates back into the Client Component - flag any privileged/internal fields included in the return value

**Next.js Route Handlers (`app/**/route.ts`):\*\*

- [ ] **Every method validates body / query / params**: `await request.json()` followed immediately by `Schema.parse(body)`. Same auth + validation rules as Server Actions
- [ ] **`request.json()` body size**: Next.js limits body size by default (1MB on the platform); flag explicit raises without justification
- [ ] **Response shape is intentional**: return DTOs, not raw ORM rows; `Prisma.UserGetPayload<...>` types are not the API contract

**Both frameworks (when accepting any input from the URL):**

- [ ] **`URLSearchParams` / route params validated**: typed via Zod before use; flag direct `parseInt(searchParams.get('id'))` without bounds + null check
- [ ] **No `dangerouslySetInnerHTML` on untrusted strings**: any usage of `dangerouslySetInnerHTML={{ __html: x }}` where `x` originates from user input, URL params, or external API must be sanitized via `DOMPurify.sanitize(html)` (or `sanitize-html` server-side) - strict allowlist; never `__html: marked(userInput)` without a sanitizer

### Step 8 - Common React Vulnerability Patterns

- [ ] **`dangerouslySetInnerHTML` audit**: every site must have either a sanitizer in the chain or a code comment justifying why the input is trusted (e.g., "static markdown from the repo, processed at build time"). Never `{__html: userMarkdown}` without `DOMPurify`
- [ ] **`href={userControlledUrl}`**: validate scheme is `http(s):` (block `javascript:`, `data:`, `vbscript:`); `<Link href>` (Next.js) and `<a href>` both are vectors when href comes from user data. URL allowlist for cross-origin nav
- [ ] **Open redirect**: `redirect(searchParams.get('returnTo'))` (Next.js Server Component) / `navigate(returnTo)` (React Router) without allowlist or relative-path-only check is an open redirect. Validate: `url.startsWith('/') && !url.startsWith('//')` and not a protocol-relative URL
- [ ] **`NEXT_PUBLIC_*` for secrets**: any `process.env.NEXT_PUBLIC_*` that names an API key, database URL, or signing secret is a critical finding - those compile into the client bundle and ship to every browser. Server-only secrets use unprefixed env vars and are accessed only from Server Components / Route Handlers / Server Actions / middleware
- [ ] **`'use server'` modules export only Server Actions**: a `"use server"` file that re-exports a non-action utility makes that utility a Server Action callable from the network. Each export must be a real Server Action with auth + validation; nothing else
- [ ] **JSON serialization of secrets to Client Components**: a Server Component fetching `prisma.user.findUnique({ where: { id } })` and passing the entire row as a prop to a Client Component serializes `passwordHash`, `mfaSecret`, etc. into the page HTML. Project to a DTO before passing the prop - or use Prisma `select` / `omit` (Prisma 5+) at the query layer
- [ ] **CSP set with sensible defaults**: `default-src 'self'`; `script-src 'self' 'nonce-XXX' 'strict-dynamic'`; `style-src 'self' 'unsafe-inline'` (Tailwind / cva accepts; trades XSS-via-CSS for ergonomics, document the choice); `img-src 'self' data: <CDN>`; `connect-src 'self' <API>`; `frame-ancestors 'none'`. Next.js 15+ supports `nonce` via `headers().get('x-nonce')` or middleware-injected
- [ ] **`unsafe-eval` / `unsafe-inline` for scripts**: not allowed in production CSP for `script-src`; any presence is a finding. Dev mode may need `unsafe-eval` for HMR - guard with `process.env.NODE_ENV !== 'production'`
- [ ] **`eval` / `new Function(string)` in client**: any occurrence is a critical finding; obfuscation libraries / template engines that use `new Function` (e.g., `lodash.template`) flagged
- [ ] **Prototype pollution via spread**: `Object.assign(target, JSON.parse(userInput))`, `{...defaults, ...userJson}` on data the client received - same risks as Node, in client code. Trust boundary is "data fetched from your API" vs "data from `URLSearchParams` / `postMessage` / external".
- [ ] **`postMessage` listeners validate origin**: `window.addEventListener('message', e => { if (e.origin !== EXPECTED) return; ... })` - missing origin check is universal XSS via parent / iframe
- [ ] **Third-party scripts**: every `<Script src="https://...">` (Next.js) / `<script src>` justified; SRI (`integrity` attribute) for any non-first-party script; analytics / chat widgets reviewed for what data they exfiltrate
- [ ] **Image / media `src` allowlist (Next.js)**: `next.config.js` `images.domains` / `remotePatterns` listed; flag changes that add a domain without justification (image proxy can be SSRF if not careful)
- [ ] **iframe sandbox**: any `<iframe>` rendering external content includes `sandbox="allow-scripts allow-same-origin..."` with the minimum allowlist; flag `<iframe src>` without `sandbox`
- [ ] **`window.opener` leak**: external `<a href target="_blank">` includes `rel="noopener noreferrer"`; Next.js `<Link>` is fine for internal links

### Step 9 - Data Protection

- [ ] **PII in client logs / Sentry**: Sentry browser SDK `beforeSend` strips known sensitive fields (`email`, `password`, `token`, `creditCard`); `Sentry.init({ sendDefaultPii: false })` (default but flag explicit `true`); `<Sentry.ErrorBoundary>` does not log entire props blobs
- [ ] **No tokens / passwords / PII in URLs**: search params and path params hit logs, browser history, referer headers; Server Actions and POST body are the right channels
- [ ] **`localStorage` / `sessionStorage` not used for tokens**: XSS-readable; cookies (`httpOnly`) for session, in-memory state for short-lived UI tokens
- [ ] **TLS enforcement**: `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` set via `next.config.js` `headers()` or hosting platform; HTTP redirected to HTTPS at the edge
- [ ] **Secrets management**: server env vars come from a secret store (Vault / AWS Secrets Manager / Doppler / hosting platform secrets); flagged any literal API key in `.env.local` checked into git; `.env.local` gitignored
- [ ] **Source maps in production**: hosting publishes source maps to Sentry but does not serve them publicly (`productionBrowserSourceMaps: false` in `next.config.js` unless intentionally serving)

## Rules

- Always validate at system boundaries: Server Action input, Route Handler body / query / params, `URLSearchParams`, `postMessage`, external API responses
- Never disable Server Action validation / middleware auth to silence a failing test - fix the test
- Never widen authorization (e.g., removing `auth()` from a Server Action, dropping middleware on a route) without an explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Default-deny via middleware allowlisting public routes; not denylisting protected ones

## Self-Check

**Verifiable from the diff (must check):**

- [ ] Stack confirmed as React; framework recorded before any framework-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); refs captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Security surface (auth config, middleware, changed Server Components / Server Actions / Route Handlers, components rendering HTML, CSP / headers config) read directly before applying checklists; prior revision consulted when guards or middleware were removed
- [ ] OWASP triage (Step 4) produced one signal verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] **Authorization drift sweep**: every new Server Action / Route Handler in the diff calls `auth()` and verifies object-level ownership when applicable
- [ ] Input validation reviewed for every changed Server Action / Route Handler; Zod / `zod-form-data` `.strict()` confirmed
- [ ] `dangerouslySetInnerHTML`, `href` / redirect targets, open-redirect, `'use server'` exports, `NEXT_PUBLIC_*` audited when the diff touches them
- [ ] CSP / security headers / cookie config reviewed when middleware or `next.config.js` headers changed
- [ ] Server Component → Client Component prop projection reviewed: no entire ORM rows passed; DTOs / `select`-projected fields only
- [ ] Severity rubric applied consistently (Critical / High / Medium / Low matches the rubric, not invented)
- [ ] Every finding includes an attack scenario, "regression risk" rationale (for missing-control gaps), or "topology-dependent" framing (for infra-flavored findings) - not just "input not validated"
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)

**Requires repo / infra access (check if visible, otherwise note as "could not verify from diff alone - flag for separate audit"):**

- [ ] Auth library config (NextAuth.js / Clerk / Lucia) reviewed - applies when auth module is in scope
- [ ] CSP / HSTS / security headers verified - applies when `next.config.js` `headers()` or middleware in scope
- [ ] Sentry browser SDK `beforeSend` strips PII - skip if Sentry init module not in diff
- [ ] `pnpm audit` / `npm audit` clean - run separately; this workflow does not execute tools

## Output Format

```markdown
## React Security Review Summary

**Stack Detected:** React <version> / TypeScript <version>
**Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
**Auth:** Auth.js (NextAuth) | Clerk | Lucia | iron-session | Custom | None (Vite + backend handles auth)
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture, calling out any React-specific risks like `NEXT_PUBLIC_` secret leak, missing Server Action input validation, ORM rows passed to Client Components, missing CSP, `dangerouslySetInnerHTML` on user input.]

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
- **Issue:** [vulnerability described in React terms - e.g., "Server Action `updateProfile` in app/account/actions.ts accepts `formData` directly into `prisma.user.update({ data: Object.fromEntries(formData) })` - mass-assignment lets a client submit `{ role: 'admin' }` and elevate privileges because there is no Zod schema enforcing the shape"]
- **Attack scenario:** [one of: (a) concrete exploit walkthrough; (b) "Regression risk: the next refactor silently removes one of these protections" — for missing-control gaps; (c) "Topology-dependent: depends on whether the CDN strips the X-Forwarded-Host header" — for infra-flavored findings. Pick one and label which.]
- **Severity rationale:** [tier] per rubric - [which clause from the Severity Rubric applies]
- **Fix:** [specific React remediation with code example - Zod schema for Server Action input, `nonce` in CSP, `DOMPurify.sanitize` wrapper, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `nonce`-based CSP via middleware", "Replace `localStorage` token with httpOnly cookie", "Migrate from Pages Router auth to Auth.js v5"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, or threat-model exercise worth spawning a subagent for). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Add Zod schema validation at top of `updateProfile` Server Action; whitelist `name`, `email`, `bio` only"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `pnpm audit` and upgrade flagged packages"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no security issues were found._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{role: 'admin'}` via FormData and gains admin via mass assignment because the Server Action lacks a Zod schema")
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending generic security advice when a React idiom applies (say "validate Server Action input with Zod", not "add input validation")
- Approving `dangerouslySetInnerHTML` on user input without a sanitizer
- Approving `NEXT_PUBLIC_*` for any secret - those ship to every browser
- Approving `localStorage` for auth tokens - XSS-readable; httpOnly cookies are the right primitive
- Approving `'use server'` files that export non-action utilities - every export becomes a network-callable Server Action
- Approving Server Components passing entire ORM rows as props to Client Components - `passwordHash` and other internal fields serialize into page HTML
- Approving `unsafe-eval` / `unsafe-inline` in production `script-src` CSP
- Approving `redirect(searchParams.get('next'))` without allowlist - open redirect
- Conflating security review with general code quality or performance review - delegate those to their workflows
- Treating client-side `if (user.role === 'admin')` as authorization - it is UX only; the server must enforce
- Recommending JWT in `localStorage` because "it's stateless" - the XSS exposure is the real cost
