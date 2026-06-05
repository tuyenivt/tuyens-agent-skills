# Tuyen's Agent Skills - Node.js / TypeScript

Claude Code plugin for Node.js/TypeScript development.

## Stack

- **TypeScript** - strict mode
- **Bun** - preferred for install, build, test, and scripts (faster than npm/yarn); Node.js remains the production runtime
- **NestJS** (primary) + **Express** (secondary)
- **Prisma** (NestJS) + **TypeORM** (Express)
- **Jest** + **Supertest** (run via `bun test` or `bun run test`)
- **PostgreSQL**

## Framework Detection

Skills automatically detect which framework your project uses:

| Signal                                                    | Detected As |
| --------------------------------------------------------- | ----------- |
| `nest-cli.json` present                                   | NestJS      |
| `@nestjs/` in imports or dependencies                     | NestJS      |
| `express` in `package.json` dependencies (without NestJS) | Express     |

## ORM Mapping

| Framework | Default ORM |
| --------- | ----------- |
| NestJS    | Prisma      |
| Express   | TypeORM     |

ORM selection can be overridden by declaring it in your project's repo context file.

## Workflow Skills

| Skill                            | Agent                     | Description                                                                                                                         |
| -------------------------------- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `task-node-implement`            | node-architect            | End-to-end feature implementation across all layers with comprehensive tests                                                        |
| `task-node-debug`                | node-architect            | Debug errors from stack traces, test failures, build errors, and runtime issues                                                     |
| `task-node-review`               | node-tech-lead            | Node staff-level code review umbrella - Phases A-E with NestJS / Express idioms; spawns parallel scope subagents                    |
| `task-node-review-perf`          | node-performance-engineer | Prisma / TypeORM N+1, event-loop blocking, BullMQ throughput, NestJS request-scoped misuse, migration safety                        |
| `task-node-review-security`      | node-security-engineer    | NestJS Guards / JWT / Passport, Express middleware auth, ValidationPipe / Zod input, prototype pollution, OWASP Top 10              |
| `task-node-review-observability` | node-tech-lead            | pino / winston, OpenTelemetry Node SDK + auto-instrumentation, prom-client, BullMQ queue events (library-level focus)               |
| `task-node-test`                 | node-test-engineer        | Jest / Supertest strategy / scaffolding (NestJS TestingModule, Testcontainers, MSW, BullMQ in-memory + real-broker)                 |
| `task-node-refactor`             | node-tech-lead            | Refactor plan: fat controllers, anemic services, sync-in-async, listener abuse, BullMQ idempotency, prototype pollution, with gates |

### Usage Examples

**Implement a feature:**

```
Add payment processing with Stripe integration to the Orders module
```

→ Designs module structure, creates data model, service, API layer, and tests.

**Debug an error:**

```
PrismaClientKnownRequestError P2002: Unique constraint failed on "email"
```

→ Classifies error, locates root cause, applies fix, adds prevention test.

## Atomic Skills

Atomic skills are loaded by workflow skills and agents (not directly invocable).

