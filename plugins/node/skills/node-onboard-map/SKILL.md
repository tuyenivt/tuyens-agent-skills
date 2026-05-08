---
name: node-onboard-map
description: Node.js / NestJS / Express project onboarding signals - package manager (npm/yarn/pnpm), framework, TypeScript config, build/run scripts, ORM, and module system (CJS vs ESM). Used by task-onboard to map a Node codebase for a new engineer.
metadata:
  category: backend
  tags: [onboarding, codebase-map, node, nestjs, express, typescript]
user-invocable: false
---

# Node Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is Node.js / TypeScript.

## When to Use

- A workflow needs Node-specific orientation: package manager, framework, TS config, build pipeline, ORM, module system.
- Project has `package.json`.

## Rules

- Identify package manager first: `package-lock.json` (npm), `yarn.lock` (Yarn), `pnpm-lock.yaml` (pnpm), `bun.lockb` (Bun). Each has different command set.
- Identify framework: NestJS (`nest-cli.json`, `@nestjs/*` deps), Express (`express` dep, plain layout), Fastify, Koa, plain Node.
- Identify Node version (`.nvmrc`, `package.json` `engines.node`, `volta` config). Node 20 LTS or 22 LTS standard.
- Identify module system: `package.json` `"type": "module"` -> ESM, default -> CommonJS.
- Identify ORM: TypeORM (`ormconfig.json` or `data-source.ts`), Prisma (`prisma/schema.prisma`), Sequelize (`sequelize-cli`), Mongoose (Mongo), Drizzle.

## Patterns

### Package Manager Inventory

| File                | Manager | Lockfile             | Common commands                                |
| ------------------- | ------- | -------------------- | ---------------------------------------------- |
| `package-lock.json` | npm     | `package-lock.json`  | `npm install`, `npm run`, `npx`                |
| `yarn.lock`         | Yarn    | `yarn.lock`          | `yarn install`, `yarn run`, `yarn dlx`         |
| `pnpm-lock.yaml`    | pnpm    | `pnpm-lock.yaml`     | `pnpm install`, `pnpm run`, `pnpm dlx`         |
| `bun.lockb`         | Bun     | `bun.lockb`          | `bun install`, `bun run`                       |

### Bootstrap Path

1. Node toolchain: confirm version from `.nvmrc` or `engines.node`. Use `nvm`/`fnm`/`volta`.
2. Install: `<manager> install`.
3. Local services: `compose.yml` for DB/Redis; check `.env.example` for required env vars.
4. Migrations:
   - **Prisma:** `npx prisma migrate dev`.
   - **TypeORM:** `npm run typeorm:migration:run` (script-defined).
   - **Sequelize:** `npx sequelize-cli db:migrate`.
   - **Drizzle:** `npx drizzle-kit migrate`.
5. Run:
   - **NestJS:** `npm run start:dev` (Nest CLI).
   - **Express + ts-node-dev:** `npm run dev`.
   - **tsx-based:** `npm run dev` (often `tsx watch src/index.ts`).
   - **Bun:** `bun run dev`.
6. Verify: default port from `.env` / config; `/health` if implemented; `/api` swagger if NestJS Swagger.

### Key File Inventory

**NestJS:**

| Location                  | Purpose                                                                          |
| ------------------------- | -------------------------------------------------------------------------------- |
| `nest-cli.json`           | NestJS CLI config; source dir, plugins                                           |
| `src/main.ts`             | `bootstrap()` function; `NestFactory.create(AppModule)`                          |
| `src/app.module.ts`       | Root module; imports feature modules                                              |
| `src/<feature>/`          | Feature modules (controller, service, dto, entity)                                |
| `src/<feature>/*.controller.ts` | HTTP routes, decorators                                                     |
| `src/<feature>/*.service.ts`    | Business logic                                                              |
| `src/<feature>/dto/`      | Validation DTOs (class-validator decorators)                                      |
| `tsconfig.json` + `tsconfig.build.json` | TypeScript config                                                       |
| `test/`                   | E2E tests (Jest by default)                                                       |

