---
name: rust-code-explain
description: Rust per-function signals: ownership, lifetimes, tokio Send/'static, `?` From conversion, sqlx tx scope, std-Mutex-across-await, detached spawn.
metadata:
  category: backend
  tags: [explanation, code-understanding, rust, axum, tokio, sqlx]
user-invocable: false
---

# Rust Code Explain (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-code-explain` when the detected stack is Rust. Emits signals injected into the host's universal sections; do not restate the host's structure.

## When to Use

A workflow needs per-function Rust signals for a `.rs` target: signature ownership, lifetimes, async behavior, error propagation, trait dispatch, sqlx transaction scope. Skip for codebase orientation (`rust-onboard-map`).

## Rules

- The signature is the contract. Read ownership (`T` / `&T` / `&mut T`), lifetimes, trait bounds, and return type before the body.
- Name `?` conversions only where the source and target `Err` types differ or the `From` impl is non-trivial; do not enumerate every `?`.
- For `async fn`: identify the runtime (tokio unless evidence says otherwise), and audit what is held across each `.await`.
- Distinguish generics (`T: Trait`, `impl Trait`, monomorphized) from trait objects (`dyn Trait`, vtable, object-safe).
- Always flag, when present: sync guard (`std::sync::MutexGuard`, `RefCell::borrow_mut`) held across `.await`; `tokio::spawn` whose `JoinHandle` is dropped; `?` between transaction `BEGIN` and `commit`; `unsafe` block without `// SAFETY:`; declared lifetime parameter that constrains nothing.

## Patterns

### Ownership signature decoder

| Signature                          | Means                                  | Caller-side consequence                |
| ---------------------------------- | -------------------------------------- | -------------------------------------- |
| `fn f(x: T)`                       | Moves `x`                              | Clone to reuse                         |
| `fn f(x: &T)`                      | Shared borrow                          | No mutation                            |
| `fn f(x: &mut T)`                  | Exclusive borrow                       | No aliasing while held                 |
| `fn f<'a>(x: &'a T) -> &'a U`      | Output borrows from input              | `x` must outlive return                |
| `Arc<T>` / `Rc<T>`                 | Shared ownership (multi / single thread) | Cycles leak; break with `Weak<T>`    |
| `Arc<Mutex<T>>` / `Arc<RwLock<T>>` | Shared mutable state                   | Use `tokio::sync::*` if held across `.await` |

### Lifetimes

Elided when the compiler infers them; explicit `'a` only when input and output references must be related. `'static` = lives for program duration.

Bad: `fn f<'a>(x: &'a str) -> String` - `'a` constrains nothing the body uses; the parameter is noise.
Good: `fn f<'a>(x: &'a str) -> &'a str` - return validity tied to `x`; caller cannot drop `x` while return is alive.

### `?` and error conversion

`?` propagates `Err` early via `From<SourceErr> for TargetErr`. Worth calling out only when source != target or the conversion has side meaning (e.g., `sqlx::Error::RowNotFound` mapped to a 404).

Bad: "`some_io()?` returns the error if it fails."
Good: "`some_io()?` converts `io::Error` -> `AppError::Io` (the function returns `Result<_, AppError>`); other `?` calls return `AppError` unchanged."

### Async / tokio

`async fn` returns `impl Future`; nothing runs until polled. Anything held across `.await` in a spawned future must be `Send`. Blocking I/O on a worker thread stalls the runtime - offload with `tokio::task::spawn_blocking`.

**Sync guard across `.await` (deadlock or `!Send` bound failure):**
Bad: `let g = std_mutex.lock().unwrap(); other.await; drop(g);`
Good: hold inside a scope that ends before `.await`, or switch to `tokio::sync::Mutex` (whose guard is `Send`).

**Detached spawn (fire-and-forget):**
Bad: `tokio::spawn(async move { work().await });` - panic is swallowed, future is cancelled on runtime drop, shutdown does not await it.
Good: keep the `JoinHandle` (or use a `JoinSet` / `CancellationToken`) and `.await` it during shutdown if completion matters.

**Panic across `.await`:** an `unwind` panic in a spawned task aborts only that task; `JoinHandle::await` surfaces it as `Err(JoinError::panic)`. A detached spawn drops the panic on the floor.

