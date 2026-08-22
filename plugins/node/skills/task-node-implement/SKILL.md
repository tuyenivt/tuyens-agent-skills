---
name: task-node-implement
description: End-to-end Node.js / TypeScript feature implementation for NestJS or Express: data model, services, controllers, DTOs, middleware, Jest tests.
agent: node-engineer
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Implement Node.js Feature

## When to Use

End-to-end Node.js/TypeScript feature work: migration + model + service + controller + DTOs + tests in one pass for NestJS or Express.

Not for: single-file edits (edit directly), bugfixes, frontend.

## Rules

- TypeScript strict; no `any`; explicit return types on public methods; all async operations awaited
- DTOs for every request/response; never expose Prisma models or TypeORM entities
- Constructor injection (NestJS `@Injectable()`; Express manual DI)
- Validation on all inputs: NestJS `class-validator` + `ValidationPipe({ whitelist: true, transform: true })`; Express Zod
- Multi-step writes use Prisma `$transaction` or TypeORM `DataSource.transaction`
- **No network I/O inside a transaction** - no HTTP call, no `queue.add`, no mailer. Capture the scalars you need inside; dispatch after commit
- Each step completes before the next; design approved before code

## Workflow

### STEP 1 - DETECT AND GATHER

Use skill: `stack-detect`. Confirm Node.js/TypeScript and identify NestJS vs Express, Prisma vs TypeORM, package manager, test runner, layout.

Extract from the request first, then ask only for what is missing. Do not re-ask what the request already answers: feature description and primary use case; entities, fields, relationships, constraints; external integrations; background jobs or async events; authentication / authorization; status transitions; idempotency requirements; webhook endpoints (signature validation, raw body); for anything that reads or writes in bulk, the expected volume and output format.

**Ask, or assume and record - the split is by blast radius.** Ask when a wrong answer would be expensive to undo: entities and their relationships, who is authorized, whether money or an external side effect is involved, the legal status transitions. Assume when a wrong answer is a cheap edit and record it under `Assumptions`: page sizes, column names, timeout values, file formats. Never invent a field or a relationship.

### STEP 2 - DESIGN (APPROVAL GATE)

Use skill: `node-nestjs-patterns` (NestJS) or `node-express-patterns` (Express) for API design. Use skill: `node-prisma-patterns` or `node-typeorm-patterns` for the data layer. Use skill: `backend-api-guidelines` for REST conventions.

Three slots below are decided here and merely implemented later, so load their owners now rather than at STEP 4: `backend-transaction-patterns` then `node-transaction-patterns` for the boundary, `backend-idempotency` for the key, `node-bullmq-patterns` for dispatch. Where a loaded atomic's rule contradicts this workflow, this workflow wins - `node-prisma-patterns` ships a look-up-then-create idempotency example that STEP 4 forbids.

Present a file tree plus this block, then wait for approval:

```markdown
**Endpoints:** method, URI, status codes, request/response DTO

**Schema:** tables, columns, indexes on FK + filter columns, status representation, unique index backing idempotency

**Transaction boundaries:** what opens a transaction, what it writes, what runs before it opens, and what is deferred until after commit - the three are different designs and the distinction is the point

**Error model:** NestJS exceptions or the custom AppError hierarchy

**Idempotency:** the key, where it is stored, the unique constraint enforcing it (or `N/A`)

**Dispatch points:** which commit triggers which job, and post-commit vs outbox with the reason

**Webhooks:** raw body, signature validation, route placement relative to global auth (or `N/A`)

**New dependencies / infrastructure:** packages and services this adds that the project does not have (or `none`)
```

**Envelope precedence.** Atomics loaded below emit their own Output Format blocks. Fold their content into the slots here and into the final Output Format; do not append their envelopes as separate sections. Where an atomic's block carries a choice no slot holds, it goes under `Decisions` - `Assumptions` is only for answers you guessed.

Several atomics declare a prerequisite of their own: `node-transaction-patterns` requires `backend-transaction-patterns` first, and `node-http-client-patterns` requires `ops-resiliency` first. Load the stack-agnostic contract before the Node binding in both cases.

### STEP 3 - DATA MODEL

Use skill: `node-migration-safety`.

- **Prisma:** models in `schema.prisma` with `@relation`, `@@index`, `@unique`. Generate with `prisma migrate dev --create-only`, review the SQL, then apply. Never run bare `prisma migrate dev` or `migrate reset` against a database you did not create for this task - both can drop data on drift.
- **TypeORM:** `@Entity` + `@Column` + `@Index` + relations; unique keys are `@Column({ unique: true })` or `@Index(..., { unique: true })` (`@unique` is Prisma-only). `typeorm migration:generate` diffs entity metadata; it cannot emit `CONCURRENTLY`, `NOT VALID` / `VALIDATE CONSTRAINT`, or backfills - use `migration:create` and hand-write those.
- **Status columns:** a native enum only on a new column. Converting an existing `varchar` in place rewrites the table - keep `varchar` plus a `CHECK` constraint, or run the expand-then-contract path in `node-migration-safety`.
- **Idempotency:** a unique index on the key column. That index is the dedup mechanism, not a convenience.

