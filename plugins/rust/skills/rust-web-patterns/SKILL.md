---
name: rust-web-patterns
description: "Axum 0.8 patterns: Router/AppState, tower layer order, validated extractors, JSON envelopes, pagination, webhooks (raw body), graceful shutdown."
metadata:
  category: backend
  tags: [rust, axum, tower, middleware, routing, pagination, webhook]
user-invocable: false
---

# Rust Web Patterns (Axum)

> Load `Use skill: stack-detect` first. This skill reads `Framework`: when it names another framework (Actix-web, Rocket, Warp, Poem) stop and emit the single line `rust-web-patterns: not applicable (<framework>)` - the extractor and tower-layer patterns here do not transfer; on `unknown` proceed as Axum only when `axum` is in the crate's `[dependencies]`, otherwise stop the same way. The Rust version is `rust-version` in the crate's `Cargo.toml` (else the `rust-toolchain.toml` channel; a `## Tech Stack` `Language:` line may carry a version, and the manifest wins when they differ). In a Cargo workspace the crate under review decides: its own `[dependencies]` (or the `[workspace.dependencies]` entries it inherits) in place of the detected values. A form that needs a newer toolchain or crate than the manifest pins is written in its older equivalent - Axum 0.7 takes `/:id` paths and `#[async_trait]` on custom extractors. A review spanning crates emits that line once per non-Axum crate, as `rust-web-patterns: not applicable (<crate>: <framework>)`, above the headings, and covers the Axum ones. Baseline: Rust 1.94+ (edition 2024: `IntoFuture` in the prelude), Axum 0.8 (`macros` feature for `FromRef`), tower-http 0.6 (0.6.7+ for `TimeoutLayer::with_status_code`), validator 0.20, hmac 0.12, sha2 0.10, Tokio 1.x.

## When to Use

- Structuring or reviewing an Axum HTTP service: router, `AppState`, extractors, layers
- Implementing middleware (auth, rate limiting, request timeouts, body limits)
- Designing consistent request/response contracts and pagination
- Webhook endpoints requiring raw body + signature validation
- Graceful shutdown, health and readiness endpoints

## Rules

- Handlers orchestrate; services execute. A handler extracts, calls one service method, and maps the result. Middleware writes only an error response (its own rejection) or an idempotent replay of a stored response; every other success body comes from a handler
- Every rejection reaches the client in the error envelope. Axum's own `Json` / `Query` / `Path` rejections are plain-text bodies (`Json`: 400 syntax, 415 content type, 413 over the body limit, 422 data) - wrap them in an extractor whose `Rejection` is `AppError`
- One JSON envelope for success and error on every endpoint that returns a JSON body. Exempt: 204s, probe endpoints, and non-JSON content types (SSE, file downloads) - name each exemption. An empty body is a 204, never an empty 200
- Paths are `/users/{id}` and `/{*rest}`. A `:id` segment panics when the router is built
- `Router::layer` wraps only the routes registered **before** it, and the last `.layer` call is the outermost. Stack shared layers in one `ServiceBuilder` (top-to-bottom = outermost first) after the last route; put auth on the protected router with `route_layer`, so an unmatched path stays 404 rather than 401
- `AppState` is cheaply `Clone`: `PgPool` as is, non-`Clone` services behind `Arc`. Handlers take the sub-state they need via `#[derive(FromRef)]`
- Bind with `TcpListener::bind((host, port))`, `host` being a bare IP or a hostname - the tuple form fails to resolve a bracketed `[::1]`
- Every route has a request timeout and a body cap. `DefaultBodyLimit` (2 MB by default) applies only to the buffering extractors (`Json`, `Form`, `Bytes`, `String`); a handler that streams `Body` or extracts `Request` needs `tower_http::limit::RequestBodyLimitLayer`
- Webhooks: extract `Bytes` and verify the signature over those bytes before deserializing; `Json<T>` consumes the body and re-serializing never reproduces the signed bytes
- Webhook routes live outside the JWT router, and handlers tolerate redelivery - providers retry on non-2xx and on timeout
- A retryable write (`POST`) takes a client `Idempotency-Key` header, scoped to the principal and bound to a hash of the body: same key + same body returns the first response, same key + different body is `409`

## Patterns

### Router Structure

