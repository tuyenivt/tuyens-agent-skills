---
name: task-rust-review
description: Rust / Axum / sqlx / Tokio code review - unwrap, locks across await, task leaks, N+1, auth; spawns perf/security/observability/reliability subagents.
agent: rust-tech-lead
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

# Rust Code Review

Staff-level Rust/Axum/sqlx/Tokio review umbrella. Covers correctness, architecture, AI quality, maintainability. Coordinates perf / security / observability / reliability subagents in parallel.

## When to Use

- Pre-merge review on a Rust/Axum PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:** pre-implementation design (`task-rust-implement`), single-error debug, new-system architecture design, single-scope reviews (delegate to perf/security/observability/reliability).

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format; they are rule sets here, and only this skill's Output Format is emitted - an atomic's stop line for a framework it does not cover (`rust-web-patterns: not applicable (Actix)`) is not emitted either, and the checks naming its constructs are read by role. Where a check below and a loaded atomic disagree, the sentence names which wins.

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + the deep-only items below |

At `deep`, three things change and nothing else does: Phase C's anemic-domain check runs; `git log` over the touched files supplies branch history for `## Key Takeaways` (state "cross-PR context unavailable" when the surrounding PRs are not readable); and deep-only sections returned by subagents are preserved per Step 6.

**Auto-promote to `deep`:** After Phase A, if Blast Radius is Wide/Critical, set depth to `deep`. Surface it in the Summary's `Depth` line using the Output Format's wording - that template is the single source for every Summary string.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E |
| + Perf | Core + `task-rust-review-perf` subagent |
| + Sec | Core + `task-rust-review-security` subagent |
| + Obs | Core + `task-rust-review-observability` subagent |
| + Rel | Core + `task-rust-review-reliability` subagent |
| Full | Core + all four in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals:**

- **+Sec:** `axum::extract::Multipart`, JWT / auth changes (`jsonwebtoken`, an auth `from_fn` layer), `Json<T>` request-DTO changes (`Deserialize` + `Validate` derives), raw SQL via `AssertSqlSafe(format!(...))` or `QueryBuilder::push` of a request value, secrets in config, `unsafe` blocks, Kafka / AMQP consumers or job handlers fed user input, a request body deserialized into a domain model (`Json<Order>` where `Order` derives `FromRow`, or `serde_json::from_value::<Order>(body)`), client-controlled price / amount / currency / discount fields on payment-adjacent endpoints (`/orders`, `/refunds`, `/checkout`)
- **+Perf:** new migration, new query statement (`query!` / `query_as!` with `fetch_one` / `fetch_all` / `fetch_optional` - a new DB roundtrip, not a pure shaping change like a `LIMIT` on an existing query), a **new filter or sort predicate** on an existing query (it needs an index that may not exist), new pagination, new endpoints with payloads, loops awaiting DB or HTTP calls, new cache reads (`moka`, Redis), new `tokio::spawn` / `JoinSet` / `join_all`, a new or changed job claim query (`FOR UPDATE SKIP LOCKED`)
- **+Obs:** new module / crate, new external client (`reqwest::Client`, `aws-sdk-*`), new job kind or Kafka / AMQP producer / consumer, `tracing_subscriber` change, `metrics` / `prometheus` registration, `console_subscriber`, lifecycle changes (`with_graceful_shutdown`)
- **+Rel:** a `reqwest::Client` built without `.timeout(...)` or `reqwest::get` on a downstream call, retry / backoff / breaker config (`backoff`, `tokio-retry`, `tower::retry`), new `tokio::spawn` with no owning `JoinHandle` / `JoinSet` or no `CancellationToken` / shutdown arm, a downstream `.await` not wrapped in `tokio::time::timeout`, `mpsc::unbounded_channel` or unbounded per-request spawn, a Kafka / AMQP publish inside an open sqlx transaction (dual write), a new job kind or a changed job claim / settle (lease, attempt cap, `dead` state)
- **2+ categories -> Full**

**Signals name the common case, not the only one - match the construct's role, not its spelling.** This applies to every named construct in this skill, whether or not the named tool is present:

- **Data-access calls.** sqlx macro names read across to the project's layer (runtime `sqlx::query` / `query_as`, `QueryBuilder`, diesel, SeaORM, `tokio-postgres`), in the scope signals, Phase B's raw-entity check, and the `rust-db-access` bullet alike.
- **Request extractors.** `Json<T>` stands for any request-DTO extractor - `Query<T>`, `Path<T>`, `Form<T>`, a project `ValidatedJson<T>`; `Multipart` is a file-upload extractor and its own +Sec signal. A DTO that reaches the request surface fires the signal regardless of which extractor populates it.
- **Route lists.** `/orders`, `/refunds`, `/checkout`, `/payments`, `/subscriptions` are examples of a class: any endpoint that moves money or provisions an entitlement is in-class whatever its path.
- **Tooling.** When a named tool is genuinely absent (a different migration runner, no sqlx), apply the rule the convention protects and suppress the tool-specific form of the finding.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-rust-review` | Current branch vs base; fails fast on trunk |
| `/task-rust-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-rust-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base.

Pass `--req <path>` to name a requirement source (ticket export, PRD, spec) for Phase 0; without it, Phase 0 uses whatever requirement is already in context.

Append a scope (`core-only`, `+perf`, `+sec`, `+obs`, `+rel`, `full`) or `deep` after the target; none of these tokens is read as a branch name.

**No checkout required.** Read via ref-qualified diffs; never modify the working tree. No `git fetch` either - the user fetches; a stale local ref is reviewed as it is.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. A subagent loads it too, unless the spawning prompt inlined its whole Rules section and its unverifiable-change disclosure, as that skill specifies.

### Step 2 - Stack and Data Access

Use skill: `stack-detect`. Accept pre-detected stack from parent. If not Rust, stop and recommend `/task-code-review`.

