---
name: node-migration-safety
description: Safe DB migration patterns for Prisma / TypeORM: zero-downtime DDL, deploy ordering, enum management, CI validation, rollback.
metadata:
  category: backend
  tags: [node, prisma, typeorm, migrations, database, zero-downtime]
user-invocable: false
---

# Migration Safety

> Load `Use skill: stack-detect` first. Its `Database` and `ORM` fields pick the DDL and commands below and surface in the plan's `Engine:` and `ORM:` lines. `Database: unknown` is written `Engine: unknown - assumed PostgreSQL` and every engine-specific choice is flagged as that assumption; an unknown version is `(version unknown - assumed <the lowest version the plan relies on>)`, and Aurora is written as its PostgreSQL / MySQL compatibility version, not the Aurora release (Aurora MySQL 3.01-3.04 is 8.0.23-8.0.28). An ORM other than Prisma or TypeORM gets the raw-SQL guidance with its own migrate command; no ORM detected is `ORM: unknown - raw SQL`.

## When to Use

- Creating or reviewing Prisma/TypeORM migrations
- Planning zero-downtime schema changes under rolling deploys
- Adding enums, indexes, or constraints to existing tables
- Recovering a failed or half-applied migration

## Rules

- Review every generated migration before applying
- Never use `prisma db push` or `synchronize: true` against production (no history, can drop data). `prisma migrate reset` **drops and recreates the database** - use it only on a disposable dev/test database you own, never to "clean up" a failed production migration
- `prisma migrate deploy` / `typeorm migration:run` apply **every** pending migration, not just the one you are fixing. Move any destructive migration queued behind a repair out of the deployed branch first
- Separate data migrations from schema migrations
- A new NOT NULL column never breaks the still-running old version's inserts. A **constant** default makes it one metadata-only step (PostgreSQL 11+ `ADD COLUMN ... NOT NULL DEFAULT 'USD'`; MySQL 8.0.12+ `ALGORITHM=INSTANT`). With no sensible constant: add nullable -> ship code that writes it -> backfill -> enforce NOT NULL (engine recipe below). The default must exist in the database - Prisma's client-side `@default(uuid())` / `cuid()` / `nanoid()` emit no SQL `DEFAULT`. Only a non-volatile database default is metadata-only: a literal, `now()`, or a non-volatile `dbgenerated(...)`. A volatile one (`autoincrement()` -> `nextval()`, `dbgenerated("gen_random_uuid()")`) rewrites the table - take the nullable -> backfill -> enforce path
- State the engine before choosing DDL: `CONCURRENTLY` and `NOT VALID` are PostgreSQL; MySQL 8 uses `ALGORITHM=INSTANT` / `INPLACE, LOCK=NONE`. MySQL commits DDL implicitly, so a TypeORM migration transaction gives no atomicity there - a half-applied migration must be repaired by hand
- Never rename columns in a single deploy - use expand-contract: add the new column, dual-write, backfill, flip reads, stop writing the old, drop it. Four deploys, and the drop only after the no-old-column code is past the rollback horizon
- Run migrations from exactly one place per release - a Kubernetes Job, a pre-deploy task, a CI step. A Deployment `initContainer` runs once per new pod, and `migrationsRun: true` runs in every replica: both race. Prisma's advisory lock times out after 10 s, so pods queued behind a longer migration crash-loop with `P1002`; TypeORM takes no lock, so replicas can apply the same migration twice
- Every write migration bounds how long it waits for its lock (below), so it fails fast instead of queueing behind a long reader and blocking every later query on the table. `CREATE INDEX CONCURRENTLY` is the exception: it waits without blocking DML, and a `lock_timeout` makes it fail and leave an invalid index

## Patterns

### Prisma vs TypeORM Commands

