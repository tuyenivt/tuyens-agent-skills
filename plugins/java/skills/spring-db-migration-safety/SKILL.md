---
name: spring-db-migration-safety
description: "Safe Flyway / Liquibase migrations for zero-downtime: expand-then-contract, NOT NULL backfill, concurrent indexes, rollback strategy."
metadata:
  category: backend
  tags: [flyway, liquibase, migrations, zero-downtime, ddl, spring-boot]
user-invocable: false
---

# DB Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack. Its `Database` sets the engine; the migration tool comes from the build file (`spring-boot-starter-flyway` / `spring-boot-starter-liquibase`, or a bare `flyway-core` / `liquibase-core`) or the directory (`db/migration` vs `db/changelog`). `Database: unknown` - give both the PostgreSQL and MySQL variant of every statement; another engine (MariaDB, SQL Server, Oracle) gets the generic rules and a note that the engine-specific lines do not apply. PostgreSQL major version from the Tech Stack or the Testcontainers image tag; unknown -> 12+ assumed and stated.

## When to Use

- Live-system schema changes (add / modify / remove columns, indexes, constraints)
- Zero-downtime deployment planning
- Reviewing migrations before merge; recovering from a failed migration

## Rules

- Every migration in release N must be backward-compatible with release N-1 code - rolling deploys run both, and Flyway/Liquibase run at the first new pod's startup while old pods still serve.
- Destructive changes (NOT NULL on existing data, rename, drop) span multiple releases via expand-then-contract.
- One concern per migration file: DDL and DML separate; one DDL statement per file (on MySQL DDL commits implicitly, so a multi-statement file that fails midway is partially applied).
- Large-table DDL must be non-blocking. PostgreSQL: `CONCURRENTLY` for indexes, `NOT VALID` + `VALIDATE` for constraints. MySQL 8.0 / Aurora MySQL 3: `ALGORITHM=INSTANT` where supported - add column (end of table before 8.0.29, any position from 8.0.29), drop column (8.0.29+ = Aurora 3.05+), rename column (8.0.28+ = Aurora 3.04+), change default; at most 64 INSTANT add/drop row versions per table before a rebuild is required. INSTANT accepts only `LOCK=DEFAULT`. Otherwise `ALGORITHM=INPLACE, LOCK=NONE`. Widening a `VARCHAR` is in-place only while its byte length stays on the same side of 255 bytes (utf8mb4 = 4 bytes/char: `VARCHAR(32)` -> `VARCHAR(64)` crosses it and copies the table). A change that needs `ALGORITHM=COPY` on a large table goes through an online schema-change tool (gh-ost, pt-online-schema-change).
- DDL that takes a table lock (ALTER TABLE, plain CREATE INDEX) on a hot table sets a lock timeout so a blocked statement cannot queue all traffic behind it. PostgreSQL: `SET LOCAL lock_timeout = '5s'` in transactional scripts; in `executeInTransaction=false` scripts `SET lock_timeout`, then `RESET lock_timeout` at the end (a session setting leaks to later scripts and pooled app connections). MySQL: `SET SESSION lock_wait_timeout = 5`, then `SET SESSION lock_wait_timeout = DEFAULT` at the end. Not on `CREATE INDEX CONCURRENTLY`: it blocks no DML, and its waits on older transactions would hit the timeout and leave an INVALID index. A timeout abort on a PostgreSQL transactional script leaves nothing behind - re-run once the blocker clears; on MySQL or a non-transactional script, recover per Failed migrations below.
- Anything expected to outlast the readiness probe window is an ops step, not a startup migration: batched backfills, `CREATE INDEX CONCURRENTLY` / `VALIDATE CONSTRAINT` on a large table, MySQL INPLACE rebuilds of a large table. It holds the migration lock while every other new pod fails startup. Run it out of band, then record it as a guarded, idempotent versioned file (`CREATE INDEX CONCURRENTLY IF NOT EXISTS`; constraints via a `DO` block, below) so a fresh environment reproduces the schema from the files alone.
- A `NOT VALID` CHECK or FK applies to every new write immediately. It ships only after the release that populates the column is fully rolled out, or still-running N-1 pods start failing inserts.
- `spring.jpa.hibernate.ddl-auto: validate` beyond local; never `update`. `validate` fails startup when a mapped column is missing or has an incompatible type - so a column is dropped or renamed only after no running release maps it. It does not check length or nullability.
- Forward-only: never edit a migration that succeeded anywhere (checksum validation fails downstream). Ship a new `Vx__revert_*.sql`. Liquibase: declare `<rollback>` for every non-auto-reversible changeset.

## Patterns

### NOT NULL on a new column

