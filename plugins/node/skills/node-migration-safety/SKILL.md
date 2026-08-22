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
- Never use `prisma db push` or `synchronize: true` against production (no history, can drop data). `prisma migrate reset` **drops and recreates the database** - it is a local-only command, never a way to "clean up" a failed production migration
- `prisma migrate deploy` / `typeorm migration:run` apply **every** pending migration, not just the one you are fixing. Move any destructive migration queued behind a repair out of the deployed branch first
- Separate data migrations from schema migrations
- Add columns nullable, backfill, then add NOT NULL - and give the NOT NULL column a `DEFAULT`, or inserts from the still-running old version fail
- State the engine before choosing DDL. `CONCURRENTLY` is PostgreSQL; MySQL 8 uses `ALGORITHM=INPLACE, LOCK=NONE`. MySQL commits DDL implicitly, so a TypeORM migration transaction gives no atomicity there - a half-applied migration must be repaired by hand
- Never rename columns in a single deploy - use expand-contract: add the new column, dual-write, backfill, flip reads, stop writing the old, drop it. Four deploys, and the drop only after the no-old-column code is past the rollback horizon

## Patterns

### Prisma vs TypeORM Commands

| Action            | Prisma                     | TypeORM                       |
| ----------------- | -------------------------- | ----------------------------- |
| Generate from diff| `prisma migrate dev`       | `typeorm migration:generate`  |
| Custom SQL        | edit `migration.sql` **and** mirror the change in `schema.prisma` | `typeorm migration:create` |
| Apply (prod/CI)   | `prisma migrate deploy`    | `typeorm migration:run`       |
| Revert            | forward-only (manual down) | `typeorm migration:revert`    |
| Reset (test only) | `prisma migrate reset`     | drop schema + re-run          |

Prisma has no built-in down migration: write each migration forward-only and backward-compatible with the previously deployed code.

### Zero-Downtime Deploy Order

| Change Type       | Correct Order                                                        | Wrong Order                                       |
| ----------------- | -------------------------------------------------------------------- | ------------------------------------------------- |
| Add column        | Migration first, then code                                           | Code first (references missing column)            |
| Drop column       | Code first (remove refs), then migration                             | Migration first (app reads dropped column)        |
| Rename column     | Expand-contract over multiple deploys                                | Rename + code in one deploy                       |
| Add index         | Migration first (additive)                                           | n/a                                               |
| Add enum value    | Migration first, then code using new value                           | Code first (writes unknown value)                 |
| Add NOT NULL      | Nullable + DEFAULT -> backfill -> `SET NOT NULL`                     | `SET NOT NULL` while old writers still send null  |
| Add foreign key   | `ADD CONSTRAINT ... NOT VALID` -> backfill/clean -> `VALIDATE`       | Plain `ADD CONSTRAINT` (full-table scan under an exclusive lock) |
| Change column type| New column -> dual-write -> backfill -> flip reads -> drop old       | `ALTER COLUMN ... TYPE` (rewrites the whole table) |
| Data backfill     | Its own migration or an out-of-band batched job, after the DDL       | Inside the schema migration (blocks the deploy)   |

Widening a `numeric` scale, changing an integer width, or most type changes rewrite every row under an `ACCESS EXCLUSIVE` lock. Treat any type change on a large table as a shadow-column expand-contract, not an `ALTER`.

Every write migration bounds how long it will wait for its lock, so it fails fast instead of queueing behind a long reader and blocking every subsequent query on the table: PostgreSQL `SET LOCAL lock_timeout = '3s'`, MySQL `SET SESSION lock_wait_timeout = 3`. The exception is a `CONCURRENTLY` migration, which must stay a single statement (below) and takes no blocking lock anyway.

### Enum Management (PostgreSQL)

Adding a value generates `ALTER TYPE "OrderStatus" ADD VALUE 'CANCELLED'` (same for Prisma and TypeORM). Safe and additive, but PostgreSQL cannot use the new value in the same transaction that adds it - put any `UPDATE`/backfill using the value in a separate migration. Removal is **not supported** - to drop a value, create a new type, migrate the column, drop the old type.

