---
name: dotnet-async-patterns
description: Enforce async/await correctness including CancellationToken propagation, background service lifecycle, and thread-starvation prevention in ASP.NET Core.
metadata:
  category: backend
  tags: [async, cancellation-token, background-services, hosted-services]
user-invocable: false
---

# Async Patterns

## When to Use

- Implementing async service methods and controllers
- Propagating `CancellationToken` through the call stack
- Building background processing with `IHostedService` or `BackgroundService`
- Avoiding deadlocks and thread starvation in ASP.NET Core

## Rules

- Every async method must accept and propagate `CancellationToken` - no `default` except at top-level entry points
- Never use `.Result`, `.Wait()`, or `.GetAwaiter().GetResult()` - always `await`
- Never use `async void` except in event handlers; use `async Task` instead
- Prefer `Task.WhenAll()` for independent parallel async operations
- Use `IHostedService` / `BackgroundService` for long-running background work - not `Task.Run` in controllers
- Register background services with `AddHostedService<T>()`
- Use `Channel<T>` or MassTransit for producer/consumer patterns; avoid shared `ConcurrentQueue` with polling
- Do not use `ConfigureAwait(false)` in ASP.NET Core app code - it is unnecessary since ASP.NET Core has no `SynchronizationContext`. Only use it in shared library code that may run outside ASP.NET Core.
- Prefer `ValueTask<T>` over `Task<T>` only when the method frequently completes synchronously (e.g., cache hits). Do not use `ValueTask<T>` as a default - it has stricter consumption rules (cannot be awaited twice or concurrently).

## Edge Cases

- **Missing CancellationToken on interface**: When a third-party interface does not accept `CancellationToken`, wrap the call with `Task.WhenAny(actualTask, Task.Delay(Timeout.Infinite, ct))` or use a `CancellationTokenSource` with a timeout.
- **BackgroundService exception swallowing**: In .NET 6+, an unhandled exception in `ExecuteAsync` stops the hosted service silently by default. Set `HostOptions.BackgroundServiceExceptionBehavior = BackgroundServiceExceptionBehavior.StopHost` to fail fast instead.
- **Startup deadlock**: `ExecuteAsync` runs on the host startup path. If it blocks synchronously (e.g., waiting on a semaphore), the entire host hangs. Always ensure the first `await` yields quickly.

## Pattern

Correct CancellationToken propagation:

```csharp
public async Task<OrderDto> GetOrderAsync(Guid id, CancellationToken ct)
{
    var order = await _repository.GetByIdAsync(id, ct)
        ?? throw new NotFoundException(nameof(Order), id);
    return _mapper.Map<OrderDto>(order);
}
```

Background service:

```csharp
public sealed class OutboxProcessorService(IServiceScopeFactory scopeFactory, ILogger<OutboxProcessorService> logger)
    : BackgroundService
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

## Avoid

- `async void` methods (unhandled exceptions crash the process)
- Blocking async code with `.Result` or `.Wait()`
- Fire-and-forget `Task.Run` inside request handlers
- Ignoring `OperationCanceledException` - let it propagate or handle gracefully
- Capturing `HttpContext` in background work (it is request-scoped and disposed after the response)
- Awaiting a `ValueTask<T>` more than once or storing it for later consumption
- `ConfigureAwait(false)` scattered through ASP.NET Core application code (no effect, adds noise)
