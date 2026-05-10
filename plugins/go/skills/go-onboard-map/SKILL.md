---
name: go-onboard-map
description: Go project onboarding signals: module layout, go.mod, framework (Gin/Echo/Chi), build tags, ORM (GORM/sqlx/pgx), observability stack.
metadata:
  category: backend
  tags: [onboarding, codebase-map, go, gin, modules]
user-invocable: false
---

# Go Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is Go.

## When to Use

- A workflow needs Go-specific orientation: module layout, framework choice, build tags, DB layer, observability stack.
- Project has `go.mod`.

## Rules

- Identify Go version (`go.mod` `go 1.x` directive); 1.22+ is current standard, 1.25 latest.
- Identify framework: Gin, Echo, Chi, Fiber, gorilla/mux, or net/http standard library. Layout differs.
- Identify DB layer: GORM (`gorm.io/gorm`), sqlx (`jmoiron/sqlx`), pgx (`jackc/pgx/v5`), database/sql + driver, ent.
- Identify project layout convention: standard `cmd/<binary>/main.go` + `internal/`, or flat layout, or domain-driven `pkg/`+`internal/`.

## Patterns

### Build Inventory

| File          | What it tells you                                                                  |
| ------------- | ---------------------------------------------------------------------------------- |
| `go.mod`      | Module path, Go version directive, direct dependencies                              |
| `go.sum`      | Cryptographic checksums of dependencies                                             |
| `Makefile`    | Common project commands (build, test, lint, run)                                    |
| `Taskfile.yml` | Alternative to Makefile (Task runner)                                              |
| `Dockerfile`  | Multi-stage build common: builder image -> distroless                               |
| `.golangci.yml` | golangci-lint config; linter coverage indicates code-quality bar                  |
| `tools.go`    | Tool dependency tracking (legacy pattern)                                           |
| `vendor/`     | Vendored deps; check `go.mod` for `// vendor` directive                            |

### Bootstrap Path

1. Go toolchain: confirm `go.mod` directive matches `go version`. Use `goenv` or version manager.
2. Dependencies: `go mod download` (no install step needed).
3. Local services: `compose.yml` for DB/Redis; required env vars in `.env.example`.
4. Migrations:
   - **golang-migrate:** `migrate -path ./migrations -database "$DATABASE_URL" up`.
   - **goose:** `goose -dir migrations postgres "$DATABASE_URL" up`.
   - **GORM AutoMigrate:** runs at app startup (declarative, often footgun in prod).
   - **sqlc** (codegen) + golang-migrate: separate generation from migration.
5. Run: `go run ./cmd/<binary>` or `make run`.
6. Hot reload: `air` (`.air.toml` config) or `reflex` for dev.
7. Verify: default port from config; `/health` or `/healthz` if instrumented.

### Key File Inventory

**Standard layout (most common modern Go):**

| Location                | Purpose                                                                  |
| ----------------------- | ------------------------------------------------------------------------ |
| `cmd/<binary>/main.go`  | Binary entry; thin, delegates to internal packages                       |
| `internal/`             | Application code; not importable from outside the module                  |
| `internal/server/`      | HTTP server setup, router, middleware                                    |
| `internal/handler/` or `internal/api/` | HTTP handlers (Gin handlers or http.HandlerFunc)            |
| `internal/service/`     | Business logic                                                            |
| `internal/repository/` or `internal/store/` | DB access                                                |
| `internal/domain/` or `internal/model/` | Entities, value objects                                       |
| `pkg/`                  | Reusable libraries (importable by other modules)                          |
| `migrations/`           | SQL migration files                                                       |
| `configs/`              | Config files (yaml/toml/env templates)                                    |
| `scripts/`              | Bootstrap and tooling scripts                                              |
| `Dockerfile`            | Multi-stage build                                                          |

### Package Layout Convention

Check which the project uses before describing the architecture - this drives where new code should land:

- **Layer-package (most common in tutorials and small services)**: `internal/handler/`, `internal/service/`, `internal/repository/`, `internal/model/` grouped by stereotype. An `Order`-related concern is spread across `internal/handler/orders.go`, `internal/service/orders.go`, `internal/repository/orders.go`. Easy to find by stereotype, hard to find by feature; cross-feature coupling is invisible because everything imports from `service` and `repository`. Default for projects with < ~5 domains
- **Feature-package (recommended for medium+ services)**: `internal/orders/{handler.go, service.go, repository.go, model.go}`, `internal/payments/{...}`, `internal/users/{...}`. An entire bounded context lives in one tree; cross-feature imports go through public service interfaces (`orders.Service`), not direct repository imports. Idiomatic Go ("accept interfaces, return structs" plus consumer-defined interfaces). Common in production codebases at scale
- **DDD / hexagonal (`internal/<domain>/{domain/, application/, adapters/}`)**: domain layer (entities, value objects, repository interfaces) is pure Go with no framework imports; application layer holds use cases; adapters layer holds Gin handlers + GORM/sqlx implementations. Used by teams enforcing hexagonal architecture. Recognizable by `domain/` subpackage with no `gin` / `gorm` imports. Less common but heavyweight teams favor it
- **Monorepo / multi-binary (`cmd/api/`, `cmd/worker/`, `cmd/migrate/` + shared `internal/`)**: multiple binaries share `internal/` packages. Each `cmd/<bin>/main.go` is a thin wire-up file. Common when one repo serves both API and Asynq workers; new business logic still goes in `internal/<feature>/`, not in `cmd/`

