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
- NOT for: simple CRUD without business rules; database query optimization (use `laravel-eloquent-patterns`)

## Rules

- Constructor injection only - never `app()` / `resolve()` in business code
- DTOs are `readonly` classes - never pass `$request` arrays between layers
- Events for cross-domain side effects - never call unrelated services directly
- Jobs dispatched inside transactions must use `afterCommit`
- No circular dependencies; no god services (>20 methods - split)
- State transitions go through a transition method - never direct `update(['status' => ...])`

### Service vs Action

| Scenario                                  | Use           |
| ----------------------------------------- | ------------- |
| Multiple related operations on one domain | Service class |
| Single operation reused across contexts   | Action class  |
| Simple CRUD with no business rules        | Controller    |
| Side effect triggered by domain event     | Listener      |

## Patterns

### Service class

```php
class OrderController extends Controller {
    public function __construct(private readonly OrderService $orderService) {}

    public function store(StoreOrderRequest $request): OrderResource {
        $order = $this->orderService->create(CreateOrderDTO::fromRequest($request));
        return new OrderResource($order);
    }
}

class OrderService {
    public function __construct(private readonly PaymentService $paymentService) {}

    public function create(CreateOrderDTO $dto): Order {
        return DB::transaction(function () use ($dto) {
            $order = Order::create($dto->toArray());
            $order->items()->createMany($dto->itemsArray());
            OrderCreated::dispatch($order);  // event for side effects
            return $order;
        });
    }
}
```

### Action class (invokable)

```php
class CreateOrder {
    public function __construct(private readonly PaymentService $paymentService) {}

    public function __invoke(CreateOrderDTO $dto): Order {
        return DB::transaction(function () use ($dto) {
            $order = Order::create([...]);
            $order->items()->createMany([...]);
            OrderCreated::dispatch($order);
            return $order;
        });
    }
}

// Same call from controller, job, artisan command:
$order = app(CreateOrder::class)($dto);
```

### DTOs (readonly)

```php
readonly class CreateOrderDTO {
    public function __construct(
        public int $userId,
        public string $total,
        /** @var OrderItemDTO[] */
        public array $items,
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

For projects using `spatie/laravel-data`, the package handles validation + transformation in one class.

### Repository pattern

Justify before adding - Eloquent already abstracts storage. Use when:

- Non-Eloquent backend (legacy stored procedure, external API as source of truth)
- Multiple data sources need a unified interface
- Specific test seam Mockery cannot satisfy

```php
interface OrderRepositoryInterface {
    public function findById(int $id): ?Order;
    public function findByUser(int $userId, int $perPage = 15): LengthAwarePaginator;
}

class EloquentOrderRepository implements OrderRepositoryInterface { /* ... */ }

// AppServiceProvider
$this->app->bind(OrderRepositoryInterface::class, EloquentOrderRepository::class);
```

A single-implementation interface backed only by direct Eloquent calls is over-abstraction - call `Order::findOrFail($id)` directly instead.

### Dependency injection

```php
// Bad - service locator hides dependency
class OrderService {
    public function create(array $data): Order {
        $payment = app(PaymentService::class);  // hidden
    }
}

// Good - constructor injection
class OrderService {
    public function __construct(private readonly PaymentService $paymentService) {}
}

// Service provider
$this->app->bind(OrderRepositoryInterface::class, EloquentOrderRepository::class);
$this->app->singleton(PaymentGateway::class, fn() =>
    new StripePaymentGateway(config('services.stripe.key'))
);
$this->app->when(OrderService::class)
    ->needs(PaymentGateway::class)
    ->give(StripePaymentGateway::class);  // contextual
```

### Events and listeners

```php
// Bad - direct cross-domain calls inside service
class OrderService {
    public function create(...): Order {
        $order = Order::create(...);
        $this->emailService->sendConfirmation($order);    // cross-domain
        $this->inventoryService->decrementStock($order);  // cross-domain
        return $order;
    }
}

// Good - dispatch event; listeners handle side effects
class OrderService {
    public function create(...): Order {
        return DB::transaction(function () {
            $order = Order::create(...);
            OrderCreated::dispatch($order);
            return $order;
        });
    }
}

class SendOrderConfirmation {
    public function handle(OrderCreated $event): void {
        $event->order->user->notify(new OrderConfirmationNotification($event->order));
    }
}

// Listener dispatching a job - afterCommit so the job sees committed state
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

### When to extract

| Signal                                            | Extract to                |
| ------------------------------------------------- | ------------------------- |
| Controller method >10-15 lines of business logic  | Service or Action         |
| Same logic in 2+ places (controller, job, command) | Action class              |
| Multiple related operations on one domain         | Service class             |
| Cross-domain side effect (email, notification)    | Event + Listener          |
| Complex query used in multiple places             | Query scope or repository |

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
- God services with 20+ methods
- Direct cross-domain calls (use events)
- Dispatching jobs inside transactions without `afterCommit`
- Anemic services that proxy single Eloquent calls (no value added)
- Circular service dependencies (indicates wrong domain boundary)
- Direct `update(['status' => ...])` without transition validation
- Single-implementation interfaces with no test seam or alternative implementation
