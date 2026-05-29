---
name: rust-async-patterns
description: "Rust/Tokio async review: runtime, JoinSet, select! cancel-safety, CancellationToken, spawn_blocking, blocking-in-async, Send bounds."
metadata:
  category: backend
  tags: [rust, tokio, async, concurrency, futures]
user-invocable: false
---

# Rust Async Patterns

> Load `Use skill: stack-detect` first to determine the project stack. Defer shared-state primitives (Arc/Mutex/RwLock, Send+Sync, channels) to `rust-concurrency`; defer worker pools, Kafka/AMQP, and outbox to `rust-messaging-patterns`.

## When to Use

- Designing or reviewing Tokio-based async services
- Diagnosing hangs, deadlocks, missed cancellations, leaked tasks, `future is not Send` errors
- Choosing between `tokio::spawn`, `JoinSet`, sequential `.await`, and `spawn_blocking`

For non-Tokio runtimes (async-std, smol), keep the structural rules (no sync blocking, structured concurrency, explicit cancellation) and map to equivalent primitives.

## Rules

- One runtime per process. `#[tokio::main]` in the binary; libraries take an async context and never call `Runtime::new()` or `block_on` from inside async.
- Never block the runtime: no `std::fs`/`std::thread::sleep`/blocking drivers/long CPU loops. Use async I/O (`tokio::fs`, `tokio::io`, async drivers) or wrap in `tokio::task::spawn_blocking`.
- Every spawned task is owned: hold the `JoinHandle` or use `JoinSet`, and handle `JoinError` (distinguish panic vs. cancellation). No fire-and-forget.
- Shutdown is explicit: propagate a `CancellationToken` to every long-running task. Drop is not a shutdown mechanism.
- `select!` branches must be cancel-safe. Pin futures across iterations with `tokio::pin!`, or use cancel-safe primitives (`mpsc::Receiver::recv`, `Notified::notified`, `CancellationToken::cancelled`, `timeout` as the outer future).
- Bound everything: bounded `tokio::sync::mpsc`, `timeout` on external calls, capacity caps on fan-out. No `std::sync::mpsc` or unbounded channels in async.
- No `std::sync::MutexGuard`, `Rc`, or `RefCell` held across `.await` (deadlocks the runtime, makes the future `!Send`). For shared state across `.await` see `rust-concurrency`.

## Patterns

### Runtime Setup

```rust
#[tokio::main]
async fn main() -> anyhow::Result<()> { serve(build_app().await?).await }

// Library: take an async context; never construct a Runtime or call block_on from inside async.
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

`JoinSet` aborts remaining tasks on drop. For graceful shutdown call `set.abort_all()` then drain `join_next()` so you log every panic/cancel instead of swallowing them.

### Cancellation with CancellationToken

```rust
use tokio_util::sync::CancellationToken;

async fn worker(token: CancellationToken, mut rx: mpsc::Receiver<Job>) {
    loop {
        tokio::select! {
            _ = token.cancelled() => return,             // graceful exit
            Some(job) = rx.recv() => process(job).await, // recv is cancel-safe
            else => return,                              // channel closed
        }
    }
}
```

Pass `token.child_token()` into nested tasks so one `cancel()` propagates.

### Timeouts: prefer `timeout` over `select! + sleep`

```rust
let body = tokio::time::timeout(Duration::from_secs(5), reqwest::get(url))
    .await
    .map_err(|_| AppError::Timeout)??     // outer: elapsed, inner: reqwest
    .text().await?;
```

Use `select!` only when racing meaningful branches (shutdown + work, primary + fallback).

### select! Cancellation Safety

```rust
// Bad: reqwest::get is not cancel-safe. On every loop iteration the in-flight
// request is dropped, leaking connection state.
loop {
    tokio::select! {
        r = self.client.get(&url).send() => break r?,
        _ = sleep(Duration::from_secs(1)) => continue,
    }
}

// Good: pin once, reuse across iterations.
let fut = self.client.get(&url).send();
tokio::pin!(fut);
tokio::select! {
    r = &mut fut => r?,
    _ = sleep(Duration::from_secs(5)) => return Err(Timeout),
}
```

A future is cancel-safe iff dropping it mid-poll leaves no observable side effect and resuming would restart cleanly. When unsure, wrap with `timeout` (single drop point) instead of `select!`.

### spawn_blocking for CPU or Sync I/O

```rust
let hash = tokio::task::spawn_blocking(move || bcrypt::hash(pw, COST))
    .await                                  // JoinError
    .map_err(AppError::join)??;             // inner Result
```

Use for: bcrypt/argon2, image/zip, `rusqlite`, large `serde_json` parses, any third-party sync API. Do not use for I/O with an async variant (`tokio::fs`, `reqwest`). The blocking pool is finite (default 512) -- still bound concurrency upstream.

## Output Format

When reviewing async code, emit one block per finding:

```
- Location: <file>:<line> (<function>)
  Issue: {Blocking-In-Async | Unowned-Task | Cancellation-Unsafe | Lock-Across-Await | Nested-Runtime | Unbounded-Backpressure | Missing-Timeout | Shutdown-Gap | Send-Bound}
  Severity: {Blocker | High | Medium | Low}
  Evidence: <quoted snippet or symbol>
  Fix: <one-line action; reference Pattern name>
  Defer-To: {rust-concurrency | rust-messaging-patterns | None}
```

Severity guide:
- **Blocker**: runtime panic, deadlock, money/data loss on cancel, dropped events.
- **High**: stalls under load, swallowed task panics, leaks under backpressure.
- **Medium**: missing timeout/shutdown wiring; non-cancel-safe `select!` arm with no observed impact.
- **Low**: stylistic (use `timeout` over `select! + sleep`).

## Avoid

- Nesting runtimes (`Runtime::new().block_on(...)` inside async) -- panics or starves the executor.
- `select!` arms whose futures are not cancel-safe and may be re-polled -- pin and reuse, or restructure with `timeout`.
- Ignoring `JoinError` -- log task identity and distinguish panic vs. cancellation.
- `unsafe impl Send`/`Sync` to silence the compiler instead of fixing the type.
