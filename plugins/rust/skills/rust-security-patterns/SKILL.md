---
name: rust-security-patterns
description: "Rust/Axum security: default-deny router, JWT alg/iss/aud pinning, IDOR scoping, serde mass-assignment, sqlx params, webhook HMAC, argon2, SSRF."
metadata:
  category: backend
  tags: [rust, axum, security, jwt, authorization, mass-assignment, secrets, webhook, ssrf, unsafe, cargo-audit]
user-invocable: false
---

# Rust Security Patterns

> Load `Use skill: stack-detect` first. This skill reads `Framework` and `Database`: the router, middleware and extractor facts are Axum 0.8's (`route_layer`, `FromRequestParts` without `#[async_trait]`, `/{id}` paths, `DefaultBodyLimit`) and do not apply under actix-web - the rules do; placeholders are `$1` on PostgreSQL and `?` on MySQL/SQLite (sqlx passes SQL through unchanged, so write the driver's style); on `Database` `unknown` the examples keep `$1`. In a Cargo workspace the crate under review decides: its own dependencies in place of the detected values. Baseline: Rust 1.94+ (edition 2024: `std::env::set_var` is `unsafe`; `IpAddr::to_canonical`, `Ipv6Addr::is_unique_local`), Axum 0.8, jsonwebtoken 9+, argon2 0.5, secrecy 0.10, validator 0.18+, reqwest 0.12, getrandom 0.3, hmac 0.12. SQL mechanics live in `rust-db-access`; `AppError` / `IntoResponse` shape in `rust-error-handling`; router and middleware wiring in `rust-web-patterns`. This skill owns only the security-specific decisions.

## When to Use

- Implementing or reviewing authentication, authorization, input validation, secrets, or crypto in a Rust/Axum service
- Hardening webhook endpoints, file uploads, or outbound HTTP that takes user-controlled URLs
- Auditing JWT setup, password hashing, `unsafe` blocks, or dependency advisories

## Rules

- Default-deny: protected routes live on a router whose **last** call is `route_layer(auth)`; public endpoints are listed on a separate `public` router merged beside it. A layer covers only routes added before it, so a `.route()` chained after the layer is silently public
- A handler that needs a principal takes an `AuthUser` extractor - it cannot run unauthenticated, and a missing principal is a 401, never a panic
- JWT: `jsonwebtoken` with `Validation::new(<one Algorithm>)` - never a multi-family `algorithms` vec (HS/RS confusion); set `iss` and `aud` and require `exp`, `iss`, `aud` through `set_required_spec_claims`; HS256 key from env/secret manager (never committed) or RS256/ES256 for cross-service. `insecure_disable_signature_validation()` and trusting `decode_header` output are findings outside a test
- Request DTOs are explicit `Deserialize` structs; never deserialize a request body into a domain model, `serde_json::Value`, a `HashMap`, or a `#[serde(flatten)]` catch-all on a write path - that is mass assignment. `#[derive(Validate)]` checks nothing until `req.validate()` runs. Responses are DTOs too; never `Json(row)` on a model with `password_hash`
- Authorize after authenticating: scope every per-owner lookup by principal at the repository (`WHERE id = $1 AND user_id = $2`), not in the handler. An admin override is a second repository function chosen by role, not a flag that widens the scoped one
- SQL via `query!` / `.bind()` / `QueryBuilder::push_bind` only; never `format!` into SQL. Identifiers (sort column, direction) come from an enum, never the request
- `Command::new(bin).arg(..)` - never `sh -c` / `cmd /C` with user input; user input never becomes an argument the binary could read as an option or a coder prefix
- Tokens, nonces, salts from the OS CSPRNG (`getrandom::fill`, `OsRng`); MACs and hashes compared in constant time (`Mac::verify_slice`, `subtle::ConstantTimeEq`), never `==`
- Passwords: argon2id via the `argon2` crate, hash and verify inside `spawn_blocking`. API keys: never stored plaintext - sha256 at issuance, look up by hash
- Secrets load once at startup into a typed config, failing fast on absence **and** on empty; held as `SecretString` so `Debug` redacts; never logged - `#[tracing::instrument]` records every argument unless `skip`/`skip_all` names it
- `unsafe`: `#![forbid(unsafe_code)]` on every crate that needs none; each remaining block carries a `// SAFETY:` comment naming the invariant. Dependencies: `cargo audit` or `cargo deny check advisories` gates CI on `--locked` builds; a waiver names the advisory and an expiry
- A retryable write takes a client `Idempotency-Key`, scoped to the principal and bound to a hash of the body: same key + same body replays the first response, same key + different body is `409`, a key from another principal is unknown. The record holds body hash, state (`in_flight | done`), status and response, kept 24h; a same-key request while `in_flight` is `409`, a `5xx` releases the key, and an `in_flight` row older than the handler's timeout is resolved by a sweeper against the side effect's own record, never silently re-executed

