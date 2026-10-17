---
name: go-migration-safety
description: "golang-migrate + PostgreSQL safety: naming, up/down pairs, zero-downtime DDL, CHECK constraints, CONCURRENTLY indexes, binary embedding."
metadata:
  category: backend
  tags: [go, migration, postgresql, golang-migrate, ddl, zero-downtime]
user-invocable: false
---

# Go Migration Safety

> Load `Use skill: stack-detect` first. This skill reads `Database`; the Go version is the `go` directive in `go.mod` (a `## Tech Stack` `Language:` line may carry a version; the directive wins when they differ). Every lock, DDL and catalog fact here is PostgreSQL 12+ on golang-migrate v4.16+ (`source/iofs` since 4.14, `database/pgx/v5` since 4.16); on MySQL the lock model and online-DDL rules differ: keep only the file-layout and up/down rules and fill `Lock Level` with `unknown`; on `unknown`, keep the PostgreSQL form.

## When to Use

- Setting up migrations for a new Go service
- Reviewing a migration for production safety (locking, rollback)
- Adding CHECK constraints for status/enum columns
- Debugging a failed or dirty migration

## Rules

- Never `GORM AutoMigrate` in production - it emits unreviewed DDL under unbounded locks with no version and no rollback (it adds columns, indexes, constraints and foreign keys and alters column size, precision and nullability, each under AccessExclusiveLock with no lock timeout; it never drops columns)
- Every `up` has a matching `down`
- Never mix DDL and DML in one file
- Never write a destructive `down` (DROP COLUMN/TABLE with data) without backup or compensating migration. A `down` undoes its `up` in exact reverse order - dropping a column first also drops its indexes, so a later `DROP INDEX` in the same file errors and strands the rollback half-applied
- Zero-downtime DDL: add before delete; expand-contract, never in-place rename
- `SET LOCAL lock_timeout = '3s'` (seconds, not minutes) at the top of any file taking `AccessExclusiveLock` or `ShareRowExclusiveLock` on a hot table, up and down. `LOCAL` scopes it to the file; a plain `SET` persists on golang-migrate's single held connection into every later file - including a `CREATE INDEX CONCURRENTLY`, which a lock timeout cancels into an INVALID index. Those locks queue behind every transaction holding a conflicting lock, and once queued block every read and write behind them - an unbounded wait turns one slow `ALTER` into an outage, a timeout is a clean retry. A CONCURRENTLY file cannot carry a `SET`, and a DSN-level `lock_timeout` would cancel its wait on older transactions into an INVALID index - so the DSN sets none: CONCURRENTLY files run without a lock timeout and the files this rule names carry their own `SET LOCAL` (golang-migrate's advisory-lock wait is bounded separately by `Migrate.LockTimeout`, 15s by default)
- **Constraint before repair, backfill before constraint - they are not in conflict.** A `NOT VALID` constraint enforces on new rows immediately, so install it first when existing rows are already violating and new bad writes must be stopped (a FK with orphans, a CHECK a live writer still breaks). Backfill first when no writer produces violating rows and the column is simply unpopulated (adding NOT NULL to a nullable column once every replica writes it). Ask which one the situation is; the wrong order either races new bad writes or fails validation
- golang-migrate adds no `BEGIN`/`COMMIT` of its own (no directive exists - `-- +goose NO TRANSACTION` is goose's, `-- migrate:up transaction:false` is dbmate's), but its Postgres driver sends the whole file in one `Exec`, which the server runs as one **implicit** transaction. Two consequences: a file containing `CREATE INDEX CONCURRENTLY` must hold that single statement and nothing else, because CONCURRENTLY cannot run in a transaction block; and a multi-statement file is already atomic - a failing statement rolls the whole file back and leaves only the version dirty, so a constraint DROP + ADD pair needs no explicit `BEGIN; ... COMMIT;`. Partial DDL survives a failure only from a non-transactional statement (CONCURRENTLY -> INVALID index) or with `x-multi-statement=true`

## File Naming

```
migrations/000002_add_email_index.up.sql
migrations/000002_add_email_index.down.sql
```

Format: `{zero-padded-version}_{snake_case_description}.{up|down}.sql`. A version applied in any environment is never renumbered or edited - a fix is a new version.

