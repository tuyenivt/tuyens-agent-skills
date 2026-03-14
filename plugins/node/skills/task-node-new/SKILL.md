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

STEP 1 - DETECT FRAMEWORK + ORM

STEP 2 - GATHER: feature description, affected modules, external integrations

STEP 3 - DESIGN: propose module structure, interfaces, data flow. Present for approval.

STEP 4 - DATA MODEL: Prisma schema or TypeORM entity + migration (load node-migration-safety)

STEP 5 - SERVICE LAYER: business logic with proper typing (load node-typescript-patterns). If feature requires background jobs or async task processing: load node-bullmq-patterns. If feature emits domain events (e.g., order.created): load node-event-emitter-patterns or node-bullmq-patterns after transaction commit. For service-to-service calls: configure timeout, handle errors explicitly (timeout → 503, not-found → 404, validation → 400).

STEP 6 - API LAYER:

- NestJS: module + controller + guards + DTOs (load node-nestjs-patterns)
- Express: router + controller + middleware (load node-express-patterns)

STEP 7 - TESTS: load node-testing-patterns, comprehensive coverage

STEP 8 - VALIDATE: build + test + lint + typecheck (prefer `bun run build`, `bun test`, `bun run lint`)

OUTPUT: file list, endpoint summary, test count

## Self-Check

- [ ] Framework detected (NestJS or Express); requirements gathered and design approved before code generation
- [ ] All layers generated: data model/migration, service, controller/routes, DTOs, tests
- [ ] DTOs used for all responses - no ORM entities exposed; all async operations properly awaited
- [ ] TypeScript types explicit; guards/middleware chain explicit
- [ ] Build, test, lint, and typecheck all pass
- [ ] Migration includes indexes; list endpoints paginated; file list and test count presented

> Run `/task-skill-feedback` if output needed significant correction.
