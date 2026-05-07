---
name: task-node-refactor
description: Node.js refactor planning for fat controllers / route handlers, anemic services, god modules, sync-in-async mixing, blocking I/O on the event loop, NestJS request-scoped provider misuse, prototype-pollution surfaces, BullMQ idempotency, Prisma / TypeORM relation traps, and module-level mutable state. Produces a step-by-step sequence of independently-committable refactoring steps with a Jest coverage gate. Stack-specific override of task-code-refactor for Node.js.
agent: node-tech-lead
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Node.js Refactor

## Purpose

Produce a safe, step-by-step refactoring plan for a specific Node.js target (NestJS controller / module, Express route / router, service, repository, Prisma / TypeORM entity, BullMQ processor, DTO / Zod schema). Identifies Node-specific smells (fat controller / route, anemic services, god modules, async-sync mixing, blocking I/O in event loop, NestJS request-scoped provider misuse, TypeORM listener abuse, prototype pollution surfaces, missing `whitelist` on `ValidationPipe`) and proposes independently-committable refactoring steps with Jest gates between each.

This workflow is the stack-specific delegate of `task-code-refactor` for Node.js.

## When to Use

- Node code-smell identification and resolution
- Node technical-debt reduction with a concrete plan
- Safe refactoring of a controller / route / service / repository / module / BullMQ processor
- Pre-merge "this PR grew the fat-controller / god-service problem - what's the cleanup?"

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-node-new`)
- Architecture-level restructuring across many modules (use `task-design-architecture`)
- Bug fixes (use `task-node-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                                    |
| --------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Target scope          | Yes         | File, module, or package to refactor (e.g., `src/orders/orders.controller.ts`, `src/orders/orders.service.ts`, `src/routes/orders.ts`)         |
| Goal                  | Yes         | What the refactoring should achieve (e.g., extract `placeOrder` service, kill `@AfterInsert` listener chain, split `OrdersService` god module) |
| Test coverage status  | Recommended | Whether Jest / Supertest / Testcontainers / job coverage exists for the target area                                                            |
| Shared/public surface | Recommended | Whether the target is used across module / library / team boundaries                                                                           |

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Node.js / TypeScript. If invoked as a subagent of a Node-aware parent, accept the pre-confirmed stack. If the detected stack is not Node, stop and tell the user to invoke `/task-code-refactor` instead.

Detect framework: NestJS vs Express (or mixed). Detect ORM: Prisma vs TypeORM. Record `Framework: NestJS | Express | mixed`, `ORM: Prisma | TypeORM` for the output.

### Step 2 - Read the Target

Read the actual file(s) named in the Inputs table before classifying smells. A refactor plan grounded in the user's prose summary instead of the source will hallucinate smells that aren't there and miss ones that are. Specifically:

1. Read the target module top-to-bottom; note function / method count, longest function, sync-vs-async signature mix, transaction placement, every external collaborator (`axios`, `fetch`, BullMQ `queue.add`, mailers).
2. Read the matching test file(s) (e.g., `orders.service.spec.ts`, `orders.controller.e2e-spec.ts`); count cases by outcome (happy path, validation failure, external failure, auth denial).
3. If callers are obvious (controller calling the service, scheduled job calling the service), read the immediate caller too - removing or reshaping a public function without seeing call sites is how silent breakage happens.

If the user named only the goal without a target file / module, ask for the target before proceeding. Do not guess.

**Sibling-smell disposition.** Real targets live inside fat modules. If the file containing the target also contains other smells (e.g., the user names `createOrder` but the same controller file has IDOR in `getOrder` and a `child_process.exec(userInput)` in `bulkImport`), do **not** action them in this plan and do **not** ignore them silently. List them under a `Sibling Smells (Out of Scope)` heading in the output, briefly state why each is deferred (separate target, separate severity, separate skill - e.g., security findings belong in `task-node-review-security`), and recommend follow-up invocations. This disambiguates "while we're here cleanup" (forbidden) from "name the deferred work for hand-off" (required).

### Step 3 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Identify the tests covering the target (`*.spec.ts`, `*.e2e-spec.ts`, integration tests against Testcontainers, BullMQ processor tests), then assign one of three statuses with sharp boundaries:

