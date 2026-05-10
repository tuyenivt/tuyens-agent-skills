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

Laravel-aware performance review that names Eloquent N+1 patterns (lazy loading in Blade / controllers / API Resources, per-iteration `Model::find` inside `foreach`, missing `with()` chain), multi-relation eager-load explosion, missing database indexes on `where` / `orderBy` / `groupBy` / FK columns, MySQL slow-query shapes (LIKE with leading `%`, OFFSET pagination on large tables, missing FULLTEXT index for search, missing covering index for hot reads), `DB::transaction` boundary holding row locks across HTTP / queue I/O, queue throughput (Redis with Horizon vs database driver, `QUEUE_CONNECTION=sync` smell in non-local, `$tries` / `$backoff` exponential discipline, `Bus::batch(...)` for fan-out, `RateLimited` middleware on third-party-API jobs), `Cache::remember` / `Cache::tags` strategy, `Http::pool(...)` for parallel HTTP fan-out, Guzzle connection reuse via the HTTP client factory, response macro caching, Blade view caching (`php artisan view:cache`), route caching (`php artisan route:cache` / `config:cache`), OPcache + JIT preload config, Octane / FrankenPHP / RoadRunner request-state leakage as the upgrade path, and database connection pool sizing (`php-fpm pm.max_children` × replicas vs MySQL `max_connections`) directly instead of routing through the generic backend adapter. Produces findings with measured or estimated impact (latency, throughput, query count, memory, queue depth, lock contention) and concrete fixes using idiomatic Laravel.

This workflow is the stack-specific delegate of `task-code-review-perf` for PHP / Laravel. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a Laravel PR or branch for performance regressions
- Investigating a slow endpoint, queue job, or scheduled command
- Pre-merge perf pass on changes touching Eloquent queries, Blade views, queue jobs, or caching primitives
- Quarterly N+1 / index / Horizon-supervisor review against slow-query log / APM data

**Not for:**

- General Laravel code review (use `task-code-review` or `task-laravel-review`)
- Security review (use `task-code-review-security` or `task-laravel-review-security`)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-laravel-implement`)

## Severity Rubric

Use these definitions to keep `High` / `Medium` / `Low` Impact labels consistent across runs. Severity is about steady-state production impact and recovery effort, not how scary the code looks.

| Severity     | Definition                                                                                                                                                                                                                                                                              |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **High**     | Production outage shape under steady load: Eloquent N+1 multiplying baseline RPS by O(N), `whereRaw($input)` blowing the query plan cache, lazy-loaded Blade `@foreach ($orders as $o) {{ $o->user->name }} @endforeach` inside a paginated index endpoint, `Order::all()` on a 1M+ row table, queue worker memory leak from passing Eloquent collections, queue connection set to `sync` in prod, Horizon misconfigured supervisor count starving Redis, missing index on hot `where` / `ORDER BY` column, lock held across HTTP call inside `DB::transaction`. Or deploy-time outage on hot tables (NOT NULL ADD with non-constant default on a 10M+-row MySQL table without `pt-online-schema-change`). |
| **Medium**   | Degraded p95 / p99 latency, wasted bandwidth, `paginate()` running `COUNT(*)` on a 1M+-row table when `simplePaginate` / `cursorPaginate` would suffice, `Cache::remember` missing TTL or unbounded by tag, missing eager-load on a relationship accessed by the Resource transformer (Resource-shaped N+1), missing FULLTEXT index on a search endpoint that does `LIKE '%term%'`, `Http::get` without timeout or retry. Recoverable with a follow-up PR; not paging on-call. |
| **Low**      | CPU / allocation churn (string concat in tight loops, `collect()->map(...)->filter(...)` chains in hot loops where a `for` would do, missing `php artisan view:cache` / `config:cache` / `route:cache` in production deploy), missing response compression, missing OPcache validate-timestamps tuning, missing JIT / preload config.                                                                                                                                                                |

When uncertain between tiers, ask "would this page on-call within 24 hours of a 2x traffic increase?" - yes ⇒ High; "would this drag the next quarter's perf budget?" - yes ⇒ Medium.

## Depth Levels

| Depth      | When to Use                                                  | What Runs                                          |
| ---------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `quick`    | Single endpoint or Eloquent model ("is this query ok?")      | Steps 5 + 6 only; Eloquent hotspots + migrations   |
| `standard` | Default - full Laravel perf review                           | All steps                                          |
| `deep`     | Profiling-driven review with Telescope / Clockwork / APM data | All steps + capacity guidance and load plan       |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                           | Meaning                                                                                                |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `/task-laravel-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first  |
| `/task-laravel-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                             |
| `/task-laravel-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                        |

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 3 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every subsequent step. When invoked as a subagent of `task-code-review-perf` or `task-laravel-review`, accept the parent's confirmation and skip re-loading.

