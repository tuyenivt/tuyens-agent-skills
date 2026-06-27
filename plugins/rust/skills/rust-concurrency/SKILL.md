---
name: rust-concurrency
description: "Rust shared state: Arc, std/tokio Mutex/RwLock, mpsc/oneshot/broadcast/watch, atomics, ArcSwap, DashMap, rayon, Send+Sync, deadlocks."
metadata:
  category: backend
  tags: [rust, concurrency, mutex, channels, atomics, send-sync, rayon]
user-invocable: false
---

# Rust Concurrency

> Load `Use skill: stack-detect` first. For runtime, `tokio::spawn`, `select!`, cancellation, `spawn_blocking` use `rust-async-patterns`; this skill owns shared-state primitives and `Send`/`Sync`.

## When to Use

- Choosing between Mutex, RwLock, atomics, channels, `ArcSwap`, `DashMap`, or rayon
- Reviewing shared state for data races, deadlocks, lock-across-await, or `Send`/`Sync` errors
- Sizing/typing channels (mpsc/oneshot/broadcast/watch; std vs tokio)
- Designing read-heavy or hot-path state with minimal contention

## Rules

- Use `tokio::sync::*` iff the guard or sender crosses `.await`; otherwise `std::sync::*` (faster, no poisoning panic on contention).
- `Arc<T>` for cross-task sharing. `Rc`/`RefCell` are single-thread only and are `!Send`.
- Lock the smallest data the shortest time: clone/copy out, drop the guard, then compute or await.
- Multiple locks: define one global order (named, documented) and acquire in that order at every site.
- Channel by topology: `oneshot` (1:1 reply), `mpsc` (N:1 pipeline), `broadcast` (1:N fanout, each msg to all), `watch` (latest value only). Always bounded; unbounded only with a documented upstream rate limit. Size for in-flight work, not throughput: `mpsc` capacity = roughly consumer parallelism x per-item in-flight depth (small, e.g. 2-4x worker count) so `.send().await` backpressures early; `broadcast` capacity = the worst lag a slow subscriber may fall behind before it is allowed to skip.
- Atomics for single counters/flags; switch to `Mutex`/`RwLock` once invariants span fields.
- Never call rayon (`par_iter`, `join`, `scope`) directly inside an async fn -- it blocks the worker. Wrap in `spawn_blocking` or hop via `rayon::spawn` + `oneshot`.
- Handle `PoisonError` (or use `parking_lot::Mutex` which can't poison); `.unwrap()` on a poisoned guard panics the request task.

## Patterns

### Primitive selection

| Need                                    | Use                                |
| --------------------------------------- | ---------------------------------- |
| Shared mutable state, mixed R/W         | `Arc<Mutex<T>>` (tokio if `.await`)|
| Read-heavy, infrequent writes, snapshot | `arc_swap::ArcSwap<T>` or `watch`  |
| Read-heavy, mutate in place             | `Arc<RwLock<T>>`                   |
| Single counter / flag                   | `AtomicU64` / `AtomicBool`         |
| Concurrent map, per-key locking         | `dashmap::DashMap`                 |
| Latest-value broadcast (config, ticks)  | `tokio::sync::watch`               |
| Pub/sub to N subscribers                | `tokio::sync::broadcast`           |
| Pipeline / work queue                   | `tokio::sync::mpsc` (bounded)      |
| Request/reply                           | `tokio::sync::oneshot`             |
| CPU-bound data parallelism              | `rayon` inside `spawn_blocking`    |

### std vs tokio sync primitive

```rust
// Bad: std::sync::MutexGuard held across .await -> future is !Send, deadlocks runtime
let g = state.cache.lock().unwrap();
let v = fetch(&*g).await;            // worker stuck holding the lock
g.insert(k, v);

// Good: short critical section, no await inside
let cached = state.cache.lock().unwrap().get(&k).cloned();
let v = match cached { Some(v) => v, None => fetch(&k).await };
state.cache.lock().unwrap().insert(k, v.clone());
```

Use `tokio::sync::Mutex` only when the guard genuinely must cross `.await` (e.g. serialising async work). It is slower and not poison-safe via std.

### Lock scope: clone out, drop, compute

```rust
// Bad: heavy work + await inside the critical section
let mut cache = state.cache.lock().await;
let result = expensive(&*cache).await;
cache.insert(key, result);

// Good: minimise the critical section
let input = state.cache.lock().await.get(&key).cloned();
let result = expensive(&input).await;
state.cache.lock().await.insert(key, result);
```

### Read-mostly: prefer ArcSwap over RwLock

```rust
// Bad: rate_limit() takes a read lock on every request hot path
async fn rate_limit(s: &AppState) -> u32 { s.config.read().await.rate_limit }

// Good: wait-free reads; writers swap the whole Arc
use arc_swap::ArcSwap;
static CONFIG: ArcSwap<Config> = ArcSwap::from_pointee(Config::default());
fn current() -> Arc<Config> { CONFIG.load_full() }
fn reload(c: Config)        { CONFIG.store(Arc::new(c)); }
```

`load()` returns a guard you can borrow through (`&cfg.allowed_origins`) with no struct clone - bind it to a `let` first, since the guard must outlive the borrow; use `load_full()` only to move an owned `Arc` across an `.await` or into a spawned task. So the "needs a borrow" case does not force `RwLock`; `RwLock` only wins when readers need a long-lived mutable-in-place borrow. Choose `ArcSwap` when readers just poll the current value, `watch` when a task must be *notified* on change (re-arm a timer, wake a worker).

### Counters: atomics, not Mutex

```rust
// Bad
*state.counter.lock().unwrap() += 1;

// Good
use std::sync::atomic::{AtomicU64, Ordering};
state.requests.fetch_add(1, Ordering::Relaxed); // independent counter -> Relaxed
```

Ordering: `Relaxed` for metrics/counters; `Acquire`/`Release` to publish data via a flag; `SeqCst` only when a total order across several atomics is required.

### DashMap for per-key locking

```rust
// Bad: single Mutex around the whole map -> all keys contend
let mut m = state.sessions.lock().await;
m.entry(uid).or_insert_with(Session::new).touch();

// Good: shard-locked map, no manual guard
state.sessions.entry(uid).or_insert_with(Session::new).touch();
```

### Channels: pick by topology, bound always

```rust
// mpsc: bounded pipeline -> .send().await applies backpressure
let (tx, mut rx) = tokio::sync::mpsc::channel::<Job>(100);

// oneshot: actor reply
struct Cmd { data: String, reply: tokio::sync::oneshot::Sender<Result<String, AppError>> }

// broadcast: each subscriber sees every message; lag is observable
let (btx, _) = tokio::sync::broadcast::channel::<Event>(256);
let mut sub = btx.subscribe();
match sub.recv().await {
    Ok(ev)                                              => handle(ev).await,
    Err(broadcast::error::RecvError::Lagged(n))         => tracing::warn!(skipped = n),
    Err(broadcast::error::RecvError::Closed)            => return,
}

// watch: latest config only; cheap reads, missed intermediates are fine
let (wtx, mut wrx) = tokio::sync::watch::channel(Config::default());
```

`std::sync::mpsc` is sync-blocking on `recv` -- never use it from async tasks; use `tokio::sync::mpsc`.

### Rayon inside async

```rust
// Bad: par_iter parks the tokio worker until the pool finishes -> stalls runtime
let totals: Vec<_> = items.par_iter().map(compute).collect();

// Good: hand off the whole parallel section to a blocking thread
let totals = tokio::task::spawn_blocking(move || {
    items.par_iter().map(compute).collect::<Vec<_>>()
}).await?;
```

### Deadlock prevention: named global order

```rust
// Bad: site A locks (orders, users); site B locks (users, orders) -> cycle
async fn assign(o: &Mutex<Orders>, u: &Mutex<Users>) {
    let _o = o.lock().await; let _u = u.lock().await; /* ... */
}

// Good: documented order -- "always users before orders" -- enforced at every site
async fn assign(o: &Mutex<Orders>, u: &Mutex<Users>) {
    let _u = u.lock().await; let _o = o.lock().await; /* ... */
}
```

Encode the order in a helper (`fn with_user_then_order(...)`) if more than two sites touch the pair.

### Send + Sync triage

```
"future cannot be sent between threads safely" -> a !Send value is alive across .await:
  Rc<T>           -> Arc<T>
  RefCell<T>      -> Mutex<T> (std if no await inside, tokio otherwise)
  MutexGuard      -> shorten the scope (see Lock scope) or switch to tokio::sync
  *const T / *mut -> wrap in a Send newtype only if the invariant is real; document why
```

Last resort: `unsafe impl Send` requires a written justification of the aliasing invariant -- if you can't write it, the type isn't `Send`.

## Output Format

One block per finding when reviewing shared-state code:

```
Primitive: {Mutex | RwLock | Atomic | mpsc | oneshot | broadcast | watch | ArcSwap | DashMap | Rayon | None}
Crate: {std | tokio | parking_lot | arc_swap | dashmap | rayon | crossbeam | N/A}
Issue: {DataRace | Deadlock | LockAcrossAwait | SendSyncViolation | UnboundedChannel | WrongChannelTopology | OverbroadLock | BlockingInAsync | WrongOrdering | Poisoning | None}
Severity: {Blocker | High | Medium | Low}
Location: <file:line or symbol>
Evidence: <one-line quote>
Fix: <one-line action; name the Pattern>
```

Omit no field; use `None` / `N/A` when not applicable. One block per root cause: if several Issue values describe one defect (e.g. an over-broad lock that also enables a deadlock), report the deepest cause and name the rest in `Fix`.

Severity: `Blocker` = unsound or hangs the runtime (lock-across-await, deadlock, `!Send` across `.await`, rayon in async, data race). `High` = correctness/availability risk under load (unbounded channel, wrong topology). `Medium` = contention or panic-on-poison. `Low` = style/clarity.

## Avoid

- `std::sync` guards crossing `.await`, or any lock held while awaiting I/O
- `Rc`/`RefCell` reachable from `tokio::spawn` or any thread
- Unbounded channels without an upstream rate limit; `std::sync::mpsc` in async code
- `Mutex<u64>`/`Mutex<bool>` where an atomic suffices
- `Arc<RwLock<T>>` for snapshot-style reads (prefer `ArcSwap`/`watch`)
- Rayon (`par_iter`, `scope`) inside async fns without `spawn_blocking`
- `Ordering::SeqCst` by default; pick `Relaxed`/`Acquire`/`Release` deliberately
- Multi-lock sites without a documented global order
- `.lock().unwrap()` on `std::sync::Mutex` in long-running services (poisoning panics the task); handle `PoisonError` or use `parking_lot`
- `unsafe impl Send`/`Sync` to silence the compiler instead of fixing the type
