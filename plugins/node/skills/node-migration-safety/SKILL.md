---
name: node-migration-safety
description: Safe DB migration patterns for Prisma / TypeORM: zero-downtime DDL, deploy ordering, enum management, CI validation, rollback.
metadata:
  category: backend
  tags: [node, prisma, typeorm, migrations, database, zero-downtime]
user-invocable: false
---

# Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Creating or reviewing Prisma/TypeORM migrations
- Planning zero-downtime schema changes under rolling deploys
- Adding enums, indexes, or constraints to existing tables

## Rules

- Review every generated migration before applying
- Never use `prisma db push` or `synchronize: true` against production (no history, can drop data)
- Separate data migrations from schema migrations
- Add columns nullable, backfill, then add NOT NULL
- Create indexes on large tables with `CONCURRENTLY`
- Never rename columns in a single deploy - use expand-contract

## Patterns

### Prisma vs TypeORM Commands

| Action            | Prisma                     | TypeORM                       |
| ----------------- | -------------------------- | ----------------------------- |
| Generate from diff| `prisma migrate dev`       | `typeorm migration:generate`  |
| Custom SQL        | edit `migration.sql`       | `typeorm migration:create`    |
| Apply (prod/CI)   | `prisma migrate deploy`    | `typeorm migration:run`       |
| Revert            | forward-only (manual down) | `typeorm migration:revert`    |
| Reset (test only) | `prisma migrate reset`     | drop schema + re-run          |

Prisma has no built-in down migration: write each migration forward-only and backward-compatible with the previously deployed code.

### Zero-Downtime Deploy Order

| Change Type    | Correct Order                                     | Wrong Order                                       |
| -------------- | ------------------------------------------------- | ------------------------------------------------- |
| Add column     | Migration first, then code                        | Code first (references missing column)            |
| Drop column    | Code first (remove refs), then migration          | Migration first (app reads dropped column)        |
| Rename column  | Expand-contract over multiple deploys             | Rename + code in one deploy                       |
| Add index      | Migration first (additive)                        | n/a                                               |
| Add enum value | Migration first, then code using new value        | Code first (writes unknown value)                 |

### Enum Management (PostgreSQL)

Adding a value generates `ALTER TYPE "OrderStatus" ADD VALUE 'CANCELLED'` (same for Prisma and TypeORM). Safe and additive, but PostgreSQL cannot use the new value in the same transaction that adds it - put any `UPDATE`/backfill using the value in a separate migration. Removal is **not supported** - to drop a value, create a new type, migrate the column, drop the old type.

### Index Strategy

Index foreign keys, frequently filtered columns (`status`, `createdAt`), unique constraint columns, and composite patterns (`[customerId, status]`). For large tables, use custom SQL:

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_status ON "Order" ("customerId", "status");
```

`CONCURRENTLY` must run outside a transaction. Prisma: place in a standalone `migration.sql` with no other statements (Prisma does not wrap migrations in transactions). TypeORM wraps migrations in transactions by default - run the index migration with `migrationsTransactionMode: "none"`, isolated in its own deploy.

### Edge Cases

- **Failed mid-migration**: Prisma marks failed entries in `_prisma_migrations`; fix SQL, run `prisma migrate resolve`. TypeORM: inspect, manually complete or revert.
- **Concurrent migrations from multiple devs**: resolve timestamp/filename conflicts before merge; Prisma may need `migrate resolve`.
- **Large-table column changes**: batched backfill in a separate migration; avoid table rewrites.

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

- Applying generated migrations without review
- Data manipulation inside schema migrations
- `DROP COLUMN` before code stops referencing it
- Adding `NOT NULL` columns without default or backfill
- Removing enum values without the multi-step type migration
