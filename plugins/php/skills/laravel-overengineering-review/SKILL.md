---
name: laravel-overengineering-review
description: Laravel necessity review - Form Request rules vs Eloquent/DB, defensive null after findOrFail, single-impl Repository, Event+single-Listener.
metadata:
  category: backend
  tags: [php, laravel, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing a Laravel diff that adds Form Request rules, model `$casts` / `$fillable` entries, defensive null guards, Repository interfaces, Event/Listener pairs, or new service/action classes
- Catching code that is correct, performant, and safe - but does not need to exist

## Rules

- Every finding cites the constraint making the code redundant: FK name, `nullable(false)` column, unique index, model cast, Form Request rule, Policy, or framework guarantee.
- Severity:
  - **Default `[Suggestion]`.** Cite the constraint, recommend the edit.
  - **`[High]`** when a measurable cost is present. Cite the cost in the `Cost:` field. Triggers:
    - Extra SELECT in a hot path
    - Blanket `catch (\Throwable)` defeating the exception handler / `renderable` mappings
    - Single-impl Repository interface forcing two-file refactors
    - Synchronous Event + single Listener where a direct call would suffice
  - **`[Question]`** when justification is plausible but not visible in the diff.
- A redundancy with **visible** justification is not a finding. See `Avoid` for the canonical exceptions.

## Patterns

### Category 1: Redundant validation vs Eloquent / DB constraints

Validation stack: **Form Request `rules()` -> Eloquent `$casts` / mutators -> DB schema (`NOT NULL`, `UNIQUE`, `FOREIGN KEY`)**. Form Requests own the 422 user-facing path; DB constraints are authoritative.

#### Inline `$request->validate(...)` when a Form Request already validates the same fields

```php
// Bad - two validation paths for the same payload
public function store(Request $request) {
    $data = $request->validate(['customer_id' => 'required|integer|exists:customers,id']);
    Order::create($data);
}

// Good
public function store(StoreOrderRequest $request) {
    Order::create($request->validated());
}
```

#### `unique:` validator without a matching DB unique index

The `unique:` rule races (concurrent submissions both pass the SELECT). The DB index is authoritative.

```php
// Bad - rule alone, no ->unique() on the migration
'email' => 'required|email|unique:users,email',
```

```php
// Good - rule for 422 UX + unique index for authority; translate the violation
'email' => 'required|email|unique:users,email',  // + $table->string('email')->unique();

try { User::create(['email' => $email]); }
catch (\Illuminate\Database\UniqueConstraintViolationException $e) {
    throw ValidationException::withMessages(['email' => __('validation.unique', ['attribute' => 'email'])]);
}
```

#### `$fillable` and `$guarded` set together

```php
// Bad
class Order extends Model {
    protected $fillable = ['customer_id', 'total'];
    protected $guarded  = ['id'];
}

// Good - allowlist only; fails closed when new columns appear
class Order extends Model {
    protected $fillable = ['customer_id', 'total'];
}
```

### Category 2: Defensive code for impossible states

`findOrFail`, the global exception handler, validated Form Requests, and `auth()->user()` after `auth:*` middleware all provide guarantees. Re-checking them is dead code and can mask real failures.

#### `if (!$model)` after `findOrFail`

```php
// Bad - findOrFail throws ModelNotFoundException; renderable maps it to 404
$order = Order::findOrFail($id);
if (!$order) abort(404);
```

#### `if (!auth()->user())` inside an `auth:*` route

```php
// Bad - middleware halted unauthenticated requests upstream
Route::middleware('auth:sanctum')->post('/orders', function () {
    if (!auth()->user()) abort(401);
});
```

#### Blanket `catch (\Throwable)` masking the exception handler

`[High]`. Catches `\Error` subclasses that should crash and erases `renderable` mappings (`AuthorizationException -> 403`, `ModelNotFoundException -> 404`, custom domain exceptions -> typed JSON).

```php
// Bad
try { return $this->service->fulfill($orderId); }
catch (\Throwable $e) { return response()->json(['error' => 'failed'], 500); }

// Good - name the failures; let the rest reach the handler
try { return $this->service->fulfill($orderId); }
catch (InsufficientStockException $e) { return response()->json(['error' => $e->getMessage()], 409); }
catch (PaymentDeclinedException $e)   { return response()->json(['error' => $e->getMessage()], 402); }
```

#### `try { ... } catch (\Throwable $e) { throw $e; }` no-op rethrow

Delete it.

### Category 3: Premature abstraction

#### Repository interface with one Eloquent implementation

`[High]` - forces two-file refactors with no behavioral reason. Eloquent already abstracts storage.

```php
// Bad
interface OrderRepositoryInterface { public function find(int $id): ?Order; }
class EloquentOrderRepository implements OrderRepositoryInterface {
    public function find(int $id): ?Order { return Order::find($id); }
}

// Good - call Eloquent directly
$order = Order::findOrFail($orderId);
```

Justified when: a non-Eloquent backend (legacy stored procedure, external API as source of truth), or a test seam Mockery cannot satisfy.

#### Service / action wrapping a single Eloquent call

```php
// Bad
class GetOrderService {
    public function execute(int $orderId): Order { return Order::findOrFail($orderId); }
}

// Good - call Eloquent directly
$order = Order::findOrFail($orderId);
```

Justified when: multi-step orchestration, cross-aggregate writes, or external I/O.

#### Event + single synchronous Listener for a direct call

`[High]` if the listener is synchronous. The indirection adds nothing.

```php
// Bad
event(new OrderPlaced($order));
class SendOrderConfirmation {
    public function handle(OrderPlaced $event): void { $this->mailer->send(new OrderConfirmation($event->order)); }
}

// Good - direct call until a second listener or ShouldQueue exists
$this->mailer->send(new OrderConfirmation($order));
```

Justified when: the listener implements `ShouldQueue` (decoupling for retry/latency), or a second listener exists.

#### `BaseRepository` / `BaseService` parent for one or two children

```php
// Bad - template-method scaffold for two consumers
abstract class BaseRepository { /* ... */ }
```

Inline until 3+ consumers share genuine cross-cutting behavior.

#### Mapper class parallel to an API Resource

```php
// Bad - OrderMapper::fromModel + OrderResource doing the same job
// Good - pick one; API Resources are Laravel's mapping primitive
```

#### Speculative `config/*.php` keys

```php
// Bad - audit and tracing_tag declared, never read
return [
    'gateway_url' => env('PAYMENT_GATEWAY_URL'),
    'audit'       => (bool) env('PAYMENT_AUDIT', false),  // never read
    'tracing_tag' => env('PAYMENT_TRACING_TAG'),          // never read
];
```

Flag speculative keys only after a repo-wide grep confirms zero `config('...')` read sites - queue jobs and Artisan commands often read indirectly.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `if (!$order)` after `Order::findOrFail($id)`}
- Redundant because: {FK name | `nullable(false)` column | unique index | Form Request rule | Eloquent cast | framework guarantee}
- Cost: {extra SELECT per save | masked exception | speculative surface area | unnecessary event dispatch} _(required for `[High]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a legitimate reason might apply; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow knows the check ran.

## Avoid

- Flagging Form Request rules on controller-bound DTOs - that layer owns user-facing error messages
- Flagging `unique:` validators paired with a unique DB index - rule for UX, index for authority
- Flagging a Repository, Event/Listener pair, or `Scope.REQUEST` before checking for a second consumer, planned non-Eloquent backend, or `ShouldQueue` justification
- Flagging `$casts` entries - framework coercion, not redundancy
- Confusing "duplicated" with "defense in depth" when multiple write paths exist (HTTP + Artisan + queue + admin panel)
