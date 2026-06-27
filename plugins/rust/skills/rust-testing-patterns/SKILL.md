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

- Async tests use `#[tokio::test]`. Never build a `Runtime` inside `#[test]`.
- Mock at consumer-side traits with `mockall::automock`. Concrete structs are not mockable - extract the trait first.
- Test through the public API. If a test needs `pub(crate)` or private items, the boundary is wrong.
- Integration tests use `testcontainers` for a real Postgres; gate with `#[ignore = "requires docker"]` so CI without Docker still passes.
- Synchronize on signals (`oneshot`, `Notify`, `tokio::time::pause` + `advance`), never wall-clock `sleep`.
- Tests run in parallel. Isolate state per test (fresh container or unique schema); reach for `#[serial_test::serial]` only when isolation is impossible. Never set `--test-threads=1` globally.

## Patterns

### Unit Test (inline `mod tests`)

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

### Handler Test (`tower::ServiceExt::oneshot`)

```rust
#[tokio::test]
async fn get_user_returns_200() {
    let mut svc = MockUserService::new();
    svc.expect_get().with(eq(1)).returning(|_| Ok(dto(1)));
    let app = build_router(AppState::with(Arc::new(svc)));
    let req = Request::builder().uri("/users/1").body(Body::empty()).unwrap();
    let res = app.oneshot(req).await.unwrap();

    assert_eq!(res.status(), StatusCode::OK);
    let body: UserDto = serde_json::from_slice(&to_bytes(res.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(body.id, 1);
}
```

Status alone is a weak assertion - deserialize the body and check the contract. Build the router with the same layers production uses so auth/middleware are exercised; a route tested without its auth layer proves nothing. Cover error paths (404, 422), not just the happy path. `axum-test`'s `TestServer` is an equivalent higher-level option; pick one and stay consistent across the suite.

### Integration Test with testcontainers

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

Container-per-test is simplest. When startup cost dominates, share one container and give each test a unique schema (`CREATE SCHEMA test_<uuid>`); never share tables via a static pool.

### Synchronize without `sleep`

```rust
// Bad: flaky wall-clock wait.
start_job().await;
tokio::time::sleep(Duration::from_secs(1)).await;
assert!(job_done());

// Good: signal completion.
let (tx, rx) = tokio::sync::oneshot::channel();
start_job_with_signal(tx).await;
rx.await.unwrap();
assert!(job_done());
```

### Property Test with proptest

Use proptest for invariants over a domain (parsers, validators, serde round-trips, ordering), not to re-assert what the type system already guarantees. A test that round-trips an input back to itself proves nothing.

```rust
proptest! {
    #[test]
    fn validate_email_never_panics(s in "\\PC{0,100}") {
        let _ = validate_email(&s);   // invariant: total function
    }
}
```

## Output Format

When reviewing a test suite, emit one finding per issue:

```
Finding: <one-line summary>
Category: {AsyncRuntime | Mocking | Boundary | Isolation | Synchronization | Coverage}
Severity: {Critical | Major | Minor}
Location: <path>:<line>
Evidence: <code excerpt or pattern reference>
Fix: <pattern name from this skill> - <one-line corrective action>
```

`Coverage` is for shallow assertions (status-only, no body), untested error paths, and test-config smells (`--test-threads=1`, missing `#[ignore]` gates). Severity: `Critical` for issues that make the suite flaky or hide real failures (wall-clock sleep, shared mutable DB state, masking races with `--test-threads=1`); `Major` for boundary/mock/coverage gaps that weaken signal; `Minor` for tests that pass but prove nothing. Collapse one anti-pattern repeated across N sites into a single finding listing each `Location`. If Docker is unavailable in CI, mark testcontainers gaps `Severity: Major` with `Fix: gate with #[ignore]` rather than dropping integration coverage.

## Avoid

- Sharing a `OnceCell`/`Lazy` DB pool across tests - state leaks, order-dependent failures.
- Asserting on log lines or stringified errors - match typed error variants.
- Property tests that round-trip an input back to itself or restate the function's type signature.
- `--test-threads=1` to paper over data races - fix the shared state instead.
