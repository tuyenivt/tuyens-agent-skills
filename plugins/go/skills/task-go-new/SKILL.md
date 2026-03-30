---
name: task-go-new
description: End-to-end Go/Gin feature implementation workflow. Generates all layers from migration to HTTP handler with full test coverage. Not for single-file changes, isolated bug fixes, or simple scaffolding tasks.
agent: go-architect
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

# Implement Go Feature

## When to Use

- Implementing a new Go/Gin feature end-to-end (migration, model, repository, service, handler, tests)
- Scaffolding a complete CRUD or domain-specific resource with Go idioms
- Adding a new domain aggregate with REST API, persistence, background jobs, and test coverage
- Any daily coding task that requires coordinated generation of multiple Go/Gin layers

Not for single-file changes (edit directly), isolated bug fixes (use `task-go-debug`), or frontend work.

## Edge Cases

- **Partial input**: User gives a vague feature name without details. Ask targeted questions in STEP 1 - never guess field names, types, or relationships
- **No database**: Feature has no persistence (e.g., external API aggregation). Skip STEP 3 (migration) and STEP 4 (data layer). Generate service and handler only
- **Existing entity**: User says "add endpoints for Order" and the model already exists. Read the existing model and extend rather than creating a new one. Check for existing DTOs and repositories too
- **Referenced entity doesn't exist**: Design references another entity (e.g., `User`) that isn't in the codebase yet. Ask the user whether to create it or use a plain ID reference
- **Webhook-only feature**: No CRUD endpoints needed, only a webhook receiver (e.g., Stripe, GitHub). Skip standard CRUD handler generation; generate a dedicated webhook handler with raw body reading and signature validation middleware
- **State machine transitions**: Feature has explicit status transitions (e.g., pending -> completed). Generate transition validation in the service layer and a CHECK constraint in the migration
- **Idempotency requirements**: Feature needs deduplication (e.g., payment processing). Add a unique idempotency key column, use `ON CONFLICT` upsert, and validate in the service layer
- **Bulk operations**: User needs batch create/update/delete. Use `db.Transaction` with batch `Create`, add a dedicated bulk endpoint, and validate collection size limits

## Rules

- No business logic in handlers - handlers orchestrate, services execute
- Constructor injection via function parameters - no global state or init()
- Errors wrapped with `fmt.Errorf("context: %w", err)` at every layer
- Repository interface defined in the service package (consumer defines its dependency)
- Transactions for multi-model mutations - `db.Transaction(func(tx *gorm.DB) error { ... })`
- Event/job dispatch timing: emit domain events or enqueue background jobs AFTER the transaction commits, never inside it. If the job fires before commit, the worker may read stale data or a missing row
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code

## Workflow

### STEP 1 - DETECT STACK AND GATHER REQUIREMENTS (MANDATORY)

Use skill: `stack-detect` to confirm the project is Go/Gin and identify framework versions, database, and project layout conventions.

Ask the user these questions before writing any code:

1. What is the feature? (brief description, primary use case)
2. What are the main entities? (fields, relationships, constraints)
3. Are there external integrations? (third-party APIs, webhooks, callbacks)
4. Are background jobs or async events needed? (notifications, syncing)
5. Does the feature need authentication/authorization?
6. Are there status transitions? (e.g., order: pending -> confirmed -> shipped)
7. Concurrency needs? (goroutines, worker pools, rate limiting)
8. Idempotency requirements? (deduplication keys, exactly-once processing)
9. Are there webhook or callback endpoints from external services? (signature validation, raw body parsing)

Do not continue until requirements are complete. If the user provides incomplete input, ask targeted clarifying questions.

### STEP 2 - DESIGN (MANDATORY APPROVAL GATE)

Use skill: `go-gin-patterns` for API/handler design. Use skill: `go-data-access` for data layer design. Propose the implementation layers and present for user approval before generating code.

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

Design decisions to present:

- Endpoints (method, URI, status codes, request/response DTOs)
- Entity model + DB schema changes (indexes, constraints, CHECK constraints for status fields)
- Service methods and transaction boundaries
- Error model (sentinel errors, custom error types)
- Idempotency strategy (if applicable)
- Webhook handler design (if applicable): raw body reading, signature validation middleware, event type routing
- Background job dispatch points (after which transaction commits)

