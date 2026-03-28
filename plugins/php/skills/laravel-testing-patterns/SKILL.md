---
name: laravel-testing-patterns
description: "Testing patterns for Laravel with Pest (primary) and PHPUnit. Covers model factories, HTTP tests, database assertions, facade mocking, queue/event faking, and CI coverage configuration."
metadata:
  category: backend
  tags: [php, laravel, pest, phpunit, testing, factories, mocking]
user-invocable: false
---

## 1. PEST FUNDAMENTALS

Pest is the primary test framework. Use `describe`/`it` syntax for readable test structure.

```php
// Feature test
describe('OrderController', function () {
    it('creates an order', function () {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->postJson('/api/orders', [
            'total' => '99.99',
            'items' => [
                ['product_name' => 'Widget', 'quantity' => 2, 'unit_price' => '49.99'],
            ],
            'shipping_address' => '123 Main St',
        ]);

        $response->assertCreated()
            ->assertJsonPath('data.status', 'pending')
            ->assertJsonCount(1, 'data.items');

        $this->assertDatabaseHas('orders', [
            'user_id' => $user->id,
            'total' => '99.99',
        ]);
    });

    it('requires authentication', function () {
        $this->postJson('/api/orders', [])
            ->assertUnauthorized();
    });

    it('validates required fields', function () {
        $user = User::factory()->create();

        $this->actingAs($user)->postJson('/api/orders', [])
            ->assertUnprocessable()
            ->assertJsonValidationErrors(['total', 'items', 'shipping_address']);
    });
});
```

### Pest Expectations (Fluent Assertions)

```php
expect($order->status)->toBe(OrderStatus::Pending);
expect($order->items)->toHaveCount(3);
expect($order->total)->toBeGreaterThan(0);
expect($user->orders)->each->toBeInstanceOf(Order::class);
expect($response->json('data'))->toMatchArray([
    'status' => 'pending',
    'total' => '99.99',
]);
```

### Datasets (Parametrize)

```php
dataset('invalid_totals', [
    'negative' => [-1],
    'zero' => [0],
    'too_large' => [100000],
    'string' => ['abc'],
]);

it('rejects invalid totals', function (mixed $total) {
    $user = User::factory()->create();

    $this->actingAs($user)->postJson('/api/orders', [
        'total' => $total,
        'items' => [['product_name' => 'X', 'quantity' => 1, 'unit_price' => '1.00']],
        'shipping_address' => '123 Main St',
    ])->assertUnprocessable();
})->with('invalid_totals');
```

## 2. MODEL FACTORIES

```php
class OrderFactory extends Factory
{
    protected $model = Order::class;

    public function definition(): array
    {
        return [
            'user_id' => User::factory(),
            'status' => OrderStatus::Pending,
            'total' => fake()->randomFloat(2, 10, 999),
            'shipping_address' => fake()->address(),
        ];
    }

    // States
    public function completed(): static
    {
        return $this->state(fn(array $attributes) => [
            'status' => OrderStatus::Completed,
        ]);
    }

    public function cancelled(): static
    {
        return $this->state(fn(array $attributes) => [
            'status' => OrderStatus::Cancelled,
        ]);
    }

    // With relationships
    public function withItems(int $count = 3): static
    {
        return $this->has(OrderItem::factory()->count($count), 'items');
    }
}

// Usage
$order = Order::factory()->withItems(5)->create();
$orders = Order::factory()->completed()->count(10)->create();
$order = Order::factory()->for($user)->create();
```

### Sequences

```php
$orders = Order::factory()
    ->count(3)
    ->sequence(
        ['status' => OrderStatus::Pending],
        ['status' => OrderStatus::Processing],
        ['status' => OrderStatus::Completed],
    )
    ->create();
```

## 3. HTTP TESTS

```php
// GET with assertions
$this->actingAs($user)
    ->getJson('/api/orders')
    ->assertOk()
    ->assertJsonCount(5, 'data')
    ->assertJsonStructure([
        'data' => [['id', 'status', 'total', 'created_at']],
        'meta' => ['current_page', 'last_page'],
    ]);

// POST with JSON
$this->actingAs($user)
    ->postJson('/api/orders', $payload)
    ->assertCreated()
    ->assertJsonPath('data.status', 'pending');

// PUT
$this->actingAs($user)
    ->putJson("/api/orders/{$order->id}", ['shipping_address' => 'New Address'])
    ->assertOk();

// DELETE
$this->actingAs($user)
    ->deleteJson("/api/orders/{$order->id}")
    ->assertNoContent();
```

## 4. DATABASE ASSERTIONS

```php
// Always use RefreshDatabase trait
uses(RefreshDatabase::class);

// Assert record exists
$this->assertDatabaseHas('orders', [
    'user_id' => $user->id,
    'status' => 'pending',
]);

// Assert record does not exist
$this->assertDatabaseMissing('orders', [
    'id' => $order->id,
]);

// Assert record count
$this->assertDatabaseCount('orders', 5);

// Assert soft-deleted
$this->assertSoftDeleted('orders', ['id' => $order->id]);
```

