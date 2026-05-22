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
| **High**   | Production outage shape under steady load. Eloquent N+1 multiplying baseline RPS by O(N); `whereRaw($input)` defeating plan cache; lazy-loaded `@foreach ($orders as $o) {{ $o->user->name }}` in a paginated endpoint; `Order::all()` on a 1M+-row table; worker memory leak from passing Eloquent collections; `QUEUE_CONNECTION=sync` in prod; Horizon supervisor starving Redis; missing index on hot `where` / `ORDER BY`; lock held across HTTP I/O inside `DB::transaction`. Or deploy-time outage (NOT NULL ADD with non-constant default on a 10M+ row MySQL table without `pt-online-schema-change`). |
| **Medium** | Degraded p95/p99 or wasted bandwidth. `paginate()` running `COUNT(*)` on a 1M+ row table when `cursorPaginate` suffices; `Cache::remember` without TTL or tag bound; Resource-shaped N+1 (eager-load missing for relation accessed by `toArray()`); missing FULLTEXT on `LIKE '%term%'`; `Http::get` without timeout or retry. Follow-up PR, not on-call paging. |
| **Low**    | CPU / allocation churn. String concat in tight loops; `collect()->map()->filter()` chains where `for` would do; missing `view:cache` / `config:cache` / `route:cache` in production deploy; missing response compression; missing OPcache tuning; missing JIT / preload. |

Tie-breaker: "would this page on-call within 24h of a 2x traffic increase?" yes -> High; "would this drag next quarter's perf budget?" yes -> Medium.

## Depth Levels

| Depth      | When to Use                                                  | What Runs                                          |
| ---------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `quick`    | Single endpoint or model ("is this query ok?")               | Steps 5 + 6 only; Eloquent hotspots + migrations   |
| `standard` | Default - full Laravel perf review                           | All steps                                          |
| `deep`     | Profiling-driven review with Telescope / Clockwork / APM     | All steps + capacity guidance and load plan        |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                           | Meaning                                                                                                |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `/task-laravel-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first  |
| `/task-laravel-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                             |
| `/task-laravel-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                        |

When invoked as a subagent of `task-code-review-perf` (parent passes the precondition-check handle plus pre-read diff and commit log), Step 3 is skipped and parent artifacts are reused.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Skip re-loading when invoked as a subagent of `task-code-review-perf` or `task-laravel-review` and the parent confirms.

### Step 2 - Confirm Stack and Detect Surface

Use skill: `stack-detect` to confirm PHP / Laravel (skip if parent pre-confirmed). If not Laravel, stop and route to `/task-code-review-perf`.

Detect and record for the Summary block (Steps 4-9 branch on these where idioms differ):

- `Database` (from `config/database.php`): MySQL `<version>` | PostgreSQL `<version>` | MariaDB `<version>`
- `Queue` (from `config/queue.php` / `.env`): `redis (Horizon)` | `database` | `sync`
- `Cache` (from `config/cache.php`): `redis` | `memcached` | `database` | `file`
- `Runtime`: `PHP-FPM` | `Octane (Swoole)` | `Octane (RoadRunner)` | `FrankenPHP`

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check`. On approval, read `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>` once and reuse. Skip entirely when running as a subagent with parent-supplied artifacts.

If precondition-check stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, denied head-vs-current confirmation), surface verbatim and stop. Never run state-changing git from this workflow.

### Step 4 - Read the Performance Surface

Open files governing query and concurrency behavior so impact estimates ground in real code:

- **Eloquent / DB:** changed models (`$casts`, `$with`, relationships, scopes), controllers / services / jobs (query patterns), Blade views (`@foreach $model->relation`), API Resources (`$this->relation` in `toArray()`), `config/database.php`, migrations, `AppServiceProvider::boot()` for `Model::preventLazyLoading()`
- **Queue:** changed jobs (`$tries`, `$backoff`, `$timeout`, `$maxExceptions`, `failed()`, `retryUntil()`, middleware), listeners (`ShouldQueue`), dispatch sites (`dispatch`, `Bus::batch`, `Bus::chain`, `dispatchSync`, `dispatchAfterResponse`, `->afterCommit()`), `config/queue.php`, `config/horizon.php`, `app/Console/Kernel.php`
- **HTTP / external:** `Http::*` (timeout, retry, connect-timeout), Guzzle / SDK clients constructed per-request
- **Cache:** `Cache::remember`, `Cache::tags`, `Cache::lock`, `Cache::flush`; `config/cache.php`
- **Runtime:** `bootstrap/app.php` middleware order, `config/octane.php` `flush` setting, `composer.json` static-analysis tooling

