---
name: task-dotnet-implement
description: "Scaffold ASP.NET Core feature end-to-end: EF Core entity + migration, repository, MediatR handlers, controller, FluentValidation, xUnit tests."
metadata:
  category: backend
  tags: [dotnet, aspnet-core, ef-core, mediatr, clean-architecture, feature]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` after `behavioral-principles` and `stack-detect`. Follow its contract: skip GATHER (and DESIGN when `plan.md` exists). Never edit `spec.md` / `plan.md` / `tasks.md`; surface conflicts as proposed amendments.

# Implement Feature

## When to Use

- New ASP.NET Core feature end-to-end (entity -> controller -> tests -> migration)
- CRUD or domain-specific resource with Clean Architecture layering
- Adding a domain aggregate with REST API, persistence, and tests

## Edge Cases

- **Partial input** (feature name only) - ask for fields, relationships, operations before design
- **No persistence** (proxy / aggregation endpoint) - skip entity, repository, migration; generate handler + controller + DTOs + tests
- **Existing entity referenced** - read and extend; skip migration if no schema change
- **Custom verb** (cancel, approve, publish) - use `PATCH /{resources}/{id}/{verb}` with a dedicated command + handler
- **Status transitions** - enforce in handler with transition map; mirror as CHECK constraint in migration
- **Idempotency** - unique `IdempotencyKey` column + find-or-create in handler + duplicate-request test
- **Role-restricted endpoints** (admin) - `[Authorize(Roles = "Admin")]`; separate query for admin-wide reads
- **Async messaging** - publish after `SaveChangesAsync`; load `dotnet-messaging-patterns`

## Rules

- Constructor injection only; never `new` dependencies
- `record` types for all DTOs, commands, queries
- `FluentValidation` for request validation; never `[Required]` annotations on DTOs
- Never expose EF entities in API responses; always project to DTO records
- `CancellationToken` parameter on every async method, propagated to EF and HTTP calls
- Clean Architecture dependencies flow inward: `Api` -> `Application` -> `Domain`; `Infrastructure` implements `Application` interfaces
- One `SaveChangesAsync(ct)` per handler (unit of work boundary)
- `[Authorize]` or `[AllowAnonymous]` explicit on every controller action

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack and Gather Requirements

Use skill: `stack-detect`. Ask the user:

1. Feature name and primary use case
2. Namespace base and operations (CRUD / custom verbs / admin variants)
3. Entity fields, relationships, validation constraints
4. Status transitions (e.g., `Pending -> Active -> Cancelled | Expired`)
5. Idempotency requirements (deduplication keys, exactly-once writes)
6. API visibility per endpoint (anonymous / authenticated / role-restricted)
7. Async messaging or external integrations

Do not continue until requirements are complete.

### Step 3 - Design (approval gate)

Present for user approval, then halt:

- Endpoints (method, URI, request/response DTO records, status codes, authorization)
- Domain entity + DB schema (indexes on FK / filter columns, CHECK constraints, unique idempotency index)
- Commands, queries, handlers (one handler per use case)
- Error model (exception hierarchy, HTTP status mapping)
- Idempotency and status-transition strategies (when applicable)

### Step 4 - Entity + Migration

Use skill: `dotnet-ef-performance`, `dotnet-db-migration-safety`.

- Domain entity: private setters, audit fields, navigation properties, factory method for invariants
- `IEntityTypeConfiguration<T>` in `Infrastructure/Persistence/Configurations`
- `decimal` columns: explicit `HasPrecision(19, 4)` for money
- Migration generated via `dotnet ef migrations add` (do not hand-write); verify indexes for FK and filter columns

Status with known transitions adds a CHECK constraint:

```csharp
builder.ToTable("subscriptions", t => t.HasCheckConstraint(
    "ck_subscriptions_status",
    "status IN ('Pending','Active','Cancelled','Expired')"));
```

Idempotency key:

```csharp
builder.HasIndex(x => x.IdempotencyKey).IsUnique();
```

### Step 5 - Repository

Use skill: `dotnet-ef-performance`. Interface in `Application/Interfaces`; implementation in `Infrastructure/Persistence/Repositories`. `AsNoTracking()` reads, DTO projections for list endpoints, `CancellationToken` on every method.

```csharp
Task<Subscription?> FindByIdempotencyKeyAsync(string key, CancellationToken ct);
```

### Step 6 - Application Layer

Use skill: `dotnet-transaction`, `dotnet-exception-handling`, `dotnet-async-patterns`.

Commands and queries as `record` types. FluentValidation validators per command. MediatR handlers contain business logic and exactly one `SaveChangesAsync(ct)`. Map entity -> DTO via record static factory `SubscriptionResponse.From(Subscription)`. Domain exceptions extend a common base.

Status transitions enforced in the handler:

```csharp
private static readonly Dictionary<Status, HashSet<Status>> Allowed = new() {
    [Status.Pending] = [Status.Active, Status.Cancelled],
    [Status.Active]  = [Status.Cancelled, Status.Expired],
};
if (!Allowed.GetValueOrDefault(s.Status, []).Contains(next))
    throw new InvalidStateTransitionException(s.Status, next);
