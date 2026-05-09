---
name: rust-code-explain
description: Rust / Axum code-explain signals: ownership, borrowing, lifetimes, tokio async, trait objects vs generics, error ?, sqlx compile-time queries.
metadata:
  category: backend
  tags: [explanation, code-understanding, rust, axum, tokio, sqlx]
user-invocable: false
---

# Rust Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Rust.

## When to Use

- A workflow needs Rust-specific signals: ownership/borrow checker rules visible in the signature, lifetimes, async with `tokio`, trait objects vs static dispatch, `Result<T, E>` propagation with `?`, sqlx compile-time SQL.
- Target is in a Rust project (`Cargo.toml`, files ending `.rs`).

## Rules

- Read the function signature first - ownership (`T` vs `&T` vs `&mut T`), lifetimes (`'a`), and trait bounds tell you most of what the function can and cannot do.
- For async, identify the runtime (almost always `tokio`) and whether the function is `async fn`. Mixing runtimes (tokio vs async-std) does not work.
- For each `?` operator, identify the error conversion path - `From` impls determine what concrete error becomes the function's `Err` type.
- Distinguish trait objects (`dyn Trait`) from generic bounds (`impl Trait` / `T: Trait`) - dyn does dynamic dispatch and requires object safety; generics are monomorphized.
- Identify `unsafe` blocks and the invariant they upheld - the comment above an unsafe block is the contract.

## Patterns

### Ownership and Borrowing

| Signature              | What it means                                                                                  | What to flag                                                                                              |
| ---------------------- | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `fn f(x: T)`           | Takes ownership; `x` cannot be used by caller after                                            | Forces a move; if caller needs `x` later, must clone                                                       |
| `fn f(x: &T)`          | Borrows immutably; caller retains ownership                                                    | Multiple `&T` allowed simultaneously                                                                       |
| `fn f(x: &mut T)`      | Borrows mutably and exclusively                                                                | Only one `&mut T` at a time; caller cannot read `x` while borrowed                                         |
| `fn f<'a>(x: &'a T)`   | Explicit lifetime; `x` must live at least as long as `'a`                                      | Lifetime annotations on returns: `fn f<'a>(x: &'a T) -> &'a T` ties the return's lifetime to the input    |
| `Box<T>`               | Heap-allocated; owned                                                                          | Used for recursive types and trait objects                                                                  |
| `Rc<T>` / `Arc<T>`     | Shared ownership; reference counted (Rc single-thread, Arc multi-thread)                       | Cycles leak - use `Weak<T>` to break                                                                       |
| `RefCell<T>` / `Mutex<T>` | Interior mutability; `RefCell` single-thread, `Mutex` multi-thread                          | `RefCell::borrow_mut` panics on conflict; `Mutex::lock` blocks                                             |

### Lifetimes

- Most lifetimes are elided. Explicit `'a` appears when the compiler cannot infer the relationship between input and output references.
- `'static` means "lives for the whole program" - string literals, `Box::leak`, etc.
- Lifetime errors at the boundary often indicate the actual bug: storing a reference past its source's scope.

### `Result<T, E>` and `?`

- `?` returns early on `Err`, converting via `From<SourceErr> for TargetErr`.
- The function's return type determines the target error: `fn f() -> Result<T, MyError>` requires `From<io::Error> for MyError` for `let x = some_io_op()?;` to compile.
- `anyhow::Error` (in apps): erased error type, easy `?` propagation, lossy on type info.
- `thiserror::Error` (in libs): derive macro for typed error enums, preserves type info for callers.
- `Option<T>::ok_or(err)` / `Result::ok()` for converting between the two.

### Async with tokio

- `async fn` returns an opaque `impl Future`. Polled by an executor, never executes by itself.
- `.await` suspends the future; control returns to the executor.
- `tokio::spawn(async { ... })` schedules a future on the runtime; returns `JoinHandle<T>`. Drop without `await` does **not** cancel - it detaches.
- `tokio::select! { ... }` multiplexes futures - first to complete wins; others are cancelled (dropped).
- `Send` and `'static` bounds on spawned futures: anything held across `.await` must be `Send`; this rules out `Rc`, `RefCell`, and non-`Send` guards.
- Holding a `MutexGuard` (sync) across `.await` is a deadlock waiting to happen - use `tokio::sync::Mutex` (async-aware) instead.
- Blocking I/O in async context: stalls the runtime worker thread. Use `tokio::task::spawn_blocking` for CPU-bound or sync I/O work.

### Traits, Generics, and Dyn

- `T: Trait` (generic): monomorphized at compile time; one copy per type. Fast, code bloat.
- `impl Trait` in argument: same as generic; in return position: opaque type, single concrete type per function.
- `dyn Trait` (trait object): runtime dispatch via vtable. Requires object safety (no generic methods, no `Self` in return position).
- `Box<dyn Trait>` for owned trait objects; `&dyn Trait` for borrowed.
- `+ Send + Sync` bounds appear when the trait object crosses thread boundaries.

