---
name: task-laravel-review-security
description: Laravel security review for mass assignment (`$guarded = []`, `Model::create($request->all())`), Sanctum / Passport authentication, Gates / Policies authorization (IDOR via `Order::find($id)` without ownership scoping, missing `$this->authorize`), Form Request validation, SQL injection via `whereRaw` / `DB::raw($input)` / `orderByRaw($request->input)`, CSRF / antiforgery, file upload safety (path traversal, MIME spoofing, public storage), webhook signature verification (`hash_equals` not `==`), `env()` outside config, secrets in `.env.example`, `serialize` / `unserialize` deserialization gadgets, `eval` / `exec` / `shell_exec` injection, OWASP Top 10 in a Laravel lens. Stack-specific override of task-code-review-security for PHP / Laravel.
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

Use skill: `stack-detect` to confirm PHP / Laravel. If the detected stack is not Laravel, stop and tell the user to invoke `/task-code-review-security` instead.

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

### Step 6 - Authentication

- [ ] **Sanctum config**: `config/sanctum.php` `stateful` domains list matches actual SPA origins; not `*`. `expiration` set to a finite window for token APIs (default `null` = forever - flag for token-API projects). `EnsureFrontendRequestsAreStateful` middleware on the SPA route group only (not on token-API routes - causes confusion)
- [ ] **`APP_KEY` from env, never committed**: `.env.example` carries `APP_KEY=` (empty); committed `APP_KEY=base64:realvalue` is `Critical` per rubric clause "secrets / Sanctum / Passport / `APP_KEY` committed in source". `php artisan key:generate` per environment
- [ ] **`Hash::make($password)` for new passwords**: never `md5($password)`, `sha1($password)`, `password_hash($password, PASSWORD_BCRYPT)` directly (use `Hash::make` so the configured driver applies, e.g., Argon2 if set in `config/hashing.php`)
- [ ] **`Hash::check($plaintext, $hashed)` for verification**: never `==` or `===` against the stored hash (timing attack, also wrong - hashes don't equal). `Auth::attempt(['email' => ..., 'password' => $req->password])` does this correctly
- [ ] **`Hash::needsRehash($hashed)` flow**: on successful login, check if the cost factor in storage is below current config (`config('hashing.bcrypt.rounds')`); if so, rehash and update. Flag missing rehash flow on long-lived auth systems
- [ ] **Brute-force protection on `/login`, `/password/reset`, `/password/email`**: `->middleware('throttle:auth')` (custom limiter at 5/min by IP), or use Laravel Fortify's built-in throttling. Flag bare auth routes
- [ ] **Email verification on signup**: `MustVerifyEmail` interface on the `User` model + middleware `verified` on routes that require it; without verification, anyone can sign up with any email and access the app
- [ ] **Password reset token expiry**: `config/auth.php` `passwords.users.expire` default 60 minutes - confirm appropriate for the threat model
- [ ] **Two-factor (when present)**: TOTP via `pragmarx/google2fa-laravel` or Fortify's 2FA; recovery codes generated via `Str::random` / `random_bytes`, not `rand`
- [ ] **No `Log::info('User logged in', ['password' => $req->password])`** that leaks credentials
- [ ] **Session cookies** (when used): `config/session.php` `secure=true` (prod), `http_only=true`, `same_site='lax'`; signed via `APP_KEY`
- [ ] **`auth:` middleware before authorization checks**: middleware order matters - auth must run first so `$request->user()` is populated by the time policies run

### Step 7 - Authorization

- [ ] **Authorization drift sweep**: every new controller action added in the diff has a Policy check (`$this->authorize('action', $model)`), Gate check (`Gate::authorize(...)`), middleware (`->middleware('can:action,modelBinding')`), OR Form Request `authorize()` override returning a real check. Bare `Order::find($id)->update(...)` without one of those is an IDOR finding
- [ ] **Policies for owned resources**: every Eloquent model with per-owner data has a Policy; controllers call `$this->authorize('view', $order)` / `'update'` / `'delete'`; Policies check `$user->id === $order->user_id` (or richer rules for shared resources)
- [ ] **Form Request `authorize()` not defaulting to `true`** on user-data endpoints: `public function authorize(): bool { return $this->user()->can('update', $this->route('order')); }`. Default `true` (or omitting the override) is silently default-allow - flag as `[High]` for any new Form Request on a user-data path
- [ ] **IDOR**: lookups scope through the principal in the query (`$user->orders()->findOrFail($id)`) rather than `Order::find($id)` then a separate ownership check. Better: every domain method takes the user / tenant context in its repository signature
- [ ] **Tenant isolation**: multi-tenant apps scope queries by `tenant_id` via global scopes (`Order::addGlobalScope(new TenantScope)`) AND repository / query layer (defense in depth), not at the controller layer alone. `Order::withoutGlobalScope(TenantScope::class)` usages must have an explicit comment justifying cross-tenant access (admin tooling, etc.)
- [ ] **CORS**: `config/cors.php` `allowed_origins` is an explicit list, not `['*']`. `supports_credentials => true` requires explicit origin list (Laravel rejects `*` + credentials at runtime). Methods and headers minimal
- [ ] **CSRF / antiforgery**: not required for stateless Sanctum-token APIs (`Authorization: Bearer ...`); required for cookie-session / Sanctum-SPA web routes - Laravel's `VerifyCsrfToken` middleware is on by default. Custom `validateCsrfTokens(except: [...])` exclusions limited to webhook endpoints with their own signature verification

### Step 8 - Input Validation and Mass Assignment

- [ ] **Form Request used for every input-accepting action**: `public function store(StoreOrderRequest $request)` not inline `$request->validate(...)`. Form Requests centralize validation + authorization
- [ ] **`rules()` covers every field**: missing rules means anything-goes input. Specific rules: `'email' => ['required', 'email:rfc,dns', 'max:255']` (the `dns` flag enforces deliverable domains), `'url' => ['nullable', 'url:http,https']` (only http/https), `'amount' => ['required', 'numeric', 'min:0.01', 'max:99999.99']`, `'role' => ['required', Rule::in(['user', 'manager'])]` (allowlist for role values)
- [ ] **No `$request->all()` passed to `Model::create` / `update`**: even with `$fillable`, this smells - any future fillable change adds a silent attack surface. Use `Model::create($request->validated())` (only validated fields land on the model)
- [ ] **No `$guarded = []` on any model**: opens every column to mass assignment. Always whitelist via `$fillable` listing exactly the user-supplied columns. Server-set fields (`user_id`, `tenant_id`, `role`, `is_admin`, `verified_at`, `password`) must be assigned explicitly outside fillable
- [ ] **No privilege-bearing fields in user-facing input rules / Form Requests**: `role`, `is_admin`, `user_id`, `tenant_id`, `is_active`, `verified_at` - server-set only. If present in `StoreUserRequest::rules()`, reject and require an admin-only path with a separate Form Request
- [ ] **No identity / cache-key fields in user-facing input**: `id`, `created_at`, `updated_at`, anything used as a cache key. Client-controlled IDs that the server also caches by ID enable cache poisoning - flag as a mass-assignment finding even when the field looks innocuous
- [ ] **`$model->fill($request->validated())` followed by explicit assignment** for server-set fields: `$order = (new Order)->fill($request->validated()); $order->user_id = $request->user()->id; $order->save();` - explicit > implicit
- [ ] **`$hidden` on User and similar models**: `protected $hidden = ['password', 'remember_token', 'two_factor_secret', 'two_factor_recovery_codes'];` so these fields don't JSON-serialize when the model is implicitly returned. Best path: never return Eloquent models directly - use API Resources. But `$hidden` is the safety net
- [ ] **No raw Eloquent model returned from controller**: always use API Resources. Returning `$user` serializes every column not in `$hidden`, plus any column added later
- [ ] **GUID / Ulid path params validated**: `Route::get('/orders/{order:uuid}', ...)` (route model binding by uuid) or explicit validation in Form Request
- [ ] **File uploads (`$request->file('field')`)**:
  - File type validated by extension AND magic bytes (Laravel's `mimes:` validation rule checks via `getMimeType()` which uses `finfo` - the actual file magic bytes, not the client-claimed `Content-Type`. Flag any `getClientMimeType()` usage - that IS client-controlled)
  - Per-file size limit enforced via `'file' => ['max:5120']` (KB) AND PHP's `upload_max_filesize` / `post_max_size` set in `php.ini`
  - Saved to a non-public disk (`Storage::disk('private')->put(...)`), served via signed URL or controller, not publicly accessible
  - Filename sanitized via `pathinfo(...)['filename']` AND stored under a generated UUID, not the user-supplied name
  - The save path canonicalized: `realpath($targetDir . '/' . $name)` and checked: `str_starts_with($real, $targetDir)`. Never `Storage::put($userPath, $contents)` with user-controlled `$userPath`
  - Virus scan pipeline or accepted-risk documented for user uploads
- [ ] **Path traversal**: `Storage::download($userControlledPath)`, `Storage::get(request('file'))`, `file_get_contents($baseDir . '/' . $userInput)` without canonicalization is path traversal. Use `Storage::disk('private')->download($savedFilename)` where `$savedFilename` came from the DB, not the request
- [ ] **Process execution**: `exec($cmd)`, `shell_exec($cmd)`, `passthru($cmd)`, `system($cmd)`, `pcntl_exec`, `popen`, `proc_open` with any user input is RCE - even `exec('convert ' . escapeshellarg($input))` is risky if the binary itself accepts shell-meta in flags. Strict allowlist of binaries, prefer SDK / library calls (e.g., Intervention Image instead of `exec('convert')`)
- [ ] **`prepareForValidation` strip / canonicalize** for inputs that need cleanup: `protected function prepareForValidation(): void { $this->merge(['notes' => strip_tags($this->notes ?? '')]); }` for HTML-tag stripping (also prevents XSS at storage boundary)

### Step 9 - Common Laravel Vulnerability Patterns

- [ ] **SQL injection via raw query**: `DB::select("SELECT * FROM orders WHERE status = '$status'")` is critical. Use bindings (`DB::select('SELECT * FROM orders WHERE status = ?', [$status])`) or, better, the Eloquent query builder. `whereRaw("status = '$status'")` is the same surface; use `whereRaw('status = ?', [$status])` or `where('status', $status)`
- [ ] **`orderByRaw($request->input('sort'))` SQL injection**: user-supplied `sort` parameter must validate against an allowlist of column names (`Rule::in(['id', 'created_at', 'total'])`). Otherwise `?sort=1)+UNION+SELECT...` is injection
- [ ] **`DB::raw($input)` flagged**: even when the raw value comes from `Request::input`, treat it as injection unless explicitly allowlisted - safer to use `DB::raw()` with constants only and pass user input as bindings
- [ ] **Eloquent `whereIn(`column`, $userArray)` is parameterized** and safe; flag only if the column name itself comes from user input
- [ ] **Command injection**: any of `exec`, `shell_exec`, `passthru`, `system`, `pcntl_exec`, `popen`, `proc_open` with user-controlled string input is RCE - use SDK / library calls (e.g., Intervention for image conversion) or strict allowlist + `escapeshellarg` per parameter
- [ ] **`unserialize($userInput)` on untrusted input**: PHP gadget chains via Composer-installed packages; `unserialize` allows object instantiation, triggering `__wakeup` / `__destruct` / `__toString` magic methods on every class in the autoloader. Critical regardless of context. Use `json_decode(...)` for cross-process data
- [ ] **`Crypt::decrypt` on untrusted input**: Laravel's encryption is authenticated (HMAC), so `Crypt::decryptString` rejects tampered values - safe for round-trip use. But `unserialize` of decrypted data is still risky if the encrypted blob came from a user (e.g., signed URL parameters). Audit `Crypt::decrypt` callsites for the deserialization path
- [ ] **Blade `{!! $userInput !!}` raw output**: any `{!! $variable !!}` with attacker-controlled `$variable` is XSS. Use `{{ $variable }}` (HTML-encoded by default) or sanitize via `strip_tags` / `Purifier::clean` first. Audit every `{!! ... !!}` in changed Blade files
- [ ] **`Response::make($html)` HTML constructed via concatenation**: same XSS surface as Blade raw output - prefer `view(...)` with templated escaping
- [ ] **Templates with user-supplied template source**: Blade compiler running on user-controlled template content is SSTI / RCE-adjacent; templates must come from disk under `resources/views/`, not from the database. Flag any `Blade::compileString($userInput)` / `Blade::render($userInput, ...)`
- [ ] **`extract($userArray)`** in old code is variable injection (writes any local variable, including loop counters and security flags) - flag as `[High]` for legacy paths
- [ ] **`include`/`require` with dynamic path**: any `include $userControlled` is LFI / RFI; allowlist the file path
- [ ] **Open redirect**: `return redirect($userInput);` validated against an allowlist or via `URL::isValidUrl($url)` and host check; reject `//evil.com`, `data:`, `javascript:`, encoded forms. Laravel's `redirect()->intended()` falls back to a default safe URL - prefer it
- [ ] **`random_bytes` / `Str::random` / `Str::uuid` (NOT `rand` / `mt_rand` / `uniqid` for security-sensitive randomness)**: `random_bytes($n)` is OS-CSPRNG; `Str::random($n)` wraps it with a base62 alphabet; `Str::uuid` (v4) is also CSPRNG. `rand()` / `mt_rand()` are seeded by `microtime` and predictable - never for tokens, password reset codes, session IDs, or anything an attacker could guess
- [ ] **`hash_equals($expected, $received)` for HMAC / signature comparison**: `==` / `===` on string equality is timing-attack vulnerable. Stripe / GitHub / Slack webhook signature verification must use `hash_equals`. Laravel's signed-URL middleware uses `hash_equals` internally; custom webhook verification must too
- [ ] **`APP_KEY` rotated when leaked**: `php artisan key:generate` invalidates all signed URLs and encrypted-cookie sessions; flag if a leaked key has not been rotated
- [ ] **Debug exposure**: `APP_DEBUG=true` in prod leaks `.env`, stack traces, query state via Whoops error page - any commit pushing `APP_DEBUG=true` to a non-local env is `[Critical]`. Telescope route registered without auth in non-local: `Telescope::filter` and `Telescope::auth` (Gate `viewTelescope`) gate access. Same for Horizon (`Gate::define('viewHorizon', ...)`)
- [ ] **`env()` outside `config/*.php`** is both correctness (`config:cache` makes it return null) AND security (no central audit point for which env vars are consumed where, makes secret rotation harder). Flag every `env(...)` call in app code
- [ ] **`.env.example` carries placeholder values only** - never real secrets. `git log -p .env.example` for any commit that introduced a real-looking secret is `[Critical]` and requires rotation
- [ ] **SSRF depth**: when a user-controlled value flows into `Http::get($userUrl)` / `Storage::download($userUrl)` / `file_get_contents($userUrl)`, the allowlist must reject (a) cloud metadata IP `169.254.169.254` and IPv6 equivalent, (b) localhost / `127.0.0.0/8` / `::1`, (c) private RFC1918 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), (d) link-local `169.254.0.0/16`. Resolve the host **after** parsing (DNS rebinding bypasses string-only allowlists - re-resolve at request time and re-check). PHP's URL parser quirks: backslash, IPv4-in-IPv6 (`::ffff:127.0.0.1`) all defeat naive checks
- [ ] **Queue payload trust boundary**: queue jobs deserialize their payload via PHP `unserialize` (via `SerializesModels`); if the queue is reachable from untrusted inputs (webhook → queued job), the payload is implicitly trusted. Validate inside the job before acting on payload fields
- [ ] **Webhook signature verification**: Stripe / GitHub / Slack / Twilio webhooks - signature verified via `hash_equals(...)`, not `==`. Read raw body before any model binding; for Stripe specifically use `\Stripe\Webhook::constructEvent($payload, $sigHeader, $secret)` which does both signature verification and replay-window checking
- [ ] **Webhook idempotency**: same event delivered multiple times; dedup via stored event ID + DB unique constraint or `Cache::add($eventId, true, $ttl)` (atomic add returns false if key exists)
- [ ] **`composer audit`** (Composer 2.4+) clean for affected; `composer outdated` reviewed; `roave/security-advisories` in `composer.json` `require-dev` blocks vulnerable packages at install time. Flag unaddressed High/Critical advisories. Dependabot / Renovate active

### Step 10 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest via Laravel's `'encrypted'` cast (`'ssn' => 'encrypted'` in `casts()`) - uses `APP_KEY` AES-256-CBC by default; or DB-native column encryption (MySQL `AES_ENCRYPT` is **not** sufficient - it's not authenticated; prefer Laravel's cast or `Crypt::encryptString`)
- [ ] **No raw Eloquent model returned from controller**: covered in Step 7 from the mass-assignment angle; here from the data-leak angle. Returning `User` serializes every column not in `$hidden`. Use `UserResource::make($user)` with explicit `toArray()` listing only public fields
- [ ] **`$hidden` on User-like models**: `password`, `remember_token`, `two_factor_secret`, `two_factor_recovery_codes`, `api_token` (legacy) all in `$hidden` so they don't JSON-serialize even if a developer accidentally returns the model
- [ ] **Log redaction**: `Log::*` and `Monolog` channels never log `password`, `token`, `Authorization` header, `Cookie` header, full request body. Custom Monolog processor (`Monolog\Processor\PsrLogMessageProcessor` + custom redactor) drops sensitive keys; or use Laravel's logging context filtering
- [ ] **No sensitive data in URLs** (use POST body, headers, or signed tokens) - URLs hit access logs, browser history, referrer headers
- [ ] **TLS enforcement**: HTTPS-only via `URL::forceScheme('https')` in `AppServiceProvider::boot` for prod; `TrustProxies` middleware configured for `X-Forwarded-Proto` (so `App\Http\Middleware\TrustProxies::$proxies = '*'` or specific load-balancer IPs)
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets management**: env vars loaded from a secret store (Vault / AWS Secrets Manager / Azure Key Vault) into the runtime env; `.env` in CI / prod sourced from secret store at deploy time, never committed; `php artisan env:encrypt` (Laravel 9+) for committed encrypted env files when secrets must travel with the code


### Step 11 - Write Report

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
- [ ] Authentication checks applied (Sanctum / Passport / session config, `Hash::make`/`Hash::check`, brute-force throttling, email verification, session cookie flags, middleware order) (Step 6)
- [ ] **Authorization drift sweep**: every new action / Form Request in the diff has `$this->authorize` / Gate / `can:` middleware / Policy enforcement OR explicit Form Request `authorize()` override; tenant isolation and CORS reviewed (Step 7)
- [ ] Mass assignment reviewed: `$guarded = []`, `$fillable` whitelist, no `Model::create($request->all())` / `Model::find($id)->update($request->all())`, server-set fields assigned explicitly; file upload checks run if uploads in diff (Step 8)
- [ ] SQL injection (`whereRaw`, `DB::raw`, `orderByRaw`, `DB::select`), command injection, Blade SSTI, `unserialize`, `extract`, dynamic `include`, open redirect, CSRNG, `hash_equals`, debug exposure, `env()` outside config, `.env.example` regression check, SSRF allowlist depth, webhook idempotency reviewed when the diff touches them (Step 9)
- [ ] Data protection assessed: PII encrypted at rest, raw model not returned, `$hidden` populated, log redaction, TLS enforcement, secrets management (Step 10)
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
