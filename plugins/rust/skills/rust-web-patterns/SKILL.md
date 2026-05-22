---
name: rust-web-patterns
description: "Axum web patterns: router composition, AppState, extractors, validator input, response envelopes, pagination caps, graceful shutdown, health/readiness."
metadata:
  category: backend
  tags: [rust, axum, tower, middleware, routing, http, web]
user-invocable: false
---

# Rust Web Patterns (Axum)

> Load `Use skill: stack-detect` first to determine the project stack. For error envelopes and `IntoResponse`, defer to `rust-error-handling`. For JWT validation, password hashing, CORS hardening, and path traversal, defer to `rust-security-patterns`. For async runtime and `spawn_blocking`, defer to `rust-async-patterns`.

## When to Use

- Structuring a new Axum HTTP service or reviewing an existing one
- Designing routers, `AppState`, extractors, response envelopes, and pagination
- Adding health/readiness endpoints and graceful shutdown

Out of scope: error type design, JWT/auth specifics, runtime/concurrency. Reference the sibling skills above.

## Rules

- Handlers orchestrate only - no DB calls, no business logic. Delegate to a service injected via `State`.
- Validate every request DTO at the handler boundary (`validator::Validate` + `serde`).
- All endpoints return a typed envelope (`ApiResponse<T>` for success, `AppError` for failure). No ad-hoc `(StatusCode, String)`.
- List endpoints clamp `page_size` to a server-enforced max. Reject negative `page`.
- `AppState` is cheaply `Clone` (wrap heavy or non-`Clone` fields in `Arc`). Never hold it behind a `Mutex` for shared data.
- Routes use Axum 0.8 capture syntax `/users/{id}`. Old `:id` is invalid.
- Production deploys must implement graceful shutdown via `with_graceful_shutdown` and bind addresses from config.

## Patterns

### Router Composition and Layer Order

Layer order is bottom-up: the last `.layer()` runs first on the request. Apply auth on the protected sub-router, never globally.

```rust
fn build_router(state: AppState) -> Router {
    let public = Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready));

    let api = Router::new()
        .route("/users", get(list_users).post(create_user))
        .route("/users/{id}", get(get_user))
        .layer(axum::middleware::from_fn_with_state(state.clone(), auth_middleware));

    Router::new()
        .merge(public)
        .nest("/api/v1", api)
        .layer(TraceLayer::new_for_http())       // outermost: wraps all requests including 404s
        .layer(CorsLayer::permissive())          // tighten per rust-security-patterns in prod
        .with_state(state)
}
```

### AppState Design

```rust
// Bad: non-Clone field forces wrapping the whole state in Arc, losing direct field access ergonomics
struct AppState { service: UserService }

// Good: cheap-Clone wrapper around shared services; PgPool is already Clone
#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub users: Arc<UserService>,
    pub config: Arc<Config>,
}
```

Use `FromRef` when handlers want a sub-field directly:

```rust
impl FromRef<AppState> for Arc<UserService> {
    fn from_ref(s: &AppState) -> Self { s.users.clone() }
}
// handler can now take `State(svc): State<Arc<UserService>>`
```

### Request Validation

```rust
#[derive(Debug, Deserialize, Validate)]
pub struct CreateUserRequest {
    #[validate(length(min = 2, max = 100))] pub name: String,
    #[validate(email)] pub email: String,
    #[validate(range(min = 0, max = 130))] pub age: Option<i32>,
}

async fn create_user(
    State(svc): State<Arc<UserService>>,
    Json(req): Json<CreateUserRequest>,
) -> Result<(StatusCode, Json<ApiResponse<UserDto>>), AppError> {
    req.validate().map_err(|e| AppError::Validation(e.to_string()))?;
    let user = svc.create(req).await?;
    Ok((StatusCode::CREATED, Json(ApiResponse::new(user))))
}
```

### Pagination with Cap

