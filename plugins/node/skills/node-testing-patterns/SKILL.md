---
name: node-testing-patterns
description: Jest testing patterns for NestJS / Express: unit mocks, Supertest e2e, TestingModule, Testcontainers PostgreSQL, per-test isolation.
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
- Prefer DI overrides for mocking over `jest.mock()`. `jest.mock()` is hoisted to the top of the file regardless of where it is written, so it silently applies to every test in that file - including e2e ones. Set `clearMocks` and `restoreMocks` in the Jest config so spies never leak across tests
- Test names state behavior: "should return 201 when order is created"
- Layer boundaries: unit mocks the DB, e2e and integration both use a **real** database. E2e drives HTTP through the app and asserts status plus response shape; integration calls the service or repository directly and asserts persisted rows
- Runner: run through the project's package manager script (`npm test` / `pnpm test` / `yarn test` / `bun run test`) - never a bare runner binary

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

E2e runs against the real database from the Testcontainers section below, and must mirror `main.ts`'s pipe configuration exactly - a pipe that differs from production tests a system that does not ship. Override the auth guard rather than removing it, or mint a real token from the app's own `JwtService` so the 401 cases still assert something.

```typescript
describe("Orders API (e2e)", () => {
  let app: INestApplication;

  beforeAll(async () => {
    const module = await Test.createTestingModule({ imports: [AppModule] })
      .overrideGuard(JwtAuthGuard)                       // or keep it real and mint a token
      .useValue({ canActivate: (ctx) => { ctx.switchToHttp().getRequest().user = testUser; return true; } })
      .compile();
    app = module.createNestApplication();
    app.useGlobalPipes(new ValidationPipe({ whitelist: true }));   // same options as main.ts
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
  // Pin the tag - an unpinned image drifts from the CI/production major version
  container = await new PostgreSqlContainer("postgres:16-alpine").start();
  process.env.DATABASE_URL = `${container.getConnectionUri()}?connection_limit=5`;
  execSync("npx prisma migrate deploy", { env: process.env });
}, 60_000);

afterAll(() => container.stop());

// Per-test isolation: truncate mutated tables in beforeEach, not afterEach - a crashed or
// filtered-out test leaves rows behind, and reset-on-entry also gives you a guaranteed-empty table.
// Raw BEGIN/ROLLBACK does NOT isolate: PrismaClient pools connections, so BEGIN and the
// next query may run on different connections.
beforeEach(() => prisma.$executeRawUnsafe(`TRUNCATE "Order", "OrderItem" RESTART IDENTITY CASCADE`));
```

- Prisma: `prisma migrate deploy` on the container. TypeORM: `synchronize: true` only in test config - and never when a migration carries hand-written SQL (partial indexes, extensions), which `synchronize` silently drops
- Start the container once in `globalSetup`, not per spec file, and give each Jest worker its own schema inside it (`JEST_WORKER_ID` in the `search_path`); dropping the container per file multiplies a 10-30s startup by the file count
- Set `connection_limit` on the test URL - `maxWorkers` x the default pool exhausts a small container's `max_connections` and reads as flakiness

### Test Data Factories

Factories beat object literals: one place owns the default shape, tests override only the fields they care about, and adding a non-null column doesn't touch every test.

```typescript
import { Factory } from "fishery";
import { faker } from "@faker-js/faker";

export const orderFactory = Factory.define<Order>(({ sequence }) => ({
  id: `ord_${sequence}`,
  customerId: faker.string.uuid(),
  status: "PENDING",
  total: faker.number.int({ min: 1_00, max: 100_00 }),
  createdAt: new Date(),
}));

// Per-test overrides
const pending = orderFactory.build();
const shipped = orderFactory.build({ status: "SHIPPED" });
const batch   = orderFactory.buildList(5, { customerId: "cust-1" });
```

`fishery` (typed, sequence-aware) or a `createOrderFactory()` helper - both beat ad-hoc literals. `@faker-js/faker` for realistic field values; never hardcode `"test@test.com"` in 30 files.

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
- Runner: `bun run test` (executes the Jest script). Plain `bun test` invokes Bun's own runner, not Jest - TestingModule/`jest-mock-extended` setups break

## Edge Cases

- **Testcontainers on CI**: startup 10-30s; set `beforeAll` timeout >=60s. No Docker on CI -> shared DB, one schema per Jest worker (`JEST_WORKER_ID`) with `search_path` set per connection, plus a run-scoped prefix so concurrent CI jobs on the same instance cannot truncate each other. Drop the schemas in `globalTeardown`.
- **Port conflicts**: pass the app instance to Supertest, or `app.listen(0)` for an OS-assigned port.
- **Flaky tests**: usually shared rows or in-memory singletons; reset in `beforeEach`, not `beforeAll`. Triage by symptom - passes with `--runInBand` means order dependence, fails only with `--randomize` means a hidden ordering assumption, hangs means an unclosed handle (`--detectOpenHandles`).
- **BullMQ**: on the producer side mock the queue and assert on `queue.add()`. To exercise processor logic, register the `@Processor` class as a plain provider and call `process(job)` with a mock `Job` - never import `BullModule`, which is what opens the Redis socket. Do not run a real Worker for handler logic. The one exception is broker behaviour itself - `attempts` / `backoff` exhaustion, `lockDuration` stall redelivery, DLQ drain - which cannot be observed without a broker: put those in their own file against Testcontainers Redis, with backoff delays overridden to CI-viable values.
- **Snapshots**: on a response containing generated ids or timestamps, `toMatchObject` with property matchers - a raw `toMatchSnapshot()` re-baselines on every run.

## Output Format

When planning or authoring, emit this block plus the test and setup code it describes. When reviewing existing tests, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit one finding per anti-pattern and skip the plan tables.

```
## Test Plan

### Infrastructure
| Lane | Database | Provisioning | Isolation | Runner command |
|------|----------|--------------|-----------|----------------|

### Unit Tests
| Test | Service Method | Mocks | Assertions |
|------|---------------|-------|------------|

### E2E Tests
| Test | Endpoint | Method | Status | Auth | Assertions |
|------|----------|--------|--------|------|------------|

### Integration Tests
| Test | Database | Setup | Assertions |
|------|----------|-------|------------|

### Coverage Targets
- Service layer: {count} unit tests
- API layer: {count} e2e tests
- Persistence layer: {count} integration tests
```

## Avoid

- Testing implementation details (asserting on mock internals vs outputs)
- Shared mutable state between tests (ordering-dependent failures)
- Snapshots for business logic
- Hardcoded ports in e2e tests
- Untyped test helpers
