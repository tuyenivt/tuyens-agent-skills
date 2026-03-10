---
name: rust-error-handling
description: "Rust error patterns: Result<T, E>, thiserror for libraries, anyhow for applications, custom error types, error propagation with ?, error mapping at layer boundaries."
user-invocable: false
---

# Rust Error Handling

## When to Use

- Designing error types for a new crate or service module
- Reviewing error handling in a code review
- Debugging unexpected error behavior (swallowed errors, lost context)
- Implementing centralized error handling in an Axum HTTP service

## Rules

- Never use `.unwrap()` or `.expect()` in production paths - use `?` operator for propagation
- Use `thiserror` for library/domain error types - derives `std::error::Error` with zero boilerplate
- Use `anyhow` for application-level error handling - provides context chaining
- Map errors at each boundary: repo errors -> service errors -> HTTP status codes
- Log OR return an error at each layer - never both (log-and-return duplicates noise)
- Panic only for programmer bugs (invariant violations at startup) - never for business logic
- Use `Result<T, E>` everywhere - never sentinel values or error codes

## Patterns

### thiserror for Domain Errors

Use for library and domain errors where callers need to match on variants:

```rust
use thiserror::Error;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("resource not found: {0}")]
    NotFound(String),

    #[error("validation failed: {0}")]
    Validation(String),

    #[error("unauthorized")]
    Unauthorized,

    #[error("database error")]
    Database(#[from] sqlx::Error),

    #[error("unexpected error")]
    Internal(#[from] anyhow::Error),
}
```

### anyhow for Application Code

Use for top-level application code where you don't need callers to match variants:

```rust
use anyhow::{Context, Result};

fn load_config(path: &str) -> Result<Config> {
    let content = std::fs::read_to_string(path)
        .context("failed to read config file")?;
    let config: Config = toml::from_str(&content)
        .context("failed to parse config")?;
    Ok(config)
}
```

### Error Propagation with ?

Always add context when propagating errors up the call stack:

```rust
// Bad - caller has no context where the error originated
async fn get_user(pool: &PgPool, id: i64) -> Result<User, sqlx::Error> {
    sqlx::query_as!(User, "SELECT * FROM users WHERE id = $1", id)
        .fetch_one(pool)
        .await
}

// Good - each layer adds its context
async fn get_user(pool: &PgPool, id: i64) -> Result<User, AppError> {
    sqlx::query_as!(User, "SELECT * FROM users WHERE id = $1", id)
        .fetch_one(pool)
        .await
        .map_err(|e| match e {
            sqlx::Error::RowNotFound => AppError::NotFound(format!("user {id}")),
            _ => AppError::Database(e),
        })
}
```

### Error Chain: Repo -> Service -> Handler

Map errors at each layer boundary rather than leaking implementation details:

```rust
// Repository layer: returns data access errors
impl UserRepository {
    async fn find_by_id(&self, id: i64) -> Result<User, AppError> {
        sqlx::query_as!(User, "SELECT * FROM users WHERE id = $1", id)
            .fetch_optional(&self.pool)
            .await
            .map_err(AppError::Database)?
            .ok_or_else(|| AppError::NotFound(format!("user {id}")))
    }
}

// Service layer: maps to business errors
impl UserService {
    async fn get_user(&self, id: i64) -> Result<UserDto, AppError> {
        let user = self.repo.find_by_id(id).await?;
        Ok(user.into())
    }
}

// Handler layer: maps to HTTP responses
async fn get_user(
    State(svc): State<Arc<UserService>>,
    Path(id): Path<i64>,
) -> Result<Json<UserDto>, AppError> {
    let user = svc.get_user(id).await?;
    Ok(Json(user))
}
```

### Axum Error Response Mapping

```rust
use axum::response::{IntoResponse, Response};
use axum::http::StatusCode;

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, message) = match &self {
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg.clone()),
            AppError::Validation(msg) => (StatusCode::BAD_REQUEST, msg.clone()),
            AppError::Unauthorized => (StatusCode::UNAUTHORIZED, "unauthorized".into()),
            AppError::Database(e) => {
                tracing::error!("database error: {e}");
                (StatusCode::INTERNAL_SERVER_ERROR, "internal server error".into())
            }
            AppError::Internal(e) => {
                tracing::error!("internal error: {e}");
                (StatusCode::INTERNAL_SERVER_ERROR, "internal server error".into())
            }
        };

        (status, axum::Json(serde_json::json!({"error": message}))).into_response()
    }
}
```

## Anti-Patterns

```rust
// Bad: unwrap in production code
let user = get_user(id).await.unwrap();

// Bad: log AND return (double-reporting)
if let Err(e) = do_something().await {
    tracing::error!("failed: {e}");
    return Err(e); // already logged, will be logged again upstream
}

// Bad: string matching on errors
if err.to_string().contains("not found") { ... }

// Bad: panic for expected business conditions
if user.is_none() {
    panic!("user not found");
}

// Bad: returning generic errors without context
Err(anyhow::anyhow!("failed"))
```

## Avoid

- `.unwrap()` or `.expect()` in fallible production paths
- Using `panic!` for flow control or expected conditions
- String matching on error messages
- Logging and returning at the same layer
- Leaking database or internal error details to HTTP clients
- Using `Box<dyn Error>` when `thiserror` or `anyhow` would be clearer
