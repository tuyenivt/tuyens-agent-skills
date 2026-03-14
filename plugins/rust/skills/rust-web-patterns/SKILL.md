---
name: rust-web-patterns
description: "Axum web framework patterns: routing, middleware with tower, extractors, request validation, consistent JSON responses, pagination, graceful shutdown, health endpoints."
user-invocable: false
---

# Rust Web Patterns (Axum)

## When to Use

- Structuring a new Axum HTTP service or reviewing an existing one
- Implementing middleware (auth, logging, rate limiting, error handling)
- Designing consistent API request/response contracts
- Adding health and readiness endpoints for Kubernetes or load balancers
- Implementing graceful shutdown for zero-downtime deploys

## Rules

- No business logic in handlers - handlers orchestrate, services execute
- Never access the database directly in handlers - delegate to service/repository
- Use tower middleware for cross-cutting concerns - composable and testable
- Return consistent response envelopes for all endpoints (success and error)
- Validate all input at the handler boundary using extractors and serde

## Patterns

### Router Structure

```rust
use axum::{Router, routing::{get, post}};
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;

fn build_router(state: AppState) -> Router {
    let public = Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready));

    let api = Router::new()
        .route("/users", get(list_users).post(create_user))
        .route("/users/{id}", get(get_user))
        .layer(axum::middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ));

    Router::new()
        .merge(public)
        .nest("/api/v1", api)
        .layer(TraceLayer::new_for_http())
        .layer(CorsLayer::permissive()) // tighten for production
        .with_state(state)
}
```

### Request Validation with Extractors

```rust
use axum::extract::{Json, Path, Query, State};
use serde::Deserialize;
use validator::Validate;

#[derive(Debug, Deserialize, Validate)]
pub struct CreateUserRequest {
    #[validate(length(min = 2, max = 100))]
    pub name: String,
    #[validate(email)]
    pub email: String,
    #[validate(range(min = 0, max = 130))]
    pub age: Option<i32>,
}

async fn create_user(
    State(svc): State<Arc<UserService>>,
    Json(req): Json<CreateUserRequest>,
) -> Result<(StatusCode, Json<UserDto>), AppError> {
    req.validate().map_err(|e| AppError::Validation(e.to_string()))?;
    let user = svc.create(req).await?;
    Ok((StatusCode::CREATED, Json(user)))
}

#[derive(Debug, Deserialize)]
pub struct ListUsersQuery {
    #[serde(default = "default_page")]
    pub page: i64,
    #[serde(default = "default_page_size")]
    pub page_size: i64,
    pub status: Option<String>,
}

fn default_page() -> i64 { 1 }
fn default_page_size() -> i64 { 20 }
```

### Consistent Response Envelope

```rust
use serde::Serialize;

#[derive(Serialize)]
pub struct ApiResponse<T: Serialize> {
    pub data: T,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub meta: Option<PaginationMeta>,
}

#[derive(Serialize)]
pub struct PaginationMeta {
    pub page: i64,
    pub page_size: i64,
    pub total_items: i64,
    pub total_pages: i64,
}

#[derive(Serialize)]
pub struct ErrorBody {
    pub error: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code: Option<String>,
}
```

### Authentication Middleware

```rust
use axum::{extract::Request, middleware::Next, response::Response};

async fn auth_middleware(
    State(state): State<AppState>,
    mut req: Request,
    next: Next,
) -> Result<Response, AppError> {
    let token = req.headers()
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .ok_or(AppError::Unauthorized)?;

    let claims = state.jwt.validate(token)
        .map_err(|_| AppError::Unauthorized)?;

    req.extensions_mut().insert(claims);
    Ok(next.run(req).await)
}
```

### Health and Readiness Endpoints

```rust
async fn health() -> (StatusCode, Json<serde_json::Value>) {
    (StatusCode::OK, Json(serde_json::json!({"status": "ok"})))
}

async fn ready(State(state): State<AppState>) -> Result<Json<serde_json::Value>, AppError> {
    sqlx::query("SELECT 1")
        .execute(&state.pool)
        .await
        .map_err(|_| AppError::Internal(anyhow::anyhow!("database not ready")))?;
    Ok(Json(serde_json::json!({"status": "ready"})))
}
```

### Graceful Shutdown

```rust
use tokio::net::TcpListener;
use tokio::signal;

async fn serve(app: Router) -> anyhow::Result<()> {
    let listener = TcpListener::bind("0.0.0.0:8080").await?;
    tracing::info!("listening on {}", listener.local_addr()?);

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async { signal::ctrl_c().await.unwrap() };
    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .unwrap()
            .recv()
            .await;
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}
```

### AppError with IntoResponse

Define a centralized error type that implements `IntoResponse` to map domain errors to HTTP status codes consistently:

```rust
use axum::{http::StatusCode, response::{IntoResponse, Response}, Json};
use serde_json::json;

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("not found")]
    NotFound,
    #[error("unauthorized")]
    Unauthorized,
    #[error("conflict: {0}")]
    Conflict(String),
    #[error("validation error: {0}")]
    Validation(String),
    #[error("internal error: {0}")]
    Internal(#[from] anyhow::Error),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, error_message) = match &self {
            AppError::NotFound       => (StatusCode::NOT_FOUND, self.to_string()),
            AppError::Unauthorized   => (StatusCode::UNAUTHORIZED, self.to_string()),
            AppError::Conflict(msg)  => (StatusCode::CONFLICT, msg.clone()),
            AppError::Validation(msg) => (StatusCode::UNPROCESSABLE_ENTITY, msg.clone()),
            AppError::Internal(err)  => {
                tracing::error!("internal error: {err:?}"); // log full chain, return generic msg
                (StatusCode::INTERNAL_SERVER_ERROR, "internal server error".to_string())
            }
        };

        (status, Json(json!({"error": error_message}))).into_response()
    }
}
```

All handlers return `Result<T, AppError>` - errors are converted to HTTP responses automatically by Axum's `IntoResponse` blanket impl on `Result`.

## Anti-Patterns

```rust
// Bad: business logic in handler
async fn get_user(Path(id): Path<i64>, State(pool): State<PgPool>) -> impl IntoResponse {
    let user = sqlx::query_as!(User, "SELECT * FROM users WHERE id = $1", id)
        .fetch_one(&pool).await.unwrap(); // DB logic + unwrap in handler
    Json(user)
}

// Bad: no validation on input
async fn create_user(Json(req): Json<CreateUserRequest>) -> impl IntoResponse {
    // req.name could be empty, req.email could be "asdf"
}

// Bad: no error envelope - raw strings
async fn handler() -> Result<String, String> {
    Err("something failed".into()) // inconsistent error format
}
```

## Avoid

- Business logic or database access in handler functions
- Missing input validation at handler boundary
- Inconsistent error/success response formats
- No pagination limits on list endpoints
- Missing graceful shutdown (in-flight requests dropped on SIGTERM)
- Hardcoded bind addresses - use configuration
