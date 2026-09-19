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

- Expand-contract is the default for every non-additive change. A constraint addition (NOT NULL, unique, foreign key) is its own shape of it: expand the writers first, backfill, then validate and promote.
- Backfills are always batched (100-1000 rows, idempotent, monitorable, each batch its own transaction). Never unbounded.
- Application code is backward compatible with both schemas across the transition window, in both directions: new code against the old schema during rollout, and old instances (or a rolled-back deploy) against the new schema.
- Rollback plan is designed before the migration runs.
- Never deploy a migration and the code that depends on it in the same release - rolling deploys leave old instances running against the new schema.
- Flag any migration requiring a database restore to roll back - those are go/no-go decisions. Before accepting one, try to demote it: copying the data to an archive table in the expand phase turns a restore into a re-copy, and a drop whose data exists nowhere else is rarely worth its irreversibility.
- Lock risk is stated for every phase that runs DDL.
- Engine or version unknown: assume worst-case locking (table rewrite, exclusive lock) and record the assumption in the output. Major version known and minor unknown: keep the engine's syntax and assume the worst case for every minor-gated feature. Replica topology unknown: assume replicas exist and throttle.
- A submitted migration file that mixes changes of different types, or bundles a fast DDL with a backfill, is split into one file per block below; the first block's `Submitted as` line names the split.

## Patterns

### Risk by change type

Lock risk is the strength and duration of the lock that blocks concurrent traffic: Low is a brief metadata lock, High blocks writes or all traffic for the duration of a scan or build, Very High blocks all traffic for a rewrite. The Strategy column names the header Strategy value first. Compatibility is whether old and new code can coexist. They are independent - a rename is cheap to run and impossible to ship in one step.

| Change                              | Lock risk | Compatibility | Strategy                                  |
| ----------------------------------- | --------- | ------------- | ----------------------------------------- |
| Add nullable column (no default)    | Low where metadata-only: PostgreSQL, SQL Server, MySQL 8.0.12+ (`INSTANT`, same limits as the next row); an `INPLACE` rebuild on earlier InnoDB | Additive | single-phase; set a lock timeout (PostgreSQL `lock_timeout`, MySQL `lock_wait_timeout`, SQL Server `SET LOCK_TIMEOUT`) so the DDL does not queue behind an open transaction |
| Add column with constant default    | Low where metadata-only: PostgreSQL 11+, MySQL 8.0.12+ (`ALGORITHM=INSTANT`, appended position only before 8.0.29), SQL Server (nullable on any edition; NOT NULL with a runtime-constant default 2012+ Enterprise). Elsewhere or with a volatile default: a rewrite - Very High on PostgreSQL, Low but long with 2x disk on InnoDB 5.6/5.7 (`INPLACE`, concurrent DML) | Additive | single-phase where metadata-only; otherwise expand-contract without a Contract: add nullable, backfill in batches, then promote the default |
| Create index                        | High on PostgreSQL (`SHARE` lock blocks writes) and SQL Server offline builds; Low on InnoDB (online by default); Low on a table created empty in the same migration | Additive | single-phase: online build (`CONCURRENTLY` / `LOCK=NONE` / `ONLINE=ON`) as its own deploy step; a unique index needs a duplicate check by query first |
| Add NOT NULL                        | Low via the recipe below (PostgreSQL 12+); High as a direct `SET NOT NULL` (full scan under `ACCESS EXCLUSIVE`) | Breaks writers that omit the column | expand-contract: writers first, then the recipe below |
| Add unique constraint / foreign key | Low via online unique index + `USING INDEX`, or `NOT VALID` + `VALIDATE`; High direct | Breaks writers producing violations | single-phase: validate existing rows by query first, then the online index or `NOT VALID` path |
| Rename column                       | Low - catalog-only | Breaks readers and writers | expand-contract |
| Change column type                  | Very High - table rewrite, except binary-coercible widenings (PostgreSQL `varchar(50)` -> `varchar(100)`, InnoDB `VARCHAR` within the same length-prefix size) and SQL Server 2016+ Enterprise `ALTER COLUMN ... WITH (ONLINE = ON)` | Breaks readers and writers | expand-contract |
| Drop column / table                 | Low - a column is catalog-only on PostgreSQL and SQL Server, `INSTANT` on MySQL 8.0.29+, an `INPLACE` rebuild (long, 2x disk, concurrent DML) on earlier InnoDB; a table is a dictionary update plus file removal on every engine | Breaks readers (a column only read) or breaks readers and writers | contract-only, after zero references (reads and writes) are verified |