## Zero-Downtime DDL

### Adding a Column

```sql
-- nullable: catalog-only, but still a brief AccessExclusiveLock - bound it
SET LOCAL lock_timeout = '3s';
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
```

PostgreSQL 11+: `ADD COLUMN ... NOT NULL DEFAULT 'value'` is instant for **new** columns when the default is non-volatile (a constant; `now()` qualifies, `clock_timestamp()` / `gen_random_uuid()` / `random()` rewrite the table). Does NOT apply to `ALTER COLUMN SET NOT NULL` on existing columns.

### Adding NOT NULL on an Existing Column

`ALTER COLUMN SET NOT NULL` acquires `AccessExclusiveLock` and scans the whole table. For large tables use CHECK with NOT VALID:

```sql
-- Migration N: nullable column
SET LOCAL lock_timeout = '3s';
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- App: every replica writes phone on insert/update before N+1 ships - otherwise rows written
-- during the backfill stay NULL and N+3 fails

-- Migration N+1: backfill in batches (see Large backfills - one UPDATE over a big table
-- holds a long transaction and bloats WAL)
UPDATE users SET phone = '' WHERE phone IS NULL AND id BETWEEN 1 AND 100000;
-- ...repeat per batch (app-driven loop or repeated migration files)

-- Migration N+2 (own file): NOT VALID skips existing rows (instant)
SET LOCAL lock_timeout = '3s';
ALTER TABLE users ADD CONSTRAINT users_phone_not_null
    CHECK (phone IS NOT NULL) NOT VALID;

-- Migration N+3 (own file): VALIDATE uses ShareUpdateExclusiveLock (allows reads/writes)
ALTER TABLE users VALIDATE CONSTRAINT users_phone_not_null;

-- Migration N+4 (PG12+): SET NOT NULL sees the validated CHECK and skips the table scan;
-- the brief AccessExclusiveLock remains
SET LOCAL lock_timeout = '3s';
ALTER TABLE users ALTER COLUMN phone SET NOT NULL;
ALTER TABLE users DROP CONSTRAINT users_phone_not_null;
```

### CHECK Constraints (status / enum)

Same NOT VALID + VALIDATE pattern. To add a new status value, drop and re-create the constraint in one file - the implicit transaction closes the window where no constraint exists. A constraint declared inline on a brand-new table needs no NOT VALID: there are no rows to scan.

### Foreign Keys

Same shape, and required for the same reason: a plain `ADD CONSTRAINT ... FOREIGN KEY` scans the whole child table while holding locks on **both** tables.

```sql
-- own file: ShareRowExclusive on both tables, but no scan
SET LOCAL lock_timeout = '3s';
ALTER TABLE orders ADD CONSTRAINT orders_warehouse_fk
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) NOT VALID;
-- own file: ShareUpdateExclusive, reads and writes continue
ALTER TABLE orders VALIDATE CONSTRAINT orders_warehouse_fk;
```

`NOT VALID` still enforces the constraint on new rows, so install it *before* repairing existing violations - otherwise the repair races new bad writes. `VALIDATE` fails if any orphan remains. A FK also makes every delete on the parent scan the child unless the referencing column is indexed. Changing a FK's `ON DELETE` action is a DROP + ADD pair in one file; the new FK is validated on creation unless `NOT VALID`, so on a large child table it is DROP + ADD NOT VALID in one file, VALIDATE in the next.

### Lock Levels

| Operation | Lock | Blocks |
|-----------|------|--------|
| `ADD COLUMN` (nullable, or PG11+ with non-volatile default), `DROP COLUMN`, `RENAME`, `SET NOT NULL`, `ADD CONSTRAINT ... CHECK`, `DROP CONSTRAINT`, `DROP TABLE` (also on every FK parent, to drop its triggers) | AccessExclusive | everything, including reads |
| `ADD CONSTRAINT ... FOREIGN KEY ... NOT VALID` | ShareRowExclusive (both tables) | writes |
| `CREATE INDEX` (non-concurrent, on the table) | Share | writes |
| `CREATE/DROP INDEX CONCURRENTLY`, `VALIDATE CONSTRAINT` | ShareUpdateExclusive | other DDL and autovacuum, not reads or writes |
| `UPDATE` / `DELETE` / `INSERT` | RowExclusive | no other DML; conflicts with Share and stronger table locks, so a non-concurrent `CREATE INDEX`, an FK add or any AccessExclusive DDL queues behind running DML and then blocks new DML |


