---
name: rails-migration-safety
description: Zero-downtime Rails/MySQL migrations: 8.0 instant DDL, online INPLACE, invisible indexes, gh-ost for >100M-row tables.
metadata:
  category: backend
  tags: [ruby, rails, mysql, migration, zero-downtime]
user-invocable: false
---

> Load `Use skill: stack-detect` first. MySQL-primary. For PostgreSQL projects, use `rails-postgresql-migration-safety`.

## When to Use

- Creating or modifying tables, columns, or indexes on MySQL/MariaDB
- Adding NOT NULL constraints or renaming/removing columns on deployed tables
- Running data backfills on tables with >100K rows
- Adding foreign keys without downtime
- Choosing between in-process Rails migration, `gh-ost`, and `pt-online-schema-change`
- Reviewing migrations for production safety before merge

## Rules

- One structural change per migration
- Every migration must be reversible
- Separate data migrations from schema migrations - use a rake task (see `rails-rake-task-patterns`)
- Always include `timestamps` on new tables
- Always add indexes on FK columns and frequently-filtered columns
- Set `config.active_record.schema_format = :sql` so MySQL-specific DDL round-trips through `structure.sql`
- Add `ignored_columns` to the model before removing a column
- Use `safety_assured` only after verifying the operation is safe for your table size
- For tables >100M rows, use `gh-ost` or `pt-online-schema-change`, not in-process Rails migrations

## Patterns

### `schema_format = :sql` for MySQL projects

`:ruby` (default) flattens MySQL-specific DDL into a normalized DSL that loses character set/collation per column, generated columns, functional indexes, `ALGORITHM=INSTANT` defaults, `CHECK` constraints, and full-text parsers. Switch to `:sql`:

```ruby
# config/application.rb
config.active_record.schema_format = :sql
```

Recommended from day one for new MySQL apps.

### strong_migrations gem

```ruby
# config/initializers/strong_migrations.rb
StrongMigrations.lock_timeout = 5.seconds
StrongMigrations.statement_timeout = 1.hour
StrongMigrations.target_version = 12
```

`safety_assured` overrides a check; use only after confirming the operation is safe.

### Online DDL: `ALGORITHM=INPLACE` and `LOCK=NONE`

MySQL 5.6+ runs most index operations online without blocking writes. MySQL 8.0 picks the best algorithm automatically. Rails does **not** auto-emit `algorithm: :concurrently` (PostgreSQL-only) - use `:inplace` or omit:

```ruby
# Bad - PG syntax, raises on MySQL
add_index :orders, :status, algorithm: :concurrently

# Good
add_index :orders, :status, algorithm: :inplace
# or, for exact control:
execute "ALTER TABLE orders ADD INDEX idx_orders_status (status), ALGORITHM=INPLACE, LOCK=NONE"
```

### Instant DDL (MySQL 8.0)

`ALGORITHM=INSTANT` is metadata-only - finishes in milliseconds even on TB-scale tables.

| Operation                            | Supported since |
| ------------------------------------ | --------------- |
| Add column (last position)           | 8.0.12          |
| Add column (any position)            | 8.0.29          |
| Drop column                          | 8.0.29          |
| Rename column                        | 8.0.13          |
| Modify default value                 | 8.0.0           |
| Add/drop virtual generated column    | 8.0.0           |
| Modify enum/set members (additions)  | 8.0.0           |
| Rename table                         | 8.0.0           |

**Rails 7.2 does not auto-emit `INSTANT`.** Use `execute` or rely on 8.0.29+ defaulting to INSTANT for supported ops:

```ruby
class AddNotesToOrders < ActiveRecord::Migration[7.2]
  def change
    execute "ALTER TABLE orders ADD COLUMN notes TEXT, ALGORITHM=INSTANT, LOCK=NONE"
  end
end
```

This collapses many "add NOT NULL with default" three-step dances into a single instant ALTER on supported tables.

### Invisible indexes (MySQL 8.0)

Soft-drop an index to verify nothing breaks before actually dropping:

```ruby
execute "ALTER TABLE orders ALTER INDEX idx_orders_legacy INVISIBLE"
# Soak; monitor query plans, slow log
# If anything breaks: ALTER INDEX ... VISIBLE (instant)
remove_index :orders, name: "idx_orders_legacy"
```

No PostgreSQL equivalent.

### Adding a NOT NULL column

For MySQL 8.0.12+ adding a column at the end with a default is `INSTANT`-eligible - one migration:

```ruby
def change
  execute "ALTER TABLE users ADD COLUMN tier VARCHAR(20) NOT NULL DEFAULT 'standard', ALGORITHM=INSTANT, LOCK=NONE"
end
```

Otherwise, classic three-step (works on any version):

```ruby
# Step 1: Add nullable with default
add_column :orders, :status, :string, default: "pending"

# Step 2: Backfill (separate migration, batched)
def up
  Order.in_batches(of: 10_000) { |b| b.where(status: nil).update_all(status: "pending") }
end

# Step 3: Enforce NOT NULL
change_column_null :orders, :status, false
```

**Large tables (>100M rows): don't `change_column_null` directly.** MySQL has no PG-style `validate: false` for `CHECK`. Two options:

1. **App-side validation forever** - leave column nullable, enforce `validates :status, presence: true`. Many production MySQL shops do this on hot tables.
2. **Use `gh-ost`**:

```bash
gh-ost --user=app --host=primary.db --database=app --table=orders \
  --alter="MODIFY COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'" --execute
```

### MySQL `CHECK` constraints (8.0.16+)

Validates on creation - no `validate: false` shortcut. For very large tables, the addition scans every row:

```ruby
add_check_constraint :orders, "total >= 0", name: "orders_total_non_negative"
```

