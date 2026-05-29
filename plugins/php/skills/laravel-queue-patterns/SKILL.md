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
- Choosing Redis vs database driver; Horizon setup
- NOT for: cron (Laravel Scheduler), synchronous flow, WebSocket events

## Rules

- Pass scalar IDs to constructors - models serialize stale snapshots and bloat payloads
- Set `$tries`, `$backoff`, `$timeout` on every job; implement `failed()`
- Dispatch inside `DB::transaction` via `afterCommit()` (or `$afterCommit = true` on job/listener)
- `handle()` is idempotent (retries re-run on transient failure) - guard on persisted state
- No `sync` driver in production

## Patterns

### Job class

```php
class ProcessPayment implements ShouldQueue {
    use Queueable;

    public int $tries = 3;
    public array $backoff = [10, 60, 300];           // escalating
    public int $timeout = 120;

    public function __construct(private readonly int $orderId) {}

    public function handle(PaymentService $payments): void {
        $order = Order::findOrFail($this->orderId);
        if ($order->isPaid()) return;                // idempotent guard
        $payments->charge($order);
    }

    public function failed(\Throwable $e): void {
        Notification::route('slack', config('services.slack.webhook'))
            ->notify(new JobFailedNotification($this->orderId, $e));
    }

    public function tags(): array { return ['order:' . $this->orderId]; }    // Horizon search
}
```

### Dispatching

```php
// Bad - races the commit, sees no row
DB::transaction(function () use ($order) {
    $order->save();
    ProcessPayment::dispatch($order->id);
});

// Good
DB::transaction(function () use ($order) {
    $order->save();
    ProcessPayment::dispatch($order->id)->afterCommit();
});

ProcessPayment::dispatch($id)->onQueue('payments');
SendReminder::dispatch($id)->delay(now()->addMinutes(30));
```

### Retry strategies

| Strategy              | Use When                                | Example                          |
| --------------------- | --------------------------------------- | -------------------------------- |
| Fixed tries + backoff | Known transient failures                | `$tries = 3; $backoff = [...]`   |
| `retryUntil()`        | Must complete within time window        | `return now()->addHours(24)`     |
| Manual `release()`    | Conditional retry per exception         | `$this->release(60)` in `catch`  |
| `ShouldBeUnique`      | One instance per entity in queue        | Payment per order                |

```php
public function retryUntil(): DateTime { return now()->addHours(24); }
```

### Middleware

```php
// Unique by business key
class ProcessPayment implements ShouldQueue, ShouldBeUnique {
    public int $uniqueFor = 60;                                 // lock TTL (releases on crash)
    public function uniqueId(): string { return (string) $this->orderId; }
}

// One running at a time per key (e.g., per-account ledger)
public function middleware(): array {
    return [(new WithoutOverlapping($this->accountId))->releaseAfter(30)];
}

// Third-party API rate limit
RateLimiter::for('stripe', fn() => Limit::perMinute(100));
public function middleware(): array { return [new RateLimited('stripe')]; }
```

### Batching

```php
Bus::batch([new ProcessPayment($o1->id), new ProcessPayment($o2->id)])
    ->then(fn(Batch $b) => Log::info('done', ['id' => $b->id]))
    ->catch(fn(Batch $b, \Throwable $e) => Log::error('first failure', ['id' => $b->id]))
    ->allowFailures()
    ->onQueue('payments')
    ->dispatch();
```

### Chaining

Sequential; subsequent jobs skip if any fail.

```php
Bus::chain([
    new ValidateOrder($order->id),
    new ProcessPayment($order->id),
    new SendConfirmation($order->id),
])->onQueue('orders')->dispatch();
```

### Driver selection

| Feature        | Redis           | Database        |
| -------------- | --------------- | --------------- |
| Setup          | Needs Redis     | Just MySQL      |
| Performance    | High            | Moderate        |
| Monitoring     | Horizon         | Manual          |
| Delayed jobs   | Native          | Polling         |
| Best for       | Production      | Small apps, dev |

```php
// config/queue.php
'redis' => [
    'driver' => 'redis', 'connection' => 'default', 'queue' => 'default',
    'retry_after' => 90, 'block_for' => 5,
],
```

### Priority queues

```php
ProcessPayment::dispatch($id)->onQueue('critical');
SendNewsletter::dispatch($id)->onQueue('low');
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
            'balance' => 'auto',                              // shift workers to busiest
            'minProcesses' => 1, 'maxProcesses' => 10,
            'tries' => 3, 'timeout' => 120,
        ],
    ],
],
```

### Failed jobs

`php artisan queue:failed | queue:retry {id|all} | queue:prune-failed --hours=48`. Wire `failed()` on every job; monitor `failed_jobs` table or Horizon's failed view.

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
- Workers without `--max-time` / `--memory` cap (OOM)
- Ignoring `failed_jobs` (no monitoring, silent loss)
