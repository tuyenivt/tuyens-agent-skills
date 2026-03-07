---
name: task-go-new
description: "End-to-end Go/Gin feature implementation. Generates migrations, models, repositories, services, handlers, middleware, and comprehensive tests from a feature description."
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

STEP 5 - BUSINESS LOGIC: service with constructor injection, error wrapping (load go-error-handling). If goroutines: load go-concurrency. If background jobs or async messaging: load go-messaging-patterns.

STEP 6 - HTTP LAYER: Gin handlers, middleware, routes

STEP 7 - TESTS: load go-testing-patterns. Table-driven + httptest + testcontainers.

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
