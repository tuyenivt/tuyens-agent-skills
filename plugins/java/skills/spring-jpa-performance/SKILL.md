---
name: spring-jpa-performance
description: "JPA/Hibernate perf: N+1 (fetch join, @EntityGraph, @BatchSize), DTO projections, pagination countQuery, JDBC batching, locking, L2 cache."
metadata:
  category: backend
  tags: [jpa, hibernate, performance, queries]
user-invocable: false
---

# JPA Performance

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Diagnosing slow data-access endpoints; preventing N+1
- Read-heavy list endpoints returning entity graphs
- Bulk inserts/updates; dynamic filter/search endpoints

## Rules

- LAZY by default; never `EAGER` on `@OneToMany` / `@ManyToMany`
- `spring.jpa.open-in-view=false` (OSIV masks N+1 and `LazyInitializationException`)
- Read endpoints: project to record/DTO; never return entities
- List endpoints take `Pageable`; never unbounded `findAll()`
- Index every column in WHERE / ORDER BY / JOIN
- Service classes default `@Transactional(readOnly=true)`; `@Transactional` only on writes
- Bulk writes: set `hibernate.jdbc.batch_size` and flush+clear per chunk

## Patterns

### Measure query counts

`spring.jpa.properties.hibernate.generate_statistics: true` + `logging.level.org.hibernate.stat: DEBUG` gives per-transaction query counts; `logging.level.org.hibernate.SQL: DEBUG` shows the statements (dev only). The Output Format's `Query Count` comes from these, not from guessing.

### N+1: fetch join vs `@EntityGraph`

```java
// Bad - N+1
userRepository.findAll().forEach(u -> log.info("{}", u.getOrders()));

// Good - JPQL fetch join (custom query; Hibernate 6 de-duplicates parents, no DISTINCT needed)
@Query("SELECT u FROM User u LEFT JOIN FETCH u.orders")
List<User> findAllWithOrders();

// Good - @EntityGraph (derived query)
@EntityGraph(attributePaths = {"orders", "orders.items"})
List<User> findByStatus(UserStatus status);
```

Fetch join for custom JPQL; `@EntityGraph` for derived methods. Don't combine.

### Two fetch-join traps

1. **Two `JOIN FETCH` on `List` collections** -> `MultipleBagFetchException` at startup. Fix: change one to `Set`, split into two queries, or use `@BatchSize`.
2. **`Pageable` + collection `JOIN FETCH`** -> `HHH90003004` warning; Hibernate paginates in memory (silent OOM).

Read-only endpoint? Drop the fetch join and project to a DTO (see DTO projections) - the trap disappears. When full entities are required:

```java
// Bad - in-memory pagination
@Query("SELECT o FROM Order o LEFT JOIN FETCH o.lines")
Page<Order> findAllWithLines(Pageable p);

// Good - two-query: page IDs (caller's Pageable sort applies here), then fetch associations
@Query("SELECT o.id FROM Order o")
Page<Long> findIds(Pageable p);

@Query("SELECT o FROM Order o LEFT JOIN FETCH o.lines WHERE o.id IN :ids")
List<Order> findWithLinesByIds(@Param("ids") List<Long> ids);
// second query returns DB order: re-sort to match idPage.getContent(),
// then new PageImpl<>(orders, p, idPage.getTotalElements())
```

Alternative: drop `JOIN FETCH` on paginated endpoints and use batch fetching.

### Batch fetching (multiple collections)

```yaml
spring.jpa.properties.hibernate.default_batch_fetch_size: 16
spring.jpa.properties.hibernate.query.in_clause_parameter_padding: true  # better plan-cache hit
```

```java
@OneToMany(mappedBy = "order") @BatchSize(size = 16)
private List<OrderItem> items;
```

Use when an entity has 2+ `@OneToMany` (fetch join produces Cartesian product).

### DTO projections

```java
public record OrderSummary(Long id, String status, BigDecimal total) {}

@Query("SELECT new com.example.dto.OrderSummary(o.id, o.status, o.total) FROM Order o WHERE o.customerId = :cid")
List<OrderSummary> findSummaries(@Param("cid") Long cid);
```

Skips dirty-checking and association loading. Prefer over entities for any read-only response.

Summary DTO needing an aggregate over a lazy collection, paginated - `GROUP BY` collapses the fan-out so `Pageable` stays in SQL:

```java
public record OrderRow(Long id, String customer, BigDecimal itemTotal) {}

@Query(value = """
       SELECT new com.example.dto.OrderRow(o.id, c.name, COALESCE(SUM(i.price), 0))
       FROM Order o JOIN o.customer c LEFT JOIN o.items i
       GROUP BY o.id, c.name""",
       countQuery = "SELECT count(o) FROM Order o")
Page<OrderRow> findRows(Pageable p);
```

With `GROUP BY`, the explicit `countQuery` is mandatory, not an optimization: the derived count query counts per group, breaking `totalElements`.

### Pagination

```java
// Bad - countQuery runs the full JOIN, defeating optimization
@Query("SELECT o FROM Order o LEFT JOIN o.customer c WHERE c.region = :r")
Page<Order> find(@Param("r") String r, Pageable p);

// Good - explicit countQuery
@Query(value = "SELECT o FROM Order o JOIN o.customer c WHERE c.region = :r",
       countQuery = "SELECT count(o) FROM Order o JOIN o.customer c WHERE c.region = :r")
Page<Order> find(@Param("r") String r, Pageable p);
```

Use `Slice<T>` when total count is not needed (skips count query). For large datasets with stable sort, prefer keyset over `OFFSET`:

```java
@Query("SELECT o FROM Order o WHERE o.id > :lastId ORDER BY o.id")
List<Order> nextPage(@Param("lastId") Long lastId, Pageable p);
```

### Dynamic filters

2+ optional filters: compose `Specification`s; null Specifications are ignored. Don't write combinatorial repository methods.

```java
static Specification<Order> byRegion(String r) {
    return r == null ? null : (root, q, cb) -> cb.equal(root.get("region"), r);
}
// repository extends JpaSpecificationExecutor<Order>
repo.findAll(Specification.allOf(byRegion(region), byStatus(status), inDateRange(from, to)), pageable);
```

### Bulk writes

```java
// Bad - one INSERT per row, no batching
orders.forEach(repository::save);

// Good - JDBC batching; flush/clear chunk matches batch_size
@Transactional
public void insertAll(List<Order> orders) {
    for (int i = 0; i < orders.size(); i++) {
        em.persist(orders.get(i));
        if ((i + 1) % 50 == 0) { em.flush(); em.clear(); }  // (i+1): no empty flush at i=0
    }
}
```

```yaml
spring.jpa.properties.hibernate.jdbc.batch_size: 50
spring.jpa.properties.hibernate.order_inserts: true
spring.jpa.properties.hibernate.order_updates: true
```

Entities with `GenerationType.IDENTITY` disable insert batching; use `SEQUENCE` for batched inserts. Switching an existing entity to `SEQUENCE` is a schema migration, not an annotation swap: create the sequence (starting above `max(id)`) and align `allocationSize` with its increment. PostgreSQL also needs `reWriteBatchedInserts=true` on the JDBC URL to collapse a batch into one multi-row INSERT. For very large jobs, chunk into multiple transactions and consider Hibernate `StatelessSession` (no persistence context, no dirty checking).

### `@Modifying` queries

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("UPDATE Order o SET o.status = :s WHERE o.id IN :ids")
int markStatus(@Param("s") String s, @Param("ids") List<Long> ids);
```

Without `clearAutomatically`, the persistence context holds stale entities after a bulk update.

### Pessimistic locking

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("SELECT p FROM Product p WHERE p.id = :id")
Optional<Product> findByIdForUpdate(@Param("id") Long id);
```

Short transactions, single rows. For bulk, prefer optimistic `@Version` + retry.

### Second-level cache

Read-heavy, rarely-changed entities only (catalog, config). Counterproductive on write-heavy entities.

```yaml
spring.jpa.properties.hibernate.cache.use_second_level_cache: true
spring.jpa.properties.hibernate.cache.region.factory_class: jcache
```

```java
@Entity @Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
public class Country { ... }
```

## Output Format

```
Optimization: {N+1 Fix | Projection | Batch Fetch | Pagination | Bulk Write | Locking | Cache}
  (one value - when several apply, label by the primary mechanism of the shipped change)
Trigger: {symptom - e.g., "P95 3s on /customers, N queries per request"}
Entity/Repo: {name(s)}
Change: {what changed - code + config; list form allowed for multi-part changes}
Query Count: {before} -> {after}
```

## Avoid

- `EAGER` on collections
- `JOIN FETCH` collection + `Pageable` in one query
- Returning entities from controllers
- `saveAll()` with `IDENTITY` IDs expecting batched inserts
- `@Modifying` without `clearAutomatically=true` when followed by reads
- L2 cache on write-heavy entities
