---
name: task-laravel-review-perf
description: Laravel performance review for Eloquent N+1 (lazy loading in Blade / controllers / API Resources, missing `with()`), `Include` cartesian explosion via multi-collection eager loads, missing indexes for `where`/`orderBy`/`groupBy` columns, MySQL slow-query patterns (LIKE with leading `%`, `OFFSET` pagination on large tables, missing FULLTEXT), `DB::transaction` boundary discipline, queue throughput (Redis vs database driver, Horizon supervisor sizing, `$tries` / `$backoff` tuning, batching, rate limiting), `Cache::remember` strategy, `Http::pool` / Guzzle connection reuse, OPcache + JIT + Octane / FrankenPHP / RoadRunner readiness, Blade view caching, route caching. Stack-specific override of task-code-review-perf for PHP / Laravel.
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
- Pre-implementation feature design (use `task-laravel-new`)

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
| `quick`    | Single endpoint or Eloquent model ("is this query ok?")      | Steps 4 + 5 only; Eloquent hotspots + migrations   |
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

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect ORM / Queue / Runtime Surface

Use skill: `stack-detect` to confirm PHP / Laravel. If the detected stack is not Laravel, stop and tell the user to invoke `/task-code-review-perf` instead.

Detect ORM use: Eloquent (typical) or query builder (`DB::table(...)`). Detect queue connection from `config/queue.php` and `.env`: `redis` (typical, with Horizon), `database`, or `sync` (smell in non-local). Detect runtime: standard PHP-FPM (typical), Laravel Octane + Swoole / RoadRunner / FrankenPHP (request-state leakage concerns). Detect cache driver: `redis`, `memcached`, `database`, `file`, `array`. Detect database engine from `config/database.php`: MySQL (typical), PostgreSQL, MariaDB.

Record `Database: MySQL <version> | PostgreSQL <version> | MariaDB <version>`, `Queue: redis (Horizon) | database | sync`, `Cache: redis | memcached | database | file`, `Runtime: PHP-FPM | Octane (Swoole) | Octane (RoadRunner) | FrankenPHP` for the Summary block. Each Step 4-9 checklist branches on this signal where the idiom differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Performance Surface

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

### Step 4 - Eloquent / Database Hotspots

Use skill: `laravel-eloquent-patterns` for canonical Eloquent perf patterns.

Inspect every changed query, model, controller, service, job, Blade view, and API Resource for:

- [ ] **N+1 in queries**: any `$model->relation` access inside a `foreach` / Blade `@foreach` over a parent collection without `->with('relation')` is N+1. Resolve via `Model::with(['rel1', 'rel2.subrel'])->get()`. Same for API Resources accessing `$this->user->name` in `toArray()` - eager-load at the controller before passing to the Resource
- [ ] **`Model::preventLazyLoading()` in dev**: `AppServiceProvider::boot()` guards against accidental lazy loading by throwing `LazyLoadingViolationException` outside production. Flag missing call as `[Suggestion]`
- [ ] **`$with` auto-eager-load misuse**: `protected $with = ['user', 'items', 'shipments'];` on a model loads three relations on every fetch even when only `user.name` is needed - over-fetching at the model level. Prefer per-call `with(...)`. Flag any new `$with` declaration without justification
- [ ] **Multi-relation eager-load explosion**: `Order::with(['items', 'shipments', 'history'])->get()` materializes one query per relation; for join-style flat-row reads, consider `selectRaw` with explicit projection or a dedicated read model
- [ ] **`Model::all()` on growable tables**: `Order::all()` materializes every row; for any table that grows over time, use `chunkById(1000, fn ($rows) => ...)`, `lazy()` (memory-efficient generator), or `cursor()` (lowest memory, no eager loading - N+1 trap if relations are accessed)
- [ ] **`$collection->count()` after fetch**: `Order::with('items')->get()->count()` fetches every row to count; use `Order::count()` for raw counts, or `Order::withCount('items')` to get per-row counts via a single SQL aggregate
- [ ] **Database aggregates over collection aggregates**: `$user->reviews->avg('rating')` loads every review into memory; `$user->reviews()->avg('rating')` runs `AVG(rating)` in SQL. Same for `count`/`sum`/`min`/`max`. Use the relationship's query builder (note the `()`)
- [ ] **`paginate()` running `COUNT(*)` on huge tables**: `Order::paginate(25)` runs both `SELECT * ... LIMIT 25` and `SELECT COUNT(*) ...`; on a 10M+-row table the COUNT is the bottleneck. Use `simplePaginate` (no count) or `cursorPaginate` (keyset, scales to any size)
- [ ] **OFFSET pagination on large tables**: `LIMIT 25 OFFSET 100000` scans 100025 rows to skip 100000. Use `cursorPaginate` (`WHERE id > $lastId LIMIT N`) for any list endpoint that can grow
- [ ] **Missing indexes for `where` / `orderBy` / `groupBy` / FK columns**: any column referenced in those clauses needs an index in the migration. Composite index column order matches the query's leftmost-prefix usage
- [ ] **`whereRaw`/`orderByRaw`/`selectRaw`/`havingRaw` defeats the query plan cache**: when the SQL fragment changes per request (interpolated values, non-parameterized), MySQL re-plans every query. Use bindings (`whereRaw('JSON_EXTRACT(metadata, ?) = ?', ['$.shipping', $method])`) or the JSON query builder (`->where('metadata->shipping_method', $method)`)
- [ ] **`LIKE '%term%'` (leading wildcard)**: cannot use a B-tree index, falls back to full-table scan. Use FULLTEXT index + `whereFullText(['col'], $term)` (MySQL 5.6+ InnoDB). For non-text exact-match prefix search, use `LIKE 'term%'` (no leading wildcard - index works) or a generated column with a B-tree
- [ ] **`firstOrCreate` / `updateOrCreate` race**: under concurrent requests, two callers may race the SELECT and both INSERT, hitting unique-constraint violations. Wrap in `DB::transaction` + `lockForUpdate`, or use `upsert` (Laravel's `Model::upsert([...], ['unique_col'], ['updatable_cols'])` for bulk `INSERT ... ON DUPLICATE KEY UPDATE`)
- [ ] **`save()` per row in a loop**: `foreach ($rows as $row) { Model::create($row); }` is N round-trips. Use `Model::insert([$row1, $row2, ...])` (skips Eloquent events / timestamps - careful) or `Model::upsert(...)` for bulk; or wrap in a single `DB::transaction` to amortize commit cost
- [ ] **Soft-delete query overhead**: `SoftDeletes` adds `WHERE deleted_at IS NULL` to every query. Confirm an index exists on `deleted_at` (or composite indexes including it) for hot tables
- [ ] **`$model->fresh()` / `$model->refresh()` per iteration**: re-fetching a model inside a loop is N round-trips. Reload the whole collection once after the bulk operation, or skip the refresh if the in-memory state is sufficient
- [ ] **`DB::transaction()` holding row locks across HTTP / queue I/O**: `DB::transaction(function () use ($req) { $order = Order::lockForUpdate()->find($id); Http::post(...); $order->update(...); })` holds the row lock for the upstream's tail latency. Capture inputs, exit transaction, dispatch HTTP / job after commit
- [ ] **Connection pool sizing**: `php-fpm pm.max_children` × number of replicas must be ≤ MySQL `max_connections` minus headroom for ops / replication. Octane workers count differently - one persistent worker per slot. Flag new replicas / supervisors without checking the pool budget
- [ ] **Read replica usage**: read-heavy endpoints can route to a read replica via `config/database.php` `read` array. Sticky-after-write protects read-your-own-write flows; flag new high-read endpoints on the writer
- [ ] **Bulk update via `Eloquent::query()->update(...)` skips events**: `Order::where('status', 'pending')->update(['status' => 'processing'])` does not fire `updating` / `updated` events, does not write `updated_at` unless explicitly included. Intentional in many cases, but flag if the codebase relies on observers for audit logging

### Step 5 - Indexes and Migrations

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

### Step 6 - Queue Throughput, Jobs, and Scheduling

Use skill: `laravel-queue-patterns` for canonical queue patterns.

Inspect every changed job, listener, dispatch site, scheduled command, and `config/queue.php` / `config/horizon.php`:

- [ ] **Queue connection is not `sync` in production**: `QUEUE_CONNECTION=sync` runs jobs inline in the request thread. Flag any production env file or `dispatchSync` usage on user-request paths
- [ ] **`$tries`, `$backoff`, `$timeout`, `$maxExceptions`, `failed()` set on every job**: defaults are unbounded retries plus a 60s timeout. Set `public int $tries = 3;`, `public array $backoff = [10, 60, 300];` (exponential), `public int $timeout = 120;`, `public int $maxExceptions = 3;`, plus `failed(Throwable $e)` for notification / dead-letter handling
- [ ] **`retryUntil()` for time-bounded jobs** (e.g., webhook delivery): `public function retryUntil(): DateTime { return now()->addHours(2); }` stops retrying after the deadline regardless of `$tries`
- [ ] **Scalar IDs in job constructors, not Eloquent models**: `new ProcessPayment($order)` serializes a snapshot of the model into the queue payload (and `SerializesModels` re-fetches anyway). Always pass IDs (`new ProcessPayment($order->id)`) and `Order::findOrFail($this->orderId)` inside `handle()`. Flag jobs with model-typed constructor parameters
- [ ] **`->afterCommit()` for jobs dispatched inside transactions**: a job dispatched inside `DB::transaction(fn() => ...)` may be picked up by a Redis worker before the transaction commits. Use `dispatch((new ProcessPayment($id))->afterCommit())` or set `public bool $afterCommit = true;` on the job. For projects setting `QUEUE_AFTER_COMMIT=true` globally in `config/queue.php`, `afterCommit` is the default - flag any explicit `withoutCommit()` override
- [ ] **Idempotent `handle()`**: queues deliver at-least-once; the same job may be processed twice (worker crash after side effect, before ack). Dedup via business key + DB unique constraint, version check, or upsert
- [ ] **`RateLimited` middleware on third-party-API jobs**: jobs calling external APIs respect the API's rate limit via `Job::middleware()` returning `[new RateLimited('stripe-api')]` (rate limiter defined in `RouteServiceProvider`). Without it, a backlog of jobs hammers the third party and burns retry budget on 429s
- [ ] **`WithoutOverlapping` middleware for resource-bound jobs**: jobs that mutate a single aggregate (a specific order, a specific user) use `[new WithoutOverlapping($this->orderId)]` to serialize per-key, preventing concurrent updates
- [ ] **`Bus::batch(...)` for fan-out**: when 1000 jobs need to run as a unit (with progress, all-or-nothing failure), use `Bus::batch([...])->then(...)->catch(...)->dispatch()`. Bare `foreach { dispatch(new Job(...)) }` over a 10k-item list works but loses batch semantics
- [ ] **`Bus::chain(...)` for ordered pipelines**: when job B depends on job A's success, chain instead of dispatching B from A's `handle()` (chain handles failures cleanly)
- [ ] **Horizon supervisor sizing** (Redis queues): `config/horizon.php` `supervisor-1.processes` matches the workload. Auto-scaling balance strategy (`balance => 'auto'`) with `minProcesses` / `maxProcesses` is canonical for variable load. Flag `simple` balance on multi-queue environments (long jobs starve short jobs)
- [ ] **Per-queue priority**: Horizon's `queue` array order is priority order; high-priority work (`emails`, `notifications`) goes first. Flag everything dumped on `default` when priority matters
- [ ] **`sync` driver in tests is fine**: `database`/`redis` in CI is unnecessarily slow. Use `Queue::fake()` for unit tests asserting dispatch, or `php artisan queue:work --once` patterns for integration
- [ ] **`scheduled` jobs with `->withoutOverlapping()` and `->onOneServer()`**: scheduled commands running on multiple replicas race; `withoutOverlapping` (cache lock per command name) and `onOneServer` (one server runs the command per tick) prevent dupes. Flag scheduled commands without these on multi-replica deployments
- [ ] **Long-running scheduled commands use `runInBackground()`**: keeps the scheduler tick from blocking on a 5-minute job
- [ ] **Job memory leaks via collection passing**: passing `Collection` of Eloquent models in job constructors balloons payload size and serializes deeply-loaded relations. Pass IDs or scalar arrays; re-fetch in `handle()`
- [ ] **`dispatch(...)` from web tier to a queue with high backlog**: dispatching to a depth-saturated queue blocks the request on `Redis::push` if Redis is also saturated. Monitor queue depth; alert thresholds defined

### Step 7 - HTTP Client / External Calls

Inspect every changed `Http::*` and Guzzle usage:

- [ ] **`Http::timeout(...)`** explicit on every outbound call - default is no client timeout in older Laravel versions (relies on PHP `default_socket_timeout`); set `Http::timeout(5)->retry(3, 100)` per call site or via a service container macro
- [ ] **`Http::retry(...)` with backoff** for transient failures; `retry(3, 100, fn ($e) => $e instanceof ConnectionException)` filters retries to recoverable cases
- [ ] **`Http::pool(fn ($pool) => [...])` for parallel HTTP fan-out**: `Http::pool` runs the callbacks concurrently via Guzzle's async pool. Sequential `Http::get(...)` calls in a controller for 5 endpoints is 5x serial latency; pool is one cumulative roundtrip-equivalent (per the slowest)
- [ ] **Persistent Guzzle / SDK clients via container**: instantiating `new Client(...)` per request defeats keep-alive and connection reuse. Bind in `AppServiceProvider`: `$this->app->singleton(Client::class, fn () => new Client(['base_uri' => ...]));`. SDKs (Stripe, AWS SDK) usually have built-in connection reuse - confirm not constructed per-request
- [ ] **Circuit breaker for fragile upstream**: when an upstream fails for minutes, retry storm makes it worse. Use `tk707/laravel-circuit-breaker` (or similar) on third-party APIs with known instability
- [ ] **Mock external HTTP in tests** via `Http::fake([...])` - never hit real network in CI

### Step 8 - Caching and Response Performance

_Skipped at `quick` depth unless the diff touches caching primitives._

- [ ] **`Cache::remember($key, $ttl, fn () => ...)`** for expensive read paths; explicit TTL mandatory; `Cache::rememberForever(...)` only with a clear invalidation story (event-driven `forget`, tag flush on related write)
- [ ] **`Cache::tags([...])->remember(...)` only on `redis` / `memcached` drivers**: `database` / `file` / `array` drivers do not support tags - calls throw. Confirm driver before using tags
- [ ] **Cache stampede protection via `Cache::lock(...)`**: hot keys with expensive regeneration use single-flight - `Cache::lock("regen:$key", 10)->block(5, fn () => Cache::remember(...))` ensures only one process regenerates while others wait
- [ ] **Cache invalidation explicit**: no caches that never expire and never invalidate; document staleness budget; prefer event-driven invalidation (`OrderUpdated` listener that calls `Cache::tags(['orders'])->flush()`) over time-based when correctness matters
- [ ] **HTTP-level caching**: `Cache-Control` headers on read-heavy GET endpoints; `ETag` / `Last-Modified` for conditional requests (304 saves serialization + transfer); Laravel's `Cache::response()` middleware or manual `header(...)` calls
- [ ] **View caching in production**: `php artisan view:cache` precompiles Blade templates; `php artisan config:cache` and `php artisan route:cache` cache config and routes. Deploy script must run these; missing them on prod deploys is a `[Low]` finding
- [ ] **Per-request memoization**: store on the container or a request-scoped service for values used by multiple consumers in the same request (config, current tenant, current user permissions)
- [ ] **`Cache::flush()` flagged**: flushes the entire driver in some configs (e.g., `redis` flushes all DBs on the connection). Use `Cache::tags(...)->flush()` or `Cache::forget($key)` for targeted invalidation

### Step 9 - Runtime, OPcache, Octane Readiness

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

### Step 10 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

This step is intentionally narrow - depth on observability belongs to `task-laravel-review-observability`. From a perf perspective, confirm only:

- [ ] Slow paths reachable from this PR have **some** instrumentation (`Log::info(...)` with structured context OR a custom metric); if not, raise as a Low/Recommendation finding and delegate to `task-laravel-review-observability` for a proper instrumentation pass rather than dictating the design here
- [ ] Slow query log enabled in non-prod for query analysis (MySQL `slow_query_log=ON`, `long_query_time=0.5`); EXPLAIN runnable via `Model::query()->explain()` (Laravel 12+ syntax) or `DB::enableQueryLog()` in dev
- [ ] Telescope / Clockwork / Debugbar runnable in non-prod for live profiling (no code change needed; this is a CI / runbook check)

Anything beyond presence/absence (sampling rates, span attributes, correlation IDs, multi-process metric aggregation, log channel design) → `task-laravel-review-observability` owns it. Note the gap, do not duplicate the audit here.

## Self-Check

- [ ] Stack confirmed as PHP / Laravel; database engine, queue connection, cache driver, runtime recorded before any specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent)
- [ ] Performance surface read directly (models, controllers, Blade views, API Resources, jobs, dispatch sites, migrations, cache sites, HTTP sites)
- [ ] `laravel-eloquent-patterns` consulted; N+1 (controllers + Blade + Resources), `$with` over-fetch, `Model::all()` on growable, paginate-vs-cursor, aggregates checked
- [ ] `laravel-migration-safety` consulted for any migration change; reversible, two-phase rename/drop, online DDL, FK constraint, chunked backfill, deploy-ordering verified
- [ ] `laravel-queue-patterns` consulted; sync-in-prod, `$tries`/`$backoff`/`$timeout`/`failed()` discipline, scalar IDs, `afterCommit`, `RateLimited` / `WithoutOverlapping` middleware, Horizon supervisor sizing audited
- [ ] HTTP client / external calls reviewed (`Http::timeout` / `retry` / `pool`, persistent client, fakes in tests)
- [ ] Caching strategy assessed (`Cache::remember` TTL, tags driver gate, single-flight via `Cache::lock`, invalidation explicit)
- [ ] Runtime / OPcache / Octane readiness assessed; static state and request-leaking singletons flagged regardless of current runtime
- [ ] Every finding states impact - measured (`p95: 800ms -> 120ms`) when profiler / APM data exists, estimated otherwise (`adds ~N queries per request at K rows` or `each unbounded retry compounds queue depth`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 4 + 5; `standard` ran 4-10; `deep` adds capacity guidance and load-test plan
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)

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
