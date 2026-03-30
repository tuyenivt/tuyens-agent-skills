---
name: go-migration-safety
description: "Safe migration patterns with golang-migrate and PostgreSQL. File naming, up/down pairs, zero-downtime DDL, CHECK constraints, embedding in Go binary, CI validation."
metadata:
  category: backend
  tags: [go, migration, postgresql, golang-migrate, ddl, zero-downtime]
user-invocable: false
---

# Go Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Setting up database migrations for a new Go service
- Reviewing a migration for production safety (locking risks, rollback coverage)
- Adding CHECK constraints for status/enum columns
- Debugging a failed migration or a schema drift issue
- Embedding migrations in the Go binary for automated startup sequencing

## Rules

- Never use `GORM AutoMigrate` in production - it can drop columns, cause table locks, and has no rollback
- Every `up` migration must have a matching `down` migration
- Never mix DDL (schema changes) and DML (data changes) in the same file - they have different rollback characteristics
- Never write a `down` that drops a column or table without a backup or a compensating migration - data loss is permanent
- Zero-downtime DDL: add before delete, never rename in place
- `CREATE INDEX CONCURRENTLY` and `VALIDATE CONSTRAINT` cannot run inside a transaction - use `-- migrate: no transaction` at the top of those files

## File Naming

```
migrations/
  000001_create_users.up.sql
  000001_create_users.down.sql
  000002_add_email_index.up.sql
  000002_add_email_index.down.sql
  000003_add_orders_table.up.sql
  000003_add_orders_table.down.sql
```

Format: `{version}_{description}.{direction}.sql`

- Version: zero-padded integer, monotonically increasing
- Description: snake_case, describes what the migration does
- Direction: `up` (apply) or `down` (revert)

## Zero-Downtime DDL Patterns

### Adding a Column (safe)

```sql
-- up: adding a nullable column is safe - no table lock, no data rewrite
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- down:
ALTER TABLE users DROP COLUMN phone;
```

### Adding a NOT NULL Column (multi-step)

A single `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT ...` or `ALTER COLUMN SET NOT NULL` acquires an `AccessExclusiveLock` that blocks all reads and writes on large tables. Use NOT VALID + VALIDATE CONSTRAINT for zero-downtime:

```sql
-- Step 1: add nullable column (migration N)
-- migrate: no transaction not needed here (DDL inside transaction is fine)
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- Step 2: backfill existing rows (migration N+1, separate DML migration)
-- Run in batches for large tables; golang-migrate runs this in a transaction
UPDATE users SET phone = '' WHERE phone IS NULL;

-- Step 3: add CHECK constraint with NOT VALID (migration N+2)
-- NOT VALID skips scanning existing rows - no table lock, instant
-- migrate: no transaction
ALTER TABLE users ADD CONSTRAINT users_phone_not_null
    CHECK (phone IS NOT NULL) NOT VALID;

-- Step 4: validate existing rows (migration N+3)
-- VALIDATE CONSTRAINT acquires ShareUpdateExclusiveLock - allows concurrent reads/writes
-- migrate: no transaction
ALTER TABLE users VALIDATE CONSTRAINT users_phone_not_null;
```

Do NOT use `ALTER TABLE users ALTER COLUMN phone SET NOT NULL` on tables with millions of rows - it acquires `AccessExclusiveLock` and scans the entire table.

**PostgreSQL 11+ shortcut**: `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT 'value'` is instant for new columns (no table rewrite) because PostgreSQL stores the default in the catalog. This is safe for new columns only - it does NOT apply to `ALTER COLUMN SET NOT NULL` on existing columns.

### Adding a CHECK Constraint (status/enum columns)

For status columns with known valid values, add a CHECK constraint to prevent invalid data at the database level:

```sql
-- up: NOT VALID skips scanning existing rows - instant, no lock
-- migrate: no transaction
ALTER TABLE payments ADD CONSTRAINT payments_status_check
    CHECK (status IN ('pending', 'processing', 'completed', 'failed')) NOT VALID;

-- Separate migration to validate existing rows:
-- migrate: no transaction
ALTER TABLE payments VALIDATE CONSTRAINT payments_status_check;

-- down:
ALTER TABLE payments DROP CONSTRAINT payments_status_check;
```

When adding a new status value later, drop and re-create the constraint:

```sql
-- migrate: no transaction
ALTER TABLE payments DROP CONSTRAINT payments_status_check;
ALTER TABLE payments ADD CONSTRAINT payments_status_check
    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'refunded')) NOT VALID;
ALTER TABLE payments VALIDATE CONSTRAINT payments_status_check;
```

### Adding an Index (use CONCURRENTLY)

```sql
-- up: CONCURRENTLY builds without locking writes
-- migrate: no transaction
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);

-- down:
DROP INDEX CONCURRENTLY IF EXISTS idx_users_email;
```

Note: `CREATE INDEX CONCURRENTLY` cannot run inside a transaction. golang-migrate runs each file in a transaction by default - add `-- migrate: no transaction` at the top of the file.

### Composite Indexes

Common for lookups that filter on multiple columns (e.g., payments by user + status):

```sql
-- migrate: no transaction
CREATE INDEX CONCURRENTLY idx_payments_user_status ON payments(user_id, status);
```