PostgreSQL 11+ `ADD COLUMN ... NOT NULL DEFAULT <non-volatile expr>` is metadata-only (constants and STABLE functions like `now()`); only volatile defaults (`random()`, `clock_timestamp()`, `gen_random_uuid()`) rewrite the table. MySQL 8.0 adds a column with a default via `ALGORITHM=INSTANT`. So a column whose value is the same for every row is one migration.

The multi-release path is for values computed per row (from another column or table). Release N adds the column nullable and its code writes it on every insert; rows the still-running N-1 pods insert during the rollout stay NULL, and the backfill after rollout fills them. A DEFAULT would give those rows a wrong value the `IS NULL` backfill never revisits - and a DEFAULT that the backfill then contradicts ships wrong data (`[Must]`):

```sql
-- V1__add_region.sql (release N) - PG shown; MySQL: ..., ALGORITHM=INSTANT
SET LOCAL lock_timeout = '5s';
ALTER TABLE orders ADD COLUMN region VARCHAR(16);      -- release N code writes region on insert

-- Backfill job (ops step, after release N is fully rolled out - N-1 pods write no region):
--   UPDATE orders o SET region = c.region FROM customers c
--   WHERE o.customer_id = c.id AND o.region IS NULL AND o.id BETWEEN :lo AND :hi;
-- MySQL: UPDATE orders o JOIN customers c ON o.customer_id = c.id SET o.region = c.region
--        WHERE o.region IS NULL AND o.id BETWEEN :lo AND :hi;
-- Gate before constraining: SELECT count(*) FROM orders WHERE region IS NULL  -> 0,
-- and count the rows the join can never fill (customer region NULL) - decide their value first.
```

Constrain in release N+1 without the table scan `SET NOT NULL` does under ACCESS EXCLUSIVE (PostgreSQL 12+), one statement per file:

```sql
-- V2: ALTER TABLE orders ADD CONSTRAINT orders_region_nn CHECK (region IS NOT NULL) NOT VALID;
-- V3 (ops step on a large table): ALTER TABLE orders VALIDATE CONSTRAINT orders_region_nn;
-- V4: ALTER TABLE orders ALTER COLUMN region SET NOT NULL;   -- instant: the validated CHECK proves it
-- V5: ALTER TABLE orders DROP CONSTRAINT orders_region_nn;
```

`VALIDATE CONSTRAINT` takes SHARE UPDATE EXCLUSIVE: reads and writes continue; other DDL, VACUUM and index builds on the table wait.

MySQL: `MODIFY ... NOT NULL` runs `INPLACE` with a table rebuild - DML continues, IO is heavy; on a large table it is an ops step (or gh-ost).

Batching bounds lock hold, transaction age and replica-lag spikes (total WAL/binlog is unchanged). Pause between batches so autovacuum can reclaim dead tuples; an unbatched full-table UPDATE roughly doubles the heap, and that space is not returned without a rewrite. Build indexes on the new column after the backfill.

### Rename via expand-then-contract (four releases)

Every step must be safe while the previous release's pods still run:

| Release | Code | Migration |
| --- | --- | --- |
| N | Maps both; old column authoritative; mirrors old -> new on every write | `ADD COLUMN customer_id` (then backfill job after N is fully out) |
| N+1 (ships after the backfill gate reads 0 NULLs) | Reads new; new authoritative; mirrors new -> old (N pods still read old) | `customer_ref` DROP NOT NULL (MySQL `MODIFY ... NULL`) - N+2 stops writing it; tighten `customer_id` with the NOT NULL pattern |
| N+2 | Stops mapping the old column | none |
| N+3 | - | `DROP COLUMN customer_ref` |

```java
// Release N: old column is authoritative
@PrePersist @PreUpdate
void syncCustomerColumns() { customerId = customerRef; }
// Release N+1 flips to: customerRef = customerId;
```

Mirror unconditionally in one direction: a fill-the-null guard (`if (a == null) a = b`) leaves the other column stale after the first update. `@PrePersist`/`@PreUpdate` do not fire for bulk JPQL or native updates - dual-write those call sites explicitly, or use a DB trigger when the writers cannot be enumerated. Gate the read switch with a feature flag. Liquibase `renameColumn` in one changeset is the one-release form - it breaks every running N-1 pod.

### Indexes

PostgreSQL - `CREATE INDEX CONCURRENTLY` cannot run in a transaction; opt out per file. On a small table it can run at startup; on a large one it is an ops step and the file below is its guarded record:

```sql
-- V20__idx_orders_customer.sql
-- flyway:executeInTransaction=false
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_customer ON orders(customer_id);
```

