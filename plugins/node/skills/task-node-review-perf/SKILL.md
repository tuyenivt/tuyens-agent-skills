---
name: task-node-review-perf
description: Node.js performance review for Prisma / TypeORM N+1, event-loop blocking, sync-in-async traps, connection pool sizing, BullMQ throughput / idempotency, JSON serialization cost, and migration safety. Detects NestJS vs Express and applies the right framework idioms. Stack-specific override of task-code-review-perf, invoked when stack-detect resolves to Node.js / TypeScript.
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

Use skill: `stack-detect` to confirm Node.js / TypeScript. If the detected stack is not Node, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Node 20+ and TypeScript strict mode.

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

> If `ORM: Prisma` was recorded in Step 1, **skip the TypeORM subsection entirely** below; do not scan it for non-applicable bullets. Likewise skip the Prisma subsection on TypeORM-only projects. The bifurcation exists for mixed codebases - on monoglot projects it should be one read, not two.

**If Prisma** - use skill: `node-prisma-patterns`:

Inspect every changed model, repository, service, and controller for:

- [ ] **N+1 in queries**: any traversal of a relation after a `findMany` is preloaded with `include: { rel: true }` or projected with `select: { rel: { select: {...} } }`. Prisma never lazy-loads (no proxy magic), so the smell is "a separate `findMany` inside a `for...of` loop over a parent list" - eager-load with `include` instead.
- [ ] **Multi-level N+1**: nested traversal across two relations (`order.items` → `item.product`) - resolve with chained `include: { items: { include: { product: true } } }`.
- [ ] **`include` overfetch**: pulling full child rows when only one column is needed - prefer `select: { items: { select: { id: true, sku: true } } }` to bound payload size.
- [ ] **Missing indexes for filter/sort columns**: any field used in `where` / `orderBy` / `groupBy` without a backing `@@index([...])` or `@unique` in the Prisma schema.
- [ ] **`findMany` without pagination**: any read of an unbounded collection - require `take` / cursor-based pagination for any list endpoint that can grow.
- [ ] **Existence checks**: use `prisma.x.findFirst({ where, select: { id: true } })` over `findMany().then(r => r.length > 0)`; for hot paths consider raw `EXISTS` via `$queryRaw`.
- [ ] **Bulk operations**: `createMany` / `updateMany` / `deleteMany` over per-row loops; `createMany` `skipDuplicates: true` for idempotent bulk inserts.
- [ ] **Upsert for idempotency**: `upsert({ where, create, update })` over `findUnique` + `if/else` create/update - races less, fewer round trips.
- [ ] **Transactions**: `prisma.$transaction([...])` for batch operations; interactive transactions (`prisma.$transaction(async (tx) => {...})`) only when needed - they hold a connection for the duration. `isolationLevel` set explicitly when stronger than READ COMMITTED is needed.
- [ ] **Connection pool sizing**: `connection_limit` documented; default is `num_cpus * 2 + 1` per engine instance; multi-instance deploys require `connection_limit` × replica count ≤ DB-side `max_connections`.
- [ ] **Prisma engine logs in prod**: `log: ['query']` flagged - logs every query at `INFO`; should be `['warn', 'error']` in prod or use OTel instrumentation.

**If TypeORM** - use skill: `node-typeorm-patterns`:

- [ ] **N+1 in queries**: any traversal of a relation after `find()` is preloaded with `relations: ['items']` or `createQueryBuilder().leftJoinAndSelect('order.items', 'items')`. `eager: true` on entity relations is risky - it forces eager load on every query, including the ones that don't need it; prefer per-query `relations: [...]`.
- [ ] **N+1 via lazy relations**: `lazy: true` returns a `Promise<T[]>` - `await order.items` triggers a query per parent; same fix as Prisma N+1 but with `relations` arrays.
- [ ] **`createQueryBuilder` cartesian explosion**: chained `leftJoinAndSelect` on multiple to-many relations duplicates parent rows; use `.distinct(true)` or split into separate queries.
- [ ] **`select` projection**: `find({ select: ['id', 'name'] })` to bound payload - default returns all columns including large `text` / `bytea`.
- [ ] **Existence checks**: `repository.exist({ where })` (TypeORM 0.3+) over `findOne()` then null-check.
- [ ] **Bulk operations**: `repository.insert([...])` / `repository.update(criteria, partial)` for batch writes; `createQueryBuilder().insert().values([...]).orIgnore()` for `INSERT ... ON CONFLICT DO NOTHING`.
- [ ] **Transactions**: `dataSource.transaction(async (manager) => {...})` or `@Transaction` decorator (deprecated in 0.3, prefer manual). `@Transactional` from `typeorm-transactional` with proper `initializeTransactionalContext()` setup.
- [ ] **Missing indexes**: any column in `where` / `orderBy` without `@Index()` on the entity or via migration.
- [ ] **`synchronize: true` in prod**: critical finding - drops and recreates schema; must be `false` in non-dev environments.
- [ ] **Connection pool sizing**: `extra.max` (pg pool) documented; `extra.max × replica_count ≤ DB max_connections`.

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

Use skill: `node-typescript-patterns` for async typing patterns.

Inspect changes touching `async` / `await`, `Promise.all`, streams, and worker threads:

- [ ] **No blocking I/O on the event loop**: `fs.readFileSync` → `fs.promises.readFile`; `crypto.pbkdf2Sync` → `crypto.pbkdf2` (or worker thread); large JSON parsing of untrusted size → streaming parser. Sync file I/O on small files at startup is acceptable; in request paths it stalls every other in-flight request on this Node process.

