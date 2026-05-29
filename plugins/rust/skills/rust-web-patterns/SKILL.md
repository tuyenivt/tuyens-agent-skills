---
name: rust-web-patterns
description: "Axum 0.8 patterns: router/AppState, extractors, validator DTOs, ApiResponse envelopes, capped pagination, graceful shutdown, health/readiness."
metadata:
  category: backend
  tags: [rust, axum, tower, middleware, routing, http, web]
user-invocable: false
---

# Rust Web Patterns (Axum)

> Load `Use skill: stack-detect` first. Defer error envelopes / `IntoResponse` to `rust-error-handling`; JWT, CORS hardening, password hashing to `rust-security-patterns`; runtime / `spawn_blocking` to `rust-async-patterns`.

## When to Use

- Structuring or reviewing an Axum HTTP service: routers, `AppState`, extractors, response shape, pagination, health, shutdown.

## Rules

- Handlers orchestrate only: parse input, call a service via `State`, map to response. No DB, no business logic.
- Validate every request DTO at the handler boundary (`validator::Validate` + `serde`).
- Every endpoint returns `ApiResponse<T>` on success and `AppError` on failure. No bare strings, raw `Json(Vec<_>)`, or ad-hoc `(StatusCode, String)`.
- List endpoints clamp `page_size` to a server-side max and reject `page < 1`.
- `AppState` is cheaply `Clone`: wrap heavy or non-`Clone` fields in `Arc`. Never put shared read state behind a `Mutex`.
- Apply auth on the protected sub-router, not the top-level `Router`.
- Axum 0.8 route syntax is `/users/{id}`. The `:id` form is a hard error.
- Production binaries bind from config and shut down via `with_graceful_shutdown`.

## Patterns

### Router composition

`.layer` is bottom-up: the *last* layer added runs *first*. Auth goes on the protected sub-router so it never wraps `/health`.

```rust
fn build_router(state: AppState) -> Router {
    let public = Router::new().route("/health", get(health)).route("/ready", get(ready));
    let api = Router::new()
        .route("/users", get(list_users).post(create_user))
        .route("/users/{id}", get(get_user))
        .layer(from_fn_with_state(state.clone(), auth_middleware));

    Router::new()
        .merge(public)
        .nest("/api/v1", api)
        .layer(TraceLayer::new_for_http())
        .layer(CorsLayer::permissive()) // tighten in prod; see rust-security-patterns
        .with_state(state)
}
```

### AppState

```rust
#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,                  // already cheap to clone
    pub users: Arc<UserService>,       // Arc wraps non-Clone services
    pub config: Arc<Config>,
}
```

Use `#[derive(FromRef)]` (or hand-written `FromRef`) so handlers can extract a sub-field directly: `State(svc): State<Arc<UserService>>`.

### Request validation

```rust
#[derive(Deserialize, Validate)]
pub struct CreateUserRequest {
    #[validate(length(min = 2, max = 100))] pub name: String,
    #[validate(email)] pub email: String,
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

### Pagination with cap

```rust
const MAX_PAGE_SIZE: i64 = 100;

#[derive(Deserialize)]
pub struct ListQuery {
    #[serde(default = "default_page")] pub page: i64,
    #[serde(default = "default_size")] pub page_size: i64,
}
fn default_page() -> i64 { 1 }
fn default_size() -> i64 { 20 }

impl ListQuery {
    pub fn normalize(&self) -> Result<(i64, i64), AppError> {
        if self.page < 1 { return Err(AppError::Validation("page must be >= 1".into())); }
        Ok((self.page, self.page_size.clamp(1, MAX_PAGE_SIZE)))
    }
}
```

Bad: `q.page_size.unwrap_or(100)` - no upper bound; a client can request a million rows.

### Response envelope

```rust
#[derive(Serialize)]
pub struct ApiResponse<T: Serialize> {
    pub data: T,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub meta: Option<PaginationMeta>,
}

#[derive(Serialize)]
pub struct PaginationMeta { pub page: i64, pub page_size: i64, pub total_items: i64, pub total_pages: i64 }

impl<T: Serialize> ApiResponse<T> {
    pub fn new(data: T) -> Self { Self { data, meta: None } }
    pub fn paginated(data: T, meta: PaginationMeta) -> Self { Self { data, meta: Some(meta) } }
}
```

Error envelope lives in `rust-error-handling` (`AppError: IntoResponse`); do not redefine.

### Middleware

Cross-cutting concerns belong in tower layers, not handlers.

```rust
async fn request_id(mut req: Request, next: Next) -> Response {
    let id = Uuid::new_v4().to_string();
    req.extensions_mut().insert(RequestId(id.clone()));
    let mut resp = next.run(req).await;
    if let Ok(v) = HeaderValue::from_str(&id) { resp.headers_mut().insert("x-request-id", v); }
    resp
}
```

### Health and readiness

Health = process is alive (no deps). Readiness = dependencies reachable. Kubernetes treats them differently.

```rust
async fn health() -> Json<ApiResponse<&'static str>> { Json(ApiResponse::new("ok")) }

async fn ready(State(s): State<AppState>) -> Result<Json<ApiResponse<&'static str>>, AppError> {
    sqlx::query("SELECT 1").execute(&s.pool).await
        .map_err(|e| AppError::Internal(anyhow::anyhow!("db not ready: {e}")))?;
    Ok(Json(ApiResponse::new("ready")))
}
```

### Graceful shutdown

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

Non-Axum stacks: emit `Stack Detected: Unknown` and apply only the framework-neutral Rules (handler/service separation, validation, envelopes, pagination caps, graceful shutdown).

## Avoid

- Cross-skill drift: redefining `AppError`/`IntoResponse` or JWT logic here instead of deferring to `rust-error-handling` / `rust-security-patterns`.
- Global auth layer (covers `/health`); shared-read state behind `Mutex`; bind address or secrets hardcoded in source.
