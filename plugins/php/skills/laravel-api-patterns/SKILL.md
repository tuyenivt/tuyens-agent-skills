---
name: laravel-api-patterns
description: "Laravel API patterns - resource controllers, route model binding, form requests, API Resources, middleware, API versioning, pagination, and exception handling for Laravel 12+."
metadata:
  category: backend
  tags: [php, laravel, api, controllers, form-requests, api-resources, middleware]
user-invocable: false
---

## 1. RESOURCE CONTROLLERS

Thin controllers that validate, delegate, and respond. No business logic.

```php
class OrderController extends Controller
{
    public function __construct(
        private readonly OrderService $orderService,
    ) {}

    public function index(Request $request): AnonymousResourceCollection
    {
        $orders = Order::where('user_id', $request->user()->id)
            ->with('items')
            ->latest()
            ->paginate();

        return OrderResource::collection($orders);
    }

    public function store(StoreOrderRequest $request): OrderResource
    {
        $order = $this->orderService->create(
            CreateOrderDTO::fromRequest($request)
        );

        return new OrderResource($order->load('items'));
    }

    public function show(Order $order): OrderResource
    {
        $this->authorize('view', $order);
        return new OrderResource($order->load('items'));
    }

    public function update(UpdateOrderRequest $request, Order $order): OrderResource
    {
        $order = $this->orderService->update($order, $request->validated());
        return new OrderResource($order);
    }

    public function destroy(Order $order): JsonResponse
    {
        $this->authorize('delete', $order);
        $this->orderService->cancel($order);
        return response()->json(null, 204);
    }
}
```

## 2. ROUTE MODEL BINDING

```php
// routes/api.php
Route::apiResource('orders', OrderController::class);

// Implicit binding (auto-resolves by {order} parameter)
public function show(Order $order): OrderResource { ... }

// Scoped binding (order must belong to user)
Route::apiResource('users.orders', OrderController::class)->scoped([
    'order' => 'id',
]);

// Custom key
Route::get('/orders/{order:uuid}', [OrderController::class, 'show']);

// Soft-deleted model binding
Route::get('/orders/{order}', [OrderController::class, 'show'])->withTrashed();
```

## 3. FORM REQUESTS

Validate and authorize in dedicated request classes. Never validate in controllers or services.

```php
class StoreOrderRequest extends FormRequest
{
    public function authorize(): bool
    {
        return $this->user()->can('create', Order::class);
    }

    public function rules(): array
    {
        return [
            'total' => ['required', 'numeric', 'min:0.01', 'max:99999.99'],
            'items' => ['required', 'array', 'min:1'],
            'items.*.product_name' => ['required', 'string', 'max:255'],
            'items.*.quantity' => ['required', 'integer', 'min:1', 'max:1000'],
            'items.*.unit_price' => ['required', 'numeric', 'min:0.01'],
            'shipping_address' => ['required', 'string', 'max:500'],
            'notes' => ['nullable', 'string', 'max:1000'],
        ];
    }

    public function messages(): array
    {
        return [
            'items.min' => 'An order must have at least one item.',
            'total.max' => 'Order total cannot exceed 99,999.99.',
        ];
    }
}

class UpdateOrderRequest extends FormRequest
{
    public function authorize(): bool
    {
        return $this->user()->can('update', $this->route('order'));
    }

    public function rules(): array
    {
        return [
            'shipping_address' => ['sometimes', 'string', 'max:500'],
            'notes' => ['nullable', 'string', 'max:1000'],
        ];
    }
}
```

## 4. API RESOURCES

Transform Eloquent models to JSON responses. Never return raw models from controllers.

```php
class OrderResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'status' => $this->status->value,
            'total' => $this->total,
            'shipping_address' => $this->shipping_address,
            'items' => OrderItemResource::collection($this->whenLoaded('items')),
            'items_count' => $this->whenCounted('items'),
            'user' => new UserResource($this->whenLoaded('user')),
            'created_at' => $this->created_at->toIso8601String(),
            'updated_at' => $this->updated_at->toIso8601String(),
        ];
    }
}

class OrderItemResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'product_name' => $this->product_name,
            'quantity' => $this->quantity,
            'unit_price' => $this->unit_price,
            'subtotal' => $this->quantity * $this->unit_price,
        ];
    }
}
```

