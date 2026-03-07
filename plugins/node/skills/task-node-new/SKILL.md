---
name: task-node-new
description: "End-to-end Node.js/TypeScript feature implementation. Detects NestJS or Express. Generates all layers: data model, services, controllers, DTOs, middleware, and comprehensive Jest tests."
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

STEP 5 - SERVICE LAYER: business logic with proper typing (load node-typescript-patterns). If feature requires background jobs or async task processing: load node-bullmq-patterns.

STEP 6 - API LAYER:

- NestJS: module + controller + guards + DTOs (load node-nestjs-patterns)
- Express: router + controller + middleware (load node-express-patterns)

STEP 7 - TESTS: load node-testing-patterns, comprehensive coverage

STEP 8 - VALIDATE: build + test + lint + typecheck

OUTPUT: file list, endpoint summary, test count

## Success Criteria

A well-executed feature implementation passes all of these. Use as a self-check before presenting to the user.

### Completeness

- [ ] Framework detected (NestJS or Express) before any code generated
- [ ] Requirements gathered and design approved before code generation
- [ ] All layers generated: data model/migration, service, controller/routes, DTOs, tests
- [ ] Validated with build, test, lint, and typecheck

### Node.js Correctness

- [ ] No ORM entities exposed in API responses - DTOs/serializers used for all responses
- [ ] All async operations are properly awaited - no unhandled promise rejections
- [ ] TypeScript types are explicit - no implicit `any`
- [ ] NestJS: `@UseGuards` / `@Roles` applied; Express: middleware chain is explicit
- [ ] Jest tests cover happy path, validation errors, and not-found scenarios

### Staff-Level Signal

- [ ] Migration includes indexes for foreign keys and filter columns
- [ ] List endpoints include pagination
- [ ] If BullMQ used, job idempotency and retry config are included
- [ ] File list, endpoint summary, and test count presented to user

## After This Skill

If the output needed significant adjustment - wrong framework detected, ORM entities exposed in responses, or unhandled promise rejections introduced - run `/task-skill-feedback` to log what changed and why.
