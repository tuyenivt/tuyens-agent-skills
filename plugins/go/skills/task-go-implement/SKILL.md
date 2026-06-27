---
name: task-go-implement
description: End-to-end Go / Gin feature implementation - generates migration, repository, service, handler layers with full test coverage.
agent: go-architect
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

Not for: single-file edits, bugfixes (`task-go-debug`), frontend.

## Rules

- Handlers orchestrate, services execute; no business logic in handlers
- Constructor injection; no globals or `init()` for wiring
- Errors wrapped with `fmt.Errorf("ctx: %w", err)` at every layer
- Repository interface declared in the **service** package
- Multi-model writes use `db.Transaction(...)`
- Background jobs dispatched **after** the transaction returns nil
- No side effects (audit logs, metrics, webhook dispatch) inside the tx closure - they outlive a rollback. Buffer audit lines and flush them after commit.
- Each step completes before the next; design approved before code

## Workflow

### STEP 1 - DETECT AND GATHER

Use skill: `stack-detect`. Confirm Go/Gin and project layout.

Ask before writing code, grouped so each cluster surfaces its own follow-ups:

**Domain**
1. Feature description and primary use case
2. Entities, fields, relationships, constraints
3. Status transitions and the invariants around them

**Persistence**
4. Schema shape (tables, indexes, FKs, soft-delete?)
5. Idempotency: client-supplied key or server-derived?

**External**
6. Integrations (which providers, sync vs async, timeout budget)
7. Webhooks: signature scheme, raw-body requirement, replay window

**Concurrency**
8. Background jobs / async events (Asynq / Kafka)
9. AuthN / AuthZ (JWT claims used; per-owner vs admin paths)
10. Concurrency requirements (fan-out, contention, ordering)

Ask targeted questions for gaps. Do not guess.

### STEP 2 - DESIGN (APPROVAL GATE)

Use skill: `go-gin-patterns` for API. Use skill: `go-data-access` for data layer.

Present file tree and decisions:

- Endpoints (method, URI, status, DTOs)
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

Concurrency: Use skill: `go-concurrency`.
Background jobs: Use skill: `go-messaging-patterns`. Dispatch after `Transaction` returns nil.
External APIs: wrap with `context.WithTimeout`; classify at the gateway; define interface for testability.

### STEP 6 - HTTP LAYER

Use skill: `go-gin-patterns`. Use skill: `go-security-patterns` for the request DTO (no privilege-bearing fields, mass-assignment guard), default-deny router group, and JWT middleware shape. `ShouldBindJSON`, response envelope, pagination. Map domain errors via centralized middleware:

| Domain Error | HTTP |
|--------------|------|
| Validation | 400 |
| Unauthorized | 401 |
| Not found | 404 |
| Conflict | 409 |
| Gone (expired token, deleted resource) | 410 |
| Invalid transition | 422 |
| External timeout | 503 |
| Already-processed webhook event | 200 (return success so provider stops retrying) |

The webhook "200 on duplicate" mapping is counterintuitive but correct: Stripe, GitHub, and similar providers retry on any non-2xx, so a duplicate-detection 409 produces a retry storm. Treat duplicate as a no-op success.

Webhooks: signature middleware reads `c.GetRawData()` before any binding; route lives outside the JWT auth group.

### STEP 7 - TESTS

Use skill: `go-testing-patterns`. Table-driven + httptest + testcontainers. Cover happy path, validation, not-found, conflict, timeout. State machines: every valid + invalid transition. Webhooks: valid / invalid / missing signature. Idempotency: duplicates return the same result.

### STEP 8 - VALIDATE

Run `go build ./...`, `go test -race ./...`, `go vet ./...`. Fix failures before reporting done.

## Edge Cases

- Vague input: ask in STEP 1; never guess
- No persistence: skip STEPs 3-4
- Existing entity: read and extend
- Webhook-only: skip CRUD; signature middleware + dedicated handler
- State transitions: service validation + DB CHECK
- Idempotency: unique key + `ON CONFLICT` + service guard
- Bulk: `db.Transaction` + batch create + size limit

## Output Format

```markdown
## Files Generated
[grouped by layer]

## Endpoints
| Method | Path | Request | Response | Status |

## Tests
- Unit: {count}
- Handler: {count}
- Integration: {count}

## Migration
[file names + what they create]
```

## Self-Check

- [ ] Stack detected; requirements gathered; design approved before code
- [ ] Deviations from the skill's defaults (error map, layout, middleware order) called out at the approval gate
- [ ] All layers generated; repository interface in service package
- [ ] Errors wrapped with `%w`; constructor injection throughout
- [ ] Background jobs dispatched after commit; no side effects inside the tx closure
- [ ] Status transitions validated (service + DB CHECK) when applicable
- [ ] Idempotency: unique index + `ON CONFLICT` + service guard when applicable
- [ ] Webhook: signature middleware, raw body, outside JWT group, duplicate-as-200 when applicable
- [ ] External APIs: `context.WithTimeout` + interface for testability
- [ ] `go build`, `go test -race`, `go vet` all pass
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
