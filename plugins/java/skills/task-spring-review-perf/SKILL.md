---
name: task-spring-review-perf
description: "Spring Boot perf review: JPA/Hibernate N+1, fetch strategies, Virtual Thread compatibility, connection pool, async throughput, caching."
agent: java-performance-engineer
metadata:
  category: backend
  tags: [java, spring-boot, performance, jpa, hibernate, virtual-threads, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Performance Review

## Purpose

Spring-aware performance review that names JPA/Hibernate, Spring Data, Virtual Thread, HikariCP, and Spring caching idioms directly instead of routing through the generic backend adapter. Produces findings with measured or estimated impact (latency, throughput, query count, GC pressure) and concrete fixes using Java 21+ / Spring Boot 3.5+ patterns.

This workflow is the stack-specific delegate of `task-code-review-perf` for Java / Spring Boot. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a Spring Boot PR or branch for performance regressions
- Investigating a slow `@RestController` action, `@Async` task, or batch job
- Pre-merge perf pass on changes touching JPA queries, repositories, fetch graphs, or `@Transactional` boundaries
- Quarterly N+1 / query-plan / pool-sizing sweep against APM-flagged endpoints

**Not for:**

- General Spring Boot code review (use `task-code-review`)
- Security review (use `task-code-review-security` or its Spring delegate)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-spring-implement`)

## Depth Levels

| Depth      | When to Use                                                         | What Runs                                          |
| ---------- | ------------------------------------------------------------------- | -------------------------------------------------- |
| `quick`    | Single endpoint or repository ("is this query ok?")                 | Steps 5 + 6 only; JPA hotspots + indexes/migration |
| `standard` | Default - full Spring perf review                                   | All steps                                          |
| `deep`     | Profiling-driven review with JFR / async-profiler / Micrometer data | All steps + capacity guidance and load-test plan   |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                          | Meaning                                                                                               |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-spring-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-spring-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-spring-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 3 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Load these rules first - they govern every step including stack detection, scope decisions, and finding generation.

### Step 2 - Confirm Stack

Use skill: `stack-detect` to confirm Java / Spring Boot. If invoked as a delegate of `task-code-review-perf` or as a subagent of `task-spring-review` (parent already detected Spring Boot), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Spring Boot, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Java 21+ and Spring Boot 3.5+ idioms.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 4 - Read the Performance Surface

Before applying the checklists, open the files that govern query and concurrency behavior so impact estimates ground in real code:

- Every changed `@Entity` (associations, fetch types, `@EntityGraph` / `@NamedEntityGraph` declarations)
- Every changed `@Repository` (derived methods, `@Query`, `Pageable` parameters, projection types)
- Every changed `@Service` and `@RestController` that calls a repository or external client
- `application.yml` (and per-profile variants) for `spring.datasource.hikari.*`, `spring.jpa.*`, `spring.kafka.listener.concurrency`, `spring.threads.virtual.enabled`, cache config
- Any new Flyway / Liquibase migration under `src/main/resources/db/migration/` or `db/changelog/`
- `build.gradle(.kts)` / `pom.xml` when the diff adds Resilience4j, Caffeine, p6spy, or datasource-proxy

For each finding produced later, cite a real `file:line`. If the diff is small but ripples through code that is not in the diff (a new controller calling an existing repository whose `@Query` does an N+1), read the unchanged file too - the regression lives there even though the line count attributes it to the new caller.

### Step 5 - JPA / Hibernate Hotspots

Use skill: `spring-jpa-performance` for canonical N+1, fetch-strategy, projection, batch, and pagination patterns. Apply that skill's checks to every changed `@Entity`, `@Repository`, `@Service`, and `@RestController`. Additionally, scan the diff for review-specific signals:

- [ ] **N+1 in serializers / response mappers**: Jackson / MapStruct mappers touching unpreloaded lazy associations - fix at repository (entity graph or fetch join) or use a projection DTO, not at the mapper
- [ ] **`LazyInitializationException` risk**: lazy access after the original `@Transactional` scope ends (controller after service returns, async thread)
- [ ] **Missing indexes for filter/sort**: any `@Query` `where` / `order by` / `group by` field without a backing index in the migration
- [ ] **`Page<T>` vs `Slice<T>` vs cursor**: `Page<T>` issues a second `count(*)` - on large tables with non-trivial filters it can dominate the request. Choose deliberately: `Slice` for next/prev UIs, cursor for infinite scroll
- [ ] **Long-running reads need `@Transactional(timeout = N)`**: untimed queries hold a connection until DB-side `wait_timeout` (often 8h on MySQL, none on PostgreSQL)
- [ ] **Streaming for >10k rows**: batch jobs / exports use `Stream<T>` + `@Transactional(readOnly=true)` + try-with-resources, not `findAll()`
- [ ] **`existsBy*` over `findBy*().isPresent()`**: existence checks compile to `select 1 ... limit 1`
- [ ] **Transaction scope**: no HTTP / broker publish / external I/O inside `@Transactional` (use `AFTER_COMMIT` or outbox)
- [ ] **Entity returns from controllers**: always project to DTO

### Step 6 - Indexes and Migrations

Use skill: `spring-db-migration-safety` for safe-migration checks on any change in `src/main/resources/db/migration/` or `db/changelog/`.

- [ ] Every column referenced in `@Query` `where` / `order by` / `group by` is backed by an index
- [ ] Composite indexes match the leftmost-prefix pattern of the queries
- [ ] Foreign keys have indexes (PostgreSQL does not auto-index FKs)
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL) - Flyway/Liquibase script split so the concurrent statement runs outside a transaction
- [ ] Unique constraints enforced at the database level, not just `@Column(unique = true)` on a non-managed column
- [ ] Partial indexes used for boolean/enum filters that select a small subset
- [ ] No DDL on hot tables in a single migration (expand-then-contract: add column nullable, backfill, switch reads, drop old column in a later release)

### Step 7 - Concurrency, Virtual Threads, and Async

_Skipped at `quick` depth - see Depth Levels above._

Use skill: `spring-async-processing` for `@Async` / Virtual Threads patterns.

Inspect changes touching `@Async`, `TaskExecutor`, `WebFlux`, or `synchronized` blocks:

- [ ] **No `synchronized` on shared instances** in Virtual-Thread-enabled code paths - pinning the carrier thread defeats the model. Replace with `ReentrantLock`, `StampedLock`, or `ConcurrentHashMap.compute`.
- [ ] Virtual Threads enabled where appropriate: `spring.threads.virtual.enabled=true` on Boot 3.2+; servlet container (Tomcat) and `@Async` `TaskExecutor` use a `VirtualThreadPerTaskExecutor`.
- [ ] **HikariCP pool sized correctly**: for Virtual Threads, the rule "small pool, fast queries" still holds - oversizing the pool increases DB contention without adding throughput. Typical: `maximumPoolSize` between `cores x 2` and `cores x 4` for OLTP; `connectionTimeout` 1-3s; `maxLifetime` 30 min (less than DB-side `wait_timeout`).
- [ ] **Connection leak detection** enabled (`leakDetectionThreshold: 5000`) in non-prod
- [ ] No long-blocking I/O inside the controller thread when an `@Async` boundary makes sense - and conversely, no `@Async` for sub-millisecond work (overhead exceeds benefit)
- [ ] HTTP clients (`RestClient`, `WebClient`, `RestTemplate`) reused as beans, not instantiated per call; connection-pool timeouts set explicitly (`connectTimeout`, `readTimeout`, response timeout)
- [ ] Circuit breaker (Resilience4j) on flaky external dependencies; bulkheads on shared executors
- [ ] No blocking calls inside reactive (`Mono`/`Flux`) chains - use `publishOn(Schedulers.boundedElastic())` if blocking is unavoidable

### Step 8 - Caching and Response Performance

_Skipped at `quick` depth unless the diff touches `@Cacheable` / `@CacheEvict` / cache config._

- [ ] Spring Cache (`@Cacheable`) used for expensive read paths with a deterministic key; explicit `unless` for null/empty short-circuits
- [ ] Cache backend chosen for the use case: Caffeine for in-process; Redis (Spring Data Redis or Lettuce) for shared / multi-instance
- [ ] **Cache stampede protection**: hot keys with expensive regeneration use Caffeine `refreshAfterWrite` or a `LoadingCache` so concurrent expiries do not pile up against the source of truth
- [ ] Cache invalidation explicit (`@CacheEvict` on writes, or TTL with documented staleness budget) - no caches that never expire and never invalidate
- [ ] HTTP caching (`ResponseEntity` with `Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GET endpoints
- [ ] No DTO mapper iterating lazy associations not declared in the entity graph
- [ ] Response compression enabled (`server.compression.enabled=true`) for JSON responses > 2KB
- [ ] **Response payload right-sized**: list endpoints that return the full entity (50 fields) when the caller renders 5 fields waste serialization CPU and network bandwidth. Use a projection DTO that selects only what the caller needs - especially when a page returns 50+ rows.
- [ ] **Negative caching is invalidated on writes**: if `@Cacheable` returns `Optional.empty()` and that empty is cached, a subsequent insert of the missing row leaves callers with the stale empty for the TTL. Either set `unless = "#result == null || #result.isEmpty()"` to skip caching empties, or add `@CacheEvict` on the relevant insert path.

### Step 9 - Messaging and Background Work

_Skipped at `quick` depth unless the diff touches `@KafkaListener` / `@RabbitListener` / `@Scheduled` / outbox patterns._

Use skill: `spring-messaging-patterns` for Kafka / RabbitMQ / `ApplicationEvent` patterns.

Inspect changes under `src/main/java/**/listeners/` or `**/events/`:

- [ ] Message handlers idempotent at the consumer side (re-fetch state, check if work was done, return early)
- [ ] Consumer concurrency tuned (`spring.kafka.listener.concurrency`, `simpleRabbitListenerContainerFactory.setConcurrentConsumers`); not left at the default `1` for high-throughput topics
- [ ] Manual ack mode (`AckMode.MANUAL_IMMEDIATE`) for at-least-once semantics; auto-ack only for fire-and-forget
- [ ] DLT / DLQ configured with explicit retry policy; no infinite-retry loops on poison messages
- [ ] **Transactional outbox** used when DB write + message publish must be atomic (publishing inside `@Transactional` is a smell - the message can be sent before commit)
- [ ] `@TransactionalEventListener(phase = AFTER_COMMIT)` for in-process event dispatch when downstream side effects must not run on rollback
- [ ] Long-running consumers split (single message handle should target sub-30-second median latency)

### Step 10 - Observability for Perf

_Skipped at `quick` depth._

- [ ] Slow paths instrumented with Micrometer `@Timed` / custom timers; metrics named under a consistent namespace
- [ ] Hibernate statistics enabled in non-prod (`spring.jpa.properties.hibernate.generate_statistics=true`); flag any change that disables them in prod
- [ ] `p6spy` or `datasource-proxy` configured in non-prod for query-count assertions in tests
- [ ] APM (Datadog / New Relic / Honeycomb) span attribution by request - confirm `traceparent` propagation through `@Async` and `WebClient` calls


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Behavioral principles loaded as Step 1 before any other delegation
- [ ] Stack confirmed as Java / Spring Boot before any Spring-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Performance surface (entities, repositories, services, application.yml HikariCP/JPA blocks, migrations) read directly before applying checklists
- [ ] `spring-jpa-performance` consulted; N+1, multi-level N+1, LazyInitializationException risk, fetch strategy, projection use all checked
- [ ] `spring-db-migration-safety` consulted for any migration change; concurrent index strategy and composite-index leftmost-prefix verified
- [ ] `spring-async-processing` consulted for any `@Async` / Virtual Thread change; `synchronized` pinning checked
- [ ] `spring-messaging-patterns` consulted for any Kafka / Rabbit / event change; outbox and post-commit dispatch verified
- [ ] HikariCP pool sizing validated against thread/concurrency model
- [ ] Caching strategy assessed (`@Cacheable`, Caffeine vs Redis, HTTP caching); invalidation explicit
- [ ] Every finding states impact - measured (`p95: 800ms -> 120ms`) when APM data exists, estimated otherwise (`adds ~N queries per request at K rows`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 5 + 6; `standard` ran 5-10; `deep` adds capacity guidance and load-test plan
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Spring Boot Performance Review Summary

**Stack Detected:** Java <version> / Spring Boot <version>
**Scope:** Backend (Spring Boot)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [what the problem is - name the Spring/JPA idiom: N+1 via lazy association, missing index, mid-transaction message publish, `synchronized` on Virtual Thread, etc.]
- **Impact:** [estimated effect - e.g., "N+1 in OrderController#list adds ~200 queries per request at 100 orders" or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [specific Spring/JPA change with code example - `@EntityGraph`, fetch join, projection DTO, post-commit event, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Enable Hibernate statistics in staging", "Switch OrderController response to projection DTO", "Add Caffeine layer for ProductCatalog reads"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, schema migration, or load-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `@EntityGraph(attributePaths = {\"lineItems\", \"customer\"})` to OrderRepository#findById"]
2. **[Delegate]** [High] [scope: schema] - [one-line action, e.g., "Add concurrent composite index on (tenant_id, created_at) - spawn DB migration subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting issues without naming the Spring/JPA idiom ("this is slow" vs "N+1 from lazy `@OneToMany`; add `@EntityGraph` on the repository method")
- Recommending generic backend advice when a Spring-specific pattern applies (say "use `@EntityGraph`", not "use eager loading")
- Suggesting `FetchType.EAGER` to fix N+1 - it just moves the problem and breaks lazy semantics elsewhere
- Suggesting caching without an invalidation strategy
- Conflating performance review with general code review or security review - delegate those to their workflows
- Treating message-broker retries as a substitute for idempotency - retries with non-idempotent handlers cause double-processing
- Recommending `synchronized` blocks in Virtual-Thread-enabled code paths