### STEP 4 - SERVICE LAYER

Use skill: `node-typescript-patterns`. Use skill: `node-transaction-patterns` for the boundary contract and `node-http-client-patterns` for any outbound call - both before writing this layer, not after. `@Injectable()` service (NestJS) or plain class (Express). Map entities to response DTOs before returning.

- **Status transitions:** validate against a `VALID_TRANSITIONS` map before persisting; throw on invalid.
- **Idempotency:** Use skill: `backend-idempotency`. Claim the key with a conflict-tolerant insert and branch on rows-affected: raw `INSERT ... ON CONFLICT (key) DO NOTHING`, or Prisma `createMany({ data: [claim], skipDuplicates: true })`, which returns `{ count }`. Two Prisma caveats: it emits `ON CONFLICT DO NOTHING` with no conflict target, so it absorbs a violation of any unique constraint on that table - keep the claim table single-constraint - and it returns no rows, so the winner re-reads the claim with `findUnique` to get its id. A raw duplicate-key error (`P2002` / `23505`) aborts the enclosing PostgreSQL transaction, so "catch it and read the row" does not work inside the transaction that carries the business write. Never look-up-then-create: two concurrent retries both miss the lookup and both perform the side effect.

  The claim row carries a status. Losing the race means the work is **in flight**, not done: return `409` or `202` while the winner is still processing, and return the recorded outcome once it is settled. A key with external side effects also needs a sweeper that resolves rows stuck in flight - without one the feature is incomplete, and the sweeper belongs in the design's `Dispatch points`.
- **Background jobs / events:** Use skill: `node-bullmq-patterns`. Enqueue after the transaction commits; pass IDs only. Choose post-commit dispatch when a lost dispatch is self-healing (the caller retries, or a sweeper re-finds the row); choose a transactional outbox when the side effect must happen and nothing else would notice it was lost - billing, provisioning, the only notification a user gets.
- **External API calls:** timeout-wrapped, errors classified, defined as an interface for testability. A timeout or 5xx after the request body was flushed is ambiguous, not failed - reconcile before retrying a charge.
- **Missing infrastructure:** when the design needs a service the project does not have (Redis for BullMQ, object storage, a mail transport), it belongs in STEP 2's `New dependencies / infrastructure` slot. Discovering it here means the design was incomplete - return to STEP 2, add it, and re-confirm before writing code. Never silently add a runtime dependency.

### STEP 5 - API LAYER

NestJS: Use skill: `node-nestjs-patterns`. Module + controller + guards + DTOs with `class-validator`. `@HttpCode(204)` on DELETE. Paginated list with query params.

Express: Use skill: `node-express-patterns`. Router + controller + Zod middleware. Express 4: async handler wrapper on every route (Express 5 forwards rejections natively).

Map domain errors to HTTP via the global exception filter (NestJS) / terminal error middleware (Express). Canonical contract: Use skill: `node-exception-handling` (AppError hierarchy, retryable flag, ORM error translation, Sentry capture-once, BullMQ retry propagation).

| Domain Error | HTTP |
|---|---|
| Validation | 400 |
| Unauthenticated (no / bad credentials) | 401 |
| Authenticated but not permitted | 403 |
| Not found | 404 |
| Conflict | 409 |
| Invalid transition | 422 |
| Rate limited | 429 + `Retry-After` |
| Upstream declined (card refused, quota) | 402 or 409 - a business outcome, not a 5xx |
| External timeout / upstream down | 503 |

A creating POST returns 201. A POST that replays an idempotency key returns the original outcome with 200, not a second 201.

**This table is for client-facing routes.** A webhook receiver answers the *sender*, not a user: return 2xx once the event is durably recorded, and handle unknown events, out-of-order arrivals, and already-applied transitions as 2xx no-ops. Reserve non-2xx for a failed signature (400) and for genuine "retry me" faults (5xx) - a 4xx on a business outcome makes the provider redeliver for days on an event that can never succeed.

For outbound HTTP to third parties, `node-http-client-patterns` (loaded in STEP 4) owns the timeout / retry / wrapper contract.

For webhooks: Use skill: `node-security-patterns` for raw-body reading, signature comparison, and timestamp freshness. Register the route outside the global auth chain, before any JSON body parser.

### STEP 6 - TESTS

Use skill: `node-testing-patterns`. Three lanes: unit (mocked deps), integration (service or repository against a real DB), E2E (Supertest through the app). Cover happy path, validation, not-found, conflict, edge cases. For state machines, test every valid + invalid transition. For webhooks, test valid / invalid / missing / replayed signature. For idempotency, test that concurrent duplicates produce one side effect and the same response.

### STEP 7 - VALIDATE

