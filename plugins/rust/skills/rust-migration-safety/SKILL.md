---
name: rust-migration-safety
description: "Safe migration patterns with sqlx-cli and PostgreSQL. File naming, reversible migrations, zero-downtime DDL, embedded migrations, CI validation."
user-invocable: false
---

# Rust Migration Safety

## When to Use

- Setting up database migrations for a new Rust service
- Reviewing a migration for production safety (locking risks, rollback coverage)
- Debugging a failed migration or a schema drift issue
- Embedding migrations in the Rust binary for automated startup sequencing

## Rules

- Use `sqlx-cli` for migration management - compile-time checked and versioned
- Every migration should be reversible when possible (up + down in separate files, or `IF EXISTS` guards)
- Never mix DDL (schema changes) and DML (data changes) in the same file - they have different rollback characteristics
- Zero-downtime DDL: add before delete, never rename in place
- Test migrations in CI before production

## File Naming

```
migrations/
  20240101000000_create_users.up.sql
  20240101000000_create_users.down.sql
  20240102000000_add_email_index.up.sql
  20240102000000_add_email_index.down.sql
  20240103000000_add_orders_table.up.sql
  20240103000000_add_orders_table.down.sql
```

Format: `{timestamp}_{description}.{direction}.sql`

- Timestamp: `YYYYMMDDHHMMSS` format, monotonically increasing
- Description: snake_case, describes what the migration does
- Direction: `up` (apply) or `down` (revert)

## Zero-Downtime DDL Patterns

### Adding a Column (safe)

```sql
-- up: adding a nullable column is safe - no table lock, no data rewrite
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- down:
ALTER TABLE users DROP COLUMN IF EXISTS phone;
```

### Adding a NOT NULL Column (multi-step)

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
-- sqlx does not wrap in transaction by default for .up.sql, so CONCURRENTLY works
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email ON users(email);

-- down:
DROP INDEX CONCURRENTLY IF EXISTS idx_users_email;
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

## sqlx-cli Usage

### CLI Commands

```bash
# Install sqlx-cli
cargo install sqlx-cli --no-default-features --features postgres

# Create a new migration
sqlx migrate add create_users

# Apply all pending migrations
sqlx migrate run --database-url "$DATABASE_URL"

# Revert the last migration
sqlx migrate revert --database-url "$DATABASE_URL"

# Check migration status
sqlx migrate info --database-url "$DATABASE_URL"
```

### Embedded Migrations in Rust Binary

```rust
use sqlx::migrate::Migrator;
use sqlx::PgPool;

static MIGRATOR: Migrator = sqlx::migrate!("./migrations");

async fn run_migrations(pool: &PgPool) -> anyhow::Result<()> {
    MIGRATOR.run(pool).await?;
    Ok(())
}
```

### Application Startup Sequencing

Run migrations before starting the HTTP server, not concurrently:

```rust
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let pool = PgPoolOptions::new()
        .max_connections(25)
        .connect(&std::env::var("DATABASE_URL")?)
        .await?;

    // 1. Run migrations first
    run_migrations(&pool).await?;

    // 2. Start application only after migrations succeed
    let app = build_router(pool);
    serve(app).await
}
```

## CI Validation

Test migrations in CI to catch errors before they reach production:

```bash
# Apply all migrations up
sqlx migrate run --database-url "$TEST_DB_URL"

# Revert one step
sqlx migrate revert --database-url "$TEST_DB_URL"

# Re-apply to verify idempotency
sqlx migrate run --database-url "$TEST_DB_URL"
```

This catches: syntax errors, missing down migrations, and migrations that fail on re-apply.

## Anti-Patterns

```sql
-- Bad: down migration that destroys data without backup step
ALTER TABLE users DROP COLUMN user_type;

-- Bad: mixing DDL and DML (different rollback behavior)
ALTER TABLE users ADD COLUMN score INT DEFAULT 0;
UPDATE users SET score = 100 WHERE role = 'admin';

-- Bad: in-place rename (breaks running app instances)
ALTER TABLE users RENAME COLUMN name TO full_name;

-- Bad: adding NOT NULL without a default or backfill step
ALTER TABLE users ADD COLUMN phone VARCHAR(20) NOT NULL;
```

## Avoid

- In-place column renames without expand-contract
- `DROP COLUMN` or `DROP TABLE` without data backup or compensating migration
- Mixing DDL and DML in the same migration file
- `CREATE INDEX` without `CONCURRENTLY` on large tables in production
- Skipping down migrations - they are required for safe rollbacks
