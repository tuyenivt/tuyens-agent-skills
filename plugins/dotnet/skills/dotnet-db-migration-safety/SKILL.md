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

- Never rename columns or tables in a single migration — use expand-then-contract
- Always apply migrations out-of-band (not on app startup in production)
- Make all new columns nullable or with a default value — never NOT NULL without a default
- Keep migrations small and focused: one concern per migration
- Test migrations against a copy of the production schema before deploying
- Never delete a migration that has been applied to any environment — add a new revert migration instead
- Use `migrationBuilder.Sql()` for data migrations; keep them idempotent

## Expand-Then-Contract Pattern

**Phase 1 — Expand** (deploy with old + new code both working):

```csharp
migrationBuilder.AddColumn<string>(
    name: "email_address",
    table: "users",
    nullable: true);       // nullable while backfill happens
```

**Phase 2 — Backfill** (data migration, separate migration file):

```csharp
migrationBuilder.Sql(@"
    UPDATE users SET email_address = email WHERE email_address IS NULL
");
```

**Phase 3 — Contract** (after old code is fully retired):

```csharp
migrationBuilder.AlterColumn<string>(
    name: "email_address",
    table: "users",
    nullable: false);      // tighten constraint once all rows are populated

migrationBuilder.DropColumn(name: "email", table: "users");
```

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