| Status       | Definition                                                                                                                                   | What the workflow does                                                                                                                        |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** at least 2 boundary outcomes per public entry point (e.g., validation failure, auth denial, external failure, not-found) | Proceed to Step 4 normally                                                                                                                    |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                                                                                               | Proceed, but the plan **must** include a non-optional `Step 0 - Coverage prerequisite` adding the missing boundaries before any refactor step |
| `Inadequate` | No tests, or **happy-path-only** (success case alone)                                                                                        | **Refuse to produce Steps 1+.** The only output is the Coverage Gate verdict and a recommendation to run `task-node-test` first               |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot tell you whether the refactor preserves validation, authorization, or error behavior - you would be flying blind.

**Output of this step:** explicit coverage status using one of the three labels above. Do not proceed past Step 4 if status is `Inadequate`.

### Step 4 - Identify Node Smells

Inspect the target for these Node-specific smells. Use judgment - these are signals, not hard rules.

**Controller / Route smells (NestJS / Express):**

| Smell                                   | Signal                                                                                                                                                                                              | Risk   |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Controller / Route                  | Endpoint > 15 lines of orchestration (multiple service calls, conditional dispatch, response shaping)                                                                                               | High   |
| Logic in Controller / Route             | Business rules, validation beyond DTO / Zod, calculation, or domain decisions inside the handler                                                                                                    | High   |
| Direct Repository / ORM in Controller   | Controllers / route handlers call `prisma.order.findMany` / `repository.find` directly, bypassing the service layer                                                                                 | Medium |
| ORM Entity Returned from Endpoint       | NestJS controller returns a Prisma model / TypeORM entity instance directly; Express route does `res.json(entity)` without mapping (mass-assignment + lazy-load risk on serialization)              | High   |
| Manual Validation Duplicating DTO / Zod | Handler body re-checks `@MinLength()` / `z.string().min(...)` constraints already on the schema                                                                                                     | Low    |
| Missing `whitelist` on `ValidationPipe` | NestJS app does not configure `whitelist: true, forbidNonWhitelisted: true` - silently accepts unknown fields including privilege-bearing ones; Express equivalent: Zod schemas without `.strict()` | High   |
| Response DTO Exposes Internal Fields    | Response DTO declares server-internal fields (`internalAuditLog`, `isTest`, `internalNotes`) - leaks via `class-transformer` even when the entity is not returned directly                          | High   |

**Service smells:**

| Smell                              | Signal                                                                                                                                                                          | Risk   |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| God Service Module                 | `*.service.ts` > 500 lines; mixes orchestration, persistence, mapping, external clients, scheduling                                                                             | High   |
| Anemic Domain                      | Entities are pure data containers; business rules live in `*.helpers.ts` with names like `calculateTotal(order)` and could belong on the entity                                 | High   |
| Single-Implementation Interface    | `OrdersServiceInterface` + single `OrdersService` with no test double, no second implementation                                                                                 | Medium |
| Sync-in-Async                      | `async` function calls a sync helper that does I/O - blocks the event loop. Reverse: function marked `async` for no benefit (no `await`)                                        | High   |
| External I/O Inside DB Transaction | HTTP call, message publish, or file write inside `prisma.$transaction(async (tx) => {...})` / `dataSource.transaction(async (m) => {...})` (defers commit, holds DB locks long) | High   |
| Service Returning `boolean`        | Service returns `boolean`; caller cannot distinguish failure cases (validation vs not-found vs external)                                                                        | Medium |
| Floating Promise / Missing `await` | `async` service calls a fire-and-forget promise without `await` or `.catch(...)` - error becomes `unhandledRejection`                                                           | High   |

**Persistence / ORM smells:**

