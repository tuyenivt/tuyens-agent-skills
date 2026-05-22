---
name: rust-error-handling
description: "Rust error handling: thiserror for libraries, anyhow for apps, ? and From conversions, panic policy, Option vs Result, boundary mapping."
metadata:
  category: backend
  tags: [rust, error-handling, thiserror, anyhow, result]
user-invocable: false
---

# Rust Error Handling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing error types for a new crate, module, or service boundary
- Reviewing error handling, panic usage, or `Result`/`Option` choices
- Diagnosing swallowed errors, lost context, or duplicated logs
- Wiring errors to HTTP responses or other transport layers

## Rules

- Libraries define a `thiserror` enum; binaries/apps return `anyhow::Result`. A library never returns `anyhow::Error` to its callers.
- Propagate with `?`; convert with `#[from]` or `map_err`. No `Box<dyn Error>` unless erasing across plugin boundaries.
- `.unwrap()`/`.expect()` only on statically-proven invariants (e.g., compiled regex, `OnceLock` post-init). `expect("…")` with a reason, never `unwrap()`.
- `panic!`/`unreachable!`/`todo!` are for programmer bugs, not runtime conditions. Missing rows, bad input, and I/O failures return `Err`.
- Log OR return, not both. The outermost layer that decides the response logs; inner layers propagate.
- Add context (`.context(...)` or a typed variant) at every boundary crossing where the source error alone would be ambiguous.
- Use `Option` for "absence is normal" (lookup miss as a value); use `Result` when absence is a caller-visible error.

## Patterns

### Library: typed errors with thiserror

Variants are caller-matchable outcomes. Carry source errors with `#[from]`, not strings.

```rust
#[derive(Debug, thiserror::Error)]
pub enum DomainError {
    #[error("user {0} not found")]
    UserNotFound(i64),
    #[error("invalid email: {0}")]
    InvalidEmail(String),
    #[error(transparent)]
    Db(#[from] sqlx::Error),
}
```

Flatten vs nest: add a new variant when callers branch on it; reuse an existing one when they would not.

### Application: anyhow with context

```rust
use anyhow::{Context, Result};

fn load_config(path: &Path) -> Result<Config> {
    let raw = fs::read_to_string(path).with_context(|| format!("reading {path:?}"))?;
    toml::from_str(&raw).with_context(|| format!("parsing {path:?}"))
}
```

Use `with_context` (closure) when the message allocates; `context` for static strings.

### Conversions: `?`, `From`, `map_err`

```rust
// Bad: raw source error leaks; caller cannot tell "not found" from other DB failures.
async fn find(id: i64) -> Result<User, sqlx::Error> {
    sqlx::query_as!(User, "...", id).fetch_one(&pool).await
}

// Good: map RowNotFound to a typed variant, let other DB errors flow via #[from].
async fn find(id: i64) -> Result<User, DomainError> {
    sqlx::query_as!(User, "...", id).fetch_one(&pool).await
        .map_err(|e| match e {
            sqlx::Error::RowNotFound => DomainError::UserNotFound(id),
            other => other.into(),
        })
}
```

### Option vs Result at boundaries

```rust
// Repo: absence is a value -> Option
async fn find(&self, id: i64) -> Result<Option<User>, DomainError> { ... }

// Service: absence is a caller-visible error -> Result
async fn get(&self, id: i64) -> Result<User, DomainError> {
    self.repo.find(id).await?.ok_or(DomainError::UserNotFound(id))
}
```

### Panic policy

```rust
// Bad
let user = repo.find(id).await.unwrap();          // runtime failure
if name.is_empty() { panic!("empty name"); }       // business condition

// Good
static RE: OnceLock<Regex> = OnceLock::new();
RE.get_or_init(|| Regex::new(r"^\w+$").expect("static regex compiles"));
```

`unreachable!` is allowed only after exhaustive matches the compiler cannot prove; prefer refactoring the type to remove it.

### Transport boundary (Axum example)

The library returns `DomainError`. The binary implements `IntoResponse` once, logs internal causes, and returns sanitized bodies. Detailed handler wiring lives in `rust-axum-handler`.

```rust
impl IntoResponse for DomainError {
    fn into_response(self) -> Response {
        match self {
            DomainError::UserNotFound(_)  => (StatusCode::NOT_FOUND, self.to_string()),
            DomainError::InvalidEmail(_)  => (StatusCode::BAD_REQUEST, self.to_string()),
            DomainError::Db(e) => {
                tracing::error!(error = ?e, "db failure");
                (StatusCode::INTERNAL_SERVER_ERROR, "internal error".into())
            }
        }.into_response()
    }
}
```

## Output Format

When this skill is invoked for review, emit:

```
Findings:
- <file>:<line> | Severity: {Blocker | Major | Minor} | Category: {Panic | Conversion | Context | Boundary | Option/Result | Crate-Choice} | <one-line issue>
  Fix: <minimal change>

Error-Type Inventory:
- Crate: <name> | Kind: {Library | Binary} | Error: {thiserror::<Type> | anyhow::Error | Other:<name>} | Verdict: {OK | Wrong-Kind | Missing}

Boundary Map:
- <from-layer> -> <to-layer>: {Direct | map_err | From/? | IntoResponse} | Verdict: {OK | Leaks-Source | Missing-Context}

Summary: <counts by severity>
```

If no Rust sources are present, emit `Findings: none (no Rust crates detected)` and stop.

## Avoid

- `anyhow::Error` in a library's public API
- `.unwrap()`/`.expect()` on runtime-fallible operations
- `panic!`/`unreachable!`/`todo!` for expected conditions or unfinished features in shipped code
- String-matching `err.to_string()` instead of matching variants
- Logging at every layer (duplicate noise); logging only inside `Display`/`Debug` impls
- `Box<dyn Error>` as a substitute for designing a typed error
- Leaking source error text (DB messages, file paths) into HTTP response bodies
