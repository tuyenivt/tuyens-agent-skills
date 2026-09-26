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

Findings name the Spring idiom and carry measured or estimated impact and a concrete fix.

Stack-specific delegate of `task-code-review-perf`.

## When to Use

- Spring Boot PR / branch for perf regressions
- Slow `@RestController`, `@Async` task, `@Scheduled` job, batch job, or consumer - with or without APM / JFR figures
- Pre-merge pass on JPA queries, repositories, fetch graphs, `@Transactional`
- Quarterly N+1 / query-plan / pool-sizing sweep

**Not for:** general Spring review (`task-code-review`), security (`task-code-review-security`), pre-implementation design (`task-spring-implement`).

## Depth

| Depth      | When                                              | Reading scope                                     | Adds                                        |
| ---------- | ------------------------------------------------- | ------------------------------------------------- | ------------------------------------------- |
| `standard` | Default                                           | Changed hunks plus the files they call into       | -                                           |
| `deep`     | Requested, handed down by `task-spring-review`, or any trunk run | Every touched file (trunk run: the resolved surface) read in full, plus config and migrations repo-wide | `Capacity and Load-Test Plan` section |

At `deep`, use profiling data (JFR / async-profiler / Micrometer) when available. **Ceiling = usable connections / mean hold**, in requests per second, always from the mean of observed durations (request p50 as a floor): Hikari `hikaricp.connections.usage` mean when measured, else query time + lazy-load count x per-query cost + blocking call time, times attempts under an active retry. A p95 hold sizes the queue tail, never the ceiling; a blocking call with no timeout that binds adds a separate worst-case stress line naming the missing timeout. Usable connections = `pods x maximumPoolSize`, capped by DB `max_connections` minus reserved. Every input not measured or observed is a declared assumption; the scaling claim is what has to hold, not the absolute number.

Invocation forms (`/task-spring-review-perf [<branch>|pr-<N>] [standard|deep] [--base <branch>]`) follow `task-code-review-perf`. **Subagent mode** (spawned by `task-spring-review`, or run inline by it when it cannot spawn): the parent passes the handle's refs, `base_sha` / `head_sha`, the diff and commit log, depth, the stack (with Boot/Java versions and database engine), `round`, `prior_head_sha`, and the prior findings for this scope. Steps 2-3 consume those; never re-raise a prior finding the parent passed unless its cited site changed since prior_head_sha.

**Trunk runs.** A standalone request naming a slow entry point enters symptom mode before Step 3, on any branch. A trunk-fail-fast sweep proceeds only when `git symbolic-ref --short HEAD` equals the named trunk; otherwise print the precondition's trunk message and stop. Both run at `deep` against `HEAD`, with `branch` = `base_ref` = `head_ref` = the checked-out branch and `base_sha` = `head_sha` = `git rev-parse HEAD`. Read "the diff" as "the resolved surface" throughout.

- **Symptom mode** - the request names a slow endpoint, job, or consumer; figures (APM, JFR, slow-query log, pool metrics) are optional. The resolved surface is that entry point's call path (controller -> service -> repositories, clients, locks, and the config and migrations of its tables) plus every shared resource the figures implicate (pool, executor, scheduler). Each figure goes in the Summary's `Measured:` slot, mapped to the finding that explains it or to `unexplained`; that finding cites it as measured Impact, and within a tier findings order by how much of the symptom each explains. No round gate, reconciliation, or report file.
- **Whole-service sweep** - no named entry point (quarterly N+1 / query-plan / pool-sizing pass). The resolved surface is the service: Step 4's categories read in full, repo-wide. With no handle, read `review-perf-<sanitized trunk name>.md` from the repository root yourself (writer filename rules; `legacy` on the precondition check's conditions), then apply Step 3's round gate.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Accept a pre-confirmed stack from a parent (`task-spring-review`) and skip detection. Standalone: use skill: `stack-detect`; if not Spring Boot, stop and route the user to `/task-code-review-perf`.

Read the Spring Boot version from the build file (Gradle `org.springframework.boot` plugin or version catalog; Maven `spring-boot-starter-parent` or the imported `spring-boot-dependencies` BOM) and the Java version from `java.toolchain` / `<java.version>` / `maven.compiler.release`; `stack-detect` does not report either. Every construct a finding cites as present and every fix recommends must exist and bind on that version - including fixes taken from a composed atomic. Read the build and deploy files at `git show <head_ref>:<path>` after the round gate, never from the working tree before it. Below Boot 4.0, write the row's or the atomic's Boot 3 form; when it has none, say `Boot 3 form not given` rather than emitting the Boot 4 one.

