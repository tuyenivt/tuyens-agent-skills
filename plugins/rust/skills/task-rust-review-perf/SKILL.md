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

**If sqlx** - use skill: `rust-db-access`:

Inspect every changed query, repository, service, and handler for:

- [ ] **N+1 in queries**: any per-iteration `sqlx::query!(... WHERE id = $1, parent_id)` inside a `for` loop over a parent set is N+1; resolve with a single `WHERE parent_id = ANY($1::int8[])` query plus in-memory grouping, OR a JOIN query that returns the parent + child rows together
- [ ] **Multi-level N+1**: nested traversal across two relations (`order → items → product`) - resolve via single JOIN or two batched queries
- [ ] **Compile-time-checked queries preferred**: `sqlx::query!` / `query_as!` for static SQL (catches schema mismatch at build time); runtime `query(...).bind(...)` is acceptable for genuinely dynamic SQL but loses validation. `sqlx-data.json` (offline mode) committed when CI lacks DB access; refreshed via `cargo sqlx prepare` after schema changes
- [ ] **Column projection over `SELECT *`**: `SELECT id, name FROM ...` to bound payload; `SELECT *` returns all columns including large `text` / `bytea` / `jsonb`. With `query_as!` and a typed struct, the macro infers the column list - but the SQL must still match the struct's fields, not implicitly select everything
- [ ] **Missing indexes for filter/sort columns**: any column used in `WHERE` / `ORDER BY` / `GROUP BY` without a `CREATE INDEX` migration
- [ ] **`fetch_all` without pagination**: any read of an unbounded collection - require `LIMIT $1 OFFSET $2` or keyset pagination (`WHERE id > $1 ORDER BY id LIMIT $2`) for any list endpoint that can grow
- [ ] **Existence checks**: `sqlx::query_scalar!("SELECT EXISTS(SELECT 1 FROM ... WHERE ...)")` over fetching the row and checking
- [ ] **Bulk operations**: `INSERT ... SELECT * FROM UNNEST($1::int8[], $2::text[])` for bulk insert (sqlx supports passing `&[T]` to `$1` with a Postgres array column type), or a single multi-VALUES insert; per-row `INSERT` in a loop is N round-trips. `ON CONFLICT (...) DO UPDATE` for idempotent upserts
- [ ] **Transactions**: `let mut tx = pool.begin().await?; ...; tx.commit().await?;` over manual statement-level commits. Long transactions (HTTP I/O inside `tx`) hold a connection for the duration - extract I/O outside the transaction, capture inputs, dispatch after commit
- [ ] **Connection pool sizing**: `PgPoolOptions::new().max_connections(N).min_connections(M).acquire_timeout(...).idle_timeout(...).max_lifetime(...)` documented; `max_connections × replica count ≤ DB-side max_connections`. Default is `max_connections(10)` - typically too low for production. `max_lifetime` always set so connections recycle past load-balancer / DB restarts
- [ ] **`acquire_timeout` set**: without it, a saturated pool blocks indefinitely. 3-10 seconds is typical; document the value
- [ ] **Per-request pool construction**: `PgPool::connect(&url).await?` inside a handler defeats pooling. The pool lives on `AppState`, cloned cheaply via `Arc`

**If diesel:**

- [ ] N+1 via per-iteration `users.find(id).first(&mut conn)` inside a loop - resolve via `users.filter(id.eq_any(ids)).load(&mut conn)`
- [ ] **Async diesel**: `diesel-async` for non-blocking queries; bare `diesel` is sync and blocks the executor unless wrapped in `spawn_blocking`. Flag any sync diesel call in an async fn
- [ ] **`bb8-diesel` / `deadpool-diesel`** for async pooling; native `r2d2` is sync-only

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

Use skill: `rust-async-patterns` for canonical patterns.

Inspect changes touching `tokio::spawn`, `JoinSet`, `select!`, channels, `Arc` + lock primitives, and worker pools:

- [ ] **Every `tokio::spawn` has an owner**: bare `tokio::spawn(async move { ... })` in a request handler is fire-and-forget - `JoinError` is dropped, panics are silently lost, results are unobservable. Use `JoinSet::spawn(...)` with `set.join_next().await` or hold the `JoinHandle` and `.await` it
- [ ] **`CancellationToken` on long-lived loops**: every `loop { ... }` in a worker / consumer pairs with `tokio::select! { _ = token.cancelled() => return, ... }`; relying on dropping the task at runtime shutdown leaks in-flight work and skips graceful drain
- [ ] **Bounded fan-out with `JoinSet`**: fan-out over a list uses `JoinSet` with a controlled spawn count or a semaphore (`tokio::sync::Semaphore::new(N)`); unbounded fan-out via `for url in urls { tokio::spawn(...) }` over a 10k-row list will exhaust DB connections / file descriptors / scheduler queues
- [ ] **`tokio::time::timeout` on every external call**: `tokio::time::timeout(Duration::from_millis(500), client.get(url).send()).await??` - explicit timeout per outbound HTTP / DB call beats relying on the underlying client default
- [ ] **`reqwest::Client` reused**: `reqwest::Client::new()` per request defeats connection pooling (each call opens a new TCP / TLS connection). Build once in `AppState`, clone the `Client` (it's `Arc`-internal) where needed
- [ ] **No `std::sync::Mutex` held across `.await`**: blocks the executor thread, deadlocks under contention. Use `tokio::sync::Mutex` when the lock must span awaits, OR restructure: `let value = { let guard = mutex.lock(); guard.clone() }; some_async(value).await;` so the guard drops before the await
- [ ] **`tokio::sync::RwLock` for read-heavy state**: many readers + occasional writer; `tokio::sync::Mutex` on a read-mostly cache forces unnecessary serialization
- [ ] **`dashmap::DashMap` for sharded concurrent maps**: `dashmap::DashMap<K, V>` is a sharded `RwLock<HashMap>` and avoids global contention; use over `Arc<RwLock<HashMap>>` for high-write or high-concurrency maps
- [ ] **Bounded channels by default**: `tokio::sync::mpsc::channel(N)` over `unbounded_channel()` - unbounded is a memory leak under backpressure
- [ ] **Channel buffer sizes intentional**: `mpsc::channel(N)` with non-obvious `N` should have a comment justifying the size (matches downstream throughput, fan-out width, or drop-policy budget)
- [ ] **No CPU-heavy work on the runtime**: hashing (`bcrypt::hash`, `argon2`), image processing, large JSON serialization on a request future blocks the executor. Wrap in `tokio::task::spawn_blocking(move || { ... })` so it runs on the blocking pool
- [ ] **No synchronous I/O on the runtime**: `std::fs::read_to_string`, `std::thread::sleep`, `reqwest::blocking::get`. Use `tokio::fs`, `tokio::time::sleep`, async `reqwest`
- [ ] **No external I/O inside a sqlx transaction**: `client.get(url).send().await` inside `let mut tx = pool.begin().await?; ... tx.commit().await?;` holds the transaction's connection for the network roundtrip. Under load this drains the pool faster than QPS would predict, and locked rows stay locked for the upstream's tail latency. Recommend: capture inputs inside the transaction, dispatch the side effect after commit

> **Impact heuristic - blast radius of a leaked Tokio task.** A leaked task is not just memory - it holds references to captured state (DB pool handles, channel halves, futures pinned in place). Under sustained traffic, leaked tasks compound: 100 leaks/sec for an hour = 360k zombie futures + their captured state, eventually triggering OOM or scheduler queue degradation. Phrase the impact as "compounding leak proportional to sustained traffic," not "this one request leaks."

> **Synchronous external dependency on the request path.** Even when the call uses `reqwest::Client` correctly, a request to a critical-path service (fraud, auth, pricing) inherits the upstream's tail latency: your p99 = max(your work, upstream p99). Recommend async patterns (decision cache, circuit breaker, fire-and-forget via background queue) when the call is non-blocking-business; recommend strict `tokio::time::timeout` plus fallback values when blocking-business.

> **Stating impact when load shape isn't in the diff.** Impact estimates need a concrete "at this RPS / at this row count" frame, but PRs rarely ship that data. When RPS, expected page size, or row count aren't in the diff or `CLAUDE.md`, **state the assumption alongside the impact** - e.g., "Assuming 100 RPS and a 5M-row `orders` table: the missing index forces a sequential scan of ~5M rows per request, p95 likely ~2s on warm cache." Failing to anchor the number leaves the finding as "this is slow" prose, which the Self-Check explicitly bans. If the assumption is load-bearing for severity (e.g., the High-tier "10M+-row" rule), say so and recommend confirming row count pre-merge.

> **Hot loop / hot path defined.** Several checklist items below gate on "hot loop" / "hot path" - by which this workflow means: (a) any code path executed once per HTTP request on the request future, (b) any code path executed once per row in a `fetch_all` / iterator result, (c) any code path inside a worker / consumer loop processing events. Setup code, one-shot startup work, and CLI tools fall outside this definition. The allocation / CPU checks in Step 7 only fire when the code is on a hot path so understood.

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

Use skill: `rust-messaging-patterns` for canonical patterns.

**If in-process Tokio task queue:**

- [ ] **Tasks idempotent**: re-fetch state, check if work was done, return early. Pass IDs / simple types as payload, never owned domain models that hold references
- [ ] **Dispatch AFTER commit**: enqueueing inside `let mut tx = pool.begin().await?; ... tx.commit().await?;` may make the worker pick up the task before the row is visible
- [ ] **Bounded queue**: `mpsc::channel(N)` with documented `N`; saturation policy (drop, block, return error) explicit
- [ ] **Worker count bounded**: a fixed number of worker tasks consume from the channel; not "spawn one task per job"

**If Kafka (`rdkafka`):**

- [ ] **Consumer groups** for parallelism so partitions distribute across consumer instances
- [ ] **Manual commits**: explicit `consumer.commit_message(&msg, CommitMode::Async)` after successful processing - never auto-commit on a message that may fail processing (at-least-once delivery requires explicit commit)
- [ ] **Idempotent consumers**: same idempotency requirement as in-process queue - retries / rebalances cause re-delivery
- [ ] **Bounded in-flight**: `queued.max.messages.kbytes`, `fetch.max.bytes` tuned for memory budget

**If AMQP (`lapin`):**

- [ ] **Manual ack**: `delivery.ack(BasicAckOptions::default()).await?` after successful processing; auto-ack drops messages on processing failure
- [ ] **Prefetch (`basic_qos`)**: limit unacked deliveries per consumer to control memory and parallelism

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
