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

# Go Test

Go-aware test strategy and scaffolding using table-driven tests, `httptest.NewRecorder` + `gin.New()`, Testcontainers-go for PostgreSQL repositories, `gomock` / `mockery`, Asynq test patterns, `go test -race`. Floors: Go 1.25+, testcontainers-go v0.35+, testify v1.10+ (per `go-testing-patterns`); read the Go version from the `go` directive and name the older form when a project sits below a floor.

## When to Use

- Test strategy for a new Go/Gin service, or for a feature whose design exists but whose code does not yet
- Test-coverage gap assessment across layers
- Scaffolding tests for under-covered handlers / services / repositories / auth
- Test pyramid review
- Adding boundary tests to happy-path-only tests

**Not for:** test failure debugging, general review (`task-go-review`).

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format (`go-testing-patterns`' `## Test Strategy`); they are rule sets here, and only this skill's Output Format is emitted, with one exception - the atomic's `Count` format (`funcs / cases`) governs every count this skill writes.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack and Data Access

Use skill: `stack-detect`. Accept pre-confirmed from parent. On a `go.work` tree with no root `go.mod`, the module under test is the stack (`stack-detect` finds no root `go.mod` and does not choose among the workspace's modules); name it in the header.

`stack-detect` emits `ORM` (from `gorm.io/gorm`), `Database` (from `jackc/pgx` or `go-sql-driver/mysql`; `lib/pq` is not in its driver list, so a `lib/pq` project reads `unknown` - infer PostgreSQL from the driver and say so), and `Test framework` (`testify` / `ginkgo` when required, else `testing (stdlib)`; the header composes `testing (stdlib) [+ testify <version> | ginkgo]`) - take those. Read the rest off `go.mod`, the driver import, and the repository constructors:

- **Versions:** Go from the `go` directive; the HTTP framework (Gin, or the substitute named in Step 5), GORM, sqlx, testify from the `require` lines - `stack-detect` emits none
- **Data Access:** GORM | sqlx | database/sql | mixed - GORM <v> + sqlx <v>
- **DB driver:** `lib/pq` and `jackc/pgx` are both PostgreSQL and raise *different* error types (Step 5)
- **Messaging:** Asynq | Kafka | Asynq + Kafka | none
- **Mock Framework:** `gomock` (`go.uber.org/mock`) | `mockery`-generated | hand-written (`testify/mock`, or function-field fakes already in the tree) | **none present** - when none, propose function-field fakes rather than importing a framework the project has not chosen. A `vendor/` tree blocks new dependencies: propose only what is already vendored, else function-field fakes

Every one of these has a slot in the header block (see Output Format).

### Step 3 - Read Code Under Test + Existing Tests

Ground output in project conventions, not generic templates.

- Read each target's package top-to-bottom: exported functions / types, request/response types, middleware, transaction boundaries, external collaborators
- Glob `**/*_test.go` and read one existing handler test, one service / repository test, one Asynq task test, `TestMain` setup - learn layout, mocks, HTTP stubs, auth helpers
- Read `Makefile` / `taskfile` / CI for `go test -race ./...`, coverage flags, integration segregation (`-tags=integration`)
- Read `internal/testutil/*.go` for shared fixtures (Testcontainers init, fake JWT, factories)
- Read `cmd/api/main.go` for the middleware order handler tests must replicate; a middleware production never mounts (an error mapper registered nowhere) is not replicated - assert the observable error and record the gap under `Findings`

**Conventions are the default, not the ceiling.** Adopt the project's layout, naming, helper, and fixture conventions. Do not adopt a convention this skill's `Avoid` list names as a defect - a house style of `gin.Default()` in handler tests, mocked-away auth, or SQLite standing in for Postgres is the gap you were called to close, not the pattern to copy. Say which convention you are departing from and why.

If no existing tests, no `Makefile`/CI, or no `internal/testutil`: say which is absent and propose the convention explicitly rather than inventing it silently. Proposed conventions belong in the deliverable, not only in your reasoning.

If exactly one existing test embodies a pattern `Avoid` rejects: write the new tests correctly alongside it, name the redundancy, and recommend deleting the old one - do not rewrite files the request did not ask you to touch. Watch for same-package symbol collisions with the existing helpers (a second `stubService` will not compile).

**A test that asserts the desired behaviour of a defect present today** (the code returns 500 where the contract says 404) is written against the contract and skipped with `t.Skip("defect: <file:line> - <what>")`, so the suite stays green and the defect stays visible; list it under `Findings`, as is an existing test the requested design collides with. A test that merely pins today's wrong behaviour is never written.

### Step 4 - Go Test Pyramid

| Layer | Tooling | What belongs |
|-------|---------|--------------|
| Unit | `testing` + `gomock` / hand-written | Service logic, validators, mappers, pure functions, `handler.ProcessTask` called directly |
| Integration | `testing` + Testcontainers Postgres + real GORM / sqlx | Repository queries, ORM constraints, DB invariants |
| Handler | `httptest.NewRecorder` + `gin.New()` | Routing, binding, validation, middleware |
| Job | Testcontainers Redis + real `asynq.Server` | Retry, `Timeout`, `MaxRetry`, archive - real broker behaviour |
| E2E | `httptest.NewServer` + Testcontainers (Postgres + Redis) | Critical journeys only |
| Contract | Pact / OpenAPI consumer-driven | API contract validation |

**Many** unit, **some** handler / integration, **few** E2E - default band ~70% / ~25% / ~5%, stated as three numbers. Job sits in the handler+integration band, Contract in the E2E band, in-process `ProcessTask` tests in unit. Shift up to 10 points from unit into handler+integration when the risk concentrates in DB semantics or endpoint authorization (container-only queries, per-tenant scoping, a wide endpoint surface); state the reason. Keep E2E at ~5% and never invert the shape. `go test -race ./...` on every CI run.

### Step 5 - Apply Go Test Patterns

Use skill: `go-testing-patterns` for canonical table-driven, fixtures, testcontainers, mocking, `synctest`. Notes below cover layer-specific or layout-specific items; where a note and the atomic disagree, the note says so and wins.

**Adapt every API name below to the stack recorded in Step 2.** The examples are written Gin-GORM-Asynq-first because that is the common pairing. Another HTTP framework substitutes by role (Echo: `echo.New()` + `httptest`, `c.Bind` for `ShouldBindJSON`); a construct with no equivalent (Gin `binding:` tags on Echo) is dropped rather than manufactured into a finding. Say what you substituted.

**Unit tests** (`*_test.go` colocated):

- One test function per public method; table-driven for outcomes (success, validation failure, external failure, edge)
- **No Gin context / DB** - if a unit needs them, it's misclassified
- Stub external HTTP via `httptest.NewServer`
- Interface mocks at service boundaries follow the `Mock Framework` recorded in Step 2: `gomock` (`mockgen -source=service.go -destination=mock_service/mock.go`), `mockery`, or the hand-written style already in the tree (`testify/mock` or function-field fakes); **propose function-field fakes when it is `none present`**
- `t.Cleanup` for teardown (not `defer`): it runs after the test and all its subtests, parallel ones included, and can be registered from helpers; a parent's `defer` fires before its parallel subtests run
- `testify/require` halts; `testify/assert` continues

**Gin handler tests:**

- Real `gin.New()` engine; apply the same global middleware production mounts (recovery, request-id, error handler, auth)
- `w := httptest.NewRecorder(); req := httptest.NewRequest(method, path, body); engine.ServeHTTP(w, req)`
- One test per `(method, path, principal-state, outcome)` triple
- Auth via test-issued JWT OR test-only middleware injecting fixed claims
- Authorization: "anonymous -> 401" per protected endpoint; "wrong role -> 403" when a role gate exists (N/A otherwise, said so); "another owner's / tenant's resource -> 404 or 403, whichever the contract fixes" for per-owner resources
- Validation: "rejects invalid payload" per DTO body
- Response shape: assert key fields, status, headers, `Content-Type`
- DB: override GORM / sqlx pointing at Testcontainers; per-test isolation per the Repository preference order below

**Repository / ORM integration:**

- Testcontainers PostgreSQL - **not SQLite, not in-memory**. SQLite has no arrays, `LATERAL`, `FOR UPDATE`, jsonb containment / existence operators (`@>`, `?`) or GIN indexes, or SQLSTATE error codes, and its typing and FK checks are loose by default (it does have partial indexes, window functions, and `ON CONFLICT` upsert)
- Shared container per **package** via `TestMain` (`go test` runs one binary per package; one container for the whole suite needs a CI-provided `TEST_DATABASE_URL`, per `go-testing-patterns`)
- A package declares one `TestMain`. **This layout wins over the atomic's tagged `TestMain`:** keep `TestMain` untagged (it also sets `gin.SetMode(gin.TestMode)`) and have it call `setupIntegration` / `teardownIntegration` hooks that are real in a `//go:build integration` file and no-ops in its `//go:build !integration` twin
- Per-test isolation, in preference order: **transactional rollback** when the constructor accepts the transaction - GORM's `db.Begin()` returns a `*gorm.DB`, so a constructor taking `*gorm.DB` already does (`tx.Rollback()` in `t.Cleanup`); sqlx needs a constructor taking `sqlx.ExtContext` for `BeginTxx`. A **per-test database cloned from a migrated template** (the atomic's parallel-safe alternative) when the constructor takes a concrete `*sqlx.DB` / `*sql.DB`; a test that must commit follows the atomic's committed-rows recipe (top-level, non-parallel, explicit cleanup). Never edit production constructors just to inject a transaction
- One test per non-trivial query; assert SQL semantics (filter, sort, eager-load), not just "method returns something"
- N+1 detection: count queries with a custom GORM `logger.Interface` whose `Trace` increments a counter, or a callback via `db.Callback().Query().After("gorm:query")`; for sqlx a `database/sql` driver wrapper or `otelsql` span count. `logger.Default.LogMode(logger.Info)` prints SQL and counts nothing. Skip the check rather than fake it
- Constraint tests: insert violating data; assert the driver's real error type - **`lib/pq` raises `*pq.Error` with `Code pq.ErrorCode`; `jackc/pgx` raises `*pgconn.PgError` with `Code string`**. Both carry `23505` for unique violation; GORM returns `gorm.ErrDuplicatedKey` only when opened with `gorm.Config{TranslateError: true}`. Check the driver and config before writing the assertion - the two drivers do not typecheck against each other
- Container schema: run the project's migrations. When a model has drifted from them, the test still runs the migrations and the drift is a `Findings` entry, not an inlined schema. If `migrations/` does not exist, inline the DDL and name the drift risk explicitly

**DTO / validator:**

- Validation is tested through the handler by default (`go-testing-patterns`). **This note wins for DTOs with custom tags:** a direct validator test using Gin's own engine covers custom rules exhaustively so the handler table stays representative. Stock-tag-only DTOs get no validator test - the handler's "rejects invalid payload" case covers them
- Use Gin's instance, never a fresh one: `v := binding.Validator.Engine().(*validator.Validate)`. Gin's is `validator.New()` + `SetTagName("binding")` without `WithRequiredStructEnabled`, and it carries the project's `RegisterValidation` customs once the registration function has run in the test binary - call it once in `TestMain` (or behind a `sync.Once` helper) before any test validates, since `RegisterValidation` is not thread-safe, or `Struct` panics `Undefined validation function`; a fresh `validator.New()` reads `validate:` tags, finds none on a `binding:`-tagged DTO, and passes everything

```go
v := binding.Validator.Engine().(*validator.Validate) // Gin's engine: binding tags + customs registered in this binary
require.Error(t, v.Struct(CreateInput{}), "validator is not reading `binding` tags")
```

**Asynq / Kafka jobs:**

- **In-process Asynq:** instantiate handler; invoke `handler.ProcessTask(ctx, task)` directly without a real worker. No Redis. Best for handler logic
- **Testcontainers Redis + real Asynq Server** for tests needing actual broker behavior (retry, `Timeout`, real `MaxRetry`). Set `asynq.Config{RetryDelayFunc: func(int, error, *asynq.Task) time.Duration { return 0 }}` and a short `DelayedTaskCheckInterval`, enqueue with `asynq.Retention(time.Minute)` (a succeeded task is otherwise deleted and `GetTaskInfo` returns `ErrTaskNotFound`), then await the terminal state via `Inspector.GetTaskInfo` under a `ctx` deadline - **this note wins over the atomic's no-poll rule** for real-broker tests (the default retry delay is 15s+)
- Idempotency: invoke twice with same payload; assert side effect happens once
- Retry: stub external to fail twice then succeed; assert task completes; assert retry count
- Archived / max-retries: stub to fail forever; assert task ends in `archived` without infinite loop
- Permanent failure: assert a malformed payload wraps `asynq.SkipRetry` rather than burning the retry budget

**Kafka (franz-go)** - the four checks above map, the APIs do not. Call the record handler directly (`consumer.handle(ctx, rec)`) for the in-process variant; `kfake` for the poll loop; Testcontainers Kafka when the test turns on real broker behavior. Substitutions: `asynq.MaxRetry` / archive -> a bounded retry wrapper plus a DLQ topic; `asynq.NewInspector` queue depth -> `kadm.Client.Lag`; dedup on `asynq.TaskID` -> an idempotency key carried in the record. Additionally assert offsets are **not** committed when the handler returned an error, and that a stale message `Version` does not overwrite newer state - the at-most-once and out-of-order losses have no Asynq analogue. With two brokers, each gets its own checks; a worker out of the request's scope is a named residual, not a scaffold.

**E2E:**

- Reserve for full-stack: auth flow end-to-end, commit + Asynq dispatch, scheduled task behavior
- `httptest.NewServer(engine)` + Testcontainers Postgres + Redis
- Avoid for what a handler test could cover

**Race detector:** `go test -race ./...` mandatory in CI for packages using goroutines / channels / mutexes / `sync`. 2-20x execution time and 5-10x memory; CI must absorb it.

### Step 6 - Test Boundaries

**Unit:** services, mappers, validators, middleware in isolation, pure functions, domain rules, calculations, state-machine transitions, concurrent helpers

**Handler:** every endpoint - happy + 401 (when an auth surface exists; `n/a` otherwise) + 403 (when a role gate exists) + other-owner + 4xx validation; pagination contract; filtering / sorting / search; custom error middleware mapping

**Integration:** every repository method with non-trivial query (multi-column filter, join, eager-load via `Preload`, aggregate); ORM constraints (unique, check, FK ON DELETE); migration smoke test on clean DB

**Asynq / Kafka:** every task with retry, idempotency, or external side effects; workflows assert complete and aggregate; post-commit tasks assert they fire after parent commits. **Dual writes** (a DB commit plus a publish, neither transactional) assert the divergence case: the row commits, the publish fails, and the caller sees the failure - the test pins which side wins

**Does NOT need a test:** framework-provided behavior (Gin routing, middleware dispatch, stock validator tags); generated boilerplate; trivial delegation (`service.Get(id) -> repository.Get(id)` with no logic)

### Step 7 - Test Data and Fixtures

- Factory functions (`NewTestOrder(opts ...func(*Order)) *Order`) over hand-rolled literals
- Share factories via `internal/testutil` **only when it does not import the package under test**. In-package tests (`package invoice`) that need a factory returning an `invoice.Invoice` cannot use a `testutil` that imports `invoice` - that is an import cycle. Then keep the factory package-local in `factories_test.go`; the sharing rule loses to the compiler
- Repository tests with Testcontainers: factories to insert; isolate per-test per Step 5's preference order
- Avoid mutating shared fixtures; `t.Cleanup` to rebuild
- Test data minimal - 100-row setups signal integration / load layer

### Step 8 - Coverage and Prioritization

**Establish the coverage number on every run** - the header's `Coverage` slot is unconditional. Take the first branch available and report which:

1. **Measured:** `go test -coverprofile=cover.out ./...` when the suite runs.
2. **Measured by enumeration:** zero `*_test.go` in the tree is 0%, a fact, not an estimate.
3. **Estimated:** when the suite cannot run (no Go toolchain, no Docker, broken build, missing generated mocks), take test lines over production lines, weighted per package, and show the arithmetic so the number is auditable. Label it an estimate.
4. **Not applicable:** the feature under plan has no code yet - write `n/a - not implemented` and key the strategy to the design's seams (handlers, repository methods, tasks it names), listing product questions the design leaves open under `Open decisions`.

**Run the P1-P5 prioritization when coverage is under ~50% or more than 5 gaps are found** - the one trigger set, used here and by the Output Format. Gaps are found gaps in existing code; a design's planned tests are not gaps, and a `n/a - not implemented` coverage does not fire it - on that branch the Strategy Doc's `Gaps to close` lists the planned tests in P1-P5 band order. It runs **before** scaffolding: the Coverage Assessment carries it in `Prioritization` and any accompanying Scaffolds manifest follows its order; when it does not fire, the manifest is in request order.

A band whose evidence is unavailable is filled `not determinable - <reason>`, never dropped and never guessed: P4 needs `git log --since="3 months ago"`, which a tree with no VCS history cannot answer; a history that exists but is empty for the window is `none - no commits in window`. Keep the 1-5 structure intact.

When the highest band points outside the requested scope (P1 names JWT middleware; the user asked for handler + repository), stay in scope and list the band's targets as named residuals. Do not silently widen the work, and do not silently drop the priority. A service with no auth surface at all writes P1 as `none - no auth surface` and the header's `Auth in tests` as `n/a - service has no auth`.

| Priority | Targets |
|----------|---------|
| P1 - AuthN/Z | Handler test per protected endpoint asserting 401 anonymous + 403 wrong-role + other-owner; JWT middleware tests (issuer, audience, signature, expiry); custom auth middleware unit tests |
| P2 - Data Integrity | Repository integration tests for non-trivial queries; service write-path tests (one happy + one rollback); Asynq idempotency; `go test -race ./...` for concurrent paths |
| P3 - Business-Critical | Revenue paths (checkout, billing, subscription states); state-machine transitions; scheduled tasks touching billing or notifications |
| P4 - High-Churn | Files with frequent recent commits (`git log --since="3 months ago"`); files with bug-fix history |
| P5 - Plumbing | Pass-through handlers, simple CRUD - lower risk, can wait |

**Multi-band rule.** When a target qualifies for multiple bands (refund Asynq processor is P2 + P3), file under highest (lowest number) and note secondary so the plan covers both axes.

### Step 9 - Test Infrastructure Hygiene

Failing boxes are listed under the Coverage Assessment's `Infrastructure` gap line or the Strategy Doc's `Prerequisites`.

- [ ] Testcontainers shared per package via `TestMain`; local reuse via `testcontainers.WithReuseByName(name)` (v0.37+; on v0.35-v0.36 `GenericContainerRequest{Reuse: true}` with a non-empty `Name`) - there is no `testcontainers.Reuse` symbol and no `testcontainers.reuse.enable` property in testcontainers-go
- [ ] `go test -race ./...` in CI for concurrent packages
- [ ] Test profile overrides only what differs from prod - never silently disables auth
- [ ] Integration tests segregated via `//go:build integration` (`go test -tags=integration ./...`)
- [ ] HTTP stubs via `httptest.NewServer`; never real network in CI
- [ ] **SDK clients bypassing `httptest.NewServer`** - it only intercepts when the system under test points at the server URL. Bypass surfaces: (a) `aws-sdk-go-v2` - override `BaseEndpoint` (`EndpointResolver` is deprecated); (b) `resty.New()` with a custom `*http.Transport` ignoring env proxy hooks; (c) `google.golang.org/grpc` - use `bufconn` for in-memory gRPC, NOT `httptest.NewServer` (HTTP/1 vs HTTP/2); (d) `cloud.google.com/go/storage` honours `STORAGE_EMULATOR_HOST` whenever it is set - the bypass is a test that never sets it. Verify with a stubbed test asserting the stub received the request (`server.URL` hit, request count > 0). "No calls were made" as green signal is the failure mode
- [ ] Coverage via `go test -coverprofile=cover.out ./... && go tool cover -html=cover.out`; per-package thresholds documented
- [ ] `gomock` mocks regenerated when interfaces change (`go generate ./... && git diff --exit-code`)

## Output Format

**Which output to produce.** Check the combined row first, then the single rows top-down:

| Request | Deliverable |
| ------- | ----------- |
| 2+ of the rows below asked for together | All matched, in this order, separated by `---`: Coverage Assessment -> Strategy Doc -> Test Scaffolds |
| "Write tests for X" / "scaffold" | Test Scaffolds |
| "What tests are missing?" / "review coverage" | Coverage Assessment |
| "Test strategy" / "test plan" | Strategy Doc |
| Unclear | Strategy Doc |

Whatever the row, when the Step 8 trigger fires (coverage under ~50% or more than 5 gaps) the Coverage Assessment is emitted **as well**, ahead of the others - it is the only deliverable with a `Prioritization` slot. Emit the header block once at the top, then the documents in that order separated by `---`; do not repeat the header inside each.

**Every deliverable opens with this header block**, so the Step 2 records and the coverage number always have a home:

```markdown
**Stack:** Go <version> / <framework> <version> - module <path>     {module suffix only on a go.work tree with no root go.mod}

**Data Access:** GORM <version> | sqlx <version> | database/sql | mixed - GORM <version> + sqlx <version>

**DB engine / driver:** PostgreSQL via lib/pq | PostgreSQL via jackc/pgx | MySQL via go-sql-driver | ... (inferred from driver)     {suffix only when no instruction file declared it}

**Messaging:** Asynq | Kafka | Asynq + Kafka | none

**Mock framework:** gomock | mockery | hand-written | none present - proposing <what>

**Test framework:** testing (stdlib) [+ testify <version> | ginkgo]     {append "- proposing <addition>" when one is needed and not vendored}

**Coverage:** <n>% (measured | measured by enumeration | estimated - <method>) | n/a - not implemented

**Auth in tests:** test-issued JWT | claims-injecting middleware | n/a - service has no auth

**Proposed conventions:** <layout, fixtures, tag split, CI command>     {only when the repo has none to adopt}
```

**Coverage Assessment:**

```markdown
## Go Test Coverage Assessment

<header block>

**Coverage gaps:**

- **Unit:** [services / validators / mappers without coverage]
- **Handler:** [endpoints without tests; missing 401/403/other-owner/validation]
- **Integration:** [repositories with non-trivial queries without tests; SQLite for Postgres app]
- **Auth:** [endpoints without authorization tests; missing JWT middleware tests; `none - no auth surface`]
- **Job:** [Asynq / Kafka handlers without tests; tasks without idempotency / retry tests; `n/a` when Messaging is none]
- **Race-detector gaps:** [packages with goroutines / channels / mutexes without `-race`]
- **Contract:** [OpenAPI / Pact without verification]
- **Infrastructure:** [Step 9 boxes that fail: no `TestMain`, no `-race` in CI, no `//go:build integration` split, no coverage command or thresholds, mocks not regenerated, suite does not build]

**Findings:** [non-test defects met while reading, each `file:line`; `none` otherwise]

**Open decisions:** [questions the tests cannot settle - an unfixed contract, an expected status the code and docs disagree on; `none` otherwise]

**Residuals:** [prioritized work outside the requested scope; `none` otherwise]

**Recommended pyramid balance:** Unit {x}% / Handler + integration {y}% / E2E {z}%

**Prioritization:**     {when the Step 8 trigger fires}

1. **P1 - AuthN/Z:** [specific endpoints / flows missing 401/403/ownership]
2. **P2 - Data integrity:** [non-trivial queries / write paths without rollback / Asynq unguarded side effects / packages missing race coverage]
3. **P3 - Business-critical:** [revenue, state machines, scheduled billing/notification tasks]
4. **P4 - High-churn:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pass-through handlers / simple CRUD]
```

**Test Scaffolds:** `## Go Test Scaffolds`, the header block, then `**Prerequisites:**` (what the scaffolds assume - a `testutil` bootstrap, the tag split, a migrated template, a defect that stops the target being exercised at all (it does not build, it panics on setup) or an untagged `TestMain` reshaped before an in-scope target can be tested - a defect a test can observe follows Step 3's skip-and-cite rule instead; `none` when the repo has it), then a file manifest (path, layer, `funcs / cases`; Step 8 priority order when its trigger fired, else request order), then the scaffolds themselves, then `**Findings:**` (non-test defects met while scaffolding, each `file:line` - the skipped contract tests from Step 3, model-migration drift, an unmounted middleware; `none` otherwise), then `**Open decisions:**` (as on the Strategy Doc; `none` otherwise), then `**Residuals:**` - prioritized work the request's scope excluded, named so it is not lost. Ready-to-run files using project conventions:

