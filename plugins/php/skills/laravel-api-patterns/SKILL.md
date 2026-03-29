---
name: laravel-api-patterns
description: "Laravel API patterns - resource controllers, route model binding, form requests, API Resources, middleware, API versioning, pagination, filtering, and exception handling for Laravel 12+."
metadata:
  category: backend
  tags: [php, laravel, api, controllers, form-requests, api-resources, middleware]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building REST API endpoints for Laravel applications
- Designing resource controllers, form requests, API resources
- Implementing pagination, filtering, and search on list endpoints
- Structuring exception handling and error responses
- NOT for: business logic (use laravel-service-patterns), database queries (use laravel-eloquent-patterns)

## Rules

- API Resources for all responses - never return raw Eloquent models
- Form Requests for all validation - never validate inline in controllers
- Controllers must be thin - delegate business logic to services/actions
- List endpoints must be paginated
- Use `$request->validated()` not `$request->all()` when passing to models

## Patterns

### 1. RESOURCE CONTROLLERS

Thin controllers that validate, delegate, and respond. No business logic.

```php
// Bad - fat controller with inline logic, no Form Request, returns raw model
class OrderController extends Controller
{
    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'total' => 'required|numeric',
            'items' => 'required|array',
        ]);

        $order = new Order();
        $order->user_id = $request->user()->id;
        $order->total = $data['total'];
        $order->status = 'pending';
        $order->save();

        foreach ($data['items'] as $item) {
            $order->items()->create($item);
        }

        return response()->json($order);
    }
}
```

```php
// Good - thin controller, Form Request validation, service delegation, API Resource response
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

### 2. ROUTE MODEL BINDING

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

### 3. FORM REQUESTS

Validate and authorize in dedicated request classes. Never validate in controllers or services.

```php
// Bad - inline validation in controller
class OrderController extends Controller
{
    public function store(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'total' => 'required|numeric|min:0.01',
            'items' => 'required|array|min:1',
            'items.*.product_name' => 'required|string|max:255',
        ]);

        $order = Order::create($request->all()); // mass assignment risk
        return response()->json($order);
    }
}
```

```php
// Good - dedicated Form Request class
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

### 4. API RESOURCES

Transform Eloquent models to JSON responses. Never return raw models from controllers.

```php
// Bad - returning raw Eloquent model from controller
public function show(Order $order): JsonResponse
{
    return response()->json($order);
    // Exposes all columns, no control over format, leaks internal structure
}
```

```php
// Good - API Resource with controlled output and conditional loading
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

#### Resource Collections with Meta

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

#### Conditional Attributes

```php
// Only include when relationship is loaded
'items' => OrderItemResource::collection($this->whenLoaded('items')),

// Only include when aggregate is loaded
'items_count' => $this->whenCounted('items'),
'items_sum_quantity' => $this->whenAggregated('items', 'quantity', 'sum'),

// Conditional on request context
'secret_notes' => $this->when($request->user()->isAdmin(), $this->secret_notes),
```

### 5. MIDDLEWARE

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

### 6. API VERSIONING

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

### 7. PAGINATION

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

### 8. EXCEPTION HANDLING

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

#### Custom API Exceptions

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

### 9. SEARCH AND FILTERING

Use `when()` for conditional query filters and scoped filters on list endpoints.

```php
// Bad - hardcoded filters, no flexibility
public function index(): AnonymousResourceCollection
{
    $products = Product::where('is_active', true)->paginate();
    return ProductResource::collection($products);
}
```

```php
// Good - conditional filters with when()
public function index(Request $request): AnonymousResourceCollection
{
    $products = Product::query()
        ->when($request->query('category_id'), fn($q, $v) => $q->where('category_id', $v))
        ->when($request->query('min_price'), fn($q, $v) => $q->where('price', '>=', $v))
        ->when($request->query('max_price'), fn($q, $v) => $q->where('price', '<=', $v))
        ->when($request->boolean('active_only'), fn($q) => $q->where('is_active', true))
        ->when($request->query('search'), fn($q, $v) => $q->whereFullText(['name', 'description'], $v))
        ->with('category')
        ->latest()
        ->paginate($request->integer('per_page', 15));

    return ProductResource::collection($products);
}
```

### 10. WEBHOOK CONTROLLERS

Webhook endpoints receive external callbacks (Stripe, payment providers, etc.). They differ from standard API endpoints: no auth middleware, signature verification instead, immediate 200 response, async processing.

```php
// Bad - processes webhook synchronously, no signature verification
Route::post('/webhooks/stripe', function (Request $request) {
    $event = json_decode($request->getContent());
    // Process inline - blocks the response, no verification
    $order = Order::find($event->data->object->metadata->order_id);
    $order->update(['status' => 'paid']);
    return response('OK');
});
```

```php
// Good - verify signature, respond fast, process async
class StripeWebhookController extends Controller
{
    public function __invoke(Request $request): JsonResponse
    {
        // 1. Verify signature (see laravel-security-patterns for details)
        $payload = $request->getContent();
        $signature = $request->header('Stripe-Signature');

        try {
            $event = \Stripe\Webhook::constructEvent(
                $payload,
                $signature,
                config('services.stripe.webhook_secret'),
            );
        } catch (\Stripe\Exception\SignatureVerificationException $e) {
            return response()->json(['error' => 'Invalid signature'], 403);
        }

        // 2. Dispatch to queue for async processing
        ProcessStripeEvent::dispatch($event->type, $event->data->object->toArray());

        // 3. Respond 200 immediately - Stripe retries on non-2xx
        return response()->json(['received' => true]);
    }
}
```

```php
// Route - no auth middleware, CSRF excluded
Route::post('/webhooks/stripe', StripeWebhookController::class)
    ->middleware('throttle:webhook');

// Dedicated rate limiter for webhooks
RateLimiter::for('webhook', function (Request $request) {
    return Limit::perMinute(120)->by($request->ip());
});
```

#### Webhook Controller Rules

| Concern        | Pattern                                                  |
| -------------- | -------------------------------------------------------- |
| Authentication | Signature verification, not Sanctum/session              |
| Response time  | Return 200 immediately, process async via queue          |
| Idempotency    | Store processed event IDs, skip duplicates               |
| CSRF           | Exclude from CSRF middleware                             |
| Rate limiting  | Separate limiter (higher than API, lower than unlimited) |
| Retry behavior | Provider retries on non-2xx; ensure idempotency          |

## Output Format

```
## Endpoints
| Method | Path | Controller Action | Request Class | Response Class | Status |

## Validation Rules
[Form Request class with rules for each endpoint]

## Response Structure
[API Resource fields with types and conditional loading]

## Error Responses
| Error Type | HTTP Status | Response Body |
```

## Avoid

- Business logic in controllers (delegate to services/actions)
- Returning raw Eloquent models from controllers (use API Resources)
- Inline validation in controllers (use Form Requests)
- `$request->all()` passed to `Model::create()` (mass assignment risk)
- Missing `authorize()` in Form Requests (defaults to `false` for safety)
- N+1 in API Resources (always eager load relationships before passing to Resource)
- Hardcoded pagination limits (allow per_page parameter with max cap)
- Returning 200 for errors or 500 for validation failures (use correct HTTP status codes)
- `abort(500)` for expected business errors (use 4xx with descriptive messages)
- Processing webhooks synchronously in the controller (dispatch to queue, respond 200 fast)
- Webhook endpoints with auth:sanctum middleware (use signature verification instead)
- Missing webhook signature verification (accepts forged payloads)
