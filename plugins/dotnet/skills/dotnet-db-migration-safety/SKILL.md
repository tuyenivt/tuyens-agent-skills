---
name: dotnet-db-migration-safety
description: EF Core migration safety, zero-downtime DDL patterns, and rollback strategies for .NET 8
metadata:
  category: backend
  tags: [ef-core, migrations, zero-downtime, ddl, database]
user-invocable: false
---

# Database Migration Safety

## When to Use

- Adding, renaming, or removing columns and tables
- Making schema changes in a zero-downtime deployment pipeline
- Designing rollback-safe migration sequences

## Rules

- Never rename columns or tables in a single migration - use expand-then-contract
- Always apply migrations out-of-band (not on app startup in production)
- Make all new columns nullable or with a default value - never NOT NULL without a default
- Keep migrations small and focused: one concern per migration
- Test migrations against a copy of the production schema before deploying
- Never delete a migration that has been applied to any environment - add a new revert migration instead
- Use `migrationBuilder.Sql()` for data migrations; keep them idempotent

## Expand-Then-Contract Pattern

**Phase 1 - Expand** (deploy with old + new code both working):

```csharp
migrationBuilder.AddColumn<string>(
    name: "email_address",
    table: "users",
    nullable: true);       // nullable while backfill happens
```

**Phase 2 - Backfill** (data migration, separate migration file):

```csharp
migrationBuilder.Sql(@"
    UPDATE users SET email_address = email WHERE email_address IS NULL
");
```

**Phase 3 - Contract** (after old code is fully retired):

```csharp
migrationBuilder.AlterColumn<string>(
    name: "email_address",
    table: "users",
    nullable: false);      // tighten constraint once all rows are populated

migrationBuilder.DropColumn(name: "email", table: "users");
```

### NOT NULL on Large Tables (PostgreSQL)

`AlterColumn nullable: false` maps to `ALTER COLUMN SET NOT NULL`, which acquires an `AccessExclusiveLock` and scans every row. On tables with millions of rows this blocks reads and writes for seconds or longer.

Use NOT VALID + VALIDATE CONSTRAINT instead - this skips scanning existing rows (no lock) and validates separately with a `ShareUpdateExclusiveLock` that allows concurrent reads and writes:

```csharp
// Phase 3a: Add CHECK constraint without scanning existing rows (instant, no lock)
migrationBuilder.Sql(@"
    ALTER TABLE users
    ADD CONSTRAINT users_email_address_not_null
    CHECK (email_address IS NOT NULL) NOT VALID;
");

// Phase 3b: Validate existing rows in a separate migration
// (ShareUpdateExclusiveLock - allows concurrent reads and writes)
migrationBuilder.Sql(@"
    ALTER TABLE users
    VALIDATE CONSTRAINT users_email_address_not_null;
");
```

Each phase goes in its own migration file so they can be deployed separately. On SQL Server, the equivalent is `WITH (ONLINE = ON)` on index/constraint operations, which is enabled by default for Enterprise Edition.

Note: EF Core does not generate NOT VALID constraints automatically - always use `migrationBuilder.Sql()` for this pattern.

## Apply Migrations Safely

```bash
# Apply pending migrations without starting the app
dotnet ef database update --connection "$CONNECTION_STRING"

# Or via a dedicated CLI tool in CI/CD
dotnet run --project src/Migrator -- migrate
```

## Avoid

- `Database.MigrateAsync()` in `Program.cs` for production apps (races, permission issues)
- Dropping a column while code still references it
- Adding a NOT NULL column without a default to an existing table
- Squashing migrations that have been applied to production
