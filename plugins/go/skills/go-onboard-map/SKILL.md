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

- Report the Go version and any `toolchain` directive verbatim from `go.mod`. Go supports the last two majors; state the position only if the current release is known from the environment, otherwise report the version and skip the judgment rather than inventing a release number
- Identify framework: Gin / Echo / Chi / Fiber / gorilla / net/http
- Identify DB: GORM / sqlx / pgx / database/sql + driver / ent / bun / sqlc
- Identify layout convention (drives where new code lands). Report every convention that applies: the package convention, and orthogonally whether it is single-binary, monorepo multi-binary, or a `go.work` multi-module workspace. In a workspace, report each module's framework, ORM, and `go` directive separately and flag version skew between them
- Grep `//go:build` tags: tagged files and tests are invisible to default builds - report required `-tags` (integration suites are commonly gated this way). Without filesystem access, say the tag surface is unverified rather than implying `go test ./...` is complete
- Deps: `vendor/` present means vendor mode is the default - `go mod download` is unnecessary and `go build` never consults the proxy. In a workspace, `go work sync` comes first
- Report the test surface as its own fact: colocated `_test.go`, tag-gated suites, or none at all. "This codebase has no tests" is a top-three onboarding fact, not a footnote

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
| **`go.work` workspace**      | `go.work` + several `*/go.mod`, each module with its own layout        | Independently versioned services in one repo |

The last two rows are orthogonal to the package convention - a feature-packaged monorepo is the common combination; report every row that applies. A layer-packaged repo without `internal/` is still layer-package: name the convention and note that the boundary is convention-only, not compiler-enforced.

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

- Goroutine lifetime + cancellation, unsupervised `go fn()` -> `go-concurrency`, `task-go-review-perf`
- N+1, pool config, `AutoMigrate`, `defer rows.Close()`, `WithContext` -> `go-data-access`
- Broker dispatch inside transactions (Asynq, Kafka, Watermill), ORM models in payloads -> `go-messaging-patterns`
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

Inject into `task-onboard` as Markdown sections in this order. Every value is read from the tree; mark a derived value `(inferred)` and an unavailable one `(unknown)`. Never carry a value over from the shape below - it shows the section skeleton, not defaults.

```markdown
### Stack and Tooling
- **Go:** <go directive> (<toolchain directive, or "no toolchain directive">)
- **Framework:** <framework, or (unknown)>
- **DB:** <library + driver + engine>
- **Migrations:** <tool + command>
- **Logging / Observability:** <libraries>
- **Lint:** <config file + enabled linters, or "none - no linter config">
- **Build tags:** <required `-tags`, "none found", or "unverified - no filesystem access">
- **Tests:** <colocated / tag-gated / none found> + the command that runs them

### Local Bootstrap
Ordered commands, each one runnable. Omit steps the tree does not support rather than
inventing them; `vendor/` present means no `go mod download`, a workspace means
`go work sync` first. Verify with `/health` or `/healthz`; if neither route exists,
name the first routed GET. Never state a port the tree does not set.

### Architecture Map
- Entry: <cmd paths>, and whether wire-up is thin
- App code: <internal/ or module root>
- Layout: **<convention>**, plus single-binary / monorepo multi-binary / go.work workspace
- <one line per structural package>
- Workspace only: per-module framework, ORM, and `go` directive; flag version skew

### Conventions
Only what the tree shows. A convention with no evidence is `(unknown)` with the file to
read for it - not restated as an idiom the repo may not follow. Call out deviations from
the idiomatic baseline explicitly, since they change where new code goes.

### Risk Hotspots
Ordered most-exploitable first, each naming the delegate skill.

### First-PR Safe Zones
Concrete paths from the observed layout. When a generic safe zone does not exist here
(no `migrations/` directory, route table inside `main.go`), say so and say why instead of
offering the generic form. Close with what to avoid and the reason.

### Unknowns - Ask the Team
Every `(unknown)` above, consolidated. On a repo with no compose file, no `.env.example`,
no CI, and no linter, this is the highest-value section for a new joiner.
```

## Avoid

- Treating Go as having exceptions
- Recommending DI frameworks (constructor injection is idiomatic)
- Glossing over context propagation
- Confusing `pkg/` and `internal/` (the latter is compiler-enforced)
- Recommending logrus/zap for new 1.21+ projects (use `slog`)
- Fabricating health paths, env var names, or default ports not visible in the tree - mark `(inferred)` or `(unknown)`
