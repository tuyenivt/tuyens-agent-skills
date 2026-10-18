---
name: spring-jpa-performance
description: "JPA/Hibernate perf: N+1 (fetch join, @EntityGraph, @BatchSize), DTO projections, pagination countQuery, JDBC batching, locking, L2 cache."
metadata:
  category: backend
  tags: [jpa, hibernate, performance, queries]
user-invocable: false
---

# JPA Performance

> Load `Use skill: stack-detect` first to determine the project stack. Its `Database` picks the JDBC batching flag, the lock-timeout syntax and the index types below; `unknown` - give the PostgreSQL and MySQL variant; another engine - give its variant where a pattern is engine-specific, or say the PostgreSQL/MySQL line does not apply. The Boot version (build file) selects the Hibernate-version notes: Boot 4.1 = Hibernate 7.4, Boot 4.0.x = 7.1-7.2, Boot 3.x = 6.x.

## When to Use

- Diagnosing slow data-access endpoints; preventing N+1
- Read-heavy list endpoints returning entity graphs; admin grids with filters and aggregates
- Bulk inserts/updates; imports
- Lost updates under concurrent writes
- Reviewing data-access code

## Rules

- LAZY by default; never `EAGER` on `@OneToMany` / `@ManyToMany` (`@ManyToOne` and `@OneToOne` default to EAGER - set LAZY; an inverse-side `@OneToOne` stays eager unless it uses `@MapsId` or bytecode enhancement)
- `spring.jpa.open-in-view=false` (OSIV masks N+1 and `LazyInitializationException`, and holds a connection for the whole request). Flipping it on an existing app turns hidden lazy loads into serialization-time failures - sweep the other read endpoints in the same change
- Read endpoints project to records/DTOs; never return entities
- List endpoints take `Pageable` (or keyset); never unbounded `findAll()`
- Index every column used in WHERE / ORDER BY / JOIN; claims about indexes made without the schema in view carry `(schema not reviewed)`. A substring filter (`LIKE '%x%'`) cannot use a btree: PostgreSQL needs a `pg_trgm` GIN index on the same expression the predicate uses (`gin (lower(name) gin_trgm_ops)` for `lower(name) LIKE ...`); MySQL has no index for it - rewrite to `MATCH ... AGAINST` over a FULLTEXT index (word match; `WITH PARSER ngram` for substrings) or accept the scan
- Service classes default `@Transactional(readOnly=true)`; `@Transactional` only on writes
- Bulk writes: set `hibernate.jdbc.batch_size`, flush+clear per chunk, and enable the driver's batch rewrite

## Patterns

### Measure query counts

`spring.jpa.properties.hibernate.generate_statistics: true` plus `logging.level.org.hibernate.session.metrics: DEBUG` logs a per-Session `Logging session metrics` block (JDBC statements executed and time) - on Hibernate 7 the property alone prints nothing; `logging.level.org.hibernate.SQL: DEBUG` shows every statement including lazy loads (dev only); `logging.level.org.hibernate.statistics: DEBUG` adds per-query timings (Hibernate 7.1 / Boot 4.0.0: `org.hibernate.stat`; Hibernate 6.x / Boot 3.x: the property alone logs an INFO `Session Metrics` line, per-query timings under `org.hibernate.stat`). The Output Format's `Query Count` comes from these, not from guessing.

### N+1: fetch join vs `@EntityGraph`

```java
// Bad - N+1
userRepository.findAll().forEach(u -> log.info("{}", u.getOrders()));

// Good - JPQL fetch join (Hibernate de-duplicates parents, no DISTINCT needed)
@Query("SELECT u FROM User u LEFT JOIN FETCH u.orders")
List<User> findAllWithOrders();

// Good - @EntityGraph on a derived query; nested paths ("orders.items") are allowed as long as
// at most one fetched collection is a List (trap 1) - otherwise load the rest via @BatchSize
@EntityGraph(attributePaths = "orders")
List<User> findByStatus(String status);
```

Fetch join for custom JPQL; `@EntityGraph` for derived methods. Don't combine.

### Two fetch-join traps

