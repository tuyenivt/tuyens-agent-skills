# Tuyen's Agent Skills - PHP

Claude Code plugin for PHP development.

## Stack

- **Primary:** PHP 8.5, Laravel 12+
- **ORM / Migrations:** Eloquent ORM / Laravel Migrations
- **Testing:** Pest (primary), PHPUnit (secondary)
- **Queue:** Laravel Queue (Redis primary, database secondary)
- **Database:** MySQL
- **Monitoring:** Laravel Horizon (Redis), Laravel Telescope (development)

## Workflow Skills

| Skill                             | Agent                      | Description                                                                                   |
| --------------------------------- | -------------------------- | --------------------------------------------------------------------------------------------- |
| task-laravel-implement            | php-engineer               | End-to-end feature implementation across all layers                                           |
| task-laravel-debug                | php-engineer               | Debug stack traces, query errors, queue failures, test errors                                 |
| task-laravel-review               | php-tech-lead              | Staff-level code review umbrella with parallel perf / security / observability subagents      |
| task-laravel-review-perf          | php-performance-engineer   | Eloquent N+1, indexes, queue throughput (Horizon), caching, OPcache / Octane readiness        |
| task-laravel-review-security      | php-security-engineer      | Mass assignment, Sanctum / Passport, Policies, SQL injection, file upload, OWASP for Laravel  |
| task-laravel-review-observability | php-observability-engineer | Monolog structured logging, OpenTelemetry PHP, Horizon / Telescope / Pulse, Sentry, lifecycle |
| task-laravel-test                 | php-test-engineer          | Pest / PHPUnit pyramid, factories, RefreshDatabase, facade fakes, Sanctum helpers             |
| task-laravel-refactor             | php-tech-lead              | Fat controller, mass assignment, Eloquent N+1, queue idempotency, Octane-readiness refactors  |

## Atomic Skills (internal, not user-invocable)

| Skill                     | Description                                                                                     |
| ------------------------- | ----------------------------------------------------------------------------------------------- |
| laravel-eloquent-patterns | Relationships, scopes, eager loading, N+1 prevention, casts, chunking, soft deletes             |
| laravel-migration-safety  | Zero-downtime DDL for MySQL, nullable-first pattern, InnoDB online DDL, data migration          |
| laravel-service-patterns  | Service classes, action classes, DTOs with readonly, DI via container, events/listeners         |
| laravel-api-patterns      | Resource controllers, route model binding, form requests, API resources, middleware, pagination |
| laravel-security-patterns | Mass assignment, SQL injection, Sanctum auth, Gates/Policies, CSRF, rate limiting, secrets      |
| laravel-queue-patterns    | Jobs, retry strategies, batching, chaining, rate limiting, Redis/database drivers, Horizon      |
| laravel-testing-patterns  | Pest syntax, model factories, HTTP tests, database assertions, facade mocking, CI coverage      |
| laravel-code-explain      | Service container, request lifecycle (middleware, form requests, controllers), Eloquent events/scopes, queues, broadcasting - injected into `task-code-explain` |
| laravel-onboard-map       | composer.json, Laravel version, .env config, Eloquent + migrations, queue backend, frontend stack (Vite/Mix), auth - injected into `task-onboard` |
| laravel-overengineering-review | Necessity review: Form Request rules / `unique:` validators duplicating Eloquent / DB constraints, defensive null after `findOrFail` / `auth()->user()` after middleware, blanket `catch (\Throwable)` defeating the exception handler, single-impl Repository interfaces / `BaseRepository` / service-for-trivial-reads / AutoMapper-style mappers parallel to API Resources / speculative config keys / Event + single Listener for direct method calls. Composed into `task-laravel-review` Phase D. |

## Agents

| Agent                      | Description                                                                                                                                 |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| php-engineer               | Builds Laravel features end-to-end across migrations, models, services/actions, controllers, and jobs; debugs errors and failing Pest tests |
| php-tech-lead              | Code review, refactoring guidance, Laravel conventions, type safety, architectural decisions                                                |
| php-security-engineer      | OWASP Top 10 for PHP/Laravel, auth review, mass assignment, SQL injection, dependency scanning                                              |
| php-performance-engineer   | Eloquent query tuning, MySQL EXPLAIN analysis, queue throughput, caching strategy, N+1 detection                                            |
| php-observability-engineer | Monolog structured logging, correlation IDs, OpenTelemetry PHP, Horizon/Pulse metrics, Telescope, Sentry/Bugsnag PII scrubbing              |
| php-test-engineer          | Pest/PHPUnit strategies, model factories, HTTP testing, mocking Laravel facades                                                             |

## Framework Detection

Laravel is the only supported framework.

Skills detect Laravel by checking:

1. **Repo context file** - explicit framework declaration takes priority
2. **File detection** (fallback):
   - `composer.json` with `laravel/framework` dependency -> Laravel
   - `artisan` file in project root -> Laravel
