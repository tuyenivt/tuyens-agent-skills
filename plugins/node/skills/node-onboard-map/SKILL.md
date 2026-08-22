---
name: node-onboard-map
description: Node.js / NestJS / Express onboarding signals: package manager, framework, tsconfig, build scripts, ORM, CJS vs ESM module system.
metadata:
  category: backend
  tags: [onboarding, codebase-map, node, nestjs, express, typescript]
user-invocable: false
---

# Node Onboard Map (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when the stack is Node.js / TypeScript.

## When to Use

Workflow needs Node-specific orientation: package manager, framework, TS config, build, ORM, module system. Project has `package.json`.

## Rules

- Detect package manager from lockfile - command set differs. Two lockfiles is a conflict, not a choice: report both and say that installing with the wrong one rewrites the other. Break the tie in order - `packageManager` in `package.json`, then the CI or Dockerfile install command, then whichever lockfile was committed most recently (`git log -1 -- <lockfile>`). A README instruction is documentation, not evidence.
- Detect framework: NestJS (`nest-cli.json`, `@nestjs/*`), Express (`express` dep), Fastify, Koa, plain Node.
- Detect Node version in precedence order `volta` > `engines.node` > `.nvmrc`, and report every source that disagrees rather than picking silently. All three absent is a finding, not a default.
- Detect module system: `"type": "module"` -> ESM, else CJS. Corroborate against usage: `__dirname` and `require()` are CJS-only, `import.meta.url` and top-level `await` are ESM-only. Any of them contradicting the declaration is a conflict, not a detail - a bare `require` in a `"type": "module"` package is a runtime crash at import, and `tsc`'s `module` setting decides which way it breaks.
- Detect ORM: Prisma (`schema.prisma`), TypeORM (`data-source.ts`), Sequelize, Drizzle, Mongoose. More than one is a real finding: report each with its own migration command, and flag which entities each owns.
- **Report unknowns as unknowns.** Every claim is either observed in the given evidence or marked `unverified`. A required field with no evidence (strict mode with no visible `tsconfig` contents, a port with no `listen` call, a health route that does not exist) is emitted as `Unknown - <what would confirm it>`. Never infer a plausible value to fill a slot.

## Patterns

### Package Manager

| Lockfile            | Manager | Commands                          |
| ------------------- | ------- | --------------------------------- |
| `package-lock.json` | npm     | `npm install`, `npm run`, `npx`   |
| `yarn.lock`         | Yarn    | `yarn install`; `yarn dlx` (Berry) or `yarn <bin>` (v1) |
| `pnpm-lock.yaml`    | pnpm    | `pnpm install`, `pnpm dlx`        |
| `bun.lock` / `bun.lockb` | Bun | `bun install`, `bun run`          |

Yarn 1 and Berry share `yarn.lock`; the discriminator is `packageManager` in `package.json` or a `.yarnrc.yml`. `dlx` and `--immutable` are Berry-only, so state the major before giving commands.

A script in `package.json` beats the canonical command: run `pnpm prisma:migrate` rather than `npx prisma migrate dev` when the script exists, since it carries the project's own flags and env.

### Bootstrap

1. Node version: `.nvmrc` / `engines.node` via `nvm` / `fnm` / `volta`.
2. Install via detected manager.
3. Local services: `compose.yml` / `docker-compose.yaml` for DB/Redis; env from `.env.example`. Cross-check the compose services against runtime deps - a `bullmq` dependency with no Redis service is a boot failure a joiner will read as "my machine is broken". Missing `.env.example` blocks this step; say so rather than inventing variables.
4. Migrations (substitute detected manager for `npm`/`npx`): Prisma `npx prisma migrate dev` | TypeORM `npm run typeorm:migration:run` | Sequelize `npx sequelize-cli db:migrate` | Drizzle `npx drizzle-kit migrate`. Mongoose has no migration tool - its schema is unversioned; say so when it is present.
5. Run: NestJS `npm run start:dev` | Express `npm run dev` (often `tsx watch`) | Bun `bun run dev`.
6. Verify, first available: an observed `/health` route | `/api` when a `SwaggerModule.setup` call is observed | any other observed route. When none was observed, the step is `BLOCKED` - "no health endpoint" is a finding only if the routes were actually enumerated.

### Key Files

**NestJS**

