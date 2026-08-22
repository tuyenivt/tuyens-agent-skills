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

Stack-specific delegate of `task-code-test` for Node.js. Preserves the parent's deliverable slots (`Covered today`, `Contract testing`, pyramid percentages) and adds Node lanes. Canonical wiring (TestingModule, Supertest, Testcontainers, MSW, BullMQ mocks) lives in `node-testing-patterns` - this workflow composes, does not restate.

## When to Use

- New NestJS / Express service or module needs a test strategy
- Coverage gaps across unit / integration / endpoint / job layers
- Scaffolding tests for under-covered endpoints, repositories, or auth code
- Reviewing an existing suite that is slow, flaky, or gives false confidence
- Boundary tests (validation, authorization, edge cases) for existing happy-path tests

**Not for:** test failure debugging, code review (`task-node-review`).

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Detect Conventions

Use skill: `stack-detect` to confirm Node.js / TypeScript. If invoked from `task-code-test`, accept the parent's stack. If not Node, stop and direct to `/task-code-test`.

Record all three - later steps and every emitted filename branch on them:

- `Framework`: NestJS (`nest-cli.json` + `@nestjs/*`) vs Express
- `ORM`: Prisma (`prisma/schema.prisma`) vs TypeORM (`data-source.ts`)
- `Test conventions`: the runner config's own `testMatch` / `testRegex` / `roots`, plus the HTTP-stub library, deep-mock helper, and auth fixture already in use. Never assume `*.spec.ts` / `*.e2e-spec.ts`. A NestJS repo usually ships **two** configs - `jest` in `package.json` (`testRegex: ".*\\.spec\\.ts$"`, which does not match `.e2e-spec.ts`) and `test/jest-e2e.json` - so record which config runs which lane, and emit each file into one that will run it.

### Step 3 - Read Code and Existing Tests

Ground output in real conventions. For each target, read the module top-to-bottom: public surface, DTOs, guards / middleware, transaction boundaries, external collaborators.

Glob with Step 2's own patterns. Read at least one endpoint test, one service / repository test, one BullMQ test (if applicable), and shared setup (`test/setup.ts`, runner config, `globalSetup`). Note mock strategy (`jest.mock` vs `overrideProvider`), HTTP stubbing (MSW vs `nock`), auth helpers, factories.

For NestJS: read `app.module.ts` / `main.ts` for the global `ValidationPipe`, guards, interceptors endpoint tests must replicate, **and how each is registered** - `useGlobalPipes` in `main.ts` versus an `APP_PIPE` / `APP_GUARD` provider changes what a test must re-register or override.

For Express: read `app.ts` middleware order.

**Convention vs rule.** Follow project convention for naming, layout, and library choice - a `nock` codebase stays on `nock`, a `jest-mock-extended` codebase stays on `mockDeep`. Override convention only where it defeats a correctness rule below (SQLite standing in for PostgreSQL, a disabled `ValidationPipe`, shared mutable fixtures, real network, literals where a shared factory already exists), and record the override with its reason. Zero glob hits means a convention mismatch, not an empty suite - re-read the config before concluding there are no tests. If there genuinely are none, propose conventions explicitly.

### Step 4 - Node.js Test Pyramid

| Layer       | Tooling                                          | Test here                                                   |
| ----------- | ------------------------------------------------ | ----------------------------------------------------------- |
| Unit        | Jest + `jest.fn()` / project's deep-mock helper  | Service logic, mappers, validators, custom `canActivate` / pipe `transform`, pure helpers |
| Integration | Jest + Testcontainers PostgreSQL + real ORM      | Non-trivial repository queries, ORM constraints (unique / check / FK), DB invariants, migration smoke |
| Endpoint    | Jest + Supertest + `TestingModule` / Express app, **against Testcontainers PostgreSQL** | Every endpoint: routing, validation, guards / middleware, response shape, pagination / filtering, custom filters |
| Job         | Jest + BullMQ handler invoked directly           | Jobs with retry, idempotency, or external side effects; flows / chains; post-commit dispatch |
| E2E         | Jest + Testcontainers + real BullMQ / Redis      | Critical journeys only (auth, checkout, transactional flow) |
| Contract    | Pact / OpenAPI                                   | API contract vs schema                                      |