`cmd/<bin>/main.go` is always thin (load config, build dependencies, start server). Business logic in `cmd/` is a smell - it's not importable from tests or other binaries because `main` is special.

### Conventions

- **`internal/`** for non-exported code; **`pkg/`** for reusable libraries (some teams skip `pkg/` entirely).
- **Errors are values:** check explicitly with `if err != nil`. Wrapping via `fmt.Errorf("ctx: %w", err)`.
- **Context propagation:** `context.Context` as first parameter for any I/O-bound function.
- **Interfaces define expectations**, declared by the consumer (small interfaces, often inline).
- **Constructor functions:** `NewServer(...)` returns a configured struct; no DI framework typically.
- **Functional options pattern:** `NewServer(opts ...Option)` for configurable constructors.
- **Generics (Go 1.18+):** used for collection utilities; not as common as in other languages.
- **Tests:** `_test.go` files alongside the source; `testify` (assert/require/mock) common but not universal; subtests via `t.Run`.

### Risk Hotspots Specific to Go

- **Goroutine lifetime + cancellation** (bare `go fn()` without owner, missing `<-ctx.Done()` arm, `time.Sleep` instead of `select`-on-`ctx`, channel close from receiver, `for range` over an unclosed channel): see `go-concurrency` and `task-go-review-perf`.
- **N+1 + connection pool** (GORM lazy access without `Preload`, `db.AutoMigrate` in prod, missing `defer rows.Close()`, missing `db.WithContext(ctx)`): see `go-data-access`.
- **Asynq dispatch inside DB transaction**, tasks taking ORM models in payloads: see `go-messaging-patterns`.
- **Mass assignment / SQL injection / missing JWT middleware / `mapstructure.Decode(req.Body, &model)`**: see `task-go-review-security`.
- **Migration safety on hot tables** (concurrent index, lock_timeout, expand-then-contract, `db.AutoMigrate` in prod): see `go-migration-safety`.
- **Go quirks** to flag on first read: default `http.Client` has no timeout, `defer` inside loops stacks until function return, `init()` doing heavy work at import time, embedded-field method shadowing, JSON tag mismatches (missing `json:"..."` exposes the Go field name), `init()`-wired globals breaking test isolation.

### First-PR Safe Zones

- New HTTP handler in existing `internal/handler/`.
- New service method following existing constructor pattern.
- New test file alongside source.
- New SQL migration file (`migrations/<timestamp>_*.sql`).

Riskier:

- `cmd/<binary>/main.go` - bootstrapping order matters.
- Middleware - applies to every handler.
- Database connection pool config.
- Goroutine spawning and context propagation patterns.

### Ecosystem Currency

- Go 1.22+ standard; 1.25 latest with structured concurrency improvements.
- Gin still dominant; Chi gaining adoption for stdlib-aligned style.
- pgx 5+ for Postgres; sqlx for general database/sql.
- sqlc for compile-time-safe SQL with generated types.
- OpenTelemetry replacing custom metric/trace libraries.
- `slog` (Go 1.21+) standard structured logger - replacing logrus/zap in new code.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Go version, framework, DB layer, migration tool, logging library, observability stack.

**Local Bootstrap:** `go mod download`, env file, run command (`go run` / `make run` / `air`), default port, health-check path.

**Architecture Map:** `cmd/`/`internal/`/`pkg/` layout, layer directories, server/router setup file, DB connection setup.

**Conventions:** error wrapping, context propagation, constructor functions, functional options usage, test framework.

**Risk Hotspots:** goroutine lifetime owners, default HTTP client timeouts, GORM AutoMigrate, init() side effects, JSON tag completeness, race-detector use in CI.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating Go as having "exceptions" - it does not; errors are values
- Recommending DI frameworks - constructor injection + functional options is idiomatic
- Glossing over context propagation - it is the cancellation backbone
- Confusing `pkg/` and `internal/` semantics - the latter is enforced by the compiler
- Skipping the default-`http.Client`-timeout warning
- Recommending logrus/zap on a new Go 1.21+ project (`slog` is now standard)
