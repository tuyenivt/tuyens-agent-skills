---
name: rust-concurrency
description: "Rust shared state: Arc, std vs tokio Mutex across .await, RwLock, ArcSwap, DashMap, atomics, bounded channels, Send+Sync, lock order, rayon."
metadata:
  category: backend
  tags: [rust, concurrency, mutex, channels, atomics, send-sync, rayon]
user-invocable: false
---

# Rust Concurrency (Shared State)

> The crate under review decides the version gates below: `rust-version` in its `Cargo.toml` (else the `rust-toolchain.toml` channel; a `## Tech Stack` `Language:` line may carry a version, and the manifest wins when they differ), its `edition`, and the crate versions in its `[dependencies]` (or the `[workspace.dependencies]` entries it inherits). A form that needs a newer toolchain, edition or crate than that is written in its older equivalent - below edition 2024, an `if let` on a guard-producing scrutinee holds the guard through the `else` branch, so bind the result with `let` first. Baseline: Rust 1.94+ (edition 2024, `LazyLock`), Tokio 1.x `sync`, arc-swap 1, dashmap 6, rayon 1, parking_lot 0.12. Task lifecycle, cancellation, `select!`, timeouts and `spawn_blocking` belong to `rust-async-patterns`; this skill owns shared-state primitives, channels and `Send` / `Sync`.

## When to Use

- Choosing between `Mutex`, `RwLock`, atomics, `ArcSwap`, `DashMap`, an actor, or rayon
- Reviewing shared state for lost updates, deadlocks, guards held across `.await`, or `Send` / `Sync` errors
- Sizing and typing channels (mpsc / oneshot / broadcast / watch; std vs tokio)
- Debugging a deadlock, lock contention, or a `future cannot be sent between threads safely` error

## Rules

- Safe Rust rules out data races, not logic races. A check-then-act split across two lock acquisitions (read, unlock, compute, re-lock, write) loses updates - an invariant lives under one critical section, or the second acquisition re-checks
- `std::sync::Mutex` / `RwLock` unless the guard must be held across `.await`; then `tokio::sync`. A std guard alive across `.await` makes the future `!Send`, and on a path that compiles anyway (current-thread runtime, a future never spawned) it can deadlock the worker. Clippy's `await_holding_lock` (on by default) flags it
- Hold a guard for a statement or a block: copy or clone out, drop, then compute or await. Never `.await` I/O or a channel send while holding any lock
- Two or more locks held together are acquired in one documented global order at every site
- `Arc<T>` shares across tasks and threads; `Rc` / `RefCell` are `!Send` and never cross `tokio::spawn`
- Channels by topology and always bounded; every send to a bounded channel picks a full policy (block with cancel / drop / evict). A channel closes only when every `Sender` is dropped - a `Sender` kept in a long-lived struct keeps the receiver loop alive forever
- Atomics for one counter or flag; a lock once the invariant spans fields
- A std `Mutex` poisons when a holder panics. Decide per lock: propagate (`lock().unwrap()` - the state may be half-written), recover (`unwrap_or_else(PoisonError::into_inner)` when no half-update is possible), or `parking_lot` (no poisoning). `tokio::sync::Mutex` does not poison
- rayon runs inside `spawn_blocking` or behind `rayon::spawn` + `oneshot`, never directly in an `async fn`
- `unsafe impl Send` / `Sync` carries a written aliasing invariant; if it cannot be written, the type is not `Send`

## Patterns

### Primitive Selection

| Need | Use |
|------|-----|
| Shared mutable state, short critical sections | `Arc<std::sync::Mutex<T>>` |
| Guard must be held across `.await` (serializing async work) | `Arc<tokio::sync::Mutex<T>>` |
| Read-mostly snapshot, whole-value replace (config, routing table) | `ArcSwap<T>` |
| Read-mostly, readers must be notified of change | `tokio::sync::watch` |
| Read-heavy, large structure mutated in place | `RwLock<T>` |
| One counter or flag | `AtomicU64` / `AtomicBool` |
| Concurrent map with per-key updates | `DashMap` |
| State with many operations and invariants | an actor: one task owns it, `mpsc` in, `oneshot` replies |
| One-time initialization | `LazyLock` / `OnceLock` (`tokio::sync::OnceCell` when the init is async) |
| CPU-bound data parallelism | rayon inside `spawn_blocking` |

