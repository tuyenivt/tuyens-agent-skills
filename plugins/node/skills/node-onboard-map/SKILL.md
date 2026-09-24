---
name: node-onboard-map
description: Node.js / NestJS / Express onboarding signals: package manager, framework, tsconfig, build scripts, ORM, CJS vs ESM module system.
metadata:
  category: backend
  tags: [onboarding, codebase-map, node, nestjs, express, typescript]
user-invocable: false
---

# Node Onboard Map (atomic)

> Load `Use skill: stack-detect` first; its fields seed Stack and Tooling, and every one is re-checked against the Rules below - where they disagree (a Tech Stack line vs the lockfile, a lockfile vs `packageManager`), the value is `Conflicting` citing both. Composed by `task-onboard` when the stack is Node.js / TypeScript.

## When to Use

Workflow needs Node-specific orientation: package manager, framework, TS config, build, ORM, module system. Project has `package.json`.

## Rules

- Package manager, in precedence order: the `packageManager` field in `package.json`, then the lockfile, then the CI or Dockerfile install command. Two lockfiles are a conflict, not a choice: report both, break the tie in that order, then by whichever lockfile was committed most recently (`git log -1 -- <lockfile>`); a README instruction is documentation, not evidence. Installing with the wrong manager writes its own lockfile with different resolutions (npm 7+ also rewrites a `yarn.lock`)
- Framework: NestJS (`@nestjs/core`, `nest-cli.json`), Express (`express` without `@nestjs/core`), Fastify, Koa, plain Node. Version = the lockfile-resolved version; the `package.json` range only when no lockfile is readable
- Node version sources are pins - `package.json#volta.node`, `.nvmrc`, `.node-version`, `.tool-versions` / `mise.toml`, the Dockerfile `FROM node:<v>`, CI `setup-node` `node-version` - plus the `engines.node` **range**. Report every pin, flag pins that disagree, and check each pin against the range (a pin outside it is `Conflicting`). The instruction file's `## Tech Stack` runtime line is a declared source too. No source of any kind is a finding, not a default
- Module system is per file: `"type": "module"` sets the default for `.js`; `.mjs` / `.mts` are always ESM and `.cjs` / `.cts` always CJS, whatever `"type"` says (a `knexfile.cjs` in an ESM package is correct, not a conflict). With no `"type"`, Node 20.19+ / 22.7+ runs an ESM-syntax `.js` as ESM - report that as `Conflicting` (undeclared ESM), not as CJS. Corroborate against usage: `__dirname` and a bare `require` are CJS-only (a `require` from `createRequire(import.meta.url)` is legitimate ESM); `import.meta.url` and top-level `await` are ESM-only. For TypeScript, `compilerOptions.module` decides what is emitted (under `node16` / `nodenext`, per file from the extension and the nearest `"type"`); `moduleResolution` only decides how imports resolve: `commonjs` under `"type": "module"` crashes at load (`exports is not defined in ES module scope`); top-level `await` fails `tsc` under `module: commonjs`
- ORM and migrations: Prisma (`prisma` / `@prisma/client` dependency; schema at `prisma/schema.prisma`, a `prisma/schema/` folder, or the path in `prisma.config.ts` / `package.json#prisma.schema` (Prisma <= 6 only)), TypeORM (`typeorm` / `@nestjs/typeorm` dependency; config in a `DataSource` file or `TypeOrmModule.forRoot`), Sequelize, Drizzle, Knex (`knexfile.*`), Mongoose. More than one is a real finding: report each with its own migration command and the entities it owns
- **Report unknowns as unknowns.** Every value is observed in the evidence, `Unknown - <what would confirm it>`, or `Conflicting - <the sources and what each says>`. A file you could not read (a permission denial, outside the read set) is `Unknown - <file> not readable`, never "absent". A file that exists but carries nothing parseable (a truncated lockfile) is `Unknown - <file> unparseable`. Git history (`git log`) and incident or design docs in the repo are evidence: a commit message may explain a mid-migration state and an incident doc may corroborate a hotspot - cite each as the source

## Patterns

### Package Manager

| Lockfile | Manager | Install | Run a local bin | One-off (fetches latest) |
| -------- | ------- | ------- | --------------- | ------------------------ |
| `package-lock.json` | npm | `npm ci` / `npm install` | `npx <bin>` | `npx <pkg>` |
| `yarn.lock` (`# yarn lockfile v1`) | Yarn 1 | `yarn install --frozen-lockfile` | `yarn <bin>` | - |
| `yarn.lock` (`__metadata:` block) | Yarn Berry | `yarn install --immutable` | `yarn <bin>` | `yarn dlx <pkg>` |
| `pnpm-lock.yaml` | pnpm | `pnpm install --frozen-lockfile` | `pnpm exec <bin>` | `pnpm dlx <pkg>` |
| `bun.lock` / `bun.lockb` | Bun | `bun install --frozen-lockfile` | `bunx <bin>` | `bunx <pkg>` |