> **Impact heuristic - blast radius of an event-loop block.** A blocking call inside an async handler does not just slow the calling request - it stalls _every other request currently in flight on this Node process_. Node has a single event loop per process; with PM2 cluster mode and 4 workers, a 50ms `crypto.pbkdf2Sync` call drags tail latency across all four workers' shares of in-flight traffic until it returns. Phrase the impact as "tail-latency contagion across all in-flight requests on this process," not "this request is slow."

> **Synchronous external dependency on the request path.** Even when the call uses `fetch` / `axios` correctly, an HTTP call to a critical-path service (fraud, auth, pricing) inherits the upstream's tail latency: your p99 = max(your work, upstream p99). Recommend async patterns (decision cache, circuit breaker, fire-and-forget) when the call is non-blocking-business; recommend strict timeouts (`AbortSignal.timeout(500)`) plus fallback values when blocking-business.

- [ ] **No CPU-heavy work on the event loop**: hashing, image processing, parsing large payloads must go to a `worker_threads` pool or a BullMQ job; otherwise tail-latency for all in-flight requests degrades.
- [ ] **No external I/O inside a DB transaction (perf lens)**: `axios` / `fetch` / `undici` / `queue.add()` inside `prisma.$transaction(async (tx) => {...})` or `dataSource.transaction(async (manager) => {...})` holds a pooled connection for the duration of the network roundtrip. Under load this drains the pool faster than QPS would predict, and locked rows stay locked for the upstream's tail latency. The correctness-lens version (worker may see uncommitted state) is owned by `task-node-review`; the perf lens here is "you turned a 5ms write into a 500ms write of pool starvation." Recommend: capture inputs inside the transaction, dispatch the side effect after `$transaction` resolves (or via `transaction.afterCommit` / event emitter).
- [ ] **`Promise.all` for fan-out**: independent I/O calls run concurrently, not sequentially in a `for...of` loop. Use `Promise.all([...])` or `Promise.allSettled([...])` (when partial failures should not abort the batch).
- [ ] **Concurrency cap**: fan-out over a list uses a bounded queue (`p-limit`, `bottleneck`, or BullMQ for durable work); unbounded `Promise.all` over a 10k-row list will exhaust connections / file descriptors.
- [ ] **`AbortSignal` / timeouts** on every external call: `fetch(url, { signal: AbortSignal.timeout(500) })`; explicit timeout per call beats relying on Node's defaults (which are effectively infinite for HTTP).
- [ ] **HTTP clients reused**: `axios.create()` instance / `undici` Pool / `node-fetch` agent shared at module level, not instantiated per request - connection reuse matters at scale.
- [ ] **No mixing of sync ORM into async path**: TypeORM / Prisma calls are async; flag any sync wrapper (`deasync`, sync-blocking patterns) - they break the event loop.
- [ ] **NestJS request-scoped providers**: `@Injectable({ scope: Scope.REQUEST })` creates a new instance per request - measurable overhead under load. Prefer default singleton scope; use request scope only when truly needed (per-request DB transaction, multi-tenant context).
- [ ] **NestJS interceptor / pipe overhead**: `@UseInterceptors(LoggingInterceptor)` runs on every request - expensive logic in interceptors compounds per request. Move heavy work to async post-response (`tap` operator).
- [ ] **Connection pool sized correctly**: Prisma `connection_limit` / TypeORM `extra.max` × replica count ≤ DB-side `max_connections`. For 4 PM2 workers and Postgres `max_connections=100`, target ~20 per worker. Oversize and DB starves.

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

Use skill: `node-bullmq-patterns` for canonical job patterns.

- [ ] **Jobs idempotent**: re-fetch state, check if work was done, return early. Pass IDs / simple types - never ORM entities (lazy loads, stale data, serialization issues).
- [ ] **Job IDs for dedup**: `queue.add(name, data, { jobId: businessKey })` where business-key collisions are intentional (BullMQ rejects duplicate `jobId` while another exists) - turns "deliver once" into a server-side guarantee.
- [ ] **Retry strategy declared**: `attempts`, `backoff: { type: 'exponential', delay: 1000 }` per-job or via `defaultJobOptions`; `removeOnComplete: { age, count }` and `removeOnFail` to prevent Redis growth.
- [ ] **Failed-jobs queue / DLQ**: jobs that exceed `attempts` move to `failed` set; processor logic / observability surfaces them; not ignored.
- [ ] **Queue routing**: time-sensitive jobs on a dedicated queue with its own `Worker` and concurrency; mixed-priority on one queue starves urgent work.
- [ ] **`queue.add()` AFTER the DB transaction commits**: dispatching inside the transaction means the worker may pick it up before the row is visible. NestJS: `entityManager.afterCommit` or `eventEmitter.emit` from `@Transactional` post-commit hook; bare TypeORM: emit after `manager.transaction(async (m) => {...})` resolves; Prisma: `prisma.$transaction(...)` resolves before `queue.add()`.
- [ ] **Long-running jobs split**: target sub-30-second median; longer work uses flow producer / `addBulk` chains.
- [ ] **`Worker` concurrency** set explicitly (default 1); align with downstream capacity, not just CPU count.
- [ ] **`lockDuration` / `stalledInterval`**: jobs that genuinely take > 30s set `lockDuration` higher; otherwise BullMQ marks them stalled and reprocesses (double-execution).

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
