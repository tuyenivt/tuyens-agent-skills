---
name: rails-postgresql-migration-safety
description: Zero-downtime Rails/PostgreSQL migrations: CONCURRENTLY, NOT VALID + VALIDATE, pg_advisory_lock, lock_timeout, large tables.
metadata:
  category: backend
  tags: [ruby, rails, postgresql, migration, zero-downtime]
user-invocable: false
---

> Load `Use skill: stack-detect` first. Use when `Database: PostgreSQL`; on `Database: unknown` read `config/database.yml` `adapter:` before choosing. For MySQL/MariaDB, see `rails-migration-safety` (sibling - load that instead, never both).

## When to Use

- Creating or modifying tables, columns, indexes on PostgreSQL
- Adding NOT NULL or renaming/removing columns on deployed tables
- Backfilling >100K rows
- Adding foreign keys without downtime
- Partial indexes on status / enum columns
- Reviewing PG migrations before merge

## Rules

- One structural change per migration; reversible.
- Data backfills in rake tasks, not `db/migrate/`.
- New tables include `timestamps` and indexes on FK + filter columns.
- `disable_ddl_transaction!` for all `CONCURRENTLY` operations.
- `ignored_columns` ships in a deploy before `remove_column`.
- `safety_assured` only after verifying the operation is safe.

## Patterns

### `strong_migrations` + concurrent index

Thresholds used throughout: `CONCURRENTLY` for any table >100K rows (cheap insurance below that too); the NOT VALID + VALIDATE constraint path for >1M rows.

```ruby
class AddIndexToOrdersStatus < ActiveRecord::Migration[7.2]
  disable_ddl_transaction!
  def change
    add_index :orders, :status, algorithm: :concurrently
  end
end
```

### `add_reference` on existing tables

`add_reference :events, :account, foreign_key: true, index: true` bundles three locking operations. Decompose:

```ruby
add_column :events, :account_id, :bigint                          # 1. metadata-only
add_index  :events, :account_id, algorithm: :concurrently         # 2. own migration, disable_ddl_transaction!
add_foreign_key :events, :accounts, validate: false               # 3. then validate_foreign_key
```

### Adding a NOT NULL column

Since PG 11 a default supplied at `ADD COLUMN` is stored as metadata (`pg_attribute.attmissingval`) and every existing row reads it immediately - no rewrite, and nothing left to backfill. So the one-liner is the whole job:

```ruby
add_column :orders, :status, :string, default: "pending", null: false   # metadata-only
```

The add / backfill / enforce sequence is for a column added *without* a default, where existing rows really are NULL:

```ruby
add_column :orders, :status, :string                                                      # 1. nullable
Order.in_batches(of: 10_000) { |b| b.where(status: nil).update_all(status: "pending") }   # 2. backfill (rake)
change_column_null :orders, :status, false                                                # 3. enforce
```

**Large tables (>1M rows): NOT VALID + VALIDATE.** Direct `change_column_null` scans the whole table holding `ACCESS EXCLUSIVE`. NOT VALID validates new rows immediately and lets existing rows validate without blocking writes - so the app must already write the column on every insert *before* the NOT VALID constraint ships, and existing NULL rows must be audited/backfilled before `VALIDATE` (it fails on the first NULL). Rows whose correct value is unrecoverable are deleted or parked on a sentinel row by an explicit decision recorded in the Coordination block.

```ruby
# Migration 1
add_check_constraint :orders, "status IS NOT NULL", name: "orders_status_null", validate: false

# Migration 2
disable_ddl_transaction!
def change
  validate_check_constraint :orders, name: "orders_status_null"
end
```

PG 12+: with a validated CHECK in place, `change_column_null` reuses it and becomes metadata-only; drop the now-redundant CHECK afterwards. Sequencing for new columns: deploy the app writing the column on every insert *before* enforcing NOT NULL, or the constraint fails on fresh rows. Cross-table backfills batch the same way - `b.update_all("col = (SELECT ... FROM other WHERE ...)")` or join via `UPDATE ... FROM` per batch.

### Partial indexes

```ruby
add_index :orders, :fulfilled_at, where: "fulfilled_at IS NOT NULL",
          algorithm: :concurrently, name: "idx_orders_fulfilled"

add_index :orders, :status, where: "status IN ('pending', 'confirmed', 'processing')",
          algorithm: :concurrently, name: "idx_orders_active_status"
```

### Renaming columns (five-step copy)

`RENAME COLUMN` is metadata-only on PG but breaks rolling deploys (old code still reads/writes the old name) and every external reader. Use it only with a coordinated cutover; default to the five-step copy:

```ruby
add_column :orders, :amount, :decimal, precision: 10, scale: 2 # 1
# Deploy dual-writes (model writes both columns) BEFORE the    # 2
# backfill - rows inserted mid-backfill otherwise keep NULL
Order.in_batches { |b| b.update_all("amount = total") }        # 3 backfill (rake)
# Cut reads to :amount; self.ignored_columns += ["total"]      # 4 deploy
safety_assured { remove_column :orders, :total, :decimal }     # 5
```

