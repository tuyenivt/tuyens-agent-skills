# Tuyen's Agent Skills - .NET / ASP.NET Core

Claude Code plugin for .NET 8 LTS / ASP.NET Core Web API development.

## Stack

- .NET 8 LTS
- C# 12
- ASP.NET Core Web API (primary), MVC (secondary), Minimal APIs (lightweight)

## Key Features

- **Clean Architecture**: Strict layer boundary enforcement (Domain → Application → Infrastructure → Api)
- **C# 12 Patterns**: Records for DTOs, primary constructors, collection expressions
- **EF Core + Dapper**: N+1 prevention, `AsNoTracking()` for reads, Dapper for complex queries
- **EF Core Migrations**: Zero-downtime DDL, expand-then-contract patterns
- **FluentValidation**: All request validation - no data annotation clutter on DTOs
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

Atomic skills provide focused, reusable .NET patterns. These are hidden from the slash menu (`user-invocable: false`) and referenced by workflow skills and agents.

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

| Agent                         | Focus                                                                                           |
| ----------------------------- | ----------------------------------------------------------------------------------------------- |
| `dotnet-architect`            | ASP.NET Core architecture, EF Core, Clean Architecture, APIs                                    |
| `dotnet-tech-lead`            | .NET code review, refactoring guidance, doc standards, async safety, layer boundary enforcement |
| `dotnet-test-engineer`        | xUnit, Testcontainers, WebApplicationFactory, Bogus                                             |
| `dotnet-security-engineer`    | JWT auth, policy-based authz, OWASP for .NET                                                    |
| `dotnet-performance-engineer` | EF Core optimization, async patterns, caching, profiling                                        |
| `dotnet-reliability-engineer` | Health checks, Polly, Serilog, incident response, runbook standards                             |
| `dotnet-sprint-planner`       | Sprint allocation for .NET features with EF Core migration and MassTransit complexity           |

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

- `/task-code-review` - Staff-level code review with risk assessment, framework-aware
- `/task-code-secure-review` - Security review
- `/task-code-test` - Test strategy
- `/task-code-refactor` - Refactoring plan
- `/task-code-perf-review` - Performance review
