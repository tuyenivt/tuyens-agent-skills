---
name: task-kotlin-review-perf
description: Kotlin / Spring Boot performance review: JPA N+1, coroutine dispatchers, Virtual Threads, HikariCP, Flow backpressure, async throughput, caching.
agent: kotlin-performance-engineer
metadata:
  category: backend
  tags: [kotlin, spring-boot, performance, jpa, hibernate, coroutines, virtual-threads, workflow]
  type: workflow
user-invocable: true
---

# Kotlin / Spring Boot Performance Review

## Purpose

Kotlin-aware perf review for JPA / Hibernate, Spring Data, coroutines, Virtual Threads, HikariCP, Spring caching. Findings with measured or estimated impact and concrete fixes using Kotlin 2.0+ / Spring Boot 3.5+. Stack-specific delegate of `task-code-review-perf`.

## When to Use

- Kotlin / Spring Boot PR for performance regressions
- Slow `@RestController` / `@Async` / `CoroutineScope.launch` / batch investigation
- Pre-merge perf pass on JPA queries / fetch graphs / `@Transactional` / `Flow` streaming
- Quarterly N+1 / query-plan / pool-sizing sweep

**Not for:** general review (`task-kotlin-review`), security (`task-kotlin-review-security`), incidents (`/task-oncall-start`), pre-implementation (`task-kotlin-implement`).

## Depth Levels

| Depth      | When                                                | What runs                                          |
| ---------- | --------------------------------------------------- | -------------------------------------------------- |
| `standard` | Default                                             | All steps                                          |
| `deep`     | Profiling-driven (JFR / async-profiler / Micrometer)| All steps + capacity guidance + load-test plan     |

## Invocation

| Invocation                          | Meaning                                       |
| ----------------------------------- | --------------------------------------------- |
| `/task-kotlin-review-perf`          | Current branch vs base                        |
| `/task-kotlin-review-perf <branch>` | `<branch>` vs base (3-dot diff)               |
| `/task-kotlin-review-perf pr-<N>`   | PR head in `pr-<N>`                            |

When invoked as a subagent of `task-kotlin-review` or `task-code-review-perf`, Step 2 skipped and parent's read-once artifacts reused.

## Workflow

### Step 1 - Behavioral principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm stack

Use skill: `stack-detect`. Accept pre-confirmed from parent.

### Step 3 - Resolve diff

Use skill: `review-precondition-check`. Read diff + log once. Skip if parent passed handle.

### Step 4 - Read the perf surface

- Every changed `@Entity` (associations, fetch types, `@EntityGraph`)
- Every changed `@Repository` (derived methods, `@Query`, `Pageable`, projections, `Flow` returns)
- Every changed `@Service` / `@RestController` (suspend boundaries, `Flow`, parallel `coroutineScope { async { } }`)
- `application.yml` for HikariCP / JPA / Kafka concurrency / VT enabled / cache config
- `build.gradle.kts` plugin block
- New Flyway / Liquibase migrations
- Dependency adds (Resilience4j, Caffeine, p6spy, datasource-proxy, Spring Retry)

For each finding, cite a real `file:line`. If the diff is small but the regression lives in unchanged code (new caller exposing existing N+1), read the unchanged file too.

### Step 5 - JPA / Hibernate hotspots

Use skill: `kotlin-spring-jpa-performance`.
Use skill: `kotlin-spring-transaction`.

