---
name: task-node-implement
description: Implement end-to-end Node.js/TypeScript features for NestJS or Express - Prisma/TypeORM schema, services, controllers, DTOs, BullMQ, Jest tests.
agent: node-engineer
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

# Implement Node.js Feature

## When to Use

End-to-end Node.js / TypeScript feature work in one pass - migration, model, service, controller or router, DTOs, jobs, tests - for NestJS or Express.

Not for: single-file edits (edit directly), bugfixes, frontend.

## Rules

- TypeScript projects: strict, no `any`, explicit return types on public methods (JavaScript: JSDoc types and Zod, per STEP 2); every promise awaited, or explicitly `void`-ed with a `.catch`
- DTOs for every request and response; Prisma models and TypeORM entities never reach the wire
- Constructor injection (NestJS providers; Express: dependencies passed in, not imported singletons)
- Validation on every input: NestJS class-validator under the project's global `ValidationPipe` - on a new app `{ whitelist: true, forbidNonWhitelisted: true, transform: true }` (per `node-security-patterns`; overrides `node-nestjs-patterns`' bootstrap), never tightened on an existing app as a side effect of this feature; Express Zod, passing the parse result onward, never `req.body`
- Multi-step writes in one `$transaction` / `dataSource.transaction`, bounded (lock, statement, and idle timeouts; Prisma `maxWait` + `timeout`)
- **No network I/O inside a transaction** - no HTTP call, no `queue.add`, no mailer; capture the scalars inside, act after commit
- Design approved before code (STEP 3 says when a run may proceed without a live approval)

## Workflow

### STEP 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### STEP 2 - Detect and Gather

Use skill: `stack-detect`. Record Framework, ORM, Database, package manager, and test runner; read the Express major and the NestJS HTTP adapter (Express or Fastify - it decides the raw-body mechanism) from `package.json`, and the layout (feature modules vs layered folders) from `src/`.

| Detected | Action |
| -------- | ------ |
| Not Node | Stop: name the detected stack; this workflow is Node-only |
| JavaScript, no `tsconfig.json` | Proceed with JSDoc types and Zod at the edges; record it under Assumptions |
| Framework `unknown` / other (Fastify, Koa) | Apply the patterns through that framework's own raw-body, error-handler, and async mechanisms; record it under Assumptions |
| ORM other (Drizzle, Sequelize) | Generic transaction and query bindings; record it under Assumptions |
| Database MySQL / SQLite | The idempotency claim is a plain `INSERT` in its own transaction catching 1062 / `SQLITE_CONSTRAINT` (never `INSERT IGNORE`); DDL per `node-migration-safety`'s engine column; STEP 4-5's PostgreSQL bindings do not apply |
| Database unknown | Assume PostgreSQL (`node-migration-safety`); record it under Assumptions |

Extract from the request first; ask only for what is missing: the feature and its primary use case; entities, fields, relationships, constraints; external integrations; background jobs or events; who may do what; status transitions; idempotency needs; webhook endpoints; for bulk reads or writes, the volume and format.

**Ask, or assume and record - the split is by blast radius.** Ask when a wrong answer is expensive to undo: entities and relationships, who is authorized, money or an external side effect, legal status transitions. Assume when a wrong answer is a cheap edit, and record it under Assumptions: page sizes, column names, timeout values, file formats. Never invent a field or a relationship; a referenced model that does not exist is a question (create it, or reference by id). A high-blast-radius question with no answer is an Open Question.

Check the Edge Cases list now and again before presenting the design.

### STEP 3 - Design (Approval Gate)

Load the owners of every decision the design settles - once, here:

- Use skill: `node-nestjs-patterns` (NestJS) or `node-express-patterns` (Express), and `node-prisma-patterns` or `node-typeorm-patterns`
- Use skill: `backend-api-guidelines` - endpoint conventions
- Use skill: `node-security-patterns` - authorization, privilege fields, webhook signatures
- Use skill: `backend-transaction-patterns`, then `node-transaction-patterns` - boundaries, bounds, dispatch
- Use skill: `backend-idempotency` - keys and replay
- Use skill: `node-exception-handling` - error hierarchy and translation
- Use skill: `node-bullmq-patterns` - when there is a job or event
- Use skill: `ops-resiliency`, then `node-http-client-patterns` - when there is an external integration
- Use skill: `node-migration-safety` - when the design adds or changes a table
- Use skill: `node-connection-pool-sizing` - when a worker or a new process is added

