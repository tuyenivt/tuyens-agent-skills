---
name: task-laravel-new
description: End-to-end Laravel feature implementation workflow. Generates all coordinated layers from migration through Pest tests for new features requiring multiple Laravel components.
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

# Implement Feature

## When to Use

- Implementing a new Laravel feature end-to-end (migration -> model -> service -> controller -> tests)
- Scaffolding a complete CRUD or domain-specific resource with production-ready patterns
- Adding a new domain aggregate requiring REST API, persistence, background jobs, and test coverage
- Any task requiring coordinated generation of multiple Laravel layers
- NOT for: single-file bug fixes or isolated errors (use `task-laravel-debug`)
- NOT for: adding a column to an existing table without new business logic

## Edge Cases

- **Partial input**: If the user provides only a feature name without details, ask for entity fields, relationships, and operations before proceeding to design.
- **Existing model**: If the user references a model that already exists, read the existing model class and extend it rather than creating a new one. Skip the migration step if no schema change is needed.
- **No database**: If the feature does not require persistence (e.g., proxy/aggregation endpoint), skip model, migration, and factory steps; generate only controller, service, DTOs, and tests.
- **Webhook endpoint**: If the feature receives external callbacks (e.g., Stripe, payment provider), use the webhook controller pattern from `laravel-api-patterns` instead of standard resource controllers.
- **Status transitions**: If the feature has state changes (e.g., pending -> processing -> shipped), use the state machine pattern from `laravel-service-patterns` with transition validation.

## Rules

- Constructor injection only - never `app()` in business logic
- `readonly` classes for all DTOs - never pass raw `$request` arrays between layers
- `$fillable` whitelist on models - never `$guarded = []`
- Backed enums for all status/type columns - never bare strings
- API Resources for all responses - never return raw Eloquent models
- Form Requests for all validation - never validate inline in controllers
- Present design for user approval before generating any code
- Each step must complete and be reviewed before proceeding to the next
- Run `php artisan test` after all files are generated

## Workflow

STEP 1 - DETECT FRAMEWORK: Use skill: `stack-detect` to confirm Laravel. Read `composer.json` to verify `laravel/framework` dependency and PHP version. If Laravel is not detected, stop and inform the user this workflow requires a Laravel project.

STEP 2 - GATHER: Ask the user these questions before writing any code:

1. What is the feature? (brief description, primary use case)
2. What are the main entities/models? (fields, relationships, constraints)
3. Are there external integrations? (payment APIs, email, third-party services)
4. Are background jobs needed? (async processing, notifications, scheduled tasks)
5. Does the feature need authentication/authorization? (who can access what?)
6. Are there status transitions? (list all states and valid transitions, e.g., pending -> processing -> shipped)
7. Are there webhook endpoints? (external callbacks from payment providers, etc.)
8. Is there concurrent access? (inventory, seat reservations - needs locking strategy)

STEP 3 - DESIGN: Propose the implementation layers and present for user approval before generating code.

Use skill: `laravel-api-patterns` for controller/resource design.
Use skill: `laravel-eloquent-patterns` for model/relationship design.
Use skill: `laravel-service-patterns` for service/action/DTO design.
**If background jobs needed**: Use skill: `laravel-queue-patterns` for job design.
**If auth needed**: Use skill: `laravel-security-patterns` for auth/policy design.
**If status transitions**: Use skill: `laravel-service-patterns` (section 7) for state machine pattern.
**If webhook endpoints**: Use skill: `laravel-api-patterns` (section 10) for webhook controller pattern and `laravel-security-patterns` (section 12) for signature verification.

Present a file tree showing what will be generated:

```
app/
  Models/Order.php                  # Eloquent model with relationships, scopes, casts
  Http/
    Controllers/OrderController.php # Thin resource controller
    Requests/StoreOrderRequest.php  # Form request validation
    Requests/UpdateOrderRequest.php
    Resources/OrderResource.php     # API Resource transformer
  Services/OrderService.php         # Business logic (or Actions/)
  Policies/OrderPolicy.php          # Authorization
  Jobs/ProcessPayment.php           # Queue job (if needed)
  Events/OrderCreated.php           # Domain event (if needed)
  Listeners/SendOrderConfirmation.php
database/
  migrations/xxx_create_orders_table.php
  factories/OrderFactory.php
tests/
  Feature/Http/OrderControllerTest.php
  Unit/Services/OrderServiceTest.php
```

STEP 4 - DATABASE: Use skill: `laravel-migration-safety` to generate the migration safely. Include indexes on foreign keys and frequently-filtered columns. For list endpoints, add indexes that support the default sort order.

```php
// Bad - missing indexes and foreign key constraints
Schema::create('orders', function (Blueprint $table) {
    $table->id();
    $table->unsignedBigInteger('user_id'); // no FK constraint
    $table->string('status');              // no index on filtered column
    $table->timestamps();
});

// Good - proper constraints and indexes
Schema::create('orders', function (Blueprint $table) {
    $table->id();
    $table->foreignId('user_id')->constrained()->cascadeOnDelete();
    $table->string('status', 20)->default('pending');
    $table->decimal('total', 10, 2);
    $table->string('shipping_address', 500);
    $table->text('notes')->nullable();
    $table->timestamps();

    $table->index(['user_id', 'status']); // supports filtered list queries
    $table->index('created_at');           // supports default sort
});
```