Migration and tool commands use the **local-bin** form - `dlx` ignores the project's pinned version (`pnpm dlx prisma` runs the latest Prisma CLI against the project's client). `packageManager` (or `.yarnrc.yml` `yarnPath`) decides which Yarn runs; the `yarn.lock` header shows which Yarn last wrote the lockfile - a `yarn@4` pin over a v1 header is a half-finished migration (`Conflicting`), and the next install rewrites the lockfile. The manager major comes from the `packageManager` version, else the lockfile format (`package-lock.json` `lockfileVersion`, `pnpm-lock.yaml` `lockfileVersion: '9.0'` = pnpm 9/10, the `yarn.lock` header). A script in `package.json` beats the canonical command: run `pnpm prisma:migrate` rather than `pnpm exec prisma migrate dev` when the script exists, since it carries the project's own flags and env.

### Bootstrap

1. Node version: activate the pin (`nvm use` reads `.nvmrc`; `fnm use` reads `.nvmrc` / `.node-version`, and `engines.node` when neither exists; Volta reads `package.json#volta` automatically; `asdf install` / `mise install` read `.tool-versions` / `mise.toml`).
2. When `packageManager` names pnpm or Yarn: `corepack enable` first (Node 25+ no longer bundles Corepack - `npm i -g corepack`); an `npm@` pin needs `corepack enable npm`; Bun is installed separately. Then install with the detected manager.
3. Local services: `compose.yaml` / `compose.yml` / `docker-compose.yaml` / `docker-compose.yml` for DB/Redis; env from a template (`.env.example`, `.env.sample`, `.env.template`) or the config validation schema (`@nestjs/config` + Joi/Zod, `envalid`). Cross-check compose services against runtime deps - a `bullmq` dependency with no Redis service and no external `REDIS_URL` in the env template is a first-run failure (connection-retry spam or hung jobs) a joiner will read as "my machine is broken". No template and no schema is `BLOCKED - no env contract`.
4. Migrations, per ORM (local-bin form; a script wins): Prisma `prisma migrate dev` (Prisma 7+: then `prisma generate` and `prisma db seed` explicitly) | TypeORM 0.3 `typeorm-ts-node-commonjs migration:run -d src/data-source.ts` (`-esm` for ESM) | Sequelize `sequelize-cli db:migrate` | Drizzle `drizzle-kit migrate` | Knex `knex migrate:latest` | Mongoose: none built in - check for `migrate-mongo` / `ts-migrate-mongoose` (`migrate-mongo-config.js`, `migrations/`) before calling the schema unversioned.
5. Run: the observed `dev` / `start:dev` script. NestJS `start:dev`; Express `dev` (often `tsx watch`); Fastify / Koa: the script that starts `fastify.listen` / `app.listen`.
6. Verify, first available: an observed `/health` route | the path passed to `SwaggerModule.setup(path, ...)` | any other observed public route. Prefix a route with an observed `app.setGlobalPrefix(...)` unless its `exclude` list names it; prefix the Swagger path only when `SwaggerModule.setup` passes `useGlobalPrefix: true`. A route a hotspot shows is broken (a dead `@Public()`) is not a verify step - take the next one. A probe path in a k8s manifest with no route behind it is a claim, not an observed route. When none was observed, the step is `BLOCKED` - "no health endpoint" is a finding only if the routes were actually enumerated.

### Key Files

| Framework | Entry | Routing | Other |
|-----------|-------|---------|-------|
| NestJS | `src/main.ts` (`NestFactory.create`) | `src/<feature>/*.controller.ts` | `src/app.module.ts` root module, `nest-cli.json`, `test/` e2e |
| Express | `src/index.ts` / `src/app.ts` | `src/routes/` | `src/middleware/`, `src/services/` |
| Fastify | the file calling `fastify.listen` | `app.register(plugin)` plugins | `fastify-plugin` wrappers |
| Koa | the file calling `app.listen` | `@koa/router` routers | `app.use` middleware order |

### Package Layout

- **Feature-package** (NestJS default): `src/orders/{controller,service,module,dto,entities}` - cross-feature imports via the feature's module exports.
- **Layer-package** (Express convention): `src/controllers/`, `src/services/`, `src/repositories/`, `src/routes/`, `src/middleware/`.
- **Mixed**: feature-package next to legacy layer dirs - project mid-migration. New code goes in feature side; confirm direction before adding files.

### Conventions

