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

Laravel-aware security review that names mass assignment via `$guarded = []` or `Model::create($request->all())`, Sanctum (token + SPA) / Passport (OAuth) authentication, Policy-based / Gate-based authorization (IDOR via `Order::find($id)` without ownership scoping, missing `$this->authorize`, missing Form Request `authorize()`), Form Request validation rules, SQL injection via `whereRaw` / `DB::raw` / `orderByRaw($request->input)` (especially user-supplied sort columns), CSRF tokens (web routes default; SPA via Sanctum's `/sanctum/csrf-cookie` flow), password hashing (`Hash::make` / `Hash::check` only - never `md5` / `sha1` / raw `bcrypt(...)`), file upload risks (`$request->file()->store()` in public disks, `Storage::put` with user-controlled paths, MIME spoofing via `getClientMimeType` not magic-byte check, file size limits), webhook signature verification (`hash_equals($expected, $received)` not `==` or `===`), `env()` outside config files (returns null after `config:cache`), secrets committed in `.env.example`, deserialization gadgets via `unserialize` on untrusted input, `eval` / `exec` / `shell_exec` / `passthru` / `system` command injection, runtime-template SSTI in Blade `{!! $userInput !!}`, path traversal in `Storage::download($path)` / file-serving routes, SSRF in `Http::get($userUrl)` reaching cloud metadata (169.254.169.254), `Composer audit` / `roave/security-advisories` dependency hygiene, and OWASP Top 10 in a Laravel lens directly instead of routing through the generic backend security adapter. Produces findings with attack scenarios and concrete Laravel-specific remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for PHP / Laravel. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a Laravel PR for security regressions
- Pre-deployment hardening pass on auth, authz, file upload, payment, or PII-handling code
- Periodic auth / Form Request / Policy drift sweep across endpoints
- Auditing a Sanctum / Passport flow, a new Policy, a new file-upload pipeline, or a webhook integration

**Not for:**

- Performance review (use `task-code-review-perf` or `task-laravel-review-perf`)
- General code review (use `task-code-review` or `task-laravel-review`)
- Production incident triage (use `/task-oncall-start`)

**Depth.** This workflow always runs at full depth - there is no `quick` / `standard` / `deep` knob. Security review has cliff-edged consequences (auth bypass, RCE) that do not benefit from a "light" mode. If callers want a shallower pass, they should scope by file, not by depth.

## Severity Rubric

Use these definitions to keep severity consistent across runs - do not invent your own scale.

| Severity     | Definition                                                                                                                                                                                                                                                             |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, authentication bypass, mass data exfiltration, working SQL injection on a production code path (`DB::select("... $userInput ...")`, `whereRaw("col = '$input'")`), `eval($userInput)` / `shell_exec($userInput)` / `system($userInput)`, secrets / Sanctum / Passport / `APP_KEY` committed in source, `unserialize` on untrusted input (PHP gadget chains), `{!! $userInput !!}` in Blade with attacker-controlled value (XSS but on a privileged surface this becomes admin takeover), `$guarded = []` on a User / Role model where role-elevation field is exposed to mass assignment via `Model::create($request->all())`. Must fix before deploy; blocks merge. |
| **High**     | Authenticated privilege escalation, IDOR with sensitive data via `Order::find($id)` without ownership scoping, SSRF reaching cloud metadata or internal services, mass assignment via `$guarded = []` granting role/admin, missing `$this->authorize` / Policy on user-data endpoint, path traversal via `Storage::download($userControlledPath)`, missing CSRF token on cookie-auth POST, webhook signature compared via `==` (timing attack), `env()` with secret used in business logic AND `.env.example` carrying a committed real value. Must fix before merge. |
| **Medium**   | Hardening gap with a mitigating control elsewhere (e.g., missing CORS allowlist when reverse proxy enforces origin), missing Form Request rules on a non-critical endpoint, weak rate limiting on a non-critical endpoint, debug exposure on a non-prod profile (Telescope reachable), `composer audit` / `roave/security-advisories` advisory not yet exploited, missing `Hash::needsRehash` flow. Should fix this PR or the next one. |
| **Low**      | Defense-in-depth nice-to-have, dependency advisory below the actively-exploited threshold, hardening recommendations without a concrete current attack scenario.                                                                                                       |

**Combined-finding rule.** When two or more findings *compose* on the same code path into a worse threat than either alone, file them as a single finding at the elevated severity and cite each component. Examples:

- Missing `$this->authorize` on a user-data endpoint (High, alone) + mass assignment via `Model::create($request->all())` with `$guarded = []` (High, alone) on the *same action* = **Critical** unauthenticated admin override (anyone authenticated can `POST /users/{id}` with `{"role": "admin"}`).
- Missing `auth:` middleware on a route group (High, alone) + admin-scope action like `User::find($id)->update($r->all())` (High, alone) + missing Form Request / Policy (High, alone) on the *same route* = **Critical** unauthenticated admin takeover (anyone on the internet can promote any user to admin).
- Missing ownership check (High, alone) + Eloquent model returned via `return $user;` exposing `password` hash + `remember_token` (Medium, alone) on the *same action* = **Critical** account takeover.
- Missing `auth:` middleware on `GET /orders/{id}` (High, alone) + `return $order;` returning the Eloquent entity directly (High, alone) on the *same action* = **Critical** unauthenticated entity exposure.
- SSRF via `Http::get($userUrl)` (High, alone) + reachable from an unauthenticated endpoint (High, alone) = **Critical** unauth SSRF.
- `unserialize($webhookBody)` (Critical, alone) + signature verification via `==` instead of `hash_equals` (High, alone) on a webhook endpoint = **Critical** RCE-via-forged-signature (the `==` is timing-attackable, but with `unserialize` the success path itself is the gadget chain trigger - severity stays Critical, but cite both).

The rule of thumb: if the realistic exploit path requires both findings to land for the attack to succeed, they are one finding. If either finding is exploitable on its own, file them separately at their independent severities.

**Same-action co-location.** Combining findings requires confirming both land on the *same code path* (same controller action, same `Route::*` group). When the diff doesn't make co-location obvious, file the findings separately at their independent severities and add a one-line `Note: Combined-finding rule applies if both land on the same action; verify and merge before merge` to the lower-severity entry. Do not silently merge or silently keep separate.

## Invocation

Mirrors `task-code-review-security`:

| Invocation                               | Meaning                                                                                                |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `/task-laravel-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first  |
| `/task-laravel-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                             |
| `/task-laravel-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                        |

When invoked as a subagent of `task-code-review-security` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 3 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every subsequent step (think before acting, surgical changes, surface confusion, push back when the user is likely wrong). When invoked as a subagent of `task-code-review-security` or `task-laravel-review`, accept the parent's confirmation and skip re-loading.

### Step 2 - Confirm Stack

Use skill: `stack-detect` to confirm PHP / Laravel. If invoked as a delegate of `task-code-review-security` or as a subagent of `task-laravel-review` (parent already detected Laravel), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Laravel, stop and tell the user to invoke `/task-code-review-security` instead.

Detect auth strategy: Sanctum (token API), Sanctum (SPA, cookie + CSRF), Passport (OAuth2 server), session-only. Detect ORM: Eloquent (typical) or query builder. Record `Auth`, `ORM`, `Tests Framework` for the Summary block.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-security` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 4 - Read the Security Surface

Before applying the OWASP and authn/authz checklists, open the files that actually wire security so findings cite real lines:

- `bootstrap/app.php` (Laravel 11+) or `app/Http/Kernel.php` (legacy) - confirm middleware order and authentication / CSRF / rate-limit / TrustProxies registration
- `config/auth.php` - guard / provider / password broker config
- `config/sanctum.php` (if Sanctum) - `stateful` domains list, CORS implications
- `config/cors.php` - allowed origins, methods, headers, `supports_credentials`
- `config/session.php` - `secure`, `http_only`, `same_site`
- Sanctum / Passport routes, custom auth controllers, password reset / email verification routes
- Every changed Policy (`app/Policies/*Policy.php`)
- Every changed action - look for `$this->authorize(...)`, `Gate::authorize(...)`, `->middleware('can:...')`, ownership scoping in controller / service body, Form Request type
- Every changed Form Request - `rules()`, `authorize()` (default `true` is a smell on user-data endpoints)
- Every changed Eloquent model (`app/Models/*.php`) for `$fillable` / `$guarded` / `$hidden` (the `$hidden` array prevents columns from JSON-serializing; missing `$hidden` for `password` / `remember_token` / `two_factor_secret` is a leak surface)
- Every changed query for parameterization (`DB::select(...)` with bindings; `whereRaw(...)` with bindings; `Eloquent->where(...)` builder is parameterized)
- Every changed migration in `database/migrations/` for schema-level security: new columns holding PII or auth state, missing FK constraints on tenant scoping columns, `migrationBuilder->raw('GRANT ...')`-style privilege widening
- `.env.example` and `config/*.php` for `env()` keys; `.gitignore` for `.env` exclusion
- `composer.json` / `composer.lock` for package versions; `roave/security-advisories` presence; recent CVEs
- `routes/api.php`, `routes/web.php`, `routes/channels.php` for middleware grouping

When the diff removes a middleware or relaxes auth, also `git log -p` the prior revision of those lines to confirm what was protected before. The blame trail is the authoritative answer to "did this change weaken authorization."

### Step 5 - OWASP Triage (Laravel Lens)

This step is a **triage pass**, not a separate findings list. Run through the OWASP categories below and produce a single output: a list of categories that show signal in this diff. Steps 6-10 then produce the actual findings; do **not** repeat them here.

| Risk                          | Laravel-specific check                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every controller action has `$this->authorize(...)`, `Gate::authorize(...)`, `->middleware('can:...')`, OR ownership scoping in the query (`$user->orders()->findOrFail($id)`). Bare `Order::find($id)` on user-owned data is IDOR. Form Request `authorize()` returns explicit boolean (default `true` is a smell on user-data endpoints).                                                  |
| Injection                     | Eloquent `where(...)` is parameterized. `DB::select(..., [bindings])` is parameterized; `DB::select("... $input ...")` is SQL injection. `whereRaw('col = ?', [$input])` is fine; `whereRaw("col = '$input'")` is injection. `orderByRaw($request->input('sort'))` is injection unless validated against an allowlist. `eval`, `exec`, `shell_exec`, `passthru`, `system`, `pcntl_exec`, `popen`, `proc_open` with user input is RCE. |
| Cryptographic Failures        | Password hashing via `Hash::make` (bcrypt default, Argon2 optional via config). Never `md5`, `sha1`, raw `bcrypt(...)` for passwords. `APP_KEY` from env, never committed. `Crypt::encryptString(...)` for two-way encryption (uses `APP_KEY`). `random_bytes(...)` / `Str::random(...)` for tokens, not `mt_rand` / `rand`.                                                  |
| Security Misconfiguration     | `APP_DEBUG=false` in prod (debug=true leaks `.env` via Whoops error page); Telescope disabled or auth-gated in prod; Horizon dashboard auth-gated (default `viewHorizon` Gate); CORS `allowed_origins` not `*` when `supports_credentials=true` (Laravel will reject this combination at runtime, but flag near-misses); session cookies `secure=true` and `http_only=true` and `same_site='lax'`; `TrustProxies` configured for load-balanced deployments. |
| SSRF                          | `Http::get($userUrl)` validates hostname against allowlist; rejects RFC1918, link-local, cloud metadata (169.254.169.254) before request.                                                                                                                                                                                                                                |
| XSS                           | Blade `{{ $variable }}` auto-escapes (HTML-encoded); `{!! $userInput !!}` (raw output) flagged as XSS unless the value is a constant string or piped through a known sanitizer. Also flag direct `Response::make($html)` returning HTML built via concatenation.                                                                                                                                                                                                                                |
| Insecure Design (A04)         | Default-deny: routes wrapped in `auth:sanctum` / `auth` middleware groups, with explicit `withoutMiddleware('auth')` for public routes (rare). Form Request `authorize()` defaulting to `true` is a default-allow design smell on user-data endpoints.                                                                                                                                                                          |
| Vulnerable Components (A06)   | `composer audit` clean; `roave/security-advisories` in `composer.json` `require-dev` blocks vulnerable packages at install time; `composer.lock` committed; Dependabot / Renovate active.                                                                                                                                                                                  |
| Data Integrity Failures (A08) | `unserialize($userInput)` is RCE-via-gadget-chain; flagged regardless of context. `serialize` of model output round-tripped through queue is fine (Laravel's `SerializesModels` trait handles it). File uploads bounded by `MAX_FILE_SIZE` and validated MIME (`mimes:` rule + magic-byte check via `League\MimeTypeDetection` if true content-type matters). Mass assignment via `$guarded = []` or `Model::create($request->all())` - both flagged.                                                                                                                  |
| Logging & Monitoring (A09)    | `Log::*` and `Monolog` channels do not log `password`, `token`, `Authorization` header, `Cookie` header, full request body. Auth events logged. Sentry / Bugsnag `beforeSend` strips PII (when wired).                                                                                                                                                                    |

### Step 6 - Authentication, Authorization, Input Validation, and Common Vulnerability Patterns

Canonical Laravel security patterns live in `laravel-security-patterns` (Sanctum token + SPA, Passport OAuth, password hashing with `Hash::make`/`Hash::check`/`needsRehash`, CSRF flow, rate limiting, Policies + Gates, Form Request `authorize()`, mass-assignment whitelist, file upload validation, webhook signature verification, secrets management, multi-tenancy). Load it for the canonical implementation patterns. This step is the **review-scoped scan** - what the reviewer must verify on the diff. Sub-scans below are organized by concern, not by separate workflow steps.

**Authentication scan:**

- [ ] Sanctum `stateful` domains explicit (not `*`); token API `expiration` set to a finite window; `EnsureFrontendRequestsAreStateful` middleware on SPA routes only
- [ ] `APP_KEY` from env, never committed; committed real value is Critical
- [ ] `Hash::make` / `Hash::check` only; never `md5` / `sha1` / direct `bcrypt(...)`; `Hash::needsRehash` on long-lived auth systems
- [ ] `/login`, `/password/reset`, `/password/email` rate-limited (`throttle:auth` 5/min by IP)
- [ ] `MustVerifyEmail` + `verified` middleware on routes that require it
- [ ] Password reset token expiry appropriate; recovery codes via `random_bytes` / `Str::random`, never `rand` / `mt_rand`
- [ ] Session cookies `secure=true`, `http_only=true`, `same_site='lax'` in prod
- [ ] `auth:` middleware runs before authorization checks (so `$request->user()` is populated)
- [ ] No `Log::*` call leaks credentials / tokens / Authorization header

**Authorization scan (auth ≠ authz; per-object scoping required):**

- [ ] Every new controller action has Policy / Gate / `can:` middleware / Form Request `authorize()` returning a real check; bare `Order::find($id)->update(...)` is an IDOR finding
- [ ] Form Request `authorize()` does not default to `true` on user-data endpoints (silent default-allow)
- [ ] Lookups scope through the principal (`$user->orders()->findOrFail($id)`), not `Order::find($id)` + separate ownership check
- [ ] Multi-tenant queries scoped at the global-scope / query layer, not just at the controller; `withoutGlobalScope` usages have explicit justification comments
- [ ] CORS `allowed_origins` is an explicit list (Laravel rejects `*` + `supports_credentials=true` at runtime)
- [ ] CSRF middleware on cookie-session / Sanctum-SPA routes; `validateCsrfTokens(except: [...])` exclusions limited to webhook endpoints with their own signature verification

**Input validation + mass assignment scan:**

- [ ] Every input-accepting action uses a typed Form Request, not inline `$request->validate(...)`
- [ ] `rules()` covers every field with specific constraints (`email:rfc,dns`, `url:http,https`, `numeric|min:|max:`, `Rule::in([...])` allowlists for enum fields)
- [ ] `Model::create($request->validated())` not `$request->all()` (even with `$fillable`)
- [ ] No `$guarded = []` anywhere; explicit `$fillable` whitelist; server-set fields (`user_id`, `tenant_id`, `role`, `is_admin`, `verified_at`, `password`) assigned explicitly outside fillable
- [ ] No privilege / identity / cache-key fields (`role`, `is_admin`, `id`, `tenant_id`, `created_at`) in user-facing Form Request rules
- [ ] `$model->fill($validated)` + explicit server-set assignment; `$hidden` populated on User-like models (`password`, `remember_token`, `two_factor_secret`)
- [ ] No raw Eloquent model returned from controllers (always API Resources)
- [ ] `prepareForValidation` strips / canonicalizes user input where applicable
- [ ] **File uploads**: validated by magic bytes (`mimes:` rule via `finfo`) not `getClientMimeType` (client-controlled); per-file size limit; non-public disk (`Storage::disk('private')`); generated UUID filename, not user-supplied; canonicalized save path with base-directory check; virus scan pipeline or accepted-risk documented
- [ ] **Path traversal**: `Storage::download($savedFilename)` where `$savedFilename` is from DB, never `Storage::download($userInput)`; canonicalize before disk access
- [ ] **Process execution**: `exec` / `shell_exec` / `passthru` / `system` / `pcntl_exec` / `popen` / `proc_open` with user input is RCE - prefer SDK / library calls; strict allowlist + `escapeshellarg` per parameter when shell call is unavoidable

**Common vulnerability pattern scan:**

- [ ] **SQL injection**: `whereRaw` / `DB::raw` / `orderByRaw` / `DB::select` use bindings; user-supplied `sort` validated against `Rule::in([...])` column allowlist
- [ ] **Deserialization**: `unserialize($userInput)` on untrusted input is RCE-via-gadget-chain (Critical regardless of context); use `json_decode`. Audit `Crypt::decrypt` for downstream `unserialize` of decrypted user-supplied blobs
- [ ] **XSS / SSTI**: `{!! $userInput !!}` flagged; `Response::make($html)` from concatenation flagged; `Blade::compileString($userInput)` / `Blade::render($userInput)` flagged (templates from disk only)
- [ ] **Variable injection / LFI**: `extract($userArray)`, `include $userControlled`, `require $userControlled` flagged
- [ ] **Open redirect**: `redirect($userInput)` validated via `URL::isValidUrl` + host allowlist; reject `//evil.com`, `data:`, `javascript:`, encoded forms; prefer `redirect()->intended()`
- [ ] **CSPRNG**: `random_bytes` / `Str::random` / `Str::uuid` for security-sensitive randomness; never `rand` / `mt_rand` / `uniqid`
- [ ] **Timing attacks**: `hash_equals($expected, $received)` for HMAC / signature comparison; never `==` / `===` on string equality
- [ ] **`APP_KEY` rotation** flagged when leaked (invalidates signed URLs + encrypted cookies)
- [ ] **Debug exposure**: `APP_DEBUG=true` in non-local is Critical; Telescope / Horizon / Pulse routes gated by Gate (`viewTelescope` / `viewHorizon` / `viewPulse`); Telescope filtered or dev-only
- [ ] **`env()` outside config files** flagged (correctness + security: no central audit, breaks `config:cache`)
- [ ] **`.env.example`** carries placeholder values only; real-looking secrets in commit history are Critical and require rotation
- [ ] **SSRF**: user-controlled URLs into `Http::*` / `Storage::download` / `file_get_contents` validated against allowlist rejecting (a) cloud metadata `169.254.169.254`, (b) localhost / `127.0.0.0/8` / `::1`, (c) RFC1918, (d) link-local; re-resolve host at request time (DNS rebinding); reject URL parser quirks (backslash, IPv4-in-IPv6)
- [ ] **Queue payload trust**: webhooks → queued job inherits webhook trust; validate inside `handle()`
- [ ] **Webhook signature verification** via `hash_equals`; Stripe via `\Stripe\Webhook::constructEvent` (verifies signature + replay window); event-ID idempotency via DB unique constraint or `Cache::add(...)`
- [ ] **Dependency hygiene**: `composer audit` clean; `roave/security-advisories` in `require-dev`; Dependabot / Renovate active

### Step 7 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest via Laravel's `'encrypted'` cast (`'ssn' => 'encrypted'` in `casts()`) - uses `APP_KEY` AES-256-CBC by default; or DB-native column encryption (MySQL `AES_ENCRYPT` is **not** sufficient - it's not authenticated; prefer Laravel's cast or `Crypt::encryptString`)
- [ ] **No raw Eloquent model returned from controller**: covered in Step 7 from the mass-assignment angle; here from the data-leak angle. Returning `User` serializes every column not in `$hidden`. Use `UserResource::make($user)` with explicit `toArray()` listing only public fields
- [ ] **`$hidden` on User-like models**: `password`, `remember_token`, `two_factor_secret`, `two_factor_recovery_codes`, `api_token` (legacy) all in `$hidden` so they don't JSON-serialize even if a developer accidentally returns the model
- [ ] **Log redaction**: `Log::*` and `Monolog` channels never log `password`, `token`, `Authorization` header, `Cookie` header, full request body. Custom Monolog processor (`Monolog\Processor\PsrLogMessageProcessor` + custom redactor) drops sensitive keys; or use Laravel's logging context filtering
- [ ] **No sensitive data in URLs** (use POST body, headers, or signed tokens) - URLs hit access logs, browser history, referrer headers
- [ ] **TLS enforcement**: HTTPS-only via `URL::forceScheme('https')` in `AppServiceProvider::boot` for prod; `TrustProxies` middleware configured for `X-Forwarded-Proto` (so `App\Http\Middleware\TrustProxies::$proxies = '*'` or specific load-balancer IPs)
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets management**: env vars loaded from a secret store (Vault / AWS Secrets Manager / Azure Key Vault) into the runtime env; `.env` in CI / prod sourced from secret store at deploy time, never committed; `php artisan env:encrypt` (Laravel 9+) for committed encrypted env files when secrets must travel with the code


### Step 8 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Rules

- Always validate at system boundaries (Form Requests, queue job payloads, external API responses, webhook payloads)
- Never disable middleware to silence a failing test - fix the test
- Never widen authorization (e.g., removing `auth:` middleware from a route, removing `$this->authorize` from an action) without an explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Follow principle of least privilege - default-deny via auth middleware groups with explicit `withoutMiddleware('auth')` opt-outs

## Self-Check

**Verifiable from the diff (must check):**

- [ ] `behavioral-principles` loaded as Step 1 before any other delegation (or accepted from parent dispatcher)
- [ ] Stack confirmed as PHP / Laravel; auth strategy, ORM, test framework recorded before any specific check applied (Step 2)
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured (Step 3)
- [ ] Diff and commit log were read once and reused by all steps - no re-issuing of git commands mid-review (Step 3)
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent) (Step 3)
- [ ] Security surface (`bootstrap/app.php` / `Kernel.php`, auth config, Sanctum / Passport config, CORS, session, Policies, changed controllers / actions, Form Requests, models, migrations, routes, .env.example) read directly before applying checklists; prior revision consulted when middleware was removed (Step 4)
- [ ] OWASP triage (Step 5) produced one signal verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings (Step 5)
- [ ] Step 6 sub-scans applied: Authentication (Sanctum / Passport / session config, `Hash::make`/`Hash::check`, throttling, email verification, session cookies, middleware order), Authorization (Policy / Gate / `can:` middleware / Form Request `authorize()`, IDOR, tenant isolation, CORS), Input Validation + Mass Assignment (`$guarded = []`, `$fillable` whitelist, `$request->validated()` not `$request->all()`, file upload, path traversal, process execution), Common Vulnerability Patterns (SQL injection, deserialization, XSS / SSTI, open redirect, CSPRNG, `hash_equals`, debug exposure, `env()` outside config, SSRF, webhook idempotency, dependency hygiene)
- [ ] Data protection assessed: PII encrypted at rest, raw model not returned, `$hidden` populated, log redaction, TLS enforcement, secrets management (Step 7)
- [ ] Severity rubric applied consistently (Critical / High / Medium / Low matches the rubric, not invented); Combined-finding rule applied where two findings compose on the same action
- [ ] Every finding includes an attack scenario, "regression risk" rationale, or "topology-dependent" framing - not just "input not validated"
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)

