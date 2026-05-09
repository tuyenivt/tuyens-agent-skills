---
name: dotnet-onboard-map
description: ".NET / ASP.NET Core onboarding map: solution layout (Clean Architecture), .csproj, target framework, EF Core migrations, config/secrets."
metadata:
  category: backend
  tags: [onboarding, codebase-map, dotnet, aspnetcore, efcore]
user-invocable: false
---

# .NET Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is .NET / ASP.NET Core.

## When to Use

- A workflow needs .NET-specific orientation: solution structure, target framework, Clean Architecture layering, EF Core + migrations, config/secrets pipeline.
- Project has `*.sln` and `*.csproj` files; or pure SDK-style project with `*.csproj`.

## Rules

- Identify target framework first: `<TargetFramework>net8.0</TargetFramework>` or `net9.0` in `.csproj`. LTS (8) vs STS (9) affects support window.
- Identify solution structure: `*.sln` lists projects; common Clean Architecture has `Domain`, `Application`, `Infrastructure`, `Presentation`/`API`/`Web` projects.
- Identify ORM: EF Core (most common; check `*.csproj` for `Microsoft.EntityFrameworkCore.*`), Dapper, NHibernate.
- Identify presentation: ASP.NET Core MVC, Minimal APIs, Razor Pages, Blazor (Server/WebAssembly), gRPC, Worker Service.
- Identify CQRS / MediatR if present (`MediatR` package); changes how endpoints invoke logic.

## Patterns

### Build Inventory

| File              | What it tells you                                                                |
| ----------------- | -------------------------------------------------------------------------------- |
| `*.sln`           | Solution; lists projects and their relationships                                  |
| `*.csproj`        | Project file: target framework, package refs, project refs                       |
| `Directory.Packages.props` | Central package management (if present)                                |
| `Directory.Build.props` / `Directory.Build.targets` | Solution-wide MSBuild config                  |
| `global.json`     | SDK version pin                                                                   |
| `nuget.config`    | NuGet package source config                                                       |
| `appsettings*.json` | Configuration files                                                             |
| `Program.cs`      | App entry; `var builder = WebApplication.CreateBuilder(args); ...`                |
| `*.Tests.csproj` / `*.UnitTests.csproj` | Test projects                                              |

### Bootstrap Path

1. SDK: confirm `global.json` SDK version matches `dotnet --version`. Install via `winget`/Homebrew/`dotnet-install.sh`.
2. Restore: `dotnet restore`.
3. Local services: `compose.yml` for SQL Server / Postgres / Redis; secrets via `dotnet user-secrets` for dev.
4. Migrations:
   - `dotnet ef database update --project src/Infrastructure --startup-project src/Api` (EF Core).
   - Migrations in `src/Infrastructure/Migrations/` typically.
5. Run: `dotnet run --project src/Api` or `dotnet watch run --project src/Api`.
6. Verify: HTTPS port from `appsettings.json` `Kestrel:Endpoints` or launch profile (`Properties/launchSettings.json`); `/swagger` if Swashbuckle is present.

### Key File Inventory

**Clean Architecture solution:**

| Project               | Purpose                                                                 |
| --------------------- | ----------------------------------------------------------------------- |
| `src/Domain/`         | Entities, value objects, domain events, no external deps                |
| `src/Application/`    | Use cases, MediatR handlers, DTOs, interfaces (e.g., `IRepository<T>`)  |
| `src/Infrastructure/` | EF Core implementations, external clients, migration history             |
| `src/Api/` (or `Web/`, `Presentation/`) | Controllers, minimal APIs, SignalR; `Program.cs` lives here |
| `tests/<Project>.Tests/` | Unit tests per layer                                                  |
| `tests/<Project>.IntegrationTests/` | Integration tests (often with WebApplicationFactory)         |

**Within `src/Api/`:**

