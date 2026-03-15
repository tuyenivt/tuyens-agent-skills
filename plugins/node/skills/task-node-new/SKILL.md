---
name: task-node-new
description: End-to-end Node.js/TypeScript feature implementation workflow. Detects NestJS or Express and generates all layers: data model, services, controllers, DTOs, middleware, and comprehensive Jest tests. Use for new features requiring multiple coordinated layers. Not for single-file fixes or isolated bug fixes (use task-node-debug for errors).
agent: node-architect
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

# Implement Feature

## When to Use

- Implementing a new Node.js/TypeScript feature end-to-end (data model → service → controller → tests)
- Scaffolding a complete CRUD or domain-specific resource with production-ready patterns
- Adding a new domain aggregate with REST API, persistence, and test coverage
- Any task requiring coordinated generation of multiple NestJS or Express layers

## Rules

- TypeScript strict mode - no `any`, explicit return types on public methods
- DTOs for all request/response shapes - never expose Prisma models or TypeORM entities directly
- Constructor injection for all dependencies (NestJS: `@Injectable()`; Express: manual DI or factory)
- Validation on all inputs: NestJS `class-validator` + `ValidationPipe({ whitelist: true, transform: true })`; Express: Zod schemas
- Transactions for multi-step mutations - Prisma `$transaction` or TypeORM `DataSource.transaction`
- Async/await everywhere - no unhandled promises; all async operations must be awaited
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code

## Implementation

STEP 1 - DETECT FRAMEWORK + ORM: Check package.json and project structure. Identify NestJS vs Express, Prisma vs TypeORM, and test runner (Jest/Vitest). This determines which atomic skills to load in later steps.

STEP 2 - GATHER: Feature name, affected modules, entity relationships, validation constraints, API operations (CRUD/custom), async processing needs (background jobs, events), external integrations.

STEP 3 - DESIGN: Propose endpoints (method + URI + request/response DTOs + status codes), entity fields with types, service methods, transaction boundaries. Present for user approval before generating code.

STEP 4 - DATA MODEL: Use skill: `node-migration-safety`. Prisma: add models to schema.prisma with `@relation`, `@@index` for FK and filter columns, enums for status fields; run `prisma migrate dev`. TypeORM: entity with `@Entity`, `@Column`, `@Index`, relations; generate migration with `typeorm migration:generate`.

STEP 5 - SERVICE LAYER: Use skill: `node-typescript-patterns`. `@Injectable()` service (NestJS) or plain class (Express). Use Prisma `$transaction` or TypeORM `DataSource.transaction` for multi-step mutations. Map entities to response DTOs before returning.

- If feature requires background jobs: Use skill: `node-bullmq-patterns`. Enqueue after transaction commits, pass only IDs as job data.
- For service-to-service calls: configure timeout, handle errors explicitly (timeout → 503, not-found → 404, validation → 400).

STEP 6 - API LAYER:

- NestJS: Use skill: `node-nestjs-patterns`. Module + controller + guards + request/response DTO classes with `class-validator` decorators. `@HttpCode(201)` for POST, `204` for DELETE. Paginated list with query params.
- Express: Use skill: `node-express-patterns`. Router + controller functions + Zod validation middleware. Async handler wrapper on all routes.

STEP 7 - TESTS: Use skill: `node-testing-patterns`. Unit tests for service logic (mock repository/dependencies). E2E tests with Supertest against running app. Cover happy path, not-found, validation errors, and edge cases.

STEP 8 - VALIDATE: Run build + test + lint + typecheck (prefer `bun run build`, `bun test`, `bun run lint`). Fix any failures before presenting results.

## Self-Check

- [ ] Framework and ORM detected; requirements gathered and design approved before code generation
- [ ] All layers generated: data model/migration, service, controller/routes, DTOs, tests
- [ ] DTOs used for all responses - no ORM entities exposed; all async operations properly awaited
- [ ] TypeScript strict types throughout; validation on all inputs; guards/middleware chain explicit
- [ ] Build, test, lint, and typecheck all pass
- [ ] Migration includes indexes for FK and filter columns; list endpoints paginated
- [ ] File list, endpoint table, and test count presented to user

## Output

Present a summary of generated files:

```markdown
## Generated Files

- [ ] Model: `src/{module}/entities/{name}.entity.ts` or `prisma/schema.prisma`
- [ ] Migration: `prisma/migrations/...` or `src/migrations/...`
- [ ] DTO: `src/{module}/dto/create-{name}.dto.ts`
- [ ] DTO: `src/{module}/dto/update-{name}.dto.ts`
- [ ] DTO: `src/{module}/dto/{name}-response.dto.ts`
- [ ] Service: `src/{module}/{name}.service.ts`
- [ ] Controller: `src/{module}/{name}.controller.ts`
- [ ] Module: `src/{module}/{name}.module.ts` (NestJS only)
- [ ] Unit test: `src/{module}/{name}.service.spec.ts`
- [ ] E2E test: `test/{name}.e2e-spec.ts`

## Endpoints

| Method | URI                        | Status | Description      |
| ------ | -------------------------- | ------ | ---------------- |
| GET    | /api/v1/{resources}        | 200    | List (paginated) |
| GET    | /api/v1/{resources}/:id    | 200    | Get by ID        |
| POST   | /api/v1/{resources}        | 201    | Create           |
| PATCH  | /api/v1/{resources}/:id    | 200    | Update           |
| DELETE | /api/v1/{resources}/:id    | 204    | Delete           |

## Tests

- Unit tests: {count} (service layer)
- E2E tests: {count} (API layer)
```
