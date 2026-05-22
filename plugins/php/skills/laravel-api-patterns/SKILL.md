---
name: laravel-api-patterns
description: "Laravel API patterns: resource controllers, route model binding, Form Requests, API Resources, middleware, versioning, pagination, exception handling."
metadata:
  category: backend
  tags: [php, laravel, api, controllers, form-requests, api-resources, middleware]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- REST endpoints: resource controllers, Form Requests, API Resources, route model binding
- List endpoints: pagination, filtering, search
- Error responses and exception rendering
- NOT for: business logic (use `laravel-service-patterns`), queries (use `laravel-eloquent-patterns`)

## Rules

- API Resources for all responses; never return raw Eloquent models (leaks columns, no shape control)
- Form Requests for validation; `$request->validated()` not `$request->all()` (mass assignment risk)
- Controllers stay thin - delegate to services/actions; list endpoints paginate
- `authorize()` on Form Requests defaults to `false` - set explicitly
- Webhook endpoints: verify signature, respond 200 fast, process async, ensure idempotency

## Patterns

### Resource controllers

Thin: validate via Form Request, delegate to service, return Resource.

```php
class OrderController extends Controller {
    public function __construct(private readonly OrderService $orderService) {}

    public function index(Request $request): AnonymousResourceCollection {
        $orders = Order::where('user_id', $request->user()->id)
            ->with('items')->latest()->paginate();
        return OrderResource::collection($orders);
    }

    public function store(StoreOrderRequest $request): OrderResource {
        $order = $this->orderService->create(CreateOrderDTO::fromRequest($request));
        return new OrderResource($order->load('items'));
    }

    public function show(Order $order): OrderResource {
        $this->authorize('view', $order);
        return new OrderResource($order->load('items'));
    }

    public function destroy(Order $order): JsonResponse {
        $this->authorize('delete', $order);
        $this->orderService->cancel($order);
        return response()->json(null, 204);
    }
}
```

### Route model binding

```php
Route::apiResource('orders', OrderController::class);

// Scoped - {order} must belong to {user}
Route::apiResource('users.orders', OrderController::class)->scoped(['order' => 'id']);

// Custom key
Route::get('/orders/{order:uuid}', [OrderController::class, 'show']);

// Include soft-deleted
Route::get('/orders/{order}', [...])->withTrashed();
```

### Form Requests

```php
class StoreOrderRequest extends FormRequest {
    public function authorize(): bool {
        return $this->user()->can('create', Order::class);
    }

    public function rules(): array {
        return [
            'total' => ['required', 'numeric', 'min:0.01', 'max:99999.99'],
            'items' => ['required', 'array', 'min:1'],
            'items.*.product_name' => ['required', 'string', 'max:255'],
            'items.*.quantity' => ['required', 'integer', 'min:1', 'max:1000'],
            'items.*.unit_price' => ['required', 'numeric', 'min:0.01'],
        ];
    }

    public function messages(): array {
        return ['items.min' => 'An order must have at least one item.'];
    }
}

// Update: authorize against the bound model
class UpdateOrderRequest extends FormRequest {
    public function authorize(): bool {
        return $this->user()->can('update', $this->route('order'));
    }
    public function rules(): array {
        return ['shipping_address' => ['sometimes', 'string', 'max:500']];
    }
}
```

### API Resources

Control output shape and conditional loading.

```php
class OrderResource extends JsonResource {
    public function toArray(Request $request): array {
        return [
            'id' => $this->id,
            'status' => $this->status->value,                   // backed enum
            'total' => $this->total,
            'items' => OrderItemResource::collection($this->whenLoaded('items')),
            'items_count' => $this->whenCounted('items'),
            'user' => new UserResource($this->whenLoaded('user')),
            'secret_notes' => $this->when($request->user()->isAdmin(), $this->secret_notes),
            'created_at' => $this->created_at->toIso8601String(),
        ];
    }
}
```

| Helper                              | Behavior                                |
| ----------------------------------- | --------------------------------------- |
| `whenLoaded('rel')`                 | Include only if eager-loaded            |
| `whenCounted('rel')`                | Include only if `withCount` was called  |
| `whenAggregated('rel', 'col', 'sum')` | Include only if aggregate was loaded  |
| `when($cond, $value)`               | Conditional on request context          |

### Middleware

