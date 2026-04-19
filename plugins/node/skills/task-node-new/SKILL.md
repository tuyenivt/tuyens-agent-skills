---
name: task-node-new
description: End-to-end Node.js/TypeScript feature implementation workflow. Detects NestJS or Express and generates all layers - data model, services, controllers, DTOs, middleware, and comprehensive Jest tests.
agent: node-architect
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Implement Feature

## When to Use

- Implementing a new Node.js/TypeScript feature end-to-end (data model, service, controller, tests)
- Scaffolding a complete CRUD or domain-specific resource with production-ready patterns
- Adding a new domain aggregate with REST API, persistence, background jobs, and test coverage
- Any daily coding task that requires coordinated generation of multiple NestJS or Express layers

Not for single-file changes (edit directly), isolated bug fixes (use `task-node-debug`), or frontend work.

## Edge Cases

- **Partial input**: User gives a vague feature name without details. Ask targeted questions in STEP 1 - never guess field names, types, or relationships
- **No database**: Feature has no persistence (e.g., external API aggregation). Skip STEP 4 (data model) and migration. Generate service and controller only
- **Existing entity**: User says "add endpoints for Order" and the model already exists. Read the existing model/schema and extend rather than creating a new one. Check for existing DTOs and services too
- **Referenced entity doesn't exist**: Design references another entity (e.g., `Customer`) that isn't in the codebase yet. Ask the user whether to create it or use a plain ID reference
- **Webhook-only feature**: No CRUD endpoints needed, only a webhook receiver (e.g., Stripe, GitHub). Skip standard CRUD generation; generate a dedicated webhook controller with raw body reading and signature validation
- **State machine transitions**: Feature has explicit status transitions (e.g., pending -> confirmed -> shipped). Generate transition validation in the service layer and an enum constraint in the schema
- **Idempotency requirements**: Feature needs deduplication (e.g., payment processing). Add a unique idempotency key field, implement find-or-create in the service layer, and validate in tests
- **Bulk operations**: User needs batch create/update/delete. Use Prisma `createMany`/`updateMany` or TypeORM `save` with chunks, add a dedicated bulk endpoint, and validate collection size limits

## Rules

- TypeScript strict mode - no `any`, explicit return types on public methods
- DTOs for all request/response shapes - never expose Prisma models or TypeORM entities directly
- Constructor injection for all dependencies (NestJS: `@Injectable()`; Express: manual DI or factory)
- Validation on all inputs: NestJS `class-validator` + `ValidationPipe({ whitelist: true, transform: true })`; Express: Zod schemas
- Transactions for multi-step mutations - Prisma `$transaction` or TypeORM `DataSource.transaction`
- Event/job dispatch timing: enqueue background jobs AFTER the transaction commits, never inside it - if the job fires before commit, the worker may read stale data or a missing row
- Async/await everywhere - no unhandled promises; all async operations must be awaited
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code

## Workflow

### STEP 1 - DETECT STACK AND GATHER REQUIREMENTS (MANDATORY)

Use skill: `stack-detect` to confirm the project is Node.js/TypeScript and identify NestJS vs Express, Prisma vs TypeORM, test runner, and project layout conventions.

Ask the user these questions before writing any code:

1. What is the feature? (brief description, primary use case)
2. What are the main entities? (fields, relationships, constraints)
3. Are there external integrations? (third-party APIs, webhooks, callbacks)
4. Are background jobs or async events needed? (email, notifications, file processing)
5. Does the feature need authentication/authorization?
6. Are there status transitions? (e.g., order: pending -> confirmed -> shipped)
7. What validation constraints apply? (uniqueness, format, business rules)
8. Idempotency requirements? (deduplication keys, exactly-once processing)
9. Are there webhook or callback endpoints from external services? (signature validation, raw body parsing)

Do not continue until requirements are complete. If the user provides incomplete input, ask targeted clarifying questions.

### STEP 2 - DESIGN (MANDATORY APPROVAL GATE)

Use skill: `node-nestjs-patterns` (NestJS) or `node-express-patterns` (Express) for API layer design. Use skill: `node-prisma-patterns` or `node-typeorm-patterns` for data layer design. Use skill: `backend-api-guidelines` for REST conventions. Propose the implementation layers and present for user approval before generating code.

Present a file tree showing what will be generated:

```
src/
  {module}/
    entities/{name}.entity.ts        # TypeORM entity (or prisma/schema.prisma)
    dto/create-{name}.dto.ts         # Request DTO
    dto/update-{name}.dto.ts         # Request DTO
    dto/{name}-response.dto.ts       # Response DTO
    {name}.service.ts                # Business logic
    {name}.controller.ts             # NestJS controller (or routes/{name}.router.ts)
    {name}.module.ts                 # NestJS module (NestJS only)
    {name}.service.spec.ts           # Unit tests
prisma/migrations/                   # Prisma migration (or src/migrations/)
test/
  {name}.e2e-spec.ts                 # E2E tests
```

Design decisions to present:

- Endpoints (method, URI, status codes, request/response DTOs)
- Entity model + DB schema changes (indexes, constraints, enums for status fields)
- Service methods and transaction boundaries
- Error model (NestJS exceptions or custom AppError hierarchy)
- Idempotency strategy (if applicable)
- Webhook handler design (if applicable): raw body reading, signature validation, event type routing
- Background job dispatch points (after which transaction commits)

Only generate code after user approves design.

### STEP 3 - DATA MODEL

Use skill: `node-migration-safety`. Prisma: add models to schema.prisma with `@relation`, `@@index` for FK and filter columns, enums for status fields; run `prisma migrate dev`. TypeORM: entity with `@Entity`, `@Column`, `@Index`, relations; generate migration with `typeorm migration:generate`.

For status fields with known transitions, use a Prisma enum or TypeORM enum column:

```prisma
enum OrderStatus {
  PENDING
  CONFIRMED
  SHIPPED
  DELIVERED
  CANCELLED
}

model Order {
  id        String      @id @default(uuid())
  status    OrderStatus @default(PENDING)
  // ...
  @@index([customerId])
  @@index([status])
}
```

For idempotency keys, add a unique constraint:

```prisma
model Payment {
  idempotencyKey String @unique
  // ...
}
```

### STEP 4 - SERVICE LAYER

Use skill: `node-typescript-patterns`. `@Injectable()` service (NestJS) or plain class (Express). Use Prisma `$transaction` or TypeORM `DataSource.transaction` for multi-step mutations. Map entities to response DTOs before returning.

For status transitions, validate transitions in the service layer before persisting:

```typescript
const VALID_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  PENDING: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
  CONFIRMED: [OrderStatus.SHIPPED, OrderStatus.CANCELLED],
  SHIPPED: [OrderStatus.DELIVERED],
  DELIVERED: [],
  CANCELLED: [],
};

async transition(id: string, newStatus: OrderStatus): Promise<OrderResponseDto> {
  const order = await this.prisma.order.findUniqueOrThrow({ where: { id } });
  const allowed = VALID_TRANSITIONS[order.status];
  if (!allowed.includes(newStatus)) {
    throw new BadRequestException(`Invalid transition ${order.status} -> ${newStatus}`);
  }
  const updated = await this.prisma.order.update({
    where: { id },
    data: { status: newStatus },
  });
  return OrderResponseDto.from(updated);
}
```

For idempotent operations (e.g., payment processing), check by idempotency key first:

```typescript
async processPayment(dto: ProcessPaymentDto): Promise<PaymentResponseDto> {
  const existing = await this.prisma.payment.findUnique({
    where: { idempotencyKey: dto.idempotencyKey },
  });
  if (existing) return PaymentResponseDto.from(existing);

  const payment = await this.prisma.$transaction(async (tx) => {
    return tx.payment.create({ data: { ...dto, status: 'PENDING' } });
  });
  // Enqueue charge job AFTER transaction commits
  await this.paymentQueue.add('charge', { paymentId: payment.id });
  return PaymentResponseDto.from(payment);
}
```

- If feature requires background jobs: Use skill: `node-bullmq-patterns`. Enqueue after transaction commits, pass only IDs as job data.
- For external API calls (e.g., Stripe, payment gateways): wrap with timeout, classify errors, and use an interface for testability:

```typescript
interface PaymentGateway {
  charge(req: ChargeRequest): Promise<ChargeResult>;
}

async chargePayment(paymentId: string): Promise<void> {
  const payment = await this.prisma.payment.findUniqueOrThrow({ where: { id: paymentId } });
  try {
    const result = await this.gateway.charge({
      amount: payment.amount,
      currency: payment.currency,
    });
    await this.prisma.payment.update({
      where: { id: paymentId },
      data: { status: 'COMPLETED', externalId: result.id },
    });
  } catch (err) {
    await this.prisma.payment.update({
      where: { id: paymentId },
      data: { status: 'FAILED', failureReason: err.message },
    });
    throw err;
  }
}
```

### STEP 5 - API LAYER