Record the **database engine** too - Steps 5-7 branch on it. Below the Boot 4.0 / Java 21 floor, mark virtual-thread rows N/A when the runtime cannot have them and note the gap on the Summary's `Stack Detected` line.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` with the invocation's target, any `--base`, and `report_type: review-perf`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy`). Surface any fail-fast verbatim and stop - **except** a trunk fail-fast, which routes to a sweep above. Subagent and symptom-mode runs skip this step.

**Round gate (standalone, before any surface read).** `git rev-parse` the handle's refs into `base_sha` / `head_sha`. A valid `prior_checkpoint` with the same `head_sha`, whose `depth` the requested depth does not exceed (`deep` exceeds `standard`) -> print `No new commits since prior perf review.` and stop. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; none, or `legacy` -> `round: 1`. Then read `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, and `git log <base_ref>..<head_ref>` once and reuse them.

### Step 4 - Read the Performance Surface

Read every changed file in these categories plus any unchanged file the diff calls into (one hop, further only when that hop reaches a repository, an HTTP client, or a lock): a new controller calling an unchanged repo's N+1 `@Query` regresses at the call site. A changed `@Configuration` or `@Bean` hops to every injection point its bean type can resolve into - an executor bean reaches every unnamed `@Async`. Defects in one-hop files are drafted like any other; verification attributes them.

- `@Entity` (associations, fetch types, `@EntityGraph`)
- `@Repository` (derived methods, `@Query`, `Pageable`, projections)
- `@Service` / `@RestController` paths touching repositories or HTTP/broker clients
- `application.yml` keys, at the production profile's values (`application-<prod>.yml` overrides the base file): `spring.datasource.hikari.*`, `spring.jpa.*`, `spring.threads.virtual.enabled`, `spring.task.execution.*`, `spring.task.scheduling.pool.size`, `spring.http.clients.*` (Boot 3.4-3.5: `spring.http.client.*`; below 3.4 no Boot key), broker listener concurrency (`spring.kafka.listener.concurrency`, `spring.rabbitmq.listener.simple.concurrency`), cache config
- Enablement, searched repo-wide: `@EnableScheduling`, `@EnableAsync`, `@EnableCaching`, and every retry enabler the inert check below names
- New migrations under `db/migration/` or `db/changelog/`
- Dependency adds (Resilience4j, Caffeine, p6spy, datasource-proxy)
- Deployment shape: replica count and DB `max_connections` when observable - Step 7's pool check needs both

- [ ] **Inert on the declared version** - the inert check searches for every enabler, not only the annotation: Framework 7 `@Retryable` / `@ConcurrencyLimit` are live with `@EnableResilientMethods` or a declared `RetryAnnotationBeanPostProcessor` / `ConcurrencyLimitBeanPostProcessor` bean; Spring Retry's `@Retryable` needs `@EnableRetry` plus the AOP starter (`spring-boot-starter-aop` on Boot 3, `spring-boot-starter-aspectj` on Boot 4); Resilience4j annotations need that same starter. A search that finds none of a construct's enablers settles it as inert. Also inert: Boot 3 `spring.http.client.*` keys on Boot 4 (binds nothing - `spring.http.clients.*`); a Jackson 2 `ObjectMapper` bean on Boot 4 (Boot uses its own `JsonMapper`); bare `flyway-core` / `liquibase-core` / `spring-kafka` on Boot 4 (no auto-configuration without the starter or module). A finding whose impact or fix assumes the inert construct works is wrong. An inert construct is an in-lens finding only when its intended effect is perf (a timeout or a concurrency limit), else an `### Out of Lens` line. A fix that enables `@EnableResilientMethods` (or `@EnableRetry`) names every `@Retryable` it activates and is recommended only when each retried call is idempotent, excludes 4xx, and runs outside a transaction; otherwise the fix is to remove the annotation or make the call idempotent first.

Also note observability prep: Micrometer timers on slow paths, Hibernate `generate_statistics` restricted to non-prod profiles, APM span propagation through `@Async` / `WebClient`. File each gap as a Low finding.

### Step 5 - JPA / Hibernate Hotspots

