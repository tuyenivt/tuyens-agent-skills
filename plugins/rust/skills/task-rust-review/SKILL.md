---
name: task-rust-review
description: Rust / Axum / sqlx / Tokio code review - unwrap, Mutex-across-await, task leaks, SQL injection; spawns perf/security/obs subagents.
agent: rust-tech-lead
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles`. Cross-check every changed surface against `spec.md` / `plan.md`: each change must trace to an AC, NFR, or task; out-of-scope changes are **blockers**; missing in-scope coverage is a gap. Never edit spec artifacts.

# Rust Code Review

Staff-level Rust / Axum / sqlx / Tokio code review umbrella. Covers correctness, architecture, AI-quality, and maintainability. Coordinates perf / security / observability subagents in parallel for extra scopes. Runs standalone with full PR/branch resolution.

## When to Use

- Pre-merge review on a Rust / Axum PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:**

- Pre-implementation design (`task-rust-implement`)
- Production incident (`/task-oncall-start`)
- Single-error / panic debug (`task-rust-debug`)
- New-system architecture (`task-design-architecture`)
- Single-scope reviews - delegate to `task-rust-review-perf` / `-security` / `-observability`

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `quick` | Time-constrained risk snapshot | Phase A + top 3 Phase B findings |
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + historical pattern matching + cross-PR context |

**Auto-promote to `deep`:** after Phase A, if `Blast Radius` is Wide or Critical and the user did not pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E (Rust-flavored) |
| + Perf | Core + `task-rust-review-perf` subagent |
| + Security | Core + `task-rust-review-security` subagent |
| + Observability | Core + `task-rust-review-observability` subagent |
| Full | Core + all three subagents in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (Rust-tuned):**

- **+Security:** file uploads (`axum::extract::Multipart`), JWT / auth changes (`jsonwebtoken`, auth `from_fn`), DTO changes (request structs deriving `Deserialize` + `Validate`), raw SQL via `sqlx::query(&format!(...))`, secrets in env / config, background tasks consuming user input, `serde_json::from_value::<DomainModel>(req.body)`, `unsafe` blocks, domain models returned by `Json(...)` from handlers
- **+Perf:** new sqlx migration, new `query!` / `query_as!`, new `JOIN`, new pagination, new endpoints with payloads, loops calling DB / HTTP, new in-process cache (`moka` / `dashmap`) or Redis read paths, new `tokio::spawn` / `JoinSet` fan-out
- **+Observability:** new module / crate, new external client (`reqwest::Client`, `redis::Client`, `aws-sdk-*`), new background worker / Kafka producer or consumer, change to `tracing_subscriber` setup, new `metrics::counter!`, new `console_subscriber`, lifecycle changes (graceful shutdown, signals), missing `#[tracing::instrument]` on new handlers
- **2+ categories -> Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-rust-review` | Current branch vs base; fails fast on trunk |
| `/task-rust-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-rust-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs the fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base. Scope and depth flags compose: `/task-rust-review pr-50273 --base release/2026.05 +security deep`.

**No checkout required.** The workflow reads via ref-qualified diffs; never modifies the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack and Detect Async / Data-Access Surface

Use skill: `stack-detect`. Accept pre-detected stack from parent if applicable. If not Rust, stop and recommend `/task-code-review`.

Detect runtime: Tokio (assumed for Axum; flag if absent or if `async-std` / `smol` is in use). Detect data access: sqlx (primary; flag diesel as a secondary path). Detect messaging: in-process Tokio queue, `lapin` (AMQP), `rdkafka` (Kafka), or none. Record `Runtime`, `Data Access`, `Messaging` for branching in later phases.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Forward `--base` if passed. If it fails fast (dirty tree, trunk branch, missing PR ref, denied head-vs-current confirmation), surface verbatim and stop. Never run state-changing git commands from this workflow.

Once approved, read once and reuse:

- `git diff <base>...<head>`
- `git diff --name-status <base>...<head>`
- `git log --oneline <base>..<head>`

