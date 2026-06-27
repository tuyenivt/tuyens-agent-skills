---
name: task-rust-review-security
description: Rust / Axum security review - JWT/auth, validator DTOs, sqlx parameterization, mass assignment, unsafe, secrets, CORS, cargo-audit, OWASP.
agent: rust-security-engineer
metadata:
  category: backend
  tags: [rust, axum, security, jwt, owasp, cargo-audit, workflow]
  type: workflow
user-invocable: true
---

# Rust Security Review

Stack-specific delegate of `task-code-review-security` for Rust / Axum. Preserves the parent's invocation, diff-resolution, and output contract.

## When to Use

- Reviewing a Rust / Axum PR for security regressions
- Pre-deployment hardening pass on auth, authz, upload, payment, or PII paths
- Auditing a JWT flow, new auth middleware, new `unsafe`, or new crypto usage

**Not for:** performance (`task-rust-review-perf`), general review (`task-rust-review`), incidents (`/task-oncall-start`).

**No depth knob.** Security regressions have cliff-edge consequences. Scope by file, not by depth.

## Severity Rubric

| Severity     | Definition                                                                                                                                                       |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, auth bypass, working SQLi (`sqlx::query(&format!(...))`), shell-out with user input, secrets committed, `alg: none` accepted, `unsafe` UB.  |
| **High**     | Authenticated privesc, IDOR on sensitive data, SSRF reaching metadata, mass assignment via `serde_json::from_value::<Domain>`, missing auth middleware, traversal. |
| **Medium**   | Hardening gap with mitigating control elsewhere, missing `validator` derives, weak rate limit on non-critical endpoint, `cargo audit` advisory not yet exploited. |
| **Low**      | Defense-in-depth, advisory below actively-exploited threshold, hardening without a concrete current attack scenario.                                             |

The rows list a finding's *baseline* tier. Tier the **resulting threat**, not the named pattern, when these elevation conditions hold:

- **Removal of the only gate on existing privileged surface** is auth bypass (Critical), not "missing auth middleware" (High) - High covers a *new* endpoint shipped without auth; deleting the sole layer on already-protected routes exposes live data now.
- **Composition crosses tiers.** Two High components on one handler that together yield an unauthenticated privileged mutation (e.g., missing auth + mass assignment) are Critical via the auth-bypass clause.
- **SSRF reaching metadata that returns credentials** (e.g., IMDS IAM role) is Critical (effective cloud auth bypass), above the bare High row; note IMDSv2/topology as the verify-before-merge condition.
- **Untrusted deserialization** (`bincode` / `rmp_serde` / `ciborium` on an untrusted body) is High - DoS via attacker-chosen layout and validation bypass; not Critical absent a concrete RCE chain, which Rust rarely affords.

**Combined-finding rule.** When two findings compose on the same handler into a worse threat (e.g., missing auth + mass assignment = unauthenticated admin override), file as one elevated finding citing each component, tiered by the resulting threat (see elevation rule). If either is independently exploitable, file separately. If co-location is unclear from the diff, file separately and note "Combined-finding rule applies if both land on the same handler; verify before merge". A combined finding may satisfy multiple `yes` OWASP rows (e.g., Broken Access Control + Insecure Design); point each such row at the single combined finding - do not split it to satisfy the one-row-per-finding shape.

## Invocation

| Form                                  | Meaning                                                              |
| ------------------------------------- | -------------------------------------------------------------------- |
| `/task-rust-review-security`          | Review current branch vs base; fails fast on trunk                   |
| `/task-rust-review-security <branch>` | Review `<branch>` vs base (3-dot diff)                               |
| `/task-rust-review-security pr-<N>`   | Review PR head in local branch `pr-<N>` (user runs the fetch)        |

When invoked as a subagent of `task-code-review-security` or `task-rust-review`, the parent passes the precondition handle plus pre-read diff/log; skip re-detection.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Skip re-load when invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept the pre-confirmed stack when invoked as a delegate. If not Rust, stop and redirect to `/task-code-review-security`.

