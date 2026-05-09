---
name: task-kotlin-review-perf
description: Kotlin/Spring Boot performance review for JPA/Hibernate N+1, fetch strategies, query plans, coroutine dispatcher / Virtual Thread interop, HikariCP sizing, async/messaging throughput, Flow backpressure, and caching. Stack-specific override of task-code-review-perf for Kotlin/Spring Boot.
agent: kotlin-performance-engineer
metadata:
  category: backend
  tags: [kotlin, spring-boot, performance, jpa, hibernate, coroutines, virtual-threads, workflow]
  type: workflow
user-invocable: true
---

# Kotlin / Spring Boot Performance Review

## Purpose

Kotlin-aware performance review that names JPA/Hibernate, Spring Data, coroutines, Virtual Thread, HikariCP, and Spring caching idioms directly. Produces findings with measured or estimated impact (latency, throughput, query count, GC pressure) and concrete fixes using Kotlin 2.0+ / Spring Boot 3.5+ patterns.

This workflow is the stack-specific delegate of `task-code-review-perf` for Kotlin / Spring Boot.

## When to Use

- Reviewing a Kotlin/Spring Boot PR or branch for performance regressions
- Investigating a slow `@RestController` action, `@Async` task, `CoroutineScope.launch` job, or batch
- Pre-merge perf pass on changes touching JPA queries, repositories, fetch graphs, `@Transactional` boundaries, or `Flow` streaming
- Quarterly N+1 / query-plan / pool-sizing sweep against APM-flagged endpoints

**Not for:**

- General Kotlin/Spring Boot code review (use `task-kotlin-review`)
- Security review (use `task-kotlin-review-security`)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-kotlin-implement`)

## Depth Levels

| Depth      | When to Use                                                         | What Runs                                          |
| ---------- | ------------------------------------------------------------------- | -------------------------------------------------- |
| `quick`    | Single endpoint or repository                                       | Steps 5 + 6 only; JPA hotspots + indexes/migration |
| `standard` | Default - full Kotlin/Spring perf review                            | All steps                                          |
| `deep`     | Profiling-driven review with JFR / async-profiler / Micrometer data | All steps + capacity guidance and load-test plan   |

Default: `standard`.

## Invocation

| Invocation                          | Meaning                                                                                              |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `/task-kotlin-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch                                  |
| `/task-kotlin-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                           |
| `/task-kotlin-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>`                                                  |

When invoked as a subagent of `task-code-review-perf`, Step 2 is skipped and parent's read-once artifacts are reused.

## Workflow

### Step 1 - Load Behavioral Principles (mandatory, first)

Use skill: `behavioral-principles`. Load these rules first - they govern every step including stack detection, scope decisions, and finding generation.

### Step 2 - Confirm Stack

Use skill: `stack-detect` to confirm Kotlin / Spring Boot. If invoked as a delegate of `task-code-review-perf` or as a subagent of `task-kotlin-review` (parent already detected Kotlin/Spring), accept the pre-confirmed stack and skip re-detection. If not, stop and tell the user to invoke `/task-code-review-perf` instead.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check`. On approval, read diff and commit log once and reuse for all steps. Skip if invoked as a subagent and parent passed the handle.

### Step 4 - Read the Performance Surface

Before applying checklists, open the files that govern query and concurrency behavior:

- Every changed `@Entity` (associations, fetch types, `@EntityGraph` / `@NamedEntityGraph`)
- Every changed `@Repository` (derived methods, `@Query`, `Pageable` parameters, projection types, `Flow` returns from `CoroutineCrudRepository`)
- Every changed `@Service` and `@RestController` (suspend boundaries, `Flow` consumption, parallel `coroutineScope { ... async { } }` patterns)
- `application.yml` for `spring.datasource.hikari.*`, `spring.jpa.*`, `spring.kafka.listener.concurrency`, `spring.threads.virtual.enabled`, cache config
- `build.gradle.kts` plugin block (presence of `kotlin("plugin.jpa")`, `kotlin("plugin.spring")`)
- Any new Flyway / Liquibase migration

For each finding, cite a real `file:line`. If the diff is small but the regression lives in unchanged code (a new caller exposing an existing N+1), read the unchanged file too.

### Step 5 - JPA / Hibernate Hotspots

Use skill: `kotlin-spring-jpa-performance` for canonical patterns.

Inspect every changed `@Entity`, `@Repository`, `@Service`, and `@RestController` for:

- [ ] **N+1 in repository calls**: any association touched after a query is preloaded with a fetch join (`@Query("... join fetch e.children ...")`), an `@EntityGraph`, or a projection. `FetchType.EAGER` on `@ManyToOne` / `@OneToMany` is a smell - prefer lazy + explicit fetch
- [ ] **N+1 in serializers / response mappers**: extension functions like `Order.toResponse()` silently trigger N+1 when they touch lazy associations not preloaded. Fix on the repository / service (entity graph or fetch join), not the mapper. Prefer projection DTOs
- [ ] **Multi-level N+1**: nested traversal (`order.lineItems.forEach { it.product.name }`) - resolve with multi-attribute `@EntityGraph` or JPQL `join fetch e.lineItems li join fetch li.product`
- [ ] **`LazyInitializationException` risk**: any access to a lazy association outside the original `@Transactional` scope (in a controller after the service returns the entity, or inside a Jackson serializer). Fix: fetch join, projection DTO, keep `OpenEntityManagerInViewInterceptor` disabled (the default in Boot 3+)
- [ ] **Missing indexes for filter/sort columns**: any field used in `@Query` `where` / `order by` / `group by` clauses without a backing index in the migration
- [ ] **`findAll()` without pagination**: any read of an unbounded collection - require `Pageable`
- [ ] **`Page<T>` vs `Slice<T>` vs `List<T>` cost**: `Page<T>` runs an extra `COUNT(*)` query per call - expensive on large filtered tables. Use `Slice<T>` when the UI only needs "has-more" semantics (no total count); use `List<T>` with explicit `LIMIT` for short lists. Flag any new `Page<T>` method backing an infinite-scroll endpoint
- [ ] **Streaming for large result sets**: repository methods returning `List<T>` over potentially unbounded queries should return `Stream<T>` (annotated `@QueryHints(@QueryHint(name = HINT_FETCH_SIZE, value = "100"))`) consumed inside a `@Transactional` block, or `Flow<T>` from `CoroutineCrudRepository`. Loading 100k rows into a `List` blows heap and stalls the request thread
- [ ] **`@Transactional(timeout = N)`** on write-heavy paths and any path that calls long external work: the default is no timeout - a stuck query holds a connection forever. Set explicit timeout (typically 5-30s) on user-facing transactional service methods; flag any new `@Transactional` without a timeout on a path that touches > 1 entity
- [ ] **Collection fetch join with `Pageable`**: a JPQL query with `LEFT JOIN FETCH e.collection` *and* a `Pageable` parameter triggers Hibernate's `HHH90003004` warning and paginates the entire collection in application memory. Same trap with `@EntityGraph(attributePaths = ["collection"])` over a `Pageable` derived query. Fix: page the parent IDs first then re-query with `WHERE id IN (:ids)` + fetch join, or replace fetch join with `@BatchSize`
- [ ] **`existsBy*` vs `findBy*().isPresent()` / `findBy*() != null`**: existence checks must use derived `existsBy*` (compiles to `select 1 ... limit 1`)
- [ ] **Batch operations**: `saveAll`, `deleteAllInBatch` over loops; `spring.jpa.properties.hibernate.jdbc.batch_size` set (typically 25-50); `order_inserts` / `order_updates` enabled when batching
- [ ] **`@Transactional(readOnly = true)`** on read paths
- [ ] **No entity returns from controllers**: controllers return DTOs or projections (`Order.toResponse()`)
- [ ] **Transactions scoped tightly**: no HTTP calls, message publishes, or external I/O inside `@Transactional` blocks (use `@TransactionalEventListener(phase = AFTER_COMMIT)` or outbox)
- [ ] **`data class` for JPA entities**: this corrupts identity semantics under Hibernate proxies, surfacing as duplicated queries during `equals` / `hashCode` calls in collections - flag as both correctness and performance

### Step 6 - Indexes and Migrations

Use skill: `kotlin-spring-db-migration-safety` for safe-migration checks on any change in `db/migration/` or `db/changelog/`.

- [ ] Every column referenced in `@Query` `where` / `order by` / `group by` is backed by an index
- [ ] Composite indexes match leftmost-prefix pattern of queries
- [ ] Foreign keys have indexes (PostgreSQL does not auto-index FKs)
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL); Flyway/Liquibase script split so concurrent statement runs outside transaction
- [ ] Unique constraints enforced at the database level
- [ ] Partial indexes used for boolean/enum filters that select small subsets
- [ ] No DDL on hot tables in a single migration (expand-then-contract)

### Step 7 - Coroutines, Virtual Threads, and Async

_Skipped at `quick` depth._

Use skill: `kotlin-spring-async-processing` for `@Async` patterns; `kotlin-coroutines-spring` for coroutine patterns.