```rust
use std::{sync::{Arc, atomic::AtomicBool}, time::Duration};
use axum::{Router, extract::{DefaultBodyLimit, FromRef}, http::StatusCode, middleware::from_fn_with_state, routing::{get, post}};
use sqlx::PgPool;
use tower::ServiceBuilder;
use tower_http::{catch_panic::CatchPanicLayer, timeout::TimeoutLayer, trace::TraceLayer};
use crate::{config::Config, handlers, mw, services::{PaymentService, UserService}};

#[derive(Clone, FromRef)]
pub struct AppState {
    pub pool: PgPool,                 // an Arc inside already
    pub users: Arc<UserService>,
    pub payments: Arc<PaymentService>,
    pub config: Arc<Config>,
    pub ready: Arc<AtomicBool>,       // flipped false by `run` during shutdown
}

pub fn router(state: AppState) -> Router {
    let api = Router::new()
        .route("/users", get(handlers::list_users).post(handlers::create_user))
        .route("/users/{id}", get(handlers::get_user))
        .route_layer(from_fn_with_state(state.clone(), mw::principal_rate_limit)) // inner: sees the principal
        .route_layer(from_fn_with_state(state.clone(), mw::auth));                // outer: runs first, matched routes only
    Router::new()
        .route("/health", get(handlers::health))
        .route("/ready", get(handlers::ready))
        .route("/api/v1/webhooks/github", post(handlers::github_webhook)) // signature is the only auth
        .nest("/api/v1", api)
        .layer(ServiceBuilder::new()
            .layer(TraceLayer::new_for_http())
            .layer(CatchPanicLayer::new()) // a handler panic becomes a 500 instead of a reset connection
            .layer(TimeoutLayer::with_status_code(StatusCode::REQUEST_TIMEOUT, Duration::from_secs(30)))
            .layer(DefaultBodyLimit::max(1 << 20)))
        .with_state(state)
}
```

Execution order inside one router is the inverse of the call order: `auth`, added last, runs first, so the principal limiter after it can read the principal. Swapping the two calls makes the limiter run unauthenticated. `mw::auth` ends in `req.extensions_mut().insert(Principal { .. })`, and handlers read it with `Extension<Principal>` or a `FromRequestParts` extractor, never caring which credential arrived. The timeout layer drops the handler future at its deadline - every `.await` in a handler is a cancellation point (see Client disconnect). `CatchPanicLayer` needs tower-http's `catch-panic` feature; without it a panic tears down only that connection, and under `panic = "abort"` the whole process.

### Request Extraction and Validation

```rust
use axum::{Json, extract::{FromRequest, Request}};
use serde::{Deserialize, de::DeserializeOwned};
use validator::Validate;
use crate::error::AppError; // AppError and its IntoResponse: rust-error-handling

pub struct ValidJson<T>(pub T);

impl<S: Send + Sync, T: DeserializeOwned + Validate> FromRequest<S> for ValidJson<T> {
    type Rejection = AppError;
    async fn from_request(req: Request, state: &S) -> Result<Self, AppError> {
        let Json(value) = Json::<T>::from_request(req, state).await
            .map_err(|e| AppError::Rejected(e.status(), e.body_text()))?; // keeps 413 / 415
        value.validate().map_err(|e| AppError::Validation(e.to_string()))?;
        Ok(Self(value))
    }
}

#[derive(Deserialize, Validate)]
#[serde(deny_unknown_fields)]
pub struct CreateUserRequest {
    #[validate(length(min = 2, max = 100))] pub name: String,
    #[validate(email)] pub email: String,
    #[validate(range(max = 130))] pub age: u8,
}
```

