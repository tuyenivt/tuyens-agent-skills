# Tuyen's Agent Skills - Go / Gin

Claude Code plugin for Go/Gin development.

## Stack

- Go 1.25+
- Gin
- GORM + sqlx (both)
- golang-migrate
- PostgreSQL

## Requirements

- Claude Code >= 2.0.0
- Go 1.25+
- Gin (`github.com/gin-gonic/gin`)
- PostgreSQL

## Installation

Install the core plugin first, then the Go plugin:

```
/plugin install core@tuyens-agent-skills
/plugin install go@tuyens-agent-skills
```

## Optional: Share Skills Between Claude Code and Codex

Claude Code and Codex use the same `agentskills.io` format. You can create a symbolic link so Codex reuses the skills managed by Claude Code.

```bash
# Unix (Linux/macOS)
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/go/skills" "$HOME/.codex/skills/tuyens-agent-skills-go-skills"

# Windows
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-go-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/go/skills"
```

## Agents

| Agent                     | Description                                                                                                                                           |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `go-architect`            | Go architect for Gin, GORM/sqlx, clean architecture, and production Go patterns. Designs features, structures projects, makes architecture decisions. |
| `go-tech-lead`            | Go tech lead for code review and engineering standards. Reviews for idiomatic Go, error handling, concurrency safety, and performance.                |
| `go-reliability-engineer` | Go reliability engineer for incident analysis in Go/Gin/PostgreSQL environments. pprof profiling, goroutine leak detection, connection pool tuning.   |

## Workflow Skills

| Skill                       | Description                                                                                                                                    |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-go-new`               | Create a new Go/Gin resource endpoint. Generates model, repository, service, handler, routes, migration, and tests.                            |
| `task-go-implement-feature` | End-to-end Go/Gin feature implementation. Generates migrations, models, repositories, services, handlers, middleware, and comprehensive tests. |
| `task-go-debug`             | Debug Go errors. Paste a panic stack trace, error log, or describe unexpected behavior. Classifies error, identifies root cause, suggests fix. |

## Atomic Skills

| Skill                 | Description                                                                                                                                        |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `go-error-handling`   | Go error patterns: explicit returns, wrapping with `%w`, sentinel errors, custom error types, `errors.Is/As`, Gin error middleware.                |
| `go-gin-patterns`     | Gin web framework patterns: routing groups, middleware, request binding with validation, consistent JSON responses, pagination, graceful shutdown. |
| `go-data-access`      | Go data access with GORM and sqlx. Model definition, associations, preloading, transactions, scopes, connection pooling.                           |
| `go-migration-safety` | Safe migration patterns with golang-migrate and PostgreSQL. File naming, up/down pairs, zero-downtime DDL, embedding in Go binary.                 |
| `go-testing-patterns` | Go testing: table-driven tests, httptest for Gin handlers, testcontainers-go for integration, testify, interface mocking, benchmarks, synctest.    |
| `go-concurrency`      | Go concurrency patterns: goroutine lifecycle, channels, context cancellation, errgroup, worker pools, sync primitives, `WaitGroup.Go`.             |

## Usage Examples

### Create a new resource endpoint

```
> task-go-new

Resource name: Order
Fields: Total float64, Status string, CustomerID uint
Data access: GORM
Operations: full CRUD

→ Generates migration, model, repository, service, handler, routes, and tests
```

### Implement a feature end-to-end

```
> task-go-implement-feature

Feature: Add payment processing with webhook endpoint
- Creates migration for payments table
- Repository with GORM for CRUD, sqlx for reporting query
- Service with Stripe integration and error wrapping
- Gin handlers with webhook signature validation
- Table-driven tests + httptest + testcontainers-go

→ Validates with go build, go test -race, go vet
```
