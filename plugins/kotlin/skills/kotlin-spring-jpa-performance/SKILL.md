---
name: kotlin-spring-jpa-performance
description: Kotlin / Spring Boot JPA performance: N+1 with fetch joins / entity graphs, batch tuning, projections, L2 cache, data class entity caveats.
metadata:
  category: backend
  tags: [kotlin, jpa, hibernate, performance, queries]
user-invocable: false
---

# Kotlin JPA Performance

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Optimizing JPA queries in Kotlin / Spring Boot
- Preventing or fixing N+1 problems
- Auditing entities for Kotlin-specific traps (`data class` JPA, missing plugins)

## Rules

- Default LAZY for all associations. EAGER on `@OneToMany` causes Cartesian explosions.
- Regular `class` for `@Entity`, never `data class` - auto-generated `equals` / `hashCode` / `copy` corrupt Hibernate proxy identity.
- ID-based `equals` / `hashCode` on entities (handles unsaved entities and proxies safely).
- Configure `kotlin("plugin.jpa")` and `kotlin("plugin.spring")` Gradle plugins.
- `spring.jpa.open-in-view=false` everywhere - OSIV silently masks lazy-loading bugs and holds connections through view rendering.
- Always use `Pageable` on list endpoints.
- Fetch joins / `@EntityGraph` for known eager loads; projections for read-only paths.
- Indexes on columns used in `WHERE`, `ORDER BY`, `JOIN`. PostgreSQL does not auto-index foreign keys.

## Patterns

### Detect N+1

Enable in test or staging:

```yaml
spring:
  jpa:
    show-sql: true
    properties:
      hibernate:
        generate_statistics: true
        format_sql: true
logging.level.org.hibernate.SQL: DEBUG
logging.level.org.hibernate.orm.jdbc.bind: TRACE
```

Look for query count growing linearly with result-set size.

### Fetch join (custom JPQL)

```kotlin
@Query("SELECT DISTINCT u FROM User u LEFT JOIN FETCH u.orders")
fun findAllWithOrders(): List<User>
```

### `@EntityGraph` (derived queries)

```kotlin
@EntityGraph(attributePaths = ["orders", "orders.items"])
fun findByStatus(status: UserStatus): List<User>
```

Use fetch join for custom JPQL, `@EntityGraph` for derived methods. Don't combine - they conflict.

### Collection fetch + `Pageable` trap

`LEFT JOIN FETCH u.orders` combined with `Pageable` triggers `HHH90003004` and paginates **in memory**, fetching the entire result set into heap. Same with `@EntityGraph` over `Pageable` derived queries.

Workarounds:
- Two-query: page IDs first, then fetch full graph with `WHERE id IN (:ids)`
- `@BatchSize` instead of fetch join
- Page on the parent root and lazy-load (acceptable with small pages + batch fetch)

**`MultipleBagFetchException`:** two `LEFT JOIN FETCH` clauses on different `List<...>` collections conflict. Change one to `Set<...>` or use `@BatchSize` for one.

### Batch fetching

```yaml
spring.jpa.properties.hibernate.default_batch_fetch_size: 16
```

Or per-association: `@BatchSize(size = 16)`. Best when an entity has multiple collections (fetch joins on multiple `@OneToMany` Cartesian-explode rows).

### Projections

Skip the entity when read-only - reduces memory and skips dirty-checking:

```kotlin
interface OrderSummary {
    val id: Long
    val status: String
    val total: BigDecimal
}

@Query("SELECT o.id AS id, o.status AS status, o.total AS total FROM Order o WHERE o.customerId = :customerId")
fun findSummariesByCustomerId(customerId: Long): List<OrderSummary>

// Or data class projection
@Query("SELECT new com.example.OrderSummaryDto(o.id, o.status, o.total) FROM Order o ...")
fun findDtosByCustomerId(customerId: Long): List<OrderSummaryDto>
```

### Read-only services

```kotlin
@Service
@Transactional(readOnly = true)         // skips Hibernate dirty-checking on all queries
class OrderQueryService(private val repo: OrderRepository) { ... }
```

### Pagination

Always `Pageable`. For large datasets with stable order, use keyset over OFFSET:

```kotlin
@Query("SELECT o FROM Order o WHERE o.id > :lastId ORDER BY o.id")
fun findNextPage(@Param("lastId") lastId: Long, pageable: Pageable): List<Order>
```

### Dynamic filters with `Specification`

Use when an endpoint has 2+ optional filters. Derived methods for single-parameter filters.

```kotlin
object ProductSpecifications {
    fun hasCategory(id: Long?) = id?.let { cid ->
        Specification<Product> { root, _, cb -> cb.equal(root.get<Category>("category").get<Long>("id"), cid) }
    }
}
```

### Pessimistic locking

```kotlin
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("SELECT p FROM Product p WHERE p.id = :id")
fun findByIdForUpdate(id: Long): Product?
```

Short-lived, single-row only. Bulk paths use optimistic `@Version` + retry.

### Second-level cache

For read-heavy, rarely-changed entities (catalogs, configuration):

```kotlin
@Entity @Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
class Product(...)
```

```yaml
spring.jpa.properties.hibernate.cache.use_second_level_cache: true
```

Avoid on write-heavy entities - invalidation cost exceeds read benefit.

### Entity caveat - regular class, ID equality

```kotlin
// Bad
@Entity data class Order(@Id @GeneratedValue val id: Long = 0, val userId: Long, var status: OrderStatus)

// Good
@Entity
class Order(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) val id: Long = 0,
    val userId: Long,
    var status: OrderStatus = OrderStatus.PENDING,
    @Column(updatable = false) val createdAt: Instant = Instant.now(),
) {
    override fun equals(other: Any?) = other is Order && id != 0L && id == other.id
    override fun hashCode() = id.hashCode()
}
```

The `kotlin("plugin.jpa")` plugin generates the no-arg constructor; `kotlin("plugin.spring")` opens the class for Hibernate to subclass.

## Output Format

```
Optimization: {N+1 Fix | Projection | Batch Fetch | Specification | Cache | Pagination}
Entity: {name}
Change: {description}
Query Count: {before} -> {after}
```

## Avoid

- EAGER on `@OneToMany` / `@ManyToMany`
- Fetch joins on multiple `@OneToMany` in the same query (Cartesian explosion - use batch fetching)
- Returning entities from controllers - DTO / projection only
- Unbounded `findAll()`
- `data class` for JPA entities
- Manual `open` modifiers - use the Gradle plugins
- Combining collection fetch join with `Pageable` (HHH90003004 in-memory pagination)
- L2 cache on frequently-written entities
