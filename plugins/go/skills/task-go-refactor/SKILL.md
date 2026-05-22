---
name: task-go-refactor
description: Go / Gin refactor plan: fat handlers, goroutine leaks, context propagation, GORM N+1, mass assignment; phased steps with `go test -race` gate.
agent: go-tech-lead
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Go Refactor

Safe, step-by-step refactoring plan for a Go target (handler, service, repository, GORM model, Asynq processor, DTO). Identifies smells, proposes independently-committable steps with `go build` + `go test -race` gates between each.

## When to Use

- Go code-smell resolution
- Technical-debt reduction with a concrete plan
- Safe refactor of a handler / service / repository / Asynq processor
- "This PR grew the fat-handler problem - what's the cleanup?"

**Not for:**
- Choosing what debt to tackle (`task-debt-prioritize`)
- Feature changes (`task-go-implement`)
- Cross-package restructuring (`task-design-architecture`)
- Bug fixes (`task-go-debug`)

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| Target scope | Yes | File / package to refactor |
| Goal | Yes | What the refactor should achieve |
| Test coverage status | Recommended | Whether tests / Testcontainers / Asynq coverage exist; whether `go test -race` is clean |
| Shared/public surface | Recommended | Whether the target is used across package / module / team boundaries |

## Workflow

### Step 1 - Confirm Stack and Detect Data Access

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. Record `Data Access` (GORM / sqlx / mixed / database/sql) and `Messaging` (Asynq / Kafka / none).

### Step 2 - Read the Target

Refactor plans grounded in user prose hallucinate smells. Before classifying:

1. Read the target file top-to-bottom; note function count, longest function, sync-vs-async signatures, transaction placement, every external collaborator (`http.Client`, Asynq `client.Enqueue`, mailers, GORM hooks)
2. Read the matching test files; count cases by outcome (happy / validation / external / auth). Confirm `go test -race` is clean
3. Read the immediate caller (handler calling the service, scheduled task calling the service) - signature changes cascade

If only a goal was given without a target file, ask for the target.

**Sibling-smell disposition.** If the target file contains other smells beyond the named target (IDOR in `GetOrder`, `exec.Command` in `BulkImport`), do **not** action them and do **not** ignore them. List under `Sibling Smells (Out of Scope)` with brief deferral rationale and a recommended follow-up invocation.

### Step 3 - Coverage Gate (mandatory)

Refactoring without tests is a rewrite. Assign one of three statuses:

| Status | Definition | Action |
|--------|------------|--------|
| `Adequate` | Happy path + ≥ 2 boundary outcomes per public entry (validation, auth denial, external failure, not-found) | Proceed to Step 4 |
| `Thin` | Happy path + exactly 1 boundary outcome | Proceed; plan must include non-optional `Step 0 - Coverage prerequisite` |
| `Inadequate` | No tests, or happy-path-only | **Refuse Steps 1+.** Output Coverage Gate verdict + recommendation to run `task-go-test` first |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot verify the refactor preserves validation, authorization, or error behavior.

**Race-detector check.** If the target uses goroutines / channels / `sync` primitives, confirm `go test -race ./<package>/...` is in CI. If not, downgrade status by one tier (Adequate → Thin, Thin → Inadequate).

Output the explicit status before proceeding.

### Step 4 - Identify Go Smells

Use skill: `go-overengineering-review` for: binding/service guards vs GORM/DB constraints, defensive nil after non-nil constructors, silent `if err != nil { return nil }` swallows, single-impl interfaces at the implementation side, `BaseRepository` embedding, naked `go fn()` wrapping sequential calls.

**Additional Go smells not covered by `go-overengineering-review`:**

