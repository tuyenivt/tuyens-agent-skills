---
name: task-rust-test
description: Rust / Axum test strategy and scaffolding: tokio::test, axum-test, tower oneshot, testcontainers, mockall, proptest, cargo nextest.
agent: rust-test-engineer
metadata:
  category: backend
  tags: [rust, axum, testing, tokio-test, axum-test, testcontainers, mockall, proptest, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, generate one test per acceptance criterion (use `// Satisfies: AC<N>` mapping or test-name suffix), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface coverage gaps as proposed amendments.

# Rust Test

## Purpose

Rust-aware test strategy and scaffolding using the `#[test]` / `#[tokio::test]` attributes (the canonical Rust forms), `axum-test` or `tower::ServiceExt::oneshot` for handler tests, `testcontainers-rs` PostgreSQL for repository tests, `mockall` for trait mocks (auto-generated via `#[automock]`), `proptest` / `quickcheck` for property-based tests on pure logic, `cargo nextest` for fast parallel test execution, and `cargo clippy --all-targets -- -D warnings` for lint discipline. Replaces the generic backend test patterns with Rust-specific guidance.

This workflow is the stack-specific delegate of `task-code-test` for Rust. The core workflow's contract (output shape, prioritization rules) is preserved so callers see a stable shape.

## When to Use

- Designing a test strategy for a new Rust/Axum service / module
- Assessing test coverage gaps across unit / integration / handler / job layers
- Scaffolding tests for under-covered handlers, services, repositories, or auth code
- Reviewing test pyramid balance for a Rust app
- Adding boundary tests (validation, authorization, error paths) to existing happy-path tests

**Not for:**

- Test failure / panic debugging (use `task-rust-debug`)
- General code review (use `task-code-review` / `task-rust-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Confirm Stack and Detect Async / Data-Access Surface

Use skill: `stack-detect` to confirm Rust / Axum. If invoked as a delegate of `task-code-test` (parent already detected Rust), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Rust, stop and tell the user to invoke `/task-code-test` instead.

Detect data access (sqlx / diesel / mixed) and messaging (Tokio queue / AMQP / Kafka / none). Detect mock framework (`mockall`, hand-written trait mocks, `mockito` for HTTP). Record `Data Access`, `Messaging`, `Mock Framework` for the output.

### Step 2 - Read the Code Under Test and Existing Tests

Before producing assessment, scaffolds, or strategy, open both the production code in scope and a representative sample of existing tests. This grounds the output in real conventions instead of generic templates.

- For each target named by the user, read the module top-to-bottom: `pub` items, request / response types, middleware, transaction boundaries, external collaborators
- Glob `tests/**/*.rs` and `src/**/*` for `#[cfg(test)] mod tests` blocks; read at least: one existing handler test, one existing service / repository test, one existing background-task test (if applicable), `tests/common/mod.rs` setup files - learn the project's test layout, mock strategy (`mockall` vs hand-written), HTTP-stub library (`mockito` vs `wiremock`), authentication helpers
- Read `Cargo.toml` `[dev-dependencies]` for the test ecosystem in use
- Read `Makefile` / `justfile` / CI config for `cargo test` vs `cargo nextest`, `cargo clippy --all-targets -- -D warnings`, integration-test segregation (`tests/` directory vs `#[cfg(test)]` modules), `cargo audit` / `cargo deny`
- Read `tests/common/mod.rs` (or equivalent) for shared fixtures (testcontainers init, fake JWT generator, factory utilities)
- Read `src/main.rs` (or `src/app.rs`) for middleware order that handler tests must replicate (auth, trace layer, error handler)

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc rather than inventing them silently. Greenfield convention list (state your choice for each, with a one-line rationale):

| Decision           | Default to propose                                                                                  |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| Test layout        | Integration / handler tests under `tests/`; unit tests colocated via `#[cfg(test)] mod tests`       |
| Async runtime      | `#[tokio::test]`; `flavor = "multi_thread"` only when handlers spawn or workers run cross-thread    |
| Handler harness    | `axum-test::TestServer` (ergonomic) over `tower::ServiceExt::oneshot` (lower-level) for greenfield  |
| DB strategy        | `testcontainers` + `testcontainers-modules` PostgreSQL via `OnceCell` shared container; per-test transactional rollback |
| Mock crate         | `mockall` `#[automock]` on trait boundaries                                                         |
| Property crate     | `proptest` for pure invariants                                                                       |
| Runner             | `cargo nextest run` for parallelism; fall back to `cargo test` if not adopted                       |
| Lint               | `cargo clippy --all-targets -- -D warnings` mandatory in CI                                          |
| Coverage           | `cargo llvm-cov` (preferred) or `cargo tarpaulin`                                                   |
| Shared fixtures    | `tests/common/mod.rs` for testcontainer init, JWT issuer, factory functions, `app_with_state(pool)` |
| `[dev-dependencies]` | Bootstrap block: `tokio` (with test-util), `axum-test`, `testcontainers`, `testcontainers-modules`, `mockall`, `proptest`, `rstest`, `pretty_assertions`, `serde_json`, `once_cell` |

### Step 3 - Rust Test Pyramid

The Rust test pyramid maps to test types:

| Layer       | Tooling                                                                       | What belongs here                                                              |
| ----------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Unit        | `#[test]` / `#[tokio::test]` + `mockall` trait mocks                          | Service business logic, validators, mappers, pure functions, calculation rules |
| Property    | `proptest` / `quickcheck` (on pure functions)                                 | Calculation invariants, parsers, state-machine laws                            |
| Integration | `#[tokio::test]` + testcontainers PostgreSQL + real sqlx / diesel client      | Repository queries, DB-level invariants, ORM constraints                       |
| Handler     | `axum-test::TestServer` or `tower::ServiceExt::oneshot` against a real router | Routing, request / response binding, validation, middleware                    |
| Job         | In-process worker fn invocation OR testcontainers Redis / Kafka + real worker | Background-task processor happy path, retry logic, idempotency                 |
| E2E         | `axum-test::TestServer` with full app + testcontainers (Postgres + broker)    | Critical user journeys only - signup, checkout, payment                        |
| Contract    | Pact / OpenAPI consumer-driven (e.g., `utoipa` schema validation)             | API contract validation against schema                                         |

**Many** unit tests, **some** handler / integration tests, **few** full E2E tests. `cargo clippy --all-targets -- -D warnings` and `cargo test` (or `cargo nextest run`) on every CI run.

### Step 4 - Apply Rust Test Patterns

**`#[tokio::test]` for async (the canonical Rust async-test form):**

```rust
#[tokio::test]
async fn place_order_returns_id_on_success() {
    // setup, exercise, assert
}

// For multi-thread runtime (handlers that spawn tasks):
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn ...
```

**Table-driven tests via parameterized cases (when behavior varies by input):**

Rust's idiomatic table-driven form uses a `Vec<TestCase>` + a loop, **or** the `rstest` crate's `#[case(...)]` attribute. Either is valid; pick whichever the project already uses:

```rust
struct Case<'a> {
    name: &'a str,
    input: PlaceOrderInput,
    expected: Result<OrderId, AppError>,
}

#[tokio::test]
async fn place_order_cases() {
    let cases = vec![
        Case { name: "happy path", input: valid_input(), expected: Ok(OrderId(1)) },
        Case { name: "validation error", input: bad_input(), expected: Err(AppError::Validation(...)) },
    ];

    for case in cases {
        let got = service.place(case.input).await;
        assert_eq!(got, case.expected, "case: {}", case.name);
    }
}
```

With `rstest`:

```rust
use rstest::rstest;

#[rstest]
#[case(valid_input(), Ok(OrderId(1)))]
#[case(bad_input(), Err(AppError::Validation(...)))]
#[tokio::test]
async fn place_order(#[case] input: PlaceOrderInput, #[case] expected: Result<OrderId, AppError>) {
    let got = service.place(input).await;
    assert_eq!(got, expected);
}
```

Failure messages cite the case (line number for `rstest`, explicit `name` for the manual loop).

**Unit tests (`#[cfg(test)] mod tests` colocated, or `tests/` integration crate):**

- Standard `#[test]` for sync; `#[tokio::test]` for async
- One test fn per outcome (happy / validation failure / external failure / edge)
- **No Axum router / DB** in a unit test - if a unit test needs `Router::new()` or a `PgPool`, it is misclassified
- Stub external HTTP via `mockito` or `wiremock` (returning canned responses); do not stub repositories with full SQL behavior - use testcontainers for that
- `mockall` for trait mocks at service boundaries: `#[automock]` on the trait generates a `MockOrderRepository` with `expect_*()` builders; use the mock in the test
- `pretty_assertions::assert_eq` for diff-rich failure output on complex structs

**Property-based tests (`proptest` / `quickcheck`):**

- Use for pure functions with invariants: a parser is round-trippable (`parse(serialize(x)) == x`), a calculation is monotonic, a state machine never returns an invalid state
- Do **not** use `proptest` to "cover more cases" of a non-deterministic function (HTTP, DB) - it generates inputs, not environments

```rust
use proptest::prelude::*;

proptest! {
    #[test]
    fn order_total_never_negative(items in prop::collection::vec(any::<OrderItem>(), 0..100)) {
        let total = calculate_total(&items);
        prop_assert!(total >= Money::zero());
    }
}
```

**Axum handler tests:**

Two canonical patterns - choose by project convention:

- **`axum-test::TestServer`** (third-party crate, ergonomic): `let server = TestServer::new(app)?; let response = server.post("/orders").json(&body).await; response.assert_status_ok();`
- **`tower::ServiceExt::oneshot`** (no extra dep, lower-level): build the `Router`, call `app.oneshot(Request::builder().method(...).uri(...).body(...).unwrap()).await?` to get a `Response`; assert on status and body

For both:

- Build the router with the **same global middleware** as `main.rs` (TraceLayer, request-id, error handler, auth) - missing auth middleware in tests masks authorization bugs
- One test per `(method, path, principal-state, outcome)` triple
- Authentication via auth middleware that reads a test-issued token, OR a test-only middleware that injects fixed claims into `Request::extensions_mut()`
- Authorization: a separate test for "anonymous → 401" and "wrong role → 403" per protected endpoint
- Validation: a "rejects invalid payload" test for any endpoint with a validated DTO body
- Response shape: assert key fields, status, headers, and `Content-Type`
- DB: pass a test-provided `PgPool` (pointing at the testcontainers DB) into `AppState`; transactional rollback per test (see Repository tests below)

**Repository / sqlx integration tests:**

- testcontainers PostgreSQL via `testcontainers` (or `testcontainers-modules`) - **not SQLite, not in-memory** - SQLite diverges from PostgreSQL on JSON / JSONB, partial indexes, window functions, `ON CONFLICT`, array types, `LATERAL` joins, and sqlx's compile-time-checked queries are validated against PostgreSQL specifically
- Shared container per test suite via a `OnceCell<TestContainer>` in `tests/common/mod.rs` or via `cargo nextest`'s test grouping - per-test container creation (~3-5s startup) dominates suite runtime if duplicated
- Per-test isolation: either (a) `let mut tx = pool.begin().await?;` at test start, drop without commit (sqlx auto-rolls back) - pass `&mut tx` to the repository constructor; or (b) truncate / recreate per test via a fixture
- Run sqlx migrations against the testcontainer in `OnceCell` setup (`sqlx::migrate!().run(&pool).await?`)
- One test per non-trivial query: assert SQL semantics (filter correctness, sort order, JOIN result), not just "method returns something"
- Custom indexes / constraints: insert violating data and assert the right error is raised (`sqlx::Error::Database` with a `PgDatabaseError` whose `code()` is `"23505"` for unique violation)

**DTO / validator tests:**

- Use `validator::Validate::validate(&req)` directly - faster than going through a full handler test
- Edge cases: missing required fields, wrong types via JSON deserialization, out-of-range values, custom validators

**Background-task / Kafka / AMQP tests:**

- **In-process for fast tests**: invoke the handler fn directly with a constructed payload; no broker. Best for handler logic
- **testcontainers Redis / Kafka + real worker** for tests that need actual broker behavior (retry, ack, redelivery)
- Idempotency test: invoke the handler twice with the same payload; assert side effect happens once
- Retry test: stub the external call to fail twice then succeed; assert task completes; assert retry count
- Dead-letter / max-retries test: stub the external call to fail forever; assert task ends in DLQ / max-retries state without infinite loop
- For Kafka (`rdkafka`): consider `mock_cluster::MockCluster` for in-process broker simulation; testcontainers Kafka for full integration

**E2E / full-context tests:**

- Reserve for tests that genuinely need the full stack: auth flow end-to-end, transactional commit + background task dispatch, scheduled-task behavior
- Use `axum-test::TestServer` with the real wired app; pair with testcontainers Postgres + Redis / Kafka
- Avoid for tests that a handler test could cover - context-load cost compounds

**Lint & runner discipline:**

- `cargo clippy --all-targets -- -D warnings` mandatory in CI - clippy catches many concurrency / lifetime / API-shape mistakes
- `cargo nextest run` (when adopted) for faster parallel test execution and better failure output; otherwise `cargo test`
- `cargo test --doc` to run doc tests on `///` examples; doc tests double as documentation correctness checks
- `cargo audit` and `cargo deny check advisories` in CI for dependency vulnerability scanning

### Step 5 - Test Boundaries (Rust-Specific)

**What deserves a unit test:**

- Service logic, mappers, validators, custom middleware (the middleware fn in isolation), pure functions / utilities
- Domain rules, calculation, state-machine transitions
- Concurrent helpers (worker pool, `JoinSet` wrapper) tested with `#[tokio::test(flavor = "multi_thread")]`

**What deserves a property test:**

- Pure invariants: parsers, serialization round-trips, monotonic calculations, idempotent operations
- Domain laws ("a refund never exceeds the original payment", "a state machine never reaches an invalid state")

**What deserves a handler test:**

- Every endpoint: happy path + 401 + 403 + 4xx validation
- **IDOR / per-owner / per-tenant resources**: anonymous → 401, other-user → 403/404, owner → 200. Any handler that takes an id path parameter and returns or mutates user-owned data needs this triple
- Pagination contract (`limit` / `offset` / cursor)
- Filtering / sorting / search query params
- Custom error middleware mapping `AppError` → HTTP status

**Web hazard tests (when handler shape signals the risk):**

| Hazard                | When the handler shape signals it                                                       | Test to add                                                                                       |
| --------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| IDOR                  | Path `:id` -> user-owned resource lookup or mutation                                    | Owner / other-user / anonymous trio per endpoint                                                  |
| Open redirect         | `Redirect::to(&user_input)` or any handler returning a 30x to a request-derived URL    | Allowlist enforcement: relative-only / domain-allowlist; reject `//evil.com`, schemes, encoded forms |
| File upload           | `axum::extract::Multipart` or any path joining `user_filename`                          | Path traversal (`../../etc/...`), MIME sniff vs `Content-Type` header lie, size cap, atomic write |
| Bulk export           | Endpoint returning `fetch_all` of an entity table; `/admin/export` shape                 | Authz + row-cap + tenant scoping ("export only my tenant's rows, max N rows")                     |
| SSRF                  | `reqwest::get(user_url)` / outbound HTTP with request-derived host                      | Allowlist rejects metadata IP, loopback, RFC1918, link-local; DNS rebinding test                  |
| Privilege escalation  | `update_user` / `update_role` / any handler that touches role / permission fields       | Non-admin cannot self-promote; admin can; role change requires explicit admin guard               |
| Command/shell injection | `Command::new("sh").arg("-c")` or any `format!`-built shell string, even outside upload  | Reject metacharacters in user input; assert arg-list invocation (`Command::new("convert").arg(path)`) is used so shell metacharacters cannot reach a shell |

These belong in handler tests, not buried in service unit tests - the security guard is at the handler boundary, so the test must exercise it through the same boundary. **Web hazards from this table default to Step 7 priority band P1** (security guard is the test's purpose), even when the underlying flow looks like P3 revenue or P2 data integrity - the secondary band still applies via the Multi-band rule.

**What deserves an integration / testcontainers test:**

- Every repository method with a non-trivial query (filter on multiple columns, JOIN, aggregate)
- DB constraints (unique, check, FK ON DELETE behavior)
- Migration smoke test: apply all migrations on a clean testcontainers DB; useful when migrations are squashed

**What deserves a background-task / Kafka test:**

- Every task with retry logic, idempotency requirements, or external side effects
- Task chains / workflows - assert the workflow completes and aggregates correctly
- Tasks dispatched via post-commit pattern - assert they fire after the parent commits, not before

**What does NOT need a test:**

- Framework-provided behavior: Axum routing resolution, middleware dispatch, default `validator` rules (test that you wired things correctly via handler tests, not that the framework works)
- Generated boilerplate: DTOs with no logic, getters returning a single field, `From` impls that only re-arrange fields
- Trivial delegation: `service::get(id) -> repository::get(id)` with no logic

### Step 6 - Test Data and Fixtures

- Prefer factory functions (`fn new_test_order(opts: TestOrderOpts) -> Order { ... }`) over hand-rolled struct literals; configure factories per project convention
- For repository tests with testcontainers, use factories to insert; isolate per-test data inside the test (transactional rollback) or use a unique-per-test prefix
- Avoid mutating shared test fixtures - use a fresh transaction per test
- Test data must be minimal and focused - 100-row `for i in 0..100 { ... }` setups signal the test belongs at integration / load-test layer

### Step 7 - Prioritization (when coverage is low)

If line coverage (or your equivalent project signal) is below ~50%, **run this step before scaffolding** - it determines _which_ tests to scaffold first. Scaffolding alphabetically or by file is wrong when authorization holes go untested while plumbing endpoints get full coverage.

When starting from low test coverage, prioritize by Rust-specific risk:

**Priority 1 - Authorization and authentication:**

- Handler test per protected endpoint asserting 401 anonymous + 403 wrong-role
- JWT middleware tests covering issuer, audience, signature, expiry validation
- Custom auth middleware unit-tested

**Priority 2 - Data integrity:**

- Repository / sqlx integration tests for every non-trivial query
- Service tests for write operations (one happy path + one rollback per write)
- Background-task idempotency for any task with side effects
- `cargo clippy --all-targets -- -D warnings` clean for any concurrent code path
- `cargo test` (or `cargo nextest`) covers `#[tokio::test(flavor = "multi_thread")]` cases for code that must run cross-thread

**Priority 3 - Business-critical flows:**

- Revenue paths (checkout, billing, subscription state transitions)
- State-machine transitions (often modeled as enums in Rust - exhaustive `match` makes them testable)
- Scheduled tasks touching billing or notifications

**Priority 4 - High-churn code:**

- Files with frequent recent commits (`git log --since="3 months ago"`)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pass-through handlers, simple CRUD - lower risk, can wait

**Multi-band rule.** Some targets fall into more than one band - a refund background-task processor is both P2 (data-integrity, side-effect idempotency) and P3 (revenue path); a payment-history endpoint is both P1 (authorization on per-owner data) and P3 (revenue). When a target qualifies for multiple bands, file it under the **highest** band (lowest number) and note the secondary band so the test plan covers both axes (e.g., a refund test must assert idempotency *and* the refund-amount invariants, not just one). Do not split the same target across two bands - that hides one of the risks.

### Step 8 - Test Infrastructure Hygiene

- [ ] testcontainers reused across tests via `OnceCell` / `Lazy` shared init (not per-test container creation)
- [ ] `cargo clippy --all-targets -- -D warnings` runs in CI
- [ ] Test profile only overrides what differs from prod - never silently disables auth middleware
- [ ] Integration tests separated under `tests/` directory (separate test crate, slower but isolated) vs `#[cfg(test)] mod tests` blocks (in-module unit tests)
- [ ] HTTP stubs via `mockito` or `wiremock` returning canned responses; never real network calls in CI
- [ ] **SDK / non-default-transport bypass surfaces**: `mockito::Server` / `wiremock::MockServer` only intercept calls that go through them - SDKs and non-`reqwest` clients bypass the mock unless wired correctly. Verify by asserting the stub server received `>= 1` request (`mock.assert_hits(1)` for `mockito`, `mock_server.received_requests().await` for `wiremock`); silent zero-call passes are the failure mode. Specific Rust bypass surfaces:
  - **`aws-sdk-*` (S3, DynamoDB, SQS, SNS, etc.)**: requires `Endpoint::immutable(stub_url)` or `endpoint_url(stub_url)` on the SDK config; without it the SDK calls real AWS regardless of `HTTP_PROXY` env vars
  - **Google Cloud SDKs (`google-cloud-storage`, etc.)**: require `STORAGE_EMULATOR_HOST` env var or explicit endpoint override; otherwise hit real GCS even when the test sets up `wiremock`
  - **gRPC over HTTP/2 (`tonic`)**: HTTP/1.1 stubs (`mockito`/`wiremock` defaults) cannot serve HTTP/2 traffic. Use `tonic::transport::Server` with an in-process `tower::service_fn` mock, or `tonic-test` patterns; gRPC tests need a gRPC stub
  - **Custom `reqwest::Client::builder()` with explicit `proxy(...)` / custom `tls_connector(...)`**: proxy or TLS overrides bypass standard system-proxy env vars - tests must inject the stub URL via DI instead of relying on `HTTPS_PROXY`
  - **`hyper::Client` directly** (rather than `reqwest`): bypasses any `reqwest`-targeted middleware / proxies; stub via DI of the URL or use `hyper`-level test patterns
- [ ] `tokio::test::block_in_place` not used in tests - use `#[tokio::test(flavor = "multi_thread")]` instead
- [ ] Coverage via `cargo llvm-cov` (or `cargo tarpaulin`) wired to CI with per-package thresholds; coverage exclusions documented
- [ ] `cargo audit` / `cargo deny check advisories` in CI - new advisories block merge
- [ ] `mockall`-generated mocks regenerated when traits change (the macro re-runs on build; CI catches mismatches via build failure)
- [ ] Doc tests (`cargo test --doc`) run on `///` examples in `pub` items

## Rust Review Checklist

Quick-reference checklist for reviewing existing Rust tests:

- [ ] Test type matches what is being tested (handler -> `axum-test` / `oneshot`, repository -> testcontainers, service -> unit + `mockall`)
- [ ] Tests are table-driven (`Vec<Case>` loop or `rstest`), not copy-pasted
- [ ] Every endpoint has at least happy + 401 + 403 + validation-error
- [ ] Every non-trivial repository query has an integration test against testcontainers (not SQLite)
- [ ] Every custom middleware has a passing-and-denied test
- [ ] Test data created via factories, not raw struct literals
- [ ] No `let repo = MockRepo::default(); repo.save = ...` mocks when an integration test could assert real DB state
- [ ] No full-stack E2E tests for what a handler test could cover
- [ ] No in-process job mock masking at-least-once / retry semantics on critical tasks
- [ ] `cargo clippy --all-targets -- -D warnings` clean in CI
- [ ] No `Box<dyn Any>` / `serde_json::Value` on mocked methods - use the `mockall`-generated typed mock
- [ ] Property tests used for pure invariants where they apply
- [ ] No `tokio::time::sleep` to wait for async work to settle - use `tokio::sync::Notify`, `oneshot`, or explicit synchronization

## Output Format

**Which output to produce:**

- User asks "what tests are missing?" or "review our test coverage" -> Coverage Assessment
- User asks "write tests for X" or "scaffold tests" -> Test Scaffolds
- User asks "test strategy", "test plan", or coverage is below 50% with no scaffolds requested -> Strategy Doc (optionally include Coverage Assessment)
- User asks for **two or more deliverables in the same invocation** ("review coverage AND scaffold tests", "what's missing and write the tests") -> produce them in this order, separated by a horizontal rule (`---`): Coverage Assessment, then Strategy Doc (if requested), then Test Scaffolds. Do not silently drop one.
- If unclear, produce Strategy Doc as the default.

**Coverage Assessment:**

```markdown
## Rust Test Coverage Assessment

**Stack:** Rust <version> / Axum <version>
**Runtime:** Tokio <version>
**Data Access:** sqlx <version> | diesel <version> | mixed
**Messaging:** Tokio queue | AMQP (lapin) | Kafka (rdkafka) | none
**Test framework:** `#[tokio::test]`, `axum-test` / `tower::oneshot`, testcontainers, `mockall`, `proptest`
**Coverage gaps:**

- **Unit tests:** [services / validators / mappers without test coverage]
- **Property tests:** [pure functions with invariants but no proptest coverage]
- **Handler tests:** [endpoints without tests; endpoints missing 401/403/validation paths]
- **Integration tests:** [repositories with non-trivial queries without tests; tests running on SQLite for a Postgres app]
- **Auth tests:** [endpoints without authorization tests; missing JWT middleware tests]
- **Web hazard tests:** [IDOR / per-owner triples missing; open redirect without allowlist tests; file upload without path-traversal / MIME / size tests; bulk export without scoping / row-cap tests; SSRF without allowlist tests; privilege-escalation guards untested]
- **Job tests:** [background-task handlers without tests; tasks without idempotency / retry tests]
- **Concurrency gaps:** [async functions tested only with `#[tokio::test]` single-thread when they spawn cross-thread work]
- **Contract tests:** [OpenAPI / Pact contracts without verification]

**Recommended pyramid balance:**

- Unit (services, validators, helpers): [count target]
- Handler + integration (`axum-test` + testcontainers): [count target]
- E2E (full stack with broker): [count target - keep small]

**Prioritization** _(include when current coverage is below ~50% or the assessment surfaces > 5 gaps)_

Apply the Step 7 risk bands. Order follow-up work as:

1. **P1 - Authorization & authentication:** [list specific endpoints / flows missing 401/403/ownership tests]
2. **P2 - Data integrity:** [repositories with non-trivial queries / write paths without rollback tests / background tasks with unguarded side effects]
3. **P3 - Business-critical flows:** [revenue, state machines, scheduled tasks touching billing or notifications]
4. **P4 - High-churn code:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pass-through handlers / simple CRUD - lowest risk]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run Rust test files using project conventions. Each scaffold must include:

- The right test type (handler / integration / unit / job / property)
- Table-driven structure (`Vec<Case>` loop or `rstest::case`) when behavior varies by input
- Factories for test data instead of raw struct literals
- For handler tests: happy path + 401 + 403 + validation-error
- For repository tests: testcontainers PostgreSQL; assertions against PostgreSQL semantics
- For auth tests: anonymous + wrong-role + correct-role cases
- For job tests: idempotency + retry + max-retries cases when applicable
- `#[tokio::test]` (or `#[tokio::test(flavor = "multi_thread")]` when cross-thread is required)
- `cargo clippy --all-targets -- -D warnings`-clean

**Strategy Doc** (when designing a test strategy):

```markdown
## Rust Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Handler + Integration {y}% / E2E {z}%
**Tooling:** `#[tokio::test]`, `axum-test` (or `tower::oneshot`), testcontainers PostgreSQL, `mockall`, `proptest`, `cargo nextest`, `cargo clippy --all-targets -- -D warnings`
**Database isolation:** testcontainers PostgreSQL via shared `OnceCell`; per-test transactional rollback (`pool.begin().await?` then drop without commit)
**Concurrency:** `#[tokio::test(flavor = "multi_thread")]` for code that must run cross-thread; `cargo clippy` mandatory in CI
**Gaps to close (prioritized):**

1. [Highest risk gap - typically authorization or repository correctness]
2. [...]
```

## Self-Check

**Always (any deliverable):**

- [ ] Stack confirmed as Rust / Axum; data-access mix and messaging recorded before any framework-specific guidance applied (Step 1)
- [ ] Code under test and a representative sample of existing tests + setup files read directly so output matches project conventions (Step 2)
- [ ] `rust-testing-patterns` consulted for canonical Rust test patterns
- [ ] Auth testing approach explicit (test-issued JWT or test-only middleware injecting claims into request extensions)
- [ ] Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage from plan.md, no out-of-scope tests)

**Strategy Doc / Coverage Assessment only:**

- [ ] Test pyramid mapped to Rust idioms (unit -> `#[tokio::test]` + `mockall`; handler -> `axum-test` / `oneshot`; integration -> testcontainers; background-task -> in-process + real-broker for non-trivial cases)
- [ ] Boundaries clearly defined: each layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization by risk applied when coverage is low - P1 authorization, P2 data integrity, P3 business-critical, P4 high-churn, P5 plumbing
- [ ] testcontainers used for repository and full-context tests; SQLite flagged as a smell for production-Postgres apps
- [ ] `cargo clippy --all-targets -- -D warnings` CI presence flagged when packages with concurrent code lack lint coverage

**Test Scaffolds only:**

- [ ] Tests are table-driven (`Vec<Case>` loop or `rstest`), not copy-pasted per case
- [ ] Test data created via factory fns, not raw struct literals; typed factory return shapes
- [ ] Handler scaffolds include happy path + 401 + 403 + validation-error; IDOR test for any per-owner / per-tenant resource
- [ ] Handler scaffolds apply same global middleware as `src/main.rs` (missing auth middleware masks authorization bugs)
- [ ] Repository scaffolds run against testcontainers PostgreSQL with per-test cleanup - never SQLite for Postgres apps
- [ ] Background-task scaffolds include idempotency + retry; real-broker (testcontainers Redis / Kafka) variant present for tasks with non-trivial retry / ack semantics
- [ ] `#[tokio::test]` (or `#[tokio::test(flavor = "multi_thread")]` for cross-thread)
- [ ] Validator unit tests scaffolded for any non-trivial DTO with custom `#[validate(...)]` derives
- [ ] `proptest` scaffold proposed for any pure function with a clear invariant

**Review-existing-tests mode only:**

- [ ] Review checklist items addressed for every test file in scope

## Avoid

- Scaffolding tests without first reading existing tests + setup files - the result imports the wrong factory, uses the wrong HTTP-stub library, or duplicates the integration-test base fixture
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no auth tests misses the bigger threat
- Writing a separate test fn per case when a `Vec<Case>` loop or `rstest` would do - copy-paste tests are harder to maintain and grow inconsistencies
- Full E2E tests (full testcontainers + real broker) for what a handler test could cover - context cost compounds across the suite
- SQLite / in-memory DB in repository tests for apps that use PostgreSQL features (JSONB, partial indexes, `ON CONFLICT`, array types) - tests pass, prod fails. sqlx's compile-time-checked queries are validated against PostgreSQL specifically; running against SQLite defeats the macro
- Handler tests that build the router without applying the same global middleware as `src/main.rs` - validation rules and auth differ between test and prod silently
- Duplicating factories per module - share via `tests/common/mod.rs`
- Using `MockRepo::expect_save(...).times(1)` mocks when a testcontainers integration test could assert real DB state
- Mocking auth middleware to silence DTO failures - the test is now incorrect for the prod config
- Skipping validator unit tests because the handler has an integration test - validators are unit-tested separately so they can be reused
- Testing framework internals (e.g., that Axum routes match, that `validator` runs `length` checks) - test your wiring, not the framework
- Using in-process worker mocks as a substitute for a real-broker test on tasks with non-trivial retry / ack semantics - the mock skips the broker and masks at-least-once / DLQ semantics
- Using `Box<dyn Any>` / `serde_json::Value` to silence type errors in mocks - use `mockall`-generated typed mocks or hand-written mocks with the right signature
- Using `tokio::time::sleep(Duration::from_millis(100))` to wait for async work to "probably finish" - use a `oneshot` channel, `Notify`, or `JoinHandle::await`; sleep-based waits are flaky and slow