Use skill: `spring-jpa-performance` for canonical N+1 / fetch-join / batch-fetching / projection / pagination / dynamic-filter / bulk-write / lost-update patterns. Additional review-context signals:

- [ ] **Serializer / mapper N+1** - Jackson or MapStruct touching unpreloaded lazy associations. Fix at repo (entity graph / fetch join) or projection DTO, not at the mapper.
- [ ] **`Page<T>` vs `Slice<T>` vs cursor** - `Page` issues `count(*)`; for next/prev UIs use `Slice`, for infinite scroll use cursor.
- [ ] **Unbounded query time** - a long read holds its connection for as long as the database lets it run. Bound it at the source (`@Transactional(timeout = N)`, or the JDBC/statement timeout) and at the engine: Postgres `statement_timeout` and `idle_in_transaction_session_timeout`; MySQL `max_execution_time` (its `wait_timeout` only reaps idle connections and never interrupts a running query).
- [ ] **Transaction scope** - no HTTP / broker / external IO inside `@Transactional`; a publish that must happen when the row commits uses the transactional outbox, and `AFTER_COMMIT` fits only best-effort side effects (it loses the send on a crash or listener exception).

(Index coverage for `@Query` `where` / `order by` / `group by` fields: Step 6.)

### Step 6 - Indexes and Migrations

Use skill: `spring-db-migration-safety` when the surface in scope contains migrations - on a sweep that is the migration history, not a diff. The index-coverage rows below run regardless.

- [ ] `where` / `order by` / `group by` columns indexed; composite indexes match leftmost-prefix usage
- [ ] FKs indexed - **Postgres does not auto-index FK columns; InnoDB does**, so this is a Postgres-only finding
- [ ] Large-table index builds avoid a full-table write lock: Postgres `CREATE INDEX CONCURRENTLY` outside a transaction; MySQL `ALGORITHM=INPLACE, LOCK=NONE`
- [ ] Unique constraints at DB level, not only `@Column(unique = true)`
- [ ] Selective filters on a small subset use a partial index (Postgres `WHERE ...`); MySQL has none - use a generated column plus a plain index
- [ ] No DDL on hot tables in a single migration; expand-then-contract

### Step 7 - Concurrency, Virtual Threads, Async

Use skill: `spring-async-processing`.

