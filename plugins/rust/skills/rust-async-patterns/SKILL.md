---
name: rust-async-patterns
description: "Review Rust/Tokio async code: runtime, JoinSet, select! cancel-safety, CancellationToken, spawn_blocking, Send bounds, blocking-in-async pitfalls."
metadata:
  category: backend
  tags: [rust, tokio, async, concurrency, futures]
user-invocable: false
---

# Rust Async Patterns

> Load `Use skill: stack-detect` first to determine the project stack. For shared-state primitives (Arc/Mutex/RwLock, Send+Sync, channels) defer to `rust-concurrency`. For worker pools, Kafka/AMQP consumers, and outbox patterns defer to `rust-messaging-patterns`.

## When to Use

- Designing or reviewing Tokio-based async services
- Diagnosing hangs, deadlocks, missed cancellations, dropped tasks, "future is not Send" errors
- Choosing between `tokio::spawn`, `JoinSet`, sequential `.await`, and `spawn_blocking`

For non-Tokio runtimes (async-std, smol), preserve the structural rules (no sync blocking, structured concurrency, explicit cancellation) and map to equivalent primitives.

## Rules

- One runtime per process. `#[tokio::main]` in the binary; libraries accept an async context, never create a runtime.
- No sync blocking on the runtime. Use `tokio::fs`/`tokio::io` for async I/O; wrap CPU-heavy or unavoidable blocking calls in `tokio::task::spawn_blocking`.
- Every spawned task is owned. Hold the `JoinHandle` (or use `JoinSet`) and handle `JoinError`. No fire-and-forget.
- Shutdown is explicit. Propagate a `CancellationToken` to every long-running task; drop is not a shutdown mechanism.
- `select!` branches must be cancel-safe. If a future may be dropped mid-poll, prefer pulling it out with `tokio::pin!` or use `Notified`/`mpsc::Receiver::recv` style cancel-safe futures.
- Bound everything. Bounded channels, `timeout`s on external calls, `JoinSet` capacity caps for concurrent fan-out.

## Patterns

### Runtime Setup

```rust
// Binary - single entry point.
#[tokio::main]
async fn main() -> anyhow::Result<()> { serve(build_app().await?).await }

// Library - accept async context, never call Runtime::new() or block_on inside async.
pub async fn run(cfg: Config) -> anyhow::Result<()> { /* ... */ }
```

### Structured Fan-Out with JoinSet

```rust
use tokio::task::JoinSet;

async fn fetch_all(urls: Vec<String>) -> Vec<Result<String, reqwest::Error>> {
    let mut set = JoinSet::new();
    for url in urls { set.spawn(async move { reqwest::get(&url).await?.text().await }); }
    let mut out = Vec::new();
    while let Some(joined) = set.join_next().await {
        match joined {
            Ok(inner) => out.push(inner),
            Err(e) if e.is_panic() => tracing::error!("task panicked: {e}"),
            Err(e) => tracing::error!("task cancelled: {e}"),
        }
    }
    out
}
```

`JoinSet` aborts remaining tasks on drop -- pair with `set.abort_all()` plus `join_next()` drain on shutdown to log outcomes.

### Cancellation with CancellationToken

```rust
use tokio_util::sync::CancellationToken;

async fn worker(token: CancellationToken, mut rx: mpsc::Receiver<Job>) {
    loop {
        tokio::select! {
            _ = token.cancelled() => return,            // graceful exit
            Some(job) = rx.recv() => process(job).await, // recv is cancel-safe
            else => return,                              // channel closed
        }
    }
}
```

Pass child tokens (`token.child_token()`) into nested tasks so a single `cancel()` propagates.

### Timeout via select! or tokio::time::timeout

```rust
// Prefer timeout() -- it wraps the future once and is cancel-safe.
let body = tokio::time::timeout(Duration::from_secs(5), reqwest::get(url))
    .await
    .map_err(|_| AppError::Timeout)??
    .text().await?;
```

Reach for `select!` only when racing multiple meaningful branches (shutdown + work). For "do X with a deadline", `timeout` is clearer.

