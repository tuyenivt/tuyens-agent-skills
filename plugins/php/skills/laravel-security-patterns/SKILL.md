---
name: laravel-security-patterns
description: "Laravel security patterns - mass assignment protection, SQL injection prevention, authentication (Sanctum/Passport), authorization (Gates/Policies), CSRF, rate limiting, input validation, and secrets management."
metadata:
  category: backend
  tags: [php, laravel, security, auth, sanctum, policies, owasp]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Implementing authentication (Sanctum API tokens, SPA sessions)
- Designing authorization (Policies, Gates, role-based access)
- Hardening input validation, mass assignment, SQL injection prevention
- Configuring CSRF, rate limiting, session security
- NOT for: infrastructure/network security, API gateway configuration, encryption at rest

## Rules

- Always `$fillable` whitelist on models - never `$guarded = []`
- Always parameterized queries - never interpolate user input into SQL
- Always use `Hash::make()` for passwords - never md5/sha1
- Never call `env()` outside config files - breaks config caching
- Always validate via Form Requests - never trust raw input
- Always rate limit authentication routes
- Never store secrets in `.env.example` or version control

## Patterns

### 1. MASS ASSIGNMENT PROTECTION

Always define `$fillable` explicitly. Never use `$guarded = []`.

```php
// Bad - all fields writable
class Order extends Model
{
    protected $guarded = [];
}

// Good - explicit whitelist
class Order extends Model
{
    protected $fillable = [
        'user_id',
        'status',
        'total',
        'shipping_address',
    ];
}
```

Use Form Requests with validation rules to filter input before it reaches `Model::create()`.

### 2. SQL INJECTION PREVENTION

Use parameterized queries or Eloquent. Never interpolate user input into raw SQL.

```php
// Bad - SQL injection
$orders = DB::select("SELECT * FROM orders WHERE status = '$status'");
$orders = Order::whereRaw("status = '$status'")->get();

// Good - parameterized
$orders = DB::select('SELECT * FROM orders WHERE status = ?', [$status]);
$orders = Order::whereRaw('status = ?', [$status])->get();
$orders = Order::where('status', $status)->get(); // Eloquent (preferred)
```

#### Safe Raw Expressions

```php
// When DB::raw() is needed, always use bindings
Order::select(DB::raw('DATE(created_at) as date'), DB::raw('COUNT(*) as count'))
    ->where('status', $status) // parameterized
    ->groupByRaw('DATE(created_at)')
    ->get();
```

### 3. AUTHENTICATION

#### Sanctum - API Tokens

```php
// Issue token
$token = $user->createToken('api-token', ['orders:read', 'orders:write']);
return ['token' => $token->plainTextToken];

// Protect routes
Route::middleware('auth:sanctum')->group(function () {
    Route::apiResource('orders', OrderController::class);
});

// Check abilities
if ($user->tokenCan('orders:write')) { ... }
```

#### Sanctum - SPA Authentication

```php
// config/sanctum.php
'stateful' => explode(',', env('SANCTUM_STATEFUL_DOMAINS', 'localhost:3000')),

// CORS config - credentials must be true for SPA auth
'supports_credentials' => true,

// SPA login flow:
// 1. GET /sanctum/csrf-cookie (sets XSRF-TOKEN cookie)
// 2. POST /login (session-based auth)
// 3. Subsequent requests use session cookie
```

#### Password Hashing

```php
// Bad - plain text password storage
$user->password = $request->password;

// Good - hashed with Hash facade
$user->password = Hash::make($request->password);
```

```php
// Always use Hash facade (bcrypt by default, argon2 optional)
use Illuminate\Support\Facades\Hash;

$hashed = Hash::make($password);
$verified = Hash::check($plaintext, $hashed);

// Never use md5(), sha1(), or plain text
```

### 4. AUTHORIZATION

#### Policies

```php
// Bad - inline authorization in controller
public function show(Order $order): OrderResource
{
    if ($order->user_id !== auth()->id()) {
        abort(403);
    }
    return new OrderResource($order);
}

// Good - policy-based authorization
public function show(Order $order): OrderResource
{
    $this->authorize('view', $order);
    return new OrderResource($order);
}
```

