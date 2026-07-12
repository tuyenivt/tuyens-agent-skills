---
name: kotlin-spring-db-migration-safety
description: Zero-downtime DB migration safety for Kotlin / Spring Boot: Flyway, Liquibase, DDL safety, expand-contract ordering, rollback strategies.
metadata:
  category: backend
  tags: [kotlin, flyway, liquibase, migrations, zero-downtime, ddl, spring-boot]
user-invocable: false
---

# Kotlin DB Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Adding / modifying / removing schema in a live Kotlin / Spring system
- Planning zero-downtime deploys with schema changes
- Reviewing migrations before merge
- Onboarding Flyway / Liquibase into an existing project

## Rules

- Migrations must be backward-compatible with the N-1 application code.
- Never add NOT NULL to an existing column in one step on large tables (expand-then-contract).
- Never rename columns directly - add, migrate, drop across three migrations.
- Never drop a column in the same release it stops being used - one full release cycle of grace.
- Never mix DDL and DML in the same migration file.
- Indexes on large tables: non-blocking (`CONCURRENTLY` on Postgres, `ALGORITHM=INPLACE` on MySQL).
- `spring.jpa.hibernate.ddl-auto=validate` outside local dev. Never `update`.
- Set `lock_timeout` / `statement_timeout` before every DDL on a large table.
- Feature-flag gate schema-dependent code paths during expand-then-contract deploys.

## Patterns

### Lock timeout before DDL

A blocked DDL queues behind every existing lock and ahead of every new query for the same table, causing pile-up. Fail fast instead.

```sql
-- Postgres
SET lock_timeout = '3s';
SET statement_timeout = '30s';
ALTER TABLE orders ADD COLUMN status VARCHAR(50);

-- MySQL
SET SESSION lock_wait_timeout = 3;
ALTER TABLE orders ADD COLUMN status VARCHAR(50);
```

### Add NOT NULL column (three migrations)

```sql
-- V1: add nullable
ALTER TABLE orders ADD COLUMN status VARCHAR(50);

-- V2 (next release): backfill in batches - drive from application or one-off job,
-- not a single UPDATE (which holds locks and bloats WAL/replication lag on a 50M-row table)
-- If from SQL, use a key-paged loop with FOR UPDATE SKIP LOCKED + COMMIT per batch.

-- V3 (release after backfill): enforce constraint
ALTER TABLE orders ALTER COLUMN status SET NOT NULL;
```

**Postgres 11+ note:** `ADD COLUMN ... NOT NULL DEFAULT 'static'` is a metadata-only change (fast, no rewrite) for non-volatile defaults. Single-step is acceptable. MySQL still rewrites - three-step required. Volatile defaults (`now()`, `gen_random_uuid()`) trigger a rewrite even on Postgres - use three-step.

### Rename column (expand-then-contract)

```sql
-- V1: add new column
ALTER TABLE orders ADD COLUMN customer_id BIGINT;

-- V2: backfill in batches (and keep in sync via app code / @PrePersist) - NOT a single UPDATE
-- on a large table; use the key-paged loop from "Add NOT NULL column" V2.

-- V3 (next release, after old column unused): drop
ALTER TABLE orders DROP COLUMN customer_ref;
```

### Non-blocking indexes

```sql
-- Postgres
CREATE INDEX CONCURRENTLY idx_orders_customer ON orders(customer_id);

-- MySQL
ALTER TABLE orders ADD INDEX idx_orders_customer (customer_id), ALGORITHM=INPLACE, LOCK=NONE;
```

**Flyway + CONCURRENTLY:** Postgres `CREATE INDEX CONCURRENTLY` cannot run inside a transaction. Disable Flyway's transaction wrapper:

```sql
-- V20250213_1100__create_index.sql
-- flyway:executeInTransaction=false
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_customer ON orders(customer_id);
```

**Failed `CREATE INDEX CONCURRENTLY` leaves an INVALID index.** It still exists in the catalog and is maintained on writes, but is unusable - and `IF NOT EXISTS` silently skips it on retry, so the index never actually gets built. Drop it before re-running (then `flyway.repair()` to clear the failed history row):

```sql
SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid WHERE NOT i.indisvalid;
DROP INDEX CONCURRENTLY IF EXISTS idx_orders_customer;
```

### Unique constraint via concurrent index

Retrofitting uniqueness onto an existing column: check for duplicates first (`SELECT key FROM payments GROUP BY key HAVING count(*) > 1`) and dedup in a separate DML migration - a concurrent unique build over duplicates fails by construction, leaving the INVALID index described above.

```sql
-- V1: add column
ALTER TABLE payments ADD COLUMN idempotency_key VARCHAR(255);

-- V2: unique index (concurrent)
-- flyway:executeInTransaction=false
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_payments_idempotency_key
    ON payments(idempotency_key);
```

### Flyway conventions

Naming: `V{yyyyMMdd}_{HHmm}__{description}.sql` for versioned, `R__name.sql` for repeatable (views, functions).

