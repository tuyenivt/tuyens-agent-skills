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

- API Resources for every response; never return raw Eloquent models
- Form Requests for validation; `authorize()` returns an explicit boolean (defaults to `false`)
- Controllers stay thin: validate, delegate to service/action, return Resource
- List endpoints paginate; enforce a server-side `per_page` cap (`min:1|max:100`)
- Webhooks: verify signature, respond 200 fast, process async, dedupe on provider event ID

## Patterns

### Resource controllers

Thin: Form Request validates, service performs work, Resource shapes output. No inline queries.

```php
class OrderController extends Controller {
    public function __construct(private readonly OrderService $orders) {}

    public function index(IndexOrderRequest $request): AnonymousResourceCollection {
        return OrderResource::collection($this->orders->listForUser($request));
    }

    public function store(StoreOrderRequest $request): OrderResource {
        $order = $this->orders->create(CreateOrderDTO::fromRequest($request));
        return new OrderResource($order->load('items'));
    }

    public function show(Order $order): OrderResource {
        $this->authorize('view', $order);
        return new OrderResource($order->load('items'));
    }

    public function destroy(Order $order): JsonResponse {
        $this->authorize('delete', $order);
        $this->orders->cancel($order);
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
}

// Update authorizes against the bound model
class UpdateOrderRequest extends FormRequest {
    public function authorize(): bool {
        return $this->user()->can('update', $this->route('order'));
    }
}

// List with per_page cap
class IndexOrderRequest extends FormRequest {
    public function authorize(): bool { return true; }
    public function rules(): array {
        return [
            'per_page' => ['integer', 'min:1', 'max:100'],
            'status' => ['nullable', Rule::enum(OrderStatus::class)],
            'sort' => ['nullable', Rule::in(['id', 'created_at', 'total'])],
        ];
    }
}
```

### API Resources

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

// bootstrap/app.php (Laravel 11+)
->withMiddleware(function (Middleware $m) {
    $m->alias(['order.owner' => EnsureOrderOwner::class]);
})
```

### Pagination

| Method             | Total | Performance    | Use When                        |
| ------------------ | ----- | -------------- | ------------------------------- |
| `paginate()`       | Yes   | Slower (COUNT) | Admin panels, known small sets  |
| `simplePaginate()` | No    | Faster         | "Load more" lists               |
| `cursorPaginate()` | No    | Fastest        | Infinite scroll, large tables   |

### Versioning

Route prefix + namespace (`Route::prefix('v1')->group(...)` -> `App\Http\Controllers\V1\OrderController`). Prefer over header versioning.

### Exception handling

Centralize in `bootstrap/app.php` (Laravel 11+); never per-controller `try/catch` wrapping framework exceptions.

```php
->withExceptions(function (Exceptions $exceptions) {
    $exceptions->render(function (ModelNotFoundException $e, Request $r) {
        if ($r->expectsJson()) {
            return response()->json(['error' => 'Resource not found'], 404);
        }
    });
    $exceptions->render(function (AuthorizationException $e, Request $r) {
        if ($r->expectsJson()) {
            return response()->json(['error' => 'Unauthorized'], 403);
        }
    });
})

// Domain exceptions extend HttpException with correct status
class InsufficientStockException extends HttpException {
    public function __construct(string $product, int $requested, int $available) {
        parent::__construct(422, "Insufficient stock for {$product}: requested {$requested}, available {$available}");
    }
}
```

### Search and filtering

`when()` keeps optional filters declarative. Push into the service / query class; the controller stays thin.

```php
public function listForUser(IndexOrderRequest $request): LengthAwarePaginator {
    return Order::query()
        ->where('user_id', $request->user()->id)
        ->when($request->query('status'), fn($q, $v) => $q->where('status', $v))
        ->when($request->query('search'), fn($q, $v) => $q->whereFullText(['title'], $v))
        ->with(['items:id,order_id,qty'])
        ->orderBy($request->validated('sort', 'id'))
        ->cursorPaginate($request->integer('per_page', 25));
}
```

### Webhook controllers

External callbacks differ from API endpoints: no Sanctum (signature verify instead), respond 200 fast, process async, dedupe on provider event ID.

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
            Log::warning('Stripe webhook signature failed', ['ip' => $request->ip()]);
            return response()->json(['error' => 'Invalid signature'], 403);
        }

        ProcessStripeEvent::dispatch($event->id, $event->type, $event->data->object->toArray());
        return response()->json(['received' => true]);
    }
}

// Route: no auth, dedicated rate limit, exempt from CSRF
Route::post('/webhooks/stripe', StripeWebhookController::class)->middleware('throttle:webhook');
RateLimiter::for('webhook', fn(Request $r) => Limit::perMinute(120)->by($r->ip()));
```

Idempotency: persist `$event->id` in a `webhook_events` table with a unique index; in the queued job, `WebhookEvent::firstOrCreate(...)` and skip if already present.

## Output Format

For **design** prompts:

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

For **audit** prompts:

```
## Findings
| Location | Issue | Fix |
```

## Avoid

- Raw Eloquent models from controllers; inline `$request->validate` or `$request->all()` to `Model::create`
- Missing `authorize()` in Form Requests (defaults to `false`)
- N+1 in Resources - eager load before passing to Resource
- Hardcoded `per_page` with no cap (DoS via huge page sizes)
- Wrong status codes (200 on errors, 500 on validation, `abort(500)` for business errors)
- Webhooks: synchronous processing, Sanctum auth, missing signature verification