- Right test type (handler / integration / unit / job)
- Table-driven with `t.Run(tc.name, ...)`
- Factories over raw literals
- Handler: happy + 401 (when an auth surface exists) + 403 (when a role gate exists) + other-owner (for per-owner resources) + validation-error
- Repository: Testcontainers; assertions against the production engine's semantics
- Asynq: idempotency + retry + max-retries when applicable
- `t.Cleanup` for teardown; `go test -race`-safe (no races in the fixture)
- **Verified before delivery.** Probe first (`go version`, `docker info`, and `go env CGO_ENABLED` plus a C compiler check if you intend `-race`), then take the matching branch and state which:
  - Toolchain and Docker present -> `go build ./...` plus `go test <packages>` including `-tags=integration`.
  - Toolchain present, Docker absent -> build and run everything except `-tags=integration`, **and type-check the tagged files anyway with `go vet -tags=integration ./...`**. Without that they ship never compiled - and they are the riskiest scaffolds, carrying driver-specific error types and version-sensitive container APIs. Name the skipped files and cases.
  - **No Go toolchain** -> the scaffolds cannot be compiled. Do a static pass (duplicate declarations across the package, build-tag symbol collisions, unused imports, fake-vs-interface conformance), then label the delivery **unverified: not compiled** and say what would verify it. Do not claim a scaffold compiles when nothing compiled it.
  - **`-race` needs cgo except on macOS.** With `CGO_ENABLED=0` or no C compiler on Linux / Windows it cannot run on any branch. Run the suite without it and report the omission with its cause rather than dropping the requirement silently.
  - **A build repair needed before anything runs** (absent `go.sum`, missing generated mocks) is in scope when it is the only thing between you and a real measurement - make it, and say what you changed. Repairing the build is not the same as changing the code under test.

