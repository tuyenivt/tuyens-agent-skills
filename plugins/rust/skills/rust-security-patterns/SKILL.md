---
name: rust-security-patterns
description: "Rust/Axum security: JWT (RS256, iss/aud), validator DTOs, mass-assignment, secrets, password hashing off-runtime, CORS, unsafe, cargo-audit."
metadata:
  category: backend
  tags: [rust, security, jwt, authorization, validation, secrets, mass-assignment, cors, unsafe, cargo-audit]
user-invocable: false
---

# Rust Security Patterns

> Load `Use skill: stack-detect` first. SQL parameterization mechanics live in `rust-db-access`; `AppError`/`IntoResponse` shape in `rust-error-handling`; router/extractor wiring in `rust-web-patterns`. This skill owns only the security-specific decisions.

## When to Use

- Reviewing Rust web service code for OWASP-class vulnerabilities
- Implementing authn/authz, input validation, secret handling, or crypto
- Auditing `unsafe` blocks and dependency CVEs

## Rules

- Validate every request DTO at the handler boundary via `validator::Validate`. Reject unknown fields with `#[serde(deny_unknown_fields)]` on mutation DTOs.
- Update DTOs declare each mutable field explicitly. Never accept `serde_json::Value`, `HashMap<String, Value>`, or `#[serde(flatten)]` catch-alls into write paths - that is mass assignment.
- JWT: asymmetric (RS256/ES256) in production. Construct `Validation::new(Algorithm::RS256)` so the alg is fixed at verification time (prevents `alg=none` and HS/RS confusion); set `iss` and `aud`.
- Authorize after authenticating. Check ownership or role against the target resource at the service layer, not just the handler.
- Run any CPU-bound hash (Argon2/bcrypt/scrypt) inside `tokio::task::spawn_blocking`.
- Load secrets from env/secret manager at startup, fail fast on absence, wrap in `secrecy::SecretString` so `Debug`/logs redact them. Never log tokens, password hashes, or full user records.
- Justify every `unsafe` block with a `// SAFETY:` comment naming the invariant the caller upholds.
- Run `cargo audit --deny warnings` in CI; pin a `rust-toolchain.toml`.

## Patterns

### Input validation + strict deserialization

```rust
#[derive(Deserialize, Validate)]
#[serde(deny_unknown_fields)]
pub struct CreateUser {
    #[validate(length(min = 2, max = 100))] pub name: String,
    #[validate(email)] pub email: String,
}

async fn create(Json(req): Json<CreateUser>) -> Result<_, AppError> {
    req.validate().map_err(|e| AppError::Validation(e.to_string()))?;
    svc.create(req).await
}
```

Bad: calling `svc.create(req).await` without `.validate()` - `serde` checks types but not lengths, ranges, formats.

### Mass assignment

```rust
// BAD: client controls which columns get written
#[derive(Deserialize)]
pub struct UpdateUser { #[serde(flatten)] pub fields: serde_json::Value }

// BAD: even an explicit map is unsafe - keys can include `is_admin`, `password_hash`
pub struct UpdateUser { pub fields: HashMap<String, serde_json::Value> }

// GOOD: explicit, typed, validated; `Option` distinguishes "absent" from "set to null"
#[derive(Deserialize, Validate)]
#[serde(deny_unknown_fields)]
pub struct UpdateUser {
    #[validate(length(min = 2, max = 100))] pub name: Option<String>,
    #[validate(email)] pub email: Option<String>,
}
```

Privilege fields (`role`, `is_admin`, `tenant_id`, `password_hash`) never appear on user-facing DTOs - they belong on admin-only or system-only DTOs.

### JWT verification

```rust
let mut v = Validation::new(Algorithm::RS256);   // fixes alg; rejects alg=none and HS-signed tokens
v.set_issuer(&[&state.jwt_issuer]);
v.set_audience(&[&state.jwt_audience]);
let data = decode::<Claims>(token, &state.decoding_key, &v)
    .map_err(|_| AppError::Unauthorized)?;
req.extensions_mut().insert(data.claims);
```

`Validation::new(_)` enforces `exp` by default. HS256 in production means a leaked symmetric secret signs valid tokens for every service that trusts the issuer, and key rotation requires synchronized redeploys.

### Authorization (separate from authn)

```rust
// BAD: any authenticated user can delete anyone
async fn delete_user(claims: Claims, Path(id): Path<i64>) -> Result<_, AppError> {
    svc.delete(id).await
}
// GOOD: explicit ownership-or-role check, enforced again in the service
if claims.sub != id.to_string() && !claims.roles.contains(&"admin".into()) {
    return Err(AppError::Forbidden);
}
```

Repeat the check in the service: handlers can be bypassed by internal callers, background jobs, or test fixtures.

### Password hashing off the runtime

