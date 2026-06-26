---
name: laravel-code-explain
description: PHP/Laravel code explanation signals: service container, middleware, Eloquent events/relationships, queue workers, Blade rendering, broadcasting.
metadata:
  category: backend
  tags: [explanation, code-understanding, php, laravel, eloquent]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is PHP / Laravel.

## When to Use

- Workflow needs Laravel-specific signals: container resolution, middleware pipeline, Eloquent events/scopes/relationships, queues, Blade, broadcasting.
- Target is a Laravel project (`composer.json` with `laravel/framework`, `artisan`).

## Rules

- Identify the layer first (controller, model, job, listener, command, middleware, provider, form request); each has a distinct lifecycle.
- For controllers, list `__construct`-injected services and route middleware in execution order. Flag form requests - their `authorize()` + `rules()` run before the controller method (403 before 422).
- For models, surface casts, relationships, scopes, and events (`booted`, observers) - these alter behavior implicitly.
- Surface transaction boundaries (`DB::transaction`, `DB::beginTransaction`) - model events fire inside the transaction.
- For providers, distinguish `register` (bindings only) from `boot` (actions on resolved services).

## Patterns

### Request Lifecycle

`public/index.php` -> HTTP Kernel -> global middleware -> route resolution -> route middleware (`auth`, `throttle`, custom) -> Form Request `authorize()` + `rules()` -> controller method -> response middleware (reversed).

Global middleware lives in `app/Http/Kernel.php` (Laravel 10) or `bootstrap/app.php` (11+). Route groups `web` (sessions, CSRF) and `api` (throttle, no session) assigned per route file. `auth:sanctum` / `auth:web` select the guard.

### Service Container

`app(X::class)` / `app()->make(X::class)` resolves. `bind` = new instance per resolve; `singleton` = one per request; `scoped` = one per request scope (L11+). Auto-wiring resolves typehinted constructor params; concrete classes need no binding. All providers' `register()` runs first, then all `boot()`.

### Eloquent Models

- `find` returns null; `findOrFail` throws `ModelNotFoundException` (auto-404).
- `$casts` coerces on access (`'array'`, `'boolean'`, `'datetime'` -> `Carbon`, enum class -> backed enum). Class-based casts (`AsCollection`, `AsArrayObject`, `AsEnumCollection`) return objects, not arrays - switching from `'array'` changes the accessor's return type and breaks array-function callers.
- Events (`creating`, `created`, `updating`, `updated`, `saving`, `saved`, `deleting`, `deleted`, `retrieved`) fire synchronously inside the transaction - non-queued listener side effects are NOT rolled back on failure unless the event/listener sets `$afterCommit` (or `DB::afterCommit()`). Observers consolidate handlers; register in a provider's `boot()`.
- `$fillable` allowlists mass assignment; `$guarded = []` opens everything. `$hidden` / `$visible` control JSON serialization.

### Relationships and N+1

Methods return `belongsTo` / `hasMany` / `hasOne` / `belongsToMany` / `morphTo`. Lazy access (`$user->posts`) issues a query; eager (`User::with('posts')`) issues one `WHERE id IN (...)`; nest with dots (`with('posts.comments')`); `loadMissing` adds eager loads post-fetch. `Model::preventLazyLoading()` in `AppServiceProvider::boot` throws on lazy load outside production - check whether it's enabled.

### Scopes

- Local: `scopeActive($query)` -> `Model::active()`.
- Global: implements `Scope`, applied to every query unless `withoutGlobalScope`.
- `SoftDeletes` adds a global scope filtering `deleted_at IS NULL`; `withTrashed()` bypasses.

### Queues and Jobs

- `Job::dispatch($args)` enqueues via `config/queue.php` (sync, database, redis, sqs, beanstalkd). `dispatchSync` runs inline (replaces deprecated `dispatchNow`).
- Args serialized; models use `SerializesModels` and are re-fetched in `handle`.
- `$tries`, `$backoff`, `failed()` control retries. Listeners implementing `ShouldQueue` are queued.
- `QUEUE_CONNECTION=sync` (common in tests) runs jobs immediately and can mask async assumptions.

### Validation via Form Requests

Typehinting `Foo $request` in the controller runs validation **before** the method body. `authorize()` returning false produces 403 before validation. `$request->validated()` returns the validated subset.

### Blade

`@extends`, `@section`, `@yield`; `@foreach`, `@forelse`; `@push` / `@stack`. `{{ $var }}` escapes HTML; `{!! $var !!}` is raw (XSS risk on user input). Components: `<x-alert />` -> `app/View/Components/Alert.php` + `resources/views/components/alert.blade.php`.

### Broadcasting and Events

Events in `app/Events/` implement `ShouldBroadcast` to publish to a channel. Listeners in `app/Listeners/` map via `EventServiceProvider`. Drivers (pusher, redis, log, null) in `config/broadcasting.php`. Frontend: `Echo.private('orders.{userId}').listen('OrderShipped', ...)`.

### Database and Transactions

`DB::transaction(fn () => ...)` rolls back on exception, commits on return; manual `beginTransaction` / `commit` / `rollBack` requires explicit try/catch. Nested transactions use savepoints; the outermost commit decides persistence. `DB::raw` / `DB::statement` bypass the query builder; bind user input via `?`.

### Configuration and Environment

`env()` is valid only inside `config/*.php`; runtime code uses `config('app.name')`. `php artisan config:cache` caches configs - `env()` outside config files **returns null** afterward.

### Auth and Authorization

Guards (`config/auth.php`) select backend (session, sanctum, JWT); default `web` uses sessions. Sanctum supports SPA cookie+CSRF or `Authorization: Bearer` - different middleware paths. Policies (`app/Policies/`) authorize model actions (`authorize('update', $post)`); Gates (in `AuthServiceProvider`) handle non-model authorization.

## Output Format

Inject signals into `task-code-explain` sections:

**Flow Context:**
- Layer (controller / model / job / listener / form request / provider)
- Controllers: middleware in execution order + form request validation/authorize
- Models: relationships, casts, observers, global scopes
- Jobs: queue connection, retry/backoff config

**Non-Obvious Behavior:**
- Form request `authorize()` + `rules()` run before the controller method
- Model events fire synchronously inside the surrounding transaction
- `SoftDeletes` global scope filters every query unless `withTrashed`
- Query-builder `update()` bypasses model events (vs instance `save`/`update`)
- `env()` outside config returns null after `config:cache`
- N+1 from view loops or Resource relationship access
- `dispatchSync` vs `dispatch` semantics in tests

**Key Invariants:**
- Container auto-wires typehinted constructor params
- All providers' `register()` runs before any `boot()`
- Job arguments must be serializable; models re-fetched via `SerializesModels`

**Change Impact Preview:**
- Adding a model event listener: fires on every save (tinker, queues, seeders included)
- Renaming route middleware: cascades to every action on that controller
- Adding a global scope: filters every query for that model unless `withoutGlobalScope`
- Changing `$casts`: existing data interpretation and JSON serialization shift

## Avoid

- Conflating instance `update()` with query-builder `update()`
- Skipping `auth` / `throttle` middleware when describing route behavior
- Recommending `env()` in runtime code
- Confusing `dispatchNow` / `dispatchSync` / `dispatch` semantics
- Glossing over provider `register` vs `boot` ordering
- Listing relationships without naming lazy/eager state
