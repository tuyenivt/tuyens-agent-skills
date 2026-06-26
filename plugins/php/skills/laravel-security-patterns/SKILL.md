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

- `$fillable` whitelist on every model; never `$guarded = []`
- Eloquent or parameter bindings only; never interpolate user input into SQL
- `Hash::make()` / `Hash::check()` for passwords; `random_bytes` / `Str::random` for tokens
- `env()` only inside `config/*.php`; runtime code uses `config()` (so `config:cache` works)
- Validate via Form Requests; authorize via Policies (not inline `auth()->id()` checks)
- Rate limit `/login`, `/register`, password reset by IP
- Verify webhook signatures with `hash_equals()`; record event IDs for idempotency

## Patterns

### Mass assignment

```php
// Bad
class Order extends Model { protected $guarded = []; }
// Good
class Order extends Model { protected $fillable = ['status', 'total', 'shipping_address']; }
// Server-set fields (user_id, tenant_id, role, is_admin) assigned outside fillable
```

### SQL injection

```php
// Bad
DB::select("SELECT * FROM orders WHERE status = '$status'");
Order::whereRaw("status = '$status'")->get();

// Good
Order::where('status', $status)->get();
Order::whereRaw('status = ?', [$status])->get();

// DB::raw safe for expressions, never values
Order::select(DB::raw('DATE(created_at) as date'), DB::raw('COUNT(*) as count'))
    ->where('status', $status)->groupByRaw('DATE(created_at)')->get();

// User-supplied sort columns: allowlist
'sort' => ['nullable', Rule::in(['id', 'created_at', 'total'])],
```

### Authentication

```php
// Sanctum API tokens with abilities
$token = $user->createToken('api', ['orders:read', 'orders:write'], now()->addDays(30));
Route::middleware('auth:sanctum')->apiResource('orders', OrderController::class);
if ($user->tokenCan('orders:write')) { /* ... */ }

// Token lifecycle
Sanctum::usePersonalAccessTokenModel(PersonalAccessToken::class);
// Schedule: PersonalAccessToken::where('last_used_at', '<', now()->subMonths(3))->delete();
```

Sanctum SPA (same-site cookie auth):

1. `GET /sanctum/csrf-cookie` -> sets `XSRF-TOKEN`
2. `POST /login` -> session established
3. Subsequent requests carry the session cookie + `X-XSRF-TOKEN` header

```php
// config/sanctum.php
'stateful' => explode(',', env('SANCTUM_STATEFUL_DOMAINS', 'localhost:3000')),
// config/cors.php
'supports_credentials' => true,
// config/session.php - same-domain SPA: same_site=lax; cross-site SPA: same_site=none + secure=true
'secure' => true, 'http_only' => true, 'same_site' => 'lax',
```

| Scenario          | Strategy                       | Package           |
| ----------------- | ------------------------------ | ----------------- |
| Mobile app API    | Sanctum API tokens             | laravel/sanctum   |
| SPA (same domain) | Sanctum SPA (session + CSRF)   | laravel/sanctum   |
| Mobile + SPA      | Both - tokens via `auth:sanctum` guard, SPA via session - configure both | laravel/sanctum   |
| Third-party OAuth | Passport with grants           | laravel/passport  |
| Social login      | Socialite                      | laravel/socialite |

### Authorization

```php
// Bad - inline check leaks rule into controller
if ($order->user_id !== auth()->id()) abort(403);

// Good - policy
$this->authorize('view', $order);

class OrderPolicy {
    public function before(User $user, string $ability): ?bool {
        return $user->isSuperAdmin() ? true : null;       // super-admin shortcut
    }
    public function view(User $user, Order $order): bool {
        return $user->id === $order->user_id;
    }
    public function update(User $user, Order $order): bool {
        return $user->id === $order->user_id && $order->status === OrderStatus::Pending;
    }
}

// In Form Request
public function authorize(): bool {
    return $this->user()->can('update', $this->route('order'));
}

// Gates for non-resource permissions
Gate::define('access-admin', fn(User $u) => $u->is_admin);
Route::middleware('can:access-admin')->group(/* ... */);
```

### CSRF and rate limiting

```php
// CSRF on by default for web; exempt only webhooks
->withMiddleware(function (Middleware $m) {
    $m->validateCsrfTokens(except: ['webhooks/*']);
})

RateLimiter::for('api', fn(Request $r) =>
    Limit::perMinute(60)->by($r->user()?->id ?: $r->ip()));
RateLimiter::for('auth', fn(Request $r) =>
    Limit::perMinute(5)->by($r->ip()));

Route::post('/login', LoginController::class)->middleware('throttle:auth');
```

### Input validation

```php
class StoreOrderRequest extends FormRequest {
    public function rules(): array {
        return [
            'email' => ['required', 'email:rfc,dns', 'max:255'],
            'total' => ['required', 'numeric', 'min:0.01', 'max:99999.99'],
            'url'   => ['nullable', 'url:http,https'],         // block javascript:, data:
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
// Good - config reads env; app reads config
'stripe' => ['key' => env('STRIPE_KEY'), 'secret' => env('STRIPE_SECRET')],
$key = config('services.stripe.key');
```

- `.env` gitignored; `.env.example` has placeholders only
- `php artisan config:cache` in production
- `php artisan env:encrypt` for committed encrypted env (Laravel 9+)

### Session and cookie

```php
// On login / logout
$request->session()->regenerate();
$request->session()->invalidate();
$request->session()->regenerateToken();
```

### Webhook signature verification

```php
// Stripe - SDK-verified
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
        ProcessStripeEvent::dispatch($event->id, $event->type, $event->data->object->toArray());
        return response()->json(['received' => true]);
    }
}

// Generic HMAC - use hash_equals to defeat timing attacks
$expected = hash_hmac('sha256', $request->getContent(),
    config('services.provider.webhook_secret'));
if (! hash_equals($expected, $request->header('X-Webhook-Signature', ''))) {
    abort(403, 'Invalid signature');
}
```

Idempotency - providers retry, dedupe on event ID:

```php
public function handle(): void {
    if (WebhookEvent::where('provider_event_id', $this->eventId)->exists()) return;

    DB::transaction(function () {
        WebhookEvent::create(['provider_event_id' => $this->eventId, 'type' => $this->eventType]);
        // process
    });
}
```

### Multi-tenancy

Two layers: global scope prevents cross-tenant queries; policy prevents privilege escalation within a tenant.

```php
class TenantScope implements Scope {
    public function apply(Builder $b, Model $m): void {
        $b->where('tenant_id', auth()->user()->tenant_id);
    }
}
class Order extends Model {
    protected static function booted(): void { static::addGlobalScope(new TenantScope()); }
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
Strategy: {Sanctum tokens | Sanctum SPA | Sanctum dual | Passport}
Guards: [list]

## Authorization
| Resource | Policy | Actions | Role Requirements |

## Security Checklist
| Concern | Status | Implementation |
```

## Avoid

- `$guarded = []`; `DB::raw` with interpolated input; user-supplied sort without allowlist
- `env()` outside config files
- Missing rate limit on auth routes; `APP_DEBUG=true` in production
- File uploads served from `public/` without access control
- `md5` / `sha1` for passwords; `==` instead of `hash_equals()` for signatures
- Webhooks without signature verification or event-ID idempotency
- `email:rfc,dns` missing; `url` validation without scheme allow-list
