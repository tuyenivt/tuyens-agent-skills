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

# Implement Go Feature

## When to Use

End-to-end Go/Gin feature work: migration + model + repository + service + handler + tests in one pass.

Not for: single-file edits, bugfixes, frontend.

## Rules

- Handlers orchestrate, services execute; no business logic in handlers. Parsing and validating a parameter is orchestration; deciding what a principal may see (admin vs owner scope) is business logic and lives in the service or middleware
- Constructor injection; no globals or `init()` for wiring
- Errors wrapped with `fmt.Errorf("ctx: %w", err)` at every layer
- Repository interface declared at the **consumer** - the service package. When the project keeps model, store and service in one feature package, declare it at the consumer within that package rather than splitting packages; when the consumer importing the implementation's package would close an import cycle (`service` -> `worker` -> `service`), the interface stays at the consumer and the cycle is broken by moving the shared type or task constructor to a leaf package (`tasks`), never by importing the worker from the service. Extending an existing interface adds methods; existing signatures are not changed. Prove conformance with `var _ Store = (*other.Repository)(nil)`. `go-data-access` states placement as an absolute; this rule wins, and the departure goes in Deviations
- Multi-model writes are transactional, and the **service** owns the boundary behind a `TxRunner` interface it declares: `InTx(ctx context.Context, fn func(tx *gorm.DB) error) error`, implemented with `db.WithContext(ctx).Transaction(fn)`; repositories expose `WithTx(tx *gorm.DB)` per `go-data-access`, and the service calls `s.refunds.WithTx(tx)` inside `fn`. This wins over `go-data-access`'s `s.db` field: a concrete handle makes the service untestable without a database (`go-testing-patterns` forbids mocking the DB), while a fake `TxRunner` calls `fn(nil)` and fake repositories ignore `WithTx`. On sqlx, `fn` takes `sqlx.ExtContext` and the implementation wraps `BeginTxx` / `Commit` with an unconditional deferred `Rollback`. Never put the boundary in the repository - it has to span work the repository does not do
- Background jobs dispatched **after** `InTx` returns nil
- No side effects (audit logs, metrics, webhook dispatch) inside the `InTx` closure - they outlive a rollback. Buffer audit lines and flush them after commit. This governs effects that *leave* the database: an audit **row** written in the same transaction is correct, precisely because a rollback erases it too
- Design approved before code. Reading ahead is expected: consult STEP 6's atomics before the gate; the *approval* gate holds, not the reading order. When implementation proves an approved decision wrong, change it, and say so in Deviations rather than silently diverging or building the worse design
- A pre-existing defect is fixed only when the feature cannot compile or cannot run its own path without the fix (a build error, an error mapper never mounted on the route the feature adds); everything else is surfaced under `## Pre-existing Issues`, not repaired

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format (`## API Design`, `## Data Access Design`, `## Migration Plan`, `## Error Design`, `## Messaging Design`, `## Concurrency Design`, `## Test Strategy`, decision tables). They are rule sets here: only this skill's Output Format is emitted, with one exception - `go-testing-patterns`' `Count` format (`funcs / cases`) governs the `## Tests` rows.