## Patterns

### Default-deny router with explicit public allowlist

```rust
use axum::{Router, middleware, routing::{get, post}};

// Bad - the layer wraps only the routes before it: /internal/debug is public
let app = Router::new()
    .route("/orders", get(list_orders))
    .route_layer(middleware::from_fn_with_state(state.clone(), require_auth))
    .route("/internal/debug", get(debug))
    .with_state(state);

// Good - two named routers; route_layer is the last call on `protected`, and a later
// .route() on it is the regression a review flags
let public = Router::new()
    .route("/auth/login", post(login))
    .route("/webhooks/github", post(github_webhook)) // the signature is the auth - see Webhook signature verification
    .route("/healthz", get(health));
let protected = Router::new()
    .route("/orders", get(list_orders))
    .route("/orders/{id}", get(get_order))
    .route("/internal/debug", get(debug).route_layer(middleware::from_fn(require_admin)))
    .route_layer(middleware::from_fn_with_state(state.clone(), require_auth));
let app = Router::new().merge(public).merge(protected).with_state(state);
```

### JWT validation (jsonwebtoken)

```rust
use jsonwebtoken::{Algorithm, DecodingKey, Validation, decode};

#[derive(Clone)]
pub struct AppState { pub pool: sqlx::PgPool, pub jwt_key: DecodingKey, pub jwt_validation: Validation }

pub fn jwt_validation(issuer: &str, audience: &str) -> Validation { // built once at startup
    let mut v = Validation::new(Algorithm::RS256); // exactly one algorithm; jsonwebtoken has no `none`
    v.set_issuer(&[issuer]);
    v.set_audience(&[audience]);
    v.set_required_spec_claims(&["exp", "iss", "aud"]); // a token missing one is rejected, not skipped
    v
}

fn verify(st: &AppState, raw: &str) -> Result<Claims, jsonwebtoken::errors::Error> {
    Ok(decode::<Claims>(raw, &st.jwt_key, &st.jwt_validation)?.claims)
}
```

- Access tokens 5-15 min, revocable through a denylist keyed on `jti`. Refresh tokens are opaque random strings (not nested JWTs), stored **hashed** server-side, rotated on every use
- RS256/ES256: `DecodingKey::from_rsa_pem` from a trusted source, or a JWKS cached with a TTL and selected by `kid`; `Validation::new` allows 60s `leeway` by default
- Transport: `Authorization: Bearer` (API) or `Secure; HttpOnly; SameSite=Lax` cookies (browser). Never a JWT in a query string - logs, history and `Referer` capture it

### Auth middleware and extractor shape

```rust
use axum::extract::{FromRequestParts, Request, State};
use axum::http::{StatusCode, header::AUTHORIZATION, request::Parts};
use axum::{middleware::Next, response::Response};

#[derive(Clone, Copy, PartialEq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Role { User, Admin }

#[derive(Clone, serde::Deserialize)]
pub struct Claims { pub sub: uuid::Uuid, pub role: Role }

pub async fn require_auth(State(st): State<AppState>, mut req: Request, next: Next) -> Result<Response, StatusCode> {
    let raw = req.headers().get(AUTHORIZATION).and_then(|v| v.to_str().ok())
        .and_then(|v| v.split_once(' '))
        .filter(|(scheme, _)| scheme.eq_ignore_ascii_case("bearer")) // the scheme is case-insensitive (RFC 9110)
        .map(|(_, token)| token)
        .ok_or(StatusCode::UNAUTHORIZED)?;
    let claims = verify(&st, raw).map_err(|_| StatusCode::UNAUTHORIZED)?; // no body details
    req.extensions_mut().insert(claims);
    Ok(next.run(req).await)
}

pub struct AuthUser(pub Claims);

impl<S: Send + Sync> FromRequestParts<S> for AuthUser {
    type Rejection = StatusCode;
    async fn from_request_parts(parts: &mut Parts, _: &S) -> Result<Self, Self::Rejection> {
        // `Extension<Claims>` would reject a missing value with 500; this is a 401 on any route
        parts.extensions.get::<Claims>().cloned().map(AuthUser).ok_or(StatusCode::UNAUTHORIZED)
    }
}

pub async fn require_admin(AuthUser(c): AuthUser, req: Request, next: Next) -> Result<Response, StatusCode> {
    if c.role != Role::Admin { return Err(StatusCode::FORBIDDEN); }
    Ok(next.run(req).await)
}
```