| Smell                                                | Signal                                                                                                                                                                                                                      | Risk   |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Entity                                           | TypeORM `@Entity` / Prisma model wrapper class > 300 lines; mixes mapping, computed properties, business operations, validation                                                                                             | High   |
| TypeORM `@AfterInsert` / `@AfterUpdate` Abuse        | Listener dispatching emails, publishing events, calling external services - races commit and silently breaks                                                                                                                | High   |
| Prisma Middleware Side Effects                       | `prisma.$use(async (params, next) => {...})` doing cross-aggregate writes - hidden control flow                                                                                                                             | High   |
| TypeORM `eager: true` Default                        | Eager load on collection relations - cartesian explosion + locks lazy semantics elsewhere                                                                                                                                   | High   |
| Repository Returning Unbounded `find()` / `findMany` | Returns full table without pagination                                                                                                                                                                                       | Medium |
| `prisma.$queryRawUnsafe(...)`                        | Dynamic SQL built via string concat instead of parameterized `prisma.$queryRaw`...${val}...``(template literal is parameterized) or`:param` placeholders                                                                    | High   |
| ORM Instance Stored Outside Connection Scope         | ORM model assigned to a module-level cache, sent to a queue payload, or `JSON.stringify`-ed after the connection-using context closes - lazy attributes, stale data, identity-map confusion. Cache IDs and re-fetch instead | High   |

**Configuration / DI smells:**

| Smell                        | Signal                                                                                                           | Risk   |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------ |
| Module-level Mutable State   | `let cache: Record<string, T> = {}` / `const handlers: Fn[] = []` mutated by request handlers                    | High   |
| `process.env.X` Sprinkled    | `process.env.X` scattered across modules; should be a `ConfigService` / typed config field                       | Medium |
| Hardcoded Defaults Inline    | Default values inline in code rather than a typed config module                                                  | Medium |
| Service Locator Pattern      | Module imports another module just to call its function for "DI" - obscures the dependency graph                 | High   |
| NestJS Request-Scoped Misuse | `@Injectable({ scope: Scope.REQUEST })` for a stateless service - unnecessary per-request allocation             | Medium |
| `forwardRef` Overuse         | Multiple `forwardRef` calls between modules signal a circular-dependency smell - extract a shared module instead | High   |

**Async / BullMQ smells:**

| Smell                                      | Signal                                                                                                                                                 | Risk   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| Blocking I/O on Event Loop                 | `fs.readFileSync`, `crypto.pbkdf2Sync`, large `JSON.parse`, large regex, `child_process.execSync` in handler                                           | High   |
| Sync-Only Code Marked `async`              | `async` function with no `await` - just adds overhead, no benefit                                                                                      | Medium |
| Unbounded `Promise.all` Fan-out            | `Promise.all(bigList.map(call))` - exhausts pool / file descriptors                                                                                    | High   |
| `queue.add()` Inside DB Transaction        | BullMQ job dispatched inside `prisma.$transaction` / `dataSource.transaction` - worker may pick up before commit                                       | High   |
| BullMQ Job Without Idempotency             | Job that re-runs side effects when delivered twice (no dedup, no upsert, no state check)                                                               | High   |
| BullMQ Job Without `attempts` for Critical | Critical job (payment, billing) running with default `attempts: 1` - lost on worker crash without retry                                                | High   |
| DTO Validator Doing I/O                    | `class-validator` `@Validate(CustomValidator)` calling DB or HTTP - validators run on every request                                                    | High   |
| Prototype Pollution Surface                | `Object.assign(target, req.body)`, `_.merge(target, req.body)`, `Object.assign({}, defaults, req.query)` without `Object.create(null)` or sanitization | High   |

**Test smells (when refactoring brings tests into scope):**

| Smell                                       | Signal                                                                            | Risk   |
| ------------------------------------------- | --------------------------------------------------------------------------------- | ------ |
| `jest.mock` Chains for ORM                  | Patching `Prisma.$transaction` instead of using a Testcontainers integration test | Medium |
| SQLite in Repository Tests for Postgres App | Tests pass on SQLite but fail in prod on JSONB / partial index / `ON CONFLICT`    | High   |
| In-Memory BullMQ Mocking Reality            | Mock queue hides at-least-once / retry / `lockDuration` semantics                 | Medium |
| `as any` in Production Code                 | Type-cast escape hatch used to bypass a real type bug                             | High   |

**General OO smells (apply with TypeScript judgment):**

Use skill: `backend-coding-standards` for the cross-language smell catalog.
Use skill: `complexity-review` when the target shows over-engineering signals (single-impl interfaces, base classes for two children, premature factory / strategy, redundant mapping layers) - those are simplification opportunities, not refactor steps to extract more abstractions.

