---
name: laravel-queue-patterns
description: "Laravel Queue patterns - job classes, retry strategies, batching, chaining, rate limiting, failed job handling, driver selection (Redis/database), and Horizon monitoring."
metadata:
  category: backend
  tags: [php, laravel, queue, jobs, redis, horizon, batching]
user-invocable: false
---

## 1. JOB CLASSES

```php
class ProcessPayment implements ShouldQueue
{
    use Queueable;

    public int $tries = 3;
    public array $backoff = [10, 60, 300]; // seconds between retries
    public int $timeout = 120; // max execution time in seconds

    public function __construct(
        private readonly int $orderId, // always pass IDs, not models
    ) {}

    public function handle(PaymentService $paymentService): void
    {
        $order = Order::findOrFail($this->orderId);
        $paymentService->charge($order);
    }

    public function failed(\Throwable $exception): void
    {
        // Notify team, log, or take compensating action
        Log::error('Payment processing failed', [
            'order_id' => $this->orderId,
            'exception' => $exception->getMessage(),
        ]);
    }
}
```

### Job Arguments

```php
// Bad - passing Eloquent model (serialization issues, stale data)
new ProcessPayment($order);

// Good - pass scalar IDs, fetch fresh data in handle()
new ProcessPayment($order->id);

// Good - multiple scalar args
new SendInvoice(orderId: $order->id, email: $user->email);
```

## 2. DISPATCH PATTERNS

```php
// Basic dispatch
ProcessPayment::dispatch($order->id);

// Dispatch after DB transaction commits (prevents processing uncommitted data)
ProcessPayment::dispatch($order->id)->afterCommit();

// Dispatch to specific queue
ProcessPayment::dispatch($order->id)->onQueue('payments');

// Delay execution
SendReminder::dispatch($order->id)->delay(now()->addMinutes(30));

// Dispatch from event listener (afterCommit on listener)
class ProcessOrderPayment
{
    public bool $afterCommit = true;

    public function handle(OrderCreated $event): void
    {
        ProcessPayment::dispatch($event->order->id);
    }
}
```

## 3. RETRY STRATEGIES

```php
// Fixed retry count with escalating backoff
public int $tries = 3;
public array $backoff = [10, 60, 300]; // 10s, 1m, 5m

// Retry until a deadline
public function retryUntil(): DateTime
{
    return now()->addHours(24);
}

// Conditional retry in handle()
public function handle(): void
{
    try {
        $this->processPayment();
    } catch (TemporaryFailureException $e) {
        $this->release(60); // retry in 60 seconds
    }
}
```

## 4. UNIQUE JOBS

Prevent duplicate jobs from being dispatched.

```php
class ProcessPayment implements ShouldQueue, ShouldBeUnique
{
    use Queueable;

    // Unique by order ID - only one ProcessPayment per order in queue
    public function uniqueId(): string
    {
        return (string) $this->orderId;
    }

    // Unique lock expires after 60 seconds (prevents permanent lock on failure)
    public int $uniqueFor = 60;
}
```

## 5. JOB BATCHING

```php
use Illuminate\Bus\Batch;
use Illuminate\Support\Facades\Bus;

$batch = Bus::batch([
    new ProcessPayment($order1->id),
    new ProcessPayment($order2->id),
    new ProcessPayment($order3->id),
])
->then(function (Batch $batch) {
    // All jobs completed successfully
    Log::info('Batch completed', ['batch_id' => $batch->id]);
})
->catch(function (Batch $batch, \Throwable $e) {
    // First batch job failure
    Log::error('Batch failed', ['batch_id' => $batch->id]);
})
->finally(function (Batch $batch) {
    // Batch finished (regardless of success/failure)
})
->allowFailures()
->onQueue('payments')
->dispatch();
```

## 6. JOB CHAINING

Sequential execution where each job depends on the previous.

```php
Bus::chain([
    new ValidateOrder($order->id),
    new ProcessPayment($order->id),
    new SendConfirmation($order->id),
    new UpdateInventory($order->id),
])->onQueue('orders')->dispatch();

// If any job fails, remaining jobs are skipped
```

