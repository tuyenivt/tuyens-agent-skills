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

- Detect package manager from lockfile - command set differs.
- Detect framework: NestJS (`nest-cli.json`, `@nestjs/*`), Express (`express` dep), Fastify, Koa, plain Node.
- Detect Node version (`.nvmrc`, `engines.node`, `volta`); module system (`"type": "module"` -> ESM, else CJS).
- Detect ORM: Prisma (`schema.prisma`), TypeORM (`data-source.ts`), Sequelize, Drizzle, Mongoose.

## Patterns

### Package Manager

| Lockfile            | Manager | Commands                          |
| ------------------- | ------- | --------------------------------- |
| `package-lock.json` | npm     | `npm install`, `npm run`, `npx`   |
| `yarn.lock`         | Yarn    | `yarn install`, `yarn dlx`        |
| `pnpm-lock.yaml`    | pnpm    | `pnpm install`, `pnpm dlx`        |
| `bun.lockb`         | Bun     | `bun install`, `bun run`          |

### Bootstrap

1. Node version: `.nvmrc` / `engines.node` via `nvm` / `fnm` / `volta`.
2. Install via detected manager.
3. Local services: `compose.yml` for DB/Redis; env from `.env.example`.
4. Migrations: Prisma `npx prisma migrate dev` | TypeORM `npm run typeorm:migration:run` | Sequelize `npx sequelize-cli db:migrate` | Drizzle `npx drizzle-kit migrate`.
5. Run: NestJS `npm run start:dev` | Express `npm run dev` (often `tsx watch`) | Bun `bun run dev`.
6. Verify: `/health` if implemented; `/api` Swagger if NestJS.

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
- **Testing:** Jest (NestJS default), Vitest.

### Risk Hotspots

- **Event-loop blocking** (`readFileSync`, `crypto.pbkdf2Sync`, large `JSON.parse`, missing `await`): see `node-typescript-patterns`, `task-node-review-perf`.
- **N+1 / ORM client lifetime** (per-request Prisma client, TypeORM `eager: true`, missing `include`/`relations`): see `node-prisma-patterns` / `node-typeorm-patterns`.
- **BullMQ in transaction**, entities in payloads: see `node-bullmq-patterns`.
- **Mass assignment / prototype pollution**, missing `ValidationPipe whitelist` / Zod `.strict()`: see `task-node-review-security`.
- **Migration safety**: `synchronize: true` in prod, missing CONCURRENTLY on hot tables: see `node-migration-safety`.
- **Node quirks**: NestJS singleton -> request-scoped (captive dependency), Express middleware order, ESM `__dirname` undefined, `as any` escape hatches, `forwardRef` overuse.

### First-PR Safe Zones

Safe: new NestJS feature module, new Express route in existing file, unit test next to a service, env var in `.env.example`.

Riskier: `app.module.ts` / `main.ts` (boot flow), migrations, auth guards, logging/interceptor config.

## Output Format

Inject into `task-onboard` sections:

- **Stack and Tooling**: package manager, Node version, framework + version, TS + strict mode, ORM, ESM/CJS.
- **Local Bootstrap**: install, env file, run, port, health-check.
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
