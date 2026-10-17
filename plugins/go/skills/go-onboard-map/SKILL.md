---
name: go-onboard-map
description: Go onboarding signals - module layout, go.mod, framework (Gin/Echo/Chi), build tags, ORM (GORM/sqlx/pgx), observability stack.
metadata:
  category: backend
  tags: [onboarding, codebase-map, go, gin, modules]
user-invocable: false
---

# Go Onboard Map (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when `Language` is Go **or** stack-detect finds a `go.mod` in a service directory it scans (a fullstack monorepo with a React root puts Go in `Additional`). When Go is the primary stack, a `## Tech Stack` declaration wins over tree inference for Framework, Database, ORM and Test framework (stack-detect precedence); when the tree disagrees, report `<declared> (tree shows <inferred>)`. When Go sits in `Additional`, those scalar fields describe the primary stack and every Go value comes from the tree. The Go version is the `go` directive in each `go.mod`.

## When to Use

- A workflow needs Go-specific orientation: module layout, framework, build tags, DB layer, observability
- Project has `go.mod` or `go.work`

## Rules

- Report the Go version and any `toolchain` directive verbatim from `go.mod`. Since Go 1.21 the `go` line is a minimum, not a must-match: under the default `GOTOOLCHAIN=auto` the local toolchain is used when it satisfies both the `go` and `toolchain` lines, and the newer named version is downloaded otherwise. Go supports the last two majors; state the position only if the current release is known from the environment, otherwise report the version and skip the judgment rather than inventing a release number
- Identify framework: Gin / Echo / Chi / Fiber / gorilla / net/http
- Identify DB: GORM / sqlx / pgx / database/sql + driver / ent / bun / sqlc
- Identify layout convention (drives where new code lands). Report every convention that applies: the package convention, and orthogonally whether it is single-binary, monorepo multi-binary, or a `go.work` multi-module workspace. In a workspace `go.work`'s own `go` line governs (the go command errors when it is older than any module's), so report it first, then each module's framework, ORM, `go` directive, `replace` directives and which sibling modules it imports; flag version skew between them
- Grep `//go:build` tags (and `// +build`, still honoured at every version and present beside `//go:build` in older trees): files behind a custom tag (`integration`, `e2e`) are excluded from default builds and `go test ./...` - report the required `-tags`; platform tags (`linux`, `amd64`) are in the default build on a matching platform and are not a finding; a `-tags` value in the Makefile or CI that no `//go:build` line uses is `defined but unused: <tag>`. Without filesystem access, say the tag surface is unverified rather than implying `go test ./...` is complete
- Deps: a module's `vendor/` makes `-mod=vendor` the default (go >= 1.14), so `go mod download` is unnecessary and `go build` never consults the proxy. In a workspace a module's own `vendor/` is ignored; only a root `vendor/` from `go work vendor` (Go 1.22+) counts. `go work sync` is not a bootstrap step - `go build`/`go run` resolve workspace modules from `go.work` without it
- Report the test surface as its own fact: colocated `_test.go`, tag-gated suites, hand-written mocks in non-test files, or none at all - per module in a workspace. "This codebase has no tests" is a top-three onboarding fact, not a footnote

## Build Inventory

| File              | What it tells you                                |
| ----------------- | ------------------------------------------------ |
| `go.mod`          | Module path, Go version, direct and `// indirect` dependencies |
| `go.mod` `require` + `cmd/<bin>/main.go` | Logging / Observability: the logger (`slog`, zap, logrus) and OTel modules, and where they are wired |
| `go.work`         | Multi-module monorepo; governing `go` line; local module resolution |
| `go.sum`          | Dependency checksums (a missing entry fails `go build` under `-mod=readonly`; `go mod tidy` writes it - a bootstrap step, note it) |
| `Makefile` / `Taskfile.yml` | Project commands                       |
| `Dockerfile`      | Multi-stage build (builder -> distroless common) |
| `.golangci.{yml,yaml,toml,json}` | Lint bar: a v2 config (`version: "2"`) starts from `linters.default`, so "enabled" = default set + `enable` - `disable`, not the `enable` list alone; no `version` key is a v1 config |
| `vendor/`         | Vendored deps if present                         |
| `sqlc.{yaml,yml,json}` | Generated DB layer - output is normally committed; `sqlc generate` is a build step only when it is absent or stale |
| `.github/workflows/*.yml`, `.gitlab-ci.yml` | CI: test flags (`-race`, `-tags`), lint, build - the `CI / Deploy` source |
| `k8s/`, `deploy/`, `Dockerfile` | Deploy target; a mismatch between them (image name, port, probe path, `GOWORK=off` or `vendor/` build) is reported under `CI / Deploy` |

