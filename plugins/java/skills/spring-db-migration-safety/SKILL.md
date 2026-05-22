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

- Every migration applied in release N must be backward-compatible with release N-1 code
- Add NOT NULL in three steps: add nullable → backfill → constrain
- Rename a column in three steps: add new → dual-write + backfill → drop old
- Indexes on large tables use `CREATE INDEX CONCURRENTLY` (Postgres) or `ALGORITHM=INPLACE, LOCK=NONE` (MySQL)
- One concern per migration: DDL and DML in separate files
- `spring.jpa.hibernate.ddl-auto` is `validate` everywhere beyond local; never `update` in staging or prod
- Feature-flag schema-dependent code paths during expand-then-contract
- Liquibase: always include `<rollback>` for non-auto-reversible changes

## Patterns

### Three-step NOT NULL

```sql
-- V1__add_status_nullable.sql
ALTER TABLE orders ADD COLUMN status VARCHAR(50);

-- V2__backfill_status.sql (next release)
UPDATE orders SET status = 'PENDING' WHERE status IS NULL;

-- V3__constrain_status.sql (after backfill confirmed)
ALTER TABLE orders ALTER COLUMN status SET NOT NULL;
```

### Three-step rename + rolling-deploy dual-write

```sql
-- V1__add_customer_id.sql (expand)
ALTER TABLE orders ADD COLUMN customer_id BIGINT;

-- V2__backfill_customer_id.sql (batched - 30M-row UPDATEs lock and bloat WAL)
UPDATE orders SET customer_id = customer_ref
WHERE customer_id IS NULL AND id BETWEEN :lo AND :hi;

-- V3__drop_customer_ref.sql (release N+1, after all instances read new column)
ALTER TABLE orders DROP COLUMN customer_ref;
```

During release N rollout, two app versions run concurrently. Keep both columns in sync from the app layer:

```java
@PrePersist @PreUpdate
void syncCustomerColumns() {
    if (customerId != null && customerRef == null) customerRef = customerId;
    if (customerRef != null && customerId == null) customerId = customerRef;
}
```

### Concurrent index creation

Flyway wraps each script in a transaction by default. `CREATE INDEX CONCURRENTLY` cannot run in a transaction - disable it for that file:

```sql
-- V20__idx_orders_customer.sql
-- flyway:executeInTransaction=false
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_customer ON orders(customer_id);
```

MySQL equivalent:

```sql
ALTER TABLE orders ADD INDEX idx_orders_customer (customer_id), ALGORITHM=INPLACE, LOCK=NONE;
```

### CHECK constraints for state machines

```sql
ALTER TABLE payments ADD CONSTRAINT payments_status_check
    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'));
```

A safety net when application validation is bypassed (manual SQL, admin scripts).

### Rollback strategy

Flyway Community has no automatic undo. Treat forward migrations as one-way:

- `DROP COLUMN` is not recoverable without restore - lean on PITR / backup retention; document recovery window.
- Schema mistakes ship a forward `Vx_revert_*.sql`, not a `git revert` (Flyway detects checksum changes and fails validation).
- "Rollback tested" means: applied on a Testcontainers clone of prod-shape data, revert migration applied, N-1 app boots cleanly.

Liquibase: declare `<rollback>` for every non-auto-reversible changeset.

### Conventions

Flyway naming: `V{yyyyMMdd}_{HHmm}__{description}.sql`. Repeatable: `R__create_order_summary_view.sql` for views/functions. One DDL statement per file.

```yaml
spring:
  flyway:
    baseline-on-migrate: true       # for retrofits
    validate-on-migrate: true
    out-of-order: false             # strict in prod
  jpa:
    hibernate.ddl-auto: validate    # never update beyond local
```

### CI validation with Testcontainers

```java
@SpringBootTest @Testcontainers
class MigrationIntegrityTest {
    @Container @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired Flyway flyway;

    @Test
    void allMigrationsApplyCleanly() {
        flyway.clean();
        var result = flyway.migrate();
        assertThat(result.success).isTrue();
        assertThat(result.migrationsExecuted).isPositive();
    }
}
```

### Expand-then-contract release ordering

```
Release N-1: app reads column_a only
Release N:   add column_b nullable; app dual-writes both
Release N+1: app reads column_b only; drop column_a
```

Gate schema-dependent code paths with a feature flag during the transition.

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

- `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT ...` in one migration on large tables
- DDL and DML in the same file
- `spring.jpa.hibernate.ddl-auto=update` beyond local dev
- Renaming or dropping columns in a single release
- Blocking index creation on large tables
- Liquibase changesets without `<rollback>` blocks
