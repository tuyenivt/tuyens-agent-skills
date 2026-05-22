---
name: rust-overengineering-review
description: Rust necessity review - validator vs sqlx/types, single-impl traits, Box<dyn> hot path, Arc<Mutex<T>> on read-only data, owned params, dead async.
metadata:
  category: backend
  tags: [rust, axum, sqlx, code-review, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing a Rust diff that adds validator derives, defensive guards, traits, `Box<dyn>`, generics, `async`, or new abstractions.
- Catching code that is correct, performant, and safe but does not need to exist.

Rust's type system, `Option`/`Result`, exhaustive `match`, and the borrow checker already eliminate many categories this skill targets elsewhere. Empty sections are correct. Skip anything `cargo clippy --all-targets -- -D warnings` would catch.

## Rules

- Every finding cites the constraint making the code redundant: validator rule, sqlx column type, unique index, type system, exhaustive `match`, framework guarantee, or repo-wide grep.
- Severity:
  - `[High]` requires a `Cost:` field. Triggers: extra query in a hot path, dynamic dispatch on a single-callsite hot path, wrong lock shape on read-only data, hot-loop allocation.
  - `[Question]` when justification is plausible but not visible in the diff.
  - `[Suggestion]` otherwise.
- A redundancy with visible justification (mock derive, second impl, public API, hot-path benchmark) is not a finding.

## Patterns

### Category 1: Redundant validation vs sqlx / DB / type system

Stack: type system -> `validator::Validate` -> sqlx column type -> DB schema. Axum + `ValidatedJson` returns 400 before the handler runs.

`#[validate(required)]` on a non-`Option` field:

```rust
// Bad - String cannot be None; serde rejects missing/null
#[validate(required)] customer_id: String,
```

Manual guard after `ValidatedJson`:

```rust
// Bad - validator already rejected empty/missing
if req.customer_id.is_empty() { return Err(AppError::Validation(...)); }
```

Manual unique-check before `INSERT` - `[High]`, races and adds a query per write:

```rust
// Bad
let existing = sqlx::query!("SELECT id FROM users WHERE email = $1", req.email)
    .fetch_optional(&db).await?;
if existing.is_some() { return Err(AppError::Conflict(...)); }
sqlx::query!("INSERT INTO users (email) VALUES ($1)", req.email).execute(&db).await?;

// Good - let the unique index decide
sqlx::query!("INSERT INTO users (email) VALUES ($1)", req.email).execute(&db).await
    .map_err(|e| match e {
        sqlx::Error::Database(de) if de.code().as_deref() == Some("23505") => AppError::Conflict(...),
        other => other.into(),
    })?;
```

### Category 2: Defensive code for impossible states

Catch-all that swallows error context:

```rust
// Bad - .map_err(|_| ...) drops the source
.map_err(|_| AppError::Internal("db".into()))

// Good
.map_err(AppError::from)
```

`Result<T, E>` where `E` is never constructed:

```rust
// Bad - only ever returns Ok
fn total(items: &[LineItem]) -> Result<i64, AppError> {
    Ok(items.iter().map(|i| i.price_cents * i.qty).sum())
}
```

Justified when a trait signature requires `Result` or a fallible branch lands in the same PR.

`.unwrap_or_default()` on non-`Option`:

```rust
// Bad - order.total is i64, not Option<i64>
let total: i64 = order.total.unwrap_or_default();
```

Sentinel errors faked to signal business state (`return Err(sqlx::Error::RowNotFound)` on a conflict) - flag and recommend a typed error variant.

### Category 3: Premature abstraction

Single-impl trait declared next to its only impl - `[High]` when no `mockall` mock exists and the trait is module-private:

```rust
// Bad - trait + only impl in the same module, no mock, no second impl
pub trait OrderRepository { async fn find(&self, id: i64) -> ...; }
pub struct PgOrderRepository { pool: PgPool }
impl OrderRepository for PgOrderRepository { /* ... */ }

// Good - export the struct; consumer declares the trait it needs
pub struct OrderService<R: OrderRepo> { repo: R }
```

Justified when (a) `#[cfg(test)] mockall` derives a mock, (b) two or more concrete impls exist, or (c) the trait is a documented public API.

`Box<dyn Trait>` on a single-callsite hot path - `[High]`, dynamic dispatch with one concrete caller:

```rust
// Bad
async fn handle(svc: Box<dyn OrderService>) -> ... { svc.fulfill().await }

// Good - static dispatch
async fn handle<S: OrderService>(svc: S) -> ... { svc.fulfill().await }
```

Justified for heterogeneous collections (`Vec<Box<dyn Trait>>`) or object-safe FFI boundaries.

`Arc<Mutex<T>>` on read-only data - `[High]`. Applies to config, handles, repos cloned once at startup:

```rust
// Bad - never mutates; lock serializes readers
let config: Arc<Mutex<Config>> = Arc::new(Mutex::new(Config::load()?));
let repo: Arc<Mutex<Box<dyn OrderRepository>>> = ...;

// Good
let config: Arc<Config> = Arc::new(Config::load()?);
let repo: Arc<PgOrderRepository> = ...;
```

`RwLock<T>` only when reads dominate and writes still happen. `Mutex<T>` only for frequent writes.

Owned parameters where a borrow suffices - flag both the call site and the signature:

```rust
// Bad - hot-loop clone and a signature forcing it
for tag in &tags { audit(tag.clone()); }
fn audit(tag: String) { ... }

// Good
for tag in &tags { audit(tag); }
fn audit(tag: &str) { ... }
```

Same shape for `Vec<T>` -> `&[T]`, `String` -> `&str`, `Box<T>` -> `&T`. `[High]` on hot loops; `[Suggestion]` otherwise.

Gratuitous `async` - an `async fn` with no `.await` in the body inflates `Future` size and forces every caller to `.await`. Remove `async` or call the underlying future directly.

Excessive generics - a type parameter used at one call site with one concrete type, no trait bound that varies, no `mockall::predicate` usage. Replace `fn run<S: AsRef<str>>(s: S)` with `fn run(s: &str)` when callers all pass `&str`.

Unused parameters - functions with `_`-prefixed or `#[allow(unused)]` parameters that no caller supplies meaningfully. Flag as `[Suggestion]` if not tied to a trait signature.

Speculative `cfg(feature)` flags - feature-gated code with no consumer enabling the feature. Confirm with a repo-wide grep before flagging.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation}
- Redundant because: {validator rule | sqlx column type | unique index | type system | exhaustive match | framework guarantee | no consumer of feature}
- Cost: {extra query | dynamic dispatch on hot path | lock on read-only data | hot-loop allocation | wrong async shape}
- Recommendation: {concrete edit}
- Justified when: {one-line note when a legitimate reason might apply, else omit}
```

`Cost:` is required for `[High]` and omitted otherwise. For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow sees the check ran.

## Avoid

- Padding to match other stacks. The type system genuinely eliminates most categories.
- Flagging `validator::Validate` derives on request DTOs - that layer owns 400 responses.
- Flagging traits declared at the consumer (idiomatic Rust); only flag traits declared at the impl side.
- Flagging `.clone()` outside hot paths or `Arc<Mutex<T>>` on data that mutates from multiple tasks.
- Recommending removal of `#[allow(...)]` lints that carry a `// reason:` comment.
- Reporting anything `cargo clippy --all-targets -- -D warnings` would already catch.
