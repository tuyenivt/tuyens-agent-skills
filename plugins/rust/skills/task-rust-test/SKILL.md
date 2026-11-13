---
name: task-rust-test
description: Rust / Axum test plan and scaffolding - tokio::test, tower oneshot, sqlx::test, Testcontainers, mockall, proptest, insta, cargo nextest discipline.
agent: rust-test-engineer
metadata:
  category: backend
  tags: [rust, axum, testing, tokio-test, sqlx-test, testcontainers, mockall, proptest, insta, nextest, workflow]
  type: workflow
user-invocable: true
---

# Rust Test

Rust-aware test strategy and scaffolding using `#[tokio::test]`, `tower::ServiceExt::oneshot` on the production Axum `Router`, `#[sqlx::test]` and Testcontainers PostgreSQL for repositories, `mockall`, `proptest`, `insta`, `criterion`, `cargo nextest`. Floors: Rust 1.94+ (edition 2024), Tokio 1.x, Axum 0.8, sqlx 0.9; read the toolchain from `rust-toolchain.toml`, else `rust-version`, and name the older form when a project sits below a floor (Axum 0.7 routes write `/:id` where 0.8 writes `/{id}`).

## When to Use

- Test strategy for a new Rust/Axum service, or for a feature whose design exists but whose code does not yet
- Test-coverage gap assessment across layers
- Scaffolding tests for under-covered handlers / services / repositories / auth
- Test pyramid review
- Adding boundary tests to happy-path-only tests

