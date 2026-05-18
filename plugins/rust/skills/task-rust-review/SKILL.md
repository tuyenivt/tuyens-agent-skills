---
name: task-rust-review
description: Rust / Axum / sqlx / Tokio code review: unwrap, panic, Mutex-across-await, task leaks, SQL injection; spawns perf/security/obs subagents.
agent: rust-tech-lead
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Rust Code Review

## Purpose

Rust-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with Rust-specific correctness, architecture, AI-quality, and maintainability checks (`.unwrap()` / `.expect()` in production paths, `panic!` in service code, `Result` that should be `Result<_, AppError>` but leaks `sqlx::Error`, `std::sync::Mutex` held across `.await`, fire-and-forget `tokio::spawn` without `JoinHandle` or `JoinSet`, missing `CancellationToken` on long-lived tasks, sqlx string-interpolation SQL via `format!`, missing extractor validation on Axum handlers, unbounded `tokio::sync::mpsc::unbounded_channel()`, blocking I/O on the runtime without `spawn_blocking`, `Arc<Mutex>` where single ownership suffices, single-implementation traits). Coordinates Rust-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for Rust. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved so callers see a stable shape. **Runs standalone** with full PR/branch resolution - the core dispatcher is optional, not required.

## When to Use

- Reviewing a Rust/Axum PR before merge
- Post-AI-generation quality gate on a Rust change set
- Architecture drift detection in a Rust codebase
- Pre-merge risk assessment on a Rust branch

**Not for:**

