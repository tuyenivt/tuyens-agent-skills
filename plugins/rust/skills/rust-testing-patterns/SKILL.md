---
name: rust-testing-patterns
description: "Rust testing patterns: unit tests with mockall, async tests with tokio::test, integration tests with testcontainers, handler tests with tower oneshot, and property-based testing with proptest."
metadata:
  category: backend
  tags: [rust, testing, mockall, testcontainers, proptest, tokio]
user-invocable: false
---

# Rust Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing a test strategy for a new Rust service
- Writing unit tests for handlers, services, or domain logic
- Writing integration tests against a real PostgreSQL database
- Reviewing test quality - coverage gaps, brittle tests, or slow suites

## Rules

- Use `#[tokio::test]` for all async tests - never block on futures in sync test functions
- Mock via traits defined in the consumer module - use `mockall` for auto-generated mocks
- Use `testcontainers` for integration tests that need a real database
- Test public behavior, not private implementation - if you're testing a private function, the module design may need rethinking
- Keep unit tests fast - isolate from I/O with trait-based mocks
- Use `cargo test -- --test-threads=1` only when tests have shared state; prefer parallel by default
- If Docker is unavailable (CI without Docker, WSL limitations), skip testcontainers tests with `#[ignore]` and document the requirement - do not remove integration tests entirely

## Patterns

### Unit Tests (inline module)

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_email_valid() {
        assert!(validate_email("user@example.com").is_ok());
    }

    #[test]
    fn test_validate_email_missing_at() {
        assert!(validate_email("userexample.com").is_err());
    }

    #[test]
    fn test_validate_email_empty() {
        assert!(validate_email("").is_err());
    }
}
```

### Async Tests with tokio::test

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_create_user_success() {
        let mut mock_repo = MockUserRepository::new();
        mock_repo
            .expect_save()
            .returning(|user| Ok(User { id: 1, ..user }));

        let svc = UserService::new(Arc::new(mock_repo));
        let result = svc.create(NewUser { name: "Alice".into(), email: "alice@test.com".into() }).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_get_user_not_found() {
        let mut mock_repo = MockUserRepository::new();
        mock_repo
            .expect_find_by_id()
            .returning(|_| Err(AppError::NotFound("user".into())));

        let svc = UserService::new(Arc::new(mock_repo));
        let result = svc.get_user(999).await;
        assert!(matches!(result, Err(AppError::NotFound(_))));
    }
}
```

### Trait Mocking with mockall

```rust
use mockall::automock;

#[automock]
#[async_trait]
pub trait UserRepository: Send + Sync {
    async fn find_by_id(&self, id: i64) -> Result<User, AppError>;
    async fn save(&self, user: NewUser) -> Result<User, AppError>;
    async fn list(&self, limit: i64, offset: i64) -> Result<Vec<User>, AppError>;
}
```

### Handler Tests with axum::test

```rust
use axum::body::Body;
use axum::http::{Request, StatusCode};
use tower::ServiceExt;

#[tokio::test]
async fn test_get_user_handler_found() {
    let mut mock_svc = MockUserService::new();
    mock_svc
        .expect_get_user()
        .with(eq(123))
        .returning(|_| Ok(UserDto { id: 123, name: "Alice".into() }));

    let app = build_router(AppState::with_user_service(Arc::new(mock_svc)));

    let response = app
        .oneshot(
            Request::builder()
                .uri("/api/v1/users/123")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
}

#[tokio::test]
async fn test_get_user_handler_not_found() {
    let mut mock_svc = MockUserService::new();
    mock_svc
        .expect_get_user()
        .returning(|_| Err(AppError::NotFound("user".into())));

    let app = build_router(AppState::with_user_service(Arc::new(mock_svc)));

    let response = app
        .oneshot(
            Request::builder()
                .uri("/api/v1/users/999")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
}
```

### Integration Tests with testcontainers

```rust
// tests/integration/user_repo.rs
use testcontainers::runners::AsyncRunner;
use testcontainers_modules::postgres::Postgres;

#[tokio::test]
async fn test_user_repo_create_and_find() {
    let container = Postgres::default().start().await.unwrap();
    let pool = setup_test_pool(&container).await;
    run_migrations(&pool).await;

    let repo = UserRepository::new(pool);

    let user = repo.save(NewUser {
        name: "Alice".into(),
        email: "alice@test.com".into(),
    }).await.unwrap();

    assert!(user.id > 0);

    let found = repo.find_by_id(user.id).await.unwrap();
    assert_eq!(found.name, "Alice");
}

async fn setup_test_pool(container: &ContainerAsync<Postgres>) -> PgPool {
    let port = container.get_host_port_ipv4(5432).await.unwrap();
    let url = format!("postgres://postgres:postgres@localhost:{port}/postgres");
    PgPoolOptions::new()
        .max_connections(5)
        .connect(&url)
        .await
        .unwrap()
}
```

### Property-Based Testing with proptest

```rust
use proptest::prelude::*;

proptest! {
    #[test]
    fn test_validate_email_never_panics(email in "\\PC{1,100}") {
        let _ = validate_email(&email); // should never panic, may return Err
    }

    #[test]
    fn test_pagination_offset_non_negative(page in 1i64..1000, size in 1i64..100) {
        let offset = (page - 1) * size;
        prop_assert!(offset >= 0);
    }
}
```

### Benchmarks with criterion

```rust
// benches/hash_benchmark.rs
use criterion::{criterion_group, criterion_main, Criterion};

fn bench_hash_password(c: &mut Criterion) {
    c.bench_function("hash_password", |b| {
        b.iter(|| hash_password("supersecretpassword"))
    });
}

criterion_group!(benches, bench_hash_password);
criterion_main!(benches);
```

## Anti-Patterns

```rust
// Bad: blocking on async in sync test
#[test]
fn test_something() {
    let result = tokio::runtime::Runtime::new().unwrap()
        .block_on(async_function()); // use #[tokio::test] instead
}

// Bad: testing private functions directly
#[test]
fn test_internal_parse_token() { ... } // test through public API instead

// Bad: hardcoded sleep for async assertions
#[tokio::test]
async fn test_background_job() {
    start_job().await;
    tokio::time::sleep(Duration::from_secs(1)).await; // flaky
    assert!(job_completed()); // use channels or notification instead
}

// Bad: mocking concrete types instead of traits
```

## Avoid

- `tokio::time::sleep` in tests for synchronization - use channels or notification primitives
- Testing private functions - restructure or test through the public API
- Creating a new Tokio runtime in sync tests - use `#[tokio::test]`
- Mocking concrete types - define traits at service boundaries
- Shared mutable state between tests without isolation
