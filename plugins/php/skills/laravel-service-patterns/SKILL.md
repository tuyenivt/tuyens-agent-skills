---
name: laravel-service-patterns
description: "Laravel business logic patterns: service classes, action classes, readonly DTOs, repository, container DI, events/listeners, state machines."
metadata:
  category: backend
  tags: [php, laravel, services, actions, dto, dependency-injection, events]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Extracting logic from controllers (typically >10-15 lines of orchestration)
- Multi-model operations; logic reused across HTTP / job / artisan
- Decoupling side effects via events
- NOT for: simple CRUD without business rules; query optimization (use `laravel-eloquent-patterns`)

## Rules

- Constructor injection only - never `app()` / `resolve()` in business code
- `readonly` DTOs across layer boundaries - never pass `$request` arrays
- Events for cross-domain side effects - never call unrelated services directly
- Jobs dispatched from inside `DB::transaction` use `afterCommit()` (or `$afterCommit = true` on the job/listener)
- State transitions go through a transition method - never direct `update(['status' => ...])`

### Extraction signals

| Signal                                            | Extract to                |
| ------------------------------------------------- | ------------------------- |
| Controller method >10-15 lines of business logic  | Service or Action         |
| Same logic in 2+ places (controller, job, command)| Action (invokable)        |
| Multiple related operations on one domain         | Service class             |
| Cross-domain side effect (email, search index)    | Event + Listener          |
| Complex query used in multiple places             | Query scope or repository |

## Patterns

### Service class

```php
class OrderService {
    public function __construct(private readonly PaymentService $payments) {}

    public function create(CreateOrderDTO $dto): Order {
        return DB::transaction(function () use ($dto) {
            $order = Order::create($dto->toArray());
            $order->items()->createMany($dto->itemsArray());
            OrderCreated::dispatch($order);   // listener with $afterCommit=true enqueues jobs
            return $order;
        });
    }
}
```

### Action class (invokable)

Single operation reused across contexts.

```php
class CreateOrder {
    public function __construct(private readonly PaymentService $payments) {}
    public function __invoke(CreateOrderDTO $dto): Order { /* ... */ }
}

// Called from controller / job / artisan
$order = app(CreateOrder::class)($dto);
```

### DTOs (readonly)

```php
readonly class CreateOrderDTO {
    public function __construct(
        public int $userId,
        public string $total,
        /** @var OrderItemDTO[] */ public array $items,
    ) {}

    public static function fromRequest(StoreOrderRequest $request): self {
        return new self(
            userId: $request->user()->id,
            total: $request->validated('total'),
            items: array_map(fn($i) => OrderItemDTO::from($i), $request->validated('items')),
        );
    }
}
```

For `spatie/laravel-data`, the package handles validation + transformation in one class.

### Repository pattern

Justify before adding - Eloquent already abstracts storage. Use when:

- Non-Eloquent backend (legacy stored procedure, external API as source of truth)
- Multiple data sources need a unified interface
- Specific test seam Mockery cannot satisfy

A single-implementation interface backed only by direct Eloquent calls is over-abstraction.

### Dependency injection

```php
// Bad - service locator hides dependency
$payment = app(PaymentService::class);

// Good - constructor injection
class OrderService {
    public function __construct(private readonly PaymentService $payments) {}
}

// Bindings (AppServiceProvider)
$this->app->bind(OrderRepositoryInterface::class, EloquentOrderRepository::class);
$this->app->singleton(PaymentGateway::class, fn() =>
    new StripePaymentGateway(config('services.stripe.key'))
);
$this->app->when(OrderService::class)
    ->needs(PaymentGateway::class)
    ->give(StripePaymentGateway::class);
```

### Events and listeners

```php
// Bad - direct cross-domain calls
class OrderService {
    public function create(...): Order {
        $order = Order::create(...);
        $this->emailService->sendConfirmation($order);     // cross-domain
        $this->inventoryService->decrementStock($order);   // cross-domain
        return $order;
    }
}

// Good - event; listeners handle side effects
class OrderService {
    public function create(...): Order {
        return DB::transaction(function () {
            $order = Order::create(...);
            OrderCreated::dispatch($order);
            return $order;
        });
    }
}

// Listener dispatching a job - $afterCommit so the job sees committed state
class ProcessOrderPayment {
    public bool $afterCommit = true;
    public function handle(OrderCreated $event): void {
        ProcessPayment::dispatch($event->order->id);
    }
}
```

| Scenario                                | Use         |
| --------------------------------------- | ----------- |
| Same domain, same transaction           | Direct call |
| Cross-domain side effect                | Event       |
| Side effect must fail independently     | Event + job |
| Strict ordering between side effects    | Direct call |

### State machine

```php
class OrderService {
    private const TRANSITIONS = [
        OrderStatus::Pending->value    => [OrderStatus::Processing, OrderStatus::Cancelled],
        OrderStatus::Processing->value => [OrderStatus::Shipped, OrderStatus::Cancelled],
        OrderStatus::Shipped->value    => [OrderStatus::Delivered],
        OrderStatus::Delivered->value  => [],
        OrderStatus::Cancelled->value  => [],
    ];

    public function transition(Order $order, OrderStatus $to): Order {
        $allowed = self::TRANSITIONS[$order->status->value] ?? [];
        if (! in_array($to, $allowed, true)) {
            throw new InvalidStatusTransitionException($order->status, $to);
        }
        return DB::transaction(function () use ($order, $to) {
            $from = $order->status;
            $order->update(['status' => $to]);
            OrderStatusChanged::dispatch($order, $from, $to);
            return $order;
        });
    }
}
```

For 6+ states with guards / side-effects per transition, prefer `spatie/laravel-model-states`.

### File layout

```
app/
  Services/OrderService.php       # multi-operation domain services
  Actions/CreateOrder.php          # single-responsibility reusable actions
  DTOs/CreateOrderDTO.php          # readonly DTOs
  Events/OrderCreated.php
  Listeners/SendOrderConfirmation.php
```

## Output Format

```
## Service Layer Design
| Class | Type | Responsibility | Dependencies |
Type: {Service | Action | DTO | Event | Listener}

## Extraction Summary
| Extracted From | Extracted To | Reason |
```

## Avoid

- Business logic in controllers or Eloquent accessors/mutators
- Raw `$request` arrays between layers (use DTOs)
- `app()` / `resolve()` in business logic
- God services (>500 lines or >20 methods - split)
- Direct cross-domain calls (use events)
- Anemic services proxying single Eloquent calls (no value added)
- Direct `update(['status' => ...])` without transition validation
- Single-implementation interfaces with no test seam or alternative impl
- Circular service dependencies (wrong domain boundary)
