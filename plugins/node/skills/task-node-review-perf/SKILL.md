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

Node.js-aware performance review naming Prisma `include` / `select` / `findMany`, TypeORM relations / QueryBuilder, event-loop discipline, NestJS interceptor / pipe overhead, BullMQ throughput, and migration lock cost. Findings carry measured or estimated impact (latency, throughput, query count, event-loop lag) and concrete TypeScript fixes.

## When to Use

- NestJS or Express PR / branch perf regression review
- Slow endpoint / BullMQ job / cron investigation, or a quarterly N+1 / pool / async sweep against APM data (whole-service sweep, below)

**Not for:** general review (`task-node-review`), security (`task-node-review-security`), pre-implementation design (`task-node-implement`).

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Steps 1-11 |
| `deep` | Requested, handed down by a parent, profiler / APM data supplied, or any whole-service sweep | Steps 1-11 + `## Capacity Guidance` + `## Load Plan` |

## Invocation

`/task-node-review-perf [<branch> | pr-<N>] [--base <branch>] [standard | deep] [sweep]`

Defaults to the current branch vs its base; fails fast on trunk. As a subagent of `task-node-review`, Step 3 is pre-satisfied and Step 11 takes its subagent branch.

**Whole-service sweep** - decided before Step 3: the invocation says `sweep`, or asks for a sweep / investigation with no PR, or supplies profiler / APM data with no branch argument while the checked-out branch is trunk. A bare invocation on trunk is not a sweep - Step 3 runs and fails fast. On the sweep:

- Scope is the service's source root, or the paths the request named; every "changed" / "in the diff" wording reads "in scope". Findings cite current code at the named branch, else `HEAD`, read via `git show <ref>:<path>`; `[Implement]` means a fix inside the swept scope.
- The run is `deep`. Rank by the supplied evidence first: an endpoint named in the APM data outranks a checklist hit with no measurement behind it.
- No precondition check, no round gate, no writer: Step 10 verifies inline and the report body is the response. Summary `Target:` names the swept scope.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept the parent's confirmation when invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`; accept a pre-confirmed stack from a parent. Not Node -> stop and route to `/task-code-review-perf`. Record from evidence (a parent passes these):

