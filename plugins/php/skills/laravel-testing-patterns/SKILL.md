---
name: laravel-testing-patterns
description: "Laravel testing patterns with Pest/PHPUnit: factories, HTTP tests, DB assertions, facade mocking, queue/event fakes, CI coverage."
metadata:
  category: backend
  tags: [php, laravel, pest, phpunit, testing, factories, mocking]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Feature tests for HTTP endpoints; unit tests for services, actions, jobs
- Factories with states/relationships; facade fakes for queues, events, mail, HTTP
- CI pipelines with coverage gates
- NOT for: Dusk/browser E2E, package testing, performance benchmarks

## Rules

- Pest `describe`/`it` over PHPUnit class-based - more concise, expressive
- Test DB engine matches production (MySQL, not SQLite) - JSON, date, constraint behaviors diverge
- `RefreshDatabase` trait on feature tests - test isolation is non-negotiable
- Tests independent - no `@depends`, no shared mutable state
- Factory states over inline data duplication
- `Queue::fake()` / `Event::fake()` only verify dispatch; test `handle()` directly for logic
- No `dd()` in test files

## Patterns

### Pest fundamentals

```php
describe('OrderController', function () {
    it('creates an order', function () {
        $user = User::factory()->create();

        $this->actingAs($user)->postJson('/api/orders', [
            'total' => '99.99',
            'items' => [['product_name' => 'Widget', 'quantity' => 2, 'unit_price' => '49.99']],
            'shipping_address' => '123 Main St',
        ])->assertCreated()
          ->assertJsonPath('data.status', 'pending');

        $this->assertDatabaseHas('orders', ['user_id' => $user->id, 'total' => '99.99']);
    });

    it('requires authentication', fn() => $this->postJson('/api/orders', [])->assertUnauthorized());
});
```

```php
// Pest fluent expectations over PHPUnit assertions
expect($order->status)->toBe(OrderStatus::Pending);
expect($order->items)->toHaveCount(3);
expect($user->orders)->each->toBeInstanceOf(Order::class);
expect($response->json('data'))->toMatchArray(['status' => 'pending', 'total' => '99.99']);
```

### Datasets

```php
dataset('invalid_totals', ['negative' => [-1], 'zero' => [0], 'string' => ['abc']]);

it('rejects invalid totals', function (mixed $total) {
    $user = User::factory()->create();
    $this->actingAs($user)->postJson('/api/orders', ['total' => $total, /* ... */])
        ->assertUnprocessable();
})->with('invalid_totals');
```

### Factories

```php
class OrderFactory extends Factory {
    public function definition(): array {
        return [
            'user_id' => User::factory(),
            'status' => OrderStatus::Pending,
            'total' => fake()->randomFloat(2, 10, 999),
        ];
    }

    public function completed(): static {
        return $this->state(fn() => ['status' => OrderStatus::Completed]);
    }

    public function withItems(int $count = 3): static {
        return $this->has(OrderItem::factory()->count($count), 'items');
    }
}

// Usage
Order::factory()->withItems(5)->create();
Order::factory()->completed()->count(10)->create();
Order::factory()->for($user)->create();

// Sequences
Order::factory()->count(3)->sequence(
    ['status' => OrderStatus::Pending],
    ['status' => OrderStatus::Processing],
    ['status' => OrderStatus::Completed],
)->create();
```

### HTTP tests

```php
$this->actingAs($user)->getJson('/api/orders')
    ->assertOk()
    ->assertJsonCount(5, 'data')
    ->assertJsonStructure(['data' => [['id', 'status', 'total']], 'meta' => ['current_page']]);

$this->actingAs($user)->postJson('/api/orders', $payload)->assertCreated();
$this->actingAs($user)->putJson("/api/orders/{$order->id}", $payload)->assertOk();
$this->actingAs($user)->deleteJson("/api/orders/{$order->id}")->assertNoContent();
```

### Database assertions

```php
uses(RefreshDatabase::class);

$this->assertDatabaseHas('orders', ['user_id' => $user->id, 'status' => 'pending']);
$this->assertDatabaseMissing('orders', ['id' => $order->id]);
$this->assertDatabaseCount('orders', 5);
$this->assertSoftDeleted('orders', ['id' => $order->id]);
```

### Facade fakes

```php
// Queue - verify dispatch without running
Queue::fake();
// ... act ...
Queue::assertPushed(ProcessPayment::class, fn($job) => $job->orderId === $order->id);
Queue::assertPushedOn('payments', ProcessPayment::class);

// Event
Event::fake([OrderCreated::class]);
Event::assertDispatched(OrderCreated::class, fn($e) => $e->order->id === $order->id);

// Notification
Notification::fake();
Notification::assertSentTo($user, OrderConfirmationNotification::class);

// Mail
Mail::fake();
Mail::assertSent(InvoiceMail::class, fn($mail) => $mail->hasTo($order->user->email));

// HTTP client (external APIs)
Http::fake(['payments.example.com/*' => Http::response(['status' => 'success'], 200)]);
Http::assertSent(fn($request) =>
    $request->url() === 'https://payments.example.com/charge' && $request['amount'] === 9999
);
```

### Testing jobs directly

`Queue::fake()` verifies dispatch but prevents `handle()` from running. Test job logic by invoking `handle()` with explicit dependencies.

```php
// Bad - Queue::fake() can't assert payment state because handle() never runs
Queue::fake();
// ... trigger ...
Queue::assertPushed(ProcessPayment::class); // dispatch only, no logic

// Good - invoke handle() directly
$order = Order::factory()->create(['status' => OrderStatus::Pending]);
$paymentService = Mockery::mock(PaymentService::class);
$paymentService->shouldReceive('charge')->once();

(new ProcessPayment($order->id))->handle($paymentService);

expect($order->fresh()->status)->toBe(OrderStatus::Processing);
```

