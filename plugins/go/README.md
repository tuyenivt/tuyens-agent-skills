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
| `go-engineer`             | Go 1.25+ engineer for Gin, GORM/sqlx - builds features end-to-end: migrations, repositories, services, handlers, middleware, tests. Debugs panics, races, GORM errors. |
| `go-tech-lead`            | Go tech lead for code review, refactoring guidance, doc standards. Reviews for idiomatic Go, error handling, concurrency safety, and performance.     |
| `go-security-engineer`    | OWASP Top 10 for Go, JWT/Gin auth middleware review, input validation, govulncheck dependency scanning.                                               |
| `go-performance-engineer` | Goroutine leak detection, GORM/sqlx query tuning, pprof profiling, memory allocation analysis, connection pool sizing.                                |
| `go-observability-engineer` | Structured logging (slog JSON), OpenTelemetry SDK + auto-instrumentation, prometheus/client_golang metrics, context correlation, pprof, graceful shutdown, Sentry SDK wiring. |
| `go-reliability-engineer` | Context deadlines, sony/gobreaker + cenkalti/backoff retries, errgroup/semaphore bounding, idempotency + transactional outbox, goroutine-leak & channel-backpressure control, graceful shutdown. |
| `go-test-engineer`        | Table-driven test strategies, httptest, Testcontainers, gomock, and `go test -race` discipline for Go/Gin services.                                   |

## Workflow Skills

| Skill                            | Agent                     | Description                                                                                                                                                          |
| -------------------------------- | ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-go-implement`              | `go-engineer`             | End-to-end Go/Gin feature implementation. Generates migrations, models, repositories, services, handlers, middleware, and comprehensive tests.                       |
| `task-go-review`                 | `go-tech-lead`            | Staff-level code review umbrella - Phases A-E with Gin / GORM / sqlx idioms; spawns perf / security / observability subagents in parallel for extra scopes.          |
| `task-go-review-perf`            | `go-performance-engineer` | Performance review for GORM / sqlx N+1, goroutine leaks, missing context, mutex contention, allocation hotspots, connection pool, Asynq throughput, migration safety.|
| `task-go-review-security`        | `go-security-engineer`    | Security review for Gin JWT middleware, ShouldBindJSON validation, SQL injection, mass assignment, command injection, path traversal, govulncheck, OWASP Go lens.    |
| `task-go-review-observability`   | `go-observability-engineer` | Observability review for slog, OpenTelemetry Go SDK, prometheus/client_golang, pprof endpoints, Asynq queue events, graceful shutdown, Sentry SDK.                   |
| `task-go-review-reliability`     | `go-reliability-engineer` | Reliability review for context timeouts/deadlines, sony/gobreaker + cenkalti/backoff retries, errgroup fan-out, goroutine leaks, channel backpressure, database/sql pool bounds, idempotency/outbox, graceful shutdown. |
| `task-go-test`                   | `go-test-engineer`        | Test strategy and scaffolding using table-driven tests, httptest, Testcontainers PostgreSQL, gomock, Asynq test patterns, and `go test -race` discipline.            |

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
| `go-onboard-map`        | Module layout, go.mod, framework (Gin/Echo/Chi/std-lib), build tags, DB layer (GORM/sqlx/pgx), observability stack - injected into `task-onboard`. |
| `go-overengineering-review` | Necessity review: `binding:` / service-layer validation duplicating GORM / DB constraints, defensive nil after non-nil constructors, `if err != nil { return nil }` silent swallows, single-impl interfaces declared at the implementation (interfaces at the consumer are idiomatic) / `BaseRepository` embedding / speculative config / `Result[T]` over `(T, error)`, naked `go fn()` wrapping sequential calls, field-less custom error types where `errors.New` sentinels suffice. Composed into `task-go-review` Phase D. |
| `go-security-patterns`  | Go/Gin security pattern bank: default-deny router, JWT (RS256, `iss`/`aud`/`exp`, alg pinning), Gin auth middleware shape, IDOR scoping at the repository, mass-assignment prevention, SQL parameterization, path traversal, command injection, webhook signature verification, password hashing, secrets, SSRF, `crypto/rand`, `InsecureSkipVerify`. Composed into `go-tech-lead`, `go-security-engineer`, `task-go-implement`, `task-go-review-security`. |
| `go-idioms`             | Go language idioms: `iota` enums + Stringer, struct tag ordering, functional options, generics (when they help), type-safe IDs (`type UserID int64`), embedding vs composition, `defer` evaluation rules and the loop antipattern, Stringer / Marshaler / `LogValuer` / `Value`/`Scan`, `go:embed` for migrations and templates. Composed into `task-go-implement`. |

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