- [ ] **Virtual threads, if enabled** (`spring.threads.virtual.enabled=true`): Tomcat and Boot's auto-configured executor and scheduler run on virtual threads. Do not recommend enabling VT for CPU-bound services. Enabling it also removes the bounded worker pool, so the connection pool becomes the request path's only admission control - say so when reviewing a PR that turns it on.
- [ ] **`synchronized` on a VT path, JDK < 24** - blocking while holding a monitor pins the carrier, and contended entry blocks it (JEP 491 removed both in JDK 24). Report it where the block is contended or wraps blocking work; an uncontended, non-blocking `synchronized` counter is not a finding. Fix with `ReentrantLock`, `StampedLock`, or `ConcurrentHashMap.compute`.
- [ ] **HikariCP sizing** - "small pool, fast queries" still holds with VT. Size against the database, not the pod: `maximumPoolSize` in the low tens for OLTP, `connectionTimeout` 1-3s, `maxLifetime` under any proxy or DB idle-connection reaper. **Then check the cluster total:** `replicas x maximumPoolSize` must fit inside DB `max_connections` minus superuser and tooling reservations.
- [ ] **Scheduling** - no `@EnableScheduling` anywhere means no `@Scheduled` method runs. With VT off, `spring.task.scheduling.pool.size` defaults to **1**, so one long job delays every other scheduled task; a job that can run for seconds needs a raised pool size or its own scheduler (the executor row applies to that bean). With VT on, `pool.size` is ignored: `fixedRate`/`cron` runs overlap past the interval, and `fixedDelay` jobs share one scheduler thread (fix per `spring-async-processing`).
- [ ] **`@Async` executor resolution** - Any user Executor bean - a ThreadPoolTaskScheduler included - backs off Boot's applicationTaskExecutor unless it is @Bean(defaultCandidate = false) (Boot 3.4+) or spring.task.execution.mode=force (Boot 3.5+). Once it is backed off, with two or more TaskExecutor beans (Boot's @EnableScheduling taskScheduler counts) and none named taskExecutor, unnamed @Async runs on a new SimpleAsyncTaskExecutor - unbounded, one thread per task. spring.task.execution.propagate-context (Boot 4.1) and TaskDecorator beans reach only Boot-built executors. Then check its fit per `spring-async-processing`.
- [ ] **HTTP clients** (`RestClient`, `WebClient`, `RestTemplate`) reused as beans with connect / read timeouts that bind: on the request factory (`HttpClientSettings` on Boot 3.5+, else the factory setters, else `Boot 3 form not given`), or `spring.http.clients.connect-timeout` / `read-timeout` (Boot 3: Step 4's key), which reach only clients built from Boot's injected builders.
- [ ] **Retries** (Framework 7 `@Retryable`, Resilience4j, spring-retry on Boot 3) active on the declared version. Transaction around the retried call: hold += attempts x timeout + retries x backoff. Retry around the transaction (the default order on one bean): each attempt holds its own connection and the backoff holds none. Bulkheads on shared executors.
- [ ] No blocking call inside a reactive chain - wrap it as `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`. `publishOn` does not rescue a blocking call above it.

### Step 8 - Caching and Response Shape

**Caching:**

- [ ] `@Cacheable` with deterministic key; explicit `unless` for nulls/empties
- [ ] Backend fits scope: Caffeine in-process, Redis (Lettuce) shared
- [ ] **Stampede protection** on hot keys - `@Cacheable(sync = true)` (per JVM), or Caffeine `refreshAfterWrite`, which needs a `CacheLoader` bean or the cache fails to build
- [ ] Invalidation explicit (`@CacheEvict` on writes, or TTL with a documented staleness budget)
- [ ] **Negative caching** - cached `Optional.empty()` leaves callers stale after insert; skip caching empties or evict on the write path
- [ ] Self-invocation - a `@Cacheable` method called from inside the same bean bypasses the proxy and never caches

**Response shape:**

- [ ] List endpoints return projection DTOs, not 50-field entities the caller renders 5 of
- [ ] HTTP caching (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GETs
- [ ] `server.compression.enabled=true` for JSON > 2 KB

### Step 9 - Messaging and Background Work

Use skill: `spring-messaging-patterns` when the surface includes a broker.

- [ ] Consumer-side idempotency (re-fetch state, check, return early)
- [ ] Consumer concurrency tuned for throughput, not left at the default of `1`
- [ ] Ack after processing: the container defaults (Kafka `BATCH`, Rabbit `AUTO`) are correct; manual modes only for conditional or mid-method acks
- [ ] DLT / DLQ with bounded retry; no infinite retry on poison messages
- [ ] **Transactional outbox** when DB write + publish must be atomic
- [ ] `@TransactionalEventListener(phase = AFTER_COMMIT)` for in-process dispatch that must not run on rollback
- [ ] Handler time fits the broker bound: Kafka `max-poll-records` x per-record latency inside `max.poll.interval.ms`; RabbitMQ an unacked delivery inside `consumer_timeout`
- [ ] `@Scheduled` jobs: bounded work per run (paged, not `findAll()`), and a run that can outlast its own interval either uses `fixedDelay` or guards against overlap

### Step 10 - Verify Findings

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Standalone runs apply review-finding-verify inline. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation`, and fill `Findings verified:` from its tally.

**Trunk runs** have no diff: run the claim-confirmation pass only (re-read each cited construct at `HEAD`, drop what is not there) and skip attribution and de-escalation (it would empty the report of its debt). Labels come from severity.

**Round 2+ (standalone, after verification).** Project every tier (never `### Out of Lens`) of the prior report at `report_path` into reconcile's parse shape: one `## High-Impact Findings` section and, per prior finding, a `### [<Label>] <file:line>` heading - the label from its Label line (none: the label its tier maps to), the bare `file:line` prefix of its Location, each Location annotation as its own group (`_(pre-existing; newly reachable via ...)_` split into `_(pre-existing)_ _(newly reachable via ...)_`), a prior `_(carried from round <N>)_` kept as its own group - followed by its Issue line as `Issue:`. A prior finding whose path is absent from the name-status is projected with `_(pre-existing)_`, so an `Unverified` or one-hop finding in an untouched file is never closed as `Addressed` without being read. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D`. On a sweep, or when the prior checkpoint's `base_sha` equals its `head_sha` (an audit, sweep or trunk run), build the comparison table directly - never call reconcile, which would mark every finding in an untouched file `Addressed` - with reconcile's columns and tally line: re-derived -> `Still open`, site read and smell absent -> `Addressed`, file gone -> `Obsolete`, site not reached -> `Needs re-check`. A row marked `Addressed` on a change that is inert on the declared version (Step 4) is `Still open`, noted as such; recount the tally after the override.

`Still open` and `Needs re-check` rows are unresolved. One this round re-derived publishes once, at this round's label. One it did not re-derive republishes its prior block in its prior tier at its prior label with the prior Location annotation kept (it skips verify, so the annotation is not re-derived) and `_(carried from round <N>)_` after the label, outside the verify tally, plus a Next Steps entry suffixed `(open since round <N>)`. `<N>` is the round the finding was first raised; a finding that already carries `_(carried from round <N>)_` keeps it (never a second group). A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`.

**Subagent runs skip verification and reconciliation** - the parent does both once.

### Step 11 - Write Report

**Subagent mode:** write no file. Return exactly these, and nothing else:

- `## Findings`, complete finding blocks in the template below, each with its Label line, citation, `Impact`, and - on every `[Must]` - `System Risk`.
- `## Next Steps`.
- At `deep`, the `Capacity and Load-Test Plan` section (the parent's Depth Appendix).
- A single trailing line `Not applicable: <steps>` (or `Not applicable: None`).

**Symptom mode:** emit the report body as the response; no file is written.

**Otherwise:** use skill: `review-report-writer` with `report_type: review-perf` and every field the writer requires - `report_body`, `branch` (the handle's `head_short_name`, or the trunk name on a sweep), `base_ref`, `head_ref`, `base_sha`, `head_sha`, `mode: full`, `round` and `prior_head_sha` from Step 3's round gate, `scope: +perf`, `depth` as resolved, `stack = java-spring-boot`, and `pr_url` when the request carried a PR/MR URL, else `prior_checkpoint.pr_url` when present. Emit the report body, then the writer's confirmation line.

## Output Format

Emit `report_body` as raw Markdown, never inside a code fence; the fence below is display only. Brace annotations `{...}` are authoring notes and never emitted. `_(quick win | structural)_` and the verification annotations are content: emit the chosen value. Atomics loaded by any step feed findings into this template; their own output blocks (`**Engine:**`, `**Stack:**`) are not emitted.

**Severity:** High = a user-facing latency or throughput regression, or resource exhaustion (pool, executor, memory, connection ceiling) that takes something down - on a request path *or* in offline work. Medium = measurable waste that degrades nothing today, or a risk gated on load growth. Low = polish with minor measurable benefit. Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one local edit that changes no behaviour beyond the finding and the surface is one users or a shared resource actually depend on (enabling an annotation or a global property is never that edit); Low -> `[Recommend]`. Each finding's first line is its Label line. Headings are severity tiers; a finding stays in its tier after verify changes its label. The Label line carries the verified Label (the severity mapping only where verify did not run); Next Steps copies each finding's Label line, never re-derives it. Overall counts tiers.

**Lens boundary.** In-lens impact is latency, throughput, or resource exhaustion; any other defect found en route (correctness, data loss, security, failure handling) is one line under `### Out of Lens` after the tiers - untiered, uncounted in Overall, absent from Next Steps. Subagent runs omit them.

```markdown
## Spring Boot Performance Review Summary

- **Stack Detected:** Java <version> / Spring Boot <version> / <database engine>{ - below the floor (<Boot 3.x | Java < 21>)}{ - past OSS end}   {each suffix only when it holds; OSS end per the spring.io support table}
- **Scope:** Backend (Spring Boot)
- **Round:** <N>   {round 2+ only}
- **Measured:** <entry point> - <source and window>   {symptom mode only; one per entry point}
  - <figure, verbatim from the request> -> #<finding number> | unexplained   {one per figure}
- **Overall:** Clean | Issues Found - [<N> High / <N> Medium / <N> Low]   {Clean only when no finding at any tier survived verification}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}   {N + M + U = the published findings that are not carried; trunk runs: `<N> confirmed, <U> unverified, <K> dropped - inline (no diff)`}
- **Not applicable:** <steps with no matching surface, e.g. "Step 6 migrations, Step 9 messaging"; `None`>

## Findings

### High Impact

1. **[Must]**{ _(carried from round <N>)_}

   **Location:** [file:line] [+ the verify annotation: `_(pre-existing)_`, `_(pre-existing; newly reachable via <file:line>)_`, or `_(unverified: <reason>)_`]

   **Issue:** [name the idiom: N+1 via lazy association, missing index, mid-tx HTTP call, etc.]

   **Impact:** [measured "p95 800ms -> 120ms", citing the `Measured:` figure it explains, or "Estimated - adds ~200 queries/request at 100 orders"]

   **System Risk:** [why this is system-level rather than a local slowdown]   {every High-tier finding and every `[Must]`}

   **Fix:** _(quick win | structural)_ [`@EntityGraph`, fetch join, projection DTO, a timeout property that binds on the declared version, etc.]

### Medium Impact

[Same numbered block; numbering continues across tiers]

### Low Impact

[Same numbered block]

### Out of Lens   {standalone only; omit when none}

- file:line - [the defect in one sentence, and the workflow that owns it]   {one per such defect}

{Omit empty tier sections; with no findings at all, `## Findings` holds the line `No performance issues found.`}

## Recommendations

[Structural improvements not tied to a single finding]

## Prior Round Reconciliation   {round 2+ standalone only}

[table, note line and tally from `review-prior-findings-reconcile`; when Step 10 built it instead, its comparison table]

## Capacity and Load-Test Plan   {deep only}

**Assumptions:** [every input not measured or observed, e.g. per-query cost, DB `max_connections`]

**Capacity:** [mean hold -> usable connections -> ceiling, per the Depth section, with replica count in the arithmetic]

**Load-Test Plan:** [scenario, target endpoints, load shape, success criteria, each tied to a finding's `file:line`]

## Next Steps

1. **[Implement]** [Must] <citation> - [action]
2. **[Delegate]** [Recommend] [scope: schema] - [action]
3. **[Implement]** [Recommend] <citation> - [action] (open since round 1)

{Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, schema, load test) independently of the label. Order Must > Recommend. Omit if none.}
```

## Self-Check

Mark a line N/A when the resolved surface (the diff; the service on a sweep; the call path in symptom mode) has no matching construct and list those steps in the Summary's `Not applicable` field (virtual threads off: `Step 7 VT rows (VT off)`). A step with any matching surface is ticked.

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed (or accepted); Boot / Java versions from the build file and DB engine recorded; every cited construct and fix binds on that version
- [ ] Step 3: `report_type: review-perf` passed; round decided from captured SHAs before any surface read (or the stop line printed); diff, name-status, log read once (subagent or symptom mode: skipped; trunk: sweep)
- [ ] Step 4: surface categories, enablement annotations, and deployment shape read; bean-definition hops followed; inert constructs checked; observability gaps filed
- [ ] Step 5: `spring-jpa-performance` consulted; mapper N+1, `Page`/`Slice`, query-time bounds, tx scope checked
- [ ] Step 6: index coverage verified against the detected engine; migration safety checked when one is present
- [ ] Step 7: `spring-async-processing` consulted; VT applicability, pool sizing including `replicas x pool` vs `max_connections`, scheduling enablement and pool, `@Async` executor resolution, HTTP-client timeouts that bind, active retries checked
- [ ] Step 8: stampede protection, invalidation and self-invocation; response shape and HTTP caching verified
- [ ] Step 9: consumer semantics, ack mode, broker time bound, outbox, post-commit, scheduled-job bounds verified
- [ ] Step 10: verify ran inline (claim-confirmation only on a trunk run; skipped as subagent); tally in the Summary form; round 2+: prior report projected and reconciled (sweep or audit-kind prior: comparison table, tally recounted), unresolved rows carried
- [ ] Step 11: subagent: three-part return, plus Capacity at `deep`; symptom mode: body emitted; otherwise: report written via `review-report-writer` with every required field, confirmation printed
- [ ] Every finding states impact (estimates labeled) and sits in its severity tier with one Label line; every High-tier finding and `[Must]` cites system risk; out-of-lens defects sit under `### Out of Lens`
- [ ] Depth honored; `deep` capacity built from the mean hold with assumptions declared; symptom mode mapped every figure
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Avoid

- Reporting issues without naming the Spring idiom ("this is slow" vs "N+1 from lazy `@OneToMany`; add `@EntityGraph`")
- Suggesting `FetchType.EAGER` to fix N+1
- Suggesting caching without an invalidation strategy
- Sizing a connection pool without checking the cluster total against DB `max_connections`
- Citing MySQL variables against a Postgres stack, or Postgres-only DDL against MySQL
- Treating broker retries as a substitute for idempotency