### Index Strategy

Index foreign keys, frequently filtered columns (`status`, `createdAt`), unique constraint columns, and composite patterns (`[customerId, status]`). For large tables, use custom SQL:

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_status ON "Order" ("customerId", "status");
```

`CONCURRENTLY` must run outside a transaction. Prisma adds no transaction of its own, but PostgreSQL wraps a **multi-statement** script in one implicit transaction - so the file must contain that single statement and nothing else. TypeORM wraps migrations in transactions by default - run the index migration with `migrationsTransactionMode: "none"`, isolated in its own deploy. MySQL has no `CONCURRENTLY`; use `ALTER TABLE ... ADD INDEX ..., ALGORITHM=INPLACE, LOCK=NONE`.

A `CONCURRENTLY` build that fails leaves an **invalid** index behind. It is not retryable in place: `DROP INDEX CONCURRENTLY` first, then rebuild (`CREATE INDEX ... IF NOT EXISTS` silently keeps the invalid one).

### Failure Recovery

`prisma migrate resolve` takes two mutually exclusive flags, and the choice is irreversible in practice:

| Situation                                                        | Flag              | Effect                                        |
| ---------------------------------------------------------------- | ----------------- | --------------------------------------------- |
| The DDL **did** land; only the bookkeeping failed                | `--applied`       | Marks finished; the migration never runs again |
| The DDL did **not** land, or you undid its partial effects       | `--rolled-back`   | Clears the failure so a corrected version runs |

Choosing `--applied` on a migration whose DDL never landed loses that change permanently. Undo any partial DDL by hand **before** resolving, then verify the schema matches the migration's end state.

### Edge Cases

- **Failed mid-migration**: Prisma marks failed entries in `_prisma_migrations`; clean up partial DDL, then `migrate resolve` per the table above. TypeORM: inspect, manually complete or revert.
- **Concurrent migrations from multiple devs**: adjacent timestamps are the visible symptom; the real hazard is that each was generated against a different schema, so both diffs are wrong once merged. Regenerate as one migration from a production-shaped schema rather than reordering filenames.
- **Migration runner concurrency**: run migrations from one place (an init container or a release job), never `migrationsRun: true` on N replicas racing each other.
- **Large-table column changes**: batched backfill in a separate migration; avoid table rewrites.
- **`down()`**: Prisma has none. A TypeORM `down()` that is empty or lies is worse than none - throw explicitly when the migration is not reversible.

## Output Format

When planning, emit this block plus the migration SQL and any backfill script it names. When reviewing existing migrations, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit one finding per unsafe change and keep the Deploy Sequence as the corrected plan.

```
## Migration Plan

Engine: {PostgreSQL | MySQL | other} - decides CONCURRENTLY vs ALGORITHM=INPLACE and DDL atomicity
ORM: {Prisma | TypeORM}

### Schema Changes
| Change | Type | Table | Column | Locks Taken | Safe Order |
|--------|------|-------|--------|-------------|------------|

### Indexes
| Index | Table | Columns | Type | Online Method |
|-------|-------|---------|------|---------------|

### Backfill
| Table | Predicate | Batch Size | Where It Runs (migration / out-of-band job) |
|-------|-----------|------------|---------------------------------------------|

### Deploy Sequence
Numbered, each step tagged [migration] or [code], with the compatibility invariant that
holds between it and the previous step (what the still-running old version can still do).

### Verification
[Query or check proving each step landed - index validity, zero NULLs, row counts]

### Rollback Plan
[Forward-only compatibility notes, or the revert steps and the point of no return]
```

## Avoid

- Applying generated migrations without review
- Data manipulation inside schema migrations
- `DROP COLUMN` before code stops referencing it, and dropping anything without archiving it first
- Adding `NOT NULL` columns without default or backfill
- Removing enum values without the multi-step type migration
- `prisma migrate reset` on any database you did not create locally
- `migrate resolve --applied` on a migration whose DDL never landed
- Postgres-only DDL (`CONCURRENTLY`, `NOT VALID`) in a plan whose engine is MySQL
