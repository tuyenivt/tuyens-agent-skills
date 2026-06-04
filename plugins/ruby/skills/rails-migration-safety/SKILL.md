---
name: rails-migration-safety
description: Zero-downtime Rails/MySQL migrations: 8.0 INSTANT DDL, online INPLACE, invisible indexes, gh-ost for >100M-row tables.
metadata:
  category: backend
  tags: [ruby, rails, mysql, migration, zero-downtime]
user-invocable: false
---

> Load `Use skill: stack-detect` first. Use when `Database: MySQL` or MariaDB. For PostgreSQL, see `rails-postgresql-migration-safety` (sibling - load that instead, never both).

## When to Use

- Creating or modifying tables, columns, indexes on MySQL/MariaDB
- Adding NOT NULL, renaming, or removing columns on deployed tables
- Backfilling >100K rows
- Adding foreign keys without downtime
- Choosing between in-process migration, `gh-ost`, `pt-online-schema-change`
- Reviewing migrations for production safety before merge

## Rules

- One structural change per migration; reversible.
- Data backfills live in rake tasks, not `db/migrate/` (see `rails-rake-task-patterns`).
- New tables include `timestamps` and indexes on FK + filter columns.
- `schema_format = :sql` - `:ruby` loses charset/collation, generated columns, functional indexes, INSTANT defaults, CHECK.
- `ignored_columns` ships in a deploy before `remove_column`.
- `safety_assured` only after verifying the operation is safe for the table size.
- Tables >100M rows: `gh-ost` or `pt-online-schema-change`, never in-process.

## Patterns

### `strong_migrations`

```ruby
# config/initializers/strong_migrations.rb
StrongMigrations.lock_timeout      = 5.seconds
StrongMigrations.statement_timeout = 1.hour
StrongMigrations.target_version    = "8.0"  # gates INSTANT checks
```

### Online DDL: INPLACE / LOCK=NONE

Rails does **not** auto-emit `algorithm: :concurrently` (PG-only):

```ruby
# Bad - raises on MySQL
add_index :orders, :status, algorithm: :concurrently

# Good
add_index :orders, :status, algorithm: :inplace
# Exact control:
execute "ALTER TABLE orders ADD INDEX idx_orders_status (status), ALGORITHM=INPLACE, LOCK=NONE"
```

### INSTANT DDL (MySQL 8.0)

Metadata-only - finishes in ms even on TB tables.

| Operation                            | Since   |
| ------------------------------------ | ------- |
| Add column (last position)           | 8.0.12  |
| Add column (any position)            | 8.0.29  |
| Drop column                          | 8.0.29  |
| Rename column                        | 8.0.13  |
| Modify default                       | 8.0.0   |
| Add/drop virtual generated column    | 8.0.0   |
| Enum/set additions                   | 8.0.0   |
| Rename table                         | 8.0.0   |

Rails 7.2 doesn't auto-emit INSTANT; use `execute`:

```ruby
execute "ALTER TABLE orders ADD COLUMN notes TEXT, ALGORITHM=INSTANT, LOCK=NONE"
```

### Invisible indexes (MySQL 8.0)

Soft-drop to verify nothing breaks before dropping:

```ruby
execute "ALTER TABLE orders ALTER INDEX idx_orders_legacy INVISIBLE"
# Soak; monitor query plans
remove_index :orders, name: "idx_orders_legacy"
```

### Adding a NOT NULL column

MySQL 8.0.12+ INSTANT-eligible when appended with default:

```ruby
execute "ALTER TABLE users ADD COLUMN tier VARCHAR(20) NOT NULL DEFAULT 'standard', ALGORITHM=INSTANT, LOCK=NONE"
```

Otherwise three-step (any version):

```ruby
add_column :orders, :status, :string, default: "pending"                    # 1. nullable + default
Order.in_batches(of: 10_000) { |b| b.where(status: nil).update_all(...) }   # 2. backfill (rake)
change_column_null :orders, :status, false                                  # 3. enforce
```

Tables >100M rows: don't `change_column_null` directly. Keep nullable + model validation, or use `gh-ost`.

### CHECK constraints (8.0.16+)

Validated on creation - no `validate: false`. Large tables: maintenance window or `gh-ost --alter`.

```ruby
add_check_constraint :orders, "total >= 0", name: "orders_total_non_negative"
```

### Functional indexes

MySQL has no partial indexes (`where:`). Functional index is the closest analogue (double parens required):

```ruby
add_index :users, "((LOWER(email)))", name: "idx_users_email_lower"
add_index :users, "(JSON_VALUE(metadata, '$.tier' RETURNING CHAR(50)))", name: "idx_users_tier"
```

### Renaming columns (four steps)

```ruby
add_column :orders, :amount, :decimal, precision: 10, scale: 2          # 1
Order.in_batches { |b| b.update_all("amount = total") }                 # 2
# self.ignored_columns += ["total"] ; deploy                            # 3
safety_assured { remove_column :orders, :total, :decimal }              # 4 next deploy
```

