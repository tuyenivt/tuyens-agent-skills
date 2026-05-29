---
name: task-node-refactor
description: Node.js / NestJS / Express refactor plan: fat controllers, anemic services, blocking I/O, ORM relation traps; phased steps with Jest coverage gate.
agent: node-tech-lead
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Node.js Refactor

Safe, step-by-step refactoring plan for a Node target (NestJS controller / module, Express route, service, repository, Prisma / TypeORM entity, BullMQ processor, DTO / Zod schema). Identifies smells, proposes independently-committable steps with `tsc --noEmit` + Jest gates between each.

## When to Use

- Node code-smell resolution
- Technical-debt reduction with a concrete plan
- Safe refactor of a controller / route / service / repository / BullMQ processor
- "This PR grew the fat-controller / god-service problem - what's the cleanup?"

**Not for:**
- Choosing what debt to tackle (`task-debt-prioritize`)
- Feature changes (`task-node-implement`)
- Cross-module restructuring (`task-design-architecture`)
- Bug fixes (`task-node-debug`)

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| Target scope | Yes | File / module to refactor (e.g., `src/orders/orders.controller.ts`) |
| Goal | Yes | What the refactor should achieve (e.g., extract `placeOrder` service, kill `@AfterInsert` chain) |
| Test coverage status | Recommended | Whether Jest / Supertest / Testcontainers / BullMQ coverage exists |
| Shared/public surface | Recommended | Whether the target crosses module / package / team boundaries |

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept pre-confirmed stack from a Node-aware parent. Record `Framework: NestJS | Express | mixed` and `ORM: Prisma | TypeORM`.

### Step 2 - Read the Target

Plans grounded in user prose hallucinate smells. Before classifying:

1. Read the target file top-to-bottom; note function count, longest function, sync-vs-async signature mix, transaction placement, every external collaborator (`axios`, `fetch`, BullMQ `queue.add`, mailers).
2. Read matching tests (`*.spec.ts`, `*.e2e-spec.ts`); count cases by outcome (happy, validation, external failure, auth denial).
3. Read the immediate caller (controller calling the service, scheduled job calling the service) - signature changes cascade.

If only a goal was given without a target file, ask for the target.

**Sibling-smell disposition.** If the file contains smells beyond the named target (IDOR in `getOrder`, `child_process.exec(userInput)` in `bulkImport`), do **not** action them and do **not** ignore them. List under `Sibling Smells (Out of Scope)` with brief deferral rationale and a recommended follow-up invocation (e.g., security findings -> `task-node-review-security`).

### Step 3 - Coverage Gate (mandatory)

Refactoring without tests is a rewrite. Assign one of three statuses:

| Status | Definition | Action |
|--------|------------|--------|
| `Adequate` | Happy path + >= 2 boundary outcomes per public entry (validation, auth denial, external failure, not-found) | Proceed to Step 4 |
| `Thin` | Happy path + exactly 1 boundary outcome | Proceed; plan must include non-optional `Step 0 - Coverage prerequisite` |
| `Inadequate` | No tests, or happy-path-only | **Refuse Steps 1+.** Output the verdict + recommendation to run `task-node-test` first |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot verify the refactor preserves validation, authorization, or error behavior.

Output the explicit status before proceeding.

### Step 4 - Identify Node Smells

Use skill: `node-nestjs-overengineering-review` (NestJS targets) or `node-express-overengineering-review` (Express targets) for: class-validator / Zod duplicating DB or TS strict-null, defensive guards on typed values, single-impl service interfaces, request-scope misuse, middleware-of-one, Repository wrappers, custom error hierarchies. Those are simplification opportunities, not extractions.

Use skill: `backend-coding-standards` for the cross-language smell catalog.
Use skill: `complexity-review` for premature factory / strategy / redundant mapping layers.

**Additional Node smells not covered above:**

