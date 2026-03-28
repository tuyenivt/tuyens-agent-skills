---
name: laravel-migration-safety
description: "Zero-downtime migration patterns for Laravel and MySQL. Covers lock-safe DDL, NOT NULL via nullable-first, InnoDB online DDL, data migration separation, expand-contract renames, and multi-release deploy sequencing."
metadata:
  category: backend
  tags: [php, laravel, mysql, migrations, zero-downtime, ddl]
user-invocable: false
---

## LARAVEL MIGRATIONS

- Artisan commands: `php artisan make:migration`, `php artisan migrate`, `php artisan migrate:rollback`
- Every migration has `up()` and `down()` - `down()` must be reversible
- Separate schema migrations from data migrations (separate migration files)
- Review every migration before running - never trust generated code blindly
- Never mix DDL and DML in the same migration

## ADD NULLABLE COLUMN (Safe)

Adding a nullable column is metadata-only in InnoDB - fast and lock-free.

```php
// Safe - nullable column addition
public function up(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->string('tracking_number', 100)->nullable()->after('status');
    });
}

public function down(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->dropColumn('tracking_number');
    });
}
```

## ADD NOT NULL COLUMN (Multi-Step)

Direct NOT NULL column addition locks the table. Use the 3-step pattern:

```php
// Step 1: Add nullable column (separate migration)
public function up(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->string('tracking_number', 100)->nullable();
    });
}

// Step 2: Backfill data (separate migration)
public function up(): void
{
    DB::table('orders')
        ->whereNull('tracking_number')
        ->chunkById(1000, function ($orders) {
            foreach ($orders as $order) {
                DB::table('orders')
                    ->where('id', $order->id)
                    ->update(['tracking_number' => 'LEGACY-' . $order->id]);
            }
        });
}

// Step 3: Set NOT NULL (separate migration, after deploy confirms backfill complete)
public function up(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->string('tracking_number', 100)->nullable(false)->change();
    });
}
```

## NOT NULL WITH DEFAULT (MySQL 8.0+ Shortcut)

MySQL 8.0+ can add a NOT NULL column with a constant DEFAULT as an instant operation (metadata-only, no table rebuild):

```php
// Single migration - instant on MySQL 8.0+ with ALGORITHM=INSTANT support
public function up(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->string('tracking_number', 100)->default('PENDING');
    });
}
```

If a constant default is NOT acceptable (values must be computed per row), use the 3-step pattern above.

## INDEX CREATION

```php
// Small table - standard index
public function up(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->index('status');
    });
}

// Large table - use algorithm hint for InnoDB online DDL
public function up(): void
{
    // InnoDB online DDL allows concurrent reads/writes during index creation
    DB::statement('ALTER TABLE orders ADD INDEX idx_orders_status (status), ALGORITHM=INPLACE, LOCK=NONE');
}

public function down(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->dropIndex('idx_orders_status');
    });
}

// Composite index
public function up(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->index(['status', 'created_at']);
    });
}
```

## FOREIGN KEY CONSTRAINTS

Add foreign keys after data migration is complete to avoid lock contention.

```php
// Step 1: Add column without constraint
public function up(): void
{
    Schema::table('order_items', function (Blueprint $table) {
        $table->unsignedBigInteger('product_id')->nullable();
    });
}

// Step 2: Backfill product_id values (separate migration)

// Step 3: Add foreign key constraint (separate migration)
public function up(): void
{
    Schema::table('order_items', function (Blueprint $table) {
        $table->foreign('product_id')->references('id')->on('products');
    });
}
```

## DATA MIGRATIONS

Separate data migrations from schema migrations. Use chunked processing for large tables.

```php
// Data migration - always use chunkById for update safety
public function up(): void
{
    DB::table('orders')
        ->where('status', 'legacy_pending')
        ->chunkById(1000, function ($orders) {
            $ids = $orders->pluck('id')->toArray();
            DB::table('orders')
                ->whereIn('id', $ids)
                ->update(['status' => 'pending']);
        });
}

public function down(): void
{
    DB::table('orders')
        ->where('status', 'pending')
        ->update(['status' => 'legacy_pending']);
}
```

## COLUMN RENAMES (Expand-Contract)

Never rename a column directly - breaks running code during deploy.

1. Add new column (nullable) - migration
2. Backfill new column from old column - data migration
3. Update app code to write to both columns, read from new - deploy
4. Stop writing to old column - deploy
5. Drop old column - migration in a later release

```php
// Step 1: Add new column
public function up(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->string('recipient_name')->nullable()->after('customer_name');
    });
}

// Step 2: Backfill (separate migration)
public function up(): void
{
    DB::table('orders')
        ->whereNull('recipient_name')
        ->chunkById(1000, function ($orders) {
            foreach ($orders as $order) {
                DB::table('orders')
                    ->where('id', $order->id)
                    ->update(['recipient_name' => $order->customer_name]);
            }
        });
}

// Step 5: Drop old column (later release, after code no longer references it)
public function up(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->dropColumn('customer_name');
    });
}
```

## TABLE DROPS

Never drop tables that running code still references. Expand-contract:

1. Remove all code references to the table - deploy
2. Drop the table - migration in a later release

## LARGE TABLE ALTERATIONS

For tables with millions of rows where standard `ALTER TABLE` is too slow or causes excessive locking:

- **pt-online-schema-change** (Percona Toolkit): Creates a shadow copy, applies changes, swaps atomically
- **gh-ost** (GitHub): Binlog-based online schema migration, no triggers

```bash
# pt-online-schema-change example
pt-online-schema-change --alter "ADD COLUMN tracking_number VARCHAR(100)" \
    --execute D=mydb,t=orders
```

Use these tools only when standard InnoDB online DDL (`ALGORITHM=INPLACE`) is insufficient.

## DEPLOY SEQUENCING

Multi-step patterns must be deployed across multiple releases:

1. **Release 1**: Add nullable column migration. Deploy. Existing app code ignores the new column.
2. **Release 2**: Update app code to read/write the new column. Deploy.
3. **Release 3**: Backfill migration + set NOT NULL. Deploy.

For column removal, reverse the order: remove code references first (Release 1), then drop the column (Release 2).

## ENUM COLUMNS

Prefer backed PHP enums with string columns over MySQL ENUM type. MySQL ENUM changes require table rebuild.

```php
// Bad - MySQL ENUM (altering requires table rebuild)
$table->enum('status', ['pending', 'active', 'cancelled']);

// Good - string column + PHP backed enum (no DDL to add new values)
$table->string('status', 20)->default('pending');

// In model
protected function casts(): array
{
    return ['status' => OrderStatus::class];
}
```

## CI VALIDATION

- Run `php artisan migrate` + `php artisan migrate:rollback` + `php artisan migrate` in CI (must be clean)
- Test migrations against a real MySQL instance (not SQLite)
- Verify `down()` reverses `up()` cleanly

## ANTI-PATTERNS

- ❌ Mixing schema and data changes in one migration
- ❌ Missing `down()` method (irreversible migrations)
- ❌ `ALTER COLUMN SET NOT NULL` directly on large tables (table lock)
- ❌ Renaming columns directly (breaks running code)
- ❌ Dropping columns referenced by running code
- ❌ MySQL ENUM type (table rebuild on change)
- ❌ `WHERE col IS NULL LIMIT N` backfill loops (O(n^2) - use `chunkById`)
- ❌ Running all multi-step migrations in a single deployment
- ❌ Testing migrations against SQLite when production is MySQL (behavior differences)
- ❌ Foreign key addition on large tables without separate backfill step