The body extractor is the last handler argument (`State`, `Path`, `Query` first) - only one extractor may consume the body. `Query` and `Path` get the same wrapper, or `axum_extra::extract::WithRejection<Query<T>, AppError>` (axum-extra's `with-rejection` feature). Validator messages name Rust fields - acceptable internally; a public API maps them to field-keyed errors. Validation the derive already enforces is not repeated in the handler.

### Response Envelope

```rust
use serde::Serialize;

#[derive(Serialize)]
pub struct ApiResponse<T, M = ()> {
    pub data: T,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub meta: Option<M>, // OffsetMeta or CursorMeta - one shape per endpoint, never both
}
impl<T> ApiResponse<T> { pub fn new(data: T) -> Self { Self { data, meta: None } } }
impl<T, M> ApiResponse<T, M> { pub fn with_meta(data: T, meta: M) -> Self { Self { data, meta: Some(meta) } } }

#[derive(Serialize)]
pub struct OffsetMeta { pub page: u32, pub page_size: u32, pub total_items: i64, pub total_pages: i64 }
#[derive(Serialize)]
pub struct CursorMeta {
    pub page_size: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<String>, // absent on the last page
    pub has_more: bool,
}
```

The error body (`{"error": ..., "code": ...}`) and its `IntoResponse` live in `rust-error-handling`; this skill never redefines them. Offset and keyset are different types, not one struct with optional mode-specific fields - a keyset response emitting `"page":0` is a contract clients code against. Serde writes field names as declared; a struct with `#[serde(rename_all = "camelCase")]` next to one without splits the API's casing - pick one at creation.

### Pagination

```rust
use axum::{Json, extract::{Query, State}};
use serde::Deserialize;
use std::sync::Arc;
use crate::{error::AppError, services::UserService, web::{ApiResponse, OffsetMeta, UserDto}};

const MAX_PAGE_SIZE: u32 = 100;

#[derive(Deserialize)]
pub struct ListQuery {
    #[serde(default = "one")] pub page: u32,
    #[serde(default = "twenty")] pub size: u32,
}
fn one() -> u32 { 1 }
fn twenty() -> u32 { 20 }

pub async fn list_users(State(svc): State<Arc<UserService>>, Query(q): Query<ListQuery>)
    -> Result<Json<ApiResponse<Vec<UserDto>, OffsetMeta>>, AppError> {
    if q.page == 0 { return Err(AppError::Validation("page must be >= 1".into())); }
    let size = q.size.clamp(1, MAX_PAGE_SIZE); // the served size goes back in meta
    let (rows, total) = svc.list(i64::from(size), i64::from(q.page - 1) * i64::from(size)).await?;
    let total_pages = (total + i64::from(size) - 1) / i64::from(size);
    Ok(Json(ApiResponse::with_meta(rows, OffsetMeta { page: q.page, page_size: size, total_items: total, total_pages })))
}
```

An unclamped size (`q.size.unwrap_or(100)`) lets a client ask for a million rows. The offset arithmetic is done in `i64` because `page * size` overflows `u32` on a hostile `page`. A growing table switches to a keyset cursor (`CursorMeta`; query shape in `rust-db-access`).

### Webhook (Raw Body + Signature)

```rust
use axum::{body::Bytes, extract::{FromRequest, Request}};
use hmac::{Hmac, Mac};
use sha2::Sha256;
use crate::{error::AppError, web::AppState};

pub struct SignedBody(pub Bytes);

impl FromRequest<AppState> for SignedBody {
    type Rejection = AppError;
    async fn from_request(req: Request, state: &AppState) -> Result<Self, AppError> {
        let sig = req.headers().get("x-hub-signature-256")
            .and_then(|v| v.to_str().ok()?.strip_prefix("sha256=").map(str::to_owned))
            .and_then(|h| hex::decode(h).ok())
            .ok_or(AppError::BadSignature)?;
        let body = Bytes::from_request(req, state).await // DefaultBodyLimit applies: 413 over the cap
            .map_err(|e| AppError::Rejected(e.status(), e.body_text()))?;
        let mut mac = Hmac::<Sha256>::new_from_slice(state.config.webhook_secret.as_bytes())
            .expect("HMAC accepts any key length");
        mac.update(&body);
        mac.verify_slice(&sig).map_err(|_| AppError::BadSignature)?; // constant-time
        Ok(Self(body))
    }
}
```

The handler takes `SignedBody(body)`, deserializes with `serde_json::from_slice`, and hands the event to a service that is idempotent on the event id. Never compare MACs with `==` or against the raw header string. Stripe signs `{t}.{payload}` in `Stripe-Signature: t=...,v1=...` and requires a timestamp tolerance to reject replays - use the SDK's verifier or check both. The status is a protocol: `2xx` stops redelivery, `5xx` asks for it, a bad signature is `400` and must never become a `2xx`.

### Rate Limiting

- Pre-auth, keyed on the client IP: sheds unauthenticated floods. Post-auth, keyed on the principal: the real quota. One IP bucket puts a whole NAT behind one limit and gives one API key N buckets
- `ConnectInfo<SocketAddr>` is the TCP peer - the proxy, behind a load balancer - and needs `into_make_service_with_connect_info::<SocketAddr>()`. `tower_governor`'s `SmartIpKeyExtractor` reads `X-Forwarded-For` / `X-Real-IP` / `Forwarded` with no trusted-proxy list, so it is spoofable unless every hop in front overwrites those headers
- An in-process `HashMap` of limiters grows one entry per key forever - evict on a last-seen sweep. Buckets are per replica: the effective ceiling is `limit * replicas`; move to Redis when the quota is contractual

### Health and Readiness

```rust
use std::{sync::{Arc, atomic::{AtomicBool, Ordering}}, time::Duration};
use axum::{Json, extract::State, http::StatusCode};
use serde_json::{Value, json};
use sqlx::PgPool;

pub async fn health() -> Json<Value> { Json(json!({"status": "ok"})) }

pub async fn ready(State(pool): State<PgPool>, State(ready): State<Arc<AtomicBool>>) -> (StatusCode, Json<Value>) {
    if !ready.load(Ordering::Relaxed) {
        return (StatusCode::SERVICE_UNAVAILABLE, Json(json!({"status": "draining"})));
    }
    // acquire_timeout defaults to 30s - far past any probe timeout
    let ping = tokio::time::timeout(Duration::from_secs(1), sqlx::query("SELECT 1").execute(&pool)).await;
    match ping {
        Ok(Ok(_)) => (StatusCode::OK, Json(json!({"status": "ready"}))),
        _ => (StatusCode::SERVICE_UNAVAILABLE, Json(json!({"status": "not ready", "reason": "db"}))),
    }
}
```

### Graceful Shutdown

```rust
use std::{net::SocketAddr, sync::{Arc, atomic::{AtomicBool, Ordering}}};
use anyhow::{Context, bail};
use axum::Router;
use tokio::{net::TcpListener, signal};
use tokio_util::sync::CancellationToken;
use crate::config::Config;

pub async fn run(app: Router, cfg: &Config, ready: Arc<AtomicBool>, streams: CancellationToken) -> anyhow::Result<()> {
    let listener = TcpListener::bind((cfg.host.as_str(), cfg.port)).await.context("bind")?;
    let stop = CancellationToken::new();
    let server = tokio::spawn(
        axum::serve(listener, app.into_make_service_with_connect_info::<SocketAddr>())
            .with_graceful_shutdown(stop.clone().cancelled_owned())
            .into_future(),
    );
    shutdown_signal().await;
    ready.store(false, Ordering::Relaxed);        // /ready fails; the LB stops routing once it notices
    tokio::time::sleep(cfg.pre_stop_delay).await; // endpoint-removal propagation, still serving
    streams.cancel();                             // SSE / streaming handlers end themselves
    stop.cancel();                                // stop accepting; in-flight requests finish
    match tokio::time::timeout(cfg.drain_timeout, server).await {
        Ok(joined) => Ok(joined.context("server task")??),
        Err(_) => bail!("drain exceeded {:?}", cfg.drain_timeout), // report it - a silent Ok hides every truncated request
    }
}

async fn shutdown_signal() {
    let ctrl_c = async { signal::ctrl_c().await.expect("install Ctrl-C handler") };
    #[cfg(unix)]
    let term = async {
        signal::unix::signal(signal::unix::SignalKind::terminate()).expect("install SIGTERM handler").recv().await;
    };
    #[cfg(not(unix))]
    let term = std::future::pending::<()>();
    tokio::select! { () = ctrl_c => {}, () = term => {} }
}
```

`with_graceful_shutdown` waits for every connection with no deadline of its own, so the outer `timeout` is the floor. Once Tokio installs a signal handler it stays installed for the process lifetime: a second SIGTERM no longer kills the process, which is why the drain deadline must exist. `pre_stop_delay + drain_timeout` must be under the platform's kill deadline (k8s `terminationGracePeriodSeconds`), and `drain_timeout` above the slowest normal request. On Kubernetes a terminating pod's EndpointSlice `ready` condition goes false at once, so for Service routing `pre_stop_delay` covers endpoint-removal propagation (~5s); only an external load balancer that probes `/ready` itself adds `failureThreshold * periodSeconds` on top. `axum::serve` exposes no header-read timeout - Slowloris protection comes from the proxy in front. Tasks a handler spawned are not drained by the server - see `rust-async-patterns`.

## Edge Cases

- **Client disconnect: decide abandon or survive.** Hyper drops the handler future when the client hangs up, cancelling it at whatever `.await` it is parked on; the timeout layer does the same. Abandon (reads, queries) needs nothing. Survive (a submitted job, a payment already taken) - hand the work to a durable queue and return 202, or run the call and the write that records its outcome inside a tracked `tokio::spawn` that the handler awaits
- `Router::merge` of two routers that register the same path and method panics at startup; so does a `nest` at `/` (use `merge`)
- A static route and a capture sibling (`/orders/export` next to `/orders/{id}`) coexist; the static segment wins regardless of registration order

## Output Format

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design / change-set | `## API Design` with `### Endpoints`, `### Middleware Stack`, `### Response Envelope`; code for new handlers, extractors and wiring follows under `### <Endpoint, extractor or layer>` headings in table order; a concern this skill does not own (transactions, authorization rules, crypto choice) is one sentence under the tables naming the owning concern; a change-set handed existing code with a defect, owned or not, emits `## Findings` first |
| Review | `## Findings`, then `## API Design` describing the surface as it exists today, scoped to the routes and layers the input supplied |

```
## API Design

### Endpoints
| Method | Path | Auth | Request | Response | Status | Change |
|--------|------|------|---------|----------|--------|--------|

### Middleware Stack
| Order | Middleware | Scope | Purpose |
|-------|------------|-------|---------|

### Response Envelope
| Shape | Body |
|-------|------|
```

Cell values: every cell describes the surface as wired; a defect in it is a Finding, never a cell annotation. `Auth` is what the route actually requires - `JWT | API key | signature | inline <kind> | none` - so a webhook behind the JWT `route_layer` reads `JWT` and the finding says why that is wrong, and a check done inside the handler body reads `inline signature` plus a `[Recommend]` to lift it into an extractor or layer. With the handler not supplied the layers decide, and a route no auth layer covers reads `unknown`. `Request` is the extractor chain's body type plus any required header (`ValidJson<CreateRefundRequest> + Idempotency-Key`), or `none`. `Response` is the envelope shape (`ApiResponse<Refund>`, `ApiResponse<Vec<Refund>, CursorMeta>`), `204`, the exemption, or the literal type when a handler returns a bare `Json<T>`. `Status` lists the HTTP codes the endpoint returns, extractor rejections and the codes its layers add (auth 401, timeout 408, body limit 413, rate limit 429, panic catch 500) included - the codes the supplied code shows, plus `unknown` for a handler the input does not supply. `Change` is `New | Changed | Unchanged | Removed`; a route that keeps its path but changes router or layers is `Changed`; a moved path is `Removed` at the old path and `New` at the new one; the column is omitted on a greenfield design and on a review. Every registered route in the supplied files is a row, whatever the request singled out, including a `nest_service` or a debug route. `Order` is the execution position within `Scope`, outermost first, numbered from 1 per scope; a nested router's inherited layers are not re-listed; when the outer stack is not supplied its rows are `unknown` and numbering still starts at 1. `Scope` is `router | route_layer <prefix> | merged <router> | route <method path> | unmounted` - `router` for any layer, a `route_layer` included, on the outermost router, `route_layer <prefix>` for any layer on a nested router, `merged <router>` for any layer on a router that is merged rather than nested (`merged protected`). `Scope` names where the layer is attached; routes registered after it are a finding, not a second row. `Purpose` is one phrase (`reject missing bearer`, `cap body at 1 MiB`). A middleware fn defined but mounted nowhere gets a row with `Scope` = `unmounted` and `Order` = `-`. `Response Envelope` rows are the shapes actually emitted, one row per distinct shape, with each exemption (204, probe, SSE, file) and each plain-text extractor rejection as its own row; `Body` is the JSON skeleton with field names (`{"data": <T>, "meta": {"next_cursor", "has_more"}}`). A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {what breaks - wrong status, lost request, spoofable input, dropped work}
- Rule: {the Axum rule or pattern violated}
- Fix: {concrete edit}
```

Owned findings: `[Must]` when the service fails to start (a `:id` path, a conflicting merge), a security control is void or bypassable (a layer registered before the routes it should cover, a spoofable client IP, a webhook behind the wrong auth, a non-constant-time compare), work is silently lost, a response makes the sender redeliver an event already processed, or a client-visible contract is wrong; `[Recommend]` otherwise. A deployment manifest is a file like any other (`k8s/api-deployment.yaml:41`). Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not; a range is `file:start-end`. Order the blocks in four groups - owned `[Must]`, owned `[Recommend]`, then the not-owned blocks described below, `[Must]` then `[Recommend]` - and within a group by file in the order the input listed them (a listed directory's files in path order at the directory's position, a file listed twice at its first; files the input did not list after those, in path order), then position in the file. With no findings, `## Findings` holds the single line `None.` One root cause at several sites is one heading citing the first site in that order, with the rest named on the `Defect:` line. An incident question is answered inside the `Defect:` line of the finding it concerns. A defect this skill does not own (transactions, task lifecycle, crypto choice, authorization rules, CORS policy) is still reported, never dropped: one block per such defect in the last two groups, labelled `[Must]` when it risks incorrect behaviour, data loss or a security hole and `[Recommend]` otherwise, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- Business logic or SQL in handlers
- Shared layers called before the routes they should wrap, and auth on the outer router (it covers `/health`)
- Unbounded list endpoints, and deep `OFFSET` paging on a growing table - switch to a keyset cursor
- `Json<T>` on webhook endpoints
- Webhook routes behind the JWT `route_layer`
- Shared read state behind a `Mutex` in `AppState`; bind address or secrets hardcoded in source