Inspect changes touching `@Async`, `TaskExecutor`, `CoroutineScope`, `suspend`, `Flow`, `withContext`, or `synchronized`:

- [ ] **No `synchronized` on shared instances** in Virtual-Thread-enabled paths - pinning carrier thread defeats the model. Replace with `ReentrantLock`, `StampedLock`, or `kotlinx.coroutines.sync.Mutex` for coroutine code
- [ ] **Virtual Threads enabled where appropriate**: `spring.threads.virtual.enabled=true` on Boot 3.2+; servlet container and `@Async` `TaskExecutor` use `VirtualThreadPerTaskExecutor`
- [ ] **`Dispatchers.IO` redundant under VTs**: if VTs are active, `withContext(Dispatchers.IO) { jdbcCall() }` is added overhead - blocking JDBC on a Virtual Thread is already non-blocking from the caller's perspective. Flag and recommend removal
- [ ] **`Dispatchers.Default` for CPU-bound only**: image processing, crypto, heavy computation - never for I/O
- [ ] **HikariCP pool sized correctly**: with VTs, "small pool, fast queries" still holds - oversizing increases DB contention. Typical: `maximumPoolSize` between `cores x 2` and `cores x 4` for OLTP; `connectionTimeout` 1-3s; `maxLifetime` 30 min (less than DB-side `wait_timeout`). With coroutine + non-blocking JDBC drivers (R2DBC), pool sizing rules differ - document explicitly
- [ ] **Connection leak detection**: enabled (`leakDetectionThreshold: 5000`) in non-prod
- [ ] **`runBlocking` in production paths**: only at top-level entry (`main`, scheduled-job adapters); never inside service / controller methods
- [ ] **`GlobalScope.launch`**: leaks coroutines on shutdown - flag as both correctness and perf
- [ ] **Coroutine cancellation propagation**: `coroutineScope { ... }` is cancellation-aware; long-running blocks should call `ensureActive()` or `yield()` periodically; cleanup in `finally` wrapped in `withContext(NonCancellable)` only when calling `suspend` functions during cleanup
- [ ] **`Flow` backpressure**: `Flow.buffer(...)` and `conflate()` for fast producers; `Flow.flatMapMerge(concurrency = N)` for parallel transforms - do not leave unbounded `flatMapMerge` (default concurrency 16)
- [ ] **HTTP clients** (`WebClient`, `RestClient`) reused as beans, not instantiated per call; connection-pool timeouts set explicitly
- [ ] **Circuit breaker** (Resilience4j) on flaky external dependencies; bulkheads on shared executors
- [ ] **No blocking calls inside reactive (`Mono`/`Flux`) chains** - use `publishOn(Schedulers.boundedElastic())` if blocking is unavoidable
- [ ] **Inline functions for hot higher-order paths**: `inline` on hot lambdas to eliminate function-object allocation; `inline value class` (`@JvmInline value class`) for primitive wrappers in hot paths

### Step 8 - Caching and Response Performance

_Skipped at `quick` depth unless the diff touches `@Cacheable` / cache config._

- [ ] Spring Cache (`@Cacheable`) used for expensive read paths with deterministic key; explicit `unless` for null/empty
- [ ] Cache backend chosen: Caffeine for in-process; Redis (Spring Data Redis or Lettuce) for shared / multi-instance
- [ ] **Cache stampede protection**: hot keys with expensive regeneration use Caffeine `refreshAfterWrite` or `LoadingCache`
- [ ] Cache invalidation explicit (`@CacheEvict` on writes, or TTL with documented staleness budget)
- [ ] **`@Cacheable` on `suspend` functions**: Spring Cache does not natively support `suspend` returns - flag and recommend caching at a synchronous adapter layer or using a coroutine-aware cache (e.g., `Caffeine.AsyncCache`)
- [ ] HTTP caching (`ResponseEntity` with `Cache-Control`, `ETag`) on read-heavy GET endpoints
- [ ] No DTO mapper iterating lazy associations not declared in the entity graph
- [ ] Response compression enabled (`server.compression.enabled=true`) for JSON responses > 2KB
- [ ] **Response payload right-sizing**: response DTOs do not include fields the client does not need; a `data class` with 25 fields where the UI shows 4 wastes both DB read time and network bandwidth - use a JPA projection interface or a slimmer response `data class`
- [ ] **Negative caching invalidation**: when caching not-found / empty results (`@Cacheable(unless = "#result == null")` is *not* this - it skips caching, the issue is the opposite: `@Cacheable` *with* null caching), any subsequent create of that key must `@CacheEvict` or the cache returns stale "not found". Flag `@Cacheable` paths that cache absence without a paired write-side eviction

