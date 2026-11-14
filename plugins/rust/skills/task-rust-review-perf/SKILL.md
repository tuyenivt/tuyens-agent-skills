---
name: task-rust-review-perf
description: Rust / Axum perf review - sqlx N+1, PgPool sizing, Tokio task leaks, Mutex across .await, blocking on runtime, clone hotspots, Kafka throughput.
agent: rust-performance-engineer
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, performance, async, flamegraph, kafka, workflow]
  type: workflow
user-invocable: true
---

# Rust Performance Review

Rust-aware review naming sqlx `query!` / `query_as!` / `fetch_all` / `QueryBuilder`, `PgPoolOptions`, Tokio task ownership (`JoinSet`, `CancellationToken`), locks across `.await`, blocking work on the runtime (`spawn_blocking`), allocation and clone hotspots, Kafka / AMQP throughput, sqlx-cli migration safety.

## When to Use

- Rust/Axum PR or branch perf regression review
- Slow endpoint / worker / Kafka or AMQP consumer investigation
- Pre-merge perf pass on sqlx queries, Tokio fan-out, channels, allocation paths
- Quarterly N+1 / pool / leak sweep

**Not for:** general review (`task-rust-review`), security (`task-rust-review-security`), pre-implementation (`task-rust-implement`).

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format; they are rule sets here, and only this skill's Output Format is emitted. Where a check below and a loaded atomic disagree, the atomic's fact wins (`rust-db-access` owns the pool arithmetic, `rust-migration-safety` the lock-level table and the `-- no-transaction` rules).

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | All steps |
| `deep` | Requested, handed down by `task-rust-review`, or profiling data (`cargo flamegraph` / `pprof-rs` / OTel / `criterion` / `tokio-console` output, or database / APM measurements such as `pg_stat_statements`, `pg_stat_activity` or a latency percentile, including snapshots committed to the repo or an incident doc) is available, whatever path it measures | All + `### Capacity & Load Plan` under Sequencing |

Request deep by appending `deep` to the invocation (e.g. `/task-rust-review-perf <branch> deep`).

**Whole-service sweep** (the quarterly N+1 / pool / leak pass, with no feature branch). When Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-14 repo-wide at `HEAD` (Step 12 confirmation-only, Step 13 on round 2+); Step 4's categories are read in full, not per changed file, and findings cite current code. Three things the sweep changes:

