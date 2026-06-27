---
name: task-laravel-implement
description: End-to-end Laravel feature implementation: generates migration, model, controller, routes, Form Request, API Resource, Pest tests across layers.
agent: php-architect
metadata:
  category: backend
  tags: [php, laravel, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Implement Laravel Feature

## When to Use

End-to-end Laravel feature work: migration + model + service + controller + Form Request + Resource + Pest tests in one pass.

Not for: single-file bugfixes (`task-laravel-debug`), schema-only changes without new business logic.

## Rules

- Constructor injection only; no `app()` in business logic
- `readonly` DTOs across layer boundaries; never raw `$request` arrays
- `$fillable` whitelist on every model; never `$guarded = []`
- Backed enums for status/type columns
- API Resources for all responses; Form Requests for all validation
- Queue dispatch and event listeners run **after** the DB transaction commits (`afterCommit`)
- Design approved before code; each step completes before the next

## Workflow

### STEP 1 - DETECT FRAMEWORK

Use skill: `stack-detect`. Read `composer.json` to confirm `laravel/framework` and PHP version. Stop if Laravel is not detected.

### STEP 2 - GATHER

Ask before writing code:

1. Feature description and primary use case
2. Entities, fields, relationships, constraints
3. External integrations (payment APIs, email, third-party services)
4. Background jobs needed (async processing, notifications, scheduled tasks)
5. Authentication / authorization (who accesses what)
6. Status transitions (states and valid transitions)
7. Webhook endpoints (external callbacks)
8. Concurrent access (inventory, seat reservations - locking strategy)

**Edge cases:** Existing model -> read and extend; skip migration if no schema change. No database -> skip migration/model/factory; controller + service + DTOs + tests only. Webhook endpoint -> use webhook controller pattern. Status transitions -> state machine pattern.

### STEP 3 - DESIGN (APPROVAL GATE)

Use skill: `laravel-api-patterns` (controllers/resources), `laravel-eloquent-patterns` (models/relationships), `laravel-service-patterns` (services/actions/DTOs).

Conditional skills:
- Background jobs -> `laravel-queue-patterns`
- Auth / webhook signature -> `laravel-security-patterns`
- Status transitions -> `laravel-service-patterns` (state machine)

Present a file tree covering: `Models/`, `Http/Controllers/`, `Http/Requests/`, `Http/Resources/`, `Services/`, `Policies/`, `Jobs/` + `Events/` + `Listeners/` (if async), `database/migrations/`, `database/factories/`, and matching `tests/Feature/` + `tests/Unit/`. Wait for approval before generating code.

### STEP 4 - DATABASE

Use skill: `laravel-migration-safety`. Index FKs, frequently-filtered columns, and the default sort column for list endpoints. Backed-enum-typed columns: string of bounded length with a default.

### STEP 5 - MODELS

Use skill: `laravel-eloquent-patterns`. Typed relationships, `$fillable` whitelist, `casts()` method, backed enums for status, local scopes for common filters.

### STEP 6 - SERVICES

Use skill: `laravel-service-patterns`. Multi-step writes wrapped in `DB::transaction()`. Concurrent decrements (balances, inventory, counters) use `lockForUpdate()` or an atomic conditional `UPDATE` inside the transaction - a bare transaction does not prevent lost updates. Events dispatched inside the transaction; listeners use `$afterCommit = true` so queue jobs see committed state.

### STEP 7 - CONTROLLERS AND FORM REQUESTS

Use skill: `laravel-api-patterns`. Thin resource controllers; Form Requests for validation; paginated list endpoints with filter params and `per_page` cap. Domain errors mapped centrally via `withExceptions()` (Laravel 11+).

### STEP 8 - API RESOURCES

Use skill: `laravel-api-patterns`. Separate Resource per entity; `whenLoaded()`, `whenCounted()`. Never return raw models.

### STEP 9 - QUEUE JOBS

If background jobs needed: Use skill: `laravel-queue-patterns`. Pass IDs; set `$tries`, `$backoff`, `$timeout`; implement `failed()`; use `ShouldBeUnique` where retries must not duplicate work.

### STEP 10 - TESTS

Use skill: `laravel-testing-patterns`. Pest feature tests (happy + error per endpoint), unit tests for service/action logic, job tests, authorization tests (owner vs non-owner), factories with states.

### STEP 11 - VALIDATE

Run `php artisan test` and `php artisan route:list`. Fix failures before reporting done.

## Output Format

```
## Files Generated
[grouped by layer: models, migrations, controllers, requests, resources, services, jobs, tests]

## Endpoints
| Method | Path             | Request            | Response          | Status |

## Queue Jobs (if any)
| Job | Queue | Trigger | Retry |

## Tests
[X] tests passing - [list test files and count per file]

## Migration
[migration file name; tables, indexes, constraints]
```

## Self-Check

- [ ] STEP 1: Laravel detected; `composer.json` confirms `laravel/framework`
- [ ] STEP 2: All eight requirement questions answered
- [ ] STEP 3: Design approved before code; webhook/state-machine patterns included if applicable
- [ ] STEP 4: Migration indexes FKs and filtered/sorted columns; safety patterns applied
- [ ] STEP 5: Models have typed relationships, `$fillable`, `casts()`, backed enums
- [ ] STEP 6: Business logic in services with `DB::transaction()`; concurrent decrements use `lockForUpdate()`/atomic update; listeners use `afterCommit`
- [ ] STEP 7: Thin controllers + Form Requests; domain errors mapped centrally; list endpoints paginated with `per_page` cap
- [ ] STEP 8: API Resources used everywhere; `whenLoaded()` for relationships
- [ ] STEP 9: Queue jobs pass IDs; `$tries`/`$backoff`/`$timeout`/`failed()` set
- [ ] STEP 10: Pest feature + unit tests; factory states; authorization covered
- [ ] STEP 11: `php artisan test` passes; `route:list` verified; output template filled

## Avoid

- Generating code before design approval
- Queue dispatch inside `DB::transaction()` without `afterCommit`
- Returning raw Eloquent models from controllers
- `$guarded = []`; bare string status fields
- Inline validation or business logic in controllers
- Unpaginated list endpoints