| Action            | Prisma                     | TypeORM 0.3                   |
| ----------------- | -------------------------- | ----------------------------- |
| Generate from diff| `prisma migrate dev`       | `typeorm migration:generate ./src/migrations/AddX -d ./src/data-source.ts` |
| Custom SQL        | `prisma migrate dev --create-only`, edit `migration.sql`, mirror it in `schema.prisma`, then `prisma migrate dev` | `typeorm migration:create ./src/migrations/AddX` |
| Apply (prod/CI)   | `prisma migrate deploy`    | `typeorm migration:run -d ./src/data-source.ts` |
| Revert            | forward-only (manual down) | `typeorm migration:revert -d ./src/data-source.ts` |
| Reset (disposable DB only) | `prisma migrate reset` | drop schema + re-run  |

TypeScript sources run through `typeorm-ts-node-commonjs` (or `-esm`) instead of bare `typeorm`; a `package.json` script beats both. Editing an already-applied Prisma `migration.sql` changes its checksum and makes the next `migrate dev` demand a reset - that is why `--create-only` comes first. Prisma has no built-in down migration: write each migration forward-only and backward-compatible with the previously deployed code.

### Zero-Downtime Deploy Order

| Change | PostgreSQL | MySQL 8 | Wrong order |
|--------|-----------|---------|-------------|
| Add column | Migration first, then code | same; `ALGORITHM=INSTANT` (any position from 8.0.29, last column before) | Code first (references a missing column) |
| Drop column | Make it nullable (or give it a default) -> code stops referencing it -> drop | `ALTER COLUMN ... SET DEFAULT` (INSTANT; `MODIFY ... NULL` rebuilds the table) -> code stops referencing it -> drop (`INSTANT` from 8.0.29) | Drop first (old code reads it); code first on a NOT NULL column (new inserts omit it and fail) |
| Rename column | Expand-contract over multiple deploys | same | Rename + code in one deploy |
| Add index | `CREATE INDEX CONCURRENTLY`, alone | `ADD INDEX ..., ALGORITHM=INPLACE, LOCK=NONE` - explicit, so an unsupported case fails instead of silently taking a lock (FULLTEXT / SPATIAL cannot be `LOCK=NONE`) | PG: plain `CREATE INDEX` (`SHARE`, blocks writes); MySQL: omitting `LOCK=NONE` |
| Add NOT NULL | Constant default: one step. Otherwise nullable -> code writes it -> backfill -> `CHECK (col IS NOT NULL) NOT VALID` -> `VALIDATE CONSTRAINT` -> `SET NOT NULL` (PG 12+ skips the scan) -> drop the check | Constant default: `INSTANT`. Otherwise nullable -> backfill -> `MODIFY ... NOT NULL` (in-place rebuild; `LOCK=NONE` needs strict `sql_mode`) | Bare `SET NOT NULL` on a large table (scan under `ACCESS EXCLUSIVE`) |
| Add foreign key | `ADD CONSTRAINT ... NOT VALID` -> clean orphans -> `VALIDATE CONSTRAINT` | Clean orphans first (`foreign_key_checks=0` never validates existing rows) -> `INPLACE` with `foreign_key_checks=0`; otherwise `COPY` off-peak or pt-online-schema-change (gh-ost does not support FKs) | Plain `ADD CONSTRAINT` on a large table |
| Change column type | Binary-coercible changes are metadata-only (widen `varchar`, `varchar` -> `text`, raise `numeric` precision at the same scale); anything else: new column -> dual-write -> backfill -> flip reads -> drop old | `VARCHAR` widen in place only while the length-byte count holds (both < 256 bytes or both >= 256); most others `COPY` - expand-contract | `ALTER COLUMN ... TYPE` that rewrites a large table |
| Add enum value | See Enum Management | Append at the end of the `ENUM` list while it stays <= 255 members: metadata-only; mid-list insert, removal, or crossing 255: `COPY` | Code that writes the value before every reader knows it |
| Data backfill | Its own migration or an out-of-band batched job, after the DDL | same | Inside the schema migration (blocks the deploy) |

### Locks and Lock Timeouts