- **Writer inputs.** The fail-fast returns no handle, so resolve them here: `branch` = `base_ref` = `head_ref` = the trunk name; `base_sha` = `head_sha` = the full `git rev-parse <trunk>` - when the current branch is not the trunk, stop and ask the user to check out the trunk or name a feature branch; `scope` / `stack` as on a diff review. The fail-fast also returns no `prior_checkpoint`: read the frontmatter of `review-perf-<sanitized trunk>.md` in the repo root yourself, with `review-precondition-check`'s filename and validity rules, and use it as `report_path` / `prior_checkpoint` for Step 3's round paragraph and Step 13; Step 13's `diff` / `name_status` (read with `-M`) then span `<prior_head_sha>...<trunk sha>` with `<prior_head_sha>` as the reconciler's `base_ref`, overriding its full-range inputs: a sweep has no base, so the commits since the prior sweep separate touched files from untouched ones.
- **Verify attribution.** Run `review-finding-verify` for confirmation only, with an empty `diff`, against the code at `HEAD`; skip its attribution and de-escalation. Labels come from the tier; every heading carries `_(pre-existing)_` plus any annotation the confirmation returned. Tally `<N> confirmed, - reattributed, <U> unverified, <K> dropped`.
- **Depth.** A sweep defaults to `deep`. Fill the Summary's `Target:` slot with what was swept.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-rust-review-perf` | Current branch vs base; on trunk, runs the whole-service sweep above |
| `/task-rust-review-perf <branch>` | `<branch>` vs base (3-dot) |
| `/task-rust-review-perf pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs fetch) |

**Subagent runs** (e.g. spawned by `task-rust-review`). The parent passes the `review-precondition-check` handle, `base_ref` / `head_ref`, `base_sha` / `head_sha`, the pre-read diff and commit log, depth, the pre-confirmed stack, and the data-access mix. Step 3 is skipped whole - never re-run its git reads. Steps 12 and 13 are skipped (the parent verifies and reconciles the merged set once): labels come from the tier (High -> `[Must]`, Medium / Low -> `[Recommend]`), a finding whose cited line the diff did not add carries `_(pre-existing)_`, plus `_(unverified: <reason>)_` when Step 4 assigned it, and no `newly reachable via` (the parent's verify adds that) so the parent's verify pass starts from it, and the `Findings verified` and `Round` lines are omitted. Step 14 returns the entire Output Format - Summary (`Depth` as the parent passed it, whatever profiling data the tree holds), Findings, Out of Lens, Recommendations, Verified Clean, Sequencing (with the Capacity & Load Plan at `deep`), Next Steps - instead of writing. Derive `Messaging` per Step 2 when the parent did not send it.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. A subagent loads it too, unless the spawning prompt inlined its whole Rules section and its unverifiable-change disclosure, as that skill specifies.

### Step 2 - Stack and Data Access

Use skill: `stack-detect`. A subagent run skips detection: it takes what the parent pre-confirmed (stack, versions, data-access mix, messaging) as passed and reads the manifests below only for a slot the parent left empty. If not Rust, stop and recommend `/task-code-review-perf`. Versions come from the repository - the Rust version the `Stack` slot shows from `rust-toolchain.toml`'s `channel`, else `Cargo.toml`'s `rust-version`, written as that source writes it (`1.94.0`, `1.94`), with the `edition` (the loaded atomics gate idioms on `rust-version` first, as they specify); Axum / Tokio / sqlx as resolved in `Cargo.lock` - and override any version a `## Tech Stack` line declared (this step's one departure from `stack-detect`'s instruction-file precedence); in a Cargo workspace the member crate under review decides, its `Cargo.toml` (and any `[workspace.dependencies]` it inherits) read in place of the detected primary stack. The `Stack` slot is `stack-detect`'s rendering with those versions added (`Rust 1.94 (edition 2024) / Axum 0.8.9 / Tokio 1.54.1`, `Rust 1.94 (edition 2024) / Tokio 1.54.1 (no framework detected)`), and the writer's `stack` is `rust-<framework>` lowercased (`rust-axum`, `rust-actix-web`; `rust` when there is none). The checks below name Axum and sqlx constructs; on another framework or data-access crate apply each to that crate's equivalent and skip one that has none. `Data Access` is the data-access crate the crate under review depends on directly - `sqlx`, `diesel` (`diesel-async` included), `SeaORM` (`sea-orm`) or `tokio-postgres` - with its `Cargo.lock` version; one present only transitively (the `sqlx` beneath SeaORM, the `tokio-postgres` beneath `diesel-async`) does not count, and two direct ones are `mixed`, both named with versions. `Messaging` lists every mechanism present in any workspace member (the reviewed crate may enqueue what another member claims), in this order, joined with ` + `: `Postgres job queue` when a worker claims rows from a jobs table (no crate marks it - read the claim query, or the migration creating the table; a claim missing `FOR UPDATE SKIP LOCKED` still counts; an outbox relay's claim is not one); `Kafka` when `rdkafka` or another Kafka client is a direct dependency; `AMQP` for `lapin`; `Tokio queue` when worker tasks drain a `tokio::sync::mpsc` channel of background jobs; `none` when there is none.

### Step 3 - Resolve Diff and Round

Standalone only - skip the whole step, SHA capture included, when a subagent received the handle.

Use skill: `review-precondition-check` with `report_type: review-perf`. A trunk fail-fast switches to the whole-service sweep under **Depth**; any other fail-fast: surface verbatim and stop. On success, print each handle `notes` entry in chat, one line each, before the report body (nothing when it has none; the handle itself stays internal). Capture `base_sha = git rev-parse <base_ref>` and `head_sha = git rev-parse <head_ref>` (full SHAs) and resolve the round below; only then read diff, log and `git diff -M --name-status <base_ref>...<head_ref>`, once, for reuse. The writer's `branch` is the handle's `head_short_name`.

**Resolve the round from the handle, before any surface is read.** No `prior_checkpoint`, or `prior_checkpoint: legacy` -> `round: 1`. Valid -> `round = prior_checkpoint.round + 1`, `prior_head_sha = prior_checkpoint.head_sha`. **When `prior_checkpoint.head_sha` equals the current `head_sha` and no deeper depth than `prior_checkpoint.depth` was requested, print `No new commits on <branch> since prior perf review at <sha_short>. Prior report unchanged.` and stop** - do not re-review and do not overwrite (`<sha_short>` is the first 7 characters of `head_sha`).

### Step 4 - Read the Performance Surface

Cite real `file:line`, each file read at `head_ref` (`git show <head_ref>:<path>`, on subagent runs too) - the working tree may be on another branch. Open:

