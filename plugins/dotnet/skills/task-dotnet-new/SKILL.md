---
name: task-dotnet-new
description: End-to-end ASP.NET Core feature implementation workflow. Generates entity, repository, service, controller, DTOs, EF Core migration, FluentValidation validators, and tests (unit + integration). Orchestrates multiple atomic skills into a complete, production-ready feature.
metadata:
  category: backend
  tags: [dotnet, aspnet-core, feature, implementation, workflow, ef-core, rest-api, testing, clean-architecture]
  type: workflow
---

# Implement Feature

## When to Use

- Implementing a new ASP.NET Core feature end-to-end (entity → controller → tests → migration)
- Scaffolding a complete CRUD or domain-specific resource with Clean Architecture patterns
- Adding a new domain aggregate with REST API, persistence, and test coverage
- Any daily coding task that requires coordinated generation of multiple .NET layers

## Rules

- Constructor injection only — never `new` dependencies inside classes
- Use `record` types for all DTOs and command/query objects (C# 12)
- `FluentValidation` for all request validation — never `[Required]` data annotations on DTOs
- Never expose EF Core entities in API responses — always map to DTO records
- All async methods must propagate `CancellationToken`
- Follow Clean Architecture layer boundaries: `Domain` → `Application` → `Infrastructure` → `Api`
- `Application` layer must not reference `Infrastructure` directly (depend on interfaces)
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code
- Run build check after all files are generated

## Implementation

### Step 1 — Gather Requirements

**Interactive.** Ask the user for:

- **Feature name / resource** — e.g., "Order", "Payment", "Notification"
- **Namespace base** — e.g., `YourApp.Orders`
- **Operations needed** — CRUD, specific operations (approve, cancel, submit), event-driven
- **Relationships to existing entities** — navigation properties, foreign keys
- **Business rules / validation constraints** — e.g., "amount must be positive", "status transitions"
- **API visibility** — public, internal, or admin-only (affects authorization policies)

Do not proceed until all required inputs are confirmed.

### Step 2 — Design

Propose to the user:

- **Endpoints** — HTTP method, URI, request/response DTOs, status codes
- **DTO records** — properties with FluentValidation rules
- **Entity fields** — column types, constraints, relationships
- **Application use-cases** — commands, queries, handlers (CQRS if using MediatR)
- **Service/handler methods** — business operations, transaction boundaries

**Present the design and wait for user approval before proceeding.**

### Step 3 — Generate Entity + Migration

Create the domain entity and corresponding EF Core migration.

Use skill: `dotnet-ef-performance` — projection usage, `AsNoTracking()`, N+1 prevention
Use skill: `dotnet-db-migration-safety` — safe DDL patterns, zero-downtime migrations

Generate:

- **Entity** — `src/YourApp.Domain/Entities/{Name}.cs`
  - Private setters, factory methods or constructors for invariant enforcement
  - Audit fields (`CreatedAt`, `UpdatedAt`)
  - Navigation properties with explicit foreign key properties
- **EF Core configuration** — `src/YourApp.Infrastructure/Persistence/Configurations/{Name}Configuration.cs`
  - `IEntityTypeConfiguration<{Name}>` with explicit column mappings and indexes
- **Migration** — `src/YourApp.Infrastructure/Persistence/Migrations/{Timestamp}_{Description}.cs`
  - Generated via `dotnet ef migrations add`
  - Include indexes for foreign keys and frequently queried columns

### Step 4 — Generate Repository

Create the repository interface and implementation.

Use skill: `dotnet-ef-performance` — query patterns, Dapper for complex reads

Generate:

- **Interface** — `src/YourApp.Application/Interfaces/I{Name}Repository.cs`
  - Async methods with `CancellationToken`
  - Pagination support via `PagedResult<T>` return types
- **Implementation** — `src/YourApp.Infrastructure/Persistence/Repositories/{Name}Repository.cs`
  - EF Core queries with `AsNoTracking()` for reads
  - Projections to DTO records for list endpoints

### Step 5 — Generate Application Layer

Create commands, queries, validators, and handlers.

Use skill: `dotnet-transaction` — `SaveChanges` boundaries, unit of work
Use skill: `dotnet-exception-handling` — domain exception hierarchy, consistent error responses

Generate:

- **Commands** — `src/YourApp.Application/{Feature}/Commands/{Operation}{Name}Command.cs` (record)
- **Queries** — `src/YourApp.Application/{Feature}/Queries/Get{Name}Query.cs` (record)
- **Validators** — `src/YourApp.Application/{Feature}/Validators/{Operation}{Name}Validator.cs` (FluentValidation)
- **Handlers** — `src/YourApp.Application/{Feature}/Handlers/{Operation}{Name}Handler.cs`
  - Business logic, entity creation, domain event publishing
  - Call `SaveChangesAsync(ct)` once per handler

### Step 6 — Generate Controller

Create the REST controller with proper HTTP semantics.

Use skill: `api-guidelines` — consistent response format, URI conventions
Use skill: `dotnet-exception-handling` — global exception handler maps domain exceptions
Use skill: `dotnet-security-patterns` — explicit auth rule on every endpoint

Generate:

- **Controller** — `src/YourApp.Api/Controllers/{Name}sController.cs`
  - `[ApiController]`, `[Route("api/v1/[controller]")]`
  - Constructor-injected `ISender` (MediatR) or direct service
  - `CancellationToken ct` parameter on every action
  - Proper HTTP status codes: `201 Created` for POST, `204 NoContent` for DELETE
  - `[Authorize]` or `[AllowAnonymous]` on every action — no implicit defaults

### Step 7 — Generate Tests

Use skill: `dotnet-test-integration` — select correct test type for each layer

Generate:

- **Unit test** — `tests/YourApp.Application.Tests/{Feature}/{Operation}{Name}HandlerTests.cs`
  - NSubstitute / Moq for repository mocks
  - Test happy path, not-found, validation, and business rule scenarios
- **Repository test** — `tests/YourApp.Infrastructure.Tests/Persistence/{Name}RepositoryTests.cs`
  - Testcontainers PostgreSQL
  - Test custom queries, pagination, relationship loading
- **API test** — `tests/YourApp.Api.Tests/Controllers/{Name}sControllerTests.cs`
  - `WebApplicationFactory` with real HTTP client
  - Test request validation, response format, HTTP status codes, error responses
- **Test fixtures** — Bogus `Faker<T>` for all test data

### Step 8 — Validate

Run build and final checks.

```bash
dotnet build --no-incremental
dotnet test --no-build
```

Present summary to user:

- Files created (with paths)
- Endpoints available (method + URI)
- Test count and coverage areas
- Any warnings or manual steps required (e.g., run `dotnet ef migrations add`)

## Output

Present a checklist of generated files:

```markdown
## Generated Files

- [ ] Entity: `src/YourApp.Domain/Entities/{Name}.cs`
- [ ] EF Config: `src/YourApp.Infrastructure/Persistence/Configurations/{Name}Configuration.cs`
- [ ] Interface: `src/YourApp.Application/Interfaces/I{Name}Repository.cs`
- [ ] Repository: `src/YourApp.Infrastructure/Persistence/Repositories/{Name}Repository.cs`
- [ ] Command: `src/YourApp.Application/{Feature}/Commands/Create{Name}Command.cs`
- [ ] Validator: `src/YourApp.Application/{Feature}/Validators/Create{Name}Validator.cs`
- [ ] Handler: `src/YourApp.Application/{Feature}/Handlers/Create{Name}Handler.cs`
- [ ] Controller: `src/YourApp.Api/Controllers/{Name}sController.cs`
- [ ] Unit test: `tests/YourApp.Application.Tests/{Feature}/Create{Name}HandlerTests.cs`
- [ ] Repo test: `tests/YourApp.Infrastructure.Tests/Persistence/{Name}RepositoryTests.cs`
- [ ] API test: `tests/YourApp.Api.Tests/Controllers/{Name}sControllerTests.cs`
- [ ] Migration: run `dotnet ef migrations add Create{Name} -p src/YourApp.Infrastructure`

## Endpoints

| Method | URI                      | Status | Description      |
| ------ | ------------------------ | ------ | ---------------- |
| GET    | /api/v1/{resources}      | 200    | List (paginated) |
| GET    | /api/v1/{resources}/{id} | 200    | Get by ID        |
| POST   | /api/v1/{resources}      | 201    | Create           |
| PUT    | /api/v1/{resources}/{id} | 200    | Update           |
| DELETE | /api/v1/{resources}/{id} | 204    | Delete           |

## Tests

- Unit tests: {count} (application/handler layer)
- Integration tests: {count} (repository layer)
- API tests: {count} (controller layer)
```

## Key Skills Reference

**Data layer:**

- Use skill: `dotnet-ef-performance` for N+1 prevention, `AsNoTracking()`, Dapper reads
- Use skill: `dotnet-db-migration-safety` for safe EF Core migrations and zero-downtime DDL
- Use skill: `dotnet-transaction` for `SaveChanges` boundaries and unit of work

**Business logic:**

- Use skill: `dotnet-exception-handling` for domain exception hierarchy and global error handler

**Security:**

- Use skill: `dotnet-security-patterns` for JWT auth and policy-based authorization

**Testing:**

- Use skill: `dotnet-test-integration` for test layer selection, Testcontainers, and Bogus

> For stack-agnostic code review and architecture review, use the core plugin's `task-code-review` and `task-design-architecture`.

## Checklist

- [ ] Requirements gathered and confirmed with user
- [ ] Design proposed and approved by user
- [ ] Entity created with private setters and factory methods
- [ ] EF Core configuration with explicit mappings and indexes
- [ ] EF Core migration generated (with indexes)
- [ ] Repository interface in Application layer; implementation in Infrastructure
- [ ] FluentValidation validators for all commands/requests
- [ ] Handlers with single `SaveChangesAsync()` per use-case
- [ ] Constructor injection throughout — no `new` on dependencies
- [ ] DTOs as C# records
- [ ] Controller with explicit `[Authorize]`/`[AllowAnonymous]` on every action
- [ ] `CancellationToken` propagated to all async calls
- [ ] Entity never exposed in API responses
- [ ] Unit tests with NSubstitute/Moq mocks
- [ ] Integration tests with Testcontainers
- [ ] API tests with WebApplicationFactory
- [ ] Build verified (`dotnet build`)
- [ ] Summary presented to user

## Avoid

- Exposing EF Core entities in API responses
- `[Required]` data annotations on DTO records (use FluentValidation)
- Service/handler directly referencing `DbContext` (use repository interface)
- Missing `CancellationToken` on async methods
- Multiple `SaveChangesAsync()` calls in one handler (partial writes on failure)
- Generating code before user approves the design
- Skipping test generation
- Over-engineering: only generate what was requested