### Login flow hardening

The login handler is the credential-stuffing target. Rate-limit by IP and by email (separate buckets, `tower_governor` or a keyed limiter) before any hashing - behind a load balancer `ConnectInfo<SocketAddr>` is the proxy's address, and `X-Forwarded-For` is spoofable unless the trusted proxy overwrites it. Then:

```rust
use argon2::{Argon2, PasswordVerifier, password_hash::PasswordHash};
use secrecy::{ExposeSecret, SecretString};

let user = repo.find_by_email(&req.email).await?; // Option<User>
// a missing user verifies against a dummy hash computed at startup with the same params: equal work
let phc = user.as_ref().map_or_else(|| st.dummy_phc.clone(), |u| u.password_hash.clone());
let pw: SecretString = req.password;
let ok = tokio::task::spawn_blocking(move || {
    PasswordHash::new(&phc).is_ok_and(|h| Argon2::default().verify_password(pw.expose_secret().as_bytes(), &h).is_ok())
}).await?;
if !ok || user.is_none() {
    return Err(AppError::InvalidCredentials); // one variant: one status, one string for both cases
}
```

Any divergence between "user missing" and "wrong password" - status, body, or timing - is a user-enumeration oracle.

### API key storage

```rust
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use sha2::{Digest, Sha256};

// Bad - lookup by plaintext; a DB compromise leaks every customer's key
sqlx::query_as::<_, ApiKey>("SELECT * FROM api_keys WHERE key = $1").bind(raw);

// Good - hash at issuance, store and look up by hash
pub fn issue_api_key() -> Result<(String, Vec<u8>), getrandom::Error> {
    let mut b = [0u8; 32];
    getrandom::fill(&mut b)?;
    let plaintext = format!("sk_{}", URL_SAFE_NO_PAD.encode(b));
    let hash = Sha256::digest(plaintext.as_bytes()).to_vec();
    Ok((plaintext, hash))
}
// verify: WHERE key_hash = $1 AND revoked_at IS NULL, bound to Sha256::digest(raw)
```

Store a key prefix (`sk_xxxx...`) in plaintext beside the hash so users can identify keys. Argon2 is overkill for high-entropy random keys. Migrating a plaintext table: add `key_hash`, backfill, switch lookups, then drop the plaintext column - no rotation needed.

### IDOR: scope at the repository, not the handler

```rust
use sqlx::PgPool;
use uuid::Uuid;

// Bad - loaded for anyone; the ownership check is per-handler and easy to forget on the next endpoint
let order = repo.find(id).await?.ok_or(StatusCode::NOT_FOUND)?;
if order.user_id != user.sub { return Err(StatusCode::NOT_FOUND); }

// Good - the principal is a parameter of the query; impossible to forget
#[derive(sqlx::FromRow, serde::Serialize)]
pub struct Order { pub id: Uuid, pub user_id: Uuid, pub total_cents: i64 }

pub async fn find_for_owner(pool: &PgPool, id: Uuid, owner: Uuid) -> Result<Option<Order>, sqlx::Error> {
    sqlx::query_as::<_, Order>("SELECT id, user_id, total_cents FROM orders WHERE id = $1 AND user_id = $2")
        .bind(id).bind(owner).fetch_optional(pool).await
}
```

Multi-tenant isolation is the same shape with `tenant_id`; PostgreSQL row-level security (`SET LOCAL app.tenant_id` per transaction) is the backstop when every query must be scoped.

### Mass-assignment prevention