### Pattern Matching and Enums

- `match` is exhaustive - all variants must be handled or `_`.
- `if let Some(x) = opt { ... }` for single-pattern; `let else` for early-exit on no-match.
- `Option<T>` and `Result<T, E>` are enums; `match` on them is the primary control flow for absence/error.

### Smart Pointers and Concurrency

- `Arc<Mutex<T>>` is the canonical "shared mutable state across threads".
- `Arc<RwLock<T>>` for many-reader, one-writer.
- Channels: `tokio::sync::mpsc` (multi-producer single-consumer), `oneshot` (single value), `broadcast` (many receivers).
- `tokio::sync::Notify` for waker patterns.

### Axum Specifics

- Routes built with `Router::new().route("/path", get(handler))`.
- Handler is an async function that takes extractors (`Path`, `Query`, `Json`, `State`, custom) and returns `IntoResponse`.
- Extractor order matters - body extractors (`Json`, `Form`) consume the request body; only one body extractor per handler.
- State (`State<AppState>`) shared across handlers, must be `Clone` and `Send + Sync + 'static`.
- Middleware via `layer(...)`; tower-based ecosystem (compression, tracing, timeout, auth via `axum-login` etc.).
- Errors: handlers return `Result<impl IntoResponse, AppError>`; `AppError` implements `IntoResponse` to produce HTTP error responses.

### sqlx Specifics

- `query!` and `query_as!` macros validate SQL at **compile time** against a real database - need `DATABASE_URL` set or `.sqlx/` cache committed.
- `query_as!(User, "SELECT ...")` returns rows as the typed struct.
- Connection pool: `PgPool::connect(...)`. Cloning the pool is cheap (Arc internally); pass `&PgPool` to functions.
- Transactions: `let mut tx = pool.begin().await?; ...; tx.commit().await?;` - drop without commit rolls back.
- No ORM - hand-write SQL. Migrations via `sqlx::migrate!()` macro.

### Cargo Features and `cfg`

- Optional features in `Cargo.toml` `[features]` section; activated with `cargo build --features foo`.
- `#[cfg(feature = "foo")]` conditionally compiles code.
- `#[cfg(test)]` for test-only code; `#[cfg(target_os = "linux")]` for OS-conditional.

### Macros

- `println!`, `vec!`, etc. are macro_rules! macros - not functions.
- `derive(...)` macros generate trait implementations; common: `Debug`, `Clone`, `PartialEq`, `Serialize`, `Deserialize`.
- Procedural macros (`#[my_macro]`) run at compile time; `tokio::main`, `axum`'s extractors, `sqlx::query!` are all procmacros.

### Common Allocation Pitfalls

- `String::clone()` copies the entire heap buffer; `Arc<str>` for shared, immutable strings.
- `vec.clone()` copies all elements; consider `Arc<Vec<T>>` or `Arc<[T]>` if read-only sharing suffices.
- `format!` allocates; use `write!` to a buffer for hot paths.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- Function ownership signature (takes `T`, `&T`, or `&mut T`)
- Async runtime (tokio); whether function is `async fn`
- Lifetime annotations and what they tie together
- For Axum: extractor list and middleware layers
- For sqlx: pool source and transaction boundary

**Into "Non-Obvious Behavior":**

- Lifetime constraints that limit how the result can be used
- `?` error conversion path (which `From` impls fire)
- Holding sync `MutexGuard` across `.await` (deadlock risk)
- Dropping a `JoinHandle` without `await` (detach, not cancel)
- `tokio::select!` cancelling other branches
- `query!` macros requiring DATABASE_URL or `.sqlx/` cache
- Cloning collections being a deep copy

**Into "Key Invariants":**

- Borrow checker rules: only one `&mut` at a time, no `&mut` while `&` exists
- `Send + 'static` required for spawned futures
- Only object-safe traits can be `dyn`
- Sync mutex must not cross `.await`

**Into "Change Impact Preview":**

- Adding a new variant to a non-`#[non_exhaustive]` enum: every `match` site must add a case (compile errors are good here)
- Changing a function from sync to async: every caller chain must propagate `await`
- Adding a new field to a `pub struct`: callers using struct literal initialization break unless `#[non_exhaustive]`
- Changing an extractor in Axum: order with body extractors matters; runtime errors if multiple consume body
- Adding `Arc<Mutex<T>>` shared state: lock contention and possible deadlocks

## Avoid

- Treating Rust's borrow checker as advisory - the signature is the contract
- Recommending `Arc<RwLock<T>>` without considering `Arc<Mutex<T>>` for write-heavy patterns
- Confusing `tokio::sync::Mutex` (async) with `std::sync::Mutex` (sync) - they have different semantics across `.await`
- Glossing over `Send` bounds on spawned futures - this is the most common spawn compile error
- Saying "Rust has no exceptions" without explaining `panic!` and where it surfaces
- Describing `?` without naming the `From` conversion that makes it work
