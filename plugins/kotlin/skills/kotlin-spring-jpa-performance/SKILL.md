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

- Optimizing data access layer queries in a Kotlin + Spring Boot project
- Preventing N+1 query problems
- Reducing memory footprint of large result sets
- Building dynamic filter/search queries with multiple optional parameters
- Auditing JPA entities for Kotlin-specific traps (data class as entity, kotlin-jpa plugin missing)

## Rules

- Default LAZY for all associations
- Avoid EAGER fetching without explicit need
- Use fetch join selectively for specific queries
- Prefer projection over entity for read-only queries
- Detect and eliminate N+1 queries
- Keep entities small, avoid heavy logic inside entities
- Add indexes on WHERE/ORDER BY/JOIN columns (see core plugin's `backend-db-indexing` for general index strategy)
- Set `spring.jpa.open-in-view=false` in all environments - open-in-view silently masks lazy loading issues by keeping the Hibernate session open through the controller layer, causing unpredictable N+1 queries in the view
- Use regular `class` for JPA entities, never `data class` - Hibernate proxies are incompatible with auto-generated `equals` / `hashCode` / `copy`
- Configure `kotlin("plugin.jpa")` and `kotlin("plugin.spring")` Gradle plugins so JPA entities and `@Transactional` services are not `final`

## Patterns

### N+1 Detection and Fix

To diagnose N+1, turn on Hibernate query counting in test or staging:

```yaml
spring:
  jpa:
    show-sql: true                                  # logs every emitted SQL statement
    properties:
      hibernate:
        generate_statistics: true                   # logs query count per session
        format_sql: true
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE              # parameter values
```

Look for "X queries" growing linearly with your result set size - that is N+1.

Bad - Causes N+1 queries:

```kotlin
val users = userRepository.findAll() // 1 query
users.forEach { u ->
    println(u.orders) // N additional queries (lazy load on each)
}
```

Good - Fetch join prevents N+1:

```kotlin
interface UserRepository : JpaRepository<User, Long> {
    @Query("SELECT DISTINCT u FROM User u LEFT JOIN FETCH u.orders")
    fun findAllWithOrders(): List<User>
}
```

Good - `@EntityGraph` for declarative fetch control (avoids JPQL when you just need eager loading on a standard query):

```kotlin
interface UserRepository : JpaRepository<User, Long> {
    @EntityGraph(attributePaths = ["orders", "orders.items"])
    fun findByStatus(status: UserStatus): List<User>
}
```

Use fetch joins for custom JPQL queries; use `@EntityGraph` on derived query methods. Do not combine both - they conflict.

Fetch joins / `@EntityGraph` work for both `@ManyToOne` and `@OneToMany` (and `@OneToOne`). For `@ManyToOne` (e.g. `order.user.name` triggering one query per order), the same fix applies: `LEFT JOIN FETCH o.user` or `@EntityGraph(attributePaths = ["user"])`.

**Critical: do not combine collection fetch join with `Pageable`.** `LEFT JOIN FETCH u.orders` plus a `Pageable` triggers Hibernate's `HHH90003004` ("firstResult/maxResults specified with collection fetch; applying in memory") - Hibernate fetches the *entire* result set and paginates in application memory. This silently turns a paged endpoint into a full-table scan that holds all rows in heap. The same trap applies to `@EntityGraph` over a `Pageable` derived query when the graph includes a collection.

Workarounds (pick one):
- Two-query pattern: page the IDs first, then fetch the full graph using `WHERE id IN (:ids)` with the fetch join
- Use `@BatchSize` instead of fetch join for the collection
- Page only on the parent root and lazy-load the collection per row (acceptable when the page is small and Virtual Threads / batch fetch keep DB round-trips bounded)

**`MultipleBagFetchException`:** Two `LEFT JOIN FETCH` clauses on different `List<...>` collections in the same query throw `cannot simultaneously fetch multiple bags`. Either change one of the collections to `Set<...>`, or fetch only one collection per query and rely on `@BatchSize` for the rest.

### Batch Fetching

When fetch joins aren't practical (e.g., multiple `@OneToMany` causing a Cartesian product), use batch fetching to reduce N+1 to N/batch queries:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 16
```

Or per-association:

```kotlin
@Entity
class Order(
    @Id @GeneratedValue val id: Long = 0,
    @OneToMany(mappedBy = "order")
    @BatchSize(size = 16)
    val items: MutableList<OrderItem> = mutableListOf(),
)
```

Batch fetching is the best option when an entity has multiple collections - fetch joins on more than one `@OneToMany` produce a Cartesian product that multiplies rows.

### Projection Queries

For read-only endpoints that don't need the full entity, use interface or `data class` projections to reduce memory and skip Hibernate dirty-checking:

```kotlin
// Interface projection - Spring generates the implementation
interface OrderSummary {
    val id: Long
    val status: String
    val total: BigDecimal
}

interface OrderRepository : JpaRepository<Order, Long> {
    @Query("SELECT o.id AS id, o.status AS status, o.total AS total FROM Order o WHERE o.customerId = :customerId")
    fun findSummariesByCustomerId(customerId: Long): List<OrderSummary>
}

// Data class projection - cleaner for DTOs
data class OrderSummaryDto(val id: Long, val status: String, val total: BigDecimal)

interface OrderRepository : JpaRepository<Order, Long> {
    @Query("SELECT new com.example.dto.OrderSummaryDto(o.id, o.status, o.total) FROM Order o WHERE o.customerId = :customerId")
    fun findDtosByCustomerId(customerId: Long): List<OrderSummaryDto>
}
```

### Read-Only Optimization

`@Transactional(readOnly = true)` on the service class tells Hibernate to skip dirty-checking for all queries in that transaction - significant performance gain for read-heavy services:

```kotlin
@Service
@Transactional(readOnly = true)
class OrderQueryService(private val orderRepository: OrderRepository) {

    // All methods here skip dirty-checking by default
    fun search(spec: Specification<Order>, pageable: Pageable): Page<OrderSummary> =
        orderRepository.findAll(spec, pageable).map { OrderSummary.from(it) }
}
```

### Pagination

Always use `Pageable` for list endpoints - never return unbounded result sets:

```kotlin
interface OrderRepository : JpaRepository<Order, Long> {
    fun findByStatus(status: OrderStatus, pageable: Pageable): Page<Order>
}

// In controller:
@GetMapping
fun list(pageable: Pageable): Page<OrderResponse> =
    orderService.findAll(pageable).map { it.toResponse() }
```

For large datasets with stable sort order, use keyset pagination (scroll queries) instead of OFFSET - OFFSET scans and discards rows:

```kotlin
@Query("SELECT o FROM Order o WHERE o.id > :lastId ORDER BY o.id")
fun findNextPage(@Param("lastId") lastId: Long, pageable: Pageable): List<Order>
```

### Dynamic Filters with Specification

When an endpoint supports multiple optional filter parameters, use `Specification` to compose them dynamically rather than writing a combinatorial explosion of repository methods:

```kotlin
object ProductSpecifications {
    fun hasCategory(categoryId: Long?): Specification<Product>? =
        categoryId?.let { id -> Specification { root, _, cb -> cb.equal(root.get<Category>("category").get<Long>("id"), id) } }

    fun priceBetween(min: BigDecimal?, max: BigDecimal?): Specification<Product>? =
        Specification { root, _, cb ->
            when {
                min != null && max != null -> cb.between(root.get("price"), min, max)
                min != null -> cb.greaterThanOrEqualTo(root.get("price"), min)
                max != null -> cb.lessThanOrEqualTo(root.get("price"), max)
                else -> null
            }
        }
}

// In service:
fun search(categoryId: Long?, minPrice: BigDecimal?, maxPrice: BigDecimal?, pageable: Pageable): Page<ProductResponse> {
    val spec = Specification.where(ProductSpecifications.hasCategory(categoryId))
        .and(ProductSpecifications.priceBetween(minPrice, maxPrice))
    return productRepository.findAll(spec, pageable).map { it.toResponse() }
}
```

Use derived query methods (e.g., `findByCategoryId`) for simple single-parameter filters. Switch to `Specification` only when the endpoint has 2+ optional filter parameters.

### Pessimistic Locking for Critical Writes

For operations where optimistic locking is insufficient (e.g., decrementing stock, balance deductions), use pessimistic locking to prevent concurrent overwrites:

```kotlin
interface ProductRepository : JpaRepository<Product, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT p FROM Product p WHERE p.id = :id")
    fun findByIdForUpdate(id: Long): Product?
}
```

Use pessimistic locks only for short-lived transactions on single rows. For bulk operations, prefer optimistic locking with `@Version` and retry on `OptimisticLockException`.

### Second-Level Cache

Enable for entities that are read-heavy and rarely change (e.g., product catalog, configuration):

```yaml
spring:
  jpa:
    properties:
      hibernate:
        cache:
          use_second_level_cache: true
          region.factory_class: org.hibernate.cache.jcache.JCacheRegionFactory
        javax.cache.provider: org.ehcache.jsr107.EhcacheCachingProvider
