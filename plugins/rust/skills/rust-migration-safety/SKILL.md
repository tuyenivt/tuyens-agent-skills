---
name: rust-migration-safety
description: "sqlx-cli + PostgreSQL migration safety: reversible pairs, -- no-transaction, lock_timeout, NOT VALID, CONCURRENTLY, expand-contract, migrate!()."
metadata:
  category: backend
  tags: [rust, sqlx, migration, postgresql, ddl, zero-downtime]
user-invocable: false
---

# Rust Migration Safety

> Load `Use skill: stack-detect` first. This skill reads `Database`; on `unknown` the sqlx feature list in the crate's `Cargo.toml` (`postgres`, `mysql`, `sqlite`) names the engine. In a Cargo workspace the crate that owns the `migrations/` directory decides (its `[dependencies]`, or the `[workspace.dependencies]` entries it inherits). Every lock, DDL and catalog fact here is PostgreSQL 12+ on sqlx-cli / sqlx 0.9; on MySQL the lock model and online-DDL rules differ (and MySQL DDL commits implicitly, so a multi-statement file is not atomic): keep only the file-layout and up/down rules and fill `Lock Level` with `unknown`; on `unknown`, keep the PostgreSQL form. Another migration tool (refinery, Diesel, SeaORM migrations) keeps its own file layout and transaction directive; the DDL rules and the Output Format apply, `Down` naming that tool's down form (Diesel `down.sql` beside `up.sql`) or reading `n/a` under a tool with no down migrations (refinery).

## When to Use

- Setting up migrations for a new Rust service
- Reviewing a migration for production safety (locking, rollback)
- Adding CHECK constraints for status/enum columns
- Debugging a failed, dirty, or checksum-mismatched migration

## Rules

- Never let the application emit unreviewed DDL at startup (a `CREATE TABLE IF NOT EXISTS` in `main`, an ORM schema sync): schema changes ship as versioned migration files
- Every migration is reversible (`sqlx migrate add -r <name>` -> `<version>_<name>.up.sql` + `.down.sql`). A directory holds one kind - sqlx-cli refuses to add a reversible migration beside simple (`<version>_<name>.sql`) ones
- Never mix DDL and DML in one file
- Never write a destructive `down` (DROP COLUMN/TABLE with data) without backup or a compensating migration. A `down` undoes its `up` in exact reverse order - dropping a column first also drops its indexes, so a later `DROP INDEX` in the same file errors and strands the rollback
- Zero-downtime DDL: add before delete; expand-contract, never in-place rename or retype
- A version applied in any environment is never edited: sqlx stores a checksum per applied version and the next `run` or `sqlx::migrate!()` aborts with a version mismatch. A fix is a new version
- `SET LOCAL lock_timeout = '3s'` at the top of any file taking `AccessExclusiveLock` or `ShareRowExclusiveLock` on a hot table, up and down. Those locks queue behind every transaction holding a conflicting lock and, once queued, block every read and write behind them - an unbounded wait turns one slow `ALTER` into an outage, a timeout is a clean retry. `LOCAL` scopes it to the migration's transaction; a plain `SET` persists on the migrator's single connection into every later file - including a `CREATE INDEX CONCURRENTLY`, which a lock timeout cancels into an INVALID index. A CONCURRENTLY file carries no `SET`, and the connection string sets no `lock_timeout`
- sqlx wraps each migration in a transaction, so a multi-statement file is atomic: a failing statement rolls the whole file back and records nothing. `-- no-transaction` as the file's **first line** turns that off; it is required for `CREATE/DROP INDEX CONCURRENTLY`, `REINDEX CONCURRENTLY` and `VACUUM`, and such a file holds that one statement - the server runs a multi-statement simple query as one implicit transaction, which CONCURRENTLY cannot run inside. `ALTER TYPE ... ADD VALUE` runs inside a transaction on PG12+, but the new value cannot be used until that transaction commits - use it in the next file
- **Constraint before repair, backfill before constraint - they are not in conflict.** A `NOT VALID` constraint enforces on new rows immediately, so install it first when existing rows already violate and new bad writes must stop (a FK with orphans, a CHECK a live writer still breaks). Backfill first when no writer produces violating rows and the column is simply unpopulated. Ask which one the situation is; the wrong order either races new bad writes or fails validation

## File Naming

```
migrations/20261114093000_add_email_index.up.sql
migrations/20261114093000_add_email_index.down.sql
```

