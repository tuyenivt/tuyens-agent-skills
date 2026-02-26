---
name: task-go-implement-feature
description: "End-to-end Go/Gin feature implementation. Generates migrations, models, repositories, services, handlers, middleware, and comprehensive tests from a feature description."
agent: go-architect
---

STEP 1 — GATHER: feature, affected packages, external deps, concurrency needs

STEP 2 — DESIGN: propose structure, interfaces, data flow. Load go-gin-patterns, go-data-access. Present for approval.

STEP 3 — DATABASE: load go-migration-safety, generate migrations

STEP 4 — DATA LAYER: repository interface + impl (GORM and/or sqlx)

STEP 5 — BUSINESS LOGIC: service with constructor injection, error wrapping (load go-error-handling). If goroutines: load go-concurrency.

STEP 6 — HTTP LAYER: Gin handlers, middleware, routes

STEP 7 — TESTS: load go-testing-patterns. Table-driven + httptest + testcontainers.

STEP 8 — VALIDATE: go build, go test -race, go vet

OUTPUT: file list, endpoint summary, test count