### Step 2 - Confirm Stack and Detect ORM / Queue / Runtime Surface

Use skill: `stack-detect` to confirm PHP / Laravel. If invoked as a delegate of `task-code-review-perf` or as a subagent of `task-laravel-review` (parent already detected Laravel), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Laravel, stop and tell the user to invoke `/task-code-review-perf` instead.

Detect ORM use: Eloquent (typical) or query builder (`DB::table(...)`). Detect queue connection from `config/queue.php` and `.env`: `redis` (typical, with Horizon), `database`, or `sync` (smell in non-local). Detect runtime: standard PHP-FPM (typical), Laravel Octane + Swoole / RoadRunner / FrankenPHP (request-state leakage concerns). Detect cache driver: `redis`, `memcached`, `database`, `file`, `array`. Detect database engine from `config/database.php`: MySQL (typical), PostgreSQL, MariaDB.

Record `Database: MySQL <version> | PostgreSQL <version> | MariaDB <version>`, `Queue: redis (Horizon) | database | sync`, `Cache: redis | memcached | database | file`, `Runtime: PHP-FPM | Octane (Swoole) | Octane (RoadRunner) | FrankenPHP` for the Summary block. Each Step 4-9 checklist branches on this signal where the idiom differs.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 4 - Read the Performance Surface

Before applying the checklists, open the files that govern query and concurrency behavior so impact estimates ground in real code:

**Eloquent / DB surface:**

- Every changed model (`app/Models/*.php`) - `$casts`, `$with` (auto-eager-load - careful, can over-fetch), relationships, scopes
- Every changed controller / service / action / job for query patterns: `Model::find`, `Model::where`, `Model::with`, `Model::all`, `chunk` / `chunkById` / `lazy` / `cursor`, `paginate` / `simplePaginate` / `cursorPaginate`, `whereRaw` / `DB::raw`, `Cache::remember` wrapping queries
- Every changed Blade view (`resources/views/**/*.blade.php`) for `@foreach` loops accessing `$model->relation` (lazy-loading N+1)
- Every changed API Resource (`app/Http/Resources/*.php`) for `$this->relation` access in `toArray()` (Resource-shaped N+1 - always need eager-loading at the controller)
- `config/database.php` - connection config, read replicas, sticky connections
- Migration files under `database/migrations/`
- `AppServiceProvider::boot()` for `Model::preventLazyLoading()` - dev-mode guard against N+1

**Queue surface:**

- Every changed job (`app/Jobs/*.php`) - `$tries`, `$backoff`, `$timeout`, `$maxExceptions`, `failed()`, `retryUntil()`, middleware (`RateLimited`, `WithoutOverlapping`, `ThrottlesExceptions`)
- Every changed listener (`app/Listeners/*.php`) - `ShouldQueue` opt-in
- Job dispatch sites - `dispatch(...)`, `Bus::batch(...)`, `Bus::chain(...)`, `dispatchSync` / `dispatchAfterResponse` / `->afterCommit()`
- `config/queue.php` - connection, retry-after, block-for; `config/horizon.php` for Redis-driven queues - supervisor counts, timeouts, balance strategy
- Scheduled commands (`app/Console/Kernel.php` or `routes/console.php`) - `->withoutOverlapping`, `->onOneServer`, `->runInBackground`

**HTTP / external surface:**

- Every changed `Http::*` call - `Http::get(...)`, `Http::pool(...)`, `Http::withToken(...)`; timeout / retry / connect-timeout configuration
- Guzzle / SDK clients instantiated per-request (`new Client(...)` inside controllers / services) - flag for sharing via container singleton or `Http::baseUrl(...)` macro

