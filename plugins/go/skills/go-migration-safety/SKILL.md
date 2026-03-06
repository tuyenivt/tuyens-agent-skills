---
name: go-migration-safety
description: "Safe migration patterns with golang-migrate and PostgreSQL. File naming, up/down pairs, zero-downtime DDL, embedding in Go binary, CI validation. Never use GORM AutoMigrate in production."
user-invocable: false
---

# Go Migration Safety

## When to Use

- Setting up database migrations for a new Go service
- Reviewing a migration for production safety (locking risks, rollback coverage)
- Debugging a failed migration or a schema drift issue
- Embedding migrations in the Go binary for automated startup sequencing

## Rules

- Never use `GORM AutoMigrate` in production - it can drop columns, cause table locks, and has no rollback
- Every `up` migration must have a matching `down` migration
- Never mix DDL (schema changes) and DML (data changes) in the same file - they have different rollback characteristics
- Never write a `down` that drops a column or table without a backup or a compensating migration - data loss is permanent
- Zero-downtime DDL: add before delete, never rename in place

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

A single `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT ...` locks the table in older Postgres. Use expand-contract:

```sql
-- Step 1: add nullable (migration N)
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- Step 2: backfill in a separate DML migration (migration N+1)
UPDATE users SET phone = '' WHERE phone IS NULL;

-- Step 3: add constraint (migration N+2)
ALTER TABLE users ALTER COLUMN phone SET NOT NULL;
```

### Adding an Index (use CONCURRENTLY)

```sql
-- up: CONCURRENTLY builds without locking writes
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);

-- down:
DROP INDEX CONCURRENTLY IF EXISTS idx_users_email;
```

Note: `CREATE INDEX CONCURRENTLY` cannot run inside a transaction. golang-migrate runs each file in a transaction by default - add `-- migrate: no transaction` at the top of the file:

```sql
-- migrate: no transaction
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);
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

## Anti-Patterns

```sql
-- Bad: GORM AutoMigrate in production startup
db.AutoMigrate(&User{}, &Order{})

-- Bad: down migration that destroys data without backup step
-- 000005_add_user_type.down.sql
ALTER TABLE users DROP COLUMN user_type; -- no backup, no compensating migration

-- Bad: mixing DDL and DML (different rollback behavior)
ALTER TABLE users ADD COLUMN score INT DEFAULT 0;
UPDATE users SET score = calculate_score(id); -- DML in same file

-- Bad: in-place rename (breaks running app instances)
ALTER TABLE users RENAME COLUMN name TO full_name; -- running app breaks immediately

-- Bad: adding NOT NULL without a default or backfill step
ALTER TABLE users ADD COLUMN phone VARCHAR(20) NOT NULL; -- fails if table has rows
```

## Avoid

- `AutoMigrate` outside of local development
- In-place column renames without expand-contract
- `DROP COLUMN` or `DROP TABLE` without data backup or compensating migration
- Mixing DDL and DML in the same migration file
- `CREATE INDEX` without `CONCURRENTLY` on large tables in production
- Skipping `down` migrations - they are required for safe rollbacks
