---
name: rust-overengineering-review
description: Rust necessity review - validator-crate vs sqlx/DB/type system, single-impl traits, Box<dyn Trait> hot path, Arc<Mutex<T>> on immutable data.
metadata:
  category: backend
  tags: [rust, axum, sqlx, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing a Rust diff that adds `validator` derives, defensive guards, traits, `Box<dyn Trait>` parameters, or new abstractions
- Catching code that is correct, performant, and safe - but does not need to exist

**Scope note.** Rust's type system, `Option<T>` / `Result<T, E>`, exhaustive matching, and the borrow checker eliminate most categories this skill family targets elsewhere. Empty sections are honest. If a finding could be a clippy lint, check `cargo clippy --all-targets -- -D warnings` first.

## Rules

- Every finding cites the constraint making the code redundant: FK name, sqlx column constraint, validator-crate rule, type-system guarantee, exhaustive `match`, or compile-time contract.
- Severity:
  - **Default `[Suggestion]`.** Cite the constraint, recommend the edit.
  - **`[High]`** when a measurable cost is present. Cite the cost in the `Cost:` field. Triggers:
    - Extra SELECT in a hot path
    - `Box<dyn Trait>` on a single-callsite hot path (dynamic dispatch with one concrete type)
    - `Arc<Mutex<T>>` on data that never mutates
    - `.clone()` on a hot-loop value where a `&str` would suffice
  - **`[Question]`** when justification is plausible but not visible in the diff.
- A redundancy with **visible** justification is not a finding. See `Avoid` for the canonical exceptions.

## Patterns

### Category 1: Redundant validation vs sqlx / DB / type system

Validation stack: **type system (`String` vs `Option<String>`) -> validator-crate `#[validate]` -> sqlx column type -> DB schema**. Axum extractors + `validator::Validate` return 400 before the handler runs. sqlx's compile-time-checked queries surface column nullability at compile time.

#### `#[validate(required)]` on a non-Optional field

```rust
// Bad - the type is String (not Option<String>); serde rejects missing/null at deserialization
#[derive(Deserialize, Validate)]
struct CreateOrderRequest {
    #[validate(required)] customer_id: String,         // dead - String cannot be None
    #[validate(range(min = 1))] total_cents: i64,
}
```

`#[validate(required)]` is appropriate on `Option<T>` fields where the business rule disallows null.

#### Manual length / null guard after validator-checked input

```rust
// Bad - validator::Validate rejected the request before this handler ran
async fn create_order(ValidatedJson(req): ValidatedJson<CreateOrderRequest>) -> ... {
    if req.customer_id.is_empty() {                    // #[validate(length(min = 1))] already rejected
        return Err(AppError::Validation("customer_id required".into()));
    }
}
```

#### Manual unique-check before `INSERT`

`[High]` - races and adds a query per write; the unique index decides anyway.

```rust
// Bad
let existing = sqlx::query!("SELECT id FROM users WHERE email = $1", req.email)
    .fetch_optional(&state.db).await?;
if existing.is_some() { return Err(AppError::Conflict("email taken".into())); }
sqlx::query!("INSERT INTO users (email) VALUES ($1)", req.email).execute(&state.db).await?;

// Good - let the unique index decide; translate at the catch site
sqlx::query!("INSERT INTO users (email) VALUES ($1)", req.email).execute(&state.db).await
    .map_err(|e| match e {
        sqlx::Error::Database(de) if de.code().as_deref() == Some("23505") => AppError::Conflict("email taken".into()),
        other => other.into(),
    })?;
```

### Category 2: Defensive code for impossible states

The compiler enforces exhaustive matching, non-null references, and `Result` propagation. Most defensive patterns are caught by the type system or clippy. The remaining cases are interpretive - the compiler can't tell whether you're guarding a real possibility or one already enforced.

#### `match` / `if let` arm for a proven-unreachable variant that swallows context

```rust
// Bad - the catch-all loses useful error context
match sqlx::query!("...").execute(&state.db).await {
    Ok(_) => Ok(()),
    Err(sqlx::Error::Database(e)) if e.code().as_deref() == Some("23505") => Err(AppError::Conflict(...)),
    Err(_) => Err(AppError::Internal("unknown".into())),   // loses the original error
}

// Good - propagate the real error
sqlx::query!("...").execute(&state.db).await.map_err(|e| match e {
    sqlx::Error::Database(de) if de.code().as_deref() == Some("23505") => AppError::Conflict(...),
    other => other.into(),
})?;
```

#### `Result<T, E>` where `E` is never constructed

```rust
// Bad - this function only ever returns Ok; the Result wrapper is dead
fn order_total(order: &Order) -> Result<i64, AppError> {
    Ok(order.line_items.iter().map(|i| i.price_cents * i.qty).sum())
}
```

Justified when the function may grow a fallible branch in the same PR or when a trait signature requires `Result`.

#### `.unwrap_or_default()` on a value that is already `T`, not `Option<T>`

```rust
// Bad - .ok_or(...)? unwrapped to Order; chaining .unwrap_or_default() on a non-Option field is dead
let order: Order = state.db.find(id).await?.ok_or(AppError::NotFound)?;
let total: i64 = order.total.unwrap_or_default();  // order.total is i64, not Option<i64>
```

### Category 3: Premature abstraction

#### Single-impl trait declared at the implementation

`[High]` when the trait is declared in the same module as its only `impl` and no `#[cfg(test)] mockall` derive exists. Like Go's "accept interfaces, return structs" - the trait belongs to the **consumer**.

```rust
// Bad - trait + only impl in the same module; no mock; no second implementer
mod repository {
    #[async_trait] pub trait OrderRepository {
        async fn find(&self, id: i64) -> Result<Order, sqlx::Error>;
    }
    pub struct PgOrderRepository { pool: PgPool }
    #[async_trait] impl OrderRepository for PgOrderRepository { /* ... */ }
}

// Good - export the struct; the consumer declares a trait it needs
mod service {
    #[async_trait] pub trait OrderRepo {
        async fn find(&self, id: i64) -> Result<Order, sqlx::Error>;
    }
    pub struct OrderService<R: OrderRepo> { repo: R }
}
```

Justified when (a) `mockall` generates a mock for tests, (b) two or more concrete impls exist, or (c) the trait is a documented public API.

#### `Box<dyn Trait>` on a single-callsite hot path

`[High]` - dynamic dispatch where the caller has one concrete type.

```rust
// Bad
async fn handle(svc: Box<dyn OrderService>) -> Result<OrderResponse, AppError> { svc.fulfill(...).await }

// Good - generic / static dispatch
async fn handle<S: OrderService>(svc: S) -> Result<OrderResponse, AppError> { svc.fulfill(...).await }
```

Justified when callers store heterogeneous impls (`Vec<Box<dyn Trait>>`), pass across an object-safe FFI boundary, or the cost is negligible on a cold path.

#### `Arc<Mutex<T>>` on data that never mutates

```rust
// Bad - Config set at startup and only read
let config: Arc<Mutex<Config>> = Arc::new(Mutex::new(Config::load()?));

// Good
let config: Arc<Config> = Arc::new(Config::load()?);
```

`RwLock<T>` for read-heavy, occasionally-mutated state. `Mutex<T>` only when writes are frequent enough that the read-write split adds overhead.

#### `.clone()` on a hot-loop value where `&str` would do

```rust
// Bad - one allocation per iteration
for item in &items { process(item.name.clone()); }   // process takes &str

// Good
for item in &items { process(&item.name); }
```

#### Speculative `cfg(feature)` flags

```rust
// Bad - feature-gated functions; no Cargo.toml consumer enables them
#[cfg(feature = "audit")] fn audit(order: &Order) { /* ... */ }
```

Confirm with a repo-wide grep before flagging.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `#[validate(required)]` on non-Optional `customer_id: String`}
- Redundant because: {FK name | sqlx column constraint | unique index | type system | validator-crate rule | exhaustive match | framework guarantee}
- Cost: {extra SELECT per save | dynamic dispatch on hot path | hot-loop allocation | wrong lock shape} _(required for `[High]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a legitimate reason might apply; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow knows the check ran. Empty sections are common and correct for Rust.

## Avoid

- Padding findings to match other stacks - the type system genuinely eliminates most categories
- Flagging `validator::Validate` derives on request DTOs - that layer owns user-facing 400 responses
- Flagging traits declared at the consumer - that's idiomatic Rust. Only flag traits declared at the implementation side
- Flagging `Box<dyn Trait>` when callers store heterogeneous impls or pass it across an object-safe FFI boundary
- Flagging `Arc<Mutex<T>>` on data that genuinely mutates from multiple tasks
- Flagging `.clone()` on `String` / `Vec<T>` outside hot paths - reserve `[High]` for genuine hot paths
- Recommending the removal of clippy lints (`#[allow(...)]` with a `// reason:` is the legitimate suppression pattern)
- Confusing "duplicated" with "defense in depth across layers" when multiple write paths exist
- Flagging anything `cargo clippy --all-targets -- -D warnings` would already catch
