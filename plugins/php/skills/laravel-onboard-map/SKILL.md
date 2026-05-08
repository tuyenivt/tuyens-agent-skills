---
name: laravel-onboard-map
description: PHP / Laravel project onboarding signals - composer.json, Laravel version, environment config, Eloquent + migrations, queue backend, broadcasting, and frontend stack (Vite/Mix). Used by task-onboard to map a Laravel codebase for a new engineer.
metadata:
  category: backend
  tags: [onboarding, codebase-map, php, laravel, composer]
user-invocable: false
---

# Laravel Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is PHP / Laravel.

## When to Use

- A workflow needs Laravel-specific orientation: composer deps, framework version, env config layout, queue backend, broadcasting, frontend stack.
- Project has `composer.json` with `laravel/framework`, `artisan`.

## Rules

- Identify Laravel version (`composer.json` first, `composer.lock` for resolved); 10 LTS, 11 / 12 are current. Each major has different bootstrap (Laravel 11 introduced consolidated `bootstrap/app.php`).
- Identify PHP version (`composer.json` `require.php`); PHP 8.2+ standard.
- Identify queue backend (`config/queue.php` default + `.env` `QUEUE_CONNECTION`); `sync` (no real queue), `database`, `redis`, `sqs`, `beanstalkd`. Sync in tests/dev hides async bugs.
- Identify auth approach: Laravel Breeze (basic), Jetstream (with teams/2FA), Sanctum (SPA/API), Passport (OAuth2), Fortify (headless).
- Identify frontend: Inertia.js + Vue/React, Livewire, Blade-only, or API-only (Sanctum).

## Patterns

### Build Inventory

| File                | What it tells you                                                                |
| ------------------- | -------------------------------------------------------------------------------- |
| `composer.json`     | PHP deps; Laravel version range                                                  |
| `composer.lock`     | Locked versions                                                                  |
| `package.json`      | NPM deps for frontend assets                                                      |
| `vite.config.js`    | Vite config (Laravel 9.19+ default)                                              |
| `webpack.mix.js`    | Laravel Mix config (legacy, pre-Vite)                                             |
| `phpunit.xml`       | PHPUnit config; test database settings                                            |
| `phpstan.neon` / `psalm.xml` | Static analysis config                                                  |
| `pint.json`         | Laravel Pint (formatter) config                                                  |

### Bootstrap Path

1. PHP toolchain: confirm `composer.json` `require.php` matches local `php -v`. Use `phpenv`/Homebrew.
2. Install: `composer install`.
3. Frontend: `npm install` (or `pnpm`/`yarn`).
4. Environment: `cp .env.example .env && php artisan key:generate`. Edit `.env` for DB, queue, mail, etc.
5. Database: `php artisan migrate` (or `migrate:fresh --seed` for full reset with seeders).
6. Local services: `compose.yml` (Laravel Sail provides one) for MySQL/Postgres/Redis/MailPit.
7. Run:
   - **Backend:** `php artisan serve` (dev server) or `php-fpm` + nginx for production parity.
   - **Frontend:** `npm run dev` (Vite hot reload).
   - **Queue worker:** `php artisan queue:work` (or `queue:listen` for code-reload in dev).
   - **Scheduler (if cron-like tasks):** `php artisan schedule:work` (dev).
8. Verify: `http://127.0.0.1:8000`; `/up` (Laravel 11+) or custom `/health`.

### Key File Inventory

**Laravel 11 / 12 (consolidated bootstrap):**

| Location                          | Purpose                                                                                  |
| --------------------------------- | ---------------------------------------------------------------------------------------- |
| `bootstrap/app.php`               | Application configuration: routes, middleware, exception handling - all in one file       |
| `routes/web.php`                  | Web routes (with session, CSRF)                                                            |
| `routes/api.php`                  | API routes (Laravel 11+: enable explicitly via `withRouting`)                              |
| `routes/console.php`              | Closures for artisan commands and scheduling                                                |

**Laravel 10 and earlier:**

| Location                          | Purpose                                                                                  |
| --------------------------------- | ---------------------------------------------------------------------------------------- |
| `app/Http/Kernel.php`             | Middleware pipeline + route middleware groups                                              |
| `app/Console/Kernel.php`          | Artisan commands + scheduler                                                               |
| `app/Exceptions/Handler.php`      | Exception rendering                                                                         |

**All versions:**

