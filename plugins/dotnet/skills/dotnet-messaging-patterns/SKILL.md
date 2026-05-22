---
name: dotnet-messaging-patterns
description: Implement reliable async messaging with MassTransit consumers, transactional outbox, retries, DLQ, and Hangfire scheduled jobs.
metadata:
  category: backend
  tags: [masstransit, hangfire, messaging, background-jobs, outbox, saga]
user-invocable: false
---

# Messaging Patterns

## When to Use

- Event-driven communication between services (MassTransit)
- Reliable publish guarantees alongside a database write (outbox)
- Scheduled, delayed, or recurring background work (Hangfire)
- Multi-step orchestrations across services (MassTransit sagas)

## Rules

- MassTransit for cross-service async messaging; Hangfire for in-process scheduled/delayed jobs
- Implement `IConsumer<T>`; never subscribe to raw broker APIs from application code
- Use `AddEntityFrameworkOutbox` (bus outbox) so publishes commit with `SaveChangesAsync` in one transaction
- Consumers and Hangfire jobs are idempotent; guard side effects by message/job id
- Configure retry and dead-letter (`_error` / `_skipped`) for every consumer
- Pass identifiers (not entities, `DbContext`, or `CancellationToken`) as Hangfire job arguments

## Patterns

**Outbox - publish commits with the DB write.**

Bad - publish escapes if `SaveChangesAsync` later throws (or vice versa):

```csharp
await _publishEndpoint.Publish(new OrderPlaced(orderId));
await _db.SaveChangesAsync(); // may throw; event already on wire
```

Good - `UseBusOutbox` defers the publish until the same transaction commits:

```csharp
x.AddEntityFrameworkOutbox<AppDbContext>(o => { o.UsePostgres(); o.UseBusOutbox(); });
// In the handler:
await _publishEndpoint.Publish(new OrderPlaced(orderId)); // buffered in outbox table
await _db.SaveChangesAsync(); // commits row + outbox entry atomically
```

**Idempotent consumer - dedupe by message id.**

```csharp
public async Task Consume(ConsumeContext<OrderPlaced> ctx)
{
    if (await _processed.ExistsAsync(ctx.MessageId!.Value)) return;
    await _inventory.DecrementAsync(ctx.Message.OrderId, ctx.CancellationToken);
    await _processed.RecordAsync(ctx.MessageId.Value);
}
```

**Retry + DLQ - bounded exponential, then dead-letter.**

```csharp
cfg.UseMessageRetry(r => r.Exponential(5, TimeSpan.FromSeconds(1), TimeSpan.FromMinutes(5), TimeSpan.FromSeconds(1)));
cfg.UseInMemoryOutbox(); // per-consumer transactional buffer
// Failures after retries land in <queue>_error automatically
```

**Hangfire delayed job - identifiers only, no entities.**

Bad:

```csharp
BackgroundJob.Schedule(() => _email.SendReminderAsync(orderEntity, token), TimeSpan.FromHours(24));
```

Good - resolve dependencies and entity inside the job:

```csharp
BackgroundJob.Schedule<IPaymentReminderJob>(j => j.RunAsync(orderId), TimeSpan.FromHours(24));
// Job loads order, checks state, exits silently if already paid (idempotent)
```

**Testing.** Use `x.UsingInMemory()` in integration tests to exercise consumer logic without a real broker.

## Output Format

When applying this skill, emit:

- **Reliability gaps**: list of missing guarantees (outbox, idempotency, retry, DLQ)
- **Changes**: file + concrete edit per gap (registration, consumer, job signature)
- **Verification**: what to assert in tests (outbox row persisted, duplicate id ignored, DLQ receives after N retries)

## Avoid

- Publishing in the domain layer instead of via outbox + domain events
- `Task.Run` / fire-and-forget for work that must survive process restart
- Long synchronous work inside a consumer (offload to Hangfire job)
- Mixing `AddConsumer<T>()` and `AddConsumers(assembly)` - consumers run twice
- Injecting singletons with mutable state into consumers (scope is per-message)
