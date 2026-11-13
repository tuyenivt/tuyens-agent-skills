---
name: rust-async-patterns
description: "Tokio async: task ownership, JoinSet/TaskTracker, CancellationToken, select! cancel safety, timeouts, spawn_blocking, bounded fan-out, task leaks."
metadata:
  category: backend
  tags: [rust, tokio, async, cancellation, joinset, spawn-blocking]
user-invocable: false
---

# Rust Async Patterns (Tokio)

> The crate under review decides the version gates below: `rust-version` in its `Cargo.toml` (else the `rust-toolchain.toml` channel; a `## Tech Stack` `Language:` line may carry a version, and the manifest wins when they differ) and the `tokio` / `tokio-util` versions in its `[dependencies]` (or the `[workspace.dependencies]` entries it inherits). A form that needs a newer toolchain or crate than that is written in its older equivalent. On another runtime (async-std, smol) the structural rules hold - every task owned, cancellation explicit, nothing blocking the executor - and the primitives map to that runtime's. Baseline: Rust 1.94+ (edition 2024), Tokio 1.4x, tokio-util 0.7 (`CancellationToken`, `TaskTracker`). Shared state, channels, `Send` / `Sync` and rayon belong to `rust-concurrency`; this skill owns task lifecycle, cancellation, timeouts and blocking work.

## When to Use

- Designing background tasks, fan-out, or shutdown for a Tokio service
- Reviewing async code for detached tasks, lost panics, cancellation hazards, or blocking calls
- Debugging hangs, stalled workers, or task-count growth

## Rules

