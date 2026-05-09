---
name: task-node-test
description: Node.js test strategy and scaffolding using Jest, Supertest, NestJS TestingModule, Testcontainers PostgreSQL, MSW for HTTP stubs, BullMQ testing, and TypeScript strict-mode test typing. Detects NestJS vs Express and applies the right idioms. Use when designing a test plan, assessing coverage gaps, or scaffolding endpoint/service/job/security tests. Stack-specific override of task-code-test, invoked when stack-detect resolves to Node.js / TypeScript.
agent: node-test-engineer
metadata:
  category: backend
  tags: [node, typescript, jest, nestjs, express, testcontainers, supertest, msw, testing, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, generate one test per acceptance criterion (use `// Satisfies: AC<N>` mapping or test-name suffix), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface coverage gaps as proposed amendments.

# Node.js Test

## Purpose

Node.js-aware test strategy and scaffolding using Jest, Supertest, NestJS `TestingModule` with `overrideProvider`, Testcontainers PostgreSQL, MSW (`msw` / `msw/node`) for HTTP stubs, BullMQ testing (`@nestjs/bull` mock queues / fixture-based workers), and TypeScript strict-mode test typing. Replaces the generic backend test patterns with Node-specific guidance.

This workflow is the stack-specific delegate of `task-code-test` for Node.js. The core workflow's contract (output shape, prioritization rules) is preserved so callers see a stable shape.

## When to Use

- Designing a test strategy for a new NestJS or Express service / module
- Assessing test coverage gaps across unit / integration / endpoint / BullMQ layers
- Scaffolding tests for under-covered endpoints, services, repositories, or auth code
- Reviewing test pyramid balance for a Node app
- Adding boundary tests (validation, authorization, edge cases) to existing happy-path tests

**Not for:**

- Test failure debugging (use `task-node-debug`)
- General code review (use `task-code-review` / `task-node-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Node.js / TypeScript. If the detected stack is not Node, stop and tell the user to invoke `/task-code-test` instead.

Detect framework: NestJS (`nest-cli.json` + `@nestjs/*`) vs Express (`express` in deps without NestJS). Detect ORM: Prisma vs TypeORM. Record `Framework: NestJS | Express | mixed`, `ORM: Prisma | TypeORM` for the output. Each section that follows branches on this signal where the test idiom differs.

### Step 2 - Read the Code Under Test and Existing Tests

Before producing assessment, scaffolds, or strategy, open both the production code in scope and a representative sample of existing tests. This grounds the output in real conventions instead of generic templates.

- For each target named by the user, read the module top-to-bottom: public functions / classes, request / response types, guards / middleware, transaction boundaries, external collaborators
- Glob `src/**/*.spec.ts`, `test/**/*.e2e-spec.ts`, `**/*.test.ts` and read at least: one existing endpoint test, one existing service / repository test, one existing BullMQ job test (if applicable), test setup files - learn the project's package layout, mock strategy (`jest.mock` vs `TestingModule.overrideProvider`), HTTP-stub library (`msw` vs `nock`), authentication helpers
- Read `jest.config.{js,ts}` / `package.json` `jest` field for `setupFilesAfterEach`, `testEnvironment`, `moduleNameMapper`, coverage config
- Read `test/setup.ts` (or equivalent) and per-module `*.spec.ts` setup for shared fixtures (Testcontainers init, NestJS app factory, factory utilities)
- For NestJS: read `app.module.ts` / `main.ts` for `ValidationPipe`, global guards / interceptors that endpoint tests must replicate; for Express: read `app.ts` middleware order

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc rather than inventing them silently.

### Step 3 - Node.js Test Pyramid

The Node test pyramid maps to test types:

| Layer       | Tooling                                                             | What belongs here                                                              |
| ----------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Unit        | Jest + plain mocks / `jest.fn()`                                    | Service business logic, validators, mappers, pure functions, calculation rules |
| Integration | Jest + Testcontainers PostgreSQL + real Prisma / TypeORM client     | Repository queries, ORM constraints, DB-level invariants                       |
| Endpoint    | Jest + Supertest + NestJS `TestingModule` (or Express app instance) | Routing, request / response binding, validation, guards / middleware           |
| Job         | Jest + BullMQ in-memory queue or `@nestjs/bull` mock                | BullMQ job processor happy path, retry logic, idempotency                      |
| E2E         | Jest + Testcontainers + real BullMQ worker / Redis                  | Critical user journeys only - signup, checkout, payment                        |
| Contract    | Pact / OpenAPI consumer-driven                                      | API contract validation against schema                                         |

**Many** unit tests, **some** endpoint / integration tests, **few** full E2E tests.

### Step 4 - Apply Node.js Test Patterns

Use skill: `node-testing-patterns` for the canonical patterns referenced below.

**Unit tests (`*.spec.ts` colocated):**

- Jest (`describe`, `it`, `expect`, `beforeEach`); `jest.mock(...)` for ESM modules with proper `__esModule: true` shape
- Test the public function / method - one test per outcome (success, validation failure, external failure, edge case)
- **No NestJS app context / DB** - if a unit test needs `TestingModule` or DB, it is misclassified
- Stub external HTTP via `msw` setupServer; do not stub repositories with full SQL behavior - use Testcontainers for that
- TypeScript strict: avoid `as any` in test setup; use `jest.MockedFunction<typeof fn>` / `DeepMocked<T>` (from `@golevelup/ts-jest`)

**NestJS endpoint tests (`*.e2e-spec.ts`):**

- `Test.createTestingModule({ imports: [AppModule] }).compile()` then `app = moduleRef.createNestApplication()` then `await app.init()`
- Apply the same global pipes / guards / interceptors as `main.ts` - missing `app.useGlobalPipes(new ValidationPipe(...))` makes validation tests pass under test but fail in prod
- `request(app.getHttpServer()).post('/orders').send(payload).expect(201)` via Supertest
- One test per `(method, path, principal-state, outcome)` triple
- Authentication via `overrideGuard(AuthGuard('jwt'))` returning a stub user, or by injecting a real JWT
- Authorization: a separate test for "anonymous → 401" and "wrong role → 403" per protected endpoint
- Validation: a "rejects invalid payload" test for any endpoint with a DTO body
- Response shape: assert key fields, status, headers, and `Content-Type`
- DB: override Prisma / TypeORM client to point at the Testcontainers connection; transactional rollback per test

**Express endpoint tests:**

- Build app instance once per test file; `request(app).post('/orders').send(payload).expect(201)`
- Apply same middleware stack as production - missing `app.use(express.json())` or auth middleware silently passes tests but fails in prod
- One test per `(method, url, principal, outcome)` triple
- Authentication: mount `requireAuth` middleware; override with a fixture that injects `req.user` for authed cases; omit middleware for anonymous
- Validation: assert `response.status === 400` and key error fields
- DB: same Testcontainers approach

**Repository / ORM integration tests:**

- Testcontainers PostgreSQL (`testcontainers` npm package) - **not SQLite, not in-memory** - SQLite diverges from PostgreSQL on JSON / JSONB, partial indexes, window functions, `ON CONFLICT`, array types, `LATERAL` joins
- Per-test transactional rollback via fixture (Prisma: `prisma.$transaction` with manual rollback throw; TypeORM: `dataSource.transaction` + manual rollback; or per-test schema reset)
- One test per non-trivial query: assert SQL semantics (filter correctness, sort order, eager-load result), not just "method returns something"
- N+1 detection: enable Prisma `log: ['query']` and count queries via event listener; for TypeORM, `dataSource.options.logging = true` and capture
- Custom indexes / constraints: insert violating data and assert the right exception is raised (`P2002` for Prisma, `QueryFailedError` for TypeORM)

**DTO / Schema tests:**

- NestJS / class-validator: use `validate(plainToInstance(CreateOrderDto, {...}))` from `class-validator` + `class-transformer` directly - faster than going through a full endpoint test
- Express / Zod: `OrderCreateSchema.safeParse({...})` - assert `success: false` and key error paths
- Edge cases: missing fields, wrong types, out-of-range values, `forbidNonWhitelisted` / `.strict()` rejecting unknown keys
- Custom validators tested in isolation

**BullMQ job tests:**

- In-memory queue or `@nestjs/bull` `getQueueToken()` overridden to a mock for synchronous-execution tests (fast, no Redis)
- Real BullMQ + Testcontainers Redis for tests that need actual broker behavior (retry, `lockDuration` stalls, real `attempts`)
- Idempotency test: invoke the processor twice with the same input, assert side effect happens once
- Retry test: stub the external call to fail twice then succeed; assert job completes; assert `attempts` decrements
- DLQ / max-retries test: stub the external call to fail forever; assert job ends in `failed` state without infinite loop

**E2E / full-context tests:**

- Reserve for tests that genuinely need the full stack: auth flow end-to-end, transactional commit + BullMQ dispatch, scheduled-job behavior
- Use Testcontainers to spin up Redis + Postgres
- Avoid for tests that an endpoint test could cover - context-load cost compounds

### Step 5 - Test Boundaries (Node-Specific)

**What deserves a unit test:**

- Service logic, mappers, validators, custom guards (the `canActivate` logic in isolation), custom pipes (the `transform` logic in isolation)
- Domain rules, calculation, state-machine transitions
- Framework-independent helpers / utilities

**What deserves an endpoint test:**

- Every endpoint: happy path + 401 + 403 + 4xx validation
- Pagination contract (`take` / `skip` / cursor)
- Filtering / sorting / search query params
- Custom exception filters (NestJS `@Catch`) / error handlers (Express middleware)

**What deserves an integration / Testcontainers test:**

- Every repository method with a non-trivial query (filter on multiple columns, eager-load via `include`, aggregate)
- ORM constraints (unique, check, FK ON DELETE behavior)
- Migration smoke test: apply all migrations on a clean Testcontainers DB; useful when migrations are squashed

**What deserves a BullMQ test:**

- Every job with retry logic, idempotency requirements, or external side effects
- Job flows / chains - assert the workflow completes and aggregates correctly
- Jobs dispatched via post-commit hook - assert they fire after the parent commits, not before

**What does NOT need a test:**

- Framework-provided behavior: NestJS routing resolution, Express path matching, default class-validator / Zod rule engines (test that you wired things correctly via endpoint tests, not that the framework works)
- Generated boilerplate: DTOs with no logic, getters returning a single property
- Trivial delegation: `service.get(id) -> repository.get(id)` with no logic

### Step 6 - Test Data and Fixtures

- Prefer factory utilities (custom `createOrderFactory`, `@faker-js/faker` for primitives, or `fishery` package) over hand-rolled object literals; configure factories per project convention
- For repository tests with Testcontainers, use factories to insert; isolate per-test data inside the test
- Class-validator DTOs: instantiate via `plainToInstance(Dto, {...})` - factories only for nested / repeated cases
- Avoid mutating shared test fixtures - use `beforeEach` to rebuild
- Test data must be minimal and focused - 100-row `Array.from` setups signal the test belongs at integration / load-test layer

### Step 7 - Prioritization (when coverage is low)

If line coverage (or your equivalent project signal) is below ~50%, **run this step before scaffolding** - it determines _which_ tests to scaffold first. Scaffolding alphabetically or by file is wrong when authorization holes go untested while plumbing endpoints get full coverage.

When starting from low test coverage, prioritize by Node-specific risk:

**Priority 1 - Authorization and authentication:**

- Endpoint test per protected endpoint asserting 401 anonymous + 403 wrong-role
- JWT flow tests covering issuer, audience, signature, expiry validation (NestJS Passport / Express `jose`)
- Custom guards / auth middleware unit-tested

**Priority 2 - Data integrity:**

- Repository / ORM integration tests for every non-trivial query
- Service tests for write operations (one happy path + one rollback per write)
- BullMQ job idempotency for any job with side effects

**Priority 3 - Business-critical flows:**

- Revenue paths (checkout, billing, subscription state transitions)
- State-machine transitions (TypeScript discriminated unions)
- Scheduled jobs touching billing or notifications

**Priority 4 - High-churn code:**

- Files with frequent recent commits (`git log --since="3 months ago"`)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pass-through endpoints, simple CRUD - lower risk, can wait

### Step 8 - Test Infrastructure Hygiene

- [ ] Testcontainers reused across tests via global setup / `globalSetup` config and `testcontainers.reuse=true` in `~/.testcontainers.properties` for local fast cycles
- [ ] Jest `testEnvironment: 'node'` (not `jsdom` for backend); `forceExit: false` (forces investigation of unclosed handles instead of masking them)
- [ ] Test profile only overrides what differs from prod - never silently disables `ValidationPipe` / auth guards
- [ ] Jest parallelism (`--maxWorkers`) tuned; per-test isolation for stateful tests (Testcontainers integration tests run with `--runInBand` or sharded)
- [ ] Strict TypeScript in tests: `tsconfig.test.json` extends `tsconfig.json` with `strict: true`; no `as any` shortcuts
- [ ] HTTP stubs via MSW (`msw/node` `setupServer`); never real network calls; `server.listen({ onUnhandledRequest: 'error' })` to fail loud on missed stubs
- [ ] **SDK clients that bypass MSW**: the Stripe SDK (`stripe-node`), AWS SDK v3 (`@aws-sdk/client-*`), `@google-cloud/*` clients, and similar use their own HTTP transport (often configurable per-client) that may or may not flow through Node's global `fetch` / `http` module that MSW intercepts. Confirm by running one stubbed test and asserting the MSW handler fires; if it does not, mock the SDK client directly via `jest.mock('@aws-sdk/client-s3')` or pass a stub `httpHandler` / `requestHandler` per the SDK's docs. Silent passthrough is how production credentials leak into test runs
- [ ] `--detectOpenHandles` reviewed; long-running fixtures flagged
- [ ] Coverage tool (Istanbul via Jest `--coverage`) wired to CI with per-package thresholds; coverage exclusions documented
- [ ] Bun-specific: if project uses `bun test`, mirror config in `bunfig.toml`; else stay on Jest. Don't mix runners in one project.

## Node Review Checklist

Quick-reference checklist for reviewing existing Node tests:

- [ ] Test type matches what is being tested (endpoint -> Supertest + TestingModule, repository -> Testcontainers, service -> unit + mocks)
- [ ] Every endpoint has at least happy + 401 + 403 + validation-error
- [ ] Every non-trivial repository query has an integration test against Testcontainers (not SQLite)
- [ ] Every guard / auth middleware has a passing-and-denied test
- [ ] Test data created via factories, not raw object literals
- [ ] No `repository.save = jest.fn()` mocks when an integration test could assert real DB state
- [ ] No full-stack E2E tests for what an endpoint test could cover
- [ ] No in-memory queue mock masking BullMQ at-least-once / `attempts` semantics on critical jobs
- [ ] No `as any` on mocked methods - use `DeepMocked<T>` or `jest.MockedFunction`

## Output Format

**Which output to produce:**

- User asks "what tests are missing?" or "review our test coverage" -> Coverage Assessment
- User asks "write tests for X" or "scaffold tests" -> Test Scaffolds
- User asks "test strategy", "test plan", or coverage is below 50% with no scaffolds requested -> Strategy Doc (optionally include Coverage Assessment)
- User asks for **two or more deliverables in the same invocation** ("review coverage AND scaffold tests", "what's missing and write the tests") -> produce them in this order, separated by a horizontal rule (`---`): Coverage Assessment, then Strategy Doc (if requested), then Test Scaffolds. Do not silently drop one.
- If unclear, produce Strategy Doc as the default.

**Coverage Assessment:**

```markdown
## Node.js Test Coverage Assessment

**Stack:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version>
**ORM:** Prisma <version> | TypeORM <version>
**Test framework:** Jest, Supertest, Testcontainers, MSW
**Coverage gaps:**

- **Unit tests:** [services / validators / mappers without test coverage]
- **Endpoint tests:** [endpoints without tests; endpoints missing 401/403/validation paths]
- **Integration tests:** [repositories with non-trivial queries without tests; tests running on SQLite for a Postgres app]
- **Auth tests:** [endpoints without authorization tests; missing JWT flow tests]
- **Job tests:** [BullMQ processors without tests; jobs without idempotency / retry tests]
- **Contract tests:** [OpenAPI / Pact contracts without verification]

**Recommended pyramid balance:**

- Unit (services, validators, helpers): [count target]
- Endpoint + integration (Supertest + Testcontainers): [count target]
- E2E (full stack with BullMQ / Redis): [count target - keep small]

**Prioritization** _(include when current coverage is below ~50% or the assessment surfaces > 5 gaps)_

Apply the Step 7 risk bands. Order follow-up work as:

1. **P1 - Authorization & authentication:** [list specific endpoints / flows missing 401/403/ownership tests]
2. **P2 - Data integrity:** [repositories with non-trivial queries / write paths without rollback tests / BullMQ jobs with unguarded side effects]
3. **P3 - Business-critical flows:** [revenue, state machines, scheduled jobs touching billing or notifications]
4. **P4 - High-churn code:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pass-through endpoints / simple CRUD - lowest risk]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run Jest test files using project conventions. Each scaffold must include:

- The right test type (endpoint / integration / unit / job)
- Factories for test data instead of raw object literals
- For endpoint tests: happy path + 401 + 403 + validation-error
- For repository tests: Testcontainers PostgreSQL; assertions against PostgreSQL semantics
- For auth tests: anonymous + wrong-role + correct-role cases
- For BullMQ tests: idempotency + retry + max-retries cases when applicable
- TypeScript strict: typed mocks via `DeepMocked<T>` / `jest.MockedFunction`, no `as any`

**Strategy Doc** (when designing a test strategy):

```markdown
## Node.js Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Endpoint + Integration {y}% / E2E {z}%
**Tooling:** Jest, Supertest, NestJS TestingModule (or Express app instance), Testcontainers PostgreSQL, MSW, BullMQ in-memory + real-broker integration
**Database isolation:** Testcontainers PostgreSQL + per-test rollback (Prisma `$transaction` + manual rollback throw, or schema reset)
**Concurrency:** [Jest --maxWorkers config; --runInBand for Testcontainers integration]
**Gaps to close (prioritized):**

1. [Highest risk gap - typically authorization or repository correctness]
2. [...]
```

## Self-Check

**Always (any deliverable):**

- [ ] Stack confirmed as Node.js / TypeScript; framework (NestJS / Express / mixed) and ORM (Prisma / TypeORM) recorded before any framework-specific guidance applied (Step 1)
- [ ] Code under test and a representative sample of existing tests + setup files read directly so output matches project conventions (Step 2)
- [ ] `node-testing-patterns` consulted for canonical Node test patterns
- [ ] Auth testing approach explicit (NestJS: `overrideGuard` returning stub user; Express: middleware mounted with fixture user)
- [ ] Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage from plan.md, no out-of-scope tests)

**Strategy Doc / Coverage Assessment only:**

- [ ] Test pyramid mapped to Node idioms (unit -> Jest + mocks; endpoint -> Supertest + TestingModule / app instance; integration -> Testcontainers; BullMQ -> in-memory mock + real-broker for non-trivial cases)
- [ ] Boundaries clearly defined: each layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization by risk applied when coverage is low - P1 authorization, P2 data integrity, P3 business-critical, P4 high-churn, P5 plumbing
- [ ] Testcontainers used for repository and full-context tests; SQLite flagged as a smell for production-Postgres apps

**Test Scaffolds only:**

- [ ] Test data created via factories, not raw object literals; typed factory return shapes
- [ ] Endpoint scaffolds include happy path + 401 + 403 + validation-error; IDOR test for any per-owner / per-tenant resource
- [ ] Endpoint scaffolds apply same global pipes / guards / middleware as `main.ts` / `app.ts` (missing `ValidationPipe` masks validation bugs)
- [ ] Repository scaffolds run against Testcontainers PostgreSQL with per-test cleanup - never SQLite for Postgres apps
- [ ] BullMQ scaffolds include idempotency + retry; real-broker (Testcontainers Redis) variant present for jobs with non-trivial `attempts` / `lockDuration`
- [ ] Typed mocks via `DeepMocked<T>` / `jest.MockedFunction` - no `as any`
- [ ] Schema unit tests scaffolded for any non-trivial DTO / Zod validator or `whitelist: true` / `.strict()` contract

**Review-existing-tests mode only:**

- [ ] Review checklist items addressed for every test file in scope

## Avoid

- Scaffolding tests without first reading existing tests + setup files - the result imports the wrong factory, uses the wrong HTTP-stub library, or duplicates the integration-test base fixture
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no auth tests misses the bigger threat
- Full E2E tests (full Testcontainers + real broker) for what an endpoint test could cover - context cost compounds across the suite
- SQLite / in-memory DB in repository tests for apps that use PostgreSQL features (JSONB, partial indexes, `ON CONFLICT`, array types) - tests pass, prod fails
- Endpoint tests that build the NestJS app without applying the same global pipes / guards as `main.ts` - validation rules and auth differ between test and prod silently
- Writing endpoint tests with `fetch(...)` against a real running server when Supertest is faster and more deterministic
- Duplicating factories per test class - share via `test/factories.ts` and / or test setup modules
- Using `repository.save = jest.fn()`-style internal mocks when a Testcontainers integration test could assert real DB state
- Mocking `ValidationPipe` to silence DTO failures - the test is now incorrect for the prod config
- Skipping schema unit tests because the endpoint has an integration test - validators are unit-tested separately so they can be reused
- Testing framework internals (e.g., that `@Body()` resolves, that Express routers route) - test your wiring, not the framework
- Using in-memory BullMQ mocks as a substitute for a real-broker test on jobs with non-trivial `attempts` / `lockDuration` - the mock skips the broker and masks at-least-once / stalled-job redelivery semantics
- Using `as any` to silence TypeScript errors in mocks - it defeats the point of strict mode; use `DeepMocked<T>` or proper typing