### Guards and `.await`

```rust
use std::{collections::HashMap, sync::{Arc, Mutex}};
use crate::{fetch, Value};

pub struct Cache { map: Mutex<HashMap<String, Value>> }

impl Cache {
    // Bad: the std guard lives across .await - !Send, and stalls every other caller for the fetch
    pub async fn get_bad(self: Arc<Self>, key: String) -> Value {
        let mut map = self.map.lock().unwrap();
        let v = fetch(&key).await;
        map.insert(key, v.clone());
        v
    }

    // Good: no guard crosses the await; the insert re-checks, so a racing miss is a duplicate fetch, never a lost value
    pub async fn get(self: Arc<Self>, key: String) -> Value {
        let cached = self.map.lock().unwrap().get(&key).cloned();
        if let Some(v) = cached { return v; }
        let fetched = fetch(&key).await;
        self.map.lock().unwrap().entry(key).or_insert(fetched).clone()
    }
}
```

When duplicate fetches are expensive, store a per-key `Arc<tokio::sync::OnceCell<Value>>` in the map so concurrent misses await one initializer. A `tokio::sync::Mutex` is for a guard that must span the await (writes to one connection, a sequence that must not interleave); it is slower and still serializes every caller for the whole await.

**Temporaries hold guards.** A guard created in a `match` scrutinee lives until the end of the `match`, even after `.cloned()`:

```rust
// Bad: the scrutinee's guard is still held in the None arm - re-locking deadlocks or panics
match state.sessions.lock().unwrap().get(&id).cloned() {
    Some(s) => s,
    None => { let s = Session::new(); state.sessions.lock().unwrap().insert(id, s.clone()); s }
}

// Good: the guard drops at the end of the let statement
let found = state.sessions.lock().unwrap().get(&id).cloned();
```

### Read-Mostly State

```rust
use std::sync::Arc;
use arc_swap::ArcSwap;
use crate::config::Config;

pub struct Settings { current: ArcSwap<Config> }

impl Settings {
    pub fn new(c: Config) -> Self { Self { current: ArcSwap::from_pointee(c) } }
    pub fn rate_limit(&self) -> u32 { self.current.load().rate_limit } // wait-free read, short-lived guard
    pub fn snapshot(&self) -> Arc<Config> { self.current.load_full() } // owned: may cross an .await
    pub fn reload(&self, c: Config) { self.current.store(Arc::new(c)); }
}
```

`ArcSwap::from_pointee` is not `const`: a global needs `LazyLock<ArcSwap<T>>`, and an `AppState` field is better. `watch` when a task must wake on change; its `borrow()` holds a read lock, so clone out before any `.await`. A std `RwLock`'s writer-vs-reader priority is platform-dependent - a steady read stream can starve writers - while `tokio::sync::RwLock` is FIFO-fair. `Arc<RwLock<T>>` over a value that is only ever replaced whole is `ArcSwap`.

### Counters

```rust
use std::sync::atomic::{AtomicU64, Ordering};

// Bad: a lock for one integer
*state.requests.lock().unwrap() += 1;

// Good
state.requests_total.fetch_add(1, Ordering::Relaxed); // an independent counter
```

`Relaxed` for counters and metrics; `Release` on the store and `Acquire` on the load to publish data through a flag; `SeqCst` only when several atomics need one total order. A read followed by a separate write (`load`, then `store(v + 1)`) is a lost update - use `fetch_add` or `compare_exchange`.

### DashMap

`sessions.entry(uid).or_insert_with(Session::new)` locks one shard, not the whole map. Every `Ref` / `RefMut` it hands out holds that shard's lock: across `.await` it is the std-guard hazard, and calling any other method on the same map while holding one deadlocks when the keys share a shard. Clone out, drop, then touch the map again. Iteration locks shards in turn and sees a mix of before and after concurrent writes.

### Channels

