---
name: dotnet-async-patterns
description: "ASP.NET Core async/await correctness: CancellationToken propagation, background service lifecycle, thread-starvation prevention."
metadata:
  category: backend
  tags: [async, cancellation-token, background-services, hosted-services]
user-invocable: false
---

# Async Patterns

## When to Use

- Reviewing or writing async service methods, controllers, or `BackgroundService`
- Propagating `CancellationToken` through call stacks
- Diagnosing deadlocks, thread starvation, or silently-stopping hosted services

## Rules

- Accept and propagate `CancellationToken` on every async method; pass it to every awaited call including `Task.Delay`. `default` only at top-level entry points.
- Always `await`. Never `.Result`, `.Wait()`, `.GetAwaiter().GetResult()`, or `Thread.Sleep` in async code.
- Return `async Task`, never `async void` (event handlers excepted).
- Long-running work goes in `BackgroundService` registered via `AddHostedService<T>()`. No `Task.Run` for background work in request handlers.
- In `BackgroundService.ExecuteAsync`, loop on `!stoppingToken.IsCancellationRequested` and resolve scoped services via `IServiceScopeFactory.CreateAsyncScope()`.
- Producer/consumer uses `Channel<T>` or a message bus, not polled `ConcurrentQueue`.
- `Task.WhenAll` for independent parallel awaits.

## Patterns

### CancellationToken propagation

```csharp
// Bad: token dropped at the Delay; controller never accepts one.
public async Task<OrderDto> GetOrderAsync(Guid id)
{
    await Task.Delay(100);
    return await _repo.GetByIdAsync(id);
}

// Good: token threaded through every await - including EF and HTTP sinks.
public async Task<OrderDto> GetOrderAsync(Guid id, CancellationToken ct)
{
    var resp = await _http.GetAsync(url, ct);
    var order = await _db.Orders.Where(o => o.Id == id).FirstOrDefaultAsync(ct);
    return _mapper.Map<OrderDto>(order);
}
```

`ToListAsync(ct)` / `FirstOrDefaultAsync(ct)` / `SaveChangesAsync(ct)` and `HttpClient` calls are the sinks where dropped tokens hide; minimal-API handlers auto-bind `CancellationToken` from `HttpContext.RequestAborted`.

### BackgroundService loop

```csharp
public sealed class OutboxProcessorService(
    IServiceScopeFactory scopeFactory) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            await using var scope = scopeFactory.CreateAsyncScope();
            var processor = scope.ServiceProvider.GetRequiredService<IOutboxProcessor>();
            await processor.ProcessPendingAsync(stoppingToken);
            await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
        }
    }
}
```

Common `ExecuteAsync` bugs: `Thread.Sleep` or `.Result` blocking the host startup path; `while (true)` ignoring `stoppingToken`; `IServiceProvider.CreateScope()` for async-disposable services; unhandled exceptions silently stopping the service. For the last, choose per intent: a resilient worker try/catches *inside* the loop and continues (re-throwing `OperationCanceledException` when `stoppingToken` fired, so shutdown still works); a fail-fast critical service sets `HostOptions.BackgroundServiceExceptionBehavior = StopHost`. Do not do both.

### Edge cases

- `ConfigureAwait(false)`: omit in ASP.NET Core app code (no `SynchronizationContext`). Use in shared libraries.
- `ValueTask<T>`: only when the method frequently completes synchronously. Awaitable once, not concurrently. Default to `Task<T>`.
- Third-party API without `CancellationToken`: wrap with `Task.WhenAny(actualTask, Task.Delay(Timeout.Infinite, ct))`.

## Output Format

```
Finding: <one-line summary>
Location: <file>:<line>
Severity: {Critical | High | Medium | Low}
Rule: <which rule or pattern violated>
Fix: <minimal change>
```

Severity guide:
- Critical: `async void`, `.Result`/`.Wait()`, missing `stoppingToken` check, unhandled exception silently stopping a `BackgroundService`, `HttpContext` capture in background work.
- High: missing `CancellationToken` propagation, `Task.Run` in request handlers.
- Medium: `ConfigureAwait(false)` noise, `ValueTask` misuse.

## Avoid

- Capturing `HttpContext` or scoped services into background work or fire-and-forget `Task.Run`.
- Swallowing `OperationCanceledException` - let it propagate.
- Reusing or concurrently awaiting a `ValueTask<T>`.