- A failed `CREATE INDEX CONCURRENTLY` leaves an INVALID index (`SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid`). `IF NOT EXISTS` sees the name and skips it - `DROP INDEX CONCURRENTLY` first, then re-run.
- Flyway 9.1.2+ on PostgreSQL holds its migration lock in an open transaction by default, which a concurrent index build waits on - set `spring.flyway.postgresql.transactional-lock: false` when any script runs `CONCURRENTLY`.
- Liquibase: `runInTransaction="false"` on the changeset.

MySQL (InnoDB): `ALTER TABLE orders ADD INDEX idx_orders_customer (customer_id), ALGORITHM=INPLACE, LOCK=NONE;` - online, but long on a large table (ops step). Its guarded record in Liquibase: `<preConditions onFail="MARK_RAN"><not><indexExists tableName="orders" indexName="idx_orders_customer"/></not></preConditions>`.

### Constraints

```sql
ALTER TABLE payments ADD CONSTRAINT payments_status_check
    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')) NOT VALID;
-- separate file / ops step, after counting the rows it would reject
-- (SELECT count(*) FROM payments WHERE status NOT IN (...); for an FK, the orphans):
ALTER TABLE payments VALIDATE CONSTRAINT payments_status_check;
```

A `NOT VALID` FK or CHECK on a column that running code already writes correctly ships in one release; on a column a new release starts populating, it waits for that release to be fully out.

Guarded record of a constraint added out of band (PostgreSQL):

```sql
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conname = 'payments_status_check' AND conrelid = 'payments'::regclass) THEN
    ALTER TABLE payments ADD CONSTRAINT payments_status_check CHECK (status IN ('PENDING','PROCESSING','COMPLETED','FAILED'));   -- validated: a fresh environment matches prod
  END IF;
END $$;
```

MySQL 8.0.16+ enforces CHECK, has no `NOT VALID`, and adding one copies the table (blocks writes) - on a large table use gh-ost/pt-osc or keep the rule in the application. Adding an FK on MySQL is INPLACE only with `foreign_key_checks=0` (which skips validating existing rows - check orphans first).

### Failed migrations

- PostgreSQL transactional script: rolled back, nothing recorded - fix the cause and re-run.
- Non-transactional script (`executeInTransaction=false`) or any MySQL DDL: Flyway records the migration as failed and every later `migrate` stops ("Detected failed migration"). Undo partial effects (drop the INVALID index; check which statements committed), correct the file if needed - a migration that never succeeded anywhere has no checksum at stake - then `flyway repair` (removes the failed row) and re-run. Pods crash-loop until then; old pods keep serving.
- Liquibase: a failed changeset is not recorded in `DATABASECHANGELOG`; undo partial effects, fix, re-run. Release a stuck lock with `liquibase release-locks` only after confirming no update is running.

### Rollback strategy

Flyway Community has no automatic undo; schema is forward-only:

- `DROP COLUMN` / `DROP TABLE` recoverable only from PITR or backup - document the recovery window.
- Mistakes ship as a forward `Vx__revert_*.sql`.
- "Rollback tested" means: migration applied on a Testcontainers clone of prod-shape data, revert applied, N-1 app boots and passes smoke tests.

Liquibase: prefer auto-reversible changes (`addColumn`, `addNotNullConstraint`, `createIndex`); `sql` / `dropColumn` need an explicit `<rollback>`. MySQL online options on a declarative ALTER (`addNotNullConstraint`, `modifyDataType`): `<modifySql dbms="mysql"><append value=", ALGORITHM=INPLACE, LOCK=NONE"/></modifySql>`; `addColumn`/`dropColumn`/`renameColumn` append `, ALGORITHM=INSTANT`; `createIndex` renders `CREATE INDEX` and takes ` ALGORITHM=INPLACE LOCK=NONE` without the comma. Auto-rollback is kept, and forcing the algorithm makes an impossible online change fail fast instead of silently copying the table.

### CI validation

Boot 4 auto-configures Flyway / Liquibase only through their Boot module - `spring-boot-starter-flyway` / `spring-boot-starter-liquibase`, or `spring-boot-starter-classic`, which bundles every module: a bare `flyway-core` / `liquibase-core` without either runs no migration at startup and the app boots against whatever schema exists - a `[Must]` config finding. Flyway 10+ also needs the database module on the classpath (`org.flywaydb:flyway-database-postgresql`, or `flyway-mysql`) or startup fails with "Unsupported Database".

```java
@SpringBootTest @Testcontainers
class MigrationIntegrityTest {
    @Container @ServiceConnection
    static PostgreSQLContainer postgres = new PostgreSQLContainer("postgres:16-alpine");   // Testcontainers 2: org.testcontainers.postgresql;
                                                                                    // Boot 3 / TC 1.x: PostgreSQLContainer<?> ... new PostgreSQLContainer<>(...)

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
                WHERE table_schema = current_schema() AND table_name = 'orders' AND column_name = 'region'""", String.class))   // MySQL: DATABASE()
            .isEqualTo("NO");
    }
}
```

