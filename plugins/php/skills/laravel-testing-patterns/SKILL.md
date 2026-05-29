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
- Factories with states/relationships; facade fakes (queue, event, mail, HTTP)
- CI pipelines with coverage gates
- NOT for: Dusk/browser E2E, package testing, performance benchmarks

## Rules

- Pest `describe`/`it` over PHPUnit class-based; PHPUnit only in legacy projects
- Test DB matches production engine (MySQL, not SQLite) - JSON, date, FK behavior diverge
- `RefreshDatabase` on feature tests; per-test transactional reset
- Tests independent - no `@depends`, no shared mutable state
- Factory states over inline data duplication
- `Queue::fake` / `Event::fake` verify dispatch only - test `handle()` directly for logic
- No `dd()` / `dump()` in test files

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

    it('rejects invalid input', function () {
        $this->actingAs(User::factory()->create())
            ->postJson('/api/orders', ['total' => -1])
            ->assertJsonValidationErrors(['total', 'items']);
    });

    it('requires authentication',
        fn() => $this->postJson('/api/orders', [])->assertUnauthorized());
});

// Fluent expectations
expect($order->status)->toBe(OrderStatus::Pending);
expect($response->json('data'))->toMatchArray(['status' => 'pending']);
```

### Auth helpers

```php
$this->actingAs($user);                                    // session
Sanctum::actingAs($user, ['orders:write']);                // Sanctum token + abilities
```

### Datasets

```php
dataset('invalid_totals', ['negative' => [-1], 'zero' => [0], 'string' => ['abc']]);

it('rejects invalid totals', function (mixed $total) {
    $this->actingAs(User::factory()->create())
        ->postJson('/api/orders', ['total' => $total])
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

Order::factory()->withItems(5)->create();
Order::factory()->completed()->count(10)->create();
Order::factory()->for($user)->create();
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

`RefreshDatabase` migrates once + per-test transaction. `DatabaseTransactions` skips migration (use when testing transaction behavior itself).

### Facade fakes

```php
Queue::fake();
Queue::assertPushed(ProcessPayment::class, fn($job) => $job->orderId === $order->id);
Queue::assertPushedOn('payments', ProcessPayment::class);

Event::fake([OrderCreated::class]);
Event::assertDispatched(OrderCreated::class, fn($e) => $e->order->id === $order->id);

Notification::fake();
Notification::assertSentTo($user, OrderConfirmationNotification::class);

Mail::fake();
Mail::assertSent(InvoiceMail::class, fn($mail) => $mail->hasTo($order->user->email));

Http::fake(['payments.example.com/*' => Http::response(['status' => 'success'], 200)]);
Http::assertSent(fn($r) => $r->url() === 'https://payments.example.com/charge');
Http::preventStrayRequests();                              // in TestCase::setUp
```

### Testing jobs directly

`Queue::fake` blocks `handle()` execution. To test handler logic, invoke `handle()` with explicit dependencies.

```php
$order = Order::factory()->create(['status' => OrderStatus::Pending]);
$payments = Mockery::mock(PaymentService::class);
$payments->shouldReceive('charge')->once();                 // assert call count

$job = new ProcessPayment($order->id);
$job->handle($payments);
$job->handle($payments);                                    // idempotent: second call is a no-op

expect($order->fresh()->status)->toBe(OrderStatus::Paid);
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
it('rolls back order when payment fails', function () {
    Http::fake(['payments.example.com/*' => Http::response(['error' => 'declined'], 422)]);
    $user = User::factory()->create();

    $this->actingAs($user)->postJson('/api/orders', $validPayload)->assertStatus(422);
    $this->assertDatabaseMissing('orders', ['user_id' => $user->id]);
});
```

### Unit testing services

Skip the HTTP layer when verifying pure logic.

```php
$dto = new CreateOrderDTO(userId: 1, total: '0', items: [/* ... */]);
$order = app(OrderService::class)->create($dto);
expect($order->total)->toBe('149.97');
```

### Test scope decision

| Scope             | What to Test                    | What to Mock                  |
| ----------------- | ------------------------------- | ----------------------------- |
| Feature (HTTP)    | Request/response, DB, status    | External APIs, queues, mail   |
| Feature (Service) | Service method with real DB     | External APIs, queues         |
| Unit              | Single class in isolation       | All dependencies (Mockery)    |
| Job               | `handle()` directly             | External services             |

### CI

```bash
php artisan test --parallel --coverage --min=80
composer phpstan                  # Larastan L5+
vendor/bin/pint --test
composer audit
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

- SQLite test DB when production is MySQL (FK/JSON/date behavior differs)
- `Queue::fake` when you need to verify `handle()` logic - fake blocks execution
- `@depends` or shared mutable state between tests
- Mocking everything in feature tests - real DB catches real bugs
- Inline data duplicated across tests (use factory states)
- Testing private methods - go through the public interface
- `sleep(N)` for async waits - use `Queue::assertPushed`, `Bus::dispatchSync`, or inline processing
- `dd()` / `dump()` in test files
