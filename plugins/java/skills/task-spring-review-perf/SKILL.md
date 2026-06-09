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

Spring-aware perf review naming JPA / Hibernate, Spring Data, Virtual Thread, HikariCP, Spring caching idioms directly. Findings carry measured or estimated impact (latency, throughput, query count, GC pressure) and concrete fixes for Java 21+ / Spring Boot 3.5+.

Stack-specific delegate of `task-code-review-perf`.

## When to Use

- Spring Boot PR / branch for perf regressions
- Slow `@RestController`, `@Async` task, or batch job
- Pre-merge pass on JPA queries, repositories, fetch graphs, `@Transactional`
- Quarterly N+1 / query-plan / pool-sizing sweep

**Not for:** general Spring review (`task-code-review`), security (`task-code-review-security`), incidents (`/task-oncall-start`), pre-implementation design (`task-spring-implement`).

## Depth

| Depth      | When                                                     | Steps Run                       |
| ---------- | -------------------------------------------------------- | ------------------------------- |
| `standard` | Default                                                  | All                             |
| `deep`     | Profiling-driven (JFR / async-profiler / Micrometer)     | All + capacity + load-test plan |

Invocation forms (`/task-spring-review-perf [<branch>|pr-<N>]`) follow `task-code-review-perf`. When invoked as subagent, parent passes the precondition handle plus pre-read diff and commit log; Step 3 is skipped.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If not Spring Boot, stop and route the user to `/task-code-review-perf`. This workflow assumes Java 21+ and Spring Boot 3.5+.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + artifacts pre-passed. Surface any fail-fast verbatim.

### Step 4 - Read the Performance Surface

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into:

- `@Entity` (associations, fetch types, `@EntityGraph`)
- `@Repository` (derived methods, `@Query`, `Pageable`, projections)
- `@Service` / `@RestController` paths touching repositories or HTTP/broker clients
- `application.yml` keys: `spring.datasource.hikari.*`, `spring.jpa.*`, `spring.kafka.listener.concurrency`, `spring.threads.virtual.enabled`, cache config
- New migrations under `db/migration/` or `db/changelog/`
- Dependency adds (Resilience4j, Caffeine, p6spy, datasource-proxy)

A small diff can ripple: a new controller calling an unchanged repo whose `@Query` does N+1 is a regression at the call site. Read the unchanged file.

Also note observability prep: Micrometer timers on slow paths, Hibernate `generate_statistics` non-prod, APM span propagation through `@Async` / `WebClient`. Flag gaps here; do not re-check in a separate step.

### Step 5 - JPA / Hibernate Hotspots

Use skill: `spring-jpa-performance` for canonical N+1 / fetch / projection / batch / pagination / streaming / `existsBy` / LIE patterns. Additional review-context signals:

- [ ] **Serializer / mapper N+1** - Jackson or MapStruct touching unpreloaded lazy associations. Fix at repo (entity graph / fetch join) or projection DTO, not at the mapper.
- [ ] **`Page<T>` vs `Slice<T>` vs cursor** - `Page` issues `count(*)`; for next/prev UIs use `Slice`, for infinite scroll use cursor.
- [ ] **`@Transactional(timeout = N)`** on long reads; untimed queries hold a connection until DB `wait_timeout`.
- [ ] **Transaction scope** - no HTTP / broker / external IO inside `@Transactional`; use `AFTER_COMMIT` or outbox.
- [ ] Missing indexes on any `@Query` `where` / `order by` / `group by` field (defer detail to Step 6).

### Step 6 - Indexes and Migrations

Use skill: `spring-db-migration-safety`.

