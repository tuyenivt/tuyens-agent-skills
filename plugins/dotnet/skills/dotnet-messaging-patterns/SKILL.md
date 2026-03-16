---
name: dotnet-messaging-patterns
description: Implement reliable async messaging with MassTransit consumers, transactional outbox, retry policies, and Hangfire for scheduled background jobs.
metadata:
  category: backend
  tags: [masstransit, hangfire, messaging, background-jobs, outbox, saga]
user-invocable: false
---

# Messaging Patterns

## When to Use

- Implementing event-driven communication between services with MassTransit
- Scheduling or queuing background jobs with Hangfire
- Ensuring reliable message delivery with the transactional outbox pattern
- Orchestrating multi-step workflows with MassTransit sagas

## Rules

- Use MassTransit for inter-service async messaging; use Hangfire for scheduled/delayed single-service jobs
- Always implement `IConsumer<T>` - never subscribe to raw broker events in application code
- Use the **transactional outbox** (`MassTransit.EntityFrameworkCore`) to guarantee at-least-once delivery
- Consumers must be idempotent - messages can be redelivered
- Configure retry policies and dead-letter queues for every consumer
- Hangfire jobs must be idempotent; use `DisableConcurrentExecution` for non-idempotent jobs

## Pattern

MassTransit consumer:

```csharp
public sealed class OrderPlacedConsumer(IOrderService orderService, ILogger<OrderPlacedConsumer> logger)
    : IConsumer<OrderPlaced>
{
    public async Task Consume(ConsumeContext<OrderPlaced> context)
    {
        logger.LogInformation("Processing OrderPlaced {OrderId}", context.Message.OrderId);
        await orderService.ProcessAsync(context.Message.OrderId, context.CancellationToken);
    }
}
```

MassTransit + EF Core outbox registration:

```csharp
builder.Services.AddMassTransit(x =>
{
    x.AddEntityFrameworkOutbox<AppDbContext>(o =>
    {
        o.UsePostgres();
        o.UseBusOutbox();
    });

    x.AddConsumer<OrderPlacedConsumer>()
        .Endpoint(e => e.Name = "order-placed");

    x.UsingRabbitMq((ctx, cfg) =>
    {
        cfg.Host(builder.Configuration["RabbitMq:Host"]);
        cfg.UseMessageRetry(r => r.Exponential(5, TimeSpan.FromSeconds(1), TimeSpan.FromMinutes(5), TimeSpan.FromSeconds(1)));
        cfg.ConfigureEndpoints(ctx);
    });
});
```

Hangfire recurring job:

```csharp
// Registration
builder.Services.AddHangfire(cfg => cfg.UsePostgreSqlStorage(connStr));
builder.Services.AddHangfireServer();

// Schedule
RecurringJob.AddOrUpdate<IReportGenerationService>(
    "daily-report",
    svc => svc.GenerateAsync(CancellationToken.None),
    Cron.Daily);
```

## Avoid

- Publishing events directly in the domain layer (use domain events + outbox instead)
- Fire-and-forget `Task.Run` for background work that must be reliable
- Consumers that are not idempotent
- Long-running synchronous work inside a consumer - offload to Hangfire if needed
- Missing dead-letter queue configuration (messages are silently dropped)

## Edge Cases

- **Outbox requires SaveChangesAsync**: The transactional outbox only publishes messages when `SaveChangesAsync()` is called on the same `DbContext`. If you publish without saving, the message is lost. Always publish within the same unit of work that persists domain state.
- **Consumer DI scope**: MassTransit creates a new DI scope per message. Scoped services (e.g., `DbContext`) work correctly. Do not inject singleton services that hold mutable state.
- **Hangfire serialization**: Hangfire serializes job arguments to JSON. Do not pass complex objects, `CancellationToken`, or EF entities as job parameters - pass identifiers and resolve dependencies inside the job.
- **MassTransit in-memory for testing**: Use `x.UsingInMemory()` in integration tests instead of requiring a real RabbitMQ broker. This avoids flaky tests while still exercising consumer logic.
- **Duplicate consumer registration**: If a consumer is registered both via `AddConsumer<T>()` and auto-discovery (`AddConsumers(assembly)`), it runs twice per message. Use one registration method consistently.