**Cache surface:**

- Every changed `Cache::*` site - `Cache::remember`, `Cache::tags`, `Cache::lock`, `Cache::flush` (dangerous - flushes entire driver in some configs)
- `config/cache.php` - default store

**Runtime / pipeline surface:**

- `bootstrap/app.php` - middleware order; expensive middleware on every request
- `config/octane.php` if Octane is in use - `flush` setting; long-running workers leaking request state
- `composer.json` - `php-cs-fixer` / `pint` / `phpstan` / `larastan` for static analysis; `--prefer-dist` for production installs

For each finding produced later, cite a real `file:line`. If the diff is small but ripples through code that is not in the diff (a new endpoint calling an existing service whose query does an N+1), read the unchanged file too - the regression lives there even though the line count attributes it to the new caller.

### Step 5 - Eloquent / Database Hotspots

Canonical Eloquent perf patterns live in `laravel-eloquent-patterns` (eager-loading strategy, N+1 prevention, `chunkById` / `lazy` / `cursor`, pagination methods, aggregates, `lockForUpdate`, atomic decrements). This step is the **review-scoped scan** for changed queries, models, controllers, services, jobs, Blade views, and API Resources:

- [ ] N+1 across loops, Blade `@foreach`, and API Resource `toArray()` - eager-load at the controller via `with(...)` (collections) or `withCount(...)` for counts
- [ ] `Model::preventLazyLoading()` wired in `AppServiceProvider::boot()` for non-prod
- [ ] No `$with` auto-eager-load without justification (over-fetches every fetch)
- [ ] `Model::all()` flagged on growable tables - require `chunkById` / `lazy` / `cursor` / `cursorPaginate`
- [ ] Pagination method matches scale: `paginate()` only when COUNT(*) is acceptable; `simplePaginate` / `cursorPaginate` on large tables; never OFFSET on millions of rows
- [ ] Filter / sort / group / FK columns referenced in the diff have a backing index migration
- [ ] `whereRaw` / `orderByRaw` / `DB::raw` use parameter bindings; user-supplied sort columns allowlisted (this is also a security finding - delegate to security workflow)
- [ ] `LIKE '%term%'` flagged - require FULLTEXT or prefix-only `LIKE 'term%'`
- [ ] `firstOrCreate` / `updateOrCreate` under concurrency uses `upsert` or `lockForUpdate` inside transaction
- [ ] Bulk writes via `insert(...)` / `upsert(...)` over per-row `save()` loops
- [ ] Database aggregates (`$user->reviews()->avg(...)` with parens) over collection aggregates (`$user->reviews->avg(...)` materializes everything)
- [ ] Soft-deleted hot tables have an index on `deleted_at` (or composite including it)
- [ ] No `DB::transaction()` holding row locks across HTTP / queue I/O - move side effects outside the transaction
- [ ] `php-fpm pm.max_children` × replicas ≤ DB `max_connections` minus ops / replication headroom; Octane workers count differently
- [ ] Bulk `Eloquent::query()->update(...)` skipping observer events flagged when the codebase relies on observers for audit
- [ ] Collection-then-paginate (`Order::all()->filter(...)->paginate(...)`) flagged - push filter into SQL
- [ ] `Cache::remember(...)` callback contents follow the same rules - the cache amortizes only when the callback's worst case is bounded

### Step 6 - Indexes and Migrations

Use skill: `laravel-migration-safety` for safe-migration checks on any change in `database/migrations/`.