**Skip entirely** when invoked as a subagent and the parent passed the handle plus pre-read artifacts.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff for the signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` -> stay Core
- One signal category -> add matching extra scope
- 2+ categories -> promote to Full
- User passed an explicit scope -> respect it; still log signals so the Summary documents why

Surface the decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure propagation scope

Output risk level and blast radius before any findings.

**Auto-promote depth:** if Blast Radius is Wide / Critical and the user did not pass `quick`, set depth to `deep` and surface promotion in Summary **before** Phases B-E (so historical pattern matching, cross-PR context, and anemic-domain assessment are in scope).

**Low-risk short-circuit:** if Risk Level is Low, Blast Radius is Narrow, **and** the change does not touch architecture-relevant files (auth middleware, JWT, router composition, shared traits, `main.rs` / `lib.rs` wiring, sqlx migrations), skip Phases C-D and produce a streamlined output with Phase B only.

### Phase B - Rust Correctness and Safety

Apply atomic skills. Each owns the canonical patterns; this phase flags deviations and surfaces what they did not see:

- Use skill: `rust-error-handling` - `thiserror` / `anyhow`, `?`, `.context(...)`, `#[from]`, `IntoResponse for AppError`, no `.unwrap()` / `.expect()` / `panic!` in production paths, no log-and-return
- Use skill: `rust-async-patterns` - Tokio task lifecycle, `JoinHandle` / `JoinSet`, `CancellationToken`, `tokio::select!`, `spawn_blocking`, `tokio::time::timeout`, bounded channels
- Use skill: `rust-concurrency` - `Arc` / `Mutex` / `RwLock` choice, `Send + Sync`, no `std::sync::Mutex` across `.await`
- Use skill: `rust-db-access` - `query!` / `query_as!` (no `format!` interpolation), transaction boundaries, post-commit dispatch, N+1 via per-iteration query
- Use skill: `rust-web-patterns` - Axum extractors with `Validate` derives, response DTO mapping (no `FromRow` domain model in `Json(...)`), tower middleware order, body-size limits
- Use skill: `rust-messaging-patterns` if diff touches Kafka / AMQP / Tokio task queues
- Use skill: `rust-migration-safety` if diff touches `migrations/`. Also use skill: `ops-backward-compatibility` for client / in-flight impact

**Additional Rust-specific checks the atomics don't own:**

- **Test coverage finding (named, not buried).** PR adds logic without `#[cfg(test)]` / integration test coverage? At minimum `[Suggestion]`; escalate to `[High]` when the change is critical path: authentication (JWT, session middleware), authorization (ownership, role middleware), money / billing, multi-step transactions / state machines, background workers that mutate data, sqlx migrations changing column semantics. Surface as a dedicated finding.
- **Authorization vs authentication.** Auth middleware proves identity, not object access. Every per-owner endpoint must scope queries by principal in the handler or service body (`WHERE id = $1 AND user_id = $2`); middleware presence is not sufficient.
- **Domain-model-in-handler leak.** `Json(user)` where `user: User` is a sqlx `FromRow` struct leaks every column (`password_hash`, `mfa_secret`, audit fields). Define an explicit `*Response` DTO at the boundary; `#[serde(skip_serializing)]` on private fields is a fallback. Flag any `Json(<domain_struct>)` regardless of current fields - adding a sensitive column later silently exposes it.
- **`unsafe` discipline.** Every `unsafe` block carries a `// SAFETY:` comment justifying invariants. Bare `unsafe` is a Blocker.
- **`cargo clippy --all-targets -- -D warnings` clean.** Clippy catches concurrency / lifetime / API-shape mistakes the review will miss.

### Phase C - Rust Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**Rust-specific:**

- **Layering:** `handler` -> `service` -> `repository` -> `model`. Handlers extract / validate / delegate / respond; services hold business rules (no Axum extractors, no sqlx types); repositories return domain types, not bare sqlx rows; `main.rs` (or `app::build()`) wires constructors and `AppState`
- **Traits at the consumer:** `OrderRepository` trait lives in the consuming module (typically `service`), not next to its `PgOrderRepository` implementation. Trait + single-impl in the same module with no second implementer and no test mock is a single-impl-trait smell (Phase D)
- **Constructor injection via `AppState`:** dependencies stored on a typed `AppState` (passed via `axum::extract::State<AppState>`); no `lazy_static!` / `OnceCell` globals scattered across modules
- **Module boundaries:** feature-module layout (`src/orders/{handler,service,repository,model}.rs`) preferred over layer-module layout; cross-feature imports go through public service traits
- **`pub` discipline:** items not in the public API surface stay `pub(crate)` or unmarked
- **Settings discipline:** typed config struct (`figment` / `config` / `envy`) loaded once at startup and stored on `AppState`; no `std::env::var("X")` sprinkled across files
- **Multi-tenant isolation:** tenant scoping enforced at the repository layer (every query filters by `tenant_id`), not at routes alone
- **Tower middleware order:** `TraceLayer` -> `RequestId` -> `CompressionLayer` -> `CorsLayer` -> auth -> rate-limit -> handler. `TraceLayer` first so subsequent errors are traced; auth after request-id so unauthenticated requests are still traced
- **Router composition per domain:** `Router::new().nest("/orders", orders_router())` over a single mega-router; auth applied via `.route_layer(middleware::from_fn(auth))` at sub-router level, not per-handler
- **`IntoResponse` for `AppError`:** one `impl IntoResponse for AppError` maps domain errors to status codes. Per-handler `(StatusCode::INTERNAL_SERVER_ERROR, "...")` scattered across files leaks internals and is inconsistent
- **`AppState` discipline:** single struct, `#[derive(Clone)]`, fields wrapped in `Arc` where needed; do not pass individual `Arc<Service>` extractors per dependency
- **Anemic domain (deep depth only):** business rules accumulating in `*_service.rs` while domain structs stay as bare data containers (no `impl` blocks beyond getters) - flag for `task-rust-refactor`. Do not raise on a single PR's evidence alone