### Step 9 - Messaging and Background Work

_Skipped at `quick` depth unless the diff touches `@KafkaListener` / `@RabbitListener` / `@Scheduled` / outbox patterns._

Inspect changes under listener / event packages:

- [ ] Message handlers idempotent (re-fetch state, dedup key, upsert, return early on replay)
- [ ] Consumer concurrency tuned (`spring.kafka.listener.concurrency`); not left at default `1` for high-throughput topics
- [ ] Manual ack mode (`AckMode.MANUAL_IMMEDIATE`) for at-least-once; auto-ack only for fire-and-forget
- [ ] DLT / DLQ configured with explicit retry policy; no infinite-retry loops
- [ ] **Transactional outbox** when DB write + message publish must be atomic (publishing inside `@Transactional` is a smell)
- [ ] `@TransactionalEventListener(phase = AFTER_COMMIT)` for in-process event dispatch
- [ ] Long-running consumers split (single message handle should target sub-30-second median latency)
- [ ] **Coroutine-based listeners**: `suspend` `@KafkaListener` methods (Kotlin coroutines + Spring Kafka) are supported but require explicit testing for backpressure and ack timing

### Step 10 - Observability for Perf

_Skipped at `quick` depth._

- [ ] Slow paths instrumented with Micrometer `@Timed` / custom timers; metrics named under consistent namespace
- [ ] Hibernate statistics enabled in non-prod (`spring.jpa.properties.hibernate.generate_statistics=true`); flag any change disabling them in prod
- [ ] `p6spy` or `datasource-proxy` configured in non-prod for query-count assertions in tests
- [ ] APM span attribution by request - confirm `traceparent` propagation through `@Async`, `CoroutineScope.launch`, and `WebClient` calls
- [ ] **MDC propagation across coroutines**: `MDCContext` from `kotlinx-coroutines-slf4j` (or equivalent) used so trace IDs survive dispatcher switches


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Kotlin / Spring Boot before any specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow)
- [ ] Diff and commit log were read once and reused by all steps
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed
- [ ] When `head_matches_current` was false, explicit user approval was obtained
- [ ] Performance surface (entities, repositories, services, application.yml HikariCP/JPA blocks, migrations, build.gradle.kts plugin block) read directly before applying checklists
- [ ] `kotlin-spring-jpa-performance` consulted; N+1, multi-level N+1, LazyInitializationException risk, fetch strategy, projection use, data class JPA flagged
- [ ] `kotlin-spring-db-migration-safety` consulted for any migration; concurrent index strategy and composite-index leftmost-prefix verified
- [ ] `kotlin-spring-async-processing` and `kotlin-coroutines-spring` consulted for any `@Async` / `suspend` / `Flow` change; `synchronized` pinning checked; Dispatchers vs VTs reviewed; `runBlocking` placement; `GlobalScope` flagged
- [ ] HikariCP pool sizing validated against thread/concurrency model
- [ ] Caching strategy assessed (`@Cacheable`, Caffeine vs Redis); `@Cacheable` on `suspend` flagged
- [ ] Every finding states impact - measured when APM data exists, estimated otherwise
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] `behavioral-principles` loaded as Step 1 before stack detection or any other delegation
- [ ] Depth honored: `quick` ran only Steps 5 + 6; `standard` ran 5-10; `deep` adds capacity guidance
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Kotlin / Spring Boot Performance Review Summary

**Stack Detected:** Kotlin <version> / Spring Boot <version>
**Scope:** Backend (Kotlin/Spring Boot)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [name the Kotlin/Spring/JPA idiom: N+1 via lazy association, missing index, mid-transaction message publish, `synchronized` on Virtual Thread, redundant `Dispatchers.IO`, `data class` JPA entity, `GlobalScope.launch`, etc.]
- **Impact:** [estimated effect or measured]
- **Fix:** [specific Kotlin/Spring/JPA change with code example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: schema] - [one-line action]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- Running state-changing git commands from this workflow
- Reporting issues without naming the Kotlin/Spring/JPA idiom
- Recommending generic backend advice when a Kotlin-specific pattern applies
- Suggesting `FetchType.EAGER` to fix N+1 - moves the problem
- Suggesting caching without invalidation strategy
- Conflating performance review with general code or security review
- Treating message-broker retries as substitute for idempotency
- Recommending `synchronized` blocks in Virtual-Thread-enabled code
- Recommending `withContext(Dispatchers.IO)` around blocking calls when Virtual Threads are enabled
- Recommending `data class` for JPA entities
