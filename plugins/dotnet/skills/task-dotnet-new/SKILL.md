---
name: task-dotnet-new
description: End-to-end ASP.NET Core feature implementation workflow that generates entity, repository, service, controller, DTO records, EF Core migration, FluentValidation validators, and tests across all layers. Not for single-file changes, isolated bug fixes, or simple scaffolding tasks.
metadata:
  category: backend
  tags: [dotnet, aspnet-core, feature, implementation, workflow, ef-core, rest-api, testing, clean-architecture]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Implement Feature

## When to Use

- Implementing a new ASP.NET Core feature end-to-end (entity → controller → tests → migration)
- Scaffolding a complete CRUD or domain-specific resource with Clean Architecture patterns
- Adding a new domain aggregate with REST API, persistence, and test coverage
- Any daily coding task that requires coordinated generation of multiple .NET layers

## Rules

- Constructor injection only - never `new` dependencies inside classes
- Use `record` types for all DTOs and command/query objects (C# 12)
- `FluentValidation` for all request validation - never `[Required]` data annotations on DTOs
- Never expose EF Core entities in API responses - always map to DTO records
- All async methods must propagate `CancellationToken`
- Follow Clean Architecture layer boundaries: `Domain` → `Application` → `Infrastructure` → `Api`
- `Application` layer must not reference `Infrastructure` directly (depend on interfaces)
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code
- Run build check after all files are generated

## Implementation

STEP 1 - GATHER: feature name, namespace base, operations (CRUD/custom), entity relationships, validation constraints, API visibility

STEP 2 - DESIGN: propose endpoints (method + URI + DTO records + status), entity fields, commands/queries/handlers (CQRS if MediatR). Present for user approval before generating code.

STEP 3 - ENTITY + MIGRATION: Use skill: `dotnet-ef-performance`, `dotnet-db-migration-safety`. Generate Domain entity (private setters, audit fields, navigation properties), EF Core `IEntityTypeConfiguration`, and migration with indexes for FK and filter columns.

STEP 4 - REPOSITORY: Use skill: `dotnet-ef-performance`. Interface in `Application/Interfaces` with async + `CancellationToken`. Implementation in `Infrastructure` with `AsNoTracking()` reads and DTO projections for lists.

STEP 5 - APPLICATION LAYER: Use skill: `dotnet-transaction`, `dotnet-exception-handling`, `dotnet-async-patterns`. Commands and Queries as records. FluentValidation validators. Handlers with business logic; single `SaveChangesAsync(ct)` per handler. If async messaging needed: Use skill: `dotnet-messaging-patterns`.

STEP 6 - CONTROLLER: Use skill: `backend-api-guidelines`, `dotnet-exception-handling`, `dotnet-security-patterns`. `[ApiController] [Route("api/v1/[controller]")]`. `CancellationToken ct` on every action. `[Authorize]` or `[AllowAnonymous]` on every action - no implicit defaults. `201 Created` POST, `204 NoContent` DELETE.

STEP 7 - TESTS: Use skill: `dotnet-test-integration`. Unit: NSubstitute/Moq, happy path + not-found + validation. Repo: Testcontainers PostgreSQL. API: `WebApplicationFactory` + real HTTP client. Test fixtures via Bogus `Faker<T>`.

STEP 8 - VALIDATE: Use skill: `dotnet-build-optimization`. `dotnet build --no-incremental`, `dotnet test --no-build`. Present file list, endpoints, test count, any manual steps (e.g., run `dotnet ef migrations add`).

## Self-Check

- [ ] Requirements gathered and design approved before any code generated
- [ ] All layers generated: EF Core migration, entity, repository (interface + impl), command/query handlers, controller, DTOs, tests
- [ ] Constructor injection only; no `new` on dependencies; `CancellationToken` on all async methods
- [ ] `record` types for all DTOs; EF Core entities never exposed in API responses
- [ ] `FluentValidation` for all request validation; no `[Required]` data annotations on DTOs
- [ ] Clean Architecture boundaries respected: `Domain` -> `Application` -> `Infrastructure` -> `Api`
- [ ] `[Authorize]` or `[AllowAnonymous]` explicit on every controller action
- [ ] `dotnet build --no-incremental` and `dotnet test --no-build` pass; file list, endpoint table, and test count presented

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
