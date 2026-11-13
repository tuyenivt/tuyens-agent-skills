---
name: task-rust-review-reliability
description: Rust reliability review - tokio timeouts, tower retry/load_shed/limits, JoinSet/Semaphore bounds, task leaks, PgPool limits, outbox, shutdown.
agent: rust-reliability-engineer
metadata:
  category: backend
  tags: [rust, axum, reliability, resilience, tokio, tower, backpressure, workflow]
  type: workflow
user-invocable: true
---

# Rust Reliability Review

Rust-aware reliability review naming `tokio::time::timeout` deadlines and drop-based cancellation, `reqwest` client timeouts, `tower` middleware (`timeout`, `retry`, `limit`, `load_shed`, `buffer`), `backon` / `reqwest-retry` backoff, `JoinSet` / `Semaphore` structured concurrency, bounded `mpsc` backpressure, `CancellationToken` task lifecycles, `PgPool` bounds, and `axum::serve(...).with_graceful_shutdown`. Reliability = behavior under failure and saturation: what happens when a dependency is slow or down, load spikes, or a process crashes mid-operation. Every finding names the failure mode and blast radius, with concrete fixes for Rust 1.94+ / Tokio / Axum 0.8.

Stack-specific delegate of `task-code-review-reliability` for Rust.

## When to Use

- Rust/Axum PR adding or changing a downstream call (`reqwest`, sqlx, Kafka / AMQP, `tonic`)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and delivery semantics
- Hardening after a near-miss; recurring resilience-debt sweep
- New `tokio::spawn` fan-out, `mpsc` pipeline, or worker pool reviewed for leaks and backpressure

**Not for:** general review (`task-rust-review`), throughput / latency (`task-rust-review-perf`), instrumentation wiring (`task-rust-review-observability`), security (`task-rust-review-security`).

## Seam With Adjacent Lenses

- **vs. Perf:** perf tunes the `PgPool` and fan-out width for throughput; this lens verifies they are bounded and that exhaustion sheds or fails fast. A slow query is perf; the untimed query holding a pooled connection while every other request waits out `acquire_timeout` is reliability.
- **vs. Observability:** obs owns the breaker-state metric, the fallback log line and the alive-task gauge; this lens owns the breaker and the fallback existing and being wired. A missing `trace_id` is obs; a missing `timeout` on the call is reliability.
- **vs. core Phase B:** `task-rust-review` Phase B owns happy-path correctness and the `rust-async-patterns` / `rust-concurrency` task-ownership and lock rules; this lens owns partial failure, dependency failure, and saturation. Idempotency sits at the seam - the umbrella dedups.

## Depth

| Depth      | When                                            | Runs                                          |
| ---------- | ----------------------------------------------- | --------------------------------------------- |
| `standard` | Default                                         | All steps except the Failure-Mode Map         |
| `deep`     | Requested, or handed down by `task-rust-review` | All + `Failure-Mode and Blast-Radius Map`     |

At `deep`, trace each new or changed dependency's failure path with `failure-propagation-analysis` across tasks and shared resources (the `PgPool`, a `Semaphore`, an `mpsc` channel, the broker) and name the loop-breaker in the Failure-Mode and Blast-Radius Map.

**Whole-service sweep** (resilience-debt pass with no feature branch, and the mode a "sweep before peak season" request asks for). When Step 3 fails fast on trunk, do not stop - skip the diff gate, keep Step 3's round paragraph (keyed to this lens's checkpoint on the trunk), and run Steps 4-14 repo-wide at `HEAD` (Step 12 confirmation-only, Step 13 on round 2+). Step 4's categories are read in full rather than per changed file, and every diff-worded rule downstream (the ripple clause, Step 4's `ops-resiliency` load gate) reads against the whole surface instead. Findings cite current code and are pre-existing by construction; a defect that is dormant today (an unreachable code path, a client no caller uses) keeps its severity, with the reachability stated under `Assumption`. Three things the sweep changes:

