---
name: rust-error-handling
description: "Rust error handling: thiserror for libraries, anyhow for apps, ? and From conversions, panic policy, Option vs Result, boundary mapping."
metadata:
  category: backend
  tags: [rust, error-handling, thiserror, anyhow, result]
user-invocable: false
---

# Rust Error Handling

> Load `Use skill: stack-detect` first to determine the project stack. For Axum `IntoResponse` wiring and response envelopes, defer to `rust-web-patterns`.

## When to Use

- Designing error types for a new crate, module, or service boundary
- Reviewing error handling, panic usage, or `Result`/`Option` choices
- Diagnosing swallowed errors, lost context, or duplicated logs

## Rules

- Libraries define a `thiserror` enum; binaries/apps return `anyhow::Result`. A library never exposes `anyhow::Error` or `Box<dyn Error>` in its public API.
- Propagate with `?`; convert with `#[from]` or `map_err`. Never swallow with `let _ = `, `.ok()`, or `.unwrap_or_default()` on a `Result`.
- `panic!`/`unreachable!`/`todo!`/`.unwrap()`/`.expect()` are for programmer bugs and statically-proven invariants only. Runtime-fallible operations (I/O, DB, parsing, user input, lookups) return `Err`. Prefer `expect("reason")` over `unwrap()`.
- Log OR return, not both. The outermost layer that decides the response logs (at the correct level); inner layers propagate.
- Add context (`.context(...)` or a typed variant) when crossing a boundary where the source error alone is ambiguous.
- `Option` for "absence is normal" (lookup miss as a value); `Result` when absence is a caller-visible error.

## Patterns

### Library: typed errors with thiserror

Variants are caller-matchable outcomes. Carry source errors with `#[from]`, not strings. Add a new variant when callers branch on it; reuse an existing one when they would not.

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

### Application: anyhow with context

```rust
use anyhow::{Context, Result};

fn load_config(path: &Path) -> Result<Config> {
    let raw = fs::read_to_string(path).with_context(|| format!("reading {path:?}"))?;
    toml::from_str(&raw).with_context(|| format!("parsing {path:?}"))
}
```

`with_context` (closure) when the message allocates; `context` for static strings.

### Mapping at the boundary

Distinguish "not found" from other DB failures by mapping the one variant callers branch on; let the rest flow via `#[from]`.

```rust
// Bad: raw sqlx::Error leaks; caller cannot tell "not found" from other failures.
sqlx::query_as!(User, "...", id).fetch_one(&pool).await?

// Good
sqlx::query_as!(User, "...", id).fetch_one(&pool).await
    .map_err(|e| match e {
        sqlx::Error::RowNotFound => DomainError::UserNotFound(id),
        other => other.into(),
    })?
```

### Option vs Result

```rust
// Repo: absence is a value -> Option
async fn find(&self, id: i64) -> Result<Option<User>, DomainError> { ... }

// Service: absence is a caller-visible error -> Result
self.repo.find(id).await?.ok_or(DomainError::UserNotFound(id))
```

### Panic vs error

```rust
// Bad: runtime failures and business conditions
let user = repo.find(id).await.unwrap();
if name.is_empty() { panic!("empty name"); }

// Good: statically-proven invariant only
static RE: OnceLock<Regex> = OnceLock::new();
RE.get_or_init(|| Regex::new(r"^\w+$").expect("static regex compiles"));
```

### Don't swallow

```rust
// Bad: error and rowcount discarded; caller proceeds on phantom success
let _ = sqlx::query!("UPDATE ...").execute(&pool).await;

// Good
let res = sqlx::query!("UPDATE ...").execute(&pool).await?;
if res.rows_affected() == 0 { return Err(DomainError::UserNotFound(id)); }
```

### Transport boundary (Axum)

Library returns `DomainError`; binary implements `IntoResponse` once, logs internal causes there, and returns sanitized bodies.

```rust
impl IntoResponse for DomainError {
    fn into_response(self) -> Response {
        match self {
            DomainError::UserNotFound(_) => (StatusCode::NOT_FOUND, self.to_string()),
            DomainError::InvalidEmail(_) => (StatusCode::BAD_REQUEST, self.to_string()),
            DomainError::Db(e) => {
                tracing::error!(error = ?e, "db failure");
                (StatusCode::INTERNAL_SERVER_ERROR, "internal error".into())
            }
        }.into_response()
    }
}
```

## Output Format

When invoked for review, emit:

```
Findings:
- <file>:<line> | Severity: {Blocker | Major | Minor} | Category: {Panic | Swallow | Conversion | Context | Boundary | Option/Result | Log-Or-Return | Crate-Choice} | <one-line issue>
  Fix: <minimal change>

Error-Type Inventory:
- Crate: <name> | Kind: {Library | Binary} | Error: {thiserror::<Type> | anyhow::Error | Box<dyn Error> | Other:<name>} | Verdict: {OK | Wrong-Kind | Missing}

Boundary Map:
- <from-layer> -> <to-layer>: {Direct | map_err | From/? | IntoResponse} | Verdict: {OK | Leaks-Source | Missing-Context}

Summary: <counts by severity>
```

Category guide: `Swallow` = `let _ =`, `.ok()`, ignored `Result`. `Log-Or-Return` = logged and returned, wrong level on success path, or log inside inner layer. `Crate-Choice` = `anyhow` in a library, `Box<dyn Error>` substituting for a typed error.

If no Rust sources are present, emit `Findings: none (no Rust crates detected)` and stop.

## Avoid

- `anyhow::Error` or `Box<dyn Error>` in a library's public API
- `.unwrap()`/`.expect()`/`panic!`/`unreachable!`/`todo!` on runtime-fallible operations or expected conditions
- Swallowing results with `let _ =`, `.ok()`, or `.unwrap_or_default()` on a `Result`
- String-matching `err.to_string()` instead of matching variants
- Logging at every layer (duplicate noise) or logging from `Display`/`Debug` impls
- Leaking source error text (DB messages, file paths) into HTTP response bodies
