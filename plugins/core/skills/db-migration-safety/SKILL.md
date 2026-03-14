---
name: db-migration-safety
description: Universal zero-downtime database migration patterns - expand-contract, lock risk, backfill safety. Language-specific migration skills (spring-db-migration-safety, go-migration-safety, etc.) wrap this with ecosystem-specific tooling.
metadata:
  category: data
  tags: [database, migration, zero-downtime, expand-contract, lock-risk, backfill, multi-stack]
user-invocable: false
---

# DB Migration Safety

> Load `Use skill: stack-detect` first to identify the database engine and migration tool in use.

## When to Use

- Planning any schema change on a production database
- Evaluating whether a migration is safe to run without downtime
- Designing an expand-contract migration sequence
- Estimating lock risk and backfill duration before committing to a migration

## Core Patterns

### Expand-Contract (Default Strategy)

For any non-additive change (rename, type change, drop, add NOT NULL), use three phases:

**Phase 1 - Expand**: Add the new structure alongside the old. Application handles both.

**Phase 2 - Migrate**: Backfill data from old to new. Validate completeness before proceeding.

**Phase 3 - Contract**: Remove the old structure once all code uses the new.

Skip expand-contract only when:

- The change is purely additive (new nullable column, new table with no existing data dependency)
- Downtime is explicitly scheduled and acceptable

### Lock Risk by Change Type

| Change                              | Lock Risk | Zero-Downtime Strategy                    |
| ----------------------------------- | --------- | ----------------------------------------- |
| Add nullable column (no default)    | Low       | Single phase, safe                        |
| Add column with default (modern DB) | Low       | Single phase, metadata-only               |
| Add column with default (old DB)    | High      | Table rewrite - use expand-contract       |
| Create index                        | High      | Use `CONCURRENTLY` or online DDL          |
| Add NOT NULL constraint             | High      | Backfill nulls first, then add constraint |
| Add unique constraint               | High      | Validate data uniqueness first            |
| Add foreign key                     | High      | Validate referential integrity first      |
| Rename column                       | Very High | Expand-contract required                  |
| Change column type                  | Very High | Expand-contract required                  |
| Drop column                         | High      | Remove all code references first          |
| Drop table                          | High      | Remove all references first               |

Flag any operation with an exclusive lock on a table estimated above 1M rows as high risk.

### PostgreSQL: Zero-Downtime NOT NULL Constraint Addition

For PostgreSQL tables with >1M rows, `ADD COLUMN col NOT NULL` takes an exclusive table lock for the full backfill duration. Use this 4-step sequence instead:

```sql
-- Step 1: Add column as nullable (fast, no lock)
ALTER TABLE orders ADD COLUMN tenant_id UUID;

-- Step 2: Backfill in batches (run as background job)
UPDATE orders SET tenant_id = 'default-tenant-uuid'
WHERE id BETWEEN :start AND :end AND tenant_id IS NULL;

-- Step 3: Add constraint as NOT VALID (validates new rows only - no full table scan)
ALTER TABLE orders ADD CONSTRAINT orders_tenant_id_not_null
  CHECK (tenant_id IS NOT NULL) NOT VALID;

-- Step 4: Validate existing rows in background (ShareUpdateExclusiveLock - allows concurrent reads/writes)
ALTER TABLE orders VALIDATE CONSTRAINT orders_tenant_id_not_null;
```

Use `NOT VALID` + `VALIDATE CONSTRAINT` whenever adding any constraint (NOT NULL, CHECK, FK) to a table with >1M rows. The `VALIDATE CONSTRAINT` step acquires only a `ShareUpdateExclusiveLock`, allowing concurrent reads and writes. This applies to PostgreSQL; MySQL and SQL Server have different online DDL mechanisms (check stack-detect Database field).

### Backfill Safety Rules

**Never run unbounded updates on production tables:**

```sql
-- DANGEROUS
UPDATE large_table SET new_col = old_col WHERE new_col IS NULL;

-- SAFE: batch in a loop until 0 rows updated
UPDATE table SET new_col = old_col
WHERE id BETWEEN :start AND :end
  AND new_col IS NULL
LIMIT 1000;
```

Backfill requirements:

- Always batch: 100-1000 rows per batch depending on row width and table hotness
- Must be idempotent: safe to re-run after failure
- Prefer a background job over an in-migration script for tables >100K rows
- Monitor progress with a row count query between batches

### Deploy Ordering

**Additive changes (add column, add table):**

1. Deploy migration (schema change)
2. Deploy application code that uses the new structure

**Non-additive changes (rename, type change, drop):**

1. Deploy application code that handles both old and new schema (expand)
2. Deploy migration (add new structure)
3. Deploy backfill
4. Deploy application code that uses only new schema
5. Deploy migration to remove old structure (contract)

**Never deploy migration and application code that requires the migration atomically** - rolling deployments mean some instances still run old code after the migration runs.

## Output Format

When surfacing migration safety analysis:

```markdown
## Migration Safety Assessment

**Change type**: [additive | non-additive | destructive]
**Strategy**: [single-phase | expand-contract | scheduled downtime]
**Lock risk**: [Low | Medium | High] - [reason]
**Backfill required**: [Yes - estimated N rows | No]

## Phases

### Phase 1: Expand

- Action: [what to run]
- Lock risk: [type and estimated duration]
- Rollback: [how to undo]

### Phase 2: Migrate (if applicable)

- Backfill: [batch size, estimated duration, idempotent: yes/no]
- Rollback: [how to undo]

### Phase 3: Contract (if applicable)

- Action: [what to drop]
- Pre-condition: [all readers/writers removed, verified]
- Rollback: [restore from backup | not needed]

## Risks

- [Any high-risk operations called out explicitly]
```

## Rules

- Rollback plan designed before the migration runs, not after it fails
- Expand-contract is the default for all non-additive changes
- Backfill operations must always be batched - never unbounded
- Application code must be backward compatible with both schemas during the transition window
- Flag changes requiring a database restore to roll back - these are go/no-go decision points

## Avoid

- Running ALTER TABLE with exclusive lock on large tables during peak traffic
- Deploying migration and application code that depends on it in the same release (rolling deploys mean old code runs against new schema)
- Unbounded UPDATE or DELETE on production tables (always batch by ID range)
- Skipping expand-contract for renames or type changes ("it's just a rename" causes downtime)
- Adding NOT NULL constraints directly on large PostgreSQL tables (use NOT VALID + VALIDATE CONSTRAINT)
- Assuming CREATE INDEX is fast on large tables (use CONCURRENTLY or online DDL)
- Running destructive migrations (DROP COLUMN/TABLE) before confirming zero reads/writes to the old structure
