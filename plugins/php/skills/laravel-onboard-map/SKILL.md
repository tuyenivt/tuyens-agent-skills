---
name: laravel-onboard-map
description: Laravel onboarding signals: composer.json, env config, Eloquent migrations, queue backend, broadcasting, Vite/Mix frontend.
metadata:
  category: backend
  tags: [onboarding, codebase-map, php, laravel, composer]
user-invocable: false
---

# Laravel Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is PHP / Laravel.

## When to Use

- Workflow needs Laravel-specific orientation: composer deps, framework version, env layout, queue backend, broadcasting, frontend stack.
- Project has `composer.json` with `laravel/framework`, `artisan`.

## Rules

- Identify Laravel version (`composer.json`, resolved in `composer.lock`); 10 LTS vs 11/12 differ in bootstrap (11 introduced consolidated `bootstrap/app.php`).
- Identify PHP version (`composer.json` `require.php`); 8.2+ standard.
- Identify queue backend (`config/queue.php` default + `.env` `QUEUE_CONNECTION`): `sync` hides async bugs; real backends are `database`, `redis`, `sqs`, `beanstalkd`.
- Identify auth: Breeze, Jetstream, Sanctum (SPA/API), Passport (OAuth2), Fortify (headless).
- Identify frontend: Inertia + Vue/React, Livewire, Blade-only, or API-only.

## Patterns

### Build Inventory

| File | What it tells you |
| ---- | ----------------- |
| `composer.json` / `composer.lock` | PHP deps; Laravel version range and locked versions |
| `package.json` + `vite.config.js` / `webpack.mix.js` | Frontend assets; Vite (9.19+) vs legacy Mix |
| `phpunit.xml` | PHPUnit + test DB settings |
| `phpstan.neon` / `psalm.xml` / `pint.json` | Static analysis and formatter config |

### Bootstrap Path

1. PHP toolchain: `composer.json` `require.php` matches `php -v` (`phpenv`/Homebrew).
2. `composer install`; `npm install` (or pnpm/yarn).
3. `cp .env.example .env && php artisan key:generate`; edit DB/queue/mail.
4. `php artisan migrate` (or `migrate:fresh --seed`).
5. Local services: `compose.yml` (Sail provides one) for MySQL/Postgres/Redis/MailPit.
6. Run: `php artisan serve` (backend), `npm run dev` (Vite), `php artisan queue:work` (worker), `php artisan schedule:work` (dev scheduler).
7. Verify: `http://127.0.0.1:8000`; `/up` (Laravel 11+) or custom `/health`.

### Key File Inventory

Bootstrap differs by version:

- **Laravel 11/12:** `bootstrap/app.php` consolidates routes, middleware, exception handling. `routes/{web,api,console}.php`; `api.php` enabled explicitly via `withRouting`.
- **Laravel 10-:** `app/Http/Kernel.php` (middleware), `app/Console/Kernel.php` (commands + scheduler), `app/Exceptions/Handler.php`.

All versions:

| Location | Purpose |
| -------- | ------- |
| `app/Models/`, `app/Http/Controllers/`, `app/Http/Requests/`, `app/Http/Middleware/` | Core HTTP layer; Requests handle validation + authorization |
| `app/Providers/`, `app/Jobs/`, `app/Events/`, `app/Listeners/`, `app/Policies/`, `app/Console/Commands/` | DI bindings, queueables, events (broadcastable via `ShouldBroadcast`), authz, artisan |
| `database/{migrations,seeders,factories}/` | Schema + test data |
| `config/` | Arrays accessed via `config('file.key')` |
| `resources/views/`, `resources/js/`, `resources/css/` | Blade + frontend assets |
| `tests/Feature/` + `tests/Unit/` | PHPUnit/Pest tests |

### Package Layout Convention

Check which the project uses before describing architecture:

- **Layer-package** (Laravel default, dominant): `app/Http/Controllers/`, `app/Services/`, `app/Models/`, `app/Jobs/`, `app/Policies/` group by stereotype. Matches `php artisan make:*` defaults.
- **Feature-package / DDD** (less common, larger codebases): `app/Domain/Orders/{Controller,Service,Repository,Action,Job}.php` keeps a feature in one directory; cross-feature imports go through public interfaces. Often paired with custom `composer.json` PSR-4 entries.
- **Mixed** (growing codebases): `app/Domain/Orders/` next to legacy `app/Services/OrderService.php` signals mid-migration: new code goes feature-package, legacy stays until refactor. Confirm direction; `make:*` defaults to layer-package locations and needs manual relocation.

### Conventions

- Eloquent over query builder (latter for complex queries).
- Form requests typehinted into controllers trigger validation.
- Service providers: bindings in `register()`, boot logic in `boot()`.
- Policies + gates for authz (`authorize('update', $post)`).
- `Route::resource(...)` for RESTful CRUD; API resources (`app/Http/Resources/`) shape responses.
- Tests: Pest or PHPUnit; `RefreshDatabase` trait per test.
- Pint formatter; Larastan/PHPStan/Psalm static analysis.

### Risk Hotspots Specific to Laravel

- Mass assignment, raw input (`$guarded = []`, `Model::create($request->all())`, `whereRaw($input)`): see `laravel-security-patterns`.
- N+1 in Blade/Resources/loops, `Model::all()` on growable tables: see `laravel-eloquent-patterns`.
- Jobs dispatched inside `DB::transaction` without `->afterCommit()`, jobs taking Eloquent models in constructors: see `laravel-queue-patterns`.
- Migration safety on hot tables (rename / drop / NOT NULL): see `laravel-migration-safety`.
- `env()` outside config files returns null after `config:cache`: see `laravel-security-patterns`.
- Eloquent quirks: soft-delete global scope, query-builder `update()` skipping events, observers firing inside transactions, middleware-alias drift between 10 and 11+.

### First-PR Safe Zones

- New route + controller method following existing pattern.
- New model + migration + factory + feature test.
- New Form Request; new artisan command in `app/Console/Commands/`.

Riskier: service providers (boot-time), middleware pipeline (broad reach), auth/Sanctum config, production migrations with FK changes.

### Ecosystem Currency

- Laravel 11/12 standard; 10 LTS for legacy. PHP 8.3/8.4 latest, 8.2 minimum.
- Pest 2/3 increasingly common; Inertia for SPA-like; Livewire 3 for PHP-driven reactivity; Pint default.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Laravel version, PHP version, queue backend, broadcasting driver, auth approach, frontend stack (Inertia/Livewire/Blade), test framework.

**Local Bootstrap:** `composer install`, `npm install`, `.env` setup + `key:generate`, `php artisan migrate`, `php artisan serve`, `npm run dev`, queue worker if needed.

**Architecture Map:** Laravel 11+ vs 10 bootstrap layout, models/controllers/jobs file counts, service providers, route file split.

**Conventions:** form requests, API resources, Eloquent vs query builder, test framework (Pest vs PHPUnit), service provider patterns.

**Risk Hotspots:** `env()` outside config, mass assignment, N+1 in views, sync queue masking, migration prod policy.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating Laravel 10 patterns as current for 11+ projects (bootstrap differs).
- Listing every composer package - focus on architectural ones.
- Recommending `env()` in runtime code.
- Skipping queue backend identification - sync vs real backend changes everything.
- Confusing query builder `update()` with model `update()` semantics.
