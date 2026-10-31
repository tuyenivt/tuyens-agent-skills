---
name: backend-db-migration
description: Plan zero-downtime schema changes - expand-contract phasing, lock risk, batched backfill, deploy ordering, rollback. Stack-adaptive.
metadata:
  category: data
  tags: [database, migration, zero-downtime, expand-contract, lock-risk, backfill, multi-stack]
user-invocable: false
---

# DB Migration Safety

> Load `Use skill: stack-detect` first to identify the database engine. The engine version and migration tool come from its `Database` value, an `Additional` line, a reviewed migration or compose image tag (version only), or the repository's migration layout (`alembic.ini` or a `<dir>/versions/` beside `env.py` Alembic, `db/migrate/` Rails, `db/migration/` Flyway, `<app>/migrations/` Django); a value none of them names is `unknown`.

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
- Lock risk is stated for every phase that runs DDL, and every such phase sets a lock timeout (PostgreSQL `lock_timeout`, MySQL `lock_wait_timeout`, SQL Server `SET LOCK_TIMEOUT`) and retries on expiry: even a catalog-only DDL queues behind any open transaction on the table, and every query on the table queues behind it. The phase's Lock risk line names the timeout and retry.
- An ORM that syncs the schema on startup (TypeORM `synchronize`, Hibernate `hbm2ddl.auto=update`) is turned off in a release before the plan's first phase: it applies DDL outside the plan.
- Readers outside the codebase - CDC or logical-replication subscribers, a warehouse table fed from the database, BI queries, another team's job on a replica - are readers: each is named, and its cutover is a pre-condition of the step that breaks it.
- Engine or version unknown: assume worst-case locking (table rewrite, exclusive lock) and record the assumption in the output. Major version known and minor unknown: keep the engine's syntax and assume the worst case for every minor-gated feature. Replica topology unknown: assume replicas exist and throttle.
- A submitted migration file that mixes changes of different types, or bundles a fast DDL with a backfill, is split into one file per block below; the first block in output order names the split in its `Submitted as` line, and each later block's reads `split from <file> - <its part>`.
- Index column choice and type-specific build behaviour (a functional or FULLTEXT index) are `backend-db-indexing`'s; this skill phases the build it hands over.

## Patterns

### Risk by change type

Lock risk is the strength of the lock that blocks concurrent traffic: Low is a metadata lock or an online operation that admits concurrent DML, however long it runs (duration goes in the phase line), High blocks writes or all traffic for the duration of a scan or build, Very High blocks all traffic for a rewrite. The Strategy column names the header Strategy value first. Compatibility is whether old and new code can coexist. They are independent - a rename is cheap to run and impossible to ship in one step.