- **Refs.** The precondition emits no handle on a fail-fast, so resolve the writer's inputs directly: `branch` = `base_ref` = `head_ref` = the trunk branch name, `base_sha` = `head_sha` = the full `git rev-parse <trunk>` - when the current branch is not the trunk, stop and ask the user to check out the trunk or name a feature branch; `scope` / `stack` as on a diff review. The fail-fast also returns no `prior_checkpoint`: read the frontmatter of `review-reliability-<sanitized trunk>.md` in the repo root yourself, with `review-precondition-check`'s filename and validity rules, and use it as `report_path` / `prior_checkpoint` for Step 3's round paragraph and Step 13; Step 13's `diff` / `name_status` (read with `-M`) then span `<prior_head_sha>...<trunk sha>` with `<prior_head_sha>` as the reconciler's `base_ref`, overriding its full-range inputs: a sweep has no base, so the commits since the prior sweep separate touched files from untouched ones.
- **Verify attribution.** Run `review-finding-verify` for confirmation only - its Step 1, against the code at `HEAD`, with an empty `diff`. **Skip its attribution and de-escalation.** With no diff, every finding attributes `Pre-existing` and every `[Must]` de-escalates, which would empty a debt sweep of the blockers it exists to surface. Labels come from the tier; every heading carries `_(pre-existing)_` plus any annotation the confirmation returned. Tally `<N> confirmed, - reattributed, <U> unverified, <K> dropped`.
- **Depth.** A sweep defaults to `deep`: the Failure-Mode and Blast-Radius Map is the per-dependency loop-breaker table a standing-debt pass is asking for. Pass `standard` explicitly to suppress it.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-rust-review-reliability` | Current branch vs base; on trunk, runs the whole-service sweep above |
| `/task-rust-review-reliability <branch>` | `<branch>` vs base (3-dot) |
| `/task-rust-review-reliability pr-<N>` | PR head fetched into local branch (user runs fetch) |

Append `deep` to request the deep pass (e.g. `/task-rust-review-reliability <branch> deep`).

**Subagent runs** (e.g. spawned by `task-rust-review`). The parent passes the precondition handle, `base_ref` / `head_ref`, `base_sha` / `head_sha`, the pre-read diff and commit log, depth, the pre-confirmed stack, the data-access mix, messaging, and the acceptance criteria when a requirement source resolved. Steps 2 and 3 accept those instead of re-running - never re-run git. Steps 12 and 13 are skipped (the parent verifies and reconciles the merged set once): labels come from the tier, a finding whose cited line the diff did not add carries `_(pre-existing)_` and no `newly reachable via` (the parent's verify adds that) so the parent's verify pass starts from it, and the `Findings verified` and `Round` lines are omitted. Step 14 returns the whole Output Format - Summary (`Depth` as the parent passed it), Findings, Out of Lens, Recommendations, Verified Clean, Next Steps, the `deep` Map - not the findings alone, and writes nothing.

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format, several with their own `## Findings`. They are rule sets here, not deliverables: emit this skill's Output Format only. Their blockquoted `Load stack-detect first` lines are satisfied by Step 2. Where a check below and a loaded atomic disagree, the sentence names which wins.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. A subagent loads it too, unless the spawning prompt inlined its whole Rules section and its unverifiable-change disclosure, as that skill specifies.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a parent and skip detection. If not Rust, stop and route the user to `/task-code-review-reliability`.

Versions come from the manifests - the Rust version from `rust-toolchain.toml`'s `channel`, else `Cargo.toml`'s `rust-version`; the HTTP framework, sqlx / diesel and resilience crates from their resolved entries in `Cargo.lock` (a `Cargo.toml` requirement such as `0.8` is a range, not a version) - and override any version a `## Tech Stack` line declared (this step's one departure from `stack-detect`'s instruction-file precedence); in a Cargo workspace the member crate under review decides, its `Cargo.toml` read in place of the detected primary stack, versions from the workspace-root `Cargo.lock`. The `Stack` slot is `stack-detect`'s rendering with those versions added (`Rust 1.94.0 / Axum 0.8.9`, `Rust 1.94.0 (no framework detected)`), and the writer's `stack` is `rust-<framework>` lowercased (`rust-axum`, `rust-actix-web`; `rust` when there is none). The checks below name Axum / `tower` constructs; on another framework apply each to that framework's equivalent and skip one that has none. `Data Access` is the data-access crate the crate under review depends on directly - `sqlx`, `diesel` (`diesel-async` included), `SeaORM` (`sea-orm`) or `tokio-postgres` - with its `Cargo.lock` version; one present only transitively (the `sqlx` beneath SeaORM, the `tokio-postgres` beneath `diesel-async`) does not count, and two direct ones are `mixed`, both named with versions. `Messaging` lists every mechanism present, in this order, joined with ` + `: `Postgres job queue` when a worker claims rows from a jobs table with `FOR UPDATE SKIP LOCKED` (no crate marks it - read the claim query, or the migration creating the table; an outbox relay's claim is not one); `Kafka` when `rdkafka` or another Kafka client is a direct dependency; `AMQP` for `lapin`; `Tokio queue` when worker tasks drain a `tokio::sync::mpsc` channel of background jobs; `none` when there is none.

### Step 3 - Resolve the Diff and Round

Standalone only - skip the whole step, SHA capture included, when running as a subagent with handle + artifacts pre-passed.

Use skill: `review-precondition-check` with `report_type: review-reliability`. A trunk fail-fast switches to the whole-service sweep under **Depth**; any other fail-fast: surface verbatim and stop. On success, print each handle `notes` entry in chat, one line each, before the report body (nothing when it has none; the handle itself stays internal). Capture `base_sha = git rev-parse <base_ref>` and `head_sha = git rev-parse <head_ref>` (full SHAs) and resolve the round below; only then read `git diff <base>...<head>`, `git diff -M --name-status <base>...<head>` and `git log <base>..<head>`, once, for reuse. The writer's `branch` is the handle's `head_short_name`.

**Resolve the round from the handle, before any surface is read.** No `prior_checkpoint`, or `prior_checkpoint: legacy` -> `round: 1`. Valid -> `round = prior_checkpoint.round + 1`, `prior_head_sha = prior_checkpoint.head_sha`. **When `prior_checkpoint.head_sha` equals the current `head_sha` and no deeper depth than `prior_checkpoint.depth` was requested, print `No new commits on <branch> since prior reliability review at <sha_short>. Prior report unchanged.` and stop** - do not re-review and do not overwrite (`<sha_short>` is the first 7 characters of `head_sha`). On a genuine round 2+, re-review the full range; Step 13 reconciles the prior findings.