Apply TypeScript judgment - a 25-line service function orchestrating clearly named private methods is fine; a 10-line function doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, tests, and deployments are affected by the refactor.

Node-specific blast-radius signals:

- [ ] **Public API surface**: target is a controller / route used by external clients - refactor risks API contract change
- [ ] **Library / package boundary**: target is in a published package on npm or an internal monorepo library consumed by other apps
- [ ] **Listener with broad receiver**: refactoring a TypeORM `@AfterInsert` connected to many entities / a Prisma middleware bound globally affects every dispatch
- [ ] **Service injected widely**: target is imported by > 10 modules (NestJS DI graph or Express direct imports) - signature changes cascade
- [ ] **ORM entity used in many queries**: refactoring an entity affects every repository / `findMany` / `find` call
- [ ] **DTO reused across endpoints**: DTO field rename / removal cascades into every dependent endpoint and its tests
- [ ] **Exported NestJS module token**: refactoring a `@Module({ exports: [...] })` provider that other modules import means breaking their imports

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single module, multiple callers) / **Wide** (cross-module, public API, broad listener) / **Critical** (published package, entity used by 5+ services).

### Step 6 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase compiles with `tsc --noEmit` cleanly and the test suite passes after each step
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step (or labeled `coupled-fix`, see below)
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing Jest suite continues to pass; new tests added when extracting new units

