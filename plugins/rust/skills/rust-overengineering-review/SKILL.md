---
name: rust-overengineering-review
description: Rust necessity review - validator vs sqlx/types, single-impl traits, Box<dyn> hot path, Arc<Mutex<T>> read-only, hot-loop clones, dead cfg.
metadata:
  category: backend
  tags: [rust, axum, sqlx, code-review, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

Reviewing a Rust diff that adds validator derives, defensive guards, traits, `Box<dyn>`, generics, `async`, `Arc<Mutex<T>>`, `.clone()`, or `cfg(feature)`.

Rust's type system, `Option`/`Result`, exhaustive `match`, and the borrow checker eliminate most categories other stacks worry about. Empty sections are correct. Skip anything `cargo clippy --all-targets -- -D warnings` would catch.

## Rules

- Every finding cites the constraint making the code redundant: validator rule, sqlx column type, unique index, type system, exhaustive `match`, framework guarantee, or repo-wide grep showing no consumer.
- Intent:
  - `[Must]` requires a `Cost:` field. Reserved for measurable waste: extra query in a hot path, dynamic dispatch on a single-callsite hot path, lock on never-mutated data, hot-loop allocation.
  - `[Question]` when justification is plausible but not visible in the diff.
  - `[Recommend]` otherwise.
- A redundancy with visible justification (mock derive, second impl, public API, hot-path benchmark) is not a finding.
- Collapse co-located findings into one block when they share a root cause (e.g., `Box<dyn Trait>` field plus its single-impl trait declared in the same module -> one finding citing both lines).

## Patterns

### Category 1: Redundant validation vs sqlx / DB / type system

Stack: type system -> `validator::Validate` -> sqlx column type -> DB schema. Axum + `ValidatedJson` returns 400 before the handler runs.

No-op or type-shadowing rules:

```rust
// Bad - String cannot be None; min=0 always passes
#[validate(required)] customer_id: String,
#[validate(length(min = 0))] note: String,

// Bad - validator already rejected empty/missing
if req.customer_id.is_empty() { return Err(AppError::Validation(...)); }
```

Manual unique-check before `INSERT` - `[Must]`, races and adds a query per write:

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

```rust
// Bad - Result<T, E> where E is never constructed
fn total(items: &[LineItem]) -> Result<i64, AppError> {
    Ok(items.iter().map(|i| i.price_cents * i.qty).sum())
}

// Bad - non-Option target
let total: i64 = order.total.unwrap_or_default();

// Bad - catch-all drops the source
.map_err(|_| AppError::Internal("db".into()))
```

Justified when a trait signature requires `Result` or a fallible branch lands in the same PR. Sentinel errors faked to signal business state (`return Err(sqlx::Error::RowNotFound)` on a conflict) -> recommend a typed error variant.

### Category 3: Premature abstraction

Single-impl trait declared next to its only impl - `[Must]` when the trait is module-private, has no `mockall` mock, and the `Box<dyn>` consumer sits in the same module:

```rust
// Bad - trait + only impl in the same module, no mock, no second impl
pub trait OrderRepository { async fn find(&self, id: i64) -> ...; }
pub struct PgOrderRepository { pool: PgPool }
impl OrderRepository for PgOrderRepository { /* ... */ }

// Good - export the struct; consumer declares the trait it needs
pub struct OrderService<R: OrderRepo> { repo: R }
```

`Box<dyn Trait>` on a single-callsite hot path - `[Must]`:

```rust
// Bad
async fn handle(svc: Box<dyn OrderService>) -> ... { svc.fulfill().await }

// Good
async fn handle<S: OrderService>(svc: S) -> ... { svc.fulfill().await }
```

Justified for heterogeneous collections (`Vec<Box<dyn Trait>>`) or object-safe FFI boundaries. Justified at the trait-declaration site when (a) `#[cfg(test)] mockall` derives a mock, (b) two or more concrete impls exist, or (c) the trait is a documented public API.

`Arc<Mutex<T>>` on never-mutated data - `[Must]`. Applies to config, handles, repos cloned once at startup:

```rust
// Bad - never mutates; lock serializes readers
let config: Arc<Mutex<Config>> = Arc::new(Mutex::new(Config::load()?));

// Good
let config: Arc<Config> = Arc::new(Config::load()?);
```

### Category 4: Wasted work and dead branches

Owned parameter where a borrow suffices, especially with a hot-loop call site - `[Must]`:

```rust
// Bad - hot-loop clone driven by an owned-param signature
for tag in &tags { audit(tag.clone()); }
fn audit(tag: String) { ... }

// Good
for tag in &tags { audit(tag); }
fn audit(tag: &str) { ... }
```

Same shape: `Vec<T>` -> `&[T]`, `String` -> `&str`, `Box<T>` -> `&T`. `[Recommend]` outside hot paths.

Gratuitous `async` - `async fn` with no `.await` in the body inflates the `Future` and forces every caller to `.await`. Drop `async` or expose the underlying value.

Speculative `cfg(feature)` flags - feature-gated code with no consumer enabling the feature anywhere in the workspace. Confirm with a repo-wide grep of `Cargo.toml` `[features]` blocks and `--features` invocations before flagging.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Must | Recommend | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction | Wasted Work}
- Code: {one-line citation, or multiple lines if collapsed}
- Redundant because: {validator rule | sqlx column type | unique index | type system | exhaustive match | framework guarantee | no consumer of feature}
- Cost: {extra query | dynamic dispatch on hot path | lock on read-only data | hot-loop allocation | gratuitous async | dead branch}
- Recommendation: {concrete edit}
- Justified when: {one-line note when a legitimate reason might apply, else omit}
```

`Cost:` is required for `[Must]` and omitted otherwise. For each of the four categories with no findings, state `No <category> findings.` so the consuming workflow sees the check ran.

## Avoid

- Padding to match other stacks. The type system genuinely eliminates most categories.
- Flagging `validator::Validate` derives on request DTOs - that layer owns 400 responses.
- Flagging traits declared at the consumer (idiomatic Rust); only flag traits declared at the impl side.
- Flagging `.clone()` outside hot paths or `Arc<Mutex<T>>` on data mutated from multiple tasks.
- Splitting one root cause into multiple findings (`Box<dyn>` field + its single-impl trait in the same module -> one block).
- Recommending removal of `#[allow(...)]` lints that carry a `// reason:` comment.
- Reporting anything `cargo clippy --all-targets -- -D warnings` would already catch.
