---
name: task-node-implement
description: End-to-end Node.js / TypeScript feature implementation for NestJS or Express: data model, services, controllers, DTOs, middleware, Jest tests.
agent: node-architect
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles` and `stack-detect`. Follow its contract; skip GATHER (and DESIGN when `plan.md` is present). Never edit spec artifacts; surface conflicts as proposed amendments.

# Implement Node.js Feature

## When to Use

End-to-end Node.js/TypeScript feature work: migration + model + service + controller + DTOs + tests in one pass for NestJS or Express.

Not for: single-file edits (edit directly), bugfixes (`task-node-debug`), frontend.

## Rules

- TypeScript strict; no `any`; explicit return types on public methods; all async operations awaited
- DTOs for every request/response; never expose Prisma models or TypeORM entities
- Constructor injection (NestJS `@Injectable()`; Express manual DI)
- Validation on all inputs: NestJS `class-validator` + `ValidationPipe({ whitelist: true, transform: true })`; Express Zod
- Multi-step writes use Prisma `$transaction` or TypeORM `DataSource.transaction`
- Background jobs / events dispatched **after** the transaction commits, never inside it
- Each step completes before the next; design approved before code

## Workflow

### STEP 1 - DETECT AND GATHER

Use skill: `stack-detect`. Confirm Node.js/TypeScript and identify NestJS vs Express, Prisma vs TypeORM, test runner, layout.

Ask the user before writing code:

1. Feature description and primary use case
2. Entities, fields, relationships, constraints
3. External integrations (third-party APIs, webhooks)
4. Background jobs or async events
5. Authentication / authorization
6. Status transitions
7. Idempotency requirements
8. Webhook endpoints (signature validation, raw body)

Ask targeted clarifying questions for any gap. Do not guess.

### STEP 2 - DESIGN (APPROVAL GATE)

Use skill: `node-nestjs-patterns` (NestJS) or `node-express-patterns` (Express) for API design. Use skill: `node-prisma-patterns` or `node-typeorm-patterns` for data layer. Use skill: `backend-api-guidelines` for REST conventions.

Present a file tree and these decisions:

- Endpoints (method, URI, status codes, DTOs)
- Schema (indexes on FK + filter columns, enums for status, unique index for idempotency)
- Service methods and transaction boundaries
- Error model (NestJS exceptions or custom AppError hierarchy)
- Idempotency strategy (if applicable)
- Webhook design (if applicable): raw body, signature validation, route outside global auth
- Background job dispatch points (which transaction commit triggers them)

Wait for approval before generating code.

### STEP 3 - DATA MODEL

Use skill: `node-migration-safety`. Prisma: models in `schema.prisma` with `@relation`, `@@index`, status enums; run `prisma migrate dev`. TypeORM: `@Entity` + `@Column` + `@Index` + relations; generate migration with `typeorm migration:generate`. For idempotency, add `@unique` on the key column.

### STEP 4 - SERVICE LAYER

Use skill: `node-typescript-patterns`. `@Injectable()` service (NestJS) or plain class (Express). Use `$transaction` / `DataSource.transaction` for multi-step writes. Map entities to response DTOs before returning.

- Status transitions: validate against a `VALID_TRANSITIONS` map before persisting; throw on invalid.
- Idempotency: look up by key first; return existing record if found; otherwise create.
- Background jobs / events: Use skill: `node-bullmq-patterns`. Enqueue after the transaction commits; pass IDs only.
- External API calls (Stripe, gateways): timeout-wrapped, errors classified, defined as an interface for testability.

### STEP 5 - API LAYER

NestJS: Use skill: `node-nestjs-patterns`. Module + controller + guards + DTOs with `class-validator`. `@HttpCode(201)` POST, `204` DELETE. Paginated list with query params.

Express: Use skill: `node-express-patterns`. Router + controller + Zod middleware. Async handler wrapper on every route.

Map domain errors to HTTP:

| Domain Error | HTTP |
|---|---|
| Validation | 400 |
| Unauthorized | 401 |
| Not found | 404 |
| Conflict | 409 |
| Invalid transition | 422 |
| External timeout | 503 |

For webhooks: raw body reading + signature validation in a route registered outside the global auth chain.

### STEP 6 - TESTS

Use skill: `node-testing-patterns`. Unit tests for services (mocked deps); E2E with Supertest. Cover happy path, validation, not-found, conflict, edge cases. For state machines, test every valid + invalid transition. For webhooks, test valid / invalid / missing signature. For idempotency, test that duplicates return the same result without creating duplicates.

### STEP 7 - VALIDATE

Run build + test + lint + typecheck (prefer `bun run build`, `bun test`, `bun run lint`). Fix failures before reporting done.

## Edge Cases

- **Vague input**: ask targeted questions in STEP 1; never guess fields or relationships
- **No persistence**: skip STEP 3; service + controller only
- **Existing entity**: read and extend rather than recreate; check existing DTOs / services
- **Referenced entity missing**: ask whether to create it or use an ID reference
- **Webhook-only**: skip CRUD; dedicated controller with raw body + signature validation
- **State transitions**: service-layer validation + enum constraint in schema
- **Idempotency**: unique-key column + find-or-create in service
- **Bulk operations**: `createMany` / chunked `save` + size-limit validation

## Output Format

```markdown
## Files Generated
[grouped by layer: schema/migration, DTOs, service, controller, module, tests]

## Endpoints
| Method | Path | Request | Response | Status |
| ... |

## Tests
- Unit: {count}
- E2E: {count}

## Migration
[file names + what they create: tables, indexes, enums, constraints]
```

## Self-Check

- [ ] Stack detected; requirements gathered; design approved before code
- [ ] All layers generated: schema/migration, DTOs, service, controller/routes, module, tests
- [ ] DTOs used everywhere; no ORM entities exposed; all async operations awaited
- [ ] TypeScript strict; validation on all inputs; guards/middleware explicit
- [ ] Background jobs dispatched after transaction commit
- [ ] Status transitions validated in service; enum constraint in schema (when applicable)
- [ ] Idempotency: unique constraint + find-or-create (when applicable)
- [ ] Webhook: raw body + signature validation, outside global auth (when applicable)
- [ ] External API calls: timeout-wrapped + interface for testability
- [ ] Build, test, lint, typecheck all pass; list endpoints paginated

## Avoid

- Generating code before design approval
- Exposing Prisma models or TypeORM entities in responses
- Background jobs inside a DB transaction
- `any` in DTOs or services
- Missing `await` on async operations
- Skipping pagination on list endpoints
- Skipping idempotency for payment / external-callback features
- Missing enum constraints on status fields
- Consuming the body before signature validation on webhook endpoints