```

Idempotent create:

```csharp
var existing = await repo.FindByIdempotencyKeyAsync(cmd.IdempotencyKey, ct);
if (existing is not null) return SubscriptionResponse.From(existing);
```

### Step 7 - Controller

Use skill: `backend-api-guidelines`, `dotnet-exception-handling`, `dotnet-security-patterns`.

`[ApiController] [Route("api/v1/[controller]")]`. `CancellationToken ct` on every action. `[Authorize]` / `[Authorize(Roles="Admin")]` / `[AllowAnonymous]` explicit. `201 Created` with `Location` header on POST, `204 NoContent` on DELETE, `PATCH /{id}/{verb}` for custom operations.

### Step 8 - Tests

Use skill: `dotnet-test-integration`.

- Unit (handlers): NSubstitute or Moq; happy path, not-found, validation failure, invalid state transition, idempotent replay
- Repository: Testcontainers PostgreSQL
- API: `WebApplicationFactory<Program>` + real `HttpClient`; assert status codes, authorization, conflict (409) on unique violation
- Fixtures via Bogus `Faker<T>`

### Step 9 - Validate

Use skill: `dotnet-build-optimization`. Run `dotnet build --no-incremental` and `dotnet test --no-build`. Present file list, endpoint table, test counts, and any manual steps (e.g., `dotnet ef migrations add Create<Name>`).

## Self-Check

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: requirements gathered (fields, transitions, idempotency, auth)
- [ ] Step 3: design presented and approved before code
- [ ] Step 4: entity, EF configuration, CHECK constraint, unique idempotency index
- [ ] Step 5: repository interface in `Application`, impl in `Infrastructure`, `AsNoTracking` reads
- [ ] Step 6: command/query records, validators, MediatR handlers; one `SaveChangesAsync` per handler; transitions enforced
- [ ] Step 7: `[Authorize]` / `[AllowAnonymous]` explicit on every action; `CancellationToken` propagated
- [ ] Step 8: unit + repo + API tests cover happy path, not-found, validation, invalid transition, idempotent replay
- [ ] Step 9: `dotnet build` and `dotnet test` pass; file list, endpoint table, test counts presented

## Output Format

```markdown
## Generated Files

- [ ] Entity: `src/YourApp.Domain/Entities/{Name}.cs`
- [ ] EF Config: `src/YourApp.Infrastructure/Persistence/Configurations/{Name}Configuration.cs`
- [ ] Repository interface: `src/YourApp.Application/Interfaces/I{Name}Repository.cs`
- [ ] Repository impl: `src/YourApp.Infrastructure/Persistence/Repositories/{Name}Repository.cs`
- [ ] Command(s): `src/YourApp.Application/{Feature}/Commands/*.cs`
- [ ] Query(ies): `src/YourApp.Application/{Feature}/Queries/*.cs`
- [ ] Validator(s): `src/YourApp.Application/{Feature}/Validators/*.cs`
- [ ] Handler(s): `src/YourApp.Application/{Feature}/Handlers/*.cs`
- [ ] Controller: `src/YourApp.Api/Controllers/{Name}sController.cs`
- [ ] Unit tests: `tests/YourApp.Application.Tests/{Feature}/*HandlerTests.cs`
- [ ] Repo tests: `tests/YourApp.Infrastructure.Tests/Persistence/{Name}RepositoryTests.cs`
- [ ] API tests: `tests/YourApp.Api.Tests/Controllers/{Name}sControllerTests.cs`
- [ ] Migration: `dotnet ef migrations add Create{Name} -p src/YourApp.Infrastructure`

## Endpoints

| Method | URI                              | Status | Auth     | Description       |
| ------ | -------------------------------- | ------ | -------- | ----------------- |
| GET    | /api/v1/{resources}              | 200    | User     | List (paginated)  |
| GET    | /api/v1/{resources}/{id}         | 200    | User     | Get by ID         |
| POST   | /api/v1/{resources}              | 201    | User     | Create            |
| PATCH  | /api/v1/{resources}/{id}/{verb}  | 200    | User     | Custom operation  |
| DELETE | /api/v1/{resources}/{id}         | 204    | User     | Delete            |

## Tests

- Unit: {count}
- Repository: {count}
- API: {count}
```

## Avoid

- Generating code before requirements + design approval
- Exposing EF entities in API responses
- `new` on dependencies; missing `CancellationToken` on async methods
- `[Required]` annotations on DTOs (use FluentValidation)
- Hand-writing EF migrations instead of using `dotnet ef migrations add`
- Multiple `SaveChangesAsync` per handler
- Implicit authorization (missing `[Authorize]` / `[AllowAnonymous]`)
- Skipping idempotency for payment or external-callback writes
- Missing CHECK constraints when status transitions are known
- Unbounded list endpoints without pagination