```php
class OrderPolicy
{
    public function view(User $user, Order $order): bool
    {
        return $user->id === $order->user_id;
    }

    public function update(User $user, Order $order): bool
    {
        return $user->id === $order->user_id
            && $order->status === OrderStatus::Pending;
    }

    public function delete(User $user, Order $order): bool
    {
        return $user->id === $order->user_id
            && $order->status === OrderStatus::Pending;
    }

    public function create(User $user): bool
    {
        return $user->hasVerifiedEmail();
    }
}

// In controller
$this->authorize('view', $order);

// In Form Request
public function authorize(): bool
{
    return $this->user()->can('update', $this->route('order'));
}
```

#### Gates

```php
// AppServiceProvider or AuthServiceProvider
Gate::define('access-admin', function (User $user): bool {
    return $user->is_admin;
});

// Usage
if (Gate::allows('access-admin')) { ... }

// Middleware
Route::middleware('can:access-admin')->group(function () { ... });
```

### 5. CSRF PROTECTION

```php
// Web routes: CSRF middleware is active by default
// API routes: use token-based auth (Sanctum) instead of CSRF

// Exclude specific routes if needed (bootstrap/app.php)
->withMiddleware(function (Middleware $middleware) {
    $middleware->validateCsrfTokens(except: [
        'webhooks/*', // third-party webhooks
    ]);
})
```

### 6. RATE LIMITING

```php
// Bad - unprotected login route
Route::post('/login', LoginController::class); // no rate limiting = brute force risk

// Good - rate-limited authentication
Route::post('/login', LoginController::class)->middleware('throttle:auth');
```

```php
// bootstrap/app.php or RouteServiceProvider
RateLimiter::for('api', function (Request $request) {
    return Limit::perMinute(60)->by($request->user()?->id ?: $request->ip());
});

RateLimiter::for('auth', function (Request $request) {
    return Limit::perMinute(5)->by($request->ip()); // strict for login/register
});

// Apply to routes
Route::middleware('throttle:api')->group(function () { ... });
Route::post('/login', LoginController::class)->middleware('throttle:auth');
```

### 7. INPUT VALIDATION

Always validate via Form Requests. Never trust raw input.

```php
// Sanitize and validate
class StoreOrderRequest extends FormRequest
{
    public function rules(): array
    {
        return [
            'email' => ['required', 'email:rfc,dns', 'max:255'],
            'total' => ['required', 'numeric', 'min:0.01', 'max:99999.99'],
            'url' => ['nullable', 'url:http,https'], // only http(s)
            'file' => ['nullable', 'file', 'mimes:pdf,jpg,png', 'max:10240'], // 10MB
        ];
    }

    // Strip HTML tags from string inputs
    protected function prepareForValidation(): void
    {
        $this->merge([
            'notes' => strip_tags($this->notes ?? ''),
        ]);
    }
}
```

### 8. FILE UPLOADS

```php
// Validate file type, size, and store outside public directory
$request->validate([
    'avatar' => ['required', 'image', 'mimes:jpg,png', 'max:2048'],
]);

// Store in non-public disk
$path = $request->file('avatar')->store('avatars', 'private');

// Serve via signed URL or controller (not direct public access)
return Storage::disk('private')->download($path);
```

### 9. SECRETS MANAGEMENT

```php
// Bad - hardcoded secret
$stripe = new StripeClient('sk_live_xxx');

// Bad - env() in application code
$key = env('STRIPE_KEY'); // breaks config caching

// Good - config file references env(), application reads config()
// config/services.php
'stripe' => [
    'key' => env('STRIPE_KEY'),
    'secret' => env('STRIPE_SECRET'),
],

// Application code
$key = config('services.stripe.key');
```

#### Environment File Rules

- `.env` is never committed to VCS (in `.gitignore`)
- `.env.example` contains placeholder values only - no real secrets
- Use `php artisan config:cache` in production (requires all `env()` calls to be in config files)
- Encrypt sensitive env values with `php artisan env:encrypt` (Laravel 9+)

### 10. SESSION AND COOKIE SECURITY

```php
// config/session.php
'secure' => true,          // HTTPS only
'http_only' => true,       // No JavaScript access
'same_site' => 'lax',      // CSRF protection

// Regenerate session after login
$request->session()->regenerate();

// Invalidate session on logout
$request->session()->invalidate();
$request->session()->regenerateToken();
```

