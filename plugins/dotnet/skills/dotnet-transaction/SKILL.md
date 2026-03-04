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

## Avoid

- Multiple `SaveChangesAsync()` calls within one request handler (partial saves on failure)
- Long-running transactions holding database locks
- `DbContext` reuse across threads
- Business logic inside the `catch` block of a transaction