**Every GORM name below is the common case, not the only one.** On a sqlx or `database/sql` project, substitute the equivalent and say you did: `clause.OnConflict{DoNothing: true}` becomes `INSERT ... ON CONFLICT DO NOTHING` on PostgreSQL (`INSERT ... ON DUPLICATE KEY UPDATE id = id` on MySQL, per `go-data-access`'s `Database` switch) with a `RowsAffected` check (on MySQL it tells insert from duplicate only while the DSN leaves `clientFoundRows` at its default `false`), `AutoMigrate` has no analogue, and "no GORM model on the wire" is the general rule that no persistence struct is a response DTO.

## Workflow

### STEP 1 - BEHAVIORAL PRINCIPLES

Use skill: `behavioral-principles`.

### STEP 2 - DETECT AND GATHER

Use skill: `stack-detect`. Confirm Go/Gin, `Database`, and project layout.

Ask before writing code, grouped so each cluster surfaces its own follow-ups. Skip clusters the feature does not touch (no External questions for a pure CRUD). A question the repo's own docs answer (a design doc, an answers file, `CLAUDE.md`) is answered - cite the source instead of asking.

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

**When a targeted question comes back unanswered**, do not stall and do not silently pick. Carry it into STEP 3 as a named open decision with a proposed default and its consequence, and let the approval gate settle it. An unanswered question that reaches code as an unmarked assumption is the failure this rule exists to prevent.

**Existing entity:** read it and extend. Record defects found in existing code while reading, for `## Pre-existing Issues`.

### STEP 3 - DESIGN (APPROVAL GATE)

Use skill: `go-gin-patterns` for API - skip it entirely when the feature has no HTTP surface. Use skill: `go-data-access` for data layer.

Present file tree and decisions:

- Open decisions carried from STEP 2, each with its proposed default and the consequence of that default - list these first; the gate exists to settle them
- Endpoints (method, URI, every status returned, DTOs) - omit for a worker-only feature
- Schema (indexes, FKs, CHECK, idempotency unique)
- Service methods, transaction boundaries
- Error model (sentinels, custom types)
- Idempotency strategy
- Webhook design (signature middleware, raw body, outside JWT)
- Background job dispatch points

When the design extends or deviates from the defaults in this skill (e.g., adds a new HTTP status to the error map, departs from the layered file tree, chooses a different middleware ordering), call out the deviation explicitly with the reason so the approver sees the choice rather than discovering it in code review.

Wait for approval. Record the answers, the settled defaults, and the approval (who, or `self-approved per instruction`) for `## Decisions`.

### STEP 4 - DATABASE

Use skill: `go-migration-safety`. up/down migrations numbered after the highest version on both base and branch (a collision with a concurrently merged migration is renumbered above the highest version before merge; an environment that already applied the branch's version is rolled back off it first (`migrate goto <N-1>`), because golang-migrate rejects two files with one version and that environment would otherwise skip main's and re-run the branch's DDL). Index FKs and frequent-filter columns. CHECK for status fields. Unique index for idempotency keys.

### STEP 5 - DATA LAYER

Use skill: `go-data-access`. Use skill: `go-idioms` for ID types (`type UserID int64`), enum fields (`iota` + `Value`/`Scan`), struct tag ordering, and `go:embed` for SQL migrations. Repository interface at the consumer; GORM/sqlx impl with `WithTx`. Configure pool right after open. List reads use keyset pagination (`CursorMeta`), which overrides the offset `List` / `OffsetMeta` defaults in `go-data-access` and `go-gin-patterns` - an offset list kept for an existing endpoint goes in Deviations; the cursor is an opaque encoding of the `ORDER BY` columns, and the repository re-applies the principal scope so a tampered cursor cannot cross owners.

### STEP 6 - SERVICE

Use skill: `go-error-handling`. Use skill: `go-security-patterns` for AuthZ scoping (IDOR), webhook signature verification, secret handling, and SSRF guards when external URLs are user-controlled. Constructor injection. Wrap at every return. `InTx` for multi-step writes.

State transitions: validate in the service via a `validTransitions` map keyed by from-state.

Concurrency: Use skill: `go-concurrency` for goroutines, channels and fan-out. Contention over a **database row** is a different problem with a different answer - two workers claiming the same job, two requests transitioning the same entity. Pick by whether the write needs the prior state:

- **Blind transition** (no read required): conditional `UPDATE ... WHERE id = ? AND status = ?`, and `RowsAffected == 0` means "someone else has it" - a normal outcome, return early.
- **Read-then-write** (the new state depends on the old, as any classifier does): `SELECT ... FOR UPDATE` / `clause.Locking{Strength: "UPDATE"}`, then the guarded `UPDATE` under the held lock. Here `RowsAffected == 0` is **unreachable** - the lock guarantees the row cannot move - so treat it as a broken invariant and return an error rather than swallowing it as contention. A broker-level uniqueness option (`asynq.TaskID`) dedups the enqueue, not the execution, and is never the guard on its own.

Background jobs: Use skill: `go-messaging-patterns`. Dispatch after `InTx` returns nil.

External APIs: wrap with `context.WithTimeout`; classify at the gateway; define interface for testability.

External mutations (charge, refund, provision): never inside the `InTx` closure. Commit an intent state (e.g. `executing`) first, then make the call - via a post-commit job when retries/backoff are needed, inline when the caller waits on the result. The outcome re-enters as a state transition (webhook, poll, or job completion moves `executing` -> `succeeded`/`failed`); a crash between commit and call is then visible and recoverable instead of silent. An indeterminate outcome (timeout after send) is not an error at the HTTP layer: the service returns the committed `executing` row and the handler renders 202 with it, so `go-error-handling`'s `ErrIndeterminate` -> 202 `error` body is never emitted; the mapper produces no status below 400.

### STEP 7 - HTTP LAYER

Use skill: `go-gin-patterns`. Use skill: `go-security-patterns` for the request DTO (no privilege-bearing fields, mass-assignment guard), default-deny router group, and JWT validation (`WithValidMethods`, `iss` / `aud` / `exp`); the middleware shape (the `principal` key, the `ErrorResponse` 401 body) comes from `go-gin-patterns`. `ShouldBindJSON` for JSON bodies; `ShouldBindQuery` / `ShouldBindUri` for params; `c.FormFile` behind `http.MaxBytesReader` for multipart uploads, whose type comes from sniffed bytes and whose stored name is server-generated. Response envelope, pagination - an envelope the project already uses wins over `go-gin-patterns`' `SuccessResponse` / `ErrorResponse`, named in Deviations. Map domain errors via centralized middleware, which writes only the domain-error rows at 400 and above; `go-gin-patterns`' `Idempotency` middleware writes the replay (at the stored original status, a stored 4xx included) and both 409 rows, adding `Retry-After` to the in-flight 409 as an extension of that middleware; every other row below 400 is written by the handler in the success envelope. The table adopts the statuses the loaded atomics already fix (`go-gin-patterns` / `go-security-patterns` idempotency and ownership, `go-error-handling` provider outcomes):

| Domain outcome | HTTP |
|--------------|------|
| Created | 201 |
| Accepted for async processing; external outcome indeterminate (intent row committed) | 202 |
| Duplicate request, original result returned | the stored original status (201 for a replayed create) |
| Duplicate request, original still in flight; same key with a different body | 409 (+ `Retry-After` while in flight) |
| Validation | 400 |
| Unauthenticated (absent, invalid, or expired credential) | 401 |
| Authenticated but wrong role | 403 |
| Not found; resource owned by another principal (the owner-scoped lookup finds nothing) | 404 |
| Conflict | 409 |
| Gone (expired single-use link token, deleted resource) | 410 |
| Payload too large (`*http.MaxBytesError`, row-count cap exceeded) | 413 |
| Invalid transition | 422 |
| Provider declined the operation (`go-error-handling`'s `ErrPaymentDeclined`) | 402 |
| External unavailable before send (`ErrRetryable`, upstream down) | 503 |
| Provider rejected the request with a decoded non-5xx error other than a decline (`ErrGatewayFailure`: invalid account, invalid parameters); an undecoded error or a 5xx after a mutation was sent is `ErrIndeterminate` and renders 202 per STEP 6 | 502 |
| Already-processed webhook event | 200 (return success so provider stops retrying) |

401 and 403 are different answers: 401 means "we do not know who you are", 403 means "we do and you may not". 404 for another principal's resource is the default because the owner-scoped query finds nothing; a 403 after an unscoped load confirms the resource exists (an existence oracle) and repeats the handler-level ownership check `go-security-patterns` labels Bad.

201 and 202 split on whether the thing the client asked for exists once you answer: a request that writes its row synchronously and only defers the work *on* that row is 201, while one with nothing yet to show is 202. A retry landing while the original is still working has no result to replay - 409 with `Retry-After` tells the client to retry shortly, not to abandon.

**Centralized rendering, per-domain classification.** The middleware owns the envelope and the status write; each domain registers a classifier `func(error) (status int, msg string, ok bool)` at wiring time. This replaces `go-error-handling`'s single-switch `ErrorMiddleware`: one middleware that names every domain's sentinels imports all of them, and any domain that also imports the web helper closes an import cycle.

Duplicate webhook events return 200: Stripe and similar providers retry on any non-2xx, so a duplicate-detection 409 produces a retry storm (GitHub does not redeliver automatically, but a 4xx still shows as a failed delivery). Treat duplicate as a no-op success.

Webhooks: signature middleware reads `c.GetRawData()` before any binding; route lives outside the JWT auth group.

### STEP 8 - TESTS

Use skill: `go-testing-patterns`. Table-driven + testcontainers, plus httptest when there is an HTTP surface.

Cover happy path, validation, not-found, conflict, timeout. On a worker those read as: a well-formed record, a malformed payload, a referenced entity that does not exist, a concurrent or duplicate delivery, and a cancelled per-record context. State machines: every valid + invalid transition. Webhooks: valid / invalid / missing signature. Idempotency: duplicates return the same result and the side effect happens once. Ownership: another principal's resource is 404. Codec and helper functions count under `Unit`.

### STEP 9 - VALIDATE

Run `go build ./...`, `go vet ./...`, `go vet -tags=integration ./...`, `go test -race ./...`, and `go test -tags=integration -race ./...` (needs Docker). Fix failures before reporting done; an integration run that could not execute is labelled unverified in `## Validation`.

**When the toolchain is absent** (`go version` fails), the step cannot pass and must not be reported as passing; when only `-race` cannot run (`-race requires cgo`: `CGO_ENABLED=0` or no C compiler on Linux / Windows), run `go test` without it and label the race runs unverified in `## Validation`. With no toolchain, do a static substitute - interface conformance against every implementation and fake, duplicate declarations, unused imports, signature mismatches - then label the delivery `unverified: not compiled` in the Output Format and name the commands that would settle it. Generated code, integration tests, and anything behind a build tag stay unverified regardless; say which. A static check that fails is a defect, not a note - fix it before reporting done, exactly as a failing build would be.

## Edge Cases

- No persistence: skip STEPs 4-5
- Webhook-only: skip CRUD; signature middleware + dedicated handler
- State transitions: service validation + DB CHECK
- Idempotency: unique key + upsert-on-conflict + service guard. When the idempotent operation is an **UPDATE**, there is no inserted row to carry the key - add a dedupe carrier (an `inbox` / `processed_events` table keyed on the event id, inserted in the same transaction as the effect) or the redelivery re-runs and, on a state machine, writes a spurious invalid-transition failure
- Bulk: batch writes + input size limit; one tx when all-or-nothing, tx per chunk when a partial import must be resumable. Resumability needs three things this rule does not name: a durable source the rows are re-read from (the stored payload, staged rows, or a re-fetchable object), a cursor advanced in the same transaction as the chunk, and a claim so two workers cannot resume the same job
- Worker-only (no HTTP): skip STEP 7 and STEP 3's `go-gin-patterns` load; omit Endpoints from the design and from the output; test the job handler instead of httptest, and read the output's `Handler` count row as the handler-level tests of whatever the entry point is (a task processor, a consumer)

## Output Format

```markdown
## Files Generated
[grouped by layer; mark each created or modified]

## Decisions
[Each STEP 2 question with its answer and source, each open decision with the default that settled it, and the approval record (`approved by <who>` or `self-approved per instruction`). Assumptions about existing code (`model.Refund` already exists) belong here too.]

## Endpoints
| Method | Path | Request | Response | Statuses |

_Omit this whole section for a worker-only feature._

## Tests
[Any row with nothing to count reads `n/a - <reason>`; a func with no subtests counts `1 / 0`, per `go-testing-patterns`]
- Unit: {funcs / cases}
- Handler: {funcs / cases} [HTTP handlers; with no HTTP surface, every job / consumer entry point]
- Jobs: {funcs / cases} [task/consumer handlers; omit the row unless the feature has both an HTTP surface and background work]
- Integration: {funcs / cases}

## Migration
[file names + what they create]

## Deviations
[Every choice that departs from this skill's defaults or from the approved design - the error-map row added, the layout change, the middleware order, a decision reversed during implementation - each with its reason. `None` when there are none. The list surfaced at the STEP 3 gate, written down.]

## Pre-existing Issues
[Defects in existing code that this change did not introduce, each marked surfaced-only or fixed-with-reason per the Rules. `None` when there are none.]

## Validation
`go build ./...` / `go vet ./...` / `go vet -tags=integration ./...` / `go test -race ./...` / `go test -tags=integration -race ./...` - per command `passed` or `unverified: <reason>` (integration without Docker, race without cgo), or for the whole delivery `unverified: not compiled` with the reason and what was checked instead.
```

## Self-Check

Mark a line N/A with its reason when the feature has no matching surface - no HTTP layer, no persistence, no webhook - or when a default needed no adaptation because the project already runs the library it names.

- [ ] STEP 1: `behavioral-principles` loaded
- [ ] STEP 2: stack and `Database` detected; requirements gathered, repo-answered questions cited; unanswered questions carried to the gate as named open decisions; existing-code defects recorded
- [ ] STEP 3: design approved before code; deviations called out at the gate **and** written into `## Deviations`; decisions and approval written into `## Decisions`
- [ ] STEP 4: migrations numbered after the highest version on base and branch; FKs and filters indexed; CHECK on status; unique index on idempotency keys
- [ ] STEP 5: repository interface at the consumer with `WithTx`; every GORM-named default adapted to the detected data-access layer, with the substitution stated; list reads keyset-paginated, or an offset list kept for an existing endpoint named in `## Deviations`
- [ ] STEP 6: errors wrapped with `%w`; constructor injection; `InTx` boundary in the service; jobs dispatched after commit; no side effects inside the closure; transitions validated; external mutations behind a committed intent state
- [ ] STEP 7: status table applied; per-domain classifiers; request DTO free of privilege-bearing fields; webhook raw body, signature, outside JWT, duplicate-as-200
- [ ] STEP 8: tests cover happy path, validation, not-found, conflict, timeout, every valid and invalid transition, a duplicate proving the side effect ran once, and another principal's resource
- [ ] STEP 9: build, vet (both tag sets), and race tests pass - or, when only `-race` cannot run, `go test` passed without it and the race runs are labelled unverified - or, with no toolchain, the static substitute ran and the delivery is labelled `unverified: not compiled`

## Avoid

- `AutoMigrate` in production
- Generating code before design approval
- `ShouldBindJSON` on webhook endpoints
- Returning 4xx for a duplicate webhook event (provider will retry forever)
- Fixing a pre-existing defect the feature can compile and run without