Any operation that rewrites or scans a table above ~1M rows under a lock that blocks traffic is high risk by default; catalog-only operations are not, whatever the row count.

### Expand-contract (default for non-additive)

1. **Expand**: add the new structure alongside the old; deploy app that reads the old and writes both (dual-write). During a rolling deploy, old instances still write only the old structure - either start the backfill after rollout completes or sync via database trigger.
2. **Migrate**: backfill old to new in batches; re-run until drift is zero; validate completeness.
3. **Promote** (constraint additions and defaulted columns): the post-backfill DDL - validate the constraint, set the default, `SET NOT NULL`.
4. **Contract**: deploy app using only the new structure; verify zero references to the old (code search + query/statement logs over a verification period); drop the old.

Skip only when the change is purely additive, the expand already shipped in an earlier release (contract-only), or downtime is scheduled (a single Apply phase inside the window).

### Adding NOT NULL on a large table (PostgreSQL 12+)

A direct `ALTER COLUMN ... SET NOT NULL` scans the table under an exclusive lock. Split it; the order matters because a `NOT VALID` constraint is enforced on every row inserted or updated from the moment it exists, so it must follow the code that populates the column:

```sql
-- 1. Expand: add nullable (brief exclusive lock, metadata-only)
ALTER TABLE orders ADD COLUMN tenant_id UUID;

-- 2. Deploy code that writes tenant_id on every insert and update (or add a constant default)

-- 3. Migrate: backfill existing rows in batches (background job, see below)

-- 4. Promote: add the constraint NOT VALID - enforced for new and updated rows, existing rows unchecked
ALTER TABLE orders ADD CONSTRAINT orders_tenant_id_not_null
  CHECK (tenant_id IS NOT NULL) NOT VALID;

-- 5. Validate existing rows (ShareUpdateExclusiveLock - concurrent reads/writes OK)
ALTER TABLE orders VALIDATE CONSTRAINT orders_tenant_id_not_null;

-- 6. PostgreSQL 12+ uses the validated CHECK to skip the scan
ALTER TABLE orders ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE orders DROP CONSTRAINT orders_tenant_id_not_null;
```

`NOT VALID` + `VALIDATE CONSTRAINT` is the PostgreSQL path for CHECK and FOREIGN KEY constraints on large tables; NOT NULL rides on a CHECK as above.

### Engine equivalents

The phasing above is engine-independent; only the mechanism changes. Examples elsewhere in this skill are PostgreSQL - translate before recommending:

| Technique                  | PostgreSQL                          | MySQL 8.0+                                              | SQL Server                              |
| -------------------------- | ----------------------------------- | ------------------------------------------------------- | --------------------------------------- |
| Non-blocking index build   | `CREATE INDEX CONCURRENTLY`         | `ALTER TABLE ... ADD INDEX, ALGORITHM=INPLACE, LOCK=NONE` (the default) | `CREATE INDEX ... WITH (ONLINE = ON)` (Enterprise edition) |
| Add defaulted column       | metadata-only (11+, constant default) | `ALGORITHM=INSTANT` (8.0.12+, appended position only until 8.0.29; not for `ROW_FORMAT=COMPRESSED` or tables with a FULLTEXT index; from 8.0.29, 64 instant changes before a rebuild is forced) | metadata-only (nullable: any edition; NOT NULL with runtime-constant default: 2012+ Enterprise) |
| Constraint without rewrite | `NOT VALID` then `VALIDATE CONSTRAINT` | none: `NOT ENFORCED` (CHECK, 8.0.16+) disables the constraint for new rows too, so verify and repair by query, then add it enforced (`INPLACE`, no rebuild, but DML is blocked for the validation scan - High on a large table); FK likewise has no deferred validation (`foreign_key_checks=0` for the session permits INPLACE but skips the check for all DML in that session; reset it immediately) | `WITH NOCHECK ADD CONSTRAINT`, then `WITH CHECK CHECK CONSTRAINT` (validates; a bare `CHECK CONSTRAINT` leaves it untrusted) |
| Online table rewrite       | none in-core - expand-contract, or logical replication to a rebuilt table | InnoDB `ALGORITHM=INPLACE, LOCK=NONE` rebuilds natively for most operations; `pt-online-schema-change` / `gh-ost` for `COPY`-only operations (most type changes, dropping a PK, charset conversion) and for throttling (both need a PK or unique NOT NULL key; gh-ost needs `binlog_format=ROW` and refuses tables with foreign keys or triggers) | online index rebuild (resumable 2017+); column type change online on 2016+ Enterprise for most types, offline before or on other editions |

