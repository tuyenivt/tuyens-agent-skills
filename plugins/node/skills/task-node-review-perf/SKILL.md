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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Node.js Performance Review

Node.js-aware performance review naming Prisma `include` / `select` / `findMany`, TypeORM relations / QueryBuilder, event-loop discipline, NestJS interceptor / pipe overhead, BullMQ task design, and Prisma / TypeORM migration safety. Findings have measured or estimated impact (latency, throughput, query count, event-loop lag) and concrete TypeScript strict-mode fixes.

## When to Use

- NestJS or Express PR / branch perf regression review
- Slow endpoint / BullMQ job / scheduled cron investigation
- Pre-merge perf pass on ORM queries, async boundaries, BullMQ dispatch, event-loop-blocking calls
- Quarterly N+1 / pool-sizing / async-correctness sweep against APM data

**Not for:**
- General Node review (`task-node-review`)
- Security review (`task-node-review-security`)
- Production incident (`/task-oncall-start`)
- Pre-implementation design (`task-node-implement`)

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `quick` | Single endpoint / repository | Steps 4 + 5 only |
| `standard` | Default | All steps |
| `deep` | Profiling-driven with clinic.js / 0x / OTel | All + capacity guidance + load plan |

## Invocation

| Form | Meaning |
|------|---------|
| `/task-node-review-perf` | Current branch vs base; fails fast on trunk |
| `/task-node-review-perf <branch>` | `<branch>` vs base (3-dot) |
| `/task-node-review-perf pr-<N>` | PR head fetched into local branch `pr-<N>` |

When invoked as subagent, Step 2 is skipped and pre-read diff is reused.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. Then:

- `nest-cli.json` / `@nestjs/*` in deps -> **NestJS**
- `express` in deps without `@nestjs/*` -> **Express**
- Both -> ask which surface this PR targets; do not guess

Default ORM mapping: NestJS -> Prisma; Express -> TypeORM. Record `Framework` and `ORM` for the Summary.

### Step 2 - Resolve the Diff

Use skill: `review-precondition-check`. Read diff and log once via `git diff <base>...<head>` and `git log <base>..<head>`; reuse. Skip entirely as subagent with handle + pre-read.

If `review-precondition-check` fails fast, surface verbatim and stop.

### Step 3 - Read the Performance Surface

Cite real `file:line` per finding. Open:

**Prisma:** every changed `schema.prisma` model (relations, `@@index`, `@db.*`), every changed repository / service (`findMany` / `findUnique` / `include` / `select` / `where` / `orderBy`), controllers (`@UseInterceptors`, response DTOs), `prisma.service.ts` / config for `connection_limit` / `log`, migrations under `prisma/migrations/`.

**TypeORM:** every changed entity (`@Entity`, `@OneToMany`, `@ManyToOne`, `@Index`, `eager`), repositories (`find` / `createQueryBuilder` / `relations`), Express routes / middleware (async error forwarding), DTOs (Zod / Joi / class-validator), `data-source.ts` for `poolSize` / `extra.max` / `synchronize`, migrations under `src/migrations/`.

**Both:** BullMQ producers, `@Processor` classes, queue config.

If the diff is small but ripples into unchanged code (a new endpoint calling an existing N+1 repository), read the unchanged file - the regression lives there.

### Step 4 - ORM Hotspots (Prisma or TypeORM)

Canonical patterns: Use skill: `node-prisma-patterns` (Prisma) or `node-typeorm-patterns` (TypeORM). This step flags deviations - skip the irrelevant subsection on monoglot projects.

- [ ] **N+1**: Prisma `include` / `select`; TypeORM `relations: [...]` or `leftJoinAndSelect` (avoid `eager: true` on collections - cartesian explosion). Multi-level (`order.items.product`) chained through one query, not nested loops
- [ ] **Overfetch**: Prisma `select`; TypeORM `find({ select: [...] })` - defaults return all columns including large `text` / `bytea`
- [ ] **Missing indexes** for `where` / `orderBy` / `groupBy` - flag any predicate / sort column without `@@index` (Prisma) / `@Index` (TypeORM) or migration
- [ ] **Unbounded reads**: list endpoints use `take` + cursor pagination, not bare `findMany` / `find()`
- [ ] **Per-row loops**: Prisma `createMany` / `updateMany`; TypeORM `repository.insert([...])` or QueryBuilder `.insert().values([...])`
- [ ] **Existence checks**: `findFirst({ where, select: { id: true } })` / `repository.exist({ where })` over fetch-then-`length`
- [ ] **Connection pool sized**: Prisma `connection_limit` / TypeORM `extra.max` x replicas <= DB `max_connections`
- [ ] **Prod-unsafe config**: TypeORM `synchronize: true` (Critical); Prisma `log: ['query']` in prod (High)