`sqlx migrate add -r` stamps a UTC timestamp; `--sequential` (or an existing sequential directory) gives `0001_`. `sqlx migrate run` applies every version it has not recorded, in version order - a branch file versioned below one already applied elsewhere still runs, after it on a deployed database and before it on a fresh one. Check the repository's `.gitattributes` pins `*.sql` to `eol=lf`: a Windows checkout that rewrites line endings changes the checksum of every applied file.

## Zero-Downtime DDL

### Adding a Column

```sql
-- nullable: catalog-only, but still a brief AccessExclusiveLock - bound it
SET LOCAL lock_timeout = '3s';
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
```

PostgreSQL 11+: `ADD COLUMN ... NOT NULL DEFAULT <value>` is instant for a **new** column when the default is non-volatile - a constant or a stable function (`now()` qualifies, evaluated once); `clock_timestamp()`, `gen_random_uuid()` and `random()` are volatile and rewrite the table. Does not apply to `ALTER COLUMN SET NOT NULL` on an existing column.

### Adding NOT NULL on an Existing Column

`ALTER COLUMN SET NOT NULL` takes `AccessExclusiveLock` and scans the whole table - unless a validated `CHECK (col IS NOT NULL)` already exists (PG12+):

```sql
-- N: nullable column
SET LOCAL lock_timeout = '3s';
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- App: every replica writes phone on insert/update before N+1 ships - otherwise rows
-- written during the backfill stay NULL and N+3 fails

-- N+1: backfill in batches (see Large backfills)
UPDATE users SET phone = '' WHERE phone IS NULL AND id BETWEEN 1 AND 100000;

-- N+2 (own file): NOT VALID skips existing rows (instant)
SET LOCAL lock_timeout = '3s';
ALTER TABLE users ADD CONSTRAINT users_phone_not_null CHECK (phone IS NOT NULL) NOT VALID;

-- N+3 (own file): VALIDATE takes ShareUpdateExclusiveLock (reads and writes continue)
ALTER TABLE users VALIDATE CONSTRAINT users_phone_not_null;

-- N+4: SET NOT NULL sees the validated CHECK and skips the scan; the brief lock remains
SET LOCAL lock_timeout = '3s';
ALTER TABLE users ALTER COLUMN phone SET NOT NULL;
ALTER TABLE users DROP CONSTRAINT users_phone_not_null;
```

### CHECK Constraints (status / enum)

Same NOT VALID + VALIDATE pattern. To add a status value, drop and re-create the constraint in one file - the migration's transaction closes the window where no constraint exists. A constraint declared inline on a brand-new table needs no NOT VALID: there are no rows to scan. A Rust enum deriving `sqlx::Type` must gain the variant before the CHECK admits it, or a row written by a newer replica fails to decode on an older one.

### Foreign Keys

A plain `ADD CONSTRAINT ... FOREIGN KEY` scans the whole child table while holding locks on **both** tables:

```sql
-- own file: ShareRowExclusive on both tables, but no scan
SET LOCAL lock_timeout = '3s';
ALTER TABLE orders ADD CONSTRAINT orders_warehouse_fk
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) NOT VALID;
-- own file: ShareUpdateExclusive, reads and writes continue
ALTER TABLE orders VALIDATE CONSTRAINT orders_warehouse_fk;
```

`NOT VALID` still enforces on new rows, so install it *before* repairing existing violations; `VALIDATE` fails if any orphan remains. A FK makes every parent delete scan the child unless the referencing column is indexed. Changing `ON DELETE` is DROP + ADD NOT VALID in one file, VALIDATE in the next.

### Lock Levels

| Operation | Lock | Blocks |
|-----------|------|--------|
| `ADD COLUMN` (nullable, or PG11+ with non-volatile default), `DROP COLUMN`, `RENAME`, `ALTER COLUMN TYPE`, `SET NOT NULL`, `ADD CONSTRAINT ... CHECK`, `DROP CONSTRAINT`, `DROP TABLE` (a FK `DROP CONSTRAINT` and `DROP TABLE` also lock every FK parent) | AccessExclusive | everything, including reads |
| `ADD CONSTRAINT ... FOREIGN KEY` (with or without `NOT VALID`) | ShareRowExclusive (both tables) | writes |
| `CREATE INDEX` (non-concurrent) | Share | writes |
| `CREATE/DROP INDEX CONCURRENTLY`, `VALIDATE CONSTRAINT` | ShareUpdateExclusive | other DDL and autovacuum, not reads or writes |
| `UPDATE` / `DELETE` / `INSERT` | RowExclusive | no other DML; queues Share and stronger table locks behind it |

