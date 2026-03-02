# Tuyen's Agent Skills - .NET / ASP.NET Core

Claude Code plugin for .NET 8 LTS / ASP.NET Core Web API development. 8 agents, 11 skills (2 workflow + 9 atomic).

> This plugin focuses exclusively on .NET 8 / ASP.NET Core with Clean Architecture. For stack-agnostic code review, architecture, ops, and governance skills, install `core`.

## Installation

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install dotnet@tuyens-agent-skills --scope project
```

## Optional: Share Skills Between Claude Code and Codex

Claude Code and Codex use the same `agentskills.io` format. You can create a symbolic link so Codex reuses the skills managed by Claude Code.

```bash
# Unix (Linux/macOS)
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/dotnet/skills" "$HOME/.codex/skills/tuyens-agent-skills-dotnet-skills"

# Windows
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-dotnet-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills\plugins\dotnet\skills"
```

## Requirements

- Claude Code >= 2.0.0
- .NET 8 LTS
- C# 12
- ASP.NET Core Web API (primary), MVC (secondary), Minimal APIs (lightweight)

## Key Features

- **Clean Architecture**: Strict layer boundary enforcement (Domain → Application → Infrastructure → Api)
- **C# 12 Patterns**: Records for DTOs, primary constructors, collection expressions
- **EF Core + Dapper**: N+1 prevention, `AsNoTracking()` for reads, Dapper for complex queries
- **EF Core Migrations**: Zero-downtime DDL, expand-then-contract patterns
- **FluentValidation**: All request validation — no data annotation clutter on DTOs
- **ASP.NET Core Security**: JWT bearer auth, policy-based authorization, Problem Details errors
- **Resilience**: Polly v8 resilience pipelines for external HTTP calls
- **Messaging**: MassTransit consumers, transactional outbox, Hangfire background jobs
- **Observability**: Serilog structured logging, OpenTelemetry, health checks
- **Testing**: xUnit, Testcontainers, WebApplicationFactory, NSubstitute/Moq, Bogus

## Workflow Skills

Workflow skills (`task-*`) orchestrate multiple atomic skills into task-oriented workflows. They are invoked as slash commands.

| Skill               | Purpose                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------ |
| `task-dotnet-new`   | End-to-end ASP.NET Core feature implementation (entity + migration + API + tests)          |
| `task-dotnet-debug` | Developer debugging workflow (paste stack trace or describe unexpected behaviour, get fix) |

## Atomic Skills (Reusable Patterns)

9 atomic skills provide focused, reusable .NET patterns. These are hidden from the slash menu (`user-invocable: false`) and referenced by workflow skills and agents.

| Skill                        | Purpose                                                |
| ---------------------------- | ------------------------------------------------------ |
| `dotnet-ef-performance`      | EF Core optimization, N+1 prevention, Dapper reads     |
| `dotnet-transaction`         | `SaveChanges` boundaries, Unit of Work patterns        |
| `dotnet-exception-handling`  | Global `IExceptionHandler`, Problem Details (RFC 7807) |
| `dotnet-async-patterns`      | async/await, CancellationToken, BackgroundService      |
| `dotnet-db-migration-safety` | EF Core migrations, zero-downtime DDL patterns         |
| `dotnet-test-integration`    | xUnit, Testcontainers, WebApplicationFactory, Bogus    |
| `dotnet-security-patterns`   | JWT bearer auth, policy-based authorization, OWASP     |
| `dotnet-build-optimization`  | NuGet CPM, Directory.Build.props, CI caching           |
| `dotnet-messaging-patterns`  | MassTransit consumers, outbox pattern, Hangfire jobs   |

## Agents

| Agent                         | Focus                                                        |
| ----------------------------- | ------------------------------------------------------------ |
| `dotnet-architect`            | ASP.NET Core architecture, EF Core, Clean Architecture, APIs |
| `dotnet-tech-lead`            | .NET code review, async safety, layer boundary enforcement   |
| `dotnet-test-engineer`        | xUnit, Testcontainers, WebApplicationFactory, Bogus          |
| `dotnet-security-engineer`    | JWT auth, policy-based authz, OWASP for .NET                 |
| `dotnet-performance-engineer` | EF Core optimization, async patterns, caching, profiling     |
| `dotnet-reliability-engineer` | Health checks, Polly, Serilog, incident response             |
| `dotnet-refactoring-expert`   | Clean Architecture migration, async modernization, tech debt |
| `dotnet-technical-writer`     | OpenAPI/Swagger, XML docs, ADRs, README, runbooks            |

## Usage Examples

**Implement full feature (entity + migration + API + tests):**

```
/task-dotnet-new
Feature: Order with payment tracking
Namespace: YourApp.Orders
Operations: CRUD, approve, cancel
Relationships: ManyToOne to Customer
```

**Debug a stack trace:**

```
/task-dotnet-debug
[paste stack trace or error message]
```

## Core Plugin Skills

The following workflows are provided by `core` (install separately):

- `/task-code-review` — Framework-agnostic code review
- `/task-code-review-advanced` — Staff-level review with risk assessment
- `/task-code-secure` — Security review
- `/task-code-test` — Test strategy
- `/task-code-refactor` — Refactoring plan
- `/task-code-perf-review` — Performance review
- `/task-docs-generate` — Documentation generation
- `/task-incident-root-cause` — Incident root cause analysis
- `/task-incident-postmortem` — Post-incident postmortem
- `/task-release-plan` — Production release planning
- `/task-design-risk-analysis` — Proactive risk assessment
- `/task-design-architecture` — Architecture design proposal