```rust
use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use validator::Validate;

// Bad - the request body is the domain model: role, is_admin, owner_id are client-controlled
async fn create(Json(user): Json<User>) -> impl IntoResponse { /* ... */ }
// Bad - a catch-all writes whatever keys arrive
#[derive(Deserialize)]
pub struct UpdateUser { #[serde(flatten)] pub fields: HashMap<String, serde_json::Value> }

// Good - request DTO with explicit fields; the server sets privileged ones
#[derive(Deserialize, Validate)]
#[serde(deny_unknown_fields)] // not supported together with #[serde(flatten)]
pub struct CreateUserRequest {
    #[validate(length(min = 1, max = 100))] pub name: String,
    #[validate(email)] pub email: String,
    // role, is_admin, owner_id, tenant_id, verified deliberately absent
}

// Good - response DTO; never Json(user_row) on a model holding password_hash / mfa_secret
#[derive(Serialize)]
pub struct UserResponse { pub id: Uuid, pub name: String, pub email: String }
```

A PATCH that must tell "absent" from "set to null" uses `Option<Option<T>>` (`serde_with::rust::double_option`), never a map. A `#[serde(skip_serializing)]` on the model is a fallback, not the design - the next field added is serialized by default.

### Input validation

```rust
use axum::{Json, extract::Path};

#[derive(Deserialize, Validate)]
pub struct UpdateOrderRequest { #[validate(range(min = 1, max = 999))] pub quantity: u32 }

async fn update_order(
    AuthUser(c): AuthUser,
    Path(id): Path<Uuid>, // a non-UUID is rejected with 400 before the handler runs
    Json(req): Json<UpdateOrderRequest>, // body extractor last
) -> Result<StatusCode, AppError> {
    req.validate()?; // derive(Validate) alone validates nothing
    // ...
}
```

- `Json<T>` rejects malformed JSON (400), a type mismatch or missing field (422), and a wrong `Content-Type` (415); range, length and format rules are `validator`'s. A `ValidatedJson` extractor that calls `validate()` makes the check structural
- Body extractors are capped at 2 MB by `DefaultBodyLimit`; `DefaultBodyLimit::disable()` is an `Availability` finding, and upload routes set their own `max`

### SQL parameterization

```rust
use sqlx::{AssertSqlSafe, Postgres, QueryBuilder};

// Bad - format! into SQL is injection whatever the type of `role`; sqlx 0.9 compiles it only behind `AssertSqlSafe`, so every `AssertSqlSafe` is a site to audit
sqlx::query(AssertSqlSafe(format!("UPDATE users SET role = '{role}' WHERE id = {id}"))).execute(&pool).await?;
// Good - bound, and compile-checked against the schema
sqlx::query!("UPDATE users SET role = $1 WHERE id = $2", role, id).execute(&pool).await?;

// Identifiers cannot be bound: deserialize into an enum, map to a literal
#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SortBy { Created, Name } // any other value fails deserialization

let col = match q.sort.unwrap_or(SortBy::Created) { SortBy::Created => "created_at", SortBy::Name => "name" };
let mut qb = QueryBuilder::<Postgres>::new("SELECT id, name FROM users WHERE tenant_id = ");
qb.push_bind(tenant_id).push(" ORDER BY ").push(col).push(" DESC LIMIT ").push_bind(limit);
```

`WHERE name ILIKE '%' || $1 || '%'` is parameterized and safe; escaping `%` / `_` for literal matching is `rust-db-access`'s.

### Path traversal

```rust
use std::path::{Component, Path};

// Bad - Path::join with an absolute argument REPLACES the base: join("/etc/passwd") is /etc/passwd
let target = Path::new("/srv/uploads").join(&name);

// Good - exactly one normal component, then join
let mut parts = Path::new(&name).components();
let (Some(Component::Normal(file)), None) = (parts.next(), parts.next()) else {
    return Err(StatusCode::BAD_REQUEST); // "..", "/x", "C:\\x", "a/b"
};
let bytes = tokio::fs::read(Path::new("/srv/uploads").join(file)).await?;
```

When users can plant symlinks under the base, open through a capability handle (`cap_std::fs::Dir`), which refuses escapes. For uploads: store under a server-generated name (a UUID), sniff the type from magic bytes (`infer`), not the `Content-Type` header or extension, and serve with `Content-Disposition: attachment` from outside any static-file root.

### Command injection

```rust
use tokio::process::Command;

// Bad - the shell interprets metacharacters in user input -> RCE
Command::new("sh").arg("-c").arg(format!("convert {user_file} out.png"));
// Still bad - no shell, but "-delay" or "msl:evil" is read by convert as an option or a coder
Command::new("convert").arg(&user_file).arg("out.png");
// Good - server-generated path, binary from an allowlist, explicit format prefix ("--" guards only a leading "-")
Command::new("convert").arg(format!("png:{}", stored_path.display())).arg("out.png");
```