```rust
let hash = tokio::task::spawn_blocking(move || {
    let salt = SaltString::generate(&mut OsRng);
    Argon2::default()
        .hash_password(pw.as_bytes(), &salt)
        .map(|h| h.to_string())
        .map_err(AppError::from)
})
.await
.map_err(|e| AppError::Internal(anyhow!("hash task panicked: {e}")))??;
```

Argon2/bcrypt/scrypt on the async runtime stall the executor for tens of ms per call. Same rule applies to `verify`. Note the `??`: outer for `JoinError`, inner for the hash result.

### Path traversal

```rust
let base = Path::new("./uploads").canonicalize()?;
let target = base.join(&filename).canonicalize()
    .map_err(|_| AppError::BadRequest("invalid path".into()))?;
if !target.starts_with(&base) { return Err(AppError::Forbidden); }
tokio::fs::read(&target).await?
```

Canonicalize the *joined* path so `..` and symlinks resolve before the prefix check. `PathBuf::starts_with` is component-wise, not string prefix - `./uploads-other` cannot bypass it.

### Secrets

```rust
// BAD
const JWT_SECRET: &str = "dev-secret-123";
let s = std::env::var("JWT_SECRET").unwrap_or("dev".into());  // silent fallback

// GOOD: fail fast, redact
let jwt_secret: SecretString = std::env::var("JWT_SECRET")
    .map_err(|_| anyhow!("JWT_SECRET required"))?.into();
```

`dotenvy::dotenv().ok()` only under `#[cfg(debug_assertions)]`. Strip secrets and full user records from `tracing` events - log a stable id (`user_id=42`) instead.

### CORS

```rust
// BAD in production
CorsLayer::permissive()
// BAD: wildcard origin with credentials is a CSRF vector (and browsers reject it)
CorsLayer::new().allow_origin(Any).allow_credentials(true)
// GOOD
CorsLayer::new()
    .allow_origin(["https://app.example.com".parse().unwrap()])
    .allow_methods([Method::GET, Method::POST])
    .allow_headers([AUTHORIZATION, CONTENT_TYPE])
```

### SQL injection

Use the `sqlx::query!` / `query_as!` macros with `$1`, `$2`. See `rust-db-access` for the full pattern set including `LIKE` escaping and dynamic `ORDER BY`. Flag any `format!` into a SQL string as Critical here regardless.

### Unsafe blocks

```rust
// BAD
unsafe { std::slice::from_raw_parts(ptr, len) }
// GOOD
// SAFETY: ptr is non-null, aligned for T, points to `len` initialized
// elements valid for the lifetime of `buf`, and is not aliased mutably.
unsafe { std::slice::from_raw_parts(ptr, len) }
```

Prefer safe alternatives (`bytes::Bytes`, `&[T]`). If `unsafe` is unavoidable, isolate it in a small module with a safe wrapper.

### Dependency audit

`cargo audit --deny warnings` in CI. Add `cargo deny` for license + duplicate-dep gates when the project requires it. Document any advisory waiver in `audit.toml` with an expiry date.

## Output Format

One Finding per issue:

```
Severity: {Critical | High | Medium | Low | Info}
Category: {Authn | Authz | Injection | MassAssignment | Crypto | Secrets | CORS | Unsafe | Deps | Other}
Location: <file>:<line>
Finding: <one-sentence vulnerability description>
Evidence: <code snippet or specific call>
Fix: <minimal change, referencing a Pattern by name>
```

End with:

```
Coverage: validation={ok|gap}, authn={ok|gap}, authz={ok|gap}, sql={ok|gap},
          mass-assignment={ok|gap}, crypto={ok|gap}, secrets={ok|gap},
          cors={ok|gap}, unsafe={ok|n/a}, deps={ok|gap}
Summary: <N> findings (<C> Critical, <H> High, <M> Medium, <L> Low)
```

Use `gap` when the category was not addressed by the code under review; `n/a` only for `unsafe` when the codebase contains no `unsafe` blocks.

## Avoid

- HS256 in production, missing `iss`/`aud` checks, trusting `alg` from the token header.
- Authenticated-equals-authorized handlers; authorization only in the handler, not the service.
- Mass-assignment DTOs: `serde_json::Value`, `HashMap<String, Value>`, `#[serde(flatten)]` into write paths.
- `format!` into SQL anywhere (including `ORDER BY`, `LIMIT`).
- `CorsLayer::permissive()` in production; wildcard origin with `allow_credentials(true)`.
- CPU-bound hashing on the async runtime.
- Hardcoded secrets, `unwrap_or("dev")` env fallbacks, secrets in `Debug` output, tokens/PII in tracing events.
- `unsafe` without a `// SAFETY:` invariant comment.
- Skipping `cargo audit` in CI; ignoring advisories without a dated waiver.
