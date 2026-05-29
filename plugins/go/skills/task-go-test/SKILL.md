---
name: task-go-test
description: Go / Gin test plan and scaffolding - table-driven, httptest, Testcontainers, gomock/mockery, Asynq, `go test -race` discipline.
agent: go-test-engineer
metadata:
  category: backend
  tags: [go, gin, testing, table-driven, httptest, testcontainers, gomock, asynq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` after `behavioral-principles`. Generate one test per AC (use `// Satisfies: AC<N>`), cover every NFR with a verification step from `plan.md`, refuse to generate tests for out-of-scope behavior. Never edit spec artifacts.

# Go Test

Go-aware test strategy and scaffolding using table-driven tests, `httptest.NewRecorder` + `gin.New()`, Testcontainers-go for PostgreSQL repositories, `gomock` / `mockery`, Asynq test patterns, `go test -race`.

## When to Use

- Test strategy for a new Go/Gin service
- Test-coverage gap assessment across layers
- Scaffolding tests for under-covered handlers / services / repositories / auth
- Test pyramid review
- Adding boundary tests to happy-path-only tests

**Not for:** test failure debugging (`task-go-debug`), general review (`task-go-review`), postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Stack and Data Access

Use skill: `stack-detect`. Accept pre-confirmed from parent. Record `Data Access`, `Messaging`, `Mock Framework` (`gomock` from `go.uber.org/mock`, hand-written, `mockery`-generated).

### Step 2 - Read Code Under Test + Existing Tests

Ground output in project conventions, not generic templates.

- Read each target's package top-to-bottom: exported functions / types, request/response types, middleware, transaction boundaries, external collaborators
- Glob `**/*_test.go` and read one existing handler test, one service / repository test, one Asynq task test, `TestMain` setup - learn layout, mocks, HTTP stubs, auth helpers
- Read `Makefile` / `taskfile` / CI for `go test -race ./...`, coverage flags, integration segregation (`-tags=integration`)
- Read `internal/testutil/*.go` for shared fixtures (Testcontainers init, fake JWT, factories)
- Read `cmd/api/main.go` for middleware order that handler tests must replicate

If no existing tests: say so and propose conventions explicitly rather than inventing them silently.

### Step 3 - Go Test Pyramid

| Layer | Tooling | What belongs |
|-------|---------|--------------|
| Unit | `testing` + `gomock` / hand-written | Service logic, validators, mappers, pure functions |
| Integration | `testing` + Testcontainers Postgres + real GORM / sqlx | Repository queries, ORM constraints, DB invariants |
| Handler | `httptest.NewRecorder` + `gin.New()` | Routing, binding, validation, middleware |
| Job | Asynq in-process server or Testcontainers Redis + real worker | Task processor happy path, retry, idempotency |
| E2E | `httptest.NewServer` + Testcontainers (Postgres + Redis) | Critical journeys only |
| Contract | Pact / OpenAPI consumer-driven | API contract validation |

**Many** unit, **some** handler / integration, **few** E2E. `go test -race ./...` on every CI run.

### Step 4 - Apply Go Test Patterns

Use skill: `go-testing-patterns` for canonical table-driven, fixtures, testcontainers, mocking, `synctest`. Notes below cover layer-specific or layout-specific items.

**Unit tests** (`*_test.go` colocated):

- One test function per public method; table-driven for outcomes (success, validation failure, external failure, edge)
- **No Gin context / DB** - if a unit needs them, it's misclassified
- Stub external HTTP via `httptest.NewServer`
- `gomock` for interface mocks at service boundaries; `mockgen -source=service.go -destination=mock_service/mock.go`
- `t.Cleanup` for teardown (not `defer`)
- `testify/require` halts; `testify/assert` continues

**Gin handler tests:**

- Real `gin.New()` engine; apply same global middleware as production (recovery, request-id, error handler, auth)
- `w := httptest.NewRecorder(); req := http.NewRequest(...); engine.ServeHTTP(w, req)`
- One test per `(method, path, principal-state, outcome)` triple
- Auth via test-issued JWT OR test-only middleware injecting fixed claims
- Authorization: separate "anonymous -> 401" and "wrong role -> 403" per protected endpoint
- Validation: "rejects invalid payload" per DTO body
- Response shape: assert key fields, status, headers, `Content-Type`
- DB: override GORM / sqlx pointing at Testcontainers; per-test transactional rollback

**Repository / ORM integration:**

- Testcontainers PostgreSQL - **not SQLite, not in-memory** (SQLite diverges on JSON / JSONB, partial indexes, window functions, `ON CONFLICT`, arrays, `LATERAL`)
- Shared container per suite via `TestMain` (startup ~3-5s)
- Per-test transactional rollback: GORM `db.Begin()` at start, `tx.Rollback()` in `t.Cleanup`; pass `tx` to repository constructor
- One test per non-trivial query; assert SQL semantics (filter, sort, eager-load), not just "method returns something"
- N+1 detection: enable GORM `Logger: logger.Default.LogMode(logger.Info)` in test setup; count queries
- Constraint tests: insert violating data; assert the right error (`pgconn.PgError.Code: "23505"` for unique; GORM wraps as `gorm.ErrDuplicatedKey`)

**DTO / validator:**

- `validator.New()` directly: `err := validate.Struct(req)` - faster than full handler test
- Edge cases: missing required, wrong types via `BindJSON`, out-of-range, custom validators

**Asynq / Kafka jobs:**

- **In-process Asynq:** instantiate handler; invoke `handler.ProcessTask(ctx, task)` directly without a real worker. No Redis. Best for handler logic
- **Testcontainers Redis + real Asynq Server** for tests needing actual broker behavior (retry, `Timeout`, real `MaxRetry`)
- Idempotency: invoke twice with same payload; assert side effect happens once
- Retry: stub external to fail twice then succeed; assert task completes; assert retry count
- Archived / max-retries: stub to fail forever; assert task ends in `archived` without infinite loop
- Kafka: `kfake` (in-process) for unit; Testcontainers Kafka for integration

**E2E:**

- Reserve for full-stack: auth flow end-to-end, commit + Asynq dispatch, scheduled task behavior
- `httptest.NewServer(engine)` + Testcontainers Postgres + Redis
- Avoid for what a handler test could cover

**Race detector:** `go test -race ./...` mandatory in CI for packages using goroutines / channels / mutexes / `sync`. ~2-10x slowdown; CI must catch it.

### Step 5 - Test Boundaries

**Unit:** services, mappers, validators, middleware in isolation, pure functions, domain rules, calculations, state-machine transitions, concurrent helpers

**Handler:** every endpoint - happy + 401 + 403 + 4xx validation; pagination contract; filtering / sorting / search; custom error middleware mapping

**Integration:** every repository method with non-trivial query (multi-column filter, join, eager-load via `Preload`, aggregate); ORM constraints (unique, check, FK ON DELETE); migration smoke test on clean DB

**Asynq / Kafka:** every task with retry, idempotency, or external side effects; workflows assert complete and aggregate; post-commit tasks assert they fire after parent commits

**Does NOT need a test:** framework-provided behavior (Gin routing, middleware dispatch, default validator); generated boilerplate; trivial delegation (`service.Get(id) -> repository.Get(id)` with no logic)

### Step 6 - Test Data and Fixtures

- Factory functions (`NewTestOrder(opts ...func(*Order)) *Order`) over hand-rolled literals
- Repository tests with Testcontainers: factories to insert; isolate per-test via transactional rollback or unique-per-test prefix
- Avoid mutating shared fixtures; `t.Cleanup` to rebuild
- Test data minimal - 100-row setups signal integration / load layer

### Step 7 - Prioritization (when coverage is low)

If coverage < ~50%, run this **before** scaffolding - determines _which_ tests first.

| Priority | Targets |
|----------|---------|
| P1 - AuthN/Z | Handler test per protected endpoint asserting 401 anonymous + 403 wrong-role; JWT middleware tests (issuer, audience, signature, expiry); custom auth middleware unit tests |
| P2 - Data Integrity | Repository integration tests for non-trivial queries; service write-path tests (one happy + one rollback); Asynq idempotency; `go test -race ./...` for concurrent paths |
| P3 - Business-Critical | Revenue paths (checkout, billing, subscription states); state-machine transitions; scheduled tasks touching billing or notifications |
| P4 - High-Churn | Files with frequent recent commits (`git log --since="3 months ago"`); files with bug-fix history |
| P5 - Plumbing | Pass-through handlers, simple CRUD - lower risk, can wait |

**Multi-band rule.** When a target qualifies for multiple bands (refund Asynq processor is P2 + P3), file under highest (lowest number) and note secondary so the plan covers both axes.

### Step 8 - Test Infrastructure Hygiene

- [ ] Testcontainers reused via `TestMain` + `testcontainers.Reuse` (`testcontainers.reuse.enable=true` local)
- [ ] `go test -race ./...` in CI for concurrent packages
- [ ] Test profile overrides only what differs from prod - never silently disables auth
- [ ] Integration tests segregated via `//go:build integration` (`go test -tags=integration ./...`)
- [ ] HTTP stubs via `httptest.NewServer`; never real network in CI
- [ ] **SDK clients bypassing `httptest.NewServer`** - only intercepts when system-under-test points at the server URL. Bypass surfaces: (a) `aws-sdk-go-v2` with baked-in endpoint resolver - override `EndpointResolver` / `BaseEndpoint`; (b) `resty.New()` with custom `*http.Transport` ignoring env proxy hooks; (c) `google.golang.org/grpc` - use `bufconn` for in-memory gRPC, NOT `httptest.NewServer` (HTTP/1 vs HTTP/2); (d) Google SDK reading `STORAGE_EMULATOR_HOST` only when explicitly enabled. Verify with a stubbed test asserting the stub received the request (`server.URL` hit, request count > 0). "No calls were made" as green signal is the failure mode
- [ ] `t.Cleanup` over `defer` (more robust on failure)
- [ ] Coverage via `go test -coverprofile=cover.out ./... && go tool cover -html=cover.out`; per-package thresholds documented
- [ ] No data races in CI
- [ ] `gomock` mocks regenerated when interfaces change (`go generate ./... && git diff --exit-code`)

## Output Format

**Which output to produce:**

- "What tests are missing?" -> Coverage Assessment
- "Write tests for X" / "scaffold" -> Test Scaffolds
- "Test strategy" / "test plan", OR coverage < 50% with no scaffolds requested -> Strategy Doc (optionally with Coverage Assessment)
- 2+ deliverables ("review coverage AND scaffold") -> in this order separated by `---`: Coverage Assessment -> Strategy Doc -> Test Scaffolds
- Unclear -> default to Strategy Doc

**Coverage Assessment:**

```markdown
## Go Test Coverage Assessment

**Stack:** Go <version> / Gin <version>
**Data Access:** GORM | sqlx | database/sql | mixed
**Messaging:** Asynq | Kafka | none
**Test framework:** `testing` + table-driven, `httptest`, Testcontainers, gomock
**Coverage gaps:**

- **Unit:** [services / validators / mappers without coverage]
- **Handler:** [endpoints without tests; missing 401/403/validation]
- **Integration:** [repositories with non-trivial queries without tests; SQLite for Postgres app]
- **Auth:** [endpoints without authorization tests; missing JWT middleware tests]
- **Job:** [Asynq processors without tests; tasks without idempotency / retry tests]
- **Race-detector gaps:** [packages with goroutines / channels / mutexes without `-race`]
- **Contract:** [OpenAPI / Pact without verification]

**Recommended pyramid balance:** Unit [target] / Handler + integration [target] / E2E [target - keep small]

**Prioritization** _(include when coverage < ~50% or > 5 gaps)_:

1. **P1 - AuthN/Z:** [specific endpoints / flows missing 401/403/ownership]
2. **P2 - Data integrity:** [non-trivial queries / write paths without rollback / Asynq unguarded side effects / packages missing race coverage]
3. **P3 - Business-critical:** [revenue, state machines, scheduled billing/notification tasks]
4. **P4 - High-churn:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pass-through handlers / simple CRUD]
```

**Test Scaffolds:** ready-to-run files using project conventions:

- Right test type (handler / integration / unit / job)
- Table-driven with `t.Run(tc.name, ...)`
- Factories over raw literals
- Handler: happy + 401 + 403 + validation-error
- Repository: Testcontainers; assertions against PostgreSQL semantics
- Auth: anonymous + wrong-role + correct-role
- Asynq: idempotency + retry + max-retries when applicable
- `t.Cleanup` for teardown
- `go test -race`-safe (no races in the fixture)

**Strategy Doc:**

```markdown
## Go Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Handler + integration {y}% / E2E {z}%
**Tooling:** `testing` + table-driven, `httptest`, Testcontainers Postgres, gomock, `go test -race`, Asynq in-process + real-broker
**Database isolation:** Testcontainers Postgres + per-test transactional rollback
**Concurrency:** `go test -race ./...` mandatory in CI; `t.Parallel()` for independent cases
**Gaps to close (prioritized):**

1. [Highest risk - typically authorization or repository correctness]
2. ...
```

## Self-Check

**Always:**

- [ ] Stack confirmed; data-access mix and messaging recorded
- [ ] Code under test + existing tests + setup files read directly
- [ ] `go-testing-patterns` consulted
- [ ] Auth testing approach explicit (test-issued JWT or claims-injecting middleware)
- [ ] Spec-aware mode honored when `--spec` was passed

**Strategy / Coverage:**

- [ ] Pyramid mapped to Go idioms (unit -> `testing` + mocks; handler -> `httptest` + `gin.New()`; integration -> Testcontainers; Asynq -> in-process + real-broker)
- [ ] Boundaries defined: each layer covers what it does best; no duplicated assertions
- [ ] Risk-based prioritization when coverage is low (P1 auth, P2 integrity, P3 business, P4 churn, P5 plumbing)
- [ ] Testcontainers used for repository / full-context; SQLite flagged for Postgres apps
- [ ] `-race` CI presence flagged when concurrent packages lack race coverage

**Scaffolds:**

- [ ] Table-driven, not copy-pasted
- [ ] Factories over raw literals
- [ ] Handler: happy + 401 + 403 + validation-error; IDOR for per-owner / per-tenant resources
- [ ] Handler applies same global middleware as `cmd/api/main.go`
- [ ] Repository runs against Testcontainers with per-test cleanup
- [ ] Asynq: idempotency + retry; real-broker variant for non-trivial `MaxRetry` / `Timeout`
- [ ] `t.Cleanup` (not `defer`)
- [ ] Validator unit tests for non-trivial DTOs with custom tags

## Avoid

- Scaffolding without reading existing tests + setup
- Chasing coverage % instead of prioritizing by risk
- Separate test function per case when table-driven would do
- Full E2E for what a handler test could cover
- SQLite / in-memory DB for Postgres apps
- Handler tests without same global middleware as `cmd/api/main.go`
- Real-server handler tests when `httptest.NewRecorder` is faster
- Duplicating factories per package (share via `internal/testutil/factories.go`)
- Mocking auth middleware to silence DTO failures
- Skipping validator unit tests because handler has an integration test
- Testing framework internals (Gin routes, validator `required`)
- In-process Asynq mocks for tasks with non-trivial `MaxRetry` / `Timeout`
- `interface{}` / `any` to silence type errors in mocks
- Skipping `go test -race ./...` for packages using goroutines / channels / `sync`