### Webhook signature verification

```rust
use axum::{body::Bytes, http::HeaderMap};
use hmac::{Hmac, Mac};

// Bytes, not Json<T>: the MAC is over the exact raw body (Bytes keeps the DefaultBodyLimit)
pub async fn github_webhook(State(st): State<AppState>, headers: HeaderMap, body: Bytes) -> StatusCode {
    let Some(sig) = headers.get("x-hub-signature-256").and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("sha256=")).and_then(|h| hex::decode(h).ok())
    else { return StatusCode::BAD_REQUEST };
    let mut mac = Hmac::<Sha256>::new_from_slice(st.webhook_secret.expose_secret().as_bytes())
        .expect("HMAC accepts any key length");
    mac.update(&body);
    if mac.verify_slice(&sig).is_err() { // constant-time, over the decoded MAC - never `==` on the header string
        return StatusCode::BAD_REQUEST; // never a 2xx
    }
    let Ok(evt) = serde_json::from_slice::<WebhookEvent>(&body) else { return StatusCode::BAD_REQUEST };
    // inbox: insert (provider, event_id) under a unique index in the state change's transaction;
    // a unique violation means already applied -> 200 without acting
    StatusCode::OK
}
```

Stripe signs `"{t}.{payload}"` into `Stripe-Signature: t=...,v1=...` with a 5-minute tolerance - use the SDK's verifier or check `t` yourself; replay protection is that timestamp check plus the inbox. Route the webhook on the `public` router; the signature is the only auth. Stripe retries on non-2xx for up to 3 days, so keep inbox rows past that window (30 days is a safe default). Outbound callbacks to partners get the same treatment in reverse: `X-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "<t>.<body>">` with a per-partner secret, rotated by dual-signing through the overlap.

### Password hashing

```rust
use argon2::{PasswordHasher, password_hash::{SaltString, rand_core::OsRng}};

pub async fn hash_password(pw: SecretString) -> anyhow::Result<String> {
    tokio::task::spawn_blocking(move || {
        let salt = SaltString::generate(&mut OsRng);
        // Argon2::default() is argon2id, m=19 MiB, t=2, p=1; the PHC string carries salt and params
        Argon2::default().hash_password(pw.expose_secret().as_bytes(), &salt)
            .map(|h| h.to_string())
            .map_err(|e| anyhow::anyhow!("hash: {e}"))
    }).await? // outer: JoinError; inner: the hash result
}
```

Argon2 on the async runtime stalls a worker thread for tens of ms per call - `spawn_blocking` for hash and verify alike. An existing bcrypt table keeps `bcrypt::verify` and rehashes to argon2id on the next successful login. Never `Sha256::digest(pw)` - fast hashes are crackable.

### Secrets and config

```rust
// Bad - silent fallback ships a known secret to production
let secret = std::env::var("JWT_SECRET").unwrap_or_else(|_| "dev-secret".into());

// Good - typed, loaded once, fails fast on missing and on empty; Debug prints [REDACTED]
pub struct Config { pub database_url: SecretString, pub jwt_secret: SecretString }

fn required(name: &str) -> anyhow::Result<SecretString> {
    let v = std::env::var(name).map_err(|_| anyhow::anyhow!("{name} is required"))?;
    anyhow::ensure!(!v.trim().is_empty(), "{name} is empty");
    Ok(SecretString::from(v))
}
```

Secrets live in Vault / AWS Secrets Manager / GCP Secret Manager / Doppler; `.env` (via `dotenvy`) for local dev only, gitignored. Log a stable id (`user_id = %id`), never a token or a full user record.

### SSRF defence

When a user-controlled value flows into an outbound URL:

1. `url::Url::parse` and reject unexpected schemes and non-standard ports
2. Check an IP-literal host directly - the connector skips DNS for it, so a resolver filter never sees `http://169.254.169.254/`
3. Enforce the block on the **resolved** addresses through `ClientBuilder::dns_resolver`: the connector dials only what the resolver returns, so DNS rebinding cannot slip a private address past a separate pre-check. Block cloud metadata (`169.254.169.254`, `fd00:ec2::254`), loopback, RFC1918, link-local, unique-local, and the unspecified address