| Change                              | Lock risk | Compatibility | Strategy                                  |
| ----------------------------------- | --------- | ------------- | ----------------------------------------- |
| Add nullable column (no default)    | Low where metadata-only: PostgreSQL, SQL Server, MySQL 8.0.12+ (`INSTANT`, same limits as the next row); an `INPLACE` rebuild on earlier InnoDB or where `INSTANT` is refused; High on a table with a FULLTEXT index (`ALGORITHM=COPY` only, writes blocked) | Additive | single-phase |
| Add column with constant default    | Low where metadata-only: PostgreSQL 11+ (any non-volatile default, `now()` included), MySQL 8.0.12+ (`ALGORITHM=INSTANT`, appended position only before 8.0.29), SQL Server 2012+ Enterprise (NOT NULL with a runtime-constant default, or nullable `WITH VALUES`; a nullable default without `WITH VALUES` leaves existing rows NULL). Elsewhere: a rewrite - Very High on PostgreSQL, Low but long with 2x disk on InnoDB before 8.0.12 or where `INSTANT` is refused (`ROW_FORMAT=COMPRESSED`, 64 row versions reached on 8.0.29+) (`INPLACE`, concurrent DML); High on a table with a FULLTEXT index (`ALGORITHM=COPY` only, `LOCK=SHARED` blocks writes); a volatile default (`random()`, MySQL `DEFAULT (RAND())`) is a rewrite on PostgreSQL and on MySQL 8.0.13+ is rejected with binary logging on and `COPY`-only without it - add nullable and backfill | Additive | single-phase where metadata-only; otherwise expand-contract without a Contract: add nullable, backfill in batches, then promote the default |
| Create index (non-unique)           | High for a plain build on PostgreSQL (`SHARE` lock blocks writes) and SQL Server, Low for the online build the Strategy column names (SQL Server: Enterprise only; offline and High elsewhere); Low on InnoDB (online by default); Low on a table created empty in the same migration | Additive | single-phase: online build (`CONCURRENTLY` / `LOCK=NONE` / `ONLINE=ON`) as its own deploy step; a unique index follows the unique-constraint row |
| Add NOT NULL                        | Low via the recipe below (PostgreSQL 12+); High as a direct `SET NOT NULL` (full scan under `ACCESS EXCLUSIVE`); MySQL 8.0 `MODIFY ... NOT NULL, ALGORITHM=INPLACE, LOCK=NONE` is a rebuild with concurrent DML (Low lock, long, 2x disk, strict SQL mode; fails on any NULL row - backfill first) | Breaks writers that omit the column | expand-contract: writers first, then the recipe below |
| Add unique constraint / foreign key | Low on PostgreSQL via online unique index + `USING INDEX`, or `NOT VALID` + `VALIDATE`; Low for a unique key on InnoDB (`ADD UNIQUE INDEX, ALGORITHM=INPLACE, LOCK=NONE`) and SQL Server Enterprise (`ADD CONSTRAINT ... UNIQUE ... WITH (ONLINE = ON)`); High direct, and High for a foreign key's validation on MySQL (`ALGORITHM=COPY`) and SQL Server (`WITH CHECK CHECK CONSTRAINT`) | Breaks writers producing violations | expand-contract without a Contract: writers stop producing violations, repair existing rows by query, then the online index or `NOT VALID` path as Promote |
| Rename column                       | Low - catalog-only | Breaks readers and writers | expand-contract |
| Change column type                  | Very High - table rewrite on PostgreSQL and offline SQL Server; High on InnoDB (`ALGORITHM=COPY` under `LOCK=SHARED`: reads allowed, writes blocked for the copy); except binary-coercible widenings (PostgreSQL `varchar(50)` -> `varchar(100)`, InnoDB `VARCHAR` within the same length-prefix size) and SQL Server 2016+ Enterprise `ALTER COLUMN ... WITH (ONLINE = ON)` | Breaks readers and writers | expand-contract |
| Drop column / table                 | Low - a column is catalog-only on PostgreSQL and SQL Server, `INSTANT` on MySQL 8.0.29+, an `INPLACE` rebuild (long, 2x disk, concurrent DML) on earlier InnoDB; a table is a dictionary update plus file removal on every engine | Breaks readers (a column only read) or breaks readers and writers | contract-only, after zero references (reads and writes) are verified; a dropped index likewise, after its reads are gone (MySQL 8.0+: `ALTER TABLE ... ALTER INDEX ... INVISIBLE` first) |

Any operation that rewrites or scans a table above ~1M rows under a lock that blocks traffic is high risk by default; catalog-only operations and online rebuilds that admit concurrent DML are not, whatever the row count or duration.

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

`NOT VALID` + `VALIDATE CONSTRAINT` is the PostgreSQL path for CHECK and FOREIGN KEY constraints on large tables; NOT NULL rides on a CHECK as above. PostgreSQL 18+ can instead add the NOT NULL constraint itself `NOT VALID`, so steps 4-6 can become `ALTER TABLE orders ADD CONSTRAINT orders_tenant_id_nn NOT NULL tenant_id NOT VALID;` then `ALTER TABLE orders VALIDATE CONSTRAINT orders_tenant_id_nn;` (`ShareUpdateExclusiveLock`).

### Engine equivalents

The phasing above is engine-independent; only the mechanism changes. Examples elsewhere in this skill are PostgreSQL - translate before recommending:

| Technique                  | PostgreSQL                          | MySQL 8.0+                                              | SQL Server                              |
| -------------------------- | ----------------------------------- | ------------------------------------------------------- | --------------------------------------- |
| Non-blocking index build   | `CREATE INDEX CONCURRENTLY`         | `ALTER TABLE ... ADD INDEX, ALGORITHM=INPLACE, LOCK=NONE` (the default) | `CREATE INDEX ... WITH (ONLINE = ON)` (Enterprise edition) |
| Add defaulted column       | metadata-only (11+, non-volatile default) | `ALGORITHM=INSTANT` (8.0.12+, appended position only until 8.0.29; not for `ROW_FORMAT=COMPRESSED` or tables with a FULLTEXT index; from 8.0.29, 64 instant changes before a rebuild is forced) | metadata-only on 2012+ Enterprise (NOT NULL with runtime-constant default, or nullable `WITH VALUES`) |
| Constraint without rewrite | `NOT VALID` then `VALIDATE CONSTRAINT` | none: `NOT ENFORCED` (CHECK, 8.0.16+) disables the constraint for new rows too, so verify and repair by query, then add it enforced (`ALGORITHM=COPY` only - a full rebuild under `LOCK=SHARED`, reads allowed and writes blocked for the copy, High on a large table; use `pt-online-schema-change` instead); FK likewise has no deferred validation (`foreign_key_checks=0` for the session permits INPLACE but skips the check for all DML in that session; reset it immediately) | `WITH NOCHECK ADD CONSTRAINT`, then `WITH CHECK CHECK CONSTRAINT` (validates under `Sch-M` - all traffic blocked for the scan, High on a large table; a bare `CHECK CONSTRAINT` leaves it untrusted) |
| Online table rewrite       | none in-core - expand-contract, or logical replication to a rebuilt table | InnoDB `ALGORITHM=INPLACE, LOCK=NONE` rebuilds natively for most operations; `pt-online-schema-change` / `gh-ost` for `COPY`-only operations (most type changes, dropping a PK, charset conversion) and for throttling (both need a PK or unique NOT NULL key; gh-ost needs `binlog_format=ROW`, refuses tables with foreign keys, and refuses tables with triggers before v1.1.8, which adds `--include-triggers`) | online index rebuild (resumable 2017+); column type change online on 2016+ Enterprise for most types, offline before or on other editions |

Verify the operation is online for the exact engine version and edition before recommending it.

### Backfill: bounded batches

```sql
-- Bad - one transaction over the whole table: row locks held for hours, bloat or undo growth,
-- and one replication event replayed serially on every replica
UPDATE large_table SET new_col = old_col WHERE new_col IS NULL;

-- Good - page by ordered key, one batch per transaction, idempotent; stop when the paged SELECT returns fewer than :n rows
-- PostgreSQL
WITH batch AS (SELECT id FROM large_table WHERE id > :last_id AND new_col IS DISTINCT FROM old_col ORDER BY id LIMIT :n),
     upd AS (UPDATE large_table t SET new_col = t.old_col FROM batch
             WHERE t.id = batch.id AND t.new_col IS DISTINCT FROM t.old_col   -- repeated: skips a no-op rewrite of a row dual-written since the subquery ran
             RETURNING t.id)
SELECT count(*), max(id) FROM batch;   -- :last_id = max(id); stop when count < :n (the UPDATE alone may touch fewer rows)
-- MySQL (error 1235 forbids LIMIT in an IN subquery, 1093 the self-referencing subquery; SQL Server: TOP (:n) and OUTPUT INSERTED.id)
SELECT id FROM large_table WHERE id > :last_id AND NOT (new_col <=> old_col) ORDER BY id LIMIT :n;   -- then
UPDATE large_table SET new_col = old_col WHERE id IN (:ids) AND NOT (new_col <=> old_col);   -- repeat the predicate: skips rows already in sync, including any dual-written since the SELECT
```

