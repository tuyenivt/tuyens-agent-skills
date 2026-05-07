---
name: task-go-refactor
description: Go refactor planning for fat Gin handlers, anemic services, god packages, goroutine leaks, missing context propagation, sync.Mutex held across I/O, GORM N+1, GORM hook abuse, mass assignment, package-level mutable state, single-implementation interfaces, and Asynq idempotency. Produces a step-by-step sequence of independently-committable refactoring steps with a `go test -race` coverage gate. Stack-specific override of task-code-refactor for Go.
agent: go-tech-lead
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Go Refactor

## Purpose

Produce a safe, step-by-step refactoring plan for a specific Go target (Gin handler, service, repository, GORM model, Asynq processor, DTO). Identifies Go-specific smells (fat handler, anemic services, god packages, goroutine without owner / cancellation, sync.Mutex held across I/O, GORM N+1, GORM hook abuse for business logic, mass assignment via `mapstructure.Decode`, package-level mutable state, single-impl interfaces violating "accept interfaces, return structs", `panic` in service code, Asynq tasks lacking idempotency) and proposes independently-committable refactoring steps with `go test -race` gates between each.

This workflow is the stack-specific delegate of `task-code-refactor` for Go.

## When to Use

- Go code-smell identification and resolution
- Go technical-debt reduction with a concrete plan
- Safe refactoring of a handler / service / repository / package / Asynq processor
- Pre-merge "this PR grew the fat-handler / god-service problem - what's the cleanup?"

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-go-implement`)
- Architecture-level restructuring across many packages (use `task-design-architecture`)
- Bug fixes / panic investigations (use `task-go-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                                                  |
| --------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Target scope          | Yes         | File or package to refactor (e.g., `internal/orders/handler.go`, `internal/orders/service.go`, `internal/worker/payment_processor.go`)                       |
| Goal                  | Yes         | What the refactoring should achieve (e.g., extract `PlaceOrder` service, kill GORM `AfterCreate` hook chain, split `OrdersService` god package)              |
| Test coverage status  | Recommended | Whether `*_test.go` / Testcontainers / Asynq coverage exists for the target area; whether `go test -race` is clean for the package                           |
| Shared/public surface | Recommended | Whether the target is used across package / module / team boundaries                                                                                         |

## Workflow

### Step 1 - Confirm Stack and Detect Data-Access Mix

Use skill: `stack-detect` to confirm Go / Gin. If invoked as a subagent of a Go-aware parent, accept the pre-confirmed stack. If the detected stack is not Go, stop and tell the user to invoke `/task-code-refactor` instead.

Detect data access (GORM / sqlx / database/sql / mixed) and messaging (Asynq / Kafka / none). Record `Data Access`, `Messaging` for the output.

### Step 2 - Read the Target

Read the actual file(s) named in the Inputs table before classifying smells. A refactor plan grounded in the user's prose summary instead of the source will hallucinate smells that aren't there and miss ones that are. Specifically:

1. Read the target file top-to-bottom; note function count, longest function, sync-vs-async signature mix (`error` returns, `context.Context` first param), transaction placement (`db.Transaction(...)`), every external collaborator (`http.Client`, `client.Enqueue` Asynq, mailers, GORM hooks).
2. Read the matching test file(s) (e.g., `service_test.go`, `handler_test.go`); count cases by outcome (happy path, validation failure, external failure, auth denial). Confirm `go test -race` runs clean (or note it doesn't).
3. If callers are obvious (handler calling the service, scheduled task calling the service), read the immediate caller too - removing or reshaping a public function without seeing call sites is how silent breakage happens.

If the user named only the goal without a target file / package, ask for the target before proceeding. Do not guess.

**Sibling-smell disposition.** Real targets live inside fat packages. If the file containing the target also contains other smells (e.g., the user names `CreateOrder` but the same handler file has IDOR in `GetOrder` and an `exec.Command("sh", "-c", userInput)` in `BulkImport`), do **not** action them in this plan and do **not** ignore them silently. List them under a `Sibling Smells (Out of Scope)` heading in the output, briefly state why each is deferred (separate target, separate severity, separate skill - e.g., security findings belong in `task-go-review-security`), and recommend follow-up invocations. This disambiguates "while we're here cleanup" (forbidden) from "name the deferred work for hand-off" (required).

### Step 3 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Identify the tests covering the target (`*_test.go`, integration tests against Testcontainers, Asynq processor tests), then assign one of three statuses with sharp boundaries:

| Status       | Definition                                                                                                                                   | What the workflow does                                                                                                                        |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** at least 2 boundary outcomes per public entry point (e.g., validation failure, auth denial, external failure, not-found) | Proceed to Step 4 normally                                                                                                                    |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                                                                                               | Proceed, but the plan **must** include a non-optional `Step 0 - Coverage prerequisite` adding the missing boundaries before any refactor step |
| `Inadequate` | No tests, or **happy-path-only** (success case alone)                                                                                        | **Refuse to produce Steps 1+.** The only output is the Coverage Gate verdict and a recommendation to run `task-go-test` first                 |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot tell you whether the refactor preserves validation, authorization, or error behavior - you would be flying blind.

**Race-detector check.** If the target package contains goroutines, channels, mutexes, or `sync` primitives, also confirm `go test -race ./<package>/...` is run in CI. If not, treat coverage status as one tier worse (Adequate → Thin, Thin → Inadequate) - refactoring concurrent code without race coverage is unsafe.

**Output of this step:** explicit coverage status using one of the three labels above. Do not proceed past Step 4 if status is `Inadequate`.

### Step 4 - Identify Go Smells

Inspect the target for these Go-specific smells. Use judgment - these are signals, not hard rules.

**Handler / Route smells:**

| Smell                                   | Signal                                                                                                                                                                                              | Risk   |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Handler                             | Handler > 30 lines of orchestration (multiple service calls, conditional dispatch, response shaping, business rules)                                                                                | High   |
| Logic in Handler                        | Business rules, validation beyond `ShouldBindJSON` + struct tags, calculation, or domain decisions inside the handler                                                                               | High   |
| Direct Repository / GORM in Handler     | Handlers call `db.Find(...)` directly, bypassing the service layer                                                                                                                                  | Medium |
| ORM Model Returned from Handler         | Handler returns `*model.Order` directly via `c.JSON(...)` without mapping (mass-assignment + lazy-load risk on serialization, leaks GORM tags / soft-delete columns / internal fields)              | High   |
| Manual Validation Duplicating Tags      | Handler body re-checks `len(req.Name) > 0` constraints already on the validator struct tag                                                                                                          | Low    |
| `BindJSON` (vs `ShouldBindJSON`)        | `BindJSON` writes 400 directly and returns - handler loses control of the error response shape; use `ShouldBindJSON` so the error middleware can format consistently                                | Low    |
| Per-handler `c.JSON(500, ...)` Errors   | Inline error mapping scattered across handlers instead of `c.Error(err)` + central error middleware                                                                                                 | Medium |
| Missing Validator Tags on DTO           | DTO declared without `validate:"required,..."` - anything-goes input                                                                                                                                | High   |
| Mass Assignment via `mapstructure`      | `mapstructure.Decode(req.Body, &order)` decoded directly into a domain model - client can override server-set fields like `UserID`, `Role`                                                          | High   |

**Service smells:**

| Smell                              | Signal                                                                                                                                                                          | Risk   |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| God Service File                   | `*_service.go` > 500 lines; mixes orchestration, persistence, mapping, external clients, scheduling                                                                             | High   |
| Anemic Domain                      | Models are pure data containers; business rules live in `*_helpers.go` with names like `CalculateTotal(order)` and could belong as methods on the model                         | High   |
| Single-Implementation Interface    | `OrderRepositoryInterface` + single `gormOrderRepository` with no second implementation, no test mock generated - the interface adds nothing                                    | Medium |
| Missing `context.Context` First Param | Service method does I/O / blocks but takes no `ctx`; cancellation cannot propagate; logs cannot correlate to the request                                                      | High   |
| `panic` in Service Code            | `panic("should never happen")` for impossible-but-not-actually-impossible cases - return a wrapped error instead; panics escape the error model                                 | High   |
| External I/O Inside DB Transaction | HTTP call, message publish, or file write inside `db.Transaction(func(tx *gorm.DB) error {...})` (defers commit, holds DB locks long, races worker pickup before commit)         | High   |
| Returning `bool` From Failure-Capable Operation | Service returns `bool` (or `(T, bool)`); caller cannot distinguish failure cases (validation vs not-found vs external) - return `(T, error)` with sentinel errors      | Medium |
| Floating Goroutine                 | `go fn()` in a service body without ownership (no `errgroup`, no `sync.WaitGroup`) and without a cancellation path (`<-ctx.Done()`) - leak                                      | High   |

**Persistence / GORM / sqlx smells:**

| Smell                                        | Signal                                                                                                                                                                                                          | Risk   |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Model                                    | GORM model struct with > 300 lines of methods; mixes mapping, computed properties, business operations, validation                                                                                              | High   |
| GORM `AfterCreate` / `AfterUpdate` Abuse     | Hook dispatching emails, publishing events, calling external services - races commit and silently breaks; hidden control flow                                                                                   | High   |
| `db.Find` Without Limit / Pagination         | Returns full table without pagination                                                                                                                                                                           | Medium |
| GORM N+1 via Lazy Access                     | Code accesses `order.Items` after `db.Find(&orders)` without `Preload("Items")` - per-row query (N+1)                                                                                                           | High   |
| `db.Raw(fmt.Sprintf(...))` String Concat     | Dynamic SQL built via string concatenation instead of parameterized `db.Raw("... WHERE id = ?", id)` or `db.Where("col = ?", val)`                                                                              | High   |
| Missing `defer rows.Close()`                 | `rows, err := db.QueryContext(...)` without `defer rows.Close()` - leaks connections to the pool                                                                                                                | High   |
| Missing `db.WithContext(ctx)` On Queries     | Queries do not propagate cancellation; long-running queries continue after request cancel                                                                                                                       | Medium |
| `db.AutoMigrate` In Production Code          | Schema changes via `db.AutoMigrate` in app startup; should be `golang-migrate` files for reproducibility / reviewability                                                                                        | High   |
| ORM Model Stored Outside Connection Scope    | GORM model assigned to a package-level cache, sent to an Asynq task payload, or `json.Marshal`-ed long after the request ends - lazy attributes, stale data. Cache IDs and re-fetch instead                     | High   |

**Configuration / DI smells:**

| Smell                        | Signal                                                                                                           | Risk   |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------ |
| Package-level Mutable State  | `var cache = map[string]T{}` / `var handlers = []Fn{}` mutated by request handlers                               | High   |
| Package-level `*sql.DB` Var  | `var DB *gorm.DB` accessed directly by repositories instead of constructor injection                             | High   |
| `os.Getenv("X")` Sprinkled   | `os.Getenv` scattered across packages; should be loaded once into a typed config struct at startup                | Medium |
| Hardcoded Defaults Inline    | Default values inline in code rather than a typed config struct                                                  | Medium |
| `init()` Wiring              | `init()` functions wiring shared state, registering globals - causes test isolation failures and hidden coupling | High   |
| Single-Impl Interface        | Interface defined for a single concrete type with no test mock and no second implementation                      | Medium |
| Interface At Producer        | Interface defined in the package that implements it (Java style); Go idiom is interface at the consumer          | Medium |

**Concurrency / Async smells:**

| Smell                                      | Signal                                                                                                                                                  | Risk   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Goroutine Without Owner                    | `go fn()` in a long-running service without `errgroup`, `sync.WaitGroup`, or a worker pool with shutdown                                                | High   |
| Goroutine Without Cancellation Path        | Goroutine blocked on a channel send / receive with no `select { case <-ctx.Done(): return }` arm - leak                                                 | High   |
| Unbounded `errgroup.Group.Go(...)` Fan-out | Fan-out over a list without `g.SetLimit(N)` (Go 1.20+) or a semaphore - exhausts pool / file descriptors at scale                                       | High   |
| `sync.Mutex` Held Across I/O               | `mu.Lock(); db.Query(...); mu.Unlock()` - serializes I/O across all callers                                                                             | High   |
| Channel Without Cancellation Pair          | `result := <-ch` without `select { case result := <-ch: ... case <-ctx.Done(): return }` - deadlocks if no sender appears                               | High   |
| `client.Enqueue()` Inside DB Transaction   | Asynq task dispatched inside `db.Transaction(...)` - worker may pick it up before commit                                                                | High   |
| Asynq Task Without Idempotency             | Task that re-runs side effects when delivered twice (no dedup, no upsert, no state check)                                                               | High   |
| Asynq Task Without `MaxRetry` for Critical | Critical task (payment, billing) running with default `MaxRetry: 25` (or whatever default) - no explicit retry policy documented                        | Medium |

**Test smells (when refactoring brings tests into scope):**

| Smell                                       | Signal                                                                            | Risk   |
| ------------------------------------------- | --------------------------------------------------------------------------------- | ------ |
| Repository Mocked With In-Process State     | Patching `repo.Save = ...` with map storage instead of using a Testcontainers integration test                                                                       | Medium |
| SQLite in Repository Tests for Postgres App | Tests pass on SQLite but fail in prod on JSONB / partial index / `ON CONFLICT`    | High   |
| In-Process Asynq Mocking Reality            | Mock processor hides at-least-once / retry / archived semantics                   | Medium |
| Copy-Paste Test Functions                   | Multiple near-identical test functions where a table-driven test would do         | Low    |
| `interface{}` / `any` In Test Mocks         | Type-cast escape hatch used to bypass a real type bug                             | Medium |

**General OO smells (apply with Go judgment):**

Use skill: `backend-coding-standards` for the cross-language smell catalog.
Use skill: `complexity-review` when the target shows over-engineering signals (single-impl interfaces, abstract base structs for two embedders, premature factory / strategy, redundant mapping layers) - those are simplification opportunities, not refactor steps to extract more abstractions.

Apply Go judgment - a 25-line service function orchestrating clearly named private functions is fine; a 10-line function doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, tests, and deployments are affected by the refactor.

Go-specific blast-radius signals:

- [ ] **Public API surface**: target is a handler used by external clients - refactor risks API contract change
- [ ] **Module boundary**: target is in a published Go module consumed by other apps (replace directives, vendor, etc.)
- [ ] **GORM hook with broad receiver**: refactoring an `AfterCreate` connected to many models / a callback registered globally affects every dispatch
- [ ] **Service injected widely**: target is constructed in `cmd/api/main.go` and passed to many other services - signature changes cascade
- [ ] **Model used in many queries**: refactoring a model affects every repository / `Find` / `Preload` call
- [ ] **DTO reused across endpoints**: DTO field rename / removal cascades into every dependent endpoint and its tests
- [ ] **Exported package symbol**: refactoring an exported type / function in `internal/x` or a public package means every internal importer breaks

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single package, multiple callers) / **Wide** (cross-package, public handler API, broad GORM hook) / **Critical** (published module, model used by 5+ services).

