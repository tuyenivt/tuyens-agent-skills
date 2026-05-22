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
>
> **Spec-aware mode:** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble`. Generate one test per acceptance criterion (tag `// Satisfies: AC<N>`), cover every NFR per `plan.md`, refuse out-of-scope tests. Never edit spec artifacts; surface gaps as proposed amendments.

# Node.js Test

Stack-specific delegate of `task-code-test` for Node.js. Preserves the parent contract (output shape, prioritization). Canonical wiring (TestingModule, Supertest, Testcontainers, MSW, BullMQ mocks) lives in `node-testing-patterns` - this workflow composes, does not restate.

## When to Use

- New NestJS / Express service or module needs a test strategy
- Coverage gaps across unit / integration / endpoint / job layers
- Scaffolding tests for under-covered endpoints, repositories, or auth code
- Boundary tests (validation, authorization, edge cases) for existing happy-path tests

**Not for:** test failure debugging (`task-node-debug`), code review (`task-node-review`), postmortems (`/task-oncall-postmortem`).

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

| Layer       | Tooling                                          | Belongs here                                                |
| ----------- | ------------------------------------------------ | ----------------------------------------------------------- |
| Unit        | Jest + `jest.fn()` / `DeepMocked<T>`             | Service logic, validators, mappers, pure functions          |
| Integration | Jest + Testcontainers PostgreSQL + real ORM      | Repository queries, ORM constraints, DB invariants          |
| Endpoint    | Jest + Supertest + `TestingModule` / Express app | Routing, validation, guards / middleware, response shape    |
| Job         | Jest + BullMQ in-memory mock                     | Processor happy path, retry, idempotency                    |
| E2E         | Jest + Testcontainers + real BullMQ / Redis      | Critical journeys only (auth, checkout, transactional flow) |
| Contract    | Pact / OpenAPI                                   | API contract vs schema                                      |

Many unit, some endpoint / integration, few E2E.

### Step 4 - Apply Node.js Test Patterns

Use skill: `node-testing-patterns` for wiring and code shapes. Per-type strategy rules:

- **Unit (`*.spec.ts`)**: one test per outcome (success / validation fail / external fail / edge). No app context or DB - if it needs `TestingModule`+DB, it is misclassified. MSW for HTTP; typed mocks, no `as any`.
- **Endpoint (`*.e2e-spec.ts`)**: one test per `(method, path, principal-state, outcome)` - happy + 401 + 403 + 4xx-validation. App built with **same** global pipes / guards / middleware as `main.ts` / `app.ts`. Auth via `overrideGuard` (NestJS) or fixture middleware (Express).
- **Repository / ORM integration**: Testcontainers PostgreSQL only - never SQLite (JSONB, partial indexes, `ON CONFLICT`, arrays, `LATERAL` diverge). Per-test rollback. Assert SQL semantics and constraint errors (`P2002`, `QueryFailedError`).
- **DTO / Schema**: validate via `validate(plainToInstance(...))` or `Schema.safeParse(...)` - faster than full endpoint test. Cover unknown-key rejection (`whitelist:true` / `.strict()`), missing required, type mismatch.
- **BullMQ**: in-memory mock (`getQueueToken()` override) for happy path; real broker via Testcontainers Redis when behavior depends on `attempts` / `lockDuration` / stalled redelivery. Always cover: idempotency (invoke twice, side effect once), retry (fail-fail-success), DLQ (fail forever, no infinite loop). Post-commit dispatched jobs: assert they fire after parent commit, not before.
- **E2E**: full-stack flows only (auth end-to-end, transactional commit + BullMQ dispatch). Avoid for what endpoint tests cover.

### Step 5 - Test Boundaries

| Layer       | Test it                                                                              |
| ----------- | ------------------------------------------------------------------------------------ |
| Unit        | Service logic, mappers, validators, custom `canActivate` / pipe `transform`, helpers |
| Endpoint    | Every endpoint: happy + 401 + 403 + 4xx; pagination / filtering; custom filters      |
| Integration | Non-trivial repository queries, ORM constraints (unique / check / FK), migration smoke |
| Job         | Jobs with retry, idempotency, or external side effects; flows / chains; post-commit dispatch |

