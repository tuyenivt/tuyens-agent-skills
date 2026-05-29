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
- Multi-step patterns span releases - never a single deploy
- Test against real MySQL (`<env DB_CONNECTION>mysql</env>` in `phpunit.xml`); SQLite hides locking/JSON/FK behavior
- Backfills use `chunkById()`; never `WHERE col IS NULL LIMIT N` loops (O(n^2))

## Patterns

### Strategy by table size

| Operation        | < 100K rows         | 100K-1M rows         | > 1M rows                          |
| ---------------- | ------------------- | -------------------- | ---------------------------------- |
| Add nullable col | Direct              | Direct (instant)     | Direct (instant)                   |
| Add NOT NULL col | Direct with default | 3-step               | 3-step; `pt-osc` if no INSTANT path |
| Add index        | Direct              | `ALGORITHM=INPLACE`  | `ALGORITHM=INPLACE, LOCK=NONE`     |
| Rename column    | Expand-contract     | Expand-contract      | Expand-contract                    |
| Drop column      | Direct              | Direct               | Remove code first, then drop       |

MySQL 8.0+: NOT NULL with constant DEFAULT is `ALGORITHM=INSTANT`. Use `pt-osc` only when INSTANT/INPLACE aren't possible (column type change, PRIMARY restructure).

### Adding columns - 3-step pattern

Use when values must be computed per row.

```php
// Release 1: nullable column
$t->string('tracking_number', 100)->nullable()->after('status');

// Release 2: backfill (separate file)
DB::table('orders')
    ->whereNull('tracking_number')
    ->chunkById(1000, function ($orders) {
        foreach ($orders as $o) {
            DB::table('orders')->where('id', $o->id)
                ->update(['tracking_number' => 'LEGACY-' . $o->id]);
        }
    });

// Release 3: enforce NOT NULL after backfill verified
$t->string('tracking_number', 100)->nullable(false)->change();
```

`->change()` requires `doctrine/dbal` on Laravel < 11.

### Indexes

InnoDB online DDL keeps reads/writes flowing. Pin the algorithm on large tables via raw SQL.

```php
$t->index('status');                                       // small
$t->index(['status', 'created_at']);                       // composite, leftmost-prefix

// Large table
DB::statement('ALTER TABLE orders ADD INDEX idx_status (status), ALGORITHM=INPLACE, LOCK=NONE');
```

### Foreign keys

Add the column and backfill first; add the constraint last.

```php
$t->unsignedBigInteger('product_id')->nullable();          // 1. column
// 2. backfill (separate migration)
$t->foreign('product_id')->references('id')->on('products'); // 3. constraint
```

### Data migrations

Separate file, separate release. Always `chunkById()`.

```php
DB::table('orders')
    ->where('status', 'legacy_pending')
    ->chunkById(1000, function ($orders) {
        DB::table('orders')
            ->whereIn('id', $orders->pluck('id'))
            ->update(['status' => 'pending']);
    });
```

### Expand-contract for renames and drops

Direct renames break running code mid-deploy. Sequence across releases:

1. Add new column (nullable)
2. Backfill from old column
3. App dual-writes (old + new), reads new
4. App stops writing old
5. Drop old column (later release)

```php
// Step 1
$t->string('recipient_name')->nullable()->after('customer_name');
// Step 5 - later release, after code stops referencing customer_name
$t->dropColumn('customer_name');
```

Table drops follow the same shape.

### Large-table alterations - external tools

When INPLACE/INSTANT isn't possible (column type change forcing rebuild on a 10M+ row table):

- **pt-online-schema-change** (Percona): shadow copy + trigger-based sync + atomic swap
- **gh-ost** (GitHub): binlog-based, no triggers

```bash
pt-online-schema-change --alter "ADD COLUMN tracking_number VARCHAR(100)" \
    --max-lag=5s --critical-load Threads_running=80 \
    --execute D=mydb,t=orders
```

### Enums

Prefer string column + backed PHP enum. MySQL `ENUM` forces a rebuild on value change.

```php
$t->string('status', 20)->default('pending');
// model: 'status' => OrderStatus::class
```

### CI validation

Run `php artisan migrate && migrate:rollback && migrate` against real MySQL. `down()` must reverse `up()` cleanly.

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

- Mixing schema and data changes in one migration file
- Missing `down()` (irreversible migration)
- Direct NOT NULL or rename on large tables (table lock, broken deploys)
- Dropping columns/tables still referenced by running code
- MySQL `ENUM` (rebuild on value change)
- `WHERE col IS NULL LIMIT N` backfill loops - use `chunkById`
- Running multi-step migrations in one deployment
- Adding FK constraint before backfill on large tables