**sqlx:** changed queries (`query!` / `query_as!` / `query_scalar!`, runtime `query` / `query_as`, `QueryBuilder`); changed repositories for `fetch_all` / `fetch` / `fetch_optional` and transaction scope (`pool.begin()` ... `tx.commit()`); `PgPoolOptions` setup (`src/main.rs`, `src/db.rs`, `AppState`) and statement logging (`ConnectOptions::log_statements`).

**Every crate:** `migrations/`; Kafka / AMQP producers + consumers; worker concurrency; new `tokio::spawn` / `JoinSet::spawn` / `spawn_blocking` sites; channels; locks (`std::sync` / `tokio::sync` / `parking_lot` / `DashMap`); `reqwest::Client` construction; `Dockerfile` and `[profile.release]` for the build profile. Pool sizing needs numbers the diff rarely carries - replica count and surge per binary (deploy manifest, `values.yaml`), DB `max_connections` and the reserved slots (`CLAUDE.md`, infra config). Read them; when still unknown, run the check assuming `maxSurge` = 25% of replicas rounded up and 10 reserved slots, and mark each `(assumed)` in the finding rather than skipping it. A performance number from an incident doc or runbook is evidence when the tree still matches it; when the tree disagrees, the finding is `_(unverified: <reason>)_`.

**Defects outside the diff or the lens.** A defect on a line the diff did not add: in this lens and made newly reachable by the diff (a new endpoint calling an existing repository with an N+1) -> read the unchanged file and file a finding anchored on the defect, citing the new call site as the trigger (Step 12 attributes it); in this lens and untouched by the diff -> a finding at its tier label with `_(pre-existing)_` (Step 12 de-escalates it to `[Recommend]`; on a subagent run the parent's verify does), at most the three most consequential (highest tier first; within a tier a `measured` impact before any other, then a file the diff touches before one it does not, then path and line order) on a diff review, counting only findings this round publishes for the first time (a sweep publishes every one), the rest one line each under `## Out of Lens`; owned by another lens, or by none (a dual write with no outbox is `+rel`, a `tracing` event with no request id is `+obs`, a compile break or logic error is `task-rust-review`'s) -> `## Out of Lens` with `file:line` and the owner. A finding on this lens's path that a sibling lens also owns (an in-tx publish, unbounded fan-out) is kept here with `Also owned by: +rel | +obs | +sec` on its `Issue` line, so the parent's merge dedups deliberately. A finding that spans two changed files anchors on the line that executes the cost and names the other file in `Issue`.

### Step 5 - sqlx Hotspots

Use skill: `rust-db-access`. On diesel / SeaORM / `tokio-postgres` apply each row to that crate's equivalent.

- [ ] **N+1:** per-iteration `query_as!(...).fetch_one` over a parent list -> one `WHERE id = ANY($1)` bound with a `&[i64]` / `&[Uuid]`, grouped in memory, or a `JOIN` with `json_agg`
- [ ] **Overfetch:** `SELECT *` over wide rows -> explicit columns into a narrow `FromRow` struct; the projection must include the key the caller groups on
- [ ] **Unbounded reads:** list endpoints use keyset pagination with a deterministic order (`WHERE id > $1 ORDER BY id LIMIT $2`); `fetch_all` on a growable table with no `LIMIT`, or `OFFSET` paging once page depth is unbounded, is a High finding; large exports stream with `fetch` + `TryStreamExt` rather than buffering via `fetch_all`
- [ ] **Per-row loops:** bulk insert via `INSERT ... SELECT * FROM UNNEST($1::int8[], $2::text[])` (one bind per column, no row cap) or `QueryBuilder::push_values` chunked at `65535 / columns` rows; `ON CONFLICT DO NOTHING` over select-then-insert
- [ ] **Existence checks:** `query_scalar!("SELECT EXISTS(SELECT 1 FROM ... WHERE ...)")` over fetch-then-`is_empty`
- [ ] **Statement bound:** dropping a query future (client disconnect, `tokio::time::timeout`) frees the task, not the server-side statement - long queries need `statement_timeout` (`PgConnectOptions::options`, or `SET LOCAL` in the transaction)
- [ ] **Pool built once:** one `PgPool` on `AppState` (it is `Arc` inside; clone it), never `PgPool::connect` per request or per job; `acquire_timeout` set below the request budget (default 30s, so starvation shows as a 30s hang rather than an error)
- [ ] **Pool sized:** `PgPoolOptions::new().max_connections(N)` (default 10 per pool), with `sum over binaries of ((replicas + maxSurge) * max_connections) < max_connections(server) - reserved` - api and worker binaries counted separately, and every pool one binary builds counted. Severity comes from the arithmetic, not from whether the pool line is in the diff: when the diff changes either side of that inequality - the pool value, a replica count, or worker concurrency - anchor the finding on the changed line, cite the unchanged constraint, and rate it on the computed consequence. A pool untouched on both sides is tiered by the same arithmetic and attributed `_(pre-existing)_`
- [ ] **Prod-unsafe config:** `log_statements(LevelFilter::Info)` or a prod `RUST_LOG` enabling `sqlx=debug` (every statement logged on the request path); a debug build shipped (see Step 8)