1. **Two bag (`List`) collections fetched in one query** - fetch joins or an entity graph naming two - throws `MultipleBagFetchException` when the query first runs, so only a test that executes the method catches it. Fix, in order: two queries in one transaction (N+M rows, entity model untouched - both fill the same managed parent instances, so no manual merge); `@BatchSize` once a third collection appears; `Set` only when the collection is genuinely unordered - it legalises the query but keeps the Cartesian product.
2. **`Pageable` + collection `JOIN FETCH`** - Hibernate below 7.4 (every Boot 3.x and 4.0.x) logs `HHH90003004` and paginates in memory (OOM on large parents); Hibernate 7.4+ (Boot 4.1+) pages the root rows in a derived-table subquery in SQL on PostgreSQL and MySQL 8, so the page is bounded and only the Cartesian row count per page remains.

Read-only endpoint? Drop the fetch join and project to a DTO - the trap disappears. When full entities are required on a Hibernate below 7.4:

```java
// Bad - in-memory pagination
@Query("SELECT o FROM Order o LEFT JOIN FETCH o.lines")
Page<Order> findAllWithLines(Pageable p);

// Good - page IDs (the caller's Pageable sort applies here), then fetch associations
@Query("SELECT o.id FROM Order o")
Page<Long> findIds(Pageable p);

@Query("SELECT o FROM Order o LEFT JOIN FETCH o.lines WHERE o.id IN :ids")
List<Order> findWithLinesByIds(@Param("ids") List<Long> ids);
// the second query returns DB order: re-sort to idPage.getContent(), then
// new PageImpl<>(orders, p, idPage.getTotalElements())
```

`spring.jpa.properties.hibernate.query.in_clause_parameter_padding: true` improves plan-cache hits for expanded `IN :ids` lists like this one.

### Batch fetching (multiple collections)

```yaml
spring.jpa.properties.hibernate.default_batch_fetch_size: 16
```

```java
@OneToMany(mappedBy = "order") @BatchSize(size = 16)
private List<OrderItem> items;
```

Use when an entity has 2+ `@OneToMany` loaded together. On PostgreSQL Hibernate batch-loads with a single array parameter (`= any (?)`).

### DTO projections

```java
public record OrderSummary(Long id, String status, BigDecimal total) {}

@Query("SELECT new com.example.dto.OrderSummary(o.id, o.status, o.total) FROM Order o WHERE o.customer.id = :cid")
List<OrderSummary> findSummaries(@Param("cid") Long cid);
```

Skips dirty-checking and association loading. Prefer over entities for any read-only response.

Paginated summary with one aggregate over a collection - `GROUP BY` collapses the fan-out so `Pageable` stays in SQL:

```java
public record OrderRow(Long id, String customer, BigDecimal itemTotal) {}

@Query(value = """
       SELECT new com.example.dto.OrderRow(o.id, c.name, COALESCE(SUM(i.price), 0))
       FROM Order o JOIN o.customer c LEFT JOIN o.items i
       GROUP BY o.id, c.name""",
       countQuery = "SELECT count(o) FROM Order o JOIN o.customer c")
Page<OrderRow> findRows(Pageable p);
// sort by the aggregate: PageRequest.of(n, 50, JpaSort.unsafe(DESC, "COALESCE(SUM(i.price), 0)"))
```

- The explicit `countQuery` is mandatory with `GROUP BY`. Without one, Data JPA 4 inside a transaction counts through Hibernate's `getResultCount()` - `select count(*)` over the whole grouped query as a derived table, aggregating every group just to count them - and outside a transaction (or on Data JPA 3.x) the Spring-derived count keeps the grouping, fetches one row per group, and - when exactly one group matches and the count runs (page size 1, or a page past the first) - returns that group's joined-row count as the total. The count keeps every join that filters rows (here the inner join to `customer`).
- Sorting: only grouped columns and aggregate expressions are sortable; pass an aggregate as an expression through `JpaSort.unsafe` (a plain `Sort` property would render as `o.itemTotal` and fail). A sort by the aggregate aggregates every matching parent before `LIMIT` - allow it only behind a narrowing filter (date range, status) and say so in the design.
- Two aggregates over two different collections (line count and paid amount) never share one `GROUP BY` over both joins - the joins multiply each other and every SUM/COUNT inflates. Use a correlated subquery per aggregate, or aggregate each collection in its own grouped subquery.
- `GROUP BY` collapses the fan-out logically, not physically - the DB aggregates the whole join before `LIMIT`. At high fan-out (100k+ parents x tens of children), page the scalar columns first and aggregate over the page's IDs only. Choose `GROUP BY` when the aggregate is the sort key or a filter, the two-query ID page otherwise.

