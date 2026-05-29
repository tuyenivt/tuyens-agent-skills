---
name: rails-postgresql-migration-safety
description: Zero-downtime Rails/PostgreSQL migrations: CONCURRENTLY, NOT VALID + VALIDATE, pg_advisory_lock, lock_timeout, large tables.
metadata:
  category: backend
  tags: [ruby, rails, postgresql, migration, zero-downtime]
user-invocable: false
---

> Load `Use skill: stack-detect` first. Use when `Database: PostgreSQL`. For MySQL, see `rails-migration-safety`.

## When to Use

- Creating or modifying tables, columns, indexes on PostgreSQL
- Adding NOT NULL or renaming/removing columns on deployed tables
- Backfilling >100K rows
- Adding foreign keys without downtime
- Partial indexes on status / enum columns
- Reviewing PG migrations before merge

## Rules

- One structural change per migration; reversible
- Data backfills in rake tasks, not `db/migrate/`
- New tables include `timestamps` + indexes on FK and filter columns
- `disable_ddl_transaction!` for all `CONCURRENTLY` operations
- `ignored_columns` before removing a column
- `safety_assured` only after verifying the operation is safe

## Patterns

### strong_migrations

```ruby
class AddIndexToOrdersStatus < ActiveRecord::Migration[7.2]
  disable_ddl_transaction!
  def change
    add_index :orders, :status, algorithm: :concurrently
  end
end
```

`safety_assured` overrides a check; use only after verifying:

```ruby
safety_assured { add_index :orders, :customer_id, algorithm: :concurrently }
```

### Adding a NOT NULL column

```ruby
# 1. add nullable + default
add_column :orders, :status, :string, default: "pending"

# 2. backfill (separate migration)
disable_ddl_transaction!
def up
  Order.in_batches(of: 10_000) { |b| b.where(status: nil).update_all(status: "pending") }
end

# 3. enforce
change_column_null :orders, :status, false
```

**Large tables (>1M rows): use NOT VALID + VALIDATE.** Direct `change_column_null` rewrites the table holding `ACCESS EXCLUSIVE`. NOT VALID validates new rows immediately and lets existing rows validate without blocking writes. Run VALIDATE in a separate migration with `disable_ddl_transaction!`:

```ruby
# Migration 1
add_check_constraint :orders, "status IS NOT NULL", name: "orders_status_null", validate: false

# Migration 2
disable_ddl_transaction!
def change
  validate_check_constraint :orders, name: "orders_status_null"
end
```

PG 12+: with a validated CHECK in place, `change_column_null` reuses it and becomes metadata-only.

### Partial Indexes

```ruby
add_index :orders, :fulfilled_at, where: "fulfilled_at IS NOT NULL",
          algorithm: :concurrently, name: "idx_orders_fulfilled"

add_index :orders, :status, where: "status IN (0, 1, 2)",
          algorithm: :concurrently, name: "idx_orders_active_status"
```

### Renaming Columns (four steps)

```ruby
# 1. add new
add_column :orders, :amount, :decimal
# 2. backfill
Order.in_batches { |b| b.update_all("amount = total") }
# 3. ignored_columns + deploy
# self.ignored_columns += ["total"]
# 4. remove (next deploy)
safety_assured { remove_column :orders, :total, :string }
```

### Dropping Columns (two deploys + audit)

Drops are final. Three phases.

**Phase 1 - Audit.** Grep every reference:

```bash
rg -n "legacy_field" app/ lib/ config/ spec/ db/ -g '*.{rb,erb,haml,slim,sql}' -g '!*.lock'
```

Also: BI dashboards, ETL pipelines, materialized views, PG functions, triggers, logical replication subscribers, FDW foreign tables. Drop dependent FK / index / generated-column / CHECK / **views** in a *prior* migration. `strong_migrations` catches FK/index but not view dependencies - find with `pg_depend`:

```sql
SELECT dependent_view.relname
FROM pg_depend
JOIN pg_rewrite ON pg_rewrite.oid = pg_depend.objid
JOIN pg_class dependent_view ON dependent_view.oid = pg_rewrite.ev_class
JOIN pg_class source_table ON source_table.oid = pg_depend.refobjid
JOIN pg_attribute ON pg_attribute.attrelid = pg_depend.refobjid
  AND pg_attribute.attnum = pg_depend.refobjsubid
WHERE source_table.relname = 'orders' AND pg_attribute.attname = 'legacy_field';
```