## Bootstrap Path

1. Toolchain: `go.mod` `go` directive is the minimum; `toolchain` names what `GOTOOLCHAIN=auto` fetches
2. Deps: `go mod download` - skip when the module's `vendor/` (in a workspace, only a root `vendor/`) is present; a module `vendor/` inside a workspace is ignored by the build and is noted, not a step; `go mod tidy` first when `go.sum` lacks entries
3. Codegen: `sqlc generate`, `go generate ./...` when the tree declares them
4. Local services: `compose.{yaml,yml}` / `docker-compose.{yaml,yml}`; env vars in `.env.example`, and how they load (`godotenv`, `direnv`, exported by hand)
5. Migrations: golang-migrate (`migrate -path <dir> -database "$DSN" up`), goose (`goose -dir <dir> <driver> "$DSN" up`, driver from the tree: `postgres`, `mysql`, `sqlite3`), `AutoMigrate` on boot (footgun), or sqlc + one of those
6. Run: one line per binary - `go run ./cmd/<binary>` (or `go run .` for a root `main.go`) with its port / `make run` / `air` for hot reload
7. Verify: `/health` or `/healthz`; if neither exists, the first routed endpoint

## Package Layout

`cmd/<bin>/main.go` (or a root `main.go`) should be thin (config + wiring); business logic or a route table in `main.go` is a smell to report, not a convention to assume.

| Convention                   | Shape                                                                  | When                                    |
| ---------------------------- | ---------------------------------------------------------------------- | --------------------------------------- |
| **Layer-package**            | `internal/handler/`, `service/`, `repository/`, `model/`               | Default for < ~5 domains; tutorials. A mixed tree reports the dominant convention first (`layer-package, one feature package: posting/`) |
| **Feature-package**          | `internal/orders/{handler,service,repository,model}.go`                | Recommended for medium+ services        |
| **DDD / hexagonal**          | `internal/<domain>/{domain,application,adapters}/`; domain has no framework imports | Teams enforcing hexagonal architecture  |
| **Monorepo multi-binary**    | `cmd/api/`, `cmd/worker/`, `cmd/migrate/` + shared `internal/`         | One repo serves API + Asynq workers     |
| **`go.work` workspace**      | `go.work` + several `*/go.mod`, each module with its own layout        | Independently versioned services in one repo |

The last two rows are orthogonal to the package convention - a feature-packaged monorepo is the common combination; report every row that applies. A layer-packaged repo without `internal/` is still layer-package: name the convention and note that the boundary is convention-only, not compiler-enforced. A small module split by concern (`config/`, `mail/`, `store/`) is layer-package.

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

- Goroutine lifetime + cancellation, unsupervised `go fn()`, loops in `init()` -> `go-concurrency`
- N+1, pool config, `AutoMigrate`, `defer rows.Close()`, `WithContext`, outbox claims without `SKIP LOCKED` -> `go-data-access`
- Broker dispatch inside transactions (Asynq, Kafka, Watermill), ORM models in payloads, consumer offset handling -> `go-messaging-patterns`
- Mass assignment, raw SQL, missing JWT, `InsecureSkipVerify`, default secrets -> `go-security-patterns`
- Migration safety on hot tables -> `go-migration-safety`
- Go quirks: default `http.Client` no timeout, `defer` in loops, `init()` doing heavy work, JSON tag mismatches, `init()`-wired globals breaking test isolation -> `go-idioms`
- Shutdown without drain, middleware order, spoofable `ClientIP`, uncapped bodies -> `go-gin-patterns`
- Tests that cannot run in parallel, SQLite standing in for Postgres, `-race` dropped in CI -> `go-testing-patterns`

## First-PR Safe Zones

Scope to the observed layout, not the generic defaults. For a feature-package repo, that means a new file in `internal/<domain>/`; for hexagonal, a new use case in `application/` or a new adapter.