| Operation (PostgreSQL) | Lock | Blocks |
|------------------------|------|--------|
| `CREATE INDEX` | `SHARE` | writes |
| `CREATE INDEX CONCURRENTLY` | `SHARE UPDATE EXCLUSIVE` | other DDL, `VACUUM`, another CIC - not reads or writes; waits for every transaction with an older snapshot |
| `VALIDATE CONSTRAINT` | `SHARE UPDATE EXCLUSIVE` | other DDL, `VACUUM` - not reads or writes |
| `ADD CONSTRAINT ... FOREIGN KEY` | `SHARE ROW EXCLUSIVE` on **both** tables | writes on both |
| `SET NOT NULL`, table rewrite, `ALTER TYPE` | `ACCESS EXCLUSIVE` | everything |
| `ADD COLUMN` (nullable, or constant default) | `ACCESS EXCLUSIVE`, brief | everything, for milliseconds - unless it queues behind a long reader |

MySQL online DDL takes a brief exclusive metadata lock at start and end; a long transaction holding a metadata lock stalls it and every query queued behind it.

Bound the wait: PostgreSQL `SET LOCAL lock_timeout = '3s'` inside the migration's transaction (a no-op outside one - under TypeORM `transaction = false` use a plain `SET lock_timeout`, and reset it). Prisma on PostgreSQL: `SET LOCAL lock_timeout = '3s';` as the first statement of `migration.sql` applies for the rest of the file's implicit transaction. MySQL (Prisma runs each statement on its own): `SET SESSION lock_wait_timeout = 3;` first. Leave `CREATE INDEX CONCURRENTLY` unbounded and check `indisvalid` after it.

### Enum Management

Any engine - rollout: migration -> code whose client **knows** the value (Prisma Client rejects an unknown enum value on read: `Value '...' not found in enum`) -> code that **writes** it. TypeORM returns the raw string and tolerates it.

PostgreSQL:

- Prisma generates `ALTER TYPE "OrderStatus" ADD VALUE 'REFUNDED'` - safe and additive. TypeORM's `migration:generate` instead renames the type, creates a new one, and `ALTER COLUMN ... TYPE ... USING` - a table rewrite under `ACCESS EXCLUSIVE`. Replace that `up()` with a hand-written `ALTER TYPE "<table>_<column>_enum" ADD VALUE '...'`. On PostgreSQL 11, `ADD VALUE` cannot run inside a transaction block: the migration needs `transaction = false` (run with `-t each`), and a Prisma file must hold only that statement
- PostgreSQL cannot use a new value in the transaction that added it. Put any `UPDATE` using it in a **later** migration - and under TypeORM's default `migrationsTransactionMode: "all"` every pending migration shares one transaction, so run with `migration:run -t each` or ship the backfill in a later deploy
- Removal is **not supported** - create a new type, migrate the column, drop the old type

### Index Strategy

Index foreign keys, frequently filtered columns (`status`, `createdAt`), unique constraint columns, and composite patterns (`[customerId, status]`). For large tables:

```sql
-- Prisma: the file holds this single statement and nothing else
CREATE INDEX CONCURRENTLY "Order_customerId_status_idx" ON "Order" ("customerId", "status");
```

`CONCURRENTLY` must run outside a transaction. Prisma adds none, but PostgreSQL wraps a multi-statement script in one implicit transaction - so the file holds that one statement. Add `@@index([customerId, status])` to `schema.prisma` in the same change - without it the next `migrate dev` emits `DROP INDEX` - and name the SQL index `<table>_<columns>_idx` from the database names (`@@map` / `@map`), or set `map:` to match it; a name mismatch alone becomes an `ALTER INDEX ... RENAME`. TypeORM: set `public transaction = false` on that migration class and run with `migration:run -t each`; the DataSource-wide `migrationsTransactionMode: "none"` turns transactions off for every migration.

A failed `CONCURRENTLY` build leaves an **invalid** index. `CREATE INDEX ... IF NOT EXISTS` silently keeps it. Rebuild with `REINDEX INDEX CONCURRENTLY` (PG 12+), or `DROP INDEX CONCURRENTLY` and re-create - under Prisma, re-deploying the same `CREATE INDEX CONCURRENTLY` after `migrate resolve --rolled-back` fails with "already exists" unless the invalid index was dropped first.