### Dropping columns (two deploys + audit)

Drops are final. Three phases.

**Phase 1 - Audit.** Grep every reference:

```bash
rg -n "legacy_field" app/ lib/ config/ spec/ db/ -g '*.{rb,rake,erb,haml,slim,jbuilder,yml,sql}'
```

Also check: BI dashboards, ETL pipelines, materialized views, PG functions, triggers, logical-replication subscribers, FDW foreign tables. External readers you can't migrate yourself (Looker, Metabase): hand the owning team a deadline and verify the cutover before Deploy B. Drop-or-recreate dependent FK / index / generated / CHECK / **views** in a *prior* migration (recreating a view without the column is one transaction - no read gap). strong_migrations performs no dependency inspection at all here - its `remove_column` check is about `ignored_columns`. What actually protects you is PostgreSQL: `DROP COLUMN` silently auto-drops the table's *own* indexes and constraints, and errors without CASCADE on anything outside the table that depends on the column - inbound foreign-key references first, plus views, rules, column-list triggers (`UPDATE OF col`) and PG 15+ publication column lists, along with dependent generated columns ("cannot drop column ... because other objects depend on it"). That is precisely why the view case needs `pg_depend`: 

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

**Phase 2 - Prep (only if NOT NULL with no DB default AND app writes on every insert).** Once deploy A stops writing, next insert fails - so ship one of these *before* Deploy A (either suffices; `from: nil` here means "no previous default"; any inert sentinel works). Both are catalog-only on every supported PostgreSQL (a brief `ACCESS EXCLUSIVE`, no scan, no rewrite - `SET DEFAULT` and `DROP NOT NULL` have never rewritten a table; PG 11 changed `ADD COLUMN ... DEFAULT`, not these):

- `change_column_default :users, :legacy_field, from: nil, to: "guest"`
- `change_column_null :users, :legacy_field, true`

**Phase 3 - Two deploys.**

```ruby
# Deploy A: model only
class User < ApplicationRecord
  self.ignored_columns += ["legacy_field"]
end
# Remove read/write refs. Wait for full rollout - Sidekiq fleets lag web.
# Soak before Deploy B: no errors referencing the column, external cutovers verified.

# Deploy B: migration. Drop the ignored_columns line in the deploy after it - a pod that
# boots without it before the migration runs caches the column and INSERTs name it.
safety_assured do
  remove_column :users, :legacy_field, :string, null: true   # restate the column as it exists now:
end                                                          # null: true after change_column_null, default: "guest" after change_column_default
```

Restate type/null/default as they exist *at drop time* (whichever Phase-2 option ran) so `db:rollback` recreates that state. `DROP COLUMN` is metadata-only in PG (no rewrite) - which is also why it reclaims nothing: the values stay inside existing heap tuples and plain autovacuum never rewrites a live tuple. Space comes back only through a rewrite (`pg_repack`, `VACUUM FULL`, `CLUSTER`) or natural row churn.

Edge cases requiring extra steps: dependent objects (FK / index / generated / CHECK / view via `pg_depend`), external systems (BI / ETL / logical replication / FDW), >100M-row tables where space reclamation is urgent (`pg_repack`).

### Creating tables

```ruby
create_table :orders do |t|
  t.references :user, null: false, foreign_key: true
  t.integer :total_cents, null: false  # money as integer cents; decimal only to match an existing convention
  t.integer :status, null: false, default: 0
  t.datetime :fulfilled_at
  t.timestamps
end
add_index :orders, [:user_id, :status]
```

### Foreign keys without table lock

These are two migrations, not one. `ADD CONSTRAINT ... NOT VALID` takes a `SHARE ROW EXCLUSIVE` lock on both tables; run it in the same DDL transaction as the validation and that lock is held for the whole scan - exactly what the split is meant to avoid.

```ruby
# Migration 1
add_foreign_key :orders, :users, validate: false  # fast, but locks both tables briefly

# Migration 2 (separate file, separate deploy)
validate_foreign_key :orders, :users              # no write lock; sequential scan
```

Fix orphans if validation fails, then rerun.

### Large tables (>1M rows)

```ruby
Order.in_batches(of: 10_000) do |batch|
  batch.update_all(processed: true)
  sleep(0.1)
end
```

See `rails-batch-processing-patterns` for chunked-transaction shape, idempotency, memory safety.

### Lock and statement timeouts

```ruby
class AddIndexToOrdersStatus < ActiveRecord::Migration[7.2]
  disable_ddl_transaction!
  def change
    reversible do |dir|   # a bare `execute` has no inverse and would make the migration irreversible
      dir.up   { execute "SET lock_timeout = '5s'" }
      dir.down { execute "SET lock_timeout = '5s'" }
    end
    add_index :orders, :status, algorithm: :concurrently
  end
end
```

Or globally: `StrongMigrations.lock_timeout = 5.seconds`.

For long backfills, also bound each batch:

```ruby
Order.in_batches(of: 10_000) do |batch|
  ActiveRecord::Base.transaction do                              # SET LOCAL needs a transaction
    ActiveRecord::Base.connection.execute("SET LOCAL statement_timeout = '30s'")
    batch.update_all(processed: true)
  end
end
```

Outside a transaction block each `execute` autocommits on its own, so PostgreSQL emits `WARNING: SET LOCAL can only be used in transaction blocks` and the following `update_all` runs with the session default - the bound silently never applies. Session-level `SET statement_timeout` once before the loop is the other valid shape.

### `change_column_default`

`SET DEFAULT` is catalog-only on every supported version - a brief `ACCESS EXCLUSIVE`, no scan, no rewrite. (PG 11 changed `ADD COLUMN ... DEFAULT`, not this.) Avoid `change_column`, which combines type+default+null: a real type change rewrites every row, `SET NOT NULL` scans the table under `ACCESS EXCLUSIVE`, and strong_migrations blocks the unsafe type changes:

```ruby
change_column_default :orders, :status, from: nil, to: "pending"
```

### Advisory locks for backfills

Guard against double-runs (deploy retry, two engineers). Full leader-election patterns and `pg_advisory_xact_lock`: `rails-db-locking-patterns`.

```ruby
# In the backfill rake task (never db/migrate):
ApplicationRecord.with_advisory_lock!("backfill_order_amount", timeout_seconds: 0) do
  Order.in_batches(of: 10_000) { |b| b.where(amount: nil).update_all(amount: ...) }
end
# The bang form raises WithAdvisoryLock::FailedToAcquireLock when someone else holds it.
# `with_advisory_lock(...) { } || abort` is a trap: the block returns in_batches' nil on a
# *successful* run, so the abort fires after the backfill completes.
```

### Rollback safety

Test `db:migrate && db:rollback && db:migrate` in CI.

```ruby
def change
  reversible do |dir|
    dir.up   { execute "CREATE EXTENSION IF NOT EXISTS citext" }
    dir.down { execute "DROP EXTENSION IF EXISTS citext" }
  end
end
```

### INVALID index recovery

```sql
SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;
```

Then `DROP INDEX CONCURRENTLY` and rerun. A migration that failed midway and is unrecorded stays editable in place until it has run somewhere; once recorded in any environment - including one that ran correctly - it is never edited: supersede it with a new file.

## Output Format

One block per operation, in execution order - a migration file bundling two operations emits two blocks sharing one `Migration:` value (and a finding against Rule 1); a corrected step that needs its own deploy is `proposed - not yet created`. A multi-step plan emits a numbered sequence (`Step:`); a redundant statement gets `Safety: Reject` with the deletion in `Notes:`. Rake backfills get blocks too, citing the rake file in `Migration:`. Non-DDL sequence steps the patterns require - a dependency audit, an `ignored_columns`-only deploy, an orphan cleanup before a VALIDATE - get a block with `Operation: Coordination` and `Algorithm: n/a`. In review or diagnosis mode, precede the blocks with numbered findings, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. The blocks describe the corrected operations, so target state lives there. This applies to a post-incident review of an already-executed migration as much as to a pre-merge one; for a recovery, the first block is the step that returns the database to a known state.

```
Step: {n of N | n/a (single operation)}

Migration: {file name | rake file path | rake file not provided - name it | proposed - not yet created | n/a (DBA command, decision or deploy-only step)}

Operation: {Create Table | Add Column | Change Column | Rename Column (coordinated cutover only) | Add Index | Drop Index | Add FK | Add CHECK (NOT VALID) | Validate Constraint | Drop Constraint | Backfill | Remove Column | Drop/Recreate View | Maintenance (pg_repack / VACUUM FULL / CREATE EXTENSION) | Coordination}

Table: {name} ({row count | new - 0 rows | "size unstated - assume large and justify"}) | n/a (multi-table or no table)

Adapter: PostgreSQL {x.y from SELECT version() or the declared ## Tech Stack | unknown - assume the oldest supported major}

Algorithm: {standard | CONCURRENTLY | NOT VALID + VALIDATE | batched rake | batched update inside a migration - GAP | n/a}

Lock window: {none | brief lock | full-table scan under ACCESS EXCLUSIVE (SET NOT NULL, VALIDATE run in-transaction) | long non-blocking lock (CONCURRENTLY / VALIDATE hold SHARE UPDATE EXCLUSIVE for the duration) | requires maintenance | n/a (Coordination, Backfill)}

Safety: {Zero-Downtime | Maintenance Window | Batched Backfill | Hardening advised - compliant but under-specified | Blocked - dependency absent, name it | Reject - rewrite required | Already applied - unsafe as run, findings say what changes | n/a (Coordination)}

Notes: {partial-index conditions, validate: false, disable_ddl_transaction! present, reversibility (db:rollback verified | raises IrreversibleMigration), etc.}
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
- `change_column` when only the default is changing - emits a same-type `ALTER TYPE` (an `ACCESS EXCLUSIVE` lock, possibly an index rebuild) for a catalog-only change