| Smell | Signal | Risk |
|-------|--------|------|
| Fat Handler | Handler > 30 lines orchestrating multiple service calls, dispatch, response shaping | High |
| Logic in Handler | Business rules, validation beyond binding, calculation in handler body | High |
| Direct GORM in Handler | `db.Find(...)` in handler, bypassing service | Medium |
| ORM Model in `c.JSON` | Raw `c.JSON(200, *model.User)` without DTO mapping | High |
| `BindJSON` (not `ShouldBindJSON`) | Handler loses error response control | Low |
| Per-handler `c.JSON(500, ...)` | Inline error mapping vs central error middleware | Medium |
| Mass Assignment | `mapstructure.Decode(req.Body, &model)` | High |
| God Service File | `*_service.go` > 500 lines mixing orchestration + persistence + clients | High |
| Anemic Domain | Business rules in `*_helpers.go` instead of methods on the model | High |
| Missing `ctx` First Param | I/O-doing function without `context.Context` first | High |
| `panic` in Service Code | "should never happen" panics; return wrapped error instead | High |
| External I/O Inside DB Transaction | HTTP / Asynq / mailer inside `db.Transaction(...)` | High |
| Returning `bool` From Failure-Capable Op | Cannot distinguish validation vs not-found vs external; use `(T, error)` | Medium |
| Floating Goroutine | `go fn()` without `errgroup` / `WaitGroup` / queue submission | High |
| Fat Model | GORM model struct > 300 lines mixing mapping + computed + business + validation | High |
| GORM `AfterCreate` Abuse | Hook dispatching emails / events / external calls; races commit | High |
| `db.Find` Without Limit | Unbounded list | Medium |
| GORM N+1 via Lazy Access | `order.Items` after `Find` without `Preload` | High |
| `db.Raw(fmt.Sprintf(...))` | SQL injection via concat instead of `?` placeholders | High |
| Missing `defer rows.Close()` | Leaks connections to the pool | High |
| Missing `db.WithContext(ctx)` | No cancellation propagation | Medium |
| `db.AutoMigrate` In Production | Use `golang-migrate` files instead | High |
| ORM Model Outside Connection Scope | Model in package cache / Asynq payload / `json.Marshal`-ed long after request | High |
| Package-level Mutable State | `var cache = map[string]T{}` mutated by request handlers | High |
| Package-level `*sql.DB` | Accessed directly by repositories instead of constructor-injected | High |
| `os.Getenv("X")` Sprinkled | Should be loaded once into a typed config struct | Medium |
| `init()` Wiring | `init()` registering globals; breaks test isolation | High |
| Interface At Producer | Interface in implementation package vs at consumer | Medium |
| Goroutine Without Cancellation | Block on channel send/receive with no `case <-ctx.Done()` | High |
| Unbounded `errgroup.Go` Fan-out | No `g.SetLimit(N)` over a large list | High |
| `sync.Mutex` Across I/O | `mu.Lock(); db.Query(...); mu.Unlock()` serializes I/O | High |
| `client.Enqueue` Inside Transaction | Worker may pick up before commit | High |
| Asynq Task Without Idempotency | Re-runs side effects on retry | High |

**Test smells (when refactoring brings tests into scope):**

- Repository mocked with in-process state map (use Testcontainers integration)
- SQLite in repository tests for a Postgres app (JSONB, partial index, `ON CONFLICT` diverge)
- In-process Asynq mocking reality (hides at-least-once semantics)
- Copy-paste test functions where table-driven would do
- `interface{}` / `any` in test mocks to bypass type bugs

**General OO smells:**

Use skill: `backend-coding-standards` for the cross-language smell catalog.
Use skill: `complexity-review` when the target shows over-engineering signals (single-impl interfaces, abstract bases for two embedders, premature factory, redundant mapping layers) - those are simplification opportunities, not refactor steps to extract more abstractions.