| Skill                      | Description                                                                                                                   |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `node-nestjs-patterns`     | NestJS patterns: modules, DI, controllers, guards, interceptors, pipes, exception filters, validation, webhook handling       |
| `node-express-patterns`    | Express patterns: router organization, middleware chain, error handling, async wrapper, Zod validation, webhook handling      |
| `node-prisma-patterns`     | Prisma ORM: schema design with enums, N+1 prevention, transactions, cursor-based pagination, upsert for idempotency           |
| `node-typeorm-patterns`    | TypeORM: entity definition with enums, repository pattern, QueryBuilder, transactions, batch operations, pagination           |
| `node-testing-patterns`    | Jest testing: NestJS TestingModule, Supertest e2e, Testcontainers, state machine testing, webhook signature testing           |
| `node-typescript-patterns` | TypeScript strict mode: generics, discriminated unions, type guards, branded types, utility types, no `any`                   |
| `node-migration-safety`    | Safe migrations: Prisma migrate + TypeORM migrations, zero-downtime DDL, enum management, deploy ordering                     |
| `node-bullmq-patterns`     | BullMQ background jobs: job design, idempotency, retry strategy, queue routing, fan-out, worker lifecycle, testing strategies |
| `node-code-explain`        | Event loop and async semantics, NestJS DI/module graph, Express middleware, error propagation across async, TS-vs-runtime - injected into `task-code-explain` |
| `node-onboard-map`         | Package manager (npm/yarn/pnpm/bun), framework (NestJS/Express), TS config, build/run scripts, ORM, ESM/CJS - injected into `task-onboard` |
| `node-nestjs-overengineering-review` | Necessity review for NestJS: class-validator decorators duplicating Prisma/TypeORM / DB / TS strict-null, defensive guards on DI-injected providers / guards / `findUniqueOrThrow`, single-impl service interfaces / `BaseService<T>` / `Scope.REQUEST` on stateless providers / `Result<T,E>` wrappers / AutoMapper-style mappers / speculative `ConfigService` keys, broad `catch (e)` defeating the global exception filter. Composed into `task-node-review` Phase D when NestJS is detected. |
| `node-express-overengineering-review` | Necessity review for Express: Zod schemas duplicating TypeORM / DB / TS strict-null, defensive null after `findOneOrFail` or on typed values, middleware factories of one, Repository wrappers over TypeORM's `Repository<T>`, custom error hierarchies with no consumer branching, `Result<T,E>` wrappers, broad `catch (e)` defeating Express's error-handling middleware. Composed into `task-node-review` Phase D when Express is detected. |
| `node-security-patterns` | JWT signing/verify, mass-assignment DTOs, prototype pollution, SSRF allowlist, file upload, webhook signatures, secrets via typed `ConfigService`, `eval`/`vm` prohibitions, open redirect, `child_process.execFile`. Canonical patterns - `task-node-review-security` Step 8 delegates here |
| `node-exception-handling` | Application-wide rescue strategy: NestJS `@Catch` filter, Express terminal middleware, `AppError` hierarchy, `Result<T,E>` vs throw, BullMQ retry propagation, Prisma/TypeORM error translation at the boundary, Sentry capture-once |
| `node-http-client-patterns` | Outbound HTTP discipline: `AbortSignal.timeout`, `Retry-After`, retry idempotent verbs only, `Idempotency-Key` on POST, per-vendor client wrapper, in-process vs BullMQ retry budget, MSW for tests |
| `node-transaction-patterns` | Cross-ORM transaction contract: no I/O inside open transactions, post-commit dispatch, transactional outbox, lock-then-write, `lock_timeout` / `statement_timeout`, read-only queries outside transactions |
| `node-connection-pool-sizing` | Whole-deployment pool math: API replicas + worker replicas + rolling-deploy overlap vs Postgres `max_connections`, BullMQ worker concurrency vs pool, PgBouncer (transaction mode caveats), RDS Proxy, serverless via Prisma Accelerate |

## Agents

| Agent                       | Description                                                                                                         |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `node-architect`            | Node.js/TypeScript architect for NestJS and Express. Designs APIs, module structure, DI, Prisma/TypeORM data access |
| `node-tech-lead`            | Code review, refactoring guidance, doc standards for TypeScript strictness, NestJS/Express patterns, test coverage  |
| `node-security-engineer`    | OWASP Top 10 for Node.js, JWT/Guards audit, ValidationPipe review, dependency scanning with bun audit / npm audit   |
| `node-performance-engineer` | Event loop blocking detection, Prisma/TypeORM query tuning, memory leak profiling, connection pool sizing           |
| `node-test-engineer`        | Jest/Supertest strategies, NestJS TestingModule, Testcontainers, MSW, and test pyramid design                       |
