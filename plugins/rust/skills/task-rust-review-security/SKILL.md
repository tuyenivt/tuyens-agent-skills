---
name: task-rust-review-security
description: Rust / Axum security review - auth layers, jsonwebtoken, validator DTOs, sqlx injection, serde mass assignment, unsafe, cargo-audit, OWASP Top 10.
agent: rust-security-engineer
metadata:
  category: backend
  tags: [rust, axum, sqlx, security, jwt, owasp, cargo-audit, cargo-deny, workflow]
  type: workflow
user-invocable: true
---

# Rust Security Review

Rust-aware security review naming Axum auth layers and extractors (`middleware::from_fn_with_state`, `FromRequestParts`), `jsonwebtoken` `Validation`, `validator` DTOs, sqlx parameterization (`query!`, `QueryBuilder::push_bind`), password hashing (`argon2`, `bcrypt`), Rust-specific risks (`Command::new("sh")` injection, `Path::join` traversal, serde mass assignment by deserializing a request body into a domain struct, `unsafe`), and dependency hygiene (`cargo audit`, `cargo deny`). Produces findings with attack scenarios and concrete Rust remediations.

Stack-specific delegate of `task-code-review-security` for Rust.

## When to Use

- Rust/Axum PR security regression review
- Pre-deployment hardening on auth, authz, file upload, payment, PII code
- Periodic validation and middleware drift sweep
- Auditing a JWT flow, new auth middleware, new `unsafe`, or new crypto usage

**Not for:** perf review (`task-rust-review-perf`), general review (`task-rust-review`).

**Depth.** This workflow always runs full - security has cliff-edge consequences. Scope by file, not by depth. A parent-supplied depth is ignored; the Summary and the writer's `depth` always carry `deep`.

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format; they are rule sets here, and only this skill's Output Format is emitted. Where this rubric and `rust-security-patterns` disagree on a tier, this rubric wins; a defect this rubric does not classify takes the higher of the two tiers, naming the clause applied.

## Severity Rubric

| Severity     | Definition |
| ------------ | ---------- |
| **Critical** | Unauthenticated RCE, auth bypass, mass data exfiltration, working SQL injection (`sqlx::query(AssertSqlSafe(format!(..., user_input)))`, `QueryBuilder::push(user_input)`), `Command::new("sh").arg("-c")` with user input, secrets / signing keys committed, JWT signature checking disabled (`Validation::insecure_disable_signature_validation()`). Must fix before deploy; blocks merge. |
| **High**     | Authenticated privilege escalation, IDOR with sensitive data, SSRF reaching cloud metadata / internal services, mass assignment granting admin (a body deserialized straight into the domain struct), missing auth layer on a user-data route, path traversal via `Path::join` with no component or canonicalize-and-`starts_with` guard, a response that serializes a secret (`password_hash`, `mfa_secret`, a token), a profiling or `console_subscriber` endpoint on the production listener without auth, `unsafe` with no `// SAFETY:` invariant on attacker-reachable input. Also: **a control removed outright, or degraded until it no longer does its job**, with nothing replacing it - `iss`/`aud`/`exp` validation deleted (`validate_exp = false`, `validate_aud = false`), an algorithm pin removed, TLS verification disabled (`danger_accept_invalid_certs(true)`, a no-op rustls verifier), a work factor dropped to the library's floor, a brute-force limit widened by an order of magnitude on a credential endpoint. Must fix before merge. |
| **Medium**   | Hardening gap with mitigating control elsewhere (missing CORS allowlist when proxy enforces origin), missing `validator` rules on DTO fields, debug exposure on non-prod, **resource exhaustion** reachable without auth (`DefaultBodyLimit::disable()` with no `RequestBodyLimitLayer`, unbounded upload or fetch, an `unwrap()` on attacker input under `panic = "abort"`), and a **control narrowed but still doing its job** (a limit loosened within a defensible range, a cost lowered but still above the recommended floor). Should fix this PR or next. |
| **Low**      | Defense-in-depth, dependency advisory below actively-exploited (`cargo audit` warning, unmaintained crate), hardening without a concrete current attack - a raw `FromRow` struct in `Json(...)` that today serializes nothing sensitive is Low with framing (b). |

**Money and entitlement integrity** rates by what the attacker controls: a value they can set that moves money or grants access is High, Critical when unauthenticated; a value they can only observe is Medium.

