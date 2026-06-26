---
name: dotnet-ef-performance
description: "EF Core perf: N+1, projection, AsNoTracking, AsSplitQuery, compiled queries, keyset pagination, ExecuteUpdate/Delete, Dapper."
metadata:
  category: backend
  tags: [ef-core, dapper, performance, queries, n+1]
user-invocable: false
---

# EF Core Performance

## When to Use

- Diagnosing slow EF Core queries or high allocation in the data layer
- Removing N+1, cartesian explosion, or deep-page `Skip` scans
- Choosing between EF Core projection, compiled query, and Dapper

## Rules

- Reads: `AsNoTracking()` + `Select()` to a DTO. The projection drives the join; do not add `Include()`.
- `Include()` is only for tracked writes or when the whole navigation is returned. Multiple collection `Include()`s require `AsSplitQuery()`.
- Bulk mutate via `ExecuteUpdateAsync` / `ExecuteDeleteAsync`. Never loop `SaveChangesAsync`.
- Paginate large/unbounded sets by keyset (`WHERE key > @last`), not `Skip/Take`.
- `EF.CompileAsyncQuery` only for hot single-entity lookups (no `Include`, no `AsSplitQuery`).
- Drop to Dapper for SQL EF translates poorly (window functions, recursive CTEs). Share the open EF transaction: pass both `_context.Database.GetDbConnection()` and `CurrentTransaction?.GetDbTransaction()` to the Dapper call.

## Patterns

**N+1 via lazy/implicit navigation - project instead of Include.**

```csharp
// Bad: N queries for Customer.Name
var orders = await _context.Orders.ToListAsync();
foreach (var o in orders) log(o.Customer.Name);

// Good: one SQL, no tracking, no Include
var orders = await _context.Orders.AsNoTracking()
    .Select(o => new OrderDto(o.Id, o.Customer.Name, o.Total))
    .ToListAsync(ct);
```

**Cartesian explosion from multiple collection Includes.**

```csharp
// Bad: Orders x Items x Tags rows multiplied
ctx.Orders.Include(o => o.Items).Include(o => o.Tags).ToListAsync();

// Good: split into separate SQL statements
ctx.Orders.AsSplitQuery().Include(o => o.Items).Include(o => o.Tags).ToListAsync();
```

**Bulk mutation - no entity load, no tracking.**

```csharp
// Bad: load + per-row SaveChanges
foreach (var p in await ctx.Products.Where(p => p.CategoryId == id).ToListAsync())
    { p.IsActive = false; await ctx.SaveChangesAsync(); }

// Good: single SQL UPDATE
await ctx.Products.Where(p => p.CategoryId == id)
    .ExecuteUpdateAsync(s => s.SetProperty(p => p.IsActive, false), ct);
```

**Keyset pagination - constant cost regardless of depth.**

```csharp
// Bad: Skip scans and discards N rows
ctx.Products.OrderBy(p => p.Id).Skip((page - 1) * size).Take(size);

// Good: filter by last seen key
ctx.Products.Where(p => p.Id > lastId).OrderBy(p => p.Id).Take(size);

// Non-unique sort column needs a tie-broken composite cursor (index on (Name, Id))
ctx.Products
    .Where(p => p.Name.CompareTo(lastName) > 0 || (p.Name == lastName && p.Id > lastId))
    .OrderBy(p => p.Name).ThenBy(p => p.Id).Take(size);
```

**Compiled query for hot-path single-entity lookup.**

```csharp
private static readonly Func<AppDbContext, Guid, CancellationToken, Task<Order?>> GetById =
    EF.CompileAsyncQuery((AppDbContext c, Guid id, CancellationToken ct) =>
        c.Orders.AsNoTracking().FirstOrDefault(o => o.Id == id));
```

## Output Format

```
Finding: <one-line problem>
Location: <file:line or query name>
Cause: {N+1 | Cartesian | Tracking overhead | Deep Skip | Loop SaveChanges | Over-fetch | Untranslatable SQL | Other}
Fix: <pattern name from this skill> - <one-line change>
Impact: {Latency | Memory | DB load} - <rough magnitude if measurable>
```

## Avoid

- `Include()` on a projected (`Select`) read path - projection already drives the join.
- Compiled queries that reference `Include`, `AsSplitQuery`, or context-bound filters - unsupported.
- Mixing keyset and offset pagination on the same endpoint - the cursor contract breaks.
- Calling Dapper on a separate `DbConnection` when a transaction is already open on the `DbContext`.
