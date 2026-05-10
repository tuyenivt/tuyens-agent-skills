---
name: spring-db-migration-safety
description: "Safe Flyway / Liquibase migrations for zero-downtime: DDL safety, expand-then-contract ordering, rollback strategy."
metadata:
  category: backend
  tags: [flyway, liquibase, migrations, zero-downtime, ddl, spring-boot]
user-invocable: false
---

# DB Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Adding, modifying, or removing database schema elements in a live system
- Planning zero-downtime deployments with schema changes
- Reviewing migration files for safety before merging
- Coordinating schema changes across multiple services
- Onboarding Flyway or Liquibase into an existing Spring Boot project

## Rules

- Never add a NOT NULL column in a single migration on large tables - add nullable first, backfill, then constrain
- Never rename columns directly - use add, migrate, drop across three separate migrations
- Never drop a column in the same release it stops being used - wait one full release cycle
- Never mix DDL and DML in the same migration file
- Always create indexes non-blocking (CONCURRENTLY for Postgres, ALGORITHM=INPLACE for MySQL)
- Never use `spring.jpa.hibernate.ddl-auto=update` outside local development
- Migrations must be backward-compatible with the N-1 version of the application code
- Use feature flags to gate schema-dependent code paths during expand-then-contract deployments

## Patterns

### 1. Zero-Downtime DDL Rules

Bad - adds NOT NULL column in one step, locks table on large datasets:

```sql
-- V20250213_1000__add_status_to_orders.sql
ALTER TABLE orders ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'PENDING';
```

Good - three-migration sequence:

```sql
-- Migration 1: add nullable column
-- V20250213_1000__add_status_nullable_to_orders.sql
ALTER TABLE orders ADD COLUMN status VARCHAR(50);

-- Migration 2 (next release): backfill existing rows
-- V20250214_1000__backfill_status_on_orders.sql
UPDATE orders SET status = 'PENDING' WHERE status IS NULL;

-- Migration 3 (release after backfill): enforce constraint
-- V20250215_1000__constrain_status_on_orders.sql
ALTER TABLE orders ALTER COLUMN status SET NOT NULL;
```

Bad - direct column rename locks table and breaks running app code:

```sql
ALTER TABLE orders RENAME COLUMN customer_ref TO customer_id;
```

Good - expand-then-contract across three migrations:

```sql
-- Migration 1 (release N, expand): add new column nullable
ALTER TABLE orders ADD COLUMN customer_id BIGINT;

-- Migration 2 (release N, backfill in batches; one big UPDATE on 30M rows
-- locks rows, bloats WAL, and may exceed lock_timeout). Run from a job or
-- repeated migration; pick batch size by row width.
UPDATE orders SET customer_id = customer_ref
WHERE customer_id IS NULL AND id BETWEEN :lo AND :hi;

-- Migration 3 (release N+1, after all instances are reading the new column):
ALTER TABLE orders DROP COLUMN customer_ref;
```

Rolling-deploy dual-write: during release N rollout, two app versions run concurrently behind the load balancer. Keep both columns in sync from the app layer until the rollout converges, otherwise the older instance writes only to `customer_ref` and the new instance reads `customer_id`:

```java
// Keeps customer_ref and customer_id in sync while old code is still in flight
@PrePersist @PreUpdate
void syncCustomerColumns() {
    if (customerId != null && customerRef == null) customerRef = customerId;
    if (customerRef != null && customerId == null) customerId = customerRef;
}
```

Bad - index creation locks the table:

```sql
CREATE INDEX idx_orders_customer ON orders(customer_id);
```

Good - non-blocking index creation:

```sql
-- Postgres
CREATE INDEX CONCURRENTLY idx_orders_customer ON orders(customer_id);

-- MySQL
ALTER TABLE orders ADD INDEX idx_orders_customer (customer_id), ALGORITHM=INPLACE, LOCK=NONE;
```

**Flyway + CONCURRENTLY caveat**: PostgreSQL's `CREATE INDEX CONCURRENTLY` cannot run inside a transaction. Flyway wraps each migration in a transaction by default. To use CONCURRENTLY, disable the transaction for that migration file:

