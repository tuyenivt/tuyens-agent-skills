---
name: task-angular-review-security
description: Angular security review: XSS via innerHTML/bypassSecurityTrust, CSP, functional guards/interceptors, token storage, open redirect, SSR, CSRF.
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

Angular-aware security review covering `[innerHTML]` / `bypassSecurityTrust*` XSS surfaces, CSP, functional `CanActivateFn` / `CanMatchFn` guards backed by server checks, `HttpInterceptorFn` token-scoping and CSRF, `environment.ts` secret leakage into the client bundle, open redirect via `Router.navigateByUrl`, SSR data exposure via `TransferState` / hydration payload, token storage, and prototype pollution. Stack-specific delegate of `task-code-review-security`; preserves its invocation, diff-resolution, and output contract.

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

**Combined-finding rule.** When two or more findings *compose* on the same code path (same component, same route segment with shared guards / providers, same auth flow) into a worse threat than either alone, file them as one finding at the elevated severity and cite each component. Rule of thumb: if the exploit requires both to land, it's one finding; if either is exploitable alone, file separately.

Illustrative compositions:

- Missing `CanActivateFn` on a privileged route + `[innerHTML]` on user-controlled input in that component = Critical unauth XSS to every viewer.
- Missing interceptor token-scoping + token in `localStorage` on the same auth flow = Critical token exfiltration (`Authorization` sent to attacker host; XSS-readable storage compounds).
- SSR `TransferState` populated with full ORM row + page reachable without auth = Critical mass exfiltration via hydration payload.

**Co-location check.** When the diff doesn't make co-location obvious, file findings separately at their independent severities and add `Note: Combined-finding rule applies if both land on the same route / component; verify before merge` to the lower-severity entry. Do not silently merge or silently keep separate.

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

Use skill: `stack-detect` to confirm Angular. If invoked as a delegate of `task-code-review-security` or as a subagent of `task-angular-review` (parent already detected Angular), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Angular, stop and tell the user to invoke `/task-code-review-security` instead.

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

- [ ] **Auth library consistent**: one path (`@auth0/auth0-angular` / `angular-oauth2-oidc` / `keycloak-angular` / `msal-angular` / custom), not mixed
- [ ] **Functional guards**: new code uses `CanActivateFn` / `CanMatchFn`; class-based guards in new code are [Medium]
- [ ] **`CanMatchFn` for lazy routes**: `CanMatchFn` blocks the chunk from loading; `CanActivateFn` only redirects after load. Flag protected lazy routes using `CanActivate`
- [ ] **Guards are UX, not authorization**: backend must enforce on every protected endpoint. A guard without a backend check on privileged data is [High]
- [ ] **No client-side authorization decisions**: `*ngIf="user.role === 'admin'"` is UX only; `if (role === 'admin') fetchAdminData()` is not a security control. Backend must reject
- [ ] **Token in interceptor, scoped to own origin**: `HttpInterceptorFn` attaches `Authorization`; checks `req.url` is same-origin / allowlisted before adding. Flag direct headers in components / services and unconditional attachment
- [ ] **Token storage**: prefer `httpOnly` cookies. Flag tokens in `localStorage` / `sessionStorage` (XSS-readable - any `[innerHTML]` exploit exfiltrates). If JS storage is unavoidable, document rotation + short TTL + httpOnly refresh
- [ ] **Refresh token**: via httpOnly cookie POST; never in JS
- [ ] **OAuth callback validation**: `state` / `nonce` validated; redirect URL allowlisted. `angular-oauth2-oidc` library API handles this; flag custom implementations that skip
- [ ] **`environment.ts` identifiers**: OAuth client ID is public by design - flag only privileged secrets (client secrets, signing keys, DSNs with write scope)

**Angular SSR (Node server, separate auth surface):**

- [ ] **No shared per-user SSR cache**: SSR templates rendering per-user data must verify cookie / token on the server-side fetch (otherwise per-user content leaks into SSR cache)
- [ ] **`TransferState` / hydration payload**: server resolvers must project to a DTO (`select: { id, name, email }`) - never serialize entire ORM rows into the HTML payload

### Step 6 - Authorization

- [ ] **Client-side route guards mirror the server**: `CanActivateFn` redirect is for UX; the backend / API must enforce authorization independently for the protected resource
- [ ] **Role checks**: when `CanActivateFn` is role-gated, the role comes from a **server-validated session / JWT** (parsed in the auth library), never from a request body / search param / header / client-provided claim that has not been verified server-side
- [ ] **Per-tenant isolation**: multi-tenant apps scope queries by `tenantId` derived from the session; not from the URL. The backend enforces; the Angular app passes through the tenant context for routing UX
- [ ] **CSRF**: for session-cookie auth (not bearer tokens), state-changing requests must include a CSRF token or use `SameSite=Strict/Lax` cookies. Angular's `withXsrfConfiguration` (in `provideHttpClient`) reads `XSRF-TOKEN` cookie and sets `X-XSRF-TOKEN` header automatically - flag projects with cookie-session auth that haven't enabled it. Flag bearer-token apps that have it enabled unnecessarily

