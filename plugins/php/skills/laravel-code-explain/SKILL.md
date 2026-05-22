---
name: laravel-code-explain
description: PHP/Laravel code explanation signals: service container, middleware, Eloquent events/relationships, queue workers, Blade rendering, broadcasting.
metadata:
  category: backend
  tags: [explanation, code-understanding, php, laravel, eloquent]
user-invocable: false
---

# Laravel Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is PHP / Laravel.

## When to Use

- Workflow needs Laravel-specific signals: container resolution, middleware pipeline, Eloquent events/scopes/relationships, queues, Blade, broadcasting.
- Target is a Laravel project (`composer.json` with `laravel/framework`, `artisan`).

## Rules

- Identify the layer first (controller, model, job, listener, command, middleware, provider, form request); each has a distinct lifecycle.
- For controllers, list `__construct`-injected services and route middleware in execution order. Flag form requests - validation/authorization runs before the controller method.
- For models, surface casts, relationships, scopes, and events (`booted`, observers) - these alter behavior implicitly.
- Surface transaction boundaries (`DB::transaction`, `DB::beginTransaction`) - they change rollback semantics for events.
- For providers, distinguish `register` (bindings only) from `boot` (actions on resolved services).

## Patterns

### Request Lifecycle

```
public/index.php -> bootstrap/app.php -> Kernel (HTTP)
  -> Global middleware (TrustProxies, etc.)
  -> Route resolution
  -> Route middleware (auth, throttle, custom)
  -> Form Request validation (if typehinted)
  -> Controller method
  -> Response middleware (reversed)
```

Global middleware lives in `app/Http/Kernel.php` (Laravel 10) or `bootstrap/app.php` (11+). Route groups `web` (sessions, CSRF) and `api` (throttle, no session) are assigned per route file. `auth:sanctum` / `auth:web` select the guard.

### Service Container

`app(X::class)` / `app()->make(X::class)` resolves. `bind` = new instance per resolve; `singleton` = one per request; `scoped` = one per request scope (9+). Auto-wiring resolves typehinted constructor params; concrete classes need no binding. Providers (`app/Providers/`) run `register()` across all providers first, then all `boot()`.

### Eloquent Models

- `find` returns null; `findOrFail` throws `ModelNotFoundException` (auto-404).
- `$casts` coerces on access (`'array'`, `'boolean'`, `'datetime'` -> `Carbon`).
- Events (`creating`, `created`, `updating`, `updated`, `saving`, `saved`, `deleting`, `deleted`, `retrieved`) fire synchronously inside the transaction. Observers consolidate handlers; register in a provider's `boot()`.
- `$fillable` allowlists mass assignment; `$guarded = []` opens everything (dangerous). `$hidden` / `$visible` control JSON serialization.

### Eloquent Relationships and N+1

Relationship methods return `belongsTo` / `hasMany` / `hasOne` / `belongsToMany` / `morphTo`. Lazy access (`$user->posts`) issues a query; eager (`User::with('posts')`) issues one `WHERE id IN (...)` per relationship; nest with dots (`with('posts.comments')`); `loadMissing` adds eager loads post-fetch. `Model::preventLazyLoading()` in `AppServiceProvider::boot()` (8.43+) throws on lazy load outside production - check whether it's enabled.

### Eloquent Scopes

- Local: `scopeActive($query)` -> `Model::active()`.
- Global: implements `Scope`, applied to every query unless `withoutGlobalScope`.
- `SoftDeletes` adds a global scope filtering `deleted_at IS NULL`; `withTrashed()` bypasses.

### Queues and Jobs

- `Job::dispatch($args)` enqueues via `config/queue.php` (sync, database, redis, sqs, beanstalkd). `dispatchSync` runs inline (replaces deprecated `dispatchNow`).
- Args serialized; models use `SerializesModels` and are re-fetched in `handle`.
- `$tries`, `$backoff`, retry-after, `failed()` control retries. Listeners implementing `ShouldQueue` are queued.
- `QUEUE_CONNECTION=sync` (common in tests) runs jobs immediately and can mask async assumptions.

### Validation via Form Requests

