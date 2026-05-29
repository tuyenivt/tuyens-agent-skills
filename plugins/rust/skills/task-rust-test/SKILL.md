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
- Review test pyramid balance

**Not for:** test failure debugging (`task-rust-debug`), general review (`task-rust-review`), postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Apply behavioral principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm stack

Use skill: `stack-detect`. If invoked as a delegate of `task-code-test` and the parent already detected Rust, accept the pre-confirmed stack. If stack is not Rust, stop and tell the user to invoke `/task-code-test`.

Record `Data Access` (sqlx / diesel / mixed), `Messaging` (Tokio queue / AMQP / Kafka / none), `Mock Framework` (`mockall` / hand-written / `mockito` / `wiremock`) for the output.

### Step 3 - Apply spec-aware mode (conditional)

If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists for the code under test, Use skill: `spec-aware-preamble`. One test per acceptance criterion (`// Satisfies: AC<N>`), cover every NFR via `plan.md`, refuse out-of-scope tests. Never edit spec artifacts; surface gaps as proposed amendments.

### Step 4 - Read code and existing tests

Read before producing output:

- Target module: `pub` items, request/response types, middleware, transaction boundaries, external collaborators
- One handler test, one service / repository test, one background-task test (if any), `tests/common/mod.rs`
- `Cargo.toml [dev-dependencies]`, `Makefile`/`justfile`/CI for `cargo test` vs `cargo nextest`, clippy gates, `cargo audit`
- `src/main.rs` (or `src/app.rs`) middleware order that handler tests must replicate

Greenfield: state choices explicitly. Defaults: `tests/` for integration / handler, `#[cfg(test)] mod tests` for unit; `#[tokio::test]` (multi-thread only when handlers spawn or workers run cross-thread); `axum-test::TestServer`; testcontainers Postgres shared via `OnceCell` with per-test schema or transactional rollback; `mockall #[automock]`; `proptest`; `cargo nextest`; `cargo clippy --all-targets -- -D warnings`; `tests/common/mod.rs` for fixtures.

### Step 5 - Map pyramid and boundaries

Use skill: `rust-testing-patterns` for canonical forms (async, mockall, oneshot, testcontainers, proptest, sleep-free sync).

| Layer       | Tooling                                                                | Belongs here                                                                        | Does NOT belong            |
| ----------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | -------------------------- |
| Unit        | `#[test]` / `#[tokio::test]` + `mockall`                               | Service logic, validators, mappers, pure fns, custom middleware fns                 | `Router::new()`, `PgPool`  |
| Property    | `proptest`                                                             | Calculation invariants, parsers, serde round-trips, domain laws                     | HTTP / DB / non-determinism|
| Integration | `#[tokio::test]` + testcontainers Postgres + real sqlx / diesel        | Non-trivial queries, DB constraints, migrations                                     | SQLite / in-memory DB      |
| Handler     | `axum-test::TestServer` or `tower::ServiceExt::oneshot`                | Routing, binding, validation, middleware, `AppError` -> HTTP mapping                | Framework internals        |
| Job         | In-process fn OR testcontainers Redis / Kafka + real worker            | Happy path, idempotency, retry, max-retries / DLQ, post-commit dispatch             | Non-trivial retry mocked   |
| E2E         | `axum-test::TestServer` + testcontainers (Postgres + broker)           | Critical journeys only (signup, checkout, payment)                                  | What a handler test covers |
| Contract    | Pact / `utoipa` schema validation                                      | API contract verification                                                           | -                          |

Many unit, some handler / integration, few E2E.

### Step 6 - Apply Rust-specific guardrails

**Handler tests must build the router with the same global middleware as `main.rs`** (TraceLayer, request-id, error handler, auth). Missing auth in test masks authorization bugs.

**Repository tests use testcontainers Postgres, never SQLite.** sqlx compile-checked queries validate against Postgres; SQLite diverges on JSONB, partial indexes, `ON CONFLICT`, arrays, `LATERAL`.

**Background-task tests cover idempotency (invoke twice, side effect once), retry (fail-N-then-succeed), and max-retries / DLQ (fail forever, no infinite loop).** In-process is fine for fast tests; use testcontainers Redis / Kafka + real worker for non-trivial retry / ack / DLQ semantics. For `rdkafka`: `mock_cluster::MockCluster` in-process or testcontainers Kafka.

**Table-driven when behavior varies** (`Vec<Case>` loop or `rstest::case`). Failure messages cite the case (line for `rstest`, explicit `name` for manual loops).

**Validators (`validator` crate) get unit tests** (`req.validate()` directly) for reuse, even when a handler test covers the same path.

**Every protected endpoint:** happy + 401 + 403 + 4xx validation; pagination / filtering / sorting contracts.

**Web hazards (handler-level; default to P1 in Step 8):**

| Hazard                | Handler-shape signal                                  | Test                                                                |
| --------------------- | ----------------------------------------------------- | ------------------------------------------------------------------- |
| IDOR                  | `:id` path + user-owned resource                      | Owner / other-user / anonymous trio                                 |
| Open redirect         | `Redirect::to(&user_input)`                           | Allowlist; reject `//evil.com`, schemes, encoded forms              |
| File upload           | `Multipart` or path joining `user_filename`           | Path traversal, MIME-vs-`Content-Type`, size cap, atomic write      |
| Bulk export           | `fetch_all` of an entity / `/admin/export`            | Authz + row-cap + tenant scoping                                    |
| SSRF                  | `reqwest::get(user_url)`                              | Allowlist rejects metadata IP, loopback, RFC1918; DNS-rebind        |
| Privilege escalation  | `update_user` / `update_role` handlers                | Non-admin cannot self-promote; explicit admin guard                 |
| Command injection     | `Command::new("sh").arg("-c")` or `format!`-built     | Arg-list invocation; reject metacharacters                          |