- **Lint:** ESLint (`eslint.config.*` flat config, the default since ESLint 9; a legacy `.eslintrc.*` works on ESLint <= 9 only and is ignored by 10 - flag it) or Biome (`biome.json` / `biome.jsonc`, lint + format); **Format:** Prettier or Biome.
- **Validation:** `class-validator` (NestJS), `zod` (Express).
- **Logging:** `pino`, `winston`, or NestJS Logger.
- **Testing:** Jest (primary runner for `task-node-test` / `node-testing-patterns`). A framework named only in a script and absent from the dependencies is `Unknown - not installed` - except the built-in runners (`node --test`, `bun test`), which the script alone establishes. Vitest is out of scope for those skills - the scaffolding translates, the Jest-specific snippets do not; flag it.
- **Types:** `@types/node` in `devDependencies` when the code uses `process`, `Buffer`, `__dirname`, or `require` from TypeScript. Strict mode is `strict` after following the tsconfig `extends` chain.
- **Port and build:** the port is the `listen` argument (`process.env.PORT ?? 3000`) and any compose mapping; the build/deploy path is the `build` script plus a `Dockerfile` or deploy manifest (k8s, ECS task definition).

### Risk Hotspots

- **Event-loop blocking** (`readFileSync`, `crypto.pbkdf2Sync`, large `JSON.parse`, missing `await`): see `node-typescript-patterns`, `task-node-review-perf`.
- **N+1 / over-fetch / ORM client lifetime** (per-request Prisma client, a fluent-API call in a loop, missing `include`/`relations`; TypeORM `eager: true` joins the relation on every `find*` - over-fetch, ignored by QueryBuilder): see `node-prisma-patterns` / `node-typeorm-patterns`.
- **BullMQ**: enqueue in a transaction, entities in payloads, worker `concurrency` above the process's DB pool (a silent queue stall, not a DB error): see `node-bullmq-patterns`.
- **Mass assignment / validation**: missing `ValidationPipe whitelist`, request data spread onto entities: see `task-node-review-security`.
- **Migration safety**: `synchronize: true` in prod, migrations run per replica, missing `CONCURRENTLY` on hot tables: see `node-migration-safety`.
- **Module system**: `require` of an ESM-only package (chalk 5, node-fetch 3, nanoid 4) throws `ERR_REQUIRE_ESM` below Node 20.19 / 22.12; from those versions `require(esm)` loads unless the ESM graph uses top-level `await`, but returns the namespace - a default export is at `.default`, so code written for the CommonJS major still breaks. ESM `__dirname` undefined.
- **Framework wiring**: NestJS singleton -> request-scoped propagation, a `@Public()` the global guard never reads, a provider or controller no module registers (dead wiring), `forwardRef` overuse; Express middleware order (error handler before routers, auth mounted globally).
- **Unhandled rejections**: no backstop, or Express 4 async handlers without a wrapper.

### First-PR Safe Zones

Safe: new NestJS feature module, new Express route in existing file, unit test next to a service, env var in the env template.

Riskier: `app.module.ts` / `main.ts` (boot flow), migrations, auth guards, logging/interceptor config.

When the joiner's first task is known, scope both lists to it: name the files that task will touch (or say the model or module it needs does not exist yet), and name the one adjacent change that looks like a one-line fix but has blast radius beyond the diff (removing `eager: true`, widening a shared DTO, renaming a queue).

## Output Format

Inject into `task-onboard`'s report, which owns the section order and envelope: Stack and Tooling -> `## Stack` (extra rows; a `Conflicting` value keeps its sources in the row), Local Bootstrap -> `## Local Quickstart`, Architecture Map -> `## Architecture`, Conventions -> `## Key Patterns and Conventions`, Risk Hotspots -> `## Tech Debt and Risk Hotspots` (each hotspot a finding; a conflict is Medium, High when installing or running with the wrong tool corrupts state; a category checked with nothing observed goes on its `Checked clean:` line), First-PR Safe Zones -> its First-PR Safe Zones subsection. Invoked standalone, the six area names below are `##` headings in this order. Every value is `<observed value>`, `Unknown - <what would confirm it>`, or `Conflicting - <the sources and what each says>`; a conflict also becomes a Risk Hotspot finding. Any step or check that cannot proceed on the available evidence is `BLOCKED - <what is missing>`, in any section.

- **Stack and Tooling**: package manager (+ major), Node version (every pin + the `engines` range), framework + resolved version, TypeScript + strict mode + `module` / `moduleResolution`, ORM(s), module system (per the Rules).
- **Local Bootstrap**: Node activation, Corepack when needed, install, local services (compose file + services, cross-checked against runtime deps), env contract, migrations (per ORM), run, port, health check, and the build/deploy path (`build` script, `Dockerfile`) - its absence is itself a finding.
- **Architecture Map**: module/feature layout, entry point, ORM entity/schema location, middleware or plugin pipeline.
- **Conventions**: lint + format, validation lib, logger, test framework, `@types/node`.
- **Risk Hotspots**: one entry per category in Patterns > Risk Hotspots, in that order; a category with nothing observed is listed as not observed rather than dropped, so a clean repo and an unread one look different. A hotspot you observed that matches no listed category still gets an entry - name it and cite `file:line`.
- **First-PR Safe Zones**: scoped to observed structure, and to the first task when one is given.

## Avoid

- npm commands when the project uses pnpm/Yarn/Bun
- Treating CJS and ESM as interchangeable
- Glossing over NestJS provider scopes
- TypeORM patterns on a Prisma project (or vice versa)
