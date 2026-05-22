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

# Rust Test

Stack-specific delegate of `task-code-test` for Rust / Axum. Preserves the core workflow's output contract.

## When to Use

- Design a test strategy for a new Rust / Axum service or module
- Assess test coverage gaps across unit / property / integration / handler / job layers
- Scaffold tests for under-covered handlers, services, repositories, auth, or workers
- Review test pyramid balance for a Rust app

**Not for:** test failure debugging (`task-rust-debug`), general code review (`task-rust-review`), incident postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Apply behavioral principles

Use skill: `behavioral-principles`. These rules govern every step that follows.

### Step 2 - Confirm stack

Use skill: `stack-detect`. If invoked as a delegate of `task-code-test` (parent already detected Rust), accept the pre-confirmed stack. If stack is not Rust, stop and tell the user to invoke `/task-code-test`.

Record `Data Access` (sqlx / diesel / mixed), `Messaging` (Tokio queue / AMQP / Kafka / none), `Mock Framework` (`mockall` / hand-written / `mockito`) for the output.

### Step 3 - Apply spec-aware mode (conditional)

If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, Use skill: `spec-aware-preamble`. Generate one test per acceptance criterion (`// Satisfies: AC<N>`), cover every NFR via `plan.md`, refuse tests for out-of-scope behavior. Never edit spec artifacts; surface gaps as proposed amendments.

### Step 4 - Read code under test and existing tests

Before producing output, read both production code and a representative sample of tests so output matches project convention.

- Target module: `pub` items, request/response types, middleware, transaction boundaries, external collaborators
- One handler test, one service / repository test, one background-task test (if any), `tests/common/mod.rs`
- `Cargo.toml [dev-dependencies]`, `Makefile`/`justfile`/CI for `cargo test` vs `cargo nextest`, clippy gates, `cargo audit`
- `src/main.rs` (or `src/app.rs`) middleware order that handler tests must replicate

Greenfield (no existing tests): state your choices explicitly, do not invent silently. Defaults: integration / handler tests under `tests/`, unit tests via `#[cfg(test)] mod tests`; `#[tokio::test]` (multi-thread only when handlers spawn); `axum-test::TestServer`; testcontainers Postgres via shared `OnceCell` + per-test transactional rollback; `mockall #[automock]`; `proptest`; `cargo nextest`; `cargo clippy --all-targets -- -D warnings`; `tests/common/mod.rs` for fixtures.

Use skill: `rust-testing-patterns` for canonical Rust test forms.

### Step 5 - Rust test pyramid

| Layer       | Tooling                                                                      | What belongs here                                                              |
| ----------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Unit        | `#[test]` / `#[tokio::test]` + `mockall`                                     | Service logic, validators, mappers, pure functions                             |
| Property    | `proptest` / `quickcheck` on pure functions                                  | Calculation invariants, parsers, state-machine laws                            |
| Integration | `#[tokio::test]` + testcontainers Postgres + real sqlx / diesel              | Repository queries, DB constraints, ORM behavior                               |
| Handler     | `axum-test::TestServer` or `tower::ServiceExt::oneshot` against real router  | Routing, request/response binding, validation, middleware                      |
| Job         | In-process worker fn OR testcontainers Redis / Kafka + real worker           | Background-task happy path, retry, idempotency                                 |
| E2E         | `axum-test::TestServer` + testcontainers (Postgres + broker)                 | Critical user journeys only (signup, checkout, payment)                        |
| Contract    | Pact / OpenAPI (e.g., `utoipa` schema validation)                            | API contract validation                                                        |

**Many** unit tests, **some** handler / integration, **few** E2E. Clippy and `cargo test` (or `nextest`) on every CI run.

### Step 6 - Apply Rust test patterns

**Async (canonical form):** `#[tokio::test]`; `flavor = "multi_thread"` only when handlers spawn or workers run cross-thread.

**Table-driven (`Vec<Case>` loop or `rstest::case`):**

```rust
#[rstest]
#[case(valid_input(), Ok(OrderId(1)))]
#[case(bad_input(), Err(AppError::Validation(_)))]
#[tokio::test]
async fn place_order(#[case] input: PlaceOrderInput, #[case] expected: Result<OrderId, AppError>) {
    assert_eq!(service.place(input).await, expected);
}
```