**Rate a weakened control by what it still stops, not by whether the line was deleted.** Removal and degradation-to-uselessness are the same defect; `validation.validate_aud = false` beside a populated `set_audience` is a deletion written as an assignment. A removed check makes a pre-existing finding newly reachable only when the removed control guarded that finding's path.

**A control that is absent but currently inert is Medium with framing (b), not its rubric tier.** A checklist row can fail while the exploit it guards is blocked elsewhere - `tower_http::services::ServeDir` rejects `..` components, so an unguarded request path it serves does not escape; `jsonwebtoken` has no `none` algorithm and rejects an algorithm whose family does not match the `DecodingKey`, so an algorithm taken from `decode_header` forges nothing while the key stays `DecodingKey::from_secret`. Name what is holding it back and what would remove that, instead of writing an exploit the code does not permit or dropping the finding. This carve-out does not apply when the blocker is itself in the diff, or is a value the team can change without review. It overrides `rust-security-patterns`' severity tiers for this workflow's reports. A raw struct in `Json(...)` that serializes nothing sensitive stays Low per the rubric; neither this carve-out nor `rust-security-patterns`' defense-in-depth tier raises it.

**Combined-finding rule.** When two or more findings *compose* on the same code path into a worse threat than either alone, file as a single finding at the elevated severity. Composition is judged on the resulting threat, not on independent exploitability - both halves of every example below are exploitable alone, and they still compose:

- Missing auth layer (High) + mass assignment on the *same handler* (High) = **Critical** unauthenticated admin override
- Missing ownership check (High) + `FromRow` struct in `Json(...)` exposing `password_hash` (High) on the *same handler* = **Critical** account takeover
- SSRF (High) + reachable from an unauthenticated route (High) = **Critical** unauth SSRF

When several bullets fire on one handler, file **one** finding at the elevated tier listing every constituent - not one per bullet. Split only when the findings sit on different code paths, or when no composition produces a threat worse than the stronger half alone (then each stands at its own severity). This replaces any per-category or `Chain:` split a loaded atomic prescribes: constituents merge and no `Chain:` line is emitted.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-rust-review-security` | Current branch vs base; fails fast on trunk |
| `/task-rust-review-security <branch>` | `<branch>` vs base (3-dot) |
| `/task-rust-review-security pr-<N>` | PR head fetched into local branch (user runs fetch) |

**Subagent runs** (of `task-code-review-security` or `task-rust-review`). The parent passes the `review-precondition-check` handle, `base_ref` / `head_ref`, `base_sha` / `head_sha`, the pre-read diff and commit log, the pre-confirmed stack, and the data-access mix. Step 3 is skipped whole, SHA capture included - never re-run git. Steps 9 and 10 are skipped (the parent verifies and reconciles the merged set once): labels come from the tier (Critical / High -> `[Must]`, Medium / Low -> `[Recommend]`), a finding whose cited line the diff did not add carries `_(pre-existing)_` and no other annotation (the parent's verify adds `newly reachable via`) so the parent's verify pass starts from it, and the `Findings verified` and `Round` lines are omitted. Step 11 returns **the entire Output Format below except the report file** - Summary, OWASP Triage, Findings, Out of Lens, Recommendations, Next Steps - not the `## Findings` section alone; the parent's merge consumes all of it.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. A subagent loads it too, unless the spawning prompt inlined its whole Rules section and its unverifiable-change disclosure, as that skill specifies.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Rust, stop and recommend `/task-code-review-security`.

Versions come from the repository - the Rust version from `rust-toolchain.toml`'s `channel`, else `Cargo.toml`'s `rust-version`, with the `edition`; the HTTP framework and data-access crates as resolved in `Cargo.lock` - and override any version a `## Tech Stack` line declared (this step's one departure from `stack-detect`'s instruction-file precedence); in a Cargo workspace the member crate under review decides, its `Cargo.toml` (and any `[workspace.dependencies]` it inherits) read in place of the detected primary stack. The `Stack` slot is `stack-detect`'s rendering with those versions added (`Rust 1.94 (edition 2024) / Axum 0.8.9`, `Rust 1.94 (edition 2024) (no framework detected)`), and the writer's `stack` is `rust-<framework>` lowercased (`rust-axum`, `rust-actix-web`; `rust` when there is none). The checks below name Axum constructs; on another framework apply each to that framework's equivalent and skip one that has none.

