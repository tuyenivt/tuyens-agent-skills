---
name: rust-async-patterns
description: "Tokio async patterns for Rust: runtime setup, task spawning with JoinSet, cancellation safety, select!, spawn_blocking for CPU work, and common async pitfalls."
metadata:
  category: backend
  tags: [rust, tokio, async, concurrency, futures]
user-invocable: false
---

# Rust Async Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing async services with Tokio
- Reviewing async code for cancellation safety and blocking issues
- Debugging hangs, deadlocks, or task panics
- Choosing between `tokio::spawn`, `JoinSet`, and sequential execution

If the project does not use Tokio (e.g., uses async-std or smol), adapt the patterns to the equivalent primitives but preserve the same structural rules (no blocking on runtime, structured concurrency, cancellation tokens).

## Rules

- Never block the Tokio runtime with synchronous I/O - use `tokio::task::spawn_blocking` for CPU-heavy or blocking operations
- Every spawned task must have an owner that handles its `JoinHandle`
- Never hold a `std::sync::MutexGuard` across an `.await` point - use `tokio::sync::Mutex` if the lock must span awaits
- Use structured concurrency (`JoinSet`, `tokio::select!`) over fire-and-forget spawns
- Pass `CancellationToken` for graceful shutdown - don't rely on dropping tasks
- Prefer `tokio::sync::mpsc` over `std::sync::mpsc` in async code

## Patterns

### Tokio Runtime Setup

```rust
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Single entry point - never nest runtimes
    let app = build_app().await?;
    serve(app).await
}

// For libraries, never create a runtime - accept async context from caller
```

### Task Spawning with JoinSet

```rust
use tokio::task::JoinSet;

async fn fetch_all(urls: Vec<String>) -> Vec<Result<String, reqwest::Error>> {
    let mut set = JoinSet::new();

    for url in urls {
        set.spawn(async move {
            reqwest::get(&url).await?.text().await
        });
    }

    let mut results = Vec::new();
    while let Some(result) = set.join_next().await {
        match result {
            Ok(inner) => results.push(inner),
            Err(e) => tracing::error!("task panicked: {e}"),
        }
    }
    results
}
```

### Graceful Shutdown with CancellationToken

```rust
use tokio_util::sync::CancellationToken;

async fn run_worker(token: CancellationToken, mut rx: mpsc::Receiver<Job>) {
    loop {
        tokio::select! {
            _ = token.cancelled() => {
                tracing::info!("worker shutting down");
                return;
            }
            Some(job) = rx.recv() => {
                process(job).await;
            }
        }
    }
}

// In main:
let token = CancellationToken::new();
let worker_token = token.clone();
let handle = tokio::spawn(run_worker(worker_token, rx));

// On SIGTERM:
token.cancel();
handle.await?;
```

### select! for Concurrent Operations

```rust
use tokio::time::{timeout, Duration};

async fn fetch_with_timeout(url: &str) -> Result<String, AppError> {
    tokio::select! {
        result = reqwest::get(url) => {
            let resp = result.map_err(AppError::Http)?;
            resp.text().await.map_err(AppError::Http)
        }
        _ = tokio::time::sleep(Duration::from_secs(5)) => {
            Err(AppError::Timeout)
        }
    }
}
```

### spawn_blocking for CPU-Heavy Work

```rust
async fn hash_password(password: String) -> Result<String, AppError> {
    tokio::task::spawn_blocking(move || {
        bcrypt::hash(password, bcrypt::DEFAULT_COST)
            .map_err(|e| AppError::Internal(e.into()))
    })
    .await
    .map_err(|e| AppError::Internal(e.into()))?
}
```

### Cancellation Safety

```rust
// Bad: not cancellation-safe - partial work lost if cancelled between awaits
async fn transfer(from: &Account, to: &Account, amount: f64) {
    from.debit(amount).await;   // if cancelled here...
    to.credit(amount).await;    // ...this never runs, money is lost
}

// Good: use a transaction or make operations idempotent
async fn transfer(pool: &PgPool, from_id: i64, to_id: i64, amount: f64) -> Result<()> {
    let mut tx = pool.begin().await?;
    sqlx::query!("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, from_id)
        .execute(&mut *tx).await?;
    sqlx::query!("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amount, to_id)
        .execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(())
}
```

## Anti-Patterns

```rust
// Bad: blocking the runtime (sync I/O on async thread)
async fn read_file() -> String {
    std::fs::read_to_string("file.txt").unwrap() // blocks the executor
}

// Bad: holding std Mutex across .await
let guard = std_mutex.lock().unwrap();
some_async_op().await; // deadlock risk - other tasks can't acquire the lock
drop(guard);

// Bad: nested runtime
#[tokio::main]
async fn main() {
    let rt = tokio::runtime::Runtime::new().unwrap(); // panic: cannot nest runtimes
    rt.block_on(async { ... });
}

// Bad: fire-and-forget spawn (no error handling, no cancellation)
tokio::spawn(async { do_work().await });

// Bad: unbounded channel (memory leak under backpressure)
let (tx, rx) = tokio::sync::mpsc::unbounded_channel();
```

## Avoid

- Blocking I/O or CPU-heavy work on the Tokio runtime - use `spawn_blocking`
- Holding `std::sync::Mutex` across `.await` points
- Nesting Tokio runtimes
- Fire-and-forget `tokio::spawn` without `JoinHandle` or `JoinSet`
- `std::sync::mpsc` in async code - use `tokio::sync::mpsc`
- Unbounded channels without backpressure strategy
- Ignoring `JoinError` (task panics are silently lost)
