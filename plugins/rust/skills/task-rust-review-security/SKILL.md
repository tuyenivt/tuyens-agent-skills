---
name: task-rust-review-security
description: Rust / Axum security review: JWT auth, validator input, sqlx parameterization, unsafe audit, cargo-audit/cargo-deny, OWASP Top 10.
agent: rust-security-engineer
metadata:
  category: backend
  tags: [rust, axum, security, jwt, owasp, cargo-audit, workflow]
  type: workflow
user-invocable: true
---

# Rust Security Review

Stack-specific delegate of `task-code-review-security` for Rust / Axum. Preserves the parent's invocation, diff-resolution, and output contract so callers see a stable shape.

## When to Use

- Reviewing a Rust/Axum PR for security regressions
- Pre-deployment hardening pass on auth, authz, upload, payment, or PII paths
- Auditing a JWT flow, new Axum auth middleware, new `unsafe`, or new crypto usage

**Not for:** performance (`task-rust-review-perf`), general review (`task-rust-review`), incidents (`/task-oncall-start`).

**No depth knob.** Security regressions have cliff-edge consequences (auth bypass, RCE). Scope by file, not by depth.

## Severity Rubric

| Severity     | Definition                                                                                                                                                                                                                       |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, auth bypass, mass data exfiltration, working SQLi (`sqlx::query(&format!(...))`), shell-out with user input, secrets committed, `alg: none` accepted, `unsafe` with attacker-controlled UB. Blocks merge.   |
| **High**     | Authenticated privilege escalation, IDOR on sensitive data, SSRF reaching metadata / internal services, mass assignment via `serde_json::from_value::<Domain>`, missing auth middleware on user-data route, path traversal.      |
| **Medium**   | Hardening gap with mitigating control elsewhere, missing `validator` derives, weak rate limit on non-critical endpoint, debug exposure on non-prod profile, `cargo audit` advisory not yet exploited.                            |
| **Low**      | Defense-in-depth, advisory below actively-exploited threshold, hardening without a concrete current attack scenario.                                                                                                             |

**Combined-finding rule.** When two findings *compose* on the same handler into a worse threat than either alone, file as one finding at the elevated severity citing each component (e.g., missing auth + mass assignment on same route = Critical unauthenticated admin override). If either is independently exploitable, file separately. When co-location is unclear from the diff, file separately and add `Note: Combined-finding rule applies if both land on the same handler; verify before merge` to the lower-severity entry.

## Invocation

Mirrors `task-code-review-security`:

| Invocation                            | Meaning                                                                  |
| ------------------------------------- | ------------------------------------------------------------------------ |
| `/task-rust-review-security`          | Review current branch vs its base; fails fast on trunk                   |
| `/task-rust-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                               |
| `/task-rust-review-security pr-<N>`   | Review PR head fetched into local branch `pr-<N>` (user runs the fetch)  |

When invoked as a subagent of `task-code-review-security`, Step 3 is skipped and pre-read diff/log are reused.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Governs every subsequent step. Skip re-load when invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept the pre-confirmed stack when invoked as a delegate of `task-code-review-security` or subagent of `task-rust-review`. If not Rust, stop and redirect to `/task-code-review-security`.

Record for the Summary block: `Data Access` (sqlx / diesel / mixed), `JWT Library` (`jsonwebtoken` / `josekit` / none), `Password Hash` (`argon2` / `bcrypt` / none).

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (default: current branch). On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip entirely when the parent passed pre-read artifacts. If precondition fails, surface the message verbatim and stop. Never run state-changing git.

### Step 4 - Read the Security Surface

Open the files that actually wire security before applying checklists, so findings cite real lines:

- Router + middleware order (`TraceLayer` -> `RequestId` -> `CorsLayer` -> auth -> rate-limit -> handler) and which sub-routers apply auth via `.route_layer(...)`
- Auth middleware (`src/middleware/auth.rs` or equivalent): JWT validation, claim extraction, error responses
- CORS (`tower_http::cors::CorsLayer`) and rate limiter (`tower_governor` or custom layer) for auth endpoints
- Every changed handler: auth at sub-router level, ownership checks, request DTO type, `validator` derives
- Every changed query: parameterization (`$1` vs `format!`)
- Every changed `migrations/` file: PII/auth columns, FK constraints on tenant scoping, `GRANT`/`REVOKE`, response-DTO leakage of new sensitive columns
- Config struct, `Cargo.toml` / `Cargo.lock`, `.env.example`, `deny.toml`

When the diff removes middleware or relaxes auth, `git log -p` the prior revision to confirm what was protected before.

### Step 5 - OWASP Triage

Use skill: `rust-security-patterns` for canonical Rust security rules (JWT, sqlx, validator, Argon2 / bcrypt, CORS, secrets, `unsafe`, `cargo audit`). Steps 6-7 produce the actual findings; this step is a one-row-per-category verdict that funnels which downstream checks run carefully.

| Risk                          | Rust signal in diff                                                                                                                       |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | New route without `.route_layer(middleware::from_fn(auth))`; missing ownership check                                                       |
| Injection                     | `sqlx::query(&format!(...))`; `Command::new("sh").arg("-c")` with user input                                                              |
| Cryptographic Failures        | Hardcoded JWT key; `md5`/`sha1` for auth; `rand::thread_rng` for tokens; `bcrypt` cost < 10                                                |
| Security Misconfiguration     | Missing HSTS / X-Frame-Options; `AllowOrigin::any()` with credentials; `tracing` at `debug` in prod; `tokio-console` exposed              |
| SSRF                          | `reqwest::get(user_url)` without RFC1918 / link-local / metadata-IP allowlist                                                              |
| XSS                           | `Html(format!("<div>{user}</div>"))`; runtime template with auto-escape disabled                                                          |
| Insecure Design (A04)         | Routes default-allow instead of default-deny via authed router + explicit public whitelist                                                 |
| Vulnerable Components (A06)   | `Cargo.lock` change with stale RUSTSEC advisory; `cargo audit` not in CI                                                                  |
| Data Integrity Failures (A08) | `serde_json::from_value::<Domain>(req.body)`; `bincode`/`rmp-serde`/`ciborium` on untrusted input; `#[serde(untagged)]`; `unsafe`         |
| Logging & Monitoring (A09)    | `tracing` logs `password`/`token`/`cookie`; missing auth-event logging; Sentry without PII-stripping `before_send`                         |

Mark each category `yes` or `no signal in diff`. Do not duplicate as standalone findings.

### Step 6 - Diff-Specific Checks

Apply these against changed files. The canonical pattern for each rule lives in `rust-security-patterns`; this step is the diff-traceable shortlist.

**Authn / authz**
- [ ] JWT: `Validation::new(Algorithm::RS256)` (never `Validation::default()`); `set_issuer`, `set_audience` set; secret from env / Vault
- [ ] Axum auth middleware extracts `Authorization: Bearer`, attaches claims via `extensions_mut()`, returns 401 with no body details
- [ ] Authorization drift: every new endpoint has `.route_layer(...)` OR is in an explicit public sub-router
- [ ] IDOR: lookups scope through the principal in the WHERE clause (`WHERE id = $1 AND user_id = $2`), not a separate post-fetch check
- [ ] Tenant isolation enforced at the repository layer, not handler layer alone
- [ ] Password hashing: `argon2` (or `bcrypt` cost >= 10); `subtle::ConstantTimeEq` for hash compare; hashing wrapped in `spawn_blocking`
- [ ] Brute-force protection: stricter rate limit on `/auth/*` than global
- [ ] CORS: explicit origin allowlist (not `AllowOrigin::any()` with credentials); CSRF only required for cookie sessions