### Pagination

```java
// Bad outside a transaction - the Spring-derived count keeps the join to customer for nothing
// (inside one, Data JPA 4 counts via Hibernate's getResultCount(), which drops the fetch join)
@Query("SELECT o FROM Order o LEFT JOIN FETCH o.customer WHERE o.status = :s")
Page<Order> findByStatus(@Param("s") String s, Pageable p);

// Good - a to-one join that does not filter is dead weight in the count; explicit on every Hibernate
@Query(value = "SELECT o FROM Order o LEFT JOIN FETCH o.customer WHERE o.status = :s",
       countQuery = "SELECT count(o) FROM Order o WHERE o.status = :s")
Page<Order> findByStatus(@Param("s") String s, Pageable p);
```

`Slice<T>` when the total is not needed (skips the count). Deep pages on large tables use keyset scrolling - `Window<Order> findFirst50ByStatusOrderByIdAsc(String status, ScrollPosition position)`, first page `ScrollPosition.keyset()`, next `window.positionAt(window.size() - 1)`; a keyset query never takes a page number. An admin grid that needs page numbers keeps `OFFSET`, with filters and indexes narrowing the rows and a cap on page depth. A client-supplied sort key is mapped through a whitelist, never passed through as a property name.

### Dynamic filters

2+ optional filters: compose `Specification`s. Spring Data JPA 4 rejects `null` Specifications (`where` / `and` / `or` / `not`, and a null element in `allOf` / `anyOf`, throw) - start from `Specification.unrestricted()` and add only the filters present. (Boot 3 / Data JPA 3.x: start from `Specification.where(null)`; null Specifications are ignored there.) Don't write combinatorial repository methods.

```java
static Specification<Order> byRegion(String r) { return (root, q, cb) -> cb.equal(root.get("region"), r); }
static Specification<Order> byStatus(String s) { return (root, q, cb) -> cb.equal(root.get("status"), s); }
static Specification<Order> byCustomerName(String s) {
    return (root, q, cb) -> cb.like(cb.lower(root.join("customer").get("name")), "%" + s.toLowerCase() + "%");
}
// repository extends JpaSpecificationExecutor<Order>
Specification<Order> spec = Specification.unrestricted();
if (region != null) spec = spec.and(byRegion(region));
if (status != null) spec = spec.and(byStatus(status));
if (name != null)   spec = spec.and(byCustomerName(name));
repo.findAll(spec, pageable);
```

`JpaSpecificationExecutor` returns entities, and a `@Query` with `GROUP BY` is static - neither alone serves a filtered grid that also needs aggregate columns or sorts by one. That combination is a custom repository fragment building a Criteria query: the same `Specification` feeds the data query (DTO construction with aggregate subqueries, `orderBy` on the subquery expression) and an explicit `countDistinct` count.

### Bulk writes and imports

```java
// Bad - no enclosing transaction: every save() is its own transaction and commit, one round trip per row, nothing batches
// (inside one big transaction without flush/clear the opposite failure: the context grows unbounded)
orders.forEach(repository::save);

// Good - one transaction per chunk, JDBC batching, flush/clear at the chunk boundary.
// Called through the proxy from another bean - a this.insertChunk(...) self-call bypasses @Transactional: no per-chunk
// transaction (none at all from a non-transactional loop, one shared transaction from a transactional one)
@Transactional
public void insertChunk(List<Order> chunk) {
    for (int i = 0; i < chunk.size(); i++) {
        em.persist(chunk.get(i));
        if ((i + 1) % 50 == 0) { em.flush(); em.clear(); }   // (i+1): no empty flush at i=0
    }
}
```