- [ ] Every column referenced in `where` / `orderBy` / `groupBy` is backed by an index (`$table->index('email')` or composite `$table->index(['tenant_id', 'created_at'])`)
- [ ] Composite indexes match the leftmost-prefix pattern of the queries
- [ ] Foreign keys have indexes (Laravel's `->constrained()` and `->foreignId()->index()` create the FK index automatically; verify it actually lands in the migration)
- [ ] Indexes on large tables added with `ALGORITHM=INPLACE, LOCK=NONE` (MySQL 5.6+ InnoDB) - `Schema::table` for index addition is online by default for non-clustered indexes; clustered (PRIMARY) restructures lock the table. For schema changes on > 10M rows, `pt-online-schema-change` (Percona) or `gh-ost` (GitHub) is the production path; flag missing tooling
- [ ] **`SET innodb_lock_wait_timeout`** before DDL on large tables to fail fast instead of blocking under contention
- [ ] Unique constraints enforced at the database level (`$table->unique('email')`) not just `Validator::make([..., 'unique:users,email'])` - validation alone races
- [ ] Partial / functional indexes used for boolean filters that select a small subset (MySQL 8.0+ supports functional indexes; otherwise use a generated column with a regular index)
- [ ] No DDL on hot tables in a single migration (expand-then-contract: add column nullable, backfill, switch reads, drop old column in a later release)
- [ ] **Backfill via `chunkById(1000, fn ($rows) => $rows->each(fn ($r) => $r->update([...])))`**, never `WHERE col IS NULL LIMIT N` (re-scans the same rows on every iteration). For very large backfills, prefer raw `UPDATE ... LIMIT N` with a keyset cursor in a CLI command, not a migration
- [ ] Data migrations isolated from DDL migrations - separate migration files
- [ ] **Migrations applied via `php artisan migrate --force` from a single deployer step**, not via `Artisan::call('migrate')` on app boot (every replica races the migration on rollout). Multi-replica deploys typically run `migrate` from one container before traffic shifts; flag boot-time migrations on multi-replica prod

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot in `where` / `orderBy` / `groupBy` even if no query in the diff currently references it - someone is adding the index for a reason. Validate the index is actually needed (column shape, expected selectivity), then assess migration safety. Conversely, when the diff _adds a column_ the application also queries on, flag the missing index proactively rather than waiting for a separate migration PR.

**Migration impact template.** Before approving any migration step on a hot table, state the impact: _"DDL on a 50M-row InnoDB table without `pt-online-schema-change` blocks all writes for the duration of the index build (typically 10-30 min on hot disks); during the rebuild, replica lag spikes and connections queue. Recommend running via `pt-osc` with `--max-lag=5s --critical-load Threads_running=80` and a maintenance window."_ If the row count is unknown, ask, or note "row count not in diff - confirm before deploy."

### Step 7 - Queue Throughput, Jobs, and Scheduling

Canonical queue patterns live in `laravel-queue-patterns` (job structure, retry/backoff, `acks_late`-equivalent semantics, idempotency, batching, chaining, rate limiting, Horizon, scheduling). This step is the **review-scoped scan** for changed jobs, listeners, dispatch sites, scheduled commands, and `config/queue.php` / `config/horizon.php`:

- [ ] `QUEUE_CONNECTION` is not `sync` in production env files; `dispatchSync` not on user-request paths
- [ ] Every job sets `$tries`, `$backoff`, `$timeout`, `$maxExceptions`, `failed()`; time-bounded jobs add `retryUntil()`
- [ ] Job constructors take scalar IDs, not Eloquent models or collections (avoids stale-snapshot serialization + payload bloat)
- [ ] Jobs dispatched inside `DB::transaction` use `->afterCommit()` (or job has `public bool $afterCommit = true;`); flag explicit `withoutCommit()` overrides when `QUEUE_AFTER_COMMIT=true` is global
- [ ] `handle()` is idempotent (business-key dedup, unique constraint, or upsert)
- [ ] Third-party-API jobs use `RateLimited` middleware; resource-bound jobs use `WithoutOverlapping`
- [ ] Fan-out over large lists uses `Bus::batch([...])` (with `chunkById` upstream so the dispatcher itself doesn't materialize all rows); ordered pipelines use `Bus::chain([...])`
- [ ] Horizon supervisor uses `balance => 'auto'` with `minProcesses` / `maxProcesses`; `simple` balance flagged on multi-queue setups (long jobs starve short jobs); per-queue priority order set
- [ ] Scheduled commands on multi-replica deploys use `->withoutOverlapping()` + `->onOneServer()`; long-running scheduled commands use `->runInBackground()`
- [ ] Dispatch path to a saturated queue surfaced if Redis depth alerts are absent

### Step 8 - HTTP Client / External Calls

Inspect every changed `Http::*` and Guzzle usage:

- [ ] **`Http::timeout(...)`** explicit on every outbound call - default is no client timeout in older Laravel versions (relies on PHP `default_socket_timeout`); set `Http::timeout(5)->retry(3, 100)` per call site or via a service container macro
- [ ] **`Http::retry(...)` with backoff** for transient failures; `retry(3, 100, fn ($e) => $e instanceof ConnectionException)` filters retries to recoverable cases
- [ ] **`Http::pool(fn ($pool) => [...])` for parallel HTTP fan-out**: `Http::pool` runs the callbacks concurrently via Guzzle's async pool. Sequential `Http::get(...)` calls in a controller for 5 endpoints is 5x serial latency; pool is one cumulative roundtrip-equivalent (per the slowest)
- [ ] **Persistent Guzzle / SDK clients via container**: instantiating `new Client(...)` per request defeats keep-alive and connection reuse. Bind in `AppServiceProvider`: `$this->app->singleton(Client::class, fn () => new Client(['base_uri' => ...]));`. SDKs (Stripe, AWS SDK) usually have built-in connection reuse - confirm not constructed per-request
- [ ] **Circuit breaker for fragile upstream**: when an upstream fails for minutes, retry storm makes it worse. Use `tk707/laravel-circuit-breaker` (or similar) on third-party APIs with known instability
- [ ] **Mock external HTTP in tests** via `Http::fake([...])` - never hit real network in CI

### Step 9 - Caching and Response Performance

_Skipped at `quick` depth unless the diff touches caching primitives._

- [ ] **`Cache::remember($key, $ttl, fn () => ...)`** for expensive read paths; explicit TTL mandatory; `Cache::rememberForever(...)` only with a clear invalidation story (event-driven `forget`, tag flush on related write)
- [ ] **`Cache::tags([...])->remember(...)` only on `redis` / `memcached` drivers**: `database` / `file` / `array` drivers do not support tags - calls throw. Confirm driver before using tags
- [ ] **Cache stampede protection via `Cache::lock(...)`**: hot keys with expensive regeneration use single-flight - `Cache::lock("regen:$key", 10)->block(5, fn () => Cache::remember(...))` ensures only one process regenerates while others wait
- [ ] **Cache invalidation explicit**: no caches that never expire and never invalidate; document staleness budget; prefer event-driven invalidation (`OrderUpdated` listener that calls `Cache::tags(['orders'])->flush()`) over time-based when correctness matters
- [ ] **HTTP-level caching**: `Cache-Control` headers on read-heavy GET endpoints; `ETag` / `Last-Modified` for conditional requests (304 saves serialization + transfer); Laravel's `Cache::response()` middleware or manual `header(...)` calls
- [ ] **View caching in production**: `php artisan view:cache` precompiles Blade templates; `php artisan config:cache` and `php artisan route:cache` cache config and routes. Deploy script must run these; missing them on prod deploys is a `[Low]` finding
- [ ] **Per-request memoization**: store on the container or a request-scoped service for values used by multiple consumers in the same request (config, current tenant, current user permissions)
- [ ] **`Cache::flush()` flagged**: flushes the entire driver in some configs (e.g., `redis` flushes all DBs on the connection). Use `Cache::tags(...)->flush()` or `Cache::forget($key)` for targeted invalidation

### Step 10 - Runtime, OPcache, Octane Readiness

_Skipped at `quick` depth unless the diff touches runtime config (`composer.json`, `php.ini` references, `bootstrap/app.php`, Octane config, Dockerfile)._

- [ ] **OPcache enabled in production**: `opcache.enable=1`, `opcache.memory_consumption=256`, `opcache.max_accelerated_files=20000`, `opcache.validate_timestamps=0` (with deploy script that calls `opcache_reset()` on deploy); `opcache.jit=tracing` + `opcache.jit_buffer_size=128M` for PHP 8.0+
- [ ] **Composer autoloader optimized**: `composer install --no-dev --optimize-autoloader --classmap-authoritative` in production; `composer dump-autoload -o` after deploys
- [ ] **`php artisan optimize`**: bundles `config:cache`, `route:cache`, `view:cache` (Laravel 11+) - confirm in deploy pipeline
- [ ] **Octane / FrankenPHP / RoadRunner readiness**: long-running workers persist in-memory state across requests. Singletons resolved at boot retain their initial state; container bindings that capture the request (current user, current tenant) leak across requests. Flag any new `app()->singleton(...)` whose closure captures request data, even when the project doesn't currently use Octane (it's a foot-gun for the future migration). The `flush` config setting in `config/octane.php` resets these between requests but adds overhead - explicit fix is to design singletons stateless
- [ ] **Static class properties as cache** are unsafe under Octane / Swoole - persist across requests. Use `Cache::*` for shared state, request-scoped service for per-request state
- [ ] **Pcntl-based signal handling in Octane workers**: long-running PHP processes need explicit shutdown handling for graceful queue drains
- [ ] **PHP-FPM `pm.max_children` tuning**: `pm.max_children = (RAM - reserved) / avg_request_memory`; too low causes connection backlog, too high triggers OOM under burst. Flag changes that alter `pm.max_children` without a load profile
- [ ] **Response compression**: nginx / Octane response compression (gzip / brotli); large JSON responses benefit
- [ ] **Telescope disabled in production** (or strictly gated): Telescope adds significant overhead per request - never enable in prod traffic. `Telescope::filter(...)` for sampling if essential

### Step 11 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

This step is intentionally narrow - depth on observability belongs to `task-laravel-review-observability`. From a perf perspective, confirm only:

- [ ] Slow paths reachable from this PR have **some** instrumentation (`Log::info(...)` with structured context OR a custom metric); if not, raise as a Low/Recommendation finding and delegate to `task-laravel-review-observability` for a proper instrumentation pass rather than dictating the design here
- [ ] Slow query log enabled in non-prod for query analysis (MySQL `slow_query_log=ON`, `long_query_time=0.5`); EXPLAIN runnable via `Model::query()->explain()` (Laravel 12+ syntax) or `DB::enableQueryLog()` in dev
- [ ] Telescope / Clockwork / Debugbar runnable in non-prod for live profiling (no code change needed; this is a CI / runbook check)

Anything beyond presence/absence (sampling rates, span attributes, correlation IDs, multi-process metric aggregation, log channel design) → `task-laravel-review-observability` owns it. Note the gap, do not duplicate the audit here.


### Step 12 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 before any other delegation (or accepted from parent dispatcher)
- [ ] Stack confirmed as PHP / Laravel; database engine, queue connection, cache driver, runtime recorded before any specific check applied (Step 2)
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured (Step 3)
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review (Step 3)
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued (Step 3)
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent) (Step 3)
- [ ] Performance surface read directly (models, controllers, Blade views, API Resources, jobs, dispatch sites, migrations, cache sites, HTTP sites) (Step 4)
- [ ] `laravel-eloquent-patterns` consulted; N+1 (controllers + Blade + Resources), `$with` over-fetch, `Model::all()` on growable, paginate-vs-cursor, aggregates, collection-then-paginate, `Cache::remember` callback contents checked (Step 5)
- [ ] `laravel-migration-safety` consulted for any migration change; reversible, two-phase rename/drop, online DDL, FK constraint, chunked backfill, deploy-ordering verified (Step 6)
- [ ] `laravel-queue-patterns` consulted; sync-in-prod, `$tries`/`$backoff`/`$timeout`/`failed()` discipline, scalar IDs, `afterCommit`, `RateLimited` / `WithoutOverlapping` middleware, `Bus::batch` for fan-out, Horizon supervisor sizing audited (Step 7)
- [ ] HTTP client / external calls reviewed (`Http::timeout` / `retry` / `pool`, persistent client, fakes in tests) (Step 8)
- [ ] Caching strategy assessed (`Cache::remember` TTL, tags driver gate, single-flight via `Cache::lock`, invalidation explicit) (Step 9)
- [ ] Runtime / OPcache / Octane readiness assessed; static state and request-leaking singletons flagged regardless of current runtime (Step 10)
- [ ] Observability hand-off captured for any slow path lacking instrumentation; deferred to `task-laravel-review-observability` rather than dictated here (Step 11)
- [ ] Severity rubric applied consistently (High / Medium / Low matches the rubric, not invented)
- [ ] Every finding states impact - measured (`p95: 800ms -> 120ms`) when profiler / APM data exists, estimated otherwise (`adds ~N queries per request at K rows` or `each unbounded retry compounds queue depth`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 5 + 6; `standard` ran 5-11; `deep` adds capacity guidance and load-test plan
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

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

### High Impact

- **Location:** [file:line]
- **Issue:** [what the problem is - name the Laravel idiom: N+1 via lazy-loaded `$order->user` in Blade `@foreach`, missing `with()` chain, `Model::all()` on a 10M-row table, `paginate()` running `COUNT(*)` on huge table, OFFSET pagination, `whereRaw` with interpolated input defeating plan cache, `LIKE '%term%'` without FULLTEXT, job constructor takes Eloquent model, missing `afterCommit()` on dispatch inside transaction, queue connection `sync` in prod, `WithoutOverlapping` missing on resource-bound job, etc.]
- **Impact:** [estimated effect - e.g., "N+1 in OrdersController.index adds ~200 queries per request at 100 orders" or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [specific Laravel change with code example - `Order::with(['user', 'items'])->cursorPaginate(25)`, scalar ID in job constructor, `dispatch(new ProcessPayment($id))->afterCommit()`, `Bus::batch(...)`, `Cache::lock(...)` single-flight, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Switch list endpoint to `cursorPaginate`", "Add Redis cache for product catalog reads with tag-based invalidation", "Move PDF generation to a `Bus::batch` of jobs", "Bind Guzzle Client as a singleton via container", "Enable `Model::preventLazyLoading()` in `AppServiceProvider::boot` for non-prod"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, schema migration, or load-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Replace `Order::all()` with `Order::cursorPaginate(50)` in `OrdersController.index`; add `with(['user'])` for the listing"]
2. **[Delegate]** [High] [scope: schema] - [one-line action, e.g., "Add `(tenant_id, created_at)` composite index via `pt-online-schema-change` - spawn DB migration subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting issues without naming the Laravel idiom ("this is slow" vs "N+1 from lazy-loaded `$order->items` in `OrdersController::index`'s Blade view; replace with `Order::with('items')->cursorPaginate(25)`")
- Recommending generic backend advice when a Laravel pattern applies (say "use `Bus::batch` for fan-out", not "use a worker pool")
- Suggesting `Model::all()` on growable tables - use `chunkById` / `lazy` / `cursor` / `cursorPaginate`
- Suggesting `paginate()` on tables > 1M rows when `cursorPaginate` would do - the COUNT(*) is the bottleneck
- Suggesting `Cache::flush()` for targeted invalidation - flushes the whole driver; use `Cache::tags(...)->flush()` or `Cache::forget($key)`
- Suggesting `whereRaw($input)` for "dynamic" queries - parameterize via bindings or use the query builder. When `whereRaw($input)` is found, the perf concern (defeats plan cache) is the smaller half - the SQL injection surface is the bigger half. Add a `[Delegate] -> task-laravel-review-security` entry to Next Steps so the security half doesn't get silently absorbed into a perf finding
- Suggesting jobs constructed with Eloquent model parameters - serializes a stale snapshot; pass scalar IDs and re-fetch in `handle()`
- Suggesting `dispatch` inside `DB::transaction` without `afterCommit()` - worker may pick up before commit
- Suggesting `QUEUE_CONNECTION=sync` in production - inline execution defeats every queue guarantee
- Approving `$with` auto-eager-load on model without justifying why every fetch needs those relations
- Approving `app()->singleton` capturing request state without flagging as Octane / FrankenPHP foot-gun
- Approving `Telescope` enabled in production - significant per-request overhead

> **Cross-workflow finding ownership.** When a finding is dual perf+security (the `whereRaw($input)` interpolation above, queue-job deserializing untrusted input, file uploads on hot endpoints), the perf review reports it once with a `[Delegate] -> task-laravel-review-security` entry in Next Steps and stops there - it does **not** enumerate every parallel security concern in the file (auth bypass, IDOR, mass assignment, open redirect). Those are the security delegate's territory.

- Reporting "missing index" without confirming the column actually appears in a `where` / `orderBy` / `groupBy` in the diff
- Approving `Eloquent::all()` returns to API endpoints - bandwidth and memory waste; paginate or cursor
- Approving `$model->fresh()` / `refresh()` per loop iteration - N round-trips
- Approving lazy loading inside Blade loops - flag and recommend `with(...)` at the controller