### Step 7 - Input Validation and Form Handling

- [ ] **Reactive Forms with validators**: typed `FormGroup<{...}>` + `Validators.*`. Flag template-driven forms in new code unless project convention
- [ ] **Server validation is source of truth**: client validators are UX; backend re-validates. Flag client-only validation on security-sensitive fields (role, price, tenant)
- [ ] **Route params validated**: `inject(ActivatedRoute).snapshot.params['id']` checked for shape (UUID / integer / slug) before reaching `HttpClient`. Backend re-validates
- [ ] **`JSON.parse(userInput)` into objects**: parsing user JSON and spreading into a service call is a mass-assignment + prototype-pollution surface. Validate via Zod / typed parser
- [ ] **`[innerHTML]` on untrusted strings**: must pass through `DomSanitizer.sanitize(SecurityContext.HTML, x)`; never `[innerHTML]="markdownService.render(userInput)"` without it (see Step 8)
- [ ] **File uploads**: client checks on `<input type="file">` are UX. Backend must validate size and MIME inferred from content (not `file.type`, which is client-controlled)

### Step 8 - Common Angular Vulnerability Patterns

- [ ] **`[innerHTML]` audit**: every binding has a sanitizer in the chain or a comment justifying trusted input. Angular's default sanitization strips scripts but is not a substitute for DOMPurify on user content. Never `[innerHTML]="userMarkdown"` without `DomSanitizer.sanitize(SecurityContext.HTML, ...)`
- [ ] **`bypassSecurityTrust*` audit**: every call (`Html` / `ResourceUrl` / `Script` / `Style` / `Url`) has a comment justifying trust. `bypassSecurityTrustHtml(userInput)` is Critical (explicit XSS opt-in); `bypassSecurityTrustResourceUrl` is the iframe / object-src vector
- [ ] **`[href]` / `[src]` / `[routerLink]` from user URL**: validate scheme is `http(s):` (block `javascript:`, `data:`, `vbscript:`); allowlist hosts for cross-origin nav
- [ ] **Open redirect**: `Router.navigateByUrl(query.returnTo)` / `window.location.href = userInput` requires `url.startsWith('/') && !url.startsWith('//')` (block protocol-relative) or an explicit allowlist
- [ ] **`environment.ts` secrets**: any entry naming a privileged API key, DB URL, or signing secret is Critical - these compile into the client bundle. Server-only secrets live in build-time env vars on the SSR server
- [ ] **SSR `TransferState` leak**: a server resolver populating `TransferState` with `prisma.user.findUnique(...)` serializes the row (including `passwordHash`, `mfaSecret`) into the HTML payload. Project to a DTO at the data-fetch layer
- [ ] **CSP defaults**: `default-src 'self'`; `script-src 'self' 'nonce-XXX' 'strict-dynamic'`; `style-src 'self' 'unsafe-inline'` (document the Angular Material trade); `img-src 'self' data: <CDN>`; `connect-src 'self' <API>`; `frame-ancestors 'none'`. Delivered via response headers; CSP via `<meta>` alone cannot enforce `frame-ancestors` / `report-uri` / `sandbox`
- [ ] **CSP wildcards / unsafe-eval / unsafe-inline**: any wildcard host in `script-src` / `connect-src` / `frame-src` is a finding; `unsafe-eval` / `unsafe-inline` not allowed in production `script-src` (AOT does not need `unsafe-eval`; flag JIT in production)
- [ ] **`eval` / `new Function(string)`**: any occurrence is Critical; flag template engines / obfuscators that rely on `new Function`
- [ ] **Prototype pollution**: `Object.assign(target, JSON.parse(userInput))` or `{...defaults, ...userJson}` on user-controlled input
- [ ] **`window.addEventListener('message')` origin check**: missing origin check is universal XSS via parent / iframe
- [ ] **Third-party scripts**: every dynamically-loaded script justified; SRI (`integrity`) required for non-first-party scripts (static or dynamic); analytics / chat widgets reviewed for data exfiltration
- [ ] **iframe sandbox + `[src]`**: external `<iframe>` includes minimum-allowlist `sandbox`; `<iframe [src]="query.embed">` requires host allowlist even with sandbox
- [ ] **`window.opener` leak**: external `<a [href] target="_blank">` includes `rel="noopener noreferrer"`

### Step 9 - Data Protection

- [ ] **PII in client logs / Sentry**: `Sentry.init({ sendDefaultPii: false })` and `beforeSend` strip `email` / `password` / `token` / `creditCard`; error handlers do not log entire form values
- [ ] **No tokens / passwords / PII in URLs**: search and path params hit logs, history, referer; use POST body
- [ ] **TLS enforcement**: `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` via response headers; HTTP redirected to HTTPS at the edge
- [ ] **Secrets management**: build-injected env vars come from a secret store (Vault / Secrets Manager / Doppler / hosting); flag literal keys in `environment.ts` in git
- [ ] **Production source maps**: `angular.json` `"sourceMap": false` (or upload-then-strip via Sentry plugin)

### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write the assembled review to the report file before ending; print the confirmation line.

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
