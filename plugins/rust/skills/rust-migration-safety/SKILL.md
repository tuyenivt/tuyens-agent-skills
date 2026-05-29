---
name: rust-migration-safety
description: Review sqlx PostgreSQL migrations for lock risk, backfill safety, rollback coverage. Expand-contract, CONCURRENTLY, NOT VALID.
metadata:
  category: backend
  tags: [rust, sqlx, postgresql, migrations, ddl, zero-downtime]
user-invocable: false
---

# Rust Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing a sqlx migration before merge
- Designing a multi-step schema change against a live table
- Investigating a migration stalled on `ACCESS EXCLUSIVE`

## Rules

- One concern per file. Never mix DDL with DML, or a fast step with a scanning step.
- Use reversible migrations (`sqlx migrate add -r`): paired `<ts>_<name>.up.sql` and `<ts>_<name>.down.sql`.
- Statements that cannot run in a transaction (`CREATE/DROP INDEX CONCURRENTLY`, `ALTER TYPE ... ADD VALUE`, `VACUUM`, `REINDEX CONCURRENTLY`) require `-- no-transaction` as the first line and must be the sole statement in the file.
- Expand-contract any rename, retype, or column drop. The old shape stays until every running deploy has stopped using it.
- A `.down.sql` either restores the prior schema with `IF EXISTS` or declares the migration irreversible in a header comment - never silently lose backfilled data.

## Lock Reference

`ACCESS EXCLUSIVE` blocks readers and writers. Operations that scan the table hold this lock for the duration of the scan.

| Statement                                   | Lock              | Safe at scale?            |
| ------------------------------------------- | ----------------- | ------------------------- |
| `ADD COLUMN` nullable, no default           | ACCESS EXCLUSIVE  | Yes - metadata only       |
| `ADD COLUMN ... DEFAULT <const>`            | ACCESS EXCLUSIVE  | Yes - metadata only       |
| `ADD COLUMN ... DEFAULT <volatile>`         | ACCESS EXCLUSIVE  | No - rewrites table       |
| `ADD COLUMN ... NOT NULL` on existing rows  | ACCESS EXCLUSIVE  | No - full scan            |
| `ALTER COLUMN ... SET NOT NULL`             | ACCESS EXCLUSIVE  | No - full scan            |
| `ADD CONSTRAINT FK` (validates)             | ACCESS EXCLUSIVE  | No - scans both tables    |
| `ADD CONSTRAINT ... NOT VALID`              | ACCESS EXCLUSIVE  | Yes - no scan, brief      |
| `VALIDATE CONSTRAINT`                       | SHARE UPDATE EXCL | Yes - concurrent r/w      |
| `CREATE INDEX`                              | SHARE             | No - blocks writes        |
| `CREATE INDEX CONCURRENTLY`                 | SHARE UPDATE EXCL | Yes                       |
| `DROP COLUMN`                               | ACCESS EXCLUSIVE  | Metadata only, but breaks deployed readers |
| `RENAME COLUMN` / `ALTER COLUMN TYPE`       | ACCESS EXCLUSIVE  | Breaks deployed code      |

## Patterns

### Add a NOT NULL column with FK on a large table

Bad - one statement, full rewrite, blocks writes:

```sql
ALTER TABLE events ADD COLUMN tenant_id BIGINT NOT NULL REFERENCES tenants(id);
```

Good - four migrations, each non-blocking:

```sql
-- 1: add nullable column (metadata-only)
ALTER TABLE events ADD COLUMN tenant_id BIGINT;

-- 2: backfill (batched DML, separate file; for very large tables run from a job, not sqlx)
UPDATE events SET tenant_id = $default
WHERE id BETWEEN $lo AND $hi AND tenant_id IS NULL;

-- 3: enforce NOT NULL via CHECK (no full-table rewrite)
ALTER TABLE events ADD CONSTRAINT events_tenant_id_not_null
  CHECK (tenant_id IS NOT NULL) NOT VALID;
ALTER TABLE events VALIDATE CONSTRAINT events_tenant_id_not_null;

-- 4: FK without table scan
ALTER TABLE events ADD CONSTRAINT events_tenant_fk
  FOREIGN KEY (tenant_id) REFERENCES tenants(id) NOT VALID;
ALTER TABLE events VALIDATE CONSTRAINT events_tenant_fk;
```

`ALTER COLUMN ... SET NOT NULL` still scans the table even after the CHECK is validated. On hot tables, leave the CHECK in place.

### Index on a large table

```sql
-- up
-- no-transaction
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_tenant ON events(tenant_id);

-- down
-- no-transaction
DROP INDEX CONCURRENTLY IF EXISTS idx_events_tenant;
```

A failed `CREATE INDEX CONCURRENTLY` leaves an `INVALID` index. The matching `down` must drop it so the next `migrate run` succeeds.

### Drop or rename a column (expand-contract)

```
1. Deploy: stop reading the old column (code change only).
2. Migration: ALTER TABLE ... DROP COLUMN old_col;  -- safe once no deploy references it.
```

For rename: add new column -> dual-write deploy -> backfill -> read-from-new deploy -> drop old. Same shape for `ALTER COLUMN TYPE` when the type change requires a rewrite or cast.

Dropping a column still referenced by any deployed instance breaks every running replica at the moment the migration applies.

### Backfill at scale

Batch by primary-key range, commit per batch. For tables above ~1M rows, run the backfill from a one-off job or `psql` script and keep the sqlx migration limited to schema changes - a single migration-bound `UPDATE` holds row locks and bloats WAL.

### Embedded migrations

`sqlx::migrate!()` runs at startup against the resolved `migrations/` directory and verifies checksums. Editing a previously-applied migration changes its checksum and aborts boot. Add a new migration to fix prior state; never edit shipped ones.

## Output Format

```
Migration Review: <filename or timestamp>

Blocking Risk: {None | Low | High | Critical}
Findings:
  - Severity: {Critical | High | Medium | Low}
    Issue: <what is wrong>
    Statement: <offending SQL>
    Fix: <concrete change>
Rewrite Plan:
  - <ordered replacement migrations, one concern per file>
Rollback Coverage: {Complete | Partial | Missing | Irreversible}
  Down: <SQL the .down.sql must contain, or reason for irreversibility>
CI Check: {Pass | Fail: <reason>}
```

Severity: `Critical` blocks production writes; `High` is a full-table scan under `ACCESS EXCLUSIVE` or a deployed-code break; `Medium` is an unsafe or missing rollback; `Low` is style or idempotency.

Blocking Risk: `Critical` if any deploy-breaking change (drop/rename referenced column, in-place type change); `High` if any `ACCESS EXCLUSIVE` scan on a large table; `Low` if only metadata-only DDL; `None` otherwise.

## Avoid

- `DEFAULT <volatile>` (e.g., `now()`, `gen_random_uuid()`) on `ADD COLUMN` - rewrites the table.
- Mixing DDL and DML, or fast and scanning steps, in one file.
- Combining `CONCURRENTLY` with any other statement, or omitting `-- no-transaction`.
- `RENAME COLUMN`, `ALTER COLUMN TYPE`, or `DROP COLUMN` while deployed code still references the column.
- Editing a migration after it has been applied anywhere - the checksum mismatch will abort `sqlx::migrate!()`.
- Destructive `.down.sql` that silently discards backfilled data.