**Requires repo / infra access (check if visible, otherwise note as "could not verify from diff alone - flag for separate audit"):**

- [ ] Authentication step run for the auth mechanism in use - applies when the auth module is in scope
- [ ] CORS, rate limiting, secure-header middleware, debug exposure verified - applies when middleware / config are in scope
- [ ] Password hashing config reviewed (`Hash::make` driver, bcrypt cost / Argon2 params) - skip if hashing config not in diff
- [ ] Sentry / Bugsnag `beforeSend` strips PII - skip if telemetry init not in diff
- [ ] `composer audit` / `roave/security-advisories` clean - run separately; this workflow does not execute tools
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Laravel Security Review Summary

**Stack Detected:** PHP <version> / Laravel <version>
**Auth:** Sanctum (token) | Sanctum (SPA) | Passport | session
**ORM:** Eloquent | Query Builder
**Authorization:** Policies + ownership checks | Gates | inline checks | none
**Tests Framework:** Pest | PHPUnit
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture, calling out any Laravel-specific risks like missing `$this->authorize` on an action, mass assignment via `Model::create($request->all())`, raw SQL via `whereRaw($input)`, exposed Telescope / Horizon dashboard in prod, `env()` outside config files in business logic, `unserialize` on untrusted input, `{!! $userInput !!}` in Blade.]

