---
name: node-migration-safety
description: Safe database migration patterns for Prisma and TypeORM. Zero-downtime DDL rules, deploy ordering (add column vs drop column), enum management, CI validation, and rollback strategies.
metadata:
  category: backend
  tags: [node, prisma, typeorm, migrations, database, zero-downtime]
user-invocable: false
---

# Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Creating or reviewing database migrations in Prisma or TypeORM projects
- Planning schema changes that must be deployed with zero downtime
- Determining safe deploy ordering for DDL changes during rolling deployments
- Adding enums, indexes, or constraints to existing tables

## Rules

- Every generated migration must be reviewed before applying
- Never use `prisma db push` or `synchronize: true` in production
- Data migrations must be separate from schema migrations
- All column additions start as nullable; add NOT NULL only after backfill completes

## Patterns

### Prisma Migrations (NestJS)

- `prisma migrate dev` - development (creates + applies)
- `prisma migrate deploy` - production (applies only, no generation)
- Review every generated migration in `prisma/migrations/`
- Custom SQL in `migration.sql` for: CONCURRENTLY indexes, partial indexes, data backfill
- Rollback: Prisma has no built-in down migration - plan forward-only migrations that are backward-compatible, or use manual SQL down scripts
- `prisma migrate reset` - for test environments only
- CI: run `prisma migrate deploy` in pipeline

### TypeORM Migrations (Express)

- `typeorm migration:generate` - generates from entity diff
- `typeorm migration:create` - creates empty migration for custom SQL
- `typeorm migration:run` - applies pending
- `typeorm migration:revert` - reverts last applied
- Always review generated migrations
- `synchronize: true` - NEVER in production

### Zero-Downtime DDL Rules

- Add columns nullable first, backfill, then add NOT NULL constraint
- Create indexes CONCURRENTLY (avoids table locks on large tables)
- Never rename columns directly - use expand-contract pattern
- Separate data migrations from schema migrations
- Test: migrate up then migrate down (TypeORM) or verify backward compatibility (Prisma)

### Deploy Order Safety

The order of code deployment relative to migration execution determines whether a rolling deploy is safe:

| Change Type    | Correct Order                                     | Wrong Order                                                    |
| -------------- | ------------------------------------------------- | -------------------------------------------------------------- |
| Add column     | Migration first, then code                        | Code first (code references non-existent column)               |
| Drop column    | Code first (remove references), then migration    | Migration first (app breaks reading dropped column)            |
| Rename column  | Expand-contract required (never in single deploy) | Rename + code in same deploy (rolling deploy partially broken) |
| Add index      | Migration first (additive, safe)                  | No ordering risk                                               |
| Add enum value | Migration first, then code that uses new value    | Code first (writes unknown enum value)                         |

For Prisma (no built-in rollback), plan each migration as forward-only and backward-compatible with the previous deployed code version:

```bash
# Deploy sequence for DROP COLUMN:
# 1. Deploy code that no longer reads/writes the column
# 2. Verify no references in production logs
# 3. Run: prisma migrate deploy (drops column)
```

### Enum Management

Adding a new value to a Prisma enum generates an `ALTER TYPE` statement. This is safe for PostgreSQL but requires attention:

```prisma
// Adding CANCELLED to an existing OrderStatus enum
enum OrderStatus {
  PENDING
  CONFIRMED
  SHIPPED
  DELIVERED
  CANCELLED  // new value
}
```

Generated migration adds the enum value:

```sql
ALTER TYPE "OrderStatus" ADD VALUE 'CANCELLED';
```

This is a non-reversible operation in PostgreSQL - you cannot remove an enum value. Plan enum values carefully.

For TypeORM, enum values are stored in `@Column({ type: 'enum', enum: OrderStatus })`. Adding a value requires a migration:

```sql
ALTER TYPE "order_status_enum" ADD VALUE 'CANCELLED';
```

### Index Strategy

Add indexes on:

- Foreign key columns (e.g., `customerId` on orders table)
- Frequently filtered columns (e.g., `status`, `createdAt`)
- Unique constraint columns (e.g., `idempotencyKey`)
- Composite indexes for common query patterns (e.g., `[customerId, status]`)

For large tables, create indexes CONCURRENTLY:

```sql
-- In Prisma custom migration SQL:
CREATE INDEX CONCURRENTLY idx_orders_customer_status ON "Order" ("customerId", "status");
```

## Edge Cases

- **Migration already applied partially (crash mid-migration)**: Prisma marks failed migrations in `_prisma_migrations` table - fix the SQL and run `prisma migrate resolve`. TypeORM: check which statements succeeded and manually complete or revert.
- **Multiple developers creating migrations simultaneously**: Merge conflicts in migration files. Prisma: may need `prisma migrate resolve` after merge. TypeORM: ensure migration timestamps do not conflict.
- **Large table migrations**: Adding a column or index on a large table can lock it. Use `CONCURRENTLY` for indexes; for column changes, consider batched backfill in a separate migration.
- **Enum value removal**: PostgreSQL does not support removing enum values. To "remove" a value, create a new enum type without it, migrate the column, and drop the old type - this requires a multi-step migration.

## Output Format

```
## Migration Plan

### Schema Changes
| Change | Type | Table | Column | Safe Order |
|--------|------|-------|--------|------------|

### Indexes
| Index | Table | Columns | Type | CONCURRENTLY |
|-------|-------|---------|------|--------------|

### Deploy Sequence
1. [First migration/code change]
2. [Second migration/code change]
3. [Verification step]

### Rollback Plan
[Forward-only compatibility notes or revert steps]
```

## Avoid

- `prisma db push` in production (no migration history, can lose data)
- `synchronize: true` in production (TypeORM auto-syncs schema without migration history - can drop columns)
- Generated migrations without review
- Data manipulation inside schema migrations
- Destructive migration (DROP COLUMN) before code is updated to remove the reference
- Adding NOT NULL columns without a default or backfill (fails on existing rows)
- Removing enum values without the multi-step type migration