**Recipe interleaving.** When more than one Common Recipe applies to a single target (e.g., a fat controller that also has `Object.assign(target, req.body)`, blocks the event loop, and stashes ORM entities in a module cache), do **not** concatenate the recipes - that produces a 25-step plan mixing concerns. Identify the **primary** refactor (usually the one named in the user's goal), use that recipe as the spine, and fold supporting recipes in as additive sub-steps where dependencies require it. State the primary recipe explicitly in the output via the `Primary recipe:` field. If the spine grows past ~8 steps, split into two plans / two PRs rather than one mega-plan.

**Coupled-fix language.** Sometimes a refactor genuinely depends on a behavior change (e.g., extracting a service that derives `ownerId` from the authenticated principal _requires_ the principal to be available, so adding `@UseGuards(AuthGuard('jwt'))` is a structural prerequisite, not "while-we're-here cleanup"). When this happens, label the step `coupled-fix` in the Output Format with its own test gate and rationale. This is **not** a bundling violation - it is an explicit prerequisite. Do not silently fold it into an extraction step.

**Transaction-boundary watch.** When extracting orchestration that runs inside `prisma.$transaction(async (tx) => {...})` or `dataSource.transaction(async (m) => {...})`, the extracted unit inherits the transaction context if called from the original entry point. If the extracted code makes HTTP calls, publishes to BullMQ, or writes files, they now happen mid-transaction (a regression). State the transaction stance per step: "callee runs inside caller's transaction" or "callee uses post-commit dispatch (event emitter / `afterCommit` hook) to defer side effects." Never silently move I/O across a transaction boundary.

**Async-boundary watch.** Adding `async` or removing it crosses a Promise boundary. State whether the new signature returns `Promise<T>` or `T` directly, and ensure callers are updated (`await` added or removed). Never silently change a function from sync to async without auditing every call site - the async function returns a `Promise` if not awaited, and the bug is silent (TypeScript catches some via `@typescript-eslint/no-floating-promises` but not all).

**Common Node refactor recipes:**

**Recipe: Extract service from fat controller (NestJS)**

1. Add `<verb>-<noun>.service.ts` (e.g., `place-order.service.ts`) with a single intention-revealing async method returning a domain result type (DTO / discriminated union); copy logic from controller; controller still does the original work
2. Add `place-order.service.spec.ts` with one test per outcome (success, validation failure, external failure)
3. Update controller to call the service via constructor injection; preserve response shape; ensure e2e tests pass unchanged
4. Remove the original logic from the controller; verify e2e tests pass
5. Add a controller-level test asserting service failure surfaces as the expected error response (likely via `@Catch` exception filter)

**Recipe: Extract service from fat route (Express)**

1. Add `<verb>-<noun>.service.ts` with a single function taking simple args and returning a domain result; copy logic from route handler
2. Add `<verb>-<noun>.test.ts`; test cases include the validation / business-rule paths
3. Update route handler to call the service
4. Remove the original logic from the route handler
5. Add a route-level test asserting service failure surfaces via global error middleware

**Recipe: Convert TypeORM `@AfterInsert` / Prisma middleware side effects to post-commit dispatch**

1. Add a service-level test (or e2e test) reproducing the current observable behavior (record updated, email sent, event published)
2. Replace the listener body with an event-emitter call (NestJS `EventEmitter2`) or remove the listener and call the side-effect from the service explicitly. Side effects now fire post-commit instead of mid-transaction
3. Run tests; confirm pass
4. If the listener was doing cross-aggregate work, extract the side-effect handler into a service method and call it from the calling service or controller - remove the listener entirely
5. Run the full suite; verify no orphan code paths still rely on the listener

**Recipe: Untangle fat controller + listener-driven side effects (combined case)**

The most common Node refactor: a controller `create` triggers an entity save whose `@AfterInsert` listener fans out (mailers, BullMQ dispatches, audit writes). Removing the listener and extracting a service must happen as one logical change, but in safe sub-steps so the suite stays green between commits.

1. **Pin behavior with an e2e + service test** asserting every observable side effect (record updated, mailer queued, job dispatched, audit row written) - this is the contract the refactor must preserve
2. **Promote listener dispatch to post-commit** first (NestJS `EventEmitter2.emit` after `prisma.$transaction` resolves; TypeORM `subscriber.afterCommit` hook); side effects fire post-commit; tests still pass
3. **Introduce a service method** (`<verb><Noun>`) that performs the write _and_ the side effects in one call; controller calls the service _but the listeners still run_ - this duplicates side effects intentionally and temporarily
4. **Make listeners no-op when called from the service** via an `AsyncLocalStorage` flag set by the service or a flag on the entity (`if (Reflect.getMetadata(SKIP_LISTENERS, entity)) return;`); verify tests still pass with side effects firing exactly once
5. **Delete the listeners entirely**; the service is now the single source of orchestration; remove the bypass flag; tests still green
6. **Audit other call sites** (`prisma.order.create`, `repository.save`, migrations, scheduled jobs) - any caller relying on the old listener is now broken and must be updated to call the service or have the side effects re-derived

The intermediate "listeners no-op when called from service" step is the safety net - it keeps the codebase shippable between the introduction of the service (step 3) and the deletion of the listeners (step 5).

**Recipe: Eliminate blocking I/O in event loop**

1. Identify the blocking call (`fs.readFileSync`, `crypto.pbkdf2Sync`, sync `child_process.execSync`, large `JSON.parse` of unbounded input)
2. For file I/O: replace `fs.readFileSync(path)` with `await fs.promises.readFile(path)`; for streams, prefer `fs.createReadStream(path)` + `for await (const chunk of stream)`
3. For crypto: `crypto.pbkdf2Sync(...)` → `await promisify(crypto.pbkdf2)(...)`; `crypto.scryptSync(...)` → `await promisify(crypto.scrypt)(...)`
4. For child process: `execSync` → `await promisify(execFile)([...args])` (avoid `exec` with shell when args are user input)
5. For CPU work: move to a `worker_threads` pool (`piscina` package) or a BullMQ job
6. Run e2e tests; assert latency under load (if perf test fixture exists) shows tail latency improvement

**Recipe: Split god service into focused services**

1. Identify the orthogonal concerns inside the service module (e.g., `orders.service.ts` doing place + cancel + refund + reporting → split into `place-order.service.ts`, `cancel-order.service.ts`, `refund-order.service.ts`, `order-report.service.ts`)
2. Extract one concern at a time into a new module / file with explicit imports; original god service delegates to it temporarily
3. Update callers (NestJS: update module providers / exports and constructor injection; Express: update direct imports) to use the new focused service directly; remove delegation from god service
4. Repeat until god service is empty; delete it. Each extraction commits independently
5. Verify all e2e / service tests still pass

**Recipe: Eliminate single-implementation interface**

1. Confirm the interface has no test doubles, no second implementation, no DI requirement that needs an abstract token
2. Inline: rename concrete `OrdersService` to live where the interface was; delete the interface; update callers (most cases the IDE rename handles it)
3. Run tests; confirm pass. Caller code is shorter and clearer
4. **Skip if** the interface is part of a published library API or has a real second implementation - the smell is fake

**Recipe: Make BullMQ job idempotent**

1. Add a job test asserting the side effect happens exactly once when the same job is dispatched twice (different request IDs, same business key)
2. Add an idempotency guard: dedup table keyed by `job.id`, business-key upsert via `prisma.x.upsert(...)` / `repository.upsert(...)`, or version check
3. Verify retries on transient failures still complete the work
4. Configure DLQ / max-retries (`attempts`, `backoff: { type: 'exponential', delay: 1000 }`) so poison messages do not loop forever
5. Set explicit `lockDuration` for jobs that genuinely take > 30s to prevent stalled-job double-execution
6. Use `jobId: businessKey` on `queue.add(...)` for client-side dedup when the same input must collapse to one job

**Recipe: Eliminate missing `whitelist` / `forbidNonWhitelisted` on `ValidationPipe`**

1. Update `main.ts`: `app.useGlobalPipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }))`
2. Run e2e tests; expect any test that POSTed unknown fields to start failing with 400 - fix or document each
3. Audit every other DTO in the codebase to ensure no client relies on unknown-field acceptance
4. Internal-only DTOs (queue payloads, internal RPC) may keep `forbidNonWhitelisted: false` with a comment justifying

**Recipe: Eliminate prototype-pollution surface**

1. Identify the unsafe merge: `Object.assign(target, req.body)`, `_.merge(target, req.body)`, `Object.assign({}, defaults, req.query)`
2. Replace with safe constructor: `Object.create(null)` + explicit field copy, or `defu(req.body, defaults)` (which sanitizes `__proto__` / `constructor` keys), or destructure-then-construct: `const { name, email } = parsedDto; const data = { name, email }`
3. Add an e2e test attempting to inject `__proto__` / `constructor` keys; assert they are stripped or rejected
4. Audit other unsafe merges in the codebase

**Recipe: Replace module-level mutable state**

1. Identify the mutable state (`let cache: Record<string, T> = {}`, `const handlers: Fn[] = []`)
2. Move into a class with explicit lifecycle (NestJS `@Injectable()` service with `OnModuleDestroy` cleanup), into a typed config field if it is config, or into request scope (NestJS `@Injectable({ scope: Scope.REQUEST })` if genuinely per-request; `AsyncLocalStorage` for cross-function-but-per-request) if appropriate
3. Update callers to receive the new dependency explicitly (NestJS constructor injection, Express middleware-attached attribute, or service constructor arg)
4. Run tests; confirm pass; assert cross-test isolation (no leaking state between tests via Jest `--runInBand` or per-file isolation)

### Step 7 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step (not just at the end)
- [ ] Steps are ordered low-risk first (extracts, additions) before high-risk (deletions, signature changes, listener removals)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## Node Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Node refactor recipes" - this is the spine]
**Stack:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version> | mixed
**ORM:** Prisma <version> | TypeORM <version>

## Coverage Gate

**Status:** Adequate | Thin | Inadequate

[If Adequate: one sentence on the boundary cases that exist.]
[If Thin: list the missing boundary tests; Step 0 below covers them.]
[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-node-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, and Verification. You may still produce the **Smells Identified** and **Sibling Smells (Out of Scope)** sections as a *preview* so the implementer has a target list when filling the coverage gap; mark them clearly as preview-only.]

**Coverage prerequisite list shape (when status is `Thin` or `Inadequate`).** List required tests as one row per public entry point with this shape: `entry-point | outcome | recommended layer`. Outcomes cover at minimum: validation failure (4xx), authorization denial (401/403), not-found / IDOR, external-collaborator failure. Layer options: e2e endpoint test (Supertest + TestingModule / app instance), service unit test, repository integration test (Testcontainers), BullMQ job test. Example: `POST /orders | unknown-field rejected (whitelist:true) | e2e endpoint test`. This makes the prerequisite directly actionable rather than a vague "add boundary tests."

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file/module that this plan does NOT address. Listed for hand-off, not action._

| Smell   | Location  | Why deferred                                                                                | Recommended follow-up                                                             |
| ------- | --------- | ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| [Smell] | file:line | [separate target / separate severity / belongs to security review / belongs to perf review] | [`task-node-review-security` / `task-node-refactor` on a different target / etc.] |

_Omit this section if the target file has no other smells._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add the missing boundary tests identified in the Coverage Gate
- **Risk:** Low (tests-only change)
- **Test gate:** new tests pass; existing suite still green
- **Rollback:** revert added test files

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass after this step - unit / e2e / Testcontainers integration / BullMQ]
- **Transaction stance:** [callee runs inside caller's transaction | callee uses post-commit dispatch | not transactional]
- **Async stance:** [sync | async | unchanged]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure. Use `Step kind: coupled-fix` for any step that intentionally changes behavior because the refactor depends on it (e.g., adding `@UseGuards(AuthGuard('jwt'))` so the extracted service can derive `ownerId` from the principal). Always state why the coupling is structural, not cosmetic.]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] `tsc --noEmit` clean and Jest suite passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step
- [ ] No I/O silently moved across transaction boundaries
- [ ] No silent sync ↔ async signature changes; every call site updated