`stack-detect` emits `ORM` and carries other `## Tech Stack` declarations into `Additional`, but no messaging field. Versions come from `Cargo.toml` and `Cargo.lock` - the Rust version from `rust-toolchain.toml`'s `channel`, else `rust-version` (`[package]`, or `[workspace.package]` when inherited); the edition from `edition`; the HTTP framework / Tokio / sqlx from their resolved `Cargo.lock` entries, since `Cargo.toml` holds requirement ranges (`axum = "0.8"`; the requirement as written when no lock file is committed) - and override any version a `## Tech Stack` line declared (this step's one departure from `stack-detect`'s instruction-file precedence); in a Cargo workspace the member crate under review decides, its `Cargo.toml` read in place of the detected primary stack, with `workspace = true` dependencies resolved through the root `[workspace.dependencies]`. `Data Access` is the data-access crate the crate under review depends on directly - `sqlx`, `diesel` (`diesel-async` included), `SeaORM` (`sea-orm`) or `tokio-postgres` - with its `Cargo.lock` version; one present only transitively (the `sqlx` beneath SeaORM, the `tokio-postgres` beneath `diesel-async`) does not count, and two direct ones are `mixed`, both named with versions. `Messaging` lists every mechanism present, in this order, joined with ` + `: `Postgres job queue` when a worker claims rows from a jobs table with `FOR UPDATE SKIP LOCKED` (no crate marks it - read the claim query, or the migration creating the table; an outbox relay's claim is not one); `Kafka` when `rdkafka` or another Kafka client is a direct dependency; `AMQP` for `lapin`; `Tokio queue` when worker tasks drain a `tokio::sync::mpsc` channel of background jobs; `none` when there is none. Confirm against the wiring in `src/main.rs` (or the `app::build()` it calls). The `Stack` slot is `stack-detect`'s rendering with those versions added (`Rust 1.94 (edition 2024) / Axum 0.8.9`, `Rust 1.94 (edition 2024) (no framework detected)`, `Rust unpinned` when no toolchain is declared), and the writer's `stack` is `rust-<framework>` lowercased (`rust-axum`, `rust-actix-web`; `rust` when there is none).

### Step 3 - Resolve Diff

Use skill: `review-precondition-check` with `report_type: review`. Forward `--base` if passed. If it fails fast, surface verbatim and stop. On success, print each handle `notes` entry in chat, one line each, before the report body (nothing when it has none; the handle itself stays internal). The handle's `head_short_name` is the writer's `branch` and the `<head_ref_short>` in every message below.

The handle may include a `prior_checkpoint` block (a prior report exists at its `report_path`). Decision logic is Step 3.5; for now, just hold onto it.

Read once and reuse:

- `git diff <base>...<head>`
- `git diff -M --name-status <base>...<head>`
- `git log <base>..<head>` - full messages; Phase 0 reads the bodies
- `git ls-tree -r --name-only <head_ref>` - the file list at head, passed to reconcile on round 2+

**Skip entirely** when invoked as subagent and parent passed handle + pre-read artifacts.

Also capture the current SHAs for the report's checkpoint frontmatter: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>` (full SHAs).

### Step 3.5 - Decide Round (re-review auto-detect)

**Every round analyzes the full `<base_ref>...<head_ref>` range read in Step 3.** Risk, blast radius, scope signals, depth promotion, and requirement fit are scored on the whole change on every round, so a small follow-up commit cannot under-score a large PR and a defect missed in round 1 stays reachable in round 2. Rounds differ only in that round 2+ reconciles against the prior report.

Skip if the handle has no `prior_checkpoint` -> `round = 1`, no reconciliation. Continue to Step 4.

If `prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `round = 1`. Note in Summary: `Prior report lacks checkpoint metadata - treated as round 1.` Continue to Step 4.

Otherwise (valid prior checkpoint present), **compare checkpoints**. Rows are not mutually exclusive - evaluate top-down and take the first match.

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha`, `prior_checkpoint.base_ref == base_ref`, and the invocation adds no scope or depth beyond the prior checkpoint | **No-op.** Print `No new commits on <head_ref_short> since prior review at <sha_short>. Prior report unchanged.` (`<sha_short>` is the first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
| `prior_checkpoint.head_sha == current_head_sha`, but the invocation expands scope or depth beyond it | `round = prior.round + 1`. Note in Summary: `Same head as round <prior.round>; re-review for expanded <scope\|depth>.` |
| `git merge-base --is-ancestor <prior_checkpoint.head_sha> <current_head_sha>` fails (prior SHA unreachable) | `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten.`      |
| `prior_checkpoint.base_ref != base_ref`                                | `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round>.`           |
| `prior_checkpoint.base_sha != current_base_sha`                        | `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round>.`       |
| None of the above                                                       | `round = prior.round + 1`.                                                                          |

**Scope expansion** is compared at the end of Step 4, once scope is resolved: when the resolved scope exceeds the checkpoint's, whether from a user flag or from firing signals, note in Summary: `Scope expanded round <N>: +<list>.` The reconciliation table only covers findings whose scope was active in the prior round.

### Step 4 - Scope Auto-Escalation

Scan file list / diff for signals listed under **Scope**. Log each as `signal: <category> -> <file:line>` in your working notes. The Summary's `signals:` list names the **construct** that fired each category, not the category (which the Scope value already states) and not the sites: `auto-escalated from Core; signals: +Perf (new WHERE predicate, unindexed column)`. Then:

- Zero signals or `core-only` -> Core; `core-only` with firing signals adds `Note in Summary: suppressed: <category> (<construct>)` per category
- One category -> add matching scope
- 2+ categories -> Full
- Explicit scope -> it wins over the rows above; a firing category outside it gets the same `suppressed:` note

**Scope precedence on round 2+:** user flag > firing signals. Signals are scored on the full range every round, so a scope that escalated in round 1 escalates again on its own - nothing is inherited from the prior checkpoint. When the resolved scope still falls below the checkpoint's (round 1 was user-flagged), note in Summary: `Scope narrowed vs round <prior.round>: <list> - re-run with <flags> to re-cover.`

### Phase 0 - Change Intent

Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and log, the `--req <path>` file when passed, and the handle's `report_path` (as its `prior_report_path`) when round > 1.

`--req <path>` resolves against the directory the command was invoked from, not the git root.

Its `## Change Brief` block goes into the report verbatim, its `Requirement Source` and `Requirement Fit` lines into Summary, its `### Requirement Findings` / `### No Requirement Findings` marker where the atomic places it (under the traceability block when that renders, directly under the Change Brief otherwise - exactly one of the two is always emitted, on a sourceless run too), and its findings join the assembled set verified in Step 6.5. With no requirement source the Brief still renders, and the traceability block and its two Summary lines are omitted. `Requirement Fit` counts criteria only; an unrequested-scope finding does not move its numbers. A `Partial` or `Unmet` criterion with no finding of its own is still indexed under `### Requirement Findings` by its traceability row; one with a finding is indexed by that finding, once. Runs before Phase A - acceptance criteria decide what counts as a defect downstream - and the low-risk short-circuit never skips it.

**Requirement fit does not cap a defect's label.** A criterion scored `Partial` maps to `[Recommend]` as a *requirement* finding; the same code reaching Phase B as an authorization hole is `[Must]`. Publish the stronger label - fit describes delivery against the ask, severity describes consequence, and the two are independent.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk
- Use skill: `review-blast-radius` for failure propagation

Output risk level + blast radius before any findings; the Summary's `Risk Level`, `Blast Radius`, and `Blast Radius rationale` lines are their only slots - the per-dimension detail stays in working notes.

**Score the contract before scoring risk.** Phase B's contract-change signal list enumerates what breaks a consumer - a removed / renamed / retyped response field, a changed status code, a newly required request field. Any of those on a contract whose consumers ship on their own schedule - outside the repo, or another internal service - makes Blast Radius `Critical` (`review-blast-radius`'s contract-break rule); a contract consumed only inside this repo, which deploys atomically, scores Code Scope by its consumers per `review-blast-radius` (Narrow, Moderate, or Wide for a shared crate or cross-service contract). An added route is additive, not a break, and sets no floor. A one-line `#[serde(rename = "...")]` edit in a one-module diff scores on this rule, not on diff footprint.