```rust
use tokio::sync::{broadcast, mpsc, oneshot, watch};
use crate::{config::Config, events::{Event, handle}, jobs::Job};

// mpsc, N:1 pipeline: a few slots per consumer, so send().await pushes back early
let (tx, mut rx) = mpsc::channel::<Job>(64);

// oneshot: request/reply into an actor that owns its state outright - no lock
pub struct Get { pub key: String, pub reply: oneshot::Sender<Option<String>> }

// broadcast, 1:N: every subscriber sees every message (T: Clone); lag is reported, not silent
let (btx, _) = broadcast::channel::<Event>(256);
let mut sub = btx.subscribe();
loop {
    match sub.recv().await {
        Ok(ev) => handle(ev).await,
        Err(broadcast::error::RecvError::Lagged(n)) => tracing::warn!(skipped = n, "subscriber lagged"),
        Err(broadcast::error::RecvError::Closed) => break,
    }
}

// watch: latest value only; intermediate values may be skipped
let (cfg_tx, mut cfg_rx) = watch::channel(Config::default());
```

| Policy | Shape | Use when |
|--------|-------|----------|
| Block with cancel | `select!` on `tx.reserve()` then `permit.send(v)`, against `token.cancelled()` | required work; the owner controls the exit |
| Drop | `tx.try_send(v)`, counting `TrySendError::Full` | telemetry, progress pings |
| Evict | `try_send` fails -> remove the subscriber's `Sender` under the registry's lock | pub/sub fan-out where a dead peer must not persist |
| Lag | `broadcast` - a slow receiver gets `Lagged(n)` and skips | 1:N where a subscriber may miss messages |
| Latest | `watch` | config, health, state snapshots |

`mpsc::channel(0)` panics - capacity is at least 1. `unbounded_channel` only behind a documented upstream bound. `std::sync::mpsc::Receiver::recv` blocks the thread - never in async code. The `select!` cancel-safety of each send and receive form is in `rust-async-patterns`.

### Rayon from Async

```rust
use rayon::prelude::*;

// Bad: par_iter parks the Tokio worker until the whole parallel section finishes
let scores: Vec<_> = items.par_iter().map(score).collect();

// Good: hand the parallel section to a blocking thread
let scores = tokio::task::spawn_blocking(move || items.par_iter().map(score).collect::<Vec<_>>()).await?;
```

`score` is the project's. rayon's global pool is shared by every caller in the process; a long batch starves the rest unless it runs on its own `ThreadPoolBuilder` pool. Alternative hop: `rayon::spawn` with a `oneshot::Sender` for the result, awaited on the receiver.

### Lock Order

```rust
use tokio::sync::Mutex;
use crate::{Orders, Users};

// Bad: assign locks (orders, users), refund locks (users, orders) - two callers deadlock
async fn assign(o: &Mutex<Orders>, u: &Mutex<Users>) { let _o = o.lock().await; let _u = u.lock().await; }

// Good: the documented order "users before orders", encoded once
async fn with_user_then_order<R>(u: &Mutex<Users>, o: &Mutex<Orders>, f: impl FnOnce(&mut Users, &mut Orders) -> R) -> R {
    let mut users = u.lock().await;
    let mut orders = o.lock().await;
    f(&mut users, &mut orders)
}
```

With more than two sites touching the pair, every site goes through the helper. Locks of the same kind (two accounts) are ordered by a stable key, as with database row locks.

### Send + Sync Triage

```
"future cannot be sent between threads safely" - the compiler note names the value held across an .await:
  std MutexGuard / RwLock guard    -> end its scope in a block before the .await, or tokio::sync if it must span it
  Rc<T>                            -> Arc<T>
  RefCell<T> / Cell<T>             -> Mutex<T> or an atomic
  Box<dyn Error> / dyn Trait       -> add + Send + Sync to the trait object
  *const T / *mut T                -> a Send newtype only with a written invariant
```

`tokio::spawn` requires `Send + 'static`; `JoinSet::spawn` the same. A `!Send` future that must stay so runs on a `LocalSet` with `spawn_local`.

## Edge Cases

- `std::sync::Mutex` is not reentrant: locking it again on the same thread deadlocks or panics
- `RwLock` read guards acquired recursively on one thread can deadlock once a writer queues between them
- `Mutex<HashMap>` held while iterating to build a response holds every other request for the whole serialization

