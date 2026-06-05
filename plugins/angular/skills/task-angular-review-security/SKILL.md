---
name: task-angular-review-security
description: Angular security review - XSS via innerHTML/bypassSecurityTrust, CSP, guards, interceptors, token storage, SSR, CSRF.
agent: angular-security-engineer
metadata:
  category: frontend
  tags: [angular, typescript, signals, security, xss, csp, owasp, workflow]
  type: workflow
user-invocable: true
---

# Angular Security Review

Angular-aware security review covering `[innerHTML]` / `bypassSecurityTrust*` XSS, CSP, functional `CanActivateFn` / `CanMatchFn` guards, `HttpInterceptorFn` token scoping and CSRF, `environment.ts` secret leakage, open redirect via `Router.navigateByUrl`, SSR data exposure via `TransferState` / hydration, token storage, prototype pollution.

**Always runs at full depth.** Security has cliff-edged consequences (XSS -> account takeover) that do not benefit from a "light" mode.

## When to Use

- Angular PR security review
- Pre-deployment hardening pass on auth, file upload, payment, PII routes
- Periodic CSP / interceptor / guard drift sweep
- Auditing a new interceptor, guard, or auth flow

**Not for:** perf (`task-angular-review-perf`), general review (`task-angular-review`), incident (`/task-oncall-start`), backend API review.

## Severity Rubric

| Severity     | One canonical example                                                                                       |
| ------------ | ----------------------------------------------------------------------------------------------------------- |
| **Critical** | Working XSS on prod path (`[innerHTML]` on user input + `bypassSecurityTrustHtml`), `environment.ts` secret, auth bypass, mass SSR `TransferState` leak. Blocks merge. |
| **High**     | Missing input validation on critical surface, missing guard on privileged lazy route, open redirect via `Router.navigateByUrl(query.next)`, CSRF on cookie-session form. Must fix before merge. |
| **Medium**   | Hardening gap with mitigating control (CSP missing nonce but no untrusted HTML rendered), Sentry collecting PII without redaction. Should fix this PR or next. |
| **Low**      | Defense-in-depth nice-to-have, dependency advisory below actively-exploited threshold.                       |

**Combined-finding rule.** When two findings *compose* on the same code path into a worse threat than either alone, file as one at the elevated severity. If exploit requires both -> one finding; either alone exploitable -> separate. Examples: missing guard + `[innerHTML]` on user input = Critical unauth XSS to every viewer; missing interceptor scoping + token in `localStorage` = Critical token exfiltration.

When co-location isn't obvious from diff: file separately at independent severities; add `Note: Combined-finding rule applies if both land on same route/component; verify before merge` to the lower entry.

## Invocation

| Invocation                               | Meaning                                  |
| ---------------------------------------- | ---------------------------------------- |
| `/task-angular-review-security`          | Current branch vs base                   |
| `/task-angular-review-security <branch>` | `<branch>` vs base (3-dot diff)          |
| `/task-angular-review-security pr-<N>`   | PR head fetched into `pr-<N>`            |

Subagent mode: parent passes precondition handle + read diff/log; Step 3 skipped.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If not Angular, stop. Record `Angular: <version>`, `SSR: enabled | disabled | unknown`, `Auth: <library>`. When SSR is unknown from diff, state assumption and flag for verification.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Read diff + commit log once. Skip if parent passed the handle.

### Step 4 - Read the Security Surface

- Every changed `*.component.ts/.html` - `[innerHTML]`, sanitizer use, navigation calls
- Every changed `*.guard.ts` / `*.resolver.ts` / `*.routes.ts` - functional guards, route config
- Every changed `*.interceptor.ts` - auth, CSRF, error handling
- Every changed `*.service.ts` - HTTP, token handling, navigation
- `app.config.ts` / `app.config.server.ts` - `provideHttpClient(withInterceptors([...]))`, security providers
- `environment.ts` / `environment.prod.ts` - flag privileged-secret entries (API keys with write scope, DB URLs, signing keys)
- `index.html` - CSP via `<meta>`
- `angular.json` - source map publishing
- For SSR: `server.ts` - server-side data flow, `TransferState`

When the diff weakens or removes a CSP rule, sanitizer call, guard, or interceptor, `git log -p` the prior revision to confirm what was protected.

### Step 5 - OWASP Triage

Triage pass only - produces one signal verdict per category (`yes` / `no signal in diff`). Steps 6-10 produce the findings; do not duplicate here.

