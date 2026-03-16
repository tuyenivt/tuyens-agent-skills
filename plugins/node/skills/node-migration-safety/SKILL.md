---
name: node-migration-safety
description: Safe database migration patterns for Prisma and TypeORM. Zero-downtime DDL rules, deploy ordering (add column vs drop column), CI validation, and rollback strategies.
metadata:
  category: backend
  tags: [node, prisma, typeorm, migrations, database, zero-downtime]
user-invocable: false
---

# Migration Safety

## When to Use

- Creating or reviewing database migrations in Prisma or TypeORM projects
- Planning schema changes that must be deployed with zero downtime
- Determining safe deploy ordering for DDL changes during rolling deployments

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
- Create indexes CONCURRENTLY (avoids table locks)
- Never rename columns directly - use expand-contract pattern
- Separate data migrations from schema migrations
- Test: migrate up then migrate down (TypeORM) or verify backward compatibility (Prisma)

### Deploy Order Safety

The order of code deployment relative to migration execution determines whether a rolling deploy is safe:

| Change Type   | Correct Order                                     | Wrong Order                                                    |
| ------------- | ------------------------------------------------- | -------------------------------------------------------------- |
| Add column    | Migration first, then code                        | Code first (code references non-existent column)               |
| Drop column   | Code first (remove references), then migration    | Migration first (app breaks reading dropped column)            |
| Rename column | Expand-contract required (never in single deploy) | Rename + code in same deploy (rolling deploy partially broken) |
| Add index     | Migration first (additive, safe)                  | No ordering risk                                               |

For Prisma (no built-in rollback), plan each migration as forward-only and backward-compatible with the previous deployed code version:

```bash
# Deploy sequence for DROP COLUMN:
# 1. Deploy code that no longer reads/writes the column
# 2. Verify no references in production logs
# 3. Run: prisma migrate deploy (drops column)
```

## Edge Cases

- **Migration already applied partially (crash mid-migration)**: Prisma marks failed migrations in `_prisma_migrations` table - fix the SQL and run `prisma migrate resolve`. TypeORM: check which statements succeeded and manually complete or revert.
- **Multiple developers creating migrations simultaneously**: Merge conflicts in migration files. Prisma: may need `prisma migrate resolve` after merge. TypeORM: ensure migration timestamps do not conflict.
- **Large table migrations**: Adding a column or index on a large table can lock it. Use `CONCURRENTLY` for indexes; for column changes, consider batched backfill in a separate migration.

## Avoid

- `prisma db push` in production (no migration history, can lose data)
- `synchronize: true` in production (TypeORM auto-syncs schema without migration history - can drop columns)
- Generated migrations without review
- Data manipulation inside schema migrations
- Destructive migration (DROP COLUMN) before code is updated to remove the reference