### Backfill

Batch by primary-key range (1-10K rows), commit per batch, sleep between batches, and pause while replica lag exceeds its alert threshold - one statement over 400M rows is one transaction, one WAL burst, and lag every replica replays serially.

### Failure Recovery

`prisma migrate resolve` takes two mutually exclusive flags, and the choice is irreversible in practice:

| Situation                                                        | Flag              | Effect                                        |
| ---------------------------------------------------------------- | ----------------- | --------------------------------------------- |
| The DDL **did** land; only the bookkeeping failed                | `--applied`       | Marks finished; the migration never runs again |
| The DDL did **not** land, or you undid its partial effects       | `--rolled-back`   | Clears the failure so a corrected version runs |

Choosing `--applied` on a migration whose DDL never landed loses that change permanently. Undo any partial DDL by hand **before** resolving, then verify the schema matches the migration's end state.

TypeORM on MySQL: the statements before the failure are committed and the migration is still pending. Either undo them by hand, or make the migration re-runnable - guard each step on `information_schema` (MySQL 8 has no `ADD COLUMN IF NOT EXISTS`) - fix the cause (a duplicate-key failure on a unique index means deduplicating the data first), then re-run.

### Edge Cases

- **Concurrent migrations from multiple devs**: adjacent timestamps are the visible symptom; the real hazard is that each was generated against a different schema, so both diffs are wrong once merged. Regenerate as one migration from a production-shaped schema rather than reordering filenames
- **`down()`**: Prisma has none. A TypeORM `down()` that is empty or lies is worse than none - throw explicitly when the migration is not reversible

## Output Format

When planning, emit this block plus the migration SQL and any backfill script it names. When reviewing or recovering, the consuming workflow owns the finding envelope; invoked standalone, each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file) followed by `Issue:` and `Fix:` lines, `[Must]` first - `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise - one per unsafe change. A diagnosis or recovery opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported failure, and a question the request asks outright gets one `Ruling:` line; both precede the findings. After the findings, emit the full plan below as the corrected plan - one plan per service or engine when the request spans several, and one Schema Changes row per step when a change takes several (add nullable, backfill, enforce). A migration moved out of the release stays in the Deploy Sequence tagged `deferred - <reason>`. Severity does not wait for a row count: an unsafe lock on a table whose size is unknown is rated as if large, and the finding says so.

```
## Migration Plan

Engine: {PostgreSQL <major> | MySQL <version> | <engine> (version unknown - assumed <floor>) | unknown - assumed PostgreSQL}

ORM: {Prisma | TypeORM | <other> - raw SQL | unknown - raw SQL}

Runner: {Job | pre-deploy task | CI step | initContainer per pod - GAP | migrationsRun on N replicas - GAP | not stated - GAP}

### Schema Changes
| Change | Type | Table | Column | Locks Taken | Lock Timeout | Safe Order |
|--------|------|-------|--------|-------------|--------------|------------|

### Indexes
| Index | Table | Columns | Type | Online Method |
|-------|-------|---------|------|---------------|

### Backfill
| Table | Predicate | Batch Size and Pacing | Where It Runs (migration / out-of-band job) |
|-------|-----------|-----------------------|---------------------------------------------|

### Deploy Sequence
{numbered steps, each tagged [migration | code | job | manual | deferred - <reason>], with the invariant the still-running old version relies on}

### Verification
{the query or check proving each step landed}

### Rollback Plan
{forward-only compatibility notes, or the revert steps and the point of no return}
```

## Avoid

- Applying generated migrations without review
- Data manipulation inside schema migrations
- `DROP COLUMN` before code stops referencing it, and dropping anything without archiving it first
- Removing enum values without the multi-step type migration
- `prisma migrate reset` on any database you do not own and cannot throw away
- `migrate resolve --applied` on a migration whose DDL never landed
- Postgres-only DDL (`CONCURRENTLY`, `NOT VALID`) in a plan whose engine is MySQL
