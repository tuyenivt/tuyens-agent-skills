---
name: node-testing-patterns
description: Jest testing patterns for NestJS / Express: unit mocks, Supertest e2e, TestingModule, Testcontainers PostgreSQL, per-test isolation.
metadata:
  category: backend
  tags: [node, typescript, jest, testing, supertest, testcontainers]
user-invocable: false
---

# Testing Patterns

> Load `Use skill: stack-detect` first. `Test framework` picks Jest (default, and for `unknown`) or Vitest (`vi.fn` / `vi.mock`, `vitest-mock-extended` 3 on Vitest 3 and 5 on Vitest 4, `globalSetup` in `vitest.config` receiving the `TestProject` - the worker count is `project.config.maxWorkers`, pinned in config - and the worker id in `VITEST_POOL_ID`; the mock and test shapes carry over). `ORM` picks the migrate command for the DB setup - Prisma and TypeORM below; any other ORM, or none, keeps the schema-per-worker shape with the project's own migrate command. `Database` picks the engine: a non-PostgreSQL database uses the matching Testcontainers module (a real engine of the same kind). `Build tool` picks the runner command; the Runner cell reads `<framework> via <manager> test` (`bun run test` on Bun). All of it surfaces in the plan's Infrastructure table - in a review or diagnosis, only inside the `Fix:` lines that name the runner or database, with no header line.

## When to Use

- Writing unit tests for services, repositories, utilities
- Writing e2e and integration tests for NestJS or Express endpoints
- Setting up test infrastructure (DB, mocks, test module), with or without Docker on CI
- Reviewing test code or diagnosing flaky, hanging, or order-dependent suites

## Rules

- TypeScript in tests: no `any`, typed mocks, typed assertions
- Each test independent: no shared mutable state
- A real database of the production engine for integration and e2e (PostgreSQL below; MySQL through its own Testcontainers module) - Testcontainers, or a shared test instance with a schema per worker; never SQLite standing in for it
- Prefer DI overrides for mocking over `jest.mock()`. A top-level `jest.mock()` is hoisted above the imports and applies to every test in that file. Set `clearMocks: true` in the Jest config; add `restoreMocks: true` only when mock implementations are set in `beforeEach` (Jest 29.4.3-29.6.2 also reset `jest.fn()` implementations set in `beforeAll` or a factory; 29.6.3+ and 30 restore `spyOn` mocks only)
- Test names state behavior: "should return 201 when order is created"
- Layer boundaries: unit mocks the DB; e2e and integration both use a **real** database. E2e drives HTTP through the app and asserts status plus response shape; integration calls the service or repository directly and asserts persisted rows
- Runner: run through the project's package manager script (`npm test` / `pnpm test` / `yarn test` / `bun run test`) - never a bare runner binary. On Bun, `bun run test` runs the Jest script; plain `bun test` runs Bun's own runner, where `jest-mock-extended` (it imports `@jest/globals`) fails to load

## Patterns

### NestJS Unit Testing

```typescript
describe("OrderService", () => {
  let service: OrderService;
  let prisma: DeepMockProxy<PrismaService>;
  let queue: { add: jest.Mock };

  beforeEach(async () => {
    queue = { add: jest.fn() };
    prisma = mockDeep<PrismaService>();
    const module = await Test.createTestingModule({
      providers: [
        OrderService,
        { provide: PrismaService, useValue: prisma },
        { provide: getQueueToken(ORDER_QUEUE), useValue: queue },
      ],
    }).compile();
    service = module.get(OrderService);
  });

  it("should persist the order and enqueue processing", async () => {
    prisma.$transaction.mockImplementation(async (fn) => fn(prisma));
    prisma.order.create.mockResolvedValue(mockOrder);

    const result = await service.create(dto);

    expect(prisma.order.create).toHaveBeenCalledWith(expect.objectContaining({
      data: expect.objectContaining({ customerId: dto.customerId }),
    }));                                                   // the persisted data is the outward effect
    expect(queue.add).toHaveBeenCalledWith("process-order", { orderId: mockOrder.id }, expect.anything());
    expect(result.orderId).toBe(mockOrder.id);
  });
});
```

- `Test.createTestingModule()` for isolated module testing; override providers via `.overrideProvider(X).useValue(...)`
- `jest-mock-extended` (`mockDeep`) for typed Prisma mocks - a devDependency to add when absent
- Assert on outward effects - the data written, the job enqueued, the return value - not on which internal method ran

### NestJS E2E Testing