### Indexes (always CONCURRENTLY in prod)

```sql
-- Own file AND the only statement in it: golang-migrate sends a multi-statement file
-- as one implicit transaction, which CONCURRENTLY cannot run inside. No SET here either -
-- a lock_timeout would cancel the build into an INVALID index (see Rules).
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);

-- down
DROP INDEX CONCURRENTLY IF EXISTS idx_users_email;
```

Composite index column order: equality columns first, then range columns; most selective leftmost. A btree is scanned backward for a `DESC` sort, so the direction clause matters only for mixed-direction sorts.

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

The backfill must not run until the dual-writing app is on **every** replica, or the rows written by an old replica during the rollout stay NULL. When a consumer outside the team reads the old column, the contract step is blocked until that team cuts over - keep the old column synchronized with a trigger rather than shipping N+2 on schedule. An in-place `RENAME COLUMN` that already shipped is the same hazard in reverse: the previous image breaks on rollback until the old name is restored.

## golang-migrate Usage

```bash
migrate -path ./migrations -database "$DATABASE_URL" up
migrate -path ./migrations -database "$DATABASE_URL" down 1
migrate -path ./migrations -database "$DATABASE_URL" goto 6      # apply or roll back to exactly version 6
migrate -path ./migrations -database "$DATABASE_URL" version
migrate -path ./migrations -database "$DATABASE_URL" force <version>  # clear dirty state
```

### Embedding in Binary

```go
import (
    "embed"
    "errors"
    "fmt"

    "github.com/golang-migrate/migrate/v4"
    _ "github.com/golang-migrate/migrate/v4/database/postgres" // registers the postgres:// driver; pgx5:// is .../database/pgx/v5
    "github.com/golang-migrate/migrate/v4/source/iofs"
)

//go:embed migrations/*.sql
var migrationsFS embed.FS // the pattern is relative to this file's directory and cannot contain ..

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

Run migrations before starting the server, not concurrently. Use a single runner (a Job or a pre-upgrade hook - an init container runs in every pod of a Deployment, so it is a single runner only at `replicas: 1`) or rely on golang-migrate's advisory lock to prevent concurrent runs from racing. An init container on every replica means a dirty version crash-loops every pod - the runner is part of the plan.

## CI Validation

```bash
migrate -path ./migrations -database "$DATABASE_URL" up
migrate -path ./migrations -database "$DATABASE_URL" down 1
migrate -path ./migrations -database "$DATABASE_URL" up   # the newest file's down really reverses its up
```

## Edge Cases

- **Dirty state**: a failed migration leaves the version dirty. `force N` records N as *applied and clean* - it does not re-run it. Reverting a failed migration N therefore means `force N-1`, after removing whatever a non-transactional statement left behind (an INVALID index; transactional files rolled back on their own); `force N` silently skips the rest of that migration's work forever. Inspect the real schema (`\d`, `pg_index.indisvalid`) before choosing, because golang-migrate records only that N failed, never how far it got
- **Killed CONCURRENTLY**: a failed/cancelled `CREATE INDEX CONCURRENTLY` leaves an INVALID index (`pg_index.indisvalid = false`); re-running fails "already exists". `DROP INDEX CONCURRENTLY IF EXISTS` it first - a plain DROP takes AccessExclusiveLock
- **Empty down**: when a migration is truly irreversible, write a down that errors with an explanation rather than leaving it blank; when the inverse lives in another file (a VALIDATE's down), write a comment saying so
- **Large backfills**: batch via `WHERE id BETWEEN ... AND ...` to avoid long-running transactions and WAL bloat
- **Adding a CHECK value**: requires DROP + ADD + VALIDATE - plan for it when designing status columns

## Output Format

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Plan | `## Migration Plan` with `### Files`, `### Safety Assessment`, `### Rollback Plan`; the SQL for each file follows under `### <file name>` headings in `Files` order. A plan handed existing files that violate a Rule emits `## Findings` first; a requested change already shipped in an applied file gets no new file - its `Files` row is that version marked `(applied)` |
| Review | `## Findings`, then `## Migration Plan` describing the **corrected** files, then `### Pre-merge Queries` - the facts the diff cannot answer (row counts behind a NOT NULL, distinct values behind a new CHECK, whether a version is already applied somewhere) as runnable queries; a review that assumes them is a guess |
| Recovery | two opening lines `**Schema now:**` (applied statements, invalid indexes, dirty version) and `**First step:**` (the operator action that stops the bleeding - pause the rollout or pin the last good image - before any SQL), then `## Runbook` - numbered, each step one command or query, with the `force` ruling as its own step; when the repo's runner binary exposes no `force`/`goto`, the step runs the `migrate` CLI against the same DSN and says so - then `## Findings`, then `## Migration Plan` for the files still to run. A dirty version never completed, so it is not applied: `force` to the previous version and fix its file in place when no environment recorded that version as clean; otherwise ship the fix as a new version and `force` past the dirty one |

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

