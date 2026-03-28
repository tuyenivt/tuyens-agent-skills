---
name: laravel-eloquent-patterns
description: "Eloquent ORM patterns for Laravel - relationships, scopes, eager loading, N+1 prevention, casts, attribute accessors, chunking, soft deletes, and MySQL-specific query optimization."
metadata:
  category: backend
  tags: [php, laravel, eloquent, mysql, orm, relationships, n-plus-one]
user-invocable: false
---

## 1. RELATIONSHIPS

Define all relationships explicitly with return types. Use foreign key constraints in migrations.

```php
// Bad - no return type, no foreign key in migration
public function items() {
    return $this->hasMany(OrderItem::class);
}

// Good - typed return, constrained in migration
public function items(): HasMany
{
    return $this->hasMany(OrderItem::class);
}

// Migration
Schema::create('order_items', function (Blueprint $table) {
    $table->foreignId('order_id')->constrained()->cascadeOnDelete();
});
```

### Relationship Types

| Relationship      | Method              | Use When                    |
| ----------------- | ------------------- | --------------------------- |
| One-to-Many       | `hasMany`           | Order -> Items              |
| Belongs To        | `belongsTo`         | Item -> Order               |
| Many-to-Many      | `belongsToMany`     | User <-> Role (pivot table) |
| Has One Through   | `hasOneThrough`     | Country -> User -> Phone    |
| Has Many Through  | `hasManyThrough`    | Country -> User -> Order    |
| Polymorphic       | `morphTo/morphMany` | Comment on Post or Video    |
| Many-to-Many Poly | `morphToMany`       | Tag on Post, Video, etc.    |

### Pivot Tables

```php
// With pivot data
public function roles(): BelongsToMany
{
    return $this->belongsToMany(Role::class)
        ->withPivot('assigned_at', 'assigned_by')
        ->withTimestamps();
}

// Pivot model for complex pivot logic
public function roles(): BelongsToMany
{
    return $this->belongsToMany(Role::class)
        ->using(RoleUser::class)
        ->withPivot('assigned_at');
}
```

## 2. EAGER LOADING AND N+1 PREVENTION

Always eager load relationships accessed in loops. Use `preventLazyLoading()` in development to catch violations.

```php
// Bad - N+1: 1 query for orders + N queries for items
$orders = Order::all();
foreach ($orders as $order) {
    echo $order->items->count(); // lazy load per iteration
}

// Good - 2 queries total: orders + items
$orders = Order::with('items')->get();
foreach ($orders as $order) {
    echo $order->items->count(); // already loaded
}
```

### Eager Loading Variants

```php
// Nested eager loading
Order::with('items.product')->get();

// Eager load with constraints
Order::with(['items' => fn($q) => $q->where('quantity', '>', 1)])->get();

// Lazy eager loading (when you already have the collection)
$orders = Order::all();
$orders->load('items');

// Load missing (skip already loaded)
$order->loadMissing('items');

// Count without loading
Order::withCount('items')->get(); // $order->items_count

// Aggregate without loading
Order::withSum('items', 'quantity')->get(); // $order->items_sum_quantity
```

### Development Guard

```php
// AppServiceProvider::boot()
Model::preventLazyLoading(! app()->isProduction());
Model::preventSilentlyDiscardingAttributes(! app()->isProduction());
```

## 3. QUERY SCOPES

Use local scopes for reusable query constraints. Avoid global scopes unless truly universal.

```php
// Local scope
public function scopeActive(Builder $query): Builder
{
    return $query->where('status', OrderStatus::Active);
}

public function scopeCreatedBetween(Builder $query, Carbon $from, Carbon $to): Builder
{
    return $query->whereBetween('created_at', [$from, $to]);
}

// Usage - scopes are chainable
Order::active()->createdBetween($start, $end)->get();
```

```php
// Global scope (use sparingly - applied to ALL queries)
// Good use case: multi-tenant filtering
class TenantScope implements Scope
{
    public function apply(Builder $builder, Model $model): void
    {
        $builder->where('tenant_id', auth()->user()->tenant_id);
    }
}

// Remove global scope when needed
Order::withoutGlobalScope(TenantScope::class)->get();
```

## 4. CASTS AND ATTRIBUTES

Use casts for automatic type conversion. Use `Attribute` class for custom accessors/mutators.

