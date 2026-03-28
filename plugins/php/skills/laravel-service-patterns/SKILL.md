---
name: laravel-service-patterns
description: "Business logic patterns for Laravel - service classes, action classes, DTOs with readonly classes, repository pattern, dependency injection via Laravel container, and events/listeners for decoupled side effects."
metadata:
  category: backend
  tags: [php, laravel, services, actions, dto, dependency-injection, events]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Extracting business logic from controllers (especially controllers > 10-15 lines of logic)
- Organizing multi-model operations into services or actions
- Logic reused across multiple contexts (HTTP controller, queue job, artisan command)
- Decoupling side effects via events and listeners
- NOT for: simple CRUD with no business rules (keep in controller)
- NOT for: database query optimization (use laravel-eloquent-patterns)

## Rules

- Controllers must be thin - validate, delegate, respond
- Services use constructor injection via Laravel container - never `app()` in business logic
- DTOs must be `readonly` classes - never pass raw `$request` arrays between layers
- Events for cross-domain side effects - never call unrelated services directly
- Jobs dispatched inside transactions must use `afterCommit`
- No circular service dependencies
- No god services with 20+ methods - split into focused services or actions

## Patterns

### 1. SERVICE CLASSES

Use service classes when a domain has multiple related operations. Thin controllers delegate to services.

```php
// Bad - business logic in controller
class OrderController extends Controller
{
    public function store(StoreOrderRequest $request): OrderResource
    {
        $order = Order::create($request->validated());
        $order->items()->createMany($request->items);
        $order->user->notify(new OrderCreated($order));
        dispatch(new ProcessPayment($order->id));
        return new OrderResource($order);
    }
}

// Good - controller delegates to service
class OrderController extends Controller
{
    public function __construct(
        private readonly OrderService $orderService,
    ) {}

    public function store(StoreOrderRequest $request): OrderResource
    {
        $order = $this->orderService->create($request->validated());
        return new OrderResource($order);
    }
}

class OrderService
{
    public function __construct(
        private readonly PaymentService $paymentService,
    ) {}

    public function create(array $data): Order
    {
        return DB::transaction(function () use ($data) {
            $order = Order::create($data);
            $order->items()->createMany($data['items']);

            OrderCreated::dispatch($order); // event for side effects

            return $order;
        });
    }
}
```

### 2. ACTION CLASSES

Use action classes for single-responsibility operations reused in multiple contexts (controller, job, command).

```php
// Bad - logic duplicated in controller and artisan command
// In OrderController:
$order = Order::create($data);
$order->items()->createMany($data['items']);
OrderCreated::dispatch($order);

// In ImportOrdersCommand (same logic copy-pasted):
$order = Order::create($data);
$order->items()->createMany($data['items']);
OrderCreated::dispatch($order);

// Good - reusable Action class (both contexts call the same code)
$order = app(CreateOrder::class)($dto);
```

```php
class CreateOrder
{
    public function __construct(
        private readonly PaymentService $paymentService,
    ) {}

    public function __invoke(CreateOrderDTO $dto): Order
    {
        return DB::transaction(function () use ($dto) {
            $order = Order::create([
                'user_id' => $dto->userId,
                'total' => $dto->total,
                'status' => OrderStatus::Pending,
            ]);

            $order->items()->createMany(
                array_map(fn(OrderItemDTO $item) => $item->toArray(), $dto->items)
            );

            OrderCreated::dispatch($order);

            return $order;
        });
    }
}

// Usage - in controller
$order = app(CreateOrder::class)($dto);

// Usage - in job
$order = app(CreateOrder::class)($dto);

// Usage - in artisan command
$order = app(CreateOrder::class)($dto);
```

#### Service vs Action Decision

| Scenario                                  | Use           |
| ----------------------------------------- | ------------- |
| Multiple related operations on one domain | Service class |
| Single operation, reused across contexts  | Action class  |
| Simple CRUD with no business rules        | Controller    |
| Side effect triggered by domain event     | Listener      |

### 3. DTOs (Data Transfer Objects)

Use `readonly` classes for DTOs. Avoid passing raw arrays between layers.