**Multi-service PRs:**

- API contract compatibility (OpenAPI diff via `utoipa`, Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility`

### Phase D - AI-Generated Code Quality

- Use skill: `complexity-review` for verbosity, over-engineering, simplification
- Use skill: `rust-overengineering-review` for: validator-crate rules duplicating sqlx / DB / the type system, unreachable `match` arms, `Result` where `E` is never constructed, dead `.unwrap_or_default()` on non-Option values, single-impl trait at the implementation, `Box<dyn Trait>` on hot single-callsite, `Arc<Mutex<T>>` on never-mutated data, hot-loop `.clone()`, speculative `cfg(feature)`

**Additional Rust AI smells the atomics don't own:**

- **Redundant mapping layers:** `Row -> InternalDto -> ServiceDto -> ResponseDto` when one mapping would suffice
- **Test verbosity:** setup helpers > 30 lines for one assertion; `mockall` chains that could be a unit test on a smaller surface; full `assert_eq!(response, full_struct...)` when a few field assertions would do
- **`tokio::spawn` misapplication:** `tokio::spawn(async move { ... })` to "make it concurrent" where the call is sequential by nature; conversely, sequential async I/O in a `for` loop that should fan out via `JoinSet`
- **Comment cruft:** doc comments restating function names; `// end of fn` markers; `///` on private helpers repeating the signature
- **`Box<dyn Error>` / `anyhow::Error` proliferation in domain types:** erases type information; if callers need to match, use a `thiserror` enum
- **`#[allow(...)]` without reason:** each suppression must have a `// reason: ...` comment; bare `#[allow(clippy::all)]` on a module is a finding

### Phase E - Maintainability and Clarity

Use skill: `backend-coding-standards` for cross-language naming. Use skill: `ops-observability` for cross-cutting logging/metrics presence (depth belongs to `task-rust-review-observability`).

**Rust-specific:**

- **Naming:** modules `snake_case`, no stutter (`user::UserService` -> `user::Service`); types `UpperCamelCase`; functions / variables `snake_case`; constants `SCREAMING_SNAKE_CASE`. Public types have doc comments starting with the type name
- **Magic numbers / strings:** extracted to `const` (`const DEFAULT_TIMEOUT: Duration = Duration::from_secs(5);`)
- **Hardcoded URLs / credentials:** in env / typed config, not inline
- **Function length:** > 30 lines reviewed for extraction; > 60 lines flagged unless clearly orchestrating intention-revealing private helpers
- **Duplicated query logic:** same `WHERE` predicate in 3+ places extracted to a repository method or typed query helper
- **Logging hygiene:** surface `println!` / `eprintln!` in production paths, log lines without correlation IDs, wrong levels (`info!` for debug spam, `error!` for non-actionable noise). Depth belongs to the observability subagent
- **`cargo fmt` / `cargo clippy` clean:** no manual formatting deviations; `clippy --all-targets -- -D warnings` clean
- **Doc comments on exported APIs:** every `pub` type, function, and const has a `///` comment; fallible functions document `# Errors`; non-obvious panics document `# Panics`; public modules have `//!` module-level docs

### Step 5 - Delegate Extra Scopes in Parallel

If scope is **Core only**, skip.

For each extra scope, spawn an independent subagent **in parallel** with the main thread:

| Scope | Subagents |
|-------|-----------|
| + Perf | `task-rust-review-perf` |
| + Security | `task-rust-review-security` |
| + Observability | `task-rust-review-observability` |
| Full | All three in parallel |

**Subagent prompt contract** - each must include:

- The resolved review target (`base_ref`, `head_ref`) plus the pre-read diff and commit log (no re-running git)
- The depth level
- Pre-confirmed stack (Rust / Axum) + detected runtime + data-access (Tokio + sqlx / diesel / mixed)
- Instruction to return findings in its own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate** cross-cutting findings (one entry citing all scopes that raised it)
- **Highest severity wins** (`Blocker` > `High` > `Suggestion` > `Question`). Map subagent scales: `Critical` -> `Blocker`, `High` -> `High`, `Medium` / `Low` -> `Suggestion`
- **Preserve `file:line` citations** from the originating subagent
- **Order by severity**, not by scope
- **Note missing scopes** in Summary as `Scope incomplete: <scope>`
- **Merge Next Steps** with `[Implement]` / `[Delegate]` tags preserved; re-sort by severity

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Write before ending; print the confirmation line.

## Feedback Labels

| Label | Meaning | Required |
|-------|---------|----------|
| [Blocker] | Must fix before merge - correctness / risk | Yes |
| [High] | Should fix - significant impact | Strong |
| [Suggestion] | Would improve - non-blocking | No |
| [Question] | Need clarity from author | Clarify |

No `[Nitpick]` or `[Praise]`.

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

- Issue: [name the Rust idiom: `.unwrap()` in production, `std::sync::Mutex` across `.await`, fire-and-forget `tokio::spawn`, sqlx `format!` interpolation, missing extractor validation, `IntoResponse` leaking `sqlx::Error`, domain struct in `Json(...)`, dispatch inside transaction, `unsafe` without SAFETY, etc.]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Rust change with code]