**Input validation / mass assignment**
- [ ] Every request body is a typed DTO with `#[derive(Deserialize, Validate)]` + `req.validate()?`; no bare `Json<Value>` / `Json<HashMap>`
- [ ] No privilege fields (`role`, `is_admin`, `owner_id`, `tenant_id`, `verified`) on user-facing input DTOs - server-set only
- [ ] No client-controlled identity / cache-key fields (`id`, fields used to key `moka::Cache` / `HashMap`) on input DTOs - cache poisoning shape
- [ ] No `serde_json::from_value::<Domain>(req.body)` into domain model - require request DTO + explicit field copy
- [ ] Response is a DTO (`UserResponse::from(u)`), not a raw `FromRow` struct - prevents `password_hash` / `mfa_secret` leak as fields are added
- [ ] `Path<Uuid>` / `Query<TypedFilters>` for path / query; never raw `Path<String>`
- [ ] File uploads: type via `infer::get(&bytes)`, size capped via `RequestBodyLimitLayer`, save path canonicalized and `starts_with(&base)` checked
- [ ] Path traversal: `base.join(input).canonicalize()?.starts_with(&base)` before any FS access; `Path::join` alone does not block `../`
- [ ] Process exec: arg-by-arg (`Command::new("convert").arg(input)`); never `sh -c` / `bash -c` / `cmd /c` with user input

**Common Rust vulnerability patterns**
- [ ] SQL: `sqlx::query!("... WHERE id = $1", id)` or `query(...).bind(id)`; never `format!` into the SQL string itself. `LIKE` with `format!("%{}%", input)` bound to `$1` is fine
- [ ] Runtime templates from user input (`tera::Tera::one_off(user_template, ...)`) is SSTI; templates from disk / constants only. `askama` is compile-time-checked - flag swaps to runtime engines
- [ ] Untrusted deserialization: `bincode`, `rmp_serde`, `ciborium` have format-specific gadget surfaces; prefer `serde_json` for untrusted bytes. `#[serde(untagged)]` on untrusted enums - prefer `#[serde(tag = "type")]`
- [ ] Every `unsafe { ... }` in the diff has a `// SAFETY:` comment justifying invariants
- [ ] `reqwest::Client::builder().danger_accept_invalid_certs(true)` only behind a documented test fixture
- [ ] Open redirect: `Redirect::to(&input)` validated against allowlist or `target.starts_with('/') && !target.starts_with("//")`
- [ ] CSPRNG: `rand::rngs::OsRng` / `getrandom` for tokens, nonces, secrets; never `rand::thread_rng`
- [ ] HMAC / signature compare via `subtle::ConstantTimeEq`; never `==` on `&[u8]`
- [ ] Webhook signatures (Stripe / GitHub / Slack): raw `bytes::Bytes` body before JSON parse; constant-time verify
- [ ] SSRF allowlist rejects (a) `169.254.169.254` and IPv6 equivalent, (b) `127.0.0.0/8` / `::1`, (c) RFC1918, (d) link-local `169.254.0.0/16`; resolve host **after** parse and re-check at request time (DNS rebinding)
- [ ] Background-task payload re-validated by the consumer when the queue is reachable from untrusted input
- [ ] `tracing` floor `info` in prod (never `debug`/`trace`); `tokio-console` / `console_subscriber` gated behind a feature flag; `RUST_BACKTRACE=full` not in error responses
- [ ] `cargo audit` / `cargo deny check advisories` in CI; High/Critical RUSTSEC advisories addressed

**Data protection**
- [ ] PII encrypted at rest (`aes-gcm` / `chacha20poly1305` with proper nonce, or KMS / DB-native encryption)
- [ ] `tracing` redacts `password` / `token` / `credit_card` / `ssn` / `api_key` (custom `Layer`, or custom `Debug` / `valuable::Valuable`)
- [ ] No sensitive data in URLs (hits logs, history, referer)
- [ ] HTTPS enforced at LB; HSTS via `tower_http::set_header`
- [ ] Secrets from env / Vault loaded once at startup via typed config (`figment` / `config` / `envy`); never `.env` committed

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write the assembled output to the report file; print the confirmation line.

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

[2-3 sentence assessment calling out Rust-specific risks: missing auth middleware on sub-router, mass assignment via `serde_json::from_value::<Domain>`, raw SQL via `format!`, exposed `tokio-console`, `danger_accept_invalid_certs(true)`, `unsafe` without SAFETY comment.]

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

