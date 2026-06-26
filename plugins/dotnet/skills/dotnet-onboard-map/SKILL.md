---
name: dotnet-onboard-map
description: ".NET / ASP.NET Core onboarding map: solution layout (Clean Architecture), .csproj, target framework, EF Core migrations, config/secrets."
metadata:
  category: backend
  tags: [onboarding, codebase-map, dotnet, aspnetcore, efcore]
user-invocable: false
---

# .NET Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. Composed by `task-onboard` when the detected stack is .NET / ASP.NET Core.

## When to Use

Workflow needs .NET-specific orientation: target framework, solution layering, EF Core + migrations, config/secrets, presentation style (MVC / Minimal API / Blazor / Worker). Project has `*.sln` and/or `*.csproj`.

## Rules

- Read target framework from `.csproj` (`<TargetFramework>net8.0</TargetFramework>`) before anything else; LTS (8, 10) vs STS (9) drives support window.
- Identify presentation style (MVC controllers, Minimal API endpoints, Razor, Blazor Server/WASM, gRPC, Worker Service) - it determines where new HTTP entry points land.
- Identify ORM by `.csproj` package refs: `Microsoft.EntityFrameworkCore.*` (most common), Dapper, NHibernate.
- Identify layout (see Patterns) before describing architecture; new code placement depends on it.
- Flag missing `global.json` if multiple SDKs are installed and team needs reproducibility.

## Patterns

### File Inventory

| File                                                | Signal                                              |
| --------------------------------------------------- | --------------------------------------------------- |
| `*.sln`                                             | Project list and relationships                      |
| `*.csproj`                                          | Target framework, package refs, project refs        |
| `global.json`                                       | SDK pin                                             |
| `Directory.Packages.props`                          | Central package management                          |
| `Directory.Build.props` / `.targets`                | Solution-wide MSBuild config                        |
| `appsettings*.json`                                 | Config per environment                              |
| `Properties/launchSettings.json`                    | Dev URLs and env vars                               |
| `Program.cs`                                        | DI registration, middleware pipeline, `app.Run()`   |
| `*.Tests.csproj` / `*.IntegrationTests.csproj`      | Test projects                                       |

### Layout Variants

Detect which the project uses (drives new-code placement); variants can compose - e.g. a Worker Service host over a modular/Clean layout - so report the combination rather than forcing one bucket:

- **Clean Architecture** (default for .NET): `src/{Domain, Application, Infrastructure, Api}` as separate projects. Domain has no refs; Application -> Domain; Infrastructure -> Application; Api -> all. Layer rules enforced by `<ProjectReference>` graph. New logic: `Application/Features/<F>/`; persistence: `Infrastructure/Persistence/`; HTTP: `Api/Controllers/` or `Api/Endpoints/`.
- **Vertical slice / feature folders**: single `Api` project with `Features/<F>/{Handler, Endpoint, Request, Repository}.cs`. Layering by namespace, not project; no compile-time gate.
- **Modular monolith**: `src/Modules/<Module>/{Domain, Application, Infrastructure, Api}` - Clean stack per module, inter-module via `BuildingBlocks` or MediatR notifications.
- **Worker Service**: `src/Worker/Program.cs` with `AddHostedService<T>`; no HTTP. New jobs are `BackgroundService` subclasses.
- **Single-file Minimal API**: all endpoints in `Program.cs`. Refactor once endpoints exceed ~5.

`Program.cs` stays thin (config + DI + middleware + `Run`). Business logic in `Program.cs` is a smell.

### Bootstrap Path

