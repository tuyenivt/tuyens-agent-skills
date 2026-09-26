---
name: task-spring-review-reliability
description: "Spring Boot reliability review: Resilience4j breakers/retries, timeouts, idempotency, transactional outbox, HikariCP bounds, DLT, graceful degradation."
agent: java-reliability-engineer
metadata:
  category: backend
  tags: [java, spring-boot, reliability, resilience, resilience4j, circuit-breaker, idempotency, outbox, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Reliability Review

Spring-aware reliability review naming Resilience4j, Framework 7 `@Retryable` / Spring Retry, Spring Kafka / RabbitMQ, `@Transactional`, HikariCP, and `RestClient` / `WebClient` idioms directly. Reliability = behavior under failure and saturation: what happens when a dependency is slow or down, load spikes, contention builds, or a process crashes mid-operation.

Stack-specific delegate of `task-code-review-reliability`.

## When to Use

- Spring Boot PR / branch adding or changing an integration point (`RestClient` / `WebClient` / Feign, `@KafkaListener` / `@RabbitListener`, `@Scheduled`)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and exactly-once semantics
- Locking and contention changes: pessimistic locks, optimistic retry, reservation flows
- Hardening after a near-miss; recurring resilience-debt sweep

**Not for:** general Spring review (`task-code-review`), perf optimization (`task-spring-review-perf`), observability wiring (`task-spring-review-observability`), security (`task-spring-review-security`).

## Seam With Adjacent Lenses

- **vs. Perf:** perf tunes HikariCP / executors for throughput; this lens verifies they are bounded and that exhaustion degrades gracefully. A slow query is perf; the untimed query holding a connection until the server reaps it is reliability.
- **vs. Observability:** obs owns the breaker-state metric and the alerting on it; this lens owns the breaker and the fallback existing, being configured to fire, and logging the original failure.
- **vs. core Phase B:** Phase B owns happy-path transaction correctness; this lens owns partial failure, dependency failure, contention, and saturation. Idempotency sits at the seam - the umbrella dedups. A defect that stops the context starting is in scope as an outage; entity/schema drift is Phase B.

## Depth

| Depth      | When                                                                     | Adds                                       |
| ---------- | ------------------------------------------------------------------------ | ------------------------------------------ |
| `standard` | Default                                                                  | -                                          |
| `deep`     | Requested, passed by the parent, or any whole-service sweep               | `Failure-Mode and Blast-Radius Map`        |

At `deep`, trace each dependency's failure path across service boundaries and shared resources (HikariCP, executors, broker, scheduler thread) and name the loop-breaker. On a diff review that means each new or changed dependency; on a sweep, each dependency in the service.

Invocation forms (`/task-spring-review-reliability [<branch>|pr-<N>] [standard|deep] [--base <branch>]`) follow `task-code-review-reliability`.

**Subagent mode** (spawned by `task-spring-review`, or run inline by it when it cannot spawn; any other invocation is standalone): the parent passes the handle's `base_ref` / `head_ref`, `base_sha` / `head_sha`, the diff and commit log already read, `depth`, the stack (with Boot/Java versions and database engine), `round`, and - on round 2+ - `prior_head_sha` and the prior findings for this scope. Step 3, verification, reconciliation, and the report file are the parent's; never re-raise a prior finding the parent passed unless its cited site changed since `prior_head_sha`.

**Whole-service sweep** (resilience-debt pass with no feature branch): entered when Step 3 fails fast on trunk. A sweep reads the checked-out tree, so it runs only when `git rev-parse HEAD` equals `git rev-parse <trunk>` for the trunk the fail-fast named; otherwise print `A sweep reviews the checked-out tree: check out <trunk>, or name a feature branch for a diff review.` and stop. No handle exists: `branch` = `base_ref` = `head_ref` = the trunk name, `base_sha` = `head_sha` = `git rev-parse HEAD`. Run Step 3's round gate, then every step from Step 4 repo-wide at `HEAD` (Step 4's categories read in full), reading "the diff" as "the service" in every step, `deep`'s per-dependency instruction and the Self-Check's N/A rule included. **A sweep runs at `deep`** unless the invocation explicitly passed `standard` - the Map is the deliverable a debt pass exists to produce. Bound the read by exposure: every external client and side-effecting flow first, then listeners and scheduled work, then the rest; state the bound in the Summary's `Coverage` field.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Accept a pre-confirmed stack from a parent and skip detection. Standalone: use skill: `stack-detect`; if not Spring Boot, stop and route the user to `/task-code-review-reliability` (as a subagent, return the mismatch to the parent). Record the database engine (the JDBC driver in the manifest when detection names none) - Steps 5 and 8 name engine-specific settings - and whether `spring.threads.virtual.enabled=true` is set, which Step 8 branches on.

