---
name: task-go-refactor
description: Go / Gin refactor plan - fat handlers, goroutine leaks, context propagation, GORM N+1, mass assignment; phased steps with `go test -race` gate.
agent: go-tech-lead
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Go Refactor

Safe, step-by-step refactor plan for a Go target (handler, service, repository, GORM model, Asynq processor, DTO). Identifies smells; proposes independently-committable steps with `go build` + `go test -race` gates between each.

## When to Use

- Go code-smell resolution
- Tech-debt reduction with a concrete plan
- Safe refactor of a handler / service / repository / Asynq processor

**Not for:** debt prioritization (`task-debt-prioritize`), feature changes (`task-go-implement`), cross-package restructuring (`task-design-architecture`), bug fixes (`task-go-debug`).

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| Target scope | Yes | File / package to refactor |
| Goal | Yes | What the refactor achieves |
| Test coverage status | Recommended | Whether tests / Testcontainers / Asynq coverage exist; `go test -race` clean |
| Shared/public surface | Recommended | Whether the target crosses package / module / team boundaries |

## Workflow

### Step 1 - Stack and Data Access

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. Record `Data Access` (GORM / sqlx / mixed / database/sql) and `Messaging` (Asynq / Kafka / none).

### Step 2 - Read the Target

Plans grounded in user prose hallucinate smells. Before classifying:

1. Read the target top-to-bottom: function count, longest function, sync-vs-async signatures, transaction placement, every external collaborator (`http.Client`, `client.Enqueue`, mailers, GORM hooks)
2. Read matching test files; count cases by outcome (happy / validation / external / auth). Confirm `go test -race` is clean
3. Read the immediate caller - signature changes cascade

If only a goal was given without a target, ask.

**Sibling-smell disposition.** If the target contains other smells beyond the named target, do **not** action them and do **not** ignore them. List under `Sibling Smells (Out of Scope)` with deferral rationale and a follow-up invocation.

### Step 3 - Coverage Gate (mandatory)

Refactoring without tests is a rewrite.

| Status | Definition | Action |
|--------|------------|--------|
| `Adequate` | Happy path + ≥ 2 boundary outcomes per public entry (validation, auth denial, external failure, not-found) | Proceed |
| `Thin` | Happy path + exactly 1 boundary outcome | Proceed; plan must include `Step 0 - Coverage prerequisite` |
| `Inadequate` | No tests, or happy-path-only | **Refuse Steps 1+.** Output Coverage Gate verdict + recommend `task-go-test` first |

**Race-detector check.** If the target uses goroutines / channels / `sync`, confirm `go test -race ./<package>/...` is in CI. If not, downgrade status by one tier.

### Step 4 - Identify Smells

Use skill: `go-overengineering-review` for: binding/service guards vs GORM/DB; defensive nil after non-nil constructors; silent `if err != nil { return nil }`; single-impl interfaces at impl side; `BaseRepository` embedding; naked `go fn()` wrapping sequential calls.

**Additional smells:**

| Smell | Signal | Risk |
|-------|--------|------|
| Fat Handler | > 30 lines orchestrating multiple service calls + response shaping | High |
| Logic in Handler | Business rules or calculation in handler body | High |
| Direct GORM in Handler | `db.Find(...)` in handler, bypassing service | Medium |
| ORM Model in `c.JSON` | `c.JSON(200, *model.User)` without DTO mapping | High |
| `BindJSON` (not `ShouldBindJSON`) | Handler loses error response control | Low |
| Per-handler `c.JSON(500, ...)` | Inline error mapping vs centralized middleware | Medium |
| Mass Assignment | `mapstructure.Decode(req.Body, &model)` | High |
| God Service File | `*_service.go` > 500 lines mixing concerns | High |
| Anemic Domain | Rules in `*_helpers.go` instead of methods on the model | High |
| Missing `ctx` First Param | I/O-doing function without `context.Context` first | High |
| `panic` in Service Code | "Should never happen" panics; return error instead | High |
| External I/O Inside Tx | HTTP / Asynq / mailer inside `db.Transaction(...)` | High |
| Returns `bool` From Failure-Capable Op | Cannot distinguish reasons; use `(T, error)` | Medium |
| Floating Goroutine | `go fn()` without `errgroup`/`WaitGroup`/queue submission | High |
| Fat Model | GORM struct > 300 lines mixing mapping + computed + business | High |
| GORM Hook Abuse | `AfterCreate` dispatching emails / Asynq; races commit | High |
| `db.Find` Without Limit | Unbounded list | Medium |
| GORM N+1 via Lazy Access | `order.Items` after `Find` without `Preload` | High |
| `db.Raw(fmt.Sprintf(...))` | SQL injection via concat | High |
| Missing `defer rows.Close()` | Leaks connections | High |
| Missing `db.WithContext(ctx)` | No cancellation propagation | Medium |
| `db.AutoMigrate` In Production | Use golang-migrate | High |
| ORM Model Outside Conn Scope | Model in cache / Asynq payload long after request | High |
| Package-level Mutable State | `var cache = map[string]T{}` mutated by handlers | High |
| Package-level `*sql.DB` | Accessed directly vs constructor-injected | High |
| `os.Getenv("X")` Sprinkled | Load once into typed config | Medium |
| `init()` Wiring | Registers globals; breaks test isolation | High |
| Interface At Producer | Interface in impl package vs at consumer | Medium |
| Goroutine Without Cancellation | Blocking ops with no `<-ctx.Done()` arm | High |
| Unbounded `errgroup.Go` Fan-out | No `g.SetLimit(N)` over large list | High |
| `sync.Mutex` Across I/O | `mu.Lock(); db.Query(...); mu.Unlock()` serializes I/O | High |
| `client.Enqueue` Inside Tx | Worker may pick up before commit | High |
| Asynq Task Without Idempotency | Re-runs side effects on retry | High |

