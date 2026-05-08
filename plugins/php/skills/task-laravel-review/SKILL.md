---
name: task-laravel-review
description: Laravel staff-level code review umbrella - Phases A-E (risk, correctness, architecture, AI quality, maintainability) with PHP 8.5 / Laravel 12+ / Eloquent idioms (mass assignment via `$guarded = []` or unfiltered `Model::create($request->all())`, N+1 via lazy loading without `with()`, `DB::raw`/`whereRaw` SQL injection, missing `$this->authorize()` / Policy enforcement, jobs dispatched inside transactions without `afterCommit()`, jobs taking Eloquent models in constructors, raw model returned from controller instead of API Resource, `env()` outside config files, fat controllers with business logic). Spawns Laravel-specific perf / security / observability subagents for extra scopes. Stack-specific override of task-code-review for PHP / Laravel. Runs standalone with full PR/branch resolution.
agent: php-tech-lead
metadata:
  category: backend
  tags: [php, laravel, eloquent, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Laravel Code Review

## Purpose

Laravel-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with Laravel-specific correctness, architecture, AI-quality, and maintainability checks (mass assignment via `$guarded = []` or `Model::create($request->all())`, Eloquent N+1 via lazy loading inside Blade or controllers, `DB::raw($input)` / `whereRaw("col = '$input'")` SQL injection, missing `$this->authorize()` or Policy on owner-data endpoints, jobs dispatched inside transactions without `->afterCommit()`, jobs taking Eloquent model instances in constructors instead of scalar IDs, fat controllers with business logic that belongs in services/actions, raw Eloquent models returned from controllers instead of API Resources, `env()` calls outside config files, missing `Form Request` validation, `$fillable` drift from the migrated columns, missing rate limiting on `/login`, queue connection set to `sync` in production). Coordinates Laravel-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for PHP / Laravel. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved so callers see a stable shape. **Runs standalone** with full PR/branch resolution - the core dispatcher is optional, not required.

## When to Use

- Reviewing a Laravel PR before merge
- Post-AI-generation quality gate on a Laravel change set
- Architecture drift detection in a layered Laravel codebase (controllers / form requests / services / actions / repositories / jobs)
- Pre-merge risk assessment on a Laravel branch

**Not for:**

- Pre-implementation feature design (use `task-laravel-implement`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error / exception debugging (use `task-laravel-debug`)
- Architecture/design review of a new system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-laravel-review-perf`, `task-laravel-review-security`, or `task-laravel-review-observability`

## Depth Levels

Mirrors `task-code-review`:

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full Laravel staff-level review                                 | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface this in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                  |
| --------------- | -------------------------------------------------------------------------- |
| Core            | Phases A-E only (Laravel-flavored)                                         |
| + Perf          | Core + parallel subagent: `task-laravel-review-perf`                       |
| + Security      | Core + parallel subagent: `task-laravel-review-security`                   |
| + Observability | Core + parallel subagent: `task-laravel-review-observability`              |
| Full            | Core + Performance + Security + Observability (3 parallel Laravel subagents)|

Default: **Core with auto-escalation** (same signal rules as `task-code-review`). Pass `core-only` to suppress.

**Scope auto-escalation signals (Laravel-tuned):**

- File uploads (`$request->file(...)`, `Storage::put`), Sanctum / Passport / `auth:` middleware changes, Gate / Policy edits, `Model::create($request->all())` / `update($request->all())` patterns, `DB::raw($input)` / `whereRaw("... $input")`, secrets read via `env()` in business code, queue jobs accepting webhook payloads, signed URLs / `URL::signedRoute`, `Crypt::encrypt`, deserialization of untrusted input → auto-add **+Security**
- New Eloquent query (`Model::where(...)`), new `with()` / eager-load chain, new Blade view iterating a relationship, new `paginate()` / `simplePaginate()` / `cursorPaginate()`, new endpoint with payload, loops calling DB or HTTP, new `Cache::remember` read paths, new `Http::pool` fan-out, new dispatched job → auto-add **+Perf**
- New service / package, new external client (`Http::withToken`, AWS SDK, Stripe SDK, etc.), new Job / Listener / `Schedule::*`, change to `bootstrap/app.php` / `config/logging.php` / `config/queue.php`, new `Log::*` channel / `Telescope` / `Horizon` config, lifecycle changes (queue worker shutdown, scheduler) → auto-add **+Observability**
- Migration touching hot table (`alter`/`drop column`/`change()`/index add on a table referenced by 5+ files in the diff or named in the PR title), addition of NOT NULL on existing column without nullable→backfill→set-NOT-NULL pattern, single-migration column rename or drop → auto-add **+Perf** (so the migration-safety review is folded into the perf subagent rather than carried inline)
- Two or more signal categories present → promote to **Full**

## Invocation

The slash command accepts an optional argument identifying the diff to review:

| Invocation                      | Meaning                                                                                                                                                                                |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-laravel-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                            |
| `/task-laravel-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                      |
| `/task-laravel-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants)  |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs and never modifies your working tree.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>` so the diff is computed against the true base.

Examples:

- `/task-laravel-review pr-123 --base release/2026.05` - PR opened against release branch
- `/task-laravel-review feature/x --base develop` - branch off `develop` rather than `main`

Scope and depth flags compose: `/task-laravel-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every subsequent step (think before acting, surgical changes, surface confusion, push back when the user is likely wrong). When invoked as a subagent of `task-code-review`, accept the parent's confirmation that this skill is already loaded; do not re-load.

### Step 2 - Confirm Stack and Detect Eloquent / Queue / Auth Surface

Use skill: `stack-detect` to confirm PHP / Laravel. If invoked as a delegate of `task-code-review` (parent already detected Laravel), accept the pre-detected stack and skip re-detection. If the detected stack is not Laravel, stop and tell the user to invoke `/task-code-review` instead.

Detect ORM use: Eloquent (typical), DB query builder (`DB::table(...)`), or raw SQL via `DB::statement`. Detect auth: Sanctum (token / SPA), Passport (OAuth), or session-only. Detect queue driver from `config/queue.php` and `.env` (`QUEUE_CONNECTION`): Redis (typical with Horizon), database, or sync (a `[Blocker]` in production). Detect testing framework: Pest (primary) or PHPUnit. Record `PHP: <version>`, `Laravel: <version>`, `Auth: Sanctum (token) | Sanctum (SPA) | Passport | session`, `Queue: redis (Horizon) | database | sync`, `Tests: Pest | PHPUnit`. Each Phase B / C / D / E checklist below branches on this signal where the idiom differs.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). Forward `--base <branch>` if the user passed it.

If the precondition check stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

Once approved, read the diff and commit log directly using the returned refs:

- Diff: `git diff <base_ref>...<head_ref>`
- Files changed: `git diff --name-status <base_ref>...<head_ref>`
- Commit log: `git log --oneline <base_ref>..<head_ref>`

All subsequent phases operate on this read-once diff and log; do not re-derive them.

**Skip this entire step** when invoked as a subagent of `task-code-review` and the parent passed the precondition handle plus pre-read diff and commit log. Reuse the parent's artifacts.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff content for the auto-escalation signals listed under **Scope** above. Make this explicit because the default of "skip if user did not pass `+security` etc." silently misses the cases where the change itself signals the need.

For each signal that fires, log a one-liner: `signal: <category> -> <file:line>`. Then decide:

- Zero signals or user passed `core-only` -> stay on Core
- One signal category -> add the matching extra scope
- Two or more signal categories -> promote to Full
- User passed an explicit scope -> respect it (do not downgrade), but still record signals so the Summary documents why the chosen scope was correct

Surface the decision in the Summary's `Scope:` field. If escalated, append `auto-escalated from Core; signals: <list>`. If the user passed a scope and signals contradicted it, surface a one-line note so reviewers see what was deliberately deferred.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (auth middleware, Sanctum / Passport config, `bootstrap/app.php`, `config/auth.php`, `config/queue.php`, `config/database.php`, Eloquent model `$fillable` / `$casts`, Policies, `database/migrations/`), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Step 4.5 - Re-evaluate Depth After Phase A

If `Blast Radius` (from Phase A) is `Wide` or `Critical` and the user did not explicitly pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)` in the Summary. Do this **before** launching Phases B-E so deep-only behaviors (historical pattern matching, cross-PR context, anemic-domain assessment) are in scope for the rest of the review.

### Phase B - Laravel Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting state integrity, backward compatibility, transaction boundary correctness, queue dispatch safety - through a Laravel lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding Pest / PHPUnit feature or unit coverage, raise this as an explicit finding. At minimum a [Suggestion]; escalate to [High] when the change is in a critical path - any of: authentication (Sanctum guards, custom auth middleware), authorization (Policies, Gates, ownership checks), money or billing flows, data-integrity writes (multi-step `DB::transaction` blocks), queue jobs that mutate data (`ShouldQueue` jobs with side effects), migrations that change column semantics. Do not bury this finding in Key Takeaways - a separate, named entry in Findings.

**Wrong-store test finding:** When a feature test runs against SQLite (`DB_CONNECTION=sqlite` or `:memory:` in `phpunit.xml` / `.env.testing`) but the production app uses MySQL/PostgreSQL, raise as `[High]`. SQLite does not enforce some FK behaviors, has different `JSON` column semantics, lacks fulltext indexing, and behaves differently under concurrent updates - tests pass while prod fails. This is more dangerous than missing tests (false confidence vs known gap).

**Laravel-specific correctness checks:**

- [ ] **No `$guarded = []` on Eloquent models**: opens every column to mass assignment via `Model::create($request->all())`. Always whitelist via `protected $fillable = [...]` listing exactly the user-supplied columns. Server-set fields (`user_id`, `tenant_id`, `role`, `is_admin`, `verified_at`, `password`) must be assigned explicitly, never via fillable
- [ ] **No `Model::create($request->all())` / `update($request->all())`**: passes the full request payload, including unexpected fields. Use `$request->validated()` (from a Form Request) so only validated fields land on the model. Even with `$fillable`, `$request->all()` smells - a future fillable change adds a silent attack surface
- [ ] **Form Request used for validation**: every controller action accepting input uses a typed Form Request (`StoreOrderRequest`, `UpdateOrderRequest`) with `rules()`, not inline `$request->validate([...])`. Inline validation scatters rules across the codebase and bypasses `authorize()` hook
- [ ] **Form Request `authorize()` returns explicit boolean**: `authorize()` returning `true` (default) is opt-in unprotected - flag any new Form Request that returns `true` without an `authorize()` override checking `$this->user()->can('...')`. The default `parent::authorize()` returns `true` in Laravel 11+; explicit `return false;` or `return $this->user()->can('update', $this->route('order'));`
- [ ] **`$this->authorize(...)` or Policy on every protected action**: every controller action touching user-owned data has either a Policy check (`$this->authorize('view', $order)`), a Gate (`Gate::authorize('admin')`), middleware (`->middleware('can:update,order')`), or an explicit ownership filter on the query. Bare `Order::find($id)` without ownership scoping or policy is IDOR - scope via `$user->orders()->findOrFail($id)` or via `Order::where('id', $id)->where('user_id', $user->id)->firstOrFail()`
- [ ] **Route model binding scoping**: `Route::get('/orders/{order}')` resolves any order by id; for nested per-owner resources use scoped binding (`Route::get('/users/{user}/orders/{order}')->scopeBindings()`) or scope inside the controller
- [ ] **No raw SQL string interpolation via `DB::raw`/`whereRaw`/`orderByRaw`/`selectRaw`/`havingRaw` with user input**: `DB::raw("WHERE id = $id")`, `whereRaw("status = '$status'")`, `orderByRaw($request->input('sort'))` are SQL injection. Use parameter bindings (`whereRaw('status = ?', [$status])`) or, better, the Eloquent query builder (`->where('status', $status)`). User-supplied `orderBy` / `orderByRaw` must validate against an allowlist of column names
- [ ] **N+1 in queries**: any `$model->relation` access inside a `foreach` over a parent collection without `->with('relation')` is N+1. Same for Blade `@foreach ($orders as $order) {{ $order->user->name }} @endforeach` without eager loading. Use `Order::with(['user', 'items'])->get()`. In dev, enable `Model::preventLazyLoading()` in `AppServiceProvider::boot()` to surface lazy loads as exceptions
- [ ] **`$model->all()` flagged on growable tables**: `Order::all()` materializes every row into memory; for any table that grows over time, use `chunk()` / `chunkById()` / `lazy()` / `cursor()` or pagination
- [ ] **Single `DB::transaction()` boundary per use case**: when a use case writes to multiple tables, wrap in `DB::transaction(function () use ($req) { ... })`. Multiple separate `save()` calls without a transaction split atomicity
- [ ] **Jobs dispatched after commit, not inside the transaction**: dispatching a queue job inside `DB::transaction(...)` lets a worker pick up the job before the row is visible (Redis worker is faster than the DB commit). Use `dispatch((new ProcessPayment($id))->afterCommit())` or set `public bool $afterCommit = true;` on the job class. For Redis queue with `QUEUE_AFTER_COMMIT=true` set globally, this is automatic but still flag uses of `dispatchSync(...)` inside a transaction
- [ ] **Jobs accept scalar IDs, not Eloquent models**: `new ProcessPayment($order)` serializes a snapshot of the model into the queue payload; when the worker picks it up minutes later, the model state is stale and `SerializesModels` re-fetches from the DB anyway. Always pass IDs (`new ProcessPayment($order->id)`) and `findOrFail()` inside `handle()`
- [ ] **`$tries`, `$backoff`, `$timeout`, `failed()` set on every queueable job**: defaults are unbounded retries which produce runaway failure cascades. `public int $tries = 3;`, `public array $backoff = [10, 60, 300];`, `public int $timeout = 120;`, plus a `failed(Throwable $e)` method for notifications / dead-letter handling
- [ ] **No `env()` outside `config/*.php` files**: `env()` returns null after `php artisan config:cache` in production. Only config files may call `env()`; application code reads `config('services.stripe.key')`. New `env(...)` calls in controllers/services/jobs are findings
- [ ] **`config:cache` compatibility**: configuration values must be cacheable - no closures in config arrays, no calls that depend on request state at config-resolution time
- [ ] **No raw Eloquent model returned from controller**: always wrap with an API Resource (`OrderResource::make($order)` / `OrderResource::collection($orders)`). Returning the model serializes every column, including `password`, `remember_token`, `two_factor_secret`, soft-delete columns, and any column added later
- [ ] **API Resources used for response shaping**: `extends JsonResource` with explicit `toArray()` listing only the public fields; conditional fields via `whenLoaded`/`when`; no implicit field exposure
- [ ] **Authentication on every protected route**: every route group touching user data is wrapped in `->middleware('auth:sanctum')` (token API), `->middleware('auth')` (session), or `->middleware('auth:api')` (Passport). Public routes must be in the explicit `withoutMiddleware` group or under a separate route file
- [ ] **Rate limiting on auth and write-heavy routes**: `Route::post('/login', ...)->middleware('throttle:auth')` (5/min by IP); `Route::post('/orders', ...)->middleware('throttle:api')` (60/min by user). Bare auth routes without throttling are brute-force surfaces
- [ ] **CSRF**: web routes are protected by default via `VerifyCsrfToken` middleware; SPA same-origin uses Sanctum's stateful CSRF flow (`/sanctum/csrf-cookie`). Token-based APIs (`Authorization: Bearer ...`) skip CSRF. Custom `validateCsrfTokens(except: [...])` exclusions must be limited to webhook endpoints with their own signature verification
- [ ] **No hardcoded secrets**: no `$key = 'sk_live_...'` literals in source; nothing in `.env.example` other than placeholders; `.env` not in version control
- [ ] **`Hash::make()` / `Hash::check()` for passwords**: never `md5($pw)`, `sha1($pw)`, `bcrypt($pw)` directly (`Hash::make` already wraps bcrypt with the right cost). Custom hashing flagged
- [ ] **`Auth::attempt()` / `auth()->attempt()` for login**: never compare raw password against `password` column manually
- [ ] **Migration PRs (any change in `database/migrations/`)**: see the Migration PRs subsection below

**Migration PRs (any change under `database/migrations/`):**

- [ ] Reversible migrations: every `up()` has a corresponding `down()` method. `up()` without `down()` is `[Blocker]` on a multi-instance deployment - rollback path is missing
- [ ] Two-phase deploys for column rename / drop (add new -> backfill -> cut over -> remove old). Single-migration drops on a deployed app cause errors during rolling deploy where old code reads the dropped column
- [ ] `NOT NULL` on existing columns goes through nullable -> backfill -> set-NOT-NULL three-step pattern on tables > 100K rows. MySQL/InnoDB online-DDL constraints determine whether `ALTER TABLE` blocks; flag `->change()` operations on tables > 1M rows for `pt-online-schema-change` review
- [ ] Indexes on large tables added via `ALGORITHM=INPLACE, LOCK=NONE` (MySQL 5.6+) - the Schema Builder default depends on column type. Flag indexes on hot tables that lack the explicit algorithm
- [ ] **Foreign keys** added with `->constrained()` and an explicit `onDelete` / `onUpdate` policy (`->cascadeOnDelete()` / `->restrictOnDelete()`); avoid the `set null` default unless the column is nullable
- [ ] Data migrations isolated from DDL migrations - one migration file changes schema, another seeds/backfills data
- [ ] Backfills via `chunkById(1000, function (Collection $rows) { ... })`, never `WHERE col IS NULL LIMIT N` (re-scans the same rows on every iteration)
- [ ] `php artisan migrate` is idempotent; on multi-replica deploys the deployment runs migrations once (e.g., `kubectl exec` from the deployer or a `migrate` init container with leader election), not on every replica's boot
- Use skill: `ops-backward-compatibility` to assess client/session/in-flight-request impact
- Use skill: `laravel-migration-safety` for canonical safe-migration patterns

**Concurrency / queue safety:**

- [ ] No mutable global state via static class properties - if shared state is needed, use `Cache::*` (Redis-backed for cross-replica) or a dedicated service with a lock (`Cache::lock('key')->block(5, fn() => ...)`); static mutable properties leak across requests in long-running PHP-FPM workers and crash under Octane
- [ ] Race-prone updates (counters, balance changes, inventory, seat reservations) use database-level locking inside a transaction (`DB::transaction(fn() => Order::lockForUpdate()->find($id))->...`) or atomic SQL (`Product::where('id', $id)->where('stock', '>=', $qty)->decrement('stock', $qty)` with a guard in the WHERE clause). In-process semaphores only protect a single replica
- [ ] `Cache::lock` for cross-replica critical sections - block with a short timeout, never indefinitely
- [ ] Queue connection is **not** `sync` in production - `sync` runs jobs inline in the request thread, defeats every queue guarantee, and turns dispatch failures into 500s
- [ ] Octane / Swoole / RoadRunner concerns: long-running workers can leak request-scoped state in singletons. Flag any new `app()->singleton(...)` whose closure captures request data, even when the project doesn't currently use Octane (it's a foot-gun for the future)
- [ ] PHPStan / Larastan level configured (level 5+ recommended); `composer phpstan` clean in CI
- [ ] Pint / PHP_CodeSniffer clean (`composer lint` / `vendor/bin/pint --test`)

Use skill: `laravel-eloquent-patterns` for canonical Eloquent correctness patterns.
Use skill: `laravel-api-patterns` for canonical Form Request / API Resource / controller patterns.
Use skill: `laravel-queue-patterns` for canonical job dispatch / retry / `afterCommit` patterns when the diff touches queues.
Use skill: `laravel-service-patterns` for service / action layering and event-driven patterns.

### Phase C - Laravel Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion.

**Laravel-specific architecture checks:**

- [ ] **Thin controllers**: controller action method bodies focus on validate (Form Request) -> delegate (service / action / handler) -> respond (API Resource). Methods > 30 lines orchestrating business logic, talking to multiple Eloquent models, or running multi-step transactions belong in a service or action class
- [ ] **Services / Actions for business logic**: shared business operations go in `app/Services/*Service.php` or single-purpose `app/Actions/*Action.php` classes resolved via the container; not duplicated across controllers, jobs, and console commands
- [ ] **No business logic in Eloquent models beyond domain attributes**: scopes, relationships, casts, accessors/mutators are fine; multi-aggregate orchestration belongs in services. A model with > 500 lines or methods that touch other aggregates is god-model
- [ ] **No Eloquent model returned from controller**: API Resources at the boundary (covered in Phase B); this guardrail catches the architecture-level pattern, not just the leak
- [ ] **DTOs for cross-layer transport when payloads are non-trivial**: prefer `readonly` DTO classes (PHP 8.2+ readonly classes) over passing `$request->validated()` arrays through deep call stacks. Trivial single-call data can stay as the validated array
- [ ] **Repository pattern only when justified**: Eloquent already abstracts the storage; repositories add value only when the team needs to swap the persistence layer or stub queries in unit tests via a non-Eloquent fake. A `OrderRepository` with one `Eloquent`-based implementation and no second use is over-abstraction (Phase D's territory; flag here for "did this PR introduce one")
- [ ] **Container bindings centralized**: `app()->bind(...)`, `app()->singleton(...)`, contextual bindings live in service providers (`app/Providers/AppServiceProvider`, `RouteServiceProvider`, `EventServiceProvider`); inline `app()->bind(...)` inside business code is a smell
- [ ] **Events for cross-domain side effects**: notifications, audit logs, search index updates fired via Events / Listeners (`event(new OrderPlaced($order))`) instead of calling unrelated services directly. Listeners that trigger expensive work implement `ShouldQueue`
- [ ] **Multi-tenant isolation**: tenant scoping enforced via global scopes (`Model::addGlobalScope(new TenantScope)`) AND repository / query layer (defense in depth), not at the controller layer alone. `withoutGlobalScope(TenantScope::class)` usages must have an explicit comment justifying the cross-tenant access (admin tooling, etc.)
- [ ] **Service Provider registration order**: providers registered in `bootstrap/providers.php` (Laravel 11+) or `config/app.php`; provider deferred via `defer = true` when the binding is rare; flag eager-loaded providers that resolve heavy services at boot
- [ ] **Middleware order in `bootstrap/app.php`**: explicit `prepend`/`append`/`replaceWith` for any custom middleware. Auth before rate limiting (so authenticated users aren't throttled by IP); CSRF before route binding for web routes
- [ ] **Resource controllers per resource**: `OrderController` covers index/show/store/update/destroy for the Order aggregate; one controller per aggregate root; thin actions
- [ ] **Custom exception handling via `Handler::reportable` / `renderable`** (Laravel 11+ via `bootstrap/app.php`'s `withExceptions(...)`): domain exceptions mapped to HTTP responses (`AuthorizationException` → 403, `ModelNotFoundException` → 404, custom domain exceptions → typed JSON error). Per-action `try / catch / return response()->json([...], 500)` scattered across controllers is inconsistent and leaks internal details

**Multi-service PRs (when change spans 2+ services or this Laravel app + a separate service):**

- API contract compatibility checked (OpenAPI diff via `darkaonline/l5-swagger` / `dedoc/scramble`, Pact, etc.)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for any changed inter-service contract

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.

**Laravel-specific AI smells:**

- [ ] **Pattern inflation**: `Manager` / `Helper` / `Service` class with one method that wraps a single Eloquent call; abstract base class hidden behind an interface with one implementer; a custom `Result` value object used inconsistently
- [ ] **Single-implementation interface**: `OrderRepositoryInterface` with one `EloquentOrderRepository` implementation, no Mockery mock, no second implementer - inline the concrete class via constructor injection. Interfaces for testability are fine when actually mocked; interfaces for abstraction's sake are smells
- [ ] **Repository over Eloquent for trivial queries**: wrapping `Order::find($id)` behind `OrderRepositoryInterface::findById($id)` adds nothing; Eloquent already abstracts storage. Reserve repositories for queries with multiple data sources or genuinely non-Eloquent stubs
- [ ] **AutoMapper-style mappers for trivial DTOs**: configuring an `OrderMapper::fromModel($order): OrderDto` when `OrderResource` does the same job - API Resources are Laravel's mapping primitive; do not parallel-build a second one
- [ ] **Service for trivial reads**: `OrderService::find($id)` that just returns `Order::findOrFail($id)` with no business logic - the indirection adds nothing. Services earn their keep on multi-step operations / cross-aggregate orchestration / external calls
- [ ] **Over-abstraction**: `BaseRepository<T>` with one consumer; premature interface for one consumer; factory classes for objects with one constructor path; generics-style abstractions in PHP via templates with no callers
- [ ] **Speculative configurability**: config keys with documented but unused values; environment-conditional code paths for environments that do not exist; feature flags with no off path
- [ ] **Redundant mapping layers**: `Eloquent -> InternalDto -> ServiceDto -> ApiResource` when one mapping would suffice
- [ ] **Test verbosity**: factory state setup > 30 lines for a single assertion; deeply nested `Mockery::mock` chains; `assertJson` matching the full payload when a few key fields would do
- [ ] **`Bus::dispatch` / queue for synchronous work**: pushing trivial in-memory operations through the queue for "decoupling"; the queue is for external I/O, slow work, or cross-aggregate side effects
- [ ] **`Event::dispatch` for direct method calls**: replacing `$searchIndex->update($order)` with `event(new OrderUpdated($order))` and a single listener that calls `$searchIndex->update($order)` is indirection without benefit unless multiple listeners exist
- [ ] **Excessive `string` building in hot paths**: `str()->of(...)->...` chains in tight loops; for high-frequency log lines use structured context arrays (`Log::info('placing order', ['order_id' => $id])`) instead of interpolated strings
- [ ] **Comment cruft**: PHPDoc restating method names; `// end of method` markers; `/** Returns the user. */` on `getUser()` with no extra info
- [ ] **`\Throwable` catch-all in business code**: `try { ... } catch (\Throwable $e) { return null; }` swallows every error; catch specific exception types and let the global handler handle the rest
- [ ] **`@phpstan-ignore` / `@phpstan-ignore-next-line` to silence analyzers**: each suppression must have a `// reason: ...` comment; bare suppressions on a file or block are findings

### Phase E - Laravel Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**Laravel-specific maintainability checks:**

- [ ] **Naming conventions (PSR-12 + Laravel)**: namespaces `PascalCase` (`App\Services\Orders`); classes `PascalCase`; methods / variables `camelCase`; constants `UPPER_SNAKE_CASE`; controllers suffixed `Controller`; Form Requests suffixed `Request`; jobs suffixed `Job` (or named imperatively, `ProcessPayment`); Policies suffixed `Policy`; events past-tense (`OrderPlaced`); listeners present-tense (`SendOrderConfirmation`); migration files with descriptive snake_case (`add_status_to_orders_table`)
- [ ] **Magic numbers / strings**: extracted to `const` or `config()`; backed enum cases for status / role / type columns instead of string literals (`OrderStatus::Pending->value`)
- [ ] **Hardcoded URLs / credentials**: in `config/services.php` referenced via `config('...')`, not inline in code (no `env()` outside config; covered in Phase B)
- [ ] **Method length**: methods > 30 lines reviewed for extraction; methods > 60 lines flagged unless they are clearly orchestrating handlers calling intention-revealing private methods
- [ ] **Duplicated query logic**: same `where(...)` chain in 3+ places extracted to a local query scope (`scopeActive(Builder $query)`) or a query class
- [ ] **`declare(strict_types=1)` at top of files**: enforced via Pint preset or PHPStan rule; missing declarations are findings
- [ ] **PHP 8.2+ feature usage**: `readonly` classes for DTOs / value objects; constructor property promotion (`public function __construct(public readonly int $orderId) {}`); first-class callable syntax (`$callable = $service->method(...)`); enum cases for state machines
- [ ] **Backed enums for status/type/role columns**: cast via `'status' => OrderStatus::class` in `casts()`; not raw strings
- [ ] **Logging hygiene**: surface obvious offenders as Core findings at `[Suggestion]` - `dd()` / `dump()` / `var_dump()` in production code path, `Log::info('foo', ['raw_password' => $pw])` PII leaks, log lines without context arrays. The observability subagent owns depth (channel config, structured-field schemas, log redaction, sampling); do not duplicate that audit here
- [ ] **`composer normalize` / Pint clean / PHPStan clean**: no manual formatting deviations; analyzers enforced in CI

Use skill: `backend-coding-standards` for cross-language naming and structure conventions.
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-laravel-review-observability` subagent owns the depth review).

### Step 5 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread (which continues running Phases A-E for Core). Subagents run concurrently with each other and with Core, not sequentially.

| Scope                | Subagents spawned                                                                                                                |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | 1 subagent running `task-laravel-review-perf`                                                                                    |
| Core + Security      | 1 subagent running `task-laravel-review-security`                                                                                |
| Core + Observability | 1 subagent running `task-laravel-review-observability`                                                                           |
| Full                 | 3 subagents running `task-laravel-review-perf`, `task-laravel-review-security`, `task-laravel-review-observability` in parallel  |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 3 (`base_ref`, `head_ref`) plus the already-read diff and commit log, so the subagent does not re-run `review-precondition-check` and does not re-issue `git diff`
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (PHP / Laravel) and detected ORM / auth / queue signal so the subagent skips its own `stack-detect`
- The spec slug if `--spec <slug>` was passed to the parent (so subagents trace findings to the same spec); pass nothing if no spec is active
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails or times out, continue with the remaining results. Note the missing scope in the synthesized output rather than blocking the whole review.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** The same issue may surface in multiple scopes (e.g., a per-iteration `Order::find($id)` inside a request loop can be flagged by both Core/Phase B and Perf). Keep one entry, citing all scopes that raised it.
- **Severity wins.** When the same finding has different labels across scopes, use the highest severity (`Blocker` > `High` > `Suggestion` > `Question`). Subagent reviews (perf / security / observability) use their own scales (`Critical` / `High` / `Medium` / `Low`); when merging, map subagent severities into this skill's labels: `Critical` → `Blocker`, `High` → `High`, `Medium` → `Suggestion`, `Low` → `Suggestion`. Do not introduce `Critical` / `Medium` / `Low` into the merged Findings list.
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by severity, not by scope.** Produce one merged Findings list.
- **Note missing scopes.** If any subagent failed, add `Scope incomplete: <scope> review did not complete` under Summary.
- **Merge Next Steps.** Combine Core Next Steps with each subagent's Next Steps into one prioritized list under `## Next Steps`. Preserve `[Implement]` / `[Delegate]` tags; deduplicate items mapping to the same fix; re-sort by severity (Blocker/Critical > High > Medium/Suggestion > Low).

## Feedback Labels

| Label        | Meaning                                     | Required |
| ------------ | ------------------------------------------- | -------- |
| [Blocker]    | Must fix before merge - correctness or risk | Yes      |
| [High]       | Should fix - significant impact or smell    | Strong   |
| [Suggestion] | Would improve - non-blocking                | No       |
| [Question]   | Need clarity from author                    | Clarify  |

No `[Nitpick]` or `[Praise]` labels.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** PHP <version> / Laravel <version>
**Auth:** Sanctum (token) | Sanctum (SPA) | Passport | session
**Queue:** redis (Horizon) | database | sync
**Tests:** Pest | PHPUnit
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the Laravel idiom: `$guarded = []` mass assignment, `Model::create($request->all())`, N+1 in Blade loop, `whereRaw($input)` SQL injection, missing `$this->authorize`, job dispatched inside transaction without `afterCommit`, job constructor takes Eloquent model, raw model returned from controller, `env()` outside config, queue connection `sync` in prod, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete Laravel change with code example]

### [High] file:line

- Issue:
- Impact:
- Fix:

### [Suggestion] file:line

- Improvement:

### [Question] file:line

- Question: [what is ambiguous in the change]
- Why it matters: [what the right next step depends on - author intent, business rule, deployment topology, etc.]

_Use [Question] when the change is genuinely ambiguous and the right action depends on author intent. Do NOT use it as a softer Blocker._

## Architecture Notes

_Summary commentary on systemic patterns. **Do not restate individual findings here.** If a pattern is severe enough to be a finding, keep it in Findings and reference it by file:line from these notes. Use this section for cross-cutting observations the per-file findings cannot carry on their own._

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

_Same rule as Architecture Notes - summary commentary, not duplicated findings._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Replace `$guarded = []` with explicit `$fillable` whitelist on Order model; audit other models for the same pattern"]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply Laravel conventions (PSR-12, Laravel docs, Pint preset, the framework's own naming), not generic backend conventions
- Provide actionable feedback with PHP / Laravel code examples
- Never comment on trivial formatting or style where Pint already applies - focus on substance
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate Laravel subagent rather than duplicating the check here


### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 before any other delegation (or accepted from parent dispatcher)
- [ ] Stack confirmed as PHP / Laravel (or accepted from parent dispatcher); auth strategy, queue driver, and test framework detected and recorded (Step 2)
- [ ] `review-precondition-check` ran (or its handle was received from a parent dispatcher); `base_ref` / `base_source` / `head_ref` / `current_branch` / `head_matches_current` captured. If user passed `--base`, `base_source: explicit-override` recorded (Step 3)
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all phases (and shared with subagents) - no re-issuing of git commands mid-review (Step 3)
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued (Step 3)
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (Step 3)
- [ ] Scope auto-escalation evaluated in Step 4; promotion (or `core-only` suppression) recorded in Summary along with the firing signals; migration-on-hot-table signal triggered +Perf when applicable (Step 4)
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`; promotion recorded in Summary (Step 4.5)
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Phase B - mass assignment (`$guarded = []`, `Model::create($request->all())`), Form Request usage, Form Request `authorize()` checked
- [ ] Phase B - `$this->authorize` / Policy on every protected action; ownership scoping (not just `auth:` middleware) checked
- [ ] Phase B - `whereRaw` / `DB::raw` / `orderByRaw` SQL injection surfaces checked; user-supplied `orderBy` allowlisted
- [ ] Phase B - N+1 via lazy loading in controllers and Blade checked; `Model::all()` on growable tables flagged
- [ ] Phase B - jobs dispatched after commit; jobs accept scalar IDs not models; `$tries` / `$backoff` / `$timeout` / `failed()` set
- [ ] Phase B - raw Eloquent model not returned from controller; API Resource present
- [ ] Phase B - `env()` outside config files flagged; queue connection not `sync` in prod; rate limiting on auth routes
- [ ] Phase B - migration safety (reversible, two-phase rename/drop, indexes online, FK constraints, chunked backfills) checked when migrations changed
- [ ] Phase C Laravel architecture checks applied: thin controllers, services / actions for business logic, no model in controller responses, repository / interface only when justified, multi-tenant isolation, middleware order
- [ ] Phase D AI-quality checks applied: pattern inflation, single-impl interfaces, repository-over-Eloquent for trivial reads, AutoMapper-style mappers, service-for-trivial-reads, redundant mapping layers, queue-for-sync-work, event-as-direct-call, `@phpstan-ignore` without reason
- [ ] Phase E Laravel maintainability checks applied: naming, magic strings / backed enums, method length, structured logging vs `dd()` / `dump()`, `declare(strict_types=1)`, Pint / PHPStan clean
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Every finding has a label, location (file:line), and actionable Laravel fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, Laravel-specific subagents (`task-laravel-review-perf`, `-security`, `-observability`) ran in parallel and received the pre-resolved diff/log handle plus stack detection (and `--spec` slug if active) (Step 5)
- [ ] Subagent findings merged into the single Output Format with deduplication and highest-severity-wins; raw subagent reports not appended (Step 6)
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>` (Step 6)
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reviewing without reading the full diff and commit log first
- Applying generic backend conventions when a Laravel idiom exists (say "wrap in a Form Request and validate via `rules()` + `authorize()`", not "validate input")
- Nitpicking style where Pint already applies; no `[Nitpick]` or `[Praise]` labels
- Providing vague feedback without a concrete Laravel fix ("this could be better")
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running perf / security / observability sub-workflows when user passed `core-only`
- Treating auto-escalation signals as advisory; the default is to promote and let the user opt out via `core-only`
- Duplicating perf / security / observability depth checks here when the dedicated Laravel subagent owns them - flag and delegate
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging into one severity-ordered Findings list
- Recommending `$guarded = []` for "convenience" - mass-assignment vector; always whitelist via `$fillable`
- Recommending `Model::create($request->all())` - bypasses validation discipline; use `Model::create($request->validated())` from a Form Request
- Recommending `whereRaw("col = '$input'")` for "dynamic" queries - SQL injection; use bindings or the query builder
- Recommending raw `Eloquent` model returned from controller actions - leaks columns; use API Resources
- Recommending `env()` outside `config/*.php` - returns null after `config:cache`; reads must go through `config()`
- Recommending `queue` driver `sync` outside local dev - defeats every queue guarantee
- Recommending passing Eloquent models into queue job constructors - use scalar IDs and re-fetch in `handle()`
- Recommending dispatching jobs inside `DB::transaction(...)` without `afterCommit()` - worker may pick up before commit
