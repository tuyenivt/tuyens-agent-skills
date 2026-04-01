---
name: node-testing-patterns
description: Jest testing patterns for NestJS and Express - unit tests with mocking, e2e tests with Supertest, NestJS TestingModule, Testcontainers for real PostgreSQL, database testing with transaction rollback, and TypeScript-first test conventions.
metadata:
  category: backend
  tags: [node, typescript, jest, testing, supertest, testcontainers]
user-invocable: false
---

# Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing unit tests for services, repositories, or utility functions
- Writing e2e tests for NestJS or Express API endpoints
- Setting up test infrastructure (database, mocking, test module)
- Reviewing test code for coverage gaps or anti-patterns

## Rules

- TypeScript in tests - no `any`, typed mocks, typed assertions
- Each test must be independent - no shared mutable state between tests
- Use real PostgreSQL via Testcontainers for integration tests - never SQLite
- Prefer dependency injection for mocking over `jest.mock()` when possible
- Test names describe expected behavior: "should return 201 when order is created"

## Patterns

### NestJS Unit Testing

```typescript
describe("OrderService", () => {
  let service: OrderService;
  let prisma: DeepMockProxy<PrismaService>;

  beforeEach(async () => {
    const module = await Test.createTestingModule({
      providers: [
        OrderService,
        { provide: PrismaService, useValue: mockDeep<PrismaService>() },
        { provide: ORDER_QUEUE, useValue: { add: jest.fn() } },
      ],
    }).compile();

    service = module.get<OrderService>(OrderService);
    prisma = module.get(PrismaService);
  });

  it("should create order with items", async () => {
    const dto: CreateOrderDto = {
      customerId: "cust-1",
      items: [{ productId: "prod-1", quantity: 2, price: 29.99 }],
    };
    prisma.$transaction.mockImplementation(async (fn) => fn(prisma));
    prisma.order.create.mockResolvedValue(mockOrder);
    prisma.orderItem.createMany.mockResolvedValue({ count: 1 });

    const result = await service.create(dto);
    expect(result.id).toBe(mockOrder.id);
    expect(prisma.$transaction).toHaveBeenCalled();
  });

  it("should reject invalid status transition", async () => {
    prisma.order.findUniqueOrThrow.mockResolvedValue({
      ...mockOrder,
      status: OrderStatus.PENDING,
    });

    await expect(
      service.transition(mockOrder.id, OrderStatus.DELIVERED),
    ).rejects.toThrow(BadRequestException);
  });
});
```

- `Test.createTestingModule()` for isolated module testing
- Override providers for mocking: `.overrideProvider(PrismaService).useValue(mockPrisma)`
- Use `jest-mock-extended` (`mockDeep`) for strongly-typed Prisma mocks

### NestJS E2E Testing

```typescript
describe("Orders API (e2e)", () => {
  let app: INestApplication;

  beforeAll(async () => {
    const module = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = module.createNestApplication();
    app.useGlobalPipes(
      new ValidationPipe({ whitelist: true, transform: true }),
    );
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  it("should return 201 when creating an order", async () => {
    const res = await request(app.getHttpServer())
      .post("/api/v1/orders")
      .send({
        customerId: "cust-1",
        items: [{ productId: "prod-1", quantity: 1 }],
      })
      .expect(201);

    expect(res.body).toHaveProperty("id");
    expect(res.body.status).toBe("PENDING");
  });

  it("should return 400 for invalid input", async () => {
    await request(app.getHttpServer())
      .post("/api/v1/orders")
      .send({ customerId: "" }) // missing items
      .expect(400);
  });

  it("should paginate order list", async () => {
    const res = await request(app.getHttpServer())
      .get("/api/v1/orders?page=1&pageSize=10")
      .expect(200);

    expect(res.body).toHaveProperty("data");
    expect(res.body).toHaveProperty("meta");
    expect(res.body.meta).toHaveProperty("totalItems");
  });
});
```

### Express Testing

```typescript
import request from "supertest";
import { app } from "../src/app";

describe("Orders API", () => {
  it("should return 200 with paginated order list", async () => {
    const res = await request(app).get("/api/v1/orders").expect(200);
    expect(res.body).toHaveProperty("data");
    expect(res.body).toHaveProperty("meta");
  });

  it("should return 409 for duplicate idempotency key", async () => {
    const payload = { idempotencyKey: "key-1", amount: 100 };
    await request(app).post("/api/v1/payments").send(payload).expect(201);
    await request(app).post("/api/v1/payments").send(payload).expect(200); // idempotent
  });
});
```