Generic safe zones (replace with concrete equivalents from the tree):
- New handler in `internal/handler/`
- New service method following existing constructor pattern
- New `_test.go` colocated
- New migration pair in the repo's existing prefix style (both tools default to timestamps; `migrate create -seq` / `goose create -s` give `000002_` / `00002_`) - golang-migrate `.up.sql` + `.down.sql`, goose one file with `-- +goose Up` / `Down` (see go-migration-safety)

Riskier: `cmd/<binary>/main.go`, middleware (applies globally), pool config, goroutine / context patterns.

## Ecosystem Currency

- Gin dominant; Chi gaining on stdlib alignment
- pgx 5+ for Postgres; sqlx for general database/sql; sqlc for type-safe generated SQL
- OpenTelemetry replacing custom metric/trace libs
- `slog` standard structured logger - replacing logrus/zap in new code

## Output

Inject into `task-onboard` as Markdown sections in this order. Every value is read from the tree (or the instruction file, per the precedence above); mark a derived value `(inferred)` - a run command assembled from the tree alone, a hotspot named from a path with no code read - and an unavailable one `(unknown)` with the reason (`file unreadable`, `no filesystem access`). A directory listing that shows no linter config supports `none`; an unreadable tree is `(unknown)`. `docs/` is part of the tree: an incident or design doc that names a hotspot is read for Risk Hotspots. Never carry a value over from the shape below - it shows the section skeleton, not defaults. In a workspace, `Go`, `Framework`, `DB`, `Migrations` and `Tests` carry one sub-bullet per module.

```markdown
### Stack and Tooling
- **Go:** <go directive> (<toolchain directive, or "no toolchain directive">; <support position, only when the current release is known>) - workspace: `go.work` line first, then per module
- **Framework:** <framework, or (unknown)>
- **DB:** <library + driver + engine>
- **Migrations:** <tool + command>
- **Logging / Observability:** <libraries>
- **Lint:** <config file + effective linter set, or "none - no linter config">
- **Build tags:** <required `-tags`, "none found", "defined but unused: <tag>", or "unverified - no filesystem access">
- **Tests:** <colocated / tag-gated / hand-written mocks only / none found> + the command that runs them
- **CI / Deploy:** <workflow file + what it runs; k8s or compose manifests; or (unknown)>

### Local Bootstrap
Ordered commands, each one runnable. Omit steps the tree does not support rather than
inventing them; a counted `vendor/` (see Rules) means no `go mod download`; a codegen config whose
output is not committed means its generate step comes before the build. Verify with `/health` or `/healthz`; if neither route
exists, name the first routed endpoint. A port counts as set when `go.mod`-adjacent code,
config, or a manifest sets it - say which; never state one the tree does not set.

### Architecture Map
- Entry: <cmd paths or root main.go>, and whether wire-up is thin
- App code: <internal/ or module root>
- Layout: **<convention>**, plus single-binary / monorepo multi-binary / go.work workspace
- <one line per structural package>
- Workspace only: per-module `replace` directives, sibling imports (a `require`/`replace` nothing imports is a deviation), and version skew - framework, ORM and `go` directive already sit per module under Stack and Tooling

### Conventions
Only what the tree shows - sample the entry, one handler, one repository, one test. A convention
with no evidence is `(unknown)` with the file to read for it - not restated as an idiom the repo
may not follow. Call out deviations from the idiomatic baseline explicitly (an unused config
struct, a logger other than slog, an interface declared beside its only implementation, a
`require` nothing imports), since they change where new code goes.

### Risk Hotspots
Ordered most-exploitable first (reachable without auth, then authenticated, then internal), then by blast radius. One bullet each:
`- <hotspot> (<path or file:line>) -> <delegate skill>`. Delegates: `go-security-patterns` (exposed pprof, auth grouping, secrets), `go-concurrency`, `go-data-access` (pool, transactions), `go-messaging-patterns`, `go-migration-safety`, `go-gin-patterns` (shutdown, middleware), `go-testing-patterns`, `go-idioms` (Go quirks); a hotspot no skill owns (module version skew, a Dockerfile/k8s mismatch) reads `-> none (ops)`.

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
- Listing `go work sync` or an unconditional `go mod download` as bootstrap steps