## OWASP Triage

| Category                  | Verdict                 |
| ------------------------- | ----------------------- |
| Broken Access Control     | yes / no signal in diff |
| Injection                 | yes / no signal in diff |
| Cryptographic Failures    | ...                     |
| Security Misconfiguration | ...                     |
| SSRF                      | ...                     |
| XSS                       | ...                     |
| Insecure Design           | ...                     |
| Vulnerable Components     | ...                     |
| Data Integrity Failures   | ...                     |
| Logging & Monitoring      | ...                     |

## Findings

### Critical

- **Location:** [file:line, or comma-separated list for multi-site findings]
- **Issue:** [vulnerability described in Laravel terms - e.g., "OrderController.update calls `Model::create($request->all())` and the Order model declares `$guarded = []`; client can submit `{ \"user_id\": 999 }` and override the server-assigned owner via mass assignment"]
- **Attack scenario:** [one of: (a) concrete exploit walkthrough; (b) "Regression risk: the next refactor silently removes one of these protections" — for test-coverage / monitoring gaps; (c) "Topology-dependent: depends on whether the reverse proxy strips X-Forwarded-Proto correctly" — for infra-flavored findings. Pick one and label which.]
- **Severity rationale:** [tier] per rubric - [which clause from the Severity Rubric applies]
- **Fix:** [specific Laravel remediation with code example - explicit `$fillable` + `Model::create($request->validated())`, `$user->orders()->findOrFail($id)`, Form Request with rules + `authorize()` returning real check, `$this->authorize('update', $order)`, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `roave/security-advisories` to composer require-dev", "Migrate from bcrypt cost 10 to Argon2id via `config/hashing.php`", "Move `STRIPE_KEY` from `env()` calls in services to `config/services.php`", "Default-deny by wrapping all `routes/api.php` in `auth:sanctum` group with explicit `withoutMiddleware('auth')` for public routes", "Enable `Model::preventLazyLoading()` and `Model::preventSilentlyDiscardingAttributes()` in non-prod"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, or threat-model exercise worth spawning a subagent for). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Replace `$guarded = []` with explicit `$fillable` whitelist on Order model; replace `Order::create($request->all())` with `Order::create($request->validated())` in OrderController.store"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `composer audit` and upgrade flagged packages - spawn dependency-review subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no security issues were found._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"admin\"}` and gains admin via mass assignment because `Model::create($request->all())` plus `$guarded = []` lets every column through")
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending generic security advice when a Laravel idiom applies (say "wrap route in `->middleware('can:update,order')` and define `OrderPolicy::update`", not "add an authorization check")
- Suggesting `APP_DEBUG=true` left enabled in prod - leaks `.env` via Whoops; flag if prod config inherits dev
- Suggesting `whereRaw($input)` or `DB::raw($input)` as acceptable - parameterize or use Eloquent
- Suggesting `==` or `===` for HMAC / signature comparison - use `hash_equals`
- Suggesting `mt_rand` / `rand` / `uniqid` for tokens - use `random_bytes` / `Str::random` / `Str::uuid`
- Suggesting `unserialize($userInput)` as acceptable - PHP gadget chains; use `json_decode`
- Suggesting `$guarded = []` for "convenience" - mass assignment vector
- Suggesting `Model::create($request->all())` even with `$fillable` - bypasses validation discipline; use `$request->validated()`
- Suggesting raw Eloquent model returned from controller - leaks columns; use API Resources
- Suggesting `env()` outside config files - returns null after `config:cache`, no central audit
- Suggesting Telescope / Horizon exposed without auth in prod - significant info leak
- Suggesting `{!! $userInput !!}` in Blade - XSS; use `{{ }}` (auto-escaped) or sanitize first
- Disabling middleware to silence a failing test - fix the test
- Conflating security review with general code quality or performance review - delegate those to their workflows
- Approving file uploads stored in `public/` disks without auth-gated download
- Approving custom hashing (`md5` / `sha1` / `bcrypt(...)` direct) - use `Hash::make`
- Approving `extract($userArray)` or `include $userControlled` - variable injection / LFI