| Location                  | Purpose                                                                                  |
| ------------------------- | ---------------------------------------------------------------------------------------- |
| `app/Models/`             | Eloquent models                                                                          |
| `app/Http/Controllers/`   | Controllers                                                                               |
| `app/Http/Requests/`      | Form requests (validation + authorization)                                                |
| `app/Http/Middleware/`    | Custom middleware                                                                         |
| `app/Providers/`          | Service providers                                                                         |
| `app/Jobs/`               | Queueable jobs                                                                             |
| `app/Listeners/`          | Event listeners                                                                            |
| `app/Events/`             | Events (broadcastable if `ShouldBroadcast`)                                                |
| `app/Policies/`           | Model policies for authorization                                                           |
| `app/Console/Commands/`   | Custom artisan commands                                                                    |
| `database/migrations/`    | Migrations (`YYYY_MM_DD_HHMMSS_*.php`)                                                    |
| `database/seeders/`       | DB seeders                                                                                 |
| `database/factories/`     | Model factories for tests                                                                  |
| `config/`                 | Config files (each returns array; accessed via `config('file.key')`)                       |
| `resources/views/`        | Blade templates                                                                            |
| `resources/js/` + `resources/css/` | Frontend assets                                                                  |
| `tests/Feature/` + `tests/Unit/` | PHPUnit tests                                                                       |

### Conventions

- **Eloquent over query builder** for most cases; query builder for complex queries.
- **Form requests** for validation in controllers (typehinted parameter triggers validation).
- **Service providers** register bindings (`register()`) and run boot logic (`boot()`).
- **Policies + gates** for authorization; `authorize('update', $post)` in controllers.
- **Resource controllers** + `Route::resource(...)` for RESTful CRUD.
- **API resources** (`app/Http/Resources/`) for response shaping; replaces direct model serialization.
- **Tests:** Pest (modern) or PHPUnit (default); database refresh per test via `RefreshDatabase` trait.
- **Pint** for code style; **Larastan / PHPStan / Psalm** for static analysis.

### Risk Hotspots Specific to Laravel

- **`env()` outside config files:** returns null after `config:cache`. Use `config('...')` in runtime code.
- **N+1 queries:** in views and serializers; check for `$model->withCount`, `with`, eager loading.
- **`$guarded = []`:** allows mass assignment of any field; flag immediately.
- **Soft delete global scope** filtering queries unless `withTrashed()`.
- **Model events firing inside transactions:** long-running listeners stretch transactions.
- **`update()` (query builder)** vs `update()` (model instance): query builder skips events.
- **`dispatch()` with `QUEUE_CONNECTION=sync`** in tests masking async bugs.
- **CSRF disabled on routes**: check `VerifyCsrfToken` exclusions.
- **Middleware aliases drift:** named middleware (`auth`, `throttle:api`) defined in `bootstrap/app.php` (L11+) or `Http/Kernel.php` (L10).
- **Migrating in production**: use `php artisan migrate --force`; missing rollback migrations is a footgun.

### First-PR Safe Zones

- New route + controller method following existing pattern.
- New model + migration + factory + feature test.
- New Form Request for validation.
- New artisan command in `app/Console/Commands/`.

Riskier:

- Service providers - run at boot.
- Middleware pipeline changes - apply to many routes.
- Authentication / Sanctum config.
- Production migrations with foreign key changes.

### Ecosystem Currency

- Laravel 11 / 12 standard; 10 LTS for legacy projects.
- PHP 8.3 / 8.4 latest; 8.2 minimum.
- Pest 2/3 increasingly common over PHPUnit.
- Inertia.js for SPA-like with server-side routing.
- Livewire 3 for hybrid (PHP-driven reactivity).
- Pint default; Laravel Pint v1.x.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Laravel version, PHP version, queue backend, broadcasting driver, auth approach, frontend stack (Inertia/Livewire/Blade), test framework.

**Local Bootstrap:** `composer install`, `npm install`, `.env` setup + `key:generate`, `php artisan migrate`, `php artisan serve`, `npm run dev`, queue worker if needed.

**Architecture Map:** Laravel 11+ vs 10 bootstrap layout, models/controllers/jobs file counts, service providers, route file split.

**Conventions:** form requests, API resources, Eloquent vs query builder, test framework (Pest vs PHPUnit), service provider patterns.

**Risk Hotspots:** `env()` outside config, mass assignment, N+1 in views, sync queue masking, migration prod policy.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating Laravel 10 patterns as current for Laravel 11+ projects (bootstrap layout differs)
- Listing every package in composer.json - focus on the architectural ones
- Recommending `env()` in runtime code
- Skipping queue backend identification - sync vs real backend changes everything
- Confusing query builder `update()` with model `update()` semantics
