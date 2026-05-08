---
name: laravel-code-explain
description: PHP / Laravel framework signals for code explanation - service container resolution, request lifecycle through middleware, Eloquent model events and relationships, queue workers, Blade view rendering, and broadcasting. Used by task-code-explain to explain Laravel code with stack-aware gotchas.
metadata:
  category: backend
  tags: [explanation, code-understanding, php, laravel, eloquent]
user-invocable: false
---

# Laravel Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is PHP / Laravel.

## When to Use

- A workflow needs Laravel-specific signals: service container resolution and providers, middleware pipeline, Eloquent events/relationships/scopes, queue workers, Blade rendering, broadcasting/Echo.
- Target is in a Laravel project (`composer.json` with `laravel/framework`, `artisan`).

## Rules

- Identify the layer first: controller, model, job, listener, command, middleware, service provider, or form request. Each has different lifecycle.
- For controllers, list `__construct`-injected services and route middleware in execution order. Form requests run before the controller method - flag if validation/authorization happens there.
- For models, identify casts (`$casts`), relationships, scopes, and events (`booted`, observers) - these alter behavior implicitly.
- Surface Eloquent transaction scope - `DB::transaction()` and `DB::beginTransaction()` boundaries change rollback semantics for events.
- For service providers, identify the registration phase (`register` for bindings only, `boot` for actions on resolved services).

## Patterns

### Request Lifecycle

```
public/index.php -> bootstrap/app.php -> Kernel (HTTP)
  -> Global middleware (TrustProxies, etc.)
  -> Route resolution
  -> Route middleware (auth, throttle, custom)
  -> Form Request validation (if typehinted)
  -> Controller method
  -> Response middleware (response stack reversed)
```

- Global middleware: `app/Http/Kernel.php` `$middleware` (Laravel 10) or `bootstrap/app.php` (Laravel 11+).
- Route middleware groups: `web` (sessions, CSRF), `api` (throttle, no session) - assigned by route file.
- `auth:sanctum`, `auth:web` - guard-specific authentication.

### Service Container

- `app(MyClass::class)` resolves from container; `app()->make(...)` is equivalent.
- `app()->bind(Interface::class, Concrete::class)` - new instance every resolve.
- `app()->singleton(Interface::class, Concrete::class)` - one instance for the request.
- `app()->scoped(Interface::class, Concrete::class)` - one instance per request (Laravel 9+).
- Auto-wiring: typehinted constructor parameters are resolved automatically; concrete classes work without explicit binding.
- Service providers (`app/Providers/`) register bindings in `register()` and run boot logic in `boot()`. Order: all `register()` then all `boot()`.

### Eloquent Models

- `Model::find($id)` returns null if not found; `Model::findOrFail($id)` throws `ModelNotFoundException` (auto-mapped to 404).
- `$casts = ['data' => 'array', 'is_active' => 'boolean']`: type coercion on attribute access. `'datetime'` cast returns `Carbon` instances.
- Model events: `creating`, `created`, `updating`, `updated`, `saving`, `saved`, `deleting`, `deleted`, `retrieved`. Fire synchronously inside the transaction.
- Observers (`app/Observers/`) consolidate event handlers - register in a service provider's `boot()`.
- Mass assignment: `$fillable` allowlist or `$guarded = []` (everything fillable - dangerous).
- `$hidden` / `$visible` controls what is serialized to JSON.

### Eloquent Relationships and N+1

- Relationships defined as methods returning `belongsTo`, `hasMany`, `hasOne`, `belongsToMany`, `morphTo`, etc.
- Lazy loading: accessing `$user->posts` issues a query.
- Eager loading: `User::with('posts')->get()` - one query per relationship via `WHERE id IN (...)`.
- Nested: `User::with('posts.comments')->get()`.
- `loadMissing` to add eager loads after the fact: `$users->loadMissing('posts')`.
- N+1 detector: `Model::preventLazyLoading()` in `AppServiceProvider::boot()` (Laravel 8.43+) - throws on lazy load in non-production. Check for it.

### Eloquent Scopes

- Local scope: method `scopeActive($query) { return $query->where('active', true); }` - called as `Model::active()`.
- Global scope: implements `Scope`; applied to every query unless `withoutGlobalScope`.
- Soft deletes (`use SoftDeletes`): adds a global scope filtering `deleted_at IS NULL`. `withTrashed()` to bypass.

### Queues and Jobs

- `Job::dispatch($args)` enqueues; backend configured in `config/queue.php` (sync, database, redis, sqs, beanstalkd).
- `dispatch(...)` (helper) enqueues; `dispatchNow` runs synchronously (deprecated in favor of `dispatchSync`).
- Job arguments are serialized; Eloquent models use `SerializesModels` trait - re-fetched on handle.
- Tries (`$tries`), backoff (`$backoff`), retry-after, and `failed()` method on the job.
- Listeners with `ShouldQueue` interface: queued event listeners.
- Sync queue in `.env` (`QUEUE_CONNECTION=sync`) runs jobs immediately - common in tests.