## Output Format

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design / implementation | `## Concurrency Design` with `### Shared State`, `### Channels`, `### Lock Order`, then top-level `## Verification` |
| Review | `## Findings`, then `## Concurrency Design` with the three subsections describing the code as it exists today, then `## Verification` |
| Debug (deadlock / contention / `Send` error) | two opening lines `**Failing:**` and `**First fix:**`, then `## Findings`, `## Concurrency Design`, `## Verification` |

```
## Concurrency Design

### Shared State
| Shared State | Protection | Crosses .await? | Why |
|--------------|------------|-----------------|-----|

### Channels
| Channel | Kind | Capacity | Full Policy | Closed By |
|---------|------|----------|-------------|-----------|

### Lock Order
| Locks | Acquisition Order | Sites |
|-------|-------------------|-------|

## Verification
| Check | Where |
|-------|-------|
```

Cell values: `Shared State` names the field or static (`AppState.sessions`). `Protection` is `std Mutex | std RwLock | tokio Mutex | tokio RwLock | parking_lot | atomic | ArcSwap | DashMap | LazyLock | OnceLock | actor | external (DB lock) | none`. `Crosses .await?` is `Yes | No` - whether any guard or borrow of it is alive across an `.await`. `Kind` is `mpsc | oneshot | broadcast | watch | unbounded mpsc | std mpsc | crossbeam | flume`. `Capacity` is the number, or `unbounded`. `Full Policy` is `block with cancel | block | drop | evict | lag | latest | none` - `block` is a bare `send().await` with no cancellation branch, `none` an unbounded channel. `Closed By` names what drops the last `Sender` (`owner drops tx on shutdown`), or `never` when a `Sender` lives in long-lived state. `Lock Order` has one row per set of locks held together, `Sites` naming every function that takes them; with no such set the table holds `None.`. Every `Protection: none` row over state that more than one task writes is also a `[Must]` finding - a Design engagement adds `## Findings` after `## Verification` to hold it. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries. `Verification` rows are the checks that would catch this class of defect - Clippy `await_holding_lock` / `await_holding_refcell_ref` as errors, `loom` model tests for hand-rolled atomics or lock-free code, Miri for `unsafe`, a `#[tokio::test(flavor = "multi_thread")]` stress test, parking_lot's `deadlock_detection` feature in staging - each naming the crate, test module or CI step that runs it. `**Failing:**` names the symptom and where it shows (`p99 4s, all workers parked in Cache::get on the std Mutex`); `**First fix:**` names the one smallest edit that removes it - a second edit, even to the same type, is a Finding. On a review every `## Concurrency Design` cell describes the code as written and the intended value goes in the finding's `Fix`; on a design the cells are the design.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {what goes wrong, and under what conditions if it is currently latent}
- Rule: {the concurrency rule violated}
- Fix: {concrete edit}
```

Owned findings: `[Must]` for a lost update, a deadlock, a guard held across `.await` or across I/O, an unbounded channel with no upstream bound, a `Sender` that keeps a loop alive forever, rayon on a Tokio worker, an unjustified `unsafe impl Send` / `Sync`, or a panic reachable in production through poisoning; `[Recommend]` otherwise (a lock where an atomic or `ArcSwap` fits, `SeqCst` by default). A defect that is currently masked (by lock ordering, by a caller that happens to serialize, by a single-replica deploy) is still `[Must]` - say what unmasks it. Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not; a range is `file:start-end`. Order owned findings `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites is one heading citing the first site, with the rest named on the `Defect:` line. A defect this skill does not own (a detached task, a non-cancel-safe `select!` branch, a swallowed error, a transaction held open) is still reported, never dropped: one block per such defect after every owned finding, in that same order among themselves, labelled `[Must]` when it risks incorrect behaviour, data loss or a security hole and `[Recommend]` otherwise, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- A std guard alive across `.await`, or any lock held while awaiting I/O
- `Rc` / `RefCell` reachable from a spawned task
- Unbounded channels with no upstream bound; `std::sync::mpsc` in async code
- `Mutex<u64>` / `Mutex<bool>` where an atomic fits
- `Arc<RwLock<T>>` for whole-value snapshot reads
- Multi-lock sites without a documented order
- `unsafe impl Send` / `Sync` to silence the compiler