Record for the Summary: `Data Access` (sqlx / diesel / mixed), `JWT Library` (`jsonwebtoken` / `josekit` / none), `Password Hash` (`argon2` / `bcrypt` / none).

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip entirely when the parent passed pre-read artifacts. Never run state-changing git.

### Step 4 - Read the Security Surface

Open the files that wire security before applying checklists, so findings cite real lines:

- Router + middleware order (`TraceLayer` -> `RequestId` -> `CorsLayer` -> auth -> rate-limit -> handler); which sub-routers apply `.route_layer(...)`
- Auth middleware: JWT validation, claim extraction, error responses
- CORS (`tower_http::cors::CorsLayer`) and rate limiter (`tower_governor`) on auth endpoints
- Every changed handler: auth at sub-router level, ownership checks, request DTO type, `validator` derives
- Every changed query: parameterization (`$1` vs `format!`)
- Every changed `migrations/` file: PII / auth columns, FK tenant scoping, response-DTO leakage of new sensitive columns
- Config struct, `Cargo.toml` / `Cargo.lock`, `.env.example`, `deny.toml`

When the diff removes middleware or relaxes auth, `git log -p` the prior revision to confirm what was protected before.

### Step 5 - Apply Canonical Patterns

Use skill: `rust-security-patterns`. Owns canonical rules for: JWT (RS256, iss/aud), validator DTOs + `deny_unknown_fields`, mass assignment, sqlx parameterization, password hashing off-runtime, secrets via `SecretString`, CORS, path traversal, `unsafe` SAFETY comments, `cargo audit`. Apply each rule against the surface from Step 4. Do not restate the rules here -- delegate.

### Step 6 - Diff-Specific Triage

The atomic owns the rules; this step is the diff-traceable shortlist for issues that need explicit checking beyond `rust-security-patterns`:

**Authorization drift**
- [ ] Every new endpoint has `.route_layer(...)` OR is in an explicit public sub-router (default-deny)
- [ ] IDOR: lookups scope by principal in `WHERE` (`WHERE id = $1 AND user_id = $2`), not post-fetch check
- [ ] Tenant isolation enforced at repository layer, not handler alone
- [ ] Brute-force: stricter rate limit on `/auth/*` than global

**Boundary discipline**
- [ ] Request body: typed DTO with `#[derive(Deserialize, Validate)]` + `req.validate()?`; never `Json<Value>` / `Json<HashMap>` / `Path<String>` for IDs
- [ ] No privilege fields (`role`, `is_admin`, `owner_id`, `tenant_id`, `verified`) on user-facing input DTOs - server-set only
- [ ] Response is a DTO (`UserResponse::from(u)`), not raw `FromRow` struct - prevents `password_hash` / `mfa_secret` leak as columns are added
- [ ] File uploads: type via `infer::get(&bytes)`, size capped via `RequestBodyLimitLayer`, save path canonicalized

**Rust-specific vulnerability patterns**
- [ ] Untrusted deserialization: `bincode` / `rmp_serde` / `ciborium` have gadget surfaces - prefer `serde_json`. `#[serde(untagged)]` on untrusted enums - prefer `#[serde(tag = "type")]`
- [ ] Runtime templates from user input (`tera::Tera::one_off(user, ...)`) is SSTI; `askama` is compile-time-checked
- [ ] CSPRNG: `rand::rngs::OsRng` / `getrandom` for tokens; never `rand::thread_rng`
- [ ] HMAC / signature compare via `subtle::ConstantTimeEq`; never `==` on `&[u8]`
- [ ] Webhook signatures: raw `bytes::Bytes` body before JSON parse; constant-time verify
- [ ] SSRF: allowlist rejects (a) `169.254.169.254` + IPv6 equiv, (b) `127.0.0.0/8` / `::1`, (c) RFC1918, (d) link-local; resolve host **after** parse and re-check at request time (DNS rebinding)
- [ ] `reqwest::Client::builder().danger_accept_invalid_certs(true)` only behind documented test fixture
- [ ] Open redirect: `Redirect::to(&input)` validated against allowlist or `starts_with('/') && !starts_with("//")`
- [ ] Background-task payload re-validated by consumer when queue is reachable from untrusted input
- [ ] `tracing` floor `info` in prod (never `debug`/`trace`); `console_subscriber` gated behind feature flag; `RUST_BACKTRACE=full` not in error responses

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write the assembled output; print the confirmation line.

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