Read the build and deploy files at `git show <head_ref>:<path>` after the round gate, never from the working tree before it - Step 4's `application.yml` and manifest included. Take the Spring Boot version from the build file (Gradle `org.springframework.boot` plugin or version catalog; Maven `spring-boot-starter-parent` or the imported `spring-boot-dependencies` BOM) and the Java version from `java.toolchain` / `<java.version>` / `maven.compiler.release`; `stack-detect` reports neither. Every construct a finding cites as present and every fix recommends must exist and bind on that version - including fixes taken from a composed atomic. Below Boot 4.0, write the row's or the atomic's Boot 3 form; when it has none, say `Boot 3 form not given` rather than emitting the Boot 4 one. Below the Boot 4.0 / Java 21 floor, note it on the Summary's `Stack Detected` line.

### Step 3 - Resolve the Diff and Round

Skip in subagent mode. Use skill: `review-precondition-check` with the invocation's target, any `--base`, and `report_type: review-reliability`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy`). Fail-fast on trunk -> the whole-service sweep; any other fail-fast -> surface it verbatim and stop.

**Round gate (standalone), before any surface read.** `git rev-parse` the handle's refs into `base_sha` / `head_sha`. A sweep has its SHAs already and reads `review-reliability-<trunk>.md` (the writer's filename sanitization) from the repository root as its `prior_checkpoint` - `legacy` on the precondition check's conditions. A valid `prior_checkpoint` with the same `head_sha` and a `depth` the requested one does not exceed (`deep` exceeds `standard`) -> print `No new commits since prior reliability review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; none, or `legacy` -> `round: 1`. Then read `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, and `git log <base_ref>..<head_ref>` once and reuse (a sweep has none).

### Step 4 - Read the Reliability Surface

Read every changed file in these categories in full, plus any unchanged file the diff calls into (a small diff ripples: a new service method calling an unchanged untimed client is a new failure path at the call site). A defect you read, inside the diff or not, is a finding; Step 10 attributes and labels it.

