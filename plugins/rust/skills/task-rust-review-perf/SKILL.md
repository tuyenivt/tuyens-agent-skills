---
name: task-rust-review-perf
description: "Rust / Axum / sqlx / Tokio perf review: N+1, pool sizing, task leaks, Mutex-across-await, blocking on runtime, allocation hotspots, migrations."
agent: rust-performance-engineer
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, performance, async, workflow]
  type: workflow
user-invocable: true
---

# Rust Performance Review

Stack-specific delegate of `task-code-review-perf` for Rust / Axum / sqlx / Tokio. Preserves parent invocation, diff resolution, and output shape so `task-rust-review` can aggregate.

## When to Use

- Rust/Axum PR or branch perf-regression sweep
- Slow endpoint, worker, or Kafka consumer investigation
- Pre-merge pass on sqlx queries, Tokio fan-out, channels, or hot allocation paths
- Quarterly N+1 / pool / leak audit against flamegraph or OTel data

**Not for:** general review (`task-rust-review`), security (`task-rust-review-security`), incidents (`/task-oncall-start`), pre-implementation design (`task-rust-implement`).

## Severity Rubric

Steady-state production impact, not "how scary it looks".

| Severity   | Definition                                                                                                                                                                                                                                                                                  |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **High**   | Outage shape under steady load: unbounded growth (leaked tasks, unbounded channels/`Vec`), pool starvation, executor stall (sync I/O / `bcrypt` on runtime), N+1 multiplying RPS by O(N), `std::sync::Mutex` across `.await`. Or deploy-time outage: non-`CONCURRENTLY` index or `NOT NULL` add on a hot table (>10M rows). |
| **Medium** | Degraded p95/p99: missing pool sizing, `SELECT *` over wide rows, missing pagination on growable lists, unjustified channel buffer, single-flight gap. Recoverable next PR.                                                                                                                |
| **Low**    | CPU / alloc churn: `.clone()` overuse, `format!` in hot paths, missing `Vec::with_capacity`, missing `CompressionLayer`, missing `#[tracing::instrument]`.                                                                                                                                  |

## Depth Levels