[2-3 sentence assessment calling out Rust-specific risks: missing auth middleware on sub-router, mass assignment via `serde_json::from_value::<Domain>`, raw SQL via `format!`, exposed `console_subscriber`, `danger_accept_invalid_certs(true)`, `unsafe` without SAFETY comment.]

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

_One row per category; `yes` rows must correspond to a Finding below. Do not duplicate as standalone findings._

## Findings

### Critical

- **Location:** [file:line, or comma-separated for multi-site]
- **Issue:** [Rust-idiom name - e.g., "`OrderHandler::update` calls `serde_json::from_value::<Order>(req.body)?`; client submits `{ \"user_id\": 999 }` and overrides owner via mass assignment"]
- **Threat label:** one of: **(a) Exploit** - the weakness is attackable now; give a concrete walkthrough; **(b) Regression risk** - protection holds today but a future refactor could silently drop it; **(c) Topology-dependent** - the attack needs infra not visible in diff. Removing a protection that was live (auth deletion, opened CORS) is Exploit, not Regression risk - the gap is open now, not next refactor. When a finding is both a standalone Exploit and an escalation gated by infra (SSRF: exploitable against internal hosts now, metadata-credential reach is topology-dependent), label Exploit and name the topology condition as the escalation. Do not invent an exploit when the realistic threat is genuinely only regression or topology.
- **Severity rationale:** [tier] per rubric - [which clause applies]
- **Fix:** [Rust remediation with code]

### High / Medium / Low

[Same structure. Omit empty sections. If all empty: "No security issues found."]

## Recommendations

[Prioritized hardening not tied to a specific finding - e.g., "Add `tower_governor` rate limit on /auth/login", "Migrate `bcrypt` to `argon2` for new hashes", "Move JWT_SECRET to Vault", "Add `cargo deny check advisories` to CI".]

## Next Steps

Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting, dependency upgrade, threat-model exercise). Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [one-line action]

_Omit if no security issues found._
```

## Self-Check

- [ ] **Step 1**: `behavioral-principles` loaded (or accepted as pre-loaded)
- [ ] **Step 2**: stack confirmed Rust / Axum; `Data Access`, `JWT Library`, `Password Hash` recorded
- [ ] **Step 3**: `review-precondition-check` ran (or handle received from parent); diff and log read once and reused; on `head_matches_current=false`, approval obtained
- [ ] **Step 4**: security surface (router / middleware order, auth module, CORS, rate limiter, changed handlers / DTOs / queries / migrations, config, `Cargo.lock`, `deny.toml`) read directly; prior revision consulted when middleware was removed
- [ ] **Step 5**: `rust-security-patterns` applied against the Step-4 surface; canonical rules not restated
- [ ] **Step 6**: authorization drift, boundary discipline, and Rust-specific vulnerability patterns checked against the diff; severity rubric applied; every finding has a Threat label (Exploit / Regression risk / Topology-dependent)
- [ ] **Step 7**: report written via `review-report-writer`; confirmation line printed
- [ ] OWASP Triage produced with one verdict per category; `yes` rows correspond to Findings (not duplicated as standalone)
- [ ] Items needing infra/repo access flagged as "could not verify from diff alone - separate audit" (e.g., Sentry `before_send`, `cargo audit` clean, CORS runtime config)

## Avoid

- State-changing git commands (`fetch`, `checkout`) - the user runs these
- Findings without a Threat label (Exploit / Regression risk / Topology-dependent)
- Duplicating OWASP triage rows as standalone findings
- Generic advice when a Rust idiom applies ("apply `.route_layer(middleware::from_fn(auth))`", not "add authorization")
- Restating `rust-security-patterns` rules in findings - cite the pattern by name
- Disabling middleware to silence a failing test - fix the test
- Conflating with general code review or perf review - delegate
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
