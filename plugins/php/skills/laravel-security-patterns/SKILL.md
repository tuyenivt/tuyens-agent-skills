---
name: laravel-security-patterns
description: "Laravel security patterns: mass assignment, SQL injection, Sanctum/Passport auth, Gates/Policies, CSRF, rate limiting, validation, secrets."
metadata:
  category: backend
  tags: [php, laravel, security, auth, sanctum, policies, owasp]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Authentication (Sanctum tokens or SPA sessions, Passport), authorization (Policies, Gates)
- Hardening input validation, mass assignment, SQL injection, CSRF, rate limiting
- Webhook verification, multi-tenant isolation, secrets handling
- NOT for: infrastructure/network security, encryption at rest, API gateway config

## Rules

- `$fillable` whitelist on every model; `$guarded = []` is a mass-assignment hole
- Pass user input through Eloquent or parameter bindings; never interpolate into SQL
- `Hash::make()` / `Hash::check()` for passwords; md5/sha1 are broken
- `env()` only inside `config/*.php`; elsewhere use `config()` so `config:cache` works
- Validate via Form Requests; authorize via Policies, not inline `auth()->id()` checks
- Rate limit auth routes (login, register, password reset) by IP
- Verify webhook signatures with `hash_equals()` before trusting payloads; record event IDs for idempotency

## Patterns

### Mass assignment

```php
// Bad - any field writable from request
class Order extends Model { protected $guarded = []; }

// Good - explicit whitelist
class Order extends Model {
    protected $fillable = ['user_id', 'status', 'total', 'shipping_address'];
}
```

### SQL injection

```php
// Bad - interpolation
DB::select("SELECT * FROM orders WHERE status = '$status'");
Order::whereRaw("status = '$status'")->get();

// Good - bindings (Eloquent preferred)
Order::where('status', $status)->get();
Order::whereRaw('status = ?', [$status])->get();

// DB::raw is safe only for expressions, not values
Order::select(DB::raw('DATE(created_at) as date'), DB::raw('COUNT(*) as count'))
    ->where('status', $status)
    ->groupByRaw('DATE(created_at)')
    ->get();
```

### Authentication

```php
// Sanctum API tokens with abilities
$token = $user->createToken('api', ['orders:read', 'orders:write']);
return ['token' => $token->plainTextToken];

Route::middleware('auth:sanctum')->apiResource('orders', OrderController::class);
if ($user->tokenCan('orders:write')) { /* ... */ }
```

Sanctum SPA flow (same-site cookie auth):

1. `GET /sanctum/csrf-cookie` - sets `XSRF-TOKEN`
2. `POST /login` - establishes session
3. Subsequent requests carry the session cookie + `X-XSRF-TOKEN` header

```php
// config/sanctum.php
'stateful' => explode(',', env('SANCTUM_STATEFUL_DOMAINS', 'localhost:3000')),
// config/cors.php
'supports_credentials' => true,
```

```php
// Password hashing
$user->password = Hash::make($request->password);
$ok = Hash::check($plaintext, $user->password);
```

| Scenario          | Strategy                              | Package           |
| ----------------- | ------------------------------------- | ----------------- |
| Mobile app API    | Sanctum API tokens                    | laravel/sanctum   |
| SPA (same domain) | Sanctum SPA (session + CSRF)          | laravel/sanctum   |
| Third-party OAuth | Passport with grants                  | laravel/passport  |
| Social login      | Socialite                             | laravel/socialite |
| Tokens + SPA      | Dual Sanctum config (separate guards) | laravel/sanctum   |

### Authorization

```php
// Bad - inline check leaks rule into controller
public function show(Order $order): OrderResource {
    if ($order->user_id !== auth()->id()) abort(403);
    return new OrderResource($order);
}

// Good - policy
public function show(Order $order): OrderResource {
    $this->authorize('view', $order);
    return new OrderResource($order);
}
```

```php
class OrderPolicy {
    public function view(User $user, Order $order): bool {
        return $user->id === $order->user_id;
    }

    public function update(User $user, Order $order): bool {
        return $user->id === $order->user_id
            && $order->status === OrderStatus::Pending;
    }

    public function create(User $user): bool {
        return $user->hasVerifiedEmail();
    }
}

// In Form Request
public function authorize(): bool {
    return $this->user()->can('update', $this->route('order'));
}
```

Use Gates for non-resource permissions (admin area, feature flags):

```php
Gate::define('access-admin', fn(User $u) => $u->is_admin);
Route::middleware('can:access-admin')->group(/* ... */);
```

### CSRF and rate limiting

```php
// CSRF is on by default for web routes; exempt only webhooks
->withMiddleware(function (Middleware $middleware) {
    $middleware->validateCsrfTokens(except: ['webhooks/*']);
})
```

```php
RateLimiter::for('api', fn(Request $r) =>
    Limit::perMinute(60)->by($r->user()?->id ?: $r->ip()));

RateLimiter::for('auth', fn(Request $r) =>
    Limit::perMinute(5)->by($r->ip()));  // strict for login/register

Route::post('/login', LoginController::class)->middleware('throttle:auth');
```

