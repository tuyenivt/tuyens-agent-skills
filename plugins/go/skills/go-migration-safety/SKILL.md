---
name: go-migration-safety
description: "golang-migrate + PostgreSQL safety: naming, up/down pairs, zero-downtime DDL, CHECK constraints, CONCURRENTLY indexes, binary embedding."
metadata:
  category: backend
  tags: [go, migration, postgresql, golang-migrate, ddl, zero-downtime]
user-invocable: false
---

# Go Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Setting up migrations for a new Go service
- Reviewing a migration for production safety (locking, rollback)
- Adding CHECK constraints for status/enum columns
- Debugging a failed or dirty migration

## Rules

- Never `GORM AutoMigrate` in production - it can drop columns and has no rollback
- Every `up` has a matching `down`
- Never mix DDL and DML in one file
- Never write a destructive `down` (DROP COLUMN/TABLE with data) without backup or compensating migration. A `down` undoes its `up` in exact reverse order - dropping a column first also drops its indexes, so a later `DROP INDEX` in the same file errors and strands the rollback half-applied
- Zero-downtime DDL: add before delete; expand-contract, never in-place rename
- `SET lock_timeout = '3s'` (seconds, not minutes) at the top of any file taking `AccessExclusiveLock`, up and down. That lock queues behind long transactions and anti-wraparound autovacuum, and once queued it blocks every read and write to the table behind it - an unbounded wait turns one slow `ALTER` into a full outage, while a timeout is a clean retry
- **Constraint before repair, backfill before constraint - they are not in conflict.** A `NOT VALID` constraint enforces on new rows immediately, so install it first when existing rows are already violating and new bad writes must be stopped (a FK with orphans, a CHECK a live writer still breaks). Backfill first when no writer produces violating rows and the column is simply unpopulated (adding NOT NULL to a nullable column). Ask which one the situation is; the wrong order either races new bad writes or fails validation
- golang-migrate adds no `BEGIN`/`COMMIT` of its own (no directive exists - `NO TRANSACTION` annotations belong to goose/dbmate), but its Postgres driver sends the whole file in one `Exec`, which the server runs as one **implicit** transaction. Two consequences: a file containing `CREATE INDEX CONCURRENTLY` must hold that single statement and nothing else, because CONCURRENTLY cannot run in a transaction block; and a single-statement-per-file set is already atomic per file, so add explicit `BEGIN; ... COMMIT;` only where two statements must land together (a constraint DROP + ADD pair). A file that mixes many statements fails partway and leaves partial DDL plus a dirty version

## File Naming

```
migrations/000002_add_email_index.up.sql
migrations/000002_add_email_index.down.sql
```

Format: `{zero-padded-version}_{snake_case_description}.{up|down}.sql`

## Zero-Downtime DDL

### Adding a Column

```sql
-- nullable: instant, no lock
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
```

PostgreSQL 11+: `ADD COLUMN ... NOT NULL DEFAULT 'value'` is instant for **new** columns (default stored in catalog). Does NOT apply to `ALTER COLUMN SET NOT NULL` on existing columns.

### Adding NOT NULL on an Existing Column

`ALTER COLUMN SET NOT NULL` acquires `AccessExclusiveLock` and scans the whole table. For large tables use CHECK with NOT VALID:

```sql
-- Migration N: nullable column
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- Migration N+1: backfill in batches (see Large backfills - one UPDATE over a big table
-- holds a long transaction and bloats WAL)
UPDATE users SET phone = '' WHERE phone IS NULL AND id BETWEEN 1 AND 100000;
-- ...repeat per batch (app-driven loop or repeated migration files)

-- Migration N+2 (own file): NOT VALID skips existing rows (instant)
ALTER TABLE users ADD CONSTRAINT users_phone_not_null
    CHECK (phone IS NOT NULL) NOT VALID;

-- Migration N+3 (own file): VALIDATE uses ShareUpdateExclusiveLock (allows reads/writes)
ALTER TABLE users VALIDATE CONSTRAINT users_phone_not_null;

-- Migration N+4 (PG12+): instant - the planner proves it from the validated CHECK
ALTER TABLE users ALTER COLUMN phone SET NOT NULL;
ALTER TABLE users DROP CONSTRAINT users_phone_not_null;
```

### CHECK Constraints (status / enum)

Same NOT VALID + VALIDATE pattern. To add a new status value, drop and re-create the constraint - wrap the DROP and ADD in an explicit `BEGIN; ... COMMIT;` or there is a window with no constraint at all.

### Foreign Keys

Same shape, and required for the same reason: a plain `ADD CONSTRAINT ... FOREIGN KEY` scans the whole child table while holding locks on **both** tables.

```sql
-- own file: ShareRowExclusive on both tables, but no scan
ALTER TABLE orders ADD CONSTRAINT orders_warehouse_fk
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) NOT VALID;
-- own file: ShareUpdateExclusive, reads and writes continue
ALTER TABLE orders VALIDATE CONSTRAINT orders_warehouse_fk;
```

`NOT VALID` still enforces the constraint on new rows, so install it *before* repairing existing violations - otherwise the repair races new bad writes. `VALIDATE` fails if any orphan remains. A FK also makes every delete on the parent scan the child unless the referencing column is indexed.

### Lock Levels

| Operation | Lock | Blocks |
|-----------|------|--------|
| `ADD COLUMN` (nullable, or PG11+ with default), `DROP COLUMN`, `RENAME`, `SET NOT NULL`, `ADD CONSTRAINT ... CHECK` | AccessExclusive | everything, including reads |
| `ADD CONSTRAINT ... FOREIGN KEY ... NOT VALID` | ShareRowExclusive (both tables) | writes |
| `CREATE INDEX` (non-concurrent) | Share | writes |
| `CREATE/DROP INDEX CONCURRENTLY`, `VALIDATE CONSTRAINT` | ShareUpdateExclusive | other DDL and autovacuum, not reads or writes |
| `UPDATE` / `DELETE` / `INSERT` | RowExclusive | conflicting row locks only |