### Step 6 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase compiles with `go build ./...` cleanly and the test suite passes after each step (`go test -race ./...` for packages with concurrency)
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step (or labeled `coupled-fix`, see below)
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing test suite continues to pass; new tests added when extracting new units

**Recipe interleaving.** When more than one Common Recipe applies to a single target (e.g., a fat handler that also has `mapstructure.Decode(req.Body, target)`, leaks a goroutine, and stashes a GORM model in a package-level cache), do **not** concatenate the recipes - that produces a 25-step plan mixing concerns. Identify the **primary** refactor (usually the one named in the user's goal), use that recipe as the spine, and fold supporting recipes in as additive sub-steps where dependencies require it. State the primary recipe explicitly in the output via the `Primary recipe:` field. If the spine grows past ~8 steps, split into two plans / two PRs rather than one mega-plan.

**Coupled-fix language.** Sometimes a refactor genuinely depends on a behavior change (e.g., extracting a service that derives `UserID` from the JWT claims _requires_ the principal to be available, so adding auth middleware to the route is a structural prerequisite, not "while-we're-here cleanup"). When this happens, label the step `coupled-fix` in the Output Format with its own test gate and rationale. This is **not** a bundling violation - it is an explicit prerequisite. Do not silently fold it into an extraction step.

**Transaction-boundary watch.** When extracting orchestration that runs inside `db.Transaction(func(tx *gorm.DB) error {...})`, the extracted unit inherits the transaction context if called from the original entry point. If the extracted code makes HTTP calls, publishes to Asynq, or writes files, they now happen mid-transaction (a regression). State the transaction stance per step: "callee runs inside caller's transaction" or "callee uses post-commit dispatch (event emitter / closure-after-Transaction-returns) to defer side effects." Never silently move I/O across a transaction boundary.

**Context-propagation watch.** Adding `ctx context.Context` to a function signature crosses an async-cancellation boundary. State whether the new signature accepts `ctx` and whether all callers now plumb it through (no `context.TODO()` / `context.Background()` mid-call as a placeholder - those signal "I gave up on plumbing"). Never silently change a function from no-context to context-aware without auditing every call site.

**Concurrency-stance watch.** Adding goroutines or `errgroup` introduces concurrency. State whether `go test -race ./...` is added to CI for the affected package as part of the refactor - if not, the new race surface is unguarded. Mutex changes (introducing, removing, swapping `Mutex` ↔ `RWMutex`) similarly demand race coverage.

**Common Go refactor recipes:**

**Recipe: Extract service from fat handler**

1. Add `internal/<feature>/service.go` (or new file alongside) with a single intention-revealing method `func (s *OrderService) Place(ctx context.Context, in PlaceOrderInput) (*PlaceOrderResult, error)`; copy logic from handler; handler still does the original work
2. Add `service_test.go` with table-driven tests covering one case per outcome (success, validation failure, external failure)
3. Update handler to call the service via constructor injection; preserve response shape; ensure handler tests pass unchanged
4. Remove the original logic from the handler; verify handler tests pass
5. Add a handler-level test asserting service failure surfaces as the expected error response (likely via `c.Error(err)` + central error middleware)

**Recipe: Convert GORM `AfterCreate` hook side effects to post-commit dispatch**

1. Add a service-level test (or handler test) reproducing the current observable behavior (record updated, email sent, event published)
2. Move the side-effect call out of the hook and into the service method that triggered the create; the side effect now fires after `db.Transaction(...)` returns nil. Side effects fire post-commit instead of mid-transaction
3. Run `go test ./...`; confirm pass
4. If the hook was doing cross-aggregate work, extract the side-effect handler into a service method and call it from the calling service explicitly - remove the hook entirely
5. Run the full suite (`go test -race ./...`); verify no orphan code paths still rely on the hook

**Recipe: Untangle fat handler + hook-driven side effects (combined case)**

The most common Go refactor: a handler `Create` triggers a `db.Create(&order)` whose `AfterCreate` hook fans out (mailers, Asynq dispatches, audit writes). Removing the hook and extracting a service must happen as one logical change, but in safe sub-steps so the suite stays green between commits.

1. **Pin behavior with a handler + service test** asserting every observable side effect (record updated, mailer enqueued, task dispatched, audit row written) - this is the contract the refactor must preserve
2. **Promote hook dispatch to post-commit** first (move the dispatch out of `AfterCreate` and into the calling service after `db.Transaction(...)` returns); side effects fire post-commit; tests still pass
3. **Introduce a service method** (`func (s *OrderService) Create(ctx context.Context, in CreateOrderInput) (*model.Order, error)`) that performs the write _and_ the side effects in one call; handler calls the service _but the hook still runs_ - this duplicates side effects intentionally and temporarily
4. **Make the hook no-op when called from the service** via a context flag (`ctx = context.WithValue(ctx, skipHooksKey{}, true)`) checked at the top of the hook; verify tests still pass with side effects firing exactly once
5. **Delete the hook entirely**; the service is now the single source of orchestration; remove the bypass flag; tests still green
6. **Audit other call sites** (`db.Create`, scheduled tasks, migrations, other services) - any caller relying on the old hook is now broken and must be updated to call the service or have the side effects re-derived

The intermediate "hook no-op when called from service" step is the safety net - it keeps the codebase shippable between the introduction of the service (step 3) and the deletion of the hook (step 5).

**Recipe: Eliminate goroutine leak**

1. Identify the leaked goroutine - bare `go fn()` in a request handler / service, no owner, no `<-ctx.Done()` arm
2. Wrap in `errgroup.WithContext(ctx)`: `g, gctx := errgroup.WithContext(ctx); g.Go(func() error { ... })`; for unbounded fan-out, add `g.SetLimit(N)` (Go 1.20+)
3. Add `<-gctx.Done()` arms to any blocking `select` inside the goroutine: `select { case x := <-ch: ... case <-gctx.Done(): return gctx.Err() }`
4. `if err := g.Wait(); err != nil { return fmt.Errorf("worker pool: %w", err) }` at the end of the orchestrator
5. Run `go test -race ./<package>/...`; confirm clean. If `-race` was not in CI for this package, add it as part of the refactor
6. Validate goroutine count under load (or via pprof `goroutine` profile) shows no growth over time

**Recipe: Eliminate `sync.Mutex` held across I/O**

1. Identify the critical section: `mu.Lock(); db.Query(...); mu.Unlock()` (or any I/O - HTTP, file, channel send to a slow consumer)
2. Decide: does the I/O need to be serialized? If no (typical case), drop the lock before I/O and reacquire only for the small mutation:
   ```go
   mu.Lock()
   localCopy := *state
   mu.Unlock()
   result, err := io.Call(ctx, localCopy)
   if err != nil { return err }
   mu.Lock()
   state.applyResult(result)
   mu.Unlock()
   ```
3. If yes (must serialize), use a per-key mutex (`sync.Map[K]*sync.Mutex`) or `singleflight.Group` to dedupe concurrent calls without blocking unrelated ones
4. Run `go test -race ./...`; confirm clean
5. Add a benchmark asserting throughput improves (`go test -bench`)

**Recipe: Plumb `context.Context` through a previously context-free path**

1. Add `ctx context.Context` as the first parameter to the target function (Go convention)
2. Pass `ctx` to every downstream call that supports it: `db.WithContext(ctx).Find(...)`, `http.NewRequestWithContext(ctx, ...)`, channel sends with `<-ctx.Done()` selects
3. Update every caller to plumb the existing `ctx` (typically `c.Request.Context()` from Gin) - never `context.Background()` / `context.TODO()` as placeholder
4. Run tests; confirm pass
5. Add a test asserting cancellation propagates: `ctx, cancel := context.WithCancel(...); cancel(); ... assert err == context.Canceled`

**Recipe: Split god service into focused services**

1. Identify the orthogonal concerns inside the service file (e.g., `orders/service.go` doing place + cancel + refund + reporting → split into `place.go`, `cancel.go`, `refund.go`, `report.go` with focused service structs or focused methods on a smaller `OrderService`)
2. Extract one concern at a time into a new file with explicit constructors; original god service delegates to it temporarily
3. Update callers to use the new focused service directly; remove delegation from god service
4. Repeat until god service is empty; delete it. Each extraction commits independently
5. Verify all tests still pass

**Recipe: Eliminate single-implementation interface**

1. Confirm the interface has no test mocks (no generated `mock_x` package), no second implementation, no construction-time abstraction need
2. Inline: the consuming code uses the concrete struct directly via constructor injection - `func NewOrderService(repo *gormOrderRepository) *OrderService` instead of `func NewOrderService(repo OrderRepository) *OrderService`. Delete the interface
3. Run tests; confirm pass. Caller code is shorter and clearer
4. **Skip if** the interface is part of a published library API or has a real second implementation (or a generated mock used in tests) - the smell is fake

**Recipe: Move interface from producer to consumer**

1. Identify the interface defined in the implementing package (Java style: `repository/interface.go` declaring `type OrderRepository interface {...}` next to the implementation)
2. Move the interface declaration into the consuming package (typically `service`): `service/order.go` declares the interface alongside the service that consumes it
3. Update imports; the producer (`repository`) no longer references the interface - it just returns its concrete struct
4. Run tests; confirm pass
5. The Go idiom is now followed: "accept interfaces, return structs" - interfaces declared at the consumer

**Recipe: Make Asynq task idempotent**

1. Add a task test asserting the side effect happens exactly once when the same payload is processed twice (different request IDs, same business key)
2. Add an idempotency guard inside the handler: dedup table keyed by `task.ResultWriter().TaskID()` or by a business key; upsert via GORM `db.Clauses(clause.OnConflict{...}).Create(...)`; or version check
3. Verify retries on transient failures still complete the work
4. Configure `MaxRetry`, `Timeout`, `Retention` explicit on the task type (or via `asynq.MaxRetry`, `asynq.Timeout` enqueue options) so poison messages do not loop forever
5. Use `asynq.TaskID(businessKey)` on `client.Enqueue(...)` for client-side dedup when the same input must collapse to one task

**Recipe: Eliminate mass assignment via `mapstructure.Decode`**

1. Identify the unsafe decode: `mapstructure.Decode(req.Body, &order)`, `json.Unmarshal(body, &order)` directly into a domain model
2. Define a request DTO with explicit fields and validator tags: `type UpdateOrderRequest struct { Notes string `validate:"max=500"` }` - no `UserID`, `Role`, `IsAdmin`, etc.
3. Replace the decode with `c.ShouldBindJSON(&req)`, then explicit field copy: `order.Notes = req.Notes`
4. Add a test attempting to inject `user_id` / `role` keys; assert they are stripped
5. Audit other unsafe decodes in the codebase

**Recipe: Replace package-level mutable state**

1. Identify the mutable state (`var cache = map[string]T{}`, `var DB *gorm.DB`, `var handlers = []Fn{}`)
2. Move into a struct with a constructor: `type Cache struct { mu sync.RWMutex; data map[string]T }`; `func NewCache() *Cache { ... }`; injected via constructor
3. Replace package-level reads/writes with method calls on the injected instance
4. Update callers to receive the new dependency explicitly (constructor argument, typically wired in `cmd/api/main.go`)
5. Run tests; confirm pass; assert cross-test isolation (no leaking state between tests via `go test -race -count=10`)

### Step 7 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step (not just at the end); `go test -race ./...` for concurrent code
- [ ] Steps are ordered low-risk first (extracts, additions) before high-risk (deletions, signature changes, hook removals)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## Go Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Go refactor recipes" - this is the spine]
**Stack:** Go <version> / Gin <version>
**Data Access:** GORM <version> | sqlx <version> | database/sql | mixed
**Messaging:** Asynq | Kafka | none

## Coverage Gate

**Status:** Adequate | Thin | Inadequate
**Race-detector coverage:** clean | not run for this package | n/a (no concurrency in target)

[If Adequate: one sentence on the boundary cases that exist.]
[If Thin: list the missing boundary tests; Step 0 below covers them.]
[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-go-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, and Verification. You may still produce the **Smells Identified** and **Sibling Smells (Out of Scope)** sections as a *preview* so the implementer has a target list when filling the coverage gap; mark them clearly as preview-only.]

**Coverage prerequisite list shape (when status is `Thin` or `Inadequate`).** List required tests as one row per public entry point with this shape: `entry-point | outcome | recommended layer`. Outcomes cover at minimum: validation failure (4xx), authorization denial (401/403), not-found / IDOR, external-collaborator failure. Layer options: handler test (`httptest` + `gin.New()`), service unit test, repository integration test (Testcontainers), Asynq task test. Example: `POST /orders | unknown-field rejected | handler test`. This makes the prerequisite directly actionable rather than a vague "add boundary tests."

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file/package that this plan does NOT address. Listed for hand-off, not action._

| Smell   | Location  | Why deferred                                                                                | Recommended follow-up                                                          |
| ------- | --------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| [Smell] | file:line | [separate target / separate severity / belongs to security review / belongs to perf review] | [`task-go-review-security` / `task-go-refactor` on a different target / etc.]  |

_Omit this section if the target file has no other smells._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add the missing boundary tests identified in the Coverage Gate
- **Risk:** Low (tests-only change)
- **Test gate:** new tests pass; existing suite still green; `go test -race ./...` clean if applicable
- **Rollback:** revert added test files

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass after this step - unit / handler / Testcontainers integration / Asynq; `go test -race ./...` for concurrent code]
- **Transaction stance:** [callee runs inside caller's transaction | callee uses post-commit dispatch | not transactional]
- **Context stance:** [accepts ctx | passes ctx through | unchanged]
- **Concurrency stance:** [no concurrency change | introduces goroutine (race coverage required) | removes goroutine | mutex change]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure. Use `Step kind: coupled-fix` for any step that intentionally changes behavior because the refactor depends on it (e.g., adding auth middleware to a route group so the extracted service can derive `UserID` from claims). Always state why the coupling is structural, not cosmetic.]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] `go build ./...` clean and `go test ./...` (with `-race` for concurrent packages) passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step
- [ ] No I/O silently moved across transaction boundaries
- [ ] No silent change to context-propagation behavior; every call site updated
- [ ] No new concurrency without race-detector coverage in CI

