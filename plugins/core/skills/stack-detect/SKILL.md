---
name: stack-detect
description: Detect tech stack from marker files and CLAUDE.md/AGENTS.md/GEMINI.md: language, framework, build tool, DB, test framework.
metadata:
  category: core
  tags: [stack, detection, environment]
user-invocable: false
---

# Stack Detection

## When to Use

- Called automatically by any skill containing `Use skill: stack-detect`.
- At the start of any workflow that adapts output to the project's tech stack.
- Cache the result for the conversation; do not re-detect per skill invocation.

## Rules

- **Never guess, never fail.** A field that cannot be determined is `unknown`, and consumers proceed.
- **Detect silently.** Do not prompt the user for stack information.
- **Pass through, do not validate.** Any value is valid; no fixed enum of allowed languages or frameworks.
- **Precedence: explicit declarations beat inference.** When both an instruction file's `## Tech Stack` and marker-file inference provide the same field, the instruction file wins (`Java 21` over an inferred `Java`). Marker files fill fields the instruction file omits.
- **Read narrowly.** Check only marker files and the `## Tech Stack` section of at most one instruction file (the first in Step 2's order that has the section). Do not scan the whole project. When a monorepo layout is evident (`apps/`, `packages/`, `services/`, or a pair such as `frontend/`+`backend/` or `client/`+`server/`), also check each immediate subdirectory of `apps/`, `packages/`, `services/` (`apps/web/package.json`) and directly inside each directory of a pair (`backend/go.mod`) for a manifest; when the root has no recognised manifest, check every immediate subdirectory of the root - a manifest found there fills the fields as a root one would, and several such manifests are a monorepo (Step 3 picks the primary). That one extra level, no deeper.

## Patterns

### Step 1 - File-based detection

Check marker files in the project root.

| Marker File(s)                                  | Language                        |
| ----------------------------------------------- | ------------------------------- |
| `build.gradle` / `build.gradle.kts` / `pom.xml` | Java; Kotlin when a Kotlin plugin is declared (`org.jetbrains.kotlin.*` or `kotlin("jvm")` / `kotlin("android")` / `kotlin("multiplatform")` or a version-catalog `alias(libs.plugins.<name>)` whose name contains `kotlin` in Gradle, `kotlin-maven-plugin` in `pom.xml`); an AGP 9+ Android module with no Kotlin plugin stays Java (AGP 9 compiles Kotlin built in, which the marker files cannot show) |
| `Gemfile` / `Rakefile`                          | Ruby                            |
| `go.mod`                                        | Go                              |
| `package.json`                                  | JavaScript; TypeScript when `tsconfig.json` is present |
| `Cargo.toml`                                    | Rust                            |
| `pyproject.toml` / `requirements.txt` / `Pipfile` | Python                        |
| `mix.exs`                                       | Elixir                          |
| `*.csproj` / `*.fsproj` / `*.sln` / `*.slnx`    | C# (`.csproj`), F# (`.fsproj`); a `.sln` / `.slnx` alone takes the language of the projects it references |
| `composer.json`                                 | PHP                             |
| `pubspec.yaml`                                  | Dart                            |

A root file outside this table (`build.zig`, `CMakeLists.txt`) is not a recognised manifest: Language stays `unknown` unless Step 2 supplies it, the file is recorded as the `Additional` line `Root marker: build.zig (unrecognised)`, and the one-level-down check still runs.

Refinements (apply in this priority; for an ecosystem a refinement does not list, the manifest's own dependency section names the field the same way; in a listed ecosystem, an unlisted test library names Test framework the same way (`insta` in `Cargo.toml`), and a library that is not a server framework (`clap`) leaves Framework `unknown`):

1. **Frontend meta-framework marker files** (override generic `package.json`):
   - `next.config.{js,mjs,ts,mts}` -> React (Next.js)
   - `nuxt.config.{js,ts}` -> Vue (Nuxt)
   - `angular.json` -> Angular
   - `@react-router/dev` dep, with or without `react-router.config.{js,ts}` -> React (React Router framework mode); `remix.config.*` or `@remix-run/react` dep -> React (Remix)
   - `@sveltejs/kit` dep, with or without `svelte.config.{js,ts}` (SvelteKit 3 has no config file) -> Svelte (SvelteKit); `svelte.config.{js,ts}` without it -> Svelte (Vite/custom)
2. **`package.json` dependency inspection** (when no meta-framework marker):
   - `react` + `next` -> React (Next.js)
   - `react-native` -> React Native, or React Native (Expo) with `expo`
   - `react` only -> React (Vite/CRA/custom)
   - `vue` + `nuxt` -> Vue (Nuxt)
   - `vue` only -> Vue (Vite/custom)
   - `@angular/core` -> Angular
   - `svelte` only -> Svelte (Vite/custom)
3. **Lockfile** (sets Build tool for JS/TS): `package-lock.json` -> npm, `yarn.lock` -> yarn, `pnpm-lock.yaml` -> pnpm, `bun.lock`/`bun.lockb` -> bun; with no lockfile, `package.json`'s `packageManager` field names it, version dropped (`pnpm@9.12.0` -> pnpm).
   **Other ecosystems - the marker names the build tool**: `pom.xml` -> Maven, `build.gradle*` -> Gradle, `go.mod` -> go, `Cargo.toml` -> Cargo, `Gemfile` -> Bundler, `Rakefile` alone -> Rake, `mix.exs` -> mix, `composer.json` -> Composer; Python: `poetry.lock` or `[tool.poetry]` -> Poetry, `uv.lock` -> uv, `pdm.lock` -> PDM, `Pipfile` -> Pipenv, `requirements.txt` alone -> pip, else `unknown`.
4. **ORM markers** (set ORM field): `prisma/schema.prisma` -> Prisma; `drizzle.config.{ts,js,mjs,json}` -> Drizzle; `typeorm` dependency -> TypeORM; `.sequelizerc` or `sequelize` dependency -> Sequelize; likewise `sqlalchemy`, `gorm.io/gorm`, `spring-boot-starter-data-jpa` / `hibernate`, `ecto`, `diesel` / `sea-orm`.
5. **Backend dependency inspection** (sets Framework): the marker file's own dependency declarations name the framework - `axum`/`actix-web` in `Cargo.toml`, `github.com/gin-gonic/gin` in `go.mod`, `rails`/`sinatra` in `Gemfile`, `fastapi`/`django`/`flask` in `pyproject.toml`/`requirements.txt`, `laravel/framework` in `composer.json`, `phoenix` in `mix.exs`, `spring-boot` in `build.gradle*`/`pom.xml`, `@nestjs/core`/`express` in `package.json`.
6. **Test-framework dev dependencies** (sets Test framework): a known test framework in the manifest's dev/test dependency section names it - `jest`/`vitest`/`mocha` in `package.json`, `rspec` in `Gemfile`, `minitest` in `Gemfile` or `rails` with `test/test_helper.rb` and no `rspec` (Rails ships Minitest without a gem line), `pytest` in `pyproject.toml`, `rstest` in `Cargo.toml`, `junit-jupiter`/`junit`/`spring-boot-starter-test`/`spring-boot-starter-*-test` (Boot 4, JUnit Jupiter)/`spock` in `build.gradle*`/`pom.xml`, `test` in a non-Flutter `pubspec.yaml` (item 8 governs Flutter). Go has no dev-dependency section: `testify`/`ginkgo` in `go.mod` names it, otherwise `testing` (stdlib).
7. **Database from a driver dependency** (sets Database): `pg`/`psycopg`/`psycopg2`/`asyncpg`/`jackc/pgx`/`lib/pq`/`postgresql` JDBC artifact -> PostgreSQL, `mysql2`/`trilogy`/`pymysql`/`mysqlclient`/`go-sql-driver/mysql`/`mysql-connector-j` -> MySQL, `mssql`/`tedious`/`pymssql`/`microsoft/go-mssqldb`/`mssql-jdbc` -> SQL Server, `better-sqlite3`/`sqlite3` -> SQLite; `prisma/schema.prisma` names it in `provider`. No driver -> `unknown`.
8. **`pubspec.yaml` inspection** (Dart projects): `flutter: {sdk: flutter}` under dependencies -> Framework Flutter, Build tool `flutter`, Test framework `flutter_test`; otherwise Language Dart, Build tool `dart`, Framework from declared dependencies (`shelf`/`dart_frog` -> that server framework). A Flutter project is a client-side marker for Step 3.
9. **Unity project** (overrides the `*.csproj` / `*.sln` row - Unity generates those files): `ProjectSettings/ProjectVersion.txt` at the root, or under a directory the one-level-down check visits (`client/ProjectSettings/ProjectVersion.txt`) -> Language C#, Framework `Unity <m_EditorVersion>` (`Unity 6000.3.21f1`), Build tool `Unity`, and Test framework `Unity Test Framework` when `Packages/manifest.json` lists `com.unity.test-framework`. These two files are the refinement's only reads. A Unity project is a client-side marker for Step 3.

### Step 2 - Instruction file (supplemental detail)

Read the first file that has a matching section, in this order - a file without one does not end the search, so a `CLAUDE.md` with no stack section falls through to `AGENTS.md`:

1. `./CLAUDE.md` or `.claude/CLAUDE.md`
2. `./AGENTS.md`
3. `./GEMINI.md`

Extract only the `## Tech Stack` section (or equivalent heading containing "stack", "technology", "tech"). Parse key-value lines as-is into the output fields:

- `Language: Rust` -> `Language`
- `Framework: Actix-web` -> `Framework`
- `Build: Cargo` or `Build tool: Cargo` -> `Build tool`
- `Database: PostgreSQL` -> `Database`
- `ORM: Diesel` -> `ORM`
- `Test: cargo test + rstest` or `Test framework: ...` -> `Test framework`
- Any other key (`Cache: Redis`, `Queue: Kafka`, ...) -> carried into `Additional` unchanged.

Skip silently if the section is missing.

### Step 3 - Classify Stack Type

Evaluate in this order - the first match wins:

1. `fullstack` when any trigger fires:
   - Monorepo containing both a client marker (`package.json` with React/Vue/Angular/Svelte, a Flutter `pubspec.yaml`, or a Unity project) and a backend marker (`build.gradle`, `go.mod`, a backend framework dependency, etc.).
   - Next.js with `pages/api/` or `app/api/` (each also under `src/`), or Next.js with an ORM detected (Server Components can hit the DB directly). An ORM in a backend-only project is not a trigger.
   - Nuxt with `server/`.
2. `frontend` when a client-side marker exists (frontend framework dependency or meta-framework config - a bare `package.json` is not one) and no backend marker does. A web app merely wrapped for desktop or a native shell (Electron, Tauri, Capacitor) stays `frontend`.
3. `backend` otherwise (server framework, library, CLI tool, or framework still unknown). Never leave Stack Type unset.

When several fullstack triggers fire, the monorepo rule wins.

For fullstack from two stacks (monorepo), set `Language` and `Framework` to the primary stack: the one whose manifest sits at the repo root and names a framework (a bare workspace root manifest does not count); otherwise the backend stack; between two backends, the one serving end-user traffic. Describe the secondary in `Additional` (e.g., `Frontend: TypeScript (React)`). The scalar fields (`Build tool`, `Database`, `Test framework`, `ORM`) also describe the primary stack; secondary-stack facts worth keeping append to its `Additional` entry (`Frontend: TypeScript (React, Next.js); build tool pnpm; test vitest`). Internal shared packages with no framework of their own are not surfaced. For fullstack from a single meta-framework (Next.js, Nuxt) with no second manifest, keep the meta-framework as `Framework`; there is no secondary entry.

## Output Format

Single canonical schema. Workflow skills parse this; do not change field names.

```
Detected stack:
  Stack Type: {backend | frontend | fullstack}
  Language: {string or "unknown"}
  Framework: {string or "unknown"}
  Build tool: {string or "unknown"}
  Database: {string or "unknown"}
  Test framework: {string or "unknown"}
  ORM: {string, omitted if not declared/detected}
  Additional: {omitted if none; otherwise one indented `key: value` line per pair}
Source: {context-file | file-detection | mixed | unknown}
Hint: add a `## Tech Stack` section to CLAUDE.md    {only when Language is unknown}
```

Contract:
- `Stack Type`, `Language`, `Framework`, `Source` are always present.
- `Source`: a source contributes when at least one output value came from it; a value present identically in both sources counts for both. `context-file` when only the instruction file contributed; `file-detection` when only marker files contributed; `mixed` when both did; `unknown` when neither did (no recognised manifest and no stack section; a `Root marker` line alone does not make marker files a contributor).
- `ORM` and `Additional` are omitted when neither source declared them; `Build tool`, `Database`, and `Test framework` are always present, written as `unknown` when undeclared.
- `unknown` for Language means consumers must fall back to language-agnostic guidance.
- This block is an input to the consuming skill, never part of the consuming skill's deliverable: a consumer surfaces the stack only through its own `**Stack:**` or `**Engine:**` slot; a consumer with neither emits nothing from it.

## Avoid

- Naming a stack the markers do not show (`Python` because the repository holds one `.py` script) - the field is `unknown`.