Apply Go judgment: a 25-line service function orchestrating clearly named private functions is fine; a 10-line function doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius`.

Go-specific signals: public handler used by external clients; published Go module surface; GORM hook with broad receiver; service injected widely; model used in many queries; DTO reused across endpoints; exported symbol in `internal/x`.

State blast radius: **Narrow** / **Moderate** / **Wide** / **Critical**.

### Step 6 - Propose the Step Sequence

Each step must be:

1. **Independently committable** - `go build ./...` clean and tests (with `-race` for concurrent packages) pass after each step
2. **Behaviorally invariant** unless labeled `coupled-fix`
3. **Reversible** in one revert
4. **Tested** - existing suite still passes; new tests when extracting new units

**Recipe interleaving.** When multiple recipes apply (a fat handler that also has `mapstructure.Decode`, leaks a goroutine, and uses a package-level cache), don't concatenate - identify the **primary** refactor (usually the one in the user's goal), name it as `Primary recipe:`, fold supporting recipes as sub-steps. If the spine > 8 steps, split into two PRs.

**Coupled-fix language.** Sometimes a refactor depends on a behavior change (extracting a service that reads `UserID` from JWT claims requires the route to have auth middleware - a structural prerequisite). Label the step `coupled-fix` with its own test gate. Not a bundling violation; an explicit prerequisite.

**Per-step disclosures** - state explicitly:

- **Transaction stance**: callee inside caller's transaction | post-commit dispatch | not transactional. Never silently move I/O across a transaction boundary
- **Context stance**: accepts ctx | passes ctx through | unchanged. Never silently change a function from no-context to context-aware without auditing every call site
- **Concurrency stance**: no change | introduces goroutine (race coverage required) | removes goroutine | mutex change

**Common Go refactor recipes:**

**Extract service from fat handler**

1. Add `internal/<feature>/service.go` with one intention-revealing method `func (s *OrderService) Place(ctx, in) (*Result, error)`; copy logic; handler unchanged
2. Add `service_test.go` with table-driven cases (success, validation, external failure)
3. Handler calls the service via constructor injection; preserve response shape
4. Remove logic from handler; handler tests still green
5. Add handler-level test asserting service failure surfaces as expected error response

**Move side effects out of an open DB transaction**

Pick **one**; do not stack.

**Option A - Post-commit dispatch** (default; simpler):

1. Identify I/O inside `db.Transaction(...)` (`client.Enqueue`, `producer.Produce`, `http.Client.Do`, `mailer.Send`, `cache.Set`)
2. Hoist out. Capture inputs (IDs, payloads) inside the tx; dispatch after `Transaction` returns nil:
   ```go
   var orderID int64
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
3. Document the failure mode: "process crash between commit and `Enqueue` drops the dispatch." If unacceptable, switch to Option B
4. Test asserts side effect fires after commit was reached

**Option B - Transactional outbox** (durable, at-least-once):

1. Add `outbox_messages` table: `id`, `aggregate_id`, `event_type`, `payload`, `created_at`, `processed_at NULL`, partial index `(processed_at) WHERE processed_at IS NULL`
2. Inside `db.Transaction`, INSERT into `outbox_messages` alongside the business write - both commit atomically; no enqueue inside the tx
3. Relay (separate goroutine / scheduled task) polls unprocessed rows and dispatches:
   ```go
   db.Clauses(clause.Locking{Strength: "UPDATE", Options: "SKIP LOCKED"}).
       Where("processed_at IS NULL").Order("id").Limit(100).Find(&msgs)
   ```
   `FOR UPDATE SKIP LOCKED` lets multiple relay replicas run without row contention (Postgres / MySQL 8.0+)
4. Side-effect handlers MUST be idempotent (`asynq.TaskID("outbox-<id>")` for client dedup + upserts in the handler)
5. Document lag budget and monitoring (queue depth, oldest unprocessed `created_at`)
6. `go test -race`; outbox row is written in the same tx; relay is idempotent under double-delivery

**Convert GORM `AfterCreate` side effects to post-commit dispatch**

1. Add a service / handler test reproducing observable behavior (record updated, email sent, event published)
2. Move side-effect call out of the hook into the service method that triggered the create; fires after `db.Transaction` returns nil
3. `go test ./...`; confirm pass
4. If the hook did cross-aggregate work, extract to a service method called from the calling service; remove the hook
5. Full suite (`go test -race`); no orphan paths relying on the hook

**Untangle fat handler + hook-driven side effects (combined case)**

The most common Go refactor: a handler `Create` triggers `db.Create(&order)` whose `AfterCreate` fans out (mailers, Asynq, audits).

Do **not** introduce a context-value bypass flag (`context.WithValue(ctx, skipHooksKey{}, true)`) to silence the hook while the service runs in parallel. Invisible control flow; a future caller forgets the flag and silently re-doubles the side effect. Audit-then-delete is the safe sequence.

1. **Pin behavior** with a handler + service test asserting every observable side effect - this is the contract
2. **Promote hook dispatch to post-commit** (move the dispatch out of `AfterCreate` into the calling service); tests still pass; hook now empty
3. **Audit every caller of `db.Create(&Order{...})`** - handler, scheduled tasks, migrations, other services. List them. Each must move to the new service method **before** step 4
4. **Introduce the service method** performing write + side effects; migrate audited callers one PR each; empty hook still runs but does nothing
5. **Delete the hook** once no caller bypasses the service

