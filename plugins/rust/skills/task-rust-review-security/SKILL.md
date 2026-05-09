---
name: task-rust-review-security
description: Rust security review for Axum auth middleware, jsonwebtoken JWT validation, validator-crate input validation, sqlx parameterization, mass assignment via serde_json::from_value, secrets management, Command injection, path traversal, unsafe-block audit, cargo-audit / cargo-deny dependency scanning, and Rust-aware OWASP Top 10. Stack-specific override of task-code-review-security, invoked when stack-detect resolves to Rust / Axum.
agent: rust-security-engineer
metadata:
  category: backend
  tags: [rust, axum, security, jwt, owasp, cargo-audit, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Rust Security Review

## Purpose

Rust-aware security review that names Axum auth middleware (`axum::middleware::from_fn`, `tower_http::auth::RequireAuthorizationLayer`), JWT libraries (`jsonwebtoken`, `josekit`), `validator` crate input validation, sqlx parameterization (compile-time-checked vs runtime), password hashing (`argon2`, `bcrypt`), Rust-specific risks (`std::process::Command` injection, path traversal via `std::path::Path::join` without canonicalization + base check, mass assignment via `serde_json::from_value::<DomainModel>(req.body)`, `unsafe` blocks, deserialization attacks via `bincode` / `rmp-serde`, `tokio::process::Command`), and Rust dependency hygiene (`cargo audit`, `cargo deny`) directly instead of routing through the generic backend security adapter. Produces findings with attack scenarios and concrete Rust-specific remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for Rust. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a Rust/Axum PR for security regressions
- Pre-deployment hardening pass on auth, authz, file upload, payment, or PII-handling code
- Periodic strong-validation and middleware drift sweep across endpoints
- Auditing a JWT flow, a new Axum auth middleware, or new `unsafe` / crypto usage

**Not for:**

- Performance review (use `task-code-review-perf` or `task-rust-review-perf`)
- General code review (use `task-code-review` or `task-rust-review`)
- Production incident triage (use `/task-oncall-start`)

**Depth.** This workflow always runs at full depth - there is no `quick` / `standard` / `deep` knob. Security review has cliff-edged consequences (auth bypass, RCE) that do not benefit from a "light" mode. If callers want a shallower pass, they should scope by file, not by depth.

## Severity Rubric

Use these definitions to keep severity consistent across runs - do not invent your own scale.

| Severity     | Definition                                                                                                                                                                                                                                                             |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, authentication bypass, mass data exfiltration, working SQL injection on a production code path (`sqlx::query(&format!("... {user_input}"))`), `Command::new("sh").arg("-c").arg(user_input)`, secrets / signing keys committed in source, JWT `alg: none` accepted, `unsafe` block with attacker-controlled inputs producing UB. Must fix before deploy; blocks merge. |
| **High**     | Authenticated privilege escalation, IDOR with sensitive data, SSRF reaching cloud metadata or internal services, mass assignment via `serde_json::from_value::<User>(req.body)` granting admin, missing auth middleware on user-data endpoint, path traversal via `Path::join` without canonicalization + base check. Must fix before merge. |
| **Medium**   | Hardening gap with a mitigating control elsewhere (e.g., missing CORS allowlist when a reverse proxy enforces origin), missing field-level `validator` derives, weak rate limiting on a non-critical endpoint, debug exposure on a non-prod profile (`tokio-console` exposed), `cargo audit` advisory not yet exploited. Should fix this PR or the next one.  |
| **Low**      | Defense-in-depth nice-to-have, dependency advisory below the actively-exploited threshold (`cargo audit` info-level), hardening recommendations without a concrete current attack scenario.                                                                            |

**Combined-finding rule.** When two or more findings *compose* on the same code path into a worse threat than either alone, file them as a single finding at the elevated severity and cite each component. Examples:

- Missing auth middleware on a user-data endpoint (High, alone) + mass assignment via `serde_json::from_value::<User>(req.body)` (High, alone) on the *same handler* = **Critical** unauthenticated admin override (anyone on the internet can `POST /admin/users/:id` with `{"role": "admin"}`).
- Missing ownership check (High, alone) + `FromRow` struct returned via `Json(...)` exposing `password_hash` (medium, alone) on the *same handler* = **Critical** account takeover (any authenticated user reads any other user's password hash).
- SSRF (High, alone) + reachable from an unauthenticated endpoint (High, alone) = **Critical** unauth SSRF.

The rule of thumb: if the realistic exploit path requires both findings to land for the attack to succeed, they are one finding. If either finding is exploitable on its own, file them separately at their independent severities.

**Same-handler co-location.** Combining findings requires confirming both land on the *same code path* (same handler function, or same router group with shared middleware). When the diff doesn't make co-location obvious - e.g., the IDOR is in `get_order` but the `FromRow` leak appears on a different handler in the same module - file the findings separately at their independent severities and add a one-line `Note: Combined-finding rule applies if both land on the same handler; verify and merge before merge` to the lower-severity entry. Do not silently merge or silently keep separate.

## Invocation

Mirrors `task-code-review-security`:

| Invocation                            | Meaning                                                                                               |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-rust-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-rust-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-rust-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-security` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Rust / Axum. If invoked as a delegate of `task-code-review-security` or as a subagent of `task-rust-review` (parent already detected Rust), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Rust, stop and tell the user to invoke `/task-code-review-security` instead.

Detect data access (sqlx / diesel / mixed), JWT library (`jsonwebtoken`, `josekit`, `frank_jwt`), and password hashing (`argon2` preferred, `bcrypt` acceptable). Record `Data Access`, `JWT Library`, `Password Hash` for the Summary block.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-security` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Security Surface

Before applying the OWASP and authn/authz checklists, open the files that actually wire security so findings cite real lines:

- `src/main.rs` and the router setup file - confirm middleware order (`TraceLayer` → `RequestId` → `CompressionLayer` → `CorsLayer` → auth middleware → rate-limit → handler) and which router groups apply auth via `.route_layer(...)`
- `src/middleware/auth.rs` (or equivalent) - JWT validation logic, claim extraction (`Validation::new(Algorithm::RS256)`, `decode::<Claims>(...)`), error responses
- CORS setup (typically `tower_http::cors::CorsLayer`) for origin allowlist
- Rate limiter (typically `tower_governor` or custom `tower::Layer`) for auth-endpoint rate limits
- Every changed handler - look for auth middleware applied at sub-router level (`Router::new().route(...).route_layer(middleware::from_fn(auth))`), ownership checks in handler/service body, request DTO type, `validator` derives
- Every changed DTO with `#[derive(Validate)]` and `#[validate(...)]` field annotations
- Every changed query for parameterization (`sqlx::query!("... WHERE id = $1", id)` parameterized; `sqlx::query(&format!("..."))` is not)
- Every changed file under `migrations/` for schema-level security: new tables / columns holding PII or auth state (sensitive-column inventory drift), missing `NOT NULL` on identity / tenant columns, missing FK constraints on tenant scoping columns, `GRANT` / `REVOKE` statements widening role privileges, audit-column additions that imply new sensitive fields the response DTO may now leak. Migration content is part of the security surface, not just schema-evolution
- Config struct for `JWT_SECRET`, allowed origins, env var loading
- `Cargo.toml` / `Cargo.lock` for dependency versions; recent CVE-affected crates
- `.env.example` for documented env vars (without real values)
- `deny.toml` (if `cargo deny` is configured) for advisory / license / source policies

When the diff removes a middleware or relaxes auth, also `git log -p` the prior revision of those lines to confirm what was protected before. The blame trail is the authoritative answer to "did this change weaken authorization."

### Step 4 - OWASP Triage (Rust Lens)

This step is a **triage pass**, not a separate findings list. Run through the OWASP categories below and produce a single output: a list of categories that show signal in this diff (e.g., `Broken Access Control: yes`, `Injection: yes`, `SSRF: yes`, `Insecure Design: no`). Steps 5-9 then produce the actual findings; do **not** repeat them here.

The triage output funnels which downstream steps must run carefully versus which can be fast-passed. If a category shows no signal, explicitly state `No signal in diff` for that category in the Summary.

| Risk                          | Rust-specific check                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every protected route has auth middleware applied via `.route_layer(middleware::from_fn(auth))` on the sub-router; ownership check in the service / handler body for per-owner data. Empty / missing is a finding.                                                                                                                                                        |
| Injection                     | sqlx uses `$1`/`$2` placeholders by default; `sqlx::query!("... WHERE id = $1", id)` is parameterized; `sqlx::query(&format!("... WHERE id = {input}"))` is **not**. `Command::new("ls").arg(input)` is fine; `Command::new("sh").arg("-c").arg(input)` is RCE. `tokio::process::Command` has the same shape.                                                              |
| Cryptographic Failures        | `argon2::Argon2::default().hash_password(...)` (preferred) or `bcrypt::hash(pw, 12)` (cost ≥ 10) for passwords. Never `md5` / `sha1` for auth (only for non-security checksums). JWT signing key from env / Vault, not hardcoded. `rand::rngs::OsRng` (CSPRNG) for tokens / nonces, not `rand::thread_rng` for security-sensitive randomness.                              |
| Security Misconfiguration     | `tower_http::set_header::SetResponseHeaderLayer` for HSTS, `X-Frame-Options`, `X-Content-Type-Options`; CORS origin allowlist (not `Any` for credentialed requests); `tokio-console` / `tracing` filter not at `debug` in prod; `RUST_BACKTRACE=full` not exposed in error responses.                                                                                      |
| SSRF                          | `reqwest::get(user_controlled_url)` validates hostname against allowlist; rejects RFC1918, link-local, cloud metadata before request.                                                                                                                                                                                                                                     |
| XSS                           | Axum auto-escapes JSON responses via `serde_json`; if rendering HTML templates (`askama`, `tera`, `maud`), confirm auto-escape is on. Manual `Html(format!("<div>{user}</div>"))` is XSS-prone - flag.                                                                                                                                                                  |
| Insecure Design (A04)         | Default-deny: top-level router requiring auth via `.route_layer(...)` unless explicitly public; explicit public routes whitelisted, not opt-out.                                                                                                                                                                                                                          |
| Vulnerable Components (A06)   | `cargo audit` clean for affected; `cargo deny check advisories` enforced in CI; Renovate / Dependabot active. No pinned-but-stale crate with known RUSTSEC advisory in `Cargo.lock`.                                                                                                                                                                                      |
| Data Integrity Failures (A08) | `serde_json::from_slice` on untrusted input bounded by `RequestBodyLimitLayer` / `Body::from_request_limit`; `bincode::deserialize` / `rmp-serde::from_slice` flagged on untrusted input - format-specific gadgets exist; `unsafe` usage flagged. Mass assignment: `serde_json::from_value::<User>(req.body)` flagged. Untagged enums (`#[serde(untagged)]`) on untrusted input flagged. |
| Logging & Monitoring (A09)    | `tracing` filter does not log `password`, `token`, `authorization`, `cookie`. Auth events logged. Sentry `before_send` strips PII (when wired).                                                                                                                                                                                                                            |

### Step 5 - Authentication

- [ ] **JWT signing**: HS256 secret in env / Vault, never committed. RS256 / ES256 with key pair preferred for cross-service. `jsonwebtoken` crate is standard; `josekit` is the strict-by-default alternative
- [ ] **`alg: none` rejected**: `Validation::new(Algorithm::RS256)` (or whatever the expected algorithm is) - never `Validation::default()` accepting any algorithm. `algorithms` field of `Validation` must be a single-element vec naming the expected algorithm
- [ ] **JWT issuer / audience validated**: `validation.set_issuer(&["expected-iss"])`, `validation.set_audience(&["expected-aud"])`; `validate_exp`, `validate_iss`, `validate_aud` all `true`
- [ ] **Access token lifetime** short (5-15 min); refresh token rotation; refresh tokens revocable via DB / Redis denylist (track `jti` claim or refresh-token UUID)
- [ ] **Password hashing**: `argon2::Argon2::default().hash_password(...)` (preferred for new code) or `bcrypt::hash(pw, 12)` (cost ≥ 10). Never `sha2::Sha256::digest` / `md5::compute` for passwords. `subtle::ConstantTimeEq` for hash comparison
- [ ] **Axum auth middleware wired correctly**: middleware extracts token from `Authorization: Bearer <token>` (`headers.get(AUTHORIZATION)`), validates, attaches claims via `Request::extensions_mut().insert(claims)`, returns `StatusCode::UNAUTHORIZED` with no body details on failure
- [ ] **Brute-force protection**: rate limiter on `/auth/login`, `/auth/refresh`, `/auth/reset-password` via `tower_governor` or custom `tower::Layer`; configured stricter than global rate limit
- [ ] **No `tracing::info!(?token)` / `tracing::debug!(token = %t)`** that leaks the JWT to logs
- [ ] **Session cookies (when used instead of bearer JWT)**: `Secure` in prod, `HttpOnly`, `SameSite=Lax`; signed via `tower_cookies::Key` (HMAC) or `axum_extra::extract::cookie::SignedCookieJar`

### Step 6 - Authorization

- [ ] **Authorization drift sweep**: every new endpoint added in the diff has auth middleware applied at the router level OR explicitly public (whitelisted in a `public` sub-router). No bare `.route("/orders", get(handler))` outside a `.route_layer(...)` boundary
- [ ] **Role / permission checks** centralized in middleware (`require_role(Role::Admin)`) using claims read from `Request::extensions().get::<Claims>()`, not inline `if claims.role != "admin" { return Err(...) }` scattered in handlers (easy to miss on new endpoints)
- [ ] **IDOR**: lookups scope through the principal (`sqlx::query_as!(Order, "SELECT * FROM orders WHERE id = $1 AND user_id = $2", order_id, claims.sub)`) rather than `... WHERE id = $1` then a separate ownership check. Better: every domain query takes `user_id` / `tenant_id` in its repository signature
- [ ] **Tenant isolation**: multi-tenant apps scope queries by `tenant_id` at the repository layer (every query includes the WHERE clause), not at the handler layer alone
- [ ] **CORS**: `CorsLayer::new().allow_origin(["https://app.example.com".parse()?])` allowlist (not `AllowOrigin::any()` for credentialed requests); methods and headers minimal
- [ ] **CSRF**: not required for stateless JWT-bearer APIs; required for cookie-session apps - confirm via auth model. `axum_csrf` middleware for cookie-session

### Step 7 - Input Validation and Mass Assignment

- [ ] **`Json(req): Json<CreateOrderRequest>` extractor with `#[derive(Deserialize, Validate)]`** on the DTO; handler entry calls `req.validate()?` (or use a wrapper extractor `ValidatedJson<T>` that calls `.validate()` automatically). Bare `Json<Value>` with no schema means anything-goes input
- [ ] **`#[validate(...)]` field tags on every DTO field**: `#[validate(length(min = 1, max = 255))]`, `#[validate(email)]`, `#[validate(range(min = 1))]` via the `validator` crate. Missing tags means anything-goes input
- [ ] **No `Json<Value>` / `Json<HashMap<String, Value>>` body**: extract a typed struct - never read fields by string key from a `serde_json::Value`
- [ ] **No privilege-bearing fields in user-facing input DTOs**: `role`, `is_admin`, `owner_id`, `user_id`, `tenant_id`, `is_active`, `verified` - server-set only. If present in `CreateOrderRequest`, reject and require an admin-only path with a separate DTO
- [ ] **No identity / cache-key fields in user-facing input DTOs**: `id`, `created_at`, `updated_at`, and any field used as a key in an in-process cache (`HashMap<id, T>`, `moka::Cache<id, T>`) - if the client controls the id and the server also caches by id, the client can write arbitrary entries into the cache and read other users' data on the next lookup. This is the cache-poisoning shape; treat it as a mass-assignment finding even when the field looks innocuous
- [ ] **No `serde_json::from_value::<User>(req.body)` / `serde_json::from_slice::<User>(body)` directly into a domain model**: this is mass-assignment. Define a request DTO, validate it, then map to the domain model with explicit field assignment
- [ ] **Response DTOs (not row structs) returned from handlers**: `OrderResponse::from(order)` maps explicitly, dropping internal fields (`password_hash`, `internal_audit_log`, `is_test`)
- [ ] **`Path((id,)): Path<(Uuid,)>` for path params**: validates and converts in one call; raw `Path<String>` returns a string with no validation
- [ ] **`Query(filters): Query<ListFilters>`** with `Validate`-derived struct for query strings
- [ ] **UUID path params parsed as `Uuid`**: never trust the raw string format
- [ ] **File uploads (`axum::extract::Multipart`)**:
  - File type validated by content (`infer::get(&bytes)`), not just `Content-Type` header (client-controlled) or extension
  - Per-file size limit enforced (`RequestBodyLimitLayer::new(5 * 1024 * 1024)`); per-field limit via `field.bytes_with_limit(...)`; total request body limit at the Tower layer
  - Saved files stored outside the webroot; `Content-Disposition: attachment` on serve
  - Filename sanitized via `Path::file_name()` AND the resulting save path canonicalized (`std::fs::canonicalize`) and checked: `saved_path.starts_with(&base_dir)`. Never `base.join(user_input)` without normalization
  - Virus scan pipeline or accepted-risk documented for user uploads
- [ ] **Path traversal**: `let candidate = base.join(user_input); let canonical = std::fs::canonicalize(&candidate)?; if !canonical.starts_with(&base) { reject }` - reject otherwise. `Path::join` alone does NOT prevent `../` traversal
- [ ] **Process execution**: `Command::new("convert").arg(user_input).arg("/tmp/out")` is safe (arg-by-arg); `Command::new("sh").arg("-c").arg(format!("convert {user_input}"))` is RCE. Strict allowlist of allowed binaries; same rule for `tokio::process::Command`

### Step 8 - Common Rust Vulnerability Patterns

- [ ] **SQL injection via raw query**: `sqlx::query(&format!("UPDATE ... WHERE id={user_input}"))` - flagged as critical; `sqlx::query_as(&format!("..."))` is the same. Use `sqlx::query!("... WHERE id = $1", id)` (compile-time-checked) or `sqlx::query("... WHERE id = $1").bind(id)` (runtime parameterized). Even `sqlx::query!("... WHERE name LIKE $1", format!("%{}%", input))` is fine - the `$1` is parameterized; the smell is unparameterized interpolation **into the SQL string itself**
- [ ] **Command injection**: `Command::new("sh").arg("-c").arg(format!("convert {user_input} /tmp/out"))` - any concatenation of user input into a shell-interpreted string is RCE; use `Command::new("convert").arg(user_input).arg("/tmp/out")` (arg-by-arg, no shell). Same for `tokio::process::Command`
- [ ] **`std::process::Command` with `shell: true` equivalent**: invoking `bash -c` / `sh -c` / `cmd /c` with user input - same RCE
- [ ] **Templates with user-supplied template source**: `tera::Tera::one_off(user_template, ...)` is SSTI / RCE-adjacent; templates must come from disk or a trusted constant. `askama` is compile-time-checked so this risk is structural-impossible there - flag if the codebase swaps to runtime templates
- [ ] **Deserialization of untrusted formats**: `bincode::deserialize::<T>(bytes)`, `rmp_serde::from_slice::<T>(bytes)`, `ciborium::de::from_reader::<T, _>(reader)` on untrusted input - format-specific gadget surfaces exist; treat as risky unless `T` is a small fixed shape and bounds are enforced. `serde_json` is the canonical untrusted-input deserializer
- [ ] **`#[serde(untagged)]` on untrusted enums**: serde tries each variant in order; misclassification is possible if variants overlap. Prefer `#[serde(tag = "type")]` (internally tagged) for untrusted input
- [ ] **`unsafe` package usage**: every `unsafe { ... }` block in the diff must have a `// SAFETY:` comment justifying the invariants. Audit for memory-safety violations; legitimate uses exist (FFI, `bytes` re-interpretation) but most are smells
- [ ] **HTTP client with `danger_accept_invalid_certs(true)`**: `reqwest::Client::builder().danger_accept_invalid_certs(true)` flagged unless behind a documented test fixture
- [ ] **Open redirect**: `Redirect::to(&user_input)` validated against an allowlist or relative-path-only check (`target.starts_with('/') && !target.starts_with("//")`)
- [ ] **`rand::rngs::OsRng` (NOT `rand::thread_rng` for security-sensitive randomness)**: `OsRng` is OS-backed CSPRNG; `thread_rng` is fast but not designed for adversarial settings. For tokens / nonces / secrets use `OsRng` or `getrandom`
- [ ] **`subtle::ConstantTimeEq` for HMAC / signature comparison**: `==` on `&[u8]` (via `PartialEq`) is timing-attack vulnerable. Stripe / GitHub / Slack webhook signature verification must use constant-time compare from the `subtle` crate
- [ ] **`JWT_SECRET` / signing key** sourced from env / Vault, never committed; rotated when leaked
- [ ] **Debug exposure**: `tracing` filter set to a sensible floor in prod (`info` minimum; `debug` / `trace` leaks request bodies); `RUST_BACKTRACE=full` not exposed in error responses; `tokio-console` / `console_subscriber` not enabled in prod build (gate via `#[cfg(feature = "console")]`)
- [ ] **SSRF depth**: when a user-controlled value flows into an outbound URL or hostname, the allowlist must reject (a) cloud metadata IP `169.254.169.254` and IPv6 equivalent, (b) localhost / `127.0.0.0/8` / `::1`, (c) private RFC1918 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), (d) link-local `169.254.0.0/16`. Resolve the host **after** parsing (DNS rebinding bypasses string-only allowlists - re-resolve at request time and re-check). `url::Url::parse` quirks: backslash, IPv4-in-IPv6 (`::ffff:127.0.0.1`) all defeat naive checks
- [ ] **Background-task payload trust boundary**: tasks serialize to bytes in the queue; consumer `serde_json::from_slice(payload)` on input from any source that can publish to the queue is implicit trust. If the queue is reachable from untrusted inputs (webhook → background task), validate inside the handler before acting on payload fields
- [ ] **HTTP request smuggling / desync** (Rust behind nginx / ALB): hyper's parser is strict by default; flag custom HTTP/1.1 parsing or proxy / forwarder middleware that re-emits headers without validation
- [ ] **Webhook signature verification**: Stripe / GitHub / Slack webhooks - signature verified via `subtle::ConstantTimeEq` (not `==`, not `eq` on slices). Read raw body via `bytes::Bytes` extractor before any JSON parsing (parsing consumes the body)
- [ ] **`cargo audit` integration**: project runs `cargo audit` (or `cargo deny check advisories`) in CI for known RUSTSEC advisories; flag unaddressed High/Critical findings

### Step 9 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest (`aes-gcm` / `chacha20poly1305` crates with proper nonce management, AWS KMS / GCP KMS for key management, or DB-native column encryption)
- [ ] **No `FromRow` struct returned from handler responses**: `Json(user)` where `user: User` (a sqlx `FromRow` struct) leaks every column the struct defines - `password_hash`, `recovery_token`, `mfa_secret`, soft-delete columns, internal audit fields, and any sensitive column added later. Handlers map to a response DTO (`UserResponse::from(u)`) that names exactly the public fields. This is both a Step 7 concern (mass-assignment shape on the way in) and a Step 9 concern (data leak on the way out) - check both directions
- [ ] **`tracing` redaction**: structured logger never logs `password`, `token`, `credit_card`, `ssn`, `api_key`. A custom `tracing_subscriber::Layer` that drops sensitive fields, OR types implement custom `Debug` / `valuable::Valuable` to override formatting
- [ ] **No sensitive data in URLs** (use POST body, headers, or signed tokens) - URLs hit logs, browser history, referer headers
- [ ] **TLS enforcement**: HTTPS-only at LB; HSTS via `tower_http::set_header::SetResponseHeaderLayer`
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets management**: env vars from a secret store (Vault / AWS Secrets Manager / GCP Secret Manager / Doppler), never `.env` committed; `.env` gitignored; `std::env::var("JWT_SECRET")` accessed via typed config struct loaded once at startup so missing-at-startup fails fast (`figment` / `config` / `envy`)


### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Rules

- Always validate at system boundaries (Axum extractors `Json` / `Query` / `Path` / `Form`, background-task payloads, Kafka message values, external API responses, webhook payloads)
- Never disable middleware to silence a failing test - fix the test
- Never widen authorization (e.g., moving an endpoint out of an authed sub-router, removing auth middleware from a route) without an explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Follow principle of least privilege - default-deny via authed router with explicit public whitelist

## Self-Check

**Verifiable from the diff (must check):**

- [ ] Stack confirmed as Rust / Axum; data-access mix, JWT library, password hash library recorded before any specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent)
- [ ] Security surface (router setup / middleware order, auth middleware, settings, changed routers / handlers, DTOs) read directly before applying checklists; prior revision consulted when middleware was removed
- [ ] OWASP triage (Step 4) produced one signal verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] **Authorization drift sweep**: every new endpoint in the diff has matching auth middleware OR is explicitly public-listed
- [ ] DTO validation reviewed; mass-assignment fields, `validator` derives, separate request vs response DTOs confirmed for changed schemas
- [ ] File upload, path traversal, and process-execution checks run if the diff touches uploads / file paths / `std::process::Command` / `tokio::process::Command`
- [ ] SQL parameterization, command injection, runtime-template SSTI, `bincode` / `rmp-serde` deserialization, `unsafe`, `danger_accept_invalid_certs`, open redirect checked when the diff touches them
- [ ] Severity rubric applied consistently (Critical / High / Medium / Low matches the rubric, not invented)
- [ ] Every finding includes an attack scenario, "regression risk" rationale (for test-coverage gaps), or "topology-dependent" framing (for infra-flavored findings) - not just "input not validated"
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)

