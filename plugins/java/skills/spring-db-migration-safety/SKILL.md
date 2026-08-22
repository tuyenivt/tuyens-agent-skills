---
name: spring-db-migration-safety
description: "Safe Flyway / Liquibase migrations for zero-downtime: expand-then-contract, NOT NULL backfill, concurrent indexes, rollback strategy."
metadata:
  category: backend
  tags: [flyway, liquibase, migrations, zero-downtime, ddl, spring-boot]
user-invocable: false
---

# DB Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Live-system schema changes (add / modify / remove columns or constraints)
- Zero-downtime deployment planning
- Reviewing migrations before merge

## Rules

- Every migration in release N must be backward-compatible with release N-1 code (rolling deploys run both versions).
- Destructive changes (NOT NULL, rename, drop) span multiple releases via expand-then-contract.
- One concern per migration file: DDL and DML separate; one DDL statement per file.
- Large-table DDL must be non-blocking - Postgres `CONCURRENTLY`, MySQL `ALGORITHM=INPLACE, LOCK=NONE`.
- DDL on hot tables: `SET lock_timeout = '5s'` (MySQL: `SET SESSION lock_wait_timeout = 5`) - a blocked ALTER queues behind long transactions and blocks all traffic behind it. A timeout abort is safe to retry: re-run the migration once the blocker clears.
- Anything long-running is an ops step, not a startup migration - batched backfills, `CREATE INDEX CONCURRENTLY` and `VALIDATE CONSTRAINT` on a large table all outlast a readiness probe and hold Flyway's lock while every other pod fails startup. Run them out of band, then record them as a guarded, idempotent versioned file (`IF NOT EXISTS` / `DO $$ IF NOT EXISTS ... $$`) so a fresh environment reproduces the schema from the files alone.
- A `NOT VALID` CHECK or FK is not "unenforced": it applies to every new write immediately. It ships only after the release that populates the column is fully rolled out, or the still-running N-1 pods start failing inserts.
- `spring.jpa.hibernate.ddl-auto: validate` beyond local; never `update`.
- Forward-only fixes: amending a merged migration breaks Flyway checksum validation. Ship a new `Vx__revert_*.sql`.
- Liquibase: declare `<rollback>` for every non-auto-reversible changeset.

## Patterns

### Three-step NOT NULL

On Postgres 11+ `ADD COLUMN ... NOT NULL DEFAULT <constant>` is metadata-only (safe). The three-step is for values computed per row (backfill from another table) or volatile defaults, where a one-statement approach rewrites the table under ACCESS EXCLUSIVE:

```sql
-- V1__add_status_nullable.sql (release N)
ALTER TABLE orders ADD COLUMN status VARCHAR(50);

-- Backfill: NOT a versioned migration (Flyway would run it at startup in one
-- transaction, stalling the deploy). Run batched from a job/ops script:
--   UPDATE orders SET status = 'PENDING' WHERE status IS NULL AND id BETWEEN :lo AND :hi;

-- V2__constrain_status.sql (release N+1, after backfill verified:
-- SELECT count(*) ... WHERE status IS NULL returns 0)
ALTER TABLE orders ALTER COLUMN status SET NOT NULL;
```

Batching avoids long-held locks and WAL bloat. Before the constraining step, gate on the rows that can never satisfy it (`SELECT count(*) ... WHERE <join misses or source is null>`) - finding them at `SET NOT NULL` time is far more expensive. Build the index *after* the backfill, not before: every backfilled row otherwise becomes a non-HOT update maintaining an index you are about to bloat. Throttle on replica lag, and expect the heap to roughly double until autovacuum catches up.

`SET NOT NULL` on an *existing* column scans the whole table under an ACCESS EXCLUSIVE lock. Postgres 12+ skips the scan if a validated equivalent CHECK already proves no nulls - add `CHECK (status IS NOT NULL) NOT VALID`, `VALIDATE CONSTRAINT` (lock-free), then `SET NOT NULL` (now instant), then drop the CHECK.

MySQL (InnoDB): `MODIFY ... NOT NULL` runs `INPLACE` but rebuilds the table - concurrent DML keeps working, IO is heavy; schedule off-peak. The same three-step (nullable, backfill job, constrain) applies.

### Rename via expand-then-contract (three releases)