```yaml
spring.jpa.properties.hibernate.jdbc.batch_size: 50
spring.jpa.properties.hibernate.order_inserts: true
spring.jpa.properties.hibernate.order_updates: true
# driver batch rewrite:
#   MySQL:      jdbc:mysql://.../db?rewriteBatchedStatements=true  - without it each statement is its own round trip
#   PostgreSQL: jdbc:postgresql://.../db?reWriteBatchedInserts=true - the batch is already pipelined; this also
#               folds inserts into multi-row VALUES
```

- `GenerationType.IDENTITY` disables Hibernate insert batching whatever the driver flag says; use `SEQUENCE`. Switching an existing entity is a schema migration (`spring-db-migration-safety`): create the sequence starting at `max(id) + allocationSize` (Hibernate's pooled optimizer treats the first value as a high-water mark) with its increment equal to `allocationSize`. MySQL has no sequences: bulk loads go through a plain JDBC batch (`JdbcTemplate.batchUpdate`) with `rewriteBatchedStatements=true`, or the entity takes application-assigned IDs. The same JDBC route avoids a sequence migration on a huge PostgreSQL table.
- `em.clear()` detaches everything, including entities the chunk loaded to compare against - flush and clear only at chunk boundaries. References a row needs (the customer by email) are resolved once per chunk with a single `IN` query into a map, never with a lookup per row.
- `IN (:ids)` is capped by the driver's bind-parameter limit (PgJDBC: 65,535) - chunk ID lists too.
- Chunked transactions give up all-or-nothing: make the write idempotent (upsert on a natural key) and checkpoint the last committed chunk (a job-run row holding the last committed source offset, written in the chunk's transaction) so a retry resumes. The natural key needs a unique index (`ON CONFLICT` / `ON DUPLICATE KEY` target it), and the source is deduplicated on that key before each statement or batch - a repeated key in one PostgreSQL `ON CONFLICT DO UPDATE` fails it (`cannot affect row a second time`; `reWriteBatchedInserts=true` folds a JDBC batch into one such statement), while `DO NOTHING` silently keeps the first row and MySQL `ON DUPLICATE KEY UPDATE` lets the last one win. No natural key in the source: load into a staging table keyed by (source file, line number), then upsert from staging in chunks; no natural key in the target: add a unique source reference column (`(order_id, source_line_ref)`) or delete-and-reinsert per source batch in one transaction.
- Very large jobs: Hibernate `StatelessSession` (no persistence context, no dirty checking; Hibernate 7 ignores `hibernate.jdbc.batch_size` there - call `setJdbcBatchSize(n)` or `insertMultiple(list)`) or plain JDBC batching.

### `@Modifying` queries

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("UPDATE Order o SET o.status = :s WHERE o.id IN :ids")
int markStatus(@Param("s") String s, @Param("ids") List<Long> ids);
```

Without `clearAutomatically`, the persistence context keeps stale entities after the bulk update. With it, the *entire* context is evicted - re-read any reference held across the call - and without `flushAutomatically` the clear discards pending unflushed changes (Hibernate's own auto-flush fires only when the table spaces overlap). A bulk `UPDATE` inside a `readOnly = true` transaction fails with a read-only-transaction error. A JPQL bulk `UPDATE` does not bump `@Version` - on a versioned entity write `UPDATE VERSIONED ...` (Hibernate) or `SET e.version = e.version + 1`.

### Concurrent updates (lost updates)

Read-check-write in one transaction (`if (stock.getOnHand() >= qty) stock.setOnHand(...)`) loses updates under concurrency - two transactions read the same value. In order of preference:

```java
// 1. Atomic conditional UPDATE - no read, no lock held across application code (the row lock still lasts
//    until commit, so keep the transaction short); 0 rows = rejected. Reservation variant:
//    SET s.reserved = s.reserved + :q WHERE s.id = :id AND s.onHand - s.reserved >= :q
@Modifying(clearAutomatically = true, flushAutomatically = true) @Query("UPDATE StockLevel s SET s.onHand = s.onHand - :q WHERE s.id = :id AND s.onHand >= :q")
int decrementIfAvailable(@Param("id") Long id, @Param("q") int qty);

// 2. Optimistic: @Version on the entity; OptimisticLockingFailureException surfaces at flush/commit - retry
//    a bounded number of times around the transaction boundary (a caller of the @Transactional method),
//    each attempt in a fresh transaction

// 3. Pessimistic - short transactions, single rows; bound the wait so a stuck holder cannot pile up waiters.
//    jakarta.persistence.lock.timeout: 0 (NOWAIT) and -2 (SKIP LOCKED) work on both engines; a positive value -
//    PostgreSQL - Hibernate 7.2.8+ / 7.4+ (Boot 4.0.6+, 4.1.x) applies it (set local lock_timeout, restored after the query);
//                 older Hibernate (every Boot 3.x, Boot 4.0.0-4.0.5): run SET LOCAL lock_timeout = '3s' first in the transaction;
//    MySQL      - ignored: SET SESSION innodb_lock_wait_timeout = 3 (session-scoped: reset it after)
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("SELECT s FROM StockLevel s WHERE s.storeId = :store AND s.sku = :sku")
Optional<StockLevel> findForUpdate(@Param("store") Long store, @Param("sku") String sku);
```

Lock the rows of a multi-row write in a fixed order (by ID) to avoid deadlocks; retry on deadlock (`CannotAcquireLockException`). Where the guard sits relative to remote calls (reserve before or after the inventory HTTP call, the payment) is `spring-transaction`'s boundary question, not a query-shape one.

### Second-level cache

Read-heavy, rarely-changed entities only (catalog, config); counterproductive on write-heavy entities. Needs `org.hibernate.orm:hibernate-jcache` plus a JCache provider (`org.ehcache:ehcache:<ver>:jakarta`), then `spring.jpa.properties.hibernate.cache.use_second_level_cache: true`, `spring.jpa.properties.hibernate.cache.region.factory_class: jcache`, `spring.jpa.properties.hibernate.javax.cache.uri: ehcache.xml` (a bare classpath resource name - a `classpath:` prefix fails bootstrap) with bounded regions and a TTL, and `@Cacheable @org.hibernate.annotations.Cache(usage = CacheConcurrencyStrategy.READ_WRITE)` on the entity.

## Output Format

In every mode, emit the `**Engine:**` line once, then one block per shipped change: independent fixes that share a symptom are separate blocks; a fix and the rewrites it forces (an OSIV flip and the endpoints it breaks) are one block with a list-form `Change`. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, list findings first - `### [Must|Recommend] file:line` (pasted input: `Class.method`), then `Issue:` and `Fix:` as separate paragraphs, `[Must]` first, `[Must]` when it loses updates, loads unbounded rows into memory, times out a request path, throws at runtime or startup, or returns wrong results, `[Recommend]` otherwise - then one block per fix as the target state. A design or authoring request against existing code reviews that code first: findings, then the blocks as the target state; a greenfield request has no findings. `Optimization` takes one value per block: the mechanism of the shipped change (a projection that replaces lazy loads is `Projection`).

```
**Engine:** {PostgreSQL | MySQL | other: <name> | unknown - both variants given}
```

```
Optimization: {N+1 Fix | Projection | Batch Fetch | Pagination | Filtering | Index | Bulk Write | Locking | Cache | Correctness}

Trigger: {symptom - e.g., "P95 3s on /customers, N queries per request"}

Entity/Repo: {entity or repository name(s) | <table> - JDBC}

Change: {what changed - code + config; list form for multi-part changes}

Query Count: {before | n/a - new endpoint} -> {after | unchanged} ({measured - hibernate.generate_statistics | derived - counted from query shape | n/a - fix changes correctness, not statement count})
```

Measure when the app can be run; otherwise count from the query shape and label the slot `derived`.

## Avoid

- `saveAll()` with `IDENTITY` IDs expecting batched inserts; MySQL batching without `rewriteBatchedStatements`
- `@Modifying` without `clearAutomatically=true` when followed by reads
- Read-check-write on counters without an atomic update or a lock
- L2 cache on write-heavy entities