**Requires repo / infra access (check if visible, otherwise note as "could not verify from diff alone - flag for separate audit"):**

- [ ] Authentication step run for the auth mechanism in use (JWT via `jsonwebtoken` / `josekit`) - applies when the auth module is in scope
- [ ] CORS, rate limiting, secure-header middleware, debug exposure verified - applies when middleware / config are in scope
- [ ] Password hashing config reviewed (argon2 preferred, bcrypt cost ≥ 10) - skip if hashing config not in diff
- [ ] Sentry `before_send` strips PII - skip if Sentry init not in diff
- [ ] `cargo audit` / `cargo deny check advisories` clean - run separately; this workflow does not execute tools
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Rust Security Review Summary

**Stack Detected:** Rust <version> / Axum <version>
**Runtime:** Tokio <version>
**Data Access:** sqlx <version> | diesel <version> | mixed
**JWT Library:** jsonwebtoken | josekit | none
**Password Hash:** argon2 | bcrypt | none
**Authorization:** router-level middleware + ownership checks | inline checks | none
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture, calling out any Rust-specific risks like missing auth middleware on a sub-router, mass assignment via `serde_json::from_value::<User>`, raw SQL via `format!`, exposed `tokio-console` in prod, `danger_accept_invalid_certs(true)` in HTTP client, or `unsafe` block without SAFETY comment.]