### select! Cancellation Safety

```rust
// Bad - reqwest::get is not cancel-safe; if the timeout fires mid-request,
// the connection state and any partial write are dropped silently.
tokio::select! {
    r = reqwest::get(&url) => r?,
    _ = sleep(Duration::from_secs(5)) => return Err(Timeout),
}

// Good - pin the future once, then poll it across iterations or wrap with timeout().
let fut = reqwest::get(&url);
tokio::pin!(fut);
tokio::select! {
    r = &mut fut => r?,
    _ = sleep(Duration::from_secs(5)) => return Err(Timeout),
}
```

Cancel-safe building blocks: `mpsc::Receiver::recv`, `Notified::notified`, `CancellationToken::cancelled`, `tokio::time::sleep` (when pinned), `tokio::time::timeout` outer future.

### spawn_blocking for CPU or Sync I/O

```rust
let hash = tokio::task::spawn_blocking(move || bcrypt::hash(pw, COST))
    .await
    .map_err(AppError::join)??;
```

Use for: bcrypt/argon2, image/zip processing, `rusqlite`, large `serde_json` parses, any third-party sync API. Do not use for I/O that has an async variant (`tokio::fs`, `reqwest`).

### Send Bounds on Spawned Futures

```rust
// Bad - holding a non-Send type (e.g. Rc, RefCell, raw pointer, MutexGuard from
// std::sync::Mutex) across .await makes the future !Send and breaks tokio::spawn.
tokio::spawn(async move {
    let g = rc_cell.borrow_mut();         // !Send guard
    other.await;                          // future is now !Send
});

// Good - scope the !Send borrow, drop it before the await.
tokio::spawn(async move {
    { let g = rc_cell.borrow_mut(); mutate(&mut g); } // dropped here
    other.await;
});
```

For shared mutable state across tasks, switch to `Arc<tokio::sync::Mutex<_>>` (see `rust-concurrency`).

## Output Format

When reviewing async code, emit findings as:

```
- Location: <file>:<line> (<function>)
  Issue: {Blocking-In-Async | Unowned-Task | Cancellation-Unsafe | Send-Bound | Lock-Across-Await | Nested-Runtime | Unbounded-Backpressure | Missing-Timeout | Shutdown-Gap}
  Severity: {Critical | High | Medium | Low}
  Evidence: <quoted snippet or symbol>
  Fix: <one-line action -- e.g. "wrap in spawn_blocking", "replace std::sync::Mutex with tokio::sync::Mutex", "pin the future across select! iterations">
  Defer-To: <rust-concurrency | rust-messaging-patterns | none>
```

Severity guide:
- **Critical**: runtime panic, deadlock, money/data loss on cancel, dropped events.
- **High**: stalls under load, lost task panics, leaks under backpressure.
- **Medium**: missing timeout/shutdown wiring, non-cancel-safe `select!` arm without observable impact yet.
- **Low**: stylistic (use `timeout` over `select! + sleep`).

## Avoid

- Sync blocking on the runtime (`std::fs`, `std::thread::sleep`, blocking DB drivers, long CPU loops) -- use `tokio::fs`, `tokio::time::sleep`, async drivers, or `spawn_blocking`.
- Holding `std::sync::MutexGuard`, `Rc`, or `RefCell` across `.await` -- deadlocks the runtime and makes the future `!Send`.
- Nesting runtimes (`Runtime::new().block_on(...)` inside async) -- panics or starves the executor.
- Fire-and-forget `tokio::spawn` -- panics are silently dropped; use `JoinSet` or hold the `JoinHandle`.
- `std::sync::mpsc` or unbounded channels in async code -- use bounded `tokio::sync::mpsc`.
- `select!` arms whose futures are not cancel-safe and may be re-polled across iterations -- pin and reuse the future, or restructure.
- Relying on `Drop` for shutdown -- propagate `CancellationToken` and `await` clean exit.
- Ignoring `JoinError` -- distinguish panic vs. cancellation; log with task identity.