### Step 4 - Read the Reliability Surface

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (a small diff ripples: a new service function calling an unchanged `reqwest::Client` built without a timeout is a new failure path at the call site). Read the full `Cargo.toml` here (not just diff adds) to fill the Summary's Resilience Libraries field; a library is `(in use)` when any source file uses it, `(declared, unused)` otherwise.

- External clients: `reqwest::Client` construction and sharing, `tonic` channels, third-party SDKs - timeouts, pool settings, breaker, retry
- Service functions composing multiple downstream calls - deadline budget, `join!` / `try_join!` / `JoinSet` fan-out, partial-failure handling
- Task launch sites: `tokio::spawn`, `JoinSet::spawn`, `spawn_blocking`, worker loops, `mpsc` pipelines - ownership, `CancellationToken`, bounding
- Postgres job queue workers, Kafka / AMQP producers + consumers and Tokio queue workers - idempotency, retry caps, job lease, DLQ, outbox relay
- Side-effecting flows (payment, notification, provisioning) - idempotency keys, outbox vs dual write
- Config / wiring: `src/main.rs` / `src/db.rs` for `PgPoolOptions`, the `ServiceBuilder` stacks on the router and on clients, retry / breaker config, shutdown and panic wiring; the deploy manifest for replica counts and the DB ceiling
- Dependency adds: `tower` (features `timeout`, `retry`, `limit`, `load-shed`, `buffer`), `tower-http`, `backon`, `reqwest-middleware` / `reqwest-retry`, `tokio-util`, a breaker crate

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns - load it when the surface includes an external client, a fanning-out service, or breaker / retry / timeout config; skip it only when **none** of those appear, which on a mixed surface means load it. Use skill: `failure-propagation-analysis` to trace how a failure at each new / changed dependency propagates through shared resources (the `PgPool`, a `Semaphore`, an `mpsc` channel, the broker) - it is an analysis tool whose output feeds the `Blast Radius` field and, at `deep`, the Map; its own template is not emitted.

**Config the code reads but the deployment does not set** is in scope here: a base URL, DSN, or credential introduced in the diff and absent from the deploy manifest fails every call at runtime rather than at boot. Check the manifest for each new setting the wiring reads, and say so when the manifest is not in the repo.

