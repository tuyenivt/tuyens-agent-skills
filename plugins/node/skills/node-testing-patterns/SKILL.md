---
name: node-testing-patterns
description: Jest testing patterns for NestJS / Express: unit mocks, Supertest e2e, TestingModule, Testcontainers PostgreSQL, transaction rollback.
metadata:
  category: backend
  tags: [node, typescript, jest, testing, supertest, testcontainers]
user-invocable: false
---

# Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing unit tests for services, repositories, utilities
- Writing e2e tests for NestJS or Express endpoints
- Setting up test infrastructure (DB, mocks, test module)
- Reviewing test code for coverage gaps or anti-patterns

## Rules

- TypeScript in tests: no `any`, typed mocks, typed assertions
- Each test independent: no shared mutable state
- Real PostgreSQL via Testcontainers for integration; never SQLite
- Prefer DI overrides for mocking over `jest.mock()`
- Test names state behavior: "should return 201 when order is created"

## Patterns

### NestJS Unit Testing

```typescript
describe("OrderService", () => {
  let service: OrderService;
  let prisma: DeepMockProxy<PrismaService>;
  let queue: { add: jest.Mock };

  beforeEach(async () => {
    queue = { add: jest.fn() };
    const module = await Test.createTestingModule({
      providers: [
        OrderService,
        { provide: PrismaService, useValue: mockDeep<PrismaService>() },
        { provide: ORDER_QUEUE, useValue: queue },
      ],
    }).compile();
    service = module.get(OrderService);
    prisma = module.get(PrismaService);
  });

  it("creates order in transaction and enqueues job", async () => {
    prisma.$transaction.mockImplementation(async (fn) => fn(prisma));
    prisma.order.create.mockResolvedValue(mockOrder);

    const result = await service.create(dto);

    expect(prisma.$transaction).toHaveBeenCalled();
    expect(queue.add).toHaveBeenCalledWith("process-order", { id: mockOrder.id });
    expect(result.id).toBe(mockOrder.id);
  });
});
```

- `Test.createTestingModule()` for isolated module testing; override providers via `.overrideProvider(X).useValue(...)`
- `jest-mock-extended` (`mockDeep`) for typed Prisma mocks
- Assert on outward effects (queue calls, return value), not mock internals

### NestJS E2E Testing

```typescript
describe("Orders API (e2e)", () => {
  let app: INestApplication;

  beforeAll(async () => {
    const module = await Test.createTestingModule({ imports: [AppModule] }).compile();
    app = module.createNestApplication();
    app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
    await app.init();
  });

  afterAll(() => app.close());

  it("returns 201 when creating an order", async () => {
    const res = await request(app.getHttpServer())
      .post("/api/v1/orders")
      .send({ customerId: "cust-1", items: [{ productId: "prod-1", quantity: 1 }] })
      .expect(201);
    expect(res.body.status).toBe("PENDING");
  });
});
```

### Express Testing

```typescript
import request from "supertest";
import { app } from "../src/app";

it("idempotent payment returns 200 on replay", async () => {
  const payload = { idempotencyKey: "key-1", amount: 100 };
  await request(app).post("/api/v1/payments").send(payload).expect(201);
  await request(app).post("/api/v1/payments").send(payload).expect(200);
});
```

### Database Testing with Testcontainers

```typescript
let container: StartedPostgreSqlContainer;

beforeAll(async () => {
  container = await new PostgreSqlContainer().start();
  process.env.DATABASE_URL = container.getConnectionUri();
  execSync("npx prisma migrate deploy", { env: process.env });
}, 60_000);

afterAll(() => container.stop());

// Per-test isolation via transaction rollback
beforeEach(() => prisma.$executeRaw`BEGIN`);
afterEach(() => prisma.$executeRaw`ROLLBACK`);
```

- Prisma: `prisma migrate deploy` on the container
- TypeORM: `synchronize: true` only in test config

### State Machine Transitions

Use `it.each` for valid/invalid transition tables:

```typescript
it.each([
  ["PENDING", "CONFIRMED", true],
  ["PENDING", "DELIVERED", false],
  ["SHIPPED", "DELIVERED", true],
])("transition %s -> %s allowed=%s", async (from, to, ok) => {
  // setup order with status `from`
  const promise = service.transition(orderId, to);
  await (ok ? expect(promise).resolves.toBeDefined() : expect(promise).rejects.toThrow());
});
```

### Webhook Signature Validation

Use the provider's test helper (e.g. `stripe.webhooks.generateTestHeaderString`) to sign payloads; cover valid + invalid in one pair:

```typescript
const sig = stripe.webhooks.generateTestHeaderString({ payload, secret });
await request(app).post("/webhooks/stripe").set("stripe-signature", sig).send(payload).expect(200);
await request(app).post("/webhooks/stripe").set("stripe-signature", "x").send(payload).expect(401);
```

### Test Structure

- `describe`/`it` with behavior names
- `beforeAll` for DB/app setup, `afterAll` teardown, `beforeEach` for data reset
- `expect().resolves` / `expect().rejects` for async
- `it.each` for table-driven cases
- Snapshots only for serializer/response shapes, never business logic
- Runner: prefer `bun test`, fall back to `npx jest`

## Edge Cases

- **Testcontainers on CI**: startup 10-30s; set `beforeAll` timeout >=60s. No Docker on CI -> shared DB with per-test transaction rollback.
- **Port conflicts**: pass the app instance to Supertest, or `app.listen(0)` for an OS-assigned port.
- **Flaky tests**: usually shared rows or in-memory singletons; reset in `beforeEach`, not `beforeAll`.
- **BullMQ**: mock the queue, assert on `queue.add()`; do not run real workers.

## Output Format

```
## Test Plan

### Unit Tests
| Test | Service Method | Mocks | Assertions |
|------|---------------|-------|------------|

### E2E Tests
| Test | Endpoint | Method | Status | Assertions |
|------|----------|--------|--------|------------|

### Integration Tests
| Test | Database | Setup | Assertions |
|------|----------|-------|------------|

### Coverage Targets
- Service layer: {count} unit tests
- API layer: {count} e2e tests
- Repository layer: {count} integration tests
```

## Avoid

- Testing implementation details (asserting on mock internals vs outputs)
- Shared mutable state between tests (ordering-dependent failures)
- Snapshots for business logic
- Hardcoded ports in e2e tests
- Untyped test helpers
