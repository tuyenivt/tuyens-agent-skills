---
name: laravel-eloquent-patterns
description: "Eloquent ORM patterns: relationships, scopes, eager loading, N+1 prevention, casts, chunking, soft deletes, MySQL query optimization."
metadata:
  category: backend
  tags: [php, laravel, eloquent, mysql, orm, relationships, n-plus-one]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing Eloquent models, relationships, scopes, casts
- Preventing N+1, working with large datasets, MySQL-specific features
- NOT for: migration DDL (use `laravel-migration-safety`), API response shaping (use `laravel-api-patterns`)

## Rules

- Typed return types on relationship methods; FK constraints in migrations
- `$fillable` whitelist - never `$guarded = []`
- Backed enums for status/type columns; never bare strings
- Eager load any relation accessed in a loop or Resource; column-select where the relation has many columns (`with('user:id,email')`)
- `Model::shouldBeStrict(! app()->isProduction())` in `AppServiceProvider::boot()` - bundles `preventLazyLoading` + `preventSilentlyDiscardingAttributes` + `preventAccessingMissingAttributes`
- Never `::all()` on growable tables; use `chunkById` / `lazy` / `cursor` / pagination
- `whereRaw` / `DB::raw` use parameter bindings, never string interpolation
- `lockForUpdate()` only inside `DB::transaction()` (otherwise lock releases immediately)

## Patterns

### Relationships

```php
// Typed return + FK in migration
public function items(): HasMany {
    return $this->hasMany(OrderItem::class);
}

Schema::create('order_items', function (Blueprint $t) {
    $t->foreignId('order_id')->constrained()->cascadeOnDelete();
});

// Pivot with data
public function roles(): BelongsToMany {
    return $this->belongsToMany(Role::class)
        ->withPivot('assigned_at', 'assigned_by')
        ->withTimestamps();
}

// hasManyThrough for jump-table reads (Order -> Product via OrderItem)
public function products(): HasManyThrough {
    return $this->hasManyThrough(Product::class, OrderItem::class);
}
```

### Eager loading and N+1 prevention

```php
// Bad - N+1
foreach (Order::all() as $o) echo $o->items->count();

// Good - eager + column select + DB aggregates
Order::with(['user:id,email', 'items:id,order_id,qty', 'items.product:id,name'])
    ->withCount('items')
    ->withSum('items', 'qty')      // $o->items_sum_qty without loading items
    ->cursorPaginate(25);

// Constrained eager load
Order::with(['items' => fn($q) => $q->where('qty', '>', 1)])->get();

// Already-fetched models
$orders->loadMissing('items');
```

### Scopes

```php
public function scopeActive(Builder $q): Builder {
    return $q->where('status', OrderStatus::Active)->whereNull('cancelled_at');
}
Order::active()->createdBetween($from, $to)->get();

// Global scope - only for universal concerns (tenancy). Bypass with withoutGlobalScope.
class TenantScope implements Scope {
    public function apply(Builder $b, Model $m): void {
        $b->where('tenant_id', auth()->user()->tenant_id);
    }
}
```

### Casts and accessors

```php
protected function casts(): array {
    return [
        'total' => 'decimal:2',
        'status' => OrderStatus::class,    // backed enum
        'metadata' => 'array',             // JSON column
        'shipped_at' => 'immutable_datetime',
        'is_gift' => 'boolean',
        'card_number' => 'encrypted',      // AES-256 via APP_KEY
    ];
}
```

Custom accessors via `Attribute::make(get: ..., set: ...)` (Laravel 9+); keep them thin - business logic belongs in services.

### Large datasets

| Method        | Memory | Eager Load | Update-Safe | Use When                           |
| ------------- | ------ | ---------- | ----------- | ---------------------------------- |
| `chunkById()` | Medium | Yes        | Yes         | Batch updates by stable PK         |
| `lazy()`      | Low    | Yes        | No          | Stream read with eager relations   |
| `cursor()`    | Lowest | No         | No          | Stream read, no relations needed   |

`::all()` excluded - forbidden on growable tables.

### Soft deletes

`use SoftDeletes` adds a `deleted_at` global scope. `withTrashed()` / `onlyTrashed()` to bypass; `restore()` / `forceDelete()` for lifecycle. Pair with `Prunable` + `php artisan model:prune` for retention. Index `deleted_at` (or composite) on hot tables.

### MySQL-specific

```php
// JSON column query / update
Order::where('metadata->shipping_method', 'express')->get();
Order::whereJsonContains('metadata->tags', 'urgent')->get();
$order->update(['metadata->tracking_id' => 'ABC123']);

// Fulltext (replaces LIKE '%term%')
$table->fullText(['title', 'description']);
Order::whereFullText(['title', 'description'], 'search term')->get();

// EXPLAIN in dev
Order::where(...)->explain()->dd();
```

### Locking and concurrency

```php
// Read-check-write requires pessimistic lock inside transaction
DB::transaction(function () use ($productId, $qty) {
    $p = Product::lockForUpdate()->findOrFail($productId);
    if ($p->stock < $qty) throw new InsufficientStockException(...);
    $p->decrement('stock', $qty);
});

// Atomic update - no lock needed
$affected = Product::where('id', $id)
    ->where('stock', '>=', $qty)
    ->decrement('stock', $qty);
if ($affected === 0) throw new InsufficientStockException(...);
```

| Scenario                     | Strategy                                              |
| ---------------------------- | ----------------------------------------------------- |
| Simple inc/dec               | Atomic `WHERE` + `UPDATE` (no lock)                   |
| Read-check-write (inventory) | `lockForUpdate()` in transaction                      |
| High-contention hot rows     | Atomic update or queue serialization                  |
| Optimistic concurrency       | `where('version', $v)->update(['version' => $v + 1])` |

### Pagination

| Method             | SQL            | Use When                        |
| ------------------ | -------------- | ------------------------------- |
| `paginate()`       | `LIMIT/OFFSET` | Small-medium, total count needed |
| `simplePaginate()` | `LIMIT/OFFSET` | Medium, no total                |
| `cursorPaginate()` | `WHERE id > ?` | Large tables, API endpoints     |

### Index design (consumed by Output Format)

- Every column in `WHERE`, `ORDER BY`, `GROUP BY` is indexed; leftmost-prefix for composites
- Cursor pagination: index on the cursor column (usually `id` or `(created_at, id)`)
- Soft-deleted hot tables: include `deleted_at` in composite
- FK columns get an index automatically via `->constrained()`

## Output Format

For **design** prompts:

```
## Model Design
| Model | Table | Relationships | Scopes | Casts |

## Query Optimization
| Endpoint | Eager Loading | Aggregates | Pagination Method |

## Indexes Needed
| Table | Columns | Type | Reason |
```

For **audit** prompts:

```
## Findings
| Location | Issue | Query Count Before -> After | Fix |
```

## Avoid

- `$guarded = []`; `Model::all()` on growable tables; lazy loading in loops
- Business logic in accessors/mutators (keep models thin)
- `whereRaw` / `DB::raw` with interpolated user input
- Global scopes for non-universal concerns (forgotten exclusions, debug pain)
- String status columns without backed enums; missing FK constraints
- `cursor()` when you need eager loading (use `lazy()`)
- Decrement without `WHERE` guard or lock (race / negative stock)