E2e imports `AppModule` (with the Redis lane below when it hosts BullMQ, or the feature-module build under BullMQ below); a module built from one controller is a unit test, not e2e. E2e runs against a real database (below) and must configure the app exactly as `main.ts` does: `createNestApplication()` does not run `main.ts`, so a test that re-declares only the pipes misses the global prefix, versioning, filters, and interceptors. Put one `configureApp(app)` in its own module (`src/configure-app.ts`) that both `main.ts` and the spec import - importing it from `main.ts` would run `bootstrap()` inside the test. Override the auth guard so it still rejects a request without a test identity, or mint a real token from the app's own `JwtService` (`app.get(JwtService).sign({ sub: user.id, tenantId })`, sent as `` .set("authorization", `Bearer ${token}`) ``) - either way the 401 cases still assert something. When the guard is global (`{ provide: APP_GUARD, useClass: JwtAuthGuard }`), `overrideGuard` does not reach it: register it as `{ provide: APP_GUARD, useExisting: JwtAuthGuard }` plus `JwtAuthGuard` as a provider, and use `.overrideProvider(JwtAuthGuard)`.

```typescript
describe("Orders API (e2e)", () => {
  let app: INestApplication;

  beforeAll(async () => {
    const module = await Test.createTestingModule({ imports: [AppModule] })
      .overrideGuard(JwtAuthGuard)
      .useValue({
        canActivate: (ctx: ExecutionContext) => {
          const req = ctx.switchToHttp().getRequest();
          if (!req.headers["x-test-user"]) throw new UnauthorizedException();   // 401; returning false is a 403
          req.user = testUser;
          return true;
        },
      })
      .compile();
    app = module.createNestApplication();
    configureApp(app);                                        // from src/configure-app.ts, shared with main.ts
    await app.init();
  });

  afterAll(() => app.close());

  it("should return 201 when creating an order", async () => {
    const res = await request(app.getHttpServer())
      .post("/api/v1/orders")
      .set("x-test-user", "1")
      .send({ customerId: customer.id, items: [{ productId: product.id, quantity: 1 }] })
      .expect(201);
    expect(res.body).toMatchObject({ status: "PENDING" });
  });
});
```

### Integration Testing

```typescript
it("should persist one order per idempotency key under a concurrent retry", async () => {
  const [a, b] = await Promise.allSettled([service.createOrder(dto), service.createOrder(dto)]);
  expect([a.status, b.status]).toContain("fulfilled");
  expect(await prisma.order.count({ where: { idempotencyKey: dto.idempotencyKey } })).toBe(1);
});
```

The service comes from a `TestingModule` wired to the real test database; the assertion reads the rows back.

### Express Testing

```typescript
import request from "supertest";
import { app } from "../src/app";          // export the app; listen() lives in index.ts

it("should return 200 on an idempotent payment replay", async () => {
  const payload = { idempotencyKey: "key-1", amount: 100 };
  await request(app).post("/api/v1/payments").send(payload).expect(201);
  await request(app).post("/api/v1/payments").send(payload).expect(200);
});
```

Pass the app to Supertest - it binds an ephemeral port per request. Never `app.listen(3000)` in a test.

### Database Setup

One PostgreSQL per run, one schema per Jest worker, migrations applied per schema. With Docker, start a Testcontainers container in `globalSetup`; without Docker on CI, point at the shared test instance and add a run-scoped prefix so concurrent CI jobs never touch each other's schemas.