```java
// Implement FlywayCallback or use Flyway 10+ per-script configuration:
// V20250213_1100__create_index_orders_customer.sql
-- flyway:executeInTransaction=false
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_customer ON orders(customer_id);
```

### Idempotency Key and CHECK Constraint Migrations

For payment/order features that need idempotency and status validation:

```sql
-- V20250213_1200__add_idempotency_key_to_payments.sql
ALTER TABLE payments ADD COLUMN idempotency_key VARCHAR(255);

-- V20250213_1210__create_unique_index_idempotency_key.sql
-- flyway:executeInTransaction=false
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_payments_idempotency_key
    ON payments(idempotency_key);

-- V20250213_1220__add_status_check_constraint.sql
ALTER TABLE payments ADD CONSTRAINT payments_status_check
    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'));
```

CHECK constraints prevent invalid status values at the database level - a safety net when application-level validation is bypassed (e.g., manual SQL, migration scripts).

### Rollback Strategy

Flyway Community has no automatic undo (Undo is paid-tier only). Treat every forward migration as one-way and plan rollback as a paired forward-fix migration:

- DROP COLUMN cannot be rolled back without a database restore. Lean on PITR / backup retention; document the recovery window in the runbook.
- Schema mistakes ship a `Vx_revert_*.sql` forward migration that re-adds the column or constraint, not a `git revert` of the original file (Flyway will detect a checksum change and fail validation).
- "Rollback tested" in the checklist means: applied on a Testcontainers Postgres clone of prod-shape data, then the revert migration applied, then the app on N-1 boots cleanly.

Liquibase has built-in `<rollback>` blocks (shown below); prefer them for non-auto-reversible operations.

### 2. Flyway Conventions

Naming pattern: `V{yyyyMMdd}_{HHmm}__{description}.sql`

```
V20250213_1030__add_payment_intent_id_to_orders.sql
V20250213_1100__create_index_orders_payment_intent.sql
R__create_order_summary_view.sql          -- Repeatable: views, functions
```

One DDL statement per migration file:

```sql
-- V20250213_1030__add_payment_intent_id_to_orders.sql
ALTER TABLE orders ADD COLUMN payment_intent_id VARCHAR(255);
```

Flyway callbacks for validation (`db/migration/callbacks/`):

```sql
-- beforeMigrate.sql
SELECT 1; -- connectivity check

-- afterMigrate.sql
ANALYZE orders; -- update statistics after bulk changes
```

Spring Boot configuration:

```yaml
spring:
  flyway:
    locations: classpath:db/migration,classpath:db/migration/common
    baseline-on-migrate: true # for retrofitting existing databases
    baseline-version: 0 # baseline at version 0
    validate-on-migrate: true
    out-of-order: false # strict ordering in production
```

Multi-module layout:

```yaml
spring:
  flyway:
    locations:
      - classpath:db/migration/core
      - classpath:db/migration/orders
      - classpath:db/migration/payments
```

### 3. Liquibase Conventions

Changeset ID pattern: `{ticket}-{sequence}`

```xml
<!-- changelog/orders/ORD-1234.xml -->
<changeSet id="ORD-1234-001" author="dev-team" context="prod,staging">
    <preConditions onFail="MARK_RAN">
        <not>
            <columnExists tableName="orders" columnName="payment_intent_id"/>
        </not>
    </preConditions>

    <addColumn tableName="orders">
        <column name="payment_intent_id" type="VARCHAR(255)"/>
    </addColumn>

    <rollback>
        <dropColumn tableName="orders" columnName="payment_intent_id"/>
    </rollback>
</changeSet>

<changeSet id="ORD-1234-002" author="dev-team" context="dev">
    <!-- dev-only seed data, excluded from prod -->
    <insert tableName="orders">
        <column name="id" value="1"/>
        <column name="payment_intent_id" value="pi_test_001"/>
    </insert>
    <rollback>
        <delete tableName="orders"><where>id = 1</where></delete>
    </rollback>
</changeSet>
```