- **Location:** [file:line, or comma-separated for multi-site]
- **Issue:** [vulnerability in Rust terms - e.g., "OrderHandler::update calls `serde_json::from_value::<Order>(req.body)?`; client can submit `{ \"user_id\": 999 }` and override the owner via mass assignment - no request DTO with explicit fields"]
- **Attack scenario:** [pick one and label: (a) concrete exploit walkthrough; (b) "Regression risk: next refactor silently removes one of these protections"; (c) "Topology-dependent: depends on whether the reverse proxy strips X-Forwarded-Proto". Do NOT invent an exploit when the realistic threat is regression or topology.]
- **Severity rationale:** [tier] per rubric - [which clause applies]
- **Fix:** [Rust remediation with code - separate request DTO + explicit field copy, `WHERE id = $1 AND user_id = $2`, `.route_layer(...)`, etc.]

### High / Medium / Low

[Same structure. Omit sections with no findings. If all sections empty, state "No security issues found."]

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `tower_governor` rate limit on /auth/login", "Migrate `bcrypt` to `argon2` for new hashes", "Move JWT_SECRET to Vault", "Add `cargo deny check advisories` to CI".]

## Next Steps

Prioritized list. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting, dependency upgrade, or threat-model exercise). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `cargo audit` and upgrade flagged crates"]

_Omit if no security issues found._
```

## Self-Check

Aligns 1:1 with the Workflow steps above.

- [ ] **Step 1**: `behavioral-principles` loaded (or accepted as pre-loaded from a parent workflow)
- [ ] **Step 2**: Stack confirmed Rust / Axum; `Data Access`, `JWT Library`, `Password Hash` recorded before any specific check applied
- [ ] **Step 3**: `review-precondition-check` ran (or handle received from parent); `base_ref` / `head_ref` / `head_matches_current` captured; diff and log read once and reused; on `head_matches_current=false`, explicit user approval obtained before review (skipped when subagent)
- [ ] **Step 4**: Security surface (router / middleware order, auth module, CORS, rate limiter, changed handlers / DTOs / queries / migrations, config, `Cargo.lock`, `deny.toml`) read directly; prior revision consulted when middleware was removed
- [ ] **Step 5**: OWASP triage produced one verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] **Step 6**: Diff-specific checks applied for authn/authz, input validation / mass assignment, common Rust vulnerability patterns, data protection; severity rubric applied consistently; every finding has an attack scenario, regression-risk, or topology-dependent label
- [ ] **Step 7**: Report written to file via `review-report-writer`; confirmation line printed

**Requires repo / infra access (note as "could not verify from diff alone - flag for separate audit" when not visible):**

- [ ] CORS, rate limiting, secure-header middleware, debug exposure verified - applies when middleware / config are in scope
- [ ] Password hashing config reviewed (argon2 preferred, bcrypt cost >= 10) - skip if hashing config not in diff
- [ ] Sentry `before_send` strips PII - skip if Sentry init not in diff
- [ ] `cargo audit` / `cargo deny check advisories` clean - run separately; this workflow does not execute tools

## Avoid

- Running `git fetch` / `git checkout` or any state-changing git command - the user runs these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario, regression-risk, or topology label
- Skipping OWASP categories that look clean - explicitly state "no signal in diff"
- Generic security advice when a Rust idiom applies (say "apply auth via `.route_layer(middleware::from_fn(auth))`", not "add an authorization check")
- Approving any of: `format!`-built SQL; `Json<Value>` over typed `Json<T>` with `Validate`; `serde_json::from_value::<Domain>(req.body)`; `unsafe` without `// SAFETY:` comment; `bincode`/`rmp-serde`/`ciborium` on untrusted input; `danger_accept_invalid_certs(true)` outside test fixtures; `rand::thread_rng` for security tokens; `==` on byte slices for HMAC; `tracing` at `debug`/`trace` in prod; exposed `tokio-console` in prod
- Disabling middleware to silence a failing test - fix the test
- Conflating with general code review or performance review - delegate to their workflows