**Phase 2 - Prep (only if NOT NULL with no DB default AND app writes on every insert).** Once deploy A stops writing, next insert fails. Both metadata-only on PG 11+:

- `change_column_default :users, :legacy_field, from: nil, to: "guest"` - sensible default fits all rows
- `change_column_null :users, :legacy_field, true` - NULL acceptable for the short window

**Phase 3 - Two deploys.**

```ruby
# Deploy A: model only
class User < ApplicationRecord
  self.ignored_columns += ["legacy_field"]
end
# Remove read/write refs. Wait for full rollout - Sidekiq fleets lag web.

# Deploy B: migration + remove ignored_columns in same PR
safety_assured do
  remove_column :users, :legacy_field, :string, null: false, default: "guest"
end
```

Restate type/null/default for `db:rollback`. `DROP COLUMN` is metadata-only in PG (no rewrite). Disk reclaims via autovacuum or `pg_repack` if needed promptly.

Edge cases requiring extra steps: dependent objects (FK / index / generated / CHECK / view via `pg_depend`), external systems (BI / ETL / logical-replication / FDW), >100M-row tables where space reclamation is urgent (plan `pg_repack`).

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
add_foreign_key :orders, :users, validate: false  # fast
validate_foreign_key :orders, :users              # no write lock; sequential scan
```

Fix orphans if validation fails, then rerun.

### Large Tables (>1M Rows)

```ruby
Order.in_batches(of: 10_000) do |batch|
  batch.update_all(processed: true)
  sleep(0.1)
end
```

See `rails-batch-processing-patterns` for chunked-transaction shape, idempotency, memory safety.

### Lock and Statement Timeouts

```ruby
class AddIndexToOrdersStatus < ActiveRecord::Migration[7.2]
  disable_ddl_transaction!
  def change
    execute "SET lock_timeout = '5s'"
    add_index :orders, :status, algorithm: :concurrently
  end
end
```

Or globally: `StrongMigrations.lock_timeout = 5.seconds`.

For long backfills, also set `statement_timeout` per-batch:

```ruby
Order.in_batches(of: 10_000) do |batch|
  ActiveRecord::Base.connection.execute("SET LOCAL statement_timeout = '30s'")
  batch.update_all(processed: true)
end
```

### `change_column_default`

PG 11+ stores defaults as metadata - fast, no rewrite. Avoid `change_column` (combines type+default+null and rewrites every row):

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

See `rails-db-locking-patterns` for full leader-election patterns and `pg_advisory_xact_lock`.

### Rollback Safety

Test `db:migrate && db:rollback && db:migrate` in CI.

```ruby
def change
  reversible do |dir|
    dir.up   { execute "CREATE EXTENSION IF NOT EXISTS citext" }
    dir.down { execute "DROP EXTENSION IF EXISTS citext" }
  end
end
```

### INVALID indexes recovery

```sql
SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;
```

Then `DROP INDEX CONCURRENTLY` and rerun.

## Output Format

```
Migration: {file name}
Operation: {Create Table | Add Column | Add Index | Add FK | Backfill | Remove Column}
Table: {name}
Algorithm: {standard | CONCURRENTLY | NOT VALID + VALIDATE}
Lock window: {none | brief MDL | requires maintenance}
Safety: {Zero-Downtime | Maintenance Window | Batched Backfill}
Notes: {partial-index conditions, validate: false, etc.}
```

## Avoid

- Data changes in schema migrations
- `remove_column` without `ignored_columns` first
- Non-concurrent index on large tables (>100K rows)
- Direct column type changes - use add/backfill/remove
- `CONCURRENTLY` inside a transaction (incompatible)
- `change_column_null` on large tables - use NOT VALID + VALIDATE
- Irreversible migrations without explicit `raise ActiveRecord::IrreversibleMigration`
- Missing indexes on FK columns
- `add_column` with `null: false` on existing tables without default
- `change_column` when only the default is changing - rewrites the table
