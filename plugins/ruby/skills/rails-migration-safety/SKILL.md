---
name: rails-migration-safety
description: Zero-downtime Rails/MySQL migrations: 8.0 INSTANT DDL, online INPLACE, invisible indexes, gh-ost for >100M-row tables.
metadata:
  category: backend
  tags: [ruby, rails, mysql, migration, zero-downtime]
user-invocable: false
---

> Load `Use skill: stack-detect` first. Targets MySQL 8.0 (8.0.x); on `Database: unknown` read `config/database.yml` `adapter:` (`mysql2` or `trilogy`).

## When to Use

- Creating or modifying tables, columns, indexes on MySQL
- Adding NOT NULL, renaming, or removing columns on deployed tables
- Backfilling >100K rows
- Adding foreign keys without downtime
- Choosing between in-process migration, `gh-ost`, `pt-online-schema-change`
- Reviewing migrations for production safety before merge

## Rules

- One structural change per migration; reversible.
- Data backfills live in rake tasks, not `db/migrate/` (see `rails-rake-task-patterns`).
- New tables include `timestamps` and indexes on FK + filter columns.
- `schema_format = :sql` when the schema holds anything `:ruby` loses - views, triggers, stored procedures, partitioning, a FULLTEXT index's `WITH PARSER ngram`; `:ruby` with none of those is compliant; `schema_format` is per database in `database.yml` (8.1), so the queue / cache / cable databases stay `:ruby` while the primary is `:sql`. (Rails does dump charset/collation, `t.virtual` generated columns, `t.check_constraint` and functional indexes, so those are no longer the argument.)
- `ignored_columns` ships in a deploy before `remove_column`.
- `safety_assured` only after verifying the operation is safe for the table size; strong_migrations raises on every bare `execute` (and on `add_check_constraint` on MySQL), so the DDL strings below carry it.
- Tables >100M rows: any operation that scans or rebuilds the table (COPY, an INPLACE rebuild, an INPLACE secondary-index build) goes through `gh-ost` / `pt-online-schema-change`, never in-process - INPLACE may be online on the primary but replicates as one serialized DDL and stalls replicas (the stall scales with table size; the threshold is where in-process becomes unacceptable, not where it starts). INSTANT and INPLACE metadata-only operations are exempt at any size.

## Patterns

### `strong_migrations`

```ruby
# config/initializers/strong_migrations.rb
StrongMigrations.lock_timeout      = 5.seconds   # emits lock_wait_timeout - the metadata-lock guard DDL queues on
# statement_timeout emits max_execution_time, which applies to SELECTs only - it bounds
# neither the ALTER nor a backfill UPDATE.
StrongMigrations.statement_timeout = 1.hour
StrongMigrations.target_version    = "8.0.46"  # the production server version, read only in development and test
                                               # (developer_env?); on MySQL it feeds only the >= 8.0 checks
```

### Online DDL: INPLACE / LOCK=NONE

`add_index`'s `algorithm:` takes MySQL's `ALGORITHM` values (`:inplace`, `:copy`, `:instant`, `:default` - MySQL then rejects INSTANT for ADD INDEX); anything else raises:

```ruby
# Bad - raises ArgumentError on the MySQL adapter
add_index :orders, :status, algorithm: :concurrently

# Good (tables under the gh-ost threshold)
add_index :orders, :status, algorithm: :inplace
# Exact control:
safety_assured { execute "ALTER TABLE orders ADD INDEX idx_orders_status (status), ALGORITHM=INPLACE, LOCK=NONE" }
```

`VARCHAR` resizes: widening is INPLACE only while the column stays in the same length-byte class, and that boundary is **255 bytes**, not 255 characters. Under the utf8mb4 this skill mandates, one character is up to 4 bytes, so the 1-byte class ends at 63 characters (63 x 4 = 252) and 64 crosses into 2 bytes (256). `VARCHAR(50) -> VARCHAR(100)` crosses it (200 -> 400 bytes) and forces a COPY rebuild. Compute `chars x charset maxlen <= 255` before assuming INPLACE. Narrowing always forces COPY and risks truncation - treat it as a type change (add/backfill/remove). A COPY blocks writes for its whole run: below ~100K rows that is seconds (`Lock window: write-blocking rebuild`, `Safety: Hardening advised`, not `Reject`); from there up to the 100M-row rule it is `Safety: Maintenance Window`, or gh-ost / pt-osc.

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
| Rename column                        | 8.0.28  |