Verify the operation is online for the exact engine version and edition before recommending it. When the version is unknown, the unknown-engine rule applies: assume a rewrite and say so.

### Backfill: bounded batches

```sql
-- Bad - one transaction over the whole table: row locks held for hours, bloat or undo growth,
-- and one replication event replayed serially on every replica
UPDATE large_table SET new_col = old_col WHERE new_col IS NULL;

-- Good - page by ordered key, one batch per transaction, idempotent; stop when a batch returns fewer than :n rows
-- PostgreSQL
UPDATE large_table SET new_col = old_col
WHERE id IN (SELECT id FROM large_table WHERE id > :last_id AND new_col IS DISTINCT FROM old_col ORDER BY id LIMIT :n)
RETURNING id;   -- :last_id = max(id) returned
-- MySQL (error 1093 forbids the self-referencing subquery; SQL Server: TOP (:n) and OUTPUT INSERTED.id)
SELECT id FROM large_table WHERE id > :last_id AND NOT (new_col <=> old_col) ORDER BY id LIMIT :n;   -- then
UPDATE large_table SET new_col = old_col WHERE id IN (:ids) AND NOT (new_col <=> old_col);   -- repeat the predicate: a dual-written row must not be reverted
```

The predicate compares new to old, so a legitimately NULL source does not match forever; completeness is the count of rows where new and old differ reaching zero (`IS DISTINCT FROM` on PostgreSQL and SQL Server 2022+, `NOT (new_col <=> old_col)` on MySQL, `EXISTS (SELECT new_col EXCEPT SELECT old_col)` on earlier SQL Server). For tables > 100K rows, prefer a background job over an in-migration script. Estimate duration by timing one batch and extrapolating (`rows / batch size x batch time`); with neither a row count nor a measured batch, write `unknown` and treat as large. Each batch commits on its own; one transaction around the loop replays nothing to replicas until the end and holds locks throughout. On replicated databases, sleep between batches and pause when replica lag exceeds threshold - row-based replication replays every backfilled row on each replica. Set the pause threshold below the staleness the read path already tolerates (a second or two where reads are replica-routed, more where replicas only serve analytics) and resume at half of it, so the backfill does not oscillate. With no replicas, pace by batch duration on the primary instead (sleep the batch's own runtime between batches).

### Unique constraint without blocking

```sql
-- Bad - ACCESS EXCLUSIVE lock blocks all traffic
ALTER TABLE users ADD CONSTRAINT users_email_unique UNIQUE (email);

-- Good (PostgreSQL) - build concurrently, then attach
CREATE UNIQUE INDEX CONCURRENTLY idx_users_email ON users(email);
ALTER TABLE users ADD CONSTRAINT users_email_unique UNIQUE USING INDEX idx_users_email;
```

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction block: migration tools that wrap each migration in one (Rails, Django on PostgreSQL, Flyway) must opt that migration out (`disable_ddl_transaction!`, `atomic = False`). A cancelled or failed concurrent build leaves an INVALID index that still costs writes - `DROP INDEX CONCURRENTLY` it before retrying.

### Deploy ordering

**Additive** (new column, new table):

1. Deploy migration
2. Deploy code using the new structure (a later release)

**Non-additive** (rename, type change, drop):

1. Deploy migration adding the new structure (additive, safe)
2. Deploy code that reads the old schema and writes both (expand)
3. Run backfill
4. Deploy code that uses only the new schema
5. Deploy migration dropping the old (contract)

### Ordering multiple migrations in one release

- Additive, fast operations first
- Long-running (backfill, online index build) as separate, independently deployable steps
- Destructive operations last, after a verification period
- Never bundle a fast DDL with a slow backfill in one file

## Output Format

One block per change, ordered by the release in which each block's first phase ships (a block's later phases ship in later releases; `Deploy order` carries the sequence); a release carrying several changes never gets one merged block with mixed enums. A move between two databases is two blocks, one per side, each naming the other in `Linked block`: the destination block is `destination` (Expand, Migrate, Promote - its Promote phase is the cutover where reads switch), the source block is `contract-only` and its Contract phase drops the source after the cutover; completeness is checked as row-count and checksum parity per batch range.

