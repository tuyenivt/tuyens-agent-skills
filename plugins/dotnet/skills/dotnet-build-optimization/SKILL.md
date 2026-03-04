---
name: dotnet-build-optimization
description: .NET 8 build performance, NuGet Central Package Management, multi-project solution setup, and CI caching
metadata:
  category: backend
  tags: [dotnet, build, nuget, cpm, solution, ci-cd]
user-invocable: false
---

# Build Optimization

## When to Use

- Speeding up local and CI builds for multi-project .NET solutions
- Standardising NuGet package versions across projects
- Structuring a Clean Architecture solution layout
- Configuring build caching in GitHub Actions or Azure Pipelines

## Rules

- Use **NuGet Central Package Management** (`Directory.Packages.props`) for all package versions
- Use `Directory.Build.props` to share common properties (nullable, warnings as errors, target framework)
- Enable build incremental compilation - avoid `dotnet clean` in CI unless cache is invalid
- Pin exact package versions in `Directory.Packages.props`; never float versions (`*` or `1.0.*`)
- Split solution into focused projects: `Domain`, `Application`, `Infrastructure`, `Api`, `Tests`
- Use `<Nullable>enable</Nullable>` and `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` globally

## Pattern

`Directory.Build.props` (solution root):

```xml
<Project>
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
    <LangVersion>12</LangVersion>
    <EnforceCodeStyleInBuild>true</EnforceCodeStyleInBuild>
  </PropertyGroup>
</Project>
```

`Directory.Packages.props` (Central Package Management):

```xml
<Project>
  <PropertyGroup>
    <ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <PackageVersion Include="Microsoft.EntityFrameworkCore" Version="8.0.11" />
    <PackageVersion Include="Dapper" Version="2.1.35" />
    <PackageVersion Include="FluentValidation.AspNetCore" Version="11.3.0" />
    <PackageVersion Include="Serilog.AspNetCore" Version="8.0.3" />
    <PackageVersion Include="xunit" Version="2.9.3" />
    <PackageVersion Include="Testcontainers.PostgreSql" Version="4.1.0" />
    <PackageVersion Include="Bogus" Version="35.6.1" />
  </ItemGroup>
</Project>
```

GitHub Actions NuGet cache:

```yaml
- name: Cache NuGet packages
  uses: actions/cache@v4
  with:
    path: ~/.nuget/packages
    key: nuget-${{ hashFiles('**/Directory.Packages.props') }}
    restore-keys: nuget-
```

## Clean Architecture Solution Layout

```
src/
  YourApp.Domain/          # Entities, value objects, domain events
  YourApp.Application/     # Use cases, interfaces, DTOs, validators
  YourApp.Infrastructure/  # EF Core, external services, repositories
  YourApp.Api/             # ASP.NET Core host, controllers, middleware
tests/
  YourApp.Domain.Tests/
  YourApp.Application.Tests/
  YourApp.Infrastructure.Tests/
  YourApp.Api.Tests/
```

## Avoid

- Individual `<PackageReference Version="...">` scattered across `.csproj` files
- `dotnet restore` without a NuGet cache step in CI
- Circular project references (Domain must not reference Application or Infrastructure)
- Mixing `net8.0` and `net6.0` targets in the same solution without reason
