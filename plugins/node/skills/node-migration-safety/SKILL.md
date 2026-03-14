---
name: node-migration-safety
description: "Safe migration patterns for Node.js with Prisma and TypeORM. Prisma migrate for NestJS, TypeORM migrations for Express. Zero-downtime DDL, review workflow, CI validation."
user-invocable: false
---

Cover:

PRISMA MIGRATIONS (NestJS):

- prisma migrate dev: development (creates + applies)
- prisma migrate deploy: production (applies only, no generation)
- Review every generated migration in prisma/migrations/
- Custom SQL in migration.sql for: CONCURRENTLY indexes, partial indexes, data backfill
- Rollback: Prisma has no built-in down migration - plan forward-only migrations
  that are backward-compatible, or use manual SQL down scripts
- prisma migrate reset: for test environments only
- CI: run prisma migrate deploy in pipeline

TYPEORM MIGRATIONS (Express):

- typeorm migration:generate - generates from entity diff
- typeorm migration:create - creates empty migration for custom SQL
- typeorm migration:run - applies pending
- typeorm migration:revert - reverts last applied
- ALWAYS review generated migrations
- synchronize: NEVER true in production

SHARED ZERO-DOWNTIME RULES (same as Core):

- Add columns nullable first → backfill → add NOT NULL
- Create indexes CONCURRENTLY
- Never rename columns directly
- Separate data migrations from schema migrations
- Test: migrate up → migrate down (TypeORM) or verify backward compatibility (Prisma)

DEPLOY ORDER SAFETY:

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

ANTI-PATTERNS:

- ❌ prisma db push in production
- ❌ synchronize: true in production (TypeORM)
- ❌ Generated migrations without review
- ❌ Data manipulation inside schema migrations
- ❌ Destructive migration (DROP COLUMN) before code is updated to remove the reference
