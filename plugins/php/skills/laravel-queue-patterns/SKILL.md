---
name: laravel-queue-patterns
description: "Laravel Queue patterns: job classes, retries, batching, chaining, rate limiting, failed jobs, Redis/database drivers, Horizon monitoring."
metadata:
  category: backend
  tags: [php, laravel, queue, jobs, redis, horizon, batching]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Background processing, retries, batching, chaining, rate limiting
- Choosing between Redis and database drivers; Horizon setup
- NOT for: cron (Laravel Scheduler), synchronous flow, WebSocket events

## Rules

- Pass scalar IDs to constructors - models serialize stale and bloat the payload
- Set `$tries`, `$backoff`, `$timeout` on every job (otherwise infinite retries or hung workers)
- Implement `failed()` - otherwise failures land silently in `failed_jobs`
- Dispatch inside transactions via `afterCommit()` - jobs race the commit and see uncommitted state
- Jobs must be idempotent (retries re-run on transient failure)
- No `sync` driver in production (blocks the request)

## Patterns

### Job class

```php
class ProcessPayment implements ShouldQueue {
    use Queueable;

    public int $tries = 3;
    public array $backoff = [10, 60, 300]; // escalating
    public int $timeout = 120;

    public function __construct(private readonly int $orderId) {}

    public function handle(PaymentService $payments): void {
        $order = Order::findOrFail($this->orderId);
        if ($order->isPaid()) return;        // idempotent guard
        $payments->charge($order);
    }

    public function failed(\Throwable $e): void {
        Notification::route('slack', config('services.slack.webhook'))
            ->notify(new JobFailedNotification($this->orderId, $e));
    }
}
```

### Dispatching

```php
// Bad - job may run before transaction commits, sees no row
DB::transaction(function () use ($order) {
    $order->save();
    ProcessPayment::dispatch($order->id);
});

// Good - afterCommit defers dispatch until commit succeeds
DB::transaction(function () use ($order) {
    $order->save();
    ProcessPayment::dispatch($order->id)->afterCommit();
});

ProcessPayment::dispatch($id)->onQueue('payments');
SendReminder::dispatch($id)->delay(now()->addMinutes(30));

// Listener-level afterCommit applies to every job it dispatches
class ProcessOrderPayment {
    public bool $afterCommit = true;
    public function handle(OrderCreated $e): void {
        ProcessPayment::dispatch($e->order->id);
    }
}
```

### Retry strategies

| Strategy              | Use When                                | Example                          |
| --------------------- | --------------------------------------- | -------------------------------- |
| Fixed tries + backoff | Known transient failures (API timeouts) | `$tries = 3; $backoff = [...]`   |
| `retryUntil()`        | Must complete within time window        | `return now()->addHours(24)`     |
| Manual `release()`    | Conditional retry per exception         | `$this->release(60)` in `catch`  |
| `ShouldBeUnique`      | One instance per entity in queue        | Payment per order                |

```php
public function retryUntil(): DateTime { return now()->addHours(24); }

public function handle(): void {
    try { $this->processPayment(); }
    catch (TemporaryFailureException) { $this->release(60); }
}
```

### Unique jobs

```php
// Bad - two dispatches concurrently charge the same order
ProcessPayment::dispatch($order->id);
ProcessPayment::dispatch($order->id);

// Good - ShouldBeUnique locks per orderId
class ProcessPayment implements ShouldQueue, ShouldBeUnique {
    use Queueable;
    public int $uniqueFor = 60; // lock TTL releases on crash
    public function uniqueId(): string { return (string) $this->orderId; }
}
```

### Batching

```php
Bus::batch([
    new ProcessPayment($o1->id),
    new ProcessPayment($o2->id),
])
->then(fn(Batch $b) => Log::info('done', ['id' => $b->id]))
->catch(fn(Batch $b, \Throwable $e) => Log::error('first failure', ['id' => $b->id]))
->finally(fn(Batch $b) => /* always */)
->allowFailures()
->onQueue('payments')
->dispatch();
```

### Chaining

Sequential jobs; subsequent jobs skip if any fail.

```php
Bus::chain([
    new ValidateOrder($order->id),
    new ProcessPayment($order->id),
    new SendConfirmation($order->id),
])->onQueue('orders')->dispatch();
```

### Rate limiting

```php
// AppServiceProvider::boot()
RateLimiter::for('emails', fn(object $job) => Limit::perMinute(30));

class SendInvoice implements ShouldQueue {
    use Queueable;
    public function middleware(): array { return [new RateLimited('emails')]; }
}
```

### Driver selection

| Feature        | Redis           | Database        |
| -------------- | --------------- | --------------- |
| Setup          | Needs Redis     | Just MySQL      |
| Performance    | High            | Moderate        |
| Monitoring     | Horizon         | Manual          |
| Delayed jobs   | Native          | Polling         |
| Unique jobs    | Atomic locks    | DB locks        |
| Best for       | Production      | Small apps, dev |

```php
// config/queue.php
'redis' => [
    'driver' => 'redis', 'connection' => 'default', 'queue' => 'default',
    'retry_after' => 90,
    'block_for' => 5, // long-poll to reduce Redis traffic
],

'database' => [
    'driver' => 'database', 'table' => 'jobs', 'queue' => 'default',
    'retry_after' => 90, 'after_commit' => false,
],
// php artisan queue:table && queue:failed-table && migrate
```

### Failed jobs

```bash
php artisan queue:failed                  # list
php artisan queue:retry {id|all}          # retry
php artisan queue:prune-failed --hours=48 # cleanup
```

### Priority queues

```php
ProcessPayment::dispatch($id)->onQueue('critical');
SendNewsletter::dispatch($id)->onQueue('low');
// Worker drains in declared order
// php artisan queue:work --queue=critical,default,low
```

### Horizon (Redis)

```php
// config/horizon.php
'environments' => [
    'production' => [
        'supervisor-1' => [
            'connection' => 'redis',
            'queue' => ['critical', 'default', 'low'],
            'balance' => 'auto',         // shift workers to busiest queue
            'minProcesses' => 1, 'maxProcesses' => 10,
            'tries' => 3, 'timeout' => 120,
        ],
    ],
],
```

### Idempotency

```php
// Bad - retry double-charges
public function handle(PaymentService $p): void {
    $p->charge(Order::findOrFail($this->orderId));
}

// Good - guard on persisted state
public function handle(PaymentService $p): void {
    $order = Order::findOrFail($this->orderId);
    if ($order->isPaid()) return;
    $p->charge($order);
}
```

## Output Format

```
## Job Classes
| Job | Queue | Trigger | Tries | Timeout | Unique |

## Queue Configuration
Driver: {redis | database}
Monitoring: {Horizon | manual}

## Retry Strategy
| Job | Strategy | Backoff | Failed Handler |
```

## Avoid

- Eloquent models in constructors (serialization, stale data)
- Dispatch inside transaction without `afterCommit()`
- Missing `$tries` / `$backoff` / `$timeout` / `failed()`
- Large payloads (pass IDs, refetch in `handle`)
- Non-idempotent handlers
- `sync` driver in production
- Workers without `--memory` cap (OOM)
- Ignoring `failed_jobs` (no monitoring, silent loss)
