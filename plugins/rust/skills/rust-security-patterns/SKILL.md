---
name: rust-security-patterns
description: "Rust security patterns: JWT authentication, input validation, SQL injection prevention, secrets management, CORS, dependency auditing with cargo-audit."
user-invocable: false
---

# Rust Security Patterns

## When to Use

- Implementing authentication and authorization in Axum services
- Reviewing code for OWASP Top 10 vulnerabilities
- Setting up input validation and sanitization
- Configuring secrets management and dependency scanning

## Rules

- Validate all input at the handler boundary - never trust user input
- Use parameterized queries exclusively - never string interpolation in SQL
- JWT validation must check `exp`, `iss`, `aud` claims - use asymmetric keys (RS256/ES256) in production
- Never expose internal error details or stack traces in API responses
- Secrets from environment variables or config files - never hardcoded
- Run `cargo audit` in CI for known CVEs

## Patterns

### JWT Authentication Middleware

```rust
use jsonwebtoken::{decode, DecodingKey, Validation, Algorithm};

#[derive(Debug, Deserialize, Clone)]
pub struct Claims {
    pub sub: String,
    pub exp: usize,
    pub iss: String,
}

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

    let mut validation = Validation::new(Algorithm::RS256);
    validation.set_issuer(&[&state.jwt_issuer]);
    validation.set_audience(&[&state.jwt_audience]);

    let token_data = decode::<Claims>(token, &state.decoding_key, &validation)
        .map_err(|_| AppError::Unauthorized)?;

    req.extensions_mut().insert(token_data.claims);
    Ok(next.run(req).await)
}
```

### Input Validation

```rust
use validator::Validate;

#[derive(Debug, Deserialize, Validate)]
pub struct CreateUserRequest {
    #[validate(length(min = 2, max = 100, message = "name must be 2-100 characters"))]
    pub name: String,
    #[validate(email(message = "invalid email format"))]
    pub email: String,
    #[validate(length(min = 8, max = 128, message = "password must be 8-128 characters"))]
    pub password: String,
}

async fn create_user(
    State(svc): State<Arc<UserService>>,
    Json(req): Json<CreateUserRequest>,
) -> Result<(StatusCode, Json<UserDto>), AppError> {
    req.validate().map_err(|e| AppError::Validation(e.to_string()))?;
    // proceed with validated input
}
```

### Password Hashing

```rust
use argon2::{Argon2, PasswordHash, PasswordHasher, PasswordVerifier};
use argon2::password_hash::SaltString;
use argon2::password_hash::rand_core::OsRng;

async fn hash_password(password: String) -> Result<String, AppError> {
    tokio::task::spawn_blocking(move || {
        let salt = SaltString::generate(&mut OsRng);
        let argon2 = Argon2::default();
        argon2
            .hash_password(password.as_bytes(), &salt)
            .map(|h| h.to_string())
            .map_err(|e| AppError::Internal(e.into()))
    })
    .await
    .map_err(|e| AppError::Internal(e.into()))?
}

async fn verify_password(password: &str, hash: &str) -> Result<bool, AppError> {
    let hash = hash.to_owned();
    let password = password.to_owned();
    tokio::task::spawn_blocking(move || {
        let parsed = PasswordHash::new(&hash)
            .map_err(|e| AppError::Internal(e.into()))?;
        Ok(Argon2::default().verify_password(password.as_bytes(), &parsed).is_ok())
    })
    .await
    .map_err(|e| AppError::Internal(e.into()))?
}
```

### CORS Configuration

```rust
use tower_http::cors::{CorsLayer, Any};

// Development
let cors = CorsLayer::permissive();

// Production - explicit origins
let cors = CorsLayer::new()
    .allow_origin(["https://app.example.com".parse().unwrap()])
    .allow_methods([Method::GET, Method::POST, Method::PUT, Method::DELETE])
    .allow_headers([AUTHORIZATION, CONTENT_TYPE])
    .max_age(Duration::from_secs(3600));
```

### Secrets Management

```rust
// Load from environment - never hardcode
let database_url = std::env::var("DATABASE_URL")
    .expect("DATABASE_URL must be set");
let jwt_secret = std::env::var("JWT_SECRET")
    .expect("JWT_SECRET must be set");

// Use dotenvy for local development only
#[cfg(debug_assertions)]
dotenvy::dotenv().ok();
```

### Dependency Auditing

```bash
# Install cargo-audit
cargo install cargo-audit

# Check for known vulnerabilities
cargo audit

# In CI pipeline
cargo audit --deny warnings
```

## Security Checklist

- [ ] All protected routes behind auth middleware
- [ ] JWT validation includes `exp`, `iss`, `aud` - RS256 or ES256 in production
- [ ] No raw SQL string interpolation - sqlx with `$1` parameterized queries
- [ ] Input validation with `validator` crate on all request DTOs
- [ ] CORS configured explicitly - no `permissive()` in production
- [ ] Secrets loaded from environment - no hardcoded credentials in source
- [ ] API error responses contain no stack traces or internal details
- [ ] `cargo audit` passing with no high-severity vulnerabilities
- [ ] Rate limiting applied to auth endpoints (tower::limit or governor)
- [ ] Password hashing uses Argon2 via `spawn_blocking` (not on async thread)

## Avoid

- Hardcoded secrets in source code
- String interpolation in SQL queries
- Exposing internal error details to clients
- `CorsLayer::permissive()` in production
- Symmetric JWT keys (HS256) in production - use RS256/ES256
- Password hashing on the async runtime (blocks the executor)
- Skipping `cargo audit` in CI
