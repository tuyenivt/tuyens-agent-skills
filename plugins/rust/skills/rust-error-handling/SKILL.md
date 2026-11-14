---
name: rust-error-handling
description: "Rust errors: thiserror enums per layer, anyhow at the edge, ? and From, panic policy, sqlx error kinds, retryable classification, Axum IntoResponse."
metadata:
  category: backend
  tags: [rust, error-handling, thiserror, anyhow, axum, result]
user-invocable: false
---

# Rust Error Handling

> Load `Use skill: stack-detect` first. This skill reads `Database`; on `unknown` the sqlx feature list in the crate's `Cargo.toml` names the engine. The Rust version is `rust-version` in the crate's `Cargo.toml` (else the `rust-toolchain.toml` channel; a `## Tech Stack` `Language:` line may carry a version, and the manifest wins when they differ). In a Cargo workspace the crate under review decides: its own `[dependencies]` (or the `[workspace.dependencies]` entries it inherits) in place of the detected values. A form that needs a newer toolchain or crate than the manifest pins is written in its older equivalent. Driver errors are matched by sqlx's engine-neutral kind (`is_unique_violation()`, `is_foreign_key_violation()`, `is_check_violation()`); a raw `code()` is SQLSTATE - `23505` / `23503` on PostgreSQL, while MySQL reports `23000` for both, so MySQL code matches go through the kind. The boundary is Axum's `IntoResponse`; under another framework the same mapping lives in its one error hook (actix-web: `ResponseError`). Baseline: Rust 1.94+ (edition 2024), thiserror 2, anyhow 1, sqlx 0.9, reqwest 0.12, Axum 0.8.

## When to Use

- Designing error types for a new crate, module, or service boundary
- Reviewing error handling, panic sites, or `Option` / `Result` choices
- Implementing the one error-to-response mapping of an Axum service
- Wrapping third-party API errors into domain errors

## Rules

- Handle every `Result`. `let _ =`, `.ok()` and `.unwrap_or_default()` on a `Result` discard the error; best-effort work still logs it
- Propagate with `?`; each layer converts into its own `thiserror` enum, keeping the cause as `#[source]` / `#[from]` so the chain survives. `anyhow` lives in `main`, CLIs and job bootstrap; a library crate's public API never exposes `anyhow::Error` or `Box<dyn Error>`
- `#[from]` is a blanket conversion: every `?` turns *all* of that error type into one variant. Map the cases callers branch on (`RowNotFound`, a unique violation) with `map_err` before it
- Match on variants and kinds; never on `to_string()`
- Log OR return at each layer, never both - converting before returning is returning
- `unwrap`, `expect`, `panic!`, `unreachable!` and unchecked slice indexing are for programmer bugs and startup invariants only, never a request or job path; `expect("why it cannot fail")` over `unwrap()`
- Map errors at layer boundaries: repository -> service -> one `IntoResponse`. The mapping `match` has no `_ =>` arm, so a new variant fails to compile until its status is decided
- Classify external errors as retryable, permanent, or indeterminate at the gateway

## Patterns

### Error Types per Layer

```rust
use axum::http::StatusCode;
use thiserror::Error;

pub type BoxError = Box<dyn std::error::Error + Send + Sync>;

#[derive(Debug, Error)]
pub enum StoreError {                          // repository: driver types stop here
    #[error("not found")] NotFound,
    #[error("unique violation on {0}")] Conflict(String),
    #[error("storage failure")] Storage(#[source] sqlx::Error),
}

#[derive(Debug, Error)]
pub enum GatewayError {                        // external provider, classified once
    #[error("declined")] Declined,
    #[error("retryable")] Retryable(#[source] BoxError),         // never reached the provider, or 429
    #[error("rejected")] Rejected(#[source] BoxError),           // decoded 4xx: permanent
    #[error("outcome indeterminate")] Indeterminate(#[source] BoxError), // may have taken effect
}

#[derive(Debug, Error)]
pub enum DomainError {                         // service: the outcomes callers branch on
    #[error("{entity} {id} not found")] NotFound { entity: &'static str, id: String },
    #[error("conflict on {0}")] Conflict(String),
    #[error("invalid transition {from} -> {to}")] InvalidTransition { from: &'static str, to: &'static str },
    #[error("payment provider")] Gateway(#[from] GatewayError),
    #[error("storage")] Storage(#[source] StoreError),
}

#[derive(Debug, Error)]
pub enum AppError {                            // HTTP boundary
    #[error("{0}")] Validation(String),
    #[error("{1}")] Rejected(StatusCode, String), // an Axum extractor rejection, its status kept
    #[error("invalid signature")] BadSignature,
    #[error("unauthorized")] Unauthorized,
    #[error("forbidden")] Forbidden,
    #[error(transparent)] Domain(#[from] DomainError),
    #[error(transparent)] Internal(#[from] anyhow::Error),
}
```

