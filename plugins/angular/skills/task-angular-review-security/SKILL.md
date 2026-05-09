---
name: task-angular-review-security
description: Angular security review for XSS via `[innerHTML]` and `bypassSecurityTrust*`, CSP, auth via functional guards / interceptors, token storage, open redirect via `Router.navigateByUrl`, `environment.ts` secret leaks, SSR data exposure, CSRF on cookie-session apps, and Angular-aware OWASP. Stack-specific override of task-code-review-security, invoked when stack-detect resolves to Angular.
agent: angular-security-engineer
metadata:
  category: frontend
  tags: [angular, typescript, signals, security, xss, csp, owasp, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Angular Security Review

## Purpose

Angular-aware security review that names `[innerHTML]` (XSS surface), `DomSanitizer.bypassSecurityTrust*` (escape hatch around Angular's auto-sanitization), Content Security Policy, functional auth guards (`CanActivateFn` / `CanMatchFn`) backed by server checks, functional HTTP interceptors (`HttpInterceptorFn`) for token injection / CSRF, `environment.ts` secret leakage (compiled into client bundle), open redirect via `Router.navigateByUrl(userInput)`, SSR data exposure (`TransferState` / hydration payload leaking ORM rows into HTML), token storage (httpOnly cookie vs `localStorage`), and Angular-specific risks (template injection via `bypassSecurityTrustHtml`, prototype pollution via spread, JSON serialization of secrets through SSR payload) directly instead of routing through the generic frontend security adapter. Produces findings with attack scenarios and concrete remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for Angular. The core workflow's contract (invocation, diff resolution, output format) is preserved.

## When to Use

- Reviewing an Angular PR for security regressions
- Pre-deployment hardening pass on auth, file upload, payment, or PII-handling routes
- Periodic CSP / interceptor / guard validation drift sweep
- Auditing a new functional interceptor, new guard, or new auth flow

**Not for:**

- Performance review (use `task-code-review-perf` or `task-angular-review-perf`)
- General code review (use `task-code-review` or `task-angular-review`)
- Production incident triage (use `/task-oncall-start`)
- Backend API security review for the API the Angular app calls (run that against the backend repo)

**Depth.** This workflow always runs at full depth - there is no `quick` / `standard` / `deep` knob. Security review has cliff-edged consequences (XSS → account takeover, exposed secrets) that do not benefit from a "light" mode.

## Severity Rubric

Use these definitions to keep severity consistent across runs - do not invent your own scale.

| Severity     | Definition                                                                                                                                                                                                                                                                                                  |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Working XSS on a production code path (`[innerHTML]` on user input without sanitizer, `bypassSecurityTrustHtml` on user content), secret committed to client bundle (`environment.ts` for an API key with privileged scope), authentication bypass (route reachable without backend check), mass exfiltration via SSR `TransferState` / hydration payload returning entire ORM rows. Blocks merge. |
| **High**     | Missing input validation on a critical client-side surface, missing auth guard on a privileged route (UX gate only - server must enforce too, but the missing UX gate signals lack of defense in depth), IDOR via path param without ownership check on the backend (raise as cross-cutting), open redirect via unchecked `Router.navigateByUrl(userInput)`, CSRF on cookie-session form. Must fix before merge. |
| **Medium**   | Hardening gap with mitigating control (CSP missing nonce but `unsafe-inline` for styles only and no untrusted HTML rendered), weak rate limit on auth route, Sentry collecting PII without redaction. Should fix this PR or the next one.                                                                  |
| **Low**      | Defense-in-depth nice-to-have, dependency advisory below actively-exploited threshold, hardening recommendations without a concrete current attack scenario.                                                                                                                                                |

**Combined-finding rule.** When two or more findings *compose* on the same code path into a worse threat than either alone, file them as a single finding at the elevated severity and cite each component. Examples:

- Missing `CanActivateFn` on a privileged route (High, alone) + `[innerHTML]` on user-controlled input from the same component without sanitizer (High, alone) on the *same component / route* = **Critical** unauth XSS reaching every viewer (anyone navigates to the unguarded route, the page renders attacker-controlled HTML, and the payload runs in every visitor's browser).
- `bypassSecurityTrustHtml(userInput)` (Critical, alone, by rubric) + the binding rendered on a route reachable from unauthenticated users (High, alone) on the *same component* = **Critical** unauth XSS - cite both because the second piece tells the reader the exploit lands without login.
- Missing functional auth interceptor token-scoping (High, alone) + token stored in `localStorage` (High, alone) on the *same auth flow* = **Critical** token exfiltration via attacker-controlled host (the unscoped interceptor sends `Authorization` to a third-party URL the attacker controls; XSS-readable storage compounds the impact when combined with `[innerHTML]` elsewhere).
- SSR `TransferState` populated with a full ORM row including `passwordHash` (Critical, alone, by rubric) + the page reachable without auth on the SSR server (High, alone) = **Critical** mass exfiltration via hydration payload (every cold visit returns the row in HTML).
- Missing `CanMatchFn` on a lazy admin route (High, alone) + `environment.ts` containing the admin API key (Critical, alone, by rubric) on the *same route bundle* = **Critical** the lazy chunk loads to anyone, exposing the admin client ID + key from the bundle even before backend auth fires.
- Open redirect via `Router.navigateByUrl(query.returnTo)` (High, alone) + the redirect target receiving session cookie due to `SameSite=Lax` (High, alone) on the *same auth callback* = **Critical** session-token theft via attacker-controlled redirect.
- `[innerHTML]` on user input (High, alone) + a custom sanitizer that returns `bypassSecurityTrustHtml` for "trusted" markdown without verifying the trust boundary (High, alone) on the *same content pipeline* = **Critical** working XSS (the bypass swallows the sanitizer's protection).

The rule of thumb: if the realistic exploit path requires both findings to land for the attack to succeed, they are one finding. If either finding is exploitable on its own, file them separately at their independent severities.

**Same-handler co-location.** Combining findings requires confirming both land on the *same code path* (same component, same route segment with shared guards / providers, same auth flow). When the diff doesn't make co-location obvious - e.g., the `[innerHTML]` is in `OrderDetailComponent` but the missing auth guard protects a different route segment - file the findings separately at their independent severities and add a one-line `Note: Combined-finding rule applies if both land on the same route / component; verify and merge before merge` to the lower-severity entry. Do not silently merge or silently keep separate.

## Invocation

Mirrors `task-code-review-security`:

| Invocation                               | Meaning                                                                                               |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-angular-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-angular-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-angular-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-security` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Configuration

Use skill: `stack-detect` to confirm Angular. If the detected stack is not Angular, stop and tell the user to invoke `/task-code-review-security` instead.

Detect: Angular major version, SSR enabled (`@angular/ssr` + `provideClientHydration`), auth library (`@auth0/auth0-angular`, `angular-oauth2-oidc`, `keycloak-angular`, `msal-angular`, custom). Record `Angular: <version>`, `SSR: enabled | disabled`, `Auth: ...`. Each step branches on these signals where the idiom differs - SSR introduces server-side data exposure surface; client-only Angular apps rely entirely on a separate backend for auth enforcement.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-security` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Security Surface

Before applying the OWASP and authn/authz checklists, open the files that actually wire security so findings cite real lines:

- Every changed `*.component.ts` / `*.component.html` - `[innerHTML]`, sanitizer use, navigation calls
- Every changed `*.guard.ts` / `*.resolver.ts` / `*.routes.ts` - functional guards (`CanActivateFn`, `CanMatchFn`), route configuration
- Every changed `*.interceptor.ts` - functional interceptors (`HttpInterceptorFn`) for auth, CSRF, error handling
- Every changed `*.service.ts` - HTTP calls, token handling, navigation logic
- `app.config.ts` / `app.config.server.ts` - `provideHttpClient(withInterceptors([...]))`, `provideRouter`, security-relevant providers
- `environment.ts` / `environment.prod.ts` - flag any entry that names a privileged secret
- `index.html` - CSP via `<meta>`, security headers
- `angular.json` - source map publishing, build config
- `package.json` for `@auth0/auth0-angular` / `angular-oauth2-oidc` / `keycloak-angular`, `dompurify` / sanitization libraries
- For SSR projects: `server.ts` / `app.config.server.ts` - server-side data flow, `TransferState` use

When the diff removes a CSP rule, removes a sanitizer call, removes / weakens a guard or interceptor, also `git log -p` the prior revision of those lines to confirm what was protected before.

### Step 4 - OWASP Triage (Angular Lens)

This step is a **triage pass**, not a separate findings list. Run through the OWASP categories below and produce a single output: a list of categories that show signal in this diff (e.g., `Broken Access Control: yes`, `XSS: yes`, `Cryptographic Failures: no signal in diff`). Steps 5-9 then produce the actual findings; do **not** repeat them here.

| Risk                          | Angular-specific check                                                                                                                                                                                                                  |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Functional guards (`CanActivateFn` / `CanMatchFn`) on protected routes; backend enforces independently; HTTP interceptor injects auth token only for own-origin requests                                                                |
| Injection                     | URL params validated before HTTP calls; ORM concerns are backend (cross-link); `JSON.parse(userInput)` flowing into objects audited                                                                                                     |
| XSS                           | Angular auto-escapes `{{ }}` interpolations; `[innerHTML]` only with sanitized HTML; `bypassSecurityTrust*` audited; markdown renderer disables raw HTML or sanitizes; CSP set with `nonce` for scripts                                |
| Cryptographic Failures        | No client-side crypto for security boundaries (client-side bcrypt is theatre); JWT verification belongs on the server; secrets sourced from build-injected env vars not committed                                                       |
| Security Misconfiguration     | CSP set via server / hosting platform headers (not just `<meta>`); `Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` set; `X-Frame-Options: DENY` or CSP `frame-ancestors`                |
| SSRF                          | Cross-link to backend API audit; client-side does not initiate SSRF                                                                                                                                                                     |
| Insecure Design (A04)         | Default-deny: route guards check by default; `CanMatchFn` for path-level gating; backend default-deny for endpoints                                                                                                                     |
| Vulnerable Components (A06)   | `npm audit` / `pnpm audit` clean for High/Critical; Dependabot active                                                                                                                                                                   |
| Data Integrity Failures (A08) | `JSON.parse` on untrusted bounded; `eval` / `new Function` flagged - any occurrence is critical                                                                                                                                         |
| Logging & Monitoring (A09)    | Sentry Angular SDK `beforeSend` strips PII; client logs do not include `password`, `token`, `authorization`                                                                                                                             |

### Step 5 - Authentication

**Angular SPA + separate backend (most common):**

- [ ] **Auth library chosen and consistent**: `@auth0/auth0-angular` / `angular-oauth2-oidc` / `keycloak-angular` / `msal-angular` / custom - one path through the codebase, not mixed
- [ ] **Functional `CanActivateFn` / `CanMatchFn` guards**: new guards use the functional form (`export const authGuard: CanActivateFn = (route, state) => { ... }`); class-based guards in new code are a [Medium] - functional is the modern idiom and works with `provideRouter` cleanly
- [ ] **Guards are UX, not authorization**: `CanActivateFn` redirects unauthenticated users to login - that is UX. The backend must independently enforce auth on every protected endpoint. A guard without a backend check is a [High] when the surface contains privileged data
- [ ] **`CanMatchFn` for lazy-loaded guards**: `CanMatchFn` runs before the route matches and prevents the lazy chunk from loading at all (better than `CanActivateFn` which loads the chunk first and then redirects). Flag protected lazy routes using `CanActivate` instead of `CanMatch`
- [ ] **Token in interceptor**: auth token attached via `HttpInterceptorFn` - flag direct `Authorization` header set in component / service
- [ ] **Interceptor scopes token to own origin**: `HttpInterceptorFn` checks `req.url` is same-origin or in an allowlist before adding `Authorization` header. Sending the token to a third-party URL leaks credentials; flag interceptors that add token unconditionally
- [ ] **Token storage**: prefer `httpOnly` cookies set by the backend; if a token must live in JS, document the XSS-recovery story (token rotation, short TTL, refresh via httpOnly cookie). Flag tokens stored in `localStorage` (XSS-readable; a single `[innerHTML]` exploit exfiltrates the token)
- [ ] **No client-side authorization decisions**: `if (user.role === 'admin') showAdminButton` is fine for UX; `if (user.role === 'admin') fetchAdminData()` is **not** a security control - the backend must reject. Flag any client-side guard not backed by a server check
- [ ] **Refresh token flow**: refresh via httpOnly cookie POST to backend; never store refresh token in JS
- [ ] **OAuth callback validation**: `state` / `nonce` validated; redirect URL allowlist; flag custom OAuth implementations that skip these. `angular-oauth2-oidc` does this correctly when used via library API
- [ ] **`environment.ts` for client identifiers**: OAuth client ID is a public token by design; flag only client _secrets_ (never appropriate in a SPA) or DSN-style values that are actually privileged

**Angular SSR (server runs Node, has its own auth surface):**

- [ ] **SSR server does not authenticate the user from server-side context**: cookies pass through SSR, but server-rendered output is shared; flag SSR templates that render per-user data without verifying the cookie / token on the server-side fetch (otherwise per-user content lands in the SSR cache)
- [ ] **`TransferState` / hydration payload does not leak server-only data**: a server-side resolver fetching `prisma.user.findUnique({ where })` and storing the entire row in `TransferState` serializes into the HTML payload. Flag for DTO projection (`select: { id, name, email }`) at the data layer

### Step 6 - Authorization

- [ ] **Client-side route guards mirror the server**: `CanActivateFn` redirect is for UX; the backend / API must enforce authorization independently for the protected resource
- [ ] **Role checks**: when `CanActivateFn` is role-gated, the role comes from a **server-validated session / JWT** (parsed in the auth library), never from a request body / search param / header / client-provided claim that has not been verified server-side
- [ ] **Per-tenant isolation**: multi-tenant apps scope queries by `tenantId` derived from the session; not from the URL. The backend enforces; the Angular app passes through the tenant context for routing UX
- [ ] **CSRF**: for session-cookie auth (not bearer tokens), state-changing requests must include a CSRF token or use `SameSite=Strict/Lax` cookies. Angular's `withXsrfConfiguration` (in `provideHttpClient`) reads `XSRF-TOKEN` cookie and sets `X-XSRF-TOKEN` header automatically - flag projects with cookie-session auth that haven't enabled it. Flag bearer-token apps that have it enabled unnecessarily

### Step 7 - Input Validation and Form Handling

- [ ] **Reactive Forms with validators**: every form uses `FormBuilder` / typed `FormGroup<{...}>` with `Validators.*` and custom validators. Flag template-driven forms in new code unless project-wide convention
- [ ] **Server validation is the source of truth**: client-side validators are UX; the backend re-validates. Flag any client-only validation for security-sensitive fields (e.g., role assignment, price)
- [ ] **`URLSearchParams` / route params validated**: route param consumption (`route.params.id` / `inject(ActivatedRoute).snapshot.params['id']`) validated for shape (UUID, integer, slug pattern) before passing to `HttpClient` calls. Backend re-validates; client-side check is UX
- [ ] **`JSON.parse(userInput)` flowing into objects**: any `JSON.parse` on data from URL params / `postMessage` / external sources spread into a service call is a mass-assignment + prototype-pollution surface. Validate via Zod / typed parser before use
- [ ] **No `[innerHTML]` on untrusted strings**: any `[innerHTML]="x"` where `x` originates from user input, URL params, or external API must be sanitized via `DomSanitizer.sanitize(SecurityContext.HTML, x)` (which strips dangerous tags) - never `[innerHTML]="markdownService.render(userInput)"` without a sanitizer
- [ ] **File uploads: type / size / content validated**: client-side checks on `<input type="file">` are UX; backend must validate `File.size`, MIME inferred from content (not `file.type` which is client-controlled). Flag client-only validation for file uploads

### Step 8 - Common Angular Vulnerability Patterns

- [ ] **`[innerHTML]` audit**: every site must have either a sanitizer in the chain, a code comment justifying why the input is trusted (e.g., "static markdown from the repo, processed at build time"), or use of Angular's `MarkdownPipe` / similar with sanitization on. Never `[innerHTML]="userMarkdown"` without `DomSanitizer.sanitize(SecurityContext.HTML, ...)`. Note Angular's default sanitization on `[innerHTML]` strips scripts but allows attributes - it is not a substitute for a hardened sanitizer like DOMPurify on user content
- [ ] **`bypassSecurityTrustHtml` / `bypassSecurityTrustResourceUrl` / `bypassSecurityTrustScript` / `bypassSecurityTrustStyle` / `bypassSecurityTrustUrl` audit**: every call has a comment justifying why the input is trusted (build-time content, internal config, etc.). `bypassSecurityTrustHtml(userInput)` is Critical - that's an explicit XSS opt-in. `bypassSecurityTrustResourceUrl` is the iframe / object src vector
- [ ] **`[href]` / `[src]` / `[routerLink]` from user-controlled URL**: validate scheme is `http(s):` (block `javascript:`, `data:`, `vbscript:`); `<a [href]>` is an XSS vector when href comes from user data with the wrong protocol. URL allowlist for cross-origin nav
- [ ] **Open redirect**: `Router.navigateByUrl(query.returnTo)` / `window.location.href = userInput` without allowlist or relative-path-only check is an open redirect. Validate: `url.startsWith('/') && !url.startsWith('//')` and not a protocol-relative URL
- [ ] **`environment.ts` / `environment.prod.ts` for secrets**: any `environment.X` that names an API key with privileged scope, database URL, or signing secret is a Critical finding - these compile into the client bundle and ship to every browser. Server-only secrets live in build-time-injected env vars on the SSR server, never in the client `environment.ts`
- [ ] **SSR `TransferState` leak**: a server-side `Resolver` / signal init populating `TransferState` with `prisma.user.findUnique({ where })` serializes the entire row (including `passwordHash`, `mfaSecret`) into the HTML payload visible to any client. Project to a DTO at the data-fetch layer
- [ ] **CSP set with sensible defaults**: `default-src 'self'`; `script-src 'self' 'nonce-XXX' 'strict-dynamic'`; `style-src 'self' 'unsafe-inline'` (Angular Material / scoped styles need; document the trade); `img-src 'self' data: <CDN>`; `connect-src 'self' <API>`; `frame-ancestors 'none'`. Angular SSR / hosting platform delivers via response headers; flag CSP delivered only via `<meta>` (cannot enforce `frame-ancestors`, `report-uri`, `sandbox`)
- [ ] **CSP wildcards**: `default-src *` or `script-src *` is effectively no CSP. Any wildcard host in `script-src` / `connect-src` / `frame-src` is a finding
- [ ] **`unsafe-eval` / `unsafe-inline` for scripts**: not allowed in production CSP for `script-src`. Angular AOT-compiled apps do not require `unsafe-eval` (templates compile to render functions at build time); JIT compilation does. Flag JIT mode in production
- [ ] **`eval` / `new Function(string)` in client**: any occurrence is a critical finding; obfuscation libraries / template engines that use `new Function` flagged
- [ ] **Prototype pollution via spread**: `Object.assign(target, JSON.parse(userInput))`, `{...defaults, ...userJson}` on data the client received - flag when input source is user-controlled
- [ ] **`window.addEventListener('message')` validates origin**: missing origin check is universal XSS via parent / iframe
- [ ] **Third-party scripts**: every dynamically-loaded script (`document.createElement('script')`) justified; SRI (`integrity` attribute) required for any non-first-party script regardless of how it loads - statically declared in `index.html` (`<script src="https://cdn.example.com/widget.js">`) or dynamically injected at runtime; analytics / chat widgets reviewed for what data they exfiltrate
- [ ] **iframe sandbox**: any `<iframe>` rendering external content includes `sandbox="allow-scripts allow-same-origin..."` with the minimum allowlist; flag `<iframe [src]>` without `sandbox`
- [ ] **iframe `[src]` from user input**: `<iframe [src]="query.embed">` is a phishing / clickjacking surface even with `sandbox`. Validate against an allowlist of expected hosts
- [ ] **`window.opener` leak**: external `<a [href] target="_blank">` includes `rel="noopener noreferrer"`; internal `[routerLink]` is fine

### Step 9 - Data Protection

- [ ] **PII in client logs / Sentry**: Sentry Angular SDK `beforeSend` strips known sensitive fields (`email`, `password`, `token`, `creditCard`); `Sentry.init({ sendDefaultPii: false })` (default but flag explicit `true`); error handlers do not log entire form values
- [ ] **No tokens / passwords / PII in URLs**: search params and path params hit logs, browser history, referer headers; POST body to backend is the right channel
- [ ] **`localStorage` / `sessionStorage` not used for tokens**: XSS-readable; cookies (`httpOnly`) for session, in-memory state (a service signal) for short-lived UI tokens
- [ ] **TLS enforcement**: `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` set via hosting platform / response headers; HTTP redirected to HTTPS at the edge
- [ ] **Secrets management**: build-injected env vars come from a secret store (Vault / AWS Secrets Manager / Doppler / hosting platform secrets); flag any literal API key in `environment.ts` checked into git
- [ ] **Source maps in production**: `angular.json` `"sourceMap": false` for production (or upload-then-strip via Sentry plugin); public source maps leak source-code structure


### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Rules

- Always validate at system boundaries: route params, `URLSearchParams`, `postMessage`, file inputs, external API responses
- Never disable Angular's auto-sanitization (`bypassSecurityTrust*`) without a comment justifying why
- Never widen authorization (e.g., removing a `CanActivateFn` from a route) without an explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Default-deny via route guards; client UX gate complements (does not replace) backend enforcement

## Self-Check

**Verifiable from the diff (must check):**

- [ ] Stack confirmed as Angular; version, SSR status, auth library recorded before any configuration-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); refs captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Security surface (auth config, interceptors, guards, changed components / services / `environment.ts`, components rendering HTML, CSP / headers config) read directly before applying checklists; prior revision consulted when guards or interceptors were removed / weakened
- [ ] OWASP triage (Step 4) produced one signal verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] Authentication checked: functional guards used in new code, token in interceptor (not component), interceptor scopes token to own origin, token storage (httpOnly cookie preferred)
- [ ] Authorization: `CanMatchFn` for lazy routes, role checks from server-validated session, CSRF for cookie-session apps via `withXsrfConfiguration`
- [ ] Input validation reviewed for forms, route params, file uploads; client-only validation for security-sensitive fields flagged
- [ ] `[innerHTML]`, `bypassSecurityTrust*`, `[href]` / `[src]` / `[routerLink]` user-controlled, open redirect, `environment.ts` secret leak audited when the diff touches them
- [ ] CSP / security headers / cookie config reviewed when delivered via SSR server / hosting; CSP delivery channel (header vs `<meta>`), wildcards, sanitizer config audited
- [ ] SSR `TransferState` / hydration payload reviewed for ORM-row leakage when SSR is enabled
- [ ] Severity rubric applied consistently (Critical / High / Medium / Low matches the rubric, not invented); Combined-finding rule applied where two findings compose on the same component / route segment / auth flow
- [ ] Every finding includes an attack scenario, "regression risk" rationale (for missing-control gaps), or "topology-dependent" framing (for infra-flavored findings)
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)

**Requires repo / infra access (check if visible, otherwise note as "could not verify from diff alone - flag for separate audit"):**

- [ ] Auth library config (`@auth0/auth0-angular` / `angular-oauth2-oidc` / etc.) reviewed - applies when auth module is in scope
- [ ] CSP / HSTS / security headers verified - applies when SSR server / hosting platform headers in scope
- [ ] Sentry Angular SDK `beforeSend` strips PII - skip if Sentry init module not in diff
- [ ] `npm audit` / `pnpm audit` clean - run separately; this workflow does not execute tools
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Angular Security Review Summary

**Stack Detected:** Angular <version> / TypeScript <version>
**SSR:** enabled | disabled
**Auth:** @auth0/auth0-angular | angular-oauth2-oidc | keycloak-angular | msal-angular | custom | none (backend handles auth)
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture, calling out any Angular-specific risks like `bypassSecurityTrustHtml` on user input, `environment.ts` secret leak, missing functional interceptor token scoping, ORM rows in SSR `TransferState`, missing CSP, `[innerHTML]` on user input.]

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
- **Issue:** [vulnerability described in Angular terms - e.g., "Component `OrderDetailComponent` in src/app/orders/order-detail.component.html:23 binds `[innerHTML]="order.description"` where `order.description` originates from the public `/api/orders/:id` endpoint and is user-controllable - any user submitting `<img src=x onerror=alert(1)>` triggers XSS in every viewer's browser since Angular's auto-sanitization on `[innerHTML]` strips scripts but the `bypassSecurityTrustHtml` wrapper in `OrderService.getOrder()` opts out of sanitization"]
- **Attack scenario:** [one of: (a) concrete exploit walkthrough; (b) "Regression risk: the next refactor silently removes one of these protections" - for missing-control gaps; (c) "Topology-dependent: depends on whether the CDN strips the X-Forwarded-Host header" - for infra-flavored findings. Pick one and label which.]
- **Severity rationale:** [tier] per rubric - [which clause from the Severity Rubric applies]
- **Fix:** [specific Angular remediation with code example - remove `bypassSecurityTrustHtml`, sanitize via `DomSanitizer.sanitize(SecurityContext.HTML, ...)` or `DOMPurify`, replace `[innerHTML]` with `{{ }}` interpolation if HTML is not needed, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `nonce`-based CSP via SSR server response headers", "Replace `localStorage` token with httpOnly cookie", "Migrate ad-hoc auth to `angular-oauth2-oidc`"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, or threat-model exercise worth spawning a subagent for). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Remove `bypassSecurityTrustHtml` from src/app/orders/order.service.ts:18 and switch the binding to `{{ description }}` interpolation; if formatted HTML is required, sanitize via `DomSanitizer.sanitize(SecurityContext.HTML, raw)`"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `pnpm audit` and upgrade flagged packages"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no security issues were found._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `<img onerror=...>` via order description, sanitization is bypassed by `bypassSecurityTrustHtml`, every viewer's browser executes the payload")
- Skipping OWASP categories that appear clean - explicitly state "no signal in diff" per category
- Recommending generic security advice when an Angular idiom applies (say "remove `bypassSecurityTrustHtml` and sanitize via `DomSanitizer.sanitize(SecurityContext.HTML, ...)`", not "add input validation")
- Approving `[innerHTML]` on user input without a sanitizer
- Approving `bypassSecurityTrust*` for user-controlled content - that is an explicit XSS opt-in
- Approving `environment.ts` for any privileged secret - those ship to every browser
- Approving `localStorage` for auth tokens - XSS-readable; httpOnly cookies are the right primitive
- Approving SSR `TransferState` populated with full ORM rows - hydration payload serializes them into HTML
- Approving `unsafe-eval` / `unsafe-inline` in production `script-src` CSP
- Approving `Router.navigateByUrl(query.next)` without allowlist - open redirect
- Conflating security review with general code quality or performance review - delegate those to their workflows
- Treating client-side `*ngIf="user.role === 'admin'"` as authorization - it is UX only; the server must enforce
- Recommending JWT in `localStorage` because "it's stateless" - the XSS exposure is the real cost
