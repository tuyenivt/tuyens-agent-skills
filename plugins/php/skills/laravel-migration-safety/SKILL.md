---
name: laravel-migration-safety
description: "Zero-downtime Laravel/MySQL migrations: lock-safe DDL, nullable-first NOT NULL, InnoDB online DDL, expand-contract renames, multi-release sequencing."
metadata:
  category: backend
  tags: [php, laravel, mysql, migrations, zero-downtime, ddl]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Adding, modifying, removing columns; renames; drops; indexes; FKs on deployed MySQL
- Large-table backfills; reviewing migrations for zero-downtime safety
- NOT for: greenfield schema design, PostgreSQL DDL, query optimization (use `laravel-eloquent-patterns`)

## Rules

- Every migration ships a reversible `down()`
- One concern per migration file: schema OR data, never both
- Multi-step patterns deploy across multiple releases, never in one
- Test against real MySQL; SQLite hides behavior differences
- All backfills use `chunkById()`; never `WHERE col IS NULL LIMIT N` loops
- Review generated migrations before running; defaults are not always safe

## Patterns

### Strategy by table size

| Operation        | < 100K rows         | 100K-1M rows         | > 1M rows                          |
| ---------------- | ------------------- | -------------------- | ---------------------------------- |
| Add nullable col | Single migration    | Single migration     | Single migration (instant)         |
| Add NOT NULL col | Direct with default | 3-step pattern       | 3-step + pt-osc backfill           |
| Add index        | Standard Schema     | `ALGORITHM=INPLACE`  | `ALGORITHM=INPLACE, LOCK=NONE`     |
| Rename column    | Expand-contract     | Expand-contract      | Expand-contract + batched backfill |
| Drop column      | Single migration    | Single migration     | Remove code first, then drop       |

### Adding columns

Nullable adds are metadata-only in InnoDB (fast, lock-free). NOT NULL with a constant DEFAULT is instant on MySQL 8.0+ (`ALGORITHM=INSTANT`). Otherwise use the 3-step pattern.

```php
// Safe - nullable add
Schema::table('orders', fn (Blueprint $t) =>
    $t->string('tracking_number', 100)->nullable()->after('status')
);

// Safe on MySQL 8.0+ - constant default
$t->string('tracking_number', 100)->default('PENDING');

// Bad - direct NOT NULL on 5M rows locks the table
$t->string('phone');
```

3-step pattern when values must be computed per row:

```php
// Migration 1: nullable column
$t->string('tracking_number', 100)->nullable();

// Migration 2: backfill (separate file, separate release)
DB::table('orders')
    ->whereNull('tracking_number')
    ->chunkById(1000, function ($orders) {
        foreach ($orders as $o) {
            DB::table('orders')->where('id', $o->id)
                ->update(['tracking_number' => 'LEGACY-' . $o->id]);
        }
    });

// Migration 3: enforce NOT NULL (after backfill confirmed)
$t->string('tracking_number', 100)->nullable(false)->change();
```

### Indexes

InnoDB online DDL keeps reads/writes flowing during index creation. Use raw SQL to pin the algorithm on large tables.

```php
// Small table
$t->index('status');

// Large table - explicit online DDL
DB::statement('ALTER TABLE orders ADD INDEX idx_orders_status (status), ALGORITHM=INPLACE, LOCK=NONE');

// Composite
$t->index(['status', 'created_at']);
```

### Foreign keys

Add the column and backfill first; add the constraint last to avoid lock contention.

```php
// 1. Column only
$t->unsignedBigInteger('product_id')->nullable();

// 2. Backfill (separate migration)

// 3. Constraint (separate migration)
$t->foreign('product_id')->references('id')->on('products');
```

### Data migrations

Always `chunkById()` for update-safe iteration. Keep schema and data in separate files.

```php
public function up(): void
{
    DB::table('orders')
        ->where('status', 'legacy_pending')
        ->chunkById(1000, function ($orders) {
            DB::table('orders')
                ->whereIn('id', $orders->pluck('id'))
                ->update(['status' => 'pending']);
        });
}

public function down(): void
{
    DB::table('orders')->where('status', 'pending')
        ->update(['status' => 'legacy_pending']);
}
```

### Renames and drops (expand-contract)

Direct renames break running code mid-deploy. Stage across releases:

1. Add new column (nullable) - migration
2. Backfill from old column - data migration
3. App writes both, reads new - deploy
4. App stops writing old - deploy
5. Drop old column - migration in a later release

```php
// Step 1
$t->string('recipient_name')->nullable()->after('customer_name');

// Step 2 - backfill via chunkById (see Data migrations)

// Step 5 - later release, after code stops referencing customer_name
$t->dropColumn('customer_name');
```

Table drops follow the same shape: remove all code references first; drop in a later release.

### Large-table alterations

When `ALGORITHM=INPLACE` is insufficient (e.g., column type changes that force rebuild), use external tools:

- **pt-online-schema-change** (Percona): shadow copy + trigger-based sync + atomic swap
- **gh-ost** (GitHub): binlog-based, no triggers

```bash
pt-online-schema-change --alter "ADD COLUMN tracking_number VARCHAR(100)" \
    --execute D=mydb,t=orders
```

### Enums

Prefer string column + backed PHP enum. MySQL `ENUM` changes force a table rebuild.

```php
// Bad - altering values requires rebuild
$t->enum('status', ['pending', 'active', 'cancelled']);

// Good - DDL-free value evolution
$t->string('status', 20)->default('pending');
// cast in model: 'status' => OrderStatus::class
```

### Deploy sequencing

Multi-step patterns span releases:

1. **Release 1**: nullable column migration. Existing code ignores it.
2. **Release 2**: app reads/writes the new column.
3. **Release 3**: backfill + enforce NOT NULL.

Drops reverse the order: remove code references first, then drop.

### CI validation

Run `php artisan migrate && migrate:rollback && migrate` against a real MySQL instance. `down()` must reverse `up()` cleanly.

## Output Format

```
## Migration Plan
| Step | Migration File | Operation | Risk Level | Deploy Phase |

Risk Level: {Low | Medium | High | Critical}

## Deploy Sequence
- Release N: [action]
- Release N+1: [action]

## Rollback Plan
[down() description per migration]
```

## Avoid

- Mixing schema and data changes in one migration
- Missing `down()` (irreversible migrations)
- Direct NOT NULL or rename on large tables (table lock, broken deploys)
- Dropping columns or tables still referenced by running code
- MySQL `ENUM` (rebuild on value change)
- `WHERE col IS NULL LIMIT N` backfill loops (O(n^2)) - use `chunkById`
- Running multi-step migrations in one deployment
- Testing on SQLite when production is MySQL
- Adding FK constraints before backfill on large tables