### Dropping columns (two deploys + audit)

Drops are final. Three phases.

**Phase 1 - Pre-flight audit.** Grep every reference:

```bash
rg -n "legacy_field" app/ lib/ config/ spec/ db/ \
  -g '*.{rb,erb,haml,slim,sql}' -g '!*.lock'
```

Also check: BI dashboards, ETL pipelines, materialized views, triggers, replicas with custom subscribers. Drop dependent FK / index / generated column / CHECK / views in a *prior* migration - `strong_migrations` catches most.

**Phase 2 - Prep (only if NOT NULL with no DB default AND app writes on every insert).** Once deploy A stops writing, the next insert fails. Both are metadata-only on MySQL 8.0:

- `change_column_default :users, :legacy_field, from: nil, to: "guest"`
- `change_column_null :users, :legacy_field, true`

**Phase 3 - Two deploys.**

```ruby
# Deploy A: model only
class User < ApplicationRecord
  self.ignored_columns += ["legacy_field"]
end
# Remove read/write refs. Wait for full rollout - Sidekiq fleets lag web.

# Deploy B: migration + remove ignored_columns in one PR
safety_assured do
  remove_column :users, :legacy_field, :string, null: false, default: "guest"
end
```

Restate type/null/default on `remove_column` so `db:rollback` re-adds the column. `DROP COLUMN` is INSTANT-eligible on 8.0.29+.

Edge cases requiring extra steps: dependent objects (FK / index / generated / CHECK / view), external systems consuming the column, tables >100M rows (use `gh-ost --alter="DROP COLUMN ..."`).

### Creating tables

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

`utf8mb4` (not `utf8`) is required for 4-byte sequences (emoji, supplementary CJK). Set collation explicitly so `db:schema:load` is reproducible.

### Large tables (>100M rows): `gh-ost`

Rails migrations don't throttle on replication lag, disk, or master CPU. `gh-ost` does:

```bash
gh-ost --user=app --host=primary.db --database=app --table=orders \
  --alter="ADD COLUMN amount DECIMAL(10,2) NOT NULL DEFAULT 0" \
  --max-load=Threads_running=25 --critical-load=Threads_running=100 \
  --max-lag-millis=1500 --execute
```

Alternative: `pt-online-schema-change` (trigger-based, slower, more topologies). Data backfills: see `rails-batch-processing-patterns`.

### Foreign keys

MySQL validates FKs on creation; brief metadata lock. Very large tables: `gh-ost --alter="ADD CONSTRAINT ..."`.

### Lock timeout per migration

```ruby
def change
  execute "SET SESSION innodb_lock_wait_timeout = 5"
  add_index :orders, :status, algorithm: :inplace
end
```

### Advisory lock for backfills

Guard against double-runs (deploy retry, two engineers). Full leader-election patterns: `rails-db-locking-patterns`.

```ruby
def up
  ApplicationRecord.with_advisory_lock("backfill_order_amount", timeout_seconds: 0) do
    Order.in_batches(of: 10_000) { |b| b.where(amount: nil).update_all(amount: ...) }
  end || abort("another backfill_order_amount is running")
end
```

### Rollback safety

Test `db:migrate && db:rollback && db:migrate` in CI. INSTANT DDL is sometimes irreversible on 8.0.29+ (instant-add metadata; rollback may require a table rebuild). Test rollback on a clone before merging.

```ruby
def change
  reversible do |dir|
    dir.up   { execute "ALTER TABLE orders ADD COLUMN notes TEXT, ALGORITHM=INSTANT" }
    dir.down { execute "ALTER TABLE orders DROP COLUMN notes, ALGORITHM=INSTANT" }
  end
end
```

### MariaDB caveats

- INSTANT not until 10.3+; narrower coverage
- CHECK syntax differs
- No invisible indexes
- For divergence, prefer `pt-online-schema-change`

## Output Format

```
Migration: {file name}
Operation: {Create Table | Add Column | Add Index | Add FK | Backfill | Remove Column}
Table: {name}
Adapter: MySQL {version}
Algorithm: {INSTANT | INPLACE | COPY | gh-ost | pt-online-schema-change}
Lock window: {none (online) | brief MDL | maintenance required}
Safety: {Zero-Downtime | Maintenance Window | Batched Backfill}
Notes: {charset/collation, INSTANT eligibility, gh-ost throttle config}
```

## Avoid

- `algorithm: :concurrently` on MySQL (PG-only)
- `where:` partial indexes on MySQL
- Data changes in schema migrations
- `remove_column` without `ignored_columns` first
- Direct column type changes - use add/backfill/remove
- Irreversible migrations without explicit `raise ActiveRecord::IrreversibleMigration`
- Missing indexes on FK columns
- `add_column` with `null: false` on existing tables without default
- `change_column_null` on hot multi-100M-row tables
- Default `utf8` instead of `utf8mb4`
- `:ruby` schema format on MySQL with functional indexes / generated columns / CHECK
- In-process migrations on >100M-row tables