```typescript
// jest config (rootDir = the repo root; under an e2e config whose rootDir is test/, drop the test/ prefix):
//              { globalSetup: "<rootDir>/test/global-setup.ts", globalTeardown: "<rootDir>/test/global-teardown.ts",
//                setupFiles: ["<rootDir>/test/setup-env.ts"] }
// test/db-url.ts - the base URL may already carry a query string (?sslmode=require)
export const workerDbUrl = (base: string, run: string, worker: string | number) => {
  const u = new URL(base);
  u.searchParams.set("schema", `t_${run}_${worker}`);   // Prisma 5-6: the schema parameter sets search_path
  u.searchParams.set("connection_limit", "5");
  return u.toString();
};

// test/global-setup.ts - runs once, in the parent process (JEST_WORKER_ID is not set here)
declare global { var __PG__: StartedPostgreSqlContainer | undefined }   // shared with globalTeardown only
export default async function globalSetup(globalConfig: Config.GlobalConfig) {
  if (process.env.CI_NO_DOCKER) {
    process.env.TEST_DB_BASE = process.env.SHARED_TEST_DB_URL;           // shared instance
  } else {
    globalThis.__PG__ = await new PostgreSqlContainer("postgres:17-alpine").start();   // pin the major
    process.env.TEST_DB_BASE = globalThis.__PG__.getConnectionUri();
  }
  process.env.TEST_RUN_ID = process.env.CI_JOB_ID ?? String(Date.now());
  for (let w = 1; w <= globalConfig.maxWorkers; w++) {                   // Jest's own worker count
    const url = workerDbUrl(process.env.TEST_DB_BASE!, process.env.TEST_RUN_ID, w);
    execSync("npx prisma migrate deploy", { env: { ...process.env, DATABASE_URL: url } });   // per schema
  }
}

// test/setup-env.ts - `setupFiles`, runs in each worker before the test file
process.env.DATABASE_URL = workerDbUrl(process.env.TEST_DB_BASE!, process.env.TEST_RUN_ID!, process.env.JEST_WORKER_ID!);
// Prisma 7 (driver adapters): the runtime client ignores ?schema= and connection_limit - the adapter carries both
const schema = `t_${process.env.TEST_RUN_ID}_${process.env.JEST_WORKER_ID}`;
export const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL, max: 5, options: `-c search_path=${schema}` }, { schema });
// the e2e module uses it - .overrideProvider(PrismaService).useValue(new PrismaClient({ adapter })) - or PrismaService builds its
// adapter from these env values; otherwise every Prisma 7 worker lands in `public`

// test/global-teardown.ts - DROP SCHEMA ... CASCADE for each t_<run>_<w>, then stop the container if one was started

// per test file - reset on entry, so a crashed or filtered-out test leaves nothing behind
beforeEach(() => prisma.$executeRawUnsafe(`TRUNCATE "Order", "OrderItem" RESTART IDENTITY CASCADE`));
```