### Running Tests

- Prefer `bun test` or `bun run test` (faster install and execution)
- Falls back to `npx jest` if bun is not available

### Database Testing with Testcontainers

```typescript
import {
  PostgreSqlContainer,
  StartedPostgreSqlContainer,
} from "@testcontainers/postgresql";

let container: StartedPostgreSqlContainer;

beforeAll(async () => {
  container = await new PostgreSqlContainer().start();
  // Use container.getConnectionUri() for Prisma or TypeORM
  process.env.DATABASE_URL = container.getConnectionUri();
  // Prisma: run migrations
  execSync("npx prisma migrate deploy", { env: process.env });
}, 60_000); // containers need longer timeout

afterAll(async () => {
  await container.stop();
});
```

- Prisma: use `prisma migrate deploy` on test container
- TypeORM: `synchronize: true` ONLY in test config
- Transaction rollback per test for isolation:

```typescript
beforeEach(async () => {
  await prisma.$executeRaw`BEGIN`;
});

afterEach(async () => {
  await prisma.$executeRaw`ROLLBACK`;
});
```

### Testing State Machine Transitions

For features with status transitions, test all valid and invalid paths:

```typescript
describe("Order status transitions", () => {
  it.each([
    ["PENDING", "CONFIRMED", true],
    ["PENDING", "CANCELLED", true],
    ["PENDING", "DELIVERED", false],
    ["CONFIRMED", "SHIPPED", true],
    ["SHIPPED", "DELIVERED", true],
    ["DELIVERED", "PENDING", false],
  ])("transition %s -> %s should be %s", async (from, to, allowed) => {
    // setup order with status `from`
    if (allowed) {
      await expect(service.transition(orderId, to)).resolves.toBeDefined();
    } else {
      await expect(service.transition(orderId, to)).rejects.toThrow();
    }
  });
});
```

### Testing Webhook Signature Validation

```typescript
describe("Stripe webhook", () => {
  it("should accept valid signature", async () => {
    const payload = JSON.stringify({
      type: "payment_intent.succeeded",
      data: {},
    });
    const sig = stripe.webhooks.generateTestHeaderString({ payload, secret });
    await request(app.getHttpServer())
      .post("/api/v1/webhooks/stripe")
      .set("stripe-signature", sig)
      .send(payload)
      .expect(200);
  });

  it("should reject invalid signature", async () => {
    await request(app.getHttpServer())
      .post("/api/v1/webhooks/stripe")
      .set("stripe-signature", "invalid")
      .send("{}")
      .expect(401);
  });
});
```

### Mocking

- `jest.mock()` for module-level mocking
- `jest.spyOn()` for partial mocking
- `jest-mock-extended` (`mockDeep`) for typed Prisma/TypeORM mocks
- Prefer dependency injection over `jest.mock` when possible

### Test Structure

- `describe`/`it` blocks with clear naming: "should return 201 when order is created"
- `beforeAll` for DB setup, `afterAll` for teardown, `beforeEach` for data reset
- Use `expect().resolves` / `expect().rejects` for async assertions
- Use `it.each()` for table-driven tests (state transitions, validation rules)
- Snapshot testing ONLY for serializers/response shapes, not business logic

## Edge Cases

- **Testcontainers timeout on CI**: Container startup can take 10-30 seconds. Set `beforeAll` timeout to at least 60 seconds. If CI has no Docker, fall back to a shared test database with per-test transaction rollback.
- **Port conflicts in e2e tests**: Use `app.listen(0)` to let the OS assign a random port. Supertest handles this automatically when given the server instance.
- **Flaky tests from shared state**: If tests fail intermittently, check for shared database rows or in-memory singletons. Use `beforeEach` to reset state, not `beforeAll`.
- **BullMQ jobs in tests**: Mock the queue to prevent real job processing. Assert on `queue.add()` calls rather than job execution.

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

- SQLite for integration tests (behavior differs from PostgreSQL - use Testcontainers)
- No types in test helpers (TypeScript applies in tests too)
- Testing implementation details (asserting on mock internals instead of outputs)
- Shared mutable state between tests (causes ordering-dependent failures)
- Snapshot tests for business logic (snapshots are for serialization shapes only)
- Hardcoded ports in e2e tests (causes conflicts in parallel test runs)