A variant exists per distinct handling decision, not per message: add one when a caller branches on it, carry fields when the caller reads them (`entity`, `id`). Messages are lowercase with no trailing punctuation, and never interpolate their own source (`#[error("query failed: {0}")]` on a `#[source]` field) - every chain printer (`{:#}`, tracing, `anyhow`'s Debug) then shows the cause twice.

### Layer Mapping

```rust
// Repository: driver error -> StoreError
let row = sqlx::query_as!(Order, "SELECT id, status FROM orders WHERE id = $1", id)
    .fetch_optional(&mut *conn).await.map_err(StoreError::Storage)?
    .ok_or(StoreError::NotFound)?;

pub fn map_write(e: sqlx::Error) -> StoreError {
    match e {
        sqlx::Error::Database(db) if db.is_unique_violation() =>
            StoreError::Conflict(db.constraint().unwrap_or("unique").to_owned()),
        other => StoreError::Storage(other),
    }
}

// Service: adds what the repository cannot know
let order = repo.find(conn, id).await.map_err(|e| match e {
    StoreError::NotFound => DomainError::NotFound { entity: "order", id: id.to_string() },
    StoreError::Conflict(c) => DomainError::Conflict(c),
    other @ StoreError::Storage(_) => DomainError::Storage(other),
})?;

// Handler: `?` converts DomainError into AppError through #[from]; IntoResponse renders it
```

`Order` and `repo` are the project's. A `query!` or `fetch_one` result propagated with a bare `?` into a `#[from] sqlx::Error` variant is how a missing row becomes a 500.

### Application Edge: anyhow

```rust
use anyhow::{Context, Result};
use std::path::Path;
use crate::config::Config;

fn load_config(path: &Path) -> Result<Config> {
    let raw = std::fs::read_to_string(path).with_context(|| format!("read {}", path.display()))?;
    toml::from_str(&raw).with_context(|| format!("parse {}", path.display()))
}
```

`with_context` (closure) when the message allocates, `context` for a static string. `anyhow::Error`'s `{}` prints only the outermost context - log it with `{:#}` (the chain) or `{:?}` (chain plus backtrace).

### Wrapping External API Errors

```rust
use std::time::Duration;
use reqwest::{Client, StatusCode};

pub async fn charge(http: &Client, url: &str, req: &ChargeRequest) -> Result<ChargeResponse, GatewayError> {
    let sent = http.post(url)
        .header("Idempotency-Key", &req.id) // the same key on every attempt is what makes a retry safe
        .json(req)
        .timeout(Duration::from_secs(10))
        .send().await;
    let res = match sent {
        Ok(res) => res,
        Err(e) if e.is_connect() => return Err(GatewayError::Retryable(e.into())), // never reached the provider
        Err(e) => return Err(GatewayError::Indeterminate(e.into())),              // timeout or reset after send
    };
    match res.status() {
        s if s.is_success() => res.json().await.map_err(|e| GatewayError::Indeterminate(e.into())), // done, body unread
        StatusCode::PAYMENT_REQUIRED => Err(GatewayError::Declined),
        StatusCode::TOO_MANY_REQUESTS => Err(GatewayError::Retryable("429 from provider".into())),
        s if s.is_server_error() => Err(GatewayError::Indeterminate(format!("{s} from provider").into())),
        s => Err(GatewayError::Rejected(format!("{s} from provider").into())),
    }
}
```

`ChargeRequest` (with its `id`) and `ChargeResponse` are the project's serde types. The provider's error type stops at the gateway; the cause rides along as `#[source]`. **Indeterminate** = the call may have taken effect (timeout after send, connection reset, 5xx after a write). Resolve it by a same-key re-send when the provider stores idempotent results, otherwise by a read against a reference you set (metadata, your order id) or the provider's webhook - never a blind retry, which is how a capture gets charged twice. A request future dropped by cancellation after `send()` began is indeterminate too.

### Code-Based Errors

```rust
use tonic::{Code, Status};

fn map_grpc(op: &'static str, s: Status) -> DomainError {
    match s.code() {
        Code::NotFound => DomainError::NotFound { entity: op, id: s.message().to_owned() },
        Code::Unavailable | Code::ResourceExhausted => GatewayError::Retryable(s.into()).into(),
        Code::DeadlineExceeded => GatewayError::Indeterminate(s.into()).into(),
        _ => GatewayError::Rejected(s.into()).into(),
    }
}
```

A wildcard is right here and wrong in the response mapper: it maps an *external* code space the crate does not own, so new codes default to the safe outcome.

### Option vs Result

`Option` when absence is a normal value (a repository lookup); `Result` when absence is a caller-visible error (`.ok_or(...)` at the service). `Option<Result<T, E>>` and `Result<Option<T>, E>` are not interchangeable - a lookup that can fail returns `Result<Option<T>, E>`, and `.transpose()` converts.

### Aggregate Errors

```rust
#[derive(Debug, thiserror::Error)]
#[error("{} of {total} items failed", .failed.len())]
pub struct BatchError { pub total: usize, pub failed: Vec<(String, DomainError)>, pub aborted: bool }
```

Collect per-item failures with their ids so the caller can decompose the result without parsing text. Keep going when the failure is scoped to the item (validation, not-found, conflict); abort when it is infrastructure-wide (pool timed out, cancelled, credentials revoked) and set `aborted`, so the caller can tell "500 bad rows" from "we stopped at row 12".

### Axum Response Mapping

```rust
use axum::{Json, http::StatusCode, response::{IntoResponse, Response}};
use serde::Serialize;

#[derive(Serialize)]
pub struct ErrorBody {
    pub error: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code: Option<&'static str>,
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, msg) = match &self {
            AppError::Validation(m) => (StatusCode::BAD_REQUEST, m.clone()),
            AppError::Rejected(s, m) => (*s, m.clone()),
            AppError::BadSignature => (StatusCode::BAD_REQUEST, self.to_string()),
            AppError::Unauthorized => (StatusCode::UNAUTHORIZED, self.to_string()),
            AppError::Forbidden => (StatusCode::FORBIDDEN, self.to_string()),
            AppError::Domain(d) => match d {
                DomainError::NotFound { .. } => (StatusCode::NOT_FOUND, "not found".into()),
                DomainError::Conflict(_) => (StatusCode::CONFLICT, "conflict".into()),
                DomainError::InvalidTransition { .. } => (StatusCode::UNPROCESSABLE_ENTITY, d.to_string()),
                DomainError::Gateway(GatewayError::Declined) => (StatusCode::PAYMENT_REQUIRED, "payment declined".into()),
                DomainError::Gateway(GatewayError::Retryable(_)) => (StatusCode::SERVICE_UNAVAILABLE, "service temporarily unavailable".into()),
                DomainError::Gateway(GatewayError::Rejected(_)) => (StatusCode::BAD_GATEWAY, "payment gateway error".into()),
                DomainError::Gateway(GatewayError::Indeterminate(_)) => (StatusCode::ACCEPTED, "pending".into()), // never a retryable 5xx
                DomainError::Storage(_) => (StatusCode::INTERNAL_SERVER_ERROR, "internal server error".into()),
            },
            AppError::Internal(_) => (StatusCode::INTERNAL_SERVER_ERROR, "internal server error".into()),
        };
        if status.is_server_error() {
            tracing::error!(error = ?self, "request failed"); // Debug keeps the source chain
        } else {
            tracing::warn!(error = %self, "request rejected"); // expected conditions are not error-level noise
        }
        (status, Json(ErrorBody { error: msg, code: None })).into_response()
    }
}
```

The body never carries a source's text (SQL, file paths, provider messages) - only the mapped message. A handler with partial-success semantics (batch import) returns its own multi-status body rather than an `AppError`. A webhook handler's status is a protocol: `2xx` acknowledges and the provider stops redelivering, `5xx` asks for redelivery, a signature failure is `400`; most providers retry every non-2xx for days, so a wrong secret shows as sustained 400s.

## Edge Cases

- An unused `Result` warns (`#[must_use]`); `let _ =` silences the warning and the error together
- `Box<dyn Error>` without `+ Send + Sync` cannot be held across `.await` in a spawned task or converted into `anyhow::Error`
- A panic in a spawned task surfaces only as a `JoinError` on its handle (`rust-async-patterns`); in an Axum handler without `CatchPanicLayer` it resets the connection, and under `panic = "abort"` it ends the process
- `main() -> anyhow::Result<()>` prints the error's Debug form and exits with code 1

## Output Format

Open the deliverable with one line above everything else, `**Engine:** {database | unknown}` - stack-detect's `Database` value as written, version included, or the engine named by the reviewed crate's sqlx feature.

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design / implementation | `## Error Design` with `### Error Types`, `### Layer Mapping`, `### External Classification` |
| Review | `## Findings`, then `## Error Design` holding only `### Layer Mapping` and, when the input includes an external call, `### External Classification`, both describing the code as it exists today (the target state lives in each finding's `Fix`) |

```
## Error Design

### Error Types
| Type | Declared In | Variants | Matched By |
|------|-------------|----------|------------|

### Layer Mapping
| Layer | Input | Output | Surface Result |
|-------|-------|--------|----------------|

### External Classification
| External Error | Domain Error | Retryable? |
|----------------|--------------|------------|
```

Cell values: `Declared In` is the module path (one row per type). `Variants` lists the variant names, or `opaque (anyhow)` / `opaque (Box<dyn Error>)`. `Matched By` is `match`, `matches!`, `downcast_ref` or `?` plus the layer that does it (`match, IntoResponse`). Layer Mapping has one row per layer per path through it - `capture` via HTTP and `capture` via the worker are two rows. `Input` is the error the layer receives (a driver type, a variant from the layer below, a `JoinError`, an `Elapsed`); `Output` is what it returns (the variant it converts to) or `handled (<what is returned instead>)` when it consumes the error. `Surface Result` is what the outermost caller sees on that path - an HTTP status, a worker decision, a process exit code, or for a webhook route the status plus `ack` / `redeliver`. Worker decisions are `Retry | Drop | DeadLetter | Resolve`: `Retry` = return the error or nack with requeue, `Drop` = ack and discard, `DeadLetter` = publish to the DLQ then ack, `Resolve` = an indeterminate outcome the handler must look up before deciding (consumer mechanics: `rust-messaging-patterns`); an error the worker neither settles nor returns reads `none (<what is left behind>)`. `Retryable?` is `Yes | No | Indeterminate` - on a review, what the code does with the error today (one the caller re-sends unclassified is `Yes`). `External Error` covers anything crossing into the crate: an HTTP client error or status, a gRPC `Code`, a sqlx error kind or SQLSTATE, a timeout `Elapsed`. A table with no rows emits `None.` rather than being dropped; a cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries - a layer the input names but does not show gets one row of `unknown` cells.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {the rule broken}
- Consequence: {what the caller or the operator loses}
- Fix: {concrete edit}
```

Owned findings: `[Must]` when the defect loses information the caller needs (a severed chain, a swallowed `Result`, a string-matched error, a blanket `#[from]` that maps not-found to 500, a failure after a side effect that is only logged), corrupts state, panics on a reachable path, reaches the client with internal detail, or answers a processed webhook event with a status the sender redelivers; `[Recommend]` otherwise. Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not; a range is `file:start-end`. Order the blocks in four groups - owned `[Must]`, owned `[Recommend]`, then the not-owned blocks described below, `[Must]` then `[Recommend]` - and within a group by file in the order the input listed them (a listed directory's files in path order at the directory's position, a file listed twice at its first; files the input did not list after those, in path order), then position in the file. With no findings, `## Findings` holds the single line `None.` One root cause at several sites is one heading citing the first site in that order, with the rest named on the `Defect:` line. A defect this skill does not own (a detached task, a signature computed over the wrong bytes, a transaction held open) is still reported, never dropped: one block per such defect in the last two groups, labelled `[Must]` when it risks incorrect behaviour, data loss or a security hole and `[Recommend]` otherwise, with its `Defect:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- `anyhow::Error` or `Box<dyn Error>` in a library crate's public API
- Leaking driver or third-party error types, or their text, past the gateway
- Logging at every layer, or logging from a `Display` / `Debug` impl
- A `_ =>` arm in the error-to-response mapping
- Blind-retrying an indeterminate outcome
