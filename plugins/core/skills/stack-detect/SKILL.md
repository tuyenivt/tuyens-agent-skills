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

- **Never guess.** If a field cannot be determined, emit `unknown`.
- **Detect silently.** Do not prompt the user for stack information.
- **Pass through, do not validate.** Any value is valid; no fixed enum of allowed languages or frameworks.
- **Precedence: explicit declarations beat inference.** When both an instruction file's `## Tech Stack` and marker-file inference provide the same field, the instruction file wins (it carries author intent and specificity like "Java 21" vs generic "Java ecosystem"). Marker files fill fields the instruction file omits.
- **Degrade gracefully.** If detection is inconclusive, emit `unknown` and let consumers proceed; do not fail loudly.
- **Read narrowly.** Check only marker files and the `## Tech Stack` section of at most one instruction file (the first in Step 2's order that has the section). Do not scan the whole project. When a monorepo layout is evident (`apps/`, `packages/`, `services/`, or a pair such as `frontend/`+`backend/` or `client/`+`server/`), also check each of those directories' immediate subdirectories for a manifest (`apps/web/package.json`); when the root has no recognised manifest, check every immediate subdirectory of the root. That one extra level, no deeper.

## Patterns

### Step 1 - File-based detection (zero-cost, reliable)

Check marker files in the project root.

| Marker File(s)                                  | Language                        |
| ----------------------------------------------- | ------------------------------- |
| `build.gradle` / `build.gradle.kts` / `pom.xml` | Java; Kotlin when the Kotlin JVM plugin is declared |
| `Gemfile` / `Rakefile`                          | Ruby                            |
| `go.mod`                                        | Go                              |
| `package.json`                                  | JavaScript; TypeScript when `tsconfig.json` is present |
| `Cargo.toml`                                    | Rust                            |
| `pyproject.toml` / `requirements.txt`           | Python                          |
| `mix.exs`                                       | Elixir                          |
| `*.csproj` / `*.fsproj` / `*.sln`               | C# (`.csproj`), F# (`.fsproj`)  |
| `composer.json`                                 | PHP                             |
| `pubspec.yaml`                                  | Dart                            |

A root file outside this table (`build.zig`, `CMakeLists.txt`) is not a recognised manifest: Language stays `unknown` unless Step 2 supplies it, and the one-level-down check still runs.

Refinements (apply in this priority):

1. **Frontend meta-framework marker files** (override generic `package.json`):
   - `next.config.{js,mjs,ts}` -> React (Next.js)
   - `nuxt.config.{js,ts}` -> Vue (Nuxt)
   - `angular.json` -> Angular
   - `react-router.config.{js,ts}` with `@react-router/dev` dep -> React (React Router framework mode); `remix.config.*` or `@remix-run/react` dep -> React (Remix)
   - `svelte.config.js` with `@sveltejs/kit` dep -> Svelte (SvelteKit); `svelte.config.js` alone -> Svelte (Vite/custom)
2. **`package.json` dependency inspection** (when no meta-framework marker):
   - `react` + `next` -> React (Next.js)
   - `react` only -> React (Vite/CRA/custom)
   - `vue` + `nuxt` -> Vue (Nuxt)
   - `vue` only -> Vue (Vite/custom)
   - `@angular/core` -> Angular
   - `svelte` only -> Svelte (Vite/custom)
3. **Lockfile** (sets Build tool for JS/TS): `package-lock.json` -> npm, `yarn.lock` -> yarn, `pnpm-lock.yaml` -> pnpm, `bun.lock`/`bun.lockb` -> bun.
   **Other ecosystems - the marker names the build tool**: `pom.xml` -> Maven, `build.gradle*` -> Gradle, `go.mod` -> go, `Cargo.toml` -> Cargo, `Gemfile` -> Bundler, `Rakefile` alone -> Rake, `mix.exs` -> mix, `composer.json` -> Composer; Python: `poetry.lock` -> Poetry, `uv.lock` -> uv, else pip.
4. **ORM markers** (set ORM field): `prisma/schema.prisma` -> Prisma; `drizzle.config.{ts,js,mjs,json}` -> Drizzle; `typeorm` dependency -> TypeORM; `.sequelizerc` or `sequelize` dependency -> Sequelize. Same move for unlisted ecosystems: an ORM dependency in the manifest names it (`sqlalchemy`, `gorm.io/gorm`, `spring-boot-starter-data-jpa` / `hibernate`, `ecto`, `diesel` / `sea-orm`).
5. **Backend dependency inspection** (sets Framework): the marker file's own dependency declarations name the framework - `axum`/`actix-web` in `Cargo.toml`, `github.com/gin-gonic/gin` in `go.mod`, `rails`/`sinatra` in `Gemfile`, `fastapi`/`django`/`flask` in `pyproject.toml`/`requirements.txt`, `laravel/framework` in `composer.json`, `phoenix` in `mix.exs`, `spring-boot` in `build.gradle*`/`pom.xml`, `@nestjs/core`/`express` in `package.json`. Same move for unlisted ecosystems: read the manifest's dependency section.
6. **Test-framework dev dependencies** (sets Test framework): a known test framework in the manifest's dev/test dependency section names it - `jest`/`vitest`/`mocha` in `package.json`, `rspec`/`minitest` in `Gemfile`, `pytest` in `pyproject.toml`, `rstest` in `Cargo.toml`, `junit-jupiter`/`junit`/`spring-boot-starter-test`/`spock` in `build.gradle*`/`pom.xml`, `test` in a non-Flutter `pubspec.yaml` (item 8 governs Flutter). Go has no dev-dependency section: `testify`/`ginkgo` in `go.mod` names it, otherwise `testing` (stdlib). Same move for unlisted ecosystems.
7. **Database from a driver dependency** (sets Database): `pg`/`psycopg`/`jackc/pgx`/`postgresql` JDBC artifact -> PostgreSQL, `mysql2`/`pymysql`/`go-sql-driver/mysql`/`mysql-connector-j` -> MySQL, `better-sqlite3`/`sqlite3` -> SQLite; `prisma/schema.prisma` names it in `provider`. No driver -> `unknown`.
8. **`pubspec.yaml` inspection** (Dart projects): `flutter: {sdk: flutter}` under dependencies -> Framework Flutter, Build tool `flutter`, Test framework `flutter_test`; otherwise Language Dart, Build tool `dart`, Framework from declared dependencies (`shelf`/`dart_frog` -> that server framework).

### Step 2 - Instruction file (supplemental detail)

Read the first file that has a matching section, in this order - a file without one does not end the search, so a `CLAUDE.md` with no stack section falls through to `AGENTS.md`:

1. `./CLAUDE.md` or `.claude/CLAUDE.md`
2. `./AGENTS.md`
3. `./GEMINI.md`

Extract only the `## Tech Stack` section (or equivalent heading containing "stack", "technology", "tech"). Parse key-value lines as-is into the output fields:

- `Language: Rust` -> `Language`
- `Framework: Actix-web` -> `Framework`
- `Build: Cargo` -> `Build tool`
- `Database: PostgreSQL` -> `Database`
- `ORM: Diesel` -> `ORM`
- `Test: cargo test + rstest` -> `Test framework`
- Any other key (`Cache: Redis`, `Queue: Kafka`, ...) -> carried into `Additional` unchanged.

Skip silently if the section is missing. Per the precedence rule, instruction-file values override marker-file inference for overlapping fields.

### Step 3 - Classify Stack Type

Evaluate in this order - the first match wins:

1. `fullstack` when any trigger fires:
   - Monorepo containing both a client marker (`package.json` with React/Vue/Angular/Svelte) and a backend marker (`build.gradle`, `go.mod`, a backend framework dependency, etc.).
   - Next.js with `app/api/` or `pages/api/`, or Next.js with an ORM detected (Server Components can hit the DB directly). An ORM in a backend-only project is not a trigger.
   - Nuxt with `server/`.
2. `frontend` when a client-side marker exists (frontend framework dependency or meta-framework config - a bare `package.json` is not one) and no backend marker does. A web app merely wrapped for desktop or a native shell (Electron, Tauri, Capacitor) stays `frontend` - its toolchain and guidance are the web's.
3. `backend` otherwise (server framework, library, CLI tool, or framework still unknown). Never leave Stack Type unset.

When more than one fullstack trigger fires, the monorepo rule wins: two separate manifests are a stronger signal than one meta-framework's server capability.

For fullstack from two stacks (monorepo), set `Language` and `Framework` to the primary stack: the one whose manifest sits at the repo root and names a framework (a bare workspace root manifest does not count); otherwise the backend stack; between two backends, the one serving end-user traffic. Describe the secondary in `Additional` (e.g., `Frontend: TypeScript (React)`). The scalar fields (`Build tool`, `Database`, `Test framework`, `ORM`) also describe the primary stack; secondary-stack facts worth keeping (its build tool, ORM, test framework) append to its `Additional` entry. Internal shared packages with no framework of their own are not surfaced. For fullstack from a single meta-framework (Next.js, Nuxt) with no second manifest, keep the meta-framework as `Framework`; there is no secondary entry.

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
- `Source`: a source contributes when at least one output value came from it; a value present identically in both sources counts for both. `context-file` when only the instruction file contributed; `file-detection` when only marker files contributed; `mixed` when both did; `unknown` when neither did (no recognised manifest and no stack section).
- `ORM` and `Additional` are omitted when neither source declared them; `Build tool`, `Database`, and `Test framework` are always present, written as `unknown` when undeclared.
- `unknown` for Language means consumers must fall back to language-agnostic guidance.
- This block is an input to the consuming skill, never part of the consuming skill's deliverable: a consumer surfaces the stack only through its own `**Stack:**` slot, if it has one.

## Avoid

- Hard-coding stack assumptions instead of detecting.
- Reading the whole project to detect - check only marker files and one `## Tech Stack` section.
- Maintaining a closed enum of valid frameworks or rejecting unfamiliar values.
- Failing loudly on inconclusive detection - emit `unknown` and continue.
