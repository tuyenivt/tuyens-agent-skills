---
name: task-node-test
description: Node.js / NestJS / Express test plan and scaffolding with Jest, Supertest, TestingModule, Testcontainers, MSW, BullMQ testing.
agent: node-test-engineer
metadata:
  category: backend
  tags: [node, typescript, jest, nestjs, express, testcontainers, supertest, msw, testing, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Node.js Test

Stack-specific delegate of `task-code-test` for Node.js. Preserves the parent contract (output shape, prioritization). Canonical wiring (TestingModule, Supertest, Testcontainers, MSW, BullMQ mocks) lives in `node-testing-patterns` - this workflow composes, does not restate.

## When to Use

- New NestJS / Express service or module needs a test strategy
- Coverage gaps across unit / integration / endpoint / job layers
- Scaffolding tests for under-covered endpoints, repositories, or auth code
- Boundary tests (validation, authorization, edge cases) for existing happy-path tests

**Not for:** test failure debugging, code review (`task-node-review`), postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Node.js / TypeScript. If invoked from `task-code-test`, accept the parent's stack. If not Node, stop and direct to `/task-code-test`.

Detect: NestJS (`nest-cli.json` + `@nestjs/*`) vs Express. ORM: Prisma vs TypeORM. Record `Framework`, `ORM` for output - downstream steps branch on these.

### Step 2 - Read Code and Existing Tests

Ground output in real conventions. For each target, read the module top-to-bottom: public surface, DTOs, guards / middleware, transaction boundaries, external collaborators.

Glob `src/**/*.spec.ts`, `test/**/*.e2e-spec.ts`. Read at least one endpoint test, one service / repository test, one BullMQ test (if applicable), and shared setup (`test/setup.ts`, `jest.config.*`). Note: mock strategy (`jest.mock` vs `overrideProvider`), HTTP-stub library (MSW vs nock), auth helpers, factory utilities.

For NestJS: read `app.module.ts` / `main.ts` for global `ValidationPipe`, guards, interceptors that endpoint tests must replicate. For Express: read `app.ts` middleware order.

If no existing tests, say so and propose conventions explicitly in the strategy doc.

### Step 3 - Node.js Test Pyramid

| Layer       | Tooling                                          | Test here                                                   |
| ----------- | ------------------------------------------------ | ----------------------------------------------------------- |
| Unit        | Jest + `jest.fn()` / `DeepMocked<T>`             | Service logic, mappers, validators, custom `canActivate` / pipe `transform`, pure helpers |
| Integration | Jest + Testcontainers PostgreSQL + real ORM      | Non-trivial repository queries, ORM constraints (unique / check / FK), DB invariants, migration smoke |
| Endpoint    | Jest + Supertest + `TestingModule` / Express app | Every endpoint: routing, validation, guards / middleware, response shape, pagination / filtering, custom filters |
| Job         | Jest + BullMQ in-memory mock                     | Jobs with retry, idempotency, or external side effects; flows / chains; post-commit dispatch |
| E2E         | Jest + Testcontainers + real BullMQ / Redis      | Critical journeys only (auth, checkout, transactional flow) |
| Contract    | Pact / OpenAPI                                   | API contract vs schema                                      |

Many unit, some endpoint / integration, few E2E.

**Skip:** framework internals (NestJS routing, Express path matching, validator engines), DTOs with no logic, trivial delegation (`service.get -> repo.get`).

### Step 4 - Apply Node.js Test Patterns

Use skill: `node-testing-patterns` for wiring and code shapes. Per-type strategy rules:

- **Unit (`*.spec.ts`)**: one test per outcome (success / validation fail / external fail / edge). No app context or DB - if it needs `TestingModule`+DB, it is misclassified. MSW for HTTP; typed mocks, no `as any`.
- **Endpoint (`*.e2e-spec.ts`)**: one test per `(method, path, principal-state, outcome)` - happy + 401 + 403 + 4xx-validation; on owner- / tenant-scoped endpoints add an IDOR case (another principal's resource returns 404/403). App built with **same** global pipes / guards / middleware as `main.ts` / `app.ts`. Auth via `overrideGuard` (NestJS) or fixture middleware (Express).
- **Repository / ORM integration**: Testcontainers PostgreSQL only - never SQLite (JSONB, partial indexes, `ON CONFLICT`, arrays, `LATERAL` diverge). Per-test rollback. Assert SQL semantics and constraint errors (`P2002`, `QueryFailedError`).
- **DTO / Schema**: validate via `validate(plainToInstance(...))` or `Schema.safeParse(...)` - faster than full endpoint test. Cover unknown-key rejection (`whitelist:true` / `.strict()`), missing required, type mismatch.
- **BullMQ**: in-memory mock (`getQueueToken()` override) for happy path; real broker via Testcontainers Redis when behavior depends on `attempts` / `lockDuration` / stalled redelivery. Always cover: idempotency (invoke twice, side effect once), retry (fail-fail-success), DLQ (fail forever, no infinite loop). Post-commit dispatched jobs: assert they fire after parent commit, not before.
- **E2E**: full-stack flows only (auth end-to-end, transactional commit + BullMQ dispatch). Avoid for what endpoint tests cover.

### Step 5 - Test Data and Fixtures

Factories over object literals (custom `createOrderFactory`, `@faker-js/faker`, `fishery`). Rebuild in `beforeEach` - never mutate shared fixtures. Class-validator: `plainToInstance(Dto, {...})`. 100-row `Array.from` setups belong at integration / load-test layer, not unit.

### Step 6 - Prioritization (when coverage is low)

Run before scaffolding when coverage is below ~50% or more than 5 gaps surfaced. Alphabetic or by-file order leaves auth holes while plumbing gets full coverage.

1. **P1 - AuthN/Z**: 401 anonymous + 403 wrong-role per protected endpoint; JWT issuer / audience / signature / expiry; custom guards / middleware.
2. **P2 - Data integrity**: integration tests for non-trivial queries; write paths with rollback; BullMQ idempotency for side-effect jobs.
3. **P3 - Business-critical**: revenue paths, state-machine transitions, scheduled billing / notification jobs.
4. **P4 - High-churn**: files with frequent recent commits (`git log --since="3 months ago"`) or bug-fix history.
5. **P5 - Plumbing**: pass-through endpoints, simple CRUD.

### Step 7 - Test Infrastructure Hygiene

- [ ] Testcontainers reused via `globalSetup` + `testcontainers.reuse=true`
- [ ] Jest `testEnvironment: 'node'`; `forceExit: false` (forces investigation of unclosed handles)
- [ ] Test profile only overrides what differs from prod - never silently disables `ValidationPipe` / guards
- [ ] `--maxWorkers` tuned; Testcontainers integration runs `--runInBand` or sharded
- [ ] Strict TypeScript in tests (`tsconfig.test.json` extends `tsconfig.json`); no `as any`
- [ ] MSW (`msw/node` `setupServer({ onUnhandledRequest: 'error' })`); no real network
- [ ] **SDKs bypassing MSW** (Stripe, AWS SDK v3, `@google-cloud/*` use their own transport): verify one stubbed test triggers the MSW handler; if not, `jest.mock` the client or inject a stub `httpHandler`. Silent passthrough leaks prod credentials.
- [ ] `--detectOpenHandles` reviewed; coverage thresholds wired to CI
- [ ] If `bun test`, mirror config in `bunfig.toml`; do not mix runners

## Review Checklist (existing tests)

- [ ] Test type matches subject (endpoint -> Supertest, repository -> Testcontainers, service -> unit)
- [ ] Endpoint: happy + 401 + 403 + validation; guards / middleware have passing + denied tests
- [ ] Repository integration on Testcontainers PostgreSQL, not SQLite; no `repository.save = jest.fn()` where real DB could assert
- [ ] No E2E covering what an endpoint test could
- [ ] Critical jobs use real-broker tests when behavior depends on `attempts` / `lockDuration`
- [ ] Factories over literals; typed mocks (`DeepMocked<T>` / `jest.MockedFunction`), no `as any`

## Output Format

**Which deliverable:**

- "what tests are missing?" / "review coverage" -> Coverage Assessment
- "write tests for X" / "scaffold tests" -> Test Scaffolds
- "test strategy" / "test plan" / coverage < 50% with no scaffolds requested -> Strategy Doc
- Multiple deliverables in one invocation -> produce all, separated by `---`, in order: Coverage Assessment, Strategy Doc, Test Scaffolds
- Unclear -> Strategy Doc as default

**Coverage Assessment:**

```markdown
## Node.js Test Coverage Assessment

**Stack:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version>
**ORM:** Prisma <version> | TypeORM <version>
**Test framework:** Jest, Supertest, Testcontainers, MSW
**Coverage gaps:**

- **Unit:** [services / validators / mappers without coverage]
- **Endpoint:** [endpoints missing 401/403/validation paths]
- **Integration:** [non-trivial queries without tests; SQLite for a Postgres app]
- **Auth:** [endpoints without authorization tests; missing JWT flow tests]
- **Job:** [BullMQ processors without tests; jobs without idempotency / retry]
- **Contract:** [OpenAPI / Pact contracts without verification]

**Recommended pyramid balance:**

- Unit: [count target]
- Endpoint + integration: [count target]
- E2E: [count target - keep small]

**Prioritization** _(when coverage < ~50% or > 5 gaps)_

Apply Step 6 risk bands: P1 AuthN/Z, P2 data integrity, P3 business-critical, P4 high-churn, P5 plumbing.
```

**Test Scaffolds:** ready-to-run Jest files using project conventions. Each scaffold must include the right test type, factories (not literals), endpoint coverage = happy + 401 + 403 + validation, repository tests on Testcontainers PostgreSQL, BullMQ tests with idempotency + retry, typed mocks (no `as any`).

**Strategy Doc:**

```markdown
## Node.js Test Strategy

**Objective:** [what this achieves]
**Pyramid balance:** Unit {x}% / Endpoint + Integration {y}% / E2E {z}%
**Tooling:** Jest, Supertest, NestJS TestingModule (or Express app), Testcontainers PostgreSQL, MSW, BullMQ in-memory + real-broker for critical jobs
**Database isolation:** Testcontainers + per-test rollback (Prisma `$transaction` + throw, or schema reset)
**Concurrency:** [`--maxWorkers` config; `--runInBand` for Testcontainers integration]
**Gaps to close (prioritized):**

1. [Highest risk - usually authorization or repository correctness]
2. [...]
```

## Self-Check

- [ ] Stack confirmed; Framework + ORM recorded; existing tests + setup read (Steps 1-2)
- [ ] Pyramid mapped to Node idioms; risk prioritization applied when coverage < ~50% (Steps 3, 6)
- [ ] Scaffolds: factories over literals; endpoint = happy + 401 + 403 + validation + IDOR; same global pipes / guards as `main.ts` / `app.ts`; repository on Testcontainers PostgreSQL (never SQLite); BullMQ with idempotency + retry, real-broker for non-trivial `attempts` / `lockDuration`; typed mocks, no `as any`
- [ ] Review mode: every test file in scope passes the Review Checklist

## Avoid

- Scaffolding without first reading existing tests + setup - imports the wrong factory, duplicates the integration base fixture
- Chasing a coverage number instead of prioritizing by risk - 100% lines with no auth tests misses the bigger threat
- E2E for what an endpoint test could cover - context cost compounds
- SQLite / in-memory DB for Postgres-feature apps (JSONB, partial indexes, `ON CONFLICT`, arrays)
- Endpoint tests built without the same global pipes / guards as `main.ts` - validation and auth differ silently
- `fetch(...)` against a real server when Supertest is faster and deterministic
- Per-test-class factory duplication - share via `test/factories.ts`
- `repository.save = jest.fn()` internal mocks where Testcontainers could assert real DB state
- Mocking `ValidationPipe` to silence DTO failures
- Skipping schema unit tests because the endpoint has integration - validators are unit-tested for reuse
- Testing framework internals (`@Body()` resolves, Express routers route)
- In-memory BullMQ mocks substituted for real-broker tests on jobs with non-trivial `attempts` / `lockDuration` - masks at-least-once / stalled redelivery
- `as any` to silence mock typing - use `DeepMocked<T>` or proper types
