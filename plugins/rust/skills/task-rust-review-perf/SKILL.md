---
name: task-rust-review-perf
description: Rust / Axum / sqlx / Tokio perf review: N+1, pool sizing, task leaks, Mutex-across-await, blocking I/O, allocation hotspots, Arc<Mutex> contention.
agent: rust-performance-engineer
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, performance, async, pprof, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Rust Performance Review

## Purpose

Rust-aware performance review that names sqlx N+1 patterns, compile-time-checked vs runtime queries, `PgPoolOptions` sizing (`max_connections`, `min_connections`, `acquire_timeout`, `max_lifetime`), Tokio task lifecycle (leak vs unbounded fan-out via `JoinSet` / `tokio::spawn`), `CancellationToken` propagation, `std::sync::Mutex` held across `.await`, blocking I/O on the runtime (synchronous file I/O, `bcrypt::hash` without `spawn_blocking`), allocation hotspots (`String` vs `&str`, `Cow<'_, str>`, `.clone()` churn, `Vec` pre-allocation, `bytes::Bytes`), `Arc<Mutex>` contention vs `Arc<RwLock>` / `dashmap::DashMap`, and sqlx-cli migration safety idioms directly instead of routing through the generic backend adapter. Produces findings with measured or estimated impact (latency, throughput, query count, allocations, task count) and concrete fixes using idiomatic Rust.

This workflow is the stack-specific delegate of `task-code-review-perf` for Rust. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a Rust/Axum PR or branch for performance regressions
- Investigating a slow endpoint, background task, or Kafka consumer
- Pre-merge perf pass on changes touching sqlx queries, Tokio task fan-out, channel patterns, or hot allocation paths
- Quarterly N+1 / pool-sizing / leak-detection sweep against pprof / OTel data

**Not for:**

