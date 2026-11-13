---
name: rust-testing-patterns
description: "Rust testing: #[tokio::test], rstest, tower oneshot handlers, #[sqlx::test], testcontainers, mockall, wiremock, proptest, paused time, nextest."
metadata:
  category: backend
  tags: [rust, testing, tokio, sqlx, testcontainers, mockall, wiremock, proptest, nextest]
user-invocable: false
---

# Rust Testing Patterns

> Load `Use skill: stack-detect` first. This skill reads `Database` - the production engine the integration rule binds to. In a Cargo workspace the crate under review decides: its own `[dev-dependencies]` and features in place of the detected values. Baseline: Rust 1.94+ (edition 2024: `std::env::set_var` is `unsafe`), Tokio 1.x (`test-util` feature for paused time), Axum 0.8, sqlx 0.9 (`#[sqlx::test]`, `migrate` feature), mockall 0.13, rstest 0.18+, testcontainers-modules 0.11+, wiremock 0.6, proptest 1.x, criterion 0.5+, cargo-nextest.

## When to Use

- Designing a test strategy for a Rust service
- Writing handler / service / repository / webhook / job tests
- Reviewing tests for coverage, brittleness, or speed

## Rules

- Parameterized cases use `rstest` `#[case]` (each case its own named test), not a `for` loop over a table that stops at the first failure and reports one name
- Setup halts with `?` - the test returns `anyhow::Result<()>`; post-conditions are `assert_eq!` / `assert!(matches!(err, AppError::NotFound))` on typed variants, never on `to_string()`
- Tests run in parallel - threads within one binary under `cargo test`, a process per test under nextest. Independence is a property you build: a fixture generates its own value for every unique-constrained column, and isolation is per-test (`#[sqlx::test]`'s database per test, or a transaction never committed). TRUNCATE between tests is not parallel-safe - it deletes a sibling's rows mid-assertion. `--test-threads=1` and `#[serial]` hide shared state rather than remove it; process-global state (env vars, a `static` pool) is injected instead
- Mock via traits the consumer declares (`mockall::automock`); never mock `sqlx` or the database. A handler that holds a concrete service cannot be tested in isolation - extract the trait at the consumer. `cfg(test)` is not set when `tests/` compiles the library, so a mock those tests need sits behind a `mocks` feature
- Integration tests run against the same engine as production - a real PostgreSQL via `#[sqlx::test]` or testcontainers. SQLite standing in for Postgres does not reproduce DDL, FK enforcement, `FOR UPDATE`, or SQLSTATE codes. When the production engine is unknown, say so and treat the substitution as unresolved rather than acceptable
- Test public behavior: unit tests in an inline `#[cfg(test)] mod tests`, integration tests in `tests/` against the crate's public API. A test reaching for private items through `pub(crate)` widening suggests the wrong boundary
- No wall-clock waiting for synchronization - `#[tokio::test(start_paused = true)]` with `tokio::time::advance`, an injected clock, `oneshot` / `Notify`, or a readiness wait. `tokio::time::sleep` on real time and a hand-rolled poll loop are the same defect at different sizes. A `tokio::time::timeout` around the code under test is a bound, not a wait, and is fine
- Safe Rust cannot data-race, so the concurrency check moves: Miri (`cargo +nightly miri test`) on crates with `unsafe`, `loom` for hand-built synchronization primitives, and contention tests against the database for logical races

## Patterns

### Parameterized Cases (rstest)

```rust
use rstest::rstest;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Status { Pending, Processing, Completed }
#[derive(Debug, PartialEq)]
pub enum TransitionError { Invalid }

#[rstest]
#[case::pending_to_processing(Status::Pending, Status::Processing, Ok(()))]
#[case::processing_to_completed(Status::Processing, Status::Completed, Ok(()))]
#[case::skip(Status::Pending, Status::Completed, Err(TransitionError::Invalid))]
#[case::reverse(Status::Completed, Status::Pending, Err(TransitionError::Invalid))]
fn transition(#[case] from: Status, #[case] to: Status, #[case] want: Result<(), TransitionError>) {
    let mut p = Payment { status: from, ..test_payment() };
    assert_eq!(p.transition(to), want);
}
```

### Handler Tests (`tower::ServiceExt::oneshot`)

```rust
use axum::{body::{Body, to_bytes}, http::{Request, StatusCode}};
use tower::ServiceExt; // oneshot
use uuid::Uuid;

#[tokio::test]
async fn get_user_not_found() -> anyhow::Result<()> {
    let mut svc = MockUserService::new();
    svc.expect_get().returning(|_| Err(AppError::NotFound));
    let app = build_router(AppState::for_test(svc)); // the production router, auth layer included
    let req = Request::builder().uri(format!("/users/{}", Uuid::new_v4()))
        .header("authorization", test_bearer()).body(Body::empty())?;
    let res = app.oneshot(req).await?;

    assert_eq!(res.status(), StatusCode::NOT_FOUND);
    let body: serde_json::Value = serde_json::from_slice(&to_bytes(res.into_body(), 64 * 1024).await?)?;
    assert_eq!(body["code"], "not_found"); // status alone is a weak assertion
    Ok(())
}
```

A route tested without its auth layer proves nothing about the route in production; add the unauthenticated case (401) beside the happy path. `#[derive(Validate)]` validates only where the handler calls `validate()` - test validation through the router (an invalid body asserts 422), not by calling the validator directly.

### Webhook Tests (Signature)

```rust
use hmac::{Hmac, Mac};
use sha2::Sha256;

const SECRET: &[u8] = b"whsec_test";
const BODY: &[u8] = br#"{"id":"evt_1"}"#;

fn sign(secret: &[u8], body: &[u8]) -> String {
    let mut mac = Hmac::<Sha256>::new_from_slice(secret).expect("any key length");
    mac.update(body);
    format!("sha256={}", hex::encode(mac.finalize().into_bytes()))
}

#[rstest]
#[case::valid(Some(sign(SECRET, BODY)), StatusCode::OK)]
#[case::tampered(Some(sign(SECRET, b"{}")), StatusCode::BAD_REQUEST)]
#[case::missing(None, StatusCode::BAD_REQUEST)]
#[tokio::test]
async fn webhook_signature(#[case] sig: Option<String>, #[case] want: StatusCode) { /* post BODY with sig */ }
```

Compute signatures in the test over the exact bytes sent; never paste a captured one - a timestamped scheme (Stripe's `t=`, 300s tolerance) fails within minutes. A test that signs a re-serialized body passes against a handler that re-serializes too, and both fail against the provider - sign the raw body.

### Trait Mocking (mockall)

```rust
use std::sync::Arc;
use async_trait::async_trait;

#[cfg_attr(any(test, feature = "mocks"), mockall::automock)] // must precede #[async_trait]
#[async_trait]
pub trait UserRepo: Send + Sync {
    async fn find(&self, id: Uuid) -> Result<Option<User>, sqlx::Error>;
}

#[tokio::test]
async fn get_returns_not_found() {
    let mut repo = MockUserRepo::new();
    repo.expect_find().times(1).returning(|_| Ok(None));
    let svc = UserService::new(Arc::new(repo));
    assert!(matches!(svc.get(Uuid::new_v4()).await, Err(AppError::NotFound)));
}
```

`#[async_trait]` is needed when the service holds `Arc<dyn UserRepo>` (native `async fn` in traits is not dyn-compatible); a service generic over `R: UserRepo` can drop it. A hand-written fake (`struct FakeRepo(Mutex<HashMap<Uuid, User>>)`) is simpler when a test needs state rather than call expectations.

### Fixtures (struct update syntax)

```rust
#[derive(Debug, Clone)]
pub struct Payment { pub id: Uuid, pub amount_cents: i64, pub currency: String, pub status: Status, pub idempotency_key: String }

// Every unique-constrained column gets a fresh value, so two parallel tests using the bare
// fixture can never collide on a unique index.
pub fn test_payment() -> Payment {
    Payment { id: Uuid::new_v4(), amount_cents: 1000, currency: "usd".into(), status: Status::Pending,
              idempotency_key: format!("idk_{}", Uuid::new_v4()) }
}

let p = Payment { status: Status::Completed, amount_cents: 5000, ..test_payment() };
```

### Integration (`#[sqlx::test]`)

```rust
use sqlx::PgPool;

// Creates a fresh database per test on DATABASE_URL's server and applies ./migrations:
// parallel-safe, and a test that must COMMIT (two sessions racing a claim) stays parallel too.
#[sqlx::test]
async fn creates_and_finds(pool: PgPool) -> anyhow::Result<()> {
    let repo = UserRepository::new(pool);
    let u = repo.create("Alice", &format!("alice+{}@example.com", Uuid::new_v4())).await?;
    assert_eq!(repo.find(u.id).await?.map(|f| f.name), Some("Alice".to_owned()));
    Ok(())
}
```

`#[sqlx::test(fixtures("users"))]` loads `fixtures/users.sql` after migrations. Keyset paging, plan and contention checks are integration tests: seed more than one page with duplicate sort keys and assert no overlap and no gap; assert an index name from `EXPLAIN (FORMAT JSON)`; release N tasks with one `tokio::sync::Barrier` against committed rows, then assert exactly one success and the invariant (`SUM(refunds) <= captured`). Give each racing session `SET lock_timeout = '1s'` - without `SKIP LOCKED` the second claimer blocks, and the test hangs CI instead of failing red. `#[sqlx::test]` panics when `DATABASE_URL` is unset: gate the file (`[[test]] name = "integration"` with `required-features = ["integration"]`) rather than `#[ignore]`, which CI silently skips unless it passes `--include-ignored`.

### Integration (testcontainers)

When the test must own its server (no CI service, a specific Postgres version):

```rust
use testcontainers_modules::{postgres::Postgres, testcontainers::{ImageExt, runners::AsyncRunner}};

#[tokio::test]
async fn repo_roundtrip_in_container() -> anyhow::Result<()> {
    let pg = Postgres::default().with_tag("16-alpine").start().await?; // removed when `pg` drops
    let url = format!("postgres://postgres:postgres@{}:{}/postgres",
        pg.get_host().await?, pg.get_host_port_ipv4(5432).await?); // mapped port, never hardcoded
    let pool = PgPool::connect(&url).await?;
    sqlx::migrate!().run(&pool).await?;
    // ...
    Ok(())
}
```

One container per test costs minutes at suite scale. Each `#[tokio::test]` has its own runtime, so a `static` pool created in one test fails in the next once that runtime shuts down - share the container's URL, never a pool or client; a `static` container is never dropped, so the CI job removes it. Under nextest every test is its own process and per-binary sharing buys nothing: for one database server per suite, CI provides a service container and `#[sqlx::test]` isolates per test.

### Idempotent Upsert Integration

```rust
#[sqlx::test]
async fn duplicate_returns_existing(pool: PgPool) -> anyhow::Result<()> {
    let repo = PaymentRepository::new(pool);
    let p = test_payment();
    let first = repo.create_idempotent(&p).await?;
    let dup = Payment { amount_cents: 9999, idempotency_key: p.idempotency_key.clone(), ..test_payment() };
    let second = repo.create_idempotent(&dup).await?;
    assert_eq!(first.id, second.id);
    assert_eq!(second.amount_cents, first.amount_cents); // original wins
    Ok(())
}
```

### Outbound HTTP Client (wiremock)

```rust
use wiremock::{Mock, MockServer, ResponseTemplate, matchers::{method, path}};

let server = MockServer::start().await;
Mock::given(method("POST")).and(path("/v1/charges"))
    .respond_with(ResponseTemplate::new(503))
    .expect(1) // verified when `server` drops
    .mount(&server).await;
let client = PaymentClient::new(&server.uri()); // base URL injected, never a hardcoded host:port
assert!(matches!(client.charge(&order, "order-1").await, Err(PaymentError::Other(_))));
```

An SDK that resolves its own endpoint needs its base URL overridden too, or the test silently calls the real API. Cover the error mappings (4xx, 5xx, malformed body, and a deadline - `ResponseTemplate::set_delay` past the client's timeout asserts the indeterminate classification, not a retry), not just the happy path. wiremock runs on real time; do not combine it with `start_paused`. A Kafka producer is tested against rdkafka's `MockCluster` (in-process) or a container, asserting the record landed once.

### Async Handler (at-least-once redelivery)

Delivery is at-least-once, so every handler needs a test that runs it twice. Coverage percentage never reveals this gap - the line ran, the scenario did not.

```rust
use std::sync::atomic::{AtomicUsize, Ordering};

#[sqlx::test]
async fn settle_twice_sends_once(pool: PgPool) -> anyhow::Result<()> {
    let sent = Arc::new(AtomicUsize::new(0));
    let h = SettleHandler::new(pool, CountingMailer(sent.clone()));
    let payload = SettlePayload { event_id: Uuid::new_v4() };

    h.handle(&payload).await?;
    h.handle(&payload).await?; // redelivery must succeed, not error
    assert_eq!(sent.load(Ordering::SeqCst), 1, "receipt emailed twice on redelivery");
    Ok(())
}
```

Also assert that a malformed payload returns the permanent class (`JobError::Permanent`), so the worker dead-letters it at once instead of retrying through the whole budget. A task spawned by the code under test that panics does not fail the test unless its `JoinHandle` is awaited - await it.

### Deterministic Time

```rust
use std::time::Duration;

#[tokio::test(start_paused = true)] // test-util feature; current_thread runtime only
async fn debounce_fires_once() {
    let calls = Arc::new(AtomicUsize::new(0));
    let c = calls.clone();
    let d = Debouncer::new(Duration::from_millis(100), move || { c.fetch_add(1, Ordering::SeqCst); });
    d.trigger(); d.trigger(); d.trigger();
    tokio::time::sleep(Duration::from_millis(150)).await; // virtual time: auto-advances, returns instantly
    assert_eq!(calls.load(Ordering::SeqCst), 1);
}
```

Paused time moves only `tokio::time`; `SystemTime::now()` and `chrono::Utc::now()` keep running. Code that reads the wall clock (expiry, rate limits) takes an injected clock:

```rust
use std::sync::Mutex;
use std::time::SystemTime;

pub trait Clock: Send + Sync { fn now(&self) -> SystemTime; }

pub struct FakeClock(Mutex<SystemTime>); // Mutex: the code under test may read it from another task
impl Clock for FakeClock { fn now(&self) -> SystemTime { *self.0.lock().unwrap() } }
impl FakeClock { pub fn advance(&self, d: Duration) { *self.0.lock().unwrap() += d; } }
```

### Benchmarks

```rust
// benches/hash.rs, with [[bench]] name = "hash", harness = false in Cargo.toml
use criterion::{Criterion, criterion_group, criterion_main};
use std::hint::black_box;

fn bench_hash(c: &mut Criterion) {
    c.bench_function("hash_password", |b| b.iter(|| hash_password_sync(black_box("secret"))));
}
criterion_group!(benches, bench_hash);
criterion_main!(benches);
```

`#[bench]` is nightly-only; stable benchmarks use criterion (or divan).

### Property Tests

Use proptest for invariants over a domain (parsers, validators, serde round-trips of *types*, ordering), not to restate the type signature.

```rust
use proptest::prelude::*;

proptest! {
    #[test]
    fn parse_amount_never_panics(s in "\\PC{0,64}") { let _ = parse_amount(&s); } // total function
}
```

### CI Invocation

```bash
cargo nextest run --workspace --locked                          # unit + integration that need no server
cargo nextest run --workspace --locked --features integration   # DATABASE_URL from the CI service container
cargo test --doc --workspace --locked                           # nextest does not run doctests
cargo +nightly miri test -p <crate-with-unsafe>                 # UB check where unsafe exists
```

`--test-threads` caps threads per binary under `cargo test` and concurrent processes under nextest; lowering it to fix a flake hides the shared state that caused it. `--locked` fails when `Cargo.lock` is stale instead of testing different versions than production.

## Edge Cases

- `#[tokio::test]` is current-thread: `tokio::task::block_in_place` panics there - use `flavor = "multi_thread"` for that test only
- `start_paused` auto-advances whenever the runtime is idle, so a test that awaits real I/O (a socket, a container) under paused time sees timeouts fire early
- Doctests compile as separate crates against the public API; a doctest using a private item fails to compile, not to run
- `std::env::set_var` in a test is `unsafe` in edition 2024 and races sibling test threads - pass config explicitly

## Output Format

Open the deliverable with one line above everything else, `**Engine:** {database | unknown}` - stack-detect's `Database` value as written, or under the workspace rule the engine of the reviewed crate's driver.

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design | `## Test Strategy` with `### Coverage`, `### Fixtures`, `### Mocks`; code for the key tests follows under `### <Test>` headings in `Coverage` order; existing tests kept as-is append `(existing)`, replaced ones `, replaces <name>`, to the `Key Scenarios` cell (Coverage) or the `Strategy` cell (Mocks); existing tests handed with the brief that violate a Rule emit `## Findings` first |
| Review | `## Findings`, then `## Test Strategy` describing the suite as it exists today |
| Triage (slow / flaky) | two opening lines `**Failing:**` and `**First fix:**`, then `## Findings`, then `## Fix Order` - numbered, isolation (`#[sqlx::test]` or a per-test transaction, feature gates) before parallelism, container consolidation before nextest tuning, since several fixes are prerequisites for others - then `## Test Strategy` as it exists today |

```
## Test Strategy

### Coverage
| Layer | Type | Count | Key Scenarios |
|-------|------|-------|---------------|

### Fixtures
| Fixture | Builder | Variants |
|---------|---------|----------|

### Mocks
| Trait | Crate | Strategy |
|-------|-------|----------|
```

Cell values: `Layer` is `handler | middleware | service | repository | worker | client | ci` - `client` for outbound HTTP and producer tests, `ci` for one row per CI, Makefile or justfile test invocation (`Type` and `Count` `n/a`, its flags in `Key Scenarios`). `Type` is `unit | handler | integration | job | property | benchmark | validation | doc` - `validation` for a test that exercises DTO deserialization and `validate()` only, `integration` also for schema, query-plan and contention assertions, `unit` for a test of a test-local helper; parameterized is a style, named in `Key Scenarios`, not a `Type`. `Count` is test functions / `#[case]` rows (`3 / 14`; a function with no cases is `1 / 0`); for tests the design proposes, a delta (`+2 / +9`); when the inventory was not supplied, deltas only. `Strategy` is `mockall mock | hand-written fake | real (sqlx::test database) | real (container) | real (in-process broker) | real (substitute engine) | wiremock server | not mocked` - `real (in-process broker)` is rdkafka's `MockCluster`, `real (substitute engine)` is SQLite standing in for Postgres and is always paired with a finding, `not mocked` a concrete dependency used as-is (its `Trait` cell names the type). `Crate` is the crate and module that declares the trait (the consumer, when the code follows the convention). `Builder` is `none (literal)` when tests construct the value inline. A table with no rows emits one row reading `(none)` with the reason, never an empty table. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries. `**Failing:**` names the symptoms; `**First fix:**` the one change the others depend on.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {what the test fails to catch, or what makes it fail spuriously}
- Rule: {the testing rule violated}
- Fix: {rewritten test code; for a CI or Cargo.toml finding the corrected line; for an owned-by block the production change in one clause}
```

Owned findings: `[Must]` when a test passes while the behavior it names is broken, fails without a code change (a real-time wait, a captured signature), shares state that makes its result depend on sibling tests or order, leaks a spawned task whose panic is never observed, or a CI setting masks failures (`--test-threads=1` over shared state, `#[ignore]` suites CI never runs, doctests dropped with the move to nextest); `[Recommend]` otherwise. A missing test cites the production symbol as `<test file>:<missing test fn>`. Cite `file:line` when the input carries line numbers (a workflow file or `Cargo.toml` is a file like any other), `file:<symbol>` when it does not; a range is `file:start-end`. Order owned findings `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites (TRUNCATE in every test) is one heading citing the first site, with the rest named on the `Defect:` line; one failure signature with one cause is one finding. A defect in the production code that a test exposes (a signature over the wrong bytes, a detached `tokio::spawn`) is still reported, never dropped: one block per such defect after every owned finding, in that same order among themselves, labelled `[Must]` when it risks incorrect behaviour, data loss or a security hole and `[Recommend]` otherwise, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- Real-time `sleep` for synchronization
- Building a `Runtime` inside `#[test]` instead of `#[tokio::test]`
- Mocking `sqlx` or the database
- A `static` / `OnceCell` pool or client shared across `#[tokio::test]` functions
- Asserting on log lines or stringified errors
- Hardcoded webhook signatures
- `#[ignore]` as the integration gate with no CI step that runs ignored tests
