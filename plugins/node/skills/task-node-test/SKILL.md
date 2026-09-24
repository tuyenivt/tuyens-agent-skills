---
name: task-node-test
description: Plan, scaffold, and review Node.js / NestJS / Express tests - coverage gaps, flaky suites, Jest / Vitest, Supertest, Testcontainers, MSW, BullMQ.
agent: node-test-engineer
metadata:
  category: backend
  tags: [node, typescript, jest, nestjs, express, testcontainers, supertest, msw, testing, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Node.js Test

Node.js test strategy, coverage assessment, suite review, and scaffolding. Canonical wiring - TestingModule, Supertest, database isolation, MSW, BullMQ lanes - lives in `node-testing-patterns`; this workflow composes it, selects the deliverable, and decides what to test first.

## When to Use

- A new NestJS / Express service or module needs a test strategy
- Coverage gaps across unit / integration / endpoint / job layers
- Scaffolding tests for under-covered endpoints, repositories, jobs, or clients
- Reviewing a suite that is slow, flaky, or gives false confidence ("CI is green but production breaks")

**Not for:** debugging one failing test, code review (`task-node-review`).

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Detect Conventions

Use skill: `stack-detect`; accept a pre-confirmed stack. A backend Node framework (NestJS, Express, or another Node server) in `Framework`, or in an `Additional` entry for the targeted package, proceeds; `unknown` proceeds on the target's own `package.json`; anything else stops and names the detected stack.

Record - later steps and every emitted filename branch on them:

- `Framework`, `ORM` (Prisma, TypeORM, or other / none - the project's own migrate command, no ORM atomic), `Database` (the Testcontainers module and engine semantics follow it), `Test framework` (Jest - the default for `unknown` - or Vitest; any other runner is named and its config read in Step 3), and `Build tool` (the runner command). Every runner- or engine-specific recipe below names its Jest / PostgreSQL form first and its Vitest / MySQL form after it.
- **Test conventions:** the runner config's own `testMatch` / `testRegex` / `roots`, plus the HTTP-stub library, deep-mock helper, and auth fixture already in use. Never assume `*.spec.ts` / `*.e2e-spec.ts`. A NestJS repo usually ships two configs - `jest` in `package.json` (`testRegex: ".*\\.spec\\.ts$"`, which does not match `.e2e-spec.ts`) and `test/jest-e2e.json` - so record which config runs which lane, and emit each file into one that runs it

### Step 3 - Read Code and Existing Tests

For each target, read the module top to bottom: public surface, DTOs, guards / middleware, transaction boundaries, external collaborators.

Glob with Step 2's own patterns. Read at least one endpoint test, one service or repository test, one BullMQ test (when the project has queues), and the shared setup (`test/setup.ts`, runner config, `globalSetup`). Note the mock strategy (`jest.mock` vs `overrideProvider`), HTTP stubbing (MSW vs `nock`), auth helpers, and factories.

NestJS: read `main.ts` and `app.module.ts` for everything production registers - pipes, prefix, versioning, filters, interceptors, guards - and **how** each is registered (`main.ts` vs an `APP_PIPE` / `APP_GUARD` provider). `createNestApplication()` never runs `main.ts`, so endpoint tests share one `configureApp(app)` with it (`node-testing-patterns`). Express: read `app.ts` middleware order.

**Convention vs rule.** Follow project convention for naming, layout, and library choice - a `nock` codebase stays on `nock`, a `jest-mock-extended` codebase stays on `mockDeep`. Override convention only where it defeats a correctness rule (SQLite standing in for the production engine, a disabled `ValidationPipe`, shared mutable fixtures, real network, literals where a shared factory exists), and record the override with its reason. Zero glob hits is a convention mismatch until the config is re-read; with genuinely no tests, propose conventions explicitly.

### Step 4 - Test Pyramid

| Layer | Tooling | Test here |
| ----- | ------- | --------- |
| Unit | The detected runner + `jest.fn()` / `vi.fn()` / the project's deep-mock helper | Service logic, mappers, validators, custom `canActivate` / pipe `transform`, pure helpers |
| Integration | The runner + a real database of the detected engine + the real ORM | Non-trivial queries, constraints (unique / check / FK), invariants, migration smoke, enqueue-after-commit (a real transaction with a mocked `queue.add`) |
| Endpoint | The runner + Supertest + the app built as production builds it, against the real database | Every endpoint: routing, validation, guards / middleware, response shape, pagination, filters |
| Job | Handler lane: the processor invoked directly with a mock `Job`; broker lane: a real `Worker` on Testcontainers Redis | Handler: idempotency, error classification. Broker: retry / backoff exhaustion, stall redelivery, flow parent / child failure |
| E2E | Endpoint tooling + a real broker | Critical journeys crossing HTTP and a queue (auth, checkout, a transactional flow) |
| Contract | Pact / OpenAPI | API contract vs schema |

`node-testing-patterns` files its Supertest-through-the-app material under "E2E"; that is this table's **Endpoint** layer. Classify an existing file by what it boots, never by its filename suffix.

Balance is judged across the service; a controller-dense module is expected to be endpoint-heavy. Never add tests to hit a ratio. **Skip:** framework internals (routing, path matching, validator engines), DTOs with no logic, trivial delegation.

### Step 5 - Apply Node Test Patterns

Use skill: `node-testing-patterns` for wiring and code shapes. Also Use skill: `node-prisma-patterns` or `node-typeorm-patterns` (per `ORM`) for the query semantics under assertion, `node-bullmq-patterns` when the target has a producer or processor (a job run from `setInterval` or a cron still gets the Job layer's idempotency cases), and `node-http-client-patterns`' MSW section for outbound-HTTP stubbing (the rest of that atomic, and `ops-resiliency` behind it, is not needed here). These atomics are consulted for semantics; their blocks are not emitted.

- **Unit:** one test per outcome (success, validation failure, external failure, edge). No `INestApplication`, HTTP server, or database - a TestingModule with mocked providers is unit; a test that needs more is misclassified. TypeScript: typed mocks from the project's helper (`DeepMocked<T>`, `mockDeep` / `DeepMockProxy`), never `as any`.
- **Endpoint:** one test per `(method, path, principal-state, outcome)`. Always the happy path. A 4xx validation case **when the route validates input** (a DTO, a Zod schema, a param pipe) - a bare `GET /:id` with no schema has none, and inventing one is a finding. 401 when the route is behind authentication; 403 when it carries a role or permission check; an IDOR case (another principal's resource returns 404 / 403) when it is owner- or tenant-scoped. A webhook substitutes its own gate - valid, invalid, missing, and replayed signature; an ungated route (health) gets its happy path only.

  Build the app through the shared `configureApp(app)`. Authentication is either real (a token minted from the app's own signing key or `JwtService`) or a stub that still rejects an anonymous request - never an always-allow guard. A global guard is overridable only when registered `{ provide: APP_GUARD, useExisting: JwtAuthGuard }` with `JwtAuthGuard` also a provider, then `.overrideProvider(JwtAuthGuard)`; `overrideGuard(JwtAuthGuard)` never reaches an `APP_GUARD` registered with `useClass`. Express: keep `requireAuth` mounted and inject the principal through the project's auth fixture.
- **Integration:** a real database of the detected engine - Testcontainers, or a shared test instance with a run-scoped schema prefix where CI has no Docker - never SQLite for a PostgreSQL or MySQL app. One schema per worker - PostgreSQL: Prisma 5-6 `?schema=` on the test URL with `connection_limit` set; Prisma 7 the same per-worker URL for `migrate deploy` plus the adapter's `schema` and pool `max` for the client; TypeORM the `schema` option plus the worker's `search_path` on the connection (`extra: { options: '-c search_path=<schema>' }`) so raw SQL in migrations lands there too. MySQL: a per-worker database in the URL. Migrate each with the project's own command (`prisma migrate deploy`, `dataSource.runMigrations()`; never `synchronize` in a suite that claims migration coverage), and clear rows in `beforeEach` - PostgreSQL `TRUNCATE ... RESTART IDENTITY CASCADE`, MySQL `SET FOREIGN_KEY_CHECKS=0` then `TRUNCATE` - never the migrations table. Never per-test `BEGIN` / `ROLLBACK` through a pooled client - the rollback can land on another connection. Assert SQL semantics and constraint errors (`P2002`; TypeORM `QueryFailedError.driverError.code` `23505` on PostgreSQL, `ER_DUP_ENTRY` on MySQL).
- **DTO / schema:** `validate(plainToInstance(Dto, input, pipeOpts.transformOptions), pipeOpts)` with the global `ValidationPipe`'s own options (a bare `validate()` runs none), or `Schema.safeParse(...)`. Cover unknown-key rejection (`forbidNonWhitelisted: true`, which needs `whitelist: true`; `whitelist` alone strips silently; Zod `.strict()` / `z.strictObject`), missing required, and type mismatch.
- **BullMQ:** the handler lane is the default - register the processor as a plain provider (or import the handler) and call it with a mock `Job`; never import `BullModule` there, which opens the Redis socket. Producer side: assert `queue.add(...)` via a `getQueueToken(name)` override (NestJS) or an injected `{ add: jest.fn() }` (Express); enqueue-after-commit belongs to the integration lane. The broker lane is for broker machinery only, in its own file, on Testcontainers Redis, with backoff `delay` - and for stall tests `lockDuration` / `stalledInterval` - overridden to CI-viable values.
- **E2E:** full-stack flows only; nothing an endpoint test covers.

### Step 6 - Test Data and Fixtures

Factories over object literals (a shared factory module, `@faker-js/faker`, `fishery`), rebuilt in `beforeEach` - never a mutated module-level fixture. 100-row setups belong to the integration or load layer, not unit.

### Step 7 - Prioritization

Applies to every deliverable that ranks work (Coverage Assessment, Strategy Doc, Test Scaffolds).

- **P0 - Blockers:** infrastructure that makes the tests below unwritable or untrustworthy - no real database where engine semantics are asserted, `forceExit: true` masking open handles, a disabled `ValidationPipe`, real network. A P0 item that is already a Step 8 / Step 9 finding is listed by its Suite Review locator only
- **P1 - AuthN / AuthZ:** Step 5's auth cases per protected endpoint (401, 403 where a role check exists, IDOR where scoped); JWT issuer / audience / signature / expiry; custom guards and middleware; tenant scoping
- **P2 - Data integrity:** non-trivial queries; write paths with rollback; idempotency of side-effect jobs
- **P3 - Business-critical:** revenue paths, state-machine transitions, scheduled billing or notification jobs
- **P4 - High-churn:** in-scope files with frequent recent commits (`git log --since="3 months ago" -- <scope paths>`) or bug-fix history; a history too short to rank (a single import commit) skips the band and says so
- **P5 - Plumbing:** pass-through endpoints, simple CRUD

### Step 8 - Suite Health

Runs whenever an existing suite is read; on a Test Scaffolds-only ask, only over the files the scaffolds touch. Each failing box is a finding, routed per the Output Format.

- [ ] Containers started once in `globalSetup`, not per spec file. Testcontainers for Node reuses a `.withReuse()` container by default; CI either omits `.withReuse()` or sets `TESTCONTAINERS_REUSE_ENABLE=false`, and reuse conflicts with a `globalTeardown` that stops the container
- [ ] Jest: `testEnvironment: 'node'`, `forceExit` unset (it hides unclosed handles), `--detectOpenHandles` reviewed; Vitest: `environment: 'node'`, no `teardownTimeout` masking hung handles
- [ ] `clearMocks: true`; `restoreMocks` only where implementations are set per test (Jest 29 resets `jest.fn()` implementations; Jest 30 restores `spyOn` mocks only)
- [ ] The test setup overrides only what differs from production - never a silently disabled `ValidationPipe`, guard, or auth middleware
- [ ] **Parallelism by isolation, not by flags** - database tests isolated per worker so the worker count applies, each worker's pool capped (`connection_limit`, or the adapter / DataSource pool `max`) so workers x pool fits `max_connections`. `maxWorkers` is global in Jest: a lane that must serialize (the broker lane) either isolates per worker (queue `prefix` suffixed with the runner's worker id, `JEST_WORKER_ID` / `VITEST_POOL_ID`) or runs as its own invocation - Jest 28+: the project carries `displayName: 'broker'`, the main script runs `jest --ignoreProjects broker`, the broker script `jest --selectProjects broker --runInBand`; Vitest: `--project broker --no-file-parallelism`. For a suite dominated by app boots, count them and share a boot per file or shard CI jobs
- [ ] Strict TypeScript in tests (a test tsconfig extending the main one), type-checked in CI (`tsc --noEmit -p <test tsconfig>` or `vitest typecheck`) when the transformer strips types (`@swc/jest`, ts-jest `isolatedModules`, Vitest); no `as any`
- [ ] No real network, loopback allowed for Supertest: MSW `server.listen({ onUnhandledRequest })` with a callback that bypasses `127.0.0.1` / `localhost` and errors otherwise, or `nock.disableNetConnect()` plus `nock.enableNetConnect(/^(127\.0\.0\.1|localhost)/)` on a `nock` codebase
- [ ] **Stub coverage verified, not assumed** - MSW and `nock` intercept Node `http` / `https`; native `fetch` needs MSW or `nock` 14+; a direct `undici.request` needs undici's `MockAgent` via `setGlobalDispatcher`; gRPC-transport SDKs (most `@google-cloud/*` via google-gax) are not intercepted at the socket; AWS SDK v3 goes over `https` and is intercepted, with `aws-sdk-client-mock` the command-level alternative where the project uses it. One stubbed test is verified to reach its handler
- [ ] Coverage thresholds wired to CI
- [ ] Runs through the package-manager script (`bun run test` on Bun); plain `bun test` runs Bun's own runner, where TestingModule and `jest-mock-extended` setups break

### Step 9 - Review Existing Tests

Skip when no suite exists. Otherwise judge every in-scope test file against Steps 4-8 - the whole suite, or on a Test Scaffolds-only ask the files covering the requested targets; above ~50 files, sample every file touching auth, money, or a migration plus the three largest per layer, and state the sample and its size.

- [ ] Test type matches subject (endpoint -> Supertest, repository -> real database, service -> unit); no `repository.save = jest.fn()` where a real database could assert
- [ ] Layer classified by what the file boots
- [ ] Assertions can fail: no mocked-away subject, no `toHaveBeenCalled()` standing in for an outcome, no request to a route the app does not expose (a missing global prefix in the test app)
- [ ] A production module on a critical path with no test file at all is a finding, located at the production file - except a target this run scaffolds, whose scaffold is the remedy
- [ ] Tests for code with a known defect assert the correct behavior (a route that hangs is asserted against its correct status, under a test timeout), and the defect is reported - never a test that pins the bug

When the ask reports a symptom ("production breaks on order creation"), trace each symptom to the tests that should have caught it and the production cause.

## Output Format

**Which deliverable.** Each row is independent: produce every deliverable whose trigger the ask matches, once each, separated by `---`, in table order. A reported production symptom the suite missed ("CI is green but production breaks") matches both Coverage Assessment and Suite Review. An ask matching no row produces the Strategy Doc. A coverage percentage never selects a deliverable.

| The ask | Deliverable |
| ------- | ----------- |
| "what tests are missing", "coverage gaps", "review coverage", a symptom the suite missed | Coverage Assessment |
| "review our tests", "audit the suite", "slow / flaky suite", a symptom the suite missed | Suite Review |
| "test strategy", "test plan" | Strategy Doc |
| "write tests for X", "scaffold tests", "add tests" | Test Scaffolds |

**Findings routing.** Every Step 8 and Step 9 finding lands in the Suite Review; if the ask did not select a Suite Review and a finding exists, emit one anyway. The `Infrastructure prerequisites` slots carry prerequisites for work not yet done, never findings about work already done.

**Envelope precedence.** `node-testing-patterns`' `## Test Plan` folds in: its Infrastructure table fills the Strategy Doc `Tooling` / `Database isolation` and the `Infrastructure prerequisites` slots; its layer tables fill the gap and scaffold slots. `## Prisma Schema Design`, `## TypeORM Design`, `## BullMQ Design`, and `node-http-client-patterns`' per-call-site blocks and Resiliency Assessment are never emitted.

**Labels.** Every Suite Review finding carries exactly one label: `[Must]` when the test gives false confidence or cannot fail (a disabled `ValidationPipe`, SQLite for the production engine, a mocked-away subject, real network, a shared mutable fixture, a critical-path module with no test), `[Recommend]` otherwise; `[Must]` first. The locator is the test's `file:line`, the config key (`jest.config.js -> forceExit`), a glob plus count for a class-wide finding (`**/*.e2e-spec.ts` (210 files)), or the production file for a missing test (a glob plus count when several share the cause); the production cause the test misses goes in `Effect`.

Brace annotations in the templates are authoring notes, never emitted.

**Coverage Assessment:**

```markdown
## Node.js Test Coverage Assessment

**Stack:** Node.js <engines>{ / TypeScript <version>} - <NestJS | Express | other> <version>, <Prisma | TypeORM | other | none> <version>, <database>

**Scope:** <the modules assessed, and how a named subset was drawn | whole service>

**Test tooling detected:** <runner, HTTP stub, deep-mock helper, container library - each absent one named absent>

**Covered today:** <1-2 lines - what the existing tests actually assert>

**Coverage gaps:**

- **Unit:** <services / validators / mappers without coverage>
- **Endpoint:** <endpoints missing validation, response-shape, or pagination cases>
- **Integration:** <non-trivial queries without tests; a stand-in engine>
- **Auth:** <401 / 403 / IDOR cases missing per endpoint; JWT flow and custom-guard gaps>
- **Job:** <processors without tests; jobs without idempotency or retry cases>
- **E2E:** <critical journeys uncovered | none>
- **Contract:** <required | not required | undetermined> - <reason, or what to confirm>

**Infrastructure prerequisites:** <what must exist before the gaps can close | none>

**Priority order:** <Step 7 bands applied to the gaps, P0 first>
```

**Suite Review:**

```markdown
## Node.js Suite Review

- **Files in scope:** <n reviewed> of <n total> (<sampling rule | all>)
- **Symptom:** <as reported> -> <cause locators>   {one line per reported symptom - one finding may serve several; omit when none was reported}
- **Ruling:** <question> -> <answer>   {one line per question the ask poses outright; omit when none}
- **Suite runtime:** <current, from CI logs or as reported | unknown> -> <target, with the lever and arithmetic | no target set>
- **Verdict:** Sound | Unsound - <n> Must / <n> Recommend   {Sound when no [Must]}

### [Must] <locator>

- Issue: <the rule broken, in Node terms>
- Effect: <what it costs: false confidence, flake, runtime - and the production cause it misses>
- Fix: <concrete change>

### [Recommend] <locator>

<same three fields>
```

**Strategy Doc:**

```markdown
## Node.js Test Strategy

**Objective:** <what this achieves>

**Pyramid balance (target):** Unit <x>% / Endpoint + Integration <y>% / E2E <z>% - <why, when it departs from 70/20/10; Job and Contract count in the middle bucket>

**Tooling:** <runner and command, Supertest, TestingModule or the Express app, the database module, the HTTP stub, BullMQ handler lane plus a broker lane where Step 5 requires one>

**Database isolation:** <Testcontainers | shared instance (run prefix)> + per-worker schema + <provisioning command> + TRUNCATE in beforeEach

**Contract testing:** <required | not required | undetermined> - <reason: required when an independently deployed team consumes the API, a message schema has separate producer and consumer deploys, or a shared client library imports it>

**Suite runtime:** <current, from CI logs or as reported | unknown> -> <target, with the lever>   {omit when no suite exists}

**Flake sources:** <ordering dependence, shared rows, unclosed handles | none observed>

**Gaps to close (prioritized):**

1. <P0 blockers first, then Step 7 bands>
```

**Test Scaffolds:**

```markdown
## Node.js Test Scaffolds

| File | Layer | Cases | Priority |
| ---- | ----- | ----- | -------- |
| <path in the project's naming, under a config that runs it> | unit / endpoint / integration / job / e2e / contract / setup | <n> | <P0-P5 - the file's highest band> |

<the files, as fenced blocks in the project's language; `setup` = globalSetup / teardown, factories, fixtures, runner config>

**New dev dependencies:** <name@version | none>

**Infrastructure prerequisites:** <globalSetup, factories module, the broker-lane invocation, runner config edits | none>

**Defects found in code under test:** <file:line - the defect each scaffold asserts against | none>

**Assumptions:** <auth fixture shape, seed data, error codes, statuses not verifiable from Steps 2-3>
```

Scaffolds use the project's naming and helpers, factories over literals, typed mocks. Layer mandates apply to the layers the request covers: endpoint files carry Step 5's case matrix, repository files run on the real engine, job files cover idempotency in the handler lane.

## Self-Check

Mark a line N/A when the selected deliverable does not reach it (a Coverage Assessment emits no scaffolds; a greenfield run has no suite to review).

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed; Framework, ORM, Database, Test framework, Build tool, and the project's runner configs, stub library, mock helper, and auth fixture recorded
- [ ] Step 3: targets and existing tests read via the project's globs; production app setup and registration style noted; convention overrides recorded with reasons
- [ ] Steps 4-5: layers mapped; `node-testing-patterns` plus the ORM, BullMQ, and HTTP-client atomics consulted; endpoint matrix applied with its predicates; auth real or a rejecting stub; per-worker database isolation; handler lane vs broker lane respected
- [ ] Step 6: factories shared, rebuilt per test
- [ ] Step 7: bands applied to every ranking deliverable, P0 first; a band that cannot be computed stated, not guessed
- [ ] Step 8: hygiene boxes run against the suite (scaffold-only asks: the touched files)
- [ ] Step 9: tests judged; missing critical-path test files and pinned bugs reported; symptoms traced; sample stated above ~50 files
- [ ] Deliverables selected by the table; findings routed to a Suite Review; atomic blocks folded, never emitted; every slot filled with project-specific content

## Avoid

- Scaffolding before reading the existing tests and setup
- A filename the runner config will not match
- Chasing a coverage number instead of prioritizing by risk
- SQLite or an in-memory stand-in for the production engine
- An endpoint test app that differs from production's pipes, guards, prefix, or middleware
- An always-allow guard, a mocked `ValidationPipe`, or an overridden `APP_PIPE`
- `repository.save = jest.fn()` where a real database could assert
- Importing `BullModule` in the handler lane, or the broker lane for handler logic
- A validation case for a route that validates nothing
- `as any` to silence mock typing