- General Rust code review (use `task-code-review` or `task-rust-review`)
- Security review (use `task-code-review-security` or `task-rust-review-security`)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-rust-implement`)

## Severity Rubric

Use these definitions to keep `High` / `Medium` / `Low` Impact labels consistent across runs. Severity is about steady-state production impact and recovery effort, not how scary the code looks.

| Severity     | Definition                                                                                                                                                                                                                                                                              |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **High**     | Production outage shape under steady load: unbounded memory growth (leaked tasks, unbounded `Vec` reads, unbounded channels), pool starvation under traffic, executor stalls (sync I/O / `bcrypt` on the runtime), N+1 multiplying baseline RPS by O(N), `std::sync::Mutex` across `.await` deadlock surface. Or deploy-time outage on hot tables (NOT NULL ADD with non-constant default on a 10M+-row table, non-`CONCURRENTLY` index on hot table).                                                          |
| **Medium**   | Degraded p95 / p99 latency, wasted bandwidth, missing pool sizing on a net-new service, `SELECT *` over wide rows, missing pagination on endpoints that *can* grow but currently don't, channel-buffer sizes without justification, single-flight cache stampede paths. Recoverable with a follow-up PR; not paging on-call. |
| **Low**      | CPU / allocation churn (`.clone()` overuse, `format!` in hot paths, missing `Vec::with_capacity`), missing `CompressionLayer`, missing `tracing::instrument` for perf observability. Defense in depth and quick wins.                                                                |

When uncertain between tiers, ask "would this page on-call within 24 hours of a 2x traffic increase?" - yes ⇒ High; "would this drag the next quarter's perf budget?" - yes ⇒ Medium.

## Depth Levels

| Depth      | When to Use                                                  | What Runs                                          |
| ---------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `quick`    | Single endpoint or repository ("is this query ok?")          | Steps 4 + 5 only; sqlx hotspots + migrations       |
| `standard` | Default - full Rust perf review                              | All steps                                          |
| `deep`     | Profiling-driven review with `flamegraph` / OTel / `criterion` data | All steps + capacity guidance and load plan |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                        | Meaning                                                                                               |
| --------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-rust-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-rust-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-rust-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Async / Data-Access Surface

Use skill: `stack-detect` to confirm Rust / Axum. If invoked as a delegate of `task-code-review-perf` or as a subagent of `task-rust-review` (parent already detected Rust), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Rust, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Rust 1.94+ on Tokio.

Detect data access:

- `sqlx` in `Cargo.toml` → **sqlx**
- `diesel` in `Cargo.toml` → **diesel**
- Both → **mixed**

Detect messaging: in-process Tokio task queue, `lapin` (AMQP), `rdkafka` (Kafka), or none.

The data-access decision drives which checklists in Step 4 apply. Record `Runtime: Tokio`, `Data Access: sqlx | diesel | mixed`, `Messaging: Tokio queue | AMQP | Kafka | none` for the Summary block.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Performance Surface

Before applying the checklists, open the files that govern query and concurrency behavior so impact estimates ground in real code:

**sqlx surface:**

- Every changed query (`sqlx::query!`, `query_as!`, runtime `query(...).bind(...)`, `fetch_one`, `fetch_optional`, `fetch_all`, `execute`)
- Every changed repository for transaction usage (`pool.begin().await?`, `tx.commit().await?`)
- Pool setup (`PgPoolOptions::new()...connect(...)`) - `max_connections`, `min_connections`, `acquire_timeout`, `idle_timeout`, `max_lifetime`
- Migration files under `migrations/` (sqlx-cli format)

**Tokio surface:**

- Every changed handler / service for `async fn` signatures, `.await` placement, blocking calls
- New `tokio::spawn(...)` / `JoinSet::spawn(...)` / `task::spawn_blocking(...)`; channel patterns (`mpsc::channel`, `broadcast::channel`, `oneshot`); `tokio::select!` arms
- `CancellationToken` usage; long-lived workers / consumers
- `Arc`, `Mutex`, `RwLock` (note: `std::sync::Mutex` vs `tokio::sync::Mutex`)

**Both:**

- HTTP / external clients (`reqwest::Client` constructed at app startup vs per-request)
- In-process cache (`moka`, `dashmap`); Redis (`redis-rs`, `bb8-redis`, `deadpool-redis`)
- Background workers; Kafka producers / consumers

For each finding produced later, cite a real `file:line`. If the diff is small but ripples through code that is not in the diff (a new endpoint calling an existing repository whose query does an N+1), read the unchanged file too - the regression lives there even though the line count attributes it to the new caller.

### Step 4 - sqlx (or diesel) Hotspots

> If `Data Access: sqlx` was recorded in Step 1, **skip the diesel subsection entirely** below. Likewise skip the sqlx subsection on diesel-only projects. The bifurcation exists for mixed codebases - on monoglot projects it should be one read, not two.

**If sqlx** - use skill: `rust-db-access` for canonical patterns. Review-scoped scan of every changed query, repository, service, and handler:

- [ ] N+1 (per-iteration `sqlx::query!` over parent set) and multi-level N+1; resolve via `WHERE id = ANY($1::int8[])` or JOIN
- [ ] `sqlx::query!` / `query_as!` for static SQL (compile-time-checked); `.sqlx/` offline cache committed and refreshed via `cargo sqlx prepare`
- [ ] Column projection over `SELECT *`; missing indexes on `WHERE` / `ORDER BY` / `GROUP BY` columns
- [ ] `fetch_all` without `LIMIT` / keyset pagination on growable lists
- [ ] Bulk insert via `UNNEST($1, $2)` or multi-VALUES (not per-row in a loop); `ON CONFLICT ... DO UPDATE` for idempotent upserts
- [ ] Transactions wrap multi-statement writes; no HTTP / queue I/O inside `pool.begin()...tx.commit()` (capture, dispatch after commit)
- [ ] Pool config (`PgPoolOptions::max_connections / acquire_timeout / max_lifetime`) sized against `max_connections × replicas ≤ DB cap`; pool lives on `AppState`, never per-request

**If diesel** - use skill: `rust-db-access`:

- [ ] N+1 resolved via `filter(id.eq_any(ids))`; `diesel-async` for async paths (bare `diesel` blocks the executor unless wrapped in `spawn_blocking`); async pool via `bb8-diesel` / `deadpool-diesel` (not sync `r2d2`)

### Step 5 - Indexes and Migrations

Use skill: `rust-migration-safety` for safe-migration checks on any change in `migrations/` (sqlx-cli format).

- [ ] Every column referenced in `WHERE` / `ORDER BY` / `GROUP BY` is backed by an index
- [ ] Composite indexes match the leftmost-prefix pattern of the queries
- [ ] Foreign keys have indexes (PostgreSQL does not auto-index FKs)
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL); sqlx-cli files contain raw SQL so this is explicit
- [ ] **`SET lock_timeout = '2s'`** before DDL on large tables to fail fast instead of blocking
- [ ] Unique constraints enforced at the database level
- [ ] Partial indexes used for boolean/enum filters that select a small subset (`CREATE INDEX ... WHERE status = 'pending'`)
- [ ] No DDL on hot tables in a single migration (expand-then-contract: add column nullable, backfill, switch reads, drop old column in a later release)
- [ ] **Backfill via keyset pagination** (`WHERE id > $1 ORDER BY id LIMIT N`), never `WHERE col IS NULL LIMIT N` (re-scans the same rows on every iteration)
- [ ] Data migrations isolated from DDL migrations - separate sqlx-cli files
- [ ] Enum changes safe: PostgreSQL `ALTER TYPE ... ADD VALUE` cannot run in a transaction; document workaround
- [ ] **Every `up.sql` has a matching `down.sql`**; `down` tested or documented as one-way
- [ ] **`cargo sqlx prepare` re-run** after schema change so `sqlx-data.json` matches the new schema (otherwise offline-mode CI breaks)

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot in `WHERE` / `ORDER BY` / `GROUP BY` even if no query in the diff currently references it - someone is adding the index for a reason. Validate the index is actually needed (column shape, expected selectivity), then assess migration safety. Conversely, when the diff _adds a column_ the application also queries on, flag the missing index proactively rather than waiting for a separate migration PR.

**Migration impact template.** Before approving any migration step on a hot table, state the impact: _"DDL on a 50M-row table without `CONCURRENTLY` blocks all writes for the duration of the index build (typically 5-30 min on Postgres at this scale). Acquires `ACCESS EXCLUSIVE`; every other transaction queues."_ If the row count is unknown, ask, or note "row count not in diff - confirm before deploy."

### Step 6 - Tokio Task Lifecycle and Async Concurrency

Use skill: `rust-async-patterns` for task lifecycle / `JoinSet` / `CancellationToken` / `select!` / `spawn_blocking`. Use skill: `rust-concurrency` for `Arc` / `Mutex` / `RwLock` / channel patterns. Review-scoped scan of changes touching `tokio::spawn`, `JoinSet`, `select!`, channels, locks, worker pools:

- [ ] Every `tokio::spawn` has an owner (`JoinHandle` retained or `JoinSet`); long-lived loops pair with `tokio::select! { _ = token.cancelled() => ... }`; fan-out bounded via `JoinSet` + `Semaphore` (not unbounded `for x in xs { tokio::spawn(...) }`)
- [ ] No `std::sync::Mutex` held across `.await` (blocks executor); use `tokio::sync::Mutex`, or drop guard before await; read-heavy state uses `tokio::sync::RwLock` or `dashmap::DashMap`
- [ ] Bounded `mpsc::channel(N)` over `unbounded_channel()`; non-obvious `N` justified by a comment
- [ ] No blocking / CPU-heavy work on the runtime (`std::fs`, `std::thread::sleep`, `bcrypt::hash`, large `serde_json::to_string`); wrap in `tokio::task::spawn_blocking` or use async equivalents (`tokio::fs`, `tokio::time::sleep`)
- [ ] `tokio::time::timeout` per outbound HTTP / DB / queue call; `reqwest::Client` built once on `AppState` (cloning is `Arc`-cheap), never per-request
- [ ] No external I/O inside `pool.begin()...tx.commit()` (drains pool, holds row locks for upstream tail latency); capture inputs, dispatch after commit

> **Impact framing.** Phrase task leaks as "compounding leak proportional to sustained traffic" (captured state + futures, not just memory). Phrase synchronous critical-path calls as "p99 = max(self, upstream p99)" - recommend cache / circuit breaker / fire-and-forget when non-blocking-business, strict `tokio::time::timeout` + fallback when blocking-business. When RPS / row count isn't in the diff or `CLAUDE.md`, state the assumption alongside the impact estimate. **Hot path** means: per-request on the request future, per-row in a `fetch_all` result, or inside a worker/consumer loop - allocation / CPU checks (Step 7) only fire on hot paths.

### Step 7 - Allocation Hotspots and CPU Cost

_Skipped at `quick` depth unless the diff touches hot loops or large allocations._

- [ ] **`String` vs `&str`**: function parameters that don't store the value should take `&str`; allocating a `String` to call `fn foo(s: String)` then immediately consuming it is a smell. `Cow<'_, str>` for "sometimes owned" cases
- [ ] **`Vec::with_capacity(n)` over `Vec::new()`**: when capacity is known, pre-allocate to avoid the geometric reallocation pattern
- [ ] **`bytes::Bytes` over `Vec<u8>` for shared payload**: `Bytes` is reference-counted and slices share the underlying buffer; `Vec<u8>` requires copying for each consumer
- [ ] **`.clone()` everywhere**: `.clone()` on every variable to silence the borrow checker is a smell - often a `&` reference avoids the clone. `Arc::clone(&x)` is cheap (atomic increment) and is fine; `String::clone` / `Vec::clone` allocates
- [ ] **`HashMap::with_capacity(n)`**: when capacity is known, avoid rehashing growth
- [ ] **Iterator adapter chains over manual indexed loops**: `.iter().filter(...).map(...).collect()` is often as fast as a hand-written loop and clearer; profile if hot
- [ ] **`json` serialization hot paths**: `serde_json::to_writer(w, &v)` writes directly to a writer (often the response body); `serde_json::to_string(&v)` allocates the full string first. Use `simd-json` or `sonic-rs` only when profiling shows `serde_json` dominates CPU - the swap is non-trivial
- [ ] **Avoid `format!` in hot paths**: `format!` allocates a `String`; concatenation via `String::with_capacity` + `push_str` is faster for known-size outputs. `write!` to a `Write` impl avoids the intermediate `String`
- [ ] **`Box<T>` only when heap allocation is required**: `Box::new(x)` for a small `Copy` type is wasteful; `Box<dyn Trait>` is justified for heterogeneous storage
- [ ] **Avoid spawning thousands of tasks for short-lived work**: scheduler overhead compounds; use a worker pool with a fixed number of workers consuming from a channel

