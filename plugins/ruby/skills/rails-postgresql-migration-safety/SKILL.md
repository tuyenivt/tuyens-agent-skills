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

Column drops are final; treat them as a three-phase change (audit, prep if needed, two deploys), not a one-line `remove_column`.

**Phase 1 - Pre-flight audit.** Grep every reference, then look outside the repo:

```bash
rg -n "legacy_field" app/ lib/ config/ spec/ test/ db/ -g '!*.lock' \
  -g '*.rb' -g '*.erb' -g '*.haml' -g '*.slim' -g '*.sql'
```

Also check: BI dashboards, ETL pipelines, materialized views, PG functions, triggers, logical replication subscribers, FDW foreign tables. Drop dependent FKs / indexes / generated-column references / `CHECK` constraints / **views** in a *prior* migration. `strong_migrations` catches FK / index cases but not view dependencies - find those with `pg_depend`:

```sql
SELECT dependent_view.relname
FROM pg_depend
JOIN pg_rewrite ON pg_rewrite.oid = pg_depend.objid
JOIN pg_class dependent_view ON dependent_view.oid = pg_rewrite.ev_class
JOIN pg_class source_table ON source_table.oid = pg_depend.refobjid
JOIN pg_attribute ON pg_attribute.attrelid = pg_depend.refobjid AND pg_attribute.attnum = pg_depend.refobjsubid
WHERE source_table.relname = 'orders' AND pg_attribute.attname = 'legacy_field';
```

**Phase 2 - Prep migration (only if the column is `NOT NULL` with no DB-side default AND the app writes to it on every insert).** Once deploy A stops writing, the next insert hits the constraint. Pick one (both are metadata-only on PG 11+):

- `change_column_default :users, :legacy_field, from: nil, to: "guest"` - no NULLs ever, existing rows unchanged. Choose when a sensible default fits all rows.
- `change_column_null :users, :legacy_field, true` - new omitted-INSERT rows get `NULL` during the window. Choose when NULL is acceptable for the (short) window before column drop.

**Phase 3 - Two deploys.** Schema cache lives in every process; a single-deploy approach races old workers (still issuing `INSERT INTO users (..., legacy_field, ...)`) against the DDL.

```ruby
# Deploy A: model only, no migration. Use += so concerns/parents are preserved.
class User < ApplicationRecord
  self.ignored_columns += ["legacy_field"]
end
```

Remove all read/write references to the column. Wait for confirmed full rollout across web, Sidekiq, schedulers, and any other process that boots Rails - Sidekiq fleets often lag web; plan for the slower one. Don't proceed on a clock; confirm via the deploy system.

```ruby
# Deploy B: migration + remove the ignored_columns line in the same PR.
class RemoveLegacyFieldFromUsers < ActiveRecord::Migration[7.2]
  def change
    safety_assured do
      remove_column :users, :legacy_field, :string, null: false, default: "guest"
    end
  end
end
```

Restate the original type/null/default on `remove_column` so `db:rollback` can re-add the column. `DROP COLUMN` is metadata-only in PG (no table rewrite, milliseconds). Disk space reclaims via autovacuum, or `pg_repack` if you need it back promptly.

**This procedure is independent of `partial_inserts`.** `ignored_columns` removes the column from Rails' attribute map entirely.

**Edge cases requiring extra prior steps:** dependent objects (FK / index / generated column / `CHECK` / view via `pg_depend`), external systems (BI / ETL / logical-replication subscribers / FDW foreign tables) consuming the column, tables >100M rows where space reclamation is urgent (plan `pg_repack` after the drop).

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