**Defects outside the diff or the lens.** A defect on a line the diff did not add: in this lens and made newly reachable or load-bearing by the diff -> a finding (Step 12 attributes it); in this lens and untouched by the diff -> a finding at its tier label with `_(pre-existing)_` (Step 12 de-escalates it to `[Recommend]`; on a subagent run the parent's verify does), at most the three most consequential (highest tier first) on a diff review, counting only findings this round publishes for the first time (a sweep publishes every one), the rest one line each under `## Out of Lens`; owned by another lens (a correctness bug, a leaked secret, a missing index) -> `## Out of Lens` with `file:line` and the owning lens. Out of Lens items never enter Next Steps. A finding that spans two files (a pool constant shared by two binaries) anchors on the line that executes the failure and names the other file in `Issue`.

Gating skips atomic loads, never checklist rows. Every checklist row below runs on this skill's own text regardless of which atomics loaded; a row goes N/A only when the diff has no matching surface (the Self-Check rule).

### Step 5 - Timeouts, Deadlines and Cancellation

Use skill: `rust-async-patterns` for timeouts, cancellation and cancel-safety.

- [ ] **Cancellation follows the request** - a client disconnect drops the Axum handler future, cancelling every `.await` beneath it. Work a handler moves into `tokio::spawn` is detached: it outlives the request with its pool connection and permits (the Rust equivalent of severing the deadline). Spawn only work meant to outlive the request, owned and bounded per Step 10.
- [ ] **Deadline on every outbound call** - `tokio::time::timeout(d, fut)` or a client-level timeout on external I/O; sqlx queries bounded by `statement_timeout` (per `rust-db-access`). A call with no deadline waits until the socket or DB decides.
- [ ] **`reqwest::Client` bounded** - one client built at startup with `timeout` and `connect_timeout` and cloned through state (it is `Arc` inside); never `reqwest::get` / `Client::new()` per call - no total timeout by default and a fresh connection pool each time, so a hung upstream parks the task forever.
- [ ] **Timeout budget on chained / fan-out calls** - one deadline computed at entry (`Instant::now() + budget`) and each leg run under `tokio::time::timeout_at(deadline, ...)`, so a slow first call leaves budget for the rest or fails fast; a router-level `tower_http::timeout::TimeoutLayer` caps the whole request. A missing or exceeded budget on a chained path is High, per `ops-resiliency`.
- [ ] **Cancellation honored** - long loops `select!` on `token.cancelled()`; `spawn_blocking` work cannot be aborted (aborting its `JoinHandle` does nothing), so long blocking work checks a flag and stops on its own.

```rust
use std::time::Duration;
use reqwest::Client;

// Bad - reqwest::get builds a fresh client with no total timeout; a hung upstream parks this task forever
let body = reqwest::get(url).await?.text().await?;

// Good - one shared client built at startup (cloned via state) with connect + total timeouts
let client = Client::builder()
    .connect_timeout(Duration::from_secs(1))
    .timeout(Duration::from_secs(3))
    .build()?;
let body = client.get(url).send().await?.error_for_status()?.text().await?;
```

### Step 6 - Retries

- [ ] **Bounded backoff with jitter** - `backon` (`op.retry(ExponentialBuilder::default().with_jitter().with_max_times(3))`), `reqwest-retry`'s `RetryTransientMiddleware` with an exponential policy, or a `tower::retry::Retry` whose `Policy` backs off via `tower::retry::backoff`; never an uncapped `loop` retry. The retry sits inside the call's deadline (`timeout(budget, op.retry(...))`): dropping the future is how a Rust retry stops on cancellation. The `backoff` crate is unmaintained; on a pinned `backoff`, apply the same caps and name the move to `backon` as Low.
- [ ] **Transient + idempotent only** - retry 500 / 502 / 503 / 504, timeouts (`reqwest::Error::is_timeout()`), connection errors (`is_connect()`), and 429 / 408 / 425; a `Retry-After` header replaces the computed backoff, and a value beyond the remaining deadline means abandon, not wait; no other 4xx except, per `ops-resiliency`, a 409 answering a request that carried an idempotency key, a 401 after one token refresh, and 412 / 423 after re-reading the state; never a non-idempotent write without an idempotency key (Step 8).
- [ ] **Retry amplification bounded** - chained services do not each retry independently (N x M call blowup); a per-request retry budget is decremented and passed downstream, or `tower::retry::budget::TpsBudget` caps retries as a share of recent traffic.
- [ ] **Non-retryable errors escape** - `backon`'s `.when(|e| is_transient(e))`, a `reqwest-retry` `RetryableStrategy` returning `Retryable::Fatal`, or a `tower` `Policy` returning `None`, so the loop exits immediately instead of burning the budget.

### Step 7 - Circuit Breakers and Bounded Concurrency

- [ ] **Breaker per external dependency** - Rust has no de-facto breaker crate; whatever the repo uses (a pinned crate, or a `tower` `Layer` holding closed / open / half-open state behind an `Arc`) has an explicit failure threshold over a window, an open duration, and a half-open probe count; one breaker per dependency, its state metered (visibility gap -> `task-rust-review-observability`). A shared or unmonitored breaker counts as missing. `ConcurrencyLimit` + `timeout` + `load_shed` on a client stack bound the damage but keep calling a dead dependency - they are not a breaker.
- [ ] **Bounded fan-out** - `stream::iter(items).map(call).buffer_unordered(N)`, or a `JoinSet` gated by an `Arc<Semaphore>`; `join_all` / `try_join_all` over a per-request collection and a `tokio::spawn` per item are unbounded and exhaust the pool and file descriptors. N/A only when the fan-out is a fixed set of legs rather than one per item.
- [ ] **Optional legs separated from required ones** - `tokio::try_join!` returns on the first `Err` and drops the remaining legs, so an optional downstream inside it fails the whole request. Run optional legs with `tokio::join!` alongside the required group and handle each `Result`. Checked independently of the bound above: a fixed four-leg fan-out needs no limit and can still be fatally mixed.
- [ ] **Bulkhead isolation** - a `Semaphore` or `tower::limit::ConcurrencyLimitLayer` per downstream client, so one slow dependency cannot consume the concurrency budget others share.
- [ ] **Acquire before spawn** - `sem.clone().acquire_owned().await` before `set.spawn(...)`, the permit moved into the task; acquiring inside the task spawns all N immediately.

### Step 8 - Idempotency and Delivery Semantics

Use skill: `rust-db-access` for transactions and atomic upsert. Use skill: `rust-messaging-patterns` for Postgres job queue / Kafka / AMQP / Tokio queue delivery and the transactional outbox. Use skill: `backend-idempotency` for key strategy and atomic dedup.

- [ ] **Idempotency keys** on money / notification / provisioning side effects; dedup is atomic - a unique constraint + `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING RETURNING id` read with `fetch_optional` (`None` = replay), not a select-then-insert race.
- [ ] **No dual write** - producing to Kafka / AMQP inside a `pool.begin()` transaction can publish and then roll back, orphaning the event; publishing after `tx.commit()` loses it on a crash between the two. Write an outbox row in the same `tx` and relay it with `FOR UPDATE SKIP LOCKED`, per `rust-messaging-patterns`. An in-process Tokio queue enqueue is the same dual write when the job matters across a restart. A Postgres job row is the opposite case: inserted inside the business `tx`, it needs no outbox, and inserting it after `commit` reopens the gap.
- [ ] **Idempotent consumers** - Kafka, AMQP and a Postgres job queue (a lapsed lease is reclaimed and run again) deliver at least once: `enable.auto.commit=false` with the offset committed after the handler succeeds, `basic_ack` after success; handlers dedupe on the broker-supplied or producer-set ID and return early on replay. For retries and consumers alike: High when the duplicated or lost effect is financial or irreversible (charge, email, webhook), Medium when it is a recoverable database write, per `backend-idempotency`.
- [ ] **DLQ with bounded retry** - a Kafka DLQ topic after capped attempts; AMQP `basic_nack` with `requeue: false` into a dead-letter exchange, never `requeue: true` on every failure (a hot redelivery loop); a Postgres job queue settles a job `dead` at once on a permanent error and once `attempts >= max_attempts` otherwise; a Tokio queue's exhausted job lands in a failed-jobs table. DLQ depth is monitored - an unwatched dead letter store is where a systematic failure goes to be invisible.
- [ ] **Shutdown budget exceeds the longest job** - ordering: job timeout < worker drain deadline < the pod's grace period. A job still running when the drain deadline ends is aborted mid-side-effect on every rolling deploy: redelivered by the broker (uncommitted offset, unacked delivery) or by lease expiry on a Postgres job queue, lost on a Tokio queue whose job was never persisted. This is what turns a non-idempotent handler from a rare race into a scheduled one.
- [ ] **Job lease outlives the job** - the claim's `locked_until` exceeds the job's own `tokio::time::timeout` (`timeout_secs` plus a margin): a shorter lease lets a second worker reclaim a job still running, and a job with no timeout holds its worker indefinitely and runs twice once its lease lapses. The claim query's lapsed-lease arm (`status = 'running' AND locked_until < now()`) is the only redelivery path after a worker crash - without it the row stays `running` forever.

### Step 9 - Graceful Degradation, Fallbacks, and Backpressure

- [ ] **Fallback per critical dependency** - a breaker-open / timeout path returns cached / default / partial data or fails fast with 503, rather than an unbounded wait. It logs the original failure at WARN (`warn!(error = ?e, ...)`) - no silent swallow that hides degradation until it compounds.
- [ ] **Partial-failure fan-out** - an optional downstream (recommendations, enrichment) failing degrades the response, not the whole request: `tokio::join!` outside the required `try_join!`, log-and-continue on the optional leg.
- [ ] **Load shedding / backpressure** - the router sheds at saturation: `ServiceBuilder::new().layer(HandleErrorLayer::new(..)).load_shed().concurrency_limit(N)` turns "at limit" into an immediate `Overloaded` error mapped to 503 instead of queueing (`HandleErrorLayer` because Axum layers must be infallible). Work queues shed with `try_send`; a `send().await` runs only inside a deadline or a `select!` on `token.cancelled()`. The service returns an error variant and the `AppError` `IntoResponse` mapping turns it into 429 - services never build responses.
- [ ] **No unbounded queueing** - `mpsc::unbounded_channel`, a `Vec` / `VecDeque` job buffer, or a task parked per pending send each gets a cap; when full it rejects or waits a bounded time.

```rust
use tokio::sync::mpsc::{error::TrySendError, Sender};

pub struct Job { pub id: u64 }

#[derive(Debug)]
pub enum EnqueueError { Busy, Closed }

// Bad - awaits capacity: a saturated worker pool parks every request on this line
pub async fn enqueue_waiting(jobs: &Sender<Job>, job: Job) -> Result<(), EnqueueError> {
    jobs.send(job).await.map_err(|_| EnqueueError::Closed)
}

// Good - shed under saturation; the handler maps Busy to 429
pub fn enqueue(jobs: &Sender<Job>, job: Job) -> Result<(), EnqueueError> {
    match jobs.try_send(job) {
        Ok(()) => Ok(()),
        Err(TrySendError::Full(_)) => Err(EnqueueError::Busy),
        Err(TrySendError::Closed(_)) => Err(EnqueueError::Closed),
    }
}
```

### Step 10 - Resource Exhaustion and Task-Leak Prevention

Use skill: `rust-concurrency` for channel sizing, lock scope, and shared state.

- [ ] **`PgPool` bounded** - `PgPoolOptions` with explicit `max_connections` (default 10), `acquire_timeout` (default 30s: a saturated pool parks every request half a minute before failing - set it to the request budget), `max_lifetime` and `idle_timeout`, built once at startup and shared. Budget every process that opens a pool, per `rust-db-access`: `sum over binaries of ((replicas + maxSurge) * max_connections) < server max_connections - reserved`, a worker's pool sized from its own concurrency, surge 25% and reserved 10 `(assumed)` when the manifest or DB config is absent. On `mixed`, a diesel pool (`deadpool` / `bb8`) is a second pool whose size adds to that binary's term. A single shared pool-size constant serving both binaries is itself the finding. When the ceiling is not in the repo, run the check anyway and state the assumption (`verify: max_connections unknown`), never silently skip it.
- [ ] **Every task owned with a guaranteed exit** - held in a `JoinSet` / `TaskTracker` or by a kept `JoinHandle`, selecting on `token.cancelled()`; dropping a `JoinHandle` detaches the task, it does not cancel it. A leaked task retains its captures (an `AppState` clone, a pool connection, a permit); at 100/sec sustained it compounds into unbounded growth.
- [ ] **No unbounded per-request spawn** - a handler does not spawn a task per row / per item without a bound. Leak signatures: Tokio's `num_alive_tasks` climbing; tokio-console tasks idle forever on `recv()` (a `Sender` clone kept alive somewhere, so the channel never closes) or on `send().await` (receiver alive and never draining - apply a backpressure policy). `spawn_blocking` shares one pool (512 threads by default); per-request blocking work queues behind it unbounded.
- [ ] **Bounded buffers and maps** - channel capacities sized deliberately (per `rust-concurrency`); per-key `HashMap` / `DashMap` state (rate-limiter clients, dedup caches) evicted - `moka` with `max_capacity` / TTL - not grown forever.
- [ ] **No I/O under a held lock or inside a transaction** - a `tokio::sync::Mutex` guard held across an HTTP / DB `.await`, or external I/O between `pool.begin()` and `commit()`, pins the resource for the upstream tail latency and serializes the whole service.

### Step 11 - Recoverability and Crash-Safety

Use skill: `rust-web-patterns` for graceful shutdown and readiness.

Cross-aggregate consistency rule (inlined on purpose - do not re-delegate this to a separate consistency atomic; it overlaps the transaction atomic `rust-db-access` already loaded in Step 8, and its one distinct rule is captured here): writes that cannot share one transaction (a charge + a separate provisioning record, a local write + a remote call) need a compensating action or a reconciliation job on partial failure - never a best-effort inline rollback that can itself fail. Prefer one transaction; when impossible, make the second step idempotent and retriable so a re-run converges.

- [ ] **Graceful shutdown** - a `shutdown_signal()` on SIGTERM + `ctrl_c`; readiness flips to failing first so the load balancer stops routing; `axum::serve(listener, app).with_graceful_shutdown(...)` drains in-flight requests, raced against a deadline because it waits on every connection with no limit; the `CancellationToken` cancelled and workers joined (`TaskTracker::close()` then `wait()`) inside the budget; Kafka: stop polling, finish in-flight records, `producer.flush(timeout)`, commit final offsets synchronously (`commit_consumer_state(CommitMode::Sync)`) - under `enable.auto.commit=false` nothing commits on drop - then drop the consumer; AMQP: ack or nack in-flight deliveries, then close the channel and connection (unacked deliveries are redelivered, so consumers stay idempotent); `pool.close().await` last. Never `std::process::exit` on the serving path - it runs no destructors.
- [ ] **Panic safety** - a handler panic unwinds the connection task and the client sees a dropped connection, not a 500: `tower_http::catch_panic::CatchPanicLayer` on the router. A spawned task's panic surfaces only as `JoinError::is_panic()`; a supervisor that never calls `join_next()` leaves a dead worker while the process and its liveness probe stay green - it restarts the worker or exits. `panic = "abort"` in the release profile makes any panic a process crash, so every request-path `unwrap` becomes whole-service. A poisoned `std::sync::Mutex` turns every later `.lock().unwrap()` into a panic (per `rust-concurrency`).
- [ ] **Crash-safe side effects** - a multi-step side effect interrupted mid-way leaves recoverable state (outbox pending, an idempotency-guarded re-run), not a half-applied change.
- [ ] **Readiness on pod-local state only** - the readiness probe gates on a draining flag and initialised pools, so an unready replica sheds traffic it cannot serve; a readiness check that pings a shared dependency (a `SELECT 1` on Postgres, Redis) removes every replica when that dependency blips and is the High finding in this lens - this wins over `rust-web-patterns`' `ready` example. Liveness stays dependency-free (probe-wiring depth -> `task-rust-review-observability`).
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes (use skill: `rust-migration-safety`; use skill: `ops-backward-compatibility`); a migration taking `ACCESS EXCLUSIVE` or `SHARE ROW EXCLUSIVE` on a hot table without `SET LOCAL lock_timeout` as its first statement (sqlx-cli runs each migration in a transaction) is High.

### Step 12 - Verify Findings

Assign each draft finding its label first (High -> `[Must]`, Medium / Low -> `[Recommend]`, escalating per the severity rules below), since `review-finding-verify` takes labelled findings and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - never re-derive one from the severity tier afterwards. Carry its `Annotation` column verbatim onto the finding heading (`_(pre-existing)_`, `_(pre-existing; newly reachable via <file:line>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`) and its tally into the Summary's `Findings verified` slot; the tally counts this round's drafts only. A finding on a file the name-status does not list gets `_(pre-existing)_`, written first, unless its annotations already have a group opening `pre-existing` or `unverified`. The verify table is working material; only the tally and the surviving rows' labels and annotations reach the report. Subagent runs skip this step entirely (see Invocation); whole-service sweeps run confirmation only, per the Depth clause.

**Attribution when the diff changes the load, not the code.** `Pre-existing (newly reachable)` also covers an unchanged shared resource the diff makes newly load-bearing - a pool whose holds now span a broker round trip, a breaker whose dependency the diff put on the request path. No new caller is required; the character of the load changed. Cite the diff line that changed the load as the `via <file:line>` site, and retain the label rather than de-escalating.

### Step 13 - Reconcile Prior Findings (round 2+, standalone)

Skip on round 1. Otherwise read the prior report at the handle's `report_path` and project its findings into the reconciler's shape: `## High-Impact Findings` holding one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, label and `file:line` copied from the `#### <n>. [Label] file:line - <title>` heading, annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` becomes `_(pre-existing)_ _(newly reachable via X)_`). Use skill: `review-prior-findings-reconcile` with `prior_report` (the projection), `diff`, `name_status`, `head_sha`, `base_ref`, and `head_files` (`git ls-tree -r --name-only <head_sha>`). Insert its output - the table, any note lines, the tally line - under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows re-enter `## Findings` with the body the prior report gave them, cited where reconcile places the smell now, under the impact heading they were last published under (this round's tier when re-drafted; the higher tier when the prior heading combined two), with the label and every annotation group they were last published with (`_(pre-existing)_` written first when the name-status does not list the file and no group opens `pre-existing` or `unverified`) plus `_(carried from round <N>)_` (N = the round that first raised it, written once) on the heading; when this round re-drafted the same defect at the same site, publish only the re-drafted finding with that annotation appended. The table keeps the prior label and line verbatim.

### Step 14 - Write Report

Standalone only - subagent runs return the Output Format to the parent, which writes the single merged report.

Use skill: `review-report-writer` with `report_type: review-reliability` and every required input: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3 (whole-service sweep: all five resolved per the Depth clause), `stack` per Step 2, `scope: +rel`, `depth` as resolved from the Depth table, `mode: full`, and the `round` / `prior_head_sha` resolved in Step 3. Write before ending; print confirmation.

## Self-Check

Mark a line N/A with its reason when the diff has no matching surface (no messaging, no task fan-out), or when the invocation mode makes it inapplicable (subagent, whole-service sweep, round 1). A row whose subject is absent entirely - no retries anywhere - is N/A for its checks and, when the absence is itself a gap, a finding.

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: stack confirmed (or accepted from parent); versions from `Cargo.lock` / toolchain file; data access and messaging recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-reliability` (or handle received; or trunk fail-fast routed to the sweep); diff, name-status and log read once; `base_sha` / `head_sha` captured; round resolved from the handle (sweep: from the self-read checkpoint); same-SHA no-op honoured; approval obtained when `head_matches_current` was false
- [ ] Step 4: surface categories read, full `Cargo.toml` and manifest consulted; `ops-resiliency` loaded per the gate; `failure-propagation-analysis` used for blast radius; defects outside the diff or lens routed per the Step 4 rule
- [ ] Step 5: request-scoped cancellation, per-call deadline, shared `reqwest::Client` with timeouts, chained budget via `timeout_at`, cancellation honored
- [ ] Step 6: backoff + jitter capped inside the deadline, transient-only status set, retry budget, non-retryable escape
- [ ] Step 7: breaker per dependency, bounded fan-out, optional legs outside `try_join!`, bulkhead, acquire-before-spawn
- [ ] Step 8: `backend-idempotency` + `rust-db-access` + `rust-messaging-patterns` applied; idempotency keys, no dual write, idempotent consumers tiered by effect, DLQ, job lease vs job timeout, drain budget vs longest job
- [ ] Step 9: fallback per critical dependency that logs; partial-failure fan-out; `load_shed` / `try_send` shedding via an error variant; bounded buffers
- [ ] Step 10: pool budget per `rust-db-access` with assumptions stated; every task owned; leak signatures read; no I/O under lock or in tx
- [ ] Step 11: graceful shutdown sequence, panic handling for handlers and tasks, crash-safety, pod-local readiness, migration rollout; cross-aggregate consistency verified
- [ ] Step 12 (standalone): findings labelled before verify; labels and annotations carried verbatim; tally in the Summary (sweep: confirmation only)
- [ ] Step 13 (round 2+): prior report projected and reconciled with `head_sha` and `base_ref`; table inserted; `Still open` / `Needs re-check` rows carried into Findings
- [ ] Step 14 (standalone): report written via `review-report-writer` with all checkpoint fields; confirmation printed. Subagent: Output Format returned, no file written
- [ ] Every finding names the failure mode and blast radius; passed and N/A rows recorded under `## Verified Clean`; `deep` filled the Failure-Mode and Blast-Radius Map
- [ ] Next Steps tagged and ordered Must > Recommend (omit if none)

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unbounded failure path, a data-loss / corruption risk under a plausible failure, **or a bounded failure whose blast radius is the whole service** (missing deadline on a hot external call, a `reqwest` client with no timeout, uncapped retry, a missing or exceeded timeout / retry budget on a chained path, a duplicated or lost financial / irreversible effect from a retry or consumer, a dual write, unbounded per-request task spawn, a worker whose panic goes unobserved, an optional dependency wired so its failure fails every request, a probe that removes every replica on one shared dependency); Medium = failure is bounded and contained to its own path but recovery or containment is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, a duplicated recoverable database write, an unbounded channel on a warm path); Low = hardening with no immediate failure path (missing bulkhead, fail-fast where stale data would serve). A dormant defect keeps the tier its failure path would have, with reachability under `Assumption`.