**Express:**

| Location                  | Purpose                                                                |
| ------------------------- | ---------------------------------------------------------------------- |
| `src/index.ts` or `app.ts` | Express app setup                                                     |
| `src/routes/`             | Route handlers                                                         |
| `src/middleware/`         | Custom middleware                                                       |
| `src/services/` or `src/controllers/` | Business logic separation (varies by team)                  |

### Conventions

- **TypeScript first** in modern Node projects; check `tsconfig.json` for strict mode.
- **Linter:** ESLint (`.eslintrc.*`) - check rules; common configs: `@nestjs/eslint-config`, `airbnb`, `standard`.
- **Formatter:** Prettier (`.prettierrc`).
- **Logging:** `pino` (modern), `winston`, or NestJS Logger built-in.
- **Validation:** `class-validator` + `class-transformer` (NestJS), `zod`, `joi`.
- **Testing:** Jest (NestJS default), Vitest (faster, modern), Mocha (older).
- **Process manager (prod):** PM2, systemd, or container runtime; not the developer's concern at onboarding.

### Risk Hotspots Specific to Node

- **Sync I/O in handlers:** `readFileSync`, sync DB drivers - blocks event loop.
- **Unhandled rejections:** Node 15+ crashes the process. Check for `process.on('unhandledRejection')` for visibility, but root cause is missing `await`.
- **NestJS provider scope mismatches:** Singleton injecting Scoped (request-scoped) - same captive-dependency bug as in .NET.
- **Express middleware order**: undocumented order is the common bug source. Auth middleware after route handlers does nothing.
- **Default `http.Agent` keep-alive misconfiguration:** connection pool defaults can be too aggressive or too low for the workload.
- **TypeScript `any` escape hatches**: especially `as any` casts; type safety is illusory in those spots.
- **Prisma client instantiation per request**: should be a singleton; leaking new clients exhausts DB connections.
- **TypeORM circular module imports**: `forwardRef` patterns, often masking design issues.
- **Mixed ESM/CJS**: `__dirname` undefined in ESM; default-import shape mismatch.
- **`npm audit` vulnerabilities**: typical project has many transitive deps; check policy.

### First-PR Safe Zones

- New NestJS feature module (controller, service, DTO) following existing pattern.
- New Express route in an existing route file.
- New unit test next to an existing service.
- New env var in `.env.example` with safe default.

Riskier:

- `app.module.ts` / `main.ts` - boot flow; bug = won't start.
- Database migrations - irreversible without explicit rollback.
- Auth guard / passport strategy.
- Logging/interceptor configuration.

### Ecosystem Currency

- Node 20 LTS standard; 22 LTS rolling out.
- TypeScript 5.4+ standard; ESM increasingly common.
- NestJS 10+; Express 4 (5 in beta - many breaking changes).
- Prisma 5+ replacing TypeORM in many new projects.
- pnpm gaining ground over npm/yarn for monorepos.
- ts-node largely replaced by tsx (esbuild-based) for dev.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** package manager, Node version, framework + version, TypeScript version + strict mode, ORM, module system (CJS/ESM).

**Local Bootstrap:** install command, env file, run command, default port, health-check path.

**Architecture Map:** module/feature directory layout, main.ts/index.ts, ORM entity/schema location, middleware pipeline.

**Conventions:** TS strict mode, ESLint config, validation library, logging library, test framework.

**Risk Hotspots:** sync I/O in async, unhandled rejection, NestJS scope mismatch, ESM/CJS boundary, Prisma client lifetime, TypeORM forward refs.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Recommending npm commands when the project uses pnpm or Yarn
- Treating CommonJS and ESM as interchangeable
- Glossing over NestJS provider scopes - they matter
- Listing dependencies without the framework context (Express vs Nest = different mental model)
- Ignoring `engines.node` mismatches with installed Node
- Recommending TypeORM patterns on a Prisma project