For very large tables, run during a maintenance window or use `gh-ost` with the constraint in `--alter`.

### Functional indexes

MySQL has no partial indexes (`where:` clause). Functional index on an expression is the closest analogue:

```ruby
add_index :users, "((LOWER(email)))", name: "idx_users_email_lower"
add_index :users, "(JSON_VALUE(metadata, '$.tier' RETURNING CHAR(50)))", name: "idx_users_tier"
```

Note the double parentheses required by Rails for raw expressions.

### Renaming columns (never directly)

```ruby
# Step 1: Add new column
add_column :orders, :amount, :decimal, precision: 10, scale: 2

# Step 2: Backfill
Order.in_batches { |b| b.update_all("amount = total") }

# Step 3: Update code; add ignored_columns
# self.ignored_columns += ["total"]

# Step 4: Remove old column (next deploy)
safety_assured { remove_column :orders, :total, :decimal }
```

MySQL 8.0.13+ supports `RENAME COLUMN` with `INSTANT`, but the four-step is still required because step 3 must complete before step 4.

### Dropping columns

```ruby
# Deploy 1: Add to ignored_columns
self.ignored_columns += ["legacy_field"]

# Deploy 2: Remove
safety_assured { remove_column :orders, :legacy_field, :string }
```

On 8.0.29+, `DROP COLUMN` is `INSTANT`-eligible - second deploy completes in ms.

### Creating tables with proper conventions

```ruby
create_table :orders, options: "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci" do |t|
  t.references :user, null: false, foreign_key: true
  t.decimal :total, precision: 10, scale: 2, null: false
  t.integer :status, null: false, default: 0
  t.datetime :fulfilled_at
  t.timestamps
end
add_index :orders, [:user_id, :status]
```

`utf8mb4` (not `utf8`) is the only character set for 4-byte sequences (emoji, supplementary plane CJK). Set collation explicitly for reproducible `db:schema:load`.

### Large tables (>100M rows): use `gh-ost`

Rails in-process migrations don't throttle on replication lag, disk usage, or master CPU. `gh-ost` does:

```bash
gh-ost --user=app --host=primary.db --database=app --table=orders \
  --alter="ADD COLUMN amount DECIMAL(10,2) NOT NULL DEFAULT 0" \
  --max-load=Threads_running=25 --critical-load=Threads_running=100 \
  --max-lag-millis=1500 --execute
```

Alternative: `pt-online-schema-change` (Percona Toolkit) - trigger-based, slower, works on more topologies.

For data backfills (not structural), see `rails-batch-processing-patterns`.

### Foreign keys

MySQL validates FKs on creation; the operation acquires a metadata lock briefly. For very large tables under load, use `gh-ost --alter="ADD CONSTRAINT ..."`.

### Lock timeouts

Set `innodb_lock_wait_timeout` so a migration waiting behind a long query fails fast:

```ruby
def change
  execute "SET SESSION innodb_lock_wait_timeout = 5"
  add_index :orders, :status, algorithm: :inplace
end
```

Configure globally via `StrongMigrations.lock_timeout = 5.seconds`.

### Advisory locks for backfills

When a backfill might be triggered twice (deploy retry, two ops engineers), guard with `with_advisory_lock` (cross-reference `rails-db-locking-patterns`):

```ruby
def up
  ApplicationRecord.with_advisory_lock("backfill_order_amount", timeout_seconds: 0) do
    Order.in_batches(of: 10_000) do |b|
      b.where(amount: nil).update_all(amount: ...)
    end
  end || abort("another backfill_order_amount is running")
end
```

### Rollback safety

Test with `rails db:migrate && rails db:rollback && rails db:migrate` in CI.

```ruby
def change
  reversible do |dir|
    dir.up   { execute "ALTER TABLE orders ADD COLUMN notes TEXT, ALGORITHM=INSTANT" }
    dir.down { execute "ALTER TABLE orders DROP COLUMN notes, ALGORITHM=INSTANT" }
  end
end
```

Note: instant DDL is irreversible in some cases (8.0.29+ records the operation in instant-add metadata; rollback may require a table rebuild). Test rollback on a clone before merging.

### MariaDB caveats

- `ALGORITHM=INSTANT` not until 10.3+, narrower coverage than MySQL 8.0
- `CHECK` since 10.2 with different naming syntax
- Invisible indexes not supported
- `GET_LOCK`: 10.0.2+ supports multiple locks per session

If you hit a divergence, use `pt-online-schema-change` (MariaDB-friendly).

## Output Format

```
Migration: {file name}
Operation: {Create Table | Add Column | Add Index | Add FK | Backfill | Remove Column}
Table: {table name}
Adapter: MySQL {version}
Algorithm: {INSTANT | INPLACE | COPY | gh-ost | pt-online-schema-change}
Lock window: {none (online) | brief MDL | maintenance required}
Safety: {Zero-Downtime | Requires Maintenance Window | Batched Backfill}
Notes: {character set / collation, instant-DDL eligibility, gh-ost throttle config}
```

## Avoid

- `algorithm: :concurrently` on MySQL - PG-only, raises
- `where:` partial-index clauses on MySQL - not supported
- Data changes in schema migrations
- `remove_column` without `ignored_columns` first
- Changing column type directly - use add/backfill/remove
- Irreversible migrations without explicit `raise ActiveRecord::IrreversibleMigration`
- Missing indexes on FK columns
- `add_column` with `null: false` on existing tables without default
- In-process migrations on tables >100M rows - use `gh-ost`
- `change_column_null` on a hot multi-100M-row table - prefer model-side validation or `gh-ost`
- Default character set assumptions - always specify `utf8mb4` and collation explicitly
- `:ruby` schema format on MySQL projects with functional indexes / generated columns / CHECK constraints