- `Framework`: NestJS (`nest-cli.json` / `@nestjs/core`), Express, or `mixed` - apply each app's idioms to its own files
- `ORM`: Prisma (`@prisma/client`; note the major - Prisma 7 / `@prisma/adapter-*` pools through the adapter), TypeORM (note the driver: `pg` or `mysql2`), both (each ORM's atomic on its own files), or `other` (no ORM atomic; generic query checks, noted)

### Step 3 - Resolve the Diff (standalone only)

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-perf`. A fail-fast surfaces verbatim and stops. A sweep is decided from the invocation before this step and never runs it, so a precondition failure never routes there.

**Round gate.** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading anything else: a valid `prior_checkpoint` whose `head_sha` and `base_sha` equal the captured ones and whose `depth` covers the resolved one (`deep` covers `standard`) -> print `No new commits on <head_short_name> since prior perf review at <sha_short>. Prior report unchanged.` (`<sha_short>` = first 7 chars of `head_sha`) and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 11 write overwrites the file) -> `round: 1`, no `prior_head_sha`.

Then read once: `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, `git log --oneline <base_ref>..<head_ref>`. Every file outside the diff is read with `git show <head_ref>:<path>`.

### Step 4 - Read the Performance Surface

Cite real `file:line`. Open:

- **Prisma:** changed `schema.prisma` models (relations, `@@index`, `@db.*`), repositories / services (`findMany` / `include` / `select` / `where` / `orderBy`), controllers and response DTOs, migrations under `prisma/migrations/`, and the pool config - the `DATABASE_URL` in env / deploy manifests on Prisma 5-6, the adapter's `max` on Prisma 7
- **TypeORM:** changed entities (`@OneToMany`, `@ManyToOne`, `@Index`, `eager`), repositories (`find` / `createQueryBuilder` / `relations`), the `DataSource` options (`extra.max` / `poolSize` / `synchronize`), migrations
- **Both:** BullMQ producers, processors, queue options - every processor sharing a worker process, since the pool check sums them; outbound clients; interceptors and pipes

A small diff that calls into unchanged code (a new endpoint on an existing N+1 repository) means reading the unchanged file - the regression lives there.

### Step 5 - ORM Hotspots

Use skill: `node-prisma-patterns` (Prisma) or `node-typeorm-patterns` (TypeORM). Flag deviations:

- [ ] **N+1** - Prisma `include` / `select`; TypeORM `relations` or `leftJoinAndSelect` (never `eager: true` on a collection). Without the `relationJoins` preview Prisma runs one query per relation level; with it, `relationLoadStrategy: "join"` is the default (one query: `LATERAL` on PostgreSQL, correlated subqueries on MySQL). The win is a bounded query count over a per-row loop, not necessarily one query. `Promise.all(ids.map(id => findUnique(...)))` is batched by Prisma into one query and is not an N+1
- [ ] **Collection join plus pagination** (TypeORM) - with `leftJoinAndSelect` on a collection, `limit` / `offset` page the joined rows (a page holds fewer roots than asked - `[Must]`), and `skip` / `take` wrap a `DISTINCT` id subquery that pages wrong under a joined-column sort; use a two-phase page (ids, then relations) or `relationLoadStrategy: "query"`
- [ ] **Overfetch** - Prisma `select`; TypeORM `find({ select: { id: true, ... } })`; large `text` / `jsonb` / `bytea` columns never fetched by default in a list
- [ ] **Unbounded reads** - list endpoints use `take` + keyset (cursor) pagination, not bare `findMany` / `find()`; an offset page over a large table is Medium
- [ ] **Per-row writes** - batch with `createMany` (a per-row array) / `updateMany` (one `data` for every matched row) or TypeORM `insert([...])`. A per-row `upsert` with per-row values becomes one `$executeRaw` `INSERT ... ON CONFLICT DO UPDATE SET col = EXCLUDED.col` (PostgreSQL), or chunked `upsert` calls inside one `$transaction`. Reads collapse to one predicate (`where: { id: { in: ids } }`, TypeORM `In(ids)`), re-associated in memory. `Promise.all` over a per-row write loop (or non-`findUnique` reads) is not the fix: it still issues N queries, which queue on the pool (`P2024` after `pool_timeout`, or an indefinite wait on node-`pg`'s default `connectionTimeoutMillis: 0`)
- [ ] **Existence checks** - `findFirst({ where, select: { id: true } })` / `repository.exists({ where })` over fetch-then-`length`
- [ ] **Pool sizing** - Use skill: `node-connection-pool-sizing`: per-process pool x processes (API replicas + workers + surge during rolling deploys) against `max_connections` minus reserved and ops slots; summed worker `concurrency` per process (x fan-out) + 2 <= the per-process pool; a sandboxed processor checks each child. A measured holder count (an incident, a `pg_stat_activity` figure) beats the formula; say which was used. When replica count or `max_connections` is unreadable, compute the verdict on stated assumptions and suffix it `(assumed)`, per `node-connection-pool-sizing`, naming each assumed input in Notes. A pool finding files in Findings; `## Capacity Guidance` carries the arithmetic, not a second copy of the finding
- [ ] **Prod-unsafe config** - TypeORM `synchronize: true` or `prisma db push` outside dev (Critical); Prisma `log: ['query']` / TypeORM `logging: true` in prod (High)

### Step 6 - Indexes and Migrations

Use skill: `node-migration-safety` when the diff touches a migration.

- [ ] Every column in `where` / `orderBy` / `groupBy` backed by an index; composite indexes match leftmost prefix; FK columns indexed (PostgreSQL does not auto-index them)
- [ ] **`CREATE INDEX CONCURRENTLY`** on a large table, outside a transaction. Prisma: `--create-only`, a migration file holding that one statement (a multi-statement file runs as one implicit transaction), and the index mirrored in `schema.prisma` as `@@index(..., map: "<name>")` so the next `migrate dev` does not drop it. TypeORM: `public transaction = false` on that migration class and `migration:run -t each` - the DataSource-wide `migrationsTransactionMode: "none"` turns transactions off for every migration. A failed concurrent build leaves an INVALID index: check `indisvalid`, then drop and re-create (or `REINDEX INDEX CONCURRENTLY`)
- [ ] **Lock timeouts** - inside a migration transaction, `SET LOCAL lock_timeout = '3s'` before DDL on a large table (`SET LOCAL` outside a transaction is a no-op); under `transaction = false`, a plain `SET lock_timeout` followed by `RESET lock_timeout` in the same migration. Leave the concurrent index build itself unbounded - a timeout makes it fail and leaves an INVALID index
- [ ] **Lock cost named correctly** - a non-concurrent `CREATE INDEX` takes `SHARE` (blocks writes, reads continue); every `ADD COLUMN`, `SET NOT NULL`, and `ALTER TYPE` takes `ACCESS EXCLUSIVE` (blocks reads and writes) - brief for a nullable or constant-default add, which still queues every later query behind a long reader, and held for a full rewrite on a volatile default or a type change; `ADD CONSTRAINT ... FOREIGN KEY` takes `SHARE ROW EXCLUSIVE` on both tables and `VALIDATE CONSTRAINT` `SHARE UPDATE EXCLUSIVE`. State the impact: "a non-concurrent index on the 48M-row `Order` table blocks writes for the whole build". Row count not in the repo -> rate as if large and say so in Impact
- [ ] Unique constraints at the DB level; partial indexes for selective boolean / enum filters
- [ ] Expand-then-contract for hot-table DDL; backfills batched by primary-key range, in their own migration or job, never with DDL
- [ ] **Enum changes** - a value added with `ALTER TYPE ... ADD VALUE` cannot be used in the transaction that added it (PG 12+; before 12 the statement cannot run in a transaction block). TypeORM's default `all` mode runs every pending migration in one transaction, so use `-t each` or ship the backfill in a later deploy

When the diff *adds* an index, treat it as evidence the column is hot: check selectivity and shape, then safety. When it adds a queried column with no index, flag the missing index.

### Step 7 - Async Correctness and Event Loop

Use skill: `node-http-client-patterns` (after `ops-resiliency`) when the diff has an outbound call, and `node-transaction-patterns` (after `backend-transaction-patterns`) when it opens a transaction. Phrase blocking impact as tail-latency contagion across every request in flight on the process, not "this request is slow". A synchronous upstream call adds its latency to yours: your p99 is at least your own work plus the upstream's p99 on that path.

- [ ] **No blocking CPU / I/O on the loop** - `fs.readFileSync`, `crypto.pbkdf2Sync` / `scryptSync`, large `JSON.parse` of untrusted size -> a `piscina` worker pool or a BullMQ sandboxed processor; a catastrophic regex -> a linear-time pattern or `re2` plus an input length cap (offloading it still pins a thread per request). Sync at startup is fine. Worker paths count too: a blocked loop stops BullMQ lock renewal, the job is declared stalled, and it re-runs concurrently with the original. The async `crypto.pbkdf2` frees the loop but contends the 4-thread libuv pool shared with `fs`, `dns.lookup`, and `zlib` - size `UV_THREADPOOL_SIZE` or move the work off-thread
- [ ] **Response serialization bounded** - `res.json()` / `JSON.stringify` on a large payload blocks the loop for the whole serialization, invisibly to query timings. Cap rows (pagination), stream exports (TypeORM `qb.stream()` on a dedicated `QueryRunner`; Prisma cursor-batched reads; NDJSON), or precompute
- [ ] **No external I/O inside a transaction** - `fetch` / `axios` / `queue.add()` inside `$transaction` / `dataSource.transaction` holds a pooled connection for the upstream's tail
- [ ] **Bounded concurrency** - independent I/O runs concurrently (`Promise.all` over a small, fixed set), and fan-out over a collection is bounded (`p-limit`, `bottleneck`, or a queue); per-row DB work is a set-based query, not concurrency
- [ ] **A total deadline on every external call** - `AbortSignal.timeout(ms)` on `fetch` / `undici.request` / axios `signal`. `fetch` has only 300 s idle timers (`headersTimeout` / `bodyTimeout`) and no total deadline; `http.request` and axios default to none
- [ ] **One keep-alive agent per upstream** - the pool lives in the agent (`undici.Agent`, `http.Agent({ keepAlive: true })`), created at module scope; `axios.create()` only merges config, so a per-request agent still defeats reuse
- [ ] **NestJS request scope** - `Scope.REQUEST` only where needed (it re-instantiates the provider chain per request). An interceptor's `tap()` runs before the response is written, so heavy work there adds latency - defer it (`res.on('finish')`, a queue)

### Step 8 - Validation and Serialization

- [ ] **NestJS** - class-validator / class-transformer are reflective and cost CPU per request at high QPS; `ClassSerializerInterceptor` with `@Exclude` serializes the full object first - project at the query (`select`) instead. `ValidationPipe` security options belong to `task-node-review-security`
- [ ] **Express** - Zod schemas defined once at module scope, not per request
- [ ] **Body limits** - body-parser defaults every parser (`json`, `raw`, `text`, `urlencoded`) to `100kb`; the finding is a raised `limit`, or an upload path with no cap (`multer` without `limits`, a raw `req` pipe)

### Step 9 - Caching and BullMQ

- [ ] **Caching** - `lru-cache` for in-process hot reads, Redis for shared ones; single-flight on expensive regeneration (a per-key `Map<string, Promise<T>>` deleted on settle, or `p-memoize` with an expiring cache); every cache has a TTL and a stated staleness budget. NestJS `CacheInterceptor` keys on the URL - per-user responses need an overridden `trackBy()` or no cache. `Cache-Control` / `ETag` on read-heavy GETs; `compression` for JSON over ~2 KB when no proxy compresses
- [ ] **BullMQ** - Use skill: `node-bullmq-patterns`. Payloads carry ids, never ORM objects. `queue.add` after `$transaction` resolves (at-most-once) or via an outbox. `attempts` + `backoff: { type: 'exponential', delay }` in the queue's `defaultJobOptions`; `removeOnComplete` / `removeOnFail` ages bounded - and longer than any `jobId` dedup window, since dedup lasts only while the job is retained; permanent failures (validation, a vendor 4xx) throw `UnrecoverableError` rather than burn retries. Time-sensitive work on its own queue; `concurrency` sized to the downstream and the pool (Step 5), not to CPU count. A long non-blocking job renews its lock and is safe; a CPU-bound one needs a sandboxed processor or a raised `lockDuration`

- [ ] **Instrumentation presence** - a slow path this PR adds has some instrumentation (an OTel span or a `prom-client` histogram); absence is a Low with a `[Delegate]` - depth belongs to `task-node-review-observability`

### Step 10 - Verify and Reconcile

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying the `Label` and `Annotation` columns, and fill `Findings verified:` in the atomic's Summary form. Subagent runs skip verification - the parent verifies the merged set. A sweep skips it too (no diff): re-read each cited construct at `HEAD`, drop what the code contradicts, mark what cannot be settled in-tree `_(unverified: <reason>)_`, and report `Findings verified: inline (no diff)`, appending `, <K> dropped` when any dropped.

**Round 2+ (standalone, after verification).** Project the prior report at the handle's `report_path` into reconcile's parse shape: one `## High-Impact Findings` section, and per prior finding (every tier) a `### [<Label>] <file:line>` heading - the label from its bold `[Must]` / `[Recommend]` token (a prior report with none: the label its tier maps to), the `file:line` prefix of its Location, each Location annotation as its own group (`_(pre-existing; newly reachable via ...)_` split into `_(pre-existing)_ _(newly reachable via ...)_`), a prior `_(carried from round <N>)_` kept - followed by its Issue line as `Issue:`. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files`. Its table, note line, and tally render as `## Prior Round Reconciliation`. A row is re-derived when this round's findings hold one on the same construct with the same smell. A `Still open` or `Needs re-check` row this round re-derived publishes once, at this round's label; one it did not re-derive republishes its prior block verbatim in its prior tier - every field, the Location with all its annotation groups - at its prior label, with `_(carried from round <N>)_` after the label unless the block already carries one (`<N>` = the round it first appeared), outside the verify tally, plus a Next Steps entry suffixed `(open since round <N>)`. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` is never carried.

### Step 11 - Write Report

**Subagent mode** (invoked by `task-node-review`): return only `## Findings` with its tier sections and any `out of lens` lines, plus - at `deep` - `## Capacity Guidance` and `## Load Plan`. No Summary, Recommendations, Next Steps, or file; the parent owns the report. This supersedes any generic "return your Output Format" in the parent's prompt.

**Sweep:** emit the report body as the response; no writer.

**Standalone:** Use skill: `review-report-writer` with `report_type: review-perf`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the round gate, `scope: +perf`, `depth` as resolved, `stack = node-typescript`, `mode: full`, `round` and `prior_head_sha` from the round gate, and `pr_url` when the request carried one, else `prior_checkpoint.pr_url` when present. Emit the body, then the writer's confirmation line.

## Output Format

Emit `report_body` as raw Markdown; the fence delimits the template for display only, and brace annotations in it are authoring notes, never emitted.

**Impact tiers.** **Critical** = data loss or a service-wide outage on deploy (`synchronize: true` outside dev, `prisma db push` against a shared database, a pool ceiling already breached at deploy peak, a write-blocking index build on a large hot table). **High** = a user-visible regression on a hot path. **Medium** = measurable cost off the hot path, or a ceiling that binds at the next growth step. **Low** = a quick win with no current impact. Rank by certainty times reach: a deterministic defect on one path and a probabilistic one on every path both reach High only when the user-visible effect does. An entity-level default (`eager: true`) that drives several endpoints files once, on the entity, naming the endpoints.

**Labels.** Critical / High -> `[Must]`; Medium / Low -> `[Recommend]` - unless the verify pass returned a different `Label`, which wins: a finding sits in the section of its tier while its label is the published one, so a `[Recommend]` under High is correct. No other label is written.

**One construct, one finding.** A construct carrying several defects (an unpaginated `findMany` that also overfetches) files once at the worst tier, naming the others in its Issue and numbering the fixes. **A defect this lens does not own is reported, never dropped:** one `- **out of lens:** file:line - <the defect, and the workflow that owns it>` line per defect, at the end of `## Findings`, for a defect outside this lens that would break the build, corrupt, lose, or expose data, or block legitimate traffic (anything else is left to `task-node-review`), untiered and uncounted; a parent drafts it as a finding.

**Envelope precedence.** The atomics loaded in Steps 5-9 (`node-prisma-patterns`, `node-typeorm-patterns`, `node-connection-pool-sizing`, `node-migration-safety`, `node-http-client-patterns`, `node-transaction-patterns`, `node-bullmq-patterns`) feed findings into this template under its tiers; their own blocks are not emitted, except the Pool Sizing Assessment at `deep`, which fills `## Capacity Guidance`.

```markdown
## Node.js Performance Review Summary

- **Stack:** Node.js <version> / TypeScript <version> / <NestJS | Express | mixed> / <Prisma | TypeORM | Prisma + TypeORM | other> <version>
- **Target:** <base_ref>...<head_ref> | <the swept scope at HEAD>
- **Depth:** standard | deep
- **Round:** <N>   {round 2+ only}
- **Evidence:** <profiler / APM figures supplied, or `static review only`>
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)} | inline (no diff){, <K> dropped}
- **Overall:** Clean | Issues Found - <n> Critical / <n> High / <n> Medium / <n> Low
- **Notes:** <assumed inputs (`assumed: max_connections 100`), measured-vs-formula choices, ORM `other`, skipped steps, the handle's own notes>   {omit when none}

## Findings

### Critical

1. **[Must | Recommend]**{ _(carried from round <N>)_} **Location:** <file:line>{ <verify annotation groups>}

   **Issue:** <Node idiom: per-iteration `findMany` in `for...of`, missing index, `crypto.pbkdf2Sync` in a handler, `queue.add` inside `$transaction`, `eager: true` on a collection>

   **Impact:** <estimated ("adds ~200 queries per request at 100 orders") or measured ("p95 800 ms -> 120 ms")>

   **Fix:** <Node change with code; several fixes on one construct numbered>

### High Impact

<same block; numbering continues across tiers>

### Medium Impact

<same>

### Low Impact / Quick Wins

<same>

- **out of lens:** <file:line - defect, owning workflow>   {only when one exists}

{omit empty tiers; when every tier is empty, write `No performance issues found.`}

## Prior Round Reconciliation   {round 2+ standalone only}

<table, note line, and tally from `review-prior-findings-reconcile`>

## Recommendations   {omit when none}

- <structural improvement not tied to a finding>

## Capacity Guidance   {deep only}

<`node-connection-pool-sizing`'s Pool Sizing Assessment - every block's `Verdict:` and the `Overall:` line - plus the headroom the fixes buy; every assumed input stated inline>

## Load Plan   {deep only}

<in order: the profile to capture (`node --cpu-prof`, `--heap-prof`, `perf_hooks.monitorEventLoopDelay()`, an OTel trace), the baseline per target endpoint, the fix order gated on those figures, and the soak that confirms it - tools the project can run>

## Next Steps

1. **[Implement]** [Must] <file:line> - <one-line action>
2. **[Delegate]** [Recommend] [scope: schema] - <one-line action>

{one entry per finding, a carried one suffixed ` (open since round <N>)`; `[Implement]` for a fix local to the PR, `[Delegate]` when it leaves it; ordered Must > Recommend, carryovers first among equals; omit when nothing is actionable}
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: stack confirmed; `Framework` and `ORM` (with Prisma major / TypeORM driver) recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-perf`; round decided from the handle before the diff was read (or the stop line printed); subagent / sweep: step skipped
- [ ] Step 4: perf surface read, including unchanged code the diff calls into
- [ ] Step 5: ORM atomic consulted; N+1, collection-join paging, overfetch, unbounded reads, per-row writes, existence checks, pool sizing, prod-unsafe config checked
- [ ] Step 6: migration atomic consulted on migration changes; index coverage, `CONCURRENTLY` recipe per ORM, lock timeouts, lock names, unique / partial indexes, expand-contract and backfills, enum values checked
- [ ] Step 7: blocking work, serialization size, I/O in transactions, bounded concurrency, total deadlines, agent reuse, request scope checked
- [ ] Step 8: validation / serialization and body limits assessed when touched
- [ ] Step 9: caching, BullMQ, and instrumentation presence assessed when touched
- [ ] Step 10: verify ran with its tally (or the subagent / sweep carve-out); round 2+ projected and reconciled, unresolved rows carried
- [ ] Step 11: standalone report written with every writer field; subagent: findings (+ deep sections) returned, no file; sweep: body emitted
- [ ] Every finding names its impact, one tier, one label; one construct files once; `deep` filled Capacity Guidance and Load Plan

## Avoid

- State-changing git (`fetch`, `checkout`) from this workflow
- "This is slow" without the Node idiom ("N+1 from per-iteration `findMany`")
- `eager: true` on a TypeORM collection as an N+1 fix
- Caching without an invalidation rule
- Treating BullMQ retries as a substitute for an idempotent side effect
- Swapping a sync hash for its callback form and calling it fixed - the work now contends the 4-thread libuv pool
- `setTimeout(..., 0)` around an unchunked block - it defers the stall, it does not remove it
- "Missing index" without confirming the column appears in `where` / `orderBy` / `groupBy`
- Approving `synchronize: true` or `prisma db push` outside dev