### 11. AUTH STRATEGY SELECTION

| Scenario          | Strategy                              | Package           |
| ----------------- | ------------------------------------- | ----------------- |
| Mobile app API    | Sanctum API tokens                    | laravel/sanctum   |
| SPA (same domain) | Sanctum SPA auth (session + CSRF)     | laravel/sanctum   |
| Third-party OAuth | Passport with grants                  | laravel/passport  |
| Social login      | Socialite                             | laravel/socialite |
| API tokens + SPA  | Dual Sanctum config (separate guards) | laravel/sanctum   |

### 12. WEBHOOK SIGNATURE VERIFICATION

Always verify webhook signatures from external providers. Never trust raw payloads without cryptographic verification.

```php
// Bad - no signature verification, trusts any payload
Route::post('/webhooks/stripe', function (Request $request) {
    $data = $request->json(); // anyone can send fake events
    Order::find($data['order_id'])->update(['status' => 'paid']);
});

// Good - verify HMAC signature before processing
class StripeWebhookController extends Controller
{
    public function __invoke(Request $request): JsonResponse
    {
        $payload = $request->getContent();
        $signature = $request->header('Stripe-Signature');
        $secret = config('services.stripe.webhook_secret');

        try {
            $event = \Stripe\Webhook::constructEvent($payload, $signature, $secret);
        } catch (\Stripe\Exception\SignatureVerificationException $e) {
            Log::warning('Stripe webhook signature verification failed', [
                'ip' => $request->ip(),
            ]);
            return response()->json(['error' => 'Invalid signature'], 403);
        }

        // Process only after verification
        ProcessStripeEvent::dispatch($event->type, $event->data->object->toArray());

        return response()->json(['received' => true]);
    }
}
```

#### Generic HMAC Verification (Non-Stripe Providers)

```php
// For providers that use simple HMAC-SHA256 signatures
class WebhookSignatureMiddleware
{
    public function handle(Request $request, Closure $next, string $configKey): Response
    {
        $secret = config("services.{$configKey}.webhook_secret");
        $expected = hash_hmac('sha256', $request->getContent(), $secret);
        $received = $request->header('X-Webhook-Signature');

        if (! hash_equals($expected, $received)) {
            abort(403, 'Invalid webhook signature');
        }

        return $next($request);
    }
}
```

#### Idempotency for Webhooks

Providers may send the same event multiple times. Store processed event IDs to prevent duplicate processing:

```php
// In the job that processes webhook events
public function handle(): void
{
    // Idempotency check - skip if already processed
    if (WebhookEvent::where('provider_event_id', $this->eventId)->exists()) {
        return;
    }

    DB::transaction(function () {
        WebhookEvent::create(['provider_event_id' => $this->eventId, 'type' => $this->eventType]);
        // ... process the event
    });
}
```

### 13. MULTI-TENANCY

Tenant isolation via global scopes and tenant-aware policies.

```php
// Global scope for tenant isolation
class TenantScope implements Scope
{
    public function apply(Builder $builder, Model $model): void
    {
        $builder->where('tenant_id', auth()->user()->tenant_id);
    }
}

// Apply via model boot
protected static function booted(): void
{
    static::addGlobalScope(new TenantScope());
}

// Tenant-aware policy
class OrderPolicy
{
    public function view(User $user, Order $order): bool
    {
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

- `$guarded = []` on any model (mass assignment vulnerability)
- `DB::raw()` with user input without parameter binding (SQL injection)
- `env()` calls outside config files (breaks config caching, hard to audit)
- Inline auth checks in controllers (use Policies)
- Missing rate limiting on auth routes (brute force vulnerability)
- `APP_DEBUG=true` in production (leaks stack traces and config)
- `CORS: allow_origins = ['*']` in production (CSRF risk)
- File uploads stored in `public/` without access control
- Real secrets in `.env.example`
- `md5()` or `sha1()` for password hashing (use `Hash::make()`)
- Trusting webhook payloads without signature verification (forged events)
- Using `==` instead of `hash_equals()` for signature comparison (timing attack)
- Missing webhook idempotency (duplicate event processing)
- Missing `email:rfc,dns` validation (allows malformed emails)