The server auto-selects INSTANT when the operation is eligible - a plain `add_column` on an eligible operation is already instant. On a table at or near the gh-ost threshold (80M rows and up), write `ALGORITHM=INSTANT` explicitly (via `execute`; Rails emits no algorithm clause): an ineligible operation then fails loudly instead of silently degrading to a multi-hour rebuild. The helper examples below rely on the server picking INSTANT. INSTANT ADD COLUMN is unavailable on a table with a FULLTEXT index, a `ROW_FORMAT=COMPRESSED` table, or one out of row versions - there the ADD is a rebuild. An expression default on ADD COLUMN (`DEFAULT (CURRENT_DATE)`, `DEFAULT (JSON_ARRAY())`) is COPY only - neither INSTANT nor INPLACE accepts it (8.0.46) - while the literal `DEFAULT CURRENT_TIMESTAMP` stays INSTANT, as does `ALTER COLUMN ... SET DEFAULT (expr)` on an existing column.

```ruby
safety_assured { execute "ALTER TABLE orders ADD COLUMN notes TEXT, ALGORITHM=INSTANT" }
# no LOCK clause: MySQL rejects LOCK=NONE/SHARED/EXCLUSIVE with ALGORITHM=INSTANT (ER_WRONG_USAGE 1221); only LOCK=DEFAULT passes.
# Instant ops permit concurrent DML anyway.
```

### Invisible indexes (MySQL 8.0)

Soft-drop to verify nothing breaks before dropping (8.1 migration methods; metadata-only, no rebuild):

```ruby
disable_index :orders, :index_orders_on_legacy_ref   # by index name; ALTER INDEX ... INVISIBLE - enable_index :orders, :index_orders_on_legacy_ref reverses it
# Soak a full business cycle; monitor query plans
remove_index :orders, :legacy_ref   # pass the column(s), not only name:, so change can reverse it
```

The reverse soak creates an index invisible first - `add_index :orders, :placed_at, enabled: false` (`t.index ..., enabled: false` inside `create_table`), `enable_index` once `EXPLAIN` on the target query confirms the plan - so a plan regression is undone with one metadata flip instead of a rebuild. `schema.rb` records `enabled: false`.

### Adding a NOT NULL column

MySQL 8.0.12+ INSTANT-eligible when appended with a literal default (an expression default is COPY - see INSTANT DDL above):

```ruby
safety_assured { execute "ALTER TABLE users ADD COLUMN tier VARCHAR(20) NOT NULL DEFAULT 'standard', ALGORITHM=INSTANT" }
```

A column added *with* a DEFAULT needs no backfill on any version - MySQL gives every existing row that default as part of the ADD (instantly on 8.0.12+ for a literal default; during an INPLACE rebuild before 8.0.12; during a COPY rebuild for an expression default), so a `where(status: nil)` pass would match nothing. The three-step sequence is for a column added *without* one, where existing rows really are NULL:

```ruby
add_column :orders, :status, :string                                                   # 1. nullable, no default
Order.in_batches(of: 10_000) { |b| b.where(status: nil).update_all(status: "pending") }   # 2. backfill (rake)
change_column_null :orders, :status, false                                             # 3. enforce
```

Tables >100M rows: don't `change_column_null` directly. Keep nullable + model validation, or use `gh-ost`.

### CHECK constraints (8.0.16+)

Validated on creation - no `validate: false` - and `ADD CHECK CONSTRAINT` is a COPY rebuild on MySQL 8.0 (INPLACE is refused, ER 1845), sized like the VARCHAR COPY rule above; existing violating rows fail the ALTER: count them first (`SELECT COUNT(*) FROM orders WHERE NOT (total >= 0)`). Large tables: maintenance window or `gh-ost --alter` (pt-osc when FK-bearing) - and there the count must be 0 *before* the run, because both tools copy rows with `INSERT ... IGNORE`, under which MySQL turns a CHECK (or FK) violation into a warning and silently leaves the row out of the new table.

```ruby
safety_assured { add_check_constraint :orders, "total >= 0", name: "orders_total_non_negative" }   # strong_migrations raises on it for MySQL
```

### Functional indexes (MySQL 8.0.13+; `JSON_VALUE` 8.0.21+)