### Resource Collections with Meta

```php
class OrderCollection extends ResourceCollection
{
    public function toArray(Request $request): array
    {
        return [
            'data' => $this->collection,
            'meta' => [
                'total_orders' => $this->collection->count(),
            ],
        ];
    }
}
```

### Conditional Attributes

```php
// Only include when relationship is loaded
'items' => OrderItemResource::collection($this->whenLoaded('items')),

// Only include when aggregate is loaded
'items_count' => $this->whenCounted('items'),
'items_sum_quantity' => $this->whenAggregated('items', 'quantity', 'sum'),

// Conditional on request context
'secret_notes' => $this->when($request->user()->isAdmin(), $this->secret_notes),
```

## 5. MIDDLEWARE

```php
// Route middleware
Route::middleware(['auth:sanctum', 'throttle:api'])->group(function () {
    Route::apiResource('orders', OrderController::class);
});

// Custom middleware
class EnsureOrderOwner
{
    public function handle(Request $request, Closure $next): Response
    {
        $order = $request->route('order');

        if ($order->user_id !== $request->user()->id) {
            abort(403, 'You do not own this order.');
        }

        return $next($request);
    }
}

// Registration in bootstrap/app.php (Laravel 11+)
->withMiddleware(function (Middleware $middleware) {
    $middleware->alias([
        'order.owner' => EnsureOrderOwner::class,
    ]);
})
```

## 6. API VERSIONING

```php
// Route prefix versioning (recommended)
Route::prefix('v1')->group(function () {
    Route::apiResource('orders', V1\OrderController::class);
});

Route::prefix('v2')->group(function () {
    Route::apiResource('orders', V2\OrderController::class);
});

// Controller namespace organization
app/Http/Controllers/
    V1/
        OrderController.php
    V2/
        OrderController.php
```

## 7. PAGINATION

```php
// Offset pagination (default - good for most cases)
Order::paginate(15);
// Returns: data, current_page, last_page, per_page, total

// Cursor pagination (better for large datasets, infinite scroll)
Order::orderBy('id')->cursorPaginate(15);
// Returns: data, next_cursor, prev_cursor

// Simple pagination (no total count - faster)
Order::simplePaginate(15);
// Returns: data, current_page, per_page (no total/last_page)
```

| Method             | Total Count | Performance    | Use When                        |
| ------------------ | ----------- | -------------- | ------------------------------- |
| `paginate()`       | Yes         | Slower (COUNT) | Admin panels, known small sets  |
| `simplePaginate()` | No          | Faster         | "Load more" button, lists       |
| `cursorPaginate()` | No          | Fastest        | Infinite scroll, large datasets |

## 8. EXCEPTION HANDLING

```php
// bootstrap/app.php (Laravel 11+)
->withExceptions(function (Exceptions $exceptions) {
    $exceptions->render(function (ModelNotFoundException $e, Request $request) {
        if ($request->expectsJson()) {
            return response()->json([
                'error' => 'Resource not found',
                'type' => 'not_found',
            ], 404);
        }
    });

    $exceptions->render(function (AuthorizationException $e, Request $request) {
        if ($request->expectsJson()) {
            return response()->json([
                'error' => 'Unauthorized',
                'type' => 'forbidden',
            ], 403);
        }
    });
})
```

### Custom API Exceptions

```php
class InsufficientStockException extends HttpException
{
    public function __construct(string $productName, int $requested, int $available)
    {
        parent::__construct(
            statusCode: 422,
            message: "Insufficient stock for {$productName}: requested {$requested}, available {$available}",
        );
    }
}
```

## 9. ANTI-PATTERNS

- ❌ Business logic in controllers (delegate to services/actions)
- ❌ Returning raw Eloquent models from controllers (use API Resources)
- ❌ Inline validation in controllers (use Form Requests)
- ❌ `$request->all()` passed to `Model::create()` (mass assignment risk)
- ❌ Missing `authorize()` in Form Requests (defaults to `false` for safety)
- ❌ N+1 in API Resources (always eager load relationships before passing to Resource)
- ❌ Hardcoded pagination limits (allow per_page parameter with max cap)
- ❌ Returning 200 for errors or 500 for validation failures (use correct HTTP status codes)
- ❌ `abort(500)` for expected business errors (use 4xx with descriptive messages)