### Validation via Form Requests

- `php artisan make:request StoreUserRequest` generates a class with `authorize()` and `rules()`.
- Typehinting in controller: `public function store(StoreUserRequest $request)` - validation runs **before** the controller method.
- `authorize()` returning false produces 403 before validation.
- Validation rules can be inline strings, arrays, or `Rule::*` objects.
- After validation, `$request->validated()` returns the validated data subset.

### Blade Templating (when present)

- `@extends('layouts.app')`, `@section('content')`, `@yield('content')` for inheritance.
- `{{ $var }}` HTML-escapes; `{!! $var !!}` outputs raw - XSS risk if not pre-sanitized.
- Components (Laravel 7+): `<x-alert />` resolves to `app/View/Components/Alert.php` + `resources/views/components/alert.blade.php`.
- Loops: `@foreach`, `@forelse`. `@push` and `@stack` for view-fragment composition.

### Broadcasting and Events

- Events (`app/Events/`) implement `ShouldBroadcast` to broadcast to a Pusher/Redis/Ably channel.
- Listeners (`app/Listeners/`) handle events; mapped in `EventServiceProvider`.
- Broadcasting drivers: pusher, redis, log, null - configured in `config/broadcasting.php`.
- Frontend Echo subscribes via `Echo.private('orders.{userId}').listen('OrderShipped', ...)`.

### Database and Transactions

- `DB::transaction(fn () => ...)` - automatic rollback on exception, commit on return.
- Manual: `DB::beginTransaction()` / `DB::commit()` / `DB::rollBack()`. Need explicit try/catch.
- Nested transactions use savepoints; outer transaction's commit decides actual persistence.
- Model events fire inside the transaction; `creating`/`saving` running expensive work stretches the transaction.
- `DB::raw(...)` and `DB::statement(...)` for raw SQL - bypass query builder; user input must be parameterized via `?` and bindings.

### Configuration and Environment

- `.env` -> `config/*.php` is one-way: env vars are read by `env()` only inside config files. Runtime code should use `config('app.name')` not `env('APP_NAME')`.
- `php artisan config:cache` caches configs - `env()` calls outside config files **return null** after cache. Common bug.
- Environment-specific: `.env.local`, `.env.testing`. `APP_ENV` selects.

### Tinker and Artisan

- `php artisan tinker` REPL with full app boot.
- Custom commands in `app/Console/Commands/`; `$signature` defines invocation.
- Scheduler (`app/Console/Kernel.php` `schedule()`) - cron entry calls `php artisan schedule:run` every minute.

### Authentication and Authorization

- Guards (`config/auth.php`) define how users are authenticated (session, sanctum, JWT plugins). Default web guard uses sessions.
- Sanctum: SPA via cookie + CSRF, or token via `Authorization: Bearer`. Different middleware paths.
- Policies (`app/Policies/`) authorize actions on models; `authorize('update', $post)` in controller.
- Gates (`AuthServiceProvider`) for non-model authorization.

### Common Bugs to Surface

- `env()` outside config files returning null after `config:cache`.
- N+1 queries from relationship access in views/serializers.
- Mass assignment with `$guarded = []` allowing arbitrary fields.
- `dispatch(...)` in tests not running because queue connection is sync but the job uses chains/batches expecting an actual queue.
- Model events not firing on `update()` query builder method (vs `save()`/`update()` on instance).
- `QUEUE_CONNECTION=sync` in test env failing async assumptions.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- Layer (controller / model / job / listener / form request / provider)
- For controllers: middleware in execution order, including form request validation/authorization
- For models: relationships, casts, observers, global scopes
- For jobs: queue connection, retry/backoff config

**Into "Non-Obvious Behavior":**

- Form request validation/authorize running before controller
- Model events fired inside transaction
- Soft delete global scope filtering queries
- `update()` on query builder bypassing model events
- `env()` outside config returning null after cache
- N+1 patterns from view loops or serializer relationship access
- `dispatchSync` vs `dispatch` semantics in tests

**Into "Key Invariants":**

- Service container auto-wires typehinted constructor params
- Service providers' `register()` runs first, then `boot()`
- Model events fire synchronously inside the transaction
- Job arguments must be serializable; models re-fetched via `SerializesModels`

**Into "Change Impact Preview":**

- Adding a model event listener: fires on every save/create across the codebase, including from tinker, queues, seeders
- Renaming a route's middleware: cascades to every action on that controller
- Adding a global scope: filters every query for that model unless `withoutGlobalScope`
- Changing `$casts`: existing data interpretation changes; serialization to JSON differs
- Removing `$fillable`: mass assignment fails silently for those fields

## Avoid

- Treating Eloquent's `update()` instance method and `update()` query method as equivalent
- Skipping `auth` and `throttle` middleware when describing route behavior
- Recommending `env()` in runtime code paths
- Confusing `dispatchNow`/`dispatchSync`/`dispatch` semantics
- Glossing over service provider `register` vs `boot` ordering
- Listing every relationship without naming the lazy/eager state