```php
// Casts
protected function casts(): array
{
    return [
        'total' => 'decimal:2',
        'status' => OrderStatus::class,    // Backed enum
        'metadata' => 'array',             // JSON column -> array
        'shipped_at' => 'immutable_datetime',
        'is_gift' => 'boolean',
    ];
}

// Attribute accessor/mutator (Laravel 9+)
protected function fullName(): Attribute
{
    return Attribute::make(
        get: fn(mixed $value, array $attributes) =>
            $attributes['first_name'] . ' ' . $attributes['last_name'],
        set: fn(string $value) => [
            'first_name' => str($value)->before(' ')->toString(),
            'last_name' => str($value)->after(' ')->toString(),
        ],
    );
}
```

### Backed Enums

```php
enum OrderStatus: string
{
    case Pending = 'pending';
    case Processing = 'processing';
    case Completed = 'completed';
    case Cancelled = 'cancelled';
}

// Usage in queries
Order::where('status', OrderStatus::Pending)->get();
```

## 5. LARGE DATASETS

Never load entire tables into memory. Use chunking, lazy collections, or cursor.

```php
// Bad - loads all rows into memory
$orders = Order::all();
foreach ($orders as $order) { /* process */ }

// Good - chunk by ID (memory-safe)
Order::chunk(1000, function (Collection $orders) {
    foreach ($orders as $order) { /* process */ }
});

// Good - lazy collection (one row at a time, memory-efficient)
Order::lazy()->each(function (Order $order) {
    // process
});

// Good - cursor (single row via PHP generator, lowest memory)
foreach (Order::cursor() as $order) {
    // process - but no eager loading available
}

// Good - chunk by ID for update safety
Order::chunkById(1000, function (Collection $orders) {
    // safe even if processing modifies the rows
});
```

| Method        | Memory     | Eager Loading | Update-Safe |
| ------------- | ---------- | ------------- | ----------- |
| `all()`       | High (all) | Yes           | N/A         |
| `chunk()`     | Medium     | Yes           | No          |
| `chunkById()` | Medium     | Yes           | Yes         |
| `lazy()`      | Low        | Yes           | No          |
| `cursor()`    | Lowest     | No            | No          |

## 6. SOFT DELETES AND PRUNING

```php
use Illuminate\Database\Eloquent\SoftDeletes;

class Order extends Model
{
    use SoftDeletes;
}

// Query includes only non-deleted
Order::all();

// Include soft-deleted
Order::withTrashed()->get();

// Only soft-deleted
Order::onlyTrashed()->get();

// Restore
$order->restore();

// Permanent delete
$order->forceDelete();
```

### Pruning Old Records

```php
use Illuminate\Database\Eloquent\Prunable;

class Order extends Model
{
    use Prunable;

    public function prunable(): Builder
    {
        return static::where('created_at', '<=', now()->subYear());
    }
}

// Schedule: php artisan model:prune
```

## 7. MYSQL-SPECIFIC PATTERNS

### JSON Columns

```php
// Migration
$table->json('metadata')->nullable();

// Query JSON
Order::where('metadata->shipping_method', 'express')->get();
Order::whereJsonContains('metadata->tags', 'urgent')->get();

// Update JSON
$order->update(['metadata->tracking_id' => 'ABC123']);
```

### Fulltext Index

```php
// Migration
$table->fullText(['title', 'description']);

// Query
Order::whereFullText(['title', 'description'], 'search term')->get();
```

### EXPLAIN Analysis

```php
// Development debugging
Order::where('status', 'pending')
    ->where('created_at', '>', now()->subDay())
    ->explain()
    ->dd();
```

## 8. ANTI-PATTERNS

- ❌ `$guarded = []` on models (mass assignment vulnerability)
- ❌ Lazy loading in loops (N+1 queries)
- ❌ `Order::all()` on large tables (memory exhaustion)
- ❌ Business logic in accessors/mutators (keep models as data layer)
- ❌ Raw SQL string interpolation (`DB::raw("WHERE id = $id")`) - use bindings
- ❌ `whereRaw()` with user input without parameter binding
- ❌ Global scopes for non-universal concerns (hard to debug, forgotten exclusions)
- ❌ Missing foreign key constraints in migrations (data integrity)
- ❌ String status columns without backed enums (typo-prone)
- ❌ `cursor()` when you need eager loading (N+1 trap)
