---
name: task-go-test
description: Go test strategy and scaffolding using table-driven tests, httptest for Gin handlers, Testcontainers PostgreSQL, gomock / mockery for interfaces, Asynq test patterns, and `go test -race` discipline. Use when designing a test plan, assessing coverage gaps, or scaffolding handler / service / repository / job tests. Stack-specific override of task-code-test, invoked when stack-detect resolves to Go / Gin.
agent: go-test-engineer
metadata:
  category: backend
  tags: [go, gin, testing, table-driven, httptest, testcontainers, gomock, asynq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, generate one test per acceptance criterion (use `// Satisfies: AC<N>` mapping or test-name suffix), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface coverage gaps as proposed amendments.

# Go Test

## Purpose

Go-aware test strategy and scaffolding using table-driven tests (the canonical Go pattern), `httptest.NewRecorder` + `gin.New()` for handler tests, Testcontainers-go for PostgreSQL repository tests, `gomock` / `mockery` for interface mocks, Asynq test patterns (in-process server vs Testcontainers Redis), and `go test -race` for concurrency safety. Replaces the generic backend test patterns with Go-specific guidance.

This workflow is the stack-specific delegate of `task-code-test` for Go. The core workflow's contract (output shape, prioritization rules) is preserved so callers see a stable shape.

## When to Use

- Designing a test strategy for a new Go/Gin service / package
- Assessing test coverage gaps across unit / integration / handler / job layers
- Scaffolding tests for under-covered handlers, services, repositories, or auth code
- Reviewing test pyramid balance for a Go app
- Adding boundary tests (validation, authorization, error paths) to existing happy-path tests

**Not for:**

- Test failure / panic debugging (use `task-go-debug`)
- General code review (use `task-code-review` / `task-go-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Confirm Stack and Detect Data-Access Mix

Use skill: `stack-detect` to confirm Go / Gin. If the detected stack is not Go, stop and tell the user to invoke `/task-code-test` instead.

Detect data access (GORM / sqlx / database/sql / mixed) and messaging (Asynq / Kafka / none). Detect mock framework (`gomock` from `go.uber.org/mock`, hand-written mocks, `mockery`-generated). Record `Data Access`, `Messaging`, `Mock Framework` for the output.

### Step 2 - Read the Code Under Test and Existing Tests

Before producing assessment, scaffolds, or strategy, open both the production code in scope and a representative sample of existing tests. This grounds the output in real conventions instead of generic templates.

- For each target named by the user, read the package top-to-bottom: exported functions / types, request / response types, middleware, transaction boundaries, external collaborators
- Glob `**/*_test.go` and read at least: one existing handler test, one existing service / repository test, one existing Asynq task test (if applicable), `TestMain` setup files - learn the project's test layout, mock strategy (`gomock` vs hand-written), HTTP-stub library (`httpmock` vs `httptest.NewServer`), authentication helpers
- Read `Makefile` / `taskfile` / CI config for `go test -race ./...`, coverage flags, integration-test segregation (`-tags=integration`)
- Read `internal/testutil/*.go` (or equivalent) for shared fixtures (Testcontainers init, fake JWT generator, factory utilities)
- Read `cmd/api/main.go` for middleware order that handler tests must replicate (auth, recovery, error handler)

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc rather than inventing them silently.

### Step 3 - Go Test Pyramid

The Go test pyramid maps to test types:

| Layer       | Tooling                                                         | What belongs here                                                              |
| ----------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Unit        | `testing` package + `gomock` / hand-written mocks               | Service business logic, validators, mappers, pure functions, calculation rules |
| Integration | `testing` + Testcontainers PostgreSQL + real GORM / sqlx client | Repository queries, ORM constraints, DB-level invariants                       |
| Handler     | `httptest.NewRecorder` + `gin.New()` with real handler          | Routing, request / response binding, validation, middleware                    |
| Job         | Asynq in-process server or Testcontainers Redis + real worker   | Asynq task processor happy path, retry logic, idempotency                      |
| E2E         | `httptest.NewServer` + Testcontainers (Postgres + Redis)        | Critical user journeys only - signup, checkout, payment                        |
| Contract    | Pact / OpenAPI consumer-driven                                  | API contract validation against schema                                         |

**Many** unit tests, **some** handler / integration tests, **few** full E2E tests. `go test -race ./...` on every CI run.

### Step 4 - Apply Go Test Patterns

Use skill: `go-testing-patterns` for the canonical patterns referenced below.

**Table-driven tests (the canonical Go form, all layers):**

```go
func TestPlaceOrder(t *testing.T) {
    tests := []struct {
        name    string
        input   PlaceOrderInput
        setup   func(repo *mock_repo.MockOrderRepository)
        wantErr error
    }{
        {name: "happy path", input: validInput, setup: ..., wantErr: nil},
        {name: "validation error", input: badInput, setup: nil, wantErr: ErrValidation},
        {name: "repo failure", input: validInput, setup: ..., wantErr: ErrRepo},
    }
    for _, tc := range tests {
        t.Run(tc.name, func(t *testing.T) {
            // setup, exercise, assert
        })
    }
}
```

`t.Run(tc.name, ...)` so failures cite the case name. `t.Parallel()` only when test cases are independent and side-effect-free.

**Unit tests (`*_test.go` colocated):**

- Standard `testing` package; one test function per public method, with table-driven cases for outcomes (success, validation failure, external failure, edge case)
- **No Gin context / DB** - if a unit test needs `gin.New()` or a DB, it is misclassified
- Stub external HTTP via `httptest.NewServer` returning canned responses; do not stub repositories with full SQL behavior - use Testcontainers for that
- `gomock` for interface mocks at service boundaries; generate via `mockgen -source=service.go -destination=mock_service/mock.go`
- `t.Cleanup(func() { ... })` for teardown - cleaner than `defer` inside the test body
- Use `testify/assert` and `testify/require` for clarity (`require` halts on failure, `assert` continues)

**Gin handler tests:**

- Build a real `gin.New()` engine in the test (not `gin.Default()` - avoid the default logging middleware noise); apply the same global middleware as production (recovery, request-id, error handler, auth)
- `w := httptest.NewRecorder(); req, _ := http.NewRequest("POST", "/orders", bytes.NewReader(body)); engine.ServeHTTP(w, req); assert.Equal(t, 201, w.Code)`
- One test per `(method, path, principal-state, outcome)` triple
- Authentication via JWT middleware that reads a test-issued token, OR a test-only middleware that injects fixed claims into `c.Set("claims", ...)`
- Authorization: a separate test for "anonymous → 401" and "wrong role → 403" per protected endpoint
- Validation: a "rejects invalid payload" test for any endpoint with a DTO body
- Response shape: assert key fields, status, headers, and `Content-Type`
- DB: override the GORM / sqlx instance to point at the Testcontainers connection; transactional rollback per test (see Repository tests below)

**Repository / ORM integration tests:**

- Testcontainers PostgreSQL via `testcontainers-go` - **not SQLite, not in-memory** - SQLite diverges from PostgreSQL on JSON / JSONB, partial indexes, window functions, `ON CONFLICT`, array types, `LATERAL` joins
- Shared container per test suite via `TestMain`, not per-test container creation - container startup is ~3-5s, multiplied across tests it dominates suite runtime
- Per-test transactional rollback via fixture: GORM `db.Begin()` at test start, `tx.Rollback()` at end (`t.Cleanup`); pass `tx` to the repository constructor
- One test per non-trivial query: assert SQL semantics (filter correctness, sort order, eager-load result), not just "method returns something"
- N+1 detection: enable GORM `Logger: logger.Default.LogMode(logger.Info)` in test setup and count queries via a custom logger that increments a counter
- Custom indexes / constraints: insert violating data and assert the right error is raised (`pgconn.PgError` with `Code: "23505"` for unique violation; GORM wraps as `gorm.ErrDuplicatedKey`)

**DTO / validator tests:**

- Use `validator.New()` directly: `err := validate.Struct(req)` - faster than going through a full handler test
- Edge cases: missing required fields, wrong types via `BindJSON` (test against the actual binding pipeline for the conversion layer), out-of-range values, custom validators

**Asynq / Kafka job tests:**

- **In-process Asynq for fast tests**: Asynq's `inspect` package + a manually-instantiated handler; invoke `handler.ProcessTask(ctx, task)` directly without running a real worker. No Redis. Best for handler logic.
- **Testcontainers Redis + real Asynq Server** for tests that need actual broker behavior (retry, `Timeout`, real `MaxRetry`)
- Idempotency test: invoke the processor twice with the same payload, assert side effect happens once
- Retry test: stub the external call to fail twice then succeed; assert task completes; assert retry count
- Archived / max-retries test: stub the external call to fail forever; assert task ends in `archived` state without infinite loop
- For Kafka (franz-go): use `kfake` (the in-process fake broker from franz-go) for unit tests; Testcontainers Kafka for integration

**E2E / full-context tests:**

- Reserve for tests that genuinely need the full stack: auth flow end-to-end, transactional commit + Asynq dispatch, scheduled-task behavior
- Use `httptest.NewServer(engine)` over the real `*gin.Engine` so the test makes actual HTTP calls; pair with Testcontainers Postgres + Redis
- Avoid for tests that a handler test could cover - context-load cost compounds

**Race detector:**

- `go test -race ./...` mandatory in CI for any package that uses goroutines, channels, mutexes, or `sync` primitives
- Race detector slows tests ~2-10x; some teams run race-disabled in dev and race-enabled in CI - acceptable, but the CI run must catch it

### Step 5 - Test Boundaries (Go-Specific)

**What deserves a unit test:**

- Service logic, mappers, validators, custom middleware (the middleware function in isolation), pure functions / utilities
- Domain rules, calculation, state-machine transitions
- Concurrent helpers (worker pool, errgroup wrapper) tested with `go test -race`

**What deserves a handler test:**

- Every endpoint: happy path + 401 + 403 + 4xx validation
- Pagination contract (`limit` / `offset` / cursor)
- Filtering / sorting / search query params
- Custom error middleware mapping domain errors → HTTP status

**What deserves an integration / Testcontainers test:**

- Every repository method with a non-trivial query (filter on multiple columns, join, eager-load via `Preload`, aggregate)
- ORM constraints (unique, check, FK ON DELETE behavior)
- Migration smoke test: apply all migrations on a clean Testcontainers DB; useful when migrations are squashed

**What deserves an Asynq / Kafka test:**

- Every task with retry logic, idempotency requirements, or external side effects
- Task chains / workflows - assert the workflow completes and aggregates correctly
- Tasks dispatched via post-commit pattern - assert they fire after the parent commits, not before

**What does NOT need a test:**

- Framework-provided behavior: Gin routing resolution, middleware dispatch, default validator engine (test that you wired things correctly via handler tests, not that the framework works)
- Generated boilerplate: DTOs with no logic, getters returning a single field
- Trivial delegation: `service.Get(id) -> repository.Get(id)` with no logic

### Step 6 - Test Data and Fixtures

- Prefer factory functions (`NewTestOrder(opts ...func(*Order)) *Order`) over hand-rolled struct literals; configure factories per project convention
- For repository tests with Testcontainers, use factories to insert; isolate per-test data inside the test (transactional rollback) or use a unique-per-test prefix
- Avoid mutating shared test fixtures - use `t.Cleanup` to rebuild
- Test data must be minimal and focused - 100-row `for i := 0; i < 100; i++` setups signal the test belongs at integration / load-test layer

### Step 7 - Prioritization (when coverage is low)

If line coverage (or your equivalent project signal) is below ~50%, **run this step before scaffolding** - it determines _which_ tests to scaffold first. Scaffolding alphabetically or by file is wrong when authorization holes go untested while plumbing endpoints get full coverage.

When starting from low test coverage, prioritize by Go-specific risk:

**Priority 1 - Authorization and authentication:**

- Handler test per protected endpoint asserting 401 anonymous + 403 wrong-role
- JWT middleware tests covering issuer, audience, signature, expiry validation
- Custom auth middleware unit-tested

**Priority 2 - Data integrity:**

- Repository / ORM integration tests for every non-trivial query
- Service tests for write operations (one happy path + one rollback per write)
- Asynq task idempotency for any task with side effects
- `go test -race ./...` for any concurrent code path

**Priority 3 - Business-critical flows:**

- Revenue paths (checkout, billing, subscription state transitions)
- State-machine transitions (often modeled as enums in Go)
- Scheduled tasks touching billing or notifications

**Priority 4 - High-churn code:**

- Files with frequent recent commits (`git log --since="3 months ago"`)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pass-through handlers, simple CRUD - lower risk, can wait

### Step 8 - Test Infrastructure Hygiene

- [ ] Testcontainers reused across tests via `TestMain` and `testcontainers.Reuse` (set via `~/.testcontainers.properties` `testcontainers.reuse.enable=true` for local fast cycles)
- [ ] `go test -race ./...` runs in CI for at least the packages with concurrent code
- [ ] Test profile only overrides what differs from prod - never silently disables auth middleware
- [ ] Integration tests separated via `//go:build integration` build tag (`go test -tags=integration ./...`) so the unit suite stays fast
- [ ] HTTP stubs via `httptest.NewServer` returning canned responses; never real network calls in CI
- [ ] `t.Cleanup` for teardown over `defer` inside test body - more robust on test failure
- [ ] Coverage via `go test -coverprofile=cover.out ./... && go tool cover -html=cover.out` wired to CI with per-package thresholds; coverage exclusions documented
- [ ] No data races in CI race-detector runs - new races block merge
- [ ] `gomock` mocks regenerated when interfaces change (CI check via `go generate ./... && git diff --exit-code`)

## Go Review Checklist

Quick-reference checklist for reviewing existing Go tests:

- [ ] Test type matches what is being tested (handler -> `httptest` + `gin.New()`, repository -> Testcontainers, service -> unit + mocks)
- [ ] Tests are table-driven, not copy-pasted
- [ ] Every endpoint has at least happy + 401 + 403 + validation-error
- [ ] Every non-trivial repository query has an integration test against Testcontainers (not SQLite)
- [ ] Every custom middleware has a passing-and-denied test
- [ ] Test data created via factories, not raw struct literals
- [ ] No `repository.Save = ...` mocks when an integration test could assert real DB state
- [ ] No full-stack E2E tests for what a handler test could cover
- [ ] No in-process Asynq mock masking at-least-once / retry semantics on critical tasks
- [ ] `go test -race ./...` clean in CI
- [ ] No `interface{}` / `any` on mocked methods - use the generated `gomock` types

## Output Format

**Which output to produce:**

- User asks "what tests are missing?" or "review our test coverage" -> Coverage Assessment
- User asks "write tests for X" or "scaffold tests" -> Test Scaffolds
- User asks "test strategy", "test plan", or coverage is below 50% with no scaffolds requested -> Strategy Doc (optionally include Coverage Assessment)
- User asks for **two or more deliverables in the same invocation** ("review coverage AND scaffold tests", "what's missing and write the tests") -> produce them in this order, separated by a horizontal rule (`---`): Coverage Assessment, then Strategy Doc (if requested), then Test Scaffolds. Do not silently drop one.
- If unclear, produce Strategy Doc as the default.

**Coverage Assessment:**

```markdown
## Go Test Coverage Assessment

**Stack:** Go <version> / Gin <version>
**Data Access:** GORM <version> | sqlx <version> | database/sql | mixed
**Messaging:** Asynq | Kafka | none
**Test framework:** `testing` + table-driven, `httptest`, Testcontainers, gomock
**Coverage gaps:**

- **Unit tests:** [services / validators / mappers without test coverage]
- **Handler tests:** [endpoints without tests; endpoints missing 401/403/validation paths]
- **Integration tests:** [repositories with non-trivial queries without tests; tests running on SQLite for a Postgres app]
- **Auth tests:** [endpoints without authorization tests; missing JWT middleware tests]
- **Job tests:** [Asynq processors without tests; tasks without idempotency / retry tests]
- **Race-detector gaps:** [packages with goroutines / channels / mutexes not covered by `go test -race`]
- **Contract tests:** [OpenAPI / Pact contracts without verification]

**Recommended pyramid balance:**

- Unit (services, validators, helpers): [count target]
- Handler + integration (httptest + Testcontainers): [count target]
- E2E (full stack with Asynq / Redis): [count target - keep small]

**Prioritization** _(include when current coverage is below ~50% or the assessment surfaces > 5 gaps)_

Apply the Step 7 risk bands. Order follow-up work as:

1. **P1 - Authorization & authentication:** [list specific endpoints / flows missing 401/403/ownership tests]
2. **P2 - Data integrity:** [repositories with non-trivial queries / write paths without rollback tests / Asynq tasks with unguarded side effects / packages missing race-detector coverage]
3. **P3 - Business-critical flows:** [revenue, state machines, scheduled tasks touching billing or notifications]
4. **P4 - High-churn code:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pass-through handlers / simple CRUD - lowest risk]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run Go test files using project conventions. Each scaffold must include:

- The right test type (handler / integration / unit / job)
- Table-driven structure with `t.Run(tc.name, ...)`
- Factories for test data instead of raw struct literals
- For handler tests: happy path + 401 + 403 + validation-error
- For repository tests: Testcontainers PostgreSQL; assertions against PostgreSQL semantics
- For auth tests: anonymous + wrong-role + correct-role cases
- For Asynq tests: idempotency + retry + max-retries cases when applicable
- `t.Cleanup` for teardown
- `go test -race`-safe (no data races introduced by the test fixture)

**Strategy Doc** (when designing a test strategy):

```markdown
## Go Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Handler + Integration {y}% / E2E {z}%
**Tooling:** `testing` + table-driven, `httptest`, Testcontainers PostgreSQL, gomock, `go test -race`, Asynq in-process + real-broker integration
**Database isolation:** Testcontainers PostgreSQL + per-test transactional rollback (GORM `db.Begin()` + `tx.Rollback()` in `t.Cleanup`)
**Concurrency:** `go test -race ./...` mandatory in CI; `t.Parallel()` for test cases that are independent
**Gaps to close (prioritized):**

1. [Highest risk gap - typically authorization or repository correctness]
2. [...]
```

## Self-Check

**Always (any deliverable):**

- [ ] Stack confirmed as Go / Gin; data-access mix and messaging recorded before any framework-specific guidance applied (Step 1)
- [ ] Code under test and a representative sample of existing tests + setup files read directly so output matches project conventions (Step 2)
- [ ] `go-testing-patterns` consulted for canonical Go test patterns
- [ ] Auth testing approach explicit (test-issued JWT or test-only middleware injecting claims)
- [ ] Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage from plan.md, no out-of-scope tests)

**Strategy Doc / Coverage Assessment only:**

- [ ] Test pyramid mapped to Go idioms (unit -> `testing` + mocks; handler -> `httptest` + `gin.New()`; integration -> Testcontainers; Asynq -> in-process + real-broker for non-trivial cases)
- [ ] Boundaries clearly defined: each layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization by risk applied when coverage is low - P1 authorization, P2 data integrity, P3 business-critical, P4 high-churn, P5 plumbing
- [ ] Testcontainers used for repository and full-context tests; SQLite flagged as a smell for production-Postgres apps
- [ ] `go test -race ./...` CI presence flagged when packages with concurrent code lack race coverage

**Test Scaffolds only:**

- [ ] Tests are table-driven, not copy-pasted per case
- [ ] Test data created via factory functions, not raw struct literals; typed factory return shapes
- [ ] Handler scaffolds include happy path + 401 + 403 + validation-error; IDOR test for any per-owner / per-tenant resource
- [ ] Handler scaffolds apply same global middleware as `cmd/api/main.go` (missing auth middleware masks authorization bugs)
- [ ] Repository scaffolds run against Testcontainers PostgreSQL with per-test cleanup - never SQLite for Postgres apps
- [ ] Asynq scaffolds include idempotency + retry; real-broker (Testcontainers Redis) variant present for tasks with non-trivial `MaxRetry` / `Timeout`
- [ ] `t.Cleanup` (not `defer` in test body) for teardown
- [ ] Validator unit tests scaffolded for any non-trivial DTO with custom struct tags

**Review-existing-tests mode only:**

- [ ] Review checklist items addressed for every test file in scope

## Avoid

- Scaffolding tests without first reading existing tests + setup files - the result imports the wrong factory, uses the wrong HTTP-stub library, or duplicates the integration-test base fixture
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no auth tests misses the bigger threat
- Writing a separate test function per case when a table-driven test would do - copy-paste tests are harder to maintain and grow inconsistencies
- Full E2E tests (full Testcontainers + real broker) for what a handler test could cover - context cost compounds across the suite
- SQLite / in-memory DB in repository tests for apps that use PostgreSQL features (JSONB, partial indexes, `ON CONFLICT`, array types) - tests pass, prod fails
- Handler tests that build the Gin engine without applying the same global middleware as `cmd/api/main.go` - validation rules and auth differ between test and prod silently
- Writing handler tests with a real running server when `httptest.NewRecorder` + `engine.ServeHTTP(w, req)` is faster and more deterministic
- Duplicating factories per package - share via `internal/testutil/factories.go`
- Using `repository.Save = ...`-style internal mocks when a Testcontainers integration test could assert real DB state
- Mocking auth middleware to silence DTO failures - the test is now incorrect for the prod config
- Skipping validator unit tests because the handler has an integration test - validators are unit-tested separately so they can be reused
- Testing framework internals (e.g., that Gin routes match, that `validator` runs `required` tag) - test your wiring, not the framework
- Using in-process Asynq mocks as a substitute for a real-broker test on tasks with non-trivial `MaxRetry` / `Timeout` - the mock skips the broker and masks at-least-once / archived-task semantics
- Using `interface{}` / `any` to silence type errors in mocks - use generated `gomock` types or hand-written mocks with the right signature
- Skipping `go test -race ./...` for packages that use goroutines, channels, or `sync` primitives - the race is real, the test will eventually flake or break in prod
