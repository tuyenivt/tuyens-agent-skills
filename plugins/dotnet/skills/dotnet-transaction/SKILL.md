---
name: dotnet-transaction
description: "EF Core transactional boundaries: single SaveChanges, IDbContextTransaction for cross-aggregate writes, Unit of Work, retry-safe execution."
metadata:
  category: backend
  tags: [ef-core, transactions, unit-of-work, consistency]
user-invocable: false
---

## When to Use

Defining transactional boundaries in service / command handlers, coordinating multiple aggregate writes, or writing domain rows together with an outbox row.

## Rules

- One `SaveChangesAsync` per use-case; never partial saves.
- Wrap multi-step writes in `IDbContextTransaction` only when more than one `SaveChangesAsync` is unavoidable, raw SQL runs alongside EF writes, or a non-default isolation level is required.
- Fetch read-only data outside the transaction; keep the transaction body to writes + commit.
- One `DbContext` per logical operation; never share across concurrent awaits.
- With `EnableRetryOnFailure`, every explicit `BeginTransactionAsync` must run inside `CreateExecutionStrategy().ExecuteAsync(...)`.
- In Clean Architecture, the Application layer depends on `IUnitOfWork`; `DbContext` implements it in Infrastructure.
- Do not write manual retry loops around `SaveChangesAsync` - the provider strategy handles transient faults.

## Patterns

### Single SaveChanges is the default

If all writes flow through one `DbContext`, a single `SaveChangesAsync` is already atomic - no explicit transaction needed. This includes the outbox pattern: domain rows and the `OutboxMessage` row commit together.

```csharp
_context.Orders.Add(order);
_context.Outbox.Add(OutboxMessage.For(new OrderPlaced(order.Id)));
await _uow.SaveChangesAsync(ct);   // atomic: order + outbox row
```

### Explicit transaction under retry

With `EnableRetryOnFailure`, calling `BeginTransactionAsync` outside an execution strategy throws. `await using` handles rollback on exception; no manual `catch` needed.

```csharp
var strategy = _context.Database.CreateExecutionStrategy();
await strategy.ExecuteAsync(async () =>
{
    await using var tx = await _context.Database
        .BeginTransactionAsync(IsolationLevel.RepeatableRead, ct);
    _context.Orders.Add(order);
    _context.Invoices.Add(invoice);
    await _uow.SaveChangesAsync(ct);
    await tx.CommitAsync(ct);
});
```

### IUnitOfWork in Clean Architecture

```csharp
public interface IUnitOfWork { Task<int> SaveChangesAsync(CancellationToken ct = default); }
public sealed class AppDbContext : DbContext, IUnitOfWork { /* ... */ }
```

Handlers depend on `IUnitOfWork` (and repositories), never `DbContext` directly.

### EnableRetryOnFailure setup

```csharp
options.UseNpgsql(cs, npgsql => npgsql.EnableRetryOnFailure(
    maxRetryCount: 3, maxRetryDelay: TimeSpan.FromSeconds(5)));
```

### Isolation levels

Default is `ReadCommitted`. Escalate only with cause:

| Level                   | Use when                                                       |
| ----------------------- | -------------------------------------------------------------- |
| `ReadCommitted`         | Default; standard CRUD                                         |
| `RepeatableRead`        | Read-then-write where the read value must not change mid-tx    |
| `Serializable`          | Strict sequential ordering (financial postings, balance debit) |
| `Snapshot` (SQL Server) | Long reads that must neither block nor be blocked              |

## Output Format

When recommending a transactional boundary, state:

- **Boundary**: `{Single SaveChanges | Explicit transaction | Saga/outbox}`
- **Isolation**: `{ReadCommitted | RepeatableRead | Serializable | Snapshot}`
- **Retry wrapping**: `{Not required | CreateExecutionStrategy required}`
- **Rationale**: one line tying the choice to the use-case (concurrency risk, multi-aggregate, raw SQL, etc.)

## Avoid

- Multiple `SaveChangesAsync` in one handler when a single call suffices.
- Long-running transactions (network calls, user input, external HTTP inside the tx).
- `TransactionScope` in async code without `TransactionScopeAsyncFlowOption.Enabled` (lost after first `await`).
- `TransactionScope` spanning multiple databases - escalates to MSDTC, unsupported on Linux/cloud; use saga/outbox.
- `Serializable` where `RepeatableRead` or row-level locking (`SELECT ... FOR UPDATE` via raw SQL) would do.
- Read-only queries inside `RepeatableRead` / `Serializable` transactions - move them outside or use `AsNoTracking()` with `ReadCommitted`.