For each finding, cite a real `file:line`. When the diff is small but ripples through unchanged code (a new endpoint calling an existing service with an N+1), read the unchanged file - the regression lives there.

### Step 5 - Eloquent / Database Hotspots

Use skill: `laravel-eloquent-patterns` for canonical patterns. Review-scoped scan over changed queries, models, controllers, services, jobs, Blade views, Resources:

- [ ] N+1 across loops, Blade `@foreach`, and Resource `toArray()` - eager-load at controller via `with(...)` / `withCount(...)`; `Model::preventLazyLoading()` wired in `AppServiceProvider::boot()` for non-prod
- [ ] No `$with` auto-eager-load without justification (over-fetches every fetch)
- [ ] `Model::all()` and collection-then-paginate (`Order::all()->filter(...)->paginate(...)`) flagged on growable tables - require `chunkById` / `lazy` / `cursor` / `cursorPaginate` and push filters into SQL
- [ ] Pagination matches scale: `paginate()` only when `COUNT(*)` is acceptable; `cursorPaginate` on large tables; never OFFSET on millions
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

- [ ] Every column in `where` / `orderBy` / `groupBy` is backed by an index; composites match leftmost-prefix; FK indexes present (`->constrained()` / `->foreignId()->index()` - verify the migration emits them)
- [ ] Index additions on large tables use `ALGORITHM=INPLACE, LOCK=NONE` (InnoDB online for non-clustered); clustered/PRIMARY restructures lock. For > 10M rows, require `pt-online-schema-change` or `gh-ost`
- [ ] `SET innodb_lock_wait_timeout` before DDL on large tables to fail fast under contention
- [ ] Unique constraints enforced at DB level (`$table->unique('email')`), not only via `Validator unique:` rule (validation alone races)
- [ ] Partial / functional indexes for low-selectivity boolean filters (MySQL 8.0+; otherwise generated column + regular index)
- [ ] Expand-then-contract for column changes on hot tables (nullable add, backfill, switch reads, drop in later release); data migrations separated from DDL migrations (distinct files)
- [ ] Backfills use `chunkById(1000, ...)`, never `WHERE col IS NULL LIMIT N` (re-scans). Very large: raw `UPDATE ... LIMIT N` with keyset cursor in a CLI command, not a migration
- [ ] `php artisan migrate --force` from a single deployer step, never `Artisan::call('migrate')` on app boot (replicas race on rollout)

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot in `where` / `orderBy` / `groupBy` even if no query in the diff references it - validate the index is actually needed, then assess migration safety. When the diff _adds a column_ the app queries on, flag the missing index proactively.

**Migration impact template.** Before approving any DDL on a hot table, state: _"DDL on a 50M-row InnoDB table without `pt-online-schema-change` blocks writes for the duration (10-30 min on hot disks); replica lag spikes, connections queue. Recommend `pt-osc` with `--max-lag=5s --critical-load Threads_running=80` and a maintenance window."_ If row count is unknown, ask or note "row count not in diff - confirm before deploy."

### Step 7 - Queue Throughput, Jobs, Scheduling

Use skill: `laravel-queue-patterns` for canonical patterns. Review-scoped scan over changed jobs, listeners, dispatch sites, scheduled commands, `config/queue.php`, `config/horizon.php`:

- [ ] `QUEUE_CONNECTION` is not `sync` in production env; `dispatchSync` not on user-request paths
- [ ] Every job sets `$tries`, `$backoff`, `$timeout`, `$maxExceptions`, `failed()`; time-bounded jobs add `retryUntil()`; `handle()` is idempotent (business-key dedup, unique constraint, or upsert)
- [ ] Job constructors take scalar IDs, not Eloquent models / collections (avoids stale snapshot + payload bloat)
- [ ] Jobs dispatched inside `DB::transaction` use `->afterCommit()` (or `public bool $afterCommit = true;`); flag explicit `withoutCommit()` when `QUEUE_AFTER_COMMIT=true` is global
- [ ] Third-party-API jobs use `RateLimited` middleware; resource-bound jobs use `WithoutOverlapping`
- [ ] Fan-out uses `Bus::batch([...])` with `chunkById` upstream so dispatcher doesn't materialize; ordered pipelines use `Bus::chain([...])`
- [ ] Horizon uses `balance => 'auto'` with `minProcesses` / `maxProcesses`; `simple` balance flagged on multi-queue setups; per-queue priority set
- [ ] Scheduled commands on multi-replica deploys use `->withoutOverlapping()` + `->onOneServer()`; long-running use `->runInBackground()`
- [ ] Dispatch path into a saturated queue surfaced if Redis depth alerts are absent

