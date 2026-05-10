---
name: rails-postgresql-migration-safety
description: Zero-downtime Rails/PostgreSQL migrations: concurrent indexes, NOT VALID check constraints, pg_advisory_lock, lock_timeout, large tables.
metadata:
  category: backend
  tags: [ruby, rails, postgresql, migration, zero-downtime]
user-invocable: false
---

> Load `Use skill: stack-detect` first. Use when `Database: PostgreSQL` is declared in CLAUDE.md. For MySQL, see `rails-migration-safety`.

## When to Use

- Creating or modifying tables, columns, or indexes on PostgreSQL
- Adding NOT NULL or renaming/removing columns on deployed tables
- Running data backfills on tables with >100K rows
- Adding foreign keys without downtime
- Adding partial indexes on status or enum columns
- Reviewing PG migrations before merge

## Rules

- One structural change per migration
- Every migration must be reversible
- Separate data migrations from schema migrations - use a rake task (see `rails-rake-task-patterns`)
- Always include `timestamps` on new tables
- Always add indexes on FK columns and frequently-filtered columns
- Use `disable_ddl_transaction!` for all `CONCURRENTLY` operations
- Add `ignored_columns` before removing a column
- Use `safety_assured` only after verifying the operation is safe

## Patterns

### strong_migrations gem

```ruby
# Bad - non-concurrent index on a large table
add_index :orders, :status

# Good
class AddIndexToOrdersStatus < ActiveRecord::Migration[7.2]
  disable_ddl_transaction!
  def change
    add_index :orders, :status, algorithm: :concurrently
  end
end
```

`strong_migrations` blocks unsafe ops; `safety_assured` overrides only after verifying:

```ruby
safety_assured { add_index :orders, :customer_id, algorithm: :concurrently }
```

### Adding a NOT NULL column

```ruby
# Step 1: Add nullable with default
add_column :orders, :status, :string, default: "pending"

# Step 2: Backfill (separate migration)
disable_ddl_transaction!
def up
  Order.in_batches(of: 10_000) do |batch|
    batch.where(status: nil).update_all(status: "pending")
  end
end

# Step 3: Add NOT NULL
change_column_null :orders, :status, false
```

**Large tables (>1M rows): use a NOT VALID check constraint.** Direct `change_column_null` rewrites the table holding `ACCESS EXCLUSIVE`. A `NOT VALID` check validates new rows immediately and lets existing rows validate without blocking writes:

```ruby
# Step 3a: Add unvalidated constraint (fast, no table scan)
add_check_constraint :orders, "status IS NOT NULL", name: "orders_status_null", validate: false

# Step 3b: Validate (no write lock; sequential scan)
validate_check_constraint :orders, name: "orders_status_null"
```

`strong_migrations` flags `change_column_null` on large tables and recommends this pattern. In PG 12+, with a validated CHECK in place, promoting to column-level `NOT NULL` is metadata-only.

### Adding a Timestamp Column with Partial Index

```ruby
class AddFulfilledAtToOrders < ActiveRecord::Migration[7.2]
  disable_ddl_transaction!
  def change
    add_column :orders, :fulfilled_at, :datetime
    add_index :orders, :fulfilled_at, where: "fulfilled_at IS NOT NULL",
              algorithm: :concurrently, name: "idx_orders_fulfilled"
  end
end
```

### Partial Indexes on Status / Enum Columns

Partial indexes reduce size by only indexing relevant rows:

```ruby
add_index :orders, :status, where: "status IN (0, 1, 2)",
          algorithm: :concurrently, name: "idx_orders_active_status"
```

### Renaming Columns (never directly)

Four-step deploy sequence:

```ruby
# Step 1: Add new column
add_column :orders, :amount, :decimal

# Step 2: Backfill
Order.in_batches { |b| b.update_all("amount = total") }

# Step 3: Update code; add ignored_columns
# self.ignored_columns += ["total"]

# Step 4: Remove (next deploy)
safety_assured { remove_column :orders, :total, :string }
```

### Dropping Columns