**Does NOT need a test:** framework behavior (Axum routing, default `validator` rules), generated boilerplate (DTOs, trivial `From` impls), trivial delegation (`service::get -> repository::get` with no logic).

### Step 7 - Prioritize when coverage is low

When line coverage is below ~50%, run this **before** scaffolding.

1. **P1 - Authz / authn:** handler tests per protected endpoint (401 anonymous, 403 wrong-role); JWT middleware (issuer, audience, signature, expiry); custom auth middleware fns.
2. **P2 - Data integrity:** repository integration tests for non-trivial queries; service writes (happy + rollback); background-task idempotency.
3. **P3 - Business-critical:** revenue paths (checkout, billing); state-machine transitions (exhaustive `match`); scheduled tasks touching billing or notifications.
4. **P4 - High-churn:** files with frequent recent commits or fix history.
5. **P5 - Plumbing:** pass-through handlers, simple CRUD.

**Multi-band rule.** File a target under the highest band (lowest number) and note the secondary band; cover both axes (a refund test asserts idempotency AND refund-amount invariants). Do not split across bands.

### Step 8 - Infra hygiene

- [ ] testcontainers shared via `OnceCell` / `Lazy` with per-test isolation (unique schema or transactional rollback), not per-test container
- [ ] `cargo clippy --all-targets -- -D warnings` in CI; `cargo audit` / `cargo deny check advisories` block merge on new advisories
- [ ] Test profile never silently disables auth middleware
- [ ] HTTP stubs (`mockito` / `wiremock`) intercept all outbound calls; SDKs (`aws-sdk-*`, GCP, `tonic` gRPC, custom `reqwest`/`hyper` clients) bypass stubs unless the endpoint URL is injected via DI - assert `>= 1` hit on each stub to catch silent bypass
- [ ] `cargo llvm-cov` (or `tarpaulin`) wired to CI with documented exclusions
- [ ] `cargo test --doc` runs `///` examples in `pub` items

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
- **Property:** [pure fns with invariants but no proptest]
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

**Test Scaffolds:** ready-to-run files using project conventions. Each scaffold includes the right test type; table-driven when behavior varies; factory fns for data; `#[tokio::test]` (multi-thread only when needed); clippy-clean. Handler scaffolds: happy + 401 + 403 + validation + IDOR triple for per-owner resources. Repository: testcontainers Postgres. Auth: anonymous + wrong-role + correct-role. Job: idempotency + retry + max-retries.

**Strategy Doc:**

```markdown
## Rust Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Handler + Integration {y}% / E2E {z}%
**Tooling:** `#[tokio::test]`, `axum-test`, testcontainers Postgres, `mockall`, `proptest`, `cargo nextest`, `cargo clippy --all-targets -- -D warnings`
**Database isolation:** testcontainers Postgres via shared `OnceCell`; per-test schema or transactional rollback
**Concurrency:** `#[tokio::test(flavor = "multi_thread")]` for cross-thread code
**Gaps to close (prioritized):**

1. [Highest-risk gap, typically authorization or repository correctness]
2. [...]
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded first
- [ ] Step 2 - Stack confirmed Rust / Axum; `Data Access`, `Messaging`, `Mock Framework` recorded
- [ ] Step 3 - Spec-aware mode honored when `--spec` was passed
- [ ] Step 4 - Code, existing tests, `Cargo.toml`, CI config read; greenfield defaults stated when no tests exist
- [ ] Step 5 - Pyramid + boundaries mapped; `rust-testing-patterns` consulted for canonical forms
- [ ] Step 6 - Guardrails applied: handler middleware matches `main.rs`; repos use testcontainers Postgres (not SQLite); jobs cover idempotency + retry + DLQ; validators unit-tested; web-hazard table applied where signal present
- [ ] Step 7 - Risk bands applied when coverage is low; multi-band targets noted with secondary band
- [ ] Step 8 - Infra hygiene checked (shared containers, clippy / audit in CI, no silent auth bypass, SDK stub hits asserted, doc tests run)

## Avoid

- Scaffolding without reading existing tests + setup files - imports wrong factory or stub library, duplicates fixtures
- Chasing coverage % over risk - 100% lines with no auth tests is worse than 60% with auth covered
- Separate test fn per case where `Vec<Case>` or `rstest` suffices
- Full E2E where a handler test covers the same risk
- SQLite / in-memory DB on a Postgres app - JSONB, partial indexes, `ON CONFLICT`, arrays, `LATERAL` diverge
- Handler tests built without the same global middleware as `main.rs` - auth and validation diverge from prod silently
- `MockRepo::expect_save(...).times(1)` where testcontainers could assert real DB state
- Mocking auth middleware to silence failures - test is no longer valid for prod
- In-process job mocks for tasks with non-trivial retry / ack semantics - masks at-least-once / DLQ
- `Box<dyn Any>` / `serde_json::Value` in mocks to silence type errors - use `mockall` typed mocks
- `tokio::time::sleep` to wait for async work - use `Notify`, `oneshot`, or `JoinHandle::await`