```yaml
spring:
  flyway:
    locations: classpath:db/migration
    baseline-on-migrate: true
    validate-on-migrate: true
    out-of-order: false
    clean-disabled: true     # CRITICAL outside local - flyway.clean() drops everything
```

One DDL statement per file.

**`flyway.repair()` after a crash:** when a migration fails mid-statement, the row in `flyway_schema_history` is marked failed and subsequent boots refuse. Inspect partial state, finish or roll back the DDL manually, then call `flyway.repair()`. Never just delete the row.

### Liquibase

```xml
<changeSet id="ORD-1234-001" author="dev-team" context="prod,staging">
    <preConditions onFail="MARK_RAN">
        <not><columnExists tableName="orders" columnName="payment_intent_id"/></not>
    </preConditions>
    <addColumn tableName="orders">
        <column name="payment_intent_id" type="VARCHAR(255)"/>
    </addColumn>
    <rollback>
        <dropColumn tableName="orders" columnName="payment_intent_id"/>
    </rollback>
</changeSet>
```

Always include a rollback block for non-auto-reversible changes.

### Spring integration

Validate in CI with `@SpringBootTest` + Testcontainers Postgres (see `kotlin-spring-test-integration`): inject `Flyway`, call `flyway.clean()` then assert `flyway.migrate().migrationsExecuted > 0`. The recommended `clean-disabled: true` makes that call throw - override with `spring.flyway.clean-disabled: false` in the test profile only.

Production: `spring.jpa.hibernate.ddl-auto: validate`. Use a smaller separate Hikari pool (`maximum-pool-size: 5`) for the migration profile to avoid starving the app pool on long DDL.

### CHECK constraint with `NOT VALID` + `VALIDATE`

Adding a CHECK on a large table normally rewrites every row. Postgres splits this in two:

```sql
-- V1: enforced for new/updated rows, NOT validated retroactively (no rewrite, no full-table lock)
ALTER TABLE orders ADD CONSTRAINT chk_status
    CHECK (status IN ('PENDING','PAID','CANCELLED','SHIPPED')) NOT VALID;

-- V2 (next release, after backfill): validate (takes ACCESS EXCLUSIVE briefly per page, not whole table)
ALTER TABLE orders VALIDATE CONSTRAINT chk_status;
```

If V2 errors with offending rows, fix them in a separate DML migration before re-running.

### `@PrePersist` / `@PreUpdate` dual-write during rename

During the rename transition window (V1 added column added, V3 drop not yet shipped), keep both columns in sync from the app:

```kotlin
@Entity
class Order(
    @Id @GeneratedValue val id: Long = 0,
    var customerRef: Long? = null,          // old column - read by N-1
    var customerId: Long? = null,           // new column - read by N+1
) {
    @PrePersist @PreUpdate
    fun syncCustomer() {
        // last-write-wins; both columns mirrored
        when {
            customerId != null && customerRef == null -> customerRef = customerId
            customerRef != null && customerId == null -> customerId = customerRef
        }
    }
}
```

Remove the entity lifecycle hook in release N+1 when the old column is dropped.

Lifecycle hooks only fire for writes through the JPA session - bulk JPQL, `@Modifying` queries, and native SQL bypass them and silently desync the columns. Audit those write paths and make each set both columns (or use a DB trigger for the window).

### Forward-only rollback strategy

Reverting a deployed migration in place is rarely safe (replication, partial writes, downstream consumers). Default policy:

1. **Schema rollback = forward-only.** If migration `V42` is broken, ship `V43` that re-establishes the desired state. Never delete `V42` or its `flyway_schema_history` row.
2. **Liquibase `<rollback>` blocks** still required for non-reversible changes - they document the inverse and run in test environments only.
3. **CI proves the revert path**: Testcontainers boots prior release schema, applies `V42` + `V43`, verifies app health. Without this, "we can roll back" is unverified.

### Multi-service ordering (expand-then-contract)

```
Release N-1:   app reads column_a only
Release N:     add column_b nullable; app writes both
Release N+1:   app reads column_b only; drop column_a
```

Feature-flag the cutover so the new path is reversible without a redeploy.

## Output Format

```
Migration: {filename}
Type: {DDL | DML}
Operation: {ADD COLUMN | ADD INDEX | BACKFILL | DROP COLUMN | RENAME | CONSTRAINT}
Table: {name}
Locks Table: {yes | no}
Backward Compatible: {yes | no - why}
Rollback: {auto-reversible | manual rollback provided | destructive (data loss) | N/A}
```

## Checklist

- [ ] Backward-compatible with current running code
- [ ] No locks on large tables
- [ ] Rollback tested
- [ ] Index creation non-blocking
- [ ] DDL and DML in separate files

## Avoid

- `ADD COLUMN ... NOT NULL DEFAULT ...` single-step on large tables (except Postgres 11+ static defaults)
- DML mixed with DDL
- `spring.jpa.hibernate.ddl-auto=update` outside local
- Migrations reading env vars or app state at execution time
- Direct column renames
- Dropping columns in the same release they leave the app
- Blocking index creation (no `CONCURRENTLY` / `ALGORITHM=INPLACE`)
- Liquibase changesets without rollback for non-reversible changes