| Depth      | When                                                       | Runs                                       |
| ---------- | ---------------------------------------------------------- | ------------------------------------------ |
| `quick`    | Single endpoint or repository                              | Steps 3 + 4 only (sqlx + migrations)       |
| `standard` | Default                                                    | Steps 1-9                                  |
| `deep`     | Profiling-driven (`flamegraph` / OTel / `criterion` data)  | All steps + capacity guidance + load plan  |

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                        | Meaning                                                                |
| --------------------------------- | ---------------------------------------------------------------------- |
| `/task-rust-review-perf`          | Review current branch vs its base; fails fast on trunk                 |
| `/task-rust-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                             |
| `/task-rust-review-perf pr-<N>`   | Review PR head in local branch `pr-<N>` (user runs the fetch first)    |

When invoked as a subagent of `task-code-review-perf` or `task-rust-review`, accept the parent's precondition handle plus pre-read diff/log; skip Steps 1-3 re-detection.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Governs every step that follows.

### Step 2 - Confirm Stack and Detect Surface

Use skill: `stack-detect`. If parent already detected Rust, accept the handoff. If not Rust, stop and route to `/task-code-review-perf`.

Record for the Summary block:

- `Data Access:` sqlx | diesel | mixed (from `Cargo.toml`)
- `Messaging:` Tokio queue | AMQP (`lapin`) | Kafka (`rdkafka`) | none
- `Runtime:` Tokio

### Step 3 - Resolve Diff and Read Surface

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once; reuse. Skip entirely if parent passed the handle.

Open files that govern query/concurrency behavior so impact estimates ground in real code: changed queries (`query!`, `query_as!`, `fetch_*`), repositories (transactions), pool setup (`PgPoolOptions`), migrations (`migrations/`), handler / worker `async fn` signatures, spawn sites (`tokio::spawn`, `JoinSet`, `spawn_blocking`), channels, locks, `CancellationToken` usage, `reqwest::Client` construction. When a small diff lands a new caller of an existing N+1 repository, read the unchanged callee too - the regression attributes to the new caller. Cite real `file:line` in every finding.

### Step 4 - sqlx Hotspots and Migrations

Use skill: `rust-db-access`. Use skill: `rust-migration-safety` (any change in `migrations/`).

Workflow-specific add-ons on top of the atomic skills:

- N+1 from per-iteration `query!` over a parent set -> `WHERE id = ANY($1::int8[])` or JOIN
- `fetch_all` without `LIMIT` / keyset pagination on growable lists
- Pool config sized: `max_connections × replicas <= DB cap`; pool on `AppState`, not per-request
- No HTTP / queue I/O inside `pool.begin()...tx.commit()` (capture, dispatch after commit)
- Migration impact stated when DDL hits a hot table: row count, lock mode, expected duration. If row count unknown: "row count not in diff - confirm before deploy"
- Reasoning rule: diff adds an index -> verify the column is hot in `WHERE`/`ORDER BY`/`GROUP BY`; diff adds a column the app queries on -> flag the missing index proactively

### Step 5 - Tokio Tasks, Locks, Blocking on Runtime

Use skill: `rust-async-patterns` (task ownership, `JoinSet`, `select!`, `spawn_blocking`, cancellation, timeouts). Use skill: `rust-concurrency` (`Arc`, std vs tokio `Mutex`/`RwLock`, channels, lock-across-await).

These atomic skills own the canonical fixes (leaked spawn, mutex-across-await, sync CPU on runtime). The reviewer surfaces the diff occurrence, names the idiom, and points to the Pattern - do not re-derive the fix inline.

Workflow-specific add-ons:

- `reqwest::Client` built once on `AppState`, never `Client::new()` per request (defeats connection pool)
- `tokio::time::timeout` on every outbound I/O (HTTP, broker, Redis); name the budget
- Bounded `mpsc::channel(N)` over `unbounded_channel()`; document N's saturation behavior

### Step 6 - Allocation Hotspots

_Skipped at `quick` depth unless the diff touches hot loops or large allocations._

Hot path = per-request on the request future, per-row in a `fetch_all` result, or inside a worker/consumer loop.

- `&str` for params not stored; `Cow<'_, str>` for "sometimes owned"; `String` only when ownership is required
- `Vec::with_capacity(n)` / `HashMap::with_capacity(n)` when `n` is known
- `bytes::Bytes` over `Vec<u8>` for shared payloads (refcount + slice share)
- `Arc::clone` cheap; `String::clone` / `Vec::clone` allocate - prefer `&` when read-only
- `serde_json::to_writer(w, &v)` over `to_string` in hot paths; `write!` over `format!` for known-shape output
- Worker pool over per-job `tokio::spawn` for short-lived work (scheduler overhead compounds)

```rust
// BAD: .to_string() per row allocates on every fetched record
for u in &users { out.push(Row { name: u.name.to_string(), .. }); }

// GOOD: borrow when the output doesn't outlive the source
for u in &users { out.push(Row { name: u.name.as_str(), .. }); }
```

### Step 7 - Caching and Response

_Skipped at `quick` depth unless the diff touches cache primitives._

- In-process: `moka` (async LRU/LFU) or `dashmap`; configure capacity + TTL. `lazy_static!` `HashMap` is not a cache
- Distributed: `redis-rs` + `bb8-redis` / `deadpool-redis`; `MGET` / `pipe()` for batches
- Stampede: `moka::try_get_with` or Redis `SET NX EX`
- Invalidation explicit; document staleness budget
- `tower_http::compression::CompressionLayer` for JSON > 2KB
- HTTP cache headers (`Cache-Control`, `ETag`) on read-heavy GETs

### Step 8 - Background Tasks / Kafka / AMQP

_Skipped at `quick` depth unless the diff touches workers or brokers._

Use skill: `rust-messaging-patterns`. Workflow-specific perf invariants on top:

- Dispatch happens after `tx.commit()`, not inside the transaction (`rust-db-access` rule, called out here because workers are where it leaks in)
- Idempotent task payloads carry IDs, not owned domain models (cuts payload size, enables broker dedup)
- Bounded `mpsc::channel(N)` with documented saturation; Kafka manual `commit_message` after success; AMQP manual `delivery.ack` after success with `basic_qos` prefetch

### Step 9 - Observability Hand-off and Report

_Observability check skipped at `quick` depth._

Confirm presence only (depth belongs to `task-rust-review-observability`):

