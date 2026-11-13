---
name: rust-overengineering-review
description: "Rust necessity review - validator/service guards duplicating sqlx/DB constraints, Option-wrapped deps, single-impl traits, read-only Arc<Mutex>."
metadata:
  category: backend
  tags: [rust, axum, sqlx, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

# Rust Overengineering Review

> Load `Use skill: stack-detect` first. This skill reads `Framework` and `Database`: the framework guarantees it cites are Axum's (`Json<T>` rejects a missing or mistyped field with 422 and malformed JSON with 400 before the handler runs; `Path<Uuid>` rejects a non-UUID with 400; a panicking handler drops its connection, not the server, and `CatchPanicLayer` exists only when installed). Under actix-web the extractor statuses differ - cite a different constraint or do not flag. The DB error helpers are sqlx 0.7+ on PostgreSQL (`DatabaseError::is_unique_violation()` / `is_foreign_key_violation()`, SQLSTATE `23505` / `23503`); Diesel matches `DatabaseErrorKind::UniqueViolation`. Rust's type system, exhaustive `match` and the borrow checker remove whole categories other stacks review for - an empty category is a correct result. Anything `cargo clippy --all-targets -- -D warnings` already reports at default levels is not a finding here.

## When to Use

- Reviewing a Rust diff that adds `validator` rules, defensive guards, traits, `Box<dyn>` / `Arc<dyn>`, generics, `async`, `Arc<Mutex<T>>`, `.clone()`, or `cfg(feature)`
- Catching code that is correct, performant, and safe but does not need to exist

## Rules

- Every finding cites the constraint making the code redundant: a `validator` rule, a field type, a newtype's constructor, a unique index or FK by name, an extractor guarantee, a compile-time contract, or a repo fact (call sites, existing implementations, a mock). When several stack (e.g., validator + FK + "only HTTP write path"), list them comma-separated in `Redundant because:`
- **Label.** `[Recommend]` is the default. `[Must]` when the code costs something at runtime or actively misleads - an extra query per request, a silently discarded error, a `catch_unwind` that reports success on failure, a lock taken on every read of immutable data, a detached `tokio::spawn` with no owner - **or** when it is a premature abstraction whose maintenance cost is concrete: parallel definitions to keep in sync, dynamic dispatch on every call, lost jump-to-impl (a single-impl trait at the implementation, a pass-through layer). `Cost:` names that cost; a runtime cost that is also a security exposure is named as both
- **Justification is repo-visible, not diff-visible.** A second implementation, a `mockall` mock, a worker or CLI call site, a `dyn` collection, and a benchmark showing a hot path all live outside the hunks. Check the repo before flagging; if you cannot, say which fact you could not verify and label `[Recommend]`, never `[Must]`. Confirmed justification is not a finding
- A redundancy outside the PR hunks that the hunks build on (the trait the new service wraps) is reported with `pre-existing` on the heading line, never silently skipped

## Patterns

### Category 1: Redundant Validation vs Types / sqlx / DB Constraints

Validation stack: **field type -> `Json<T>` deserialization -> `validator` rule -> service guard -> DB schema**. Deserialization and `validate()` both reject before any service call; the DB is authoritative.

#### Manual check after a `validator` rule or a type

```rust
// Bad - #[validate(length(min = 1))] already rejected an empty name, and a non-Option field
// cannot be missing: Json<T> rejected that with 422
if req.name.is_empty() { return Err(AppError::Validation("name required".into())); } // dead
```

`#[validate(required)]` is meaningful only on an `Option<T>`; on a plain field serde already enforces presence. A guard re-checking an invariant a newtype's constructor enforces (`Email::parse` then `email.as_str().contains('@')`) is the same shape.

#### Existence probe before a write the DB already constrains

`[Must]` - races (two concurrent requests pass the SELECT) and adds a query per write. The same shape appears against a unique index and against a foreign key; both are the constraint doing the work twice.

```rust
// Bad
let taken = sqlx::query_scalar::<_, i64>("SELECT 1 FROM users WHERE email = $1")
    .bind(&req.email).fetch_optional(&pool).await?;
if taken.is_some() { return Err(AppError::EmailTaken); }
sqlx::query("INSERT INTO users (email) VALUES ($1)").bind(&req.email).execute(&pool).await?;

// Good - let the constraint decide, map its error
sqlx::query("INSERT INTO users (email, customer_id) VALUES ($1, $2)")
    .bind(&req.email).bind(req.customer_id).execute(&pool).await
    .map_err(|e| match &e {
        sqlx::Error::Database(d) if d.is_unique_violation() => AppError::EmailTaken,
        sqlx::Error::Database(d) if d.is_foreign_key_violation() => AppError::CustomerNotFound,
        _ => AppError::from(e),
    })?;
```

With several unique indexes on the table, disambiguate with `d.constraint()`.

#### Service-layer guard duplicating validator + FK

```rust
// Bad - the DTO's range(min = 1) enforced it on the only write path; the FK rejects an unknown customer
pub async fn create(&self, customer_id: i64, total_cents: i64) -> Result<Order, AppError> {
    if customer_id <= 0 { return Err(AppError::Validation("customer_id".into())); } // dead
    self.repo.create(customer_id, total_cents).await
}
```

Justified when a non-HTTP write path (a job handler, a CLI, a gRPC service) reaches the service without the DTO - or make the type carry it (`NonZeroU64`, a `CustomerId` newtype) and delete both checks.

### Category 2: Defensive Code for Impossible States

A guard on a state the types already exclude is `[Recommend]`; `[Must]` only when it reports success on failure or hides a wiring bug.

#### `Option` around a dependency the constructor always or never sets

```rust
// Bad - OrderService::new sets mailer: None and nothing else assigns it: the email silently never sends
if let Some(m) = &self.mailer { m.send(&receipt).await?; }
```

`[Must]` when the constructor never sets it - the guard hides a wiring bug as a feature. `[Recommend]` when it always sets it - the `Option` is noise. Either the dependency is required (a constructor parameter, no `Option`) or the behaviour is optional by design (name the option).

#### `Result` whose `Err` is never constructed

```rust
// Bad - infallible, but every caller writes `?` and an error arm that cannot run
fn total(items: &[LineItem]) -> Result<i64, AppError> {
    Ok(items.iter().map(|i| i.price_cents * i.qty).sum())
}
```

Justified when a trait signature requires `Result`, or a fallible branch lands in the same PR.

#### Discarded errors

`[Must]`. Reports success on failure.

```rust
// Bad - `let _ =` silences #[must_use]; `.ok()` turns the error into None that nothing reads
let _ = repo.save(&order).await;
audit.record(&event).await.ok();

// Good - propagate; or, for a genuinely best-effort write, log it where it is dropped
repo.save(&order).await?;
if let Err(e) = audit.record(&event).await { tracing::warn!(error = %e, "audit record dropped"); }
```

#### `catch_unwind` in business code

```rust
use std::panic::AssertUnwindSafe;
use futures::FutureExt;

// Bad - converts a programmer bug into a logged line and Ok(()): the caller sees success
let res = AssertUnwindSafe(process(order)).catch_unwind().await;
if let Err(p) = res { tracing::error!(?p, "panic"); return Ok(()); }
```

Panic containment belongs to the edge (`CatchPanicLayer`, the runtime's per-task boundary). In business code `[Must]` when it returns success, `[Recommend]` when it returns an error (redundant with the edge, not misleading). With `panic = "abort"` in the release profile it never catches anything - dead and misleading, `[Must]`.

### Category 3: Premature Abstraction

#### Single-impl trait at the implementation side

`[Must]` when the trait lives beside its only implementor, no mock is derived, and no second impl exists - the trait plus `Arc<dyn Trait>` adds dynamic dispatch and a parallel definition to keep in sync. One block covers the trait and the `dyn` field that consumes it.

```rust
use std::sync::Arc;
use sqlx::PgPool;

// Bad - trait and only impl in repository.rs; no mock, no second impl
pub trait OrderRepository: Send + Sync { async fn find(&self, id: i64) -> Result<Option<Order>, sqlx::Error>; }
pub struct PgOrderRepository { pool: PgPool }
pub struct OrderService { repo: Arc<dyn OrderRepository> } // also needs #[async_trait] to be dyn-compatible

// Good - the concrete type until a second impl or a test double exists
pub struct OrderRepository { pool: PgPool }
pub struct OrderService { repo: OrderRepository }
```

Justified when `#[cfg_attr(test, mockall::automock)]` (or a `mocks` feature) derives a mock that tests use, 2+ concrete impls exist, the trait is a documented public API of a library crate, or a heterogeneous collection (`Vec<Box<dyn Handler>>`) needs `dyn`.

#### Generic type with fewer than three instantiations

`Repository<T>` / `Service<T: Entity>` instantiated once or twice. `Redundant because:` fewer than three instantiations - write the concrete types. `[Must]` when it forces a trait per entity or a `dyn` on every path, `[Recommend]` otherwise.

#### Detached `tokio::spawn` wrapping a sequential call

`[Must]` - no owner at shutdown (the runtime drops the task at its next `.await`), unbounded concurrency, the `Result` is dropped with the `JoinHandle`, and a panic surfaces only on stderr.

```rust
// Bad
repo.save(&order).await?;
tokio::spawn(async move { notifier.notify(&order).await }); // fire-and-forget; the error is lost

// Good - call directly, or enqueue to a tracked async system with a retry policy
notifier.notify(&order).await?;
```

Justified when dispatched to a tracked async system - a job table, a `JoinSet` drained at shutdown, an outbox - with its own retry policy. `tokio::join!` / `try_join!` inside the request is synchronous fan-out, not async dispatch, and has no retry.

#### Pure pass-through layer

A type whose every method only forwards to one dependency. `Redundant because:` the consumer can hold the dependency directly - the layer adds a parallel API to keep in sync (`[Must]`, maintenance cost).

```rust
// Bad - middleman: all 5 methods look like this
pub async fn get_by_id(&self, id: i64) -> Result<Option<Item>, sqlx::Error> { self.repo.get_by_id(id).await }
```

Justified when sibling methods on the same type carry real logic (API consistency), or the same PR introduces a cross-cutting concern (authz, a transaction boundary) into the layer.

#### Single-variant error enum

```rust
// Bad - one variant wrapping one source; every caller immediately converts it to AppError
#[derive(Debug, thiserror::Error)]
pub enum FindOrderError { #[error(transparent)] Db(#[from] sqlx::Error) }

// Good - return the module's error type (or sqlx::Error) directly
pub async fn find_order(pool: &PgPool, id: i64) -> Result<Option<Order>, sqlx::Error> { /* ... */ }
```

Justified when callers match on its variants or read fields off them. The smell is an enum that exists only to be converted.

### Category 4: Wasted Work

#### `Arc<Mutex<T>>` / `Arc<RwLock<T>>` on data never mutated after startup

`[Must]` - every read takes a lock, and a `std::sync::Mutex` serializes all readers.

```rust
use std::sync::Mutex;

// Bad - config is never written after load
let config: Arc<Mutex<Config>> = Arc::new(Mutex::new(Config::load()?));
// Good
let config: Arc<Config> = Arc::new(Config::load()?);
```

`Arc<PgPool>` and `Arc<reqwest::Client>` are the `[Recommend]` cousin: both are already `Arc`-backed handles whose `clone()` is cheap.

#### Owned parameter forcing a clone

```rust
// Bad - an owned-param signature drives a clone per iteration
fn audit(tag: String) { /* reads tag */ }
for tag in &tags { audit(tag.clone()); }

// Good
fn audit(tag: &str) { /* ... */ }
for tag in &tags { audit(tag); }
```

Same shape: `Vec<T>` -> `&[T]`, `Box<T>` -> `&T`. `[Must]` on a request or per-record path, `[Recommend]` elsewhere.

#### Gratuitous `async` and `#[async_trait]`

An `async fn` with no `.await` in its body forces every caller to `.await` a future that does nothing - drop `async`. `#[async_trait]` on a trait never used as `dyn` boxes every call's future; native `async fn` in traits (Rust 1.75+) does not. `[Recommend]`.

### Category 5: Dead Code

Items, request fields or config keys nothing reads (a `pub fn list_by_order` with no caller, a DTO field the handler ignores, a `cfg(feature = "x")` block no `Cargo.toml` or CI invocation enables). `dead_code` does not fire for `pub` items of a library crate, and `#[allow(dead_code)]` hides the rest - so `Redundant because:` no reader, naming the grep that proved it (workspace-wide, including `[features]` and `--features` in CI). `[Recommend]`, unless the dead path also hides a defect - cite it as `Cost:` and label `[Must]`.

## Output Format

Emit one block per finding, ordered `[Must]` first, then `[Recommend]`; within a label, in-hunk findings by file in the order the input listed them then line, then `pre-existing` blocks by path, then owned-by blocks; the consuming workflow merges them. Every finding carries exactly one label:

```
### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}{ pre-existing}

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction | Wasted Work | Dead Code}
- Code: {one-line citation}
- Redundant because: {constraint(s) making the code dead; comma-separate when stacked}
- Cost: {required for [Must]; omit otherwise}
- Recommendation: {concrete edit}
- Justified when: {one-line note if legitimate reason might apply; otherwise omit}
```

`pre-existing` marks a finding outside the PR hunks that the hunks build on. Close with one line `Checked, not flagged: <abstractions whose justification the repo confirmed>` (or `none`). Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not; a range is `file:start-end`. One shape at several sites is one block citing the first site, with the rest named on the `Code:` line; a trait and the `dyn` field consuming it are one shape. For each category with zero findings, emit exactly: `No <category> findings.` (using the category name from the enum) so the workflow knows the check ran; omit the line for categories that have at least one finding. A defect this skill does not own (an `unwrap()` on a request path, an unparameterised query, a missing transaction) is still reported, never dropped: one block per such defect, sorted per the order above, labelled `[Must]` when it risks incorrect behaviour, data loss or a security hole and `[Recommend]` otherwise, with its `Redundant because:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- Flagging `#[derive(Validate)]` rules on request DTOs (that layer owns 422 responses)
- Flagging traits declared at the consumer, or traits that carry a `mockall` mock the tests use
- Flagging `?` propagation (idiomatic; the smell is `let _ =` / `.ok()` - a silent discard)
- Flagging `.clone()` off hot paths, or `Arc<Mutex<T>>` on data more than one task mutates
- Flagging an `#[allow(...)]` that carries a `reason = "..."` or a comment justifying it
