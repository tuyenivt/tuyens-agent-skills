---
name: rust-migration-safety
description: "Review sqlx PostgreSQL migrations for lock risk, backfill safety, and rollback coverage. Expand-contract, CONCURRENTLY, NOT VALID, batched DML."
metadata:
  category: backend
  tags: [rust, sqlx, postgresql, migrations, ddl, zero-downtime]
user-invocable: false
---

# Rust Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing a sqlx migration for production safety before merge
- Designing a multi-step schema change against a large or live table
- Investigating a stalled migration holding `ACCESS EXCLUSIVE` on a hot table

## Rules

- One concern per file. Never mix DDL and DML, never combine an unsafe step with a safe one.
- Every destructive or backfill migration ships with a `.down.sql` that compensates without data loss.
- Operations against tables larger than ~1M rows must use the non-blocking variant (`CONCURRENTLY`, `NOT VALID`, batched updates).
- Use sqlx reversible migrations (`sqlx migrate add -r`). Add `-- sqlx:no-transaction` to migrations that contain `CONCURRENTLY` or `ALTER TYPE ... ADD VALUE` (cannot run inside a transaction).
- Expand-contract for any rename or type change. Never rename or retype in place.

## Lock Reference

PostgreSQL DDL acquires these locks. Anything `ACCESS EXCLUSIVE` blocks readers and writers on a hot table.

| Statement                                      | Lock              | Safe at scale?              |
| ---------------------------------------------- | ----------------- | --------------------------- |
| `ADD COLUMN` (nullable, no default)            | ACCESS EXCLUSIVE  | Yes (metadata-only, fast)   |
| `ADD COLUMN ... DEFAULT <const>` (PG 11+)      | ACCESS EXCLUSIVE  | Yes (metadata-only)         |
| `ADD COLUMN ... DEFAULT <volatile>`            | ACCESS EXCLUSIVE  | No (rewrites table)         |
| `ADD COLUMN ... NOT NULL` on existing data     | ACCESS EXCLUSIVE  | No (full scan)              |
| `ALTER COLUMN ... SET NOT NULL`                | ACCESS EXCLUSIVE  | No (full scan)              |
| `ADD CONSTRAINT FK` (default, validates)       | ACCESS EXCLUSIVE  | No (scans both tables)      |
| `ADD CONSTRAINT ... NOT VALID`                 | ACCESS EXCLUSIVE  | Yes (no scan, brief lock)   |
| `VALIDATE CONSTRAINT`                          | SHARE UPDATE EXCL | Yes (concurrent reads/writes) |
| `CREATE INDEX`                                 | SHARE             | No (blocks writes)          |
| `CREATE INDEX CONCURRENTLY`                    | SHARE UPDATE EXCL | Yes                         |
| `DROP COLUMN`                                  | ACCESS EXCLUSIVE  | Yes (metadata-only)         |
| `ALTER TABLE ... RENAME COLUMN`                | ACCESS EXCLUSIVE  | Breaks deployed app code    |

## Patterns

### NOT NULL column on a large table

Bad - one migration, table-rewriting scan, blocks writes for minutes:

```sql
ALTER TABLE events ADD COLUMN tenant_id BIGINT NOT NULL REFERENCES tenants(id);
```

Good - four migrations, each step non-blocking:

```sql
-- N_add_events_tenant_id.up.sql: nullable column, fast metadata change
ALTER TABLE events ADD COLUMN tenant_id BIGINT;

-- N+1_backfill_events_tenant_id.up.sql: batched DML, no DDL
-- Run from a job or psql, not via sqlx, if the table is very large.
UPDATE events SET tenant_id = $default_id
WHERE id BETWEEN $lo AND $hi AND tenant_id IS NULL;

-- N+2_events_tenant_id_not_null.up.sql: CHECK NOT VALID then VALIDATE
ALTER TABLE events ADD CONSTRAINT events_tenant_id_not_null
  CHECK (tenant_id IS NOT NULL) NOT VALID;
ALTER TABLE events VALIDATE CONSTRAINT events_tenant_id_not_null;
-- Optional once validated: promote to column NOT NULL (still scans; skip for very large tables)
-- ALTER TABLE events ALTER COLUMN tenant_id SET NOT NULL;

-- N+3_events_tenant_fk.up.sql: FK without table scan
ALTER TABLE events ADD CONSTRAINT events_tenant_fk
  FOREIGN KEY (tenant_id) REFERENCES tenants(id) NOT VALID;
ALTER TABLE events VALIDATE CONSTRAINT events_tenant_fk;
```

### Index on a large table

```sql
-- up: must be the only statement; requires no-transaction marker
-- sqlx:no-transaction
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_tenant ON events(tenant_id);

-- down:
-- sqlx:no-transaction
DROP INDEX CONCURRENTLY IF EXISTS idx_events_tenant;
```

`CREATE INDEX CONCURRENTLY` can leave an `INVALID` index on failure. The `down` must drop it so re-running the up succeeds.

### Rename via expand-contract

```sql
-- N: add new column        N+1: dual-write deploy
-- N+2: backfill (batched)  N+3: read-from-new deploy
-- N+4: drop old column
```

In-place `RENAME COLUMN` breaks every running instance of the app that still references the old name.

### Backfill at scale

- Do not run a single `UPDATE` over a 10M+ row table inside a migration - it holds row locks and bloats WAL.
- Batch by primary key range (`WHERE id BETWEEN $lo AND $hi`), commit per batch, sleep between batches.
- For tenant-tagged backfills, prefer running the backfill from a one-off job or `psql` script and keeping the sqlx migration limited to schema metadata.

### Down migrations

- DDL: emit the inverse (`DROP COLUMN`, `DROP INDEX`, `DROP CONSTRAINT`) with `IF EXISTS`.
- Backfill DML: a true inverse usually does not exist. Document the irreversibility in a header comment and ship an empty `.down.sql` rather than destructive SQL that loses data.

## Output Format

```
Migration Review: <file or migration id>

Blocking Risk: {None | Low | High | Critical}
Findings:
  - <Severity>: <issue> (<statement>) - <fix>
    Severity: {Critical | High | Medium | Low}
Rewrite Plan:
  - <ordered list of replacement migrations, one concern each>
Rollback Coverage: {Complete | Partial | Missing | N/A}
  Down: <what the .down.sql must contain, or "irreversible: <reason>">
CI Check: {sqlx migrate run && revert && run passes | will fail because <reason>}
```

Severity guide: `Critical` = blocks production writes; `High` = full-table scan under ACCESS EXCLUSIVE; `Medium` = unsafe rollback; `Low` = style or idempotency.

## Avoid

- `ALTER TABLE ... ADD COLUMN ... NOT NULL` on a table with existing rows
- `ADD CONSTRAINT FOREIGN KEY` without `NOT VALID` on a large table
- `CREATE INDEX` without `CONCURRENTLY` on tables > ~1M rows
- Combining `CONCURRENTLY` with any other statement in the same file, or omitting `-- sqlx:no-transaction`
- Single-statement backfills over very large tables inside a sqlx migration
- `RENAME COLUMN` or `ALTER COLUMN TYPE` in place on a deployed table
- Destructive `down.sql` that silently loses backfilled data