### [High] file:line
- Issue: ...
- Impact: ...
- Fix: ...

### [Suggestion] file:line
- Improvement: ...

### [Question] file:line
- Question: [what is ambiguous]
- Why it matters: [what the right next step depends on]

_Use [Question] for genuine ambiguity, not as a softer Blocker._

## Architecture Notes

_Cross-cutting commentary. Do not restate individual findings; reference them by file:line._

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

_Same rule as Architecture Notes._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact and what to address before merge.

## Next Steps

Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.** No Blocker heading if there are none.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply Rust conventions (Rust API Guidelines, Rust Book, `cargo clippy`)
- Provide actionable feedback with Rust code examples
- `cargo fmt` applies; do not nitpick style
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security / observability depth to subagents

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2: stack confirmed as Rust / Axum; runtime, data-access, and messaging recorded
- [ ] Step 3: `review-precondition-check` ran (or handle received); diff and commit log read once and reused; for `pr-ref` mode the fetch command was surfaced; when `head_matches_current` was false, explicit approval was obtained
- [ ] Step 4: scope auto-escalation evaluated; promotion (or `core-only` suppression) recorded with firing signals
- [ ] Phase A: risk level and blast radius stated before any finding; depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`; low-risk short-circuit applied when applicable
- [ ] Phase B: atomic skills applied (`rust-error-handling`, `rust-async-patterns`, `rust-concurrency`, `rust-db-access`, `rust-web-patterns`, plus `rust-messaging-patterns` / `rust-migration-safety` when relevant); test coverage, authorization, domain-model-leak, and `unsafe` discipline checked; clippy-clean expectation noted
- [ ] Phase C: layering, trait-at-consumer, AppState constructor injection, settings discipline, multi-tenant, tower middleware order, `IntoResponse for AppError` applied
- [ ] Phase D: `complexity-review` + `rust-overengineering-review` applied; Rust AI smells covered (redundant mapping, test verbosity, `tokio::spawn` misapplication, comment cruft, `anyhow::Error` in domain types, `#[allow(...)]` without reason)
- [ ] Phase E: naming, magic numbers, function length, structured logging vs `println!`, doc comments on `pub` items
- [ ] Missing tests raised as a named finding (not buried)
- [ ] Every Blocker states a system risk
- [ ] Every finding has label + `file:line` + actionable Rust fix
- [ ] If `--spec` passed: every finding traces to AC/NFR/task or is flagged as out-of-scope blocker
- [ ] Step 5: extra scopes ran in parallel with the pre-resolved diff/log handle plus stack detection
- [ ] Step 6: subagent findings merged into one severity-ordered Findings list; raw reports not appended; failed/missing scope noted as `Scope incomplete: <scope>`; Next Steps tagged `[Implement]` / `[Delegate]` and ordered by severity
- [ ] Step 7: review report written via `review-report-writer`; confirmation line printed

## Avoid

- `git fetch` / `git checkout` from this workflow - user runs these
- Reviewing without reading the full diff and commit log first
- Generic backend conventions when a Rust idiom exists ("define the trait in the consuming module", not "use dependency inversion")
- Nitpicking style where `cargo fmt` applies
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security / observability depth here when the dedicated Rust subagent owns them
- Sequential extra scopes that could parallelize
- Appending raw subagent reports instead of merging
- Recommending `panic!` / `.expect()` in service code - return a wrapped `AppError` so `IntoResponse` maps it
- Recommending raw `sqlx::query(&format!(...))` for "dynamic" queries - use `query!` / `query_as!` for static SQL or a query builder for genuinely dynamic SQL
- Recommending `Arc<Mutex<T>>` as a default - prefer `Arc<T>` (immutable), `Arc<RwLock<T>>` (read-heavy), `dashmap::DashMap` (sharded)
- Recommending `unbounded_channel()` to "avoid backpressure" - that is a memory leak; use `mpsc::channel(N)` with a defined drop / await policy
