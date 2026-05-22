---
name: rust-testing-patterns
description: "Rust testing: #[tokio::test], mockall traits, testcontainers Postgres, tower oneshot handlers, proptest, fixture isolation."
metadata:
  category: backend
  tags: [rust, testing, mockall, testcontainers, proptest, tokio]
user-invocable: false
---

# Rust Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing a test strategy for a Rust async service
- Reviewing unit, integration, handler, or property tests
- Diagnosing flaky, slow, or brittle test suites

## Rules

- Async tests use `#[tokio::test]` - never construct a runtime inside `#[test]`
- Mock at trait boundaries declared in the consumer module; use `mockall::automock` - do not mock concrete structs
- Integration tests use `testcontainers` with a fresh container per test (or per-test schema); guard Docker-required tests with `#[ignore]` when Docker is absent
- Test public API only - if a test needs a `pub(crate)` item, the boundary is wrong
- No `tokio::time::sleep` for synchronization - use channels, `Notify`, or `tokio::time::pause` + `advance`
- Tests run in parallel by default; serialize only with `serial_test::serial`, never `--test-threads=1` globally

## Patterns

### Unit Test (inline)

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_email_missing_at() {
        assert!(validate_email("userexample.com").is_err());
    }
}
```

### Async Test with mockall

```rust
#[mockall::automock]
#[async_trait::async_trait]
pub trait UserRepo: Send + Sync {
    async fn find(&self, id: i64) -> Result<User, AppError>;
}

#[tokio::test]
async fn returns_not_found() {
    let mut repo = MockUserRepo::new();
    repo.expect_find().returning(|_| Err(AppError::NotFound("user".into())));
    let svc = UserService::new(Arc::new(repo));
    assert!(matches!(svc.get(1).await, Err(AppError::NotFound(_))));
}
```

### Handler Test via `tower::ServiceExt::oneshot`

```rust
#[tokio::test]
async fn get_user_returns_200() {
    let mut svc = MockUserService::new();
    svc.expect_get().with(eq(1)).returning(|_| Ok(dto(1)));
    let app = build_router(AppState::with(Arc::new(svc)));
    let req = Request::builder().uri("/users/1").body(Body::empty()).unwrap();
    let res = app.oneshot(req).await.unwrap();
    assert_eq!(res.status(), StatusCode::OK);
}
```

### Integration Test with testcontainers (per-test container)

```rust
#[tokio::test]
#[ignore = "requires docker"]
async fn save_and_find_roundtrip() {
    let pg = Postgres::default().start().await.unwrap();
    let pool = connect(&pg).await;
    sqlx::migrate!("./migrations").run(&pool).await.unwrap();

    let repo = UserRepository::new(pool);
    let saved = repo.save(new_user()).await.unwrap();
    assert_eq!(repo.find(saved.id).await.unwrap().name, saved.name);
}
```

Per-test containers give isolation at the cost of startup time. For larger suites, share a container but give each test a unique schema (`CREATE SCHEMA test_<uuid>`), never a shared static pool with shared tables.

### Async Synchronization without `sleep`

```rust
// Bad: flaky wait
start_job().await;
tokio::time::sleep(Duration::from_secs(1)).await;
assert!(job_done());

// Good: signal completion
let (tx, rx) = tokio::sync::oneshot::channel();
start_job_with_signal(tx).await;
rx.await.unwrap();
assert!(job_done());
```

### Property Test with proptest

```rust
proptest! {
    #[test]
    fn validate_email_never_panics(s in "\\PC{0,100}") {
        let _ = validate_email(&s);
    }
}
```

## Output Format

When reviewing a test suite, emit one finding per issue:

```
Finding: <one-line summary>
Category: {AsyncRuntime | Mocking | Isolation | Synchronization | Boundary | Coverage | Flakiness}
Severity: {Critical | Major | Minor}
Location: <path>:<line>
Evidence: <code excerpt or pattern reference>
Fix: <pattern name from this skill> - <one-line corrective action>
```

When no issues found in a category, omit it. If Docker is unavailable, mark testcontainers findings `Severity: Major` with `Fix: gate with #[ignore]` rather than dropping integration coverage.

## Avoid

- Constructing `tokio::runtime::Runtime` inside `#[test]` - use `#[tokio::test]`
- Mocking concrete struct types - extract a trait at the consumer boundary
- Testing `pub(crate)` or private functions directly - test through the public API
- `tokio::time::sleep` for awaiting async work - use channels, `Notify`, or virtual time
- `Once`/`OnceCell` for a shared DB pool across tests - state leaks, ordering bugs
- `--test-threads=1` to mask data races - fix the shared state or use `serial_test::serial` per-test
- Asserting on log output or error message strings - assert on typed error variants
