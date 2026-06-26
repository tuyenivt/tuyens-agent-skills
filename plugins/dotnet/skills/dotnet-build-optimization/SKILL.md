---
name: dotnet-build-optimization
description: Speed up .NET solution builds with Central Package Management, Directory.Build.props, Clean Architecture layout, and CI NuGet caching.
metadata:
  category: backend
  tags: [dotnet, build, nuget, cpm, solution, ci-cd]
user-invocable: false
---

# Build Optimization

## When to Use

- Multi-project .NET solution with slow local or CI builds
- Package versions drifting across `.csproj` files
- New solution needing shared build settings and Clean Architecture layout

## Rules

- Centralize NuGet versions in `Directory.Packages.props` with `ManagePackageVersionsCentrally=true`; pin exact versions, never float.
- Share MSBuild properties (TFM, nullable, warnings-as-errors, lang version) via `Directory.Build.props` at solution root.
- Commit `packages.lock.json` (`RestorePackagesWithLockFile=true`) and restore with `--locked-mode` in CI for reproducible, transitive-pinned restores.
- Cache `~/.nuget/packages` in CI keyed on the lock-file hash (falls back to `Directory.Packages.props`); build with `--no-restore` after a successful `dotnet restore`.
- Enforce a one-way dependency graph: `Domain` <- `Application` <- `Infrastructure`/`Api`. Domain references nothing.

## Patterns

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

`Directory.Packages.props`:

```xml
<Project>
  <PropertyGroup>
    <ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <PackageVersion Include="Microsoft.EntityFrameworkCore" Version="8.0.11" />
    <PackageVersion Include="xunit" Version="2.9.3" />
  </ItemGroup>
</Project>
```

Project `.csproj` references omit `Version`:

```xml
<PackageReference Include="Microsoft.EntityFrameworkCore" />
```

GitHub Actions NuGet cache:

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.nuget/packages
    key: nuget-${{ hashFiles('**/packages.lock.json', '**/Directory.Packages.props') }}
    restore-keys: nuget-
```

Clean Architecture layout: `src/{App}.Domain`, `{App}.Application`, `{App}.Infrastructure`, `{App}.Api`; `tests/<Project>.Tests` mirror.

**Migrating to CPM:** inventory current versions (`dotnet list package`) first; when projects disagree, consolidate to the highest compatible version (use `VersionOverride` on the one project that genuinely needs another). Strip every `Version="..."` from `<PackageReference>`, declare each package once in `Directory.Packages.props`, run `dotnet nuget locals all --clear`, then restore. Test-only packages still declare their version centrally.

**Multi-TFM:** use `<TargetFrameworks>net8.0;net9.0</TargetFrameworks>` and verify every central package supports both targets.

## Output Format

- Files changed: `Directory.Build.props`, `Directory.Packages.props`, CI workflow, affected `.csproj`
- Migration steps if adopting CPM on an existing solution
- Expected impact (restore/build time delta, CI cache hit behavior)

## Avoid

- Floating versions (`*`, `1.0.*`) in `Directory.Packages.props`
- `dotnet clean` in CI unless cache is known invalid
- Mixing TFMs across projects without a stated reason
- Domain referencing Application or Infrastructure