Detect: data access, JWT library (`jsonwebtoken`, `josekit`, `jwt-simple`), password hashing (`argon2` vs `bcrypt` vs `scrypt`). `Data Access` is the data-access crate the crate under review depends on directly - `sqlx`, `diesel` (`diesel-async` included), `SeaORM` (`sea-orm`) or `tokio-postgres` - with its `Cargo.lock` version; one present only transitively (the `sqlx` beneath SeaORM, the `tokio-postgres` beneath `diesel-async`) does not count, and two direct ones are `mixed`, both named with versions.

### Step 3 - Resolve Diff and Round

Standalone only - skip the whole step, SHA capture included, when a subagent received the handle.

Use skill: `review-precondition-check` with `report_type: review-security`. Any fail-fast: surface verbatim and stop. On success, print each handle `notes` entry in chat, one line each, before the report body (nothing when it has none; the handle itself stays internal). Capture `base_sha = git rev-parse <base_ref>` and `head_sha = git rev-parse <head_ref>` (full SHAs) and resolve the round below; only then read diff, log and `git diff -M --name-status <base_ref>...<head_ref>`, once, for reuse. The writer's `branch` is the handle's `head_short_name` in every invocation mode; `head_ref` is the handle's.

**Resolve the round from the handle, before any surface is read.** No `prior_checkpoint`, or `prior_checkpoint: legacy` -> `round: 1`. Valid -> `round = prior_checkpoint.round + 1`, `prior_head_sha = prior_checkpoint.head_sha`. **When `prior_checkpoint.head_sha` equals the current `head_sha`, print `No new commits on <head_short_name> since prior security review at <sha_short>. Prior report unchanged.` and stop** - do not re-review and do not overwrite (`<sha_short>` is the first 7 characters of `head_sha`). On a genuine round 2+, re-review the full range; Step 10 reconciles the prior findings.

### Step 4 - Read the Security Surface

Cite real lines. Open:

- `src/main.rs` + router construction - which sub-routers carry the auth layer and in what order layers wrap (`.layer` is bottom-up: the last added runs first; a `Router::layer` / `route_layer` wraps only the routes added **before** it, so a `.route(...)` chained after the auth layer is public). A public rate limit sits outside auth so `/auth/login` is covered
- The auth middleware or `FromRequestParts` extractor - JWT validation, claim extraction, rejection responses
- `CorsLayer` setup for the origin allowlist
- Rate limiter (`tower_governor`) on auth routes, and its key extractor (`SmartIpKeyExtractor` trusts `X-Forwarded-For`)
- Every changed handler - auth at sub-router level, ownership checks, request DTO type, `.validate()` call
- Every changed DTO's `validator` rules - `#[derive(Validate)]` and `#[validate(...)]` validate nothing until `.validate()` runs (or a `Valid<Json<T>>` / `Garde<Json<T>>` extractor wraps it)
- Every changed query for parameterization
- Config struct for `JWT_SECRET` / signing keys, allowed origins, env loading
- `Cargo.toml` / `Cargo.lock`, `deny.toml`, `audit.toml` for dependency versions, sources and waivers
- `.env.example` for documented env vars
- **Static file serving** - `ServeDir` / `ServeFile` and the directory each serves. A directory that is both writable by an upload handler and served on the app's own origin turns any upload defect into same-origin script execution; `ServeDir` picks `Content-Type` from the extension, not from whatever the handler validated

When the diff **weakens the authorization posture** - removes a layer, registers a new route outside the authed sub-router or after its `.layer`, drops `iss`/`aud`/`exp` validation, deletes alg-pinning, widens a limit, or lowers a work factor - `git log -p` the prior revision; the blame trail is authoritative. Any of these is evidence of Insecure Design (A06:2025); call it out even when each change looks "small" in isolation. The team's stated rationale ("internal only, behind the VPC", "we'll add it back later", "QA kept getting locked out") is not a compensating control - a network boundary is not authentication, and a schedule is not a control. Record each removal, the rationale offered, and why it does not compensate, in the Summary paragraph.