### Step 8 - HTTP Client / External Calls

Inspect every changed `Http::*` and Guzzle usage:

- [ ] `Http::timeout(...)` explicit on every outbound call (default relies on PHP `default_socket_timeout` in older Laravel); typical `Http::timeout(5)->retry(3, 100)`
- [ ] `Http::retry(...)` with backoff filtered to recoverable cases: `retry(3, 100, fn ($e) => $e instanceof ConnectionException)`
- [ ] `Http::pool(fn ($pool) => [...])` for parallel fan-out - 5 sequential `Http::get` is 5x latency; pool is one cumulative roundtrip (per slowest)
- [ ] Persistent Guzzle / SDK clients via container singleton (`$this->app->singleton(Client::class, ...)`); `new Client(...)` per request defeats keep-alive
- [ ] Circuit breaker on fragile upstream (e.g. `tk707/laravel-circuit-breaker`) to prevent retry storms
- [ ] `Http::fake([...])` in tests - never hit real network in CI

### Step 9 - Caching and Response Performance

_Skipped at `quick` depth unless the diff touches caching primitives._

- [ ] `Cache::remember($key, $ttl, fn () => ...)` for expensive reads; explicit TTL mandatory; `rememberForever` only with a clear invalidation story
- [ ] `Cache::tags([...])->remember(...)` only on `redis` / `memcached` - `database` / `file` / `array` drivers throw; confirm driver
- [ ] Stampede protection: `Cache::lock("regen:$key", 10)->block(5, fn () => Cache::remember(...))` for hot keys with expensive regeneration
- [ ] Invalidation explicit (event-driven `Cache::tags(['orders'])->flush()` on `OrderUpdated`); document staleness budget. `Cache::flush()` flagged - whole-driver; use `tags(...)->flush()` or `forget($key)`
- [ ] HTTP caching: `Cache-Control` on read-heavy GETs; `ETag` / `Last-Modified` for 304s
- [ ] `php artisan view:cache` / `config:cache` / `route:cache` in deploy script (missing = Low finding)
- [ ] Per-request memoization for values used by multiple consumers (config, current tenant, permissions)

### Step 10 - Runtime, OPcache, Octane Readiness

_Skipped at `quick` depth unless the diff touches runtime config (`composer.json`, `php.ini`, `bootstrap/app.php`, `config/octane.php`, Dockerfile)._

- [ ] OPcache enabled in prod: `enable=1`, `memory_consumption=256`, `max_accelerated_files=20000`, `validate_timestamps=0` (with deploy-time `opcache_reset()`); `jit=tracing` + `jit_buffer_size=128M` on PHP 8.0+
- [ ] Composer autoloader optimized (`--no-dev --optimize-autoloader --classmap-authoritative`); `php artisan optimize` in deploy pipeline (Laravel 11+ bundles config/route/view caches)
- [ ] Octane / FrankenPHP / RoadRunner readiness: workers persist in-memory state across requests. Flag any `app()->singleton(...)` whose closure captures request data (current user/tenant) - foot-gun even when project isn't on Octane today. Static class properties as cache also flagged. Use `Cache::*` or request-scoped service; explicit fix is stateless singletons (the `config/octane.php` `flush` reset adds overhead)
- [ ] Pcntl signal handling in long-running Octane workers for graceful queue drains
- [ ] `pm.max_children` tuning has a load profile (`(RAM - reserved) / avg_request_memory`); flag changes without one
- [ ] Response compression (gzip/brotli) on large JSON; Telescope disabled or strictly sampled (`Telescope::filter(...)`) in production

### Step 11 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

Narrow check - depth belongs to `task-laravel-review-observability`. Confirm only:

- [ ] Slow paths reachable from this PR have some instrumentation (`Log::info` with structured context OR a metric); if absent, raise Low/Recommendation and delegate
- [ ] Slow query log available in non-prod (`slow_query_log=ON`, `long_query_time=0.5`); EXPLAIN via `Model::query()->explain()` (Laravel 12+) or `DB::enableQueryLog()`
- [ ] Telescope / Clockwork / Debugbar runnable in non-prod

