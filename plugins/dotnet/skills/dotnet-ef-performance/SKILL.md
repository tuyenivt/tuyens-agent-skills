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

## Compiled Queries

For hot-path queries executed frequently, compiled queries skip expression tree translation on every call:

```csharp
private static readonly Func<AppDbContext, Guid, CancellationToken, Task<Order?>> GetOrderById =
    EF.CompileAsyncQuery((AppDbContext ctx, Guid id, CancellationToken ct) =>
        ctx.Orders.AsNoTracking().FirstOrDefault(o => o.Id == id));

// Usage
var order = await GetOrderById(_context, orderId, ct);
```

## Pagination

Use keyset pagination for large datasets - `Skip(N)` scans and discards N rows on every page:

```csharp
// Offset pagination (simple but slow for deep pages)
var page = await _context.Products
    .AsNoTracking()
    .OrderBy(p => p.Name)
    .Skip((pageNumber - 1) * pageSize)
    .Take(pageSize)
    .ToListAsync(ct);

// Keyset pagination (consistent performance regardless of page depth)
var page = await _context.Products
    .AsNoTracking()
    .Where(p => p.Name.CompareTo(lastSeenName) > 0)
    .OrderBy(p => p.Name)
    .Take(pageSize)
    .ToListAsync(ct);
```

## Bulk Operations

`ExecuteUpdateAsync` and `ExecuteDeleteAsync` (EF Core 7+) run directly as SQL - no entity loading, no change tracking:

```csharp
// Deactivate all products in a category - single SQL UPDATE
await _context.Products
    .Where(p => p.CategoryId == categoryId)
    .ExecuteUpdateAsync(s => s.SetProperty(p => p.IsActive, false), ct);

// Purge soft-deleted records older than 90 days - single SQL DELETE
await _context.Products
    .Where(p => !p.IsActive && p.DeletedAt < DateTime.UtcNow.AddDays(-90))
    .ExecuteDeleteAsync(ct);
```

## Global Query Filters

Apply cross-cutting filters (soft delete, multi-tenancy) once in configuration rather than scattering `.Where()` clauses:

```csharp
// In IEntityTypeConfiguration<Product>
builder.HasQueryFilter(p => !p.IsDeleted);

// All queries automatically exclude deleted records
var active = await _context.Products.ToListAsync(ct);

// Bypass when needed (e.g., admin view)
var all = await _context.Products.IgnoreQueryFilters().ToListAsync(ct);
```

## Avoid

- `Include()` chains without `AsNoTracking()` on read paths
- Loading entire entity graphs when only a few columns are needed
- Lazy loading (disabled by default - keep it disabled)
- Calling `SaveChangesAsync()` inside a loop
- `Skip/Take` pagination on tables with millions of rows - use keyset pagination
- Loading entities just to delete or update them - use `ExecuteUpdateAsync`/`ExecuteDeleteAsync`
