---
name: task-go-implement
description: End-to-end Go / Gin feature implementation: generates migration, repository, service, handler layers with full test coverage.
agent: go-architect
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles` and `stack-detect`. Follow its contract; skip GATHER (and DESIGN when `plan.md` is present). Never edit spec artifacts; surface conflicts as proposed amendments.

# Implement Go Feature

## When to Use

End-to-end Go/Gin feature work: migration + model + repository + service + handler + tests in one pass.

Not for: single-file edits (edit directly), bugfixes (`task-go-debug`), frontend.

## Rules

- Handlers orchestrate, services execute; no business logic in handlers
- Constructor injection via function parameters; no globals or `init()`
- Errors wrapped with `fmt.Errorf("context: %w", err)` at every layer
- Repository interface declared in the **service** package (consumer-defined)
- Multi-model writes use `db.Transaction(...)`
- Background jobs / events dispatched **after** the transaction returns nil, never inside it
- Each step completes before the next; design approved before code

## Workflow

### STEP 1 - DETECT AND GATHER

Use skill: `stack-detect`. Confirm Go/Gin and project layout.

Ask the user before writing code:

1. Feature description and primary use case
2. Entities, fields, relationships, constraints
3. External integrations (third-party APIs, webhooks)
4. Background jobs or async events
5. Authentication / authorization
6. Status transitions
7. Concurrency requirements
8. Idempotency requirements
9. Webhook endpoints (signature validation, raw body)

Ask targeted clarifying questions for any gap. Do not guess.

### STEP 2 - DESIGN (APPROVAL GATE)

Use skill: `go-gin-patterns` for API design. Use skill: `go-data-access` for data layer design.

Present a file tree and these decisions:

- Endpoints (method, URI, status codes, DTOs)
- Schema (indexes, FKs, CHECK constraints, idempotency unique index)
- Service methods and transaction boundaries
- Error model (sentinels, custom types)
- Idempotency strategy (if applicable)
- Webhook design (if applicable): signature middleware, raw body, route group outside JWT auth
- Background job dispatch points (which transaction commit triggers them)

Wait for approval before generating code.

### STEP 3 - DATABASE

Use skill: `go-migration-safety`. Generate up/down migration files. Index FKs and frequently-filtered columns. For status fields with known values, add a CHECK constraint. For idempotency keys, add a unique index.

### STEP 4 - DATA LAYER

Use skill: `go-data-access`. Generate the repository interface in the service package and the GORM/sqlx implementation. Configure the connection pool immediately after open. For idempotency, use the canonical `clause.OnConflict{DoNothing: true}` upsert.

### STEP 5 - SERVICE

Use skill: `go-error-handling`. Generate the service with constructor injection. Wrap errors at every return. Use `db.Transaction` for multi-step writes.

For status transitions, validate in the service before persisting (a `validTransitions` map keyed by from-state).

For concurrency: Use skill: `go-concurrency`.
For background jobs / events: Use skill: `go-messaging-patterns`. Dispatch after the transaction returns nil.
For external API calls: wrap with `context.WithTimeout`, classify errors at the gateway boundary, define the gateway as an interface for testability.

### STEP 6 - HTTP LAYER

Use skill: `go-gin-patterns`. Gin handlers with `ShouldBindJSON`, consistent response envelope, pagination. Map domain errors to HTTP via centralized error middleware:

| Domain Error | HTTP |
|--------------|------|
| Validation | 400 |
| Unauthorized | 401 |
| Not found | 404 |
| Conflict | 409 |
| Invalid transition | 422 |
| External timeout | 503 |

For webhooks: signature middleware reads `c.GetRawData()` before any binding, in a route group **outside** the JWT auth group.

### STEP 7 - TESTS

Use skill: `go-testing-patterns`. Table-driven + httptest + testcontainers. Cover happy path, validation, not-found, conflict, timeout. For state machines, table-test every valid + invalid transition. For webhooks, test valid / invalid / missing signature. For idempotency, test that duplicates return the same result.

### STEP 8 - VALIDATE

Run `go build ./...`, `go test -race ./...`, `go vet ./...`. Fix failures before reporting done.

## Edge Cases

- **Vague input**: ask targeted questions in STEP 1; never guess fields or relationships
- **No persistence**: skip STEPs 3-4; service + handler only
- **Existing entity**: read and extend rather than recreate
- **Referenced entity missing**: ask whether to create it or use an ID reference
- **Webhook-only**: skip CRUD; signature middleware + dedicated handler
- **State transitions**: service-layer validation + DB CHECK constraint
- **Idempotency**: unique key column + `ON CONFLICT` upsert + service-layer guard
- **Bulk operations**: `db.Transaction` + batch create + size-limit validation

## Output Format

```markdown
## Files Generated
[grouped by layer]

## Endpoints
| Method | Path | Request | Response | Status |
| ... |

## Tests
- Unit: {count}
- Handler: {count}
- Integration: {count}

## Migration
[file names + what they create]
```

## Self-Check

- [ ] Stack detected; requirements gathered; design approved before code
- [ ] All layers generated; repository interface in service package
- [ ] Errors wrapped with `%w`; constructor injection throughout
- [ ] Background jobs dispatched after transaction commit
- [ ] Status transitions validated (service + DB CHECK) when applicable
- [ ] Idempotency: unique index + `ON CONFLICT` upsert when applicable
- [ ] Webhook: signature middleware reads raw body, outside JWT group when applicable
- [ ] External API calls: `context.WithTimeout` + interface for testability
- [ ] `go build`, `go test -race`, `go vet` all pass
- [ ] List endpoints paginated

## Avoid

- Business logic in handlers
- Background jobs inside `db.Transaction`
- Global DB connections; `init()` for wiring
- `AutoMigrate` in production
- Returning GORM models from handlers (use response DTOs)
- Unbounded list endpoints
- Generating code before design approval
- `ShouldBindJSON` on webhook endpoints (consumes body)
- Allowing invalid state transitions
