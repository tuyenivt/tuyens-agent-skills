---
name: laravel-service-patterns
description: "Business logic patterns for Laravel - service classes, action classes, DTOs with readonly classes, repository pattern, dependency injection via Laravel container, and events/listeners for decoupled side effects."
metadata:
  category: backend
  tags: [php, laravel, services, actions, dto, dependency-injection, events]
user-invocable: false
---

## 1. SERVICE CLASSES

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

## 2. ACTION CLASSES

Use action classes for single-responsibility operations reused in multiple contexts (controller, job, command).

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

### Service vs Action Decision

| Scenario                                  | Use           |
| ----------------------------------------- | ------------- |
| Multiple related operations on one domain | Service class |
| Single operation, reused across contexts  | Action class  |
| Simple CRUD with no business rules        | Controller    |
| Side effect triggered by domain event     | Listener      |

## 3. DTOs (Data Transfer Objects)

Use `readonly` classes for DTOs. Avoid passing raw arrays between layers.

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

### Alternative: spatie/laravel-data

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

## 4. REPOSITORY PATTERN

Use repositories when you need to abstract data access for testability or when switching between Eloquent and raw queries.

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

### When to Use Repository vs Direct Eloquent

| Scenario                            | Approach        |
| ----------------------------------- | --------------- |
| Standard CRUD, single database      | Direct Eloquent |
| Complex queries needing testability | Repository      |
| Multiple data sources (API + DB)    | Repository      |
| Team prefers explicit data layer    | Repository      |
| Simple project, small team          | Direct Eloquent |

## 5. DEPENDENCY INJECTION

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

### Service Provider Registration

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

## 6. EVENTS AND LISTENERS

Use events for decoupled side effects. Never call unrelated domains directly from services.

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

### Event vs Direct Call Decision

| Scenario                                | Use         |
| --------------------------------------- | ----------- |
| Same domain, same transaction           | Direct call |
| Cross-domain side effect (notification) | Event       |
| Side effect can fail independently      | Event + job |
| Ordering matters between side effects   | Direct call |
| Multiple listeners for same trigger     | Event       |

## 7. ANTI-PATTERNS

- ❌ Business logic in controllers (fat controllers)
- ❌ Business logic in Eloquent accessors/mutators (fat models)
- ❌ Passing raw `$request` arrays between layers (use DTOs)
- ❌ `app()` / `resolve()` in business logic (use constructor injection)
- ❌ God services with 20+ methods (split into actions or focused services)
- ❌ Direct cross-domain calls from services (use events for decoupling)
- ❌ Dispatching jobs inside DB transactions (use `afterCommit`)
- ❌ Anemic services that just proxy Eloquent calls (no value added)
- ❌ Circular service dependencies (indicates wrong domain boundary)
