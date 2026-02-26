# Tuyen's Agent Skills - Node.js / TypeScript

Claude Code plugin for Node.js/TypeScript development.

## Stack

- **TypeScript** - strict mode
- **NestJS** (primary) + **Express** (secondary)
- **Prisma** (NestJS) + **TypeORM** (Express)
- **Jest** + **Supertest**
- **PostgreSQL**

## Installation

Install the core plugin first, then the Node plugin:

```
/plugin install core@tuyens-agent-skills
/plugin install node@tuyens-agent-skills
```

## Optional: Share Skills Between Claude Code and Codex

Claude Code and Codex use the same `agentskills.io` format. You can create a symbolic link so Codex reuses the skills managed by Claude Code.

```bash
# Unix (Linux/macOS)
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/node/skills" "$HOME/.codex/skills/tuyens-agent-skills-node-skills"

# Windows
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-node-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/node/skills"
```

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

ORM selection can be overridden by declaring it in your project's `CLAUDE.md`.

## Workflow Skills

Workflow skills orchestrate multi-step tasks using the `node-architect` agent.

| Skill                         | Description                                                                                       |
| ----------------------------- | ------------------------------------------------------------------------------------------------- |
| `task-node-new`               | Create a new resource: module/router, controller, service, DTOs, data model, migration, and tests |
| `task-node-implement-feature` | End-to-end feature implementation across all layers with comprehensive tests                      |
| `task-node-debug`             | Debug errors from stack traces, test failures, build errors, and runtime issues                   |

### Usage Examples

**Create a new resource:**

```
Create an Orders resource with fields: customerId, items, total, status
```

→ Detects NestJS/Express, generates all layers, runs build + test + lint.

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

| Skill                      | Description                                                                                                |
| -------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `node-nestjs-patterns`     | NestJS patterns: modules, DI, controllers, guards, interceptors, pipes, exception filters, validation      |
| `node-express-patterns`    | Express patterns: router organization, middleware chain, error handling, async wrapper, request validation |
| `node-prisma-patterns`     | Prisma ORM for NestJS: schema design, migrations, N+1 prevention, transactions, connection pooling         |
| `node-typeorm-patterns`    | TypeORM for Express: entity definition, repository pattern, query builder, migrations, transactions        |
| `node-testing-patterns`    | Jest testing: NestJS TestingModule, Supertest e2e, Testcontainers, mocking, database testing               |
| `node-typescript-patterns` | TypeScript strict mode: generics, discriminated unions, type guards, utility types, no `any`               |
| `node-migration-safety`    | Safe migrations: Prisma migrate + TypeORM migrations, zero-downtime DDL, CI validation                     |

## Agents

| Agent                       | Model  | Description                                                                                                         |
| --------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------- |
| `node-architect`            | sonnet | Node.js/TypeScript architect for NestJS and Express. Designs APIs, module structure, DI, Prisma/TypeORM data access |
| `node-tech-lead`            | sonnet | Code review for TypeScript strictness, NestJS/Express patterns, query optimization, test coverage                   |
| `node-reliability-engineer` | sonnet | Incident analysis: event loop blocking, memory leaks, connection pools, graceful shutdown, monitoring               |
