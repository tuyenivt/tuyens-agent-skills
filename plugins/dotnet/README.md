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

| Skill                              | Agent                          | Purpose                                                                                    |
| ---------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------------ |
| `task-dotnet-implement`            | `dotnet-architect`             | End-to-end ASP.NET Core feature implementation (entity + migration + API + tests)          |
| `task-dotnet-debug`                | `dotnet-tech-lead`             | Developer debugging workflow (paste stack trace or describe unexpected behaviour, get fix) |
| `task-dotnet-review`               | `dotnet-tech-lead`             | .NET-aware staff-level code review umbrella (Phases A-E + parallel perf/security/observability subagents) |
| `task-dotnet-review-perf`          | `dotnet-performance-engineer`  | Performance review: EF Core N+1, async pitfalls, allocation hotspots, caching, pool sizing |
| `task-dotnet-review-security`      | `dotnet-security-engineer`     | Security review: JWT bearer, policy-based authz, mass assignment, FluentValidation, OWASP   |
| `task-dotnet-review-observability` | `dotnet-tech-lead`             | Observability review: Serilog, OpenTelemetry, `Meter` + Prometheus, dotnet-counters, Sentry |
| `task-dotnet-test`                 | `dotnet-test-engineer`         | Test strategy & scaffolds: xUnit, WebApplicationFactory, Testcontainers, NSubstitute, Bogus |
| `task-dotnet-refactor`             | `dotnet-tech-lead`             | Refactor planning: fat controllers, `.Result` blocking, EF Core N+1, mass assignment, captive deps |

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
| `dotnet-code-explain`        | DI container scopes, middleware pipeline, async/await with cancellation tokens, EF Core change tracking, Clean Architecture layers - injected into `task-code-explain` |
| `dotnet-onboard-map`         | Solution layout (Clean Architecture), .csproj target framework, EF Core + migrations, configuration/secrets - injected into `task-onboard` |

## Agents

| Agent                         | Focus                                                                                           |
| ----------------------------- | ----------------------------------------------------------------------------------------------- |
| `dotnet-architect`            | ASP.NET Core architecture, EF Core, Clean Architecture, APIs                                    |
| `dotnet-tech-lead`            | .NET code review, refactoring guidance, doc standards, async safety, layer boundary enforcement |
| `dotnet-test-engineer`        | xUnit, Testcontainers, WebApplicationFactory, Bogus                                             |
| `dotnet-security-engineer`    | JWT auth, policy-based authz, OWASP for .NET                                                    |
| `dotnet-performance-engineer` | EF Core optimization, async patterns, caching, profiling                                        |

## Usage Examples

**Implement full feature (entity + migration + API + tests):**

```
/task-dotnet-implement
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
- `/task-code-review-security` - Security review
- `/task-code-test` - Test strategy
- `/task-code-refactor` - Refactoring plan
- `/task-code-review-perf` - Performance review