| Smell | Signal | Risk |
|-------|--------|------|
| Fat Controller / Route | Endpoint > 15 lines orchestrating multiple service calls, dispatch, response shaping | High |
| Logic in Controller / Route | Business rules, calculation, domain decisions inside handler | High |
| Direct Repository / ORM in Controller | `prisma.x.findMany` / `repository.find` in handler, bypassing service | Medium |
| ORM Entity Returned from Endpoint | Controller / `res.json(entity)` without DTO mapping (mass-assignment + lazy-load risk) | High |
| Missing `whitelist` on `ValidationPipe` | No `whitelist: true, forbidNonWhitelisted: true`; Zod equivalent: no `.strict()` | High |
| Response DTO Exposes Internal Fields | DTO declares `internalAuditLog` / `isTest` - leaks via `class-transformer` | High |
| God Service Module | `*.service.ts` > 500 lines mixing orchestration + persistence + clients | High |
| Anemic Domain | Business rules in `*.helpers.ts` instead of methods on the entity | High |
| Sync-in-Async / Async-without-await | `async` function calling sync I/O, or `async` with no `await` | High |
| External I/O Inside DB Transaction | HTTP / `queue.add` / mailer inside `prisma.$transaction` / `dataSource.transaction` | High |
| Service Returning `boolean` | Caller cannot distinguish validation vs not-found vs external | Medium |
| Floating Promise | `async` call without `await` or `.catch` - becomes `unhandledRejection` | High |
| Fat Entity | Entity > 300 lines mixing mapping + computed + business + validation | High |
| TypeORM `@AfterInsert` / Prisma `$use` Side Effects | Hook dispatching emails / events / external calls; races commit | High |
| TypeORM `eager: true` Default | Eager load on collections - cartesian explosion | High |
| `prisma.$queryRawUnsafe` | Dynamic SQL via concat instead of parameterized template literal | High |
| Repository Returning Unbounded `findMany` | No pagination | Medium |
| ORM Instance Outside Connection Scope | Entity in module cache / queue payload / `JSON.stringify`-ed | High |
| Module-level Mutable State | `let cache = {}` mutated by handlers | High |
| `process.env.X` Sprinkled | Should be a typed `ConfigService` | Medium |
| `forwardRef` Overuse | Circular-dependency smell - extract a shared module | High |
| NestJS Request-Scoped Misuse | `Scope.REQUEST` on a stateless service | Medium |
| Blocking I/O on Event Loop | `fs.readFileSync`, `crypto.pbkdf2Sync`, `child_process.execSync`, large `JSON.parse` | High |
| Unbounded `Promise.all` Fan-out | `Promise.all(bigList.map(call))` - exhausts pool / FDs | High |
| `queue.add` Inside DB Transaction | Worker may pick up before commit | High |
| BullMQ Job Without Idempotency / `attempts` | Re-runs side effects on retry; critical job with default `attempts: 1` | High |
| DTO Validator Doing I/O | `class-validator` `@Validate(...)` calling DB / HTTP per request | High |
| Prototype Pollution Surface | `Object.assign(target, req.body)`, `_.merge(target, req.body)` without sanitization | High |
| `as any` in Production Code | Type-cast bypassing a real type bug | High |

**Test smells (when refactoring brings tests into scope):** `jest.mock` chains for ORM instead of Testcontainers; SQLite in repository tests for a Postgres app (JSONB, partial index, `ON CONFLICT` diverge); in-memory BullMQ mocking reality (hides at-least-once / `lockDuration`).

