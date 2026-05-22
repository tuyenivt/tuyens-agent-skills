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

- Typed return types on relationship methods; foreign key constraints in migrations
- `$fillable` whitelist - never `$guarded = []`
- Backed enums for status/type columns; never bare strings
- Eager load relationships accessed in loops; `preventLazyLoading()` in non-prod
- Never `::all()` on growable tables
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
```

### Eager loading and N+1 prevention

```php
// Bad - N+1
foreach (Order::all() as $o) echo $o->items->count();

// Good
foreach (Order::with('items')->get() as $o) echo $o->items->count();

// Variants
Order::with('items.product')->get();                                    // nested
Order::with(['items' => fn($q) => $q->where('qty', '>', 1)])->get();   // constrained
Order::withCount('items')->get();                                       // $o->items_count
Order::withSum('items', 'qty')->get();                                  // aggregate without loading

// AppServiceProvider::boot()
Model::preventLazyLoading(! app()->isProduction());
Model::preventSilentlyDiscardingAttributes(! app()->isProduction());
```

### Scopes

```php
// Local scope - reusable, chainable
public function scopeActive(Builder $q): Builder {
    return $q->where('status', OrderStatus::Active)->whereNull('cancelled_at');
}

Order::active()->createdBetween($from, $to)->get();

// Global scope - only for universal concerns (e.g., multi-tenant)
class TenantScope implements Scope {
    public function apply(Builder $b, Model $m): void {
        $b->where('tenant_id', auth()->user()->tenant_id);
    }
}
Order::withoutGlobalScope(TenantScope::class)->get(); // bypass when needed
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
    ];
}

// Custom accessor/mutator (Laravel 9+)
protected function fullName(): Attribute {
    return Attribute::make(
        get: fn($v, array $attrs) => $attrs['first_name'].' '.$attrs['last_name'],
        set: fn(string $v) => [
            'first_name' => str($v)->before(' ')->toString(),
            'last_name' => str($v)->after(' ')->toString(),
        ],
    );
}
```

### Large datasets

| Method        | Memory | Eager Load | Update-Safe |
| ------------- | ------ | ---------- | ----------- |
| `all()`       | High   | Yes        | N/A         |
| `chunk()`     | Medium | Yes        | No          |
| `chunkById()` | Medium | Yes        | Yes         |
| `lazy()`      | Low    | Yes        | No          |
| `cursor()`    | Lowest | No         | No          |

```php
Order::chunkById(1000, function (Collection $orders) { /* safe for updates */ });
Order::lazy()->each(fn(Order $o) => /* one row at a time */);
foreach (Order::cursor() as $o) { /* lowest memory, no eager load */ }
```

### Soft deletes and pruning

```php
class Order extends Model {
    use SoftDeletes, Prunable;

    public function prunable(): Builder {
        return static::where('created_at', '<=', now()->subYear());
    }
}

Order::withTrashed()->get();    // include soft-deleted
Order::onlyTrashed()->get();    // only soft-deleted
$order->restore();
$order->forceDelete();
// Schedule: php artisan model:prune
```

### MySQL-specific

```php
// JSON columns
$table->json('metadata')->nullable();
Order::where('metadata->shipping_method', 'express')->get();
Order::whereJsonContains('metadata->tags', 'urgent')->get();
$order->update(['metadata->tracking_id' => 'ABC123']);

// Fulltext
$table->fullText(['title', 'description']);
Order::whereFullText(['title', 'description'], 'search term')->get();

// EXPLAIN (dev)
Order::where(...)->explain()->dd();
```

### Locking and concurrency

```php
// Read-check-write needs pessimistic lock
DB::transaction(function () use ($productId, $qty) {
    $p = Product::lockForUpdate()->findOrFail($productId);
    if ($p->stock < $qty) throw new InsufficientStockException(...);
    $p->decrement('stock', $qty);
});

// Atomic update (no lock needed for simple inc/dec)
$affected = Product::where('id', $id)
    ->where('stock', '>=', $qty)  // guard in WHERE
    ->decrement('stock', $qty);
if ($affected === 0) throw new InsufficientStockException(...);
```

| Scenario                     | Strategy                            |
| ---------------------------- | ----------------------------------- |
| Simple inc/dec               | Atomic WHERE+UPDATE (no lock)       |
| Read-check-write (inventory) | `lockForUpdate()` in transaction    |
| High-contention hot rows     | Atomic update or queue serialization |
| Optimistic concurrency       | Version column check on update     |

### Aggregates

```php
// Bad - loads full collection
$count = $product->reviews->count();

// Good - database aggregate
Product::withCount('reviews')->withAvg('reviews', 'rating')->paginate();
// $product->reviews_count, $product->reviews_avg_rating

// Filtered
Product::withCount(['reviews' => fn($q) => $q->where('rating', '>=', 4)])->get();
```

### Pagination

| Method             | SQL            | Use When                        |
| ------------------ | -------------- | ------------------------------- |
| `paginate()`       | `LIMIT/OFFSET` | Small-medium, need total count  |
| `simplePaginate()` | `LIMIT/OFFSET` | Medium, no total needed         |
| `cursorPaginate()` | `WHERE id > ?` | Large tables, API endpoints     |

```php
Order::with('items')->orderBy('id')->cursorPaginate($request->integer('per_page', 25));
```

## Output Format

```
## Model Design
| Model | Table | Relationships | Scopes | Casts |

## Query Optimization
| Endpoint | Eager Loading | Aggregates | Pagination Method |

## Indexes Needed
| Table | Columns | Type | Reason |
```

## Avoid

- `$guarded = []` (mass assignment vulnerability)
- Lazy loading in loops; `Model::all()` on growable tables
- Business logic in accessors/mutators (keep models thin)
- `whereRaw` / `DB::raw` with interpolated user input
- Global scopes for non-universal concerns (forgotten exclusions, debug pain)
- Missing FK constraints; string status columns without backed enums
- `cursor()` when you need eager loading
- Decrement without `WHERE` guard or lock (race / negative stock)
- `lockForUpdate()` outside `DB::transaction()` (lock immediately released)
