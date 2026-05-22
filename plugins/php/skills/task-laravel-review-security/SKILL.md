---
name: task-laravel-review-security
description: Laravel security review: mass assignment, Sanctum/Passport, Gates/Policies, Form Requests, SQL injection, CSRF, file upload, webhook signatures.
agent: php-security-engineer
metadata:
  category: backend
  tags: [php, laravel, security, sanctum, policies, owasp, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Laravel Security Review

## Purpose

Laravel-aware security review covering mass assignment, Sanctum/Passport auth, Policies/Gates, Form Requests, raw SQL, CSRF, file upload, webhook signatures, deserialization, command injection, Blade XSS, path traversal, SSRF, and dependency hygiene through an OWASP Top 10 lens. Stack-specific delegate of `task-code-review-security`; preserves the parent contract (invocation, diff resolution, output format).

## When to Use

- Reviewing a Laravel PR for security regressions
- Pre-deployment hardening on auth, authz, file upload, payment, or PII code
- Periodic auth / Form Request / Policy drift sweep
- Auditing a Sanctum / Passport flow, new Policy, file-upload pipeline, or webhook

**Not for:** performance (`task-laravel-review-perf`), general review (`task-laravel-review`), incident triage (`/task-oncall-start`). Always full depth; scope by file, not depth.

## Severity Rubric

Use these definitions consistently across runs - do not invent your own scale.

| Severity     | Definition                                                                                                                                                                                                                                                             |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauth RCE or auth bypass; working SQLi on prod path (`DB::select("... $input ...")`, `whereRaw("col = '$input'")`); `eval`/`shell_exec`/`system($userInput)`; secrets / `APP_KEY` committed; `unserialize` on untrusted input; `{!! $userInput !!}` on privileged surface; `$guarded = []` on User/Role with `Model::create($request->all())` exposing role. Blocks merge. |
| **High**     | Authenticated privilege escalation; IDOR via `Order::find($id)` without ownership scoping; SSRF to cloud metadata / internal services; mass assignment granting role/admin; missing `$this->authorize` / Policy on user-data endpoint; path traversal via `Storage::download($userInput)`; missing CSRF on cookie-auth POST; webhook signature compared via `==`; `env()` secret in business logic with a real value in `.env.example`. Fix before merge. |
| **Medium**   | Hardening gap with a mitigating control elsewhere; missing Form Request rules on non-critical endpoint; weak rate limit on non-critical endpoint; debug exposure on non-prod (Telescope reachable); `composer audit` advisory not yet exploited; missing `Hash::needsRehash` flow. Fix this PR or next. |
| **Low**      | Defense-in-depth nice-to-have; advisory below actively-exploited threshold; hardening with no concrete current attack scenario.                                                                                                                                       |

**Combined-finding rule.** When two or more findings *compose* on the same code path into a worse threat than either alone, file as a single finding at the elevated severity and cite each component. Examples:

- Missing `$this->authorize` + `Model::create($request->all())` with `$guarded = []` on same action = **Critical** authenticated admin override.
- Missing `auth:` middleware + `User::find($id)->update($r->all())` + missing Form Request/Policy on same route = **Critical** unauth admin takeover.
- Missing ownership check + raw `return $user;` exposing `password` / `remember_token` on same action = **Critical** account takeover.
- Missing `auth:` on `GET /orders/{id}` + `return $order;` returning Eloquent entity on same action = **Critical** unauth entity exposure.
- SSRF via `Http::get($userUrl)` reachable from an unauthenticated endpoint = **Critical** unauth SSRF.
- `unserialize($webhookBody)` + signature compared via `==` on webhook endpoint = **Critical** RCE-via-forged-signature (cite both).

Rule of thumb: if the realistic exploit requires both findings to land, they are one finding. If either is exploitable alone, file separately.

**Same-action co-location.** Combining requires both on the *same code path* (same controller action, same `Route::*` group). When the diff doesn't make co-location obvious, file separately at independent severities and add `Note: Combined-finding rule applies if both land on the same action; verify and merge before merge` to the lower-severity entry. Do not silently merge or silently keep separate.

## Invocation

Mirrors `task-code-review-security`:

| Invocation                               | Meaning                                                                                                |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `/task-laravel-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first  |
| `/task-laravel-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                             |
| `/task-laravel-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                        |

When invoked as a subagent of `task-code-review-security` (parent passes precondition-check handle plus already-read diff and commit log), Step 3 is skipped and parent artifacts are reused.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Skip when invoked as a subagent of `task-code-review-security` or `task-laravel-review`.

### Step 2 - Confirm Stack

Use skill: `stack-detect` to confirm PHP / Laravel. Skip when parent already detected. If not Laravel, stop and tell the user to invoke `/task-code-review-security`. Detect auth (Sanctum token / Sanctum SPA / Passport / session) and ORM (Eloquent / query builder). Record `Auth`, `ORM`, `Tests Framework` for the Summary.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip with parent-supplied artifacts. If precondition fails fast, surface the message verbatim and stop. Never run state-changing git commands.

### Step 4 - Read the Security Surface

Open files that wire security so findings cite real lines:

- `bootstrap/app.php` / `app/Http/Kernel.php` (middleware order); `config/auth.php`, `config/sanctum.php`, `config/cors.php`, `config/session.php`
- Sanctum / Passport routes, custom auth controllers, password reset / email verification
- Every changed Policy, controller action (`$this->authorize`, `can:` middleware, ownership scoping), Form Request (`rules()`, `authorize()`), model (`$fillable` / `$guarded` / `$hidden`), query (parameterization), migration (PII, FK on tenant scoping, privilege widening)
- `.env.example`, `config/*.php` for `env()` keys; `.gitignore` for `.env`; `composer.json` / `composer.lock` for versions, `roave/security-advisories`, CVEs
- `routes/api.php`, `routes/web.php`, `routes/channels.php` for middleware grouping

When the diff removes middleware or relaxes auth, `git log -p` the prior revision - the blame trail is authoritative for "did this change weaken authorization."

### Step 5 - OWASP Triage (Laravel Lens)

A **triage pass**, not a separate findings list. Produce one signal verdict per category. Steps 6-7 produce findings; do **not** repeat them here.

| Risk                          | Laravel-specific check                                                                                                                                                                                                                       |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | `$this->authorize` / `Gate::authorize` / `can:` middleware / ownership scoping (`$user->orders()->findOrFail($id)`). Bare `Order::find($id)` on user-owned data is IDOR. Form Request `authorize()` returns explicit boolean.                |
| Injection                     | Eloquent / `DB::select(..., [bindings])` / `whereRaw('col = ?', [$input])` parameterized; `whereRaw("col = '$input'")` and `orderByRaw($request->input('sort'))` without allowlist are injection. `eval`/`exec`/`shell_exec`/`passthru`/`system`/`pcntl_exec`/`popen`/`proc_open` with user input is RCE. |
| Cryptographic Failures        | `Hash::make` only (never `md5` / `sha1` / raw `bcrypt(...)`); `APP_KEY` from env; `Crypt::encryptString` for two-way; `random_bytes` / `Str::random` not `mt_rand` / `rand`.                                                                  |
| Security Misconfiguration     | `APP_DEBUG=false` in prod; Telescope/Horizon/Pulse auth-gated; CORS not `*` with `supports_credentials=true`; session cookies `secure`/`http_only`/`same_site='lax'`; `TrustProxies` configured.                                              |
| SSRF                          | `Http::get($userUrl)` validates hostname against allowlist; rejects RFC1918, link-local, cloud metadata `169.254.169.254`.                                                                                                                   |
| XSS                           | `{{ $variable }}` auto-escapes; `{!! $userInput !!}` flagged unless constant or sanitized; `Response::make($html)` from concatenation flagged.                                                                                                |
| Insecure Design (A04)         | Default-deny: routes wrapped in `auth:sanctum` / `auth` groups with explicit `withoutMiddleware('auth')` for public. Form Request `authorize()` defaulting to `true` is a default-allow smell.                                                |
| Vulnerable Components (A06)   | `composer audit` clean; `roave/security-advisories` in `require-dev`; `composer.lock` committed; Dependabot / Renovate active.                                                                                                               |
| Data Integrity Failures (A08) | `unserialize($userInput)` is RCE-via-gadget-chain. File uploads bounded by size and validated MIME (`mimes:` + magic-byte). Mass assignment via `$guarded = []` or `Model::create($request->all())` flagged.                                  |
| Logging & Monitoring (A09)    | `Log::*` / `Monolog` never log `password`, `token`, `Authorization`, `Cookie`, full request body. Auth events logged. Sentry/Bugsnag `beforeSend` strips PII.                                                                                |

### Step 6 - Authentication, Authorization, Input Validation, and Common Vulnerability Patterns

Use skill: `laravel-security-patterns` for canonical implementation (Sanctum + SPA, Passport, hashing, CSRF, rate limiting, Policies + Gates, Form Request `authorize()`, mass-assignment whitelist, file upload, webhook signature, secrets, multi-tenancy). Sub-scans are review-scoped checks on the diff; each check appears in exactly one sub-scan.

**Authentication scan:**

- [ ] Sanctum `stateful` domains explicit (not `*`); token `expiration` finite; `EnsureFrontendRequestsAreStateful` only on SPA routes
- [ ] `APP_KEY` from env (committed real value is Critical); `Hash::make` / `Hash::check` only; `Hash::needsRehash` on long-lived auth
- [ ] `/login`, `/password/reset`, `/password/email` rate-limited (`throttle:auth` 5/min by IP); `MustVerifyEmail` + `verified` middleware where required; reset token expiry appropriate
- [ ] Session cookies `secure`, `http_only`, `same_site='lax'` in prod; `auth:` middleware before authorization (so `$request->user()` is populated)

**Authorization scan (auth != authz; per-object scoping required):**

- [ ] Every new action has Policy / Gate / `can:` middleware / Form Request `authorize()` with a real check; bare `Order::find($id)->update(...)` is IDOR
- [ ] Form Request `authorize()` does not default to `true` on user-data endpoints
- [ ] Lookups scope through principal (`$user->orders()->findOrFail($id)`); multi-tenant queries scoped at global-scope / query layer; `withoutGlobalScope` has justification comment
- [ ] CORS `allowed_origins` an explicit list; CSRF middleware on cookie-session / Sanctum-SPA routes; `validateCsrfTokens(except: [...])` limited to webhooks with their own signature verification

**Input validation + mass assignment scan:**

- [ ] Every input-accepting action uses a typed Form Request, not inline `$request->validate(...)`; `rules()` covers every field with specific constraints (`email:rfc,dns`, `url:http,https`, `numeric|min:|max:`, `Rule::in([...])`)
- [ ] `Model::create($request->validated())` not `$request->all()`; no `$guarded = []`; explicit `$fillable`; server-set fields (`user_id`, `tenant_id`, `role`, `is_admin`, `verified_at`, `password`) assigned outside fillable
- [ ] No privilege / identity fields (`role`, `is_admin`, `id`, `tenant_id`) in user-facing Form Request rules; `$hidden` on User-like models (`password`, `remember_token`, `two_factor_secret`); no raw Eloquent model returned (always API Resources)
- [ ] **File uploads**: validated via magic bytes (`mimes:` via `finfo`), not `getClientMimeType`; per-file size limit; non-public disk; generated UUID filename; canonicalized save path
- [ ] **Path traversal**: `Storage::download($savedFilename)` from DB, never user input
- [ ] **Process execution**: prefer SDK calls; if unavoidable, strict allowlist + `escapeshellarg` per parameter

**Common vulnerability pattern scan:**

- [ ] **SQL injection**: `whereRaw` / `DB::raw` / `orderByRaw` / `DB::select` use bindings; user-supplied `sort` validated against `Rule::in([...])` allowlist
- [ ] **Deserialization**: `unserialize($userInput)` is Critical regardless of context; use `json_decode`. Audit `Crypt::decrypt` for downstream `unserialize`
- [ ] **XSS / SSTI**: `{!! $userInput !!}`, `Response::make($html)` from concatenation, `Blade::compileString` / `Blade::render` on user input flagged
- [ ] **Variable injection / LFI**: `extract($userArray)`, `include $userControlled`, `require $userControlled` flagged
- [ ] **Open redirect**: `redirect($userInput)` validated via `URL::isValidUrl` + host allowlist; reject `//evil.com`, `data:`, `javascript:`; prefer `redirect()->intended()`
- [ ] **CSPRNG**: `random_bytes` / `Str::random` / `Str::uuid`; never `rand` / `mt_rand` / `uniqid`. **Timing attacks**: `hash_equals` for HMAC / signature; never `==` / `===`
- [ ] **Debug exposure**: `APP_DEBUG=true` in non-local is Critical; Telescope / Horizon / Pulse gated by Gate
- [ ] **`env()` outside config files** flagged (returns null after `config:cache`); **`.env.example`** carries placeholders only; real-looking secrets in history require rotation + `APP_KEY` rotation if leaked
- [ ] **SSRF**: user-controlled URLs into `Http::*` / `Storage::download` / `file_get_contents` validated against allowlist rejecting cloud metadata, localhost, RFC1918, link-local; re-resolve at request time (DNS rebinding); reject parser quirks
- [ ] **Queue payload trust**: webhooks -> queued job inherits webhook trust; validate inside `handle()`
- [ ] **Webhook signature** via `hash_equals`; Stripe via `\Stripe\Webhook::constructEvent`; event-ID idempotency via DB unique constraint or `Cache::add(...)`
- [ ] **Dependency hygiene**: `composer audit` clean; `roave/security-advisories` in `require-dev`; Dependabot / Renovate active

### Step 7 - Data Protection

- [ ] **PII encrypted at rest** via `'encrypted'` cast (AES-256-CBC with `APP_KEY`) or `Crypt::encryptString`; MySQL `AES_ENCRYPT` is not authenticated and not sufficient
- [ ] **`$hidden`** populated (`password`, `remember_token`, `two_factor_secret`, `two_factor_recovery_codes`, `api_token`); **log redaction** via custom Monolog processor or Laravel logging context filtering
- [ ] **No sensitive data in URLs** (POST body, headers, or signed tokens); **TLS** via `URL::forceScheme('https')` + `TrustProxies` for `X-Forwarded-Proto`; backups encrypted and access-controlled
- [ ] **Secrets management**: env from secret store (Vault / AWS Secrets Manager / Azure Key Vault); `.env` in CI/prod sourced at deploy time; `php artisan env:encrypt` for committed encrypted env files

### Step 8 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write the assembled output to the report file before ending the session. Print the confirmation line to the console.

## Rules

- Validate at every system boundary (Form Requests, queue payloads, external API responses, webhook payloads)
- Never disable middleware to silence a failing test; never widen authorization without an explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Default-deny via auth middleware groups with explicit `withoutMiddleware('auth')` opt-outs

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2: PHP / Laravel confirmed; auth, ORM, test framework recorded
- [ ] Step 3: `review-precondition-check` ran (or handle received); diff and commit log read once; `head_matches_current=false` got explicit user approval
- [ ] Step 4: Security surface read directly; prior revision consulted when middleware removed
- [ ] Step 5: OWASP triage produced one verdict per category; not duplicated as standalone findings
- [ ] Step 6: All four sub-scans applied (Authentication, Authorization, Input Validation + Mass Assignment, Common Vulnerability Patterns)
- [ ] Step 7: Data protection assessed (PII encryption, `$hidden`, log redaction, TLS, secrets)
- [ ] Step 8: Report written via `review-report-writer`; confirmation line printed
- [ ] Severity rubric applied consistently; Combined-finding rule applied where findings compose on the same action
- [ ] Every finding has attack scenario, regression-risk rationale, or topology-dependent framing
- [ ] Next Steps tagged `[Implement]` or `[Delegate]`, ordered Critical > High > Medium > Low (omit only when no issues)

## Output Format

```markdown
## Laravel Security Review Summary

**Stack Detected:** PHP <version> / Laravel <version>
**Auth:** Sanctum (token) | Sanctum (SPA) | Passport | session
**ORM:** Eloquent | Query Builder
**Authorization:** Policies + ownership checks | Gates | inline checks | none
**Tests Framework:** Pest | PHPUnit
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment calling out Laravel-specific risks.]

## OWASP Triage

| Category                  | Verdict                 |
| ------------------------- | ----------------------- |
| Broken Access Control     | yes / no signal in diff |
| Injection                 | ...                     |
| Cryptographic Failures    | ...                     |
| Security Misconfiguration | ...                     |
| SSRF                      | ...                     |
| XSS                       | ...                     |
| Insecure Design           | ...                     |
| Vulnerable Components     | ...                     |
| Data Integrity Failures   | ...                     |
| Logging & Monitoring      | ...                     |

## Findings

### Critical / High / Medium / Low

Each finding:

- **Location:** [file:line]
- **Issue:** [vulnerability in Laravel terms]
- **Attack scenario:** [(a) concrete exploit walkthrough; (b) "Regression risk: ..."; (c) "Topology-dependent: ...". Pick one and label.]
- **Severity rationale:** [tier] per rubric - [which clause applies]
- **Fix:** [specific Laravel remediation with code]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding.]

## Next Steps

Prioritized list. Each item tagged `[Implement]` (localized) or `[Delegate]` (cross-cutting). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action]
2. **[Delegate]** [High] [scope] - [one-line action]

_Omit if no security issues were found._
```

## Avoid

- State-changing git commands (`git fetch`, `git checkout`, etc.)
- Findings without an attack scenario; skipping OWASP categories silently (state "no signal in diff")
- Generic security advice when a Laravel idiom applies ("wrap in `->middleware('can:update,order')` and define `OrderPolicy::update`", not "add an authorization check")
- Conflating security with general code quality or performance review
- Approving file uploads in `public/` disks without auth-gated download