### Flyway conventions

Versioned: `V{yyyyMMdd}_{HHmm}__{description}.sql`; repeatable `R__{description}.sql` for views/functions/triggers. The `V1`/`V2` names above are shorthand. With timestamp versions, a branch merged after a newer migration already ran is "ignored" and fails `validate-on-migrate` - re-stamp the file at merge rather than enabling `spring.flyway.out-of-order` (which hides dev/CI/prod ordering drift).

```yaml
spring:
  flyway:
    validate-on-migrate: true
  jpa:
    hibernate.ddl-auto: validate
```

## Output Format

Plans and reviews both open with the `**Engine:**` line, once. A plan follows with one `Plan:` line mapping releases to steps (`Plan: N: V1 + backfill job after rollout; N+1: V2-V5; ...`) and then one block per file or step. A review follows with the blocks for the files as written - a file carrying several DDL/DML statements gets one block per statement, named `<file> (stmt n/m)`; session `SET`/`RESET` lines are not blocks; a config file finding is `Migration: config: <file>` - then the corrected `Plan:` line and one block for every file or step it introduces (backfill job, ops step, guarded record, `flyway repair`). When reviewing, the consuming workflow owns the finding envelope; invoked standalone, list findings before the blocks - `### [Must|Recommend] file:line` (pasted input: the file name), then `Issue:` and `Fix:` as separate paragraphs, `[Must]` first, `[Must]` when a statement blocks traffic, breaks running N-1 pods, fails startup, ships wrong data, or loses data, `[Recommend]` otherwise.

```
**Engine:** {PostgreSQL <major> | PostgreSQL (major unknown - 12+ assumed) | MySQL 8.0 | Aurora MySQL 3 | <other> - generic rules only | unknown - both variants given} + {Flyway | Liquibase | unknown}
```

```
Migration: {filename | filename (stmt n/m) | ops step: <command> | backfill job | config: <file>}

Release: {N | N+1 | N+2 | N+3 | ops step during <release>}

Type: {DDL | DML | METADATA}

Operation: {CREATE_TABLE | ADD_COLUMN | MODIFY_COLUMN | ADD_INDEX | DROP_INDEX | CONSTRAINT | VALIDATE_CONSTRAINT | BACKFILL | RENAME | DROP_COLUMN | DROP_TABLE | REPEATABLE_OBJECT | REPAIR | CONFIG | unknown - file not supplied}

Table: {name}

Phase: {expand | migrate | contract}

Locks Table: {yes | brief-metadata | no}

Concurrency Safe: {yes-CONCURRENTLY | yes-INSTANT | yes-INPLACE | yes-metadata-only | yes-not-valid-then-validate | yes-online-schema-change-tool | yes-batched | no | n/a}

Startup Safe: {yes | no - outlasts the readiness probe, run as ops step | n/a - not a startup migration}

Backward Compatible With N-1: {yes | no - what changes with code release}

Rollback: {auto-reversible | liquibase-rollback | forward-fix | restore-from-backup}
```

Legend. `Type`: `METADATA` is a schema-history operation (`flyway repair`, Liquibase `release-locks` / `changelog-sync`); a metadata-only ALTER is still `DDL`. `Operation`: SET NOT NULL, CHECK and FK are `CONSTRAINT`; `R__` views/functions/triggers are `REPEATABLE_OBJECT`. `Phase` is what the statement does, as written: `expand` adds structure (columns, tables, indexes, widening, NOT VALID constraints); `migrate` moves data (backfills, validation); `contract` removes or tightens (drop, rename completion, SET NOT NULL, an immediately-validated constraint); `METADATA` and config rows take the phase of the step they unblock. `Locks Table`: `CONCURRENTLY` builds and `VALIDATE CONSTRAINT` take SHARE UPDATE EXCLUSIVE - `no` (DML continues). `Concurrency Safe`: `yes-batched` is a batched DML job (short per-batch row locks); `no` is a statement that blocks traffic. `Startup Safe` covers the other failure: a statement that blocks no traffic can still stall the rollout by holding the migration lock past the probe window - the window is `initialDelaySeconds + periodSeconds x failureThreshold`.

## Avoid

- `ADD COLUMN ... NOT NULL DEFAULT <volatile expr>` on a large PostgreSQL table (full rewrite under lock)
- Dropping or renaming a column while any running release still maps it
- Blocking index creation on large tables (no `CONCURRENTLY` / `INPLACE`)
- Editing a migration that succeeded anywhere
- Unbounded `UPDATE` for backfill - batch by primary key range
- `flyway.clean()` outside ephemeral test containers