**Test smells (when refactoring brings tests into scope):**

- Repository mocked with in-process state (use Testcontainers)
- SQLite for a Postgres app (JSONB, partial index, `ON CONFLICT` diverge)
- In-process Asynq mocking reality (hides at-least-once)
- Copy-paste tests where table-driven would do
- `interface{}` / `any` in mocks to bypass type bugs

**General OO smells:** Use skill: `backend-coding-standards`. Use skill: `complexity-review` when over-engineering signals appear - those are simplification opportunities, not refactor steps adding more abstraction.

### Step 5 - Cross-Module Risk

Use skill: `review-blast-radius`.

Go signals: public handler used externally; published Go module surface; GORM hook with broad receiver; service injected widely; model used in many queries; DTO reused across endpoints; exported symbol in `internal/x`.

State blast radius: **Narrow** / **Moderate** / **Wide** / **Critical**.

### Step 6 - Step Sequence

Each step must be:

1. **Independently committable** - `go build ./...` clean and tests (with `-race` for concurrent packages) pass after each step
2. **Behaviorally invariant** unless labeled `coupled-fix`
3. **Reversible** in one revert
4. **Tested** - existing suite passes; new tests when extracting new units

**Recipe interleaving.** When multiple recipes apply, identify the **primary** (usually the user's goal) and fold supporting recipes as sub-steps. If the spine > 8 steps, split into two PRs.

**Coupled-fix.** When a refactor depends on a behavior change (extracting a service that reads `UserID` from JWT requires auth middleware), label `coupled-fix` with its own test gate. Not a bundling violation; an explicit prerequisite.

**Per-step disclosures:**

- **Transaction stance**: callee inside caller's tx | post-commit dispatch | not transactional
- **Context stance**: accepts ctx | passes ctx through | unchanged
- **Concurrency stance**: no change | introduces goroutine (race required) | removes goroutine | mutex change

**Common recipes:**

**Extract service from fat handler**

1. Add `internal/<feature>/service.go` with `func (s *OrderService) Place(ctx, in) (*Result, error)`; copy logic; handler unchanged
2. Add `service_test.go` with table-driven cases (success, validation, external failure)
3. Handler calls service via constructor injection; response shape preserved
4. Remove logic from handler; handler tests stay green
5. Handler-level test asserting service failure surfaces as expected error response

**Move side effects out of an open transaction**

Pick **one**:

*Option A - Post-commit dispatch* (default):

1. Identify I/O inside `db.Transaction(...)` (`Enqueue`, `Produce`, `http.Client.Do`, mailer, cache)
2. Hoist out. Capture inputs inside the tx; dispatch after `Transaction` returns nil:
   ```go
   err := db.Transaction(func(tx *gorm.DB) error {
       if err := tx.Create(&order).Error; err != nil { return err }
       orderID = order.ID
       return nil
   })
   if err != nil { return err }
   if _, err := asynqClient.Enqueue(asynq.NewTask("order.notify", payload)); err != nil {
       slog.ErrorContext(ctx, "post-commit enqueue failed", "order_id", orderID, "err", err)
   }
   ```
3. Document the failure mode (process crash between commit and `Enqueue` drops the dispatch). If unacceptable, use Option B
4. Test asserts side effect fires after commit reached

*Option B - Transactional outbox* (durable, at-least-once):

1. Add `outbox_messages` table: `id`, `aggregate_id`, `event_type`, `payload`, `created_at`, `processed_at NULL`, partial index `(processed_at) WHERE processed_at IS NULL`
2. Inside `db.Transaction`, INSERT outbox alongside business write - both commit atomically
3. Relay polls and dispatches with `FOR UPDATE SKIP LOCKED` for multi-replica safety
4. Handlers MUST be idempotent (`asynq.TaskID("outbox-<id>")` + upserts)
5. Document lag budget and monitoring (queue depth, oldest unprocessed)

**Convert GORM `AfterCreate` to post-commit dispatch**

1. Service / handler test reproducing every observable side effect (the contract)
2. Move side-effect call out of the hook into the calling service; fires after `Transaction` returns nil
3. Confirm pass; hook now empty
4. Audit every caller of `db.Create(&Order{...})` and migrate each to the new service method
5. Delete the hook once no caller bypasses the service

**Combined: fat handler + hook-driven side effects**

Most common Go refactor. Do **not** introduce a context-value bypass flag - invisible control flow.

1. Pin behavior with handler + service tests asserting every side effect
2. Promote hook dispatch to post-commit (move out of `AfterCreate` into the calling service)
3. Audit every caller of `db.Create(&Order{...})` - each must move to the new service method before step 4
4. Introduce the service method performing write + side effects; migrate audited callers one PR each
5. Delete the hook once no caller bypasses the service

If step 3 finds an immovable caller, pause: keep the hook and defer, or split across releases.

**Eliminate goroutine leak**

1. Identify bare `go fn()` with no owner / `<-ctx.Done()`
2. Wrap in `errgroup.WithContext(ctx)`; add `g.SetLimit(N)` for unbounded fan-out
3. Add `<-gctx.Done()` arms to blocking selects
4. `if err := g.Wait(); err != nil { return fmt.Errorf("worker pool: %w", err) }`
5. `go test -race`; add `-race` to CI if missing
6. Validate goroutine count under load (pprof)

**Eliminate `sync.Mutex` across I/O**

1. Identify `mu.Lock(); db.Query(...); mu.Unlock()`
2. If I/O need not be serialized: drop lock before I/O; reacquire only for mutation:
   ```go
   mu.Lock(); localCopy := *state; mu.Unlock()
   result, err := io.Call(ctx, localCopy)
   if err != nil { return err }
   mu.Lock(); state.applyResult(result); mu.Unlock()
   ```
3. If serialization required: per-key mutex (`sync.Map[K]*sync.Mutex`) or `singleflight.Group`
4. `go test -race`; benchmark throughput improvement

**Plumb `context.Context`**

1. Add `ctx context.Context` as first param
2. Pass to every downstream call (`db.WithContext(ctx)`, `http.NewRequestWithContext`, `select` with `<-ctx.Done()`)
3. Every caller passes existing `ctx` (typically `c.Request.Context()`); never `context.Background()` / `TODO()` as placeholder
4. Tests pass; add cancellation propagation test

**Split god service**

1. Identify orthogonal concerns
2. Extract one at a time; god service delegates temporarily
3. Callers use focused service directly; remove delegation
4. Delete god service when empty

**Eliminate single-impl interface**

1. Confirm no test mocks, no second impl, no construction-time abstraction
2. Inline: consumer uses concrete struct via constructor injection
3. Skip if interface is published library API or has real second impl

**Move interface from producer to consumer**

1. Identify interface in implementing package (Java-style)
2. Move into the consuming package
3. Update imports; producer returns concrete struct

**Make Asynq task idempotent**

1. Test asserting side effect happens once on duplicate processing
2. Guard inside handler: dedup table; upsert via `clause.OnConflict`; or version check
3. Verify retries on transient failures still complete
4. Configure `MaxRetry`, `Timeout`, `Retention`
5. `asynq.TaskID(businessKey)` for client-side dedup

**Eliminate mass assignment via `mapstructure.Decode`**

1. Identify unsafe decode
2. Define request DTO with explicit fields + validator tags (no `UserID`, `Role`, `IsAdmin`)
3. Replace with `c.ShouldBindJSON(&req)` + explicit field copy
4. Test attempts to inject `user_id` / `role`; assert stripped

**Replace package-level mutable state**

1. Identify (`var cache = map[string]T{}`, `var DB *gorm.DB`)
2. Move into a struct with constructor (`type Cache struct { mu sync.RWMutex; data map[string]T }`)
3. Replace package-level access with method calls; constructor-injected
4. `go test -race -count=10` asserts cross-test isolation

### Step 7 - Validate Plan

- [ ] Goal achieved at end of sequence
- [ ] Each step reviewable in < 30 minutes
- [ ] Test coverage runs between every step; `-race` for concurrent code
- [ ] Low-risk first (extracts, additions) before high-risk (deletions, signature changes)
- [ ] Rollback path is one revert per step
- [ ] No step bundles unrelated cleanup

## Output Format

```markdown
## Go Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from Common recipes]
**Stack:** Go <version> / Gin <version>
**Data Access:** GORM | sqlx | database/sql | mixed
**Messaging:** Asynq | Kafka | none

## Coverage Gate

**Status:** Adequate | Thin | Inadequate
**Race-detector coverage:** clean | not run for this package | n/a

[If Adequate: one sentence on boundary cases.]
[If Thin: list missing boundary tests; Step 0 covers them.]
[If Inadequate: state required coverage; recommend `task-go-test` first. **Stop here** - omit Blast Radius, Step Sequence, Verification. Smells Identified and Sibling Smells may appear as preview-only.]

**Coverage prerequisite list shape (when `Thin` or `Inadequate`):** one row per public entry point: `entry-point | outcome | recommended layer`. Outcomes: validation failure, authorization denial, not-found / IDOR, external-collaborator failure. Layers: handler (`httptest` + `gin.New()`), service unit test, repository integration (Testcontainers), Asynq task test.

## Smells Identified

| Smell | Location | Risk | Notes |

## Sibling Smells (Out of Scope)

| Smell | Location | Why deferred | Recommended follow-up |

_Omit if no other smells in target._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Adequate)_

- **Change:** add boundary tests from Coverage Gate
- **Risk:** Low
- **Test gate:** new tests pass; suite green; `-race` clean if applicable
- **Rollback:** revert added test files

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass; `-race` for concurrent]
- **Transaction stance:** [...]
- **Context stance:** [...]
- **Concurrency stance:** [...]
- **Rollback:** [how to revert]

## Verification

- [ ] Goal achieved
- [ ] Each step independently committable
- [ ] `go build ./...` clean and `go test ./...` (with `-race`) between every step
- [ ] No bundled cleanup
- [ ] Rollback path is one revert per step
- [ ] No I/O silently moved across transaction boundaries
- [ ] No silent context-propagation change
- [ ] No new concurrency without race-detector coverage in CI

## Out of Scope

[Adjacent improvements explicitly NOT in this plan]
```

## Self-Check

**Plan-time:**

- [ ] Stack confirmed; data-access mix and messaging recorded
- [ ] Target files and matching tests read before classification
- [ ] Sibling smells listed (or section omitted)
- [ ] Coverage gate evaluated with sharp boundaries (happy-path-only = `Inadequate`); plan refused if `Inadequate`; race-detector check applied
- [ ] Blast radius stated before steps
- [ ] `Primary recipe:` named; supporting recipes folded as sub-steps
- [ ] Step 0 included if `Thin`; omitted if `Adequate`
- [ ] Transaction / context / concurrency stance per step
- [ ] `Step kind: coupled-fix` labeled for any intentional behavior change with rationale
- [ ] Steps ordered low-risk first
- [ ] Plan length ≤ 8 steps or split
- [ ] No step bundles unrelated cleanup
- [ ] Goal mapped to end state

**Execution commitments:**

- [ ] `go build ./...` clean and `go test ./...` between every step
- [ ] `go test -race ./...` clean for concurrency-introducing steps
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Refactor without a coverage gate (that's a rewrite)
- Introducing concurrency to a package without `go test -race` in CI
- Bundling behavior changes with refactoring
- "While we're here" unrelated cleanup
- Renaming during a refactor (separate PRs)
- Removing GORM hooks without a test asserting side effects preserved
- `context.Value` skip-flag to silence a hook for "the new path" - audit and delete the hook
- Extracting a single-impl interface without a real second use case
- Moving I/O across a transaction boundary without explicit stance disclosure
- Changing a function from no-context to context-aware without auditing every call site
- Refactoring an exported symbol in a published module without backward-compat plan
- Replacing `gorm` with `sqlx` (or vice versa) without measured benefit
- Replacing package-level state with `context.Value` pointer (same global with extra steps)
