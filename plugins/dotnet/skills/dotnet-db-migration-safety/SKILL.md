---
name: dotnet-db-migration-safety
description: Enforce zero-downtime EF Core migrations - expand-then-contract, NOT VALID constraints, concurrent indexes, out-of-band apply.
metadata:
  category: backend
  tags: [ef-core, migrations, zero-downtime, ddl, database]
user-invocable: false
---

# Database Migration Safety

## When to Use

- Adding, renaming, dropping columns or tables
- Tightening constraints (NOT NULL, FK, CHECK) on populated tables
- Adding indexes to large tables
- Designing rollback-safe sequences for zero-downtime deploys

## Rules

- One concern per migration; schema and data changes in separate files.
- New columns are nullable or have a default - never add NOT NULL without a default to a populated table.
- Renames and drops use expand-then-contract; old name removed only after no deployed code references it.
- Tighten constraints on populated tables via `migrationBuilder.Sql()` using `NOT VALID` + `VALIDATE` (PostgreSQL) or `WITH (ONLINE = ON)` (SQL Server).
- Index large tables with `CREATE INDEX CONCURRENTLY` (PostgreSQL) or `WITH (ONLINE = ON)` (SQL Server).
- Data migrations are idempotent (re-runnable without corruption).
- Apply migrations out-of-band, never on app startup.
- Applied migrations are never edited or deleted; revert via a new migration.

## Patterns

### Expand-Then-Contract

Three migrations across three releases. Old code keeps running until Phase 3.

```csharp
// Phase 1 - Expand: add nullable target column
migrationBuilder.AddColumn<string>("email_address", "users", nullable: true);

// Phase 2 - Backfill (idempotent)
migrationBuilder.Sql(
    "UPDATE users SET email_address = email " +
    "WHERE email_address IS NULL AND email IS NOT NULL;");

// Phase 3 - Contract (after all deployed code reads email_address)
migrationBuilder.AlterColumn<string>("email_address", "users", nullable: false);
migrationBuilder.DropColumn("email", "users");
```

During the expand window deployed code must dual-write both columns (or new writes to the old column are lost from the new one). On a large table, tighten via the `NOT VALID` CHECK + `VALIDATE` path below instead of a bare `AlterColumn(nullable: false)`.

### NOT NULL on Large Tables (PostgreSQL)

`AlterColumn(nullable: false)` issues `ALTER COLUMN SET NOT NULL`, taking `AccessExclusiveLock` and scanning every row. Use a `NOT VALID` CHECK constraint, then validate separately. EF Core does not generate this; use `migrationBuilder.Sql()`.

```csharp
// Migration A - add constraint (instant, no row scan)
migrationBuilder.Sql(@"
    ALTER TABLE users
    ADD CONSTRAINT users_email_address_not_null
    CHECK (email_address IS NOT NULL) NOT VALID;");

// Migration B - validate (allows concurrent reads/writes)
migrationBuilder.Sql(
    "ALTER TABLE users VALIDATE CONSTRAINT users_email_address_not_null;");
```

SQL Server equivalent: `ALTER TABLE ... ADD CONSTRAINT ... WITH (ONLINE = ON)` (Enterprise). Once the CHECK is validated, `SET NOT NULL` on the column skips its own scan (PG12+); then drop the now-redundant CHECK.

### Index on Large Tables

```csharp
// Bad - locks the table against writes during build
migrationBuilder.CreateIndex("ix_orders_created_at", "orders", "created_at");

// Good - PostgreSQL concurrent build, no write lock
migrationBuilder.Sql(
    "CREATE INDEX CONCURRENTLY ix_orders_created_at ON orders(created_at);",
    suppressTransaction: true);
```

`CONCURRENTLY` cannot run inside a transaction - `suppressTransaction: true` is required (Postgres only; SQL Server `ONLINE = ON` is transactional and needs no suppression). Because it is non-atomic, a failed `CREATE INDEX CONCURRENTLY` leaves an INVALID index that still consumes space - `DROP INDEX` it before retrying.

### Apply Migrations

```bash
# Out-of-band, before deploying new app code
dotnet ef database update --connection "$CONNECTION_STRING"
```

## Output Format

```
Change: <description>
Risk: {Low | Moderate | High}        # High if locks a large table or breaks old code
Phases:
  1. <migration name> - <DDL/data step> - <release N>
  2. ...
Rollback: <how to revert each phase>
Locks: <expected lock type and table size impact>
```

## Avoid

- `Database.MigrateAsync()` in `Program.cs` for production (startup races, permission scope)
- `AlterColumn(nullable: false)` on tables over ~1M rows without `NOT VALID` + `VALIDATE`
- Editing or squashing migrations already applied to any shared environment