| Risk                          | Angular-specific check                                                                                                                                                                                  |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Functional guards (`CanActivateFn` / `CanMatchFn`) on protected routes; backend enforces; interceptor scopes token to own origin                                                                       |
| Injection                     | URL params validated; `JSON.parse(userInput)` audited                                                                                                                                                  |
| XSS                           | Angular escapes `{{ }}`; `[innerHTML]` only with sanitized HTML; `bypassSecurityTrust*` audited; CSP with `nonce` for scripts                                                                          |
| Cryptographic Failures        | No client-side crypto for security boundaries; secrets from build-injected env vars                                                                                                                    |
| Security Misconfiguration     | CSP via server headers (not just `<meta>`); HSTS, X-Content-Type-Options, Referrer-Policy, Permissions-Policy; X-Frame-Options or CSP `frame-ancestors`                                                |
| SSRF / Insecure Design / Vulnerable Components | Cross-link to backend audit; default-deny via route guards; `npm audit` clean for High/Critical                                                                                       |
| Data Integrity Failures (A08) | `JSON.parse` on untrusted bounded; `eval` / `new Function` flagged (any occurrence = Critical)                                                                                                          |
| Logging & Monitoring (A09)    | Sentry `beforeSend` strips PII; client logs do not include `password`, `token`, `authorization`                                                                                                        |

**Privileged secret definition** (used in Steps 6 + 8): a value that grants write or admin access if exposed - `DATABASE_URL`, API keys with write scope, signing keys, JWT secrets, OAuth client secrets. NOT privileged: Sentry DSNs, OAuth client IDs, Stripe publishable keys (public by design).

### Step 6 - Authentication

**Angular SPA + separate backend (most common):**

- [ ] **Auth library consistent**: one path, not mixed
- [ ] **Functional guards** in new code; class-based guards in new code are [Medium]
- [ ] **`CanMatchFn` for lazy routes** - blocks chunk load; `CanActivateFn` only redirects after load
- [ ] **Guards are UX, not authorization** - backend must enforce; UX-only guard on privileged data is [High]
- [ ] **No client-side authorization decisions** - `*ngIf="user.role === 'admin'"` is UX only
- [ ] **Token in interceptor, scoped to own origin** - `req.url` allowlist check before adding `Authorization`. Direct headers in components or unconditional attachment is a finding
- [ ] **Token storage** - prefer `httpOnly` cookies. Tokens in `localStorage` are XSS-readable (compounds with any `[innerHTML]` exploit)
- [ ] **Refresh token** via httpOnly cookie POST; never in JS
- [ ] **OAuth callback validation** - `state`/`nonce` validated; redirect URL allowlisted
- [ ] **`environment.ts` privileged secrets** (see definition above) - flag any occurrence

**Angular SSR:**

- [ ] **No shared per-user SSR cache** - per-user data must verify cookie/token on server-side fetch
- [ ] **`TransferState` / hydration payload** - server resolvers project to a DTO (`select: { id, name, email }`); never serialize entire ORM rows

### Step 7 - Authorization

- [ ] **Client guards mirror server** - guard redirect is UX; backend enforces authz independently
- [ ] **Role checks** - role comes from server-validated session/JWT (parsed by auth library), never from request body / search param / unverified client claim
- [ ] **Per-tenant isolation** - tenant scoped via session, not URL
- [ ] **CSRF** - cookie-session auth needs token (`X-XSRF-TOKEN` via `withXsrfConfiguration`) or `SameSite=Strict/Lax`. Bearer-token apps should not enable it unnecessarily

### Step 8 - Input Validation, Vulnerability Patterns, and Data Protection

Combined to avoid cross-step duplication. Each pattern lives in exactly one place.

**Input validation:**

- [ ] **Reactive Forms with validators** - typed `FormGroup<{...}>` + `Validators.*`
- [ ] **Server validation is source of truth** - client validators are UX; backend re-validates. Client-only validation on security-sensitive fields (role, price, tenant) is a finding
- [ ] **Route params validated** for shape (UUID / integer / slug)
- [ ] **`JSON.parse(userInput)` into objects** - mass-assignment + prototype-pollution surface
- [ ] **File uploads** - backend validates size and MIME inferred from content

**XSS / sanitizer / navigation:**

- [ ] **`[innerHTML]`** - every binding has sanitizer in chain or comment justifying trust. Never `[innerHTML]="markdownService.render(userInput)"` without `DomSanitizer.sanitize(SecurityContext.HTML, ...)`
- [ ] **`bypassSecurityTrust*`** - every call (`Html` / `ResourceUrl` / `Script` / `Style` / `Url`) has comment justifying trust. `bypassSecurityTrustHtml(userInput)` is Critical. **Audit the upstream**: when `bypassSecurityTrustHtml` is used, the input must be DOMPurify-sanitized (or equivalent) before this point, OR sourced from a server-trusted endpoint - flag the chain end-to-end, not the call site alone
- [ ] **`[href]` / `[src]` / `[routerLink]` from user URL** - scheme must be `http(s):`; allowlist hosts
- [ ] **Open redirect** - `Router.navigateByUrl(query.returnTo)` requires `url.startsWith('/') && !url.startsWith('//')` or allowlist
- [ ] **`window.addEventListener('message')`** origin check
- [ ] **`window.opener` leak** - external `target="_blank"` includes `rel="noopener noreferrer"`
- [ ] **iframe `[src]`** - host allowlist; `sandbox` attribute on external iframes

