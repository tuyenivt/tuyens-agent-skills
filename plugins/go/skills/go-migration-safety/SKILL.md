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
- Never write a destructive `down` (DROP COLUMN/TABLE with data) without backup or compensating migration
- Zero-downtime DDL: add before delete; expand-contract, never in-place rename
- golang-migrate does **not** wrap migrations in transactions: `CREATE INDEX CONCURRENTLY` / `VALIDATE CONSTRAINT` just need their own file (no directive exists - `NO TRANSACTION` annotations belong to goose/dbmate). Conversely, multi-statement DDL that must be atomic needs explicit `BEGIN; ... COMMIT;` in the file - otherwise a mid-file failure leaves partial DDL plus a dirty version

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

Same NOT VALID + VALIDATE pattern. To add a new status value, drop and re-create the constraint.

### Indexes (always CONCURRENTLY in prod)

```sql
-- own file - golang-migrate runs it without a transaction, which CONCURRENTLY requires
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);

-- down
DROP INDEX CONCURRENTLY IF EXISTS idx_users_email;
```

Composite index column order: equality columns first, then range columns; most selective leftmost.

### Renaming a Column (expand-contract)

```sql
-- N:   ADD COLUMN full_name
-- App: dual-write old + new
-- N+1: UPDATE users SET full_name = name WHERE full_name IS NULL
-- App: read full_name only
-- N+2: DROP COLUMN name
```

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

- **Dirty state**: failed mid-migration leaves the version "dirty" - use `force <version>` to reset, fix, re-run
- **Killed CONCURRENTLY**: a failed/cancelled `CREATE INDEX CONCURRENTLY` leaves an INVALID index (`pg_index.indisvalid = false`); re-running fails "already exists". `DROP INDEX CONCURRENTLY IF EXISTS` it first - a plain DROP takes AccessExclusiveLock
- **Empty down**: when a migration is truly irreversible, write a down that errors with an explanation rather than leaving it blank
- **Large backfills**: batch via `WHERE id BETWEEN ... AND ...` to avoid long-running transactions and WAL bloat
- **Adding a CHECK value**: requires DROP + ADD + VALIDATE - plan for it when designing status columns

## Output Format

```
## Migration Plan

### Files
| Version | File | Type | Lock Level | Notes |

### Safety Assessment
| Risk | Mitigation |

### Rollback Plan
[down description per step]
```

## Avoid

- `AutoMigrate` in production
- In-place column rename (no expand-contract)
- `DROP COLUMN/TABLE` without backup
- Mixed DDL+DML in one file
- `CREATE INDEX` without `CONCURRENTLY` on large tables
- `ALTER COLUMN SET NOT NULL` on large tables - use NOT VALID CHECK
- Missing down migrations