If step 3 finds a caller that cannot move yet (e.g., a migration before the service is wired), pause: keep the hook and defer the refactor, or split across releases. Do not paper over with a bypass flag.

**Eliminate goroutine leak**

1. Identify bare `go fn()` with no owner / no `<-ctx.Done()`
2. Wrap in `errgroup.WithContext(ctx)`; for unbounded fan-out add `g.SetLimit(N)`
3. Add `<-gctx.Done()` arms to blocking selects
4. `if err := g.Wait(); err != nil { return fmt.Errorf("worker pool: %w", err) }`
5. `go test -race ./<package>/...`; clean. Add `-race` to CI if not present
6. Validate goroutine count under load (pprof `goroutine` profile)

**Eliminate `sync.Mutex` held across I/O**

1. Identify `mu.Lock(); db.Query(...); mu.Unlock()`
2. If I/O need not be serialized: drop the lock before I/O; reacquire only for the mutation:
   ```go
   mu.Lock(); localCopy := *state; mu.Unlock()
   result, err := io.Call(ctx, localCopy)
   if err != nil { return err }
   mu.Lock(); state.applyResult(result); mu.Unlock()
   ```
3. If serialization is required: per-key mutex (`sync.Map[K]*sync.Mutex`) or `singleflight.Group`
4. `go test -race`; clean
5. Benchmark asserting throughput improves

**Plumb `context.Context` through a context-free path**

1. Add `ctx context.Context` as first parameter
2. Pass `ctx` to every downstream call: `db.WithContext(ctx).Find(...)`, `http.NewRequestWithContext(ctx, ...)`, `select` with `<-ctx.Done()`
3. Every caller passes the existing `ctx` (typically `c.Request.Context()`); never `context.Background()` / `context.TODO()` as placeholder
4. Tests pass; add cancellation propagation test

**Split god service into focused services**

1. Identify orthogonal concerns inside the file
2. Extract one concern at a time into a new file with explicit constructors; the god service delegates temporarily
3. Callers use the focused service directly; remove delegation
4. Repeat; delete the god service when empty
5. All tests still pass

**Eliminate single-implementation interface**

1. Confirm no test mocks, no second impl, no construction-time abstraction need
2. Inline: consumer uses the concrete struct via constructor injection. Delete the interface
3. Tests still pass; caller code shorter and clearer
4. **Skip if** the interface is a published library API or has a real second impl

**Move interface from producer to consumer**

1. Identify the interface in the implementing package (Java style)
2. Move into the consuming package
3. Update imports; producer just returns its concrete struct
4. Tests pass

**Make Asynq task idempotent**

1. Test asserting side effect happens exactly once on duplicate processing
2. Idempotency guard inside handler: dedup table keyed by business key; upsert via `db.Clauses(clause.OnConflict{...}).Create(...)`; or version check
3. Verify retries on transient failures still complete the work
4. Configure `MaxRetry`, `Timeout`, `Retention` explicitly
5. Use `asynq.TaskID(businessKey)` on `client.Enqueue(...)` for client-side dedup

**Eliminate mass assignment via `mapstructure.Decode`**

1. Identify the unsafe decode
2. Define a request DTO with explicit fields and validator tags: no `UserID`, `Role`, `IsAdmin`
3. Replace with `c.ShouldBindJSON(&req)`, then explicit field copy: `order.Notes = req.Notes`
4. Test attempts to inject `user_id` / `role`; assert stripped
5. Audit other unsafe decodes

**Replace package-level mutable state**

1. Identify the mutable state (`var cache = map[string]T{}`, `var DB *gorm.DB`)
2. Move into a struct with a constructor: `type Cache struct { mu sync.RWMutex; data map[string]T }`; `func NewCache() *Cache`; constructor-injected
3. Replace package-level access with method calls
4. Callers receive the new dependency explicitly (constructor argument)
5. Tests pass; assert cross-test isolation (`go test -race -count=10`)

### Step 7 - Validate Plan Against Goal

- [ ] Goal achieved at the end of the sequence
- [ ] Each step small enough to review in < 30 minutes
- [ ] Test coverage runs between every step; `go test -race` for concurrent code
- [ ] Low-risk steps first (extracts, additions) before high-risk (deletions, signature changes, hook removals)
- [ ] Rollback path is one revert per step
- [ ] No step bundles unrelated cleanup

## Output Format