MySQL has no partial indexes (`where:`). Functional index is the closest analogue - MySQL wants `((expr))` and Rails adds the outer pair, so the String carries one. A B-tree on TEXT/BLOB needs a prefix (`length: { notes: 100 }` - sized to the selectivity you need, within InnoDB's 3072-byte key limit, 768 utf8mb4 characters) or a generated column - MySQL rejects a bare one. Searching words in a TEXT column is a FULLTEXT index instead: `ADD FULLTEXT` is INPLACE but permits no concurrent writes (`LOCK=SHARED`), and a table's first FULLTEXT index also rebuilds it (adding the hidden `FTS_DOC_ID`), so on a large table it is a maintenance window or pt-osc:

```ruby
add_index :users, "(LOWER(email))", name: "idx_users_email_lower"
add_index :users, "(JSON_VALUE(metadata, '$.tier' RETURNING CHAR(50)))", name: "idx_users_tier"
```

### Renaming columns (five-step copy)

`RENAME COLUMN` is metadata-only while the type is unchanged - INSTANT from 8.0.28, INPLACE with concurrent DML before. It is cheap at the storage layer and still wrong here, because it breaks rolling deploys (old code reads and writes the old name) and every external reader. Use it only with a coordinated cutover; default to the five-step copy. The same shape carries a type change (`decimal` to integer cents): the backfill does the conversion.

```ruby
add_column :orders, :amount_cents, :bigint                              # 1
# Deploy dual-writes (model writes both columns) BEFORE the backfill -  # 2
# rows inserted mid-backfill otherwise keep NULL in the new column
Order.in_batches { |b| b.update_all("amount_cents = ROUND(total * 100)") }   # 3 backfill (rake)
# Cut reads to :amount_cents; self.ignored_columns += ["total"]; deploy # 4
safety_assured { remove_column :orders, :total, :decimal, precision: 10, scale: 2 }  # 5 next deploy
```

### Dropping columns (two deploys + audit)

Drops are final. Three phases.

**Phase 1 - Pre-flight audit.** Grep every reference:

```bash
rg -n "legacy_field" app/ lib/ config/ spec/ db/ \
  -g '*.{rb,rake,erb,haml,slim,jbuilder,yml,sql}'
```

Find DB-side view dependencies (MySQL tracks them per table only - `VIEW_TABLE_USAGE`, 8.0.13+ - not per column, so search the view definitions):

```sql
SELECT TABLE_NAME FROM information_schema.VIEWS WHERE VIEW_DEFINITION LIKE '%legacy_field%';
```

Also check: BI dashboards, ETL pipelines, triggers, binlog/CDC consumers (Debezium, DMS). External readers you can't migrate yourself (Metabase, Looker): hand the owning team a deadline and verify the cutover before Deploy B - their breakage is your incident. Drop or recreate dependent FK / index / generated column / CHECK / views in a *prior* migration. Nothing catches these for you - strong_migrations does no dependency inspection (its `remove_column` check is only about `ignored_columns`), and MySQL raises at ALTER time only for FKs, generated columns, functional indexes and multi-column CHECK constraints (a CHECK on the dropped column alone is dropped silently): a dependent view is not checked (the drop succeeds, the view fails at query time), and a plain index containing the column is narrowed - or dropped when it was the only key part - so a composite UNIQUE silently becomes stricter, or fails with ER_DUP_ENTRY 1062 when the remaining columns hold duplicates. The `information_schema` query above plus `KEY_COLUMN_USAGE`, `STATISTICS` (`COLUMN_NAME`, and `EXPRESSION` for functional key parts), `CHECK_CONSTRAINTS` and `COLUMNS.GENERATION_EXPRESSION` is the pre-flight audit.

**Phase 2 - Prep (only if NOT NULL with no DB default AND app writes on every insert).** Once deploy A stops writing, the next insert fails - so ship one of these *before* Deploy A (either suffices; the default is INSTANT and the usual choice, any inert sentinel works):

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

# Deploy B: migration. Drop the ignored_columns line in the deploy after it - a pod that
# boots without it before the migration runs caches the column and INSERTs name it.
safety_assured do
  remove_column :users, :legacy_field, :string, null: true   # restate the column as it exists now:
end                                                          # null: true after change_column_null, default: "guest" after change_column_default
```

Restate type/null/default as they exist *at drop time* (whichever Phase-2 option ran) so `db:rollback` re-adds the column in that state. A rename whose target column already exists is a finding, not a migration - reconcile the two columns first. `DROP COLUMN` is INSTANT-eligible on 8.0.29+.

Edge cases requiring extra steps: dependent objects (FK / index / generated / CHECK / view), external systems consuming the column, and a large table where INSTANT drop is unavailable (before 8.0.29, or row versions exhausted) - gh-ost, or pt-osc when the table is FK-bearing.

### Creating tables

```ruby
create_table :orders, options: "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci" do |t|
  t.references :user, null: false, foreign_key: true, index: false   # the composite below leads with user_id
  t.integer :total_cents, null: false  # money as integer cents; decimal only to match an existing convention
  t.integer :status, null: false, default: 0
  t.datetime :fulfilled_at
  t.timestamps
end
add_index :orders, [:user_id, :status]
```

`utf8mb4` (not `utf8`) is required for 4-byte sequences (emoji, supplementary CJK). Set collation explicitly so `db:schema:load` is reproducible; `utf8mb4_0900_ai_ci` is accent- and case-insensitive, so a unique index on `users.email` under it already rejects `A@x` next to `a@x` - normalise in the model (`normalizes :email`) rather than switching to a `_bin` collation. A new table's block reads `Algorithm: n/a` and `Lock window: none (online)` - there is no existing data to rebuild, and an FK to a populated parent adds only a brief metadata lock on the parent. Framework tables that arrive as a migration (`bin/rails active_storage:install`) get a block per table with `Migration: generated - <generator>`, reviewed for charset and the polymorphic index only; `solid_queue:install` writes `db/queue_schema.rb` for a separate database, loaded by `db:prepare`, with no migration to review. `StrongMigrations.target_version` set to the production server version is a `[Recommend]` finding when absent or wrong - it makes development checks mirror production (on MySQL it feeds only the >= 8.0 checks) - and a Gemfile without `strong_migrations` at all is a `[Recommend]` finding.

### Large tables (>100M rows): `gh-ost`

Rails migrations don't throttle at all. `gh-ost` throttles on replication lag (`--max-lag-millis`) and MySQL status variables (`--max-load`, e.g. `Threads_running`), with anything else expressible as `--throttle-query` or a `--throttle-flag-file`; crossing `--critical-load` aborts the migration rather than throttling it. It has no disk or CPU metric of its own:

```bash
# A real rebuild (a column type change) on a table with no FKs - an appended
# ADD COLUMN is INSTANT and needs no gh-ost at all
gh-ost --user=app --ask-pass --host=primary.db --database=app --table=events \
  --alter="MODIFY COLUMN payload MEDIUMTEXT" \
  --max-load=Threads_running=25 --critical-load=Threads_running=100 \
  --max-lag-millis=1500 --allow-on-master --execute
```

One gh-ost / pt-osc run carries every pending ALTER for the table (a NOT NULL change and its new index together; a table under the threshold keeps in-process INPLACE for each) and takes the lag budget as a flag (`--max-lag-millis` here; on pt-osc `pt-online-schema-change --alter "ADD INDEX idx_events_kind (kind)" --max-lag=1 --check-interval=1 --critical-load Threads_running=100 --execute D=app,t=events` - `--max-lag` takes whole seconds; `1.5` parses as 5 s) rather than running twice. `--allow-on-master` is required whenever gh-ost connects to the primary, on any topology. On RDS/managed MySQL (no SUPER): add `--assume-rbr`. After any out-of-band gh-ost ALTER, apply the same ALTER locally (or record it in a guarded migration), then `db:schema:dump`, so `db/structure.sql` matches production - a dump of a database that never got the ALTER shows no diff. Alternative: `pt-online-schema-change` (trigger-based, slower, more topologies). Data backfills - including lag-aware throttling and external-API safety in backfill loops: see `rails-batch-processing-patterns` and `rails-rake-task-patterns`.

### Foreign keys

With the default `foreign_key_checks=1`, `ALTER TABLE ... ADD FOREIGN KEY` supports **only ALGORITHM=COPY** - a full table rebuild that blocks writes, not a brief metadata lock. INPLACE becomes available only with `foreign_key_checks=0`, which buys `LOCK=NONE` at the cost of an unvalidated constraint until you re-check it.

Before adding one, audit orphans (`SELECT COUNT(*) FROM order_items c LEFT JOIN orders p ON p.id = c.order_id WHERE p.id IS NULL`) - they fail the COPY, sit silently under an unvalidated INPLACE constraint, or are silently dropped by pt-osc's `INSERT LOW_PRIORITY IGNORE` row copy. On a large table this is *not* gh-ost work: gh-ost does not support foreign keys at all and refuses to run on any table holding an FK as child or parent. Use `pt-online-schema-change --alter "ADD FOREIGN KEY ..."`, adding `--alter-foreign-keys-method=rebuild_constraints` (or `drop_swap`) when other tables reference this one; pt-osc prefixes the new table's constraint names with `_`, so re-dump the schema afterwards. The same limitation qualifies the ">100M rows -> gh-ost" rule everywhere in this skill: `t.references ... foreign_key: true` is the house convention, so most large tables here are FK-bearing and belong to pt-osc.

### Lock timeout per migration

```ruby
# up/down, not change: `execute` has no inverse, so inside `change` it makes db:rollback raise
def up
  safety_assured { execute "SET SESSION lock_wait_timeout = 5" }   # metadata-lock timeout - what DDL queues on
  add_index :orders, :status, algorithm: :inplace
end

def down
  remove_index :orders, :status
end
```

`StrongMigrations.lock_timeout` emits the same setting for every migration, which makes the per-migration line unnecessary.

`innodb_lock_wait_timeout` bounds InnoDB *row-lock* waits and has no effect on the metadata lock a DDL statement waits for; with only that set, the migration still blocks indefinitely behind a long-running transaction. `lock_wait_timeout` is the MDL knob (default 31536000 - a year), and it is what `StrongMigrations.lock_timeout` emits on MySQL.

### Advisory lock for backfills

Guard against double-runs (deploy retry, two engineers). Full leader-election patterns: `rails-db-locking-patterns`.

```ruby
# In the backfill rake task (never db/migrate); `with_advisory_lock` gem (7.x) - a Gemfile without it is a finding naming the gem
ApplicationRecord.with_advisory_lock!("backfill_order_amount", timeout_seconds: 0) do
  Order.in_batches(of: 10_000) { |b| b.where(amount: nil).update_all("amount = total") }
end
# The bang form raises WithAdvisoryLock::FailedToAcquireLock when someone else holds it.
# `with_advisory_lock(...) { } || abort` is a trap: the block returns in_batches' nil on a
# *successful* run, so the abort fires after the backfill completes.
```

### Rollback safety

Test `db:migrate && db:rollback && db:migrate` in CI, and test rollback on a clone before merging. MySQL DDL is not transactional: a multi-statement migration that fails midway leaves the earlier statements applied and `schema_migrations` unrecorded. Reconcile first (`Operation: Reconcile` - compare `information_schema` to the file), then split or delete what already applied so the file re-runs cleanly. Two INSTANT caveats, in opposite directions: on 8.0.12-8.0.28 an instantly-added column could not be dropped instantly, so the rollback rebuilt the table; from 8.0.29 instant `DROP COLUMN` exists, but every instant ADD/DROP COLUMN consumes one of a table's **64 row versions** - once exhausted, instant ADD/DROP COLUMN fails with "Maximum row versions reached for table" until an INPLACE or COPY rebuild (or `OPTIMIZE TABLE`) resets the count; other INSTANT operations (rename, defaults, ENUM append) are unaffected. Check the budget before planning instant steps: `SELECT TOTAL_ROW_VERSIONS FROM information_schema.INNODB_TABLES WHERE NAME = 'app/orders'`.

```ruby
def change
  reversible do |dir|
    dir.up   { safety_assured { execute "ALTER TABLE orders ADD COLUMN notes TEXT, ALGORITHM=INSTANT" } }
    dir.down { safety_assured { execute "ALTER TABLE orders DROP COLUMN notes, ALGORITHM=INSTANT" } }   # 8.0.29+; omit the clause below that
  end
end
```

## Output Format

One block per operation, in execution order - a migration file bundling two operations emits two blocks sharing one `Migration:` value (and a finding against the one-structural-change-per-migration rule; an index or constraint on the table the same file creates belongs to that `Create Table` block, not a second one), and a multi-step plan emits a numbered sequence whose `Step` numbers run across the whole plan, split files included. Rake backfills get blocks too (`Operation: Backfill`, `Algorithm: batched rake`); a gh-ost / pt-osc run keeps its DDL `Operation` with `Algorithm: gh-ost` / `pt-online-schema-change`, and one run carrying several ALTERs is still one block per operation, each with the tool's `Algorithm` and `Notes: same run as step N`. Non-DDL sequence steps that the patterns require - a dependency audit, an `ignored_columns`-only deploy, an external-reader cutover, a reconcile after a partial run - get a block with `Operation: Coordination` (or `Reconcile`), `Algorithm: n/a`, and `n/a` in `Lock window` and `Safety`. In review or diagnosis mode, numbered findings precede the blocks, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Every block field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and when the enum value that matches already carries a `GAP`, `FIX` or `BLOCKER` marker in any spelling (` - GAP`, `(GAP)`, `(FIX)`, `(BLOCKER)`, a trailing parenthetical included), that value is the observed half and ` -> <corrected>` follows it. The marker applies to every field except `Safety`, whether or not its enum lists a `GAP` value; a field whose value is several named or `+`-joined parts marks only the violated part. A violation that belongs to no block - process or deploy config, a schema defect, a sibling skill's concern, a bug seen in passing - is a numbered finding with no block, naming the file and, for a sibling's concern, the owning skill. A violation whose block unit the code lacks (no client class, no transaction, no channel class) gets a block for the unit the fix introduces, its name suffixed `(proposed)`. When the request's premise or a document contradicts the code or schema, the code wins: say so in a finding and proceed on what the code shows. A request to add code, or to change code the request does not ask you to judge, is build mode: every block field holds the corrected value and no GAP marker (an enum value's own marker is dropped), and a pre-existing violation the change touches is still a numbered finding. A request that names existing code to assess, even when it also asks for the fix, is review mode. A block is the corrected operation, so `Safety` rates the operation as corrected and carries no GAP marker - `Blocked` when its required tool is absent - and the as-written verdict lives in the finding; a block keeps `Reject` only when this skill has no safe rewrite for it, with `n/a` in `Algorithm` and `Lock window`. Prerequisite Coordination steps (an audit, a tool install) come first in the sequence; a file split in the correction keeps its name on the operation it retains, and each split-off operation reads `proposed - split from <file>`. This applies to a post-incident review of an already-executed migration as much as to a pre-merge one.

```
Step: {n of N | n/a (single operation)}

Migration: {file name | rake file path | rake file not provided - name it | proposed - not yet created | proposed - split from <file> | generated - <generator> | n/a (out-of-band gh-ost / pt-osc run, a DBA command, a decision or a deploy-only step)}

Operation: {Create Table | Rename Table | Drop Table | Add Column | Change Column | Rename Column (coordinated cutover only) | Add Index | Alter Index (invisible soak) | Drop Index | Add FK | Add CHECK | Drop Constraint | Backfill | Remove Column | Drop/Recreate View | Coordination | Reconcile}

Table: {name} ({row count | new - 0 rows | absent from the schema - Blocked | "size unstated - assume large and justify"}) | n/a (Coordination, Reconcile with no single table)

Engine: MySQL {x.y.z from SELECT VERSION(), the declared ## Tech Stack or committed ops docs | unknown - assume no INSTANT support}

Algorithm: {INSTANT | INPLACE | COPY | gh-ost | pt-online-schema-change | batched rake | n/a (Create Table, Coordination, Reconcile, Reject)}

Lock window: {none (online) | brief cut-over lock (gh-ost / pt-osc) | brief metadata lock | write-blocking rebuild (COPY or LOCK=SHARED - brief only on a small table) | maintenance required | n/a (Coordination, Reconcile, Backfill, Reject)}

Safety: {Zero-Downtime (online DDL, or a gh-ost / pt-osc run) | Maintenance Window | Batched Backfill | Hardening advised - compliant but under-specified | Blocked - required tooling or dependency absent (tool, target table), name it | Blocked - depends on step N (a later step behind a Blocked one keeps its own Algorithm and Lock window) | Reject - rewrite required | Already applied - unsafe as run, findings say what changes | n/a (Coordination, Reconcile)}

Notes: {charset/collation, INSTANT eligibility, gh-ost throttle config}
```

`Engine` takes its patch level from `## Tech Stack`, committed ops docs or the server, else `unknown` - never an assumed 8.0.latest. When the >100M-row rule mandates gh-ost/pt-osc and neither is confirmed installed, that is `Safety: Blocked`, not a silent downgrade to an in-process ALTER: say which tool is needed and that installing it is a prerequisite of the change.

## Avoid

- In-process type changes that force a COPY on a deployed table above ~100K rows outside a maintenance window - use add/backfill/remove, or gh-ost / pt-osc for a pure widening
- `disable_ddl_transaction!` as a safety measure - MySQL DDL is never transactional, so it changes nothing
- Irreversible migrations without explicit `raise ActiveRecord::IrreversibleMigration`