```php
// Bad - passing raw array between layers
$this->orderService->create($request->all()); // no type safety, mass assignment risk

// Good - typed DTO
$this->orderService->create(CreateOrderDTO::fromRequest($request));
```

```php
readonly class CreateOrderDTO
{
    public function __construct(
        public int $userId,
        public string $total,
        /** @var OrderItemDTO[] */
        public array $items,
    ) {}

    public static function fromRequest(StoreOrderRequest $request): self
    {
        return new self(
            userId: $request->user()->id,
            total: $request->validated('total'),
            items: array_map(
                fn(array $item) => OrderItemDTO::from($item),
                $request->validated('items'),
            ),
        );
    }

    public function toArray(): array
    {
        return [
            'user_id' => $this->userId,
            'total' => $this->total,
        ];
    }
}

readonly class OrderItemDTO
{
    public function __construct(
        public string $productName,
        public int $quantity,
        public string $unitPrice,
    ) {}

    public static function from(array $data): self
    {
        return new self(
            productName: $data['product_name'],
            quantity: $data['quantity'],
            unitPrice: $data['unit_price'],
        );
    }

    public function toArray(): array
    {
        return [
            'product_name' => $this->productName,
            'quantity' => $this->quantity,
            'unit_price' => $this->unitPrice,
        ];
    }
}
```

#### Alternative: spatie/laravel-data

For projects using `spatie/laravel-data`, DTOs also handle validation and transformation:

```php
use Spatie\LaravelData\Data;

class CreateOrderData extends Data
{
    public function __construct(
        public int $userId,
        #[Min(0.01)]
        public float $total,
        /** @var OrderItemData[] */
        #[DataCollectionOf(OrderItemData::class)]
        public array $items,
    ) {}
}
```

### 4. REPOSITORY PATTERN

Use repositories when you need to abstract data access for testability or when switching between Eloquent and raw queries.

```php
// Bad - query logic scattered across controllers and services
class OrderController extends Controller
{
    public function index(Request $request): OrderCollection
    {
        // Same query duplicated in ReportService, ExportCommand, etc.
        $orders = Order::where('user_id', $request->user()->id)
            ->with('items')
            ->latest()
            ->paginate(15);
        return new OrderCollection($orders);
    }
}

// Good - centralized in repository
class OrderController extends Controller
{
    public function __construct(
        private readonly OrderRepositoryInterface $orders,
    ) {}

    public function index(Request $request): OrderCollection
    {
        return new OrderCollection($this->orders->findByUser($request->user()->id));
    }
}
```

```php
// Interface
interface OrderRepositoryInterface
{
    public function findById(int $id): ?Order;
    public function findByUser(int $userId, int $perPage = 15): LengthAwarePaginator;
    public function create(array $data): Order;
}

// Eloquent implementation
class EloquentOrderRepository implements OrderRepositoryInterface
{
    public function findById(int $id): ?Order
    {
        return Order::with('items')->find($id);
    }

    public function findByUser(int $userId, int $perPage = 15): LengthAwarePaginator
    {
        return Order::where('user_id', $userId)
            ->with('items')
            ->latest()
            ->paginate($perPage);
    }

    public function create(array $data): Order
    {
        return Order::create($data);
    }
}

// Service provider binding
$this->app->bind(OrderRepositoryInterface::class, EloquentOrderRepository::class);
```

#### When to Use Repository vs Direct Eloquent

| Scenario                            | Approach        |
| ----------------------------------- | --------------- |
| Standard CRUD, single database      | Direct Eloquent |
| Complex queries needing testability | Repository      |
| Multiple data sources (API + DB)    | Repository      |
| Team prefers explicit data layer    | Repository      |
| Simple project, small team          | Direct Eloquent |

### 5. DEPENDENCY INJECTION

Use constructor injection via Laravel container. Avoid `app()` helper in business logic.

