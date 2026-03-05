---
name: task-go-new
description: "End-to-end Go/Gin feature implementation. Generates migrations, models, repositories, services, handlers, middleware, and comprehensive tests from a feature description."
agent: go-architect
---

STEP 1 - GATHER: feature, affected packages, external deps, concurrency needs

STEP 2 - DESIGN: propose structure, interfaces, data flow. Load go-gin-patterns, go-data-access. Present for approval.

STEP 3 - DATABASE: load go-migration-safety, generate migrations

STEP 4 - DATA LAYER: repository interface + impl (GORM and/or sqlx)

STEP 5 - BUSINESS LOGIC: service with constructor injection, error wrapping (load go-error-handling). If goroutines: load go-concurrency. If background jobs or async messaging: load go-messaging-patterns.

STEP 6 - HTTP LAYER: Gin handlers, middleware, routes

STEP 7 - TESTS: load go-testing-patterns. Table-driven + httptest + testcontainers.

STEP 8 - VALIDATE: go build, go test -race, go vet

OUTPUT: file list, endpoint summary, test count

## Success Criteria

A well-executed feature implementation passes all of these. Use as a self-check before presenting to the user.

### Completeness

- [ ] Requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, repository, service, handler, routes, tests
- [ ] Validated with `go build`, `go test -race`, and `go vet`

### Go Correctness

- [ ] Constructor injection via function parameters - no global state or `init()` wiring
- [ ] Errors wrapped with `fmt.Errorf("%w")` - not swallowed or logged and returned
- [ ] No goroutine leaks - all goroutines have a cancellation or completion path
- [ ] Repository interface defined in the service layer - not the infrastructure layer
- [ ] Table-driven tests used for unit tests; `httptest` for handler tests; Testcontainers for DB

### Staff-Level Signal

- [ ] Migration includes indexes for foreign keys and filter columns
- [ ] List endpoints include pagination
- [ ] `go test -race` passes - no data races introduced
- [ ] File list, endpoint summary, and test count presented to user