```rust
const MAX_PAGE_SIZE: i64 = 100;
const DEFAULT_PAGE_SIZE: i64 = 20;

#[derive(Debug, Deserialize)]
pub struct ListQuery {
    #[serde(default = "one")] pub page: i64,
    #[serde(default = "default_size")] pub page_size: i64,
    pub status: Option<String>,
}
fn one() -> i64 { 1 }
fn default_size() -> i64 { DEFAULT_PAGE_SIZE }

impl ListQuery {
    pub fn normalize(&self) -> Result<(i64, i64), AppError> {
        if self.page < 1 { return Err(AppError::Validation("page must be >= 1".into())); }
        Ok((self.page, self.page_size.clamp(1, MAX_PAGE_SIZE)))
    }
}
```

Bad: `let size = q.page_size.unwrap_or(100);` - no upper bound; a client can request 1M rows.

### Response Envelope

```rust
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

impl<T: Serialize> ApiResponse<T> {
    pub fn new(data: T) -> Self { Self { data, meta: None } }
    pub fn paginated(data: T, meta: PaginationMeta) -> Self { Self { data, meta: Some(meta) } }
}
```

Error envelope is defined in `rust-error-handling` via `AppError: IntoResponse`. Do not redefine it here.

### Middleware Structure

Cross-cutting concerns go in tower layers, not handlers. For auth specifics, see `rust-security-patterns`.

```rust
async fn request_id_middleware(mut req: Request, next: Next) -> Response {
    let id = Uuid::new_v4().to_string();
    req.extensions_mut().insert(RequestId(id.clone()));
    let mut resp = next.run(req).await;
    resp.headers_mut().insert("x-request-id", id.parse().unwrap());
    resp
}
```

### Health and Readiness

Health = process is up. Readiness = dependencies reachable. Kubernetes uses them differently.

```rust
async fn health() -> Json<ApiResponse<&'static str>> {
    Json(ApiResponse::new("ok"))
}

async fn ready(State(state): State<AppState>) -> Result<Json<ApiResponse<&'static str>>, AppError> {
    sqlx::query("SELECT 1").execute(&state.pool).await
        .map_err(|e| AppError::Internal(anyhow::anyhow!("db not ready: {e}")))?;
    Ok(Json(ApiResponse::new("ready")))
}
```

### Graceful Shutdown

```rust
async fn serve(app: Router, addr: SocketAddr) -> anyhow::Result<()> {
    let listener = TcpListener::bind(addr).await?;
    axum::serve(listener, app).with_graceful_shutdown(shutdown_signal()).await?;
    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async { signal::ctrl_c().await.ok(); };
    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("install SIGTERM handler").recv().await;
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();
    tokio::select! { _ = ctrl_c => {}, _ = terminate => {} }
}
```

## Output Format

Workflows parse this contract.

```
Findings:
  - [Severity: {Blocker|High|Medium|Low}] [Category: {Handler|State|Extractor|Validation|Envelope|Pagination|Routing|Middleware|Health|Shutdown}]
    File: <path>:<line>
    Issue: <one-line description>
    Fix: <prescribed change, referencing a Pattern by name>

Risk Summary:
  Untrusted Input Risk: {None|Low|Medium|High}
  Unbounded Response Risk: {None|Low|Medium|High}
  Shutdown Safety: {Safe|At-Risk|Missing}

Stack Detected: {Axum 0.8+ | Axum 0.7 | Unknown}
Notes: <unresolved questions, partial info, or "n/a">
```

If the framework is not Axum, emit `Stack Detected: Unknown` and apply only the framework-neutral Rules (handler/service separation, validation, envelopes, pagination caps, graceful shutdown).

## Avoid

- Business logic or DB calls in handlers.
- Skipping `validate()` on request DTOs.
- Returning bare `String`, raw `Json(Vec<_>)`, or ad-hoc tuples instead of `ApiResponse<T>` / `AppError`.
- `page_size` without a server-side cap; negative `page` accepted silently.
- Wrapping `AppState` in `Mutex` for shared read state (use `Arc` on the inner field instead).
- Applying auth middleware globally instead of on the protected sub-router.
- Old `/users/:id` route syntax (Axum 0.7) in an 0.8+ project.
- Bind address or secrets hardcoded in source; missing `with_graceful_shutdown`.
- Duplicating `AppError`/`IntoResponse` or JWT logic here - see `rust-error-handling`, `rust-security-patterns`.
