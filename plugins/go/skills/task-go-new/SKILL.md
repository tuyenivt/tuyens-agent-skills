---
name: task-go-new
description: End-to-end Go/Gin feature implementation workflow. Generates all layers from migration to HTTP handler with full test coverage. Use for new features requiring multiple coordinated layers. Not for single-file fixes or isolated bug fixes (use task-go-debug for errors).
agent: go-architect
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

STEP 1 - GATHER: feature, affected packages, external deps, concurrency needs

STEP 2 - DESIGN: propose structure, interfaces, data flow. Load go-gin-patterns, go-data-access. Present for approval.

STEP 3 - DATABASE: load go-migration-safety, generate migrations

STEP 4 - DATA LAYER: repository interface + impl (GORM and/or sqlx)

STEP 5 - BUSINESS LOGIC: service with constructor injection, error wrapping (load go-error-handling). If goroutines: load go-concurrency. If background jobs or async messaging: load go-messaging-patterns. For service-to-service calls: wrap with timeout (context.WithTimeout), classify errors (timeout vs not-found vs server error), map to HTTP status.

STEP 5.5 - EVENTS: If the feature must emit domain events (e.g., order.created), load go-messaging-patterns. Emit after transaction commit, not before.

STEP 6 - HTTP LAYER: Gin handlers, middleware, routes. Map domain errors to HTTP status codes: validation errors → 400, not found → 404, conflict → 409, external service timeout → 503.

STEP 7 - TESTS: load go-testing-patterns. Table-driven + httptest + testcontainers. Cover: happy path, validation errors, not-found, external service timeout.

STEP 8 - VALIDATE: go build, go test -race, go vet

OUTPUT: file list, endpoint summary, test count

## Self-Check

- [ ] Requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, repository, service, handler, routes, tests
- [ ] Constructor injection via function parameters; errors wrapped with `fmt.Errorf("%w")`
- [ ] No goroutine leaks; repository interface defined in service layer
- [ ] `go build`, `go test -race`, and `go vet` all pass
- [ ] Migration includes indexes; list endpoints paginated; file list and test count presented

> Run `/task-skill-feedback` if output needed significant correction.