Failure messages must cite the case (line for `rstest`, explicit `name` for manual loops).

**Unit (`#[cfg(test)] mod tests`):** one fn per outcome; no `Router::new()` or `PgPool`; stub external HTTP via `mockito`/`wiremock`; `mockall #[automock]` for trait mocks; `pretty_assertions::assert_eq` for diff output.

**Property (`proptest`):** for pure invariants (round-trip, monotonicity, state-machine laws). Not for "more cases" of a non-deterministic function (HTTP, DB) - it generates inputs, not environments.

```rust
proptest! {
    #[test]
    fn order_total_never_negative(items in prop::collection::vec(any::<OrderItem>(), 0..100)) {
        prop_assert!(calculate_total(&items) >= Money::zero());
    }
}
```

**Handler (`axum-test::TestServer` or `tower::ServiceExt::oneshot`):**

- Build the router with **the same global middleware as `main.rs`** (TraceLayer, request-id, error handler, auth). Missing auth in test masks authorization bugs.
- One test per `(method, path, principal-state, outcome)` triple.
- Auth: test-issued JWT, OR a test-only middleware injecting claims into `Request::extensions_mut()`.
- Assert key fields, status, headers, `Content-Type`.

**Repository (testcontainers Postgres):**

- **Not SQLite** - sqlx compile-checked queries validate against Postgres; SQLite diverges on JSONB, partial indexes, `ON CONFLICT`, arrays, `LATERAL`.
- Share container via `OnceCell<TestContainer>` in `tests/common/mod.rs`; run `sqlx::migrate!()` once.
- Isolate per test: `let mut tx = pool.begin().await?;` then drop without commit, OR truncate fixture per test.
- One test per non-trivial query; assert SQL semantics (filter, sort, JOIN); for constraints insert violating data and assert specific error (`code() == "23505"` for unique).

**DTO / validator:** call `validator::Validate::validate(&req)` directly; faster than a handler round-trip.

**Background-task / broker:**

- In-process for fast tests: invoke handler fn with constructed payload.
- testcontainers Redis / Kafka + real worker for non-trivial retry / ack / DLQ semantics.
- Required cases per task: idempotency (invoke twice, side effect once), retry (fail-N-then-succeed), max-retries / DLQ (fail forever, no infinite loop).
- For Kafka (`rdkafka`): `mock_cluster::MockCluster` in-process, or testcontainers Kafka for full integration.

**E2E:** reserve for cases requiring the full stack (end-to-end auth, transactional commit + dispatched task). Use `axum-test::TestServer` + testcontainers Postgres + broker. Do not use where a handler test suffices.

**Lint and runner:** `cargo clippy --all-targets -- -D warnings` mandatory; `cargo nextest run` when adopted; `cargo test --doc` for `///` examples; `cargo audit` + `cargo deny check advisories` in CI.

### Step 7 - Test boundaries

**Unit:** service logic, mappers, validators, custom middleware fn in isolation, pure functions, concurrent helpers (`#[tokio::test(flavor = "multi_thread")]`).

**Property:** parsers, serialization round-trips, monotonic calculations, idempotent operations, domain laws ("refund never exceeds payment").

**Handler (every endpoint):** happy + 401 + 403 + 4xx validation; pagination, filtering, sorting contracts; `AppError` -> HTTP status mapping.

**Web hazards (handler-level; default to P1 in Step 8):**

| Hazard                | Handler-shape signal                                  | Test                                                                |
| --------------------- | ----------------------------------------------------- | ------------------------------------------------------------------- |
| IDOR                  | `:id` path + user-owned resource                      | Owner / other-user / anonymous trio                                 |
| Open redirect         | `Redirect::to(&user_input)`                           | Allowlist; reject `//evil.com`, schemes, encoded forms              |
| File upload           | `Multipart` or path joining `user_filename`           | Path traversal, MIME-vs-`Content-Type`, size cap, atomic write      |
| Bulk export           | `fetch_all` of an entity / `/admin/export`            | Authz + row-cap + tenant scoping                                    |
| SSRF                  | `reqwest::get(user_url)`                              | Allowlist rejects metadata IP, loopback, RFC1918; DNS-rebind        |
| Privilege escalation  | `update_user` / `update_role` handlers                | Non-admin cannot self-promote; explicit admin guard                 |
| Command injection     | `Command::new("sh").arg("-c")` or `format!`-built     | Use arg-list invocation; reject metacharacters                      |

