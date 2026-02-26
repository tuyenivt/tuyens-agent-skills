---
name: rails-migration-safety
description: "Safe Rails migration patterns for PostgreSQL. strong_migrations gem, zero-downtime DDL, reversible migrations, data migration separation, large table operations."
user-invocable: false
---

## 1. strong_migrations Gem

```ruby
# Gemfile
gem "strong_migrations"

# Automatically blocks unsafe operations:
# - Adding a column with a default (pre-Rails 5)
# - Adding a non-concurrent index
# - Changing column type
# - Removing a column without ignored_columns

# Override when you've verified safety:
class AddIndexToOrders < ActiveRecord::Migration[7.1]
  def change
    safety_assured do
      add_index :orders, :customer_id, algorithm: :concurrently
    end
  end
end
```

## 2. Zero-Downtime DDL

### Adding a NOT NULL column

```ruby
# Step 1: Add nullable column with default
class AddStatusToOrders < ActiveRecord::Migration[7.1]
  def change
    add_column :orders, :status, :string, default: "pending"
  end
end

# Step 2: Backfill (separate migration or background job)
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

### Adding indexes concurrently

```ruby
class AddIndexToOrdersStatus < ActiveRecord::Migration[7.1]
  disable_ddl_transaction!

  def change
    add_index :orders, :status, algorithm: :concurrently
  end
end
```

### Renaming columns (never directly)

```ruby
# ❌ NEVER: rename_column :orders, :total, :amount
# This locks the table and breaks running code.

# ✅ Step 1: Add new column
add_column :orders, :amount, :decimal

# ✅ Step 2: Backfill
Order.in_batches { |b| b.update_all("amount = total") }

# ✅ Step 3: Update code to use new column

# ✅ Step 4: Add ignored_columns to model
# class Order < ApplicationRecord
#   self.ignored_columns += ["total"]
# end

# ✅ Step 5: Remove old column
remove_column :orders, :total
```

### Dropping columns

```ruby
# Step 1: Add to ignored_columns FIRST (deploy)
class Order < ApplicationRecord
  self.ignored_columns += ["legacy_field"]
end

# Step 2: Remove column (next deploy)
class RemoveLegacyFieldFromOrders < ActiveRecord::Migration[7.1]
  def change
    safety_assured { remove_column :orders, :legacy_field, :string }
  end
end
```

## 3. Conventions

- **One structural change per migration** — don't mix adding columns with adding indexes
- **Always reversible** — use `change` method or explicit `up`/`down`
- **Separate data migrations** from schema migrations — use maintenance_tasks or a `db/data_migrate/` pattern
- **Timestamps** — always include `timestamps` on new tables

```ruby
class CreateOrders < ActiveRecord::Migration[7.1]
  def change
    create_table :orders do |t|
      t.references :customer, null: false, foreign_key: true
      t.decimal :total, precision: 10, scale: 2, null: false
      t.string :status, null: false, default: "pending"
      t.timestamps
    end

    add_index :orders, :status
  end
end
```

## 4. Large Tables (>1M Rows)

```ruby
# Use in_batches for data changes
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

# disable_ddl_transaction! for CONCURRENTLY operations
class AddIndexConcurrently < ActiveRecord::Migration[7.1]
  disable_ddl_transaction!

  def change
    add_index :orders, :customer_id, algorithm: :concurrently
  end
end
```

## 5. Foreign Keys

```ruby
# ✅ Add FK without full validation (avoids table lock)
class AddForeignKeyToOrders < ActiveRecord::Migration[7.1]
  def change
    add_foreign_key :orders, :customers, validate: false
  end
end

# ✅ Validate separately (no lock)
class ValidateOrdersCustomerFk < ActiveRecord::Migration[7.1]
  def change
    validate_foreign_key :orders, :customers
  end
end
```

## 6. Rollback

- Every migration MUST be reversible — test with `rails db:rollback`
- Add rollback testing to CI: `rails db:migrate && rails db:rollback && rails db:migrate`
- Use `reversible` block for complex cases:

```ruby
def change
  reversible do |dir|
    dir.up { execute "CREATE EXTENSION IF NOT EXISTS citext" }
    dir.down { execute "DROP EXTENSION IF EXISTS citext" }
  end
end
```

## 7. Anti-Patterns

- ❌ Data changes in schema migrations — use separate data migrations
- ❌ `remove_column` without `ignored_columns` first — causes errors on deploy
- ❌ Non-concurrent index on large tables — locks the table
- ❌ Changing column type directly — use add/backfill/remove pattern
- ❌ Running migrations in a transaction with CONCURRENTLY — they're incompatible
- ❌ Irreversible migrations without explicit `raise ActiveRecord::IrreversibleMigration`