### Generics vs `dyn`

- `T: Trait` / `impl Trait`: static dispatch, monomorphized, code-bloat tradeoff.
- `dyn Trait`: vtable, runtime dispatch, requires object safety (no generic methods, no `Self` in return).

Bad: `fn handlers() -> Vec<impl Handler>` - all elements must be the same concrete type.
Good: `fn handlers() -> Vec<Box<dyn Handler + Send + Sync>>` - heterogeneous, cross-thread-shareable.

### sqlx (per-function)

- `query!` / `query_as!` validate SQL at compile time against `DATABASE_URL` or `.sqlx/` cache; drift between cache and live schema breaks the build.
- `Transaction<'_, Postgres>` borrows the pool, is not `Clone`, and cannot cross `tokio::spawn` boundaries.
- `tx.commit().await` finalizes; drop without commit rolls back. **Any `?` between `begin()` and `commit()` rolls back silently** - call out which DB writes are reverted on the failure path.
- Check the executor of every `await` inside the tx window: `&mut *tx` runs on the transaction; `&pool` / `&self.pool` runs on a separate connection and is **not** rolled back. A pool call between `begin()` and `commit()` silently escapes the transaction (e.g. an audit write that persists even when the tx aborts).

### Axum (per-handler, only if target is a handler)

- Signature `async fn(extractors...) -> Result<impl IntoResponse, AppError>`. Extractor order matters: body extractors (`Json`, `Form`, `Bytes`) consume the request body, so at most one per handler and it must come last.
- `State<S>` requires `S: Clone + Send + Sync + 'static`.

## Output Format

Emit signals as bullets under tags matching the host's section names. The host (`task-code-explain`) injects these into its universal Flow Context / Non-Obvious Behavior / Key Invariants / Change Impact Preview. Omit any tag with no findings.

```
[Flow Context]
- Ownership: {moves | borrows &T | borrows &mut T | mixed: <field-by-field>}
- Lifetimes: {none | elided | explicit: <'a ties X to Y> | declared but unused: <'a>}
- Generics: {none | <bounds and dispatch: static via impl / dynamic via dyn>}
- Async: {sync | async fn (runtime: tokio | <other>)}
- Error type: <return Err type; list only non-trivial From conversions in play>
- Transaction scope: {none | begin at <line>, commit at <line>, writes inside: <tables>}
- Axum extractors: <list in order, mark which consumes the body>     // omit if not a handler

[Non-Obvious Behavior]
- <each value held across .await that is !Send or a sync guard>
- <each `?` between begin() and commit() and what is rolled back>
- <awaits inside the tx window that use the pool (&pool) instead of &mut *tx and so escape the rollback>
- <detached spawns (JoinHandle dropped) and what is lost on shutdown / panic>
- <select! branches whose loss cancels in-flight work>
- <cache / DB writes that can diverge on partial failure>
- <implicit clones (.clone() on Arc, Vec, String in hot paths)>

[Key Invariants]
- <borrow / aliasing rules the caller must preserve>
- <Send + 'static bounds on spawned futures and the data they capture>
- <object-safety constraints, if dyn>
- <transaction atomicity guarantees the function assumes>

[Change Impact Preview]
- <signature ripple: callers, From impls, await-chain Send bound>
- <enum variant additions: presence of #[non_exhaustive]>
- <sync <-> async flip: propagates to every caller>
- <extractor reorder or second body consumer: compile-time failure>
- <cfg(feature) gates that hide or expose this function>
```

## Avoid

- Enumerating every `?` when the conversion is identity.
- Conflating `tokio::sync::Mutex` (async, guard is `Send`) with `std::sync::Mutex` (sync).
- Skipping the `Send + 'static` audit on spawned futures.
- Reporting `tx.commit()` exists without naming what gets rolled back on the `?` paths above it.
- Treating `tokio::spawn` as fire-and-forget without flagging panic swallowing and shutdown-cancellation.
- Drifting into ecosystem or onboarding territory (`rust-onboard-map` owns that).
- Restating the host's section structure instead of emitting tagged signals.
