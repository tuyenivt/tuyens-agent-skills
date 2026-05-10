---
name: task-node-review-perf
description: Node.js performance review: Prisma/TypeORM N+1, event-loop blocking, async traps, connection pool, BullMQ throughput, JSON serialization.
agent: node-performance-engineer
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, performance, prisma, typeorm, bullmq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Node.js Performance Review

## Purpose

Node.js-aware performance review that names Prisma `include` / `select` / `findMany`, TypeORM relation strategies, event-loop discipline, NestJS interceptor / pipe overhead, BullMQ task design, and Prisma migrate / TypeORM migration safety idioms directly instead of routing through the generic backend adapter. Produces findings with measured or estimated impact (latency, throughput, query count, event-loop lag) and concrete fixes using TypeScript strict-mode patterns.

This workflow is the stack-specific delegate of `task-code-review-perf` for Node.js. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a NestJS or Express PR or branch for performance regressions
- Investigating a slow endpoint, BullMQ job, or scheduled cron
- Pre-merge perf pass on changes touching ORM queries, async boundaries, BullMQ dispatch, or event-loop-blocking calls
- Quarterly N+1 / pool-sizing / async-correctness sweep against APM-flagged endpoints

**Not for:**

- General Node.js code review (use `task-code-review` or `task-node-review`)
- Security review (use `task-code-review-security` or `task-node-review-security`)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-node-implement`)

## Depth Levels

| Depth      | When to Use                                             | What Runs                                   |
| ---------- | ------------------------------------------------------- | ------------------------------------------- |
| `quick`    | Single endpoint or repository ("is this query ok?")     | Steps 4 + 5 only; ORM hotspots + migrations |
| `standard` | Default - full Node.js perf review                      | All steps                                   |
| `deep`     | Profiling-driven review with clinic.js / 0x / OTel data | All steps + capacity guidance and load plan |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                        | Meaning                                                                                               |
| --------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-node-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-node-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-node-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Node.js / TypeScript. If invoked as a delegate of `task-code-review-perf` or as a subagent of `task-node-review` (parent already detected Node), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Node, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Node 20+ and TypeScript strict mode.

Then detect the web framework:

- `nest-cli.json` present / `@nestjs/*` in `package.json` deps → **NestJS**
- `express` in `package.json` deps without `@nestjs/*` → **Express**
- Both present → ask the user which surface this PR targets; do not guess

The framework decision drives which checklists in Step 4 apply. Default ORM mapping: NestJS → Prisma; Express → TypeORM. If the project's repo context file overrides this, honor it. Record `Framework: NestJS | Express | mixed` and `ORM: Prisma | TypeORM | mixed` for the Summary block.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Performance Surface

Before applying the checklists, open the files that govern query and concurrency behavior so impact estimates ground in real code:

**NestJS / Prisma surface:**

- Every changed Prisma `schema.prisma` model (relations, indexes, `@@index`, `@db.*` types)
- Every changed repository / service module (`prisma.<model>.findMany`, `findUnique`, `findFirst`, `include`, `select`, `where`, `orderBy`)
- Every changed controller / route handler (sync vs async, `@UseInterceptors`, `@UseGuards`, response DTO mapping)
- Every changed DTO with non-trivial `class-validator` decorators or `class-transformer` `@Transform` logic
- `app.module.ts` / `prisma.service.ts` / config module for `connectionLimit`, `poolTimeout`, Prisma `log` settings
- Prisma migrations under `prisma/migrations/`
- BullMQ producers and processors; `@Processor` classes; queue config

**Express / TypeORM surface:**

- Every changed TypeORM entity (`@Entity`, `@OneToMany`, `@ManyToOne`, `@Index`, `eager`, `cascade`)
- Every changed repository / data-access module (`repository.find`, `findOne`, `createQueryBuilder`, `relations`, `where`)
- Every changed Express route / middleware - look for sync handlers wrapping async work without proper error forwarding (`asyncHandler` wrappers)
- Every changed DTO / schema (Zod, Joi, class-validator) with non-trivial validators
- `data-source.ts` / `ormconfig.json` / config for `poolSize`, `extra.max`, `synchronize` (must be `false` in prod)
- TypeORM migrations under `src/migrations/`
- BullMQ producers and processors

For each finding produced later, cite a real `file:line`. If the diff is small but ripples through code that is not in the diff (a new endpoint calling an existing repository whose query does an N+1), read the unchanged file too - the regression lives there even though the line count attributes it to the new caller.

### Step 4 - ORM Hotspots (Prisma or TypeORM)

> If `ORM: Prisma` was recorded in Step 1, **skip the TypeORM subsection entirely**; likewise skip Prisma on TypeORM-only projects. The bifurcation exists for mixed codebases - on monoglot projects it should be one read, not two.

Canonical patterns live in `node-prisma-patterns` (Prisma) and `node-typeorm-patterns` (TypeORM). This step is the **review-scoped scan** - flag deviations against the canonical owner; do not re-derive idioms here.

**Review-scoped scan** (Prisma or TypeORM, branching on `ORM:`):

- [ ] **N+1**: relation traversal after a list query is eager-loaded - Prisma `include` / `select`; TypeORM `relations: [...]` or `leftJoinAndSelect` (avoid `eager: true` on collections - cartesian explosion). Multi-level N+1 (`order.items.product`) chained through one query, not nested loops
- [ ] **Overfetch**: payload bounded via projection - Prisma `select`, TypeORM `find({ select: [...] })` - default returns all columns including large `text` / `bytea`
- [ ] **Missing indexes for `where` / `orderBy` / `groupBy` columns** - flag any predicate / sort column without a backing `@@index` (Prisma) / `@Index` (TypeORM) or migration
- [ ] **Unbounded reads**: list endpoints use `take` + cursor pagination, not bare `findMany` / `find()`
- [ ] **Per-row loops** in place of bulk operations - `createMany` / `updateMany` (Prisma); `repository.insert([...])` / QueryBuilder `.insert().values([...])` (TypeORM)
- [ ] **Existence checks**: `findFirst({ where, select: { id: true } })` / `repository.exist({ where })` over fetch-then-length
- [ ] **Connection pool sizing documented**: Prisma `connection_limit` / TypeORM `extra.max` × replica count ≤ DB `max_connections`
- [ ] **Prod-unsafe config**: TypeORM `synchronize: true` is a Critical finding; Prisma `log: ['query']` in prod is High (every query at INFO)

### Step 5 - Indexes and Migrations

Use skill: `node-migration-safety` for safe-migration checks on any change in `prisma/migrations/` (Prisma) or `src/migrations/` (TypeORM).

- [ ] Every column referenced in `where` / `orderBy` / `groupBy` is backed by an index
- [ ] Composite indexes match the leftmost-prefix pattern of the queries
- [ ] Foreign keys have indexes (PostgreSQL does not auto-index FKs)
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL) - Prisma via `prisma migrate diff` + manual SQL in migration file with `-- CreateIndex CONCURRENTLY`; TypeORM via `queryRunner.query('CREATE INDEX CONCURRENTLY ...')`
- [ ] **`SET lock_timeout = '2s'`** before DDL on large tables to fail fast instead of blocking
- [ ] Unique constraints enforced at the database level, not just `@unique` on a non-managed column
- [ ] Partial indexes used for boolean/enum filters that select a small subset
- [ ] No DDL on hot tables in a single migration (expand-then-contract: add column nullable, backfill, switch reads, drop old column in a later release)
- [ ] **Backfill via keyset pagination** (`WHERE id > $lastId ORDER BY id LIMIT N`), never `WHERE col IS NULL LIMIT N` (re-scans the same rows on every iteration)
- [ ] Data migrations isolated from DDL migrations - separate Prisma migration / TypeORM migration class
- [ ] Enum changes safe: PostgreSQL `ALTER TYPE ... ADD VALUE` cannot run in a transaction; document `prisma migrate` workaround or use `--create-only` then edit

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot in `WHERE` / `ORDER BY` / `GROUP BY` even if no query in the diff currently references it - someone is adding the index for a reason, and the migration is the load-bearing artifact. Validate the index is actually needed (column shape, expected selectivity), then assess migration safety. Conversely, when the diff _adds a column_ the application also queries on, flag the missing index proactively rather than waiting for a separate migration PR.

**Migration impact template.** Before approving any migration step on a hot table, state the impact: _"DDL on a 50M-row table without `CONCURRENTLY` blocks all writes for the duration of the index build (typically 5-30 min on Postgres at this scale). Acquires `ACCESS EXCLUSIVE`; every other transaction queues."_ If the row count is unknown, ask, or note "row count not in diff - confirm before deploy."

### Step 6 - Async Correctness and Event Loop

Canonical async patterns live in `node-typescript-patterns`. Apply the **review-scoped scan** below.

> **Impact heuristic.** A blocking call inside an async handler stalls _every request in flight on this Node process_, not just the calling one. Phrase impact as "tail-latency contagion across in-flight requests," not "this request is slow." HTTP to a critical-path upstream inherits its tail latency: your p99 = max(your work, upstream p99) - recommend `AbortSignal.timeout(500)` + fallback, or async pattern (decision cache, circuit breaker).

- [ ] **No blocking I/O / CPU on the event loop**: `fs.readFileSync`, `crypto.pbkdf2Sync`, large `JSON.parse` of untrusted size, large regex on user input - flag in any request path. Hashing / image / large parse → `worker_threads` (`piscina`) or BullMQ. Sync at startup is fine; sync in request paths stalls every in-flight request
- [ ] **No external I/O inside a DB transaction (perf lens)**: `axios` / `fetch` / `undici` / `queue.add()` inside `prisma.$transaction` / `dataSource.transaction` holds a pooled connection for the upstream's tail latency - 5ms write becomes a 500ms write of pool starvation. Capture inputs inside, dispatch after the transaction resolves (or via `afterCommit` / event emitter). Correctness lens is owned by `task-node-review`
- [ ] **Concurrency control**: fan-out uses `Promise.all` / `Promise.allSettled` instead of sequential `for...of` await; unbounded fan-out over a large list bounded via `p-limit` / `bottleneck` / BullMQ
- [ ] **`AbortSignal.timeout(...)` on every external call**: Node's default HTTP timeout is effectively infinite
- [ ] **HTTP clients module-level**: `axios.create()` / `undici` Pool / `node-fetch` agent shared, not per-request - connection reuse matters at scale
- [ ] **NestJS request-scoped providers**: `@Injectable({ scope: Scope.REQUEST })` only when needed (per-request transaction / multi-tenant context); default-singleton otherwise. Heavy logic in interceptors / pipes runs per request - move post-response via `tap`
- [ ] **Connection pool sized correctly**: Prisma `connection_limit` / TypeORM `extra.max` × replica count ≤ DB `max_connections` (e.g., 4 PM2 workers vs Postgres `max_connections=100` → ~20/worker)

### Step 7 - Validation / Serialization

_Skipped at `quick` depth unless the diff touches DTOs with non-trivial validators._

**NestJS:**

- [ ] **`ValidationPipe` global**: `app.useGlobalPipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }))` - rejects unknown fields and runs `class-transformer`. Per-route pipes are noisy and easy to forget.
- [ ] **`class-validator` overhead**: heavy `@IsString()` + `@Length()` chains on hot endpoints reviewed - validation is reflective and not free at high QPS. Prefer Zod for hot paths (compiled validator).
- [ ] **`class-transformer` `@Transform`** with non-trivial logic runs on every request; flag expensive transforms.
- [ ] **`@Exclude()` / `@Expose()`**: `ClassSerializerInterceptor` wraps response serialization - prefer projecting fields at the query layer (Prisma `select`, TypeORM `select`) over excluding them at serialization time.
- [ ] **Response DTO mapping**: `plainToInstance(ResponseDto, entity)` adds CPU cost; for hot endpoints, return plain objects shaped at the repository.

**Express:**

- [ ] **Schema validation library chosen**: Zod (compile-once, fast) or class-validator + class-transformer (reflective, slower). For high-QPS endpoints, Zod is the right choice; flag inconsistent mixing.
- [ ] **`zod.parse` vs `zod.safeParse`**: `parse` throws (allocates an Error); `safeParse` returns a discriminated union - same cost, but `safeParse` integrates more cleanly with handler return paths.
- [ ] **Reuse schemas**: top-level `const OrderCreate = z.object({...})` reused across endpoints - first construction is the slow path; per-request construction wastes allocations.
- [ ] **Body size limit**: `app.use(express.json({ limit: '100kb' }))` - default `100kb` is sane; raise only deliberately. Unbounded body parsing is a DoS surface.

### Step 8 - Caching and Response Performance

_Skipped at `quick` depth unless the diff touches caching primitives._

- [ ] **Per-request memoization**: `Symbol`-keyed property on `req` for values used by multiple middlewares; NestJS `RequestContext` for request-scoped state.
- [ ] **Process-level cache**: `lru-cache` (in-process, eviction-aware) for hot reads; Redis (`ioredis`, `redis` v4) for shared / multi-instance.
- [ ] **Cache stampede protection**: hot keys with expensive regeneration use single-flight (`p-memoize` with TTL, or per-key `Map<string, Promise<T>>` to dedupe in-flight); for distributed cache, Redis `SET NX EX` lock.
- [ ] **Cache invalidation explicit** - no caches that never expire and never invalidate; document staleness budget.
- [ ] **NestJS `CacheModule`**: TTL configured; `@CacheKey` / `@CacheTTL` declared; understand it caches the full response - skip for endpoints with per-user variation unless `cacheKey` includes the principal.
- [ ] **HTTP caching** (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GET endpoints; NestJS `@Header` decorator or Express `res.set`.
- [ ] **Response compression** middleware (`compression` for Express; `@nestjs/common` is configured at the platform layer) for JSON responses > 2KB.

### Step 9 - BullMQ / Background Work

_Skipped at `quick` depth unless the diff touches BullMQ._

Canonical patterns live in `node-bullmq-patterns`. Apply the **review-scoped scan** below.

- [ ] **Idempotent + ID payloads**: re-fetch state, return early if done; payload uses IDs / primitives, never ORM entities. `queue.add(name, data, { jobId: businessKey })` for server-side dedup
- [ ] **`queue.add()` AFTER commit**: never inside `prisma.$transaction` / `dataSource.transaction` - worker may pick up before the row is visible. NestJS post-commit hook / `EventEmitter2`; bare TypeORM `manager.transaction` resolves first
- [ ] **Retry + DLQ declared**: `attempts` + `backoff: { type: 'exponential' }`, `removeOnComplete` / `removeOnFail` (prevent Redis growth); failed-jobs surfaced via observability, not ignored
- [ ] **Queue routing + Worker concurrency**: time-sensitive jobs on a dedicated queue; `Worker` concurrency explicit (default 1) and aligned to downstream capacity, not CPU count
- [ ] **`lockDuration` matches job runtime**: jobs > 30s set `lockDuration` higher or split via flow producer / `addBulk` - otherwise BullMQ marks them stalled and reprocesses (double-execution)

### Step 10 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

This step is intentionally narrow - depth on observability belongs to `task-node-review-observability`. From a perf perspective, confirm only:

- [ ] Slow paths reachable from this PR have **some** instrumentation (OTel span or `prom-client` histogram); if not, raise as a Low/Recommendation finding and delegate to `task-node-review-observability` for a proper instrumentation pass rather than dictating the design here.
- [ ] Prisma `log: ['query']` not enabled in prod; TypeORM `logging: true` not enabled in prod - if visible in the diff. If neither is in the diff, skip.

Anything beyond presence/absence (sampling rates, span attributes, correlation IDs, multi-process Prometheus) → `task-node-review-observability` owns it. Note the gap, do not duplicate the audit here.


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Node.js / TypeScript; framework (NestJS / Express / mixed) and ORM (Prisma / TypeORM) recorded before any framework-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Performance surface read directly (entities / schema, repositories, controllers / handlers, DTOs, config, migrations, BullMQ producers / processors)
- [ ] `node-prisma-patterns` consulted for Prisma projects; N+1, multi-level N+1, `include` overfetch, projection use, upsert idempotency checked
- [ ] `node-typeorm-patterns` consulted for TypeORM projects; relations, lazy traps, cartesian explosion, `synchronize: true` flagged
- [ ] `node-migration-safety` consulted for any migration change; `lock_timeout`, concurrent index, keyset-pagination backfill, expand-contract verified
- [ ] Async correctness audit run (blocking I/O, `Promise.all`, `AbortSignal` timeouts, request-scoped providers)
- [ ] `node-bullmq-patterns` consulted for any BullMQ change; idempotency, retry policy, post-commit dispatch, DLQ verified
- [ ] Connection pool sizing validated against worker / framework concurrency model **if pool config is in the diff**; otherwise note as Low / Recommendation and skip rather than fail the check
- [ ] Caching strategy assessed (in-process vs Redis, single-flight, invalidation explicit)
- [ ] Validation / serialization cost assessed when applicable
- [ ] Every finding states impact - measured (`p95: 800ms -> 120ms`) when APM data exists, estimated otherwise (`adds ~N queries per request at K rows`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 4 + 5; `standard` ran 4-10; `deep` adds capacity guidance and load-test plan
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Node.js Performance Review Summary

**Stack Detected:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version> | mixed
**ORM:** Prisma <version> | TypeORM <version> | mixed
**Scope:** Backend (Node.js)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [what the problem is - name the Node idiom: N+1 via per-iteration `findMany` inside a `for...of`, missing index, sync `crypto.pbkdf2Sync` in async handler, BullMQ `queue.add` inside transaction, TypeORM `eager: true` cartesian, etc.]
- **Impact:** [estimated effect - e.g., "N+1 in OrdersController.list adds ~200 queries per request at 100 orders" or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [specific Node.js change with code example - `include`, `relations`, `await`, `bullmq jobId`, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Switch list endpoint to cursor pagination", "Add Redis cache for product catalog reads", "Move PDF generation to BullMQ"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, schema migration, or load-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `include: { items: { include: { product: true } } }` to OrdersService.list"]
2. **[Delegate]** [High] [scope: schema] - [one-line action, e.g., "Add concurrent composite index on (tenantId, createdAt) - spawn DB migration subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting issues without naming the Node idiom ("this is slow" vs "N+1 from per-iteration `findMany` inside loop; replace with `include`")
- Recommending generic backend advice when a Node pattern applies (say "use `include`", not "use eager loading")
- Suggesting `eager: true` on TypeORM collection relations to fix N+1 - it forces eager load on every query including the ones that don't need it; use per-query `relations: [...]` or QueryBuilder `leftJoinAndSelect`
- Suggesting caching without an invalidation strategy
- Conflating performance review with general code review or security review - delegate those to their workflows
- Treating BullMQ retries as a substitute for idempotency - retries with non-idempotent jobs cause double-charging / double-emailing
- Recommending sync APIs (`fs.readFileSync`, `crypto.pbkdf2Sync`) on request paths - they block the event loop and stall every other in-flight request
- Recommending `setTimeout(..., 0)` to "yield" - that pushes work to the next macrotask but doesn't free the event loop; use `worker_threads` for CPU work
- Reporting "missing index" without confirming the column actually appears in a `where` / `orderBy` / `groupBy` in the diff
- Approving `synchronize: true` (TypeORM) or `prisma db push` workflows for non-dev environments