- Pre-implementation feature design (use `task-rust-implement`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error / panic debugging (use `task-rust-debug`)
- Architecture/design review of a new system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-rust-review-perf`, `task-rust-review-security`, or `task-rust-review-observability`

## Depth Levels

Mirrors `task-code-review`:

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full Rust staff-level review                                    | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface this in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                |
| --------------- | ------------------------------------------------------------------------ |
| Core            | Phases A-E only (Rust-flavored)                                          |
| + Perf          | Core + parallel subagent: `task-rust-review-perf`                        |
| + Security      | Core + parallel subagent: `task-rust-review-security`                    |
| + Observability | Core + parallel subagent: `task-rust-review-observability`               |
| Full            | Core + Performance + Security + Observability (3 parallel Rust subagents)|

Default: **Core with auto-escalation** (same signal rules as `task-code-review`). Pass `core-only` to suppress.

**Scope auto-escalation signals (Rust-tuned):**

- File uploads (`axum::extract::Multipart`, `TempFile`), JWT middleware / auth changes (`jsonwebtoken`, `axum::middleware::from_fn` for auth), extractor type changes (request DTOs deriving `Deserialize` + `Validate`), raw SQL via `sqlx::query(&format!(...))` / `sqlx::query_as(&format!(...))`, secrets in env / config, background tasks reading user-supplied input (Tokio task queues, Kafka consumers via `rdkafka`), `serde_json::from_value::<DomainModel>(req.body)` patterns, `unsafe` blocks → auto-add **+Security**
- New sqlx migration file, new `sqlx::query_as!` / `query!` invocation, new `JOIN` in raw SQL, new pagination, new endpoints with payloads, loops calling DB or HTTP, new in-process cache (`moka` / `dashmap`) or Redis read paths, new `tokio::spawn` / `JoinSet` fan-out → auto-add **+Perf**
- New module (`mod`) / crate, new external client (`reqwest::Client`, `redis::Client`, `aws-sdk-*`), new background worker / Kafka producer / consumer, change to logging config (`tracing_subscriber` setup, layer composition), new `metrics::counter!` registration, new `console_subscriber` (tokio-console) integration, lifecycle changes (graceful shutdown, signal handling) → auto-add **+Observability**
- Two or more signal categories present → promote to **Full**

## Invocation

The slash command accepts an optional argument identifying the diff to review:

| Invocation                   | Meaning                                                                                                                                                                               |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-rust-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                           |
| `/task-rust-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                     |
| `/task-rust-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants) |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs and never modifies your working tree.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>` so the diff is computed against the true base.

Examples:

- `/task-rust-review pr-123 --base release/2026.05` - PR opened against release branch
- `/task-rust-review feature/x --base develop` - branch off `develop` rather than `main`

Scope and depth flags compose: `/task-rust-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every subsequent step (think before acting, surgical changes, surface confusion, push back when the user is likely wrong). When invoked as a subagent of `task-code-review`, accept the parent's confirmation that this skill is already loaded; do not re-load.

### Step 2 - Confirm Stack and Detect Async / Data-Access Surface

Use skill: `stack-detect` to confirm Rust / Axum. If invoked as a delegate of `task-code-review` (parent already detected Rust), accept the pre-detected stack and skip re-detection. If the detected stack is not Rust, stop and tell the user to invoke `/task-code-review` instead.

Detect runtime: Tokio (`tokio` in `Cargo.toml`) - assumed default for Axum; flag if absent or if `async-std` / `smol` is in use. Detect data access: sqlx (`sqlx` in `Cargo.toml`) - the primary expectation; flag diesel as a secondary path. Detect messaging: in-process Tokio task queue, `lapin` (AMQP), `rdkafka` (Kafka), or none. Record `Runtime: Tokio`, `Data Access: sqlx | diesel | mixed`, `Messaging: Tokio queue | AMQP | Kafka | none`. Each Phase B / C / D / E checklist below branches on this signal where the idiom differs.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). Forward `--base <branch>` if the user passed it.

If the precondition check stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

Once approved, read the diff and commit log directly using the returned refs:

- Diff: `git diff <base_ref>...<head_ref>`
- Files changed: `git diff --name-status <base_ref>...<head_ref>`
- Commit log: `git log --oneline <base_ref>..<head_ref>`

All subsequent phases operate on this read-once diff and log; do not re-derive them.

**Skip this entire step** when invoked as a subagent of `task-code-review` and the parent passed the precondition handle plus pre-read diff and commit log. Reuse the parent's artifacts.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff content for the auto-escalation signals listed under **Scope** above. Make this explicit because the default of "skip if user did not pass `+security` etc." silently misses the cases where the change itself signals the need.

For each signal that fires, log a one-liner: `signal: <category> -> <file:line>`. Then decide:

- Zero signals or user passed `core-only` -> stay on Core
- One signal category -> add the matching extra scope
- Two or more signal categories -> promote to Full
- User passed an explicit scope -> respect it (do not downgrade), but still record signals so the Summary documents why the chosen scope was correct

Surface the decision in the Summary's `Scope:` field. If escalated, append `auto-escalated from Core; signals: <list>`. If the user passed a scope and signals contradicted it, surface a one-line note so reviewers see what was deliberately deferred.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (auth middleware, JWT validation, router composition, shared traits, `main.rs` / `lib.rs` wiring, sqlx migrations), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Step 4.5 - Re-evaluate Depth After Phase A

If `Blast Radius` (from Phase A) is `Wide` or `Critical` and the user did not explicitly pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)` in the Summary. Do this **before** launching Phases B-E so deep-only behaviors (historical pattern matching, cross-PR context, anemic-domain assessment) are in scope for the rest of the review.

### Phase B - Rust Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting state integrity, backward compatibility, transaction boundary correctness, async cancellation safety - through a Rust lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding `#[cfg(test)]` / integration test coverage, raise this as an explicit finding. At minimum a [Suggestion]; escalate to [High] when the change is in a critical path - any of: authentication (JWT validation, session middleware), authorization (ownership checks, role middleware), money or billing flows, data-integrity writes (multi-step transactions, state machines), background workers that mutate data, sqlx migrations that change column semantics. Do not bury this finding in Key Takeaways - a separate, named entry in Findings.

**Rust-specific correctness checks (delegate-heavy; see canonical owners):**

- [ ] **Error model**: no `.unwrap()` / `.expect()` / `panic!` in production paths (`.expect` allowed in `main.rs` for unrecoverable startup invariants); error chain preserved via `.context(...)` (anyhow) or `#[from]` (thiserror); errors mapped at layer boundaries (repo `sqlx::Error` → `AppError::NotFound` etc.); no `Box<dyn Error>` as domain return; log OR return, not both - see `rust-error-handling`
- [ ] **Async / cancellation**: no `std::sync::Mutex` across `.await`; every `tokio::spawn` has owner (`JoinHandle` / `JoinSet`); long-lived loops have `CancellationToken` + `tokio::select!`; no blocking I/O / CPU-heavy work on runtime (`bcrypt`, `std::fs`); `tokio::time::timeout` on every outbound HTTP/DB/queue call; bounded channels (`mpsc::channel(N)`); cancellation-safe multi-await (single transaction, not bare sequential debit/credit) - see `rust-async-patterns`, `rust-concurrency`
- [ ] **sqlx data access**: `query!` / `query_as!` for static SQL (no `format!` interpolation); N+1 via per-iteration query checked; transaction wraps multi-statement writes; background dispatch AFTER `tx.commit().await?` - see `rust-db-access`
- [ ] **Axum extractors / authz**: `Json(req): Json<DTO>` with `Validate` derives (no bare `Deserialize`-only DTOs); auth middleware at sub-router level AND ownership check in handler/service body (auth presence ≠ authorization); no `Redirect::to(&user_input)` without allowlist; no nested Tokio runtimes - see `rust-web-patterns`
- [ ] **Body-size limits**: `axum::extract::DefaultBodyLimit` / `tower_http::RequestBodyLimitLayer` configured globally and tuned per-route for `Json` / `Form` / `Multipart` (default 2MB applies cross-route; large uploads need explicit higher, streaming routes explicit lower)
- [ ] **No domain model returned from handlers** (`Json(user)` where `user: User` is a sqlx `FromRow` struct leaks every column - `password_hash`, `mfa_secret`, audit fields); map to a `*Response` DTO at the boundary
- [ ] **Response-DTO field-stripping audit**: even when a `*Response` DTO is used, audit for sensitive fields - `password_hash` / `encrypted_password`, `mfa_secret` / `otp_secret` / `recovery_codes`, `api_key` / `webhook_secret`, `internal_notes` / `audit_log`, `is_admin` / `role`, `deleted_at`, `last_login_ip`. Use `#[serde(skip_serializing)]` on private fields OR define an explicit `*Response` DTO. `#[serde(flatten)]` flagged as a particular smell (flattens the source struct's full field set)
- [ ] **No mass assignment via `serde_json::from_value::<DomainModel>(req.body)`** - define request DTO with explicit `Validate`-derived fields, map with explicit field copy
- [ ] **HTTP `Idempotency-Key` header on retry-prone POSTs (distinct from worker-side dedup)**: client→server replay protection via `request_idempotency` table or Redis with TTL keyed by `(tenant_id, idempotency_key)` storing `(response_status, response_body)`. On replay return stored response. Protects against retry storms (mobile flake, browser back-button). Distinct from worker-side message-dedup (`task.id` / `processed_jobs`) which handles queue redelivery - a system needs both
- [ ] **`unsafe` blocks** carry `// SAFETY:` comment justifying invariants; gratuitous lifetime annotations elided; `Arc` (not `Rc`) for cross-task sharing; `tracing` for structured logging (not `println!` / `eprintln!`)
- [ ] **Migration PRs (any change in `migrations/`)**: see the Migration PRs subsection below

**Migration PRs (any change under `migrations/` for sqlx-cli):**

- [ ] sqlx-cli reversible migrations: every `<timestamp>_<name>.up.sql` has a sibling `.down.sql` file present in the diff. Missing `.down.sql` is a finding (not a one-way "we'll document it later" exception) - revert path needs to exist before the change ships, even if rolling back means accepting data loss for the new column
- [ ] Two-phase deploys for column rename / drop (add new → backfill → cut over → remove old)
- [ ] `NOT NULL` on existing columns: PostgreSQL 11+ avoids a full table rewrite when `ADD COLUMN ... NOT NULL DEFAULT <constant>` is added (the default is stored in pg_attribute, not back-filled). For older Postgres versions, for non-constant defaults (`now()`, function calls), or for adding `NOT NULL` to an *existing* nullable column on a hot table, require the two-step (add nullable → backfill → set NOT NULL via separate migration). Do not flag `ADD COLUMN ... NOT NULL DEFAULT 'literal'` on PG11+ as unsafe by default - it is safe; the row count and PG version determine the verdict
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL); sqlx-cli files contain the raw SQL so this is explicit
- [ ] **`SET lock_timeout`** before DDL on large tables to fail fast
- [ ] Foreign keys added with validation deferred (or as a separate validate step)
- [ ] Data migrations isolated from DDL migrations; long-running data backfills not in the same migration as the schema change; backfills via keyset pagination, never `WHERE col IS NULL LIMIT N`
- [ ] After schema change, `cargo sqlx prepare` re-run and `sqlx-data.json` committed so offline-mode builds keep matching the schema
- Use skill: `ops-backward-compatibility` to assess client/session/in-flight-request impact
- Use skill: `rust-migration-safety` for canonical safe-migration patterns

**Concurrency safety:**

- [ ] No shared mutable global state (`static MUT_CACHE: Lazy<Mutex<HashMap<...>>>` mutated by request handlers); if state is required, encapsulate in a struct held in `Arc`, owned by the application state, with a clear ownership / locking story (`tokio::sync::RwLock` for read-heavy, `tokio::sync::Mutex` for write-heavy, `dashmap::DashMap` for sharded concurrent maps). `static mut` is `unsafe`
- [ ] Race-prone updates (counters, balance changes, state transitions) use database-level locking (`SELECT ... FOR UPDATE` via `sqlx::query!("... FOR UPDATE")` inside a transaction, or optimistic version field) - not in-process mutexes, which only protect a single replica
- [ ] HTTP clients (`reqwest::Client`) shared at app level (`Arc<Client>` in `AppState`) - per-request `reqwest::Client::new()` breaks connection reuse, defeats the connection pool, and triggers excess TCP / TLS overhead
- [ ] `cargo clippy --all-targets -- -D warnings` clean - lints catch many concurrency / lifetime / API-shape mistakes

Use skill: `rust-db-access` for canonical sqlx correctness patterns.
Use skill: `rust-error-handling` for thiserror / anyhow / `?` / `IntoResponse` patterns.
Use skill: `rust-async-patterns` for Tokio task lifecycle, `JoinSet`, `CancellationToken`, `select!`, `spawn_blocking` design.
Use skill: `rust-concurrency` for `Arc` / `Mutex` / `RwLock` / channels / `Send + Sync` review.
Use skill: `rust-web-patterns` for Axum routing, extractors, tower middleware, response patterns.
Use skill: `rust-messaging-patterns` for background-task / Kafka / AMQP patterns when the diff touches messaging.

### Phase C - Rust Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion.

**Rust-specific architecture checks:**

- [ ] **Layering**: `handler` → `service` → `repository` → `model`. Handlers extract / validate / delegate / respond - no business logic. Services hold business rules - no Axum extractors, no sqlx types. Repositories return domain types, not bare sqlx rows leaked upward. `main.rs` (or a dedicated `app::build()` function) wires constructors and the `AppState`
- [ ] **Traits defined at the consumer**: `OrderRepository` trait lives in the consuming module (typically `service`), not next to its `PgOrderRepository` implementation. The Rust idiom mirrors Go's "accept interfaces, return structs" - the trait belongs to the caller. Trait + single-impl in the same module with no second implementer and no test mock is a single-impl-trait smell (Phase D)
- [ ] **Constructor injection via `AppState`**: dependencies stored on a typed `AppState` struct (passed as `axum::extract::State<AppState>`); not via `lazy_static!` / `OnceCell` globals scattered across modules. Globals cause test-isolation failures and hidden coupling
- [ ] **Module boundaries**: feature-module layout (`src/orders/{handler,service,repository,model}.rs`) preferred over layer-module layout (`src/handlers/`, `src/services/`); cross-feature imports go through public service traits, not direct repository imports
- [ ] **`pub` discipline**: items not in the public API surface stay `pub(crate)` or unmarked; widening visibility without a caller is a smell
- [ ] **Anemic domain antipattern (deep depth only)**: when reviewing in `deep` mode and historical pattern matching shows business rules accumulating in `*_service.rs` files while domain `struct`s stay as bare data containers (no `impl` blocks beyond getters), flag for refactor via `task-rust-refactor`. Do **not** raise on a single PR's evidence alone
- [ ] **Settings discipline**: typed config struct (often via `figment` / `config` / `envy`) loaded once at startup and stored on `AppState`; no `std::env::var("X")` sprinkled across files - centralize so missing-at-startup fails fast
- [ ] **Multi-tenant isolation**: tenant scoping enforced at the repository layer (every query filters by `tenant_id`), not at the route layer alone
- [ ] **Tower middleware order**: `TraceLayer` → `RequestId` → `CompressionLayer` → `CorsLayer` → auth middleware → rate-limit → handler. `TraceLayer` first so subsequent middleware errors are logged; auth after request-id so unauthenticated requests are still traced
- [ ] **Router composition per domain**: `Router::new().nest("/orders", orders_router())` over a single mega-router; auth middleware applied via `.route_layer(middleware::from_fn(auth))` at the sub-router level, not per-handler
- [ ] **`IntoResponse` for `AppError`**: a single `impl IntoResponse for AppError` maps domain errors → HTTP status codes (`AppError::NotFound` → 404, `AppError::Unauthorized` → 401). Per-handler `(StatusCode::INTERNAL_SERVER_ERROR, "...")` scattered across files leaks internal details and is inconsistent
- [ ] **`AppState` discipline**: a single `AppState` struct cloned cheaply (`#[derive(Clone)]`, fields wrapped in `Arc` where needed); `State<AppState>` extractor on every handler that needs dependencies. Do not pass individual `Arc<Service>` extractors per dependency - that fragments the wiring contract

**Multi-service PRs (when change spans 2+ services or this Rust app + a separate service):**

- API contract compatibility checked (OpenAPI diff via `utoipa` or similar, Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for any changed inter-service contract

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.
Use skill: `rust-overengineering-review` for: validator-crate rules duplicating sqlx / DB / the type system, unreachable `match` arms / `Result` where `E` is never constructed / dead `.unwrap_or_default()` on non-Option values, single-impl trait at the implementation / `Box<dyn Trait>` on hot single-callsite / `Arc<Mutex<T>>` on never-mutated data / hot-loop `.clone()` / speculative `cfg(feature)`. Each finding cites the redundancy source.

**Additional Rust AI smells not covered by the above:**

- [ ] **Redundant mapping layers**: `Row → InternalDto → ServiceDto → ResponseDto` when one mapping would suffice
- [ ] **Test verbosity**: setup helpers > 30 lines for a single assertion; `mockall` chains that could be a unit test on a smaller surface; full `assert_eq!(response, full_struct...)` when a few key field assertions would do
- [ ] **`tokio::spawn` misapplication**: `tokio::spawn(async move { ... })` to "make it concurrent" where the call is sequential by nature; conversely, sequential async I/O calls in a `for` loop that should fan out via `JoinSet`
- [ ] **Comment cruft**: doc comments restating function names; `// end of fn` markers; `///` on private helpers that just repeat the signature
- [ ] **`Box<dyn Error>` / `anyhow::Error` proliferation in domain types**: erases type information; if callers need to match, use `thiserror` enum
- [ ] **`#[allow(...)]` to silence clippy**: each suppression must have a `// reason: ...` comment; bare `#[allow(clippy::all)]` on a module is a finding

### Phase E - Rust Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**Rust-specific maintainability checks:**

- [ ] **Naming conventions**: module names lowercase / snake_case, no stutter (`user::UserService` → `user::Service`); types `UpperCamelCase`; functions / variables `snake_case`; constants `SCREAMING_SNAKE_CASE`. Public types have doc comments starting with the type name (`/// Represents an order...`)
- [ ] **Magic numbers / strings**: extracted to `const` items; `const DEFAULT_TIMEOUT: Duration = Duration::from_secs(5);` over raw `Duration::from_secs(5)` mid-expression
- [ ] **Hardcoded URLs / credentials**: in env vars / typed config struct, not inline in code
- [ ] **Function length**: functions > 30 lines reviewed for extraction; functions > 60 lines flagged unless they are a clearly orchestrating service function calling intention-revealing private helpers
- [ ] **Duplicated query logic**: same `WHERE` predicate in 3+ places extracted to a repository method or a typed query helper
- [ ] **Logging hygiene**: surface obvious offenders as Core findings at `[Suggestion]` - `println!` / `eprintln!` in production code path, log lines without correlation IDs, wrong log levels (`info!` for debug spam, `error!` for things that aren't actionable). The observability subagent owns depth (sampling, structured-field schemas, OTel correlation IDs, log redaction, `tracing` filter config); do not duplicate that audit here
- [ ] **`cargo fmt` / `cargo clippy` clean**: no manual formatting deviations; `clippy --all-targets -- -D warnings` clean (or noted exceptions documented per item, not blanket-suppressed)
- [ ] **Doc comments on exported APIs**: every `pub` type, function, and const has a `///` comment; fallible functions document `# Errors`; functions with non-obvious panics document `# Panics`; public modules have `//!` module-level docs

Use skill: `backend-coding-standards` for cross-language naming and structure conventions.
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-rust-review-observability` subagent owns the depth review).

### Step 5 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread (which continues running Phases A-E for Core). Subagents run concurrently with each other and with Core, not sequentially.

| Scope                | Subagents spawned                                                                                                          |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | 1 subagent running `task-rust-review-perf`                                                                                 |
| Core + Security      | 1 subagent running `task-rust-review-security`                                                                             |
| Core + Observability | 1 subagent running `task-rust-review-observability`                                                                        |
| Full                 | 3 subagents running `task-rust-review-perf`, `task-rust-review-security`, `task-rust-review-observability` in parallel     |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 3 (`base_ref`, `head_ref`) plus the already-read diff and commit log, so the subagent does not re-run `review-precondition-check` and does not re-issue `git diff`
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (Rust / Axum) and detected runtime + data-access (Tokio + sqlx / diesel / mixed) so the subagent skips its own `stack-detect` and data-access branching
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails or times out, continue with the remaining results. Note the missing scope in the synthesized output rather than blocking the whole review.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** The same issue may surface in multiple scopes (e.g., a sqlx query missing a join inside a request loop can be flagged by both Core/Phase B and Perf). Keep one entry, citing all scopes that raised it.
- **Severity wins.** When the same finding has different labels across scopes, use the highest severity (`Blocker` > `High` > `Suggestion` > `Question`). Subagent reviews (perf / security / observability) use their own scales (`Critical` / `High` / `Medium` / `Low`); when merging, map subagent severities into this skill's labels: `Critical` → `Blocker`, `High` → `High`, `Medium` → `Suggestion`, `Low` → `Suggestion`. Do not introduce `Critical` / `Medium` / `Low` into the merged Findings list.
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by severity, not by scope.** Produce one merged Findings list.
- **Note missing scopes.** If any subagent failed, add `Scope incomplete: <scope> review did not complete` under Summary.
- **Merge Next Steps.** Combine Core Next Steps with each subagent's Next Steps into one prioritized list under `## Next Steps`. Preserve `[Implement]` / `[Delegate]` tags; deduplicate items mapping to the same fix; re-sort by severity (Blocker/Critical > High > Medium/Suggestion > Low).

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.

## Feedback Labels

| Label        | Meaning                                     | Required |
| ------------ | ------------------------------------------- | -------- |
| [Blocker]    | Must fix before merge - correctness or risk | Yes      |
| [High]       | Should fix - significant impact or smell    | Strong   |
| [Suggestion] | Would improve - non-blocking                | No       |
| [Question]   | Need clarity from author                    | Clarify  |

No `[Nitpick]` or `[Praise]` labels.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Rust <version> / Axum <version>
**Runtime:** Tokio <version>
**Data Access:** sqlx <version> | diesel <version> | mixed
**Messaging:** Tokio queue | AMQP (lapin) | Kafka (rdkafka) | none
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the Rust idiom: `.unwrap()` in production, `panic!` in service code, `std::sync::Mutex` held across `.await`, fire-and-forget `tokio::spawn`, missing `JoinHandle`, sqlx string-interpolation SQL, unbounded channel, bare `Box<dyn Error>` return type, `unsafe` without SAFETY comment, missing extractor validation, IntoResponse leaking `sqlx::Error`, dispatch inside transaction, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete Rust change with code example]

### [High] file:line

- Issue:
- Impact:
- Fix:

### [Suggestion] file:line

- Improvement:

### [Question] file:line

- Question: [what is ambiguous in the change]
- Why it matters: [what the right next step depends on - author intent, business rule, deployment topology, etc.]

_Use [Question] when the change is genuinely ambiguous and the right action depends on author intent. Do NOT use it as a softer Blocker._

## Architecture Notes

_Summary commentary on systemic patterns. **Do not restate individual findings here.** If a pattern is severe enough to be a finding, keep it in Findings and reference it by file:line from these notes. Use this section for cross-cutting observations the per-file findings cannot carry on their own._

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

_Same rule as Architecture Notes - summary commentary, not duplicated findings._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Replace `std::sync::Mutex` with `tokio::sync::Mutex` on `OrderCache` to allow async access without deadlocking the executor"]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply Rust conventions (Rust API Guidelines, Rust Book, `cargo clippy`), not generic backend conventions
- Provide actionable feedback with Rust code examples
- Never comment on trivial formatting or style where no project standard exists - assume `cargo fmt` applies
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate Rust subagent rather than duplicating the check here

## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 (or accepted from parent dispatcher)
- [ ] Stack confirmed as Rust / Axum (or accepted from parent dispatcher); runtime, data-access, and messaging detected and recorded
- [ ] `review-precondition-check` ran (or its handle was received from a parent dispatcher); `base_ref` / `base_source` / `head_ref` / `current_branch` / `head_matches_current` captured. If user passed `--base`, `base_source: explicit-override` recorded
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all phases (and shared with subagents) - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran
- [ ] Scope auto-escalation evaluated (Step 4); promotion (or `core-only` suppression) recorded in Summary along with the firing signals
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`; promotion recorded in Summary
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Phase B - no `.unwrap()` / `.expect()` / `panic!` in production paths; error chain preserved with `.context(...)` / `#[from]`; errors mapped at layer boundaries
- [ ] Phase B - no `std::sync::Mutex` held across `.await`; every `tokio::spawn` has owner or uses `JoinSet`; long-lived tasks have `CancellationToken`
- [ ] Phase B - no blocking I/O on the runtime; CPU-heavy work in `spawn_blocking`; channels bounded; receivers select on cancellation
- [ ] Phase B - extractor validation present; authentication AND authorization both checked (ownership scoping, not just middleware presence)
- [ ] Phase B - sqlx parameterization (no `format!` into SQL); compile-time-checked queries preferred; N+1 via per-iteration query checked
- [ ] Phase B - domain-model-in-handler leak (no row struct returned from `Json(...)`) checked
- [ ] Phase B - transaction boundaries + post-commit dispatch checked
- [ ] Phase B - migration safety (concurrent index, lock_timeout, expand-contract, keyset backfill, sqlx-data.json refresh) checked when migrations changed
- [ ] Phase C Rust architecture checks applied: layering, trait-at-consumer, AppState constructor injection, settings discipline, `IntoResponse for AppError`, multi-tenant
- [ ] Phase D applied via `complexity-review` and `rust-overengineering-review` (validator vs sqlx/DB/type-system, unreachable match arms / Result with unconstructed E / dead `.unwrap_or_default()`, single-impl trait at implementation / `Box<dyn Trait>` on hot path / `Arc<Mutex<T>>` on never-mutated data / hot-loop `.clone()` / speculative `cfg(feature)`); Rust-specific AI smells covered: redundant mapping layers, test verbosity, `tokio::spawn` misapplication, comment cruft, `anyhow::Error` proliferation in domain types, `#[allow(...)]` without reason
- [ ] Phase E Rust maintainability checks applied: naming, magic numbers, function length, structured logging vs `println!`, doc comments on `pub` items
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Every finding has a label, location (file:line), and actionable Rust fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, Rust-specific subagents (`task-rust-review-perf`, `-security`, `-observability`) ran in parallel and received the pre-resolved diff/log handle plus stack detection
- [ ] Subagent findings merged into the single Output Format with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>`
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reviewing without reading the full diff and commit log first
- Applying generic backend conventions when a Rust idiom exists (say "define the trait in the consuming module", not "use dependency inversion")
- Nitpicking style where `cargo fmt` already applies
- Providing vague feedback without a concrete Rust fix ("this could be better")
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running perf / security / observability sub-workflows when user passed `core-only`
- Treating auto-escalation signals as advisory; the default is to promote and let the user opt out via `core-only`
- Duplicating perf / security / observability depth checks here when the dedicated Rust subagent owns them - flag and delegate
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging into one severity-ordered Findings list
- Recommending `panic!` / `.expect()` in service code for "this should never happen" cases - return a wrapped `AppError` instead; panics escape the error model and bypass `IntoResponse`
- Recommending raw `sqlx::query(&format!(...))` for "dynamic" queries - use `sqlx::query!` / `query_as!` (compile-time checked) for static SQL or a query builder for genuinely dynamic SQL
- Recommending `Arc<Mutex<T>>` as a default for shared state - many fits are `Arc<T>` (immutable), `Arc<RwLock<T>>` (read-heavy), or `dashmap::DashMap` (sharded)
- Recommending `Box<dyn Trait>` over generics for hot paths or single-callsite consumers - use static dispatch unless heterogeneous storage is required
- Recommending `unbounded_channel()` to "avoid backpressure" - that is a memory leak; use `mpsc::channel(N)` and decide the drop / await policy