## 7. RATE LIMITING

```php
// Define rate limiter
// AppServiceProvider::boot()
RateLimiter::for('emails', function (object $job) {
    return Limit::perMinute(30);
});

// Apply to job
class SendInvoice implements ShouldQueue
{
    use Queueable;

    public function middleware(): array
    {
        return [new RateLimited('emails')];
    }
}
```

## 8. QUEUE DRIVER SELECTION

### Redis Driver (Recommended)

```php
// config/queue.php
'redis' => [
    'driver' => 'redis',
    'connection' => 'default',
    'queue' => 'default',
    'retry_after' => 90,
    'block_for' => 5, // block for 5s when polling (reduces Redis calls)
],
```

### Database Driver (Simpler Setup)

```php
// Create jobs table
// php artisan queue:table && php artisan migrate

// config/queue.php
'database' => [
    'driver' => 'database',
    'connection' => null, // uses default DB connection
    'table' => 'jobs',
    'queue' => 'default',
    'retry_after' => 90,
    'after_commit' => false,
],

// Create failed_jobs table
// php artisan queue:failed-table && php artisan migrate
```

### Driver Comparison

| Feature          | Redis          | Database        |
| ---------------- | -------------- | --------------- |
| Setup complexity | Requires Redis | Just MySQL      |
| Performance      | High           | Moderate        |
| Monitoring       | Horizon        | Manual / custom |
| Delayed jobs     | Native support | Polling-based   |
| Unique jobs      | Atomic locks   | DB locks        |
| Best for         | Production     | Small apps, dev |

### Database Driver Tuning

```php
// Polling interval - higher = less DB load, more latency
// Supervisor config
[program:queue-worker]
command=php artisan queue:work database --sleep=3 --tries=3 --timeout=90

// For low-latency needs with database driver, reduce sleep:
command=php artisan queue:work database --sleep=1
```

## 9. FAILED JOB HANDLING

```php
// List failed jobs
// php artisan queue:failed

// Retry a specific failed job
// php artisan queue:retry {id}

// Retry all failed jobs
// php artisan queue:retry all

// Delete old failed jobs
// php artisan queue:flush

// Prune failed jobs older than 48 hours
// php artisan queue:prune-failed --hours=48
```

### Custom Failed Job Handling

```php
// In job class
public function failed(\Throwable $exception): void
{
    // Send alert, compensating transaction, etc.
    Notification::route('slack', config('services.slack.webhook'))
        ->notify(new JobFailedNotification($this->orderId, $exception));
}
```

## 10. PRIORITY QUEUES

```php
// Dispatch to specific queue
ProcessPayment::dispatch($id)->onQueue('critical');
SendNewsletter::dispatch($id)->onQueue('low');

// Worker processes queues in priority order
// php artisan queue:work --queue=critical,default,low
```

## 11. HORIZON (Redis Only)

```php
// config/horizon.php
'environments' => [
    'production' => [
        'supervisor-1' => [
            'connection' => 'redis',
            'queue' => ['critical', 'default', 'low'],
            'balance' => 'auto', // auto-balance workers across queues
            'minProcesses' => 1,
            'maxProcesses' => 10,
            'tries' => 3,
            'timeout' => 120,
        ],
    ],
],
```

## 12. ANTI-PATTERNS

- ❌ Passing Eloquent models as job constructor arguments (serialization, stale data)
- ❌ Dispatching jobs inside DB transactions without `afterCommit()` (job processes before commit)
- ❌ Missing `$tries` and `$backoff` on jobs (infinite retries or no retry)
- ❌ Missing `failed()` method (silent failures)
- ❌ Missing `$timeout` on long-running jobs (hangs worker)
- ❌ Large payloads in job arguments (pass IDs, fetch in handle)
- ❌ Non-idempotent jobs (duplicate processing on retry)
- ❌ No monitoring on failed jobs table (failures go unnoticed)
- ❌ `sync` driver in production (blocks the request)
- ❌ Not setting `--memory` flag on workers (OOM risk)