## Out of Scope

[Adjacent improvements explicitly NOT in this plan - e.g., "renaming `OrderProcessor` to `OrderFulfiller` is a follow-up; this plan only extracts behavior, not renames"]
```

## Self-Check

**Plan-time checks (verifiable now from the plan itself):**

- [ ] Stack confirmed as Node.js / TypeScript (or accepted from parent dispatcher); framework and ORM recorded (Step 1)
- [ ] Target file(s) and matching tests read directly before smell classification - no smells inferred from prose alone (Step 2)
- [ ] Sibling smells in the target file listed under `Sibling Smells (Out of Scope)` with deferral rationale, or section omitted because none exist (Step 2)
- [ ] Coverage gate evaluated using the sharp boundaries (`Adequate` / `Thin` / `Inadequate`); plan refused if `Inadequate`; happy-path-only treated as `Inadequate` not `Thin` (Step 3)
- [ ] Node-specific smells identified using Step 4 catalog (controller/route, service, persistence, configuration/DI, async/BullMQ) (Step 4)
- [ ] Cross-module risk (blast radius) stated before proposing steps (Step 5)
- [ ] `Primary recipe:` named in the output; supporting recipes folded as sub-steps, not concatenated (Step 6)
- [ ] Step 0 included if Coverage Gate is `Thin`; omitted if `Adequate` (Output Format)
- [ ] Transaction stance stated per step (no I/O silently moved across transaction boundary) (Step 6)
- [ ] Async stance stated per step (no silent sync ↔ async signature changes) (Step 6)
- [ ] `Step kind:` set to `coupled-fix` for any step that intentionally changes behavior because the refactor depends on it; rationale stated; otherwise `refactor` (Step 6)
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions, listener removals, signature changes) (Step 6)
- [ ] Plan length ≤ ~8 steps, or split into multiple PRs explicitly (Step 6)
- [ ] No step bundles unrelated cleanup (Step 6)
- [ ] Goal explicitly mapped to the end state of the sequence (Step 7)

**Execution-time gates (commitments the plan makes for the implementer):**

- [ ] `tsc --noEmit` clean and Jest suite passes between every step
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate - that's a rewrite, not a refactor
- Bundling behavior changes with refactoring steps - keep them separate, label clearly
- Making "while we're here" unrelated cleanups - they belong in their own PR
- Renaming during a refactor (rename PRs are separate; mixing the two doubles the review surface)
- Removing TypeORM listeners or Prisma middleware without a test asserting the original behavior is preserved
- Extracting a single-implementation interface without a real second use case - wait for the second use case before generalizing
- Moving HTTP calls or BullMQ dispatches from a non-transactional context to inside a transactional one (or vice versa) without explicitly stating the transaction stance
- Changing a function from sync to async (or back) without auditing every call site - missing `await` returns a `Promise` silently and the bug evades simple tests
- Refactoring a published npm package without a backward-compatibility plan - that is a public API
- Replacing `axios` with `undici` on a code path with no measured benefit (premature change; if the team is already on `axios` and it works, the recipe is "address the smell" not "swap libraries")
- Replacing module-level mutable state with `AsyncLocalStorage` without checking that the codebase actually has a clear request-bound boundary - ALS without a clear `als.run(...)` boundary leaks state across requests
