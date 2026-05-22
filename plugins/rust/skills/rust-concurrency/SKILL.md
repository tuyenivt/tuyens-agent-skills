---
name: rust-concurrency
description: "Rust concurrency: Arc/Mutex/RwLock, mpsc/oneshot/broadcast channels, atomics, Send+Sync, deadlock prevention, lock-free shared state."
metadata:
  category: backend
  tags: [rust, concurrency, mutex, channels, atomics, send-sync]
user-invocable: false
---

# Rust Concurrency

> Load `Use skill: stack-detect` first to determine the project stack. For runtime-level concerns (spawn, select!, cancellation) use `rust-async-patterns`; this skill covers shared-state primitives.

## When to Use

- Choosing between Mutex, RwLock, atomics, channels, or lock-free structures
- Reviewing shared state for data races, deadlocks, or Send/Sync errors
- Fan-out/fan-in messaging (mpsc, broadcast, oneshot)
- Designing read-heavy or hot-path state with minimal contention

## Rules

- Use `tokio::sync::*` when the guard or send can cross `.await`; otherwise `std::sync::*` is faster and fine.
- `Arc<T>` for shared ownership across tasks; `Rc`/`RefCell` are single-thread only.
- Lock the smallest data the smallest time: copy/clone out, drop the guard, then compute.
- Acquire multiple locks in a single global order; never hold lock A while awaiting lock B without that order.
- Pick channel by topology: `oneshot` (1:1 reply), `mpsc` (many producers, one consumer), `broadcast` (one producer, many consumers, each gets every message), `watch` (single latest value).
- Bound every channel; unbounded variants only with an explicit upstream backpressure source.
- Atomics for counters/flags only; reach for `Mutex`/`RwLock` once invariants span multiple fields.

## Patterns

### Primitive selection

| Need                                  | Use                                |
| ------------------------------------- | ---------------------------------- |
| Shared mutable state, mixed R/W       | `Arc<Mutex<T>>` (tokio if `.await`)|
| Read-heavy, infrequent writes         | `Arc<RwLock<T>>` or `ArcSwap<T>`   |
| Single counter / flag                 | `AtomicU64` / `AtomicBool`         |
| Latest-value broadcast (config, ticks)| `tokio::sync::watch`               |
| Pub/sub to N subscribers              | `tokio::sync::broadcast`           |
| Pipeline / work queue                 | `tokio::sync::mpsc` (bounded)      |
| Request/reply                         | `oneshot`                          |
| Concurrent map without manual locks   | `dashmap::DashMap`                 |

### Lock scope: extract, drop, compute

```rust
// Bad: lock held across await and across heavy work
let mut cache = state.cache.lock().await;
let result = expensive(&*cache).await; // every other task blocked
cache.insert(key, result);

// Good: clone out, drop guard, compute, re-lock briefly
let input = state.cache.lock().await.get(&key).cloned();
let result = expensive(&input).await;
state.cache.lock().await.insert(key, result);
```

### RwLock for read-heavy state

```rust
// Use when reads >> writes and the protected value is non-trivial to clone.
// For "read latest snapshot" prefer watch / ArcSwap (no read lock at all).
pub struct ConfigStore { inner: Arc<RwLock<Config>> }

impl ConfigStore {
    pub async fn snapshot(&self) -> Config { self.inner.read().await.clone() }
    pub async fn replace(&self, c: Config) { *self.inner.write().await = c; }
}
```

### Channels: mpsc / oneshot / broadcast

```rust
// mpsc: bounded pipeline, drop on full = backpressure
let (tx, mut rx) = tokio::sync::mpsc::channel::<Job>(100);

// oneshot: actor reply
struct Cmd { data: String, reply: tokio::sync::oneshot::Sender<Result<String, AppError>> }

// broadcast: each subscriber sees every message; slow subscribers get RecvError::Lagged
let (btx, _) = tokio::sync::broadcast::channel::<Event>(256);
let mut sub = btx.subscribe();
tokio::spawn(async move {
    loop {
        match sub.recv().await {
            Ok(ev) => handle(ev).await,
            Err(tokio::sync::broadcast::error::RecvError::Lagged(n)) => {
                tracing::warn!(skipped = n, "subscriber lagged");
            }
            Err(_) => break, // sender dropped
        }
    }
});
```

### Atomics: ordering choice

```rust
use std::sync::atomic::{AtomicU64, AtomicBool, Ordering};

// Relaxed: independent counters/metrics
metrics.requests.fetch_add(1, Ordering::Relaxed);

// Acquire/Release: flag publishes data written before it
data.write(payload);
ready.store(true, Ordering::Release);
// reader side
if ready.load(Ordering::Acquire) { read(data); }

// SeqCst: only when total order across multiple atomics matters
```

### Lock-free read path with ArcSwap

```rust
// Read-mostly config without a read lock on the hot path.
use arc_swap::ArcSwap;
static CONFIG: ArcSwap<Config> = ArcSwap::from_pointee(Config::default());

fn current() -> Arc<Config> { CONFIG.load_full() } // wait-free
fn reload(new: Config) { CONFIG.store(Arc::new(new)); }
```

### Deadlock prevention: global lock order

```rust
// Bad: tasks acquire (a, b) and (b, a) -> cycle
async fn t1(a: &Mutex<A>, b: &Mutex<B>) { let _a = a.lock().await; let _b = b.lock().await; }
async fn t2(a: &Mutex<A>, b: &Mutex<B>) { let _b = b.lock().await; let _a = a.lock().await; }

// Good: every site locks in the same order (e.g., by address or by name)
async fn with_pair(a: &Mutex<A>, b: &Mutex<B>) {
    let (first, second) = if (a as *const _) < (b as *const _) { (a, b) } else { (b, a) };
    let _g1 = first.lock().await;
    let _g2 = second.lock().await;
}
```

### Send + Sync error triage

```rust
// "future is not Send" -> something non-Send is held across .await.
// Fix by either dropping it before the await, or swapping the type:
//   Rc<T>          -> Arc<T>
//   RefCell<T>     -> Mutex<T> / RwLock<T>
//   *const T       -> wrap in a Send newtype only if you can prove the invariant
{
    let guard = std_mutex.lock().unwrap();
    let v = guard.clone();
    drop(guard);                 // released before await
    remote_call(v).await;
}
```

## Output Format

When reviewing shared-state code, emit:

```
Primitive: {Mutex | RwLock | Atomic | mpsc | oneshot | broadcast | watch | ArcSwap | DashMap}
Async-Safe: {Yes | No | N/A}   # tokio::sync vs std::sync vs lock-free
Issue: {DataRace | Deadlock | LockAcrossAwait | SendSyncViolation | UnboundedChannel | OverbroadCriticalSection | WrongOrdering | None}
Severity: {Blocker | High | Medium | Low}
Location: <file:line or symbol>
Evidence: <one-line quote or trace>
Fix: <one-line action; reference Pattern name>
```

One block per finding. Omit no field; use `None` / `N/A` when not applicable.

## Avoid

- `std::sync::Mutex`/`RwLock` guards crossing `.await`
- Locking around await-ing work; lock around state mutation only
- `Rc`/`RefCell` in any code reachable from `tokio::spawn` or a thread
- Unbounded channels without an upstream rate limit
- `Ordering::SeqCst` by default; choose Relaxed/Acquire/Release deliberately
- Multiple-lock sites without a documented global order
- `unsafe impl Send`/`Sync` to silence the compiler instead of fixing the type
