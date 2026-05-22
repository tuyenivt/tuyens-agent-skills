---
name: task-spring-review-perf
description: "Spring Boot perf review: JPA/Hibernate N+1, fetch strategies, Virtual Thread compatibility, HikariCP, async throughput, Spring caching."
agent: java-performance-engineer
metadata:
  category: backend
  tags: [java, spring-boot, performance, jpa, hibernate, virtual-threads, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Performance Review

Spring-aware perf review naming JPA / Hibernate, Spring Data, Virtual Thread, HikariCP, Spring caching idioms directly. Findings include measured or estimated impact (latency, throughput, query count, GC pressure) and concrete fixes using Java 21+ / Spring Boot 3.5+ patterns.

Stack-specific delegate of `task-code-review-perf` for Java / Spring Boot.

## When to Use

- Spring Boot PR / branch for perf regressions
- Slow `@RestController` action, `@Async` task, or batch job
- Pre-merge perf pass on changes to JPA queries, repositories, fetch graphs, `@Transactional`
- Quarterly N+1 / query-plan / pool-sizing sweep against APM-flagged endpoints

**Not for:**
- General Spring review (`task-code-review`)
- Security review (`task-code-review-security` or Spring delegate)
- Incident response (`/task-oncall-start`)
- Pre-implementation design (`task-spring-implement`)

## Depth Levels

| Depth      | When                                                                 | What Runs                                          |
| ---------- | -------------------------------------------------------------------- | -------------------------------------------------- |
| `quick`    | Single endpoint or repository ("is this query ok?")                  | Steps 5 + 6 only - JPA hotspots + indexes          |
| `standard` | Default                                                              | All steps                                          |
| `deep`     | Profiling-driven with JFR / async-profiler / Micrometer data         | All steps + capacity guidance and load-test plan   |

Default: `standard`.

## Invocation

| Invocation                          | Meaning                                                       |
| ----------------------------------- | ------------------------------------------------------------- |
| `/task-spring-review-perf`          | Current branch vs base; fails fast on trunk                   |
| `/task-spring-review-perf <branch>` | `<branch>` vs base (3-dot diff)                               |
| `/task-spring-review-perf pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)         |

When invoked as a subagent, the parent passes the precondition handle + pre-read diff and commit log; Step 3 below is skipped.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from a parent. If not Spring Boot, stop and tell the user to invoke `/task-code-review-perf` - this workflow assumes Java 21+ and Spring Boot 3.5+.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent and the parent passed the handle plus artifacts.

If the precondition check stops with a fail-fast message, surface verbatim and stop. No state-changing git.

### Step 4 - Read the Performance Surface

Before applying checklists:

- Every changed `@Entity` (associations, fetch types, `@EntityGraph`, `@NamedEntityGraph`)
- Every changed `@Repository` (derived methods, `@Query`, `Pageable`, projections)
- Every changed `@Service` / `@RestController` that calls a repository or external client
- `application.yml` for `spring.datasource.hikari.*`, `spring.jpa.*`, `spring.kafka.listener.concurrency`, `spring.threads.virtual.enabled`, cache config
- Any new migration under `src/main/resources/db/migration/` or `db/changelog/`
- `build.gradle(.kts)` / `pom.xml` when Resilience4j, Caffeine, p6spy, or datasource-proxy is added

If the diff is small but ripples through unchanged code (a new controller calling an existing repository whose `@Query` does an N+1), read the unchanged file too - the regression lives there.

### Step 5 - JPA / Hibernate Hotspots

Use skill: `spring-jpa-performance` for canonical N+1 / fetch / projection / batch / pagination patterns. Additional review signals:

- [ ] **N+1 in serializers / mappers** - Jackson / MapStruct touching unpreloaded lazy associations → fix at repository (entity graph or fetch join) or projection DTO, not at the mapper
- [ ] **`LazyInitializationException` risk** - lazy access after the original `@Transactional` scope ends (controller after service returns, async thread)
- [ ] **Missing indexes** - any `@Query` `where` / `order by` / `group by` field without a backing index
- [ ] **`Page<T>` vs `Slice<T>` vs cursor** - `Page<T>` issues a `count(*)` that can dominate large-table requests. Choose deliberately: `Slice` for next/prev UIs, cursor for infinite scroll
- [ ] **Long-running reads need `@Transactional(timeout = N)`** - untimed queries hold a connection until DB-side `wait_timeout` (often 8h on MySQL, none on Postgres)
- [ ] **Streaming for >10k rows** - batch jobs / exports use `Stream<T>` + `@Transactional(readOnly=true)` + try-with-resources, not `findAll()`
- [ ] **`existsBy*` over `findBy*().isPresent()`** - compiles to `select 1 ... limit 1`
- [ ] **Transaction scope** - no HTTP / broker / external IO inside `@Transactional` (use AFTER_COMMIT or outbox)
- [ ] **Entity returns from controllers** - always project to DTO

### Step 6 - Indexes and Migrations

Use skill: `spring-db-migration-safety` for safe-migration checks.

- [ ] Every column in `@Query` `where` / `order by` / `group by` is indexed
- [ ] Composite indexes match leftmost-prefix patterns
- [ ] FKs are indexed (Postgres does not auto-index FKs)
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY` (Postgres) outside a transaction
- [ ] Unique constraints at the DB level, not just `@Column(unique = true)` on a non-managed column
- [ ] Partial indexes for boolean / enum filters selecting a small subset
- [ ] No DDL on hot tables in a single migration (expand-then-contract)

### Step 7 - Concurrency, Virtual Threads, Async

_Skipped at `quick` depth._

Use skill: `spring-async-processing`.

- [ ] **No `synchronized` on shared instances** in VT paths - pinning the carrier defeats the model. Use `ReentrantLock`, `StampedLock`, or `ConcurrentHashMap.compute`
- [ ] Virtual Threads on Boot 3.2+: `spring.threads.virtual.enabled=true`; Tomcat and `@Async` use a `VirtualThreadPerTaskExecutor`
- [ ] **HikariCP sizing** - "small pool, fast queries" still holds with VT. Typical: `maximumPoolSize` `cores x 2` to `cores x 4` for OLTP; `connectionTimeout` 1-3s; `maxLifetime` 30 min (less than DB `wait_timeout`)
- [ ] **Connection leak detection** - `leakDetectionThreshold: 5000` non-prod
- [ ] No long-blocking IO in the controller thread when `@Async` makes sense; conversely no `@Async` for sub-millisecond work
- [ ] HTTP clients (`RestClient`, `WebClient`, `RestTemplate`) reused as beans, not per call; explicit `connectTimeout`, `readTimeout`, response timeout
- [ ] Circuit breaker (Resilience4j) on flaky external dependencies; bulkheads on shared executors
- [ ] No blocking calls inside reactive (`Mono`/`Flux`) chains - use `publishOn(Schedulers.boundedElastic())` if unavoidable

### Step 8 - Caching and Response Performance

_Skipped at `quick` unless the diff touches `@Cacheable` / `@CacheEvict` / cache config._

- [ ] Spring Cache (`@Cacheable`) for expensive reads with a deterministic key; explicit `unless` for null/empty short-circuits
- [ ] Cache backend chosen: Caffeine for in-process; Redis (Spring Data Redis / Lettuce) for shared
- [ ] **Cache stampede protection** - hot keys with expensive regeneration use Caffeine `refreshAfterWrite` or `LoadingCache`
- [ ] Cache invalidation explicit (`@CacheEvict` on writes, or TTL with documented staleness budget)
- [ ] HTTP caching (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GETs
- [ ] No DTO mapper iterating lazy associations not in the entity graph
- [ ] Response compression (`server.compression.enabled=true`) for JSON > 2 KB
- [ ] **Response payload right-sized** - list endpoints returning 50-field entities when the caller renders 5 waste CPU and bandwidth. Use a projection DTO
- [ ] **Negative caching invalidated on writes** - cached `Optional.empty()` leaves callers stale after an insert. Either `unless = "#result == null || #result.isEmpty()"` to skip caching empties, or `@CacheEvict` on the insert path

### Step 9 - Messaging and Background Work

_Skipped at `quick` unless the diff touches `@KafkaListener` / `@RabbitListener` / `@Scheduled` / outbox._

Use skill: `spring-messaging-patterns`.

- [ ] Message handlers idempotent on the consumer side (re-fetch state, check, return early)
- [ ] Consumer concurrency tuned (`spring.kafka.listener.concurrency`, `setConcurrentConsumers`); not default `1` for high-throughput
- [ ] Manual ack (`AckMode.MANUAL_IMMEDIATE`) for at-least-once; auto-ack only for fire-and-forget
- [ ] DLT / DLQ with explicit retry policy; no infinite retry on poison messages
- [ ] **Transactional outbox** when DB write + message publish must be atomic
- [ ] `@TransactionalEventListener(phase = AFTER_COMMIT)` for in-process dispatch when downstream must not run on rollback
- [ ] Long-running consumers split (target sub-30-second median handle latency)

### Step 10 - Observability for Perf

_Skipped at `quick` depth._

- [ ] Slow paths instrumented with Micrometer `@Timed` / custom timers; consistent namespace
- [ ] Hibernate statistics enabled non-prod (`spring.jpa.properties.hibernate.generate_statistics=true`); flag if disabled in prod
- [ ] `p6spy` or `datasource-proxy` non-prod for query-count assertions in tests
- [ ] APM (Datadog / New Relic / Honeycomb) span attribution per request - confirm `traceparent` propagation through `@Async` and `WebClient`

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Write to the report file before ending; print confirmation.

## Self-Check

- [ ] Behavioral principles loaded as Step 1
- [ ] Stack confirmed before Spring-specific checks
- [ ] `review-precondition-check` ran (or handle received); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log read once and reused - no mid-review git re-issuing
- [ ] For `pr-ref` mode, user-run fetch surfaced; local ref existed before continuing
- [ ] When `head_matches_current` was false, explicit user approval obtained (skipped as subagent)
- [ ] Performance surface (entities, repos, services, HikariCP/JPA config, migrations) read before checklists
- [ ] `spring-jpa-performance` consulted; N+1, multi-level N+1, LIE risk, fetch strategy, projections checked
- [ ] `spring-db-migration-safety` consulted for migrations; concurrent index strategy and leftmost-prefix verified
- [ ] `spring-async-processing` consulted for `@Async` / VT; `synchronized` pinning checked
- [ ] `spring-messaging-patterns` consulted for Kafka / Rabbit / event; outbox and post-commit verified
- [ ] HikariCP sizing validated against thread / concurrency model
- [ ] Caching strategy assessed; invalidation explicit
- [ ] Every finding states impact - measured (`p95: 800ms -> 120ms`) when APM data exists, estimated otherwise (`adds ~N queries per request at K rows`) - never "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 5 + 6; `standard` ran 5-10; `deep` adds capacity + load-test plan
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered High > Medium > Low (omit if none)
- [ ] Report written via `review-report-writer`; confirmation printed

## Output Format

```markdown
## Spring Boot Performance Review Summary

**Stack Detected:** Java <version> / Spring Boot <version>
**Scope:** Backend (Spring Boot)
**Overall:** Clean | Issues Found - [count: High/Medium/Low]

## Findings

### High Impact
- **Location:** [file:line]
- **Issue:** [name the JPA/Spring idiom: N+1 via lazy association, missing index, mid-tx message publish, `synchronized` on VT, etc.]
- **Impact:** [estimated: "N+1 in OrderController#list adds ~200 queries per request at 100 orders" or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [`@EntityGraph`, fetch join, projection, post-commit event, etc.]

### Medium Impact
[Same structure]

### Low Impact / Quick Wins
[Same structure]

_Omit empty sections._

## Recommendations

[Structural improvements not tied to a specific finding]

## Next Steps

Prioritized, each tagged `[Implement]` (localized) or `[Delegate]` (cross-cutting refactor, schema migration, load test). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: schema] - [one-line action]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git from this workflow
- Reporting issues without naming the idiom ("this is slow" vs "N+1 from lazy `@OneToMany`; add `@EntityGraph`")
- Generic backend advice when a Spring-specific pattern applies (say "use `@EntityGraph`", not "use eager loading")
- Suggesting `FetchType.EAGER` to fix N+1
- Suggesting caching without an invalidation strategy
- Conflating perf with general review or security
- Treating broker retries as a substitute for idempotency
- Recommending `synchronized` in VT-enabled paths