```rust
use std::net::{IpAddr, SocketAddr};
use std::sync::Arc;
use reqwest::dns::{Addrs, Name, Resolve, Resolving};

type BoxError = Box<dyn std::error::Error + Send + Sync>;

fn is_public(ip: IpAddr) -> bool {
    match ip.to_canonical() { // ::ffff:127.0.0.1 -> 127.0.0.1
        IpAddr::V4(v4) => !(v4.is_private() || v4.is_loopback() || v4.is_link_local() || v4.is_unspecified() || v4.is_broadcast()),
        IpAddr::V6(v6) => !(v6.is_loopback() || v6.is_unspecified() || v6.is_unique_local() || v6.is_unicast_link_local()),
    }
}

struct PublicOnly;
impl Resolve for PublicOnly {
    fn resolve(&self, name: Name) -> Resolving {
        Box::pin(async move {
            let addrs: Vec<SocketAddr> = tokio::net::lookup_host((name.as_str(), 0)).await?
                .filter(|a| is_public(a.ip())).collect();
            if addrs.is_empty() { return Err("blocked: no public address".into()); }
            Ok::<Addrs, BoxError>(Box::new(addrs.into_iter()))
        })
    }
}

let client = reqwest::Client::builder()
    .dns_resolver(Arc::new(PublicOnly))
    .no_proxy() // a system proxy (HTTP_PROXY, on by default) resolves the target itself, bypassing the resolver
    .redirect(reqwest::redirect::Policy::limited(3)) // redirect hosts re-resolve through PublicOnly; IP literals need a custom policy
    .timeout(std::time::Duration::from_secs(10)) // reqwest has no default timeout
    .build()?;
```

Cap the response body (read `chunk()` until a byte budget) to defeat oversized-response DoS. `100.64.0.0/10` (CGNAT) is not covered by the stable predicates; add it when the platform routes it.

### CSPRNG, TLS and CORS

```rust
use rand::{RngCore, SeedableRng, rngs::SmallRng};

// Bad - predictable: seeded or non-cryptographic generators
let token = SmallRng::seed_from_u64(now_secs).next_u64();
let token = fastrand::u64(..);

// Good
let mut b = [0u8; 32];
getrandom::fill(&mut b)?;
let token = URL_SAFE_NO_PAD.encode(b);

// Bad in any non-test path - disables TLS verification
reqwest::Client::builder().danger_accept_invalid_certs(true);
// Bad - reflects any Origin with credentials: every site can read authenticated responses
tower_http::cors::CorsLayer::very_permissive();
```

`danger_accept_invalid_certs` / `danger_accept_invalid_hostnames` (or a custom rustls `ServerCertVerifier`) is acceptable only behind a documented test fixture; a partner sandbox with a self-signed certificate gets its CA added via `add_root_certificate`. CORS for a credentialed browser client lists exact origins (`AllowOrigin::list`); `AllowOrigin::mirror_request()` with `allow_credentials(true)` is the same hole as `very_permissive`.

### `unsafe` and dependency audit

```rust
#![forbid(unsafe_code)] // crate root of every crate that needs none

// In the crate that does:
// SAFETY: `ptr` is non-null, aligned, and points to `len` initialized `T`s that outlive `buf`
// and are not mutated while the slice lives.
let buf = unsafe { std::slice::from_raw_parts(ptr, len) };
```

Keep `unsafe` in a small module behind a safe API; enable `clippy::undocumented_unsafe_blocks`; run Miri (`cargo +nightly miri test`) on that crate. In edition 2024 `std::env::set_var` / `remove_var` are `unsafe` - calling them after threads start is a data race on the environment. CI runs `cargo audit` (RustSec) or `cargo deny check advisories bans sources` against the committed `Cargo.lock`; a waiver lives in `deny.toml` / `.cargo/audit.toml` with the advisory ID, a reason and an expiry.

## Output Format

A **review** targets supplied code: emit `## Findings` and close with one coverage line naming what was not examined (routes, files, or layers the input did not supply), so silence is not read as a clean bill. An **audit** targets a named surface or a whole service: `## Findings`, then `## Remediation` with the table below, then `**Verdict:**` one line answering "are we ready" with the condition, then the coverage line. When invoked from an **implementation** workflow, emit the decision table, one row per decision the brief asked for plus any prerequisite the code needs first (marked `(prerequisite)`), with code for each decision that needs it under `### <Concern>` headings in row order; existing code handed with the brief that violates a Rule emits `## Findings` first; close with the coverage line naming the surfaces the brief did not supply (callers, routes, config).