### Step 6 - Indexes and Migrations

Use skill: `rust-migration-safety` for changes in `migrations/`; it owns the lock-level table and the per-file rules. Checks this lens adds:

- [ ] Every `WHERE` / `ORDER BY` / `GROUP BY` column added or newly queried by the diff is backed by an index; composite indexes match the leftmost prefix; FK columns indexed (PostgreSQL does not auto-index FKs); partial indexes for boolean / enum filters selecting a small subset
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY` in a file whose first line is `-- no-transaction` and which holds that one statement and no `SET` (sqlx wraps every other file in a transaction, and `CONCURRENTLY` aborts inside one); a transactional file, up or down, taking `ACCESS EXCLUSIVE` or `SHARE ROW EXCLUSIVE` on a hot table opens with `SET LOCAL lock_timeout = '3s'`
- [ ] Unique constraints at DB level, not just a pre-insert existence check in the repository
- [ ] Expand-then-contract; DDL separated from DML; backfill via keyset pagination, never `WHERE col IS NULL LIMIT N`
- [ ] `ALTER TYPE ... ADD VALUE` (PG12+) may run in a transaction, but the new value is unusable until commit - no statement in the same file may reference it
- [ ] Reversible migrations (`.up.sql` / `.down.sql`) pair every `up` with a `down`; no applied migration file edited (sqlx checksums each, and a changed file aborts `sqlx::migrate!().run` at boot)

**Reasoning rule.** When the diff _adds_ an index, validate the index is needed (selectivity, shape), then assess safety. When the diff _adds a column_ that will be queried, flag the missing index proactively.

**Migration impact template.** State impact before approving DDL on a hot table, naming the lock from `rust-migration-safety`'s table: a non-concurrent `CREATE INDEX` takes `SHARE` (blocks writes, allows reads); most `ALTER TABLE` DDL takes `ACCESS EXCLUSIVE` (blocks both), while `ADD ... FOREIGN KEY ... NOT VALID` takes `SHARE ROW EXCLUSIVE` and `VALIDATE CONSTRAINT` takes `SHARE UPDATE EXCLUSIVE`. _"`CREATE INDEX` without `CONCURRENTLY` on a 40M-row table takes `SHARE` for 5-30 min at this scale; every write queues."_ When `sqlx::migrate!().run` runs at boot, the lock also holds every replica's readiness. If row count unknown, note "row count not in diff - confirm before deploy."

**Consolidation.** Group by the edit that fixes it, not by the row that caught it. Several safety rows failing in one migration version - no `CONCURRENTLY`, missing `-- no-transaction`, DDL not separated from DML, unbatched backfill, no `SET LOCAL lock_timeout` on its `ACCESS EXCLUSIVE` / `SHARE ROW EXCLUSIVE` files - are **one** finding at the strongest severity listing the failed rows, and the version's `up` and `down` files count as one version. A defect whose fix is a **different** file (a missing index that needs its own new migration, numbered after the highest version on the branch) stays a separate finding even when the same version exposed it.

### Step 7 - Tokio Tasks, Locks and Blocking

Use skill: `rust-async-patterns` (task ownership, cancellation, timeouts, `spawn_blocking`). Use skill: `rust-concurrency` (locks, channels, `Send` / `Sync`). They own the canonical fixes; name the idiom and cite the pattern.

**Impact heuristic.** A detached task retains everything it captured - an `AppState` clone, the request body, a pooled connection, a semaphore permit. Under load, leaks compound (100/sec for an hour = 360k tasks). Phrase as "compounding leak proportional to sustained traffic," not "this one request leaks."

- [ ] **Task ownership + cancellation:** every `tokio::spawn` has an owner (`JoinSet`, `tokio_util::task::TaskTracker`, or a stored `JoinHandle` that is awaited or aborted - dropping the handle detaches the task); long-running loops `select!` on `CancellationToken::cancelled()`
- [ ] **Bounded fan-out:** `Arc<Semaphore>` with `acquire_owned`, or `stream::iter(..).buffer_unordered(N)`; an unbounded `join_all` or spawn loop over a request-sized list exhausts the pool / FDs
- [ ] **Timeouts on outbound calls:** `reqwest::ClientBuilder::timeout` (no default timeout) or `tokio::time::timeout` around broker / Redis / gRPC calls; name the budget
- [ ] **Shared HTTP client:** one `reqwest::Client` on `AppState` (cheap to clone); `Client::new()` per request rebuilds the connection pool and TLS config every call
- [ ] **Locks not held across `.await`:** a `std::sync::Mutex` / `parking_lot` guard across `.await` is a compile error in a `Send` future (Axum handlers, `tokio::spawn`) but compiles in `!Send` contexts and trips clippy `await_holding_lock`; a `tokio::sync::Mutex` guard held across an HTTP / DB call compiles and serializes every caller. Drop the guard in a scoped block before the await; per-key coalescing via `moka` or a `DashMap` of entries (never a `DashMap` ref held across `.await`); read-mostly config via `ArcSwap` or `RwLock`
- [ ] **No blocking on the runtime:** `std::fs`, `std::thread::sleep`, `reqwest::blocking`, a sync DB driver, `bcrypt` / `argon2` hashing, or a large `serde_json` parse on a runtime worker stalls every task on that thread -> `tokio::task::spawn_blocking` (pool capped at 512 threads by default), `rayon` for CPU-parallel work, `tokio::fs` for file I/O
- [ ] **Bounded channels:** `mpsc::channel(N)` over `unbounded_channel()`, with N's saturation behaviour documented; an unbounded channel with a faster producer is unbounded memory
- [ ] **No external I/O inside a transaction:** an HTTP / broker call between `pool.begin()` and `tx.commit()` holds a pooled connection for the upstream's tail latency. Capture inputs; dispatch after `commit` returns `Ok`

### Step 8 - Allocation Hotspots

Hot path = per request, per row of a `fetch_all` result, or inside a worker / consumer loop.

- [ ] **Pre-allocation:** `Vec::with_capacity(n)` / `HashMap::with_capacity(n)` / `String::with_capacity(n)` when `n` is known
- [ ] **Clones:** `String` / `Vec` / large-struct `.clone()` per row -> borrow (`&str`, `Cow<'_, str>`), share (`Arc<str>`, `bytes::Bytes`), or move; `Arc::clone` is a refcount bump and is fine
- [ ] **Formatting:** `format!` / `to_string` in loops -> `write!` into one reused buffer
- [ ] **Serialization:** typed structs over a `serde_json::Value` round-trip; `serde_json::to_writer` into the response buffer for large bodies; `simd-json` / `sonic-rs` only when profiling shows `serde_json` dominating
- [ ] **Build profile:** the shipped binary is built with `--release` and `[profile.release]` does not lower `opt-level`; a debug build in the `Dockerfile` is High (an order of magnitude slower on CPU-bound paths)
- [ ] **Allocator:** RSS climbing with no leaked tasks under a multi-threaded runtime is glibc fragmentation -> `tikv-jemallocator` / `mimalloc`, only on measured evidence