```php
Route::middleware(['auth:sanctum', 'throttle:api'])->group(function () {
    Route::apiResource('orders', OrderController::class);
});

class EnsureOrderOwner {
    public function handle(Request $request, Closure $next): Response {
        if ($request->route('order')->user_id !== $request->user()->id) {
            abort(403, 'You do not own this order.');
        }
        return $next($request);
    }
}

// bootstrap/app.php (Laravel 11+)
->withMiddleware(function (Middleware $middleware) {
    $middleware->alias(['order.owner' => EnsureOrderOwner::class]);
})
```

### Versioning

Route prefix + controller namespace. Prefer over header versioning for simplicity.

```php
Route::prefix('v1')->group(fn() => Route::apiResource('orders', V1\OrderController::class));
Route::prefix('v2')->group(fn() => Route::apiResource('orders', V2\OrderController::class));
// app/Http/Controllers/V1/OrderController.php, V2/OrderController.php
```

### Pagination

| Method             | Total | Performance    | Use When                        |
| ------------------ | ----- | -------------- | ------------------------------- |
| `paginate()`       | Yes   | Slower (COUNT) | Admin panels, known small sets  |
| `simplePaginate()` | No    | Faster         | "Load more" lists               |
| `cursorPaginate()` | No    | Fastest        | Infinite scroll, large datasets |

```php
Order::orderBy('id')->cursorPaginate($request->integer('per_page', 15));
```

### Exception handling

```php
// bootstrap/app.php (Laravel 11+)
->withExceptions(function (Exceptions $exceptions) {
    $exceptions->render(function (ModelNotFoundException $e, Request $request) {
        if ($request->expectsJson()) {
            return response()->json(['error' => 'Resource not found', 'type' => 'not_found'], 404);
        }
    });
    $exceptions->render(function (AuthorizationException $e, Request $request) {
        if ($request->expectsJson()) {
            return response()->json(['error' => 'Unauthorized', 'type' => 'forbidden'], 403);
        }
    });
})

// Domain exception with correct status code
class InsufficientStockException extends HttpException {
    public function __construct(string $product, int $requested, int $available) {
        parent::__construct(422, "Insufficient stock for {$product}: requested {$requested}, available {$available}");
    }
}
```

### Search and filtering

`when()` keeps optional filters declarative.

```php
public function index(Request $request): AnonymousResourceCollection {
    $products = Product::query()
        ->when($request->query('category_id'), fn($q, $v) => $q->where('category_id', $v))
        ->when($request->query('min_price'),   fn($q, $v) => $q->where('price', '>=', $v))
        ->when($request->boolean('active_only'), fn($q) => $q->where('is_active', true))
        ->when($request->query('search'), fn($q, $v) => $q->whereFullText(['name', 'description'], $v))
        ->with('category')->latest()
        ->paginate($request->integer('per_page', 15));

    return ProductResource::collection($products);
}
```

### Webhook controllers

External callbacks differ from API endpoints: no Sanctum auth (signature verify instead), respond 200 immediately (provider retries on non-2xx), process async, ensure idempotency.

```php
class StripeWebhookController extends Controller {
    public function __invoke(Request $request): JsonResponse {
        try {
            $event = \Stripe\Webhook::constructEvent(
                $request->getContent(),
                $request->header('Stripe-Signature'),
                config('services.stripe.webhook_secret'),
            );
        } catch (\Stripe\Exception\SignatureVerificationException $e) {
            return response()->json(['error' => 'Invalid signature'], 403);
        }

        ProcessStripeEvent::dispatch($event->type, $event->data->object->toArray());
        return response()->json(['received' => true]);
    }
}

// Route - no auth middleware, dedicated rate limit, exclude from CSRF
Route::post('/webhooks/stripe', StripeWebhookController::class)->middleware('throttle:webhook');

RateLimiter::for('webhook', fn(Request $r) => Limit::perMinute(120)->by($r->ip()));
```

Idempotency: persist `$event->id` and skip duplicates in the queued job.

## Output Format

```
## Endpoints
| Method | Path | Controller Action | Request Class | Response Class | Status |

## Validation Rules
[Form Request class with rules per endpoint]

## Response Structure
[API Resource fields with types and conditional loading]

## Error Responses
| Error Type | HTTP Status | Response Body |
```

## Avoid

- Raw Eloquent models from controllers (leaks columns, no shape control)
- Inline validation or `$request->all()` to `Model::create()` (mass assignment)
- Missing `authorize()` in Form Requests (defaults to `false` - locks legitimate users out)
- N+1 in Resources - eager load before passing to Resource
- Hardcoded `per_page` with no cap (DoS via huge page sizes)
- Wrong status codes: 200 on errors, 500 on validation failures, `abort(500)` for business errors
- Webhooks: synchronous processing, Sanctum auth, missing signature verification