Always include a rollback block - never omit it for non-auto-reversible changes:

```xml
<!-- Bad: no rollback -->
<changeSet id="ORD-1235-001" author="dev-team">
    <addColumn tableName="orders">
        <column name="region" type="VARCHAR(50)"/>
    </addColumn>
</changeSet>

<!-- Good: explicit rollback -->
<changeSet id="ORD-1235-001" author="dev-team">
    <addColumn tableName="orders">
        <column name="region" type="VARCHAR(50)"/>
    </addColumn>
    <rollback>
        <dropColumn tableName="orders" columnName="region"/>
    </rollback>
</changeSet>
```

### 4. Spring Boot Integration

Testcontainers-based migration validation in CI:

```java
@SpringBootTest
@Testcontainers
class MigrationIntegrityTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasourceProps(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    Flyway flyway;

    @Test
    void allMigrationsApplyCleanly() {
        flyway.clean();
        var result = flyway.migrate();
        assertThat(result.success).isTrue();
        assertThat(result.migrationsExecuted).isPositive();
    }
}
```

Separate, smaller connection pool during migrations:

```yaml
# application-migration.yml - activate only during migration phase
spring:
  datasource:
    hikari:
      maximum-pool-size: 5 # small pool; migration is single-threaded
      connection-timeout: 60000 # longer timeout for DDL locks
```

Never allow Hibernate to manage the schema in staging or production:

```yaml
# Bad in any non-local environment
spring:
  jpa:
    hibernate:
      ddl-auto: update

# Good - all environments beyond local
spring:
  jpa:
    hibernate:
      ddl-auto: validate            # fail fast if schema doesn't match entities
```

### 5. Multi-Service Migration Ordering (Expand-Then-Contract)

```
Release N-1 (current):   app reads column_a only
Release N   (expand):    add column_b (nullable); app writes both column_a and column_b
Release N+1 (contract):  app reads column_b only; drop column_a
```

Feature flag gating during expand phase:

```java
@Service
@RequiredArgsConstructor
public class OrderService {

    private final FeatureFlags featureFlags;

    public void processOrder(OrderRequest req) {
        if (featureFlags.isEnabled("USE_PAYMENT_INTENT_V2")) {
            // code path that requires payment_intent_id column
            processWithPaymentIntent(req);
        } else {
            processLegacy(req);
        }
    }
}
```

Dependency ordering in CI/CD - shared schema migrations run first:

```
1. shared-schema service  -> applies core DDL
2. orders service         -> applies order-domain DDL
3. payments service       -> applies payments-domain DDL (may reference orders schema)
```

Backward-compatibility rule: every migration applied in release N must be safe to run while release N-1 code is still serving traffic.

## Output Format

When generating migrations, document each file:

```
Migration: {filename}
Type: {DDL | DML}
Operation: {ADD_COLUMN | ADD_INDEX | BACKFILL | DROP_COLUMN | RENAME | CONSTRAINT | OTHER}
Table: {table name}
Phase: {expand | migrate | contract}
Release: {N | N+1 | N+2}
Locks Table: {yes | no}
Concurrency Safe: {yes-CONCURRENTLY | yes-INPLACE | no}
Dual-Write Required: {yes | no}
Backward Compatible With N-1: {yes | no}
Compatibility Notes: {free text - what code change shipped alongside}
Rollback: {auto-reversible | liquibase-rollback-block | forward-fix-migration | restore-from-backup}
```

## Avoid

- `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT ...` in a single migration on large tables - locks the table
- Data migrations (DML) mixed with schema changes (DDL) in the same file
- `spring.jpa.hibernate.ddl-auto=update` in any environment beyond local dev
- Migrations that read environment variables or application state at execution time
- Renaming columns directly in a single ALTER statement
- Dropping columns in the same release they are removed from application code
- Blocking index creation without CONCURRENTLY / ALGORITHM=INPLACE
- Omitting rollback blocks in Liquibase changesets for non-auto-reversible changes
