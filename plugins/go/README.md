# Tuyen's Agent Skills - Go / Gin

Claude Code plugin for Go/Gin development.

## Stack

- Go 1.25+
- Gin
- GORM + sqlx (both)
- golang-migrate
- PostgreSQL

## Agents

| Agent                     | Description                                                                                                                                           |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `go-architect`            | Go architect for Gin, GORM/sqlx, clean architecture, and production Go patterns. Designs features, structures projects, makes architecture decisions. |
| `go-tech-lead`            | Go tech lead for code review, refactoring guidance, doc standards. Reviews for idiomatic Go, error handling, concurrency safety, and performance.     |
| `go-security-engineer`    | OWASP Top 10 for Go, JWT/Gin auth middleware review, input validation, govulncheck dependency scanning.                                               |
| `go-performance-engineer` | Goroutine leak detection, GORM/sqlx query tuning, pprof profiling, memory allocation analysis, connection pool sizing.                                |
| `go-test-engineer`        | Table-driven test strategies, httptest, Testcontainers, gomock, and `go test -race` discipline for Go/Gin services.                                   |

## Workflow Skills

| Skill                            | Agent                     | Description                                                                                                                                                          |
| -------------------------------- | ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-go-implement`              | `go-architect`            | End-to-end Go/Gin feature implementation. Generates migrations, models, repositories, services, handlers, middleware, and comprehensive tests.                       |
| `task-go-debug`                  | `go-tech-lead`            | Debug Go errors. Paste a panic stack trace, error log, or describe unexpected behavior. Classifies error, identifies root cause, suggests fix.                       |
| `task-go-review`                 | `go-tech-lead`            | Staff-level code review umbrella - Phases A-E with Gin / GORM / sqlx idioms; spawns perf / security / observability subagents in parallel for extra scopes.          |
| `task-go-review-perf`            | `go-performance-engineer` | Performance review for GORM / sqlx N+1, goroutine leaks, missing context, mutex contention, allocation hotspots, connection pool, Asynq throughput, migration safety.|
| `task-go-review-security`        | `go-security-engineer`    | Security review for Gin JWT middleware, ShouldBindJSON validation, SQL injection, mass assignment, command injection, path traversal, govulncheck, OWASP Go lens.    |
| `task-go-review-observability`   | `go-tech-lead`            | Observability review for slog, OpenTelemetry Go SDK, prometheus/client_golang, pprof endpoints, Asynq queue events, graceful shutdown, Sentry SDK.                   |
| `task-go-test`                   | `go-test-engineer`        | Test strategy and scaffolding using table-driven tests, httptest, Testcontainers PostgreSQL, gomock, Asynq test patterns, and `go test -race` discipline.            |
| `task-go-refactor`               | `go-tech-lead`            | Refactor planning for fat handlers, anemic services, goroutine leaks, GORM hook abuse, mass assignment, mutable state - with `go test -race` coverage gate.          |

## Atomic Skills

| Skill                   | Description                                                                                                                                        |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `go-error-handling`     | Go error patterns: explicit returns, wrapping with `%w`, sentinel errors, custom error types, `errors.Is/As`, Gin error middleware.                |
| `go-gin-patterns`       | Gin web framework patterns: routing groups, middleware, request binding with validation, consistent JSON responses, pagination, graceful shutdown. |
| `go-data-access`        | Go data access with GORM and sqlx. Model definition, associations, preloading, transactions, scopes, connection pooling.                           |
| `go-migration-safety`   | Safe migration patterns with golang-migrate and PostgreSQL. File naming, up/down pairs, zero-downtime DDL, embedding in Go binary.                 |
| `go-testing-patterns`   | Go testing: table-driven tests, httptest for Gin handlers, testcontainers-go for integration, testify, interface mocking, benchmarks, synctest.    |
| `go-concurrency`        | Go concurrency patterns: goroutine lifecycle, channels, context cancellation, errgroup, worker pools, sync primitives, `WaitGroup.Go`.             |
| `go-messaging-patterns` | Background jobs with Asynq, Kafka consumers with franz-go, and in-process worker pools.                                                            |
| `go-code-explain`       | Goroutines and channels, context.Context propagation, defer ordering, error wrapping, interface satisfaction, GORM/sqlx semantics - injected into `task-code-explain`. |
| `go-onboard-map`        | Module layout, go.mod, framework (Gin/Echo/Chi/std-lib), build tags, DB layer (GORM/sqlx/pgx), observability stack - injected into `task-onboard`. |

## Usage Examples

### Implement a feature end-to-end

```
> task-go-implement

Feature: Add payment processing with webhook endpoint
- Creates migration for payments table
- Repository with GORM for CRUD, sqlx for reporting query
- Service with Stripe integration and error wrapping
- Gin handlers with webhook signature validation
- Table-driven tests + httptest + testcontainers-go

→ Validates with go build, go test -race, go vet
```