```ruby
# Deploy 1: Add to ignored_columns
self.ignored_columns += ["legacy_field"]

# Deploy 2: Remove
safety_assured { remove_column :orders, :legacy_field, :string }
```

`remove_column` on a column with no FK or index is metadata-only in PG.

### Creating Tables

```ruby
create_table :orders do |t|
  t.references :user, null: false, foreign_key: true
  t.decimal :total, precision: 10, scale: 2, null: false
  t.integer :status, null: false, default: 0
  t.datetime :fulfilled_at
  t.timestamps
end
add_index :orders, [:user_id, :status]
```

### Foreign Keys Without Table Lock

```ruby
# Migration 1: Add FK without validation (fast)
add_foreign_key :orders, :users, validate: false

# Migration 2: Validate FK (no write lock; sequential scan)
validate_foreign_key :orders, :users
```

If validation fails, fix orphan rows and rerun.

### Large Tables (>1M Rows)

```ruby
# Batched data changes with throttling
Order.in_batches(of: 10_000) do |batch|
  batch.update_all(processed: true)
  sleep(0.1)
end
```

For chunked-transaction shape, idempotency, memory safety, see `rails-batch-processing-patterns`.

### Lock Timeouts and Statement Timeouts

A migration waiting behind a long query can pile up blocked sessions. Set `lock_timeout`:

```ruby
class AddIndexToOrdersStatus < ActiveRecord::Migration[7.2]
  disable_ddl_transaction!
  def change
    execute "SET lock_timeout = '5s'"
    add_index :orders, :status, algorithm: :concurrently
  end
end
```

Configure globally via `StrongMigrations.lock_timeout = 5.seconds`.

For long backfills, also set `statement_timeout` per-batch:

```ruby
Order.in_batches(of: 10_000) do |batch|
  ActiveRecord::Base.connection.execute("SET LOCAL statement_timeout = '30s'")
  batch.update_all(processed: true)
end
```

### `change_column_default`

PG 11+ stores defaults as metadata - `change_column_default` is fast, no table rewrite. Avoid `change_column` (which combines type+default+null and rewrites every row even if you only meant to change the default):

```ruby
change_column_default :orders, :status, from: nil, to: "pending"
```

### Advisory Locks for Backfills

```ruby
def up
  ApplicationRecord.with_advisory_lock("backfill_order_amount", timeout_seconds: 0) do
    Order.in_batches(of: 10_000) { |b| b.where(amount: nil).update_all(amount: ...) }
  end || abort("another backfill_order_amount is running")
end
```

For full leader-election patterns and `pg_advisory_xact_lock`, see `rails-db-locking-patterns`.

### Rollback Safety

Test with `rails db:migrate && rails db:rollback && rails db:migrate` in CI.

```ruby
def change
  reversible do |dir|
    dir.up   { execute "CREATE EXTENSION IF NOT EXISTS citext" }
    dir.down { execute "DROP EXTENSION IF EXISTS citext" }
  end
end
```

### INVALID indexes recovery

If `CONCURRENTLY` fails midway you'll have an `INVALID` index. Detect:

```sql
SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;
```

Then `DROP INDEX CONCURRENTLY` and rerun.

## Output Format

```
Migration: {file name}
Operation: {Create Table | Add Column | Add Index | Add FK | Backfill | Remove Column}
Table: {table name}
Algorithm: {standard | CONCURRENTLY | NOT VALID + VALIDATE}
Lock window: {none | brief MDL | requires maintenance}
Safety: {Zero-Downtime | Requires Maintenance Window | Batched Backfill}
Notes: {partial-index conditions, validate: false flag, etc.}
```

## Avoid

- Data changes in schema migrations
- `remove_column` without `ignored_columns` first
- Non-concurrent index on large tables (>100K rows)
- Changing column type directly - use add/backfill/remove
- Running `CONCURRENTLY` inside a transaction (incompatible)
- `change_column_null` on large tables - use NOT VALID + VALIDATE pattern
- Irreversible migrations without explicit `raise ActiveRecord::IrreversibleMigration`
- Missing indexes on FK columns
- `add_column` with `null: false` on existing tables without default
- `change_column` when only the default is changing - rewrites the table
