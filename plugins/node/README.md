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

Workflow skills orchestrate multi-step tasks using the `node-architect` agent.

| Skill             | Description                                                                     |
| ----------------- | ------------------------------------------------------------------------------- |
| `task-node-new`   | End-to-end feature implementation across all layers with comprehensive tests    |
| `task-node-debug` | Debug errors from stack traces, test failures, build errors, and runtime issues |

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

## Agents

| Agent                       | Model  | Description                                                                                                         |
| --------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------- |
| `node-architect`            | sonnet | Node.js/TypeScript architect for NestJS and Express. Designs APIs, module structure, DI, Prisma/TypeORM data access |
| `node-tech-lead`            | sonnet | Code review, refactoring guidance, doc standards for TypeScript strictness, NestJS/Express patterns, test coverage  |
| `node-security-engineer`    | sonnet | OWASP Top 10 for Node.js, JWT/Guards audit, ValidationPipe review, dependency scanning with bun audit / npm audit   |
| `node-performance-engineer` | sonnet | Event loop blocking detection, Prisma/TypeORM query tuning, memory leak profiling, connection pool sizing           |
| `node-test-engineer`        | sonnet | Jest/Supertest strategies, NestJS TestingModule, Testcontainers, MSW, and test pyramid design                       |