**Low-risk short-circuit:** if Risk is Low, Blast Radius is Narrow, **and** the change does not touch architecture-relevant files (auth middleware, JWT, router composition, shared traits, `main.rs` / `app::build()` wiring, migrations), skip Phases C-E. Step 5 still runs for any scope Step 4 resolved beyond Core. The streamlined report contains Summary, the Phase 0 outputs (Change Brief, traceability, requirement findings), `## Prior Round Reconciliation` on round 2+, High-Impact Findings (Phase B plus any lens findings), Next Steps, `## Verified Clean` (Phase B's passing checks plus any lens's), and - when Step 5 ran - the Notes sections and the lens-owned sections Step 6 maps lens output into; Step 7 still writes the checkpointed report.

### Step 4.5 - Re-evaluate Depth After Phase A

If Blast Radius is Wide / Critical, set depth to `deep` and surface promotion in Summary **before** Phases B-E.

**Depth precedence on round 2+:** user flag > this round's auto-promotion. Blast radius is scored on the full range every round, so a promotion that fired in round 1 fires again - nothing is inherited. When the resolved depth still falls below the checkpoint's (round 1 was user-flagged `deep`), note in Summary: `Depth narrowed vs round <prior.round> - re-run with deep to re-cover.`

### Phase B - Rust Correctness and Safety

Apply atomic skills; each owns canonical patterns:

- Use skill: `rust-error-handling` - `thiserror` domain enums, `anyhow` at the binary edge, `?` with `.context(...)`, one `IntoResponse for AppError`, no `.unwrap()` / `.expect()` / `panic!` on request paths
- Use skill: `rust-async-patterns` - task ownership (`JoinSet` / held `JoinHandle`), `CancellationToken` / `select!` shutdown arms, `spawn_blocking` for CPU or sync I/O, `tokio::time::timeout` on downstream awaits, bounded channels
- Use skill: `rust-concurrency` - `Arc` / `Mutex` / `RwLock` choice, no lock guard held across `.await`, `Send + Sync` bounds, `rayon` kept off the async runtime
- Use skill: `rust-db-access` - `query!` / `query_as!` with `$n` binds (no `format!` into SQL), transaction boundaries over `&mut *tx`, post-commit dispatch, per-iteration N+1 (`= ANY($1)`), pool and statement timeouts
- Use skill: `rust-web-patterns` - extractor order (body extractor last), `Validate` derives on request DTOs, response DTO (no `FromRow` struct in `Json(...)`), `/{id}` route syntax, body-size limits
- Use skill: `rust-messaging-patterns` if diff touches a Postgres job queue, Kafka, AMQP or an in-process Tokio job queue
- Use skill: `rust-migration-safety` if diff touches `migrations/`. Use skill: `ops-backward-compatibility` for client / in-flight impact
- **API contract change** - when the diff carries a contract-change signal (a removed / renamed / retyped response-struct field, including a `#[serde(rename)]` / `rename_all` change, a changed status code, a new **required** request field - non-`Option` with no `#[serde(default)]` - or a tightened `#[validate]` constraint, a new public route on a `/v1/`-versioned or externally consumed API, a handler returning a `FromRow` entity via `Json(...)`, or an edit to a committed OpenAPI / `utoipa` spec), use skill: `backend-api-guidelines` and use skill: `ops-backward-compatibility`. Judge breakage from the consumer's view ("no external callers" needs a search; when consumption is unknown, treat a `/v1/`-versioned or spec-published surface as externally consumed); responses go through a response DTO, never a raw `FromRow` model; errors follow the project's documented envelope (per `backend-api-guidelines`, stated in the instruction file or the client contract; here an `ApiResponse<T>` / `AppError` shape already used across existing endpoints also counts, overriding that definition), otherwise RFC 9457; collections paginated; the committed OpenAPI / `utoipa` spec matches the code. Each finding names who breaks and how (for a leaked model: what it exposes and who couples to it). Labels map from `backend-api-guidelines`' own tiers: High -> `[Must]`, Medium -> `[Recommend]`, Low -> below the reporting bar, write nothing; the one explicit downgrade is a raw `FromRow` model on an internal-only surface, which stays with the **Response DTO hygiene** check below at `[Recommend]`. A committed spec the diff left disagreeing with the code is Medium. Granularity: one finding per `file:line`, except where `backend-api-guidelines` folds one rule broken identically across N endpoints into a single finding listing all N sites - that fold wins, since the ask is one edit