### Step 9 - Caching

- [ ] **In-process:** `moka::future::Cache` with `max_capacity` and `time_to_live`; a `static` `Mutex<HashMap>` with no bound or expiry is a leak, not a cache
- [ ] **Redis cache:** shared across replicas via `deadpool-redis` / `bb8-redis` (or `fred`); `SET ... EX` for TTL; `redis::pipe()` / `MGET` for batched ops
- [ ] **Stampede protection:** hot keys with expensive regen use `moka`'s `try_get_with` (concurrent misses on one key run the init once); distributed via Redis `SET NX EX` lock
- [ ] **Invalidation explicit** - document the staleness budget
- [ ] **HTTP caching** (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GETs, set in the handler or via `tower_http::set_header::SetResponseHeaderLayer`
- [ ] **Response compression** via `tower_http::compression::CompressionLayer`, raising the floor with `.compress_when(DefaultPredicate::new().and(SizeAbove::new(2048)))` (the default predicate compresses anything over 32 bytes)
- [ ] **Per-request memoization** via request extensions (`req.extensions_mut().insert` in middleware, read with the `Extension<T>` extractor)

### Step 10 - Kafka / AMQP / Background Work

Skip when `Messaging` is `none` and the diff adds no producer, consumer, or job queue; mark the step N/A. Otherwise use skill: `rust-messaging-patterns`.

**All brokers and in-process queues:**

- [ ] **Idempotent + ID payloads:** re-fetch state, return early if done; payload carries IDs / primitives, not owned domain structs
- [ ] **Publish AFTER commit:** never between `pool.begin()` and `tx.commit()`; an outbox when publish and write must be atomic (`Also owned by: +rel`). A Postgres job row is the exception: it is inserted inside the business transaction
- [ ] **Retry policy explicit:** capped attempts with backoff, then a DLQ (a job table's `dead` status); worker concurrency aligned to downstream capacity and to the pool budget in Step 5

**Postgres job queue:**

- [ ] **Claim query indexed:** the `FOR UPDATE SKIP LOCKED` subquery is served by an index matching its predicate and `ORDER BY` (a partial index on `run_at` `WHERE status = 'queued'`), and `done` / `dead` rows are pruned - a claim scanning settled rows slows every worker as the table grows
- [ ] **Claim batch and poll interval sized:** workers x claim batch fits the pool share from Step 5, since each claim and settle holds a connection; the idle poll is a deliberate latency / load trade (N workers polling every 100ms is 10N queries/s against an empty table) - `PgListener` on a `NOTIFY` wakes workers when latency matters

**Kafka (`rdkafka`):**

- [ ] **Manual commits:** `enable.auto.commit=false` and `consumer.commit_message(&msg, CommitMode::Async)` after successful processing (or `enable.auto.offset.store=false` with `store_offset_from_message` after success)
- [ ] **Bounded in-flight:** processing concurrency capped (`buffer_unordered(N)` or a semaphore over the `StreamConsumer` stream); `queued.max.messages.kbytes` / `fetch.max.bytes` tuned for memory

**AMQP (`lapin`):**

- [ ] **Prefetch + manual ack:** `basic_qos(prefetch_count, ...)` set (0 means unlimited deliveries in flight); `delivery.ack(BasicAckOptions::default())` after success, `nack` with an explicit requeue decision on failure

### Step 11 - Observability for Perf (delegation handoff)

Depth belongs to `task-rust-review-observability`. Confirm only:

- [ ] Slow paths from this PR have **some** instrumentation (`#[tracing::instrument]` span or `metrics::histogram!`); if not, raise a Low-impact finding (`[Recommend]`) and delegate
- [ ] sqlx statement logging not at `info` in prod (only if in diff)
- [ ] Profiling surfaces (`pprof-rs` endpoint, `console_subscriber`) non-prod, behind a cargo feature, or behind auth

**Checks that ran clean.** A checklist row that was evaluated and passed goes in `## Verified Clean`, naming the row and its evidence.

### Step 12 - Verify Findings

Applies to every finding in the review. Assign each draft finding its label first (High -> `[Must]`, Medium / Low -> `[Recommend]`), since `review-finding-verify` takes labelled findings and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - it de-escalates `[Must]` to `[Recommend]` on untouched pre-existing code, and that survives onto the finding heading and into Next Steps. Carry its `Annotation` column verbatim onto the heading (every group it returned: `_(pre-existing)_`, `_(pre-existing; newly reachable via <file:line>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`) and its tally into the Summary's `Findings verified` slot; the tally counts this round's drafts only, a carried finding among them only when this round re-drafted it. A finding on a file the name-status does not list gets `_(pre-existing)_`, written first, unless its annotations already have a group opening `pre-existing` or `unverified`. The verify table is working material; only the tally and the surviving rows' labels and annotations reach the report.

Subagent runs skip this step entirely (see Invocation); whole-service sweeps run confirmation only (see Depth).

### Step 13 - Reconcile Prior Findings (round 2+, standalone)

Skip on round 1. Otherwise read the prior report at the handle's `report_path` and project its findings into the reconciler's shape: `## High-Impact Findings` holding one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, label and `file:line` copied from the `#### <n>. [Label] file:line - <title>` heading, annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` becomes `_(pre-existing)_ _(newly reachable via X)_`). Use skill: `review-prior-findings-reconcile` with `prior_report` (the projection), `diff`, `name_status`, `head_sha`, `base_ref`, and `head_files` (`git ls-tree -r --name-only <head_sha>`). Insert its output - the table, any note lines, the tally line - under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows re-enter `## Findings` with the body the prior report gave them, cited where reconcile places the smell now, under the impact heading they were last published under (this round's tier when re-drafted; the higher tier when the prior heading combined two), with the label and every annotation group they were last published with (`_(pre-existing)_` written first when the name-status does not list the file and no group opens `pre-existing` or `unverified`) plus `_(carried from round <N>)_` (N = the round that first raised it, written once) on the heading; when this round re-drafted the same defect at the same site, publish only the re-drafted finding with that annotation appended. The table keeps the prior label and line verbatim.

### Step 14 - Write Report

Standalone only - subagent runs return the Output Format to the parent, which writes the single merged report.

Use skill: `review-report-writer` with `report_type: review-perf` and every required input: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3 (whole-service sweep: all five per the Depth clause), `stack` per Step 2, `scope: +perf`, `depth` as resolved from the Depth table, `mode: full`, and the `round` / `prior_head_sha` resolved in Step 3. Write before ending; chat then carries the handle notes, the report body and the writer's confirmation line, in that order.

## Self-Check

Mark a line N/A with its reason when the diff has no matching surface (no messaging, no migrations, no task fan-out), or when the invocation mode makes it inapplicable (subagent, sweep, round 1).

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: stack confirmed Rust (or stopped with `/task-code-review-perf`); versions from `rust-toolchain.toml` / `Cargo.toml` / `Cargo.lock`; data-access mix and messaging recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-perf` (or handle received; or trunk fail-fast routed to the sweep); diff, log and name-status read once; `base_sha` / `head_sha` captured; round resolved from the handle (sweep: from the self-read checkpoint); same-SHA no-op honoured; approval obtained when `head_matches_current` was false
- [ ] Step 4: performance surface read directly; replica count, surge, `max_connections` and reserved resolved or marked `(assumed)`; defects outside the diff or lens routed per the Step 4 rule; sibling overlap marked `Also owned by`
- [ ] Step 5: `rust-db-access` applied; N+1, overfetch, pagination, batching, statement timeout, pool built once, pool arithmetic anchored on the changed side, prod-unsafe config
- [ ] Step 6: `rust-migration-safety` applied; indexes, `CONCURRENTLY` with `-- no-transaction`, `SET LOCAL lock_timeout`, expand-contract, backfill, applied files unedited; lock named from its table; per-version findings consolidated
- [ ] Step 7: `rust-async-patterns` and `rust-concurrency` applied; task ownership, fan-out, timeouts, shared client, locks across `.await`, blocking on the runtime, bounded channels, I/O inside transactions
- [ ] Step 8: allocation hotspots and build profile assessed when the diff touches hot loops, large structs, or the build
- [ ] Step 9: caching assessed (in-process vs Redis, stampede, invalidation, compression)
- [ ] Step 10: `rust-messaging-patterns` applied when messaging is present (or N/A); idempotency, post-commit publish, retry policy, concurrency, claim index / batch / poll interval, manual commits, prefetch / bounded in-flight
- [ ] Step 11: instrumentation presence confirmed; clean rows recorded under `## Verified Clean`
- [ ] Step 12 (standalone): findings labelled before verify; labels and annotations carried verbatim; tally in the Summary (sweep: confirmation only)
- [ ] Step 13 (round 2+): prior report projected and reconciled with `head_sha` and `base_ref`; table inserted; `Still open` / `Needs re-check` rows carried into Findings
- [ ] Step 14 (standalone): report written via `review-report-writer` with all checkpoint fields; confirmation printed. Subagent: Output Format returned, no file written. Either way: every finding states impact labelled `measured`, `estimated`, or `projected`; findings ordered by impact; `## Sequencing` names quick wins vs structural; `deep` filled all four parts of the Capacity & Load Plan; Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Fill rules.** `Overall` counts by impact tier: `Issues Found - <N> High / <N> Medium / <N> Low`. `Findings verified` is omitted on subagent runs, its parenthetical when K is 0; a sweep writes `-` for reattributed. `Target` and `Review shape` appear only on a whole-service sweep. Placement is by tier and the label by Step 12 (Step 13 for carried findings): a High finding de-escalated to `[Recommend]` stays under `### High Impact`. `Depth` is this run's, whatever a prior round ran. Any field the repo cannot settle takes the value plus `(inferred from <evidence>)`.

**Impact tiers.** High = the finding accounts for a measured breach, or scales with request volume or row count so it degrades on its own (N+1, unbounded read, pool oversubscription, a leaked task or unbounded channel, blocking work stalling a runtime worker, a lock or transaction held across I/O, an allocation source dominating the profile). Medium = a real cost that is bounded and does not grow (a fixed overfetch, a missing outbound timeout, one unbatched write loop, a per-request `reqwest::Client`). Low = hardening with no current cost path, or a fix worth making while the file is open. The tier follows consequence, not evidence quality: `estimated` evidence does not cap it. **Impact is labelled by provenance.** `measured` = a number observed today (flamegraph, `pprof-rs`, OTel, APM, `pg_stat_statements`). `estimated` = derived from row counts or cart sizes in the repo. `projected` = a post-fix target; never labelled measured.

**Each finding is its own numbered block** under its impact heading, headed `#### <n>. [Label] file:line - <short title> _(annotations)_` where the label is exactly one of `[Must]` / `[Recommend]` and, with the annotations, comes from Step 12 verbatim (Step 13 for carried findings; the subagent-run and sweep rules above on those runs). Numbering continues across tiers so Sequencing and Next Steps can cite `finding <n>`. Blank lines separate the field lines.

```markdown
## Rust Performance Review Summary

- **Stack:** Rust <version> (edition <edition>) / <framework> <version> / Tokio <version> | Rust <version> (edition <edition>) / Tokio <version> (no framework detected)
- **Data Access:** sqlx <version> | diesel <version> | SeaORM <version> | tokio-postgres <version> | mixed - <crate> <version> + <crate> <version>
- **Messaging:** Postgres job queue | Kafka | AMQP | Tokio queue | <several, joined by " + "> | none
- **Scope:** Backend (Rust)
- **Review shape:** whole-service sweep at `HEAD` on <trunk>     {sweep only}
- **Target:** <what was swept>                                    {sweep only}
- **Depth:** standard | deep
- **Overall:** Clean | Issues Found - <N> High / <N> Medium / <N> Low
- **Round:** <N>                                                   {round 2 onward; omitted on subagent runs}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff)

## Prior Round Reconciliation     {round 2+ only; omit otherwise}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

<note line>     {one paragraph per note line reconcile emitted; omit when none}

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Findings

### High Impact

#### 1. [Must] file:line - <short title> _(annotations)_     {annotation groups only when a rule above assigns any}

- **Issue:** [Rust idiom: N+1 via per-iteration `query_as!(...).fetch_one`, `fetch_all` with no `LIMIT`, missing index, `argon2` hashing on a runtime worker, detached `tokio::spawn` with no `CancellationToken`, `tokio::sync::Mutex` held across an HTTP call, Kafka publish inside a transaction; `Also owned by: +rel | +obs | +sec` when a sibling lens shares it]

- **Impact:** [measured: "552,914 calls, 418s DB time over the run" / estimated: "adds ~200 queries per request at 100 orders" / projected: "~4 queries after batching"]

- **Fix:** [Rust change with code]

#### 2. [Must] file:line - <short title>

[Same block]

### Medium Impact

[Same blocks, numbering continues]

### Low Impact

[Same blocks, numbering continues]

Omit empty sections. When every section is empty, write "No performance issues found."

## Out of Lens

[Defects another lens or `task-rust-review` owns, each with `file:line` and the owner, and pre-existing in-lens defects beyond the three published, each with `file:line`. Omit when there are none.]

## Recommendations

[Structural improvements not tied to a single finding]

## Verified Clean

Checks that ran and passed, with their evidence - instrumentation present, pool correctly sized, retry policy explicit. Top-level so a parent merging by section heading cannot drop it.

## Sequencing

Quick wins (single-file, mechanical) vs structural (change the shape of the path), each citing finding numbers, plus the order to land them when findings compound.

### Capacity & Load Plan     {deep only}

Current measured state per breached signal; connection budget (`sum over binaries of ((replicas + maxSurge) * max_connections)` vs server `max_connections - reserved`, assumptions marked); projected post-fix numbers, labelled projections; numbered re-measure plan naming which signal confirms which fix.

## Next Steps

Each tagged `[Implement]` (localized code change this team owns) or `[Delegate]` (schema/migration work, another lens, or a cross-team dependency), with `[scope: schema | observability | reliability | security | cross-service | ops]` on delegated items. Order: Must > Recommend. Each item carries its finding's label as published; one row per finding, naming a shared edit on the row rather than repeating it.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: schema] - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- `git fetch` / `git checkout` from this workflow
- Writing a report when invoked as a subagent - the parent owns it
- Reporting without naming the idiom ("this is slow" vs "N+1 from per-iteration `query_as!`"); generic advice when a Rust pattern applies ("use `JoinSet` + `Semaphore`", not "use a worker pool")
- "Missing index" without confirming the column appears in `WHERE` / `ORDER BY` / `GROUP BY`
