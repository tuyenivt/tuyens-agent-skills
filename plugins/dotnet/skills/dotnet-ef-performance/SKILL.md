---
name: dotnet-ef-performance
description: EF Core query optimization, N+1 prevention, and Dapper for read-heavy queries
metadata:
  category: backend
  tags: [ef-core, dapper, performance, queries, n+1]
user-invocable: false
---

# EF Core Performance

## When to Use

- Optimizing data access layer queries
- Preventing N+1 query problems in EF Core
- Selecting between EF Core and Dapper for a given query
- Reducing memory footprint of large result sets

## Rules

- Default to `AsNoTracking()` for all read-only queries
- Never call `Include()` without a concrete loading requirement
- Use projections (`Select()`) instead of full entity loads for read-only views
- Prefer Dapper for complex reporting queries or bulk reads
- Detect and eliminate N+1: never lazy-load inside a loop
- Add indexes on `WHERE`/`ORDER BY`/`JOIN` columns (see core plugin's `db-indexing`)
- Use `AsSplitQuery()` for multi-collection includes to avoid cartesian explosion
- Batch writes with `ExecuteUpdateAsync` / `ExecuteDeleteAsync` (EF Core 7+) for bulk mutations

## Pattern

Bad - causes N+1 queries:

```csharp
var orders = await _context.Orders.ToListAsync();
foreach (var order in orders)
{
    Console.WriteLine(order.Customer.Name); // N additional queries
}
```

Good - explicit include prevents N+1:

```csharp
var orders = await _context.Orders
    .AsNoTracking()
    .Include(o => o.Customer)
    .Select(o => new OrderSummaryDto(o.Id, o.Customer.Name, o.TotalAmount))
    .ToListAsync(cancellationToken);
```

Good - Dapper for complex read:

```csharp
var sql = "SELECT o.Id, c.Name FROM Orders o JOIN Customers c ON c.Id = o.CustomerId WHERE o.Status = @Status";
var results = await _connection.QueryAsync<OrderSummaryDto>(sql, new { Status = status });
```

## Avoid

- `Include()` chains without `AsNoTracking()` on read paths
- Loading entire entity graphs when only a few columns are needed
- Lazy loading (disabled by default - keep it disabled)
- Calling `SaveChangesAsync()` inside a loop