| File / dir             | Purpose                                                              |
| ---------------------- | -------------------------------------------------------------------- |
| `Program.cs`           | DI container setup, middleware pipeline, app startup                  |
| `appsettings.json` + `appsettings.Development.json` | Config                                  |
| `Properties/launchSettings.json` | Dev environment + URLs                                       |
| `Controllers/`         | Controller-based routes                                              |
| `Endpoints/`           | Minimal API endpoint groups (if used)                                |
| `Middleware/`          | Custom middleware                                                     |
| `Filters/`             | Action/exception filters                                              |

### Module Layout Convention

Check which the project uses before describing the architecture - this drives where new code should land:

- **Clean Architecture (most common in production .NET)**: `src/Domain/`, `src/Application/`, `src/Infrastructure/`, `src/Api/` (or `Web/` / `Presentation/`) as separate projects in the solution. Domain has no project references; Application references Domain only; Infrastructure references Application + Domain (implements interfaces); Api references all. Cross-project boundaries enforced by `.csproj` `<ProjectReference>` graph - the compiler catches a layer violation. New business logic lands in `Application/Features/<Feature>/`; persistence in `Infrastructure/Persistence/Repositories/`; HTTP entry in `Api/Controllers/`. MediatR is typical for the Application layer
- **Feature folders / vertical slice (modern alternative within a single project)**: `src/Api/Features/Orders/{PlaceOrderHandler.cs, PlaceOrderEndpoint.cs, PlaceOrderRequest.cs, OrderRepository.cs}` - each feature is a folder owning its entire vertical (request DTO + validator + handler + endpoint + repository). No separate Application / Infrastructure projects; layering is by namespace convention, not by project. Recognizable by `Features/` directory and lack of separate Domain / Application / Infrastructure projects. Easier to navigate per-feature; harder to enforce layer rules (no compile-time gate)
- **Minimal API endpoint groups (`MapGroup`)**: `src/Api/Endpoints/OrdersEndpoints.cs` with `app.MapGroup("/api/v1/orders").MapOrdersEndpoints();` extension method pattern. Often combined with feature folders. Replaces `Controllers/` directory in greenfield .NET 7+ projects. The endpoint extension is the public surface; behind it sits the same handler/service/repository tree as Clean Architecture (or feature-folder Vertical Slice)
- **Modular monolith / multi-bounded-context**: `src/Modules/Orders/{Orders.Domain, Orders.Application, Orders.Infrastructure, Orders.Api}` - each module is its own Clean Architecture stack inside a top-level `Modules/` folder. Modules communicate via a shared `BuildingBlocks` library or in-process bus (`MediatR.Notifications`). Used by teams scaling toward microservice extraction without paying the deploy cost yet. Recognizable by `src/Modules/<ModuleName>/` directory tree
- **Worker Service / Background-only**: `src/Worker/` with `Program.cs` calling `Host.CreateDefaultBuilder().ConfigureServices(s => s.AddHostedService<MyWorker>())`. No HTTP surface. New jobs land as `IHostedService` or `BackgroundService` subclasses; shared logic typically in a separate library project
- **Single-`Program.cs` minimal API (small services / samples)**: everything in `Api/Program.cs` with inline endpoint mappings. Fine for < 5 endpoints or templates; refactor to feature folders or Clean Architecture before it grows

