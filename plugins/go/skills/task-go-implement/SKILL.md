---
name: task-go-implement
description: End-to-end Go / Gin feature implementation - generates migration, repository, service, handler layers with full test coverage.
agent: go-engineer
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Implement Go Feature

## When to Use

End-to-end Go/Gin feature work: migration + model + repository + service + handler + tests in one pass.

Not for: single-file edits, bugfixes, frontend.

## Rules

- Handlers orchestrate, services execute; no business logic in handlers
- Constructor injection; no globals or `init()` for wiring
- Errors wrapped with `fmt.Errorf("ctx: %w", err)` at every layer
- Repository interface declared in the **service** package. When the project's convention keeps model, store and service in one feature package, the rule is satisfied by declaring the interface at the consumer within that package - do not split packages to satisfy it literally, and prove cross-package conformance with `var _ Store = (*other.Repository)(nil)` where one exists. `go-data-access` states this as an absolute; this carve-out wins, and the departure goes in Deviations.
- Multi-model writes are transactional, and the **service** owns the boundary - behind a `TxRunner.InTx(ctx, fn)` interface the service declares, never a `*gorm.DB` field. GORM implements it with `db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {...})`; sqlx has no equivalent, so wrap `BeginTxx` / `Commit` with an unconditional deferred `Rollback` and have repository methods take the transaction as an `sqlx.ExtContext`. A concrete handle in the service is untestable without a live database and `go-testing-patterns` forbids mocking the DB, so the interface is what keeps STEP 7 satisfiable. Never put the boundary in the repository - it has to span work the repository does not do
- Background jobs dispatched **after** the transaction returns nil
- No side effects (audit logs, metrics, webhook dispatch) inside the tx closure - they outlive a rollback. Buffer audit lines and flush them after commit. This governs effects that *leave* the database: an audit **row** written to a table in the same transaction is correct and belongs there, precisely because a rollback erases it too.
- Design approved before code. Reading ahead is expected - STEP 2 cannot decide dispatch points or consumer shape without the atomics STEP 5 loads, so consult them early and keep the *approval* gate, not the reading order. When implementation proves an approved decision wrong, change it, and say so in the Output Format's Deviations block rather than silently diverging or building the worse design.

**Every GORM name below is the common case, not the only one.** On a sqlx or `database/sql` project, substitute the equivalent and say you did: `clause.OnConflict{DoNothing: true}` becomes `INSERT ... ON CONFLICT DO NOTHING` with a `RowsAffected` check, `AutoMigrate` has no analogue, and "no GORM model on the wire" is the general rule that no persistence struct is a response DTO.

## Workflow

### STEP 1 - DETECT AND GATHER

Use skill: `stack-detect`. Confirm Go/Gin and project layout.

Ask before writing code, grouped so each cluster surfaces its own follow-ups. Skip clusters the feature does not touch (no External questions for a pure CRUD):

**Domain**
1. Feature description and primary use case
2. Entities, fields, relationships, constraints
3. Status transitions and the invariants around them

**Persistence**
4. Schema shape (tables, indexes, FKs, soft-delete?)
5. Idempotency: client-supplied key or server-derived, and what carries it - an `Idempotency-Key` header, a body field, or a provider event id. A body field rides inside the DTO the mass-assignment guard filters; a header does not
6. Bulk or streamed input, whatever carries it - an upload (multipart, presigned URL, inline JSON), a broker record, a scheduled scan. Three answers: what carries the payload, what caps it (row count, byte size, attempt budget), and - when the work must be resumable - what the rows are re-read from on resume (the stored file, staged rows, an uncommitted offset)

**External**
7. Integrations (which providers, sync vs async, timeout budget)
8. Webhooks: signature scheme, raw-body requirement, replay window

**Concurrency**
9. Background jobs / async events (Asynq / Kafka)
10. Concurrency requirements (fan-out, contention, ordering)

**Access**
11. AuthN / AuthZ (JWT claims used; per-owner vs admin paths). Skip for a feature with no caller-facing surface