Where two loaded atomics disagree, this workflow settles it (Rules, STEP 3, STEPS 5-6) and names the atomic it overrides. `node-prisma-patterns`' create-then-catch-`P2002`-after-rollback is a valid claim for a database-local effect - its `409 / 202` answer is overridden: a duplicate of a committed create replays the stored response, and a fingerprint mismatch is 422. STEP 5's rows-affected claim is required when the claim shares a transaction with statements that must run after it.

**Envelope precedence.** The atomics loaded here emit their own blocks; fold their content into the design block and the Output Format slots, and emit none of their envelopes.

Present a file tree plus the design block (every slot filled or `none`):

```markdown
**Endpoints:** {method, path, status codes, request / response DTO, pagination, idempotency - one line per route}

**Schema:** {tables, columns, indexes on FK and filter columns, status representation, the (scope, key) unique index backing idempotency}

**Authorization:** {who may call each route; object and tenant scoping in the query}

**Transaction boundaries:** {per transaction: what it writes, what runs before it opens, what is deferred until after commit, its bounds}

**Idempotency:** {per non-idempotent operation, one line each: key (required - 400 when absent), scope, store, unique constraint, request fingerprint (a hash of the body as received; 422 on mismatch), TTL, and the vendor key it derives | none}

**Side effects:** {per effect: post-commit | outbox + relay | call-then-record; its guarantee; what a crash between commit and dispatch leaves; consumer idempotency (jobId + retention); the sweeper | none}

**Outbound calls:** {per vendor call: deadline, retry owner, vendor idempotency key, breaker | none}

**Jobs:** {per queue: attempts + backoff, non-retryable errors, retention, concurrency vs the pool | none}

**Error model:** {the hierarchy (the project's existing one when present - new code extends it - else `node-exception-handling`'s AppError), response body shape (RFC 9457 or the project's documented envelope - either overrides `node-exception-handling`'s `{ error, message }` body)}

**Webhooks:** {raw body, signature scheme, freshness window, dedupe key (event / delivery id), ack status, route placement relative to global auth | none}

**New dependencies / infrastructure:** {packages and services the project does not have | none}

**Assumptions:** {each low-blast-radius answer guessed, and what changes if it is wrong | none}

**Decisions:** {each choice the request did not dictate, with its reason | none}

**Open Questions:** {each unanswered high-blast-radius question | none}

**Existing defects:** {defects found in code this feature touches, each fixed here or deferred with its reason | none}
```

**The gate.** With the user present, wait for approval; an approval that changes the design is re-presented. A design-only request stops after approval. With no user reachable (non-interactive run):

- Any Open Question -> stop here, with `## Design` marked `(unapproved - open questions)`.
- Otherwise proceed, `## Design` marked `(not reviewed - non-interactive run)`.

A run that stops here emits the design-only output: Files, Endpoints, and Migration describe the planned change; `## Code` is `none`; Tests list the planned tests under `Not written`; Validation says nothing ran.

A dependency or service discovered after the gate (Redis for BullMQ, object storage, a resilience library) returns to this step; the gate rule applies again - a run that cannot re-present the design records the addition in Decisions and New Dependencies and says so. Never add a runtime dependency silently.

### STEP 4 - Data Model

Use skill: `node-migration-safety`.