Column order matters: put the most selective (highest cardinality) column first, or the column that appears in equality conditions before range conditions.

### Unique Index for Idempotency Keys

```sql
-- migrate: no transaction
CREATE UNIQUE INDEX CONCURRENTLY idx_payments_idempotency_key ON payments(idempotency_key);
```

### Renaming a Column (expand-contract, never in-place rename)

```sql
-- Step 1: add new column (migration N)
ALTER TABLE users ADD COLUMN full_name VARCHAR(255);

-- Step 2: deploy app code that writes to both old and new columns

-- Step 3: backfill new column from old (migration N+1)
UPDATE users SET full_name = name WHERE full_name IS NULL;

-- Step 4: deploy app code that reads from new column only

-- Step 5: drop old column (migration N+2)
ALTER TABLE users DROP COLUMN name;
```

## golang-migrate Usage

### CLI

```bash
# Apply all pending migrations
migrate -path ./migrations -database "postgres://user:pass@localhost/dbname?sslmode=disable" up

# Roll back the last migration
migrate -path ./migrations -database "..." down 1

# Check current version
migrate -path ./migrations -database "..." version

# Force set version (use when dirty state after failed migration)
migrate -path ./migrations -database "..." force 3
```

### Embedding in Go Binary

```go
import (
    "embed"
    "github.com/golang-migrate/migrate/v4"
    _ "github.com/golang-migrate/migrate/v4/database/postgres"
    "github.com/golang-migrate/migrate/v4/source/iofs"
)

//go:embed migrations/*.sql
var migrationsFS embed.FS

func RunMigrations(dsn string) error {
    src, err := iofs.New(migrationsFS, "migrations")
    if err != nil {
        return fmt.Errorf("migrations source: %w", err)
    }

    m, err := migrate.NewWithSourceInstance("iofs", src, dsn)
    if err != nil {
        return fmt.Errorf("migrate init: %w", err)
    }
    defer m.Close()

    if err := m.Up(); err != nil && !errors.Is(err, migrate.ErrNoChange) {
        return fmt.Errorf("migrate up: %w", err)
    }
    return nil
}
```

### Application Startup Sequencing

Run migrations before starting the HTTP server, not concurrently:

```go
func main() {
    cfg := loadConfig()

    // 1. Run migrations first
    if err := RunMigrations(cfg.DatabaseURL); err != nil {
        log.Fatalf("migrations failed: %v", err)
    }

    // 2. Start application only after migrations succeed
    r := setupRouter(cfg)
    if err := r.Run(cfg.Addr); err != nil {
        log.Fatalf("server: %v", err)
    }
}
```

## CI Validation

Test migrations in CI to catch errors before they reach production:

```bash
# Apply all migrations up
migrate -path ./migrations -database "$TEST_DB_URL" up

# Roll back one step
migrate -path ./migrations -database "$TEST_DB_URL" down 1

# Re-apply to verify idempotency
migrate -path ./migrations -database "$TEST_DB_URL" up
```

This catches: syntax errors, missing down migrations, and migrations that fail on re-apply.

## Edge Cases

- **Dirty migration state**: if a migration fails mid-way, golang-migrate marks the version as "dirty" - use `migrate force <version>` to reset to the last known good version, then fix and re-run
- **Concurrent migration runs**: multiple app instances starting simultaneously can race on migrations - use a single migration runner (init container, CLI job) or rely on golang-migrate's advisory lock
- **Empty down migration**: if a migration cannot be safely reversed (e.g., dropped column with data), write a down file that raises an error explaining why manual intervention is needed rather than leaving it empty
- **Large table backfills**: batch `UPDATE` statements to avoid long-running transactions and WAL bloat - use `WHERE id BETWEEN ... AND ...` or a cursor-based approach
- **Adding a status value to CHECK constraint**: requires dropping and re-creating the constraint (see pattern above). Plan for this when designing status columns - consider whether the constraint is worth the maintenance cost

## Output Format

```
## Migration Plan

### Migration Files
| Version | File | Type | Lock Level | Notes |
|---------|------|------|-----------|-------|
| 000N | create_payments | DDL | ShareRowExclusive | new table |
| 000N+1 | add_payments_status_check | DDL | None (NOT VALID) | CHECK constraint |
| 000N+2 | validate_payments_status_check | DDL | ShareUpdateExclusive | validate existing rows |
| 000N+3 | add_payments_indexes | DDL | None (CONCURRENTLY) | idempotency_key unique, user_id+status composite |

### Safety Assessment
| Risk | Mitigation |
|------|-----------|
| Table lock on large table | {NOT VALID + VALIDATE / CONCURRENTLY / batched backfill} |
| Data loss on rollback | {compensating migration / backup step} |

### Rollback Plan
[down migration description for each step]
```

## Avoid

- `AutoMigrate` outside of local development
- In-place column renames without expand-contract
- `DROP COLUMN` or `DROP TABLE` without data backup or compensating migration
- Mixing DDL and DML in the same migration file
- `CREATE INDEX` without `CONCURRENTLY` on large tables in production
- Skipping `down` migrations - they are required for safe rollbacks
- `ALTER COLUMN SET NOT NULL` on large tables - use CHECK constraint with NOT VALID instead
