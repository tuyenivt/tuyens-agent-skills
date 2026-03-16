---
name: node-testing-patterns
description: Jest testing patterns for NestJS and Express - unit tests with mocking, e2e tests with Supertest, NestJS TestingModule, Testcontainers for real PostgreSQL, and TypeScript-first test conventions.
metadata:
  category: backend
  tags: [node, typescript, jest, testing, supertest, testcontainers]
user-invocable: false
---

# Testing Patterns

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

### NestJS Testing

```typescript
// Unit test with TestingModule
const module = await Test.createTestingModule({
  providers: [
    OrderService,
    { provide: PrismaService, useValue: mockPrisma },
  ],
}).compile();

const service = module.get<OrderService>(OrderService);
```

- `Test.createTestingModule()` for isolated module testing
- Override providers for mocking: `.overrideProvider(PrismaService).useValue(mockPrisma)`
- E2E with Supertest: `app.getHttpServer()` + `request(server).get('/api/orders')`
- Use `@nestjs/testing` utilities

### Express Testing

```typescript
// E2E test with Supertest
import request from "supertest";
import { app } from "../src/app";

describe("Orders API", () => {
  it("should return 200 with order list", async () => {
    const res = await request(app).get("/api/v1/orders").expect(200);
    expect(res.body).toHaveProperty("data");
  });
});
```

- Supertest directly on Express app
- Mock services via dependency injection or `jest.mock()`

### Running Tests

- Prefer `bun test` or `bun run test` (faster install and execution)
- Falls back to `npx jest` if bun is not available

### Database Testing with Testcontainers

```typescript
import { PostgreSqlContainer } from "@testcontainers/postgresql";

let container: StartedPostgreSqlContainer;

beforeAll(async () => {
  container = await new PostgreSqlContainer().start();
  // Use container.getConnectionUri() for Prisma or TypeORM
}, 60_000); // containers need longer timeout

afterAll(async () => {
  await container.stop();
});
```

- Prisma: use `prisma migrate deploy` on test container
- TypeORM: `synchronize: true` ONLY in test config
- Transaction rollback per test for isolation

### Mocking

- `jest.mock()` for module-level mocking
- `jest.spyOn()` for partial mocking
- Manual mocks in `__mocks__/` directories
- Prefer dependency injection over `jest.mock` when possible

### Test Structure

- `describe`/`it` blocks with clear naming: "should return 201 when order is created"
- `beforeAll` for DB setup, `afterAll` for teardown, `beforeEach` for data reset
- Use `expect().resolves` / `expect().rejects` for async assertions
- Snapshot testing ONLY for serializers/response shapes, not business logic

## Edge Cases

- **Testcontainers timeout on CI**: Container startup can take 10-30 seconds. Set `beforeAll` timeout to at least 60 seconds. If CI has no Docker, fall back to a shared test database with per-test transaction rollback.
- **Port conflicts in e2e tests**: Use `app.listen(0)` to let the OS assign a random port. Supertest handles this automatically when given the server instance.
- **Flaky tests from shared state**: If tests fail intermittently, check for shared database rows or in-memory singletons. Use `beforeEach` to reset state, not `beforeAll`.

## Avoid

- SQLite for integration tests (behavior differs from PostgreSQL - use Testcontainers)
- No types in test helpers (TypeScript applies in tests too)
- Testing implementation details (asserting on mock internals instead of outputs)
- Shared mutable state between tests (causes ordering-dependent failures)
- Snapshot tests for business logic (snapshots are for serialization shapes only)
