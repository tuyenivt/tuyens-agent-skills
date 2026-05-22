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
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for this feature, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles` and `stack-detect`. The preamble decides between modes (`no-spec`, `spec-only`, `spec+plan`, `full-spec`); follow its contract - skip GATHER (and DESIGN, when `plan.md` is present) and treat the spec as the source of truth. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface conflicts as proposed amendments.

# Implement Laravel Feature

## When to Use

End-to-end Laravel feature work: migration + model + service + controller + Form Request + Resource + Pest tests in one pass.

Not for: single-file bugfixes (`task-laravel-debug`), schema-only changes without new business logic.

## Rules

- Constructor injection only; no `app()` in business logic
- `readonly` DTOs across layer boundaries; never pass raw `$request` arrays
- `$fillable` whitelist on every model; never `$guarded = []`
- Backed enums for status/type columns; never bare strings
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

Ask targeted clarifications for any gap. Do not guess.

### STEP 3 - DESIGN (APPROVAL GATE)

Use skill: `laravel-api-patterns` (controllers/resources), `laravel-eloquent-patterns` (models/relationships), `laravel-service-patterns` (services/actions/DTOs).

Conditional skills:
- Background jobs: `laravel-queue-patterns`
- Auth: `laravel-security-patterns`
- Status transitions: `laravel-service-patterns` (state machine section)
- Webhooks: `laravel-api-patterns` (webhook controller) + `laravel-security-patterns` (signature verification)

Present a file tree covering: `Models/`, `Http/Controllers/`, `Http/Requests/`, `Http/Resources/`, `Services/`, `Policies/`, `Jobs/` + `Events/` + `Listeners/` (if async), `database/migrations/`, `database/factories/`, and matching `tests/Feature/` + `tests/Unit/`. Wait for approval before generating code.

### STEP 4 - DATABASE

Use skill: `laravel-migration-safety`. Index FKs, frequently-filtered columns, and the default sort column for list endpoints. Backed-enum-typed columns use string of bounded length with a default.

### STEP 5 - MODELS

Use skill: `laravel-eloquent-patterns`. Typed relationships, `$fillable` whitelist, `casts()` method, backed enums for status, local scopes for common filters.

### STEP 6 - SERVICES

Use skill: `laravel-service-patterns`. Wrap multi-step writes in `DB::transaction()`; dispatch events inside the transaction and gate listeners with `$afterCommit = true` so queue jobs never race the commit.

```php
public function create(CreateOrderDTO $dto): Order
{
    return DB::transaction(function () use ($dto) {
        $order = Order::create($dto->toArray());
        $order->items()->createMany(array_map(fn($i) => $i->toArray(), $dto->items));
        OrderCreated::dispatch($order); // listener with $afterCommit=true enqueues the job
        return $order;
    });
}
```

### STEP 7 - CONTROLLERS AND FORM REQUESTS

Use skill: `laravel-api-patterns`. Thin resource controllers; Form Requests for validation; paginated list endpoints with filter params. Map domain errors:

| Domain Error         | HTTP |
| -------------------- | ---- |
| Validation failure   | 422  |
| Not found            | 404  |
| Conflict (duplicate) | 409  |
| External timeout     | 503  |
| Unauthorized         | 401  |
| Forbidden            | 403  |

### STEP 8 - API RESOURCES

Use skill: `laravel-api-patterns`. Separate Resource per entity; `whenLoaded()` for conditional relationships; `whenCounted()` for aggregates. Never return raw models.

### STEP 9 - QUEUE JOBS

If background jobs needed: Use skill: `laravel-queue-patterns`. Pass IDs (not models); set `$tries`, `$backoff`, `$timeout`; implement `failed()`; use `ShouldBeUnique` where retries must not duplicate work.

### STEP 10 - TESTS

Use skill: `laravel-testing-patterns`. Pest feature tests (happy + error per endpoint), unit tests for service/action logic, job tests, authorization tests (owner vs non-owner), factories with states.

### STEP 11 - VALIDATE

Run `php artisan test` and `php artisan route:list`. Fix failures before reporting done.

## Edge Cases

- **Partial input**: ask for entity fields, relationships, and operations before design
- **Existing model**: read and extend; skip migration if no schema change
- **No database**: skip migration/model/factory; controller + service + DTOs + tests only
- **Webhook endpoint**: use webhook controller pattern from `laravel-api-patterns` instead of resource controllers
- **Status transitions**: use the state machine pattern in `laravel-service-patterns` with transition validation

## Output Format

```
## Files Generated
[grouped by layer: models, migrations, controllers, requests, resources, services, jobs, tests]

## Endpoints
| Method | Path             | Request            | Response          | Status |
| ------ | ---------------- | ------------------ | ----------------- | ------ |
| POST   | /api/orders      | StoreOrderRequest  | OrderResource     | 201    |
| GET    | /api/orders      | query params       | OrderCollection   | 200    |

## Queue Jobs (if any)
| Job | Queue | Trigger | Retry |
| --- | ----- | ------- | ----- |

## Tests
[X] tests passing - [list test files and count per file]

## Migration
[migration file name and what it creates: tables, indexes, constraints]
```

## Self-Check

- [ ] STEP 1: Laravel detected; `composer.json` confirms `laravel/framework`
- [ ] STEP 2: All eight requirement questions answered
- [ ] STEP 3: Design approved before code; webhook/state-machine patterns included if applicable
- [ ] STEP 4: Migration indexes FKs and filtered/sorted columns; safety patterns applied
- [ ] STEP 5: Models have typed relationships, `$fillable`, `casts()`, backed enums
- [ ] STEP 6: Business logic in services with `DB::transaction()`; listeners use `afterCommit`
- [ ] STEP 7: Thin controllers + Form Requests; domain errors mapped to HTTP; list endpoints paginated
- [ ] STEP 8: API Resources used everywhere; `whenLoaded()` for relationships
- [ ] STEP 9: Queue jobs pass IDs; `$tries`/`$backoff`/`$timeout` set
- [ ] STEP 10: Pest feature + unit tests; factory states; authorization covered
- [ ] STEP 11: `php artisan test` passes; `route:list` verified; output template filled

## Avoid

- Generating code before design approval
- Queue dispatch inside `DB::transaction()` without `afterCommit`
- Returning raw Eloquent models from controllers
- `$guarded = []` (mass-assignment risk)
- Bare string status fields without backed enums
- Inline validation or business logic in controllers
- Unpaginated list endpoints