`ALTER COLUMN TYPE` also rewrites the table and its indexes unless the change is binary-coercible (`varchar(20)` -> `varchar(40)` or `text`).

### Indexes (always CONCURRENTLY in prod)

```sql
-- no-transaction
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email ON users(email);
```

```sql
-- no-transaction
DROP INDEX CONCURRENTLY IF EXISTS idx_users_email;
```

The directive is the very first line of each file (up and down) and the statement is the only one in it. Composite index column order: equality columns first, then range columns. A btree scans backward for a `DESC` sort, so the direction clause matters only for mixed-direction sorts.

### Renaming a Column (expand-contract)

```sql
-- N:   ADD COLUMN full_name
-- App: dual-write old + new, deployed to every replica before N+1
-- N+1: batched backfill
--      UPDATE users SET full_name = name WHERE full_name IS NULL AND id BETWEEN $lo AND $hi
-- App: read full_name only
-- N+2: DROP COLUMN name
```

The backfill must not run until the dual-writing app is on **every** replica. A `query_as!` struct that still selects the old column breaks the replicas running it the moment N+2 applies, and the checked macros only see the schema they were prepared against - `.sqlx/` from before N+2 compiles happily. When a consumer outside the team reads the old column, keep it synchronized with a trigger rather than shipping N+2 on schedule.

## sqlx-cli Usage

```bash
sqlx migrate add -r add_email_index          # reversible pair
sqlx migrate run                             # applies pending versions in order
sqlx migrate revert                          # reverts the newest applied version
sqlx migrate revert --target-version 20261101000000
sqlx migrate info                            # applied / pending / checksum per version
```

### Embedding in the Binary

```rust
use sqlx::{PgPool, migrate::Migrator};

static MIGRATOR: Migrator = sqlx::migrate!(); // ./migrations relative to CARGO_MANIFEST_DIR, embedded at compile time

pub async fn run_migrations(pool: &PgPool) -> anyhow::Result<()> {
    MIGRATOR.run(pool).await?; // takes a PostgreSQL advisory lock, then applies pending versions
    Ok(())
}
```

`migrate!()` embeds the files at compile time, and Cargo does not rebuild when only a `.sql` file is added - generate a `build.rs` with `sqlx migrate build-script` so it does. The migrator's advisory lock is session-scoped and waits without a timeout; run it against the database directly, never through PgBouncer in transaction mode, where lock and unlock can land on different server connections.

### Startup Sequencing

Run migrations before the server starts, from a single runner: a Job or pre-upgrade hook running `sqlx migrate run` or the binary's `migrate` subcommand. `MIGRATOR.run` in `main` on every replica is serialized by the advisory lock, but a failing migration then crash-loops every pod - the runner is part of the plan.

## CI Validation

```bash
sqlx migrate run && sqlx migrate revert && sqlx migrate run  # the newest down really reverses its up
cargo sqlx prepare --check --workspace                        # .sqlx/ matches the migrated schema
```

## Edge Cases