### Input validation

```php
class StoreOrderRequest extends FormRequest {
    public function rules(): array {
        return [
            'email' => ['required', 'email:rfc,dns', 'max:255'],
            'total' => ['required', 'numeric', 'min:0.01', 'max:99999.99'],
            'url'   => ['nullable', 'url:http,https'],  // block javascript:, data:
            'file'  => ['nullable', 'file', 'mimes:pdf,jpg,png', 'max:10240'],
        ];
    }

    protected function prepareForValidation(): void {
        $this->merge(['notes' => strip_tags($this->notes ?? '')]);
    }
}
```

### File uploads

```php
$request->validate([
    'avatar' => ['required', 'image', 'mimes:jpg,png', 'max:2048'],
]);

// Private disk + signed/controller delivery - never public/
$path = $request->file('avatar')->store('avatars', 'private');
return Storage::disk('private')->download($path);
```

### Secrets and env

```php
// Bad - env() outside config breaks config:cache
$key = env('STRIPE_KEY');

// Good - config/services.php reads env; app reads config
'stripe' => ['key' => env('STRIPE_KEY'), 'secret' => env('STRIPE_SECRET')],
$key = config('services.stripe.key');
```

- `.env` is gitignored; `.env.example` holds placeholders only
- `php artisan config:cache` in production (forces all `env()` to live in config)
- `php artisan env:encrypt` for sensitive shared env values (Laravel 9+)

### Session and cookie

```php
// config/session.php
'secure' => true, 'http_only' => true, 'same_site' => 'lax',

// On login / logout
$request->session()->regenerate();   // after successful login
$request->session()->invalidate();   // on logout
$request->session()->regenerateToken();
```

### Webhook signature verification

```php
// Bad - trusts any payload
Route::post('/webhooks/stripe', fn(Request $r) =>
    Order::find($r->json('order_id'))->update(['status' => 'paid']));

// Good - verify before processing
class StripeWebhookController extends Controller {
    public function __invoke(Request $request): JsonResponse {
        try {
            $event = \Stripe\Webhook::constructEvent(
                $request->getContent(),
                $request->header('Stripe-Signature'),
                config('services.stripe.webhook_secret'),
            );
        } catch (\Stripe\Exception\SignatureVerificationException) {
            Log::warning('Stripe webhook signature failed', ['ip' => $request->ip()]);
            return response()->json(['error' => 'Invalid signature'], 403);
        }

        ProcessStripeEvent::dispatch($event->type, $event->data->object->toArray());
        return response()->json(['received' => true]);
    }
}
```

Generic HMAC providers - compare with `hash_equals()` to defeat timing attacks:

```php
class WebhookSignatureMiddleware {
    public function handle(Request $request, Closure $next, string $configKey): Response {
        $expected = hash_hmac('sha256', $request->getContent(),
            config("services.{$configKey}.webhook_secret"));
        if (! hash_equals($expected, $request->header('X-Webhook-Signature', ''))) {
            abort(403, 'Invalid webhook signature');
        }
        return $next($request);
    }
}
```

Idempotency - providers retry, so dedupe on provider event ID:

```php
public function handle(): void {
    if (WebhookEvent::where('provider_event_id', $this->eventId)->exists()) return;

    DB::transaction(function () {
        WebhookEvent::create(['provider_event_id' => $this->eventId, 'type' => $this->eventType]);
        // ... process the event
    });
}
```

### Multi-tenancy

Global scope + tenant-aware policy. Both layers - scope prevents cross-tenant queries, policy prevents privilege escalation within a tenant.

```php
class TenantScope implements Scope {
    public function apply(Builder $builder, Model $model): void {
        $builder->where('tenant_id', auth()->user()->tenant_id);
    }
}

class Order extends Model {
    protected static function booted(): void {
        static::addGlobalScope(new TenantScope());
    }
}

class OrderPolicy {
    public function view(User $user, Order $order): bool {
        return $user->tenant_id === $order->tenant_id
            && ($user->id === $order->user_id || $user->isAdmin());
    }
}
```

## Output Format

```
## Auth Configuration
Strategy: {Sanctum tokens | Sanctum SPA | Passport | Dual}
Guards: [list of auth guards configured]

## Authorization
| Resource | Policy | Actions | Role Requirements |

## Security Checklist
| Concern | Status | Implementation |
```

## Avoid

- `$guarded = []` (mass assignment); `DB::raw` with interpolated user input (SQL injection)
- `env()` outside config files (breaks `config:cache`, hard to audit)
- Inline auth checks in controllers; missing rate limit on `/login`, `/register`, password reset
- `APP_DEBUG=true` or `CORS allow_origins = ['*']` in production
- File uploads served from `public/` without access control; real secrets in `.env.example`
- `md5` / `sha1` for passwords; `==` instead of `hash_equals()` for signatures
- Trusting webhook payloads without signature verification; missing idempotency on retry
- Missing `email:rfc,dns`; `url` validation without scheme allow-list