### Authorization

```php
it('prevents non-owner access', function () {
    $order = Order::factory()->create();
    $this->actingAs(User::factory()->create())
        ->getJson("/api/orders/{$order->id}")
        ->assertForbidden();
});
```

### Transactions and side effects

```php
// Rollback on failure
it('rolls back order when payment fails', function () {
    Http::fake(['payments.example.com/*' => Http::response(['error' => 'declined'], 422)]);
    $user = User::factory()->create();

    $this->actingAs($user)->postJson('/api/orders', $validPayload)->assertStatus(422);
    $this->assertDatabaseMissing('orders', ['user_id' => $user->id]);
});

// Side-effect state changes
it('decrements stock after order', function () {
    $product = Product::factory()->create(['stock' => 10]);
    $this->actingAs(User::factory()->create())
        ->postJson('/api/orders', ['items' => [['product_id' => $product->id, 'quantity' => 3]]])
        ->assertCreated();

    expect($product->fresh()->stock)->toBe(7);
});
```

### Unit testing services

Test business logic in isolation - skip the HTTP layer when verifying pure logic.

```php
// Bad - HTTP roundtrip to test calculation
$response = $this->actingAs($user)->postJson('/api/orders', [...]);
expect($response->json('data.total'))->toBe('149.97');

// Good - call service directly
$dto = new CreateOrderDTO(userId: 1, total: '0', items: [/* ... */]);
$order = app(OrderService::class)->create($dto);
expect($order->total)->toBe('149.97');
```

### Webhooks

```php
describe('StripeWebhookController', function () {
    it('processes valid signed webhook', function () {
        Queue::fake();

        $payload = json_encode(['type' => 'payment_intent.succeeded', 'data' => [...]]);
        $timestamp = time();
        $signature = 't=' . $timestamp . ',v1=' . hash_hmac(
            'sha256', $timestamp . '.' . $payload, config('services.stripe.webhook_secret')
        );

        $this->postJson('/webhooks/stripe', [], ['Stripe-Signature' => $signature])
            ->assertOk();

        Queue::assertPushed(ProcessStripeEvent::class);
    });

    it('rejects invalid signature', function () {
        $this->postJson('/webhooks/stripe', [], ['Stripe-Signature' => 't=123,v1=invalid'])
            ->assertForbidden();
    });
});

// Idempotency - duplicate events must not double-process
it('skips duplicate webhook events', function () {
    WebhookEvent::create(['provider_event_id' => 'evt_123', 'type' => 'payment_intent.succeeded']);
    (new ProcessStripeEvent('payment_intent.succeeded', ['id' => 'evt_123'], 'evt_123'))->handle();
    $this->assertDatabaseCount('webhook_events', 1);
});
```

### Test scope decision

| Scope             | What to Test                    | What to Mock                  | Use When                          |
| ----------------- | ------------------------------- | ----------------------------- | --------------------------------- |
| Feature (HTTP)    | Request/response, DB, status    | External APIs, queues, mail   | Endpoint, validation, auth        |
| Feature (Service) | Service method with real DB     | External APIs, queues         | Business logic + DB               |
| Unit              | Single class in isolation       | All dependencies (Mockery)    | Pure logic, calculations, DTOs    |
| Job               | `handle()` directly             | External services             | Queue job processing logic        |

### RefreshDatabase vs DatabaseTransactions

| Trait                  | Behavior                                       | Use When                        |
| ---------------------- | ---------------------------------------------- | ------------------------------- |
| `RefreshDatabase`      | Migrates once, wraps each test in transaction  | Default - most feature tests    |
| `DatabaseTransactions` | Wraps in transaction, does NOT migrate         | Testing transaction behavior    |

### Organization

```
tests/
  Pest.php
  Feature/
    Http/      # OrderControllerTest.php
    Jobs/      # ProcessPaymentTest.php
    Services/  # OrderServiceTest.php
  Unit/
    Actions/   # CreateOrderTest.php
    Models/    # OrderTest.php
```

```php
// tests/Pest.php
uses(Tests\TestCase::class, RefreshDatabase::class)->in('Feature');
uses(Tests\TestCase::class)->in('Unit');
```

### CI and coverage

```xml
<!-- phpunit.xml -->
<php>
    <env name="DB_CONNECTION" value="mysql"/>
    <env name="QUEUE_CONNECTION" value="sync"/>
    <env name="CACHE_STORE" value="array"/>
</php>
```

```bash
php artisan test --coverage --min=80
php artisan test --parallel
php artisan test --filter=OrderControllerTest
```

## Output Format

```
## Test Files
| File | Type | Tests | Assertions | Fakes/Mocks |
Type: {Feature/HTTP | Feature/Service | Unit | Job}

## Coverage
Target: [percentage]
Excluded: [directories]

## Factory States
| Factory | States | Relationships |
```

## Avoid

- SQLite test DB when production is MySQL (JSON, date, constraint behavior differs)
- `Queue::fake()` when you need to verify `handle()` logic - fake blocks execution
- `@depends` or shared mutable state between tests
- Mocking everything in feature tests - real DB interactions catch real bugs
- Inline data duplicated across tests instead of factory states
- Testing private methods directly - go through public interface
- Webhook tests without signature verification (passes locally, fails in prod)
- Missing idempotency tests for webhook handlers - duplicate events double-process
- `dd()` left in test files