## OWASP Triage

_The Step 4 verdicts. One row per category, `yes` (signal present, see Findings) or `no signal in diff`._

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
- **Issue:** [vulnerability described in Rust terms - e.g., "OrderHandler::update accepts the request body directly into a domain model via `serde_json::from_value::<Order>(req.body)?`; client can submit `{ \"user_id\": 999 }` and override the server-assigned owner via mass assignment because there is no separate request DTO with explicit fields"]
- **Attack scenario:** [one of: (a) concrete exploit walkthrough; (b) "Regression risk: the next refactor silently removes one of these protections" — for test-coverage / monitoring gaps; (c) "Topology-dependent: depends on whether the reverse proxy strips X-Forwarded-Proto correctly" — for infra-flavored findings. Pick one and label which. Do NOT invent an exploit when the realistic threat is regression or topology.]
- **Severity rationale:** [tier] per rubric - [which clause from the Severity Rubric applies]
- **Fix:** [specific Rust remediation with code example - separate request DTO + explicit field copy, `WHERE id = $1 AND user_id = $2`, auth middleware via `.route_layer(...)`, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `tower_governor` rate limit on /auth/login", "Migrate from `bcrypt` to `argon2` for new password hashes", "Move JWT_SECRET from .env literal to Vault", "Add `cargo deny check advisories` to CI", "Configure `deny.toml` to enforce license policy"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, or threat-model exercise worth spawning a subagent for). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Replace `serde_json::from_value::<Order>(req.body)?` with a typed `UpdateOrderRequest` DTO + explicit field copy in OrderHandler::update"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `cargo audit` and upgrade flagged crates - spawn dependency-review subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no security issues were found._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"admin\"}` and gains admin via mass assignment because handler deserializes directly into `User` model")
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending generic security advice when a Rust idiom applies (say "apply auth middleware via `.route_layer(middleware::from_fn(auth))` on the sub-router", not "add an authorization check")
- Suggesting `tracing` filter at `debug` / `trace` left as default in prod - leaks request bodies in logs; flag if prod uses default
- Suggesting `format!`-built SQL as acceptable - parameterize via `$1` / `query!` macro
- Suggesting `danger_accept_invalid_certs(true)` outside test fixtures
- Suggesting `rand::thread_rng` for tokens / nonces / secrets - use `OsRng` / `getrandom`
- Suggesting `==` on byte slices for HMAC / signature comparison - use `subtle::ConstantTimeEq`
- Suggesting `Json<Value>` over typed `Json<T>` extractors with `Validate` derives - bare Value is anything-goes
- Suggesting `serde_json::from_value::<DomainModel>(req.body)` as acceptable - mass-assignment vector
- Disabling middleware to silence a failing test - fix the test
- Conflating security review with general code quality or performance review - delegate those to their workflows
- Approving exposed `tokio-console` / `console_subscriber` in prod build
- Approving `bincode` / `rmp-serde` / `ciborium` deserialization on untrusted input without bounded structural guarantees
- Approving `unsafe` blocks without `// SAFETY:` comments justifying the invariants
