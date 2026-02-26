---
name: task-go-new
description: "Create a new Go/Gin resource endpoint. Generates model, repository (GORM or sqlx), service, handler, route registration, golang-migrate migration, and table-driven tests."
agent: go-architect
---

STEP 1 — GATHER (interactive):

- Resource name (Order, Payment)
- Fields with Go types (Total float64, Status string, CustomerID uint)
- Data access: GORM, sqlx, or both
- Operations: full CRUD or subset
- Concurrency needs? (background processing)

STEP 2 — MIGRATION:
Load skill: go-migration-safety

- Generate {version}_create_{table}.up.sql and .down.sql

STEP 3 — MODEL:
Go struct with GORM tags or sqlx db tags based on choice

STEP 4 — REPOSITORY:
Load skill: go-data-access

- Interface definition in service package (accept interfaces)
- Implementation in repository package (return structs)

STEP 5 — SERVICE:
Load skill: go-error-handling

- Business logic, constructor injection, error wrapping

STEP 6 — HANDLER:
Load skill: go-gin-patterns

- Gin handlers with binding/validation, consistent response format

STEP 7 — ROUTES:
Register in router group under /api/v1

STEP 8 — TESTS:
Load skill: go-testing-patterns

- Table-driven service tests
- httptest handler tests
- testcontainers-go repository tests (if integration)

STEP 9 — VALIDATE:
go build ./... && go test -race ./... && go vet ./...

OUTPUT: file checklist in standard project layout