`php artisan make:request Foo` generates a class with `authorize()` and `rules()`. Typehinting `Foo $request` in the controller runs validation **before** the method body; `authorize()` returning false produces 403 before validation. Rules accept inline strings, arrays, or `Rule::*` objects. `$request->validated()` returns the validated subset.

### Blade Templating

Inheritance: `@extends`, `@section`, `@yield`. Loops: `@foreach`, `@forelse`. Composition: `@push` / `@stack`. `{{ $var }}` escapes HTML; `{!! $var !!}` is raw (XSS risk if input is unsanitized). Components (7+): `<x-alert />` -> `app/View/Components/Alert.php` + `resources/views/components/alert.blade.php`.

### Broadcasting and Events

Events in `app/Events/` implement `ShouldBroadcast` to publish to a channel. Listeners in `app/Listeners/` map via `EventServiceProvider`. Drivers (pusher, redis, log, null) live in `config/broadcasting.php`. Frontend: `Echo.private('orders.{userId}').listen('OrderShipped', ...)`.

### Database and Transactions

`DB::transaction(fn () => ...)` rolls back on exception, commits on return; manual `beginTransaction` / `commit` / `rollBack` requires explicit try/catch. Nested transactions use savepoints; the outermost commit decides persistence. Model events fire inside the transaction - expensive work in `creating`/`saving` stretches it. `DB::raw` / `DB::statement` bypass the query builder; bind user input via `?`.

### Configuration and Environment

`env()` is valid only inside `config/*.php`; runtime code uses `config('app.name')`. `php artisan config:cache` caches configs - `env()` outside config files **returns null** afterward (common bug). `APP_ENV` selects `.env.local`, `.env.testing`, etc.

### Tinker, Artisan, Auth

- `php artisan tinker`: REPL with full app boot. Custom commands in `app/Console/Commands/`; `$signature` defines invocation.
- Scheduler (`app/Console/Kernel.php::schedule`) needs a cron entry running `php artisan schedule:run` every minute.
- Guards (`config/auth.php`) select auth backend (session, sanctum, JWT); default `web` uses sessions. Sanctum supports SPA cookie+CSRF or `Authorization: Bearer` - different middleware paths.
- Policies (`app/Policies/`) authorize model actions: `authorize('update', $post)`. Gates (in `AuthServiceProvider`) handle non-model authorization.

### Common Bugs to Surface

- `env()` outside config returning null after `config:cache`.
- N+1 from relationship access in views/serializers.
- `$guarded = []` allowing arbitrary mass-assigned fields.
- Query-builder `update()` bypassing model events (vs instance `save`/`update`).
- `QUEUE_CONNECTION=sync` masking chain/batch assumptions in tests.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- Layer (controller / model / job / listener / form request / provider)
- Controllers: middleware in execution order, including form request validation/authorization
- Models: relationships, casts, observers, global scopes
- Jobs: queue connection, retry/backoff config

**Into "Non-Obvious Behavior":**

- Form request validation/authorize running before controller
- Model events fired inside transaction
- Soft delete global scope filtering queries
- Query-builder `update()` bypassing model events
- `env()` outside config returning null after cache
- N+1 patterns from view loops or serializer relationship access
- `dispatchSync` vs `dispatch` semantics in tests

**Into "Key Invariants":**

- Container auto-wires typehinted constructor params
- All providers' `register()` runs before any `boot()`
- Model events fire synchronously inside the transaction
- Job arguments must be serializable; models re-fetched via `SerializesModels`

**Into "Change Impact Preview":**

- Adding a model event listener: fires on every save/create (tinker, queues, seeders included)
- Renaming route middleware: cascades to every action on that controller
- Adding a global scope: filters every query for that model unless `withoutGlobalScope`
- Changing `$casts`: existing data interpretation and JSON serialization shift
- Removing `$fillable`: mass assignment fails silently for those fields

## Avoid

- Conflating instance `update()` with query-builder `update()`
- Skipping `auth` / `throttle` middleware when describing route behavior
- Recommending `env()` in runtime code paths
- Confusing `dispatchNow` / `dispatchSync` / `dispatch` semantics
- Glossing over provider `register` vs `boot` ordering
- Listing relationships without naming lazy/eager state
