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
- Identify layout convention (drives where new code lands); when two fit, report the dominant one and note the secondary in parentheses
- Grep `//go:build` tags: tagged files and tests are invisible to default builds - report required `-tags` (integration suites are commonly gated this way)

## Build Inventory

| File              | What it tells you                                |
| ----------------- | ------------------------------------------------ |
| `go.mod`          | Module path, Go version, direct dependencies     |
| `go.work`         | Multi-module monorepo; local module resolution   |
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
6. Verify: `/health` or `/healthz`; if neither exists, first routed GET

## Package Layout

`cmd/<bin>/main.go` is always thin (config + wiring); business logic in `cmd/` is a smell.

| Convention                   | Shape                                                                  | When                                    |
| ---------------------------- | ---------------------------------------------------------------------- | --------------------------------------- |
| **Layer-package**            | `internal/handler/`, `service/`, `repository/`, `model/`               | Default for < ~5 domains; tutorials     |
| **Feature-package**          | `internal/orders/{handler,service,repository,model}.go`                | Recommended for medium+ services        |
| **DDD / hexagonal**          | `internal/<domain>/{domain,application,adapters}/`; domain has no framework imports | Teams enforcing hexagonal architecture  |
| **Monorepo multi-binary**    | `cmd/api/`, `cmd/worker/`, `cmd/migrate/` + shared `internal/`         | One repo serves API + Asynq workers     |

Monorepo multi-binary is orthogonal to the package convention - a feature-packaged monorepo is the common combination; report both.

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

Scope to the observed layout, not the generic defaults. For a feature-package repo, that means a new file in `internal/<domain>/`; for hexagonal, a new use case in `application/` or a new adapter.

Generic safe zones (replace with concrete equivalents from the tree):
- New handler in `internal/handler/`
- New service method following existing constructor pattern
- New `_test.go` colocated
- New `migrations/<version>_<desc>.up.sql` + `.down.sql` pair (golang-migrate format - see go-migration-safety)

Riskier: `cmd/<binary>/main.go`, middleware (applies globally), pool config, goroutine / context patterns.

## Ecosystem Currency

- Toolchain: read `go.mod` (see Rules); Go's release policy supports the last two majors
- Gin dominant; Chi gaining on stdlib alignment
- pgx 5+ for Postgres; sqlx for general database/sql; sqlc for type-safe generated SQL
- OpenTelemetry replacing custom metric/trace libs
- `slog` standard structured logger - replacing logrus/zap in new code

## Output

Inject into `task-onboard` as Markdown sections in this exact order and shape. Flag inferred items as `(inferred)` rather than fabricating values not in the tree.

```markdown
### Stack and Tooling
- **Go:** 1.23 (toolchain go1.23.4, within support window)
- **Framework:** Chi
- **DB:** sqlc + sqlx on pgx / Postgres 16
- **Migrations:** golang-migrate (`migrate up`)
- **Logging:** slog JSON; OTel for traces/metrics
- **Lint:** golangci-lint (govet, errcheck, staticcheck, revive, gosec)

### Local Bootstrap
- `go mod download`
- `cp .env.example .env`; set DB_DSN, REDIS_URL, OTEL_ENDPOINT, STRIPE_KEY
- `docker compose up -d` (postgres, redis, otel-collector)
- `make migrate-up`
- `go run ./cmd/api` -> http://localhost:8080/health
- `go run ./cmd/worker` for Asynq consumers

### Architecture Map
- Entry: `cmd/{api,worker,migrate,jobs}/main.go` (thin wire-up)
- App code: `internal/` (compiler-enforced boundary)
- Layout: **feature-package** under `internal/payments/`, `internal/refunds/`, `internal/webhooks/` (monorepo multi-binary on top)
- Server: `internal/server/router.go` (Chi + middleware)
- DB: `internal/db/` (sqlx + pgx); per-feature queries via sqlc in each `repo.go`
- Observability: `internal/obs/` (otel + slog setup)
- Shared utilities: `pkg/money/`

### Conventions
- Errors wrapped with `fmt.Errorf("ctx: %w", err)` (inferred from golangci errcheck)
- `context.Context` first param on I/O functions
- Constructors `NewX(...)`, no DI framework
- envconfig for config; `.env` for dev
- Tests `_test.go` colocated; assertion lib (inferred)

### Risk Hotspots
- Asynq dispatched from request path: ensure post-commit pattern (`go-messaging-patterns`)
- sqlc + sqlx coexistence: confirm pool ownership; check `WithContext` plumbing (`go-data-access`)
- Stripe webhook signature verification (`task-go-review-security`)
- pgx pool config under k8s replica scaling (`go-data-access`)
- Goroutine cancellation on graceful shutdown (`go-concurrency`)
- Migration safety on `payments` / `refunds` (`go-migration-safety`)

### First-PR Safe Zones
- New endpoint: add handler in `internal/payments/handler.go`, wire in `internal/server/router.go`
- New Asynq task: add type + handler in `internal/payments/tasks.go`
- New migration: `migrations/000042_<desc>.up.sql` + `.down.sql` (golang-migrate format)
- Avoid for first PR: `cmd/*/main.go`, `internal/server/middleware/`, `internal/db/`
```

## Avoid

- Treating Go as having exceptions
- Recommending DI frameworks (constructor injection is idiomatic)
- Glossing over context propagation
- Confusing `pkg/` and `internal/` (the latter is compiler-enforced)
- Recommending logrus/zap for new 1.21+ projects (use `slog`)
- Fabricating health paths, env var names, or default ports not visible in the tree - mark `(inferred)` or `(unknown)`