```markdown
## Go Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Go refactor recipes"]
**Stack:** Go <version> / Gin <version>
**Data Access:** GORM | sqlx | database/sql | mixed
**Messaging:** Asynq | Kafka | none

## Coverage Gate

**Status:** Adequate | Thin | Inadequate
**Race-detector coverage:** clean | not run for this package | n/a

[If Adequate: one sentence on boundary cases.]
[If Thin: list missing boundary tests; Step 0 covers them.]
[If Inadequate: state what coverage must exist; recommend running `task-go-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, Verification. You may still produce **Smells Identified** and **Sibling Smells** as a preview; mark preview-only.]

**Coverage prerequisite list shape (when `Thin` or `Inadequate`):** one row per public entry point: `entry-point | outcome | recommended layer`. Outcomes cover validation failure, authorization denial, not-found / IDOR, external-collaborator failure. Layer options: handler test (`httptest` + `gin.New()`), service unit test, repository integration (Testcontainers), Asynq task test.

## Smells Identified

| Smell | Location | Risk | Notes |
| ----- | -------- | ---- | ----- |

## Sibling Smells (Out of Scope)

| Smell | Location | Why deferred | Recommended follow-up |
| ----- | -------- | ------------ | --------------------- |

_Omit if no other smells in target._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Adequate)_

- **Change:** add boundary tests from Coverage Gate
- **Risk:** Low
- **Test gate:** new tests pass; existing suite green; `go test -race ./...` clean if applicable
- **Rollback:** revert added test files

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass; `go test -race` for concurrent]
- **Transaction stance:** [callee inside caller's tx | post-commit dispatch | not transactional]
- **Context stance:** [accepts ctx | passes ctx through | unchanged]
- **Concurrency stance:** [no change | introduces goroutine (race required) | removes goroutine | mutex change]
- **Rollback:** [how to revert]

### Step 2 - [...]

[`Step kind: coupled-fix` for steps that intentionally change behavior because the refactor depends on it; state why the coupling is structural.]

## Verification

- [ ] Goal achieved at end of sequence
- [ ] Each step independently committable
- [ ] `go build ./...` clean and `go test ./...` (with `-race`) passes between every step
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

- [ ] Stack confirmed; data-access mix and messaging recorded (Step 1)
- [ ] Target files and matching tests read directly before classification (Step 2)
- [ ] Sibling smells listed with deferral rationale (or section omitted) (Step 2)
- [ ] Coverage gate evaluated using sharp boundaries; happy-path-only treated as `Inadequate`; plan refused if `Inadequate`; race-detector check applied (Step 3)
- [ ] Smells identified using Step 4 catalog (Step 4)
- [ ] Blast radius stated before steps (Step 5)
- [ ] `Primary recipe:` named; supporting recipes folded as sub-steps (Step 6)
- [ ] Step 0 included if `Thin`; omitted if `Adequate` (Output Format)
- [ ] Transaction stance per step (Step 6)
- [ ] Context stance per step (Step 6)
- [ ] Concurrency stance per step (Step 6)
- [ ] `Step kind: coupled-fix` labeled for any intentional behavior change with rationale (Step 6)
- [ ] Steps ordered low-risk first (Step 6)
- [ ] Plan length ≤ 8 steps or split (Step 6)
- [ ] No step bundles unrelated cleanup (Step 6)
- [ ] Goal mapped to end state (Step 7)

**Execution-time (commitments for the implementer):**

- [ ] `go build ./...` clean and `go test ./...` passes between every step
- [ ] `go test -race ./...` clean for concurrency-introducing steps
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Refactor without a coverage gate - that's a rewrite
- Introducing concurrency to a package without `go test -race` in CI
- Bundling behavior changes with refactoring steps
- "While we're here" unrelated cleanup
- Renaming during a refactor (separate PRs)
- Removing GORM hooks without a test asserting original side effects are preserved
- `context.Value` skip-flag to silence a hook for "the new path" - audit and delete the hook outright instead
- Extracting a single-impl interface without a real second use case
- Moving I/O across a transaction boundary without explicit transaction-stance disclosure
- Changing a function from no-context to context-aware without auditing every call site
- Refactoring an exported symbol in a published module without a backward-compatibility plan
- Replacing `gorm` with `sqlx` (or vice versa) without measured benefit
- Replacing package-level state with `context.Value` carrying a pointer - same global with extra steps
