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

| Skill              | Agent         | Description                                                   |
| ------------------ | ------------- | ------------------------------------------------------------- |
| task-laravel-new   | php-architect | End-to-end feature implementation across all layers           |
| task-laravel-debug | php-architect | Debug stack traces, query errors, queue failures, test errors |

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

## Agents

| Agent                    | Model  | Description                                                                                      |
| ------------------------ | ------ | ------------------------------------------------------------------------------------------------ |
| php-architect            | sonnet | Designs Laravel APIs, Eloquent models, service/action layers, queue pipelines, project structure |
| php-tech-lead            | sonnet | Code review, refactoring guidance, Laravel conventions, type safety, architectural decisions     |
| php-security-engineer    | sonnet | OWASP Top 10 for PHP/Laravel, auth review, mass assignment, SQL injection, dependency scanning   |
| php-performance-engineer | sonnet | Eloquent query tuning, MySQL EXPLAIN analysis, queue throughput, caching strategy, N+1 detection |
| php-test-engineer        | sonnet | Pest/PHPUnit strategies, model factories, HTTP testing, mocking Laravel facades                  |

## Framework Detection

Laravel is the only supported framework.

Skills detect Laravel by checking:

1. **Repo context file** - explicit framework declaration takes priority
2. **File detection** (fallback):
   - `composer.json` with `laravel/framework` dependency -> Laravel
   - `artisan` file in project root -> Laravel