Sampling rates, span attributes, correlation IDs, log channel design -> `task-laravel-review-observability`. Note the gap; don't duplicate the audit.

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
- **Issue:** [name the Laravel idiom: N+1 via lazy-loaded `$order->user` in Blade `@foreach`, `Model::all()` on 10M rows, OFFSET pagination, `whereRaw` with interpolated input, `LIKE '%term%'` without FULLTEXT, job constructor taking Eloquent model, missing `afterCommit()`, `QUEUE_CONNECTION=sync` in prod, missing `WithoutOverlapping`, etc.]
- **Impact:** [estimated, e.g. "N+1 in `OrdersController.index` adds ~200 queries per request at 100 orders"; or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [specific Laravel change with code: `Order::with(['user', 'items'])->cursorPaginate(25)`, scalar ID in job, `dispatch(new ProcessPayment($id))->afterCommit()`, `Bus::batch(...)`, `Cache::lock(...)` single-flight]

## Recommendations

[Structural improvements not tied to a specific finding - e.g. "Switch list endpoint to `cursorPaginate`", "Bind Guzzle Client as singleton", "Enable `Model::preventLazyLoading()` in `AppServiceProvider::boot` for non-prod"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, schema migration, or load-test work for a subagent). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: schema] - [one-line action, e.g. "Add `(tenant_id, created_at)` index via `pt-online-schema-change`"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2 - stack confirmed as PHP / Laravel; database, queue, cache, runtime recorded
- [ ] Step 3 - `review-precondition-check` ran (or handle received from parent); diff and commit log read once and reused; for `pr-ref` the user-run fetch was surfaced (not executed); `head_matches_current=false` got explicit approval
- [ ] Step 4 - performance surface read directly (models, controllers, Blade views, Resources, jobs, dispatch sites, migrations, cache sites, HTTP sites)
- [ ] Step 5 - `laravel-eloquent-patterns` consulted; N+1, `$with`, `Model::all()`, pagination, aggregates, collection-then-paginate, `Cache::remember` callback bounds checked
- [ ] Step 6 - `laravel-migration-safety` consulted; index/FK presence, online DDL, chunked backfill, deploy-time ordering verified; reasoning rule + migration impact template applied
- [ ] Step 7 - `laravel-queue-patterns` consulted; sync-in-prod, retry discipline, scalar IDs, `afterCommit`, middleware, `Bus::batch` fan-out, Horizon sizing audited
- [ ] Step 8 - `Http::timeout` / `retry` / `pool`, persistent client, `Http::fake` in tests reviewed
- [ ] Step 9 - `Cache::remember` TTL, tags driver gate, single-flight via `Cache::lock`, invalidation strategy assessed
- [ ] Step 10 - OPcache / autoloader / Octane readiness assessed; request-leaking singletons and static state flagged regardless of current runtime
- [ ] Step 11 - observability hand-off captured for any slow path lacking instrumentation; deferred to `task-laravel-review-observability`
- [ ] Step 12 - report written via `review-report-writer`; confirmation line printed
- [ ] Severity rubric applied consistently; every finding states impact (measured or estimated, never just "this is slow"); findings ordered by impact; Next Steps tagged `[Implement]` / `[Delegate]` and ordered High > Medium > Low
- [ ] Depth honored: `quick` ran only Steps 5 + 6; `standard` ran 5-11; `deep` adds capacity guidance and load-test plan

## Avoid

- State-changing git commands (`fetch`, `checkout`) from this workflow - the user runs them
- Findings without naming the Laravel idiom ("this is slow" vs "N+1 from lazy-loaded `$order->items` in `OrdersController::index` Blade; `Order::with('items')->cursorPaginate(25)`")
- Generic backend advice where a Laravel pattern applies (say `Bus::batch` for fan-out, not "worker pool")
- Reporting "missing index" without confirming the column appears in `where` / `orderBy` / `groupBy` in the diff
- Approving `Eloquent::all()` / `$with` auto-eager-load / `Model::all()` / `paginate()` on > 1M rows when `cursorPaginate` fits, jobs constructed with Eloquent models, `dispatch` inside `DB::transaction` without `afterCommit()`, `QUEUE_CONNECTION=sync` in prod, `Cache::flush()` for targeted invalidation, `app()->singleton` capturing request state, `$model->fresh()`/`refresh()` per loop iteration, lazy loading in Blade loops, Telescope in production
- Treating `whereRaw($input)` as perf-only - the SQL injection surface is the bigger half. Add a `[Delegate] -> task-laravel-review-security` entry; do not silently absorb security into perf

> **Cross-workflow finding ownership.** Dual perf+security findings (`whereRaw($input)`, queue-job deserializing untrusted input, file uploads on hot endpoints) are reported once with a `[Delegate] -> task-laravel-review-security` entry in Next Steps. This workflow does **not** enumerate parallel security concerns (auth bypass, IDOR, mass assignment, open redirect) - those belong to the security delegate.
