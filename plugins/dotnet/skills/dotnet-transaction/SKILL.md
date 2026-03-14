---
name: dotnet-transaction
description: Transaction scope, SaveChanges boundaries, and Unit of Work patterns for EF Core
metadata:
  category: backend
  tags: [ef-core, transactions, unit-of-work, consistency]
user-invocable: false
---

# Transaction Management

## When to Use

- Defining transactional boundaries in service methods
- Coordinating multiple aggregate writes in a single transaction
- Handling distributed operations with outbox or saga patterns

## Rules

- One `SaveChangesAsync()` per use-case - avoid partial saves
- Wrap multi-step writes in `IDbContextTransaction` only when needed
- Keep transactions short: fetch data outside the transaction, write inside
- Never share a single `DbContext` across parallel async operations
- Use `IUnitOfWork` abstraction in Clean Architecture to decouple services from EF Core
- Register `DbContext` with `AddDbContext` (scoped lifetime) - never singleton

## Pattern

Single save per use-case:

```csharp
public async Task<OrderId> PlaceOrderAsync(PlaceOrderCommand command, CancellationToken ct)
{
    var customer = await _customerRepository.GetByIdAsync(command.CustomerId, ct);
    var order = customer.PlaceOrder(command.Items);     // domain logic
    _context.Orders.Add(order);
    await _context.SaveChangesAsync(ct);               // single flush
    return order.Id;
}
```

Explicit transaction for cross-aggregate writes:

```csharp
await using var tx = await _context.Database.BeginTransactionAsync(ct);
try
{
    _context.Orders.Add(order);
    _context.Invoices.Add(invoice);
    await _context.SaveChangesAsync(ct);
    await tx.CommitAsync(ct);
}
catch
{
    await tx.RollbackAsync(ct);
    throw;
}
```

IUnitOfWork abstraction (Clean Architecture):

```csharp
// Application layer interface
public interface IUnitOfWork
{
    Task<int> SaveChangesAsync(CancellationToken ct = default);
}

// Infrastructure implementation - DbContext already is a UoW
public sealed class AppDbContext : DbContext, IUnitOfWork { }

// Handler uses the interface, not DbContext directly
public sealed class PlaceOrderHandler(IOrderRepository orders, IUnitOfWork uow)
{
    public async Task<OrderId> Handle(PlaceOrderCommand cmd, CancellationToken ct)
    {
        var order = Order.Create(cmd.CustomerId, cmd.Items);
        await orders.AddAsync(order, ct);
        await uow.SaveChangesAsync(ct);
        return order.Id;
    }
}
```

## Transient Fault Retry

Enable automatic retry for transient database errors (connection drops, deadlocks). EF Core handles this at the provider level - do not write manual retry loops:

```csharp
builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseNpgsql(connectionString, npgsql =>
        npgsql.EnableRetryOnFailure(
            maxRetryCount: 3,
            maxRetryDelay: TimeSpan.FromSeconds(5),
            errorCodesToAdd: null)));
```

When using `EnableRetryOnFailure` with explicit transactions, wrap the entire operation in an execution strategy:

```csharp
var strategy = _context.Database.CreateExecutionStrategy();
await strategy.ExecuteAsync(async () =>
{
    await using var tx = await _context.Database.BeginTransactionAsync(ct);
    _context.Orders.Add(order);
    _context.Invoices.Add(invoice);
    await _context.SaveChangesAsync(ct);
    await tx.CommitAsync(ct);
});
```

## Isolation Levels

Default (`ReadCommitted`) is correct for most use cases. Only escalate when needed:

| Isolation Level         | Use When                                                  |
| ----------------------- | --------------------------------------------------------- |
| `ReadCommitted`         | Default. Standard CRUD, most business operations          |
| `RepeatableRead`        | Read-then-write where the read value must not change      |
| `Serializable`          | Financial operations requiring strict sequential ordering |
| `Snapshot` (SQL Server) | Long-running reads that must not block or be blocked      |

```csharp
await using var tx = await _context.Database
    .BeginTransactionAsync(IsolationLevel.RepeatableRead, ct);
```

## Avoid

- Multiple `SaveChangesAsync()` calls within one request handler (partial saves on failure)
- Long-running transactions holding database locks
- `DbContext` reuse across threads
- Business logic inside the `catch` block of a transaction
- Manual retry loops around `SaveChangesAsync` - use `EnableRetryOnFailure` instead
- `Serializable` isolation when `RepeatableRead` suffices (unnecessary lock contention)