STEP 5 - MODELS: Generate Eloquent models following `laravel-eloquent-patterns`. Include:

- Typed relationships with return types
- `$fillable` whitelist (never `$guarded = []`)
- `casts()` method for type conversion
- Backed enums for status fields
- Local scopes for common query constraints
- Foreign key constraints in migrations

STEP 6 - SERVICES: Business logic layer following `laravel-service-patterns`.

```php
// CORRECT: dispatch after commit
public function create(CreateOrderDTO $dto): Order
{
    return DB::transaction(function () use ($dto) {
        $order = Order::create($dto->toArray());
        $order->items()->createMany(
            array_map(fn($item) => $item->toArray(), $dto->items)
        );
        OrderCreated::dispatch($order);
        return $order;
    });
}

// Queue job dispatched in event listener with afterCommit
class ProcessOrderPayment
{
    public bool $afterCommit = true;
    public function handle(OrderCreated $event): void
    {
        ProcessPayment::dispatch($event->order->id);
    }
}
```

STEP 7 - CONTROLLERS AND FORM REQUESTS: Resource controllers and validation following `laravel-api-patterns`. Map domain errors to HTTP status codes:

| Domain Error         | HTTP Status |
| -------------------- | ----------- |
| Validation failure   | 422         |
| Not found            | 404         |
| Conflict (duplicate) | 409         |
| External timeout     | 503         |
| Unauthorized         | 401         |
| Forbidden            | 403         |

List endpoints must be paginated. Include filtering on common fields.

STEP 8 - API RESOURCES: Use skill: `laravel-api-patterns` for response transformation. Never return raw models from controllers.

- Use `whenLoaded()` for conditional relationship inclusion
- Use `whenCounted()` for aggregate data
- Separate Resource per entity

STEP 9 - QUEUE JOBS: If background jobs needed, follow `laravel-queue-patterns`.

- Pass IDs, not Eloquent models
- Define `$tries`, `$backoff`, `$timeout`
- Implement `failed()` method
- Use `ShouldBeUnique` where appropriate

STEP 10 - TESTS: Use skill: `laravel-testing-patterns` for Pest patterns. Generate:

- Feature tests: happy path + error cases for each endpoint
- Unit tests: service/action business logic
- Job tests: if queue jobs exist
- Model factories with states
- Authorization tests: owner vs non-owner

STEP 11 - VALIDATE: Run `php artisan test`, `php artisan route:list` to verify. Fix any failures before presenting output.

## Output Format

```
## Files Generated
[grouped file list by layer: models, migrations, controllers, requests, resources, services, jobs, tests]

## Endpoints
| Method | Path             | Request            | Response          | Status |
| ------ | ---------------- | ------------------ | ----------------- | ------ |
| POST   | /api/orders      | StoreOrderRequest  | OrderResource     | 201    |
| GET    | /api/orders      | query params       | OrderCollection   | 200    |
| ...    | ...              | ...                | ...               | ...    |

## Queue Jobs (if any)
| Job            | Queue    | Trigger        | Retry           |
| -------------- | -------- | -------------- | --------------- |

## Tests
[X] tests passing - [list test files and count per file]

## Migration
[migration file name and what it creates: tables, indexes, constraints]
```

## Avoid

- Dispatching queue jobs inside a DB transaction without `afterCommit()` (job races the commit)
- Returning raw Eloquent models from controllers (use API Resources)
- Using `$guarded = []` on any model (mass assignment vulnerability)
- Skipping pagination on list endpoints
- Using bare string fields for status without backed enums
- Generating code before user approves the design
- Inline validation in controllers (use Form Requests)
- Business logic in controllers (delegate to services/actions)

## Self-Check

- [ ] STEP 1: Laravel detected via `stack-detect`; `composer.json` confirms `laravel/framework`
- [ ] STEP 2: Requirements gathered from user; all eight questions answered
- [ ] STEP 3: Design presented and approved by user before code generation; webhook/state machine patterns included if applicable
- [ ] STEP 4: Migration created with indexes on FKs and filtered columns; zero-downtime patterns applied
- [ ] STEP 5: Models have typed relationships, `$fillable` whitelist, `casts()`, backed enums
- [ ] STEP 6: Business logic in services/actions with `DB::transaction()`; events dispatched for side effects
- [ ] STEP 7: Thin resource controllers with Form Request validation; domain errors mapped to HTTP status codes
- [ ] STEP 8: API Resources used for all responses; `whenLoaded()` for conditional relationships
- [ ] STEP 9: Queue jobs pass IDs not models; `$tries`/`$backoff`/`$timeout` set; `afterCommit()` used
- [ ] STEP 10: Pest feature + unit tests generated; factories with states; authorization tests included
- [ ] STEP 11: `php artisan test` passes; `php artisan route:list` verified; output format filled
