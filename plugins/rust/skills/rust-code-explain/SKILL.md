---
name: rust-code-explain
description: Explain Rust functions: ownership/borrow signature, lifetimes, tokio async, generics vs dyn, `?` error conversion, sqlx tx boundary.
metadata:
  category: backend
  tags: [explanation, code-understanding, rust, axum, tokio, sqlx]
user-invocable: false
---

# Rust Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Rust.

## When to Use

- A workflow needs per-function Rust signals: signature ownership, lifetimes, async behavior, error propagation, trait dispatch, sqlx transaction scope.
- Target is a function/method in a Rust project (`Cargo.toml`, `.rs`).

Not for codebase orientation (use `rust-onboard-map`) or framework tutorials.

## Rules

- The signature is the contract. Read ownership (`T` vs `&T` vs `&mut T`), lifetimes, trait bounds, and return type before the body.
- For every `?`, name the `From<SourceErr> for TargetErr` that fires; the function's `Err` type determines the target.
- For `async fn`, identify the runtime (tokio assumed unless evidence says otherwise), what is held across `.await`, and `Send`/`'static` bounds on spawned futures.
- Distinguish generics (`T: Trait`, `impl Trait`) - monomorphized - from trait objects (`dyn Trait`) - vtable, object-safe only.
- Flag any sync guard (`std::sync::MutexGuard`, `RefCell::borrow_mut`) held across `.await`, any `JoinHandle` dropped without await, any `unsafe` block without `// SAFETY:`.

## Patterns

### Ownership signature decoder

| Signature                  | Means                                                | Flag                                              |
| -------------------------- | ---------------------------------------------------- | ------------------------------------------------- |
| `fn f(x: T)`               | Moves `x`; caller loses it                           | Caller must clone to reuse                        |
| `fn f(x: &T)`              | Shared borrow; many allowed                          | Cannot mutate                                     |
| `fn f(x: &mut T)`          | Exclusive borrow                                     | No aliasing while held                            |
| `fn f<'a>(x: &'a T) -> &'a U` | Output tied to input lifetime                     | Caller's `x` must outlive returned ref            |
| `Arc<T>` / `Rc<T>`         | Shared ownership (multi/single thread)               | Cycles leak; use `Weak<T>`                        |
| `Arc<Mutex<T>>` / `Arc<RwLock<T>>` | Shared mutable state                         | Pick async lock (`tokio::sync::*`) for async code |

### Lifetimes

Elided when the compiler infers them. Explicit `'a` appears when input/output references must be related. `'static` = lives for program duration (literals, `Box::leak`, owned-only generics).

Bad: claiming `fn f<'a>(x: &'a str) -> String` carries a lifetime constraint - the return owns, so `'a` only constrains `x`'s caller scope.
Good: `fn f<'a>(x: &'a str) -> &'a str` ties the return's validity to `x`; caller cannot drop `x` while the return is alive.

### `Result` and `?`

`?` propagates `Err` early, converting via `From`. The function's return `Err` type drives which `From` impls must exist.

Bad: "the `?` returns the error". Misses the conversion.
Good: "`some_io()?` converts `io::Error` -> `AppError` via `From<io::Error> for AppError`; the function returns `Result<_, AppError>`."

### Async / tokio

- `async fn` returns an opaque `impl Future`; nothing runs until polled.
- `tokio::spawn` requires the future to be `Send + 'static`; drop of `JoinHandle` detaches, does not cancel.
- `tokio::select!` cancels losing branches (drops their futures mid-execution).
- Anything held across `.await` must be `Send` for spawned futures. Sync `MutexGuard` across `.await` is a deadlock risk; use `tokio::sync::Mutex`.
- Blocking I/O in async stalls the worker; offload via `tokio::task::spawn_blocking`.

Bad: `let g = std_mutex.lock().unwrap(); foo().await; drop(g);` - sync guard across await.
Good: `{ let g = std_mutex.lock().unwrap(); /* sync work */ }; foo().await;` or switch to `tokio::sync::Mutex`.

### Generics vs `dyn`

- `T: Trait` / `impl Trait`: monomorphized, static dispatch, code bloat.
- `dyn Trait`: vtable, runtime dispatch, requires object safety (no generic methods, no `Self` in return).
- `Box<dyn Trait + Send + Sync>` for owned cross-thread trait objects.

### sqlx specifics (per-function level)

- `query!` / `query_as!` validate SQL at compile time against `DATABASE_URL` or `.sqlx/` cache.
- `&PgPool` is cheap to pass (Arc internally). A `Transaction<'_, Postgres>` borrows the pool and is not `Send`-cloneable; it cannot cross `tokio::spawn` boundaries.
- `tx.commit().await` finalizes; drop without commit rolls back.

### Axum specifics (per-handler level)

- Handlers are `async fn(extractors...) -> Result<impl IntoResponse, AppError>`.
- Body extractors (`Json`, `Form`) consume the body; one per handler.
- `State<S>` requires `S: Clone + Send + Sync + 'static`.

## Output Format

This atomic emits signals consumed by `task-code-explain`. Produce exactly four blocks with the field enums below.

```
Flow Context:
- Ownership: {moves | borrows &T | borrows &mut T | mixed: ...}
- Lifetimes: {none | elided | explicit: <'a ties X to Y>}
- Generics: {none | <bounds>}
- Async: {sync | async fn, runtime: tokio | async fn, runtime: <other>}
- Error type: <Err type and key From impls>
- sqlx tx scope: {none | open at <line>, commit at <line>}
- Axum extractors: {none | <list>}

Non-Obvious Behavior:
- <each `?` conversion path>
- <anything held across `.await` and its Send/sync class>
- <JoinHandle drops, select! cancellations>
- <cache/DB divergence on partial failure>
- <implicit clones or deep copies>

Key Invariants:
- <borrow rules in force>
- <Send/'static bounds and why>
- <object-safety constraints, if dyn>
- <transaction atomicity guarantees>

Change Impact Preview:
- <signature change ripple: callers, From impls, await chain>
- <enum variant additions: non_exhaustive presence>
- <sync->async or vice versa: caller propagation>
- <extractor reorder or duplicate body consumers>
- <feature flag flips that gate the function>
```

If a block has no findings, emit `- (none)`. If the function is non-async, omit Async lock/`Send` items rather than fabricating them.

## Avoid

- Treating the borrow checker as advisory; the signature is the contract.
- Describing `?` without naming the `From` conversion.
- Conflating `tokio::sync::Mutex` (async) with `std::sync::Mutex` (sync) across `.await`.
- Skipping `Send + 'static` analysis on spawned futures.
- Drifting into ecosystem/onboarding territory (`rust-onboard-map` owns that).
- Saying "Rust has no exceptions" without explaining `panic!` surfacing.