## 5. FACADE MOCKING

```php
// Queue fake - verify jobs dispatched without running them
it('dispatches payment job after order creation', function () {
    Queue::fake();

    $user = User::factory()->create();
    $this->actingAs($user)->postJson('/api/orders', $validPayload);

    Queue::assertPushed(ProcessPayment::class, function ($job) {
        return $job->orderId === Order::first()->id;
    });
    Queue::assertPushedOn('payments', ProcessPayment::class);
});

// Event fake
it('dispatches OrderCreated event', function () {
    Event::fake([OrderCreated::class]);

    // ... trigger action ...

    Event::assertDispatched(OrderCreated::class, function ($event) use ($order) {
        return $event->order->id === $order->id;
    });
});

// Notification fake
it('sends confirmation notification', function () {
    Notification::fake();

    // ... trigger action ...

    Notification::assertSentTo($user, OrderConfirmationNotification::class);
});

// Mail fake
it('sends invoice email', function () {
    Mail::fake();

    // ... trigger action ...

    Mail::assertSent(InvoiceMail::class, function ($mail) use ($order) {
        return $mail->hasTo($order->user->email);
    });
});

// HTTP client fake (external API calls)
it('calls payment gateway', function () {
    Http::fake([
        'payments.example.com/*' => Http::response(['status' => 'success'], 200),
    ]);

    // ... trigger action ...

    Http::assertSent(function ($request) {
        return $request->url() === 'https://payments.example.com/charge'
            && $request['amount'] === 9999;
    });
});
```

## 6. TESTING JOBS DIRECTLY

```php
// Test job handle() logic directly
it('processes payment for order', function () {
    $order = Order::factory()->create(['status' => OrderStatus::Pending]);

    $paymentService = Mockery::mock(PaymentService::class);
    $paymentService->shouldReceive('charge')->once()->with(
        Mockery::on(fn($o) => $o->id === $order->id)
    );

    $job = new ProcessPayment($order->id);
    $job->handle($paymentService);

    expect($order->fresh()->status)->toBe(OrderStatus::Processing);
});
```

## 7. TESTING AUTHORIZATION

```php
it('prevents non-owner from viewing order', function () {
    $order = Order::factory()->create();
    $otherUser = User::factory()->create();

    $this->actingAs($otherUser)
        ->getJson("/api/orders/{$order->id}")
        ->assertForbidden();
});

it('allows owner to view order', function () {
    $order = Order::factory()->create();

    $this->actingAs($order->user)
        ->getJson("/api/orders/{$order->id}")
        ->assertOk();
});
```

## 8. TEST ORGANIZATION

```
tests/
  Pest.php                     # Pest configuration (uses, helpers)
  Feature/
    Http/
      OrderControllerTest.php  # API endpoint tests
      AuthControllerTest.php
    Jobs/
      ProcessPaymentTest.php   # Queue job tests
    Services/
      OrderServiceTest.php     # Service integration tests
  Unit/
    Actions/
      CreateOrderTest.php      # Action unit tests
    Models/
      OrderTest.php            # Model scope, cast, relationship tests
```

### Pest.php Configuration

```php
// tests/Pest.php
uses(Tests\TestCase::class, RefreshDatabase::class)->in('Feature');
uses(Tests\TestCase::class)->in('Unit');
```

## 9. CI AND COVERAGE

```xml
<!-- phpunit.xml -->
<coverage>
    <include>
        <directory suffix=".php">app</directory>
    </include>
    <exclude>
        <directory>app/Providers</directory>
    </exclude>
</coverage>

<php>
    <env name="APP_ENV" value="testing"/>
    <env name="DB_CONNECTION" value="mysql"/>
    <env name="DB_DATABASE" value="testing"/>
    <env name="QUEUE_CONNECTION" value="sync"/>
    <env name="CACHE_STORE" value="array"/>
    <env name="SESSION_DRIVER" value="array"/>
</php>
```

```bash
# Run tests with coverage
php artisan test --coverage --min=80

# Run specific test file
php artisan test --filter=OrderControllerTest

# Parallel testing
php artisan test --parallel
```

## 10. ANTI-PATTERNS

- ❌ PHPUnit class-based syntax when Pest is available (use `it()`, `expect()`, `describe()`)
- ❌ Testing against SQLite when production is MySQL (behavior differences with JSON, dates, constraints)
- ❌ Missing `RefreshDatabase` trait (test isolation failure)
- ❌ `@depends` between test methods (tests must be independent)
- ❌ Mocking everything (test real DB interactions for feature tests)
- ❌ `Queue::fake()` in tests that need to verify job handle() logic (fake prevents execution)
- ❌ Shared mutable state between tests
- ❌ Missing factory states (inline data setup duplicated across tests)
- ❌ Testing private methods directly (test through public interface)
- ❌ `dd()` left in test files