- Prisma 5-6 selects the schema from the `?schema=` URL parameter - it sets `search_path` and keeps `_prisma_migrations` there; a `search_path` set any other way does not steer `migrate deploy`. Prisma 7's CLI reads the URL from `prisma.config.ts` (`env("DATABASE_URL")` picks up the per-schema URL above) while the runtime client takes schema and pool size from the adapter, as in `setup-env.ts`. `migrate deploy` does not run `prisma generate` - the generated client exists before the workers start (`postinstall` or an explicit step). MySQL: a schema is a database - `CREATE DATABASE t_<run>_<w>` as root (`new MySqlContainer("mysql:8.0")`, `getConnectionUri(true)`; the default `test` user lacks the privilege), and the reset is one `TRUNCATE TABLE <t>` per table between `SET FOREIGN_KEY_CHECKS=0` and `=1`, sent as separate statements on one connection (a `prisma.$transaction([...])` batch) - `FOREIGN_KEY_CHECKS` is a session variable, so the pooling rule below applies. TypeORM: set the `schema` option on the `DataSource` and run the migrations (`dataSource.runMigrations()`; when `migrations` points at `dist/`, build first or point the test DataSource at the `src` glob through ts-jest); `synchronize` builds from entity metadata only, so objects that exist only in hand-written migration SQL (extensions, triggers, raw DDL) are absent
- Raw `BEGIN` / `ROLLBACK` around a test does not isolate: the client pools connections, so `BEGIN` and the next query may run on different ones
- Cap the per-worker pool (`connection_limit` on the URL for Prisma 5-6, `max` on the `PrismaPg` adapter for Prisma 7, `poolSize` for TypeORM) - `maxWorkers` x the default pool exhausts a small instance's `max_connections` and reads as flakiness. Read the schema count from Jest's `maxWorkers` (above), never a separate setting
- Container startup takes 10-30s: give `globalSetup` the time (Jest's `testTimeout` does not apply to it; a CI step timeout does)

### Test Data Factories

Factories beat object literals: one place owns the default shape, tests override only the fields they care about, and adding a non-null column doesn't touch every test.

```typescript
import { Factory } from "fishery";
import { faker } from "@faker-js/faker";   // 9 under Jest + ts-jest (CommonJS); 10 is ESM-only

export const orderFactory = Factory.define<Order>(({ sequence }) => ({
  id: `ord_${sequence}`,
  customerId: faker.string.uuid(),
  status: "PENDING",
  total: faker.number.int({ min: 1_00, max: 100_00 }),
  createdAt: new Date(),
}));

const shipped = orderFactory.build({ status: "SHIPPED" });
const batch   = orderFactory.buildList(5, { customerId: "cust-1" });
```

### State Machine Transitions

```typescript
const cases: [OrderStatus, OrderStatus, boolean][] = [
  ["PENDING", "CONFIRMED", true],
  ["PENDING", "DELIVERED", false],
  ["SHIPPED", "DELIVERED", true],
];

it.each(cases)("transition %s -> %s allowed=%s", async (from, to, ok) => {
  const order = await createOrder(orderFactory.build({ status: from }));
  const promise = service.transition(order.id, to);
  await (ok ? expect(promise).resolves.toBeDefined() : expect(promise).rejects.toThrow(InvalidTransitionError));
});
```

### Webhook Signature Validation

Use the provider's test helper to sign the exact string you send - a JSON string, with the matching content type, or the raw-body parser never captures it:

```typescript
const payload = JSON.stringify(event);
const sig = stripe.webhooks.generateTestHeaderString({ payload, secret });
await request(app).post("/webhooks/stripe").set("content-type", "application/json")
  .set("stripe-signature", sig).send(payload).expect(200);
await request(app).post("/webhooks/stripe").set("content-type", "application/json")
  .set("stripe-signature", "t=1,v1=bad").send(payload).expect(401);
```

A provider with no helper: compute the signature in the test with the same function the handler uses to verify, over the same raw string.

### Test Structure

- `describe`/`it` with behavior names; `it.each` for table-driven cases
- `beforeAll` for app setup, `afterAll` teardown, `beforeEach` for data reset
- `expect().resolves` / `expect().rejects` for async
- Snapshots only for serializer/response shapes, never business logic

## Edge Cases

- **Flaky tests** - triage by symptom: passes alone or with `--runInBand` but fails in parallel means contention between workers over an external shared resource (a DB schema or rows, a port, a fixed Redis key or queue name, a temp file path); fails only with `--randomize` means an ordering assumption inside a file; hangs after the run means an open handle (`--detectOpenHandles`) - usually a server, pool, Redis socket, or timer nobody closed (`app.close()` runs `onModuleDestroy`, so `$disconnect` only when `PrismaService` implements it; a client built outside Nest needs its own `afterAll(() => prisma.$disconnect())`)
- **Retry loops** (`node-http-client-patterns`): sequence MSW responses with one-shot handlers (`server.use(http.get(url, resolver, { once: true }))` - a bare `server.use` persists until `resetHandlers()`), and drive the backoff with `jest.useFakeTimers()` + `jest.advanceTimersByTimeAsync(ms)`. Under Jest's CommonJS runtime MSW 2.11.3+ pulls ESM-only deps and MSW 3 is ESM-only itself (`Must use import to load ES Module`): pin `msw@~2.10`, or babel-jest with `transform` covering `.mjs` (`"^.+\\.[mc]?js$"`) and `transformIgnorePatterns` un-ignoring them
- **BullMQ**: on the producer side mock the queue and assert on `queue.add()`. To exercise processor logic, register the `@Processor` class as a plain provider and call `process(job)` with a mock `Job` - never import `BullModule`, which is what opens the Redis socket (a bare `new Worker(name, fn)` is tested by calling `fn(job)`; an anonymous `fn` inside a top-level `new Worker` is extracted and exported first, and is a finding). An e2e suite that imports `AppModule` boots `BullModule` with it: give that lane a Redis container, or build the test module from the feature modules and override the queue tokens - a `@Processor` host opens its Worker socket however the queue is mocked. Broker behaviour itself - `attempts` / `backoff` exhaustion, stall redelivery, DLQ drain - goes in its own file against a real Redis, with backoff delays overridden to CI-viable values
- **Snapshots**: on a response containing generated ids or timestamps, pass property matchers to the snapshot - `expect(body).toMatchSnapshot({ id: expect.any(String), createdAt: expect.any(String) })`. A raw `toMatchSnapshot()` fails on every run as the values change; `-u` would only re-baseline it once

## Output Format

When planning or authoring, emit this block plus the test and setup code it describes; a build over existing tests is authoring plus review - findings for the existing defects the change touches, then the block. Tests for code with a known defect assert the correct behaviour, and the defect is a finding - never a test that pins the bug. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file; `cause.ts:line -> symptom.ts:line` when the two sit in different files) followed by `Issue:` and `Fix:` lines, `[Must]` first - `[Must]` when it risks incorrect behaviour, data loss, or a security hole (a test that cannot fail, a suite that tests a system that does not ship, isolation that leaks), `[Recommend]` otherwise - one per anti-pattern, with no plan tables. A Lane is one runner config - a config file (`test/jest-e2e.json`) or a Jest / Vitest `projects` entry (Vitest `workspace` before 3.2); a section with no rows carries the line `none`. A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright gets one `Ruling:` line; both precede the findings.

```
## Test Plan

### Infrastructure
| Lane | Runner (framework + command) | Database | Provisioning | Isolation |
|------|------------------------------|----------|--------------|-----------|

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

- `-u` on a failing snapshot without reading the diff
- A test that pins a known defect