The predicate compares new to old, so a legitimately NULL source does not match forever; completeness is the count of rows where new and old differ reaching zero (`IS DISTINCT FROM` on PostgreSQL and SQL Server 2022+, `NOT (new_col <=> old_col)` on MySQL, `EXISTS (SELECT new_col EXCEPT SELECT old_col)` on earlier SQL Server). When the new column has no source column, the predicate is `new_col IS NULL` and the value is the change's stated rule; with none stated, Backfill reads `unknown - business value required`. For tables > 100K rows, prefer a background job over an in-migration script. Estimate duration by timing one batch and extrapolating (`rows / batch size x batch time`); with neither a row count nor a measured batch, write `unknown` and treat as large. Each batch commits on its own; one transaction around the loop replays nothing to replicas until the end and holds locks throughout. On replicated databases, sleep between batches and pause when replica lag exceeds threshold - row-based replication replays every backfilled row on each replica. Set the pause threshold below the staleness the read path already tolerates (2 s where reads are replica-routed, 30 s where replicas serve only analytics or CDC; with the tolerance unstated, 2 s marked assumed) and resume at half of it, so the backfill does not oscillate. With no replicas, pace by batch duration on the primary instead (sleep the batch's own runtime between batches).

### Unique constraint without blocking

```sql
-- Bad - ACCESS EXCLUSIVE lock blocks all traffic
ALTER TABLE users ADD CONSTRAINT users_email_unique UNIQUE (email);

-- Good (PostgreSQL) - build concurrently, then attach
CREATE UNIQUE INDEX CONCURRENTLY idx_users_email ON users(email);
ALTER TABLE users ADD CONSTRAINT users_email_unique UNIQUE USING INDEX idx_users_email;
```

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction block. Rails and Django wrap each PostgreSQL migration in one - opt that migration out (`disable_ddl_transaction!`, `atomic = False`); Alembic runs the statement inside `with op.get_context().autocommit_block():`; Flyway runs a migration non-transactionally only when every statement in it is non-transactional (or with `mixed=true`), so keep the build alone in its file, and from Flyway 9.1.2 its default PostgreSQL schema-history lock holds a transaction open that the build waits on forever - set `postgresql.transactional.lock=false`. A cancelled or failed concurrent build leaves an INVALID index that still costs writes - `DROP INDEX CONCURRENTLY` it before retrying.

### Deploy ordering

**Additive** (new column, new table):

1. Deploy migration
2. Deploy code using the new structure (a later release)

**Non-additive** (rename, type change, drop):

1. Deploy migration adding the new structure (additive, safe)
2. Deploy code that reads the old schema and writes both (expand)
3. Run backfill
4. Deploy code that reads the new schema and still writes both
5. Deploy code that stops writing the old (make an old NOT NULL column nullable first); verify zero reads and writes of the old
6. Deploy migration dropping the old (contract)

### Ordering multiple migrations in one release

- Additive, fast operations first
- Long-running (backfill, online index build) as separate, independently deployable steps
- Destructive operations last, after a verification period

## Output Format

One block per change, ordered by the release in which each block's first phase ships (a block's later phases ship in later releases; `Deploy order` carries the sequence); a release carrying several changes never gets one merged block with mixed enums. Phases number from 1 within each block; release numbers are global to the assessment (a block whose first phase ships third starts at release 3, and blocks sharing one deploy hook share a release), and each block's `Deploy order` names the release every phase ships in, so cross-block ordering is read from them. Code releases (dual-write, stop writing the old, and a same-database read cutover) are `Deploy order` lines, not phases; a cross-database move's read cutover is the destination block's Promote phase; a phase that needs a code release live names it in its Pre-condition. `## Risks` closes each block with that block's risks; an assumption shared by several blocks is repeated in each block's `Assumptions`. A lock timeout with no project value renders `lock timeout 5 s (assumed), retry 3 / exponential backoff (assumed)`. A move between two databases is two blocks, one per side, each naming the other in `Linked block`: the destination block is `destination` (Expand, Migrate, Promote - its Promote phase is the cutover where reads switch), the source block is `contract-only` and its Contract phase drops the source after the cutover; completeness is checked as row-count and checksum parity per batch range.

