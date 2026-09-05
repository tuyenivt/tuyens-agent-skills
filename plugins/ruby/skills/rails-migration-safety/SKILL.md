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
- `schema_format = :sql` - `:ruby` loses views, triggers, stored procedures, partitioning, and expression-index fidelity. (Rails 7.2 does dump charset/collation, `t.virtual` generated columns and `t.check_constraint`, so those are no longer the argument.)
- `ignored_columns` ships in a deploy before `remove_column`.
- `safety_assured` only after verifying the operation is safe for the table size.
- Tables >100M rows: any rebuild (COPY or INPLACE) goes through `gh-ost` / `pt-online-schema-change`, never in-process - INPLACE may be online on the primary but replicates as one serialized DDL and stalls replicas. INSTANT (metadata-only) operations are exempt at any size.

## Patterns

### `strong_migrations`

```ruby
# config/initializers/strong_migrations.rb
StrongMigrations.lock_timeout      = 5.seconds
# On MySQL this emits max_execution_time, which applies to SELECTs only - it bounds
# neither the ALTER nor a backfill UPDATE. lock_wait_timeout is the real DDL guard.
StrongMigrations.statement_timeout = 1.hour
StrongMigrations.target_version    = "8.0.35"  # the real server version - a bare "8.0" sorts
                                               # below 8.0.12/8.0.16 and fails every version gate
```

### Online DDL: INPLACE / LOCK=NONE

Rails does **not** auto-emit `algorithm: :concurrently` (PG-only):

```ruby
# Bad - raises on MySQL
add_index :orders, :status, algorithm: :concurrently

# Good (tables under the gh-ost threshold)
add_index :orders, :status, algorithm: :inplace
# Exact control:
execute "ALTER TABLE orders ADD INDEX idx_orders_status (status), ALGORITHM=INPLACE, LOCK=NONE"
```

`VARCHAR` resizes: widening is INPLACE only while the column stays in the same length-byte class, and that boundary is **255 bytes**, not 255 characters. Under the utf8mb4 this skill mandates, one character is up to 4 bytes, so the 1-byte class ends at 63 characters (63 x 4 = 252) and 64 crosses into 2 bytes (256). `VARCHAR(50) -> VARCHAR(100)` crosses it (200 -> 400 bytes) and forces a COPY rebuild. Compute `chars x charset maxlen <= 255` before assuming INPLACE. Narrowing always forces COPY and risks truncation - treat it as a type change (add/backfill/remove).

### INSTANT DDL (MySQL 8.0)

Metadata-only - finishes in ms even on TB tables.

| Operation                            | Since   |
| ------------------------------------ | ------- |
| Add column (last position)           | 8.0.12  |
| Add column (any position)            | 8.0.29  |
| Drop column                          | 8.0.29  |
| Modify default                       | 8.0.12  |
| Add/drop virtual generated column    | 8.0.12  |
| Enum/set additions                   | 8.0.12  |
| Rename table                         | 8.0.12  |

The server auto-selects INSTANT when the operation is eligible - a plain `add_column` on an eligible operation is already instant. Write `ALGORITHM=INSTANT` explicitly anyway (via `execute`; Rails emits no algorithm clause): an ineligible operation then fails loudly instead of silently degrading to a multi-hour rebuild.

```ruby
execute "ALTER TABLE orders ADD COLUMN notes TEXT, ALGORITHM=INSTANT"
# no LOCK clause: MySQL rejects LOCK=NONE with ALGORITHM=INSTANT
# (ER_ALTER_OPERATION_NOT_SUPPORTED_REASON). Instant ops permit concurrent DML anyway.
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
execute "ALTER TABLE users ADD COLUMN tier VARCHAR(20) NOT NULL DEFAULT 'standard', ALGORITHM=INSTANT"
```

A column added *with* a DEFAULT needs no backfill on any version - MySQL gives every existing row that default as part of the ADD (instantly on 8.0.12+, during the rebuild before that), so a `where(status: nil)` pass would match nothing. The three-step sequence is for a column added *without* one, where existing rows really are NULL:

```ruby
add_column :orders, :status, :string                                        # 1. nullable, no default
Order.in_batches(of: 10_000) { |b| b.where(status: nil).update_all(...) }   # 2. backfill (rake)
change_column_null :orders, :status, false                                  # 3. enforce
```

Tables >100M rows: don't `change_column_null` directly. Keep nullable + model validation, or use `gh-ost`.

### CHECK constraints (8.0.16+)

Validated on creation - no `validate: false`. Large tables: maintenance window or `gh-ost --alter`.

```ruby
add_check_constraint :orders, "total >= 0", name: "orders_total_non_negative"
```

### Functional indexes (MySQL 8.0.13+; `JSON_VALUE` 8.0.21+)

MySQL has no partial indexes (`where:`). Functional index is the closest analogue (double parens required). Not available on MariaDB at any version - index a virtual generated column there instead:

```ruby
add_index :users, "((LOWER(email)))", name: "idx_users_email_lower"
add_index :users, "(JSON_VALUE(metadata, '$.tier' RETURNING CHAR(50)))", name: "idx_users_tier"
```

### Renaming columns (five-step copy)

`RENAME COLUMN` is INPLACE and metadata-only - no rebuild, concurrent DML allowed while the type is unchanged. MySQL has never supported `ALGORITHM=INSTANT` for a rename, in any 8.0.x. It is cheap at the storage layer and still wrong here, because it breaks rolling deploys (old code reads and writes the old name) and every external reader. Use it only with a coordinated cutover; default to the five-step copy:

```ruby
add_column :orders, :amount, :decimal, precision: 10, scale: 2          # 1
# Deploy dual-writes (model writes both columns) BEFORE the backfill -  # 2
# rows inserted mid-backfill otherwise keep NULL in the new column
Order.in_batches { |b| b.update_all("amount = total") }                 # 3 backfill (rake)
# Cut reads to :amount; self.ignored_columns += ["total"] ; deploy      # 4
safety_assured { remove_column :orders, :total, :decimal, precision: 10, scale: 2 }  # 5 next deploy
```

### Dropping columns (two deploys + audit)

Drops are final. Three phases.

**Phase 1 - Pre-flight audit.** Grep every reference:

```bash
rg -n "legacy_field" app/ lib/ config/ spec/ db/ \
  -g '*.{rb,erb,haml,slim,sql}' -g '!*.lock'
```

Find DB-side view dependencies (MySQL has no `pg_depend`):

```sql
SELECT TABLE_NAME FROM information_schema.VIEWS WHERE VIEW_DEFINITION LIKE '%legacy_field%';
```

Also check: BI dashboards, ETL pipelines, triggers, replicas with custom subscribers. External readers you can't migrate yourself (Metabase, Looker): hand the owning team a deadline and verify the cutover before Deploy B - their breakage is your incident. Drop or recreate dependent FK / index / generated column / CHECK / views in a *prior* migration. Nothing catches these for you - strong_migrations does no dependency inspection (its `remove_column` check is only about `ignored_columns`), and MySQL raises at ALTER time. The `information_schema` query above plus `KEY_COLUMN_USAGE`, `CHECK_CONSTRAINTS` and `COLUMNS.GENERATION_EXPRESSION` is the pre-flight audit.

**Phase 2 - Prep (only if NOT NULL with no DB default AND app writes on every insert).** Once deploy A stops writing, the next insert fails - so ship these *before* Deploy A (any inert sentinel works as the default):

- `change_column_default :users, :legacy_field, from: nil, to: "guest"` - INSTANT
- `change_column_null :users, :legacy_field, true` - INPLACE online rebuild (not metadata-only); >100M rows route through gh-ost

**Phase 3 - Two deploys.**

```ruby
# Deploy A: model only
class User < ApplicationRecord
  self.ignored_columns += ["legacy_field"]
end
# Remove read/write refs. Wait for full rollout - Sidekiq fleets lag web.
# Soak before Deploy B: confirm no errors referencing the column and external cutovers done.

# Deploy B: migration + remove ignored_columns in one PR
safety_assured do
  remove_column :users, :legacy_field, :string, null: true, default: "guest"
end
```

Restate type/null/default as they exist *at drop time* (post-Phase-2: nullable) so `db:rollback` re-adds the column in that state. `DROP COLUMN` is INSTANT-eligible on 8.0.29+.

Edge cases requiring extra steps: dependent objects (FK / index / generated / CHECK / view), external systems consuming the column, tables >100M rows (use `gh-ost --alter="DROP COLUMN ..."`).

### Creating tables

```ruby
# utf8mb4_0900_ai_ci is MySQL 8.0 only - MariaDB raises "Unknown collation".
# On MariaDB use utf8mb4_uca1400_ai_ci (10.10+) or utf8mb4_unicode_ci.
create_table :orders, options: "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci" do |t|
  t.references :user, null: false, foreign_key: true
  t.integer :total_cents, null: false  # money as integer cents; decimal only to match an existing convention
  t.integer :status, null: false, default: 0
  t.datetime :fulfilled_at
  t.timestamps
end
add_index :orders, [:user_id, :status]
```

`utf8mb4` (not `utf8`) is required for 4-byte sequences (emoji, supplementary CJK). Set collation explicitly so `db:schema:load` is reproducible.

### Large tables (>100M rows): `gh-ost`

Rails migrations don't throttle at all. `gh-ost` throttles on replication lag (`--max-lag-millis`) and MySQL status variables (`--max-load`, `--critical-load`, e.g. `Threads_running`), with anything else expressible as `--throttle-query` or a `--throttle-flag-file`. It has no disk or CPU metric of its own:

```bash
gh-ost --user=app --host=primary.db --database=app --table=orders \
  --alter="ADD COLUMN amount DECIMAL(10,2) NOT NULL DEFAULT 0" \
  --max-load=Threads_running=25 --critical-load=Threads_running=100 \
  --max-lag-millis=1500 --execute
```