- `#[tracing::instrument]` or `metrics::histogram!` on slow paths reachable from the PR
- `tokio-console` / `console_subscriber` available behind a flag in non-prod

Gaps -> Low / Recommendation with `[Delegate] -> task-rust-review-observability`.

Then use skill: `review-report-writer` with `report_type: review-perf`. Write the report to file; print the confirmation line.

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
- **Issue:** [name the Rust idiom: N+1 via per-iteration `sqlx::query!`, sync `bcrypt::hash` on runtime, leaked spawn without `JoinSet`, `std::sync::Mutex` across `.await`, dispatch inside transaction, `NOT NULL` add on hot table, etc.]
- **Impact:** [measured (`p95 800ms -> 120ms`) or estimated (`adds ~N queries per request at K rows`, `each leaked task retains M bytes`)]
- **Fix:** [specific Rust change with code - `WHERE id = ANY($1::int8[])`, `JoinSet + Semaphore`, `spawn_blocking`, post-commit dispatch]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit empty sections._

## Recommendations

[Structural items not tied to a single finding - keyset pagination on list endpoints, Redis cache for catalog reads, move PDF generation to a worker, wrap `bcrypt` in `spawn_blocking` across the codebase.]

## Next Steps

Each item `[Implement]` (localized) or `[Delegate]` (cross-cutting / schema / load test). Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: schema] - [one-line action]
3. **[Implement]** [Recommend] file:line - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded
- [ ] Step 2 - stack confirmed Rust/Axum; `Data Access`, `Messaging`, `Runtime` recorded
- [ ] Step 3 - `review-precondition-check` ran or parent handle accepted; diff + log read once; performance surface opened (queries, pool, spawn sites, channels, locks)
- [ ] Step 4 - `rust-db-access` and `rust-migration-safety` consulted; N+1, projection, pagination, pool sizing, post-commit dispatch, migration impact stated; index/column reasoning rule applied
- [ ] Step 5 - `rust-async-patterns` and `rust-concurrency` consulted; task ownership, mutex-across-await, blocking on runtime, shared `reqwest::Client`, timeouts, bounded channels audited
- [ ] Step 6 - allocation hotspots assessed on hot paths (skipped at `quick` unless triggered)
- [ ] Step 7 - caching assessed: capacity/TTL, stampede, invalidation, compression (skipped at `quick` unless triggered)
- [ ] Step 8 - `rust-messaging-patterns` consulted for any worker / broker change; post-commit dispatch + ID-only payloads + bounded channels verified (skipped at `quick` unless triggered)
- [ ] Step 9 - observability presence checked or `[Delegate]` added; report written via `review-report-writer`; confirmation printed
- [ ] Every finding states impact (measured or estimated, never just "this is slow") and cites `file:line`
- [ ] Depth honored: `quick` ran only Steps 3-4; `standard` ran 1-9; `deep` adds capacity + load-test plan

## Avoid

- State-changing git (`fetch`, `checkout`, `reset`) - the user runs these to protect uncommitted work
- "This is slow" without naming the Rust idiom (N+1, mutex-across-await, leaked spawn, sync I/O on runtime)
- Generic backend advice when a Rust pattern applies ("use `JoinSet` + `Semaphore`", not "use a worker pool")
- Re-deriving fixes that `rust-async-patterns` / `rust-concurrency` / `rust-db-access` already own - cite the Pattern, do not paste it
- `tokio::spawn` without an owner (`JoinHandle` / `JoinSet`) or bound (`Semaphore`)
- `Arc<Mutex<T>>` as default - many fits are `Arc<T>`, `Arc<RwLock<T>>`, or `dashmap::DashMap`
- `std::sync::Mutex` in async code; `unbounded_channel()` "to avoid backpressure" (memory leak)
- Caching without an invalidation strategy
- Approving `bcrypt::hash` / `argon2::hash` on the request future without `spawn_blocking`
- Approving `reqwest::Client::new()` per request (defeats connection pooling)
- "Missing index" without confirming the column appears in `WHERE`/`ORDER BY`/`GROUP BY` in the diff
- **Dual perf+security findings** (`format!`-built SQL, `Command::new("sh")`, untrusted deserialization): report the perf half once with `[Delegate] -> task-rust-review-security` in Next Steps. Do not enumerate parallel security concerns - that is the security delegate's job
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
