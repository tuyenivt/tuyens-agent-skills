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

- Reviewing a Laravel diff that adds Form Request rules, model `$casts` / `$fillable`, defensive null guards, Repository interfaces, Event/Listener pairs, or new service/action classes
- Catching code that is correct, performant, and safe - but does not need to exist

## Rules

- Every finding cites the constraint making the code redundant: FK, `nullable(false)`, unique index, model cast, Form Request rule, Policy, or framework guarantee.
- Severity:
  - **Default `[Suggestion]`.** Cite the constraint, recommend the edit.
  - **`[High]`** when a measurable cost is present (record in `Cost:`). Triggers: extra SELECT in a hot path; blanket `catch (\Throwable)` defeating `renderable` mappings; single-impl Repository forcing two-file refactors; synchronous Event + single Listener replacing a direct call.
  - **`[Question]`** when justification is plausible but not visible in the diff.
- A redundancy with **visible** justification is not a finding. See `Avoid`.

## Patterns

### Category 1: Redundant validation vs Eloquent / DB constraints

Validation stack: **Form Request `rules()` -> Eloquent `$casts` / mutators -> DB schema (`NOT NULL`, `UNIQUE`, `FOREIGN KEY`)**. Form Requests own the 422 path; DB constraints are authoritative.

#### Inline `$request->validate(...)` duplicating a Form Request

```php
// Bad - two validation paths for the same payload
public function store(Request $request) {
    $data = $request->validate(['customer_id' => 'required|integer|exists:customers,id']);
    Order::create($data);
}
// Good
public function store(StoreOrderRequest $request) { Order::create($request->validated()); }
```

#### `unique:` validator without a matching DB unique index

The `unique:` rule races (concurrent submissions both pass the SELECT). Keep the rule for 422 UX, add the index for authority, and translate the violation:

```php
'email' => 'required|email|unique:users,email',  // + $table->string('email')->unique();

try { User::create(['email' => $email]); }
catch (\Illuminate\Database\UniqueConstraintViolationException $e) {
    throw ValidationException::withMessages(['email' => __('validation.unique', ['attribute' => 'email'])]);
}
```

#### `$fillable` and `$guarded` set together

Pick one. Allowlist (`$fillable`) fails closed when new columns appear.

```php
// Bad
protected $fillable = ['customer_id', 'total'];
protected $guarded  = ['id'];
```

### Category 2: Defensive code for impossible states

`findOrFail`, the global exception handler, validated Form Requests, and `auth()->user()` after `auth:*` middleware provide guarantees. Re-checking them is dead code and can mask real failures.

#### `if (!$model)` after `findOrFail`

```php
// Bad - findOrFail throws ModelNotFoundException; renderable maps it to 404
$order = Order::findOrFail($id);
if (!$order) abort(404);
```

#### `if (!auth()->user())` inside an `auth:*` route

Middleware halted unauthenticated requests upstream. Delete the guard.

#### Blanket `catch (\Throwable)` masking the exception handler

`[High]`. Catches `\Error` subclasses that should crash and erases `renderable` mappings (`AuthorizationException -> 403`, `ModelNotFoundException -> 404`, domain exceptions -> typed JSON).

```php
// Bad
try { return $this->service->fulfill($orderId); }
catch (\Throwable $e) { return response()->json(['error' => 'failed'], 500); }

// Good - name the failures; let the rest reach the handler
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
// Good - Order::findOrFail($orderId);
```

Justified when: a non-Eloquent backend (stored procedure, external API as source of truth), or a test seam Mockery cannot satisfy.

#### Service / action wrapping a single Eloquent call

```php
// Bad
class GetOrderService {
    public function execute(int $orderId): Order { return Order::findOrFail($orderId); }
}
// Good - Order::findOrFail($orderId);
```

Justified when: multi-step orchestration, cross-aggregate writes, or external I/O.

#### Event + single synchronous Listener replacing a direct call

`[High]` if the listener is synchronous. The indirection adds nothing.

```php
// Bad - event(new OrderPlaced($order)) -> single sync listener calling $this->mailer->send(...)
// Good - $this->mailer->send(new OrderConfirmation($order));
```

Justified when: the listener implements `ShouldQueue` (retry/latency decoupling), or a second listener exists.

#### `BaseRepository` / `BaseService` parent for one or two children

Inline until 3+ consumers share genuine cross-cutting behavior.

#### Mapper class parallel to an API Resource

Pick one; API Resources are Laravel's mapping primitive. Flag `OrderMapper::fromModel` running alongside `OrderResource`.

#### Speculative `config/*.php` keys

```php
// Bad - declared, never read
return [
    'gateway_url' => env('PAYMENT_GATEWAY_URL'),
    'audit'       => (bool) env('PAYMENT_AUDIT', false),  // never read
    'tracing_tag' => env('PAYMENT_TRACING_TAG'),          // never read
];
```

Flag only after a repo-wide grep confirms zero `config('...')` read sites - queue jobs and Artisan commands often read indirectly.

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
- Flagging Repository, Event/Listener pair, or scoped binding before checking for a second consumer, planned non-Eloquent backend, or `ShouldQueue` justification
- Flagging `$casts` entries - framework coercion, not redundancy
- Confusing "duplicated" with "defense in depth" when multiple write paths exist (HTTP + Artisan + queue + admin panel)
