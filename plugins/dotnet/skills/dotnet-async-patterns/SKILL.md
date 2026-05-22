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

- Reviewing or writing async service methods, controllers, or `BackgroundService` implementations
- Propagating `CancellationToken` through call stacks
- Diagnosing deadlocks, thread starvation, or silently-stopping hosted services

## Rules

- Accept and propagate `CancellationToken` on every async method; pass it to every awaited call including `Task.Delay`. `default` only at top-level entry points.
- Always `await`. Never `.Result`, `.Wait()`, `.GetAwaiter().GetResult()`, or `Thread.Sleep` in async code.
- Use `async Task`, never `async void` (event handlers excepted).
- Long-running background work goes in `BackgroundService` / `IHostedService` registered via `AddHostedService<T>()`. No `Task.Run` for background work in controllers.
- In `BackgroundService.ExecuteAsync`, loop on `!stoppingToken.IsCancellationRequested` and use `IServiceScopeFactory` (not `IServiceProvider.CreateScope` directly) with `CreateAsyncScope()`.
- Producer/consumer: `Channel<T>` or MassTransit. Not `ConcurrentQueue` with polling.
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
```

```csharp
// Good: token threaded through every await.
public async Task<OrderDto> GetOrderAsync(Guid id, CancellationToken ct)
{
    var order = await _repo.GetByIdAsync(id, ct)
        ?? throw new NotFoundException(nameof(Order), id);
    return _mapper.Map<OrderDto>(order);
}
```

### BackgroundService loop

```csharp
// Bad: ignores stoppingToken, blocks startup, fire-and-forget loses exceptions,
// IServiceProvider.CreateScope is sync and not awaitable for async disposables.
protected override async Task ExecuteAsync(CancellationToken stoppingToken)
{
    Thread.Sleep(2000);
    while (true)
    {
        var scope = _sp.CreateScope();
        var pending = scope.ServiceProvider.GetRequiredService<IOutboxProcessor>()
            .GetPendingAsync().Result;
        foreach (var o in pending) Task.Run(() => Process(o));
        await Task.Delay(1000);
    }
}
```

```csharp
public sealed class OutboxProcessorService(
    IServiceScopeFactory scopeFactory,
    ILogger<OutboxProcessorService> logger) : BackgroundService
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

### Nuanced guidance

- **`ConfigureAwait(false)`**: omit in ASP.NET Core app code (no `SynchronizationContext`). Use only in shared libraries that may run outside ASP.NET Core.
- **`ValueTask<T>`**: use only when the method frequently completes synchronously (e.g., cache hits). Awaitable once, not concurrently. Default to `Task<T>`.
- **Third-party interface without `CancellationToken`**: wrap with `Task.WhenAny(actualTask, Task.Delay(Timeout.Infinite, ct))` or a `CancellationTokenSource` timeout.
- **`BackgroundService` exception handling**: unhandled exceptions in `ExecuteAsync` silently stop the service. Set `HostOptions.BackgroundServiceExceptionBehavior = StopHost` to fail fast, or wrap the loop body in try/catch that logs and continues.
- **Startup blocking**: `ExecuteAsync` runs on the host startup path. Yield (`await Task.Yield()` or an awaited I/O call) before any sync work so the host can finish starting.

## Output Format

When reviewing code, report findings as:

```
Finding: <one-line summary>
Location: <file>:<line>
Severity: {Critical | High | Medium | Low}
Rule: <which rule or pattern violated>
Fix: <minimal change>
```

Severity guide: `async void`, `.Result`/`.Wait()`, missing `stoppingToken` check, `HttpContext` capture in background = Critical. Missing `CancellationToken` propagation, `Task.Run` in request handlers = High. `ConfigureAwait(false)` noise, `ValueTask` misuse = Medium.

## Avoid

- Capturing `HttpContext` (request-scoped, disposed after response) or any scoped service into background work or fire-and-forget `Task.Run`.
- Swallowing `OperationCanceledException` - let it propagate.
- Reusing or concurrently awaiting a `ValueTask<T>`.