Apply TypeScript judgment: a 25-line service function orchestrating clearly named private methods is fine; a 10-line function doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius`.

Node-specific signals: public controller / route used by external clients; published npm package surface; TypeORM listener / Prisma middleware bound globally; service injected by > 10 modules; entity used in many queries; DTO reused across endpoints; exported NestJS module provider.

State blast radius: **Narrow** / **Moderate** / **Wide** / **Critical**.

### Step 6 - Propose the Step Sequence

Each step must be:

1. **Independently committable** - `tsc --noEmit` clean and Jest suite passes after each step
2. **Behaviorally invariant** unless labeled `coupled-fix`
3. **Reversible** in one revert
4. **Tested** - existing suite still passes; new tests when extracting new units

**Recipe interleaving.** When multiple recipes apply (a fat controller that also blocks the event loop and stashes entities in a module cache), don't concatenate - identify the **primary** refactor (usually the one in the user's goal), name it as `Primary recipe:`, fold supporting recipes as sub-steps. If the spine > 8 steps, split into two PRs.

**Coupled-fix language.** When a refactor depends on a behavior change (extracting a service that derives `ownerId` from the principal requires `@UseGuards(AuthGuard('jwt'))` - a structural prerequisite), label the step `coupled-fix` with its own test gate. Not a bundling violation; an explicit prerequisite.

**Per-step disclosures** - state explicitly:

- **Transaction stance:** callee runs inside caller's transaction | post-commit dispatch | not transactional. Never silently move I/O across a transaction boundary.
- **Async stance:** sync | async | unchanged. Never silently change a function from sync to async without auditing every call site - `@typescript-eslint/no-floating-promises` catches some, not all.

**Common Node refactor recipes:**

**Extract service from fat controller / route**

1. Add `<verb>-<noun>.service.ts` with one intention-revealing async method returning a domain result type (DTO / discriminated union); copy logic; controller / route still calls the original
2. Add `<verb>-<noun>.service.spec.ts` with cases for success, validation failure, external failure
3. Controller / route delegates via constructor injection (NestJS) or direct import (Express); preserve response shape
4. Remove the original logic; e2e tests still pass
5. Add a controller-level / route-level test asserting service failure surfaces as the expected error response (NestJS `@Catch` filter; Express global error middleware)

**Move side effects out of an open DB transaction**

The case: `prisma.$transaction(async tx => { await tx.order.create(...); await queue.add('send-email', ...); await axios.post(webhookUrl, ...); })`. Worker may pick the job before the row is visible; HTTP call holds a pooled DB connection; rollback leaves email queued / webhook fired.

Pick **one**; do not stack.

_Option A - Post-commit dispatch_ (default; simpler):

1. Capture inputs needed for side effects (IDs, scalars - never the ORM entity) inside the transaction
2. Move `queue.add` / `axios.post` / `mailer.send` to **after** `prisma.$transaction(...)` resolves. For TypeORM, use `subscriber.afterCommit` or `EventEmitter2` from the caller after `dataSource.transaction(...)` returns. NestJS pattern: `runOnTransactionCommit(() => ...)` from `typeorm-transactional`
3. Test asserts: side effects fire exactly once on commit; nothing fires on rollback
4. Document the failure mode: process crash between commit and dispatch drops the side effect. Acceptable for non-critical paths; not for billing - use Option B

_Option B - Transactional outbox_ (durable, at-least-once):

1. Add `outbox_messages` table: `id`, `aggregate_id`, `event_type`, `payload Json`, `created_at`, `processed_at NULL`
2. Inside `prisma.$transaction`, write the outbox row alongside the business write - both commit atomically
3. Relay (BullMQ scheduler / `setInterval`) selects unprocessed rows with `SELECT ... FOR UPDATE SKIP LOCKED`, dispatches, marks `processed_at = now()` after success
4. Side-effect handlers must be idempotent (`jobId: outboxId` for BullMQ dedup; idempotency keys on HTTP)
5. Test: outbox row exists post-commit; relay picks up; second relay run does not re-dispatch
6. Heavier but guarantees at-least-once under crashes - prefer for billing, payments, contractually-required notifications

**Untangle fat controller + listener-driven side effects (combined case)**

A controller `create` triggers an entity save whose `@AfterInsert` fans out (mailers, BullMQ, audits). Removing the listener and extracting a service must happen as one logical change, but in safe sub-steps so the suite stays green between commits.

Do **not** introduce an `AsyncLocalStorage` skip-flag or `Reflect.getMetadata(SKIP_LISTENERS, entity)` attribute to make the listener no-op for the new caller. ALS without a clear `als.run(...)` boundary leaks across requests; entity metadata is easy to forget on a new caller. The flag ships as a permanent footgun.

1. **Pin behavior** with an e2e + service test asserting every observable side effect (record updated, mailer queued, job dispatched, audit row written) - this is the contract
2. **Promote listener dispatch to post-commit** (`EventEmitter2.emit` after `prisma.$transaction` resolves; TypeORM `subscriber.afterCommit`); side effects fire post-commit; tests still pass
3. **Audit every caller of the entity write** - controller, scheduled jobs, BullMQ processors, other services. List them. Each must move to the new service method **before** step 5
4. **Introduce the service method** that delegates to the existing repository / `prisma.x.create` path; listener still owns side effects; behavior unchanged
5. **Atomic swap** - in one commit, move side-effect calls from the listener into the service method **and** delete the listener. Because step 3 ensured every caller goes through the service, no caller can reach the entity without the side effects
6. **Verify** with `git grep` for the deleted listener / direct repository entry points - zero hits

If step 3 finds a caller that cannot move yet, pause: keep the listener and defer, or split across releases. Do not paper over with a skip-flag.

**Eliminate blocking I/O in event loop**

1. Identify the blocking call (`fs.readFileSync`, `crypto.pbkdf2Sync`, `execSync`, large `JSON.parse` of unbounded input)
2. File I/O -> `await fs.promises.readFile` or `fs.createReadStream(...)` + `for await (const chunk of stream)`
3. Crypto -> `await promisify(crypto.pbkdf2)(...)` / `crypto.scrypt`
4. Child process -> `await promisify(execFile)([...args])` (avoid `exec` with shell on user input)
5. CPU work -> `worker_threads` pool (`piscina`) or a BullMQ job
6. Run e2e; assert latency improvement under load if a perf fixture exists

**Split god service into focused services**

1. Identify orthogonal concerns (`orders.service.ts` doing place + cancel + refund + reporting -> `place-order.service.ts`, `cancel-order.service.ts`, `refund-order.service.ts`, `order-report.service.ts`)
2. Extract one concern at a time; god service delegates temporarily
3. Update callers to use the focused service directly (NestJS providers / Express direct imports); remove delegation
4. Repeat; delete the god service when empty

**Make BullMQ job idempotent**

1. Test asserting the side effect fires exactly once when the same job is dispatched twice (different request IDs, same business key)
2. Idempotency guard: dedup table keyed by `job.id`, business-key upsert via `prisma.x.upsert` / `repository.upsert`, or version check
3. Configure DLQ / `attempts`, `backoff: { type: 'exponential', delay: 1000 }`, explicit `lockDuration` for jobs > 30s
4. Use `jobId: businessKey` on `queue.add(...)` for client-side dedup

**Eliminate missing `whitelist` / `forbidNonWhitelisted`**

1. `app.useGlobalPipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }))`
2. Run e2e; tests posting unknown fields will start failing with 400 - fix or document each
3. Audit other DTOs; internal-only DTOs (queue payloads, RPC) may keep `forbidNonWhitelisted: false` with a comment

**Eliminate prototype-pollution surface**

1. Identify unsafe merges: `Object.assign(target, req.body)`, `_.merge(target, req.body)`
2. Replace with `Object.create(null)` + explicit field copy, `defu(req.body, defaults)`, or destructure-then-construct: `const { name, email } = parsedDto; const data = { name, email }`
3. Test injects `__proto__` / `constructor` keys; assert stripped or rejected
4. Audit other unsafe merges

**Replace module-level mutable state**

1. Identify `let cache: Record<string, T> = {}` / `const handlers: Fn[] = []`
2. Move into a NestJS `@Injectable()` with `OnModuleDestroy` cleanup, a typed config field, or request scope (`Scope.REQUEST` if genuinely per-request, `AsyncLocalStorage` for cross-function per-request with a clear `als.run(...)` boundary)
3. Callers receive the dependency explicitly
4. Tests pass; assert cross-test isolation (Jest `--runInBand` or per-file isolation)

### Step 7 - Validate Plan Against Goal

- [ ] Goal achieved at the end of the sequence
- [ ] Each step small enough to review in < 30 minutes
- [ ] Test coverage runs between every step
- [ ] Low-risk steps first (additions, extractions) before high-risk (deletions, signature changes, listener removals)
- [ ] Rollback is one revert per step
- [ ] No step bundles unrelated cleanup

## Output Format

```markdown
## Node Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Node refactor recipes"]
**Stack:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version> | mixed
**ORM:** Prisma <version> | TypeORM <version>

