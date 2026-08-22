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
- Pre-implementation design (`task-node-implement`)

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | All steps |
| `deep` | Requested, handed down by a parent, profiler or APM data supplied, or any whole-service sweep | All + `Capacity Guidance` + `Load Plan` |

## Invocation

| Form | Meaning |
|------|---------|
| `/task-node-review-perf` | Current branch vs base; fails fast on trunk |
| `/task-node-review-perf <branch>` | `<branch>` vs base (3-dot) |
| `/task-node-review-perf pr-<N>` | PR head fetched into local branch `pr-<N>` |

Depth (`standard` \| `deep`) and `--base <branch>` compose with any form: `/task-node-review-perf pr-50273 --base release/2026.05 deep`. When invoked as subagent, Step 2 is skipped and pre-read diff is reused.

**Whole-service sweep.** The quarterly / APM-driven sweep has no diff, so the trunk fail-fast would end it. Enter this path only when Step 2 fails fast on trunk **and** the invocation asked for a sweep or supplied profiler / APM data - a wrong-branch mistake is not a sweep, and there the fail-fast stands. On the sweep path:

- Scope is the service's own source root, or the path the invocation named. Every "changed" / "in diff" wording below reads as "in scope".
- Findings cite current code at `HEAD`. Verification is inline (Step 10's carve-out), not `review-finding-verify`.
- Writer fields come from the repo: `branch` = current branch short name, `base_ref` = `head_ref` = that same name, `base_sha` = `head_sha` = `git rev-parse HEAD`, `round` from the re-review gate as usual.
- The Summary carries `Target:` naming the swept scope, and the run is `deep`.
- Rank by the supplied evidence first: an endpoint named in the APM data outranks a checklist hit with no measurement behind it.

## Workflow

### Step 1 - Load Behavioral Principles and Confirm Stack

Use skill: `behavioral-principles` first, before any other delegation. Then use skill: `stack-detect`; accept a pre-confirmed stack from a parent. Then:

- `nest-cli.json` / `@nestjs/*` in deps -> **NestJS**
- `express` in deps without `@nestjs/*` -> **Express**
- Both -> ask which surface this PR targets; do not guess

Detect ORM from evidence, never from framework: `@prisma/client` in deps / `prisma/schema.prisma` -> **Prisma**; `typeorm` in deps / `data-source.ts` -> **TypeORM**; both -> ask which surface this PR touches. Record `Framework` and `ORM` for the Summary.

### Step 2 - Resolve the Diff

Use skill: `review-precondition-check`; forward `--base <branch>` when passed. Read diff and log once via `git diff <base>...<head>` and `git log <base>..<head>`; reuse. Also capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs - the writer runs no git of its own. Skip entirely as subagent with handle + pre-read.

If `review-precondition-check` fails fast, surface verbatim and stop - **except** a trunk fail-fast on a sweep invocation, which routes to the Whole-service sweep under Invocation instead of stopping.

**Re-review gate (standalone only).** The handle's `prior_checkpoint` is keyed to `review-<branch>.md`, the general review's report - not this lens's. Check for `review-perf-<branch>.md` yourself, sanitizing `branch` the way the writer does (`/` and any character outside `[A-Za-z0-9_-]` becomes `-`). If it exists with valid frontmatter, its `head_sha` equals the current head, the invocation adds no depth beyond it, and it is not a sweep checkpoint standing in front of a diff review, print `No new commits on <branch> since prior perf review at <sha_short>. Prior report unchanged.` and stop without writing. Otherwise `round` = prior + 1, and pass its `head_sha` as `prior_head_sha`. No such file, or one whose frontmatter is missing or invalid -> `round: 1`, no `prior_head_sha`; that is the common path and it is not an error.

### Step 3 - Read the Performance Surface

Cite real `file:line` per finding. Open:

**Prisma:** every changed `schema.prisma` model (relations, `@@index`, `@db.*`), every changed repository / service (`findMany` / `findUnique` / `include` / `select` / `where` / `orderBy`), controllers (`@UseInterceptors`, response DTOs), `prisma.service.ts` / config for `connection_limit` / `log`, migrations under `prisma/migrations/`.

**TypeORM:** every changed entity (`@Entity`, `@OneToMany`, `@ManyToOne`, `@Index`, `eager`), repositories (`find` / `createQueryBuilder` / `relations`), Express routes / middleware (async error forwarding), DTOs (Zod / Joi / class-validator), `data-source.ts` for `poolSize` / `extra.max` / `synchronize`, migrations under `src/migrations/`.

**Both:** BullMQ producers, `@Processor` classes, queue config.

If the diff is small but ripples into unchanged code (a new endpoint calling an existing N+1 repository), read the unchanged file - the regression lives there.

### Step 4 - ORM Hotspots (Prisma or TypeORM)

Canonical patterns: Use skill: `node-prisma-patterns` (Prisma) or `node-typeorm-patterns` (TypeORM). This step flags deviations - skip the irrelevant subsection on monoglot projects.

- [ ] **N+1**: Prisma `include` / `select`; TypeORM `relations: [...]` or `leftJoinAndSelect` (avoid `eager: true` on collections - cartesian explosion). The fix is a bounded number of queries, not one: TypeORM's `leftJoinAndSelect` emits a single JOIN, but Prisma's default `relationLoadStrategy` is `query` - one statement per relation level, stitched in memory - so nested `include` is a few round trips, not one, and only `relationLoadStrategy: "join"` makes it a JOIN - which needs `previewFeatures = ["relationJoins"]` in the generator block before Prisma 6.7, and is Postgres/MySQL only. Either way the win is over a per-row loop, which is O(rows)
- [ ] **Overfetch**: Prisma `select`; TypeORM `find({ select: [...] })` - defaults return all columns including large `text` / `bytea`
- [ ] **Missing indexes** for `where` / `orderBy` / `groupBy` - flag any predicate / sort column without `@@index` (Prisma) / `@Index` (TypeORM) or migration
- [ ] **Unbounded reads**: list endpoints use `take` + cursor pagination, not bare `findMany` / `find()`
- [ ] **Per-row loops**: writes batch through Prisma `createMany` / `updateMany` or TypeORM `repository.insert([...])`. Prisma has no bulk upsert, so a per-row `upsert` loop becomes `createMany({ skipDuplicates: true })` plus a follow-up `updateMany`, or one `$executeRaw` `INSERT ... ON CONFLICT DO UPDATE`. Reads collapse into one predicate - Prisma `where: { id: { in: ids } }`, TypeORM `where: { id: In(ids) }` - then re-associate in memory. `Promise.all` over the same loop is the wrong fix: it opens N connections at once against a bounded pool
- [ ] **Existence checks**: `findFirst({ where, select: { id: true } })` / `repository.exists({ where })` (`exist()` on TypeORM < 0.3.21) over fetch-then-`length`
- [ ] **Connection pool sized**: Use skill: `node-connection-pool-sizing` for the math (API replicas + workers + rolling deploys vs Postgres `max_connections`, plus pooler tier). Flag deviations. When replica count or `max_connections` is unreadable, the sizing verdict is not computable - say so and still report the checks that are (worker `concurrency` vs pool is arithmetic you always have)
- [ ] **Prod-unsafe config**: TypeORM `synchronize: true` (Critical); Prisma `log: ['query']` in prod (High)

### Step 5 - Indexes and Migrations

Use skill: `node-migration-safety` for changes in `prisma/migrations/` or `src/migrations/`.

- [ ] Every column in `where` / `orderBy` / `groupBy` backed by an index
- [ ] Composite indexes match leftmost-prefix
- [ ] FK columns indexed (PostgreSQL does not auto-index FKs)
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY`, which must run outside a transaction. Prisma: `--create-only` plus a migration file holding that single statement and nothing else (Postgres wraps a multi-statement script in one implicit transaction). TypeORM wraps migrations in a transaction by default, so `queryRunner.query(...)` alone still fails - the migration needs `migrationsTransactionMode: "none"`, isolated in its own deploy
- [ ] `SET LOCAL lock_timeout = '3s'` **inside** the migration's transaction before DDL on large tables - standalone `SET` is a no-op outside a transaction and contaminates the pooled connection for every later borrower. Not applicable to a `CONCURRENTLY` migration, which takes no blocking lock
- [ ] Unique constraints at the DB level, not just `@unique` on a non-managed column
- [ ] Partial indexes for boolean/enum filters selecting a small subset
- [ ] No DDL on hot tables in a single migration (expand-then-contract)
- [ ] Backfill via keyset pagination (`WHERE id > $1 ORDER BY id LIMIT N`), never `WHERE col IS NULL LIMIT N`
- [ ] Data migrations isolated from DDL migrations
- [ ] Enum changes safe: PostgreSQL `ALTER TYPE ... ADD VALUE` cannot be used in the same transaction that adds it (pre-PG12: cannot run in a transaction at all). TypeORM wraps migrations in a transaction by default; Prisma adds none of its own, but Postgres wraps any multi-statement file in one

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot - validate the index is needed (selectivity, shape), then assess safety. When the diff _adds a column_ also queried on, flag the missing index proactively.

**Migration impact template.** State the impact before approving DDL on a hot table: _"Building this index on a 50M-row table without `CONCURRENTLY` blocks writes for 5-30 min at this scale."_ Name the lock correctly: a non-concurrent `CREATE INDEX` takes `SHARE`, which blocks writes and lets reads through, while `ALTER TABLE` DDL takes `ACCESS EXCLUSIVE`, which blocks both. Do not tell a team its read path goes dark during an index build. If row count is unknown, ask, or note "row count not in diff - confirm before deploy."

### Step 6 - Async Correctness and Event Loop

**Impact heuristic.** A blocking call inside an async handler stalls _every request in flight on this Node process_. Phrase impact as "tail-latency contagion across in-flight requests," not "this request is slow." HTTP to a critical-path upstream inherits its tail: your p99 = max(your work, upstream p99); recommend `AbortSignal.timeout(500)` + fallback, or async via decision cache / circuit breaker.

Canonical contracts: Use skill: `node-http-client-patterns` (timeout, retry budget, BullMQ delegation, per-vendor wrapper) and `node-transaction-patterns` (no I/O inside open transactions, post-commit dispatch, outbox). Flag deviations.

- [ ] **No blocking I/O / CPU on the event loop**: `fs.readFileSync`, `crypto.pbkdf2Sync`, large `JSON.parse` of untrusted size, large regex on user input -> `worker_threads` (`piscina`) or a BullMQ sandboxed processor. Sync at startup is fine. This applies to **worker paths too**, not just request paths: a blocked loop stops BullMQ lock renewal, so the job is declared stalled and re-run concurrently with the original
- [ ] **Response serialization bounded**: `res.json()` / `JSON.stringify` on a large payload blocks the loop for the whole serialization, and the cost is invisible in query timings. Cap the row count (pagination, `take`), stream (`QueryBuilder.stream()`, NDJSON, `JSONStream`) for exports, or precompute. When a profile shows time in `JSON.stringify`, the fix is a smaller payload, not a faster serializer
- [ ] **No external I/O inside a transaction** (see `node-transaction-patterns`): `axios` / `fetch` / `queue.add()` inside `prisma.$transaction` / `dataSource.transaction` holds a pooled connection for the upstream's tail; capture inside, dispatch after commit
- [ ] **Bounded concurrency**: `Promise.all` / `Promise.allSettled` over sequential `for...of await`; large fan-out bounded via `p-limit` / `bottleneck` / BullMQ
- [ ] **`AbortSignal.timeout(...)` on every external call** (see `node-http-client-patterns`) - Node's default HTTP timeout is effectively infinite
- [ ] **HTTP clients module-level**: shared `axios.create()` / `undici` Pool, not per-request (see `node-http-client-patterns`)
- [ ] **NestJS request-scoped providers**: `Scope.REQUEST` only when needed (per-request transaction / multi-tenant); default-singleton otherwise. Move heavy interceptor / pipe logic post-response via `tap`

### Step 7 - Validation / Serialization

**NestJS:**
- [ ] **`ValidationPipe` registered once globally**, not reconstructed per route - that repetition is the perf concern. Its `whitelist` / `forbidNonWhitelisted` settings are a security control owned by `task-node-review-security`; do not raise them from this lens
- [ ] **`class-validator` / `class-transformer` overhead**: reflective, not free at high QPS; prefer Zod for hot paths. Flag expensive `@Transform` and `ClassSerializerInterceptor` use - project at the query layer (Prisma `select`, TypeORM `select`) over excluding at serialization

**Express:**
- [ ] **Zod schemas reused** (top-level `const`, not per-request); `safeParse` integrates more cleanly with handler return paths than `parse`
- [ ] **Body size limit**: body-parser already defaults to `100kb`, so a bare `express.json()` is not the finding - a raised `limit`, or an `express.raw()` / `express.text()` mounted without one, is

### Step 8 - Caching and Response Performance

- [ ] **In-process**: `lru-cache` (eviction-aware) for hot reads; Redis (`ioredis`) for shared / multi-instance
- [ ] **Stampede protection**: hot keys with expensive regen use single-flight (`p-memoize` / per-key `Map<string, Promise<T>>`); distributed via Redis `SET NX EX`
- [ ] **Invalidation explicit** - document staleness budget; no never-expiring caches
- [ ] **NestJS `CacheModule`**: TTL set; `cacheKey` includes principal for per-user variation
- [ ] **HTTP caching** (`Cache-Control`, `ETag`) on read-heavy GETs
- [ ] **Response compression** (`compression` for Express) for JSON > 2KB
- [ ] **Per-request memoization**: `Symbol`-keyed property on `req` / NestJS `RequestContext` for cross-middleware values

### Step 9 - BullMQ / Background Work

Use skill: `node-bullmq-patterns`. Apply the review-scoped scan:

- [ ] **Idempotent + ID payloads**: re-fetch state, return early if done; payload uses IDs / primitives, never ORM entities. `queue.add(name, data, { jobId: businessKey })` for server-side dedup
- [ ] **`queue.add()` AFTER commit**: never inside `prisma.$transaction` / `dataSource.transaction` - worker may pick up before the row is visible. Use post-commit hook / `EventEmitter2`
- [ ] **Retry + DLQ**: `attempts` + `backoff: { type: 'exponential' }`, `removeOnComplete` / `removeOnFail` (prevent Redis growth); failed jobs surfaced via observability
- [ ] **Queue routing + Worker concurrency**: time-sensitive on dedicated queue; concurrency aligned to downstream capacity, not CPU count
- [ ] **`lockDuration` survives the job**: a worker renews its lock on a timer, so a long *non-blocking* job is safe. What breaks renewal is a blocked event loop or a dropped Redis connection - then BullMQ declares the job stalled and re-runs it concurrently with the original. CPU-bound handlers need a sandboxed processor (separate process) or a raised `lockDuration`; long I/O-bound ones usually need neither
- [ ] **Worker concurrency fits the pool**: `concurrency + 2 <= ` the per-process DB pool (`node-connection-pool-sizing`), summed across worker replicas against `max_connections`

### Step 10 - Observability for Perf (delegation handoff)

Depth on observability belongs to `task-node-review-observability`. Confirm only:

- [ ] Slow paths from this PR have **some** instrumentation (OTel span or `prom-client` histogram); if not, raise as Low / Recommendation and delegate
- [ ] Prisma `log: ['query']` / TypeORM `logging: true` not enabled in prod (only if in diff)

Beyond presence/absence -> `task-node-review-observability` owns it.

**One construct, one finding.** A construct carrying several defects (an unpaginated `findMany` that also overfetches) publishes once at the worst impact, naming the others in its Issue line.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary.

Its `Label` wins over the impact mapping: a `### High Impact` finding tagged `[Recommend]` because it is pre-existing and untouched is the correct output, not a contradiction.

Two carve-outs. Subagent runs skip it - the parent verifies the merged set once. Whole-service sweeps skip it too: with no diff every finding attributes as `Pre-existing` and every `[Must]` would de-escalate. A sweep instead runs **claim confirmation only** - re-read each construct you cited, drop anything that is not really there or not really reachable, and skip attribution and de-escalation entirely - then reports `Findings verified: inline (no diff)`, appending `, <K> dropped` when confirmation dropped any.

**Round 2+ (standalone).** When the re-review gate set `round > 1`, use skill: `review-prior-findings-reconcile` with the prior report body, the diff (or, on a sweep, the in-scope file list), and `git diff --name-status`. Insert its table under `## Prior Round Reconciliation` and fold `Still open` rows into Next Steps suffixed `(open since round <N>)`. A quarterly sweep re-keys the same report file every time, so without this the counter increments while last quarter's findings are silently re-reported as new.

### Step 11 - Write Report

**Subagent mode:** if invoked by `task-node-review`, do not write a file - `review-report-writer` is invoked only by the workflow that owns the report. Return exactly four things, and this list supersedes any generic "return your Output Format" instruction in the parent's prompt:

1. The findings, each carrying its `[Must]` / `[Recommend]` label and its `file:line`
2. `## Next Steps`, tagged and ordered, for the parent to re-sort into its own
3. `## Recommendations` (the parent's Summary has no perf fields, so anything Summary-shaped that still matters goes here as a bullet)
4. At `deep`, `## Capacity Guidance` and `## Load Plan`, which the parent preserves as their own sections

Omit the Summary block - the parent owns it. Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-perf` and every field it marks required:

- `report_body` (the assembled Markdown), `branch`, `base_ref`, `head_ref` - from the precondition handle, or from the repo on a sweep
- `base_sha` / `head_sha` captured in Step 2 via `git rev-parse`
- `scope: +perf`, `depth` as invoked, `stack = node-typescript`, `mode: full`
- `round` from Step 2's re-review gate, plus `prior_head_sha` when round > 1

Write before ending; print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Envelope precedence.** The atomics loaded in Steps 4-9 (`node-prisma-patterns`, `node-typeorm-patterns`, `node-connection-pool-sizing`, `node-migration-safety`, `node-http-client-patterns`, `node-transaction-patterns`, `node-bullmq-patterns`) each define their own assessment envelope and severity scale. Fold their content into the finding blocks below under this skill's impact scale; do not append their envelopes as separate sections. The one exception is the Pool Sizing Assessment, which has its own slot at `deep` under `## Capacity Guidance`.

Every finding carries exactly one label: `[Must]` or `[Recommend]`. No other label is written.

```markdown
## Node.js Performance Review Summary

- **Stack Detected:** Node.js <version> / TypeScript <version>
- **Framework:** NestJS <version> | Express <version> | mixed
- **ORM:** Prisma <version> | TypeORM <version> | mixed
- **Target:** <base_ref>...<head_ref>, or the swept scope at `HEAD` on a sweep
- **Evidence:** <profiler / APM figures supplied, or "static review only">
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(omit the parenthetical when K is 0; sweeps: `inline (no diff)`)_
- **Overall:** Clean | Issues Found - [<N> Critical / <N> High / <N> Medium / <N> Low]

## Findings

### Critical

_Data loss or a service-wide outage on deploy: TypeORM `synchronize: true` outside dev, `prisma db push` against a non-dev database, a pool ceiling already breached at deploy peak. High = a user-visible regression on a hot path. Medium = measurable cost off the hot path, or a ceiling that binds at the next growth step. Low = a quick win with no current impact._

1. **[Must]** **Location:** [file:line - add `_(pre-existing)_` or `(unverified: <reason>)` when the verify pass returned one]

   **Issue:** [Node idiom: N+1 via per-iteration `findMany` in `for...of`, missing index, `crypto.pbkdf2Sync` in a request path, BullMQ `queue.add` inside a transaction, TypeORM `eager: true` cartesian, etc.]

   **Impact:** [estimated: "N+1 in OrdersController.list adds ~200 queries per request at 100 orders" / measured: "p95 800ms -> 120ms after fix"]

   **Fix:** [Node change with code: `include`, `relations`, `await`, BullMQ `jobId`, etc. Several fixes on one construct become a numbered list here.]

### High Impact

[Same numbered-block structure; numbering continues across tiers]

### Medium Impact

[Same]

### Low Impact / Quick Wins

[Same]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a finding - e.g., "Switch list endpoint to cursor pagination", "Add Redis cache for product catalog reads", "Move PDF generation to BullMQ"]

## Capacity Guidance

_(`deep` only - omit at `standard`.)_
`node-connection-pool-sizing`'s Pool Sizing Assessment, including its `Verdict:` row, plus the headroom the fixes above buy. State every assumed input inline.

## Load Plan

_(`deep` only - omit at `standard`.)_
What to measure before and after, in order: the profile to capture (`node --cpu-prof`, `--heap-prof`, `perf_hooks.monitorEventLoopDelay()`, or an OTel trace), the baseline figure per target endpoint, the fix order gated on those figures, and the soak that confirms it. Name tools the project can actually run.

## Next Steps

Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: schema] - [one-line action]

_Omit if no actionable findings._
```

Impact maps to label: Critical / High -> `[Must]`; Medium / Low -> `[Recommend]` - unless the verify pass returned a different `Label`, which wins.

## Self-Check

- [ ] `behavioral-principles` loaded first; stack, framework, ORM recorded; diff/log read once and SHAs captured via `git rev-parse`; re-review gate applied; perf surface read directly (Steps 1-3)
- [ ] ORM atomics consulted; N+1, overfetch, missing indexes, unbounded reads, per-row loops, existence checks, pool sizing, prod-unsafe config covered (Step 4)
- [ ] Migration-safety atomic consulted on migration changes: `lock_timeout`, CONCURRENTLY, keyset backfill, expand-contract (Step 5)
- [ ] Async audit: blocking I/O, `Promise.all` boundedness, `AbortSignal`, request-scoped providers, no I/O in transactions (Step 6)
- [ ] Validation / serialization, caching, BullMQ assessed when diff touches them (Steps 7-9)
- [ ] Observability presence/absence confirmed; depth delegated (Step 10)
- [ ] `review-finding-verify` ran and its tally reached the Summary - or a documented carve-out applied (subagent, or sweep reporting `inline (no diff)`); its `Label` carried, overriding the impact mapping
- [ ] Depth honored: `standard` ran all; `deep` and every sweep filled `Capacity Guidance` and `Load Plan`
- [ ] Every finding states measured or estimated impact and carries one label; one construct publishes one finding; findings ordered by impact
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend
- [ ] Step 11: standalone: every required writer field assembled, report written, confirmation printed; subagent: labelled findings + Next Steps + Recommendations + deep sections returned, no file written

## Avoid

- `git fetch` / `git checkout` from this workflow - user runs these
- Reporting issues without naming the Node idiom ("this is slow" vs "N+1 from per-iteration `findMany`")
- Generic backend advice when a Node pattern applies (say "use `include`", not "use eager loading")
- Suggesting `eager: true` on TypeORM collection relations to fix N+1 - forces eager on every query; use per-query `relations: [...]` or `leftJoinAndSelect`
- Suggesting caching without invalidation strategy
- Conflating perf with general or security review
- Treating BullMQ retries as a substitute for idempotency
- Recommending sync APIs (`fs.readFileSync`, `crypto.pbkdf2Sync`) on request paths
- Swapping a sync hash for its async callback form and calling it fixed - `crypto.pbkdf2` lands on the 4-thread libuv pool shared with `fs` and `dns.lookup`; move the work off-process instead
- Prescribing a bare `SET` for a migration timeout, or `queryRunner.query('CREATE INDEX CONCURRENTLY ...')` inside TypeORM's default migration transaction
- Claiming a nested Prisma `include` is one query - the default load strategy is one query per relation level
- Recommending `setTimeout(..., 0)` to "yield" - pushes work to the next macrotask but doesn't free the event loop; use `worker_threads` for CPU
- Reporting "missing index" without confirming the column appears in `where` / `orderBy` / `groupBy`
- Approving `synchronize: true` (TypeORM) or `prisma db push` for non-dev environments
