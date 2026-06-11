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
- **Read narrowly.** Check only marker files and the `## Tech Stack` section of one instruction file. Do not scan the whole project.

## Patterns

### Step 1 - File-based detection (zero-cost, reliable)

Check marker files in the project root.

| Marker File(s)                                  | Ecosystem                       |
| ----------------------------------------------- | ------------------------------- |
| `build.gradle` / `build.gradle.kts` / `pom.xml` | Java                            |
| `Gemfile` / `Rakefile`                          | Ruby                            |
| `go.mod`                                        | Go                              |
| `package.json`                                  | JavaScript/TypeScript           |
| `Cargo.toml`                                    | Rust                            |
| `pyproject.toml` / `requirements.txt`           | Python                          |
| `mix.exs`                                       | Elixir                          |
| `*.csproj` / `*.sln`                            | .NET                            |
| `composer.json`                                 | PHP                             |

Refinements (apply in this priority):

1. **Frontend meta-framework marker files** (override generic `package.json`):
   - `next.config.{js,mjs,ts}` -> React (Next.js)
   - `nuxt.config.{js,ts}` -> Vue (Nuxt)
   - `angular.json` -> Angular
   - `remix.config.*` or `app/root.tsx` with `@remix-run` dep -> React (Remix)
2. **`package.json` dependency inspection** (when no meta-framework marker):
   - `react` + `next` -> React (Next.js)
   - `react` + `@remix-run/react` -> React (Remix)
   - `react` only -> React (Vite/CRA/custom)
   - `vue` + `nuxt` -> Vue (Nuxt)
   - `vue` only -> Vue (Vite/custom)
   - `@angular/core` -> Angular
3. **`tsconfig.json` alongside `package.json`** -> Language: TypeScript.
4. **ORM markers** (set ORM field):
   - `prisma/schema.prisma` -> Prisma
   - `drizzle.config.ts` -> Drizzle
   - `ormconfig.json` / `data-source.ts` -> TypeORM
   - `.sequelizerc` / `sequelize.config.js` -> Sequelize
5. **Backend dependency inspection** (sets Framework): the marker file's own dependency declarations name the framework - `axum`/`actix-web` in `Cargo.toml`, `gin` in `go.mod`, `rails`/`sinatra` in `Gemfile`, `fastapi`/`django`/`flask` in `pyproject.toml`/`requirements.txt`, `laravel/framework` in `composer.json`, `phoenix` in `mix.exs`, `spring-boot` in `build.gradle*`/`pom.xml`, `@nestjs/core`/`express` in `package.json`. Same move for unlisted ecosystems: read the manifest's dependency section.

File-based detection can determine Language, Build tool, sometimes Framework and ORM. It cannot determine Database or Test framework.

### Step 2 - Instruction file (supplemental detail)

Read the first file found, in this order:

1. `./CLAUDE.md` or `.claude/CLAUDE.md`
2. `./AGENTS.md`
3. `./GEMINI.md`

Extract only the `## Tech Stack` section (or equivalent heading containing "stack", "technology", "tech"). Parse key-value lines as-is:

- `Language: Rust` -> language = "Rust"
- `Framework: Actix-web` -> framework
- `Build: Cargo` -> build_tool
- `Database: PostgreSQL` -> database
- `ORM: Diesel` -> orm
- `Test: cargo test + rstest` -> test_framework
- Any other key (`Cache: Redis`, `Queue: Kafka`, ...) -> carried into `Additional` unchanged.

Skip silently if the section is missing. Per the precedence rule, instruction-file values override marker-file inference for overlapping fields.

If no language results from either step, emit `language: unknown` and suggest the user add a `## Tech Stack` section.

### Step 3 - Classify Stack Type

| Stack Type  | Condition                                                                                              |
| ----------- | ------------------------------------------------------------------------------------------------------ |
| `frontend`  | React/Vue/Angular/Svelte SPA or SSR framework with no server-side routes or backend marker             |
| `backend`   | Server framework (Spring, Django, FastAPI, Rails, NestJS, Express, Gin, Axum, ASP.NET, etc.)           |
| `fullstack` | Both frontend and backend present, OR a meta-framework with server capability (see fullstack triggers) |

No row matches (library, CLI tool, framework still unknown): fall back to `frontend` if only frontend markers exist, otherwise `backend`. Never leave Stack Type unset.

Fullstack triggers:
- Next.js with `app/api/`, Server Actions, or any DB ORM detected (Server Components can hit the DB directly).
- Nuxt with `server/`.
- Monorepo containing both `package.json` (with React/Vue/Angular) and a backend marker (`build.gradle`, `go.mod`, etc.).

For fullstack, set `Language` and `Framework` to the primary stack and describe the secondary in `Additional` (e.g., `Frontend: TypeScript (React)`).

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
  Additional: {key-value pairs, omitted if none}
Source: {context-file | file-detection | mixed | unknown}
```

Contract:
- `Stack Type`, `Language`, `Framework`, `Source` are always present.
- `Source`: a source contributes only if at least one of its values survives into the output (fully overridden inference does not count). `context-file` when only the instruction file contributed; `file-detection` when only marker files contributed; `mixed` when both did.
- Fields beyond the required four may be omitted when neither source declared them.
- `unknown` for Language means consumers must fall back to language-agnostic guidance.

## Avoid

- Hard-coding stack assumptions instead of detecting.
- Reading the whole project to detect - check only marker files and one `## Tech Stack` section.
- Maintaining a closed enum of valid frameworks or rejecting unfamiliar values.
- Failing loudly on inconclusive detection - emit `unknown` and continue.