**Defects outside the diff.** A defect on a line the diff did not add: in this lens and made newly reachable by the diff -> a finding (Step 9 attributes it); in this lens and untouched by the diff -> a finding at its tier label with `_(pre-existing)_` (Step 9 de-escalates it to `[Recommend]`; on a subagent run the parent's verify does), at most the three most consequential (highest tier first), counting only findings this round publishes for the first time, the rest one line each under `## Out of Lens`; owned by another lens (a leaked task, a missing index) -> `## Out of Lens` with `file:line` and the owning lens.

### Step 5 - OWASP Triage (Rust Lens)

**Triage pass**, not findings list. Steps 6-8 produce findings. One verdict per category, from this enum, each with a one-clause reason:

| Verdict | When |
| ------- | ---- |
| `yes` | The listed signal, or another instance of that category, is present anywhere in the surface Step 4 read - including unchanged files. The `Rust signal` column is a starting list, not the category's definition: stored XSS via a served upload directory is `yes` on XSS even though the row names templates |
| `no signal in diff` | Checked, nothing found |
| `not verifiable here` | Settling it needs something outside the tree - a CI config, a deployment manifest, an advisory database, a live `cargo audit` run. Name what is missing |

| Risk | Rust signal |
|------|-------------|
| Broken Access Control | Route outside the authed sub-router or added after its `.layer`; missing ownership check |
| Injection | `AssertSqlSafe(format!(...))` passed to a `sqlx::query*()` call; `QueryBuilder::push` with user input; `Command::new("sh").arg("-c").arg(user_input)` |
| Cryptographic Failures | `md5` / `sha1` for auth; hardcoded JWT key; `SmallRng` / `fastrand` / a fixed seed for tokens; missing `argon2` / `bcrypt` |
| Security Misconfiguration | `CorsLayer::very_permissive()` or `AllowOrigin::mirror_request()` with credentials; ungated `console_subscriber` / profiling endpoint; no security headers |
| SSRF | `reqwest::get(user_url)` without allowlist; RFC1918 / metadata IP not rejected; redirects followed without re-check |
| XSS | `Html(format!("...{user_input}..."))`; askama `\|safe` on user input; `Tera::one_off(.., false)` with user data |
| Insecure Design (A06:2025) | Default-allow router (auth as a per-handler extractor someone must remember instead of a sub-router layer) |
| Authentication Failures (A07:2025) | JWT accepted with an algorithm from `decode_header` or without `iss` / `aud` / `exp` checks; no brute-force limit on a credential endpoint; session cookie flags missing |
| Software Supply Chain Failures (A03:2025) | Crate with a RustSec advisory; missing `cargo audit` / `cargo deny` in CI; git or unpinned registry source |
| Data Integrity (A08:2025) | `bincode` / `rmp_serde` / `ciborium` decode of an untrusted body with no size limit; request body deserialized into a domain struct; body limit disabled; unjustified `unsafe` |
| Logging & Alerting (A09:2025) | `#[instrument]` without `skip` on a handler taking a password or token; `Debug` derived on a secret-holding struct; missing auth event log; Sentry not stripping PII |
| Mishandling of Exceptional Conditions (A10:2025) | An auth or verification `Result` discarded so the request proceeds (`let _ = verify(&raw)`, `.ok()`, `.unwrap_or_default()`); `{e:?}` or a backtrace returned to the client |

### Step 6 - Apply the Pattern Bank

Use skill: `rust-security-patterns` for the canonical AuthN, AuthZ, validation, injection, crypto, secrets, and SSRF patterns. The skill owns the recipes; this workflow owns the diff-level triage below.

**AuthN diff triage:**

- [ ] Exact algorithm pinned with `Validation::new(Algorithm::RS256)` (or `ES256`); an algorithm read from `decode_header` is not a pin; `iss` / `aud` set via `set_issuer` / `set_audience`; `exp` enforced (`validate_exp` stays `true`, `exp` stays in `required_spec_claims`); `insecure_disable_signature_validation()` appears nowhere outside tests
- [ ] Access token lifetime short; refresh rotation; revocation surface (`jti` denylist or refresh UUID)
- [ ] Password hashing via `Argon2::default()` (Argon2id) or `bcrypt` cost >= 10, run inside `spawn_blocking`; verify via `PasswordVerifier`
- [ ] Auth rejection is 401 with no body details; brute-force rate limit on `/auth/login`, `/auth/refresh`, `/auth/reset-password`
- [ ] No `tracing` event or `#[instrument]` argument leaking JWT, password, or session cookie value; secrets held as `secrecy::SecretString` (redacted `Debug`, no `Serialize`)
- [ ] Cookie sessions (if used): `Cookie::build(...)` with `.secure(true)`, `.http_only(true)`, `.same_site(...)`; `PrivateCookieJar` / `SignedCookieJar` for server-trusted values

**AuthZ diff triage:**

- [ ] Every new route sits in an authed sub-router (added before its `.layer`) OR is explicitly public-listed (default-deny)
- [ ] Role / permission checks centralized in a layer or extractor, not scattered inline
- [ ] Per-owner lookups scope by principal at the repository (`WHERE id = $1 AND owner_id = $2`); another principal's resource is `404`, a wrong role `403`
- [ ] Multi-tenant queries scoped by `tenant_id` at the repository, not the handler
- [ ] CORS allowlist explicit; no `very_permissive()` / `mirror_request()` / `Any` for credentialed requests
- [ ] CSRF protection present iff auth model is cookie-session

**Input validation / mass assignment diff triage:**

- [ ] Typed `Json<Dto>` body with `.validate()` called (or a validating extractor); no `Json<serde_json::Value>` / `HashMap<String, Value>` / `#[serde(flatten)]` catch-all on a write path
- [ ] `#[validate(...)]` on every DTO field that has a bound; `#[serde(deny_unknown_fields)]` on mutation DTOs
- [ ] No privilege-bearing fields (`role`, `is_admin`, `owner_id`, `user_id`, `merchant_id`, `tenant_id`, `is_active`, `verified`) in input DTOs
- [ ] No request body deserialized into a domain or `FromRow` struct (`Json<User>`, `serde_json::from_value::<Order>(body)`)
- [ ] Response DTO (not the `FromRow` struct) returned; a struct serializing a secret is High, otherwise Low with framing (b)
- [ ] `Path<Uuid>` / `Path<i64>` and `Query<Typed>` for path / query params, not `Path<String>` parsed by hand
- [ ] File uploads: content type detected from bytes (`infer::get`), size capped (`DefaultBodyLimit::max` / `RequestBodyLimitLayer`), stored outside any served directory, filename never used as the path
- [ ] Path traversal guarded by accepting only `Component::Normal` components, or `canonicalize` of the joined path checked with `Path::starts_with` against the canonical base; `base.join(user)` alone is a finding (an absolute `user` replaces the base), and so is a `str::starts_with` prefix check
- [ ] `Command::new(program).args([...])` with an arg slice; no `sh -c` / `cmd /C` with user input

### Step 7 - Rust-specific Vulnerability Patterns

Pattern bank in `rust-security-patterns`. Diff-level checks:

- [ ] No `format!` interpolation into SQL; `query!` / `query_as!` with `$1`, `.bind(...)` on runtime queries, `QueryBuilder::push_bind` for dynamic parts; a dynamic `ORDER BY` column chosen from a fixed `match`, never pushed raw
- [ ] No runtime template built from user input (`Tera::one_off(user_template, ..)` is SSTI); askama templates compile-time and autoescaped, with no `|safe` on user data
- [ ] No `bincode` / `rmp_serde` / `ciborium` decode of an untrusted body without a size limit (a length prefix drives the allocation); JSON bodies stay under Axum's default body limit, or a deliberate `DefaultBodyLimit::max`
- [ ] `unsafe` blocks audited: each carries a `// SAFETY:` invariant, the crate root has `#![forbid(unsafe_code)]` where none is needed; edition 2024 `unsafe { std::env::set_var(..) }` after the runtime starts is a data race
- [ ] No panicking `unwrap()` / `expect()` / slice index on attacker-controlled input in a handler; under `panic = "abort"` one request kills the process, otherwise `CatchPanicLayer` keeps it a 500
- [ ] No `danger_accept_invalid_certs(true)` / custom no-op `ServerCertVerifier` outside a test fixture
- [ ] Open redirect: `Redirect::to(&input)` validated against an allowlist, or relative-path-only (`starts_with('/') && !starts_with("//")`)
- [ ] Tokens, nonces, secrets from `OsRng` / `getrandom` / `rand::rng()` (a CSPRNG); never `SmallRng`, `fastrand`, or a `seed_from_u64` RNG
- [ ] HMAC / signature compare via `Mac::verify_slice` or `subtle::ConstantTimeEq` - not `==` on bytes
- [ ] `tracing` level `info` or stricter in prod; `console_subscriber` / profiling endpoint behind a cargo feature or admin auth; no `{e:?}` in client responses
- [ ] SSRF: user-controlled outbound URL resolves and rejects metadata / loopback / RFC1918 / link-local, connects to the checked IP (a filtering `dns_resolver`), and re-checks or disables redirects (`redirect::Policy::none()`)
- [ ] Webhook: raw body via a `Bytes` extractor (the last extractor) before parsing; signature via `Mac::verify_slice`; route outside the JWT sub-router; body capped **before** the read; **replay window enforced** - the signed timestamp is parsed and compared to the clock (reject beyond ~5 min), not merely folded into the MAC. Binding `t` into the signature stops an attacker editing it; only a clock comparison stops replaying the original `(t, sig, body)` triple, and a dedup table with no retention policy is a weaker substitute
- [ ] Postgres job queue / Kafka / AMQP / in-process queue payload trust: re-validate inside the consumer or job handler whenever the queue is a second entry path to a value an HTTP-boundary control protected, or the broker is reachable by anything outside this service - not only when the payload's original source is untrusted. A signed webhook that enqueues an amount, which the worker then writes without re-checking, has moved the trust boundary to the broker
- [ ] `cargo audit` (or `cargo deny check advisories`) clean in CI; `deny.toml` `[sources]` rejects unknown registries and git sources; every `audit.toml` waiver carries a reason. `cargo audit` needs the RustSec advisory database; when it is unavailable, record `not verifiable here` in the triage and say so in the finding rather than implying a clean result

### Step 8 - Data Protection

- [ ] PII / sensitive encrypted at rest (`aes-gcm`, KMS, or DB column encryption)
- [ ] No `FromRow` struct returned from handlers (new columns leak silently when added later)
- [ ] `tracing` redaction: never log `password`, `token`, `credit_card`, `ssn`, `api_key`; `#[instrument(skip(...))]` / `skip_all` on handlers taking them; secret-holding types wrap `SecretString` or hand-write `Debug`
- [ ] No sensitive data in URLs (logs / browser history / referer)
- [ ] TLS enforcement at LB; HSTS and security headers via `SetResponseHeaderLayer`
- [ ] DB backups encrypted; access controlled
- [ ] Secrets via a typed config struct loaded once at startup into `AppState`, failing fast when absent; no scattered `std::env::var`; `.env` gitignored

### Step 9 - Verify Findings

Assign each draft finding its label first - Critical / High -> `[Must]`, Medium / Low -> `[Recommend]` - because `review-finding-verify` takes labelled findings as input and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - it de-escalates `[Must]` to `[Recommend]` on untouched pre-existing code, and that survives into the finding heading and into Next Steps. Never re-derive a label from the severity tier after this step; a `### Critical` finding tagged `[Recommend]` because it is pre-existing is the correct output, not a contradiction. Carry its `Annotation` column verbatim onto the heading (`_(pre-existing)_`, `_(pre-existing; newly reachable via <file:line>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`; only Step 10's projection splits the combined group) and its tally into the Summary's `Findings verified` slot; the tally counts this round's drafts only. A finding on a file the name-status does not list gets `_(pre-existing)_`, written first, unless its annotations already have a group opening `pre-existing` or `unverified`. The verify table is working material; only the tally and the surviving rows' labels and annotations reach the report.

Subagent runs skip this step entirely (see Invocation).

### Step 10 - Reconcile Prior Findings (round 2+, standalone)

Skip on round 1. Otherwise read the prior report at the handle's `report_path` and project its findings into the reconciler's shape: `## High-Impact Findings` holding one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, the label and `file:line` copied from the `#### <n>. [Label] file:line` heading, annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` becomes `_(pre-existing)_ _(newly reachable via X)_`). Use skill: `review-prior-findings-reconcile` with `prior_report` (the projection), `diff`, `name_status`, `head_sha`, `base_ref`, and `head_files` (`git ls-tree -r --name-only <head_sha>`). Insert its output - the table, any note lines, the tally line - under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows re-enter `## Findings` with the body the prior report gave them, cited where reconcile places the smell now, under the severity heading they were last published under (re-rated only when this round re-drafted the defect; the tier its `Severity rationale` names when the prior heading combined several), with the label and annotation groups they were last published with (`_(pre-existing)_` written first when the name-status does not list the file and no group opens `pre-existing` or `unverified`) plus `_(carried from round <N>)_` (N = the round that first raised it, written once) on the heading, so the next round reconciles them again; when this round re-drafted the same defect at the same site, publish only the re-drafted finding with that annotation appended. The table keeps the prior label and line verbatim.

### Step 11 - Write Report

Standalone only - subagent runs return the Output Format to the parent, which writes the single merged report.

Use skill: `review-report-writer` with `report_type: review-security` and every required input: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3, `stack` per Step 2, `scope: +sec`, `depth: deep` (this workflow always runs full depth), `mode: full`, and the `round` / `prior_head_sha` resolved in Step 3. Write before ending; print confirmation.

## Self-Check

Mark a line N/A with its reason when the diff has no matching surface, or when the invocation mode makes it inapplicable (subagent, round 1).

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: stack confirmed Rust (or stopped with `/task-code-review-security`); data-access mix with versions, JWT library, password hash recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-security` (or handle received); diff, log and name-status read once; `base_sha` / `head_sha` captured; round resolved from the handle; same-SHA no-op honoured; approval obtained when `head_matches_current` was false
- [ ] Step 4: security surface read directly; layer order and routes added after the auth layer checked; static file serving checked; prior revision consulted when a control was removed; defects outside the diff routed per the Step 4 rule
- [ ] Step 5: OWASP triage produced one verdict per category from the three-value enum, with a reason; not duplicated as standalone findings
- [ ] Step 6: `rust-security-patterns` applied; AuthN, AuthZ, DTO / mass-assignment triage done; **every new route has an auth layer OR is explicitly public-listed**
- [ ] Step 7: injection, templates, binary decoders, `unsafe`, panics on input, TLS verification, redirect, randomness, constant-time compare, debug surfaces, SSRF, webhook, queue trust, `cargo audit` / `cargo deny` checked where the diff touches them
- [ ] Step 8: data protection (encryption at rest, struct on the wire, `tracing` redaction, secrets in URLs, TLS / HSTS, typed config) checked
- [ ] Step 9 (standalone): findings labelled before verify; verify's labels and annotations carried onto the headings verbatim; tally in the Summary
- [ ] Step 10 (round 2+): prior report projected and reconciled with `head_sha` and `base_ref`; table inserted; `Still open` / `Needs re-check` rows carried into Findings
- [ ] Step 11 (standalone): report written via `review-report-writer` with all checkpoint fields; confirmation printed. Subagent: Output Format returned, no file written
- [ ] Severity rubric applied consistently; every finding has an attack scenario, "regression risk" rationale, or "topology-dependent" framing
- [ ] Next Steps tagged `[Implement]` or `[Delegate]`, ordered Must > Recommend (omitted only when no issues)

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Fill rules.** `Overall Posture` counts every published finding by tier, whatever its label: `Issues Found - <N> Critical / <N> High / <N> Medium / <N> Low`. `Depth` is always `deep`. `Password Hash` is `argon2 | bcrypt | scrypt | weak (<algorithm>) | none | not observable` - `weak` for an unsalted or fast digest (`sha2`, `md5`) used as a password hash, `none` for a password stored or compared in plaintext, `not observable` when the tree neither hashes nor verifies a stored password (a verify call alone settles it: `Argon2::default().verify_password` is `argon2`). `Authorization` is `sub-router auth layer + ownership checks | per-handler extractor | inline checks | partial - <where missing> | none`. `Findings verified` is omitted on subagent runs, its parenthetical when K is 0. Any field whose value the repo cannot settle takes the value plus `(inferred from <evidence>)`.

**Each finding is its own numbered block** under its severity heading, headed `#### <n>. [Label] file:line _(annotations)_` where the label and annotations come from Step 9 verbatim (tier-derived label and `_(pre-existing)_` on subagent runs; `_(carried from round <N>)_` on carried findings). Numbering continues across tiers so Recommendations and Next Steps can cite `finding <n>`. Blank lines separate the field lines; consecutive bare `**Label:** value` lines collapse into one paragraph when the report renders.

```markdown
## Rust Security Review Summary

- **Stack:** Rust <version> (edition <edition>) / <framework> <version> | Rust <version> (edition <edition>) (no framework detected)
- **Data Access:** sqlx <version> | diesel <version> | SeaORM <version> | tokio-postgres <version> | mixed - <both, named>
- **JWT Library:** jsonwebtoken <version> | josekit <version> | jwt-simple <version> | none
- **Password Hash:** argon2 | bcrypt | scrypt | weak (<algorithm>) | none | not observable
- **Authorization:** sub-router auth layer + ownership checks | per-handler extractor | inline checks | partial - <where missing> | none
- **Depth:** deep
- **Overall Posture:** Clean | Issues Found - <N> Critical / <N> High / <N> Medium / <N> Low
- **Round:** <N>                                {round 2 onward; omitted on subagent runs}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff)

[2-3 sentence assessment naming Rust-specific risks: a route outside the auth layer, a body deserialized into the domain struct, SQL built with `format!`, an exposed `console_subscriber`, `danger_accept_invalid_certs(true)`, `unsafe` without a `// SAFETY:` invariant. When the diff weakened the authorization posture, this is where each removed control, the rationale offered for it, and why that rationale is not a compensating control are recorded.]

## OWASP Triage

| Category                  | Verdict                                             | Reason                                  |
| ------------------------- | --------------------------------------------------- | --------------------------------------- |
| Broken Access Control     | yes \| no signal in diff \| not verifiable here     | [signal cited, or what is missing]      |
| Injection                 | ...                                                 | ...                                     |
| Cryptographic Failures    | ...                                                 | ...                                     |
| Security Misconfiguration | ...                                                 | ...                                     |
| SSRF                      | ...                                                 | ...                                     |
| XSS                       | ...                                                 | ...                                     |
| Insecure Design           | ...                                                 | ...                                     |
| Authentication Failures   | ...                                                 | ...                                     |
| Supply Chain Failures     | ...                                                 | ...                                     |
| Data Integrity Failures   | ...                                                 | ...                                     |
| Logging & Alerting        | ...                                                 | ...                                     |
| Exceptional Conditions    | ...                                                 | ...                                     |

## Prior Round Reconciliation     {round 2+ only; omit otherwise}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

<note line>     {one paragraph per note line reconcile emitted; omit when none}

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Findings

### Critical

#### 1. [Must] file:line _(annotations)_     {annotation groups only when Step 9, Step 10, or the subagent rule assigned any}

- **Location:** [file:line]

- **Issue:** [vulnerability in Rust terms - e.g., "`update_order` extracts `Json<Order>` and writes it back; client submits `{ \"user_id\": 999 }` and overrides the server-assigned owner because there is no separate request DTO"]

- **Attack scenario:** [pick one and label: (a) concrete exploit; (b) "Regression risk: next refactor silently removes one of these protections"; (c) "Topology-dependent: depends on whether reverse proxy strips X-Forwarded-For correctly". When two apply, label the one that sets the tier and name the other in a clause. Do NOT invent an exploit when the realistic threat is regression or topology.]

- **Severity rationale:** [tier] per rubric - [which clause applies; when a composition elevated it, name the constituents]

- **Fix:** [specific Rust remediation with code]

#### 2. [Must] file:line

[Same block]

### High

[Same blocks, numbering continues across tiers]

### Medium

[Same blocks]

### Low

[Same blocks]

Omit severity sections with no findings. When every section is empty, write "No security issues found." A composition that empties the High tier by folding its constituents into a Critical is expected - say so in the Summary assessment so the distribution does not read as miscalibrated.

## Out of Lens

[Defects noticed while reading the surface that another lens owns, and pre-existing in-lens defects beyond the three published - each with `file:line` and the owning lens. Omit when there are none.]

## Recommendations

[Prioritized hardening not tied to a finding]

## Next Steps

Each tagged `[Implement]` or `[Delegate]` (`[scope: <owning lens or team>]` on delegated items; a row spanning files lists them comma-separated). Order: Must > Recommend. Each item carries its finding's label as published; one row per finding, naming a shared edit on the row rather than repeating it.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: platform team] - [one-line action]

_Omit if no issues found._
```

## Avoid

- `git fetch` / `git checkout` from this workflow
- Writing a report when invoked as a subagent - the parent owns it
- Reporting without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"admin\"}` and gains admin via mass assignment")
- Generic advice when a Rust idiom applies ("put the route in the sub-router carrying `.layer(from_fn_with_state(state, require_auth))`", not "add authorization check")
- Disabling middleware to silence a failing test - fix the test
- Widening authorization (a route moved out of the authed sub-router, a removed JWT check) without a security review note
- Conflating security with general or perf review
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