- External clients: `RestClient` / `WebClient` / `RestTemplate` / Feign beans - timeouts, breakers, retries
- `@Service` methods composing multiple downstream calls - timeout budget, partial-failure handling
- `@KafkaListener` / `@RabbitListener` / `@JmsListener` - idempotency, ack mode, error handler, DLT
- `@Scheduled` / `@Async` - overlap and starvation guards, bounded executors, failure isolation
- Locking and contention: `@Lock`, `@Version`, `SELECT ... FOR UPDATE`, reservation and expiry flows
- Side-effecting flows (payment, notification, provisioning, reservation) - idempotency keys, outbox
- Migrations on the write path - rollout shape (Step 9's last row)
- `application.yml` **in full, not just its diff hunks** - config is never "called into", so the ripple rule above cannot reach it: `resilience4j.*`, `spring.datasource.hikari.*`, `spring.kafka.*`, `spring.rabbitmq.listener.*`, `spring.task.execution.*`, **`spring.task.scheduling.pool.size`**, `spring.threads.virtual.enabled`, the global HTTP client timeouts (key per version in Step 5's timeouts row; they apply to the auto-configured `RestClient.Builder`, so a bean with no per-bean timeout may still be bounded), per-client `*.timeout` keys, `management.endpoint.health.group.readiness.*`
- The full dependency manifest (`pom.xml` / `build.gradle`), not just diff adds - it fills the Summary's Resilience Library field and decides which fixes are even available

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns when the surface includes an external client or a fanning-out `@Service`, or where breaker / retry / timeout config belongs - present or missing, since the absence is usually the finding. Use skill: `spring-transaction` when the surface includes `@Transactional`, locking, or a dual write. Use skill: `spring-messaging-patterns` and `backend-idempotency` when the surface includes a broker or a side-effecting flow. Use skill: `spring-async-processing` when it includes `@Async`, `@Scheduled`, or an executor. Use skill: `spring-db-migration-safety` and `ops-backward-compatibility` when it includes a migration.

**Gating skips atomic loads, never checklist rows.** Every row below runs on this skill's own text regardless of which atomics loaded; a row goes N/A only when the surface has nothing matching it.

**Proxy reachability applies to every fix and finding in Steps 5-9.** Resilience4j, `@Retryable`, `@Transactional`, `@Async`, and `@Cacheable` all run through proxies, so a self-invoked, `private`, or `final` method silently skips the advice; when you cannot see the call path, state the assumption in the finding. Enablement is never an assumption: Step 5's inert row settles it. A fix that enables `@EnableResilientMethods` (or `@EnableRetry`) names every `@Retryable` it activates and is recommended only when each retried call is idempotent, excludes 4xx, and runs outside a transaction; otherwise the fix is to remove the annotation or make the call idempotent first. Where `@Retryable` and `@Transactional` sit on the same method, the retry advice is outer in Framework 7, Spring Retry and Resilience4j, so each attempt opens a fresh transaction.

### Step 5 - Timeouts, Retries, Circuit Breakers

**With Resilience4j absent:** on Boot 4, Framework 7 `@Retryable(includes, maxRetries, delay, multiplier, jitter)` under `@EnableResilientMethods`, and `@ConcurrencyLimit` as a per-method bulkhead - but no breaker and no fallback method: the caller catches the final exception; Spring Retry is archived and unmanaged there. On Boot 3, Spring Retry is the BOM-managed option - `@EnableRetry` plus `spring-boot-starter-aop`, `@Retryable(retryFor, maxAttempts)`, `@Backoff(delay, multiplier, random = true)`, `@Recover`, `org.springframework.retry.annotation.@CircuitBreaker(openTimeout, resetTimeout)` - and `@EnableResilientMethods`, `@ConcurrencyLimit`, and `maxRetries` do not exist. Resilience4j on Boot 4 is `resilience4j-spring-boot4` plus `spring-boot-starter-aspectj` (Boot 3: `resilience4j-spring-boot3` plus `spring-boot-starter-aop`). A pattern the classpath lacks means recommending the dependency, never an annotation that will not compile.

- [ ] **Inert on the declared version** - the inert check searches for every enabler, not only the annotation: Framework 7 `@Retryable` / `@ConcurrencyLimit` are live with `@EnableResilientMethods` or a declared `RetryAnnotationBeanPostProcessor` / `ConcurrencyLimitBeanPostProcessor` bean and need no AOP starter; Spring Retry's `@Retryable` needs `@EnableRetry` plus the AOP starter (`spring-boot-starter-aop` on Boot 3, `spring-boot-starter-aspectj` on Boot 4); Resilience4j annotations need that same starter. A search that finds none of a construct's enablers settles it as inert. Also inert: Boot 3 `spring.http.client.*` keys on Boot 4 (binds nothing - `spring.http.clients.*`); a Jackson 2 `ObjectMapper` bean on Boot 4 (Boot uses its own `JsonMapper`); bare `flyway-core` / `liquibase-core` / `spring-kafka` on Boot 4 (no auto-configuration without the starter or module). A finding whose impact or fix assumes the inert construct works is wrong.
- [ ] **Timeouts on every external call** - `RestClient` / `WebClient` / `RestTemplate` beans set explicit connect and read timeouts, per bean or through the global keys: Boot 4 `HttpClientSettings` / `spring.http.clients.connect-timeout` / `read-timeout`; Boot 3.4-3.5 `ClientHttpRequestFactorySettings` (`org.springframework.boot.http.client`) / `spring.http.client.connect-timeout` / `read-timeout`; Boot 3.0-3.3 per bean only (`org.springframework.boot.web.client.ClientHttpRequestFactorySettings`), no global key. A separate response timeout is a Reactor Netty concept, not a blocking-client one. No default-infinite waits.
- [ ] **Query and transaction time bounded** - `@Transactional(timeout = N)` on long reads (it sets the JDBC query timeout), plus the engine-side backstop: Postgres `statement_timeout` and `idle_in_transaction_session_timeout` (unset, a hung external call inside a transaction pins a backend and its row locks indefinitely and blocks vacuum); MySQL `max_execution_time` bounds read-only `SELECT`s only - writes and lock waits need `innodb_lock_wait_timeout` and the JDBC timeout, and `wait_timeout` (8h default) only reaps an idle session, never a running query.
- [ ] **No external I/O inside `@Transactional`** - an HTTP / SDK call inside the transaction holds its HikariCP connection and any row locks for the upstream's tail latency; a dependency slowdown exhausts the pool.
- [ ] **Timeout budget on chained calls** - a request fanning out to multiple downstreams caps total time; a slow first call leaves budget for the rest or fails fast.
- [ ] **Retries bounded and safe** - capped attempts, exponential backoff, jitter. Retry only the transient errors `ops-resiliency` lists (5xx except 501 / 505, timeouts, connection errors, 429 / 408 / 425) - an `includes` as broad as `RestClientException` retries every 4xx; never a non-idempotent operation without an idempotency key. A retry of a call whose transaction already committed is duplication.
- [ ] **Retry amplification** - chained retries share a per-request budget; N services x M retries is not left to multiply. Two retry libraries both active on one call path is its own finding.
- [ ] **Circuit breaker per external dependency, configured to fire** - Resilience4j's defaults require 100 calls before evaluating, and treat a call as slow only past 60s at a 100% rate, so a dependency that is slow but not erroring never opens it. Check `minimumNumberOfCalls`, `failureRateThreshold`, `slowCallDurationThreshold`, `slowCallRateThreshold`, and `waitDurationInOpenState` - and that the values reach the instance: `configs.default` is inherited by every instance that declares no `baseConfig`, but `instances.default` is just an instance named `default` that `@CircuitBreaker(name="tax")` never touches. `@TimeLimiter` is not the timeout for a blocking client - it wraps `CompletableFuture` and reactive returns only, so a `RestClient` needs client-level timeouts.
- [ ] **Bulkhead isolation** - separate executors, a Resilience4j `@Bulkhead`, or `@ConcurrencyLimit` (Boot 4) per downstream so one slow dependency cannot exhaust a pool others share.

### Step 6 - Idempotency and Delivery Semantics

- [ ] **Idempotency keys** on any side effect a caller can safely repeat but the system cannot - money, notifications, provisioning, and stock or capacity reservations, where a duplicate submit decrements twice. Dedup atomic (unique constraint or dedup table), not a read-then-write race; an `Idempotency-Key` the endpoint accepts but no dedup reads counts as absent.
- [ ] **No in-transaction dual write** - `save` + `kafkaTemplate.send` inside one `@Transactional` can commit the DB and lose the publish (or publish and roll back the DB) on crash. A publish or remote call that must happen when the row commits needs the transactional outbox. AFTER_COMMIT fits only best-effort side effects: it loses the send on a crash or a listener exception (swallowed in afterCompletion). A money call whose result must be saved is neither: PENDING row, the call outside any transaction, a completion transaction, and a reconciler.
- [ ] **Consumer idempotency** - at-least-once delivery means handlers re-fetch state, check, and return early on replay. A handler that sends mail or money on every delivery has no replay defense.
- [ ] **Ack discipline** - offsets / acks committed only after successful processing. Spring Kafka's container forces `enable.auto.commit=false` and defaults to `AckMode.BATCH`, which qualifies; flag an explicit `enable-auto-commit: true` or an ack before the work completes - that is at-most-once, silent loss on crash.
- [ ] **Failed messages land somewhere** - ack discipline alone does not decide this; the error handler does. Spring Kafka's `DefaultErrorHandler` defaults to a small burst of immediate retries and then **logs and skips, committing the offset** - bounded, and silently lossy. A poison message needs `@RetryableTopic` or `DeadLetterPublishingRecoverer` so it is retained, not discarded. RabbitMQ: `default-requeue-rejected` defaults to `true`, so with retry off a failing message requeues in a hot loop; enable `spring.rabbitmq.listener.simple.retry` (`max-retries` on Boot 4; Boot 3 `max-attempts`, which counts the first delivery) and bind a dead-letter exchange so the exhausted message is retained. Boot configures no AMQP JSON converter, so a record payload fails at send under `SimpleMessageConverter` without a `JacksonJsonMessageConverter` bean (Boot 3: `Jackson2JsonMessageConverter`).

### Step 7 - Graceful Degradation and Fallbacks

- [ ] **Defined fallback per critical dependency** - cached / default / partial data, or an explicit fail-fast (503) rather than an unbounded wait.
- [ ] **Fallbacks fail closed on writes** - serving cached or default data in place of a failed *read* degrades gracefully; doing it in place of a failed *write* (a reservation, a charge, an authorization) fabricates a success the system will act on.
- [ ] **Fallbacks log the original failure** at WARN with context; no silent swallow that hides degradation until it compounds.
- [ ] **Partial responses** - an optional downstream (recommendations, enrichment) failing degrades the response, not the whole request.
- [ ] **Load shedding / backpressure** - saturation returns 429 / 503 or sheds load rather than queueing unboundedly.

### Step 8 - Resource Exhaustion and Saturation

- [ ] **HikariCP bounded, and bounded against the server** - `maximumPoolSize` set, `connectionTimeout` failing fast (1-3s; the 30s default blocks callers under exhaustion), `maxLifetime` under any proxy or server-side idle reaper. Check the cluster total: `replicas x maximumPoolSize` must fit inside DB `max_connections` minus reserved connections, or the surplus pods fail to connect at all. When the ceiling is not observable, run the check anyway and state the assumption in the finding (`verify: max_connections unknown`), never silently skip it.
- [ ] **Executors bounded and resolved** - any user `Executor` bean - a `ThreadPoolTaskScheduler` included - backs off Boot's `applicationTaskExecutor` unless it is `@Bean(defaultCandidate = false)` (Boot 3.4+) or `spring.task.execution.mode=force` (Boot 3.5+). Once it is backed off, with two or more `TaskExecutor` beans (Boot's `@EnableScheduling` `taskScheduler` counts) and none named `taskExecutor`, unnamed `@Async` runs on a new `SimpleAsyncTaskExecutor` - unbounded, one thread per task. `spring.task.execution.propagate-context` (Boot 4.1) and `TaskDecorator` beans reach only Boot-built executors. With virtual threads on, Boot's executor is a VT-per-task `SimpleAsyncTaskExecutor` that ignores `spring.task.execution.pool.*`: its bound is `spring.task.execution.simple.concurrency-limit`, and the connection pool behind it is what saturates. On platform threads, `@Async` / `spring.task.execution.pool.*` need a max size, a queue capacity, and a stated rejection policy. `queue-capacity: 0` hands off synchronously, so the pool grows straight to `max-size` before rejecting and those threads contend for the connection pool; an unbounded capacity piles work up until heap does.
- [ ] **Scheduler thread pool** - on platform threads `spring.task.scheduling.pool.size` defaults to **1**, so one long `@Scheduled` job monopolizes the only scheduler thread and starves every other scheduled task; raise the pool or give the long job its own executor - on `ThreadPoolTaskScheduler` a periodic task never overlaps *itself* at any pool size. With virtual threads on, the scheduler is `SimpleAsyncTaskScheduler`, which ignores `pool.size`: `fixedRate` and `cron` run each tick on a new thread and overlap themselves when a run outlasts the period; `fixedDelay` does not, but fixed-delay jobs share its single thread, so a long one delays the rest: give it a `ThreadPoolTaskScheduler` (pool > 1) with `spring.task.execution.mode=force`.
- [ ] **`@Scheduled` across replicas** - the same job on N instances runs N times concurrently on the same rows. Only a distributed lock (`ShedLock`) addresses that; `fixedDelay` and an in-process running-flag do not.
- [ ] **Lock contention bounded** - a pessimistic lock with no wait bound queues callers until something else times out. Bound it at the engine (`lock_timeout` on Postgres, `innodb_lock_wait_timeout` on MySQL); a positive `jakarta.persistence.lock.timeout` hint reaches Postgres only on Hibernate 7.2+ (Boot 4.0.1+; read the resolved Hibernate version), which sets `lock_timeout` around the query - older Hibernate, every Boot 3.x included, needs `SET LOCAL lock_timeout` - and MySQL drops it on every version; `NOWAIT` (0) and `SKIP_LOCKED` (-2) work on both. Take multi-row locks in a deterministic order so concurrent callers cannot deadlock. Where deadlock is possible, the caller needs a bounded retry on the serialization failure - this is the one place a retry is the fix rather than the risk.
- [ ] **No unbounded accumulation** - in-memory collections, caches, and buffers that grow with load have a bound or eviction; large payloads streamed, not fully buffered. Rows that accumulate because nothing deletes them count too.

### Step 9 - Recoverability and Consistency Under Failure

Cross-aggregate consistency rule (inlined deliberately): writes that cannot share one transaction need a compensating action or a reconciliation job on partial failure - never a best-effort inline rollback that can itself fail. Prefer one transaction; when impossible, make the second step idempotent and retriable so a re-run converges.

- [ ] **Crash-safety** - a multi-step side effect interrupted mid-way leaves recoverable state (outbox pending, saga compensation, or a safe re-run), not a half-applied change. A side effect that commits externally before the local row exists is unrecoverable by any later sweep, because nothing records that it happened.
- [ ] **Written state is enforced by something** - an expiry, deadline, or status a row carries but no job, query filter, or constraint acts on is decoration. Reserved stock that never expires, a `PENDING` row nothing reconciles, a TTL column no sweeper reads.
- [ ] **Compensation / saga** - cross-aggregate or cross-service writes that cannot be one transaction have a compensating action on partial failure.
- [ ] **Readiness reflects readiness, in both directions.** Too little: Boot's readiness group contains only `readinessState` unless the service adds to it, so by default a pod with an exhausted connection pool keeps taking traffic - a service that cannot serve without its database should say so in `management.endpoint.health.group.readiness.include`. Too much: an optional dependency added to that group drags every replica out of rotation when it degrades, and a Resilience4j breaker indicator is the usual culprit where `registerHealthIndicator` was enabled.
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes.

### Step 10 - Verify and Reconcile

Subagent runs skip this step - the parent verifies and reconciles its merged set once. Standalone runs apply review-finding-verify inline: Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns; the verify table stays internal and its tally fills the Summary. A claim resting on an external service's behaviour the repository cannot show is `_(unverified: <reason>)_`. A sweep has no diff: run the claim-confirmation pass only - no attribution, no de-escalation, no annotation but `_(unverified: <reason>)_` - since de-escalating would strip `[Must]` from the debt a sweep exists to surface.

**Round 2+.** Project every tier of the prior report (the file at `report_path`) into reconcile's parse shape: one `## High-Impact Findings` section; per finding a `### [<Label>] <file:line>` heading from its Label line (no Label line: the bold label opening the block; a trailing `_(carried from round <N>)_` kept as its own group) and the bare `file:line` prefix of its Location line, a `_(pre-existing)_` annotation kept as its own group (verify's combined `_(pre-existing; newly reachable via ...)_` splits into `_(pre-existing)_ _(newly reachable via ...)_`), and its Issue as the `Issue:` line. A prior finding whose path is absent from the name-status is projected with `_(pre-existing)_`, so an `Unverified` or one-hop finding in an untouched file is never closed as `Addressed` without being read. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status list, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D`. On a sweep, or when the prior checkpoint's `base_sha` equals its `head_sha` (an audit, sweep or trunk run), build the comparison table directly - never call reconcile, which would mark every finding in an untouched file `Addressed` - with reconcile's columns and tally line: re-derived -> `Still open`, site read and smell absent -> `Addressed`, file gone or a `[Praise]` row -> `Obsolete`, site not reached -> `Needs re-check`. `Still open` and `Needs re-check` rows carry into their prior tier at their prior label, marked `_(carried from round <N>)_` (`<N>` = the round the finding was first raised; a finding already carrying the group keeps it, never a second), each republishing its prior block with the prior Location annotation kept (it skips verify, so the annotation is not re-derived), and into Next Steps; a finding this round re-derives publishes once. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and publishes as `[Must]` when it was `[Blocker]`, `[High]`, or `[Critical]`, else `[Recommend]`.

### Step 11 - Write Report

**Subagent mode:** write no file. Return exactly `## Findings` (the tier sections and complete finding blocks: Label, Location, Issue, Failure Mode, Blast Radius, and Fix; the parent maps Failure Mode to Impact and Blast Radius to System Risk), then `## Next Steps`, then at `deep` the `Failure-Mode and Blast-Radius Map`, then one trailing line `Not applicable: <steps or rows>` (or `Not applicable: None`), which the parent puts in a Notes bullet. No Summary or `Prior Round Reconciliation`; each Recommendation returns as a `[Delegate]` Next Step.