- **Prisma:** models with `@relation`, `@@index`, `@@unique`. Generate the migration against a disposable local database (`prisma migrate dev --create-only`, or `prisma migrate diff ... --script`), review and hand-edit the SQL, and apply to any shared environment only with `prisma migrate deploy`. Never `migrate dev` (resets on drift) or `migrate reset` (always drops) against a shared database.
- **TypeORM:** `@Entity`, `@Column`, `@Index`, relations; unique keys via `@Column({ unique: true })` or `@Index([...], { unique: true })`. `migration:generate` diffs metadata and cannot emit `CONCURRENTLY`, `NOT VALID` / `VALIDATE CONSTRAINT`, or backfills - use `migration:create` and hand-write those.
- **Status columns:** a native enum on a new column or a new table. An existing `varchar` status column stays `varchar` with a hand-written `CHECK (...) NOT VALID`, then `VALIDATE CONSTRAINT` in a later migration - its own transaction, a separate Prisma migration directory (Prisma cannot express a CHECK - edit the generated SQL). Extend an existing enum per `node-migration-safety` (PostgreSQL).
- **Idempotency:** a unique index on (scope, key) - tenant or user plus key; built `CONCURRENTLY` when added to an existing large table. That index is the dedup mechanism.
- **Money:** new money columns follow the ORM atomic (Prisma `Decimal` / integer minor units, never `Float`; a TypeORM `decimal` reads back as `string`, typed so) even beside a legacy sibling column; the mismatch goes in Decisions.

### STEP 5 - Service Layer

Use skill: `node-typescript-patterns`. `@Injectable()` service (NestJS) or plain class (Express). Map models to response DTOs before returning.