**Vocabulary.** `node-testing-patterns` files its Supertest-through-the-app material under the heading "E2E"; that material is this table's **Endpoint** layer and carries its real database. Reserve E2E here for flows that additionally cross a real broker. Classify an existing file by what it boots, never by its filename suffix.

Balance is measured across the service: many unit, some endpoint / integration, few E2E. A single controller-dense module where Step 5's matrix outnumbers its unit tests is expected - rebalance by adding unit coverage elsewhere, never by dropping mandated endpoint cases.

**Skip:** framework internals (NestJS routing, Express path matching, validator engines), DTOs with no logic, trivial delegation (`service.get -> repo.get`).

### Step 5 - Apply Node.js Test Patterns

Use skill: `node-testing-patterns` for wiring and code shapes. Also use skill: `node-prisma-patterns` or `node-typeorm-patterns` (per Step 2's `ORM`) for the query semantics under assertion, and `node-bullmq-patterns` when the target has a producer or processor.

- **Unit**: one test per outcome (success / validation fail / external fail / edge). No app context or DB - if it needs `TestingModule`+DB, it is misclassified. Typed mocks from whichever helper the project already uses (`DeepMocked<T>` from `@golevelup/ts-jest`, or `mockDeep` / `DeepMockProxy` from `jest-mock-extended`); never `as any`.
- **Endpoint**: one test per `(method, path, principal-state, outcome)`. Always the happy path. Add a 4xx-validation case **when the route validates input** (a DTO, a Zod schema, or a param pipe) - a bare `GET /:id` with no schema has no validation case, and inventing one is a finding, not coverage. Add 401 when the route is behind authn; add 403 when it carries a role or permission check; add an IDOR case (another principal's resource returns 404/403) when it is owner- or tenant-scoped. A route with no principal at all (webhook, health) substitutes its own gate - valid / invalid / replayed signature.

  Build the app with the **same** global pipes / guards / middleware as production, registered the way production registers them. Keep authn real and mint a valid token from the app's own signing key or `JwtService`; a guard overridden to always-allow makes the 401 case assert nothing. When an override is genuinely needed, override the token the guard is registered under - `overrideGuard(JwtAuthGuard)` replaces a class-token guard and does **not** touch one registered globally as `{ provide: APP_GUARD, useClass: JwtAuthGuard }`. Express: keep `requireAuth` mounted and inject the principal through the project's auth fixture.
- **Repository / ORM integration**: Testcontainers PostgreSQL only - never SQLite (JSONB, partial indexes, `ON CONFLICT`, arrays, `LATERAL` diverge). Provision with `prisma migrate deploy` (Prisma) or `dataSource.runMigrations()` (TypeORM; `synchronize: true` only when no migration carries hand-written SQL). Isolate on **both** axes, they compose rather than substitute: across workers, one schema per Jest worker (`JEST_WORKER_ID` in `search_path`) or one container per worker; within a worker, `TRUNCATE ... RESTART IDENTITY CASCADE` in `beforeEach`. Never per-test `BEGIN`/`ROLLBACK` - `PrismaClient` and a TypeORM `DataSource` both pool connections, so the rollback can land on a different connection than the writes. Assert SQL semantics and constraint errors (`P2002`; TypeORM `QueryFailedError.driverError.code === '23505'`).
- **DTO / Schema**: validate via `validate(plainToInstance(...))` or `Schema.safeParse(...)` - faster than a full endpoint test. Cover unknown-key rejection (`whitelist:true` / `.strict()`), missing required, type mismatch.
- **BullMQ**: two lanes, and the lane decides what is testable.
  - *Handler lane (default)*: register the `@Processor` class as a plain provider, or import the handler function, and call it with a mock `Job`. Never import `BullModule` here - that is what opens the Redis socket. Producer side: assert `queue.add(...)`, mocked via `getQueueToken(name)` override on NestJS or a stub `{ add: jest.fn() }` injected at the module boundary on Express, which has no DI token. This lane covers idempotency (invoke twice, side effect once) and handler-thrown classification (`UnrecoverableError` vs retryable).
  - *Broker lane (escalation)*: `attempts` / `backoff` exhaustion, `lockDuration` stall redelivery, and DLQ drain are broker machinery and cannot be observed in the handler lane. Test them against a real `Worker` on Testcontainers Redis, in their own file, with backoff delays overridden to CI-viable values (tens of milliseconds, not the production `delay`). Escalate only for these; everything else stays in the handler lane.
  - Post-commit dispatched jobs: assert they fire after parent commit, not before.
- **E2E**: full-stack flows only (auth end-to-end, transactional commit + BullMQ dispatch). Avoid for what endpoint tests cover.

### Step 6 - Test Data and Fixtures

Factories over object literals (custom `createOrderFactory`, `@faker-js/faker`, `fishery`), shared from a single module. Rebuild in `beforeEach` - never mutate a module-level fixture. Class-validator: `plainToInstance(Dto, {...})`. 100-row `Array.from` setups belong at integration / load-test layer, not unit.

### Step 7 - Prioritization

Apply whenever the deliverable ranks work, and always when coverage is below ~50% or more than 5 gaps surfaced.

**P0 - Blockers.** Infrastructure that makes the tests below unwritable or untrustworthy (no Testcontainers where Postgres semantics are asserted, `forceExit: true` masking open handles, a disabled `ValidationPipe`, real network). Nothing beneath P0 is worth writing first.

1. **P1 - AuthN/Z**: 401 anonymous + 403 wrong-role per protected endpoint; JWT issuer / audience / signature / expiry; custom guards / middleware; tenant scoping.
2. **P2 - Data integrity**: integration tests for non-trivial queries; write paths with rollback; BullMQ idempotency for side-effect jobs.
3. **P3 - Business-critical**: revenue paths, state-machine transitions, scheduled billing / notification jobs.
4. **P4 - High-churn**: files with frequent recent commits (`git log --since="3 months ago"`) or bug-fix history. No git history available: skip the band and say so rather than guessing.
5. **P5 - Plumbing**: pass-through endpoints, simple CRUD.

### Step 8 - Suite Health and Infrastructure Hygiene

Runs on every invocation that reads an existing suite. Each failing box is a finding; the Output Format's **Findings routing** rule says where it lands.

- [ ] Testcontainers started once in `globalSetup`, not per spec file. (Reuse is a local-dev accelerator only, off on CI: `.withReuse()` plus either `TESTCONTAINERS_REUSE_ENABLE=true` in the environment or `testcontainers.reuse.enable=true` in `~/.testcontainers.properties`. It also conflicts with a `globalTeardown` that stops the container.)
- [ ] Jest `testEnvironment: 'node'`; `forceExit: false` (forces investigation of unclosed handles)
- [ ] Test profile only overrides what differs from prod - never silently disables `ValidationPipe` / guards / auth middleware
- [ ] **Parallelism is a config decision, not a flag.** DB-backed tests isolated per worker so `--maxWorkers` still applies; where a lane must serialize (the BullMQ broker lane), give it its own Jest `project` with `maxWorkers: 1` rather than `--runInBand`, which serializes the entire run. For a suite dominated by app boots, count them - N full `AppModule` boots is usually the largest single term - and reduce by sharing a boot per file or by sharding across CI jobs.
- [ ] Strict TypeScript in tests (`tsconfig.test.json` extends `tsconfig.json`); no `as any`
- [ ] No real network: MSW `server.listen({ onUnhandledRequest: 'error' })` - the option belongs to `listen`, not `setupServer(...handlers)` - or `nock.disableNetConnect()` on a `nock` codebase
- [ ] **Stub coverage verified, not assumed.** MSW and `nock` intercept Node `http` / `https`; native `fetch` (undici) and `undici.request` need an interceptor that targets it - MSW covers native `fetch`, `nock` only from v14. gRPC SDKs (`@google-cloud/*`) and HTTP/2 clients are not intercepted at all, and AWS SDK v3 is stubbed idiomatically with `aws-sdk-client-mock` rather than at the socket. Verify one stubbed test actually reaches the handler; silent passthrough leaks prod credentials.
- [ ] `--detectOpenHandles` reviewed; coverage thresholds wired to CI
- [ ] If `bun test`, mirror config in `bunfig.toml`; do not mix runners

### Step 9 - Review Existing Tests

Skip when no suite exists. Otherwise judge every in-scope test file against Steps 4-8. Above ~50 files, sample: every file touching auth, money, or a migration, plus the three largest files per layer. State the sample and its size in the deliverable.

Review-only checks, not covered above:

- [ ] Test type matches subject (endpoint -> Supertest, repository -> Testcontainers, service -> unit); no `repository.save = jest.fn()` where a real DB could assert
- [ ] Layer classified by what the file boots, so no E2E remains that an endpoint test could cover
- [ ] Assertions can actually fail: no mocked-away subject, no `expect(mock).toHaveBeenCalled()` standing in for an outcome

## Output Format

**Which deliverable.** Each row is independent: produce every deliverable whose trigger the ask matches, once each, separated by `---`, in table order. An ask matching no row produces the Strategy Doc. A coverage percentage never selects a deliverable - it only gates Step 7.

| The ask                                                             | Deliverable         |
| ------------------------------------------------------------------- | ------------------- |
| "what tests are missing", "coverage gaps", "review coverage"        | Coverage Assessment |
| "review our tests", "audit the suite", "the suite is slow / flaky"  | Suite Review        |
| "test strategy", "test plan"                                        | Strategy Doc        |
| "write tests for X", "scaffold tests", "add tests"                  | Test Scaffolds      |

**Findings routing.** Every Step 8 and Step 9 finding lands in the Suite Review. If the ask selected no Suite Review and either step produced a finding, emit one anyway as an additional deliverable. The `Infrastructure` slots in the other three carry prerequisites for work not yet done, never findings about work already done.

**Envelope precedence.** The atomics loaded in Step 5 emit their own blocks (`## Test Plan`, `## Prisma Schema Design`, `## BullMQ Design`). Fold their content into the slots below; do not emit those blocks as separate sections.

**Coverage Assessment:**

```markdown
## Node.js Test Coverage Assessment

**Stack:** Node.js <version> / TypeScript <version>

**Framework:** NestJS <version> | Express <version>

**ORM:** Prisma <version> | TypeORM <version>

**Test tooling detected:** <runner, HTTP stub, deep-mock helper, container lib - name each absent one as absent>

**Covered today:** [1-2 lines - what the existing tests actually assert]

**Coverage gaps:**

- **Unit:** [services / validators / mappers without coverage]
- **Endpoint:** [endpoints missing 401 / 403 / IDOR / validation paths]
- **Integration:** [non-trivial queries without tests; SQLite for a Postgres app]
- **Auth:** [endpoints without authorization tests; missing JWT flow tests]
- **Job:** [BullMQ processors without tests; jobs without idempotency / retry]
- **Contract:** [contracts without verification, or `not required - <reason>`]

**Infrastructure prerequisites:** [what must exist before the gaps above can be closed - Testcontainers, factories module; or "none"]

**Priority order:** [Step 7 bands applied to the gaps above, P0 first]
```

**Suite Review:**

```markdown
## Node.js Suite Review

- **Files in scope:** <n reviewed> of <n total> (<sampling rule, or "all">)
- **Suite runtime:** <current> -> <target, with the lever and arithmetic that produce it; or "no target set">
- **Verdict:** Sound | Unsound - <n> Must / <n> Recommend

### [Must] <locator>

- Issue: [the rule broken, in Node terms]
- Effect: [what it costs: false confidence, flake, runtime]
- Fix: [concrete change]

### [Recommend] <locator>

[same three fields]
```

`<locator>` is `file:line` for a single-file finding, the config key for a config finding (`jest.config.js -> forceExit`), or a glob plus a count for a class-wide one (`**/*.e2e-spec.ts` (210 files)).

Every finding carries exactly one label: `[Must]` when the test gives false confidence or cannot fail (disabled `ValidationPipe`, SQLite standing in for PostgreSQL, mocked-away subject, real network, shared mutable fixture), `[Recommend]` otherwise. `[Must]` first. No other label is written.

**Strategy Doc:**

```markdown
## Node.js Test Strategy

**Objective:** [what this achieves]

**Pyramid balance (target):** Unit {x}% / Endpoint + Integration {y}% / E2E {z}% - default 70/20/10 unless the risk profile justifies otherwise, and say why. Job and Contract tests count in the middle bucket.

**Tooling:** [runner, Supertest, TestingModule or Express app, Testcontainers PostgreSQL, the project's HTTP stub, BullMQ handler lane plus a broker lane where Step 5 requires one]

**Database isolation:** Testcontainers + per-worker schema + `TRUNCATE` in `beforeEach`

**Contract testing:** required / not required - required when the API is consumed by an independently deployed team, when a message schema has separate producer and consumer deploys, or when a shared client library imports it; a third-party client the team merely calls needs stubs, not a contract suite

**Suite runtime:** <current> -> <target, with the lever> _(omit when no suite exists)_

**Flake sources:** [ordering dependence, shared rows, unclosed handles; or "none observed"]

**Gaps to close (prioritized):**

1. [P0 blockers first, then Step 7 bands]
2. [...]
```

**Test Scaffolds:**

```markdown
## Node.js Test Scaffolds

| File | Layer | Cases | Priority |
| ---- | ----- | ----- | -------- |
| <path, in the project's own naming convention, under a config that runs it> | unit / endpoint / integration / job / e2e | <n> | P0-P5 |

<the files, as fenced TypeScript blocks>

**New dev dependencies:** [name@version, or "none"]

**Infrastructure prerequisites:** [globalSetup, factories module, a serialized Jest project for the broker lane, runner config edits; or "none"]

**Assumptions:** [what was inferred - auth fixture shape, seed data, error codes, status codes not verifiable from Steps 2-3]
```

Scaffolds use the project's naming and helpers from Step 2, factories over literals, typed mocks. Layer mandates apply to the layers the request actually covers: endpoint files carry Step 5's case matrix, repository files run on Testcontainers PostgreSQL, job files cover idempotency in the handler lane.

## Self-Check

Mark a line N/A when the selected deliverable does not reach it (a Coverage Assessment emits no scaffolds; a greenfield run has no suite to review).

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed; Framework, ORM, and the project's own runner config, stub library, mock helper, and auth fixture recorded
- [ ] Step 3: target module and existing tests read via the project's globs; global-provider registration style noted; convention overrides recorded with reasons
- [ ] Steps 4-5: layers mapped to Node idioms; `node-testing-patterns` plus the matching ORM and BullMQ atomics consulted; endpoint matrix applied with its predicates, authn kept real, Testcontainers isolation on both axes, BullMQ handler lane vs broker escalation respected
- [ ] Step 6: factories shared, rebuilt per test
- [ ] Step 7: bands applied whenever work is ranked, P0 first; unavailable bands stated, not guessed
- [ ] Step 8: hygiene boxes run against the existing suite
- [ ] Step 9: existing tests judged; sample and its size stated above ~50 files
- [ ] Findings routing honored - Step 8/9 findings reached a Suite Review, emitted as an extra deliverable if the ask did not select one
- [ ] Deliverable(s) selected by the Output Format table and every slot filled with project-specific content

## Avoid

- Scaffolding without first reading existing tests + setup - imports the wrong factory, duplicates the integration base fixture
- Emitting a filename into a runner config that will not match it
- Chasing a coverage number instead of prioritizing by risk - 100% lines with no auth tests misses the bigger threat
- SQLite / in-memory DB for Postgres-feature apps (JSONB, partial indexes, `ON CONFLICT`, arrays)
- Endpoint tests whose app differs from production's pipes, guards, or middleware registration
- Mocking `ValidationPipe`, overriding `APP_PIPE`, or stubbing a guard to always-allow - the 401 and validation cases then assert nothing
- `repository.save = jest.fn()` internal mocks where Testcontainers could assert real DB state
- Importing `BullModule` in the handler lane, or reaching for the broker lane when the assertion is about handler logic
- Inventing a validation case for a route that validates nothing
- E2E for what an endpoint test could cover; `fetch(...)` against a real server where Supertest is deterministic
- Testing framework internals (`@Body()` resolves, Express routers route)
- `as any` to silence mock typing - use the project's typed-mock helper