Cell values: one `Files` row per statement whose lock level differs from its file's others, otherwise one row per file - the lock is the unit that matters; a version's up row precedes its down row. A file the plan splits takes the next unused versions when nothing after it is applied anywhere (`000004` -> `000004`, `000005`, ...); once a later version is applied anywhere, the split appends after the highest version and the original file stays as a no-op marker - an applied version is never renumbered. `Version` is `n/a` for a row with no file. `Notes` records the deploy ordering the file depends on (`app dual-writing on every replica first`) and `(applied)` for a version already in production. `Type` is `DDL | DML | index | constraint | validate | none` - `none` for a deliberate no-op (a `SET`-only or comment-only down). `Down` is the down file's name, or `<missing>`, followed by its inverse statement in one clause. `Lock Level` is the Postgres lock name (`AccessExclusiveLock`, `ShareRowExclusiveLock`, `ShareUpdateExclusiveLock`, `ShareLock`, `RowExclusiveLock`, `none`). `Reversible?` is `Yes | Guarded | No | n/a` - `Guarded` when the down is destructive and refuses unless an operator opts in, `No` when it must raise an explanatory error, `n/a` when the down is a deliberate no-op because the inverse lives in another file; `unknown` when the inverse cannot be known from the input (the original FK definition is not supplied). A `Safety Assessment` row whose `Risk` is a fact the diff cannot answer has `Mitigation` = `ask: <who or which query>`. A backfill that matches zero rows is `[Recommend]`. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {what happens when this runs against production}
- Rule: {the migration rule violated}
- Fix: {the corrected SQL or file split}
```

`[Must]` when the migration cannot succeed, locks a hot table for a full scan or an unbounded lock wait, loses data, has no usable rollback, or leaves a dirty version; `[Recommend]` otherwise - judge by blast radius on the target table, not by matching the list. A `Guarded` down refuses by default; show the mechanism (a `DO $$ ... RAISE EXCEPTION $$` block gated on `current_setting('app.allow_destructive', true) = 'on'`, delivered on the runner's own session through the DSN (`options=-c app.allow_destructive=on`) - an operator's `SET LOCAL` on another connection never reaches it) rather than describing it. Cite `file:line` when the input carries line numbers; a missing down file is cited as `<version>.down.sql:<missing>`; a range is `file:start-end`. Order `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites (the same unbounded lock in three files) is one heading citing the first site, with the rest named on the `Defect:` line. A defect this skill does not own (the runner topology, an index the query layer needs, an image that cannot roll back) is still reported, never dropped: one block per such defect after the owned findings, in the same file-then-line order, labelled by the criteria above, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- `AutoMigrate` in production
- In-place column rename (no expand-contract)
- `DROP COLUMN/TABLE` without backup
- Mixed DDL+DML in one file
- `CREATE INDEX` without `CONCURRENTLY` on large tables
- `ALTER COLUMN SET NOT NULL` on a large table with no validated CHECK already in place (the CHECK is what lets PG12+ skip the scan)
- Missing down migrations
- A plain `SET lock_timeout` (session-scoped on the runner's connection) - always `SET LOCAL`