Standalone: Use skill: `review-report-writer` with `report_type: review-reliability`, `report_body`, `branch` (the handle's `head_short_name`; a sweep's trunk name), `base_ref` / `head_ref` as the handle emitted them (sweep: the trunk name), `base_sha` / `head_sha` and `round` / `prior_head_sha` from Step 3's round gate, `mode: full`, `scope: +rel`, `depth` as run, `stack = java-spring-boot`, and `pr_url` when the request carried a PR URL, else `prior_checkpoint.pr_url` when present. Write the report file, then print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown; never wrap the whole report in a code fence. Every italic line, brace annotation, bracketed placeholder, and enum listing inside the fence is a fill rule addressed to you, not content: act on it, never print it.

**Severity assignment:** High = data loss, corruption (a lost update on a balance or counter included), duplicated side effects, or an outage under a plausible failure - whether the path is bounded or not. A bounded misconfiguration that guarantees an outage (a cluster pool total exceeding `max_connections`, an unbounded retry on a charge, an in-transaction dual write, at-most-once acking) is High, as is a missing timeout budget on a chained path (`ops-resiliency`). Medium = the failure is contained but recovery or degradation is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, a consumer or retry whose duplicate is a recoverable DB write). Low = hardening with no immediate failure path (missing bulkhead, fail-fast where stale data would serve). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the path moves money or provisions an external resource and the fix is a single edit; Low -> `[Recommend]`.