## Coverage Gate

**Status:** Adequate | Thin | Inadequate

[If Adequate: one sentence on boundary cases.]
[If Thin: list missing boundary tests; Step 0 covers them.]
[If Inadequate: state what coverage must exist; recommend running `task-node-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, Verification. You may still produce **Smells Identified** and **Sibling Smells** as a preview; mark preview-only.]

**Coverage prerequisite list shape (when `Thin` or `Inadequate`):** one row per public entry point: `entry-point | outcome | recommended layer`. Outcomes cover validation failure (4xx), authorization denial (401/403), not-found / IDOR, external-collaborator failure. Layer options: e2e endpoint test (Supertest + TestingModule), service unit test, repository integration (Testcontainers), BullMQ job test.

## Smells Identified

| Smell | Location | Risk | Notes |
| ----- | -------- | ---- | ----- |

## Sibling Smells (Out of Scope)

| Smell | Location | Why deferred | Recommended follow-up |
| ----- | -------- | ------------ | --------------------- |

_Omit if no other smells in target._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Adequate)_

- **Change:** add boundary tests from Coverage Gate
- **Risk:** Low
- **Test gate:** new tests pass; existing suite green
- **Rollback:** revert added test files

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass - unit / e2e / Testcontainers / BullMQ]
- **Transaction stance:** [inside caller's tx | post-commit dispatch | not transactional]
- **Async stance:** [sync | async | unchanged]
- **Rollback:** [how to revert]

### Step 2 - [...]

[`Step kind: coupled-fix` for any step that intentionally changes behavior; state why the coupling is structural.]

## Verification

- [ ] Goal achieved at end of sequence
- [ ] Each step independently committable
- [ ] `tsc --noEmit` clean and Jest suite passes between every step
- [ ] No bundled cleanup
- [ ] Rollback path is one revert per step
- [ ] No I/O silently moved across transaction boundaries
- [ ] No silent sync / async signature changes; every call site updated

## Out of Scope

[Adjacent improvements explicitly NOT in this plan]
```

## Self-Check

- [ ] Stack, framework, ORM recorded; target + tests read before classification (Steps 1-2)
- [ ] Sibling smells listed with deferral rationale (or section omitted)
- [ ] Coverage gate evaluated with sharp boundaries; happy-path-only = `Inadequate` -> plan refused (Step 3)
- [ ] Smells identified via overengineering-review + Step 4 catalog
- [ ] Blast radius stated before steps (Step 5)
- [ ] `Primary recipe:` named; supporting recipes folded as sub-steps; <= 8 steps or split (Step 6)
- [ ] Each step: transaction stance + async stance disclosed; `coupled-fix` labeled when behavior changes
- [ ] Steps ordered low-risk first; no bundled cleanup; goal mapped to end state (Steps 6-7)
- [ ] Execution commitments listed: `tsc --noEmit` + Jest pass between steps; one-revert rollback per step

## Avoid

- Refactor without a coverage gate - that's a rewrite
- Bundling behavior changes with refactoring steps
- "While we're here" unrelated cleanup
- Renaming during a refactor (separate PRs)
- Removing TypeORM listeners or Prisma middleware without a test asserting original side effects are preserved
- `AsyncLocalStorage` skip-flag or `Reflect.getMetadata(SKIP_LISTENERS, ...)` to silence a listener for "the new path" - audit and delete instead
- Extracting a single-impl interface without a real second use case
- Moving I/O across a transaction boundary without explicit transaction-stance disclosure
- Changing a function from sync to async without auditing every call site
- Refactoring a published npm package without a backward-compatibility plan
- Replacing `axios` with `undici` (or similar library swap) on a path with no measured benefit
- Replacing module-level mutable state with `AsyncLocalStorage` without a clear `als.run(...)` boundary - leaks state across requests
