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

# Go Test

Go-aware test strategy and scaffolding using table-driven tests, `httptest.NewRecorder` + `gin.New()`, Testcontainers-go for PostgreSQL repositories, `gomock` / `mockery`, Asynq test patterns, `go test -race`.

## When to Use

- Test strategy for a new Go/Gin service
- Test-coverage gap assessment across layers
- Scaffolding tests for under-covered handlers / services / repositories / auth
- Test pyramid review
- Adding boundary tests to happy-path-only tests

**Not for:** test failure debugging, general review (`task-go-review`).

## Workflow

### Step 1 - Stack and Data Access

Use skill: `stack-detect`. Accept pre-confirmed from parent.

Then record four things it does not emit as fields - read them off `go.mod`, the driver import, and the repository constructors yourself:

- **Data Access:** GORM | sqlx | database/sql | mixed (name both when mixed)
- **DB engine and driver:** the driver import settles it (`lib/pq` and `jackc/pgx` are both PostgreSQL, and they raise *different* error types - see Step 4). `stack-detect` returns `Database: unknown` from file detection alone; infer from the driver and say you inferred it
- **Messaging:** Asynq | Kafka | none
- **Mock Framework:** `gomock` (`go.uber.org/mock`) | `mockery`-generated | hand-written | **none present** - when none, propose function-field fakes rather than importing a framework the project has not chosen

Every one of these has a slot in the deliverable (see Output Format).

### Step 2 - Read Code Under Test + Existing Tests

Ground output in project conventions, not generic templates.

- Read each target's package top-to-bottom: exported functions / types, request/response types, middleware, transaction boundaries, external collaborators
- Glob `**/*_test.go` and read one existing handler test, one service / repository test, one Asynq task test, `TestMain` setup - learn layout, mocks, HTTP stubs, auth helpers
- Read `Makefile` / `taskfile` / CI for `go test -race ./...`, coverage flags, integration segregation (`-tags=integration`)
- Read `internal/testutil/*.go` for shared fixtures (Testcontainers init, fake JWT, factories)
- Read `cmd/api/main.go` for middleware order that handler tests must replicate

**Conventions are the default, not the ceiling.** Adopt the project's layout, naming, helper, and fixture conventions. Do not adopt a convention this skill's `Avoid` list names as a defect - a house style of `gin.Default()` in handler tests, mocked-away auth, or SQLite standing in for Postgres is the gap you were called to close, not the pattern to copy. Say which convention you are departing from and why.

If no existing tests, no `Makefile`/CI, or no `internal/testutil`: say which is absent and propose the convention explicitly rather than inventing it silently. Proposed conventions belong in the deliverable, not only in your reasoning.

If exactly one existing test embodies a pattern `Avoid` rejects: write the new tests correctly alongside it, name the redundancy, and recommend deleting the old one - do not rewrite files the request did not ask you to touch. Watch for same-package symbol collisions with the existing helpers (a second `stubService` will not compile).

### Step 3 - Go Test Pyramid

| Layer | Tooling | What belongs |
|-------|---------|--------------|
| Unit | `testing` + `gomock` / hand-written | Service logic, validators, mappers, pure functions |
| Integration | `testing` + Testcontainers Postgres + real GORM / sqlx | Repository queries, ORM constraints, DB invariants |
| Handler | `httptest.NewRecorder` + `gin.New()` | Routing, binding, validation, middleware |
| Job | Asynq in-process server or Testcontainers Redis + real worker | Task processor happy path, retry, idempotency |
| E2E | `httptest.NewServer` + Testcontainers (Postgres + Redis) | Critical journeys only |
| Contract | Pact / OpenAPI consumer-driven | API contract validation |

**Many** unit, **some** handler / integration, **few** E2E - default band ~70% / ~25% / ~5%. Shift up to 10 points from unit into handler+integration when the risk concentrates in DB semantics or endpoint authorization (container-only queries, per-tenant scoping, a wide endpoint surface); state the reason. Keep E2E at ~5% and never invert the shape. `go test -race ./...` on every CI run.

### Step 4 - Apply Go Test Patterns

Use skill: `go-testing-patterns` for canonical table-driven, fixtures, testcontainers, mocking, `synctest`. Notes below cover layer-specific or layout-specific items.

**This workflow's Output Format wins.** The atomic declares its own `## Test Strategy` envelope; take its patterns and discard its envelope - the deliverable is the one the routing table selected.

**Adapt every API name below to the stack recorded in Step 1.** The examples are written GORM-and-Asynq-first because that is the common pairing, not because the others are out of scope. Where a named construct does not exist in this project, use its equivalent and say so; where it has no equivalent, drop the check rather than manufacture a finding.

**Unit tests** (`*_test.go` colocated):