### Step 8 - Caching and Response Performance

_Skipped at `quick` depth unless the diff touches caching primitives._

- [ ] **In-process cache**: `moka` (lock-free, async-friendly LRU/LFU) or `dashmap` (sharded concurrent map) - configure max capacity and TTL. `lazy_static!`-wrapped `HashMap` is not a cache - it has no eviction
- [ ] **Redis cache (`redis-rs` / `bb8-redis` / `deadpool-redis`)**: shared across replicas; `SETEX` for TTL; `MGET` / `pipe()` for batched ops
- [ ] **Cache stampede protection**: hot keys with expensive regeneration use single-flight (`moka`'s `try_get_with` blocks duplicate populators); for distributed cache, Redis `SET NX EX` lock
- [ ] **Cache invalidation explicit** - no caches that never expire and never invalidate; document staleness budget
- [ ] **HTTP caching** (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GET endpoints via Axum response headers
- [ ] **Response compression**: `tower_http::compression::CompressionLayer` for JSON responses > 2KB
- [ ] **Per-request memoization**: store on `Request::extensions_mut()` for values used by multiple middlewares in the same request

### Step 9 - Background Tasks / Kafka / AMQP

_Skipped at `quick` depth unless the diff touches background tasks or message brokers._

Use skill: `rust-messaging-patterns` for canonical patterns. Review-scoped scan:

- [ ] **All brokers**: tasks idempotent (payload carries IDs / simple types, not owned domain models); dispatch AFTER `tx.commit().await?` (never inside an open transaction)
- [ ] **In-process Tokio queue**: `mpsc::channel(N)` bounded with documented saturation policy; worker count fixed (not "spawn-per-job")
- [ ] **Kafka (`rdkafka`)**: consumer groups for partition parallelism; manual `commit_message(...)` after success (never auto-commit); `queued.max.messages.kbytes` / `fetch.max.bytes` tuned for memory budget
- [ ] **AMQP (`lapin`)**: manual `delivery.ack(...)` after success; `basic_qos` prefetch limit set

### Step 10 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

This step is intentionally narrow - depth on observability belongs to `task-rust-review-observability`. From a perf perspective, confirm only:

- [ ] Slow paths reachable from this PR have **some** instrumentation (`tracing::instrument` span via `tracing` or a `metrics::histogram!` via the `metrics` crate); if not, raise as a Low/Recommendation finding and delegate to `task-rust-review-observability` for a proper instrumentation pass rather than dictating the design here
- [ ] sqlx logging not at `debug` / `trace` in prod (configured via `tracing` filter); `RUST_LOG=sqlx=warn,info` is the typical floor
- [ ] `tokio-console` / `console_subscriber` enabled for non-prod or behind a feature flag so live task profiling is possible

Anything beyond presence/absence (sampling rates, span attributes, correlation IDs, multi-process metric aggregation) → `task-rust-review-observability` owns it. Note the gap, do not duplicate the audit here.


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Rust / Axum; runtime, data-access, and messaging recorded before any specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent)
- [ ] Performance surface read directly (queries / repositories, handlers, pool config, migrations, task spawn sites, channels)
- [ ] `rust-db-access` consulted for the project's data-access mix; N+1, multi-level N+1, projection, upsert idempotency checked
- [ ] `rust-migration-safety` consulted for any migration change; `lock_timeout`, concurrent index, keyset-pagination backfill, expand-contract, `cargo sqlx prepare` refresh verified
- [ ] `rust-async-patterns` consulted; task ownership / cancellation, bounded fan-out via `JoinSet`, mutex-across-await, blocking-on-runtime audited
- [ ] `rust-messaging-patterns` consulted for any background task / Kafka / AMQP change; idempotency, post-commit dispatch, bounded queues verified
- [ ] Connection pool sizing validated against worker / replica concurrency model **if pool config is in the diff**; otherwise note as Low / Recommendation and skip rather than fail the check
- [ ] Allocation hotspots assessed when the diff touches hot loops or large structs
- [ ] Caching strategy assessed (in-process vs Redis, single-flight, invalidation explicit)
- [ ] Every finding states impact - measured (`p95: 800ms -> 120ms`) when flamegraph / OTel data exists, estimated otherwise (`adds ~N queries per request at K rows` or `each leaked task retains M bytes`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 4 + 5; `standard` ran 4-10; `deep` adds capacity guidance and load-test plan
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Rust Performance Review Summary

**Stack Detected:** Rust <version> / Axum <version>
**Runtime:** Tokio <version>
**Data Access:** sqlx <version> | diesel <version> | mixed
**Messaging:** Tokio queue | AMQP (lapin) | Kafka (rdkafka) | none
**Scope:** Backend (Rust)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [what the problem is - name the Rust idiom: N+1 via per-iteration `sqlx::query!` inside a `for` loop, missing `JOIN`, missing index, sync `bcrypt::hash` on the runtime, leaked Tokio task via missing `JoinHandle`, dispatch inside transaction, `sqlx::query` without `LIMIT`, `std::sync::Mutex` held across `.await`, etc.]
- **Impact:** [estimated effect - e.g., "N+1 in OrderHandler::list adds ~200 queries per request at 100 orders" or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [specific Rust change with code example - `WHERE id = ANY($1::int8[])`, `JoinSet` with bounded spawn, `tokio::sync::Mutex`, `spawn_blocking` for CPU work, post-commit dispatch, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Switch list endpoint to keyset pagination", "Add Redis cache for product catalog reads", "Move PDF generation to a background worker", "Wrap `bcrypt::hash` calls in `spawn_blocking`"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, schema migration, or load-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Replace per-iteration `sqlx::query!` with batched `WHERE parent_id = ANY($1::int8[])` in OrderRepository::list_with_items"]
2. **[Delegate]** [High] [scope: schema] - [one-line action, e.g., "Add concurrent composite index on (tenant_id, created_at) - spawn DB migration subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting issues without naming the Rust idiom ("this is slow" vs "N+1 from per-iteration `sqlx::query!` inside loop; replace with `WHERE id = ANY($1::int8[])`")
- Recommending generic backend advice when a Rust pattern applies (say "use `JoinSet` with `set.join_next().await`", not "use a worker pool")
- Suggesting `tokio::spawn` to "make it concurrent" without bounding (`JoinSet` + semaphore) and without an owner (`JoinHandle` or `JoinSet`)
- Suggesting `Arc<Mutex<T>>` as a default - many fits are `Arc<T>` (immutable), `Arc<RwLock<T>>` (read-heavy), or `dashmap::DashMap` (sharded)
- Suggesting `std::sync::Mutex` in async code - blocks the executor; use `tokio::sync::Mutex` or restructure to drop the guard before the await
- Suggesting `unbounded_channel()` to "avoid backpressure" - that is a memory leak; use `mpsc::channel(N)` and decide the drop / await policy
- Suggesting caching without an invalidation strategy
- Conflating performance review with general code review or security review - delegate those to their workflows
- Treating background-task retries as a substitute for idempotency - retries with non-idempotent tasks cause double-charging / double-emailing
- Recommending `db.execute_unchecked` / raw `format!`-built SQL for "dynamic" queries - parameterize via `$1`, use `query!` for static SQL, or a query builder for genuinely dynamic SQL. When `format!`-built SQL is found, the perf concern (defeats prepared-statement cache, unbounded statement plan growth) is the smaller half - the SQL injection surface is the bigger half. Add a `[Delegate] -> task-rust-review-security` entry to Next Steps so the security half doesn't get silently absorbed into a perf finding

> **Cross-workflow finding ownership.** When a finding is dual perf+security (the `format!`-built SQL above, `Command::new("sh")` shell-out, deserialization-of-untrusted-input), the perf review reports it once with a `[Delegate] -> task-rust-review-security` entry in Next Steps and stops there - it does **not** enumerate every parallel security concern in the file (auth bypass, IDOR, mass assignment, open redirect, JWT misvalidation). Those are the security delegate's territory. The perf review's job is to surface the perf half cleanly and hand off; trying to be exhaustive on the security half drowns the perf signal and produces two parallel security audits.
- Reporting "missing index" without confirming the column actually appears in a `WHERE` / `ORDER BY` / `GROUP BY` in the diff
- Approving `bcrypt::hash` / `argon2::hash` on the request future without `spawn_blocking` - blocks the executor for 100ms+ per call
- Approving `reqwest::Client::new()` per request - rebuild defeats connection pooling
- Approving `Box<dyn Trait>` over generics for hot paths or single-callsite consumers - prefer static dispatch unless heterogeneous storage is required