Ask targeted questions for gaps. Do not guess.

**When a targeted question comes back unanswered**, do not stall and do not silently pick. Carry it into STEP 2 as a named open decision with a proposed default and its consequence, and let the approval gate settle it. An unanswered question that reaches code as an unmarked assumption is the failure this rule exists to prevent.

### STEP 2 - DESIGN (APPROVAL GATE)

Use skill: `go-gin-patterns` for API - skip it entirely when the feature has no HTTP surface. Use skill: `go-data-access` for data layer.

These atomics declare their own design envelopes, as does `go-security-patterns` where STEP 5 and STEP 6 load it. Every one of them is a rule set here: present the decisions below, not their own `## API Design` / `## Data Access Design` / decision tables.

Present file tree and decisions:

- Open decisions carried from STEP 1, each with its proposed default and the consequence of that default - list these first; the gate exists to settle them
- Endpoints (method, URI, status, DTOs) - omit for a worker-only feature
- Schema (indexes, FKs, CHECK, idempotency unique)
- Service methods, transaction boundaries
- Error model (sentinels, custom types)
- Idempotency strategy
- Webhook design (signature middleware, raw body, outside JWT)
- Background job dispatch points

When the design extends or deviates from the defaults in this skill (e.g., adds a new HTTP status to the error map, departs from the layered file tree, chooses a different middleware ordering), call out the deviation explicitly with the reason so the approver sees the choice rather than discovering it in code review.

Wait for approval.

### STEP 3 - DATABASE

Use skill: `go-migration-safety`. up/down migrations. Index FKs and frequent-filter columns. CHECK for status fields. Unique index for idempotency keys.

### STEP 4 - DATA LAYER

Use skill: `go-data-access`. Use skill: `go-idioms` for ID types (`type UserID int64`), enum fields (`iota` + `Value`/`Scan`), struct tag ordering, and `go:embed` for SQL migrations. Repository interface in the service package; GORM/sqlx impl. Configure pool right after open. Use `clause.OnConflict{DoNothing: true}` for idempotent upserts.

### STEP 5 - SERVICE

Use skill: `go-error-handling`. Use skill: `go-security-patterns` for AuthZ scoping (IDOR), webhook signature verification, secret handling, and SSRF guards when external URLs are user-controlled. Constructor injection. Wrap at every return. `db.Transaction` for multi-step writes.

State transitions: validate in the service via a `validTransitions` map keyed by from-state.

Concurrency: Use skill: `go-concurrency` for goroutines, channels and fan-out. Contention over a **database row** is a different problem with a different answer - two workers claiming the same job, two requests transitioning the same entity. Pick by whether the write needs the prior state:

- **Blind transition** (no read required): conditional `UPDATE ... WHERE id = ? AND status = ?`, and `RowsAffected == 0` means "someone else has it" - a normal outcome, return early.
- **Read-then-write** (the new state depends on the old, as any classifier does): `SELECT ... FOR UPDATE` / `clause.Locking{Strength: "UPDATE"}`, then the guarded `UPDATE` under the held lock. Here `RowsAffected == 0` is **unreachable** - the lock guarantees the row cannot move - so treat it as a broken invariant and return an error rather than swallowing it as contention. A broker-level uniqueness option (`asynq.TaskID`) dedups the enqueue, not the execution, and is never the guard on its own.
Background jobs: Use skill: `go-messaging-patterns`. Dispatch after `Transaction` returns nil.
External APIs: wrap with `context.WithTimeout`; classify at the gateway; define interface for testability.

External mutations (charge, refund, provision): never inside the tx closure. Commit an intent state (e.g. `executing`) first, then make the call - via a post-commit job when retries/backoff are needed, inline when the caller waits on the result. The outcome re-enters as a state transition (webhook, poll, or job completion moves `executing` -> `succeeded`/`failed`); a crash between commit and call is then visible and recoverable instead of silent.

### STEP 6 - HTTP LAYER