- One test function per public method; table-driven for outcomes (success, validation failure, external failure, edge)
- **No Gin context / DB** - if a unit needs them, it's misclassified
- Stub external HTTP via `httptest.NewServer`
- Interface mocks at service boundaries follow the `Mock Framework` recorded in Step 1: `gomock` (`mockgen -source=service.go -destination=mock_service/mock.go`) or `mockery` when the project already uses one; **function-field fakes when it uses neither** - do not add a mocking framework the project has not chosen
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
- Shared container needs `TestMain`, and a package may declare only one. Keep `TestMain` untagged (it also sets `gin.SetMode(gin.TestMode)`) and have it call `setupIntegration` / `teardownIntegration` hooks that are real under `//go:build integration` and no-ops without it
- Per-test isolation, in preference order: **transactional rollback** when the repository constructor accepts an interface the transaction satisfies (GORM `db.Begin()` + `tx.Rollback()` in `t.Cleanup`; sqlx `BeginTxx` where the constructor takes `sqlx.ExtContext`); **unique-per-test key prefix** (tenant, owner, or SKU) plus a `t.Cleanup` delete when it takes a concrete `*gorm.DB` / `*sqlx.DB`. Never edit production constructors just to inject a transaction
- One test per non-trivial query; assert SQL semantics (filter, sort, eager-load), not just "method returns something"
- N+1 detection: count queries via GORM `Logger: logger.Default.LogMode(logger.Info)`, or a `database/sql` driver wrapper / `otelsql` span count for sqlx - sqlx has no logger hook. Skip the check rather than fake it
- Constraint tests: insert violating data; assert the driver's real error type - **`lib/pq` raises `*pq.Error` with `Code pq.ErrorCode`; `jackc/pgx` raises `*pgconn.PgError` with `Code string`**. Both carry `23505` for unique violation; GORM additionally wraps it as `gorm.ErrDuplicatedKey`. Check the driver in `go.mod` before writing the assertion - the two do not typecheck against each other
- Container schema: run the project's migrations. If `migrations/` does not exist, inline the DDL, and name the drift risk explicitly - an inlined schema silently diverges from production

**DTO / validator:**

- `validator.New()` directly is faster than a full handler test, but **it will silently pass everything unless you set the tag name.** validator/v10 reads `validate:` tags; Gin registers its instance with `SetTagName("binding")`, so a DTO carrying only `binding:` tags has zero rules from validator's default view and `validate.Struct(req)` returns `nil` for every input - a green test asserting nothing. Set the tag name and assert the validator is live before using it:

```go
v := validator.New(validator.WithRequiredStructEnabled())
v.SetTagName("binding")                                    // match Gin's instance
require.Error(t, v.Struct(CreateInput{}), "validator is not reading `binding` tags")
```

- Edge cases: missing required, wrong types via `BindJSON`, out-of-range, custom validators. Worth writing even when every tag is stock - the rules are the request contract, and this is where they are covered exhaustively so the handler table can stay representative

**Asynq / Kafka jobs:**

- **In-process Asynq:** instantiate handler; invoke `handler.ProcessTask(ctx, task)` directly without a real worker. No Redis. Best for handler logic
- **Testcontainers Redis + real Asynq Server** for tests needing actual broker behavior (retry, `Timeout`, real `MaxRetry`)
- Idempotency: invoke twice with same payload; assert side effect happens once
- Retry: stub external to fail twice then succeed; assert task completes; assert retry count
- Archived / max-retries: stub to fail forever; assert task ends in `archived` without infinite loop
- Permanent failure: assert a malformed payload wraps `asynq.SkipRetry` rather than burning the retry budget

**Kafka (franz-go)** - the three checks above map, the APIs do not. Call the record handler directly (`consumer.handle(ctx, rec)`) for the in-process variant; `kfake` for the poll loop; Testcontainers Kafka when the test turns on real broker behavior. Substitutions: `asynq.MaxRetry` / archive -> a bounded retry wrapper plus a DLQ topic; `asynq.NewInspector` queue depth -> `kadm.Client.Lag`; dedup on `asynq.TaskID` -> an idempotency key carried in the record. Additionally assert offsets are **not** committed when the handler returned an error, and that a stale message `Version` does not overwrite newer state - the at-most-once and out-of-order losses have no Asynq analogue

**E2E:**

- Reserve for full-stack: auth flow end-to-end, commit + Asynq dispatch, scheduled task behavior
- `httptest.NewServer(engine)` + Testcontainers Postgres + Redis
- Avoid for what a handler test could cover

**Race detector:** `go test -race ./...` mandatory in CI for packages using goroutines / channels / mutexes / `sync`. ~2-10x slowdown; CI must catch it.

### Step 5 - Test Boundaries

**Unit:** services, mappers, validators, middleware in isolation, pure functions, domain rules, calculations, state-machine transitions, concurrent helpers

