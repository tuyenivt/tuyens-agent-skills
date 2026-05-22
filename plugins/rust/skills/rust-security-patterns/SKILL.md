---
name: rust-security-patterns
description: "Rust/Axum security review: authn/authz, JWT (RS256), validator input, SQL injection, Argon2, path traversal, secrets, unsafe, cargo-audit."
metadata:
  category: backend
  tags: [rust, security, jwt, authorization, validation, secrets, unsafe, cargo-audit]
user-invocable: false
---

# Rust Security Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing Rust web service code for OWASP-class vulnerabilities
- Implementing authn/authz, input validation, secret handling, or crypto
- Auditing `unsafe` blocks and dependency CVEs

For sqlx query mechanics see `rust-db-access`. For middleware wiring and `AppError` see `rust-web-patterns`. This skill covers the security-specific decisions only.

## Rules

- Validate every request DTO at the handler boundary via `validator::Validate`.
- Parameterize all SQL (`$1`, `$2`) -- never `format!` user input into queries.
- JWT: asymmetric (RS256/ES256) in production; validate `exp`, `iss`, `aud`.
- Authorize after authenticating -- claim presence is not permission.
- Hash passwords with Argon2 inside `spawn_blocking`; never on the async runtime.
- Load secrets from env/secret manager; never commit, never log, never return in errors.
- Justify every `unsafe` block with a `// SAFETY:` comment stating the invariant.
- Run `cargo audit --deny warnings` in CI.

## Patterns

### Input validation (bad/good)

```rust
// BAD: trusts JSON shape
async fn create(Json(req): Json<CreateUserRequest>) -> Result<_, AppError> {
    svc.create(req).await // no .validate() call
}
// GOOD
req.validate().map_err(|e| AppError::Validation(e.to_string()))?;
```

Constrain fields with `#[validate(length, email, range, regex)]` on the DTO. Reject unknown fields with `#[serde(deny_unknown_fields)]` for strict APIs.

### SQL injection (bad/good)

```rust
// BAD
let q = format!("SELECT * FROM users WHERE email = '{email}'");
sqlx::query(&q).fetch_all(pool).await?;
// GOOD
sqlx::query_as!(User, "SELECT * FROM users WHERE email = $1", email)
    .fetch_one(pool).await?;
```

`LIKE` patterns: bind `format!("%{}%", escape(input))` -- still parameterized.

### JWT validation

```rust
let mut v = Validation::new(Algorithm::RS256);
v.set_issuer(&[&state.jwt_issuer]);
v.set_audience(&[&state.jwt_audience]);
let data = decode::<Claims>(token, &state.decoding_key, &v)
    .map_err(|_| AppError::Unauthorized)?;
req.extensions_mut().insert(data.claims);
```

`Validation::new(_)` already enforces `exp`. Reject HS256 in production; key rotation is impossible without redeploy and a leaked secret signs valid tokens.

### Authorization (separate from authn)

```rust
// BAD: authenticated == authorized
async fn delete_user(claims: Claims, Path(id): Path<i64>) -> Result<_, AppError> {
    svc.delete(id).await // any logged-in user deletes anyone
}
// GOOD: explicit check against resource owner or role
if claims.sub != id.to_string() && !claims.roles.contains(&"admin".into()) {
    return Err(AppError::Forbidden);
}
```

Enforce at the service layer too -- handlers can be bypassed by internal callers.

### Password hashing

```rust
tokio::task::spawn_blocking(move || {
    let salt = SaltString::generate(&mut OsRng);
    Argon2::default().hash_password(pw.as_bytes(), &salt)
        .map(|h| h.to_string())
}).await?
```

Argon2 on the async runtime stalls the executor under load. Same rule applies to `verify_password`.

### Path traversal

```rust
// BAD
tokio::fs::read(format!("./uploads/{filename}")).await? // "../../etc/passwd"
// GOOD
let base = Path::new("./uploads").canonicalize()?;
let target = base.join(&filename).canonicalize()
    .map_err(|_| AppError::BadRequest("invalid path".into()))?;
if !target.starts_with(&base) {
    return Err(AppError::Forbidden);
}
tokio::fs::read(&target).await?
```

Canonicalize the *joined* path so symlinks and `..` resolve before the prefix check. `PathBuf::starts_with` is component-wise, not string prefix.

### Secrets

```rust
// BAD: hardcoded, or panics late
const JWT_SECRET: &str = "dev-secret-123";
// GOOD: fail fast at startup, never log
let jwt_secret = std::env::var("JWT_SECRET")
    .map_err(|_| anyhow!("JWT_SECRET required"))?;
```

Wrap sensitive values in `secrecy::Secret<String>` to redact from `Debug`/logs. `dotenvy::dotenv().ok()` only under `#[cfg(debug_assertions)]`.

### CORS

```rust
// BAD: in production
CorsLayer::permissive()
// GOOD
CorsLayer::new()
    .allow_origin(["https://app.example.com".parse().unwrap()])
    .allow_methods([Method::GET, Method::POST])
    .allow_headers([AUTHORIZATION, CONTENT_TYPE])
```

`allow_credentials(true)` + wildcard origin is rejected by browsers; combining them is a code smell.

### Unsafe blocks

```rust
// BAD
unsafe { std::slice::from_raw_parts(ptr, len) }
// GOOD
// SAFETY: ptr is non-null, aligned for T, points to `len` initialized
// elements valid for the lifetime of `buf`, and is not mutated concurrently.
unsafe { std::slice::from_raw_parts(ptr, len) }
```

Prefer safe alternatives (`bytes::Bytes`, `&[T]`). If `unsafe` is unavoidable, isolate it in a small module with a safe wrapper and a property test.

### Error responses

```rust
// BAD: leaks internals
Err(format!("db error: {e:?}"))
// GOOD: log full chain server-side, return generic message
tracing::error!("db error: {e:?}");
Err(AppError::Internal)
```

### Dependency audit

`cargo audit --deny warnings` in CI. Pin a `rust-toolchain.toml`. Review `cargo deny` for license + duplicate-dep gates if the project uses it.

## Output Format

Produce a security review with this structure:

```
Severity: {Critical | High | Medium | Low | Info}
Category: {Authn | Authz | Injection | Crypto | Secrets | Unsafe | Deps | Other}
Location: <file>:<line>
Finding: <one-sentence description of the vulnerability>
Evidence: <code snippet or specific call>
Fix: <minimal change, with the pattern name from this skill>
```

End with a coverage line:

```
Coverage: validation=<ok|gap>, authn=<ok|gap>, authz=<ok|gap>, sql=<ok|gap>,
          crypto=<ok|gap>, secrets=<ok|gap>, unsafe=<ok|n/a>, deps=<ok|gap>
```

Mark `gap` when the category was not addressed by the code under review.

## Avoid

- HS256 JWT, missing `iss`/`aud` checks, or trusting `alg` from the token header.
- Authenticated-equals-authorized handlers.
- `format!` into SQL, including `ORDER BY` and `LIMIT` clauses.
- `CorsLayer::permissive()` in production.
- Argon2 (or any CPU-bound hash) on the async runtime.
- Hardcoded secrets, secrets in `Debug` output, secrets in error responses.
- `unsafe` without a `// SAFETY:` invariant comment.
- Skipping `cargo audit` in CI; ignoring advisories without a documented waiver.