- NestJS: Use skill: `node-nestjs-patterns`. Module + controller + guards + request/response DTO classes with `class-validator` decorators. `@HttpCode(201)` for POST, `204` for DELETE. Paginated list with query params.
- Express: Use skill: `node-express-patterns`. Router + controller functions + Zod validation middleware. Async handler wrapper on all routes.

Map domain errors to HTTP status codes:

| Domain Error         | HTTP Status |
| -------------------- | ----------- |
| Validation failure   | 400         |
| Not found            | 404         |
| Conflict (duplicate) | 409         |
| Unauthorized         | 401         |
| Invalid transition   | 422         |
| External timeout     | 503         |

For webhook endpoints (Stripe, GitHub, etc.), use raw body reading with signature validation:

```typescript
// NestJS webhook controller
@Post('webhooks/stripe')
async handleStripeWebhook(
  @Req() req: RawBodyRequest<Request>,
  @Headers('stripe-signature') signature: string,
): Promise<{ received: boolean }> {
  const event = this.stripe.webhooks.constructEvent(
    req.rawBody!,
    signature,
    this.configService.get('STRIPE_WEBHOOK_SECRET'),
  );
  await this.paymentService.handleWebhookEvent(event);
  return { received: true };
}
```

### STEP 6 - TESTS

Use skill: `node-testing-patterns`. Unit tests for service logic (mock repository/dependencies). E2E tests with Supertest against running app. Cover happy path, not-found, validation errors, conflict, and edge cases.

For features with state machines, test all valid and invalid transitions:

```typescript
it('should transition from PENDING to CONFIRMED', async () => { ... });
it('should reject transition from PENDING to DELIVERED', async () => { ... });
```

For webhook handlers, test signature validation (valid sig, invalid sig, missing sig).

For idempotency, test that duplicate requests return the same result without creating duplicate records.

### STEP 7 - VALIDATE

Run build + test + lint + typecheck (prefer `bun run build`, `bun test`, `bun run lint`). Fix any failures before presenting results.

## Output Format

```markdown
## Files Generated

[grouped file list by layer: model/schema, migration, DTOs, service, controller, module, tests]

## Endpoints

| Method | URI                     | Request           | Response                                   | Status |
| ------ | ----------------------- | ----------------- | ------------------------------------------ | ------ |
| GET    | /api/v1/{resources}     | query params      | { data: Resource[], meta: PaginationMeta } | 200    |
| GET    | /api/v1/{resources}/:id | -                 | Resource                                   | 200    |
| POST   | /api/v1/{resources}     | CreateResourceDto | Resource                                   | 201    |
| PATCH  | /api/v1/{resources}/:id | UpdateResourceDto | Resource                                   | 200    |
| DELETE | /api/v1/{resources}/:id | -                 | -                                          | 204    |
| POST   | /api/v1/webhooks/stripe | raw body          | { received: true }                         | 200    |

## Tests

- Unit tests: {count} (service layer)
- E2E tests: {count} (API layer)

## Migration

[migration file names and what they create: tables, indexes, enums, constraints]
```

## Self-Check

- [ ] Stack detected and requirements gathered; design approved before any code generated
- [ ] All layers generated: data model/migration, service, controller/routes, DTOs, module, tests
- [ ] DTOs used for all responses - no ORM entities/models exposed; all async operations properly awaited
- [ ] TypeScript strict types throughout; validation on all inputs; guards/middleware chain explicit
- [ ] Background jobs dispatched after transaction commit, not inside it
- [ ] Status transitions validated in service layer; enum constraint in schema (if applicable)
- [ ] Idempotency key with unique constraint and find-or-create logic (if applicable)
- [ ] Webhook signature validation with raw body reading (if applicable)
- [ ] External API calls wrapped with timeout and behind an interface
- [ ] Build, test, lint, and typecheck all pass
- [ ] Migration includes indexes for FK and filter columns; list endpoints paginated; output template filled

## Avoid

- Generating code before requirements are gathered and design is approved
- Exposing Prisma models or TypeORM entities directly in API responses (always map to DTOs)
- Dispatching background jobs inside a DB transaction (worker races the commit)
- `any` in DTOs or service code (defeats TypeScript strict mode)
- Skipping pagination on list endpoints
- Missing `await` on async operations (causes unhandled rejections)
- Skipping idempotency handling when the feature involves payment or external service callbacks
- Missing enum constraints for status fields with known transitions
- Using `ShouldBindJSON`-style patterns on webhook endpoints (consumes body, breaks signature validation)