Labels: High -> `[Must]`; Low -> `[Recommend]`; Medium -> `[Recommend]`, escalated to `[Must]` only when **all three** hold: the fix that fully resolves the failure mode is confined to one file, it needs no product or architectural decision (no fallback policy to choose, no new component), and the defect sits on a money, auth, or data-integrity path. Judge by the fix that resolves the failure mode, not the cheapest partial one. When any leg is arguable, leave it `[Recommend]` and say why in the finding - an escalation that two reviewers would split on is not a merge blocker.

**One finding per root cause, where the unit is the edit that fixes it.** A defect satisfying several checklist items (an unbounded fan-out hits Steps 7 and 10) is one finding at the strongest severity. Several defects in one construct that one rewrite resolves - a detached task that is also unbounded and also unobserved on panic - are likewise one finding; enumerate them (a)/(b)/(c) inside `Failure Mode` and `Blast Radius`, and count it once in `Overall`. Two defects at one call site that need **separate** fixes, or that survive each other's fix, are two findings. Two instances of one missing policy across different dependencies are one finding when the fix is a shared module, and separate findings when each site must be edited on its own terms.

**Fill rules.** `Overall` counts every published finding by tier, dormant ones included; placement is by tier too, so a High finding verify de-escalated to `[Recommend]` stays under `### High Impact`. `Findings verified` is omitted on subagent runs, its parenthetical when K is 0; a sweep writes `-` for reattributed. `Review shape` appears only on a sweep. `Resilience Libraries` lists, among `tower`, `tower-http`, `backon`, `reqwest-retry`, `tokio-util` and any breaker crate, every one `Cargo.toml` declares. Each finding heading is `#### <n>. [Label] file:line - <short title> _(annotations)_` with the label and annotations from Step 12 verbatim (tier-derived label on subagent runs and sweeps; `_(pre-existing)_` on a subagent finding whose line the diff did not add and on every sweep finding, followed by any annotation verify's confirmation returned; `_(carried from round <N>)_` on carried findings); numbering continues across tiers.

```markdown
## Rust Reliability Review Summary

- **Stack:** Rust <version> / <framework> <version> | Rust <version> (no framework detected)
- **Data Access:** sqlx <version> | diesel <version> | SeaORM <version> | tokio-postgres <version> | mixed - <crate> <version> + <crate> <version>
- **Messaging:** Postgres job queue | Kafka | AMQP | Tokio queue | <several, joined by " + "> | none
- **Resilience Libraries:** every one detected, comma-separated with versions, each marked `(in use)` or `(declared, unused)`; `none detected` only when there are none
- **Review shape:** whole-service sweep at `HEAD` on <trunk>     {sweep only}
- **Depth:** standard | deep
- **Overall:** Resilient | Gaps Found - <N> High / <N> Medium / <N> Low
- **Round:** <N>                                                   {round 2 onward; omitted on subagent runs}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff)

## Prior Round Reconciliation     {round 2+ only; omit otherwise}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

<note line>     {one paragraph per note line reconcile emitted; omit when none}

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Findings

### High Impact

#### 1. [Must] file:line - <short title> _(annotations)_     {annotation groups only when the Fill rules assign any}

- **Issue:** [name the gap: `reqwest::get` with no timeout, missing `tokio::time::timeout`, uncapped retry loop, Kafka produce inside the `sqlx` transaction, unbounded `tokio::spawn` per item, worker `JoinError` never joined, etc.]

- **Failure Mode:** [what fails and how: "payment-gateway stall parks the handler future indefinitely; each parked request holds a pooled connection"]

- **Blast Radius:** [what else is affected: "`max_connections(25)` exhausts under sustained traffic; every endpoint sharing the pool waits out `acquire_timeout` and returns 503"]

- **Fix:** [shared `reqwest::Client` with `timeout`, `tokio::time::timeout_at`, `buffer_unordered(N)` or a `Semaphore`, outbox row in the same `tx`, idempotency key, `CatchPanicLayer`, a supervisor on `join_next()`, etc.]

- **Assumption:** [only when the finding rests on something the repo cannot settle - `verify: max_connections unknown`, `assumes no out-of-repo env source`, `dormant: no caller today`]

#### 2. [Must] file:line - <short title>

[Same block, numbering continues across tiers]

### Medium Impact

[Same blocks]

### Low Impact

[Same blocks]

Omit empty sections. When every section is empty, write "No reliability issues found." Blank lines separate the field lines - consecutive bare `**Label:** value` lines collapse into one paragraph when the report renders.

## Out of Lens

[Defects another lens owns, and pre-existing in-lens defects beyond the three published - each with `file:line` and the owning lens. Omit when there are none.]

## Recommendations

[Structural resilience improvements not tied to a single finding]

## Verified Clean

Checklist rows that were evaluated and passed, with their evidence - pool budget correct, graceful shutdown complete, no dual write, every task owned. On an already-resilient service this is most of the review's value, and `Overall: Resilient` alone cannot carry it. Rows that went **N/A** belong here too, marked `N/A - <reason>`: "no fan-out exists" and "checked and correct" are different facts; a subsystem absent from the surface entirely gets one `N/A` row, not one per check. Top-level so a parent merging by section heading cannot drop it.

## Next Steps

Each tagged `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra; `[scope: <owner>]`). Order: Must > Recommend. Each item carries its finding's label as published; one row per finding, naming a shared edit on the row rather than repeating it.

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: platform] - [action]

_Omit if none._

## Failure-Mode and Blast-Radius Map     {deep only}

| Dependency (new / changed) | Down or slow | Shared resource on the propagation path | Loop-breaker |
| -------------------------- | ------------ | --------------------------------------- | ------------ |
| <name, and what the diff did to it> | <what fails, and how far it gets> | <the `PgPool`, a `Semaphore`, an `mpsc` channel, the broker, the Service endpoint list> | Present (<what contains it>) \| Partial (<what is missing>) \| **Missing** (<what to add>) |

Follow the table with any **amplification loop** found - a cycle where the failure's own consequence feeds the cause (probe failure removing replicas, which raises load on the rest, which fails more probes) - naming the one change that breaks the cycle.
```

## Avoid

- `git fetch` / `git checkout` from this workflow
- Writing a report when invoked as a subagent - the parent owns it
- Reporting a missing pattern without the failure mode ("add a timeout" vs "`reqwest::get` with no timeout parks the task and pins a pooled connection until the pool is exhausted")
- Recommending retries on non-idempotent ops without an idempotency key, or a breaker with no monitoring
- Treating Kafka / AMQP redelivery as a substitute for consumer idempotency
- Overlapping into perf (throughput tuning) or observability (metric / log wiring) - name the failure-survival gap
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
