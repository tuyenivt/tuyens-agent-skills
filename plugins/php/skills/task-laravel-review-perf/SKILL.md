---
name: task-laravel-review-perf
description: Laravel perf review: Eloquent N+1, missing indexes, MySQL slow queries, queue throughput, Cache::remember, Octane/FrankenPHP, OPcache+JIT.
agent: php-performance-engineer
metadata:
  category: backend
  tags: [php, laravel, eloquent, mysql, performance, queue, horizon, octane, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Laravel Performance Review

## Purpose

Laravel-aware perf review producing findings with measured or estimated impact (latency, throughput, query count, memory, queue depth, lock contention) and concrete fixes in idiomatic Laravel. Stack-specific delegate of `task-code-review-perf`; preserves the parent contract (invocation, diff resolution, output format) so callers see a stable shape.

## When to Use

- Reviewing a Laravel PR or branch for performance regressions
- Investigating a slow endpoint, queue job, or scheduled command
- Pre-merge perf pass on Eloquent queries, Blade views, queue jobs, or caching primitives
- Quarterly N+1 / index / Horizon-supervisor review against slow-query log or APM data

**Not for:** general Laravel review (`task-laravel-review`), security review (`task-laravel-review-security`), incident response (`/task-oncall-start`), pre-implementation design (`task-laravel-implement`).

## Severity Rubric

| Severity   | Definition |
| ---------- | ---------- |
| **High**   | Production outage shape under steady load. N+1 multiplying baseline RPS by O(N); `whereRaw($input)` defeating plan cache; lazy-loaded `@foreach ($orders as $o) {{ $o->user->name }}` on a paginated endpoint; `Order::all()` on a 1M+-row table; wide `with(['a','b','c','d'])` on paginated lists (per-relation roundtrip + memory blowup); OFFSET `paginate()` on > 1M rows; worker memory leak from passing Eloquent collections; `QUEUE_CONNECTION=sync` in prod; Horizon supervisor starving Redis; missing index on hot `where` / `ORDER BY`; lock held across HTTP I/O inside `DB::transaction`. Or deploy-time outage (NOT NULL ADD with non-constant default on a 10M+ row MySQL table without `pt-online-schema-change`). |
| **Medium** | Degraded p95/p99 or wasted bandwidth. `paginate()` running `COUNT(*)` on a 1M+ row table when `cursorPaginate` suffices; `Cache::remember` without TTL or tag bound; Resource-shaped N+1; missing FULLTEXT on `LIKE '%term%'`; `Http::get` without timeout or retry. |
| **Low**    | CPU / allocation churn. String concat in tight loops; `collect()->map()->filter()` chains where `for` would do; missing `view:cache` / `config:cache` / `route:cache` in deploy; missing response compression; missing OPcache tuning; missing JIT / preload. |

Tie-breaker: "would this page on-call within 24h of a 2x traffic increase?" yes -> High; "would this drag next quarter's perf budget?" yes -> Medium.

## Depth Levels

| Depth      | When to Use                                                  | What Runs                                          |
| ---------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `standard` | Default - full Laravel perf review                           | All steps                                          |
| `deep`     | Profiling-driven review with Telescope / Clockwork / APM     | All steps + capacity guidance and load plan        |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                           | Meaning                                                                                                |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `/task-laravel-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch                                    |
| `/task-laravel-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                             |
| `/task-laravel-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                        |

When invoked as a subagent of `task-code-review-perf` (parent passes the precondition-check handle plus pre-read diff and commit log), Step 3 is skipped and parent artifacts are reused.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Skip re-loading when invoked as a subagent of `task-code-review-perf` or `task-laravel-review`.

### Step 2 - Confirm Stack and Detect Surface

Use skill: `stack-detect` to confirm PHP / Laravel (skip if parent pre-confirmed). If not Laravel, route to `/task-code-review-perf`.

Detect and record for the Summary block:

- `Database` (from `config/database.php`): MySQL `<version>` | PostgreSQL `<version>` | MariaDB `<version>`
- `Queue` (from `config/queue.php` / `.env`): `redis (Horizon)` | `database` | `sync`
- `Cache` (from `config/cache.php`): `redis` | `memcached` | `database` | `file`
- `Runtime`: `PHP-FPM` | `Octane (Swoole)` | `Octane (RoadRunner)` | `FrankenPHP`

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check`. On approval, read `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>` once and reuse. Skip when running as a subagent with parent-supplied artifacts.

### Step 4 - Read the Performance Surface

Open files governing query and concurrency behavior so impact estimates ground in real code:

- **Eloquent / DB:** changed models (`$casts`, `$with`, relationships, scopes), controllers / services / jobs (query patterns), Blade views (`@foreach $model->relation`), API Resources (`$this->relation` in `toArray()`), `config/database.php`, migrations, `AppServiceProvider::boot()` for `Model::shouldBeStrict()`
- **Queue:** changed jobs (`$tries`, `$backoff`, `$timeout`, `$maxExceptions`, `failed()`, `retryUntil()`, middleware), listeners (`ShouldQueue`), dispatch sites (`dispatch`, `Bus::batch`, `Bus::chain`, `dispatchSync`, `dispatchAfterResponse`, `->afterCommit()`), `config/queue.php`, `config/horizon.php`, `app/Console/Kernel.php`
- **HTTP / external:** `Http::*` (timeout, retry, connect-timeout), Guzzle / SDK clients constructed per-request
- **Cache:** `Cache::remember`, `Cache::tags`, `Cache::lock`, `Cache::flush`; `config/cache.php`
- **Runtime:** `bootstrap/app.php` middleware order, `config/octane.php` `flush` setting, `composer.json` static-analysis tooling

For each finding, cite a real `file:line`. When the diff is small but ripples through unchanged code, read the unchanged file - the regression lives there.

### Step 5 - Eloquent / Database Hotspots

Use skill: `laravel-eloquent-patterns` for canonical patterns. Review-scoped scan over changed queries, models, controllers, services, jobs, Blade views, Resources:

- [ ] N+1 across loops, Blade `@foreach`, and Resource `toArray()` - eager-load at controller via `with(...)` / `withCount(...)`; `Model::shouldBeStrict()` for non-prod
- [ ] **Wide eager-load chains** (`with(['a','b','c','d'])`) - each relation is a separate `WHERE IN` roundtrip; flag on paginated lists; constrain via column selects (`with('user:id,email')`) or split into per-action loads
- [ ] No `$with` auto-eager-load without justification (over-fetches every fetch)
- [ ] `Model::all()` and collection-then-paginate flagged on growable tables - require `chunkById` / `lazy` / `cursor` / `cursorPaginate` and push filters into SQL
- [ ] Pagination matches scale: `paginate()` only when `COUNT(*)` is acceptable; `cursorPaginate` on large tables; never `OFFSET` on millions
- [ ] Filter / sort / group / FK columns in the diff have a backing index migration
- [ ] `whereRaw` / `orderByRaw` / `DB::raw` use bindings; user-supplied sort columns allowlisted (dual perf+security - delegate)
- [ ] `LIKE '%term%'` flagged - require FULLTEXT or prefix-only `LIKE 'term%'`
- [ ] `firstOrCreate` / `updateOrCreate` under concurrency uses `upsert` or `lockForUpdate` in transaction; bulk writes via `insert` / `upsert` over per-row `save()` loops
- [ ] Database aggregates (`$user->reviews()->avg(...)`) over collection aggregates (`$user->reviews->avg(...)` materializes everything)
- [ ] Soft-deleted hot tables have index on `deleted_at` (or composite including it)
- [ ] No `DB::transaction()` holding row locks across HTTP / queue I/O
- [ ] `php-fpm pm.max_children` x replicas <= DB `max_connections` minus ops / replication headroom; Octane workers count differently
- [ ] Bulk `Eloquent::query()->update(...)` skipping observer events flagged when audit observers exist
- [ ] `Cache::remember(...)` callback bounded - cache amortizes only when worst case is bounded

### Step 6 - Indexes and Migrations

Use skill: `laravel-migration-safety` for any change in `database/migrations/`.

- [ ] Every column in `where` / `orderBy` / `groupBy` is backed by an index; composites match leftmost-prefix; FK indexes present
- [ ] Index additions on large tables use `ALGORITHM=INPLACE, LOCK=NONE`; clustered/PRIMARY restructures lock. For > 10M rows, require `pt-online-schema-change` or `gh-ost`
- [ ] `SET innodb_lock_wait_timeout` before DDL on large tables to fail fast under contention
- [ ] Unique constraints enforced at DB level, not only via `Validator unique:` rule
- [ ] Partial / functional indexes for low-selectivity boolean filters (MySQL 8.0+)
- [ ] Expand-then-contract for column changes on hot tables; data migrations separated from DDL migrations
- [ ] Backfills use `chunkById(1000, ...)`, never `WHERE col IS NULL LIMIT N` (re-scans)
- [ ] `php artisan migrate --force` from a single deployer step, never `Artisan::call('migrate')` on app boot

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot in `where` / `orderBy` / `groupBy` even if no query in the diff references it. When the diff _adds a column_ the app queries on, flag the missing index proactively.

**Migration impact template.** Before approving any DDL on a hot table, state: _"DDL on a 50M-row InnoDB table without `pt-online-schema-change` blocks writes for the duration (10-30 min on hot disks); replica lag spikes, connections queue. Recommend `pt-osc` with `--max-lag=5s --critical-load Threads_running=80` and a maintenance window."_ If row count is unknown, ask or note "row count not in diff - confirm before deploy."

### Step 7 - Queue Throughput, Jobs, Scheduling

Use skill: `laravel-queue-patterns`. Review-scoped scan:

- [ ] `QUEUE_CONNECTION` is not `sync` in production env; `dispatchSync` not on user-request paths
- [ ] Every job sets `$tries`, `$backoff`, `$timeout`, `$maxExceptions`, `failed()`; time-bounded jobs add `retryUntil()`; `handle()` is idempotent (business-key dedup, unique constraint, or upsert)
- [ ] Job constructors take scalar IDs, not Eloquent models / collections
- [ ] Jobs dispatched inside `DB::transaction` use `->afterCommit()` (or `public bool $afterCommit = true;`)
- [ ] Third-party-API jobs use `RateLimited` middleware; resource-bound jobs use `WithoutOverlapping`
- [ ] Fan-out uses `Bus::batch([...])` with `chunkById` upstream; ordered pipelines use `Bus::chain([...])`
- [ ] Horizon uses `balance => 'auto'` with `minProcesses` / `maxProcesses`; `simple` balance flagged on multi-queue setups; per-queue priority set
- [ ] Scheduled commands on multi-replica deploys use `->withoutOverlapping()` + `->onOneServer()`; long-running use `->runInBackground()`

### Step 8 - HTTP Client / External Calls

- [ ] `Http::timeout(...)` explicit on every outbound call (default relies on PHP `default_socket_timeout`); typical `Http::timeout(5)->retry(3, 100)`
- [ ] `Http::retry(...)` with backoff filtered to recoverable cases: `retry(3, 100, fn ($e) => $e instanceof ConnectionException)`
- [ ] `Http::pool(fn ($pool) => [...])` for parallel fan-out
- [ ] Persistent Guzzle / SDK clients via container singleton; `new Client(...)` per request defeats keep-alive
- [ ] Circuit breaker on fragile upstream to prevent retry storms
- [ ] `Http::fake([...])` in tests - never hit real network in CI

### Step 9 - Caching and Response Performance

- [ ] `Cache::remember($key, $ttl, fn () => ...)` for expensive reads; explicit TTL mandatory; `rememberForever` only with a clear invalidation story
- [ ] `Cache::tags([...])->remember(...)` only on `redis` / `memcached` - `database` / `file` / `array` drivers throw; confirm driver
- [ ] Stampede protection: `Cache::lock("regen:$key", 10)->block(5, fn () => Cache::remember(...))` for hot keys
- [ ] Invalidation explicit (event-driven `Cache::tags(['orders'])->flush()` on `OrderUpdated`); document staleness budget. `Cache::flush()` flagged
- [ ] HTTP caching: `Cache-Control` on read-heavy GETs; `ETag` / `Last-Modified` for 304s
- [ ] `php artisan view:cache` / `config:cache` / `route:cache` in deploy script
- [ ] Per-request memoization for values used by multiple consumers (config, current tenant, permissions)

### Step 10 - Runtime, OPcache, Octane Readiness

- [ ] OPcache enabled in prod: `enable=1`, `memory_consumption=256`, `max_accelerated_files=20000`, `validate_timestamps=0`; `jit=tracing` + `jit_buffer_size=128M` on PHP 8.0+
- [ ] Composer autoloader optimized (`--no-dev --optimize-autoloader --classmap-authoritative`); `php artisan optimize` in deploy pipeline
- [ ] Octane / FrankenPHP / RoadRunner readiness: flag any `app()->singleton(...)` whose closure captures request data (current user/tenant) - foot-gun even when project isn't on Octane today; static class properties as cache also flagged
- [ ] Pcntl signal handling in long-running Octane workers for graceful queue drains
- [ ] `pm.max_children` tuning has a load profile (`(RAM - reserved) / avg_request_memory`)
- [ ] Response compression (gzip/brotli) on large JSON; Telescope disabled or strictly sampled in production

### Step 11 - Observability for Perf (delegation hand-off)

Narrow check - depth belongs to `task-laravel-review-observability`:

- [ ] Slow paths reachable from this PR have some instrumentation; if absent, raise Low/Recommendation and delegate
- [ ] Slow query log available in non-prod (`slow_query_log=ON`, `long_query_time=0.5`); EXPLAIN via `Model::query()->explain()`
- [ ] Telescope / Clockwork / Debugbar runnable in non-prod

Sampling rates, span attributes, correlation IDs, log channel design -> `task-laravel-review-observability`.

### Step 12 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Write the assembled output to the report file before ending the session; print the confirmation line.

## Output Format

```markdown
## Laravel Performance Review Summary

**Stack Detected:** PHP <version> / Laravel <version>
**Database:** MySQL <version> | PostgreSQL <version> | MariaDB <version>
**Queue:** redis (Horizon) | database | sync
**Cache:** redis | memcached | database | file
**Runtime:** PHP-FPM | Octane (Swoole) | Octane (RoadRunner) | FrankenPHP
**Scope:** Backend (Laravel)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

Bucket by `### High Impact` / `### Medium Impact` / `### Low Impact / Quick Wins`. Omit empty buckets. Each finding:

- **Location:** [file:line]
- **Issue:** [name the Laravel idiom]
- **Impact:** [estimated, e.g. "N+1 in `OrdersController.index` adds ~200 queries per request at 100 orders"; or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [specific Laravel change with code]

## Recommendations

[Structural improvements not tied to a specific finding]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: schema] - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2 - stack confirmed as PHP / Laravel; database, queue, cache, runtime recorded
- [ ] Step 3 - `review-precondition-check` ran; diff and commit log read once and reused
- [ ] Step 4 - performance surface read directly
- [ ] Step 5 - `laravel-eloquent-patterns` consulted; N+1, wide eager-load, `Model::all()`, pagination, aggregates checked
- [ ] Step 6 - `laravel-migration-safety` consulted when migrations present; reasoning rule + migration impact template applied
- [ ] Step 7 - `laravel-queue-patterns` consulted when queue files present; sync-in-prod, retry discipline, scalar IDs, `afterCommit`, middleware audited
- [ ] Steps 8-10 - skipped or applied per diff signals; gating recorded; `Cache::remember` TTL/tag-driver and `Http::*` timeouts checked when present
- [ ] Step 11 - observability hand-off captured for any slow path lacking instrumentation
- [ ] Step 12 - report written via `review-report-writer`; confirmation printed
- [ ] Severity rubric applied consistently; every finding states impact; Next Steps tagged and ordered

## Avoid

- State-changing git commands from this workflow
- Findings without naming the Laravel idiom ("this is slow" vs "N+1 from lazy-loaded `$order->items` in `OrdersController::index` Blade")
- Generic backend advice where a Laravel pattern applies (say `Bus::batch` for fan-out, not "worker pool")
- Reporting "missing index" without confirming the column appears in `where` / `orderBy` / `groupBy` in the diff
- Treating `whereRaw($input)` as perf-only - the SQL injection surface is the bigger half. Add a `[Delegate] -> task-laravel-review-security` entry; do not silently absorb security into perf
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.

> **Cross-workflow finding ownership.** Dual perf+security findings (`whereRaw($input)`, queue-job deserializing untrusted input, file uploads on hot endpoints) are reported once with a `[Delegate] -> task-laravel-review-security` entry in Next Steps. This workflow does **not** enumerate parallel security concerns (auth bypass, IDOR, mass assignment, open redirect) - those belong to the security delegate.