**Code execution / config:**

- [ ] **`eval` / `new Function(string)`** - any occurrence is Critical
- [ ] **Prototype pollution** - `Object.assign(target, JSON.parse(userInput))` or `{...defaults, ...userJson}` on user-controlled input
- [ ] **`environment.ts` privileged secrets** (see definition above) are Critical even without runtime use - they compile into the client bundle
- [ ] **CSP** - `default-src 'self'`; `script-src 'self' 'nonce-XXX' 'strict-dynamic'`; `style-src 'self' 'unsafe-inline'` (Angular Material tradeoff); `img-src 'self' data: <CDN>`; `connect-src 'self' <API>`; `frame-ancestors 'none'`. Via response headers, not `<meta>`. Wildcards in `script-src`/`connect-src` or `unsafe-eval`/`unsafe-inline` in production = finding
- [ ] **Third-party scripts** - SRI (`integrity`) required for non-first-party

**Data protection:**

- [ ] **PII in client logs / Sentry** - `sendDefaultPii: false`; `beforeSend` strips `email`/`password`/`token`/`creditCard`
- [ ] **No tokens / passwords / PII in URLs** - search and path params hit logs, history, referer
- [ ] **TLS enforcement** - `Strict-Transport-Security` via response headers
- [ ] **Secrets management** - build-injected env vars from secret store (Vault / Secrets Manager / Doppler / hosting)
- [ ] **Production source maps** - `angular.json` `sourceMap: false` or upload-then-strip via Sentry plugin

### Step 9 - SSR-Specific Exposure

_Skipped on SPA-only._

- [ ] **`TransferState` payload** - server resolver populating `TransferState` with `prisma.user.findUnique(...)` serializes the row (including `passwordHash`, `mfaSecret`) into the HTML payload. Project to a DTO at the data-fetch layer
- [ ] **Module-level mutable state** - `let cache = {}` mutated by render leaks across SSR requests

### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Print confirmation line.

## Rules

- Validate at system boundaries: route params, `URLSearchParams`, `postMessage`, file inputs, external API responses
- Never disable Angular auto-sanitization (`bypassSecurityTrust*`) without justifying comment
- Never widen authorization (e.g., remove a `CanActivateFn`) without explicit security review note
- Log security events (login failure, permission denied) without sensitive data
- Default-deny via route guards; client UX complements (does not replace) backend enforcement

## Output Format

```markdown
## Angular Security Review Summary

**Stack:** Angular <version> / SSR: <enabled|disabled|unknown> / Auth: <library or "none (backend handles auth)">
**Overall Posture:** Clean | Issues Found [Critical/High/Medium/Low counts]

[2-3 sentence assessment of overall security posture, calling out Angular-specific risks present.]

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
- **Issue:** [vulnerability in Angular terms with file paths and code]
- **Attack scenario:** [(a) concrete exploit walkthrough; (b) "Regression risk: ..." for missing-control gaps; (c) "Topology-dependent: ..." for infra-flavored findings - pick one and label]
- **Severity rationale:** [tier] - matches rubric example "[paraphrase the canonical example used as the anchor]"
- **Fix:** [specific Angular remediation with code: remove `bypassSecurityTrustHtml`, sanitize via `DomSanitizer.sanitize(SecurityContext.HTML, ...)`, etc.]

### High / Medium / Low

[Same structure. Omit empty sections. If all empty: "No security issues found."]

## Recommendations

[Prioritized hardening not tied to a finding - e.g., "Add `nonce`-based CSP via SSR response headers", "Replace `localStorage` token with httpOnly cookie"]

## Next Steps

Each tagged `[Implement]` or `[Delegate]`. Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action]

_Omit if no security issues found._
```

## Self-Check

- [ ] Principles loaded; stack confirmed; Angular version, SSR, auth library recorded (SSR `unknown` flagged for verification when not visible in diff)
- [ ] Diff resolved once; precondition handle reused; prior revisions consulted when guards/interceptors removed
- [ ] Security surface read directly before checklists
- [ ] OWASP triage produces one signal verdict per category; not duplicated as findings
- [ ] Authn / Authz / Input validation / Vuln patterns / Data protection / SSR checked per scope
- [ ] Severity rubric applied consistently; Combined-finding rule applied where two findings compose on same path
- [ ] Every finding has attack scenario, regression risk, or topology framing labelled
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Critical > High > Medium > Low
- [ ] Report written; confirmation line printed

## Avoid

- State-changing git commands - user runs these
- Vulnerabilities without an attack scenario ("input not validated" vs concrete exploit walkthrough)
- Generic security advice when an Angular idiom applies ("remove `bypassSecurityTrustHtml` and sanitize via `DomSanitizer.sanitize(SecurityContext.HTML, ...)`", not "add validation")
- Conflating security review with general review or perf - delegate
- Treating client-side `*ngIf="user.role === 'admin'"` as authorization
- Recommending JWT in `localStorage` because "stateless" - XSS exposure is the real cost