```

```kotlin
@Entity
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
class Product(
    @Id @GeneratedValue val id: Long = 0,
    val name: String,
    val price: BigDecimal,
)
```

Only cache entities with low write frequency - cache invalidation on every update negates the benefit for write-heavy entities.

### Kotlin Entity Caveat - regular class, not data class

```kotlin
// Bad: data class JPA entity - copy() and equals() based on all properties break Hibernate proxies
@Entity
data class Order(
    @Id @GeneratedValue val id: Long = 0,
    val userId: Long,
    var status: OrderStatus,
)

// Good: regular class with ID-based equals/hashCode (lazy-proxy-safe)
@Entity
class Order(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long = 0,
    val userId: Long,
    var status: OrderStatus = OrderStatus.PENDING,
    @Column(updatable = false)
    val createdAt: Instant = Instant.now(),
) {
    override fun equals(other: Any?) = other is Order && id != 0L && id == other.id
    override fun hashCode() = id.hashCode()
}
```

The `kotlin("plugin.jpa")` Gradle plugin generates the no-arg constructor; `kotlin("plugin.spring")` opens the class so Hibernate can subclass it. Without these the runtime fails with `No default constructor for entity` or `Entity class is final`.

## Output Format

When applying JPA performance patterns, document the optimization:

```
Optimization: {N+1 Fix | Projection | Batch Fetch | Specification Filter | Cache | Pagination}
Entity: {entity name}
Change: {description of what was changed}
Query Count: {before} -> {after} (estimated)
```

## Avoid

- EAGER fetching on `@OneToMany` relationships - it loads the collection on every query even when not needed
- Fetch joins on multiple `@OneToMany` collections in the same query - use batch fetching instead
- `SELECT *` without projection for read-only endpoints - wastes memory and enables dirty-checking overhead
- Unbounded `findAll()` without pagination on tables that grow over time
- Second-level cache on frequently-written entities - cache invalidation overhead exceeds read benefit
- `data class` for JPA entities - breaks Hibernate proxies and lazy loading
- Manual `open` modifiers on entities or services - use `kotlin("plugin.jpa")` and `kotlin("plugin.spring")` plugins
