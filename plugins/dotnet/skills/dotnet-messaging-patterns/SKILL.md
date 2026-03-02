---
name: dotnet-messaging-patterns
description: MassTransit consumers, sagas, outbox pattern, and Hangfire background jobs for .NET 8
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
- Always implement `IConsumer<T>` — never subscribe to raw broker events in application code
- Use the **transactional outbox** (`MassTransit.EntityFrameworkCore`) to guarantee at-least-once delivery
- Consumers must be idempotent — messages can be redelivered
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
- Long-running synchronous work inside a consumer — offload to Hangfire if needed
- Missing dead-letter queue configuration (messages are silently dropped)