```
## Migration Safety Assessment: {change, e.g. "orders: rename total -> total_amount"}

**Engine**: {database / version, migration tool | unknown}

**Submitted as**: {what the migration file does today and the rule it breaks | as planned - nothing submitted yet}

**Change type**: {additive | non-additive | destructive}

**Strategy**: {single-phase | expand-contract | contract-only | destination (cross-database move) | scheduled downtime}

**Lock risk**: {None | Low | High | Very High} - {the highest phase and why}

**Compatibility**: {additive - old code unaffected | breaks writers | breaks readers | breaks readers and writers} - {who must change first}

**Backfill required**: {Yes - estimated N rows | Yes - row count unknown, treat as large | No}

**Assumptions**: {engine/version/topology assumed, or "none - all inputs known"}

**Linked block**: {the other side of a cross-database move | none}

**Deploy order**: {numbered releases, one line each: what ships, what must already be live}

## Phases                                          {numbered consecutively from 1; only the phases that apply}

### Phase N: {Expand | Apply}                    {Expand for expand-contract and destination; Apply for single-phase and scheduled downtime}

- Action: {what to run}
- Lock risk: {Low | High | Very High} - {type and estimated duration}
- Rollback: {how to undo}

### Phase N: Migrate                              {when Backfill required is Yes}

- Backfill: {batch size, estimated duration or "unknown - time one batch first", idempotent: yes/no}
- Throttle: {pause condition and resume threshold | "no replicas - pace by batch duration" | "assumed replicas - pause above N s lag"}
- Lock risk: {None - DML only | Low | High} - {reason}
- Rollback: {how to undo}

### Phase N: Promote                              {when post-backfill DDL remains: validate, set default, SET NOT NULL, cutover}

- Action: {what to run}
- Lock risk: {Low | High | Very High} - {type and estimated duration}
- Rollback: {how to undo}

### Phase N: Contract                             {when Strategy is expand-contract or contract-only}

- Action: {what to drop}
- Pre-condition: {readers and writers removed and verified | unverifiable - <why> - go/no-go}
- Lock risk: {Low | High | Very High} - {reason}
- Rollback: {reverse copy from new structure | archive copy | restore from backup - go/no-go | not needed}

## Risks

- {high-risk operations called out explicitly; any restore-only rollback or unverifiable pre-condition is repeated here as a go/no-go}
```

`destructive` means the change removes data that exists nowhere else (drop, truncate, lossy type change); a drop of a structure whose data was copied and verified elsewhere stays `non-additive`, whether it came from a rename or not. `contract-only` is a drop whose expand and migrate happened in earlier releases. The header `Lock risk` is the maximum across all phases, DDL or DML, `None` when no phase holds a blocking lock. A single-phase change with a backfill emits `Apply`, `Migrate`, and `Promote` when DDL follows the backfill; a scheduled-downtime change emits one `Apply` phase.

## Avoid

- Exclusive-lock ALTER TABLE on large tables during peak traffic
- Deploying a migration and dependent code in the same release
- Unbounded UPDATE or DELETE on production tables
- Skipping expand-contract for renames or type changes ("just a rename")
- Direct `SET NOT NULL` on large PostgreSQL tables (use the CHECK NOT VALID recipe)
- Assuming `CREATE INDEX` is fast on large tables (use `CONCURRENTLY` or online DDL)
- Destructive migrations before confirming zero traffic to the old structure