**Strategy Doc:**

```markdown
## Go Test Strategy

<header block>

**Objective:** [what this strategy achieves]

**Pyramid balance:** Unit {x}% / Handler + integration {y}% / E2E {z}% - [the risk that moved it off the default band]

**Tooling:** [what this project will use, per the header's Mock framework and Messaging]

**Database isolation:** Testcontainers <engine> + [transactional rollback | cloned template database (MySQL: schema-dump clone) | committed rows, top-level non-parallel - per Step 5's preference order]

**Concurrency:** `go test -race ./...` mandatory in CI; `t.Parallel()` for independent cases

**Prerequisites:**     {infrastructure that must exist before any test below can be written - list first, they gate the rest}

1. [e.g. `internal/testutil` bootstrap, `//go:build integration` split, CI workflow]

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

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed, module under test named on a workspace; versions, data access, driver, messaging, mock and test framework recorded in the header block
- [ ] Step 3: code under test + existing tests + setup files read directly; absent ones named; contract-vs-defect tests skipped with the defect cited
- [ ] Step 4: pyramid stated as three numbers with Job and Contract placed in their bands
- [ ] Step 5: `go-testing-patterns` applied; every API name adapted to the detected stack (framework, driver error type, tx injection, queue client); the three stated overrides (untagged `TestMain` hooks, custom-tag validator tests, real-broker await) applied as written
- [ ] Step 6: boundaries defined - each layer covers what it does best, no duplicated assertions; handler cases include 401 when an auth surface exists, 403 when gated, other-owner for per-owner resources, validation
- [ ] Step 7: factories over literals; shared via `testutil` only without an import cycle
- [ ] Step 8: coverage number stated with its branch; P1-P5 run when the trigger fires, bands `not determinable` named; out-of-scope bands listed as residuals
- [ ] Step 9: hygiene boxes checked; failing ones listed under `Infrastructure` or `Prerequisites`
- [ ] Output: routing row named; header block once; every emitted deliverable carries Findings, Open decisions and Residuals (`none` when empty), Scaffolds also Prerequisites and the manifest; verification branch taken and stated, delivery labelled `unverified: not compiled` when nothing compiled it

## Avoid

- Scaffolding without reading existing tests + setup
- Chasing coverage % instead of prioritizing by risk
- Separate test function per case when table-driven would do
- Full E2E for what a handler test could cover; real-server handler tests when `httptest.NewRecorder` is faster
- SQLite / in-memory DB for Postgres apps
- Handler tests without the global middleware production mounts
- Duplicating factories across packages when `internal/testutil` can hold them without an import cycle
- Mocking auth middleware to silence DTO failures
- Testing framework internals (Gin routes, stock validator tags)
- In-process Asynq tests for behaviour only the real broker exhibits (`MaxRetry`, `Timeout`)
- `interface{}` / `any` to silence type errors in mocks
- Skipping `go test -race ./...` for packages using goroutines / channels / `sync`
