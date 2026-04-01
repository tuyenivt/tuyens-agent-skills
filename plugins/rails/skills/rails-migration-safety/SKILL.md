---
name: rails-migration-safety
description: Zero-downtime migration patterns for Rails/PostgreSQL. Covers strong_migrations gem enforcement, concurrent indexes, safe column operations, data migration separation, and large table strategies.
metadata:
  category: backend
  tags: [ruby, rails, postgresql, migration, zero-downtime]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Creating or modifying database tables, columns, or indexes
- Adding NOT NULL constraints or renaming/removing columns on deployed tables
- Running data backfills on tables with >100K rows
- Adding foreign keys to existing tables without downtime
- Adding partial indexes on status or enum columns
- Reviewing migrations for production safety before merge

## Rules

- One structural change per migration - do not mix adding columns with adding indexes
- Every migration must be reversible - use `change` method or explicit `up`/`down`
- Separate data migrations from schema migrations - use maintenance_tasks or `db/data_migrate/` pattern
- Always include `timestamps` on new tables
- Always add indexes on foreign key columns and frequently-filtered columns
- Use `disable_ddl_transaction!` for all `CONCURRENTLY` operations
- Add `ignored_columns` to the model before removing a column
- Use `safety_assured` only after verifying the operation is safe for your table size

## Patterns

### strong_migrations Gem

Bad - adding a non-concurrent index on a large table (locks reads/writes):

```ruby
class AddIndexToOrders < ActiveRecord::Migration[7.1]
  def change
    add_index :orders, :status # blocks the table
  end
end
```

Good - concurrent index with `disable_ddl_transaction!`:

```ruby
class AddIndexToOrdersStatus < ActiveRecord::Migration[7.1]
  disable_ddl_transaction!

  def change
    add_index :orders, :status, algorithm: :concurrently
  end
end
```

The `strong_migrations` gem automatically blocks unsafe operations. Override with `safety_assured` only after verifying safety:

```ruby
# Gemfile
gem "strong_migrations"

class AddIndexToOrders < ActiveRecord::Migration[7.1]
  def change
    safety_assured do
      add_index :orders, :customer_id, algorithm: :concurrently
    end
  end
end
```

### Adding a NOT NULL Column

Bad - adding NOT NULL column directly (fails if rows exist):

```ruby
add_column :orders, :status, :string, null: false
```

Good - three-step pattern:

```ruby
# Step 1: Add nullable column with default
class AddStatusToOrders < ActiveRecord::Migration[7.1]
  def change
    add_column :orders, :status, :string, default: "pending"
  end
end

# Step 2: Backfill (separate migration)
class BackfillOrderStatus < ActiveRecord::Migration[7.1]
  disable_ddl_transaction!

  def up
    Order.in_batches(of: 10_000) do |batch|
      batch.where(status: nil).update_all(status: "pending")
    end
  end

  def down; end
end

# Step 3: Add NOT NULL constraint
class AddNotNullToOrderStatus < ActiveRecord::Migration[7.1]
  def change
    change_column_null :orders, :status, false
  end
end
```

### Adding a Timestamp Column to an Existing Table

Good - nullable timestamp with partial index (e.g., `fulfilled_at` on orders):

```ruby
class AddFulfilledAtToOrders < ActiveRecord::Migration[7.1]
  disable_ddl_transaction!

  def change
    add_column :orders, :fulfilled_at, :datetime
    add_index :orders, :fulfilled_at, where: "fulfilled_at IS NOT NULL",
              algorithm: :concurrently, name: "idx_orders_fulfilled"
  end
end
```

### Partial Indexes on Status/Enum Columns

Partial indexes reduce index size by only indexing relevant rows. Useful for status columns where queries target non-terminal states:

```ruby
class AddPartialIndexOnOrderStatus < ActiveRecord::Migration[7.1]
  disable_ddl_transaction!

  def change
    add_index :orders, :status,
              where: "status IN (0, 1, 2)", # pending, confirmed, processing
              algorithm: :concurrently,
              name: "idx_orders_active_status"
  end
end
```

### Renaming Columns (Never Directly)

Bad - locks table and breaks running code:

```ruby
rename_column :orders, :total, :amount
```

Good - four-step deploy sequence:

```ruby
# Step 1: Add new column
add_column :orders, :amount, :decimal

# Step 2: Backfill
Order.in_batches { |b| b.update_all("amount = total") }

# Step 3: Update code to use new column, add ignored_columns
# class Order < ApplicationRecord
#   self.ignored_columns += ["total"]
# end

# Step 4: Remove old column (next deploy)
safety_assured { remove_column :orders, :total, :string }
```

### Dropping Columns

Bad - removing column while app still references it:

```ruby
remove_column :orders, :legacy_field
```

Good - two-deploy sequence:

```ruby
# Deploy 1: Add to ignored_columns
class Order < ApplicationRecord
  self.ignored_columns += ["legacy_field"]
end

# Deploy 2: Remove column
class RemoveLegacyFieldFromOrders < ActiveRecord::Migration[7.1]
  def change
    safety_assured { remove_column :orders, :legacy_field, :string }
  end
end
```

### Creating Tables with Proper Conventions

```ruby
class CreateOrders < ActiveRecord::Migration[7.1]
  def change
    create_table :orders do |t|
      t.references :user, null: false, foreign_key: true
      t.decimal :total, precision: 10, scale: 2, null: false
      t.integer :status, null: false, default: 0
      t.datetime :fulfilled_at
      t.timestamps
    end

    add_index :orders, :status
    add_index :orders, [:user_id, :status]
  end
end

class CreateOrderItems < ActiveRecord::Migration[7.1]
  def change
    create_table :order_items do |t|
      t.references :order, null: false, foreign_key: true
      t.references :product, null: false, foreign_key: true
      t.integer :quantity, null: false
      t.decimal :unit_price, precision: 10, scale: 2, null: false
      t.timestamps
    end
  end
end
```

### Large Tables (>1M Rows)

```ruby
# Batched data changes with throttling
Order.in_batches(of: 10_000) do |batch|
  batch.update_all(processed: true)
  sleep(0.1) # throttle to reduce DB load
end

# Background migration with maintenance_tasks gem
class Maintenance::BackfillOrderAmountTask < MaintenanceTasks::Task
  def collection
    Order.where(amount: nil)
  end

  def process(order)
    order.update!(amount: order.total * 1.1)
  end
end
```

### Foreign Keys Without Table Lock

Good - add FK without full validation, then validate separately:

```ruby
# Migration 1: Add FK (no validation - fast)
class AddForeignKeyToOrders < ActiveRecord::Migration[7.1]
  def change
    add_foreign_key :orders, :users, validate: false
  end
end

# Migration 2: Validate FK (no lock)
class ValidateOrdersUserFk < ActiveRecord::Migration[7.1]
  def change
    validate_foreign_key :orders, :users
  end
end
```

### Rollback Safety

Every migration must be reversible. Test with `rails db:rollback` in CI:

```bash
rails db:migrate && rails db:rollback && rails db:migrate
```

Use `reversible` block for operations that need explicit up/down:

```ruby
def change
  reversible do |dir|
    dir.up { execute "CREATE EXTENSION IF NOT EXISTS citext" }
    dir.down { execute "DROP EXTENSION IF EXISTS citext" }
  end
end
```

## Output Format

When generating migrations, document each change:

```
Migration: {file name}
Operation: {Create Table | Add Column | Add Index | Add FK | Backfill | Remove Column}
Table: {table name}
Safety: {Zero-Downtime | Requires Maintenance Window | Batched Backfill}
Notes: {any special considerations - partial index conditions, concurrent algorithm, etc.}
```

## Avoid

- Data changes in schema migrations - use separate data migrations
- `remove_column` without `ignored_columns` first - causes errors on deploy
- Non-concurrent index on large tables (>100K rows) - locks the table
- Changing column type directly - use add/backfill/remove pattern
- Running `CONCURRENTLY` inside a transaction - they are incompatible
- Irreversible migrations without explicit `raise ActiveRecord::IrreversibleMigration`
- Missing indexes on foreign key columns - slows joins and cascading deletes
- `add_column` with `null: false` on existing tables without default - fails if rows exist
