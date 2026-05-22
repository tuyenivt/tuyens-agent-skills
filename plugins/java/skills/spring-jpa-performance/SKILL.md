---
name: spring-jpa-performance
description: "JPA / Hibernate performance: N+1 fixes (fetch join, @EntityGraph, batch size), projections, pagination, locking, second-level cache."
metadata:
  category: backend
  tags: [jpa, hibernate, performance, queries]
user-invocable: false
---

# JPA Performance

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Optimizing data-access queries; preventing N+1
- Read-only endpoints with heavy entities
- Dynamic filter/search endpoints with multiple optional params

## Rules

- LAZY by default on all associations; never EAGER on `@OneToMany`
- Set `spring.jpa.open-in-view=false` everywhere (OSIV silently masks N+1 and `LazyInitializationException`)
- Read-only endpoints: project to DTO / record, do not return entities
- Index every column used in WHERE / ORDER BY / JOIN
- List endpoints always take `Pageable` - never unbounded `findAll()`
- Service classes default to `@Transactional(readOnly = true)`; `@Transactional` only on mutating methods

## Patterns

### N+1: fetch join vs `@EntityGraph`

```java
// Bad - N+1 on u.getOrders() per row
userRepository.findAll().forEach(u -> log.info("{}", u.getOrders()));

// Good - fetch join on custom JPQL
@Query("SELECT DISTINCT u FROM User u LEFT JOIN FETCH u.orders")
List<User> findAllWithOrders();

// Good - @EntityGraph on derived query
@EntityGraph(attributePaths = {"orders", "orders.items"})
List<User> findByStatus(UserStatus status);
```

Use fetch join for custom JPQL; `@EntityGraph` for derived methods. Do not combine.

### Two fetch-join traps

1. **Two `JOIN FETCH` on `List` collections** → `MultipleBagFetchException` at startup. Fix: change one to `Set`, split into two queries, or use `@BatchSize`.
2. **`Pageable` + collection `JOIN FETCH`** → Hibernate logs `HHH90003004` and paginates in memory (silent OOM).

```java
// Bad - in-memory pagination
@Query("SELECT DISTINCT o FROM Order o LEFT JOIN FETCH o.lines")
Page<Order> findAllWithLines(Pageable pageable);

// Good - two-query: page IDs first, fetch associations by ID
@Query("SELECT o.id FROM Order o ORDER BY o.id")
Page<Long> findOrderIds(Pageable pageable);

@Query("SELECT DISTINCT o FROM Order o LEFT JOIN FETCH o.lines WHERE o.id IN :ids ORDER BY o.id")
List<Order> findWithLinesByIds(@Param("ids") List<Long> ids);
```

Or skip `JOIN FETCH` on paginated endpoints entirely and use batch fetching.

### Batch fetching (multiple collections)

```yaml
spring.jpa.properties.hibernate.default_batch_fetch_size: 16
```

Or per-association:

```java
@OneToMany(mappedBy = "order") @BatchSize(size = 16)
private List<OrderItem> items;
```

Use batch fetching when an entity has multiple `@OneToMany` (fetch join produces Cartesian product).

### Projections for read-only queries

```java
public record OrderSummary(Long id, String status, BigDecimal total) {}

@Query("SELECT new com.example.dto.OrderSummary(o.id, o.status, o.total) FROM Order o WHERE o.customerId = :cid")
List<OrderSummary> findSummaries(Long cid);
```

Skips dirty-checking and avoids loading associations.

### Pagination and dynamic filters

`Page<T>` always for list endpoints. For very large datasets with stable sort, use keyset pagination over `OFFSET`:

```java
@Query("SELECT o FROM Order o WHERE o.id > :lastId ORDER BY o.id")
List<Order> nextPage(@Param("lastId") Long lastId, Pageable pageable);
```

When an endpoint has 2+ optional filters, compose `Specification`s instead of writing combinatorial repository methods. `null` Specifications are ignored by Spring Data.

### Pessimistic locking

For decrements / balance updates where optimistic locking is insufficient:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("SELECT p FROM Product p WHERE p.id = :id")
Optional<Product> findByIdForUpdate(Long id);
```

Short-lived transactions on single rows only. For bulk, use optimistic `@Version` + retry.

### Second-level cache

Enable for read-heavy, rarely-changed entities (catalog, config). Negates itself on write-heavy entities. Configuration goes under `hibernate.cache.*` with `@Cache(usage = READ_WRITE)` on the entity.

## Output Format

```
Optimization: {N+1 Fix | Projection | Batch Fetch | Specification | Cache | Pagination}
Entity: {name}
Change: {what changed}
Query Count: {before} → {after}
```

## Avoid

- `EAGER` on `@OneToMany` - loads collection on every query
- Combining `JOIN FETCH` on a collection with `Pageable`
- Returning entities from controllers - project to DTO
- Second-level cache on write-heavy entities
