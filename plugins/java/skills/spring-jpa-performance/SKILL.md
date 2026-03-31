---
name: spring-jpa-performance
description: JPA/Hibernate performance patterns covering N+1 detection with fetch joins and entity graphs, batch size tuning, projection queries, and second-level cache strategy.
metadata:
  category: backend
  tags: [jpa, hibernate, performance, queries]
user-invocable: false
---

# JPA Performance

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Optimizing data access layer queries
- Preventing N+1 query problems
- Reducing memory footprint of large result sets
- Building dynamic filter/search queries with multiple optional parameters

## Rules

- Default LAZY for all associations
- Avoid EAGER fetching without explicit need
- Use fetch join selectively for specific queries
- Prefer projection over entity for read-only queries
- Detect and eliminate N+1 queries
- Keep entities small, avoid heavy logic inside entities
- Add indexes on WHERE/ORDER BY/JOIN columns (see core plugin's `backend-db-indexing` for general index strategy)
- Set `spring.jpa.open-in-view=false` in all environments - open-in-view silently masks lazy loading issues by keeping the Hibernate session open through the controller layer, causing unpredictable N+1 queries in the view

## Patterns

### N+1 Detection and Fix

Bad - Causes N+1 queries:

```java
List<User> users = userRepository.findAll(); // 1 query
for (User u : users) {
    System.out.println(u.getOrders()); // N additional queries
}
```

Good - Fetch join prevents N+1:

```java
@Query("SELECT DISTINCT u FROM User u LEFT JOIN FETCH u.orders")
List<User> findAllWithOrders();
```

Good - `@EntityGraph` for declarative fetch control (avoids JPQL when you just need eager loading on a standard query):

```java
@EntityGraph(attributePaths = {"orders", "orders.items"})
List<User> findByStatus(UserStatus status);
```

Use fetch joins for custom JPQL queries; use `@EntityGraph` on derived query methods. Do not combine both - they conflict.

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

```java
@OneToMany(mappedBy = "order")
@BatchSize(size = 16)
private List<OrderItem> items;
```

Batch fetching is the best option when an entity has multiple collections - fetch joins on more than one `@OneToMany` produce a Cartesian product that multiplies rows.

### Projection Queries

For read-only endpoints that don't need the full entity, use interface or record projections to reduce memory and skip Hibernate dirty-checking:

```java
// Interface projection - Spring generates the implementation
public interface OrderSummary {
    Long getId();
    String getStatus();
    BigDecimal getTotal();
}

@Query("SELECT o.id AS id, o.status AS status, o.total AS total FROM Order o WHERE o.customerId = :customerId")
List<OrderSummary> findSummariesByCustomerId(Long customerId);

// Record projection (Java 21+) - cleaner for DTOs
public record OrderSummaryDto(Long id, String status, BigDecimal total) {}

@Query("SELECT new com.example.dto.OrderSummaryDto(o.id, o.status, o.total) FROM Order o WHERE o.customerId = :customerId")
List<OrderSummaryDto> findDtosByCustomerId(Long customerId);
```

### Read-Only Optimization

`@Transactional(readOnly = true)` on the service class tells Hibernate to skip dirty-checking for all queries in that transaction - significant performance gain for read-heavy services:

```java
@Service
@Transactional(readOnly = true)
@RequiredArgsConstructor
public class OrderQueryService {
    // All methods here skip dirty-checking by default
    public Page<OrderSummary> search(Specification<Order> spec, Pageable pageable) {
        return orderRepository.findAll(spec, pageable);
    }
}
```

### Pagination

Always use `Pageable` for list endpoints - never return unbounded result sets:

```java
Page<Order> findByStatus(OrderStatus status, Pageable pageable);

// In controller:
@GetMapping
public Page<OrderResponse> list(Pageable pageable) {
    return orderService.findAll(pageable).map(OrderResponse::from);
}
```

For large datasets with stable sort order, use keyset pagination (scroll queries) instead of OFFSET - OFFSET scans and discards rows:

```java
@Query("SELECT o FROM Order o WHERE o.id > :lastId ORDER BY o.id")
List<Order> findNextPage(@Param("lastId") Long lastId, Pageable pageable);
```

### Dynamic Filters with Specification

When an endpoint supports multiple optional filter parameters, use `Specification` to compose them dynamically rather than writing a combinatorial explosion of repository methods:

```java
public class ProductSpecifications {
    public static Specification<Product> hasCategory(Long categoryId) {
        return (root, query, cb) -> categoryId == null ? null : cb.equal(root.get("category").get("id"), categoryId);
    }

    public static Specification<Product> priceBetween(BigDecimal min, BigDecimal max) {
        return (root, query, cb) -> {
            if (min != null && max != null) return cb.between(root.get("price"), min, max);
            if (min != null) return cb.greaterThanOrEqualTo(root.get("price"), min);
            if (max != null) return cb.lessThanOrEqualTo(root.get("price"), max);
            return null; // null spec is ignored by Spring Data
        };
    }
}

// In service:
public Page<ProductResponse> search(Long categoryId, BigDecimal minPrice, BigDecimal maxPrice, Pageable pageable) {
    Specification<Product> spec = Specification.where(hasCategory(categoryId))
        .and(priceBetween(minPrice, maxPrice));
    return productRepository.findAll(spec, pageable).map(ProductResponse::from);
}
```

Use derived query methods (e.g., `findByCategoryId`) for simple single-parameter filters. Switch to `Specification` only when the endpoint has 2+ optional filter parameters.

### Pessimistic Locking for Critical Writes

For operations where optimistic locking is insufficient (e.g., decrementing stock, balance deductions), use pessimistic locking to prevent concurrent overwrites:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("SELECT p FROM Product p WHERE p.id = :id")
Optional<Product> findByIdForUpdate(Long id);
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

```java
@Entity
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
public class Product {
    // ...
}
```

Only cache entities with low write frequency - cache invalidation on every update negates the benefit for write-heavy entities.

## Output Format

When applying JPA performance patterns, document the optimization:

```
Optimization: {N+1 Fix | Projection | Batch Fetch | Specification Filter | Cache | Pagination}
Entity: {entity name}
Change: {description of what was changed}
Query Count: {before} → {after} (estimated)
```

## Avoid

- EAGER fetching on `@OneToMany` relationships - it loads the collection on every query even when not needed
- Fetch joins on multiple `@OneToMany` collections in the same query - use batch fetching instead
- `SELECT *` without projection for read-only endpoints - wastes memory and enables dirty-checking overhead
- Unbounded `findAll()` without pagination on tables that grow over time
- Second-level cache on frequently-written entities - cache invalidation overhead exceeds read benefit
