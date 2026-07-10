---
name: backend-db-migration
description: Plan zero-downtime schema changes - expand-contract phasing, lock risk, batched backfill, deploy ordering, rollback. Stack-adaptive.
metadata:
  category: data
  tags: [database, migration, zero-downtime, expand-contract, lock-risk, backfill, multi-stack]
user-invocable: false
---

# DB Migration Safety

> Load `Use skill: stack-detect` first to identify the database engine and migration tool.

## When to Use

- Planning any schema change on a production database
- Estimating lock risk and backfill duration before committing
- Designing an expand-contract sequence for renames, type changes, or drops

## Rules

- Expand-contract is the default for every non-additive change.
- Backfills are always batched (100-1000 rows, idempotent, monitorable). Never unbounded.
- Application code is backward compatible with both schemas across the transition window.
- Rollback plan is designed before the migration runs.
- Never deploy a migration and the code that depends on it in the same release - rolling deploys leave old instances running against the new schema.
- Flag any migration requiring a database restore to roll back - those are go/no-go decisions.
- Lock risk must be stated for every recommendation.
- Engine or version unknown: assume worst-case locking (table rewrite, exclusive lock) and state the assumption in the output.

## Patterns

### Lock risk by change type

| Change                              | Lock Risk | Strategy                                  |
| ----------------------------------- | --------- | ----------------------------------------- |
| Add nullable column (no default)    | Low       | Single phase                              |
| Add column with default (modern DB) | Low       | Single phase, metadata-only               |
| Add column with default (old DB)    | High      | Table rewrite - use expand-contract       |
| Create index                        | High      | Use `CONCURRENTLY` or online DDL          |
| Add NOT NULL constraint             | High      | Backfill nulls first, then add constraint |
| Add unique constraint               | High      | Validate uniqueness first                 |
| Add foreign key                     | High      | Validate referential integrity first      |
| Rename column                       | Very High | Expand-contract required                  |
| Change column type                  | Very High | Expand-contract required                  |
| Drop column / table                 | High      | Remove all references first               |

Any exclusive-lock operation on a table > 1M rows is high risk by default.

### Expand-contract (default for non-additive)

1. **Expand**: add the new structure alongside the old; deploy app that reads the old and writes both (dual-write). During a rolling deploy, old instances still write only the old structure - either start the backfill after rollout completes or sync via database trigger.
2. **Migrate**: backfill old to new in batches; re-run until drift is zero; validate completeness.
3. **Contract**: deploy app using only the new structure; verify zero references to the old (code search + query/statement logs over a verification period); drop the old.

Skip only when the change is purely additive, or downtime is scheduled.

### Adding NOT NULL on a large table (PostgreSQL example)

The naive `ADD COLUMN NOT NULL` takes an exclusive lock for the full backfill. Split it:

```sql
-- 1. Add nullable (fast, no lock)
ALTER TABLE orders ADD COLUMN tenant_id UUID;

-- 2. Backfill in batches (background job)
UPDATE orders SET tenant_id = :default_tenant
WHERE id BETWEEN :start AND :end AND tenant_id IS NULL;

-- 3. Add constraint NOT VALID (validates new rows only)
ALTER TABLE orders ADD CONSTRAINT orders_tenant_id_not_null
  CHECK (tenant_id IS NOT NULL) NOT VALID;

-- 4. Validate existing rows (ShareUpdateExclusiveLock - concurrent reads/writes OK)
ALTER TABLE orders VALIDATE CONSTRAINT orders_tenant_id_not_null;
```

Use `NOT VALID` + `VALIDATE CONSTRAINT` whenever adding NOT NULL, CHECK, or FK to a large PostgreSQL table. MySQL and SQL Server have different online DDL mechanisms - check the detected database.

### Backfill: bounded batches

```sql
-- Bad - unbounded UPDATE locks the table
UPDATE large_table SET new_col = old_col WHERE new_col IS NULL;

-- Good - bounded key range, idempotent, loop until exhausted (any engine)
UPDATE large_table SET new_col = old_col
WHERE id > :last_id AND id <= :last_id + 1000 AND new_col IS NULL;
```

For tables > 100K rows, prefer a background job over an in-migration script. On replicated databases, sleep between batches and pause when replica lag exceeds threshold - replication replays every backfilled row on each replica.

### Unique constraint without blocking

```sql
-- Bad - ACCESS EXCLUSIVE lock blocks all traffic
ALTER TABLE users ADD CONSTRAINT users_email_unique UNIQUE (email);

-- Good (PostgreSQL) - build concurrently, then attach
CREATE UNIQUE INDEX CONCURRENTLY idx_users_email ON users(email);
ALTER TABLE users ADD CONSTRAINT users_email_unique UNIQUE USING INDEX idx_users_email;
```

### Deploy ordering

**Additive** (new column, new table):

1. Deploy migration
2. Deploy code using the new structure

**Non-additive** (rename, type change, drop):

1. Deploy migration adding the new structure (additive, safe)
2. Deploy code that reads the old schema and writes both (expand)
3. Run backfill
4. Deploy code that uses only the new schema
5. Deploy migration dropping the old (contract)

### Ordering multiple migrations in one release

- Additive, fast operations first
- Long-running (backfill, `CONCURRENTLY` index) as separate, independently deployable steps
- Destructive operations last, after a verification period
- Never bundle a fast DDL with a slow backfill in one file

## Output Format

```
## Migration Safety Assessment

**Change type**: [additive | non-additive | destructive]
**Strategy**: [single-phase | expand-contract | scheduled downtime]
**Lock risk**: [Low | Medium | High | Very High] - {reason}
**Backfill required**: [Yes - estimated N rows | No]

## Phases

### Phase 1: Expand

- Action: {what to run}
- Lock risk: {type and estimated duration}
- Rollback: {how to undo}

### Phase 2: Migrate (if applicable)

- Backfill: {batch size, estimated duration, idempotent: yes/no}
- Rollback: {how to undo}

### Phase 3: Contract (if applicable)

- Action: {what to drop}
- Pre-condition: {readers/writers removed and verified}
- Rollback: {restore from backup | not needed}

## Risks

- {high-risk operations called out explicitly}
```

## Avoid

- Exclusive-lock ALTER TABLE on large tables during peak traffic
- Deploying a migration and dependent code in the same release
- Unbounded UPDATE or DELETE on production tables
- Skipping expand-contract for renames or type changes ("just a rename")
- Direct NOT NULL on large PostgreSQL tables (use `NOT VALID` + `VALIDATE CONSTRAINT`)
- Assuming `CREATE INDEX` is fast on large tables (use `CONCURRENTLY` or online DDL)
- Destructive migrations before confirming zero traffic to the old structure