- Every spawned task has an owner and a termination path: a held `JoinHandle`, a `JoinSet`, or a `TaskTracker` drained at shutdown. Dropping a `JoinHandle` detaches the task - it runs on, and its result and its panic reach no one
- A panic inside a task is caught by the runtime and surfaces only as a `JoinError` from its handle; the owner checks `is_panic()` and never discards it
- Every long-running task observes a `CancellationToken` (or its input channel closing) in the same `select!` as its work. Drop is not a shutdown mechanism - `Drop` cannot `.await`
- `select!` drops every losing branch each time it completes: a branch future inside a loop is cancel-safe, or is created once outside the loop and polled by `&mut`
- Never block a worker thread: no `std::thread::sleep`, blocking `std::fs` / `std::net`, `reqwest::blocking`, sync drivers, or CPU work longer than ~100 µs between `.await`s. Those go to `spawn_blocking`
- One runtime per process: `#[tokio::main]` in the binary; library code is `async fn` and never calls `Runtime::new()` or `block_on` (inside a runtime that panics)
- Every external call has a deadline (`tokio::time::timeout` or the client's own), and every fan-out has a bound (`Semaphore`, `buffer_unordered(n)`)
- A group that must all succeed fails as a unit: `try_join!` for a fixed set, `JoinSet` for N - the first error returns, and dropping the set aborts the rest

## Patterns

### Task with Cancellation

```rust
use std::time::Duration;
use tokio::{task::JoinHandle, time::{MissedTickBehavior, interval}};
use tokio_util::sync::CancellationToken;
use crate::jobs::sweep;

// Bad: no termination path - nothing cancels the sleep loop, and the handle is dropped
tokio::spawn(async { loop { tokio::time::sleep(Duration::from_secs(30)).await; sweep().await; } });

// Good: the owner keeps the handle; the tick and the cancellation share one select
pub fn spawn_sweeper(token: CancellationToken) -> JoinHandle<()> {
    tokio::spawn(async move {
        let mut tick = interval(Duration::from_secs(30)); // the first tick fires immediately
        tick.set_missed_tick_behavior(MissedTickBehavior::Delay); // no catch-up burst after a stall
        loop {
            tokio::select! {
                biased;                              // check cancellation first
                () = token.cancelled() => return,
                _ = tick.tick() => {
                    if token.run_until_cancelled(sweep()).await.is_none() { return; }
                }
            }
        }
    })
}
```

A branch's body is not raced: a long `sweep().await` written directly in the arm delays shutdown by its full length, which is why it runs under `run_until_cancelled` (tokio-util 0.7.13+; earlier, a nested `select!`). Anything spawned in a constructor takes a token or returns its handle, or every construction leaks a task. Nested tasks take `token.child_token()`, so one `cancel()` reaches all of them.

### Required Group

```rust
use tokio::task::JoinSet;

// Fixed set: concurrent on one task, no 'static bound; the first Err drops the other futures
let (users, orders) = tokio::try_join!(fetch_users(&client), fetch_orders(&client))?;

// N items: one task each
let mut set = JoinSet::new();
for id in ids { let c = client.clone(); set.spawn(async move { fetch_account(&c, id).await }); }
let mut accounts = Vec::with_capacity(set.len());
while let Some(joined) = set.join_next().await {
    match joined {
        Ok(Ok(a)) => accounts.push(a),
        Ok(Err(e)) => return Err(e.into()),                         // returning drops `set`: the rest abort
        Err(e) => return Err(anyhow::Error::new(e).context("fetch task")), // panicked or aborted
    }
}
```

`fetch_users`, `fetch_orders` and `fetch_account` are the project's. Abort stops a task at whichever `.await` it is parked on - a task mid-way through a non-idempotent sequence (write, then publish) stops between the two. Such a task checks the token at a safe point instead of being aborted.

### Mixed Required / Optional Fan-Out

```rust
use std::time::Duration;
use futures::future::join_all;
use tokio::time::timeout;

pub async fn notify_confirmed(&self, p: &Payment) -> Result<(), NotifyError> {
    let required = async {
        timeout(Duration::from_secs(5), self.email.send(&p.user_email, "Payment confirmed")).await
            .map_err(|_| NotifyError::Timeout)?
    };
    let optional = join_all(self.optional_senders(p).into_iter().map(|s| async move {
        match timeout(Duration::from_secs(5), s.send()).await {
            Ok(Ok(())) => {}
            Ok(Err(e)) => tracing::warn!(channel = s.name(), error = %e, "optional notification failed"),
            Err(_) => tracing::warn!(channel = s.name(), "optional notification timed out"),
        }
    }));
    let (required, _) = tokio::join!(required, optional); // both finish; neither cancels the other
    required
}
```

`Payment`, `NotifyError` and the senders are the project's. Each future sets its own timeout - one group-wide deadline forces a 2s cache read and a 10s external call to share a budget. A batch whose items are independent (settle 50k orders) is neither shape: collect per-item errors and keep going (aggregate shape in `rust-error-handling`), aborting only on an infrastructure-wide error - cancellation, or the same dependency failing for every item in a row.

### Bounded Fan-Out

```rust
use std::sync::Arc;
use tokio::{sync::Semaphore, task::JoinSet};

let permits = Arc::new(Semaphore::new(max_concurrency));
let mut set = JoinSet::new();
for item in items {
    let permit = permits.clone().acquire_owned().await?; // before spawn: at most n tasks exist
    set.spawn(async move { let _permit = permit; process(item).await });
}
while let Some(joined) = set.join_next().await { joined??; }
```

Acquiring inside the spawned task creates all N tasks at once. Without spawning, `futures::stream::iter(items).map(process).buffer_unordered(n)` bounds concurrency on the current task. A bound is not a rate: a provider quota (25 req/s) needs a shared limiter (`governor`) awaited before each call. Size the bound against shared resources too - n tasks each holding a database connection need `n + every other consumer of the pool <= max_connections`. Limits are per replica.

**Worker loop or bounded fan-out:** a known collection processed once -> bounded fan-out. An open-ended channel consumed by long-lived tasks -> N workers each looping on `recv()` with a cancellation arm (channel shape and backpressure: `rust-concurrency`).

### select! Cancellation Safety

| Branch future | Cancel-safe? | What a lost race costs |
|---------------|--------------|------------------------|
| `mpsc::Receiver::recv`, `broadcast::Receiver::recv`, `watch::Receiver::changed`, `CancellationToken::cancelled`, `Interval::tick`, `TcpListener::accept`, `AsyncReadExt::read` | Yes | nothing |
| `mpsc::Sender::send` | No | the unsent value is dropped - `reserve()` in the branch, then `permit.send(v)` |
| `Mutex::lock`, `Semaphore::acquire` | Yes | the queue position |
| `read_exact`, `read_to_end`, `AsyncBufReadExt::read_line`, `AsyncWriteExt::write_all` | No | bytes already read or written |
| an `async fn` or block with several `.await`s | Only if every step is | work done before the drop point is not undone |

```rust
// Bad: a fresh request each iteration - every tick drops the in-flight one and starts over
let res = loop {
    tokio::select! {
        r = client.get(&url).send() => break r?,
        _ = progress.tick() => report_progress(),
    }
};

// Good: create once, poll by reference until it completes
let mut req = std::pin::pin!(client.get(&url).send());
let res = loop {
    tokio::select! {
        r = &mut req => break r?,
        _ = progress.tick() => report_progress(),
    }
};
```

A `select!` with no matching branch left and no `else` panics; give a loop over channel results an `else => break` arm.

### Timeouts

```rust
match tokio::time::timeout(Duration::from_secs(5), fetch(&url)).await {
    Ok(Ok(body)) => Ok(body),
    Ok(Err(e)) => Err(e),                        // the call failed
    Err(_) => Err(FetchError::Timeout),          // deadline: the inner future was dropped mid-flight
}
```

`timeout` cancels by dropping, so its inner future carries the same hazard as a `select!` branch - a write cut off mid-way is an indeterminate outcome (classification: `rust-error-handling`). It fires only at an `.await`: a blocking call inside never times out. A nested deadline is shorter than the one enclosing it.

### Blocking Work

```rust
// Bad: ~100 ms of CPU on a worker thread - every task scheduled on it stalls
let hash = hash_password(&password)?;

// Good: off the runtime; `??` = JoinError, then the hash error
let hash = tokio::task::spawn_blocking(move || hash_password(&password)).await??;
```

For password hashing, compression, image work, large `serde_json` parses, and sync SDKs. The blocking pool caps at 512 threads by default (`max_blocking_threads`), so callers still bound concurrency upstream. A blocking task cannot be aborted once it starts, and runtime shutdown waits for it unless the runtime is shut down with `shutdown_timeout`. A loop that blocks for the life of the process gets `std::thread::spawn`, not a pool thread. `block_in_place` panics on a current-thread runtime, which is what `#[tokio::test]` builds by default. Dropping a `reqwest::blocking::Client` inside async code panics. Data parallelism across cores (rayon) is `rust-concurrency`.

### Graceful Shutdown of Background Tasks

```rust
use tokio_util::{sync::CancellationToken, task::TaskTracker};

let token = CancellationToken::new();
let tracker = TaskTracker::new();
tracker.spawn(run_sweeper(token.child_token()));
tracker.spawn(run_relay(token.child_token(), pool.clone()));

shutdown_signal().await;                  // signal handling: rust-web-patterns
token.cancel();
tracker.close();                          // wait() resolves only once closed and empty
if tokio::time::timeout(drain_budget, tracker.wait()).await.is_err() {
    tracing::error!(remaining = tracker.len(), "drain exceeded budget"); // report it, never a silent Ok
}
```

In-flight units finish inside `drain_budget` or stop at the next cancellation check; work that must survive persists progress per unit (a `processed_at` column) so the next run resumes. The deepest single path's timeouts sum to less than `drain_budget`, and `drain_budget` is under the platform's kill deadline (k8s `terminationGracePeriodSeconds`). `TaskTracker` frees each task as it ends and keeps no outputs - the fit for spawn-per-request work; `JoinSet` keeps every output until joined. The HTTP server's own drain is `rust-web-patterns`; a queue consumer's is `rust-messaging-patterns`.

## Task Leak Diagnosis (debugging)

- Export `Handle::current().metrics().num_alive_tasks()` as a gauge and alert on sustained growth; tokio-console (`console-subscriber`, built with `RUSTFLAGS="--cfg tokio_unstable"`) lists tasks by spawn location with busy / idle time and wake counts
- **Growth decides, signature explains.** Rank spawn locations by count growth across snapshots; only a growing location is the leak. A flat count is a steady state even when its signature looks suspicious - say so rather than reporting a second leak. A flat count can still be a `[Must]` on the source (an uncancellable loop) - report it as a defect, not as the leak
- Counts carry structure: N idle sweeper tasks means N owners (N constructors called), not one
- Await point -> cause:
  - idle on `Receiver::recv` = a `Sender` clone is still alive (held in a struct, captured by another task), so the channel never closes
  - idle on `Sender::send` = the consumer is gone or stalled and the channel is full (backpressure policy: `rust-concurrency`)
  - idle on `join_next` / a `JoinHandle` = a child never returns
  - idle in a `select!` = no branch can complete and the token is never cancelled
  - busy for long polls, few yields = blocking work on a worker thread; other tasks show scheduled-but-not-running time
- Each leaked task retains its future's captured state, so memory tracks task count and never recovers without a restart
- tokio-console and panic locations come from the deployed build; when they differ from the tree, match on function name and say which build the evidence is from. Working from metrics with no source: name the cause from the signature and mark the inferred clauses `(inferred)`

## Output Format

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design / implementation | `## Async Design` with `### Tasks`, `### Fan-Out`, `### Blocking Work`, then top-level `## Verification` |
| Review | `## Findings`, then `## Async Design` with the three subsections describing the code as it exists today, then `## Verification` |
| Debug (leak / hang / stall) | two opening lines `**Failing:**` and `**First fix:**`, then `## Task Diagnosis`, `## Findings`, `## Verification` - all three top-level |

```
## Async Design

### Tasks
| Task | Owner | Termination Path | Timeout |
|------|-------|------------------|---------|

### Fan-Out
| Operation | Required? | Failure Behavior | Bound | Timeout |
|-----------|-----------|------------------|-------|---------|

### Blocking Work
| Call | Placement | Why |
|------|-----------|-----|

## Task Diagnosis
| Task Signature | Count Trend | Root Cause | Fix |
|----------------|-------------|------------|-----|

## Verification
| Check | Where |
|-------|-------|
```

Cell values: `Owner` is the function or type that spawns the task and joins it (`Settler::settle_all`, `main`); a task the framework owns (a hyper connection, a consumer library's poll loop) gets one row naming the framework as `Owner`; a dropped handle is `none (detached)`. `Termination Path` is the exit the code actually gives the task (`token.cancelled()`, `channel closed`, `returns when done`, `aborted on JoinSet drop`, `none` when nothing ends it); the owner's join belongs in `Owner`. `Required?` is `Required | Optional`. `Failure Behavior` is `cancel siblings | record and continue | abort batch | none` - `none` when the code neither propagates nor records the failure. `Bound` is the concurrency cap (`Semaphore(8)`, `buffer_unordered(16)`) or `none`. `Placement` is `spawn_blocking | block_in_place | dedicated thread | inline async | inline blocking` - `inline blocking` is a blocking call on a worker thread and always carries a finding. `Task Signature` is the spawn location plus the await point it idles on; `Count Trend` is `Growing | Flat | unknown` - one row per signature in the evidence; code with no evidence row is a Finding, not a row. `Timeout` is a duration or `none`. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries. `Verification` rows are the checks that would catch this class of defect - a test asserting the task returns within a bound after `token.cancel()`, `#[tokio::test(start_paused = true)]` with `tokio::time::advance` for timer logic (Tokio `test-util` feature), `flavor = "multi_thread"` for code that must not stall its siblings, the alive-task gauge - each naming the test module or CI step that runs it. `**Failing:**` names the symptom and the signature that carries it (`alive tasks 1.2k -> 9.8k, idle on Sender::send in Broadcaster::publish`); `**First fix:**` names the one smallest edit that stops the growth - a second edit, even to the same type, is a Finding. `(inferred)` suffixes the clause it qualifies, not the whole cell. When the evidence disagrees with the source, the evidence wins and the `Defect:` line names the discrepancy. On a review every `## Async Design` cell describes the code as written and the intended value goes in the finding's `Fix`; on a design the cells are the design.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {what goes wrong, and under what conditions if it is currently latent}
- Rule: {the async rule violated}
- Fix: {concrete edit}
```

Owned findings: `[Must]` for a detached task whose failure matters, a lost panic, a leak, a hang, a lost or silently dropped result, a task that cannot be cancelled, a non-cancel-safe branch that loses data, blocking work on a worker thread in a request path, a fan-out whose size the input sets with no bound, or a nested runtime; `[Recommend]` otherwise. A defect that is currently masked (by a caller that happens to serialize, by low traffic) is still `[Must]` - say what unmasks it. Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not; a range is `file:start-end`. Order owned findings `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites is one heading citing the first site, with the rest named on the `Defect:` line. A defect this skill does not own (a lock held across `.await`, a swallowed error, a transaction held open, an authorization gap) is still reported, never dropped: one block per such defect after every owned finding, in that same order among themselves, labelled `[Must]` when it risks incorrect behaviour, data loss or a security hole and `[Recommend]` otherwise, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- `tokio::spawn` with the handle dropped
- `tokio::time::sleep` loops with no cancellation branch
- Re-creating a non-cancel-safe future on every `select!` iteration
- `Runtime::new().block_on(...)` or `Handle::block_on` inside async code
- One group for required and optional work, where the first optional failure aborts the required
- `unsafe impl Send` to get a future past `tokio::spawn` (the real fix is in `rust-concurrency`)