`Program.cs` (or the API project's `Program.cs` in Clean Architecture) is always thin (load config, build DI, register middleware, `app.Run()`). Business logic in `Program.cs` is a smell - it cannot be tested without booting the host. Move to a handler / service / extension method.

### Conventions

- **Constructor injection** via DI container (built-in `IServiceCollection`); no field/property injection without explicit attribute.
- **`async`/`await` everywhere I/O is involved**; `CancellationToken` parameter on every async method.
- **Configuration:** `IOptions<T>` / `IOptionsSnapshot<T>` / `IOptionsMonitor<T>` patterns; secrets via `dotnet user-secrets` (dev), Azure Key Vault / AWS Secrets Manager (prod).
- **Logging:** `ILogger<T>` via DI; categorized by generic type. `Serilog` and `NLog` common alternatives.
- **Validation:** FluentValidation is common; data annotations alternative.
- **MediatR + CQRS:** if present, every endpoint is thin and dispatches to a handler. Pipeline behaviors for cross-cutting concerns.
- **Tests:** xUnit dominant; NUnit and MSTest legacy. Moq or NSubstitute for mocking.
- **EF Core conventions:** `DbSet<Entity>` per aggregate; configurations in `IEntityTypeConfiguration<T>` files (Fluent API).

### Risk Hotspots Specific to .NET

- **Captive dependency:** Singleton injecting Scoped service - the Scoped is captured for app lifetime. Enable `ValidateScopes` in dev.
- **`DbContext` thread-safety:** not thread-safe; one per request (Scoped). Reusing across `await` in parallel work is a race.
- **`IQueryable` -> client-side LINQ boundary:** calling a non-translatable C# method in `Where` after an EF query loads the entire table client-side.
- **Async void**: only for event handlers; exceptions become unhandled.
- **`ConfigureAwait(false)`** in app code: not needed in ASP.NET Core (no SyncContext); needed in libraries.
- **`Task.Result` / `.Wait()` / `Task.GetAwaiter().GetResult()`** in async context: deadlock risk on UI/legacy frameworks; pointless in ASP.NET Core but blocks a threadpool thread.
- **`AddDbContext` lifetime mismatch with usage**: registering as Singleton breaks; default Scoped is correct.
- **Middleware order**: `UseAuthentication` before `UseAuthorization`; `UseRouting` before either.
- **`appsettings.Production.json` overriding dev** when committed by accident.
- **EF Core Migrations across multiple DbContexts**: must specify `--context` argument.

### First-PR Safe Zones

- New endpoint in existing controller / minimal API endpoint group.
- New MediatR handler + DTO + validator (CQRS projects).
- New unit test in `tests/<Project>.Tests/`.
- New configuration option in `appsettings.json` + `IOptions<T>`.

Riskier:

- `Program.cs` - DI registration order matters; middleware order matters.
- EF Core migrations - production rollback requires explicit reverse migration.
- DI lifetime changes - cascade through the dependency graph.
- Authentication/authorization configuration.

### Ecosystem Currency

- .NET 8 LTS standard; .NET 9 STS; .NET 10 LTS expected.
- Minimal APIs gaining over MVC controllers in new projects.
- EF Core 8+ has bulk operations (`ExecuteUpdate`, `ExecuteDelete`).
- `record` types standard for DTOs; primary constructors (C# 12) common.
- Source generators replacing reflection-based startup in libraries.
- AOT compilation supported but constrains library choices (no reflection-heavy code).

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** target framework, solution structure (Clean Architecture or other), ORM, presentation layer (MVC/Minimal/Blazor), MediatR/CQRS presence, validation library, test framework.

**Local Bootstrap:** `dotnet restore`, user secrets setup if needed, `dotnet ef database update`, `dotnet run --project ...`, default ports, swagger path.

**Architecture Map:** project layering, `Program.cs` location, controllers/endpoints directory, DbContext + entity configuration locations.

**Conventions:** DI, `IOptions<T>` config, logging stack, async/cancellation token usage, validation library, test framework.

**Risk Hotspots:** captive dependencies, DbContext concurrency, IQueryable client-side boundary, middleware ordering, async-over-sync deadlocks, migration multi-context.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Listing solution projects without identifying their layer purpose
- Treating .NET Framework patterns as current (.NET Core / .NET 5+ unified)
- Recommending `ConfigureAwait(false)` in ASP.NET Core app code
- Skipping `dotnet user-secrets` for dev configuration
- Glossing over middleware order in `Program.cs`
- Treating MVC and Minimal API endpoint patterns as interchangeable