## Out of Scope

[Adjacent improvements explicitly NOT in this plan - e.g., "renaming `OrderProcessor` to `OrderFulfiller` is a follow-up; this plan only extracts behavior, not renames"]
```

## Self-Check

**Plan-time checks (verifiable now from the plan itself):**

- [ ] Stack confirmed as Go / Gin (or accepted from parent dispatcher); data-access mix and messaging recorded (Step 1)
- [ ] Target file(s) and matching tests read directly before smell classification - no smells inferred from prose alone (Step 2)
- [ ] Sibling smells in the target file listed under `Sibling Smells (Out of Scope)` with deferral rationale, or section omitted because none exist (Step 2)
- [ ] Coverage gate evaluated using the sharp boundaries (`Adequate` / `Thin` / `Inadequate`); plan refused if `Inadequate`; happy-path-only treated as `Inadequate` not `Thin`; race-detector check applied for concurrent packages (Step 3)
- [ ] Go-specific smells identified using Step 4 catalog (handler/route, service, persistence, configuration/DI, concurrency/Asynq) (Step 4)
- [ ] Cross-module risk (blast radius) stated before proposing steps (Step 5)
- [ ] `Primary recipe:` named in the output; supporting recipes folded as sub-steps, not concatenated (Step 6)
- [ ] Step 0 included if Coverage Gate is `Thin`; omitted if `Adequate` (Output Format)
- [ ] Transaction stance stated per step (no I/O silently moved across transaction boundary) (Step 6)
- [ ] Context stance stated per step (no silent context-propagation change) (Step 6)
- [ ] Concurrency stance stated per step (race-detector coverage required when concurrency added) (Step 6)
- [ ] `Step kind:` set to `coupled-fix` for any step that intentionally changes behavior because the refactor depends on it; rationale stated; otherwise `refactor` (Step 6)
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions, hook removals, signature changes) (Step 6)
- [ ] Plan length ≤ ~8 steps, or split into multiple PRs explicitly (Step 6)
- [ ] No step bundles unrelated cleanup (Step 6)
- [ ] Goal explicitly mapped to the end state of the sequence (Step 7)

**Execution-time gates (commitments the plan makes for the implementer):**

- [ ] `go build ./...` clean and `go test ./...` passes between every step
- [ ] `go test -race ./...` clean for any package touched by a concurrency-introducing step
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate - that's a rewrite, not a refactor
- Proposing a refactor that introduces concurrency to a package that lacks `go test -race` in CI - the new race surface is unguarded
- Bundling behavior changes with refactoring steps - keep them separate, label clearly
- Making "while we're here" unrelated cleanups - they belong in their own PR
- Renaming during a refactor (rename PRs are separate; mixing the two doubles the review surface)
- Removing GORM hooks without a test asserting the original side effects are preserved (post-commit, in the right order)
- Extracting a single-implementation interface without a real second use case - wait for the second use case before generalizing
- Moving HTTP calls or Asynq dispatches from a non-transactional context to inside a `db.Transaction(...)` (or vice versa) without explicitly stating the transaction stance
- Changing a function from no-context to context-aware without auditing every call site - missing context plumbing means cancellation does not propagate, and the bug is silent
- Refactoring an exported symbol in a published Go module without a backward-compatibility plan - that is a public API
- Replacing `gorm` with `sqlx` (or vice versa) on a code path with no measured benefit (premature change; if the team is on GORM and it works, the recipe is "address the smell" not "swap libraries")
- Replacing package-level mutable state with `context.Value` carrying a pointer to it - that is the same global with extra steps; use constructor injection instead