- [ ] **N+1 in repositories**: association walked after a query without fetch join / `@EntityGraph` / projection (`FetchType.EAGER` is the smell, not the fix)
- [ ] **N+1 in mappers**: extension functions touching lazy associations - fix on repo / service side
- [ ] **`LazyInitializationException` risk**: lazy access outside `@Transactional`
- [ ] **Collection fetch join + `Pageable`**: `HHH90003004` in-memory pagination; same trap for `@EntityGraph` over `Pageable` derived query
- [ ] **`findAll()` without `Pageable`**; `Page<T>` vs `Slice<T>` cost; `existsBy*` over `findBy*() != null`
- [ ] **Streaming large results**: `Stream<T>` with fetch-size hint or `Flow<T>` from `CoroutineCrudRepository`, not `List<T>`
- [ ] **Missing indexes** for `@Query` WHERE / ORDER BY / GROUP BY
- [ ] **`@Transactional` correctness**: `readOnly = true` on read paths; explicit `timeout`; no external I/O inside (route via `AFTER_COMMIT` listener or outbox)
- [ ] **Batch operations**: `saveAll` / `deleteAllInBatch`; `hibernate.jdbc.batch_size`, `order_inserts` / `order_updates`
- [ ] **Entities never returned from controllers** - DTOs / projections only
- [ ] **`data class` JPA entity** - correctness + perf

### Step 6 - Indexes and migrations

Use skill: `kotlin-spring-db-migration-safety` for any migration.

- [ ] Every column in `@Query` WHERE / ORDER BY / GROUP BY backed by an index
- [ ] Composite indexes match leftmost-prefix pattern of queries
- [ ] FKs have indexes (Postgres does not auto-index FKs)
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY` (Postgres); concurrent statement outside a transaction
- [ ] Unique constraints at DB level
- [ ] Partial indexes for boolean/enum filters selecting small subsets
- [ ] No DDL on hot tables in a single migration (expand-then-contract)

### Step 7 - Coroutines, Virtual Threads, async

Use skill: `kotlin-coroutines-spring`.
Use skill: `kotlin-spring-async-processing`.

- [ ] **`synchronized` on Virtual Thread paths** - pins carrier; use `ReentrantLock` or `Mutex`
- [ ] **Virtual Threads wired** - `spring.threads.virtual.enabled=true`; `VirtualThreadPerTaskExecutor` for `@Async`
- [ ] **`Dispatchers.IO` redundant under VTs**; `Dispatchers.Default` only for CPU-bound
- [ ] **`runBlocking` / `GlobalScope.launch` in production** - flag both
- [ ] **`Flow` backpressure**: `buffer`, `conflate`, bounded `flatMapMerge(concurrency = N)`
- [ ] **HikariCP pool sizing** matches thread / concurrency model: `maximumPoolSize` `cores*2` to `cores*4` for OLTP; `connectionTimeout` 1-3s; `maxLifetime` < DB `wait_timeout`; `leakDetectionThreshold: 5000` non-prod (R2DBC sizing differs - document)
- [ ] **HTTP clients** (`WebClient` / `RestClient`) reused as beans with explicit pool + timeout; circuit breakers on flaky deps
- [ ] **No blocking inside `Mono` / `Flux` chains** - `publishOn(Schedulers.boundedElastic())` if unavoidable
- [ ] **`inline` / `@JvmInline value class`** on hot higher-order paths

### Step 8 - Caching

- [ ] Spring Cache for expensive read paths with deterministic key; explicit `unless` for null/empty
- [ ] Caffeine in-process; Redis (Spring Data Redis or Lettuce) for shared
- [ ] **Stampede protection**: Caffeine `refreshAfterWrite` or `LoadingCache` for hot keys
- [ ] Cache invalidation explicit (`@CacheEvict` on writes or TTL with documented staleness budget)
- [ ] **`@Cacheable` on `suspend`**: Spring Cache does not natively support `suspend` returns - flag, recommend caching at a synchronous adapter or use `Caffeine.AsyncCache`
- [ ] HTTP caching (`Cache-Control`, `ETag`) on read-heavy GETs
- [ ] No DTO mapper iterating lazy associations not in the entity graph
- [ ] Response compression for JSON > 2KB
- [ ] **Right-size response payload**: don't include 25 fields when the UI uses 4 - JPA projection or slimmer DTO
- [ ] **Negative caching**: when `@Cacheable` caches null / empty, subsequent create must `@CacheEvict` or the cache returns stale "not found"

### Step 9 - Messaging and background work

Use skill: `kotlin-spring-messaging-patterns`.

- [ ] Message handlers idempotent (re-fetch state, dedup key, upsert, return early on replay)
- [ ] Consumer concurrency tuned (`spring.kafka.listener.concurrency`)
- [ ] Manual ack (`AckMode.MANUAL_IMMEDIATE`) for at-least-once
- [ ] DLT / DLQ with explicit retry policy; no infinite retries
- [ ] **Transactional outbox** when DB + publish must be atomic
- [ ] `@TransactionalEventListener(AFTER_COMMIT)` for in-process dispatch
- [ ] Long-running consumers split (target sub-30s median latency per message)
- [ ] **Coroutine-based listeners**: `suspend @KafkaListener` supported but needs backpressure + ack-timing tests

### Step 10 - Observability for perf

Only the perf-relevant slice. Full instrumentation review lives in `task-kotlin-review-observability`.

- [ ] Slow paths instrumented with Micrometer `@Timed`
- [ ] Hibernate statistics enabled in non-prod; flag changes that disable them in prod
- [ ] `p6spy` / `datasource-proxy` in non-prod for query-count assertions

### Step 11 - Write report

**Subagent carve-out:** when spawned by a parent review (`task-kotlin-review` / `task-code-review-perf`), do **not** call `review-report-writer` - the parent owns the single report and passes no checkpoint fields. Return the findings inline (Output Format below) for the parent to synthesize, and skip the rest of this step.

Standalone: Use skill: `review-report-writer` with `report_type: review-perf`. Print confirmation.

## Output Format

```markdown
## Kotlin / Spring Boot Performance Review Summary