Use skill: `go-gin-patterns`. Use skill: `go-security-patterns` for the request DTO (no privilege-bearing fields, mass-assignment guard), default-deny router group, and JWT middleware shape. `ShouldBindJSON` for JSON bodies; `ShouldBindQuery` / `ShouldBindUri` for params; `c.FormFile` behind `http.MaxBytesReader` for multipart uploads, whose type comes from sniffed bytes and whose stored name is server-generated. Response envelope, pagination. Map domain outcomes via centralized middleware:

| Domain outcome | HTTP |
|--------------|------|
| Created | 201 |
| Accepted for async processing | 202 |
| Duplicate request, original result returned | 200 |
| Duplicate request, original still in flight (no result yet) | 202 |
| Validation | 400 |
| Unauthenticated (absent or invalid credential) | 401 |
| Authenticated but not permitted (wrong role, not the owner) | 403 |
| Not found | 404 |
| Conflict | 409 |
| Gone (expired token, deleted resource) | 410 |
| Payload too large (`*http.MaxBytesError`, row-count cap exceeded) | 413 |
| Invalid transition | 422 |
| External timeout | 503 |
| Provider rejected the operation (decline, invalid account) | 422 |
| Provider malfunction (5xx, malformed response) | 502 |
| Already-processed webhook event | 200 (return success so provider stops retrying) |

401 and 403 are different answers: 401 means "we do not know who you are", 403 means "we do and you may not". Returning 404 instead of 403 to avoid confirming a resource exists is a deliberate choice - make it once, apply it consistently, and note it as a deviation.

201 and 202 split on whether the thing the client asked for exists once you answer: a request that writes its row synchronously and only defers the work *on* that row is 201, while one with nothing yet to show is 202. A retry landing while the original is still working has no result to replay - answer 202, not 409, or an aggressive client abandons work that is about to succeed. Statuses below 400 render the success envelope even when the mapper produced them; a 2xx carrying an `error` object is a contract clients will code against.

**Centralized rendering, per-domain classification.** The middleware owns the envelope and the status write; the mapping from a domain's sentinels to a status belongs with that domain and is handed to the middleware at wiring time. One middleware that names every domain's sentinels imports all of them, and any domain that also imports the web helper closes an import cycle.

The webhook "200 on duplicate" mapping is counterintuitive but correct: Stripe, GitHub, and similar providers retry on any non-2xx, so a duplicate-detection 409 produces a retry storm. Treat duplicate as a no-op success.

Webhooks: signature middleware reads `c.GetRawData()` before any binding; route lives outside the JWT auth group.

### STEP 7 - TESTS

Use skill: `go-testing-patterns` - its `Count` format (`funcs / cases`) governs the output's test rows. Table-driven + testcontainers, plus httptest when there is an HTTP surface.

Cover happy path, validation, not-found, conflict, timeout. On a worker those read as: a well-formed record, a malformed payload, a referenced entity that does not exist, a concurrent or duplicate delivery, and a cancelled per-record context. State machines: every valid + invalid transition. Webhooks: valid / invalid / missing signature. Idempotency: duplicates return the same result and the side effect happens once.

### STEP 8 - VALIDATE

Run `go build ./...`, `go test -race ./...`, `go vet ./...`. Fix failures before reporting done.

**When the toolchain is absent** (`go version` fails), the step cannot pass and must not be reported as passing. Do a static substitute - interface conformance against every implementation and fake, duplicate declarations, unused imports, signature mismatches - then label the delivery `unverified: not compiled` in the Output Format and name the commands that would settle it. Generated code, integration tests, and anything behind a build tag stay unverified regardless; say which. A static check that fails is a defect, not a note - fix it before reporting done, exactly as a failing build would be.

## Edge Cases