**Not for:** test failure debugging, general review (`task-rust-review`).

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format (`rust-testing-patterns`' `## Test Strategy`); they are rule sets here, and only this skill's Output Format is emitted, with one exception - the atomic's `Count` format (`fns / cases`) governs every count this skill writes.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack and Data Access

Use skill: `stack-detect`. Accept pre-confirmed from parent. When the code under test is not Rust, stop and say so: this workflow is Rust-only. In a Cargo workspace the member crate under test is the stack, its `Cargo.toml` read in place of the primary stack `stack-detect` picked; name the member in the header.

`stack-detect` emits `ORM` (Diesel or SeaORM; sqlx is a query library and leaves it empty), `Database`, and `Test framework` (`rstest` or another declared test crate, else `cargo test`) - take those. `Database` stays `unknown` when only `sqlx` is declared: read its features (`postgres`, `mysql`, `sqlite`). Read the rest off `Cargo.toml`, `Cargo.lock`, and the repository constructors:

- **Versions:** the toolchain from `rust-toolchain.toml` / `rust-version`, the edition, and the resolved Axum (or the substitute named in Step 5), Tokio, sqlx and Diesel versions from `Cargo.lock` - these override any version `stack-detect` carried from an instruction file, in every header slot that renders one
- **Data Access:** sqlx macros (`query!` / `query_as!`) | sqlx runtime (`query_as::<_, T>`) | Diesel | SeaORM | tokio-postgres | mixed - sqlx <v> + Diesel <v>
- **DB error type:** sqlx raises `sqlx::Error::Database` (`code()`, `is_unique_violation()`), Diesel `DatabaseError(DatabaseErrorKind::UniqueViolation, _)`, tokio-postgres `Error::code()` against `SqlState` - *different* types (Step 5)
- **Messaging:** Postgres job table | apalis | Kafka (`rdkafka`) | AMQP (`lapin`) | in-process Tokio channel | none
- **Mock Framework:** `mockall` | hand-written fakes (a test struct implementing the trait) | **none present** - when none, propose hand-written fakes rather than adding a crate the project has not chosen. HTTP stubs: `wiremock` | `mockito` | `httpmock` | none. A vendored tree (`cargo vendor` with a `[source]` replacement in `.cargo/config.toml`) or an offline CI blocks new dependencies: propose only what is already vendored, else hand-written fakes

Every one of these has a slot in the header block (see Output Format).

### Step 3 - Read Code Under Test + Existing Tests

Ground output in project conventions, not generic templates.

- Read each target's module top-to-bottom: `pub` items, request/response types, layers, transaction boundaries, external collaborators
- Find `#[cfg(test)] mod tests` blocks and `tests/*.rs`; read one existing handler test, one service / repository test, one job test, and `tests/common/mod.rs` - learn layout, mocks, HTTP stubs, auth helpers. Each file directly under `tests/` is its own crate; `tests/common/mod.rs` is the shared-helper form that does not become one
- Read `Cargo.toml` `[dev-dependencies]` and features, `.config/nextest.toml`, `Makefile` / `justfile` / CI for `cargo test` vs `cargo nextest`, `#[ignore]` or feature segregation of Docker-backed tests, `SQLX_OFFLINE`, coverage
- Read the function that builds the production `Router` (`app(state)` in `src/app.rs` or `main.rs`) for the layer order handler tests must reuse; a layer production never mounts (an error mapper registered nowhere) is not replicated - assert the observable error and record the gap under `Findings`

**Conventions are the default, not the ceiling.** Adopt the project's layout, naming, helper, and fixture conventions. Do not adopt a convention this skill's `Avoid` list names as a defect - a house style of hand-built routers in handler tests, mocked-away auth, or SQLite standing in for Postgres is the gap you were called to close, not the pattern to copy. Say which convention you are departing from and why.

If no existing tests, no `Makefile`/CI, or no `tests/common`: say which is absent and propose the convention explicitly rather than inventing it silently. Proposed conventions belong in the deliverable, not only in your reasoning.

If exactly one existing test embodies a pattern `Avoid` rejects: write the new tests correctly alongside it, name the redundancy, and recommend deleting the old one - do not rewrite files the request did not ask you to touch. Watch for name collisions inside one `mod tests` and for a second `mod common` declaration in the same test crate.

**A test that asserts the desired behaviour of a defect present today** (the code returns 500 where the contract says 404) is written against the contract and marked `#[ignore = "defect: <file:line> - <what>"]`, so the suite stays green and the defect stays visible; list it under `Findings`, as is an existing test the requested design collides with. A test that merely pins today's wrong behaviour is never written.

### Step 4 - Rust Test Pyramid

| Layer | Tooling | What belongs |
|-------|---------|--------------|
| Unit | `#[test]` / `#[tokio::test]` + `mockall` / hand-written fakes | Service logic, validators, mappers, pure functions, a job handler called directly |
| Property | `proptest` | Invariants of calculations, parsers, serde round-trips |
| Integration | `#[sqlx::test]` or Testcontainers Postgres + the real data layer | Repository queries, constraints, DB invariants |
| Handler | production `Router` + `tower::ServiceExt::oneshot` | Routing, extraction, validation, layers, error mapping |
| Job | Postgres job table or Testcontainers broker + the real worker loop | Retry, backoff, max attempts, dead-letter - real queue behaviour |
| E2E | `axum::serve` on `127.0.0.1:0` + `reqwest` + Testcontainers (Postgres + broker) | Critical journeys only |
| Contract | Pact / OpenAPI (`utoipa`) consumer-driven | API contract validation |

**Many** unit, **some** handler / integration, **few** E2E - default band ~70% / ~25% / ~5%, stated as three numbers. Property sits in the unit band, Job in the handler+integration band, Contract in the E2E band. Shift up to 10 points from unit into handler+integration when the risk concentrates in DB semantics or endpoint authorization (Postgres-only queries, per-tenant scoping, a wide endpoint surface); state the reason. Keep E2E at ~5% and never invert the shape. `criterion` benches in `benches/` are not part of the pyramid.

### Step 5 - Apply Rust Test Patterns

Use skill: `rust-testing-patterns` for canonical async tests, fixtures, Testcontainers, mocking, and sleep-free synchronization. Notes below cover layer-specific or layout-specific items; where a note and the atomic disagree, the note says so and wins.

**Adapt every API name below to the stack recorded in Step 2.** The examples are written Axum-sqlx-Postgres-first because that is the common pairing. Another HTTP framework substitutes by role (actix-web: `actix_web::test::init_service` + `call_service` for `oneshot`, `ResponseError` for `IntoResponse`); a check with no equivalent is dropped rather than manufactured into a finding. Say what you substituted.

**Unit tests** (`#[cfg(test)] mod tests` colocated):

- One test function per public method; table-driven for outcomes (success, validation failure, external failure, edge) via `rstest` `#[case]` or a `Vec<Case>` loop whose assert message names the case
- **No `Router` / `PgPool`** - if a unit needs them, it's misclassified
- Stub external HTTP via `wiremock::MockServer`, its `uri()` injected as the client's base URL
- Trait mocks at service boundaries follow the `Mock Framework` recorded in Step 2: `#[automock]` on the consumer's trait (above `#[async_trait]` when both apply), or the hand-written fake already in the tree; **propose hand-written fakes when it is `none present`**
- Assert typed outcomes (`assert!(matches!(err, RefundError::NotFound))`), never a stringified error; `insta::assert_json_snapshot!` with redactions for ids and timestamps when a body is large
- Time: `#[tokio::test(start_paused = true)]` plus `tokio::time::advance` (Tokio's `test-util` feature, current-thread runtime only) - never a wall-clock `sleep`

**Axum handler tests:**

- The production router-building function, not a hand-built `Router`; same layers (trace, request-id, error mapping, auth) in the same order
- `app(state).oneshot(request).await` (`tower` with its `util` feature), the body read with `http_body_util::BodyExt::collect`
- One test per `(method, path, principal-state, outcome)` triple
- Auth via a test-issued JWT signed with a test key, a test-only layer inserting fixed claims, or a seeded key on an API-key service
- Authorization: "anonymous -> 401" per protected endpoint; "wrong role -> 403" when a role gate exists (N/A otherwise, said so); "another owner's / tenant's resource -> 404 or 403, whichever the contract fixes" for per-owner resources
- Validation: "rejects invalid payload" per DTO body. Axum's `Json` rejects a deserialization failure (unknown field, wrong type) with 422 and malformed JSON with 400 unless the project maps rejections - assert what the contract says, and a mismatch is a `Findings` entry
- Response shape: assert key fields, status, headers, `Content-Type`
- DB: `AppState` built on the test database's pool; per-test isolation per the Repository preference order below

```rust
use axum::body::{Body, Bytes};
use axum::http::{Request, StatusCode};
use axum::Router;
use http_body_util::BodyExt;
use tower::ServiceExt;

// called as send(app(state), Request::get("/refunds/1").body(Body::empty())?)
async fn send(app: Router, req: Request<Body>) -> (StatusCode, Bytes) {
    let res = app.oneshot(req).await.expect("Router's error type is Infallible");
    let status = res.status();
    (status, res.into_body().collect().await.expect("body").to_bytes())
}
```

**Repository / data-layer integration:**

- Real PostgreSQL - **not SQLite, not in-memory**. SQLite has no arrays, `LATERAL`, `FOR UPDATE`, jsonb containment / existence operators (`@>`, `?`) or GIN indexes, or SQLSTATE error codes, and its typing and FK checks are loose by default (it does have partial indexes, window functions, and `ON CONFLICT` upsert)
- `#[sqlx::test]` hands each test a fresh database on the server `DATABASE_URL` names, with `migrations/` applied - the default where CI provides a Postgres service. Without one, start a Testcontainers Postgres once per test binary behind a `tokio::sync::OnceCell` that holds the **connection URL**, never a pool: each `#[tokio::test]` runs its own runtime, and a pool built on one runtime fails on the next. A container held in a `static` is never dropped, so the CI job, not the test, removes it
- Per-test isolation, in preference order: **a fresh database per test** (`#[sqlx::test]`, or one cloned from a migrated template); **transactional rollback** when the repository methods take `&mut PgConnection` or an `Executor` - a `Transaction` dropped without `commit` rolls back. A test that must commit follows the atomic's committed-rows recipe (serial, explicit cleanup). Never edit production constructors just to inject a transaction
- One test per non-trivial query; assert SQL semantics (filter, sort, joins), not just "method returns something"
- N+1 detection: sqlx logs each statement as a `tracing` event on target `sqlx::query`; a test subscriber layer counting those events is the counter. Skip the check rather than fake it
- Constraint tests: insert violating data; assert the data layer's real error type - **sqlx `Error::Database(e)` with `e.code().as_deref() == Some("23505")` or `e.is_unique_violation()`; Diesel `DatabaseErrorKind::UniqueViolation`**. A repository that maps to a domain `Conflict` variant is asserted on that variant
- Container schema: run the project's migrations. When a model has drifted from them, the test still runs the migrations and the drift is a `Findings` entry, not an inlined schema. If `migrations/` does not exist, inline the DDL and name the drift risk explicitly
- Query macros compile against `DATABASE_URL` or committed `.sqlx/` data; queries that live only in tests need `cargo sqlx prepare -- --all-targets`, or `SQLX_OFFLINE=true` CI cannot build them

**DTO / validator:**

- Validation is tested through the handler by default. **This note wins for DTOs with custom rules:** a direct `validate()` test covers `#[validate(custom(function = "..."))]` rules exhaustively so the handler table stays representative. DTOs using only stock attributes get no validator test - the handler's "rejects invalid payload" case covers them
- `#[serde(deny_unknown_fields)]` is a serde rule, not a `validator` one: it is proved through the handler, never by `validate()`

```rust
use validator::{Validate, ValidationError};

fn not_blank(v: &str) -> Result<(), ValidationError> {
    if v.trim().is_empty() { Err(ValidationError::new("blank")) } else { Ok(()) }
}

#[derive(Validate)]
struct CreateRefund {
    #[validate(custom(function = "not_blank"))]
    reason: String,
}

#[test]
fn rejects_blank_reason() {
    let errs = CreateRefund { reason: "  ".into() }.validate().unwrap_err();
    assert!(errs.field_errors().contains_key("reason"));
}
```

**Jobs (Postgres job table / apalis / Kafka):**

- **In-process:** call the job handler function directly (`process(&ctx, job).await`) without a worker. No broker. Best for handler logic
- **Real worker** for tests needing actual queue behaviour (retry, backoff, max attempts): the worker loop against the test database (or a Testcontainers broker), retry delay configured to zero, and the terminal state awaited by re-reading the job's status under `tokio::time::timeout` - **this note wins over the atomic's no-poll rule** for real-worker tests, where no signal reaches the test
- Idempotency: invoke twice with same payload; assert side effect happens once
- Retry: stub external to fail twice then succeed; assert job completes; assert attempt count
- Dead / max-attempts: stub to fail forever; assert the job ends dead without infinite loop
- Permanent failure: assert a malformed payload goes straight to dead rather than burning the retry budget

**Kafka (`rdkafka`)** - the four checks above map, the APIs do not. Call the record handler directly for the in-process variant; `rdkafka::mocking::MockCluster` for the poll loop; Testcontainers Kafka when the test turns on real broker behaviour. Substitutions: max attempts / dead state -> a bounded retry wrapper plus a DLQ topic; dedup on the job key -> an idempotency key carried in the record. Additionally assert offsets are **not** committed when the handler returned an error (`enable.auto.commit=false`), and that a stale message `version` does not overwrite newer state - the at-most-once and out-of-order losses have no job-table analogue. With two brokers, each gets its own checks; a worker out of the request's scope is a named residual, not a scaffold.

**E2E:**

- Reserve for full-stack: auth flow end-to-end, commit + job dispatch, scheduled job behaviour
- `axum::serve` on a `TcpListener` bound to `127.0.0.1:0` in a spawned task, `reqwest` against it, Testcontainers Postgres + broker
- Avoid for what a handler test could cover

**Concurrency:** safe Rust rules out data races, not logical ones (two requests transitioning one row, a lost update, a lock held across `.await`). A default `#[tokio::test]` is a current-thread runtime and never runs two tasks at once: concurrency tests use `#[tokio::test(flavor = "multi_thread", worker_threads = 4)]`, drive the calls through `tokio::join!` or a `JoinSet`, and assert against the real database. `loom` is for hand-written lock-free primitives only.

### Step 6 - Test Boundaries

**Unit:** services, mappers, validators, middleware functions in isolation, pure functions, domain rules, calculations, state-machine transitions, concurrent helpers

**Handler:** every endpoint - happy + 401 (when an auth surface exists; `n/a` otherwise) + 403 (when a role gate exists) + other-owner + 4xx validation; pagination contract; filtering / sorting / search; `IntoResponse` error mapping

**Integration:** every repository method with a non-trivial query (multi-column filter, join, aggregate); constraints (unique, check, FK ON DELETE); migration smoke test on a clean database

**Jobs:** every job with retry, idempotency, or external side effects; workflows assert complete and aggregate; post-commit jobs assert they fire after the parent commits and never on rollback. **Dual writes** (a DB commit plus a publish, neither transactional) assert the divergence case: the row commits, the publish fails, and the caller sees the failure - the test pins which side wins

**Does NOT need a test:** framework-provided behaviour (Axum routing, layer dispatch, stock `validator` attributes); generated boilerplate (derives, trivial `From` impls); trivial delegation (`service.get(id) -> repository.get(id)` with no logic)

### Step 7 - Test Data and Fixtures

- Builder functions or `Default` plus struct update (`Refund { amount_cents: 5, ..refund() }`) over hand-rolled literals
- Integration-test helpers live in `tests/common/mod.rs`; unit tests in `src` cannot reach `tests/`, so their factories live in a `#[cfg(test)] pub(crate) mod test_support`. A shared `test-support` crate that depends on the crate under test is usable from `tests/` but **not** from that crate's own unit tests: the dev-dependency cycle compiles the crate twice, and its types do not match. The sharing rule loses to the compiler
- Repository tests: factories to insert; isolate per-test per Step 5's preference order
- Never mutate a shared fixture; build a fresh one per test
- Test data minimal - 100-row setups signal integration / load layer

### Step 8 - Coverage and Prioritization

**Establish the coverage number on every run** - the header's `Coverage` slot is unconditional. Take the first branch available and report which:

1. **Measured:** `cargo llvm-cov` (or `cargo llvm-cov nextest`) when the suite runs.
2. **Measured by enumeration:** no `#[test]`, `#[tokio::test]`, `#[sqlx::test]` or `#[rstest]` in the tree is 0%, a fact, not an estimate.
3. **Estimated:** when the suite cannot run (no toolchain, no Docker, broken build, no `.sqlx/` data and no database), take test lines (`tests/` plus every `#[cfg(test)]` module) over production lines, weighted per crate, and show the arithmetic so the number is auditable. Label it an estimate.
4. **Not applicable:** the feature under plan has no code yet - write `n/a - not implemented` and key the strategy to the design's seams (handlers, repository methods, jobs it names), listing product questions the design leaves open under `Open decisions`.

**Run the P1-P5 prioritization when coverage is under ~50% or more than 5 gaps are found** - the one trigger set, used here and by the Output Format. Gaps are found gaps in existing code; a design's planned tests are not gaps, and a `n/a - not implemented` coverage does not fire it - on that branch the Strategy Doc's `Gaps to close` lists the planned tests in P1-P5 band order. It runs **before** scaffolding: the Coverage Assessment carries it in `Prioritization` and any accompanying Scaffolds manifest follows its order; when it does not fire, the manifest is in request order.

A band whose evidence is unavailable is filled `not determinable - <reason>`, never dropped and never guessed: P4 needs `git log --since="3 months ago"`, which a tree with no VCS history cannot answer; a history that exists but is empty for the window is `none - no commits in window`. Keep the 1-5 structure intact.

When the highest band points outside the requested scope (P1 names the JWT layer; the user asked for handler + repository), stay in scope and list the band's targets as named residuals. Do not silently widen the work, and do not silently drop the priority. A service with no auth surface at all writes P1 as `none - no auth surface` and the header's `Auth in tests` as `n/a - service has no auth`.

| Priority | Targets |
|----------|---------|
| P1 - AuthN/Z | Handler test per protected endpoint asserting 401 anonymous + 403 wrong-role + other-owner; JWT layer tests (issuer, audience, signature, expiry); webhook signature verification; custom auth extractor unit tests |
| P2 - Data Integrity | Repository integration tests for non-trivial queries; service write-path tests (one happy + one rollback); job idempotency; multi-thread tests for concurrent paths |
| P3 - Business-Critical | Revenue paths (checkout, billing, subscription states); state-machine transitions; scheduled jobs touching billing or notifications |
| P4 - High-Churn | Files with frequent recent commits (`git log --since="3 months ago"`); files with bug-fix history |
| P5 - Plumbing | Pass-through handlers, simple CRUD - lower risk, can wait |

**Multi-band rule.** When a target qualifies for multiple bands (the refund job is P2 + P3), file under highest (lowest number) and note secondary so the plan covers both axes.

### Step 9 - Test Infrastructure Hygiene

Failing boxes are listed under the Coverage Assessment's `Infrastructure` gap line, or the `Prerequisites` of the Strategy Doc or Test Scaffolds.

- [ ] One database server per test binary (CI service or a `OnceCell`-held container URL), a fresh database or rollback per test - never a container per test, never a pool shared across runtimes
- [ ] Concurrency tests on the multi-thread runtime in CI
- [ ] Test configuration overrides only what differs from prod - never silently disables auth
- [ ] Docker-backed tests segregated (`#[ignore = "requires docker"]` run by a CI job with `--include-ignored`, or an `integration` cargo feature) and still compiled on every run
- [ ] HTTP stubs via `wiremock` / `mockito`; never real network in CI
- [ ] **SDK clients bypassing the stub** - it only intercepts when the system under test points at the stub's URL. Bypass surfaces: (a) `aws-sdk-*` - set `endpoint_url` on the config loader; (b) a `reqwest::Client` wrapper with a hard-coded base URL - the URL must be injected; (c) `tonic` gRPC - serve the real service on `127.0.0.1:0`, NOT an HTTP/1 stub; (d) a client that reads an emulator variable (`STORAGE_EMULATOR_HOST`) - the bypass is a test that never sets it. Verify with `wiremock`'s `.expect(1)`, checked when the `MockServer` drops. "No calls were made" as green signal is the failure mode
- [ ] Coverage via `cargo llvm-cov --html`; thresholds enforced with `--fail-under-lines` and documented per crate
- [ ] `cargo sqlx prepare --check -- --all-targets` in CI, so `.sqlx/` data cannot drift from the queries; `cargo test --doc` beside `cargo nextest run`, which skips doctests

## Output Format

**Which output to produce.** Check the combined row first, then the single rows top-down:

| Request | Deliverable |
| ------- | ----------- |
| 2+ of the rows below asked for together | All matched, in this order, separated by `---`: Coverage Assessment -> Strategy Doc -> Test Scaffolds |
| "Write tests for X" / "scaffold" | Test Scaffolds |
| "What tests are missing?" / "review coverage" | Coverage Assessment |
| "Test strategy" / "test plan" | Strategy Doc |
| Unclear | Strategy Doc |

Whatever the row, when the Step 8 trigger fires (coverage under ~50% or more than 5 gaps) the Coverage Assessment is emitted **as well**, ahead of the others - it is the only deliverable with a `Prioritization` slot. On a combined delivery the header block is emitted once, above the first document's heading, and each template's `<header block>` slot is left out; the documents follow in that order separated by `---`, a later one's `Findings`, `Open decisions` and `Residuals` listing only what is new to it (`as listed above` when nothing is).

**Every delivery opens with this header block**, so the Step 2 records and the coverage number always have a home:

```markdown
**Stack:** Rust <version> (edition <year>) / <framework> <version> - crate <name>     {crate suffix only in a Cargo workspace}

**Data Access:** sqlx <version> (macros | runtime) | Diesel <version> | SeaORM <version> | tokio-postgres | mixed - sqlx <version> + Diesel <version>

**DB engine / driver:** PostgreSQL via sqlx | PostgreSQL via Diesel | MySQL via sqlx | ... (inferred from crate features)     {suffix only when no instruction file declared it}

**Messaging:** Postgres job table | apalis | Kafka | AMQP | in-process channel | none

**Mock framework:** mockall | hand-written fakes | none present - proposing <what>; HTTP stubs: wiremock | mockito | httpmock | none

**Test framework:** cargo test [+ rstest | proptest | insta] [via cargo nextest]     {append "- proposing <addition>" when one is needed and not vendored}

**Coverage:** <n>% (measured | measured by enumeration | estimated - <method>) | n/a - not implemented

**Auth in tests:** test-issued JWT | claims-injecting layer | seeded API key | n/a - service has no auth

**Proposed conventions:** <layout, fixtures, Docker segregation, CI command>     {only when the repo has none to adopt}
```

**Coverage Assessment:**

```markdown
## Rust Test Coverage Assessment

<header block>

**Coverage gaps:**

- **Unit:** [services / validators / mappers without coverage; invariants without a property test]
- **Handler:** [endpoints without tests; missing 401/403/other-owner/validation]
- **Integration:** [repositories with non-trivial queries without tests; SQLite for a Postgres app]
- **Auth:** [endpoints without authorization tests; missing JWT layer or webhook signature tests; `none - no auth surface`]
- **Job:** [job / consumer handlers without tests; jobs without idempotency / retry tests; `n/a` when Messaging is none]
- **Concurrency gaps:** [contended paths tested only on the current-thread runtime, or not at all]
- **Contract:** [OpenAPI / Pact without verification]
- **Infrastructure:** [Step 9 boxes that fail: no shared database server, Docker-backed tests never compiled, no coverage command or thresholds, `.sqlx/` data stale, doctests skipped, suite does not build]

**Findings:** [non-test defects met while reading, each `file:line`; `none` otherwise]

**Open decisions:** [questions the tests cannot settle - an unfixed contract, an expected status the code and docs disagree on; `none` otherwise]

**Residuals:** [prioritized work outside the requested scope; `none` otherwise]

**Recommended pyramid balance:** Unit {x}% / Handler + integration {y}% / E2E {z}%

**Prioritization:**     {when the Step 8 trigger fires}

1. **P1 - AuthN/Z:** [specific endpoints / flows missing 401/403/ownership]
2. **P2 - Data integrity:** [non-trivial queries / write paths without rollback / unguarded job side effects / concurrent paths without multi-thread tests]
3. **P3 - Business-critical:** [revenue, state machines, scheduled billing/notification jobs]
4. **P4 - High-churn:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pass-through handlers / simple CRUD]
```

**Test Scaffolds:** `## Rust Test Scaffolds`, the header block, then `**Prerequisites:**` (what the scaffolds assume - a `tests/common` bootstrap, the Docker segregation, a reachable `DATABASE_URL` or `.sqlx/` data, a dev-dependency feature (`tokio` `test-util`, `tower` `util`), a defect that stops the target being exercised at all (it does not build, it panics on setup) - a defect a test can observe follows Step 3's ignore-and-cite rule instead; `none` when the repo has it), then a file manifest (path, layer, `fns / cases`; a support file - a fake, `tests/common/mod.rs`, a `test_support` module - takes layer `support` and no count; Step 8 priority order when its trigger fired, else request order), then the scaffolds themselves, then `**Findings:**` (non-test defects met while scaffolding, each `file:line` - the ignored contract tests from Step 3, model-migration drift, an unmounted layer; `none` otherwise), then `**Open decisions:**` (as on the Strategy Doc; `none` otherwise), then `**Residuals:**` - prioritized work the request's scope excluded, named so it is not lost. Ready-to-run files using project conventions:

- Right test type (handler / integration / unit / job)
- Table-driven with `rstest` cases or a named `Vec<Case>` loop
- Factories over raw literals
- Handler: happy + 401 (when an auth surface exists) + 403 (when a role gate exists) + other-owner (for per-owner resources) + validation-error
- Repository: real Postgres; assertions against the production engine's semantics
- Jobs: idempotency + retry + max attempts when applicable
- Isolation per test; no `sleep`; clippy-clean (`cargo clippy --all-targets -- -D warnings`)
- **Verified before delivery.** Probe first (`cargo --version`, `docker info`, a reachable `DATABASE_URL`, and `.sqlx/` present when the query macros are used), then take the matching branch and state which:
  - Toolchain and a database present -> `cargo build --all-targets` plus `cargo test` (or `cargo nextest run` + `cargo test --doc`) including the Docker-backed tests (`-- --include-ignored`, or `--features integration`).
  - Toolchain present, database absent -> run everything that needs none, **and compile the rest anyway with `cargo test --no-run --all-targets`** (plus the integration feature when that is the gate; `#[ignore]` skips only at run time). Without that they ship never compiled - and they are the riskiest scaffolds, carrying data-layer error types and version-sensitive container APIs. Query macros with no `.sqlx/` data cannot compile here either: say so. Name the skipped files and cases.
  - **No Rust toolchain** -> the scaffolds cannot be compiled. Do a static pass (duplicate names in one test module, fake-vs-trait signature conformance, unused imports, missing dev-dependency features), then label the delivery **unverified: not compiled** and say what would verify it. Do not claim a scaffold compiles when nothing compiled it.
  - **A build repair needed before anything runs** (a stale `.sqlx/` regenerated with `cargo sqlx prepare -- --all-targets` while a database is reachable, a missing `test-util` / `util` feature) is in scope when it is the only thing between you and a real measurement - make it, and say what you changed. Repairing the build is not the same as changing the code under test.

**Strategy Doc:**

```markdown
## Rust Test Strategy

<header block>

**Objective:** [what this strategy achieves]

**Pyramid balance:** Unit {x}% / Handler + integration {y}% / E2E {z}% - [the risk that moved it off the default band]

**Tooling:** [what this project will use, per the header's Mock framework and Messaging]

**Database isolation:** <engine> via [#[sqlx::test] fresh database | cloned template database | transactional rollback | committed rows, serial - per Step 5's preference order]

**Concurrency:** multi-thread `#[tokio::test]` for contended paths; `cargo nextest` runs each test in its own process

**Prerequisites:**     {infrastructure that must exist before any test below can be written - list first, they gate the rest}

1. [e.g. `tests/common` bootstrap, Docker segregation, CI database service]

**Findings:**     {non-test defects met while reading, each `file:line`, and the existing tests the design collides with; `none` otherwise}

**Gaps to close (prioritized):**

1. [Highest risk - typically authorization or repository correctness]
2. ...

**Open decisions:**     {product or design questions the tests cannot settle - the expected status for a case the design leaves open - and the answer taken for any the user settled; `none` otherwise}

**Residuals:**     {prioritized work outside the requested scope; `none` otherwise}

**Verification:** [the branch Step 8 / the scaffold probe took, and what remains unverified]
```

## Self-Check

Mark a line N/A with its reason when the routing table did not select that deliverable, or when the request's scope excludes it - an N/A line still names what was left undone.

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: Rust confirmed (else stopped), workspace member named; versions, data access, DB error type, messaging, mock and test framework recorded in the header block
- [ ] Step 3: code under test + existing tests + setup files read directly; absent ones named; contract-vs-defect tests ignored with the defect cited
- [ ] Step 4: pyramid stated as three numbers with Property, Job and Contract placed in their bands
- [ ] Step 5: `rust-testing-patterns` applied; every API name adapted to the detected stack (framework, data-layer error type, transaction injection, queue client); the two stated overrides (custom-rule validator tests, real-worker await) applied as written; a shared container hands out its URL, never a pool
- [ ] Step 6: boundaries defined - each layer covers what it does best, no duplicated assertions; handler cases include 401 when an auth surface exists, 403 when gated, other-owner for per-owner resources, validation
- [ ] Step 7: factories over literals; shared via `tests/common` or `test_support` without a dev-dependency cycle
- [ ] Step 8: coverage number stated with its branch; P1-P5 run when the trigger fires, bands `not determinable` named; out-of-scope bands listed as residuals
- [ ] Step 9: hygiene boxes checked; failing ones listed under `Infrastructure` or `Prerequisites`
- [ ] Output: deliverables match the routing row; header block once; every emitted deliverable carries Findings, Open decisions and Residuals (`none` when empty; on a combined delivery a later document lists only what is new), Scaffolds also Prerequisites and the manifest; verification branch taken and stated, delivery labelled `unverified: not compiled` when nothing compiled it

## Avoid

- Scaffolding without reading existing tests + setup
- Chasing coverage % instead of prioritizing by risk
- Separate test function per case when table-driven would do
- Full E2E for what a handler test could cover; a bound server when `oneshot` is faster
- SQLite / in-memory DB for Postgres apps
- Handler tests on a hand-built `Router` without the layers production mounts
- Duplicating factories across test crates when `tests/common` can hold them
- Mocking auth layers to silence DTO failures
- Testing framework internals (Axum routing, stock `validator` attributes)
- In-process job tests for behaviour only the real worker exhibits (backoff, max attempts)
- `serde_json::Value` or `Box<dyn Any>` in mocks to silence type errors
- `tokio::time::sleep` to wait for async work, or concurrency tests left on the current-thread runtime