Headings are severity tiers; a finding stays in its tier after verify changes its label. The Label line carries the verified Label (the severity mapping only where verify did not run); Next Steps copies each finding's Label line, never re-derives it. Overall counts tiers. The Label line holds only the label and the carried marker; any other annotation goes on the Location line, which on a sweep carries only `_(unverified: <reason>)_`. Two failure mechanisms that one fix removes are one finding: its Issue names each and the worse sets the tier. Defects that need separate fixes stay separate findings, even in one method.

```markdown
## Spring Boot Reliability Review Summary

- **Stack Detected:** Java <version> / Spring Boot <version> / <database engine> _(append `- below the floor (<Boot 3.x | Java < 21>)` when either is, and `- past OSS end` when the spring.io support table says so)_
- **Resilience Library:** Resilience4j | Spring Framework resilience | Spring Retry | several - <list> | none detected _(append `- declared but not enabled` when Step 5's inert row finds none of a construct's enablers)_
- **Coverage:** <on a diff review, the changed surface plus the unchanged files it calls into; on a sweep, what was read and what was not>
- **Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}   {diff review}
- **Findings verified:** <N> confirmed, <U> unverified, <K> dropped - inline (no diff)   {sweep, instead}
- **Not applicable:** <rows whose surface is absent, grouped by step and named at whichever granularity is honest - a whole step when none of it applies ("Step 6 messaging"), the rows when only some do ("Step 5 external-call rows"); `None`>

## Findings

### High Impact

1. **Label:** [Must] | [Recommend]{ _(carried from round <N>)_}

   **Location:** [file:line; `file#member` when the supplied diff has no hunk headers]{ the verify Annotation verbatim}

   **Issue:** [name the gap: unbounded `RestClient` call, uncapped retry on a non-idempotent charge, in-tx dual write, breaker that cannot fire on slow calls, cluster pool overcommit, unordered multi-row lock, etc.]{ verify: <the unobservable ceiling or setting assumed>}

   **Failure Mode:** [what fails and how: "payment-gateway latency spike blocks request threads until HikariCP exhausts (20/20)"]

   **Blast Radius:** [what else is affected: "all endpoints sharing the pool return 503"]

   **Fix:** [a construct the project has on its Boot version, or an explicit "add this dependency" when it does not]