- [ ] `where` / `order by` / `group by` columns indexed; composite indexes match leftmost-prefix usage
- [ ] FKs indexed (Postgres does not auto-index FKs)
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY` outside a transaction (Postgres)
- [ ] Unique constraints at DB level, not only `@Column(unique = true)`
- [ ] Partial indexes for boolean / enum filters selecting a small subset
- [ ] No DDL on hot tables in a single migration; expand-then-contract

### Step 7 - Concurrency, Virtual Threads, Async

Use skill: `spring-async-processing`.

- [ ] **No `synchronized` on shared state in VT paths** - pins the carrier and defeats the model. Use `ReentrantLock`, `StampedLock`, or `ConcurrentHashMap.compute`.
- [ ] Virtual Threads enabled (`spring.threads.virtual.enabled=true`); Tomcat + `@Async` use `VirtualThreadPerTaskExecutor`.
- [ ] **HikariCP sizing** - "small pool, fast queries" still holds with VT. OLTP baseline: `maximumPoolSize = cores * 2..4`, `connectionTimeout` 1-3s, `maxLifetime` < DB `wait_timeout`, `leakDetectionThreshold: 5000` non-prod.
- [ ] HTTP clients (`RestClient`, `WebClient`, `RestTemplate`) reused as beans with explicit connect / read / response timeouts.
- [ ] Resilience4j circuit breaker on flaky externals; bulkheads on shared executors.
- [ ] No blocking calls inside `Mono`/`Flux` chains without `publishOn(boundedElastic())`.
- [ ] `@Async` only when work is non-trivial; no `@Async` for sub-millisecond tasks.

### Step 8 - Caching and Response Shape

**Caching:**

- [ ] `@Cacheable` with deterministic key; explicit `unless` for nulls/empties
- [ ] Backend fits scope: Caffeine in-process, Redis (Lettuce) shared
- [ ] **Stampede protection** on hot keys - Caffeine `refreshAfterWrite` or `LoadingCache`
- [ ] Invalidation explicit (`@CacheEvict` on writes, or TTL with a documented staleness budget)
- [ ] **Negative caching** - cached `Optional.empty()` leaves callers stale after insert; skip caching empties or evict on the write path

**Response shape:**

- [ ] List endpoints return projection DTOs, not 50-field entities the caller renders 5 of
- [ ] HTTP caching (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GETs
- [ ] `server.compression.enabled=true` for JSON > 2 KB

### Step 9 - Messaging and Background Work

Use skill: `spring-messaging-patterns`.

- [ ] Consumer-side idempotency (re-fetch state, check, return early)
- [ ] Consumer concurrency tuned for throughput, not default `1`
- [ ] Manual ack (`AckMode.MANUAL_IMMEDIATE`) for at-least-once; auto-ack only for fire-and-forget
- [ ] DLT / DLQ with bounded retry; no infinite retry on poison messages
- [ ] **Transactional outbox** when DB write + publish must be atomic
- [ ] `@TransactionalEventListener(phase = AFTER_COMMIT)` for in-process dispatch that must not run on rollback
- [ ] Long-running handlers split so median latency stays well below broker session timeout

### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Write to the report file, then print confirmation.

## Output Format

```markdown
## Spring Boot Performance Review Summary

**Stack Detected:** Java <version> / Spring Boot <version>
**Scope:** Backend (Spring Boot)
**Overall:** Clean | Issues Found - [count: High/Medium/Low]

## Findings

### High Impact
- **Location:** [file:line]
- **Issue:** [name the idiom: N+1 via lazy association, missing index, mid-tx publish, `synchronized` on VT, etc.]
- **Impact:** [measured "p95 800ms -> 120ms" or estimated "adds ~200 queries/request at 100 orders"]
- **Fix:** [`@EntityGraph`, fetch join, projection DTO, post-commit event, etc.]

### Medium Impact
[Same structure]

### Low Impact / Quick Wins
[Same structure]

_Omit empty sections._

## Recommendations

[Structural improvements not tied to a single finding]

## Next Steps

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: schema] - [action]
3. **[Implement]** [Recommend] file:line - [action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, schema, load test). Order Must > Recommend > Question. Omit if none._
```

## Self-Check

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Spring Boot 3.5+ / Java 21+
- [ ] Step 3: precondition check ran (or handle received); diff + log read once
- [ ] Step 4: entities, repos, services, HikariCP/JPA config, migrations, observability prep read
- [ ] Step 5: `spring-jpa-performance` consulted; mapper N+1, `Page`/`Slice`, tx timeout, tx scope checked
- [ ] Step 6: `spring-db-migration-safety` consulted; indexes and concurrent strategy verified
- [ ] Step 7: `spring-async-processing` consulted; VT pinning, HikariCP sizing, HTTP-client reuse checked
- [ ] Step 8: caching invalidation explicit; response shape and HTTP caching verified
- [ ] Step 9: `spring-messaging-patterns` consulted; outbox and post-commit verified
- [ ] Step 10: report written via `review-report-writer`; confirmation printed
- [ ] Every finding states impact (measured or estimated), never "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `standard` ran all; `deep` adds capacity + load-test plan
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Avoid

- Reporting issues without naming the idiom ("this is slow" vs "N+1 from lazy `@OneToMany`; add `@EntityGraph`")
- Generic backend advice when a Spring idiom applies (say "use `@EntityGraph`", not "use eager loading")
- Suggesting `FetchType.EAGER` to fix N+1
- Suggesting caching without an invalidation strategy
- Conflating perf with general review or security
- Treating broker retries as a substitute for idempotency
- Recommending `synchronized` in VT-enabled paths
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
