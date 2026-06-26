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
- `spring.jpa.hibernate.ddl-auto: validate` beyond local; never `update`.
- Forward-only fixes: amending a merged migration breaks Flyway checksum validation. Ship a new `Vx__revert_*.sql`.
- Liquibase: declare `<rollback>` for every non-auto-reversible changeset.

## Patterns

### Three-step NOT NULL

Adding `NOT NULL` with `DEFAULT` in one statement rewrites every row and holds an ACCESS EXCLUSIVE lock - unsafe on large tables.

```sql
-- V1__add_status_nullable.sql (release N)
ALTER TABLE orders ADD COLUMN status VARCHAR(50);

-- V2__backfill_status.sql (release N, batched DML)
UPDATE orders SET status = 'PENDING'
WHERE status IS NULL AND id BETWEEN :lo AND :hi;

-- V3__constrain_status.sql (release N+1, after backfill verified)
ALTER TABLE orders ALTER COLUMN status SET NOT NULL;
```

Batched backfill avoids long-held locks and WAL bloat. Run from app or job, not as a single `UPDATE`.

`SET NOT NULL` on an *existing* column scans the whole table under an ACCESS EXCLUSIVE lock. Postgres 12+ skips the scan if a validated equivalent CHECK already proves no nulls - add `CHECK (status IS NOT NULL) NOT VALID`, `VALIDATE CONSTRAINT` (lock-free), then `SET NOT NULL` (now instant), then drop the CHECK.

### Three-step rename with dual-write

```sql
-- V1__add_customer_id.sql (expand)
ALTER TABLE orders ADD COLUMN customer_id BIGINT;

-- V2__backfill_customer_id.sql (batched)
UPDATE orders SET customer_id = customer_ref
WHERE customer_id IS NULL AND id BETWEEN :lo AND :hi;

-- V3__drop_customer_ref.sql (release N+1)
ALTER TABLE orders DROP COLUMN customer_ref;
```

During release N rollout both columns are read by some instances. Keep them in sync at the app layer until release N+1 ships:

```java
@PrePersist @PreUpdate
void syncCustomerColumns() {
    if (customerId != null && customerRef == null) customerRef = customerId;
    if (customerRef != null && customerId == null) customerId = customerRef;
}
```

Gate read-path switches with a feature flag so a bad release can flip back without a migration.

### Concurrent index creation

Flyway wraps each script in a transaction. `CREATE INDEX CONCURRENTLY` cannot run inside one - opt out per file:

```sql
-- V20__idx_orders_customer.sql
-- flyway:executeInTransaction=false
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_customer ON orders(customer_id);
```

A failed `CREATE INDEX CONCURRENTLY` leaves an INVALID index behind (it is not rolled back - the script ran outside a transaction). `IF NOT EXISTS` will not replace it; `DROP INDEX CONCURRENTLY` first, then re-run.

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

Liquibase: prefer auto-reversible changes (`addColumn`, `addNotNullConstraint`); for `sql`/`dropColumn` declare an explicit `<rollback>`.

### CI validation

```java
@SpringBootTest @Testcontainers
class MigrationIntegrityTest {
    @Container @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired Flyway flyway;

    @Test
    void allMigrationsApplyAndValidate() {
        var result = flyway.migrate();
        assertThat(result.success).isTrue();
        flyway.validate(); // checksum + ordering
    }
}
```

### Flyway conventions

Versioned: `V{yyyyMMdd}_{HHmm}__{description}.sql`. Repeatable: `R__{description}.sql` for views/functions/triggers (re-runs on checksum change).

```yaml
spring:
  flyway:
    validate-on-migrate: true
  jpa:
    hibernate.ddl-auto: validate
```

## Output Format

```
Migration: {filename}
Type: {DDL | DML}
Operation: {ADD_COLUMN | ADD_INDEX | BACKFILL | DROP_COLUMN | RENAME | CONSTRAINT}
Table: {name}
Phase: {expand | migrate | contract}
Locks Table: {yes | no}
Concurrency Safe: {yes-CONCURRENTLY | yes-INPLACE | no}
Backward Compatible With N-1: {yes | no - what changes with code release}
Rollback: {auto-reversible | liquibase-rollback | forward-fix | restore-from-backup}
```

## Avoid

- `ADD COLUMN ... NOT NULL DEFAULT ...` in one statement on large tables (full rewrite under lock).
- Renaming or dropping a column in the same release that stops reading it.
- Blocking index creation on large tables (omitting `CONCURRENTLY` / `INPLACE`).
- Editing a merged migration to "fix" it - breaks checksum validation downstream.
- Unbounded `UPDATE` for backfill - batch by primary key range.
- `flyway.clean()` outside ephemeral test containers.