A rename is never one release: release N adds the new column and dual-writes; release N+1 stops referencing the old column; the drop ships in N+2. Dropping in N+1 breaks the still-running N instances mid-rolling-deploy (Flyway runs on the first new instance's startup while old code still writes the old column).

```sql
-- V1__add_customer_id.sql (release N - expand)
ALTER TABLE orders ADD COLUMN customer_id BIGINT;

-- Backfill (release N): batched job/ops script, not a versioned migration:
--   UPDATE orders SET customer_id = customer_ref
--   WHERE customer_id IS NULL AND id BETWEEN :lo AND :hi;

-- (release N+1: code reads/writes customer_id only - no migration)

-- V2__drop_customer_ref.sql (release N+2 - contract, after N+1 fully deployed)
ALTER TABLE orders DROP COLUMN customer_ref;
```

During release N both columns are live. Mirror them unconditionally in **one** direction - from whichever column that release treats as authoritative - and flip the direction at the read switch:

```java
// Release N: old column is authoritative (N-1 pods still write only it)
@PrePersist @PreUpdate
void syncCustomerColumns() { customerId = customerRef; }
// Release N+1 flips to: customerRef = customerId;
```

A fill-the-null-side guard (`if (a == null) a = b`) looks safer and is not: once the backfill has populated both, an update to one column leaves the other permanently stale. `@PrePersist`/`@PreUpdate` also do not fire for bulk JPQL or native updates - dual-write those call sites explicitly, or use a DB trigger when the writers cannot be enumerated.

Gate read-path switches with a feature flag so a bad release can flip back without a migration.

### Concurrent index creation

Flyway wraps each script in a transaction. `CREATE INDEX CONCURRENTLY` cannot run inside one - opt out per file:

```sql
-- V20__idx_orders_customer.sql
-- flyway:executeInTransaction=false
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_customer ON orders(customer_id);
```

A failed `CREATE INDEX CONCURRENTLY` leaves an INVALID index behind (it is not rolled back - the script ran outside a transaction). `IF NOT EXISTS` will not replace it; `DROP INDEX CONCURRENTLY` first, then re-run. Liquibase equivalent of the opt-out: `runInTransaction="false"` on the changeset.

MySQL equivalent (InnoDB):

```sql
ALTER TABLE orders ADD INDEX idx_orders_customer (customer_id),
  ALGORITHM=INPLACE, LOCK=NONE;
```

### CHECK constraints

Database-level safety when validation is bypassed (manual SQL, admin scripts, other services):

```sql
ALTER TABLE payments ADD CONSTRAINT payments_status_check
    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'));
```

On large tables add as `NOT VALID` first, then `VALIDATE CONSTRAINT` separately to avoid a full-table scan under lock.

### Rollback strategy

Flyway Community has no automatic undo. Schema is forward-only:

- `DROP COLUMN` / `DROP TABLE` recoverable only from PITR or backup - document the recovery window.
- Mistakes ship as a forward `Vx__revert_*.sql`; never edit a merged migration (checksum mismatch fails `validate-on-migrate`).
- "Rollback tested" means: migration applied on a Testcontainers clone of prod-shape data, revert migration applied, N-1 app boots and passes smoke tests.

Liquibase: prefer auto-reversible changes (`addColumn`, `addNotNullConstraint`); for `sql`/`dropColumn` declare an explicit `<rollback>`. Declarative changes cannot carry `ALGORITHM=` / `LOCK=`, so on a large MySQL table use raw `<sql>` plus an explicit `<rollback>` - forcing the algorithm makes an impossible in-place change fail immediately instead of silently copying the table. MySQL commits DDL implicitly, so DDL changesets need `runInTransaction="false"`.

### CI validation

```java
@SpringBootTest @Testcontainers
class MigrationIntegrityTest {
    @Container @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired Flyway flyway;
    @Autowired JdbcTemplate jdbc;

    // Boot already ran migrate() during context startup - re-invoking it asserts on a no-op.
    @Test
    void allMigrationsApplyAndValidate() {
        flyway.validate();   // checksum + ordering
    }

    // Guarded ops-step record files are no-ops in prod, so assert the end state, not the file list.
    @Test
    void schemaMatchesIntent() {
        assertThat(jdbc.queryForObject("""
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = 'orders' AND column_name = 'status'""", String.class))
            .isEqualTo("NO");
    }
}
```

### Flyway conventions

Versioned: `V{yyyyMMdd}_{HHmm}__{description}.sql`. Repeatable: `R__{description}.sql` for views/functions/triggers (re-runs on checksum change). The `V1`/`V2` names in this skill's examples are shorthand - real files follow the timestamp convention.

```yaml
spring:
  flyway:
    validate-on-migrate: true
  jpa:
    hibernate.ddl-auto: validate
```

## Output Format

Open multi-release plans with one line mapping releases to steps (`Plan: N: V1 + backfill job; N+1: code switch; N+2: V2`), then one block per migration, ops step, or job, with any explanation in prose after its block. Reviews: emit one block per DDL/DML statement when a file carries several (a four-statement file cannot fill one `Operation`), then the corrected `Plan:` line.

```
Migration: {filename | ops step: <command> | backfill job}
Release: {N | N+1 | N+2 | N+3 | ops step during <release>}
Type: {DDL | DML}
Operation: {ADD_COLUMN | MODIFY_COLUMN | ADD_INDEX | DROP_INDEX | BACKFILL | DROP_COLUMN | RENAME | CONSTRAINT | unknown - file not supplied}
Table: {name}
Phase: {expand | migrate | contract}
Locks Table: {yes | brief-metadata | no}
Concurrency Safe: {yes-CONCURRENTLY | yes-INPLACE | yes-metadata-only | yes-batched | no}
Backward Compatible With N-1: {yes | no - what changes with code release}
Rollback: {auto-reversible | liquibase-rollback | forward-fix | restore-from-backup}
```

`yes-batched` is the value for a batched DML job: short per-batch row locks, no table lock. Reserve `no` for a statement that blocks traffic.

## Avoid

- `ADD COLUMN ... NOT NULL DEFAULT ...` with a computed/volatile default on large tables (full rewrite under lock; constant defaults are metadata-only on PG 11+).
- Dropping a column in the same release that stops reading it - contract one release later, after that code is fully deployed.
- Blocking index creation on large tables (omitting `CONCURRENTLY` / `INPLACE`).
- Editing a merged migration to "fix" it - breaks checksum validation downstream.
- Unbounded `UPDATE` for backfill - batch by primary key range.
- `flyway.clean()` outside ephemeral test containers.
