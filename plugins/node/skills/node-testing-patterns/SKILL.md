---
name: node-testing-patterns
description: "Jest testing patterns for NestJS and Express. Unit tests, e2e tests with Supertest, NestJS testing module, mocking, test database with Testcontainers, and TypeScript-first testing."
user-invocable: false
---

Cover:

1. NESTJS TESTING:
   - Test.createTestingModule() for isolated module testing
   - Override providers for mocking: .overrideProvider(PrismaService).useValue(mockPrisma)
   - E2E with Supertest: app.getHttpServer() + request(server).get('/api/orders')
   - Use @nestjs/testing utilities

2. EXPRESS TESTING:
   - Supertest directly on Express app
   - request(app).get('/api/v1/orders').expect(200)
   - Mock services via dependency injection or jest.mock()

3. DATABASE TESTING:
   - testcontainers (testcontainers-node) for real PostgreSQL
   - Prisma: use prisma migrate deploy on test container
   - TypeORM: synchronize: true ONLY in test config
   - Transaction rollback per test for isolation

4. MOCKING:
   - jest.mock() for module-level mocking
   - jest.spyOn() for partial mocking
   - Manual mocks in **mocks**/ directories
   - Prefer dependency injection over jest.mock when possible

5. PATTERNS:
   - describe/it blocks with clear naming: "should return 201 when order is created"
   - beforeAll for DB setup, afterAll for teardown, beforeEach for data reset
   - Use expect().resolves / expect().rejects for async assertions
   - Snapshot testing ONLY for serializers/response shapes, not business logic

6. ANTI-PATTERNS:
   - ❌ SQLite for integration tests (use Testcontainers PostgreSQL)
   - ❌ No types in test helpers (TypeScript in tests too)
   - ❌ Testing implementation details (mock internals)
   - ❌ Shared mutable state between tests