The brief locks are the dangerous ones on a hot table: acquisition queues behind the oldest in-flight transaction, and every query arriving after it queues behind the lock.

### Indexes (always CONCURRENTLY in prod)

```sql
-- Own file AND the only statement in it: golang-migrate sends a multi-statement file
-- as one implicit transaction, which CONCURRENTLY cannot run inside.
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);

-- down
DROP INDEX CONCURRENTLY IF EXISTS idx_users_email;
```

Composite index column order: equality columns first, then range columns; most selective leftmost.

### Renaming a Column (expand-contract)

```sql
-- N:   ADD COLUMN full_name
-- App: dual-write old + new, deployed to every replica before N+1
-- N+1: batched backfill (see Large backfills - a bare full-table UPDATE here has
--      the same WAL and lock-window cost it has anywhere else)
--      UPDATE users SET full_name = name WHERE full_name IS NULL AND id BETWEEN ? AND ?
-- App: read full_name only
-- N+2: DROP COLUMN name
```

The backfill must not run until the dual-writing app is on **every** replica, or the rows written by an old replica during the rollout stay NULL. When a consumer outside the team reads the old column, the contract step is blocked until that team cuts over - keep the old column synchronized with a trigger rather than shipping N+2 on schedule.

## golang-migrate Usage

```bash
migrate -path ./migrations -database "$DATABASE_URL" up
migrate -path ./migrations -database "$DATABASE_URL" down 1
migrate -path ./migrations -database "$DATABASE_URL" version
migrate -path ./migrations -database "$DATABASE_URL" force <version>  # clear dirty state
```

### Embedding in Binary

```go
//go:embed migrations/*.sql
var migrationsFS embed.FS

func RunMigrations(dsn string) error {
    src, err := iofs.New(migrationsFS, "migrations")
    if err != nil { return fmt.Errorf("migrations source: %w", err) }

    m, err := migrate.NewWithSourceInstance("iofs", src, dsn)
    if err != nil { return fmt.Errorf("migrate init: %w", err) }
    defer m.Close()

    if err := m.Up(); err != nil && !errors.Is(err, migrate.ErrNoChange) {
        return fmt.Errorf("migrate up: %w", err)
    }
    return nil
}
```

### Startup Sequencing

Run migrations before starting the server, not concurrently. Use a single runner (init container, CLI job) or rely on golang-migrate's advisory lock to prevent concurrent runs from racing.

## CI Validation

```bash
migrate up
migrate down 1
migrate up   # catches non-idempotent migrations
```

## Edge Cases

- **Dirty state**: a failed migration leaves the version dirty. `force N` records N as *applied and clean* - it does not re-run it. Reverting a failed migration N therefore means `force N-1`, after manually undoing whatever partial DDL landed; `force N` silently skips the rest of that migration's work forever. Inspect the real schema (`\d`, `pg_index.indisvalid`) before choosing, because golang-migrate records only that N failed, never how far it got
- **Killed CONCURRENTLY**: a failed/cancelled `CREATE INDEX CONCURRENTLY` leaves an INVALID index (`pg_index.indisvalid = false`); re-running fails "already exists". `DROP INDEX CONCURRENTLY IF EXISTS` it first - a plain DROP takes AccessExclusiveLock
- **Empty down**: when a migration is truly irreversible, write a down that errors with an explanation rather than leaving it blank
- **Large backfills**: batch via `WHERE id BETWEEN ... AND ...` to avoid long-running transactions and WAL bloat
- **Adding a CHECK value**: requires DROP + ADD + VALIDATE - plan for it when designing status columns

## Output Format

Planning a change set emits `## Migration Plan`. Reviewing existing files or recovering a failed migration emits `## Findings` first, then the plan tables describing the corrected files.

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

Cell values: one `Files` row per statement whose lock level differs from its file's others, otherwise one row per file - the lock is the unit that matters. `Type` is `DDL | DML | index | constraint | validate`. `Lock Level` is the Postgres lock name (`AccessExclusiveLock`, `ShareUpdateExclusiveLock`, `ShareLock`, `RowExclusiveLock`, `none`). `Reversible?` is `Yes | Guarded | No` - `Guarded` when the down is destructive and refuses unless an operator opts in, `No` when it must raise an explanatory error.

```
## Findings

### [Must] file:line

- Defect: {what happens when this runs against production}
- Rule: {the migration rule violated}
- Fix: {the corrected SQL or file split}
```

`[Must]` when the migration cannot succeed, locks a hot table for a full scan or an unbounded lock wait, loses data, has no usable rollback, or leaves a dirty version; `[Recommend]` otherwise - judge by blast radius on the target table, not by matching the list. A `Guarded` down refuses by default; show the mechanism (a `DO $$ ... RAISE EXCEPTION $$` block gated on a settable GUC) rather than describing it.

When reviewing, list the facts the diff cannot answer - row counts behind a NOT NULL, distinct values behind a new CHECK, whether the version is already applied somewhere - as queries to run before merging. A review that assumes them is a guess. When recovering a failed migration, state the current schema reality first (applied statements, invalid indexes, row counts), then the ordered commands - a runbook whose steps are not ordered is not actionable.

## Avoid

- `AutoMigrate` in production
- In-place column rename (no expand-contract)
- `DROP COLUMN/TABLE` without backup
- Mixed DDL+DML in one file
- `CREATE INDEX` without `CONCURRENTLY` on large tables
- `ALTER COLUMN SET NOT NULL` on large tables - use NOT VALID CHECK
- Missing down migrations
