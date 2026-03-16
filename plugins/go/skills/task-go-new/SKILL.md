---
name: task-go-new
description: End-to-end Go/Gin feature implementation workflow. Generates all layers from migration to HTTP handler with full test coverage.
agent: go-architect
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

## Rules

- No business logic in handlers - handlers orchestrate, services execute
- Constructor injection via function parameters - no global state or init()
- Errors wrapped with `fmt.Errorf("context: %w", err)` at every layer
- Repository interface defined in the service package (consumer defines its dependency)
- Transactions for multi-model mutations - `db.Transaction(func(tx *gorm.DB) error { ... })`
- Event/job dispatch timing: emit domain events or enqueue background jobs AFTER the transaction commits, never inside it. If the job fires before commit, the worker may read stale data or a missing row
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code

## Implementation

STEP 1 - GATHER: Ask the user these questions before writing any code:

1. What is the feature? (brief description, primary use case)
2. What are the main entities? (fields, relationships, constraints)
3. Are there external integrations? (third-party APIs, message brokers)
4. Are background jobs or async events needed? (notifications, syncing)
5. Does the feature need authentication/authorization?
6. Are there status transitions? (e.g., order: pending -> confirmed -> shipped)
7. Concurrency needs? (goroutines, worker pools, rate limiting)

STEP 2 - DESIGN: Use skill: `go-gin-patterns` for API/handler design. Use skill: `go-data-access` for data layer design. Propose the implementation layers and present for user approval before generating code.

Present a file tree showing what will be generated:

```
internal/
  model/order.go                 # GORM model
  repository/order.go            # Repository interface + impl
  service/order.go               # Business logic
  handler/order.go               # Gin handlers
  middleware/auth.go             # Auth middleware (if needed)
  dto/order.go                   # Request/response types
cmd/
  api/main.go                   # Wire dependencies
migrations/
  000X_create_orders.up.sql
  000X_create_orders.down.sql
internal/
  handler/order_test.go          # Handler tests (httptest)
  service/order_test.go          # Service unit tests
  repository/order_test.go       # Integration tests (testcontainers)
```

STEP 3 - DATABASE: Use skill: `go-migration-safety`. Generate up/down SQL migration files. Include indexes on foreign keys and frequently-filtered columns.

STEP 4 - DATA LAYER: Use skill: `go-data-access`. Generate repository interface (in service package) and implementation. Use GORM for CRUD with associations, sqlx for complex reporting queries. Configure connection pool immediately after opening.

STEP 5 - SERVICE: Use skill: `go-error-handling`. Generate service with constructor injection. Wrap errors with context at every return. Use `db.Transaction` for multi-step mutations.

- If goroutines needed: Use skill: `go-concurrency`
- If background jobs or events needed: Use skill: `go-messaging-patterns`. Dispatch after transaction commit, not inside it.
- For service-to-service calls: wrap with `context.WithTimeout`, classify errors (timeout -> 503, not-found -> 404, server error -> 500)

STEP 6 - HTTP LAYER: Use skill: `go-gin-patterns`. Gin handlers with `ShouldBindJSON` for request binding, consistent response envelope, pagination on list endpoints. Map domain errors to HTTP status codes:

| Domain Error | HTTP Status |
|---|---|
| Validation failure | 400 |
| Not found | 404 |
| Conflict (duplicate) | 409 |
| Unauthorized | 401 |
| External timeout | 503 |

STEP 7 - TESTS: Use skill: `go-testing-patterns`. Table-driven tests + httptest + testcontainers. Cover: happy path, validation errors, not-found, conflict, external service timeout.

STEP 8 - VALIDATE: Run `go build ./...`, `go test -race ./...`, `go vet ./...`. Fix any failures before presenting output.

## Output

```markdown
## Files Generated
[grouped file list by layer: models, repository, service, handler, dto, tests, migrations]

## Endpoints

| Method | Path | Request | Response | Status |
|--------|------|---------|----------|--------|
| POST   | /api/v1/orders | CreateOrderRequest | SuccessResponse{Order} | 201 |
| GET    | /api/v1/orders | query params | SuccessResponse{[]Order} + PaginationMeta | 200 |
| GET    | /api/v1/orders/:id | - | SuccessResponse{Order} | 200 |
| PATCH  | /api/v1/orders/:id | UpdateOrderRequest | SuccessResponse{Order} | 200 |
| DELETE | /api/v1/orders/:id | - | - | 204 |

## Tests
- Unit tests: {count} (service layer)
- Handler tests: {count} (httptest)
- Integration tests: {count} (testcontainers)

## Migration
[migration file names and what they create: tables, indexes, constraints]
```

## Avoid

- Business logic in Gin handlers (delegate to service layer)
- Dispatching background jobs inside a DB transaction (worker races the commit)
- Global database connections or `init()` for dependency setup (use constructor injection)
- `AutoMigrate` in production (use versioned SQL migration files)
- Returning raw GORM models from endpoints (use response DTOs)
- Skipping pagination on list endpoints
- Generating code before user approves the design

## Self-Check

- [ ] Requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, repository, service, handler, routes, tests
- [ ] Constructor injection via function parameters; errors wrapped with `fmt.Errorf("%w")`
- [ ] No goroutine leaks; repository interface defined in service layer
- [ ] Background jobs dispatched after transaction commit, not inside it
- [ ] `go build`, `go test -race`, and `go vet` all pass
- [ ] Migration includes indexes; list endpoints paginated; output template filled
