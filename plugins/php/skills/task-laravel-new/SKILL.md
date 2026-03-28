---
name: task-laravel-new
description: End-to-end Laravel feature implementation workflow. Generates all layers - migrations, Eloquent models, services/actions, controllers, form requests, API resources, queue jobs, and Pest tests. Use for new features requiring multiple coordinated layers. Not for single-file fixes or isolated bug fixes (use task-laravel-debug for errors).
agent: php-architect
metadata:
  category: backend
  tags: [php, laravel, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

# Implement Feature

## When to Use

- Implementing a new Laravel feature end-to-end (migration -> model -> service -> controller -> tests)
- Scaffolding a complete CRUD or domain-specific resource with production-ready patterns
- Adding a new domain aggregate requiring REST API, persistence, background jobs, and test coverage
- Any task requiring coordinated generation of multiple Laravel layers

## Rules

- Detect Laravel first via `stack-detect` before generating any code
- API Resources for all responses - never return raw Eloquent models from controllers
- `$fillable` explicitly defined on every model - never `$guarded = []`
- Queue jobs dispatched AFTER DB transaction commits via `afterCommit()`, never inside the transaction
- Transactions: `DB::transaction()` for multi-step operations
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code

## Implementation

STEP 1 - DETECT FRAMEWORK: Use skill: `stack-detect` to confirm Laravel. Read `composer.json` to verify `laravel/framework` dependency and PHP version.

STEP 2 - GATHER: Ask the user these questions before writing any code:

1. What is the feature? (brief description, primary use case)
2. What are the main entities/models? (fields, relationships, constraints)
3. Are there external integrations? (payment APIs, email, third-party services)
4. Are background jobs needed? (async processing, notifications, scheduled tasks)
5. Does the feature need authentication/authorization?
6. Are there status transitions? (e.g., order: pending -> processing -> completed)

STEP 3 - DESIGN: Propose the implementation layers and present for user approval before generating code.

Use skill: `laravel-api-patterns` for controller/resource design.
Use skill: `laravel-eloquent-patterns` for model/relationship design.
Use skill: `laravel-service-patterns` for service/action/DTO design.
**If background jobs needed**: Use skill: `laravel-queue-patterns` for job design.
**If auth needed**: Use skill: `laravel-security-patterns` for auth/policy design.

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

STEP 8 - API RESOURCES: Transform Eloquent models to JSON. Never return raw models from controllers.

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

## Output Template

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

- [ ] Laravel detected; requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, service, controller, form request, API resource, tests
- [ ] API Resources used for all responses - no raw Eloquent models
- [ ] `$fillable` defined on every model; no `$guarded = []`
- [ ] Queue jobs dispatched after DB commit via `afterCommit()`; jobs accept IDs not models
- [ ] Pest tests pass; routes verified with `php artisan route:list`
- [ ] Migration includes indexes; list endpoints paginated; output template filled