```php
// Bad - service locator
class OrderService
{
    public function create(array $data): Order
    {
        $payment = app(PaymentService::class); // hidden dependency
        $payment->charge($data['total']);
    }
}

// Good - constructor injection
class OrderService
{
    public function __construct(
        private readonly PaymentService $paymentService,
    ) {}

    public function create(array $data): Order
    {
        $this->paymentService->charge($data['total']);
    }
}
```

#### Service Provider Registration

```php
class AppServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        // Interface binding
        $this->app->bind(OrderRepositoryInterface::class, EloquentOrderRepository::class);

        // Singleton (shared instance)
        $this->app->singleton(PaymentGateway::class, fn() =>
            new StripePaymentGateway(config('services.stripe.key'))
        );

        // Contextual binding
        $this->app->when(OrderService::class)
            ->needs(PaymentGateway::class)
            ->give(StripePaymentGateway::class);
    }
}
```

### 6. EVENTS AND LISTENERS

Use events for decoupled side effects. Never call unrelated domains directly from services.

```php
// Bad - direct cross-domain call inside order service
class OrderService
{
    public function __construct(
        private readonly EmailService $emailService,
        private readonly InventoryService $inventoryService,
        private readonly AnalyticsService $analyticsService,
    ) {}

    public function create(CreateOrderDTO $dto): Order
    {
        $order = Order::create($dto->toArray());
        $this->emailService->sendConfirmation($order);       // cross-domain
        $this->inventoryService->decrementStock($order);      // cross-domain
        $this->analyticsService->trackPurchase($order);       // cross-domain
        return $order;
    }
}

// Good - dispatch event, listeners handle side effects independently
class OrderService
{
    public function create(CreateOrderDTO $dto): Order
    {
        return DB::transaction(function () use ($dto) {
            $order = Order::create($dto->toArray());
            OrderCreated::dispatch($order);
            return $order;
        });
    }
}
```

```php
// Event
class OrderCreated
{
    use Dispatchable, SerializesModels;

    public function __construct(
        public readonly Order $order,
    ) {}
}

// Listener - notification
class SendOrderConfirmation
{
    public function handle(OrderCreated $event): void
    {
        $event->order->user->notify(new OrderConfirmationNotification($event->order));
    }
}

// Listener - queue job dispatch (dispatch AFTER commit)
class ProcessOrderPayment
{
    public function handle(OrderCreated $event): void
    {
        ProcessPayment::dispatch($event->order->id);
    }

    public bool $afterCommit = true;
}

// Registration in EventServiceProvider or via attribute
#[AsEventListener]
class SendOrderConfirmation { ... }
```

#### Event vs Direct Call Decision

| Scenario                                | Use         |
| --------------------------------------- | ----------- |
| Same domain, same transaction           | Direct call |
| Cross-domain side effect (notification) | Event       |
| Side effect can fail independently      | Event + job |
| Ordering matters between side effects   | Direct call |
| Multiple listeners for same trigger     | Event       |

### WHEN TO EXTRACT

| Signal                                               | Extract To                |
| ---------------------------------------------------- | ------------------------- |
| Controller method > 10-15 lines of business logic    | Service or Action         |
| Same logic in 2+ places (controller, job, command)   | Action class              |
| Multiple related operations on one domain            | Service class             |
| Side effect for another domain (email, notification) | Event + Listener          |
| Complex query used in multiple places                | Repository or query scope |

### FILE ORGANIZATION

```
app/
  Services/OrderService.php       # Multi-operation domain services
  Actions/CreateOrder.php          # Single-responsibility reusable actions
  DTOs/CreateOrderDTO.php          # Readonly data transfer objects
  Events/OrderCreated.php          # Domain events
  Listeners/SendOrderConfirmation.php  # Event listeners
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

- Business logic in controllers (fat controllers)
- Business logic in Eloquent accessors/mutators (fat models)
- Passing raw `$request` arrays between layers (use DTOs)
- `app()` / `resolve()` in business logic (use constructor injection)
- God services with 20+ methods (split into actions or focused services)
- Direct cross-domain calls from services (use events for decoupling)
- Dispatching jobs inside DB transactions (use `afterCommit`)
- Anemic services that just proxy Eloquent calls (no value added)
- Circular service dependencies (indicates wrong domain boundary)
