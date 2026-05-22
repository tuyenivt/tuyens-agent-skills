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
- Designing rollback-safe migration sequences for zero-downtime deploys

## Rules

- One concern per migration; each phase in its own file
- New columns are nullable or have a default - never add NOT NULL without a default to an existing table
- Renames and drops use expand-then-contract; old name removed only after no deployed code references it
- Tightening constraints on populated tables uses `NOT VALID` + `VALIDATE` (PostgreSQL) or `WITH (ONLINE = ON)` (SQL Server) via `migrationBuilder.Sql()`
- Index creation on large tables uses `CONCURRENTLY` (PostgreSQL) or `ONLINE = ON` (SQL Server)
- Data migrations use `migrationBuilder.Sql()` and are idempotent (re-runnable without corruption)
- Migrations are applied out-of-band, not on app startup
- Applied migrations are never edited or deleted; revert via a new migration

## Patterns

### Expand-Then-Contract (rename or replace)

Three migrations deployed across three releases. Old code keeps running until Phase 3.

Phase 1 - Expand (add nullable target column):

```csharp
migrationBuilder.AddColumn<string>("email_address", "users", nullable: true);
```

Phase 2 - Backfill (idempotent data migration):

```csharp
migrationBuilder.Sql(
    "UPDATE users SET email_address = email " +
    "WHERE email_address IS NULL AND email IS NOT NULL;");
```

Phase 3 - Contract (only after all deployed code reads `email_address`):

```csharp
// Separate migration: enforce NOT NULL (see below for large tables)
migrationBuilder.AlterColumn<string>("email_address", "users", nullable: false);

// Separate migration: drop the old column
migrationBuilder.DropColumn("email", "users");
```

### NOT NULL on Large Tables (PostgreSQL)

`AlterColumn(nullable: false)` issues `ALTER COLUMN SET NOT NULL`, taking `AccessExclusiveLock` and scanning every row - blocks reads and writes. Use a `NOT VALID` CHECK constraint, then validate separately. EF Core does not generate this; use `migrationBuilder.Sql()`.

Migration A - add constraint (instant, no row scan):

```csharp
migrationBuilder.Sql(@"
    ALTER TABLE users
    ADD CONSTRAINT users_email_address_not_null
    CHECK (email_address IS NOT NULL) NOT VALID;");
```

Migration B - validate (allows concurrent reads/writes):

```csharp
migrationBuilder.Sql(
    "ALTER TABLE users VALIDATE CONSTRAINT users_email_address_not_null;");
```

SQL Server equivalent: `ALTER TABLE ... ADD CONSTRAINT ... WITH (ONLINE = ON)` (Enterprise Edition).

### Index on Large Tables

```csharp
// Bad - locks the table against writes during build
migrationBuilder.CreateIndex("ix_orders_created_at", "orders", "created_at");

// Good - PostgreSQL concurrent build, no write lock
migrationBuilder.Sql("CREATE INDEX CONCURRENTLY ix_orders_created_at ON orders(created_at);");
```

`CONCURRENTLY` cannot run inside a transaction; configure the migration with `migrationBuilder.Sql(..., suppressTransaction: true)`.

### Apply Migrations

```bash
# Out-of-band, before deploying new app code
dotnet ef database update --connection "$CONNECTION_STRING"
```

## Output Format

When proposing a migration plan:

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
- Combining schema and data changes in one migration
- `AlterColumn(nullable: false)` on tables over ~1M rows without `NOT VALID` + `VALIDATE`
- Creating non-concurrent indexes on large tables
- Editing or squashing migrations already applied to any shared environment