1. SDK: match `global.json` to `dotnet --version`.
2. `dotnet restore`.
3. Services: `compose.yml` for SQL Server / Postgres / Redis; `dotnet user-secrets set` for dev secrets.
4. Migrations: if EF Core, `dotnet ef database update --project <persistence-project> --startup-project <startup-project>`; discover DbContexts via `: DbContext` and run once per context with `--context <Name>` (each may have its own output dir). If no EF Core, report the observed mechanism (Dapper + `schema.sql`/DbUp/FluentMigrator) instead.
5. Run: `dotnet run --project <startup-project>` (`--project` optional for a single-project repo).
6. Verify: for a web app, URL from `launchSettings.json` / `Kestrel:Endpoints`, `/swagger` if Swashbuckle is referenced. For a Worker Service, no URL - verify via logs.

### Conventions (call out what's present)

- DI: constructor injection via `IServiceCollection`.
- Config: `IOptions<T>` / `IOptionsSnapshot<T>` / `IOptionsMonitor<T>`; secrets via `dotnet user-secrets` (dev), Key Vault / Secrets Manager (prod).
- Logging: `ILogger<T>`; Serilog/NLog if referenced.
- Validation: FluentValidation if referenced, else DataAnnotations.
- Async: `async`/`await` with `CancellationToken` on every async method.
- MediatR / CQRS: if referenced, endpoints dispatch to handlers; pipeline behaviors carry cross-cutting concerns.
- EF Core: `DbSet<T>` per aggregate; configs in `IEntityTypeConfiguration<T>`.
- Tests: xUnit (dominant), NUnit/MSTest (legacy); Moq or NSubstitute.

### Risk Hotspots

- **Async / cancellation**, **DI lifetime** (Singleton capturing Scoped; `DbContext` is Scoped). See `dotnet-async-patterns`.
- **EF Core**: N+1, `Include` cartesian explosion, missing `AsNoTracking`, client-eval boundary, multi `SaveChangesAsync`. See `dotnet-ef-performance`.
- **Background dispatch in transaction**, tracked entities in payloads. See `dotnet-messaging-patterns`, `dotnet-transaction`.
- **Migrations**: online indexes, `lock_timeout`, expand-then-contract, multi-DbContext via `--context`. See `dotnet-db-migration-safety`.
- **Security**: mass assignment, SQL injection, JWT misvalidation, `BinaryFormatter` / `Newtonsoft.Json TypeNameHandling.All` on untrusted input. See `dotnet-security-patterns`.
- **ASP.NET Core quirks**: middleware order (`UseRouting` -> `UseAuthentication` -> `UseAuthorization`); `appsettings.Production.json` accidentally committed.

### First-PR Safe Zones

Safer: new endpoint in existing controller/group; new MediatR handler + DTO + validator; new unit test; new `IOptions<T>` config key.

Riskier: `Program.cs` edits (DI order, middleware order), EF Core migrations, DI lifetime changes, auth configuration.

## Output Format

Inject into `task-onboard` sections:

- **Stack and Tooling**: target framework; layout variant; ORM + provider; presentation style; MediatR/CQRS yes/no; validation lib; logging stack; test framework.
- **Local Bootstrap**: SDK check, `dotnet restore`, services compose, `dotnet user-secrets`, schema/migration step (EF Core `database update` with `--project`/`--startup-project`/`--context`, or the observed non-EF mechanism), `dotnet run --project ...`; for web apps the URL + swagger path, for Workers the log-based verification.
- **Architecture Map**: project graph (which references which), `Program.cs` location, controllers/endpoints directory, `DbContext` + `IEntityTypeConfiguration<T>` locations, migrations directory.
- **Conventions**: DI, `IOptions<T>`, logging, async/cancellation, validation, tests - only what the repo actually uses.
- **Risk Hotspots**: subset from the list above that applies to the observed code.
- **First-PR Safe Zones**: scoped to observed structure.

## Avoid

- Listing solution projects without naming each one's layer purpose.
- Treating .NET Framework patterns as current (.NET 5+ is unified).
- Recommending `ConfigureAwait(false)` in ASP.NET Core app code (no-op; reserve for libraries).
- Conflating MVC, Minimal API, and Razor patterns.