**Handler:** every endpoint - happy + 401 + 403 + 4xx validation; pagination contract; filtering / sorting / search; custom error middleware mapping

**Integration:** every repository method with non-trivial query (multi-column filter, join, eager-load via `Preload`, aggregate); ORM constraints (unique, check, FK ON DELETE); migration smoke test on clean DB

**Asynq / Kafka:** every task with retry, idempotency, or external side effects; workflows assert complete and aggregate; post-commit tasks assert they fire after parent commits. **Dual writes** (a DB commit plus a publish, neither transactional) assert the divergence case: the row commits, the publish fails, and the caller sees the failure - the test pins which side wins

**Does NOT need a test:** framework-provided behavior (Gin routing, middleware dispatch, default validator); generated boilerplate; trivial delegation (`service.Get(id) -> repository.Get(id)` with no logic)

### Step 6 - Test Data and Fixtures

- Factory functions (`NewTestOrder(opts ...func(*Order)) *Order`) over hand-rolled literals
- Share factories via `internal/testutil` **only when it does not import the package under test**. In-package tests (`package invoice`) that need a factory returning an `invoice.Invoice` cannot use a `testutil` that imports `invoice` - that is an import cycle. Then keep the factory package-local in `factories_test.go`; the sharing rule loses to the compiler
- Repository tests with Testcontainers: factories to insert; isolate per-test via transactional rollback or unique-per-test prefix
- Avoid mutating shared fixtures; `t.Cleanup` to rebuild
- Test data minimal - 100-row setups signal integration / load layer

### Step 7 - Prioritization (when coverage is low)

If coverage < ~50%, run this **before** scaffolding - determines _which_ tests first.

Establish the number in this order, and report which branch you took:

1. **Measured:** `go test -coverprofile=cover.out ./...` when the suite runs.
2. **Measured by enumeration:** zero `*_test.go` in the tree is 0%, a fact, not an estimate.
3. **Estimated:** when the suite cannot run (no Go toolchain, no Docker, broken build, missing generated mocks), take test lines over production lines, weighted per package, and show the arithmetic so the number is auditable. Label it an estimate.

When the request is scaffolding rather than assessment, the prioritization still runs - it decides file order - and lands in the deliverable's `Prioritization` slot.

A band whose evidence is unavailable is filled `not determinable - <reason>`, never dropped and never guessed: P4 needs `git log --since="3 months ago"`, which a tree with no VCS history cannot answer. Keep the 1-5 structure intact.

When the highest band points outside the requested scope (P1 names JWT middleware; the user asked for handler + repository), stay in scope and list the band's targets as named residuals. Do not silently widen the work, and do not silently drop the priority.

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

**Which output to produce.** Match the request against these rows top-down and take the first hit - the rows overlap, and the first match wins:

| Request | Deliverable |
| ------- | ----------- |
| "Write tests for X" / "scaffold" | Test Scaffolds |
| "What tests are missing?" / "review coverage" | Coverage Assessment |
| "Test strategy" / "test plan" | Strategy Doc |
| 2+ of the above asked for together | All matched, in this order, separated by `---`: Coverage Assessment -> Strategy Doc -> Test Scaffolds |
| Unclear | Strategy Doc |

Whatever the row, when coverage is under ~50% the Coverage Assessment is emitted **as well**, ahead of the others - it is the only deliverable with a `Prioritization` slot, and Step 7 is mandatory below that threshold. Emit the header block once at the top, then the documents in that order separated by `---`; do not repeat the header inside each.

**Every deliverable opens with this header block**, so the Step 1 records and the coverage number always have a home:

```markdown
**Stack:** Go <version> / Gin <version>

**Data Access:** GORM <version> | sqlx <version> | database/sql | mixed - <both, named>

**DB engine / driver:** PostgreSQL via lib/pq | PostgreSQL via jackc/pgx | ... _(say "inferred from driver" when no instruction file declared it)_

**Messaging:** Asynq | Kafka | none

**Mock framework:** gomock | mockery | hand-written | none present - proposing <what>

**Test framework:** <what the repo actually has; "none present - proposing <list>" when go.mod declares no test dependency>

**Coverage:** <n>% (measured | measured by enumeration | estimated - <method>)

**Auth in tests:** test-issued JWT | claims-injecting middleware - <which and why>

**Proposed conventions** _(only when the repo has none to adopt)_: <layout, fixtures, tag split, CI command>
```

**Coverage Assessment:**

