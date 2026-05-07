---
name: kotlin-spring-db-migration-safety
description: Safe database migration patterns for zero-downtime deployments in Kotlin/Spring Boot - Flyway and Liquibase conventions, DDL safety rules, expand-then-contract migration ordering, and rollback strategies. SQL migration files are language-agnostic; this skill captures the surrounding Kotlin/Spring config.
metadata:
  category: backend
  tags: [kotlin, flyway, liquibase, migrations, zero-downtime, ddl, spring-boot]
user-invocable: false
---

# Kotlin DB Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Adding, modifying, or removing database schema elements in a live Kotlin/Spring system
- Planning zero-downtime deployments with schema changes
- Reviewing migration files for safety before merging
- Coordinating schema changes across multiple services
- Onboarding Flyway or Liquibase into an existing Kotlin/Spring Boot project

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
-- Migration 1: add new column
ALTER TABLE orders ADD COLUMN customer_id BIGINT;

-- Migration 2: backfill and keep in sync via app code or trigger
UPDATE orders SET customer_id = customer_ref;

-- Migration 3 (next release after old column unused): drop old column
ALTER TABLE orders DROP COLUMN customer_ref;
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

```sql
-- V20250213_1100__create_index_orders_customer.sql
-- flyway:executeInTransaction=false
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_customer ON orders(customer_id);
```

### Idempotency Key and CHECK Constraint Migrations

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

### 2. Flyway Conventions

Naming pattern: `V{yyyyMMdd}_{HHmm}__{description}.sql`

```
V20250213_1030__add_payment_intent_id_to_orders.sql
V20250213_1100__create_index_orders_payment_intent.sql
R__create_order_summary_view.sql          -- Repeatable: views, functions
```

One DDL statement per migration file. Spring Boot `application.yml`:

```yaml
spring:
  flyway:
    locations: classpath:db/migration,classpath:db/migration/common
    baseline-on-migrate: true
    baseline-version: 0
    validate-on-migrate: true
    out-of-order: false
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

```xml
<!-- changelog/orders/ORD-1234.xml -->
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

Always include a rollback block - never omit it for non-auto-reversible changes.

### 4. Spring Boot Integration (Kotlin)

Testcontainers-based migration validation in CI (Kotlin syntax):

```kotlin
@SpringBootTest
@Testcontainers
class MigrationIntegrityTest {

    companion object {
        @Container
        @JvmStatic
        val postgres = PostgreSQLContainer("postgres:16-alpine")

        @DynamicPropertySource
        @JvmStatic
        fun datasourceProps(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url", postgres::getJdbcUrl)
            registry.add("spring.datasource.username", postgres::getUsername)
            registry.add("spring.datasource.password", postgres::getPassword)
        }
    }

    @Autowired lateinit var flyway: Flyway

    @Test
    fun `all migrations apply cleanly`() {
        flyway.clean()
        val result = flyway.migrate()
        result.success shouldBe true
        result.migrationsExecuted shouldBeGreaterThan 0
    }
}
```

Separate, smaller connection pool during migrations:

```yaml
# application-migration.yml - activate only during migration phase
spring:
  datasource:
    hikari:
      maximum-pool-size: 5
      connection-timeout: 60000
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
      ddl-auto: validate
```

### 5. Multi-Service Migration Ordering (Expand-Then-Contract)

```
Release N-1 (current):   app reads column_a only
Release N   (expand):    add column_b (nullable); app writes both column_a and column_b
Release N+1 (contract):  app reads column_b only; drop column_a
```

Feature flag gating during expand phase:

```kotlin
@Service
class OrderService(private val featureFlags: FeatureFlags) {
    fun processOrder(req: OrderRequest) =
        if (featureFlags.isEnabled("USE_PAYMENT_INTENT_V2")) processWithPaymentIntent(req)
        else processLegacy(req)
}
```

Backward-compatibility rule: every migration applied in release N must be safe to run while release N-1 code is still serving traffic.

## Output Format

When generating migrations, document each file:

```
Migration: {filename}
Type: {DDL | DML}
Operation: {ADD COLUMN | ADD INDEX | BACKFILL | DROP COLUMN | RENAME | CONSTRAINT}
Table: {table name}
Locks Table: {yes | no}
Backward Compatible: {yes | no - why}
Rollback: {auto-reversible | manual rollback provided | N/A}
```

## Checklist

- [ ] Migration is backward-compatible with current running code?
- [ ] No table locks on large tables?
- [ ] Rollback tested?
- [ ] Index creation is non-blocking?
- [ ] Separate DDL and DML migrations?

## Avoid

- `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT ...` in a single migration on large tables
- Data migrations (DML) mixed with schema changes (DDL) in the same file
- `spring.jpa.hibernate.ddl-auto=update` in any environment beyond local dev
- Migrations that read environment variables or application state at execution time
- Renaming columns directly in a single ALTER statement
- Dropping columns in the same release they are removed from application code
- Blocking index creation without CONCURRENTLY / ALGORITHM=INPLACE
- Omitting rollback blocks in Liquibase changesets for non-auto-reversible changes