- Vague input: ask in STEP 1; never guess
- No persistence: skip STEPs 3-4
- Existing entity: read and extend
- Webhook-only: skip CRUD; signature middleware + dedicated handler
- State transitions: service validation + DB CHECK
- Idempotency: unique key + `ON CONFLICT` + service guard. When the idempotent operation is an **UPDATE**, there is no inserted row to carry the key - add a dedupe carrier (an `inbox` / `processed_events` table keyed on the event id, inserted in the same transaction as the effect) or the redelivery re-runs and, on a state machine, writes a spurious invalid-transition failure
- Bulk: batch writes + input size limit; one tx when all-or-nothing, tx per chunk when a partial import must be resumable. Resumability needs three things this rule does not name: a durable source the rows are re-read from (the stored payload, staged rows, or a re-fetchable object), a cursor advanced in the same transaction as the chunk, and a claim so two workers cannot resume the same job
- Worker-only (no HTTP): skip STEP 6 and STEP 2's `go-gin-patterns` load; omit Endpoints from the design and from the output; test the job handler instead of httptest, and read the output's `Handler` count row as the handler-level tests of whatever the entry point is (a task processor, a consumer)

## Output Format

```markdown
## Files Generated
[grouped by layer; mark each created or modified]

## Endpoints
| Method | Path | Request | Response | Status |

_Omit this whole section for a worker-only feature._

## Tests
- Unit: {count}
- Handler: {count} [HTTP handlers; the job/consumer entry point when there is no HTTP]
- Jobs: {count} [task/consumer handlers when the feature has both an HTTP surface and background work; omit the row when it has neither]
- Integration: {count}

## Migration
[file names + what they create]

## Deviations
[Every choice that departs from this skill's defaults or from the approved design - the error-map row added, the layout change, the middleware order, a decision reversed during implementation - each with its reason. `None` when there are none. This is the same list surfaced at the STEP 2 gate; it belongs in the written deliverable too, or it survives only in the conversation.]

## Pre-existing Issues
[Defects in existing code that this change did not introduce, each marked surfaced-only or fixed-with-reason. A defect the feature cannot compile around gets fixed; the rest are reported here, not silently repaired. `None` when there are none.]

## Validation
`go build ./...` / `go test -race ./...` / `go vet ./...` - passed, or `unverified: not compiled` with the reason and what was checked instead.
```

## Self-Check

Mark a line N/A with its reason when the feature has no matching surface - no HTTP layer, no persistence, no webhook - or when a default needed no adaptation because the project already runs the library it names.

- [ ] `behavioral-principles` loaded
- [ ] Stack detected; requirements gathered; unanswered questions carried to the gate as named open decisions; design approved before code
- [ ] Every GORM-named default adapted to the detected data-access layer, with the substitution stated
- [ ] Deviations called out at the approval gate **and** written into the `## Deviations` section
- [ ] All layers generated; repository interface in service package
- [ ] Errors wrapped with `%w`; constructor injection throughout
- [ ] Background jobs dispatched after commit; no side effects inside the tx closure
- [ ] Status transitions validated (service + DB CHECK) when applicable
- [ ] Idempotency: unique index + `ON CONFLICT` + service guard when applicable
- [ ] Webhook: signature middleware, raw body, outside JWT group, duplicate-as-200 when applicable
- [ ] External APIs: `context.WithTimeout` + interface for testability
- [ ] Tests cover happy path, validation, not-found, conflict, and timeout - plus every valid and invalid transition, and a duplicate proving the side effect ran once
- [ ] `go build`, `go test -race`, `go vet` all pass - or, with no toolchain, the static substitute ran and the delivery is labelled `unverified: not compiled`
- [ ] List endpoints paginated

## Avoid

- Business logic in handlers
- Background jobs, audit logs, metrics, or webhook dispatch inside `db.Transaction`
- Global DB connections; `init()` for wiring
- `AutoMigrate` in production
- Returning GORM models from handlers (use response DTOs)
- Unbounded list endpoints
- Generating code before design approval
- `ShouldBindJSON` on webhook endpoints
- Allowing invalid state transitions
- Returning 4xx for a duplicate webhook event (provider will retry forever)