**Integration (testcontainers):** every repository method with a non-trivial query; DB constraints (unique, check, FK `ON DELETE`); migration smoke test on clean DB.

**Background-task:** every task with retry, idempotency, or external side effects; task chains; post-commit dispatch (fires after commit, not before).

**Does NOT need a test:** framework behavior (Axum routing, default `validator` rules); generated boilerplate (DTOs, `From` impls re-arranging fields); trivial delegation (`service::get -> repository::get` with no logic).

### Step 8 - Prioritize when coverage is low

When line coverage is below ~50%, run this **before** scaffolding - choose what to scaffold first.

1. **P1 - Authz / authn:** handler tests per protected endpoint (401 anonymous, 403 wrong-role); JWT middleware (issuer, audience, signature, expiry); custom auth middleware fn.
2. **P2 - Data integrity:** repository integration tests for non-trivial queries; service tests for writes (happy + rollback); background-task idempotency.
3. **P3 - Business-critical:** revenue paths (checkout, billing); state-machine transitions (exhaustive `match`); scheduled tasks touching billing or notifications.
4. **P4 - High-churn:** files with frequent recent commits (`git log --since="3 months ago"`) or fix history (`git log --grep="fix"`).
5. **P5 - Plumbing:** pass-through handlers, simple CRUD.

**Multi-band rule.** When a target qualifies for multiple bands, file it under the **highest** band (lowest number) and note the secondary band; cover both axes (a refund test must assert idempotency AND refund-amount invariants). Do not split across bands - hides one risk.

### Step 9 - Test infrastructure hygiene

- [ ] testcontainers shared via `OnceCell` / `Lazy`, not per-test creation
- [ ] `cargo clippy --all-targets -- -D warnings` in CI
- [ ] Test profile never silently disables auth middleware
- [ ] `tests/` integration crate separated from `#[cfg(test)] mod tests` unit blocks
- [ ] HTTP stubs (`mockito` / `wiremock`) intercept all outbound calls - SDKs (`aws-sdk-*`, GCP, `tonic` gRPC, custom `reqwest`/`hyper` clients) bypass stubs unless the endpoint URL is injected via DI; assert `>= 1` hit on each stub to catch silent bypass
- [ ] `cargo llvm-cov` (or `tarpaulin`) coverage wired to CI with documented exclusions
- [ ] `cargo audit` / `cargo deny check advisories` in CI; new advisories block merge
- [ ] Doc tests (`cargo test --doc`) run on `///` examples in `pub` items
- [ ] `tokio::time::sleep` not used to wait for async work - use `Notify`, `oneshot`, or `JoinHandle::await`

## Output Format

**Which output:**

- "what tests are missing?" / "review coverage" -> Coverage Assessment
- "write tests for X" / "scaffold tests" -> Test Scaffolds
- "test strategy" / "test plan" / coverage < 50% without scaffold request -> Strategy Doc
- Multiple deliverables in one ask -> produce in order separated by `---`: Coverage Assessment, Strategy Doc, Test Scaffolds. Do not silently drop one.
- Unclear -> Strategy Doc as default.

**Coverage Assessment:**

```markdown
## Rust Test Coverage Assessment

**Stack:** Rust <version> / Axum <version>
**Runtime:** Tokio <version>
**Data Access:** sqlx <version> | diesel <version> | mixed
**Messaging:** Tokio queue | AMQP (lapin) | Kafka (rdkafka) | none
**Test framework:** `#[tokio::test]`, `axum-test` / `tower::oneshot`, testcontainers, `mockall`, `proptest`

**Coverage gaps:**

- **Unit:** [services / validators / mappers without coverage]
- **Property:** [pure functions with invariants but no proptest]
- **Handler:** [endpoints without tests; missing 401/403/validation paths]
- **Integration:** [repositories with non-trivial queries untested; SQLite on a Postgres app]
- **Auth:** [endpoints missing authz tests; missing JWT middleware tests]
- **Web hazards:** [IDOR triples / open-redirect / file-upload / bulk-export / SSRF / priv-esc gaps]
- **Job:** [background tasks without idempotency / retry tests]
- **Concurrency:** [async fns spawning cross-thread tested only on single-thread runtime]
- **Contract:** [OpenAPI / Pact contracts without verification]

