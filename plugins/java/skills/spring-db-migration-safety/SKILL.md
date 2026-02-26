---
name: spring-db-migration-safety
description: Safe database migration patterns for zero-downtime deployments. Covers Flyway and Liquibase conventions, DDL safety rules, migration ordering, and rollback strategies. Referenced by workflow skills for Spring Boot projects.
metadata:
  category: backend
  tags: [flyway, liquibase, migrations, zero-downtime, ddl, spring-boot]
user-invocable: false
---

# DB Migration Safety

## When to Use

- Adding, modifying, or removing database schema elements in a live system
- Planning zero-downtime deployments with schema changes
- Reviewing migration files for safety before merging
- Coordinating schema changes across multiple services
- Onboarding Flyway or Liquibase into an existing Spring Boot project

## Rules

- Never add a NOT NULL column in a single migration on large tables — add nullable first, backfill, then constrain
- Never rename columns directly — use add, migrate, drop across three separate migrations
- Never drop a column in the same release it stops being used — wait one full release cycle
- Never mix DDL and DML in the same migration file
- Always create indexes non-blocking (CONCURRENTLY for Postgres, ALGORITHM=INPLACE for MySQL)
- Never use `spring.jpa.hibernate.ddl-auto=update` outside local development
- Migrations must be backward-compatible with the N-1 version of the application code
- Use feature flags to gate schema-dependent code paths during expand-then-contract deployments

## Pattern

### 1. Zero-Downtime DDL Rules

Bad — adds NOT NULL column in one step, locks table on large datasets:

```sql
-- V20250213_1000__add_status_to_orders.sql
ALTER TABLE orders ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'PENDING';
```

Good — three-migration sequence:

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

Bad — direct column rename locks table and breaks running app code:

```sql
ALTER TABLE orders RENAME COLUMN customer_ref TO customer_id;
```

Good — expand-then-contract across three migrations:

```sql
-- Migration 1: add new column
ALTER TABLE orders ADD COLUMN customer_id BIGINT;

-- Migration 2: backfill and keep in sync via app code or trigger
UPDATE orders SET customer_id = customer_ref;

-- Migration 3 (next release after old column unused): drop old column
ALTER TABLE orders DROP COLUMN customer_ref;
```

Bad — index creation locks the table:

```sql
CREATE INDEX idx_orders_customer ON orders(customer_id);
```

Good — non-blocking index creation:

```sql
-- Postgres
CREATE INDEX CONCURRENTLY idx_orders_customer ON orders(customer_id);

-- MySQL
ALTER TABLE orders ADD INDEX idx_orders_customer (customer_id), ALGORITHM=INPLACE, LOCK=NONE;
```

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

Always include a rollback block — never omit it for non-auto-reversible changes:

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
# application-migration.yml — activate only during migration phase
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

# Good — all environments beyond local
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

Dependency ordering in CI/CD — shared schema migrations run first:

```
1. shared-schema service  -> applies core DDL
2. orders service         -> applies order-domain DDL
3. payments service       -> applies payments-domain DDL (may reference orders schema)
```

Backward-compatibility rule: every migration applied in release N must be safe to run while release N-1 code is still serving traffic.

## Checklist

- [ ] Migration is backward-compatible with current running code?
- [ ] No table locks on large tables?
- [ ] Rollback tested?
- [ ] Index creation is non-blocking?
- [ ] Separate DDL and DML migrations?

## Avoid

- `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT ...` in a single migration on large tables — locks the table
- Data migrations (DML) mixed with schema changes (DDL) in the same file
- `spring.jpa.hibernate.ddl-auto=update` in any environment beyond local dev
- Migrations that read environment variables or application state at execution time
- Renaming columns directly in a single ALTER statement
- Dropping columns in the same release they are removed from application code
- Blocking index creation without CONCURRENTLY / ALGORITHM=INPLACE
- Omitting rollback blocks in Liquibase changesets for non-auto-reversible changes