### Step 5 - Indexes and Migrations

Use skill: `node-migration-safety` for changes in `prisma/migrations/` or `src/migrations/`.

- [ ] Every column in `where` / `orderBy` / `groupBy` backed by an index
- [ ] Composite indexes match leftmost-prefix
- [ ] FK columns indexed (PostgreSQL does not auto-index FKs)
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY` (Prisma: `--create-only` + manual SQL; TypeORM: `queryRunner.query(...)`)
- [ ] `SET lock_timeout = '2s'` before DDL on large tables
- [ ] Unique constraints at the DB level, not just `@unique` on a non-managed column
- [ ] Partial indexes for boolean/enum filters selecting a small subset
- [ ] No DDL on hot tables in a single migration (expand-then-contract)
- [ ] Backfill via keyset pagination (`WHERE id > $1 ORDER BY id LIMIT N`), never `WHERE col IS NULL LIMIT N`
- [ ] Data migrations isolated from DDL migrations
- [ ] Enum changes safe: PostgreSQL `ALTER TYPE ... ADD VALUE` cannot run in a transaction

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot - validate the index is needed (selectivity, shape), then assess safety. When the diff _adds a column_ also queried on, flag the missing index proactively.

**Migration impact template.** State the impact before approving DDL on a hot table: _"DDL on a 50M-row table without `CONCURRENTLY` blocks writes for 5-30 min on Postgres at this scale. Acquires `ACCESS EXCLUSIVE`; every other transaction queues."_ If row count is unknown, ask, or note "row count not in diff - confirm before deploy."

### Step 6 - Async Correctness and Event Loop

**Impact heuristic.** A blocking call inside an async handler stalls _every request in flight on this Node process_. Phrase impact as "tail-latency contagion across in-flight requests," not "this request is slow." HTTP to a critical-path upstream inherits its tail: your p99 = max(your work, upstream p99); recommend `AbortSignal.timeout(500)` + fallback, or async via decision cache / circuit breaker.

- [ ] **No blocking I/O / CPU on the event loop**: `fs.readFileSync`, `crypto.pbkdf2Sync`, large `JSON.parse` of untrusted size, large regex on user input in request paths -> `worker_threads` (`piscina`) or BullMQ. Sync at startup is fine
- [ ] **No external I/O inside a transaction**: `axios` / `fetch` / `queue.add()` inside `prisma.$transaction` / `dataSource.transaction` holds a pooled connection for the upstream's tail - 5ms write becomes 500ms of pool starvation. Capture inside, dispatch after commit
- [ ] **Bounded concurrency**: `Promise.all` / `Promise.allSettled` over sequential `for...of await`; large fan-out bounded via `p-limit` / `bottleneck` / BullMQ
- [ ] **`AbortSignal.timeout(...)` on every external call** - Node's default HTTP timeout is effectively infinite
- [ ] **HTTP clients module-level**: shared `axios.create()` / `undici` Pool, not per-request
- [ ] **NestJS request-scoped providers**: `Scope.REQUEST` only when needed (per-request transaction / multi-tenant); default-singleton otherwise. Move heavy interceptor / pipe logic post-response via `tap`

### Step 7 - Validation / Serialization

_Skipped at `quick` unless the diff touches DTOs with non-trivial validators._

**NestJS:**
- [ ] **`ValidationPipe` global** with `whitelist: true, forbidNonWhitelisted: true, transform: true` - per-route pipes are noisy and easy to forget
- [ ] **`class-validator` / `class-transformer` overhead**: reflective, not free at high QPS; prefer Zod for hot paths. Flag expensive `@Transform` and `ClassSerializerInterceptor` use - project at the query layer (Prisma `select`, TypeORM `select`) over excluding at serialization

**Express:**
- [ ] **Zod schemas reused** (top-level `const`, not per-request); `safeParse` integrates more cleanly with handler return paths than `parse`
- [ ] **Body size limit**: `express.json({ limit: '100kb' })` - unbounded body parsing is a DoS surface

### Step 8 - Caching and Response Performance

_Skipped at `quick` unless the diff touches caching primitives._

- [ ] **In-process**: `lru-cache` (eviction-aware) for hot reads; Redis (`ioredis`) for shared / multi-instance
- [ ] **Stampede protection**: hot keys with expensive regen use single-flight (`p-memoize` / per-key `Map<string, Promise<T>>`); distributed via Redis `SET NX EX`
- [ ] **Invalidation explicit** - document staleness budget; no never-expiring caches
- [ ] **NestJS `CacheModule`**: TTL set; `cacheKey` includes principal for per-user variation
- [ ] **HTTP caching** (`Cache-Control`, `ETag`) on read-heavy GETs
- [ ] **Response compression** (`compression` for Express) for JSON > 2KB
- [ ] **Per-request memoization**: `Symbol`-keyed property on `req` / NestJS `RequestContext` for cross-middleware values

### Step 9 - BullMQ / Background Work

_Skipped at `quick` unless the diff touches BullMQ._

Use skill: `node-bullmq-patterns`. Apply the review-scoped scan:

- [ ] **Idempotent + ID payloads**: re-fetch state, return early if done; payload uses IDs / primitives, never ORM entities. `queue.add(name, data, { jobId: businessKey })` for server-side dedup
- [ ] **`queue.add()` AFTER commit**: never inside `prisma.$transaction` / `dataSource.transaction` - worker may pick up before the row is visible. Use post-commit hook / `EventEmitter2`
- [ ] **Retry + DLQ**: `attempts` + `backoff: { type: 'exponential' }`, `removeOnComplete` / `removeOnFail` (prevent Redis growth); failed jobs surfaced via observability
- [ ] **Queue routing + Worker concurrency**: time-sensitive on dedicated queue; concurrency aligned to downstream capacity, not CPU count
- [ ] **`lockDuration` matches job runtime**: jobs > 30s set higher `lockDuration` or split via flow producer / `addBulk` - else BullMQ marks stalled and reprocesses (double-execution)

### Step 10 - Observability for Perf (delegation handoff)

_Skipped at `quick`._

Depth on observability belongs to `task-node-review-observability`. Confirm only:

- [ ] Slow paths from this PR have **some** instrumentation (OTel span or `prom-client` histogram); if not, raise as Low / Recommendation and delegate
- [ ] Prisma `log: ['query']` / TypeORM `logging: true` not enabled in prod (only if in diff)

Beyond presence/absence -> `task-node-review-observability` owns it.

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Write before ending; print confirmation.

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
- **Issue:** [Node idiom: N+1 via per-iteration `findMany` in `for...of`, missing index, `crypto.pbkdf2Sync` in async handler, BullMQ `queue.add` inside transaction, TypeORM `eager: true` cartesian, etc.]
- **Impact:** [estimated: "N+1 in OrdersController.list adds ~200 queries per request at 100 orders" / measured: "p95 800ms -> 120ms after fix"]
- **Fix:** [Node change with code: `include`, `relations`, `await`, BullMQ `jobId`, etc.]

### Medium Impact
[Same structure]

### Low Impact / Quick Wins
[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a finding - e.g., "Switch list endpoint to cursor pagination", "Add Redis cache for product catalog reads", "Move PDF generation to BullMQ"]

## Next Steps

Each item tagged `[Implement]` or `[Delegate]`. Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: schema] - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Stack, framework, ORM recorded; diff/log read once; perf surface read directly (Steps 1-3)
- [ ] ORM atomics consulted; N+1, overfetch, missing indexes, unbounded reads, per-row loops, existence checks, pool sizing, prod-unsafe config covered (Step 4)
- [ ] Migration-safety atomic consulted on migration changes: `lock_timeout`, CONCURRENTLY, keyset backfill, expand-contract (Step 5)
- [ ] Async audit: blocking I/O, `Promise.all` boundedness, `AbortSignal`, request-scoped providers, no I/O in transactions (Step 6)
- [ ] Validation / serialization, caching, BullMQ assessed when diff touches them (Steps 7-9)
- [ ] Observability presence/absence confirmed; depth delegated (Step 10)
- [ ] Depth honored: `quick` = Steps 4-5; `standard` = 4-10; `deep` adds capacity + load plan
- [ ] Every finding states measured or estimated impact; findings ordered by impact
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered High > Medium > Low
- [ ] Report written via `review-report-writer`; confirmation printed

## Avoid

- `git fetch` / `git checkout` from this workflow - user runs these
- Reporting issues without naming the Node idiom ("this is slow" vs "N+1 from per-iteration `findMany`")
- Generic backend advice when a Node pattern applies (say "use `include`", not "use eager loading")
- Suggesting `eager: true` on TypeORM collection relations to fix N+1 - forces eager on every query; use per-query `relations: [...]` or `leftJoinAndSelect`
- Suggesting caching without invalidation strategy
- Conflating perf with general or security review
- Treating BullMQ retries as a substitute for idempotency
- Recommending sync APIs (`fs.readFileSync`, `crypto.pbkdf2Sync`) on request paths
- Recommending `setTimeout(..., 0)` to "yield" - pushes work to the next macrotask but doesn't free the event loop; use `worker_threads` for CPU
- Reporting "missing index" without confirming the column appears in `where` / `orderBy` / `groupBy`
- Approving `synchronize: true` (TypeORM) or `prisma db push` for non-dev environments