- **Dirty version**: a transactional migration that fails rolls back and records nothing. A `-- no-transaction` migration is recorded with `success = false` before it runs, so a failure leaves that row and the next run stops with a dirty-version error. sqlx has no `force`: clean up what the statement left (an INVALID index), then `DELETE FROM _sqlx_migrations WHERE version = <N> AND NOT success` and run again. Inspect the real schema (`\d`, `pg_index.indisvalid`) first - the table records only that N failed
- **Killed CONCURRENTLY**: a failed or cancelled `CREATE INDEX CONCURRENTLY` leaves an INVALID index; `IF NOT EXISTS` then skips it silently. `DROP INDEX CONCURRENTLY IF EXISTS` it first - a plain DROP takes AccessExclusiveLock
- **Checksum mismatch**: `revert` the version where it is applied and fix the file only when no other environment applied it; otherwise restore the original bytes and ship a new version
- **Empty down**: when a migration is truly irreversible, write a down that raises with an explanation rather than leaving it blank; when the inverse lives in another file (a VALIDATE's down), say so in a comment
- **Large backfills**: batch by primary-key range, commit per batch; above ~1M rows run them from a job, not a migration - one `UPDATE` holds row locks and bloats WAL

## Output Format

Open the deliverable with one line above everything else, `**Engine:** {database | unknown}` - stack-detect's `Database` value as written, or the engine named by the owning crate's sqlx feature.

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Plan | `## Migration Plan` with `### Files`, `### Safety Assessment`, `### Rollback Plan`; the SQL for each file follows under `### <file name>` headings in `Files` order. A plan handed existing files that violate a Rule emits `## Findings` first; a requested change already shipped in an applied file gets no new file - its `Files` row is that version marked `(applied)` |
| Review | `## Findings`, then `## Migration Plan` describing the **corrected** files, then `### Pre-merge Queries` - the facts the diff cannot answer (row counts behind a NOT NULL, distinct values behind a new CHECK, whether a version is already applied somewhere) as runnable queries; a review that assumes them is a guess |
| Recovery | two opening lines `**Schema now:**` (applied statements, invalid indexes, dirty or mismatched version) and `**First step:**` (the operator action that stops the bleeding - pause the rollout or pin the last good image - before any SQL), then `## Runbook` - numbered, each step one command or query, with the `_sqlx_migrations` edit as its own step - then `## Findings`, then `## Migration Plan` for the files still to run. A dirty version never completed: fix its file in place when no environment recorded it with `success = true`; otherwise ship the fix as a new version |

```
## Migration Plan

### Files
| Version | File | Type | Lock Level | Notes |
|---------|------|------|------------|-------|

### Safety Assessment
| Risk | Mitigation |
|------|------------|

### Rollback Plan
| Version | Down | Reversible? |
|---------|------|-------------|
```

Cell values: one `Files` row per statement whose lock level differs from its file's others, otherwise one row per file - the lock is the unit that matters; a version's up row precedes its down row. A file the plan splits takes new versions above the highest version on both base and branch - a version is never renumbered once applied anywhere. A file applied anywhere is never edited (the checksum). `Version` is `n/a` for a row with no file. `Notes` records the deploy ordering the file depends on (`app dual-writing on every replica first`), `no-transaction` when the file carries the directive, and `(applied)` for a version already in production. `Type` is `DDL | DML | index | constraint | validate | none` - `none` for a deliberate no-op (a comment-only down). `Down` is the down file's name, or `<missing>`, followed by its inverse statement in one clause. `Lock Level` is the Postgres lock name (`AccessExclusiveLock`, `ShareRowExclusiveLock`, `ShareUpdateExclusiveLock`, `ShareLock`, `RowExclusiveLock`, `none`). `Reversible?` is `Yes | Guarded | No | n/a` - `Guarded` when the down is destructive and refuses unless an operator opts in, `No` when it must raise an explanatory error, `n/a` when the down is a deliberate no-op because the inverse lives in another file; `unknown` when the inverse cannot be known from the input (the original FK definition is not supplied). A `Safety Assessment` row whose `Risk` is a fact the diff cannot answer has `Mitigation` = `ask: <who or which query>`. A backfill that matches zero rows is `[Recommend]`. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {what happens when this runs against production}
- Rule: {the migration rule violated}
- Fix: {the corrected SQL or file split}
```

Owned findings: `[Must]` when the migration cannot succeed (CONCURRENTLY without `-- no-transaction` as line 1, an edited applied file), locks a hot table for a full scan or an unbounded lock wait, loses data, has no usable rollback, or leaves a dirty version; `[Recommend]` otherwise - judge by blast radius on the target table, not by matching the list. A `Guarded` down refuses by default; show the mechanism (a `DO $$ ... RAISE EXCEPTION $$` block gated on `current_setting('app.allow_destructive', true) = 'on'`, delivered on the runner's own session through the connection string's `options=-c app.allow_destructive=on` - an operator's `SET LOCAL` on another connection never reaches it) rather than describing it. Cite `file:line` when the input carries line numbers; a missing down file is cited as `<version>_<name>.down.sql:<missing>`; a range is `file:start-end`. Order owned findings `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites (the same unbounded lock in three files) is one heading citing the first site, with the rest named on the `Defect:` line. A defect this skill does not own (an index the query layer needs, a `query_as!` struct still selecting a dropped column, an image that cannot roll back) is still reported, never dropped: one block per such defect after every owned finding, in that same order among themselves, labelled `[Must]` when it risks incorrect behaviour, data loss or a security hole and `[Recommend]` otherwise, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- DDL emitted by the application at startup
- In-place column rename or retype (no expand-contract)
- `DROP COLUMN/TABLE` without backup
- Mixed DDL+DML in one file
- `CREATE INDEX` without `CONCURRENTLY` on large tables, or CONCURRENTLY without `-- no-transaction` on line 1
- `ALTER COLUMN SET NOT NULL` on a large table with no validated CHECK already in place
- Editing a migration after any environment applied it
- A plain `SET lock_timeout` (session-scoped on the migrator's connection) - always `SET LOCAL`