| Location                  | Purpose                          |
| ------------------------- | -------------------------------- |
| `nest-cli.json`           | CLI config                       |
| `src/main.ts`             | `NestFactory.create(AppModule)`  |
| `src/app.module.ts`       | Root module                      |
| `src/<feature>/`          | Feature modules (ctrl/svc/dto)   |
| `tsconfig.json`           | TS config                        |
| `test/`                   | E2E tests                        |

**Express**

| Location                              | Purpose            |
| ------------------------------------- | ------------------ |
| `src/index.ts` or `app.ts`            | App setup          |
| `src/routes/`                         | Route handlers     |
| `src/middleware/`                     | Custom middleware  |
| `src/services/` or `src/controllers/` | Business logic     |

### Package Layout

- **Feature-package** (NestJS default): `src/orders/{controller,service,module,dto,entities}` - cross-feature imports via the feature's module exports.
- **Layer-package** (Express convention): `src/controllers/`, `src/services/`, `src/repositories/`, `src/routes/`, `src/middleware/`.
- **Mixed**: feature-package next to legacy layer dirs - project mid-migration. New code goes in feature side; confirm direction before adding files.

### Conventions

- **Lint:** ESLint (`.eslintrc.*`); **Format:** Prettier.
- **Validation:** `class-validator` (NestJS), `zod` (Express).
- **Logging:** `pino`, `winston`, or NestJS Logger.
- **Testing:** Jest (NestJS default, primary runner used by `task-node-test` / `node-testing-patterns`). Vitest is out of scope - if the project uses Vitest, the test scaffolding patterns translate but the workflow's Jest-specific snippets do not; flag this in the onboarding report.

### Risk Hotspots

- **Event-loop blocking** (`readFileSync`, `crypto.pbkdf2Sync`, large `JSON.parse`, missing `await`): see `node-typescript-patterns`, `task-node-review-perf`.
- **N+1 / ORM client lifetime** (per-request Prisma client, TypeORM `eager: true`, missing `include`/`relations`): see `node-prisma-patterns` / `node-typeorm-patterns`.
- **BullMQ in transaction**, entities in payloads, and worker `concurrency` above the process's DB pool (a silent queue stall, not a DB error): see `node-bullmq-patterns`.
- **Mass assignment / prototype pollution**, missing `ValidationPipe whitelist` / Zod `.strict()`: see `task-node-review-security`.
- **Migration safety**: `synchronize: true` in prod, missing CONCURRENTLY on hot tables: see `node-migration-safety`.
- **Node quirks**: NestJS singleton -> request-scoped (captive dependency), Express middleware order, ESM `__dirname` undefined, `as any` escape hatches, `forwardRef` overuse.

### First-PR Safe Zones

Safe: new NestJS feature module, new Express route in existing file, unit test next to a service, env var in `.env.example`.

Riskier: `app.module.ts` / `main.ts` (boot flow), migrations, auth guards, logging/interceptor config.

When the joiner's first task is known, scope both lists to it: name the files that task will touch, and name the one adjacent change that looks like a one-line fix but has blast radius beyond the diff (removing `eager: true`, widening a shared DTO, renaming a queue).

## Output Format

Inject into `task-onboard` sections. Every value is `<observed value>`, `Unknown - <what would confirm it>`, or `Conflicting - <the sources and what each says>`; a conflict also gets a Risk Hotspot row. Any step or check that cannot proceed on the available evidence is `BLOCKED - <what is missing>`, in any section. A hotspot category with nothing observed is listed as not observed rather than dropped, so a clean repo and an unread one look different.

- **Stack and Tooling**: package manager (+ major), Node version, framework + version, TS + strict mode, ORM(s), ESM/CJS.
- **Local Bootstrap**: install, env file, run, port, health-check, and the build/deploy path (`build` script, `Dockerfile`) - its absence is itself a finding.
- **Architecture Map**: module/feature layout, entry point, ORM entity/schema location, middleware pipeline.
- **Conventions**: TS strict mode, ESLint config, validation lib, logger, test framework.
- **Risk Hotspots**: sync I/O, unhandled rejection, NestJS scope mismatch, ESM/CJS boundary, ORM client lifetime.
- **First-PR Safe Zones**: scoped to observed structure.

## Avoid

- npm commands when the project uses pnpm/Yarn/Bun
- Treating CJS and ESM as interchangeable
- Glossing over NestJS provider scopes
- TypeORM patterns on a Prisma project (or vice versa)
- Ignoring `engines.node` mismatches
