---
name: task-node-new
description: "Create a new Node.js/TypeScript resource. Detects NestJS or Express. Generates module/router, controller, service, DTOs, Prisma schema or TypeORM entity, migration, and Jest tests."
agent: node-architect
---

STEP 1 — DETECT: NestJS (nest-cli.json) vs Express. ORM: Prisma (NestJS) vs TypeORM (Express)

STEP 2 — GATHER: resource name, fields, relations, operations

STEP 3 — DATA MODEL:

- NestJS: update schema.prisma, run prisma migrate dev (load node-prisma-patterns)
- Express: create TypeORM entity, generate migration (load node-typeorm-patterns)
- Load: node-migration-safety

STEP 4 — SERVICE: business logic with DI

- NestJS: @Injectable service (load node-nestjs-patterns)
- Express: class with constructor injection

STEP 5 — CONTROLLER/ROUTER:

- NestJS: @Controller with decorators, DTOs with class-validator
- Express: router + controller functions, zod validation (load node-express-patterns)

STEP 6 — DTOS: TypeScript classes/types for request/response (load node-typescript-patterns)

STEP 7 — TESTS: load node-testing-patterns

- NestJS: TestingModule + Supertest
- Express: Supertest + jest.mock

STEP 8 — VALIDATE: npm run build && npm test && npm run lint

OUTPUT: file checklist