Every finding carries exactly one severity:

```
## Findings

### [{Critical | High | Medium | Low}] {file:line | file:start-end | file:<symbol> | <area>}{ (unverified)}

- Category: {AuthN | AuthZ | Validation | Injection | Crypto | Secrets | SSRF | Traversal | Exposure | Availability | Unsafe | Dependencies}
- Code: {one-line citation}
- Attack scenario: {concrete exploit, regression risk, or topology-dependent note}
- Chain: {locators of the findings this one compounds with, comma-separated}
- Fix: {concrete Rust change with code}
```

`Critical` = unauthenticated compromise, cross-tenant or cross-account data access, arbitrary file or command execution, memory corruption reachable from request input; `High` = authenticated privilege escalation, credential disclosure, or a security control that is present but inert (a `Validate` derive never called, a route chained after its auth layer); `Medium` = defense-in-depth gap or an information oracle; `Low` = hardening. Judge by what an attacker gains, not by matching the wording. `(unverified)` marks a finding whose impact depends on code the input did not supply - keep the severity the exploit would have and say what to check. `Exposure` covers debug routes, over-serialized responses, PII, and sensitive values in logs or `#[instrument]` fields; `Unsafe` covers an `unsafe` block without a stated invariant or with one the code does not uphold; `Dependencies` covers RustSec advisories and a missing audit gate - an advisory on a reachable path takes its exploit's severity, an unmaintained crate is `Low`; `Availability` covers missing rate limits, uncapped bodies, and request-path panics. A correct check at the wrong layer (handler instead of repository) is `Low`; severity is judged at exploit time - a control that makes the path unreachable today goes in `Attack scenario:`, not the label. Order owned findings by severity, then by file in the order the input listed them, then line; with no findings, `## Findings` holds the single line `None.`; cite `file:line` when the input carries line numbers, `file:<symbol>` or `<area>` when it is a snippet or prose (say so once at the top rather than inventing numbers); a range is `file:start-end`. One root cause at several sites is one heading citing the first site, with the rest named on the `Code:` line. A `Chain:` line exists only on compounding findings - on each of them, naming the others by locator - and marks them as such (a forged token that then reaches a tenant-scoping gap); each keeps its own severity, and partial remediation of a chain buys much less than the finding count suggests. A defect this skill does not own (a detached `tokio::spawn`, a transaction held open across an HTTP call) is still reported, never dropped: one block per such defect after every owned finding, in that same order among themselves, labelled by the criteria above, with its `Attack scenario:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

```
## Remediation
| # | Finding | Severity | Effort | Ship first? |
|---|---------|----------|--------|-------------|
```

One row per finding heading, `Finding` being the heading's locator plus a short title, ordered by what removes an exploitable path first. `Effort` is `S | M | L` (hours / a day / a sprint). `Ship first?` is `Yes` on every row that closes an exploitable path on its own, `No` otherwise - an `(unverified)` row is judged by the exploit it would have. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries.

```
| Concern | Decision | Rationale |
|---------|----------|-----------|
| JWT alg | RS256 via Validation::new, iss/aud/exp required | cross-service verification, key in JWKS |
| Request DTO | `CreateUserRequest` without role/owner_id, deny_unknown_fields | mass-assignment guard |
```

## Avoid

- `Json<User>` (a domain model) as a write-path extractor, or `Json(row)` as a response
- `format!` into any SQL string, including `ORDER BY` and `LIMIT`
- `sh -c` / `cmd /C` with any user-controlled segment
- `rand::rngs::SmallRng`, `StdRng::seed_from_u64`, `fastrand`, or timestamps for tokens, nonces, or secrets
- `==` on MACs, signatures, or hashes (timing attack)
- API keys stored or looked up in plaintext
- `danger_accept_invalid_certs(true)` outside a test fixture
- `CorsLayer::very_permissive()` or a mirrored origin with credentials in production
- `#[tracing::instrument]` on a function taking a password, token, or `Authorization` header without `skip`
- Argon2 or bcrypt on the async runtime instead of `spawn_blocking`
- `unwrap_or("dev")` env fallbacks for secrets
- Login responses that differ between "user missing" and "wrong password"