Run build + test + lint + typecheck via the project's own scripts and package manager detected in STEP 1 (`npm run` / `pnpm` / `yarn` / `bun`). Do not swap test runners - a Jest suite runs under Jest, not `bun test`. Fix failures before reporting done. When the working tree cannot run (design-only invocation, no installed dependencies), say so on the `Validation` line rather than claiming a pass.

## Edge Cases

Check this list at STEP 2, before presenting the design - each entry changes the shape of what STEPS 3-6 produce.

- **Vague input**: ask targeted questions in STEP 1; never guess fields or relationships
- **No persistence**: skip STEP 3; service + controller only
- **Existing entity**: read and extend rather than recreate; check existing DTOs / services
- **Referenced entity missing**: ask whether to create it or use an ID reference
- **Webhook-only**: skip CRUD; dedicated controller with raw body + signature validation
- **Bulk write**: `createMany` / chunked `save` + size-limit validation
- **Bulk read / export**: keyset pagination + streaming (`stream.pipeline`, async generators); never buffer an unbounded result set

## Output Format

Slots marked `(or none)` take the literal `none` when they do not apply - a webhook-only or read-only feature leaves several empty, and that is the expected shape, not an omission.

```markdown
## Design

[the approved STEP 2 block, as approved]

## Files

| File | New / Modified | Layer | Purpose |
| ---- | -------------- | ----- | ------- |

## Code

[every file in the table above, each under its path as a bold label, as fenced TypeScript / SQL blocks in dependency order: schema and migration, DTOs, service, controller or router, module wiring, processors, tests. This is the deliverable; the sections around it describe it and must not restate it. `none` on a design-only invocation.]

## Endpoints

| Method | Path | Request | Response | Status |
| ------ | ---- | ------- | -------- | ------ |

_(or `none` - a webhook receiver lists its route here with `raw body` as the request.)_

## Migration

[file names + what they create: tables, indexes, enums, constraints; deploy ordering and the compatibility invariant each step preserves, when more than one] _(or `none`)_

## Tests

| Lane | Count | Covers |
| ---- | ----- | ------ |
| Unit | {n} | [outcomes] |
| Integration | {n} | [persisted state, constraints] |
| E2E | {n} | [journeys] |

## New Dependencies / Infrastructure

[packages and services this adds that the project did not have] _(or `none`)_

## Decisions

[each choice the request did not dictate, with its reason: outbox vs post-commit, varchar+CHECK vs enum, the API conventions the atomics settled. The test is what a wrong entry costs: a `Decision` you got wrong is rework, an `Assumption` you got wrong is a wrong feature. Approval at STEP 2 does not move an entry between them.]

## Assumptions

[each low-blast-radius answer assumed rather than confirmed, and what would change if it is wrong] _(or `none`)_

## Open Questions

[each high-blast-radius question STEP 1 forbids assuming that is still unanswered - authorization, money, external side effects, legal transitions - with the interim choice made to keep going and what it blocks] _(or `none`)_

## Validation

[build / test / lint / typecheck results, or why they could not run]
```

## Self-Check

Mark a line N/A when the feature does not reach it - a read-only export has no transaction, no idempotency key, and no state machine, and saying so beats ticking a box that was never exercised.

- [ ] `behavioral-principles` loaded; stack detected (Step 1); high-blast-radius questions asked, low-blast-radius answers recorded as Assumptions
- [ ] Edge Cases checked at Step 2; any that applies is reflected in the design
- [ ] Design block presented and approved before any code (Step 2)
- [ ] Migration safe for the column's current state; unique index backs any idempotency key (Step 3)
- [ ] Transaction and HTTP-client contracts loaded before the service layer, each after its stack-agnostic prerequisite; no network I/O inside a transaction; idempotency claimed with a conflict-tolerant insert that distinguishes in-flight from settled, plus a sweeper where there are external side effects; jobs dispatched post-commit or via outbox with the choice stated (Step 4)
- [ ] DTOs everywhere, no ORM entities on the wire; errors mapped through the table; webhook raw body + signature outside global auth (Step 5)
- [ ] Tests cover all three lanes; state machines cover invalid transitions; idempotency covers concurrent duplicates (Step 6)
- [ ] Validation run and reported honestly, including when it could not run (Step 7)
- [ ] Every Output Format slot filled or explicitly `none`, including `## Code`; atomic envelopes folded in, not appended; `Decisions` and `Assumptions` kept distinct

## Avoid

- Generating code before design approval
- Exposing ORM entities; `any` in DTOs; missing `await`; unpaginated lists
- Look-up-then-create as an idempotency strategy, or catching a raw duplicate-key error inside the transaction it just aborted
- Returning 4xx from a webhook receiver for a business outcome - the provider redelivers for days
- Skipping idempotency on payment / external-callback features
- Consuming the body before signature validation on webhook endpoints
- Running `prisma migrate dev` without `--create-only`, or `migrate reset`, against a shared database