```
## Migration Safety Assessment: {change, e.g. "orders: rename total -> total_amount"}

**Engine:** {database[ / version], migration tool | database[ / version], tool unknown | unknown, migration tool | unknown}

**Submitted as:** {what the migration file does today, its lock risk, and the rule it breaks or "no rule broken" | split from <file> - <its part> | already applied - <what it did> | as planned - nothing submitted yet}

**Change type:** {additive | non-additive | destructive}

**Strategy:** {single-phase | expand-contract | contract-only | destination (cross-database move) | scheduled downtime}

**Lock risk:** {Low | High | Very High} - {the highest phase and why}

**Compatibility:** {additive - old code unaffected | breaks writers | breaks readers | breaks readers and writers} - {who must change first}

**Backfill required:** {Yes - estimated N rows | Yes - row count unknown, treat as large | No}

**Assumptions:** {engine/version/topology assumed, or "none - all inputs known"}

**Linked block:** {the other side of a cross-database move | none}

**Deploy order:** {numbered releases, one line each: what ships, what must already be live}

## Phases                                          {numbered consecutively from 1; only the phases that apply}

### Phase N: {Expand | Apply}                    {Expand for expand-contract (a constraint addition on an existing column starts at Migrate) and destination; Apply for single-phase and scheduled downtime}

- Action: {what to run}
- Pre-condition: {code release N live; each external reader's tolerance of the new structure confirmed (a CDC subscriber's schema handling)}       {only when the phase needs a code release live or an external reader sees this phase}
- Lock risk: {Low | High | Very High} - {type and estimated duration}; lock timeout {value}, retry {count / backoff}
- Rollback: {how to undo}

### Phase N: Migrate                              {when Backfill required is Yes, including existing rows repaired by query}

- Backfill: {batch size, estimated duration or "unknown - time one batch first", idempotent: yes/no | unknown - business value required}
- Pre-condition: {code release N live}       {only when the phase needs a code release live}
- Throttle: {pause condition and resume threshold (replica lag, and replication-slot lag when CDC reads the table) | "no replicas - pace by batch duration" | "assumed replicas - pause above 2 s lag (assumed), resume below 1 s"}
- Lock risk: {Low - DML only, per-batch row locks | High - an InnoDB batch statement that scans the table (no index on the paging key or predicate) and locks every scanned row} - {reason}
- Rollback: {how to undo}

### Phase N: Promote                              {when post-backfill DDL remains: validate, set default, SET NOT NULL; or a cross-database move's read cutover}

- Action: {what to run}
- Pre-condition: {code release N live}       {only when the phase needs a code release live}
- Lock risk: {Low | High | Very High} - {type and estimated duration}; lock timeout {value}, retry {count / backoff} | Low - cutover, no DDL: {how reads switch}
- Rollback: {how to undo}

### Phase N: Contract                             {when an old structure is dropped: contract-only, or expand-contract replacing a structure}

- Action: {what to drop}
- Pre-condition: {readers and writers removed and verified, external readers' cutover named | unverifiable - <why> - go/no-go}
- Lock risk: {Low | High | Very High} - {reason}; lock timeout {value}, retry {count / backoff}
- Rollback: {reverse copy from new structure | archive copy | restore from backup - go/no-go | not needed}

## Risks

- {high-risk operations called out explicitly; any restore-only rollback or unverifiable pre-condition is repeated here as a go/no-go; a rebuild needing 2x disk names the free-space check}
```

`additive` adds a structure old code ignores (a column, table, or non-unique index; a defaulted column on any path); `non-additive` changes or constrains an existing structure (rename, type change, constraint addition - a unique index included) or drops one whose data was copied and verified elsewhere, whether it came from a rename or not; `destructive` removes data that exists nowhere else (drop, truncate, lossy type change). `contract-only` is a drop whose expand and migrate happened in earlier releases. The header `Lock risk` is the maximum across the plan's phases, DDL or DML; the submitted file's own risk goes in `Submitted as`, which for a migration already applied reads `already applied - <what it did>` and the phases become the corrective plan. `**Engine:**` is stack-detect's `Database` value; a version is written only when that value, an `Additional` line, or a reviewed file (a migration, a compose image tag) names one, omitted otherwise, and the tool comes from the `Database` value, an `Additional` line, or the layout rule above. The phases plan the file as submitted; a model that declares the column differently (nullable where the file says NOT NULL) is a Risk, not a reason to plan the model's version. A defaulted column on a rewrite path emits `Expand`, `Migrate`, and `Promote`; a constraint addition on an existing column emits `Migrate` and `Promote`, the writer change being a `Deploy order` line named in Migrate's Pre-condition; a scheduled-downtime change emits one `Apply` phase.

## Avoid

- Exclusive-lock ALTER TABLE on large tables during peak traffic, even when a lock timeout bounds the wait