- **Status transitions:** validate against a `VALID_TRANSITIONS` map, then write with the prior state as a guard - Prisma `updateMany({ where: { id, status: from }, data: { status: to } })` (`count`), TypeORM `createQueryBuilder().update(Order).set({ status: to }).where("id = :id AND status = :from", { id, from }).execute()` (`affected`); zero rows -> re-read by id within scope: absent -> 404, moved on -> 409 - or lock the row `FOR UPDATE` first. A map check followed by an unguarded write loses updates under concurrency.
- **Idempotency claim** (per `backend-idempotency`): a conflict-tolerant insert, branching on rows affected - raw `INSERT ... ON CONFLICT (scope, key) DO NOTHING`, Prisma `createManyAndReturn({ data: [claim], skipDuplicates: true })` (5.14+; an empty array means lost - older versions use `createMany` and re-read), TypeORM `createQueryBuilder().insert().values(claim).orIgnore().execute()`, lost when `raw.length === 0` (PostgreSQL; these bindings are PostgreSQL's - STEP 2 gives MySQL / SQLite). Prisma's `skipDuplicates` names no conflict target and absorbs any unique violation, so keep the claim table single-constraint. A raw duplicate-key error (`P2002` / `23505`) aborts the enclosing PostgreSQL transaction, so catching it and reading the row only works after that transaction rolled back. Never look-up-then-create.
- **Losing the claim:** a loser first compares the request fingerprint - a mismatch is 422 in any state. When the claim committed `processing` ahead of an external call, a loser answers `409` with `Retry-After` while the winner runs, and the recorded outcome once it settles (a key first answered 202 stays `processing` until the outcome settles, then replays the settled outcome); a sweeper resolves rows stuck `processing`, and belongs in the Side effects slot. When the claim commits with a database-local write, a loser's insert waited for the winner, so a count of 0 means settled: roll back and replay the stored outcome in a new transaction.
- **Side effects:** post-commit dispatch (`queue.add` after the transaction resolves, ids only) when a lost dispatch is acceptable or self-healing; a transactional outbox when delivery must happen and nothing else would notice a loss (a contractual notification, provisioning); call-then-record when the call's result is written back (a charge and its reference): a pending row committed, the call outside any transaction with the vendor's idempotency key, the result recorded in a second transaction, and a sweeper for rows left pending. A definite vendor decline after a local write committed (credit reserved, balance held) takes a named compensating write in that second transaction, releasing what the first held.
- **External calls** (per `node-http-client-patterns`): a total deadline, errors classified, behind an interface for tests. A timeout or 5xx after the request was sent is an unknown outcome: retry with the same vendor idempotency key within its lifetime; without one, or past it, reconcile with a lookup before any retry.

### STEP 6 - API Layer

NestJS, per `node-nestjs-patterns` (loaded at STEP 3): module, controller, guards, DTOs; `@HttpCode(204)` on DELETE; a status chosen per request (201 new, 202 pending, the stored status on replay) through `@Res({ passthrough: true }) res; res.status(n)`, since `@HttpCode` is static; paginated lists. Express, per `node-express-patterns`: router, handler, Zod middleware; on Express 4 every async handler wrapped (Express 5 forwards rejections natively).

Domain errors map to HTTP in one place - the global exception filter (NestJS) or the terminal error middleware (Express) - each row an error class in the Error model:

| Domain Error | HTTP |
| ------------ | ---- |
| Validation, missing `Idempotency-Key` | 400 |
| Unauthenticated | 401 |
| Role or permission denied on the route | 403 |
| Not found, or an object outside the caller's scope | 404 |
| Conflict, key in flight | 409 (+ `Retry-After` when in flight) |
| Invalid transition, key reused with a different body | 422 |
| Rate limited (emitted by the rate-limit middleware) | 429 + `Retry-After` |
| Upstream declined (card refused) | 402 or 409, as the Error model states - a business outcome, never a 5xx (overrides `node-exception-handling`'s 400 mapping; 402 is outside `backend-api-guidelines`' status set - name it) |
| External timeout / upstream down / upstream rate limit | 503 (outside `backend-api-guidelines`' set - name it) |

A creating POST returns 201; accepted work whose outcome is still pending (a payout awaiting the vendor) returns 202 with the resource's status; an outcome settled synchronously (a vendor rejection before acceptance) answers with its settled status in the body of the 201. A replayed idempotency key returns the stored response - status and body as first sent (per `backend-idempotency`; this overrides `node-testing-patterns`' 200-on-replay example).

**Webhook receivers answer the sender, not a user.** A failed signature or stale timestamp is 401 (per `node-security-patterns`; this overrides the 400 in the framework atomics' examples). Already-applied and unknown-type events are 2xx no-ops. An event that is not applicable yet (out of order) is parked durably before the 2xx, or answered 5xx when the provider retries (Stripe, Slack) - a provider that does not retry (GitHub) is always parked; never dropped. Reserve other non-2xx answers for genuine "retry me" faults; a 4xx on a business outcome makes the provider redeliver for days. Placement: NestJS - `NestFactory.create(AppModule, { rawBody: true })` (Express or Fastify adapter), `req.rawBody`, `@Public()` to leave the global guard, `@HttpCode(200)`; Express - `express.raw()` on the route, mounted before `express.json()` and outside the auth mount.

### STEP 7 - Tests

Use skill: `node-testing-patterns`. Unit (mocked collaborators), integration (repository or service against a real database), endpoint / E2E (Supertest through the app with production's pipes and guards). Cover the happy path, validation, not-found and out-of-scope, conflict, and edge cases. State machines: every valid and invalid transition, plus a concurrent transition. Webhooks: valid, invalid, missing, stale, and replayed signature; an out-of-order event. Idempotency: concurrent duplicates produce one side effect - with a processing-first claim the loser gets `409` while the winner runs and the stored response after; with a database-local claim the loser gets the replayed stored response; a changed body gets 422. A project convention the testing atomic rules out (SQLite standing in for PostgreSQL) is overridden in the new tests and recorded in Decisions. A test that cannot be written yet is listed under Tests `Not written`, with the reason.

### STEP 8 - Validate

Run build, test, lint, and typecheck through the project's own scripts and package manager (`npm run` / `pnpm` / `yarn` / `bun run`); never swap runners - a Jest suite runs under Jest. Fix failures before reporting done. When the tree cannot run (design-only output, no installed dependencies, no database), say so on the `Validation` line.

## Edge Cases

Checked at STEP 2 and before presenting the design:

- **Vague input:** targeted questions in STEP 2; never guess fields or relationships
- **No persistence:** skip STEP 4
- **Existing entity:** read and extend, never recreate; reuse existing DTOs and services
- **Referenced entity missing:** an Open Question - create it, or reference by id
- **Webhook-only:** no CRUD; a dedicated receiver per STEP 6
- **Bulk write:** Prisma `createMany` in ~1000-row chunks; TypeORM `insert([...])` for pure inserts (`save` only when upserting entities); a size limit on the input
- **Bulk read / export:** keyset pagination and streaming (`stream.pipeline`, async generators); never buffer an unbounded result

## Output Format

Every slot is filled or the literal `none`; a webhook-only or read-only feature leaves several `none`, and that is the expected shape. `## Code` is the deliverable - every file in `## Files`, in dependency order - and the sections around it describe it without restating it; its blocks use the file's language (`typescript`, `prisma`, `sql`). A webhook receiver lists its route in `## Endpoints` with `raw body` as the request. `## Endpoints` and `## New Dependencies / Infrastructure` record what was built; the Design block records what was planned.

```markdown
## Design   {no suffix when approved | ` (unapproved - open questions)` | ` (not reviewed - non-interactive run)`, per the STEP 3 gate}

{the STEP 3 block as approved or presented, Assumptions / Decisions / Open Questions included}

## Files

| File | New / Modified | Layer | Purpose |
| ---- | -------------- | ----- | ------- |

## Code

{every file in the table, each under its path as a bold label: schema and migration, DTOs, service, controller or router, module wiring, processors, tests | none}

## Endpoints

| Method | Path | Request | Response | Status | Pagination | Idempotency |
| ------ | ---- | ------- | -------- | ------ | ---------- | ----------- |

## Migration

{file names and what each creates; deploy order and the compatibility invariant each step keeps; the runner (one place per release - a Job, a pre-deploy task) and command; the lock timeout each write migration sets; how to verify it; how to roll it back | none}

## Tests

| Lane | Count | Covers |
| ---- | ----- | ------ |
| Unit | {n} | {outcomes} |
| Integration | {n} | {persisted state, constraints} |
| E2E | {n} | {journeys} |

**Infrastructure:** {database provisioning and isolation, runner config the tests need | none}

**Not written:** {each test deferred, and why | none}

## New Dependencies / Infrastructure

{packages and services added | none}

## Validation

{build / test / lint / typecheck results, or why they could not run}
```

`Assumptions`, `Decisions`, and `Open Questions` live in the Design block only. The test for which one an entry belongs to is what a wrong entry costs: a wrong Assumption is a cheap edit, a wrong Decision is rework, an unanswered Open Question can make the feature unsafe. Approval does not move an entry between them.

## Self-Check

Mark a line N/A when the feature does not reach it - a read-only export has no transaction, no idempotency key, and no state machine.

- [ ] STEP 1: `behavioral-principles` loaded
- [ ] STEP 2: stack detected and the unknown-stack table applied; high-blast-radius questions asked, low-blast-radius answers recorded as Assumptions; Edge Cases checked
- [ ] STEP 3: owning atomics loaded once; design block complete, Existing defects included; approval obtained, or the non-interactive gate rule applied (stop on any Open Question); design-only requests stop after approval
- [ ] STEP 4: migration safe for the column's current state and engine; `CHECK ... NOT VALID` validated in a later migration; (scope, key) unique index backs any idempotency key
- [ ] STEP 5: transitions written with a prior-state guard and a discriminating re-read; claim conflict-tolerant with fingerprint, in-flight, and settled handled; each side effect on the right mechanism with its sweeper; transactions bounded; no network I/O inside one
- [ ] STEP 6: DTOs everywhere; errors mapped through the table (403 vs 404 split); replay returns the stored response; webhooks 401 on a bad signature, out-of-order events parked, placed outside global auth with the raw body
- [ ] STEP 7: three lanes; invalid and concurrent transitions; webhook signature cases; concurrent duplicates; unwritten tests listed
- [ ] STEP 8: validation run and reported honestly
- [ ] Every Output Format slot filled or `none`; atomic blocks folded per Envelope precedence

## Avoid

- Code before the STEP 3 gate is satisfied
- Exposing ORM models; `any` in DTOs; a missing `await`; unpaginated lists
- Look-up-then-create as an idempotency strategy, or catching a duplicate-key error inside the transaction it aborted
- A status transition checked in memory and written without a guard
- A 4xx from a webhook receiver for a business outcome, or a 2xx that drops an out-of-order event
- `prisma migrate dev` or `migrate reset` against a shared database