**Skip:** framework internals (NestJS routing, Express path matching, validator engines), DTOs with no logic, trivial delegation (`service.get -> repo.get`).

### Step 6 - Test Data and Fixtures

Factories over object literals (custom `createOrderFactory`, `@faker-js/faker`, `fishery`). Rebuild in `beforeEach` - never mutate shared fixtures. Class-validator: `plainToInstance(Dto, {...})`. 100-row `Array.from` setups belong at integration / load-test layer, not unit.

### Step 7 - Prioritization (when coverage is low)

Run before scaffolding when coverage is below ~50%. Alphabetic or by-file order leaves auth holes while plumbing gets full coverage.

1. **P1 - AuthN/Z**: 401 anonymous + 403 wrong-role per protected endpoint; JWT issuer / audience / signature / expiry; custom guards / middleware.
2. **P2 - Data integrity**: integration tests for non-trivial queries; write paths with rollback; BullMQ idempotency for side-effect jobs.
3. **P3 - Business-critical**: revenue paths, state-machine transitions, scheduled billing / notification jobs.
4. **P4 - High-churn**: files with frequent recent commits (`git log --since="3 months ago"`) or bug-fix history.
5. **P5 - Plumbing**: pass-through endpoints, simple CRUD.

### Step 8 - Test Infrastructure Hygiene

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
- [ ] Every endpoint: happy + 401 + 403 + validation
- [ ] Non-trivial repository queries integration-tested against Testcontainers, not SQLite
- [ ] Every guard / auth middleware has passing-and-denied tests
- [ ] Test data via factories, not literals
- [ ] No internal `repository.save = jest.fn()` mocks where integration could assert real DB state
- [ ] No E2E covering what an endpoint test could
- [ ] No in-memory queue mock masking `attempts` / `lockDuration` semantics on critical jobs
- [ ] No `as any` - use `DeepMocked<T>` or `jest.MockedFunction`

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

Apply Step 7 risk bands: P1 AuthN/Z, P2 data integrity, P3 business-critical, P4 high-churn, P5 plumbing.
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

**Always:**

- [ ] Stack confirmed Node.js / TypeScript; Framework + ORM recorded (Step 1)
- [ ] Code under test + sample existing tests + setup read directly (Step 2)
- [ ] `node-testing-patterns` consulted for canonical wiring (Step 4)
- [ ] Auth approach explicit (NestJS `overrideGuard` stub user; Express fixture middleware)
- [ ] Spec-aware mode honored when `--spec` passed (one test per AC, NFR coverage, no out-of-scope)

**Strategy Doc / Coverage Assessment:**

- [ ] Pyramid mapped to Node idioms (Step 3) - no duplicated assertions across layers
- [ ] Risk prioritization applied when coverage is low (Step 7)
- [ ] Testcontainers required for repository tests; SQLite flagged on Postgres apps

**Test Scaffolds:**

- [ ] Factories over object literals; typed factory return shapes (Step 6)
- [ ] Endpoint scaffolds: happy + 401 + 403 + validation; IDOR for per-owner / per-tenant resources
- [ ] Endpoint scaffolds apply same global pipes / guards / middleware as `main.ts` / `app.ts`
- [ ] Repository scaffolds on Testcontainers PostgreSQL with per-test cleanup - never SQLite
- [ ] BullMQ scaffolds include idempotency + retry; real-broker variant for non-trivial `attempts` / `lockDuration`
- [ ] Typed mocks (`DeepMocked<T>` / `jest.MockedFunction`); no `as any`
- [ ] Schema unit tests for non-trivial DTOs / Zod / `whitelist:true` / `.strict()` contracts

**Review-existing-tests mode:**

- [ ] Review Checklist items addressed for every test file in scope

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