**Stack Detected:** Kotlin <version> / Spring Boot <version>
**Scope:** Backend (Kotlin/Spring Boot)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact
- **Location:** [file:line]
- **Issue:** [Kotlin/Spring/JPA idiom name: N+1 via lazy association, missing index, mid-TX publish, `synchronized` on VT, redundant `Dispatchers.IO`, `data class` JPA, `GlobalScope.launch`, etc.]
- **Impact:** [measured or estimated]
- **Fix:** [specific Kotlin/Spring/JPA change with code]

### Medium Impact / Low Impact / Quick Wins
[Same structure]

_Omit empty sections._

## Recommendations
[Structural improvements not tied to a specific finding]

## Next Steps
1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope] - [one-line action]
3. **[Implement]** [Recommend] file:line - [one-line action]
```

## Self-Check

- [ ] Stack confirmed
- [ ] `review-precondition-check` ran (or handle received)
- [ ] Diff and log read once; reused across steps
- [ ] For `pr-ref`, user-run fetch surfaced and local ref existed
- [ ] When `head_matches_current` was false, user approval obtained
- [ ] Perf surface read directly (entities, repositories, services, HikariCP/JPA config, migrations, plugin block)
- [ ] JPA hotspots checked via `kotlin-spring-jpa-performance`
- [ ] Migration safety checked via `kotlin-spring-db-migration-safety`
- [ ] Coroutine / VT / async checked via `kotlin-coroutines-spring` + `kotlin-spring-async-processing`
- [ ] HikariCP pool sizing validated
- [ ] Caching assessed; `@Cacheable` on suspend flagged
- [ ] Every finding states impact - measured when APM data exists, estimated otherwise
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] `behavioral-principles` loaded as Step 1
- [ ] Depth honored
- [ ] Next Steps with `[Implement]` / `[Delegate]`, ordered Must > Recommend > Question
- [ ] Standalone: report written + confirmation printed. Subagent: findings returned inline, `review-report-writer` not called

## Avoid

- State-changing git from this workflow
- Reporting issues without naming the Kotlin/Spring/JPA idiom
- Generic backend advice when a Kotlin-specific pattern applies
- Suggesting `FetchType.EAGER` to fix N+1 (moves the problem)
- Suggesting caching without invalidation strategy
- Conflating perf review with general code or security review
- Treating broker retries as substitute for idempotency
- Recommending `synchronized` on VT paths
- Recommending `withContext(Dispatchers.IO)` when VTs are enabled
- Recommending `data class` for JPA entities
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
