---
name: rust-concurrency
description: "Rust concurrency primitives: Arc/Mutex, RwLock, channels (mpsc/oneshot), Send+Sync traits, rayon for CPU-bound parallelism, atomics, and deadlock prevention."
metadata:
  category: backend
  tags: [rust, concurrency, mutex, channels, rayon, send-sync]
user-invocable: false
---

# Rust Concurrency

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing shared state patterns for concurrent access
- Reviewing code for data races, deadlocks, or Send+Sync violations
- Choosing between Mutex, RwLock, channels, and atomics
- Implementing CPU-bound parallelism with rayon

## Rules

- The compiler enforces thread safety via `Send` and `Sync` - trust the borrow checker
- Use `Arc<Mutex<T>>` for shared mutable state across tasks - never raw pointers
- Prefer `tokio::sync::Mutex` over `std::sync::Mutex` when the lock spans `.await` points
- Use channels for ownership transfer between tasks - not shared state
- Use `rayon` for CPU-bound data parallelism - not Tokio (Tokio is for I/O concurrency)
- Minimize critical section size - lock, mutate, unlock immediately

## Patterns

### Arc<Mutex<T>> for Shared State

```rust
use std::sync::Arc;
use tokio::sync::Mutex;

#[derive(Clone)]
struct AppState {
    cache: Arc<Mutex<HashMap<String, String>>>,
}

async fn get_cached(state: &AppState, key: &str) -> Option<String> {
    let cache = state.cache.lock().await;
    cache.get(key).cloned()
}

async fn set_cached(state: &AppState, key: String, value: String) {
    let mut cache = state.cache.lock().await;
    cache.insert(key, value);
}
```

### RwLock for Read-Heavy Workloads

```rust
use tokio::sync::RwLock;

struct ConfigStore {
    config: Arc<RwLock<Config>>,
}

impl ConfigStore {
    async fn get(&self) -> Config {
        self.config.read().await.clone() // many readers, no blocking
    }

    async fn update(&self, new_config: Config) {
        let mut config = self.config.write().await; // exclusive access
        *config = new_config;
    }
}
```

### Channels for Ownership Transfer

```rust
use tokio::sync::mpsc;

async fn run_pipeline(pool: PgPool) -> anyhow::Result<()> {
    let (tx, mut rx) = mpsc::channel::<Job>(100); // bounded channel

    // Producer
    let producer = tokio::spawn(async move {
        for job in fetch_jobs().await {
            tx.send(job).await.unwrap();
        }
        // tx is dropped here, signaling completion
    });

    // Consumer
    while let Some(job) = rx.recv().await {
        process(job).await?;
    }

    producer.await?;
    Ok(())
}
```

### oneshot for Request-Response

```rust
use tokio::sync::oneshot;

struct Command {
    data: String,
    reply: oneshot::Sender<Result<String, AppError>>,
}

async fn actor(mut rx: mpsc::Receiver<Command>) {
    while let Some(cmd) = rx.recv().await {
        let result = handle_command(&cmd.data).await;
        let _ = cmd.reply.send(result);
    }
}
```

### Atomics for Simple Counters

```rust
use std::sync::atomic::{AtomicU64, Ordering};

struct Metrics {
    request_count: AtomicU64,
}

impl Metrics {
    fn increment_requests(&self) {
        self.request_count.fetch_add(1, Ordering::Relaxed);
    }

    fn get_request_count(&self) -> u64 {
        self.request_count.load(Ordering::Relaxed)
    }
}
```

### rayon for CPU-Bound Parallelism

```rust
use rayon::prelude::*;

// Use spawn_blocking to run rayon on Tokio
async fn process_batch(items: Vec<Item>) -> Vec<Result<Output, AppError>> {
    tokio::task::spawn_blocking(move || {
        items.par_iter()
            .map(|item| transform(item))
            .collect()
    })
    .await
    .unwrap()
}
```

### Send + Sync Constraints

```rust
// Send: safe to transfer ownership between threads
// Sync: safe to share references between threads (&T is Send)

// Arc<T> is Send + Sync when T is Send + Sync
// Mutex<T> is Send + Sync when T is Send
// Rc<T> is NOT Send - use Arc instead
// RefCell<T> is NOT Sync - use Mutex instead

// Common fix for "not Send" errors:
// Replace Rc with Arc
// Replace RefCell with Mutex or RwLock
// Use Arc<Mutex<T>> for shared mutable state across tasks
```

## Anti-Patterns

```rust
// Bad: std::sync::Mutex across .await (can deadlock)
let guard = std_mutex.lock().unwrap();
some_async_op().await; // other tasks can't acquire the lock
drop(guard);

// Bad: holding lock longer than necessary
let mut data = state.cache.lock().await;
let result = expensive_computation(&data).await; // lock held during computation
data.insert(key, result);

// Good: lock, clone/extract, unlock, then compute
let input = {
    let data = state.cache.lock().await;
    data.get(key).cloned()
};
let result = expensive_computation(&input).await;
state.cache.lock().await.insert(key, result);

// Bad: Rc in async code (not Send)
let shared = Rc::new(RefCell::new(vec![]));
tokio::spawn(async move { shared.borrow_mut().push(1) }); // compile error: Rc is not Send

// Bad: unbounded channel (memory leak under backpressure)
let (tx, rx) = mpsc::unbounded_channel();
```

## Avoid

- `std::sync::Mutex` across `.await` points - use `tokio::sync::Mutex`
- Holding locks longer than necessary - minimize critical sections
- `Rc`/`RefCell` in async or multi-threaded code - use `Arc`/`Mutex`
- Unbounded channels without backpressure strategy
- Using Tokio for CPU-bound work - use `rayon` via `spawn_blocking`
- Ignoring `Send + Sync` compiler errors by using `unsafe` - fix the data type instead