On RDS/managed MySQL (no SUPER): add `--assume-rbr --allow-on-master`. After any out-of-band gh-ost ALTER, regenerate `db/structure.sql` (`db:schema:dump`) so the repo matches production. Alternative: `pt-online-schema-change` (trigger-based, slower, more topologies). Data backfills - including lag-aware throttling and external-API safety in backfill loops: see `rails-batch-processing-patterns` and `rails-rake-task-patterns`.

### Foreign keys

With the default `foreign_key_checks=1`, `ALTER TABLE ... ADD FOREIGN KEY` supports **only ALGORITHM=COPY** - a full table rebuild that blocks writes, not a brief metadata lock. INPLACE becomes available only with `foreign_key_checks=0`, which buys `LOCK=NONE` at the cost of an unvalidated constraint until you re-check it.

On a large table this is *not* gh-ost work: gh-ost does not support foreign keys at all and refuses to run on any table holding an FK as child or parent. Use `pt-online-schema-change --alter-foreign-keys-method=rebuild_constraints` (or `drop_swap`). The same limitation qualifies the ">100M rows -> gh-ost" rule everywhere in this skill: `t.references ... foreign_key: true` is the house convention, so most large tables here are FK-bearing and belong to pt-osc.

### Lock timeout per migration

```ruby
def change
  execute "SET SESSION lock_wait_timeout = 5"   # metadata-lock timeout - what DDL queues on
  add_index :orders, :status, algorithm: :inplace
end
```

`innodb_lock_wait_timeout` bounds InnoDB *row-lock* waits and has no effect on the metadata lock a DDL statement waits for; with only that set, the migration still blocks indefinitely behind a long-running transaction. `lock_wait_timeout` is the MDL knob (default 31536000 - a year), and it is what `StrongMigrations.lock_timeout` emits on MySQL.

### Advisory lock for backfills

Guard against double-runs (deploy retry, two engineers). Full leader-election patterns: `rails-db-locking-patterns`.

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

Test `db:migrate && db:rollback && db:migrate` in CI, and test rollback on a clone before merging. Two INSTANT caveats, in opposite directions: on 8.0.12-8.0.28 an instantly-added column could not be dropped instantly, so the rollback rebuilt the table; from 8.0.29 instant `DROP COLUMN` exists, but every instant ADD/DROP consumes one of a table's **64 row versions** - once exhausted, any `ALGORITHM=INSTANT` fails with "Maximum row versions reached for table" until an INPLACE or COPY rebuild (or `OPTIMIZE TABLE`) resets the count.

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
- Invisible indexes are spelled `ALTER TABLE ... ALTER INDEX idx IGNORED` (MariaDB 10.6+); absent below 10.6
- `utf8mb4_0900_*` collations do not exist
- No functional indexes at any version - index a virtual generated column instead
- For divergence, prefer `pt-online-schema-change`

## Output Format

One block per operation, in execution order - a migration file bundling two operations emits two blocks sharing one `Migration:` value, and a multi-step plan emits a numbered sequence. Rake backfills and gh-ost runs get blocks too (`Operation: Backfill`, `Algorithm: batched rake` / `gh-ost`). Non-DDL sequence steps that the patterns require - a dependency audit, an `ignored_columns`-only deploy, an external-reader cutover - get a block with `Operation: Coordination` and `Algorithm: n/a`. In review mode, precede the blocks with numbered findings, each citing the violated rule; the blocks describe the corrected operations, so target state lives there. This applies to a post-incident review of an already-executed migration as much as to a pre-merge one.

```
Migration: {file name | rake file path | proposed - not yet created | n/a (out-of-band gh-ost run)}

Operation: {Create Table | Add Column | Change Column | Add Index | Drop Index | Add FK | Add CHECK | Backfill | Remove Column | Drop/Recreate View | Coordination}

Table: {name} ({row count, or "size unstated - assume large and justify"})

Adapter: {MySQL | MariaDB} {x.y.z from SELECT VERSION() or the declared ## Tech Stack | unknown - assume no INSTANT support}

Algorithm: {INSTANT | INPLACE | COPY | gh-ost | pt-online-schema-change | batched rake | n/a}

Lock window: {none (online) | brief metadata lock | maintenance required}

Safety: {Zero-Downtime | Maintenance Window | Batched Backfill | Hardening advised - compliant but under-specified | Blocked - required tooling absent, name it | Reject - rewrite required}

Notes: {charset/collation, INSTANT eligibility, gh-ost throttle config}
```

`Adapter` version drives every INSTANT gate above, and `stack-detect` never supplies a patch level - read it from the server or the project's `## Tech Stack`, and when neither exists say `unknown` rather than assuming 8.0.latest. When the >100M-row rule mandates gh-ost/pt-osc and neither is installed, that is `Safety: Blocked`, not a silent downgrade to an in-process ALTER: say which tool is needed and that installing it is a prerequisite of the change.

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