Only generate code after user approves design.

### STEP 3 - DATABASE

Use skill: `go-migration-safety`. Generate up/down SQL migration files. Include indexes on foreign keys and frequently-filtered columns.

For status fields with known transitions, add a CHECK constraint:

```sql
ALTER TABLE payments ADD CONSTRAINT payments_status_check
    CHECK (status IN ('pending', 'processing', 'completed', 'failed'));
```

For idempotency keys, add a unique index:

```sql
CREATE UNIQUE INDEX idx_payments_idempotency_key ON payments(idempotency_key);
```

### STEP 4 - DATA LAYER

Use skill: `go-data-access`. Generate repository interface (in service package) and implementation. Use GORM for CRUD with associations, sqlx for complex reporting queries. Configure connection pool immediately after opening.

For idempotency, implement upsert with `ON CONFLICT`:

```go
func (r *paymentRepo) CreateIdempotent(ctx context.Context, payment *Payment) (*Payment, error) {
    result := r.db.WithContext(ctx).
        Clauses(clause.OnConflict{
            Columns:   []clause.Column{{Name: "idempotency_key"}},
            DoNothing: true,
        }).Create(payment)
    if result.RowsAffected == 0 {
        // Already exists - fetch and return the existing record
        return r.FindByIdempotencyKey(ctx, payment.IdempotencyKey)
    }
    return payment, result.Error
}
```

### STEP 5 - SERVICE

Use skill: `go-error-handling`. Generate service with constructor injection. Wrap errors with context at every return. Use `db.Transaction` for multi-step mutations.

For status transitions, validate transitions in the service layer before persisting:

```go
var validTransitions = map[string][]string{
    "pending":    {"processing"},
    "processing": {"completed", "failed"},
}

func (s *paymentService) Transition(ctx context.Context, id string, newStatus string) error {
    payment, err := s.repo.FindByID(ctx, id)
    if err != nil {
        return fmt.Errorf("paymentService.Transition id=%s: %w", id, err)
    }
    allowed, ok := validTransitions[payment.Status]
    if !ok || !slices.Contains(allowed, newStatus) {
        return fmt.Errorf("invalid transition %s -> %s: %w", payment.Status, newStatus, ErrInvalidTransition)
    }
    // ...
}
```

- If goroutines needed: Use skill: `go-concurrency`
- If background jobs or events needed: Use skill: `go-messaging-patterns`. Dispatch after transaction commit, not inside it.
- For external API calls (e.g., Stripe, payment gateways): wrap with `context.WithTimeout`, classify errors (timeout -> 503, not-found -> 404, server error -> 500), and use an interface for testability:

```go
type PaymentGateway interface {
    Charge(ctx context.Context, req ChargeRequest) (*ChargeResult, error)
}

func (s *paymentService) ProcessPayment(ctx context.Context, req ProcessRequest) error {
    ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
    defer cancel()

    result, err := s.gateway.Charge(ctx, ChargeRequest{...})
    if err != nil {
        return fmt.Errorf("paymentService.ProcessPayment: %w", err)
    }
    // ...
}
```

### STEP 6 - HTTP LAYER

Use skill: `go-gin-patterns`. Gin handlers with `ShouldBindJSON` for request binding, consistent response envelope, pagination on list endpoints. Map domain errors to HTTP status codes:

| Domain Error         | HTTP Status |
| -------------------- | ----------- |
| Validation failure   | 400         |
| Not found            | 404         |
| Conflict (duplicate) | 409         |
| Unauthorized         | 401         |
| Invalid transition   | 422         |
| External timeout     | 503         |

For webhook endpoints (Stripe, GitHub, etc.), use raw body reading with signature validation middleware:

```go
// Middleware: validate webhook signature before handler runs
func WebhookSignatureMiddleware(secret string) gin.HandlerFunc {
    return func(c *gin.Context) {
        body, err := c.GetRawData()
        if err != nil {
            c.AbortWithStatusJSON(http.StatusBadRequest, ErrorResponse{Error: "invalid body"})
            return
        }
        sig := c.GetHeader("Stripe-Signature")
        if _, err := webhook.ConstructEvent(body, sig, secret); err != nil {
            c.AbortWithStatusJSON(http.StatusUnauthorized, ErrorResponse{Error: "invalid signature"})
            return
        }
        // Store raw body for handler to parse events from
        c.Set("webhook_body", body)
        c.Next()
    }
}

// Handler: reads pre-validated body from context
func HandleStripeWebhook(svc PaymentService) gin.HandlerFunc {
    return func(c *gin.Context) {
        body := c.MustGet("webhook_body").([]byte)
        var event stripe.Event
        if err := json.Unmarshal(body, &event); err != nil {
            c.JSON(http.StatusBadRequest, ErrorResponse{Error: "invalid event"})
            return
        }
        if err := svc.HandleWebhookEvent(c.Request.Context(), event); err != nil {
            c.Error(err)
            return
        }
        c.JSON(http.StatusOK, gin.H{"received": true})
    }
}
```

### STEP 7 - TESTS

Use skill: `go-testing-patterns`. Table-driven tests + httptest + testcontainers. Cover: happy path, validation errors, not-found, conflict, external service timeout.

For features with state machines, test all valid and invalid transitions:

```go
{name: "valid transition pending->processing", from: "pending", to: "processing", wantErr: false},
{name: "invalid transition pending->completed", from: "pending", to: "completed", wantErr: true},
```

For webhook handlers, test signature validation (valid sig, invalid sig, missing sig, replay attack with old timestamp).

For idempotency, test that duplicate requests return the same result without creating duplicate records.

### STEP 8 - VALIDATE

Run `go build ./...`, `go test -race ./...`, `go vet ./...`. Fix any failures before presenting output.

## Output Format

```markdown
## Files Generated

[grouped file list by layer: models, repository, service, handler, dto, tests, migrations]

## Endpoints

| Method | Path                    | Request            | Response                                  | Status |
| ------ | ----------------------- | ------------------ | ----------------------------------------- | ------ |
| POST   | /api/v1/orders          | CreateOrderRequest | SuccessResponse{Order}                    | 201    |
| GET    | /api/v1/orders          | query params       | SuccessResponse{[]Order} + PaginationMeta | 200    |
| GET    | /api/v1/orders/:id      | -                  | SuccessResponse{Order}                    | 200    |
| PATCH  | /api/v1/orders/:id      | UpdateOrderRequest | SuccessResponse{Order}                    | 200    |
| DELETE | /api/v1/orders/:id      | -                  | -                                         | 204    |
| POST   | /api/v1/webhooks/stripe | raw body           | {"received": true}                        | 200    |

## Tests

- Unit tests: {count} (service layer)
- Handler tests: {count} (httptest)
- Integration tests: {count} (testcontainers)

## Migration

[migration file names and what they create: tables, indexes, constraints, CHECK constraints]
```

## Self-Check

- [ ] Stack detected and requirements gathered; design approved before any code generated
- [ ] All layers generated: migration, model, repository, service, handler, routes, tests
- [ ] Constructor injection via function parameters; errors wrapped with `fmt.Errorf("%w")`
- [ ] No goroutine leaks; repository interface defined in service layer
- [ ] Background jobs dispatched after transaction commit, not inside it
- [ ] Status transitions validated in service layer; CHECK constraint in migration (if applicable)
- [ ] Idempotency key with unique index and upsert logic (if applicable)
- [ ] Webhook signature validation in middleware; raw body reading before JSON parse (if applicable)
- [ ] External API calls wrapped with `context.WithTimeout` and behind an interface
- [ ] `go build`, `go test -race`, and `go vet` all pass
- [ ] Migration includes indexes; list endpoints paginated; output template filled

## Avoid

- Business logic in Gin handlers (delegate to service layer)
- Dispatching background jobs inside a DB transaction (worker races the commit)
- Global database connections or `init()` for dependency setup (use constructor injection)
- `AutoMigrate` in production (use versioned SQL migration files)
- Returning raw GORM models from endpoints (use response DTOs)
- Skipping pagination on list endpoints
- Generating code before user approves the design
- Using `ShouldBindJSON` on webhook endpoints (consumes the body, breaks signature validation)
- Allowing invalid status transitions without service-layer validation