**Pyramid balance:** Unit [n] / Handler + Integration [n] / E2E [n - keep small]

**Prioritization** _(when coverage < ~50% or > 5 gaps)_

1. P1 - Authz / authn: [endpoints / flows]
2. P2 - Data integrity: [repos / writes / tasks]
3. P3 - Business-critical: [revenue / state machines / scheduled]
4. P4 - High-churn: [files]
5. P5 - Plumbing: [pass-through / simple CRUD]
```

**Test Scaffolds:** ready-to-run Rust files using project conventions. Each must include the right test type; table-driven structure when behavior varies; factory fns for data; `#[tokio::test]` (multi-thread only when needed); clippy-clean. Handler scaffolds: happy + 401 + 403 + validation + IDOR triple for per-owner resources. Repository: testcontainers Postgres. Auth: anonymous + wrong-role + correct-role. Job: idempotency + retry + max-retries.

**Strategy Doc:**

```markdown
## Rust Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Handler + Integration {y}% / E2E {z}%
**Tooling:** `#[tokio::test]`, `axum-test`, testcontainers Postgres, `mockall`, `proptest`, `cargo nextest`, `cargo clippy --all-targets -- -D warnings`
**Database isolation:** testcontainers Postgres via shared `OnceCell`; per-test transactional rollback
**Concurrency:** `#[tokio::test(flavor = "multi_thread")]` for cross-thread code; clippy mandatory in CI
**Gaps to close (prioritized):**

1. [Highest-risk gap, typically authorization or repository correctness]
2. [...]
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded before any other step
- [ ] Step 2 - Stack confirmed as Rust / Axum; `Data Access`, `Messaging`, `Mock Framework` recorded
- [ ] Step 3 - Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage, no out-of-scope tests)
- [ ] Step 4 - Code under test and a sample of existing tests + `Cargo.toml` + CI config read directly; `rust-testing-patterns` consulted
- [ ] Step 5 - Pyramid mapped to Rust idioms (unit -> `#[tokio::test]` + `mockall`; handler -> `axum-test` / `oneshot`; integration -> testcontainers; job -> in-process + real-broker for non-trivial cases)
- [ ] Step 6 - Patterns applied: tests table-driven when behavior varies; factories not raw literals; handler builds the same middleware as `main.rs`; repos use testcontainers Postgres, never SQLite; jobs cover idempotency + retry + DLQ
- [ ] Step 7 - Boundaries respected (no `PgPool` in unit tests, no E2E for what a handler covers); web-hazard table applied where handler shape signals risk
- [ ] Step 8 - Risk bands applied when coverage is low (P1 authz, P2 data, P3 critical, P4 churn, P5 plumbing); multi-band targets noted with secondary band
- [ ] Step 9 - Infra hygiene checks pass (shared testcontainers, clippy in CI, no sleep-based waits, SDK stub hits asserted)

## Avoid

- Scaffolding without reading existing tests + setup files - imports the wrong factory or stub library, duplicates fixtures
- Chasing coverage % over risk - 100% lines with no auth tests is worse than 60% with auth covered
- Separate test fn per case where `Vec<Case>` or `rstest` suffices
- Full E2E where a handler test covers the same risk - context cost compounds
- SQLite / in-memory DB on a Postgres app - JSONB, partial indexes, `ON CONFLICT`, arrays diverge; sqlx compile-checked queries validate against Postgres specifically
- Handler tests built without the same global middleware as `main.rs` - auth and validation diverge from prod silently
- `MockRepo::expect_save(...).times(1)` where testcontainers could assert real DB state
- Mocking auth middleware to silence failures - test is no longer valid for prod config
- Skipping validator unit tests because a handler test covers the path - validators are unit-tested separately for reuse
- Testing framework internals (Axum routing, `validator` built-ins) - test the wiring, not the framework
- In-process job mocks for tasks with non-trivial retry / ack semantics - masks at-least-once / DLQ
- `Box<dyn Any>` / `serde_json::Value` in mocks to silence type errors - use `mockall` typed mocks
- `tokio::time::sleep` to wait for async work - use `Notify`, `oneshot`, or `JoinHandle::await`