### Medium Impact

[Same block; numbering continues across tiers]

### Low Impact

[Same block]

_Omit empty sections._

## Recommendations

[Structural resilience improvements not tied to a single finding]

## Prior Round Reconciliation   {round 2+ standalone only}

[table, note line and tally from `review-prior-findings-reconcile`; when Step 10 built it instead, its comparison table]

## Failure-Mode and Blast-Radius Map   {deep only}

A table, one row per dependency and shared resource, not a restatement of the findings above: what fails, the shared resource it propagates through, and the loop-breaker that contains it - or `none`. Its value is the rows with no finding of their own and the resources several findings converge on.

| Dependency / resource | Fails how | Propagates through | Loop-breaker |
| --------------------- | --------- | ------------------ | ------------ |

## Next Steps

1. **[Implement]** [Must] <citation> - [action]
2. **[Delegate]** [Recommend] [scope: platform] - [action]
3. **[Implement]** [Recommend] <citation> - [action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra) independently of the label. Order Must > Recommend. Emit one entry per finding above. Omit if none._
```

## Self-Check

Mark a line N/A when the surface has nothing matching it, and list those steps in the Summary's `Not applicable` field.

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed (or accepted from parent) with database engine and virtual-threads flag; Boot and Java versions read from the build file; every cited construct and fix binds on them
- [ ] Step 3: standalone: `report_type: review-reliability` passed, or the sweep entered on the trunk checkout with its fields assembled; round decided before any surface read, or the stop line printed; diff, name-status, and log read once
- [ ] Step 4: changed files in full, called-into files, config in full, and the full dependency manifest read; proxy reachability considered for every fix, and every `@Retryable` a proposed enablement would activate checked
- [ ] Step 5: inert-on-version constructs; timeouts per version, engine-side time bounds, no in-tx external I/O, retry safety and budget, a breaker configured to actually fire, bulkhead - each fix naming a construct the project has
- [ ] Step 6: idempotency keys, no in-tx dual write (outbox, not AFTER_COMMIT, for a required publish), consumer idempotency, ack discipline, and where failed Kafka and RabbitMQ messages land
- [ ] Step 7: fallback per critical dependency, failing closed on writes; fallbacks log; partial responses; load shedding
- [ ] Step 8: HikariCP bounded including the cluster total; executors bounded and resolved (back-off, unnamed `@Async`); scheduler per the virtual-threads flag and cross-replica scheduling; lock waits bounded and ordered; no unbounded accumulation
- [ ] Step 9: crash-safety, written state actually enforced, cross-aggregate compensation, readiness composition in both directions, migration rollout
- [ ] Step 10: standalone: `review-finding-verify` ran inline (claim-confirmation only on a sweep) and filled the tally; round 2+: prior findings projected and reconciled (sweep or sweep-kind prior: comparison table, no reconcile call); subagent: skipped
- [ ] Step 11: standalone: report written via `review-report-writer` with every field from the round gate, confirmation printed; subagent: findings, Next Steps, any deep-only Map, and the `Not applicable` line returned, no file written
- [ ] Every finding sits in its severity tier, names the failure mode and blast radius (never just the missing pattern), and carries its verified Label
- [ ] Depth honored: `deep` filled the Failure-Mode and Blast-Radius Map

## Avoid

- Reporting a missing pattern without the failure mode ("add a timeout" vs "unbounded call to payment-gateway exhausts HikariCP")
- Approving a circuit breaker on library defaults - it will not open for a dependency that is merely slow
- Overlapping into perf (throughput tuning) or observability (metric and alert wiring) - name the failure-survival gap
- Treating broker retries, or a bounded error handler that discards the message, as a substitute for consumer idempotency and a DLT
- Citing MySQL server variables against a Postgres stack, or the reverse