**Pre-existing defects are in scope when the diff reaches them.** A defect on a line the diff did not add is reportable when the diff makes it newly reachable, newly consequential, or newly load-bearing (a guard removed in front of it, a first caller added, a second condition stacked on it, a shared resource whose holds now span new work) - in a touched file or an untouched one alike. Anchor the finding on the defect's own `file:line` and name the diff's call site as the trigger; `review-finding-verify` assigns the attribution. All three of those cases take **`Pre-existing (newly reachable)`** - "reachable" there means the diff changed how the defect is reached or how much it bears, not only that a new caller exists - so the label is retained rather than de-escalated. Plain `Pre-existing` is for a defect in a touched file that the diff neither reaches nor loads differently. A defect in an untouched file the diff never reaches belongs in `Architecture Notes` or `Maintainability Notes`, not in findings (a lens's own published pre-existing findings stay findings, per Step 6).

**Additional checks (not owned by atomics):**

- **Test coverage finding (named, not buried).** PR adds logic without a `#[cfg(test)]` module or a `tests/` integration test (`#[tokio::test]`, `#[sqlx::test]`) -> `[Recommend]`; escalate to `[Must]` when critical path: auth, ownership / role checks, money / billing, multi-table writes, state machines, Kafka / AMQP consumers and job handlers that mutate data, migrations changing column semantics
- **Test files are reviewed for coverage only.** For files that are themselves tests, the only finding to raise is a coverage gap: production logic in the diff that no test exercises. Anchor that finding to the untested production `file:line` and state the case to cover, not the test file. Do not review test code for style, structure, duplication, naming, or performance - a passing test with awkward setup is not a finding.
- **Authorization + IDOR.** Every per-owner endpoint scopes queries by principal: `WHERE id = $1 AND user_id = $2` bound to `<principal-id>` - whatever the project uses (`claims.sub`, an `AuthUser` extractor's `user.id`, `Extension<CurrentUser>`). JWT proves authn, not object access
- **Response DTO hygiene.** Compare the response DTO's `Serialize` fields against the model. Flag `password_hash` / `mfa_secret` / `recovery_codes` / `api_key` / `webhook_secret` / `internal_notes` / `audit_log` / `is_admin` / `role` / `deleted_at` / `last_login_ip` on the wire. A raw `Json(user)` of a `FromRow` model on an internal-only surface is `[Recommend]` regardless of current fields (a sensitive column added later silently exposes it) - this wins over `architecture-guardrail`'s and `backend-coding-standards`' `[Must]` for the same site; an externally consumed surface takes the API contract check's label
- **HTTP `Idempotency-Key` on retry-prone POSTs.** `/payments`, `/orders`, `/refunds`, `/subscriptions`, `/webhooks` accept the header and dedupe via a `request_idempotency` table. Distinct from consumer-side dedupe on a message ID, which dedupes delivery, not the request
- **Client-controlled money fields.** Price / amount / discount on payment-adjacent endpoints (`/orders`, `/refunds`, `/checkout`) come from the server (or a server-validated catalog), not the request DTO. Trusting `req.unit_price` is `[Must]`
- **Postgres FK indexes.** `REFERENCES other(id)` does not create an index on the FK column - add one explicitly in the migration. Missing FK indexes cause sequential scans on join, lock contention on cascade delete, and degrade as the parent grows
- **`unsafe` discipline.** Every `unsafe` block carries a `// SAFETY:` comment stating the invariant it relies on; a bare `unsafe` is `[Must]`
- **Rust boundary quirks.** `tracing` macros (not `println!` / `eprintln!` / `dbg!`); `Utc::now()` (not `Local::now()`) for timestamps stored in a zone-less `TIMESTAMP` (`NaiveDateTime`) column - not a finding against `TIMESTAMPTZ` (`DateTime<Utc>`), which normalizes on write, so check the column type in `migrations/` before raising it
- **Multi-replica race safety.** Counters / balances / state transitions use DB locking (`SELECT ... FOR UPDATE` inside the transaction, or an optimistic `version` column), not an in-process `Mutex` / `DashMap` (one replica only)
- **HTTP client sharing.** One `reqwest::Client` built at startup and cloned through `AppState` (it is an `Arc` internally); `reqwest::Client::new()` per request, or `reqwest::get`, which builds a fresh client on every call, defeats connection reuse and drops the shared timeout
- **`cargo sqlx prepare --check`** clean in CI when `.sqlx/` offline metadata is committed - a changed `query!` without regenerated metadata breaks offline builds

### Phase C - Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**Rust-specific:**

- **Layering:** `handler` -> `service` -> `repository` -> `model`. Handlers extract / validate / delegate / respond; services hold rules (no Axum extractors or `StatusCode`; sqlx only to own a transaction boundary, per `rust-db-access`); repositories return domain types; `main.rs` (or `app::build()`) wires `AppState`
- **Traits at consumer.** The consuming module (typically `service`) declares the repository trait; the repository module provides the concrete `PgOrderRepository`
- **`AppState` injection, no globals.** One `#[derive(Clone)]` `AppState` extracted via `State<AppState>`; a `static` `LazyLock` / `OnceLock` / `lazy_static!` holding a `PgPool` or client is a smell
- **Visibility:** `pub(crate)` for crate-internal items; a workspace crate for shared libraries
- **Settings discipline:** typed config struct (`config` / `figment` / `envy`) loaded once; no `std::env::var("X")` scattered
- **Feature-module layout** (`src/orders/{handler,service,repository}.rs`) preferred over layer-module
- **Multi-tenant isolation** at the repository layer, not routes alone
- **Tower layer order** per `rust-web-patterns` (`.layer` is bottom-up: the last added runs first): panic catching inside tracing so a panicked request still gets its span; `CorsLayer` via `.layer` on the top-level router (`route_layer` runs only on a matched route, so a preflight `OPTIONS` to a POST-only route gets no CORS headers); auth via `route_layer` on the protected sub-router, never wrapping `/health`
- **Error-handling boundary:** handlers return `Result<_, AppError>` and one `impl IntoResponse for AppError` maps them (per `rust-error-handling`); per-handler `(StatusCode::INTERNAL_SERVER_ERROR, e.to_string())` scattered is `[Recommend]`
- **Anemic domain (deep depth only):** rules in services while models stay pure data - flag for refactor/extraction. Don't raise on a single PR alone

**Multi-service PRs:** API contract compatibility (OpenAPI diff, Pact); deployment order documented; use skill: `ops-backward-compatibility`.

### Phase D - AI-Generated Code Quality

- Use skill: `complexity-review` for verbosity, over-engineering
- Use skill: `rust-overengineering-review` for validator rules duplicating sqlx / DB / type system, unreachable `match` arms, `Result` whose error is never constructed, single-impl traits at the impl, `Box<dyn Trait>` on a hot single-callsite path, `Arc<Mutex<T>>` on never-mutated data, hot-loop `.clone()`, speculative `cfg(feature)`

`complexity-review` emits `[Severity: High | Medium | Low]`: map High -> `[Must]`, Medium -> `[Recommend]`, Low -> below the reporting bar, write nothing. `rust-overengineering-review` already labels each block `[Must]` or `[Recommend]`; take its labels as they are.

**Additional AI smells:**

- Redundant mapping layers (`Row -> InternalDto -> ServiceDto -> ResponseDto`)
- Test verbosity (setup > 30 lines for one assertion; full deep-equal when a few fields would do)
- DTO noise (identical DTOs reimplemented per endpoint; gratuitous `#[serde(skip_serializing_if = "Option::is_none")]`)
- Comment cruft (doc comments restating function names, `///` on private helpers)
- `anyhow::Error` / `Box<dyn Error>` in domain signatures (a caller that must match needs a `thiserror` enum; erasing the type to silence a compile error is a finding)

### Phase E - Maintainability

Use skill: `backend-coding-standards` for cross-language naming and function length (decompose over 50 lines; flat exhaustive `match` dispatch exempt) - judged once, here, overriding `complexity-review`'s method-length row. Use skill: `ops-observability` for cross-cutting logging/metrics presence (depth in `task-rust-review-observability`); its `[Severity:]` gaps map like `complexity-review`'s.

**Rust-specific:**

- Naming: `snake_case` modules and functions, `UpperCamelCase` types, `SCREAMING_SNAKE_CASE` constants; no stutter (`user::UserService` -> `user::Service`); no `utils` / `helpers` / `common` modules
- Magic numbers / strings extracted to `const`
- Hardcoded URLs / credentials in env / typed config
- Duplicated query logic: same `WHERE` in 3+ places -> repository method. Not a finding for a security predicate (tenant, owner, soft-delete): repeating it at every call site is what makes an omission visible, and hiding it behind a helper is how one query silently loses it
- Logging hygiene: surface `println!` / `eprintln!` / `dbg!` in prod paths; spans without correlation IDs; wrong levels
- `cargo fmt --check` / `cargo clippy --all-targets -- -D warnings` clean
- Doc comments on `pub` items, with `# Errors` / `# Panics` sections where they apply; `utoipa` annotations when the project uses them

### Step 5 - Delegate Extra Scopes in Parallel

Skip if scope is **Core only**. For each selected scope, spawn one independent subagent **in parallel** with the main thread. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; an observability review is not a `rust-tech-lead` spawn:

| Scope | Skill                            | Subagent (`subagent_type`)    |
| ----- | -------------------------------- | ----------------------------- |
| +Perf | `task-rust-review-perf`          | `rust-performance-engineer`   |
| +Sec  | `task-rust-review-security`      | `rust-security-engineer`      |
| +Obs  | `task-rust-review-observability` | `rust-observability-engineer` |
| +Rel  | `task-rust-review-reliability`   | `rust-reliability-engineer`   |

`Full` = 4 subagents.

**Subagent prompt contract** - pass every field; each delegate's subagent carve-out depends on receiving them:

- The `review-precondition-check` handle itself (each delegate skips its own precondition step only when it receives one)
- Resolved review target (`base_ref`, `head_ref`), `base_sha` / `head_sha`, + pre-read diff and commit log (no re-running git)
- Depth level. It propagates as resolved here, except `+Sec`, which always runs full by its own rule and ignores the value
- Pre-confirmed stack (Rust and edition, the framework, versions), data-access mix, **and messaging** (perf, observability and reliability record it in a Summary slot; security uses it only to scope broker-input checks)
- Phase 0's acceptance criteria when a requirement source resolved, so a lens can judge intent rather than only mechanics
- Explicitly: return your entire Output Format, write no report file, and skip your own verify and reconcile passes - the parent verifies and reconciles the merged set once
- `behavioral-principles`: the subagent loads it as its own Step 1, unless this prompt inlines the whole Rules section and the disclosure block

**Failure isolation:** if a subagent fails, times out, or cannot be spawned at all, run that lens's skill inline under the same prompt contract, sequentially after Phases B-E (its findings join the set Step 6.5 verifies like any other); only when that is impossible too, note the scope on the Summary's Scope line as `Scope incomplete: <scope>`.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into single Output Format. Do not append raw reports.

**Project each lens's sections onto this report's shape first.** Match on the severity word, not the exact heading string - perf, obs and reliability head their tiers `### High Impact` / `### Medium Impact` / `### Low Impact`, while security heads them `### Critical` / `### High` / `### Medium` / `### Low`. Keep the label on each lens heading (a lens may escalate a Medium to `[Must]` by its own rule); derive one from the severity word only for an entry carrying none - Critical / High -> `[Must]`, Medium / Low -> `[Recommend]`. Re-file every entry under `## High-Impact Findings` as `### [Label] file:line`, carrying any `_(pre-existing)_` the lens attached. Nothing downstream parses the lens headings - `review-prior-findings-reconcile` reads only `## High-Impact Findings` - so a finding left under its lens heading is invisible to the next round.

Map the lens's fields onto `Issue` / `Impact` / `System Risk` / `Fix`: the lens's own `Issue` and `Fix` carry over; `Failure Mode`, `Attack scenario` and the perf `Impact` become `Impact`; `Blast Radius` and `Severity rationale` become `System Risk`, with a reliability `Assumption` line appended to it; the obs `Impact` carries over as `Impact`. When a `[Must]` lens block has nothing for `System Risk`, write why the finding is system-level rather than dropping the slot; a projected `[Recommend]` entry carries `System Risk` only when the lens block mapped a field into it.

**Granularity is the parent's, not the lens's.** A lens may fold several defects into one entry - security's combined-finding rule composes missing auth, mass assignment and replayability on one handler into a single Critical. This report files **one entry per fix**, so un-fold it: publish each defect at its own `file:line` with its own remedy, and carry the composition in the strongest one's `System Risk` ("alone this is X; with the two below it is unauthenticated, unbounded, repeatable money movement"). The composition is the reason the severity is what it is, and it survives as prose rather than as a merged entry the next round cannot reconcile.

- Deduplicate cross-cutting findings (one entry citing all scopes; a lens's `Also owned by` note names the duplicate) - but never merge two findings that will verify differently in Step 6.5 (see its dedup rule)
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend`
- Preserve `file:line` citations; order by intent, not scope
- Merge Next Steps with `[Implement]` / `[Delegate]` tags; re-sort by intent
- Preserve every non-findings section a lens returns, not only the deep-only ones, and **match on heading text at any level** - a lens may emit `## Verified Clean` or `### Verified Clean` and both mean the same thing. Reliability's `Failure-Mode and Blast-Radius Map` and perf's `Capacity & Load Plan` become their own sections after Next Steps. `Sequencing` folds into this report's Next Steps ordering; `Verified Clean` joins this report's `## Verified Clean`; `Out of Lens` items join `## Next Steps` as `[Delegate]` `[Recommend]` rows carrying the owning lens (a lens's own beyond-the-three overflow is `[Implement]` `[Recommend]`; an item with no lens owner goes to `Architecture Notes`); a lens's `Recommendations` (including its `### SLI / SLO` block) merge into `Architecture Notes` or `Maintainability Notes` by subject; security's `OWASP Triage` and obs's `Surface Map` become their own sections after Next Steps; every lens Summary field this Summary lacks (security: `JWT Library`, `Password Hash`, `Authorization`, `Overall Posture`; obs: `Logging`, `Metrics`, `Tracing`, `tokio-console`, `Graceful shutdown`, broker instrumentation, `Error Tracker`, `Overall`; reliability: `Resilience Libraries`, `Overall`; perf: `Overall`) and each lens's Summary assessment paragraph go under `Architecture Notes`, one line per lens. The merge drops nothing a lens was required to produce

**Cross-phase same root cause.** When one defect spans multiple phases (e.g., a layering violation that also degrades testability and DTO discipline), file the finding once under the phase where the root cause sits and reference its `file:line` from `Architecture Notes` or `Maintainability Notes`. Do not double-count by listing the same defect as separate findings; two distinct defects at one `file:line` stay two headings.

### Step 6.5 - Verify Findings (second pass)

Use skill: `review-finding-verify` with the assembled findings (including any merged back from subagents), the diff already read, and `base_ref` / `head_ref`.

Runs before reconciliation so prior-round matching sees the corrected set. Publish only rows whose Verdict is not `Dropped`, carrying the skill's `Label` column and its `Annotation` column onto the heading as **separate** `_(...)_` groups: verify's combined `_(pre-existing; newly reachable via X)_` is written `_(pre-existing)_ _(newly reachable via X)_`, because `review-prior-findings-reconcile` matches `_(pre-existing)_` exactly and a merged group marks an untouched prior finding `Addressed` next round. `_(unverified: <reason>)_` and `_(mechanism: <actual>)_` carry over as they are. Carry its tally into Summary verbatim: `Findings verified: <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff)`, parenthetical omitted when `K` is 0. The verify table is working material; only the tally and the surviving rows' labels and annotations reach the report. A finding on a file the name-status does not list gets `_(pre-existing)_`, written first, unless its annotations already have a group opening `pre-existing` or `unverified`.

**Dedup must not cross an attribution boundary.** Step 6 merges duplicate findings; this pass assigns each one verdict and one attribution. A merged entry whose halves verify differently - one `Confirmed` on new code, one `Pre-existing` that de-escalates - cannot carry both, and this skill only rules on what it is given. Un-merge those back into separate findings before verifying rather than forcing one verdict onto both.

### Step 6.6 - Reconcile Prior Findings (round 2+ only)

Skip on round 1. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the loaded body of the file at the handle's `report_path` (frontmatter excluded)
- `diff`: the full-range diff from Step 3
- `name_status`: the full-range `git diff -M --name-status <base_ref>...<head_ref>` from Step 3
- `head_sha`: `current_head_sha` - the ref every file read inside the skill uses
- `base_ref`: the handle's `base_ref` - reconcile derives the merge base from it
- `head_files`: the `git ls-tree -r --name-only <head_ref>` list from Step 3 (optional to the skill, which otherwise falls back to `git cat-file -e` per path; passing it saves one call per prior finding)

The reconcile skill returns a Markdown table, any note lines, and a tally line. Insert all of it under `## Prior Round Reconciliation` in the report (see Output Format).

**`Still open` and `Needs re-check` rows re-enter `## High-Impact Findings`** as `### [Label] <current file:line> _(carried from round <N>)_` with this round's label and the site where the smell now lives - a round-1 `[Recommend]` that this round's rules make `[Must]`, or a smell that moved from `:38` to `:44`, is published at the current assessment, and a carried `_(pre-existing)_` finding whose line the diff has since modified drops the annotation, and one on a file the name-status does not list gains it, written first, unless a group opens `pre-existing` or `unverified`. A carried row whose smell this round's findings already publish at the same site is not re-added; that existing entry takes `_(carried from round <N>)_` on its heading and `(open since round <N>)` on its Next Steps row. Every carried finding also enters `## Next Steps` suffixed `(open since round <N>)`, ordered by severity alongside this round's findings; no standalone "Carry-Over Open Items" section. The table itself preserves the prior label and `file:line` verbatim (the reconcile skill's own rule): the table is the audit trail, the finding is the ask.

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `branch = head_short_name` (from the handle - never `head_ref`, which the next round's precondition check would treat as legacy), `base_ref`, `base_sha = current_base_sha`, `head_ref`, `head_sha = current_head_sha`
- `mode: full` (the writer's only accepted value), `round` (from Step 3.5), `prior_head_sha = prior_checkpoint.head_sha` (omit on round 1)
- `scope` (resolved in Step 4, mapped to the writer's enum: `Core` -> `core-only`, `+Sec` -> `+sec`, `+Perf` -> `+perf`, `+Obs` -> `+obs`, `+Rel` -> `+rel`, `Full` -> `full` - the writer rejects unmapped display values), `depth` (resolved/auto-promoted), `stack` per Step 2

Write before ending; print confirmation.

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |

No `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]` or `[Recommend]`, don't write it down.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Fill rules.** `Scope` carries the resolved value, then `auto-escalated from Core; signals: <list>` when escalated, then `Scope incomplete: <scope>` for any lens Step 5 could not run. `Round Notes` collects every `Note in Summary` string Steps 3.5, 4 and 4.5 produced, the legacy note and signals `core-only` or an explicit scope suppressed (`suppressed: +Sec (<construct>)`) included; omit the line when there are none. `Findings verified` takes Step 6.5's tally verbatim. `Requirement Source` and `Requirement Fit` are emitted together or omitted together. `Blast Radius` carries `review-blast-radius`'s overall line verbatim (its contract-break parenthetical and two-state `<level> (unmitigated) -> <level> (with <mitigation>)` form included); the short-circuit and Step 4.5 gate on the mitigated value when the atomic's `Mitigation` tag is `in-place:`, otherwise on the unmitigated value. `Blast Radius rationale` names the one factor that set the level - the contract break, or the dimension (Code / Data / User) that reached it - in one sentence. `Assessment` is `Discuss` when at least one `[Must]` is published and every one is `_(unverified: ...)_`, or when an open design question blocks the verdict, `Request Changes` when any other `[Must]` is published, `Approve` otherwise. `file:line` cites the head file's line; two findings may share one `file:line`, one heading each; a finding in a non-Rust file (CI, manifest, migration) takes its label from its consequence like any other.

**Every finding heading is `### [Label] file:line _(annotations)_`**, `[Must]` first, the label and annotations from Step 6.5 as separate groups (`_(carried from round <N>)_` on carried findings). This is the only heading the next round's reconciliation parses; merged subagent findings are re-filed here per Step 6, never left under a lens heading. When the set exceeds ~12, group by root cause - one entry listing its sites rather than one entry per site - for `[Recommend]` always, and for `[Must]` when several sites share one root cause and one edit. Volume is not thoroughness - a 30-item list of blockers reads as none. Field lines keep their `- Issue:` / `- Impact:` / `- System Risk:` / `- Fix:` prefixes - the reconciler reads the `Issue:` line - separated by blank lines.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss
- **Risk Level:** Low | Medium | High | Critical
- **Blast Radius:** Narrow | Moderate | Wide | Critical     {the atomic's overall line, parenthetical and two-state form included}
- **Stack:** Rust <version> (edition <year>) / <framework> <version> | Rust <version> (edition <year>) (no framework detected)
- **Data Access:** sqlx <version> | diesel <version> | SeaORM <version> | tokio-postgres <version> | mixed - <crate> <version> + <crate> <version>
- **Messaging:** Postgres job queue | Kafka | AMQP | Tokio queue | <several, joined by " + "> | none
- **Scope:** Core | +Sec | +Perf | +Obs | +Rel | Full     {+ escalation and incomplete notes per the fill rules}
- **Depth:** standard | deep | deep (auto-promoted from standard; Blast Radius: <level>)
- **Round:** <N>                                {round 2 onward}
- **Round Notes:** <notes, semicolon-separated>     {omit when none}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff)
- **Requirement Source:** <`review-change-intent`'s line value as emitted: each source with its authority, two joined by ` + `>     {omit when Phase 0 resolved no source}
- **Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable     {omit when Phase 0 resolved no source}
- **Blast Radius rationale:** <the one factor that set the level - contract break or the Code / Data / User dimension that reached it>

## Change Brief

**Requested:** <what the change was asked to do, citing the source; with no source resolved, the `(inferred from ...)` form `review-change-intent` emits>

**Delivered:** <the mechanism implemented and where>

**Author decisions:** <each choice the request did not imply, with its consequence, excluding choices already raised as findings; `None observed` when nothing remains>

**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

### Requirement Findings     {when the traceability block does not render; otherwise it sits under that block}

One bullet per requirement finding, each citing the `file:line` and the `## High-Impact Findings` entry that publishes it in full - `[Must] src/orders/handler.rs:44 - AC1 partial: no ownership check (see `## High-Impact Findings`, same `file:line`)`; a Partial or Unmet criterion with no finding cites its traceability row instead. The bullet is an index, not a second copy.

### No Requirement Findings     {instead, when there are none - exactly one of the two markers is always emitted}

## Requirement Traceability     {omit when Phase 0 resolved no source}

| Criterion | Status | Implementation | Proof |
| --------- | ------ | -------------- | ----- |
| <id or quoted outcome> | Met \| Partial \| Unmet \| Deferred \| Untraceable | <file:line, or `-`> | <file:line or verification note, or `-`> |

## Prior Round Reconciliation     {round 2+ only; omit otherwise}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

<note line>     {one paragraph per note line reconcile emitted; omit when none}

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

### [Must] file:line _(annotations)_     {annotation groups only when Step 6.5 or Step 6.6 assigned any}

- Issue: [name the Rust idiom]

- Impact: [user-visible or operational]

- System Risk: [why this is system-level]

- Fix: [concrete Rust change with code]

### [Recommend] file:line _(annotations)_     {annotation groups only when Step 6.5 or Step 6.6 assigned any}

- Issue: [name the Rust idiom]

- Impact: [user-visible or operational]

- System Risk: [why this is system-level]     {only when a lens block mapped a field into it}

- Fix: [concrete Rust change with code]

## Architecture Notes

_Cross-cutting commentary. Reference findings by file:line._
- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

- Over-engineering detected:
- Simplification opportunities:

## Verified Clean

Checks that ran and passed, with their evidence - the authz scoping that is correct, the response DTO that leaks nothing, the money field that is server-derived, the FK that is indexed. Includes any `Verified Clean` a lens returned. A reader cannot otherwise tell "checked and fine" from "never checked", and on a clean PR that distinction is the review.

## Key Takeaways

2-4 bullets on systemic impact.

## Next Steps

Each item tagged `[Implement]` or `[Delegate]` (`[scope: <owner or lens>]` on delegated items). Order: Must > Recommend. Carried findings keep their `(open since round <N>)` suffix.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] old_file.rs:88 - N+1 in list_all (open since round 1)
3. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]

_Omit if no actionable findings._

## OWASP Triage     {only when the security lens ran and returned it}

_Verbatim from the lens._

## Surface Map     {only when the observability lens ran and returned it}

_Verbatim from the lens._

## Failure-Mode and Blast-Radius Map     {only when the reliability lens ran and returned it}

_Verbatim from the lens._

## Capacity & Load Plan     {only when the perf lens ran and returned it}

_Verbatim from the lens._
```

**Omit empty sections.** No Must heading if there are none.

## Self-Check

Mark a line N/A with its reason when the invocation mode makes it inapplicable - round-2 lines on round 1, Step 5/6 lines on Core, the short-circuit lines when it did not fire.

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: stack confirmed; versions from `Cargo.toml` / `Cargo.lock`; data-access mix and messaging recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review` (or handle received); diff / name-status / log / ls-tree read once and reused; `current_head_sha` and `current_base_sha` captured; approval obtained when `head_matches_current` was false
- [ ] Step 3.5: round decided (1 / prior + 1 / no-op) from the handle's `prior_checkpoint`; the full `<base_ref>...<head_ref>` range analyzed regardless of round; no-op path exits without writing
- [ ] Step 4: scope auto-escalation evaluated; promotion (or `core-only`) recorded; scope expansion / narrowing noted on round 2+
- [ ] Phase 0: `review-change-intent` ran on the cumulative diff; Change Brief carried into the report; exactly one requirement-findings marker emitted where the atomic places it; requirement lines in Summary or omitted together; its findings verified with the rest
- [ ] Phase A: risk + blast radius stated before any finding, contract scored first; short-circuit applied only when all three conditions held
- [ ] Step 4.5: depth auto-promoted to `deep` when Blast Radius is Wide/Critical; narrowing noted on round 2+
- [ ] Phase B: atomic skills applied; test coverage, authz, response DTO, Idempotency-Key, money fields, FK indexes, `unsafe` discipline, race safety, client sharing checked; API contract checks ran when the diff carried a contract-change signal; pre-existing defects anchored on the defect with the diff's trigger named
- [ ] Phase C: layering, trait-at-consumer, `AppState` injection, settings, multi-tenant, tower layer order; anemic domain at `deep`
- [ ] Phase D: `complexity-review` mapped and `rust-overengineering-review` labels taken as-is
- [ ] Phase E: naming, magic numbers, function length per `backend-coding-standards`, structured logging
- [ ] Step 5: extra scopes ran in parallel with the full prompt contract (handle, refs, SHAs, diff, log, depth, stack, data access, messaging, acceptance criteria, no-write / no-verify instruction); a lens that could not spawn ran inline or was noted `Scope incomplete`
- [ ] Step 5: subagent loaded behavioral-principles, or the whole Rules section and the disclosure block inlined in the spawning prompt
- [ ] Step 6: lens findings projected onto `### [Label] file:line` under `## High-Impact Findings`, un-folded one entry per fix; every non-findings lens section preserved by heading text; no raw reports appended
- [ ] Step 6.5: `review-finding-verify` ran on all assembled findings; Dropped rows excluded; labels and split annotations on the headings; tally in Summary
- [ ] Step 6.6 (round 2+): `review-prior-findings-reconcile` ran with `head_sha`, `base_ref` and `head_files`; table inserted preserving prior labels and lines; `Still open` / `Needs re-check` rows re-entered High-Impact Findings with `_(carried from round <N>)_` and Next Steps with `(open since round <N>)`
- [ ] Step 7: report written via `review-report-writer` with `branch = head_short_name` and the full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope mapped to the writer's enum, depth, stack); confirmation printed
- [ ] Every finding has label + `file:line` + a concrete fix in whatever language the fix lives in (Rust, SQL, YAML, TOML); every Must cites system risk; Next Steps tagged and ordered by intent

## Avoid

- State-changing git from this workflow (checkout / fetch / merge / pull / rebase)
- Scoping round 2+ analysis to `<prior_head_sha>...<head_sha>` - risk, scope, depth, and requirement fit score the full `<base_ref>...<head_ref>` range on every round
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`)
- Generic backend conventions when a Rust idiom exists ("declare the trait in the consuming module", not "use DI"); nitpicking style where `rustfmt` applies; blocking on personal preference
- Duplicating perf / security / observability / reliability depth here, or running extra scopes when `core-only` was passed
- Recommending `.unwrap()` / `.expect()` / `panic!` on request paths, `AssertSqlSafe(format!(...))` around request data, or a `std::sync::Mutex` guard held across `.await`