```markdown
## Go Test Coverage Assessment

<header block>

**Coverage gaps:**

- **Unit:** [services / validators / mappers without coverage]
- **Handler:** [endpoints without tests; missing 401/403/validation]
- **Integration:** [repositories with non-trivial queries without tests; SQLite for Postgres app]
- **Auth:** [endpoints without authorization tests; missing JWT middleware tests]
- **Job:** [Asynq processors without tests; tasks without idempotency / retry tests]
- **Race-detector gaps:** [packages with goroutines / channels / mutexes without `-race`]
- **Contract:** [OpenAPI / Pact without verification]
- **Infrastructure:** [Step 8 hygiene boxes that fail: no `TestMain`, no `-race` in CI, no `//go:build integration` split, no coverage command or thresholds, mocks not regenerated, suite does not build]

**Recommended pyramid balance:** Unit [target] / Handler + integration [target] / E2E [target - keep small]

**Prioritization** _(include when coverage < ~50% or > 5 gaps)_:

1. **P1 - AuthN/Z:** [specific endpoints / flows missing 401/403/ownership]
2. **P2 - Data integrity:** [non-trivial queries / write paths without rollback / Asynq unguarded side effects / packages missing race coverage]
3. **P3 - Business-critical:** [revenue, state machines, scheduled billing/notification tasks]
4. **P4 - High-churn:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pass-through handlers / simple CRUD]
```

**Test Scaffolds:** the header block, then a file manifest (path, layer, test funcs / cases), then the scaffolds themselves, then `**Residuals:**` - prioritized work the request's scope excluded, named so it is not lost. Ready-to-run files using project conventions:

- Right test type (handler / integration / unit / job)
- Table-driven with `t.Run(tc.name, ...)`
- Factories over raw literals
- Handler: happy + 401 + 403 + validation-error
- Repository: Testcontainers; assertions against PostgreSQL semantics
- Auth: anonymous + wrong-role + correct-role
- Asynq: idempotency + retry + max-retries when applicable
- `t.Cleanup` for teardown
- `go test -race`-safe (no races in the fixture)
- **Verified before delivery.** Probe first (`go version`, `docker info`, and `go env CGO_ENABLED` plus a C compiler check if you intend `-race`), then take the matching branch and state which:
  - Toolchain and Docker present -> `go build ./...` plus `go test <packages>` including `-tags=integration`.
  - Toolchain present, Docker absent -> build and run everything except `-tags=integration`, **and type-check the tagged files anyway with `go vet -tags=integration ./...`**. Without that they ship never compiled - and they are the riskiest scaffolds, carrying driver-specific error types and version-sensitive container APIs. Name the skipped files and cases.
  - **No Go toolchain** -> the scaffolds cannot be compiled. Do a static pass (duplicate declarations across the package, build-tag symbol collisions, unused imports, fake-vs-interface conformance), then label the delivery **unverified: not compiled** and say what would verify it. Do not claim a scaffold compiles when nothing compiled it.
  - **`-race` needs cgo.** With `CGO_ENABLED=0` or no C compiler it cannot run on any branch. Run the suite without it and report the omission with its cause rather than dropping the requirement silently.
  - **A build repair needed before anything runs** (absent `go.sum`, missing generated mocks) is in scope when it is the only thing between you and a real measurement - make it, and say what you changed. Repairing the build is not the same as changing the code under test.

**Strategy Doc:**

```markdown
## Go Test Strategy

<header block>

**Objective:** [what this strategy achieves]

**Pyramid balance:** Unit {x}% / Handler + integration {y}% / E2E {z}% - [the risk that moved it off the default band]

**Tooling:** [what this project will use, per the header's Mock framework and Messaging]

**Database isolation:** Testcontainers <engine> + [transactional rollback | unique-per-test prefix, per Step 4's preference order]

**Concurrency:** `go test -race ./...` mandatory in CI; `t.Parallel()` for independent cases

**Prerequisites** _(infrastructure that must exist before any test below can be written - list first, they gate the rest)_:

1. [e.g. `internal/testutil` bootstrap, `//go:build integration` split, CI workflow]

**Gaps to close (prioritized):**

1. [Highest risk - typically authorization or repository correctness]
2. ...
```

## Self-Check

Mark a line N/A with its reason when the routing table did not select that deliverable, or when the request's scope excludes it - an N/A line still names what was left undone.

**Always:**

- [ ] `behavioral-principles` loaded
- [ ] Stack confirmed; data access, DB engine + driver, messaging, and mock framework all recorded and carried into the header block
- [ ] Code under test + existing tests + setup files read directly; absent ones named
- [ ] `go-testing-patterns` consulted; its patterns used, this skill's Output Format kept
- [ ] Every API name adapted to the detected stack (driver error type, tx injection, queue client) - no construct prescribed that the project does not have
- [ ] Auth testing approach explicit (test-issued JWT or claims-injecting middleware)
- [ ] Coverage number stated with its branch (measured / by enumeration / estimated + method)

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
- [ ] Verification branch taken and stated; skipped subset named; delivery labelled `unverified: not compiled` when no toolchain exists
- [ ] Residuals listed for prioritized work the request's scope excluded

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
