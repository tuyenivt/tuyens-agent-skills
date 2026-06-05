---
name: go-onboard-map
description: Go onboarding signals - module layout, go.mod, framework (Gin/Echo/Chi), build tags, ORM (GORM/sqlx/pgx), observability stack.
metadata:
  category: backend
  tags: [onboarding, codebase-map, go, gin, modules]
user-invocable: false
---

# Go Onboard Map (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when stack is Go.

## When to Use

- A workflow needs Go-specific orientation: module layout, framework, build tags, DB layer, observability
- Project has `go.mod`

## Rules

- Identify Go version from `go.mod` (`go 1.x`); current toolchain range per Go release policy (last two majors are supported)
- Identify framework: Gin / Echo / Chi / Fiber / gorilla / net/http
- Identify DB: GORM / sqlx / pgx / database/sql + driver / ent / sqlc
- Identify layout convention (drives where new code lands)

## Build Inventory

| File              | What it tells you                                |
| ----------------- | ------------------------------------------------ |
| `go.mod`          | Module path, Go version, direct dependencies     |
| `go.sum`          | Dependency checksums                             |
| `Makefile` / `Taskfile.yml` | Project commands                       |
| `Dockerfile`      | Multi-stage build (builder -> distroless common) |
| `.golangci.yml`   | Lint coverage indicates quality bar              |
| `vendor/`         | Vendored deps if present                         |

## Bootstrap Path

1. Toolchain: `go.mod` directive matches `go version`
2. Deps: `go mod download`
3. Local services: `compose.yml`; env vars in `.env.example`
4. Migrations: golang-migrate (`migrate up`), goose, `AutoMigrate` (footgun), or sqlc + golang-migrate
5. Run: `go run ./cmd/<binary>` / `make run` / `air` for hot reload
6. Verify: `/health` or `/healthz`

## Package Layout

`cmd/<bin>/main.go` is always thin (config + wiring); business logic in `cmd/` is a smell.

| Convention                   | Shape                                                                  | When                                    |
| ---------------------------- | ---------------------------------------------------------------------- | --------------------------------------- |
| **Layer-package**            | `internal/handler/`, `service/`, `repository/`, `model/`               | Default for < ~5 domains; tutorials     |
| **Feature-package**          | `internal/orders/{handler,service,repository,model}.go`                | Recommended for medium+ services        |
| **DDD / hexagonal**          | `internal/<domain>/{domain,application,adapters}/`; domain has no framework imports | Teams enforcing hexagonal architecture  |
| **Monorepo multi-binary**    | `cmd/api/`, `cmd/worker/`, `cmd/migrate/` + shared `internal/`         | One repo serves API + Asynq workers     |

| Location                                  | Purpose                                       |
| ----------------------------------------- | --------------------------------------------- |
| `cmd/<binary>/main.go`                    | Entry; thin wire-up                           |
| `internal/`                               | App code, not importable externally           |
| `internal/server/`                        | Router, middleware                            |
| `internal/handler/` or `api/`             | HTTP handlers                                 |
| `internal/service/`                       | Business logic                                |
| `internal/repository/` or `store/`        | DB access                                     |
| `internal/domain/` or `model/`            | Entities, value objects                       |
| `pkg/`                                    | Reusable libraries (some teams skip entirely) |
| `migrations/`                             | SQL files                                     |
| `configs/`, `scripts/`                    | Config templates, bootstrap                   |

## Conventions

- Errors are values; wrap with `fmt.Errorf("ctx: %w", err)`
- `context.Context` as first param for I/O-bound functions
- Interfaces declared at the consumer (small, often inline)
- Constructor functions (`NewServer(...)`); no DI framework
- Functional options for configurable constructors
- Tests `_test.go` colocated; `testify` common but not universal

## Risk Hotspots (delegate depth to dedicated skills)

- Goroutine lifetime + cancellation -> `go-concurrency`, `task-go-review-perf`
- N+1, pool config, `AutoMigrate`, `defer rows.Close()`, `WithContext` -> `go-data-access`
- Asynq inside transactions, ORM models in payloads -> `go-messaging-patterns`
- Mass assignment, raw SQL, missing JWT -> `task-go-review-security`
- Migration safety on hot tables -> `go-migration-safety`
- Go quirks: default `http.Client` no timeout, `defer` in loops, `init()` doing heavy work, JSON tag mismatches, `init()`-wired globals breaking test isolation

## First-PR Safe Zones

- New handler in `internal/handler/`
- New service method following existing constructor pattern
- New `_test.go` colocated
- New `migrations/<timestamp>_*.sql`

Riskier: `cmd/<binary>/main.go`, middleware (applies globally), pool config, goroutine / context patterns.

## Ecosystem Currency

- Toolchain: read `go.mod` (see Rules); Go's release policy supports the last two majors
- Gin dominant; Chi gaining on stdlib alignment
- pgx 5+ for Postgres; sqlx for general database/sql; sqlc for type-safe generated SQL
- OpenTelemetry replacing custom metric/trace libs
- `slog` standard structured logger - replacing logrus/zap in new code

## Output

Inject into `task-onboard`:

**Stack and Tooling:** Go version, framework, DB layer, migration tool, logging, observability

**Local Bootstrap:** `go mod download`, env file, run command, default port, health path

**Architecture Map:** `cmd/`/`internal/`/`pkg/` layout, layer dirs, server file, DB setup

**Conventions:** error wrapping, context, constructors, options, test framework

**Risk Hotspots:** goroutine ownership, `http.Client` timeouts, `AutoMigrate`, `init()` side effects, race detector in CI

**First-PR Safe Zones:** scoped to observed structure

## Avoid

- Treating Go as having exceptions
- Recommending DI frameworks (constructor injection is idiomatic)
- Glossing over context propagation
- Confusing `pkg/` and `internal/` (the latter is compiler-enforced)
- Recommending logrus/zap for new 1.21+ projects (use `slog`)
