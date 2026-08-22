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

Spring-aware reliability review naming Resilience4j, Spring Retry, Spring Kafka / RabbitMQ, `@Transactional`, HikariCP, and `RestClient` / `WebClient` idioms directly. Reliability = behavior under failure and saturation: what happens when a dependency is slow or down, load spikes, contention builds, or a process crashes mid-operation. Findings name the failure mode and blast radius.

Stack-specific delegate of `task-code-review-reliability`.

## When to Use

- Spring Boot PR / branch adding or changing an integration point (`RestClient` / `WebClient` / Feign, `@KafkaListener` / `@RabbitListener`, `@Scheduled`)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and exactly-once semantics
- Locking and contention changes: pessimistic locks, optimistic retry, reservation flows
- Hardening after a near-miss; recurring resilience-debt sweep

**Not for:** general Spring review (`task-code-review`), perf optimization (`task-spring-review-perf`), observability wiring (`task-spring-review-observability`), security (`task-spring-review-security`).

## Seam With Adjacent Lenses

- **vs. Perf:** perf tunes HikariCP / executors for throughput; this lens verifies they are bounded and that exhaustion degrades gracefully. A slow query is perf; the untimed query holding a connection until the server reaps it is reliability.
- **vs. Observability:** obs owns the breaker-state metric and the fallback log line; this lens owns the breaker and the fallback existing and being configured to fire.
- **vs. core Phase B:** Phase B owns happy-path transaction correctness; this lens owns partial failure, dependency failure, contention, and saturation. Idempotency sits at the seam - the umbrella dedups.

## Depth

| Depth      | When                                                                     | Adds                                       |
| ---------- | ------------------------------------------------------------------------ | ------------------------------------------ |
| `standard` | Default                                                                  | -                                          |
| `deep`     | Requested, handed down by `task-spring-review`, or any whole-service sweep | `Failure-Mode and Blast-Radius Map`        |

At `deep`, trace each dependency's failure path across service boundaries and shared resources (HikariCP, executors, broker, scheduler thread) and name the loop-breaker. On a diff review that means each new or changed dependency; on a sweep, each dependency in the service.

Invocation forms (`/task-spring-review-reliability [<branch>|pr-<N>] [standard|deep] [--base <branch>]`) follow `task-code-review-reliability`. When invoked as subagent, the parent passes the pre-confirmed stack, the precondition handle, pre-read diff and commit log, depth, and round; Steps 2-3 consume those instead of re-running.

**Whole-service sweep** (resilience-debt pass with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run every remaining step, Step 4 onward, repo-wide at `HEAD` (Step 4's categories read in full, not per changed file). Read "the diff" as "the service" in every step below, including `deep`'s per-dependency instruction and the Self-Check's N/A rule. **A sweep runs at `deep`** unless the invocation explicitly passed `standard` - the Map is the deliverable a debt pass exists to produce. Bound the read by exposure: every external client and side-effecting flow first, then listeners and scheduled work, then the rest; state the bound in the Summary's `Coverage` field. `branch` = the current branch name, `base_ref` = `head_ref` = `HEAD`, `base_sha` = `head_sha` = `git rev-parse HEAD` (a resolved SHA, not the literal string).

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Accept a pre-confirmed stack from a parent (`task-spring-review`) and skip detection. Standalone: use skill: `stack-detect`; if not Spring Boot, stop and route the user to `/task-code-review-reliability`. Record the database engine - Step 5 and Step 8 name engine-specific settings.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Once the handle is emitted, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + artifacts pre-passed. Surface any fail-fast verbatim and stop - **except** a trunk fail-fast, which routes to the whole-service sweep above.

**Round gate (standalone only).** Look for `review-reliability-<branch>.md` with `review-report-writer`'s filename sanitization applied to `<branch>`; `review-precondition-check` keys prior checkpoints to `review-<branch>.md`, a different report. Exists with valid frontmatter, `head_sha` equal to the current head, and a `depth` not below the one requested -> print `No new commits since prior reliability review at <sha_short>.` and stop. Otherwise `round = prior.round + 1`, `prior_head_sha = prior.head_sha`; missing or invalid frontmatter means `round: 1`.

**On round 2+, reconcile after Step 10's verification.** `review-prior-findings-reconcile` parses a `## High-Impact Findings` section whose findings are `### [Label] file:line` headings, which is not this lens's shape. Project the prior report into it first - one `### [<label>] <citation>` heading per prior finding, carrying its annotation - then pass the projection as `prior_report` with the diff and name-status list, or with `head_files` alone on the sweep path where neither exists. Insert the returned table under `## Prior Round Reconciliation`.

### Step 4 - Read the Reliability Surface

Read every changed file in these categories plus any unchanged file the diff calls into (a small diff ripples: a new service method calling an unchanged untimed client is a new failure path at the call site):

- External clients: `RestClient` / `WebClient` / `RestTemplate` / Feign beans - timeouts, breakers, retries
- `@Service` methods composing multiple downstream calls - timeout budget, partial-failure handling
- `@KafkaListener` / `@RabbitListener` / `@JmsListener` - idempotency, ack mode, error handler, DLT
- `@Scheduled` / `@Async` - overlap and starvation guards, bounded executors, failure isolation
- Locking and contention: `@Lock`, `@Version`, `SELECT ... FOR UPDATE`, reservation and expiry flows
- Side-effecting flows (payment, notification, provisioning, reservation) - idempotency keys, outbox
- Migrations on the write path - rollout shape (Step 9's last row)
- `application.yml` **in full, not just its diff hunks** - config is never "called into", so the ripple rule above cannot reach it: `resilience4j.*`, `spring.datasource.hikari.*`, `spring.kafka.*`, `spring.task.execution.pool.*`, **`spring.task.scheduling.pool.size`**, `spring.http.client.connect-timeout` / `read-timeout` (Boot 3.4+, applied to the auto-configured `RestClient.Builder`, so a bean with no per-bean timeout may still be bounded), per-client `*.timeout` keys, `management.endpoint.health.group.readiness.*`
- The full dependency manifest (`pom.xml` / `build.gradle`), not just diff adds - it fills the Summary's Resilience Library field and decides which fixes are even available

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns when the surface includes an external client or a fanning-out `@Service`, or where breaker / retry / timeout config belongs - present or missing, since the absence is usually the finding. Use skill: `spring-transaction` when the surface includes `@Transactional`, locking, or a dual write. Use skill: `spring-messaging-patterns` and `backend-idempotency` when the surface includes a broker or a side-effecting flow. Use skill: `spring-async-processing` when it includes `@Async`, `@Scheduled`, or an executor. Use skill: `spring-db-migration-safety` and `ops-backward-compatibility` when it includes a migration.

**Gating skips atomic loads, never checklist rows.** Every row below runs on this skill's own text regardless of which atomics loaded; a row goes N/A only when the surface has nothing matching it.

**Annotation reachability applies to every fix and finding in Steps 5-9.** Spring Retry needs `@EnableRetry` (Boot does not auto-enable it); Resilience4j, `@Transactional`, `@Async`, and `@Cacheable` all run through proxies, so a self-invoked, `private`, or `final` method silently skips the advice. When you cannot see the enabling annotation or the call path, run the check anyway and state the assumption in the finding (`verify: @EnableRetry present`). Where `@Retryable` and `@Transactional` sit on the same method, say which is outer: Spring Retry's advisor has higher precedence by default, so each attempt opens a fresh transaction rather than retrying inside one.

### Step 5 - Timeouts, Retries, Circuit Breakers

Every fix below must name a construct the project actually has. **With Resilience4j absent and Spring Retry present**, the in-classpath equivalents are `@Retryable(retryFor = ..., maxAttempts = ...)`, `@Backoff(delay, multiplier, random = true)` for exponential backoff with jitter, `@Recover` for a fallback, and `org.springframework.retry.annotation.@CircuitBreaker(openTimeout, resetTimeout)` for a breaker. Bulkheads have no Spring Retry equivalent - recommending one means recommending the dependency, so say that explicitly rather than naming an annotation that will not compile.

- [ ] **Timeouts on every external call** - `RestClient` / `WebClient` / `RestTemplate` beans set explicit connect and read timeouts (`ClientHttpRequestFactorySettings`; a separate response timeout is a Reactor Netty concept, not a blocking-client one). No default-infinite waits.
- [ ] **Query and transaction time bounded** - `@Transactional(timeout = N)` on long reads, plus the engine-side backstop: Postgres `statement_timeout` and `idle_in_transaction_session_timeout` (unset, a hung external call inside a transaction pins a backend and its row locks indefinitely and blocks vacuum); MySQL `max_execution_time` (its `wait_timeout` only reaps idle connections and never interrupts a running query).
- [ ] **No external I/O inside `@Transactional`** - an HTTP / SDK call inside the transaction holds its HikariCP connection and any row locks for the upstream's tail latency; a dependency slowdown exhausts the pool.
- [ ] **Timeout budget on chained calls** - a request fanning out to multiple downstreams caps total time; a slow first call leaves budget for the rest or fails fast.
- [ ] **Retries bounded and safe** - capped attempts, exponential backoff, jitter. Retry only transient errors (5xx, timeouts, connection); never 4xx; never a non-idempotent operation without an idempotency key. A retry wrapping a transaction that has already written is not a retry, it is duplication.
- [ ] **Retry amplification** - chained retries share a per-request budget; N services x M retries is not left to multiply. Two retry libraries both active on one call path is its own finding.
- [ ] **Circuit breaker per external dependency, configured to fire** - a breaker with only default config does not protect against the most common outage shape. Resilience4j's defaults require 100 calls before evaluating, and treat a call as slow only past 60s at a 100% rate, so a dependency that is slow but not erroring never opens it. Check `minimumNumberOfCalls`, `failureRateThreshold`, `slowCallDurationThreshold`, `slowCallRateThreshold`, and `waitDurationInOpenState` - and that the values reach the instance: `configs.default` is inherited by every instance that declares no `baseConfig`, but `instances.default` is just an instance named `default` that `@CircuitBreaker(name="tax")` never touches. `@TimeLimiter` is not the timeout for a blocking client - it wraps `CompletableFuture` and reactive returns only, so a `RestClient` needs client-level timeouts.
- [ ] **Bulkhead isolation** - separate executors or a `@Bulkhead` per downstream so one slow dependency cannot exhaust a pool others share.

### Step 6 - Idempotency and Delivery Semantics

- [ ] **Idempotency keys** on any side effect a caller can safely repeat but the system cannot - money, notifications, provisioning, and stock or capacity reservations, where a duplicate submit decrements twice. Dedup atomic (unique constraint or dedup table), not a read-then-write race.
- [ ] **No in-transaction dual write** - `save` + `kafkaTemplate.send` inside one `@Transactional` can commit the DB and lose the publish (or publish and roll back the DB) on crash. Use a transactional outbox or `@TransactionalEventListener(phase = AFTER_COMMIT)`.
- [ ] **Consumer idempotency** - at-least-once delivery means handlers re-fetch state, check, and return early on replay. A handler that sends mail or money on every delivery has no replay defense.
- [ ] **Ack discipline** - offsets / acks committed only after successful processing. Spring Kafka's container forces `enable.auto.commit=false` and defaults to `AckMode.BATCH`, which qualifies; flag an explicit `enable-auto-commit: true` or an ack before the work completes - that is at-most-once, silent loss on crash.
- [ ] **Failed messages land somewhere** - ack discipline alone does not decide this; the error handler does. Spring Kafka's `DefaultErrorHandler` defaults to a small burst of immediate retries and then **logs and skips, committing the offset** - bounded, and silently lossy. A poison message needs `@RetryableTopic` or `DeadLetterPublishingRecoverer` so it is retained, not discarded.

### Step 7 - Graceful Degradation and Fallbacks

- [ ] **Defined fallback per critical dependency** - cached / default / partial data, or an explicit fail-fast (503) rather than an unbounded wait.
- [ ] **Fallbacks fail closed on writes** - serving cached or default data in place of a failed *read* degrades gracefully; doing it in place of a failed *write* (a reservation, a charge, an authorization) fabricates a success the system will act on. A fallback on a side-effecting call must surface the failure, not synthesize a result.
- [ ] **Fallbacks log the original failure** at WARN with context; no silent swallow that hides degradation until it compounds.
- [ ] **Partial responses** - an optional downstream (recommendations, enrichment) failing degrades the response, not the whole request.
- [ ] **Load shedding / backpressure** - saturation returns 429 / 503 or sheds load rather than queueing unboundedly.

### Step 8 - Resource Exhaustion and Saturation

- [ ] **HikariCP bounded, and bounded against the server** - `maximumPoolSize` set, `connectionTimeout` failing fast (1-3s; the 30s default blocks callers under exhaustion), `maxLifetime` under any proxy or server-side idle reaper. Check the cluster total: `replicas x maximumPoolSize` must fit inside DB `max_connections` minus reserved connections, or the surplus pods fail to connect at all. When the ceiling is not observable, run the check anyway and state the assumption in the finding (`verify: max_connections unknown`), never silently skip it.
- [ ] **Executors bounded, and bounded where you think** - `@Async` / `spring.task.execution.pool.*` need a max size, a queue capacity, and a stated rejection policy. `queue-capacity: 0` is not "no queueing at low load": it makes the executor hand off synchronously and grow straight to `max-size` threads before rejecting, so a large max is reached instantly and those threads then contend for the connection pool. An unbounded capacity is the opposite failure - work piles up until heap does.
- [ ] **Scheduler thread pool** - `spring.task.scheduling.pool.size` defaults to **1**, so one long `@Scheduled` job monopolizes the only scheduler thread and starves every other scheduled task in the service. Raise the pool or give the long job its own executor; a periodic task never overlaps *itself* at any pool size, so raising it is safe.
- [ ] **`@Scheduled` across replicas** - the same job on N instances runs N times concurrently on the same rows. Only a distributed lock (`ShedLock`) addresses that; `fixedDelay` and an in-process running-flag do not.
- [ ] **Lock contention bounded** - a pessimistic lock with no wait bound queues callers until something else times out. Bound it at the engine (`lock_timeout` on Postgres, `innodb_lock_wait_timeout` on MySQL); a `jakarta.persistence.lock.timeout` hint only reaches the database on dialects that support a wait clause, and Postgres silently drops a positive value, honouring only `NOWAIT` and `SKIP_LOCKED`. Take multi-row locks in a deterministic order so concurrent callers cannot deadlock. Where deadlock is possible, the caller needs a bounded retry on the serialization failure - this is the one place a retry is the fix rather than the risk.
- [ ] **No unbounded accumulation** - in-memory collections, caches, and buffers that grow with load have a bound or eviction; large payloads streamed, not fully buffered. Rows that accumulate because nothing deletes them count too.

### Step 9 - Recoverability and Consistency Under Failure

Cross-aggregate consistency rule (inlined deliberately): writes that cannot share one transaction need a compensating action or a reconciliation job on partial failure - never a best-effort inline rollback that can itself fail. Prefer one transaction; when impossible, make the second step idempotent and retriable so a re-run converges.

- [ ] **Crash-safety** - a multi-step side effect interrupted mid-way leaves recoverable state (outbox pending, saga compensation, or a safe re-run), not a half-applied change. A side effect that commits externally before the local row exists is unrecoverable by any later sweep, because nothing records that it happened.
- [ ] **Written state is enforced by something** - an expiry, deadline, or status a row carries but no job, query filter, or constraint acts on is decoration. Reserved stock that never expires, a `PENDING` row nothing reconciles, a TTL column no sweeper reads.
- [ ] **Compensation / saga** - cross-aggregate or cross-service writes that cannot be one transaction have a compensating action on partial failure.
- [ ] **Readiness reflects readiness, in both directions.** Too little: Boot's readiness group contains only `readinessState` unless the service adds to it, so by default a pod with an exhausted connection pool keeps taking traffic - a service that cannot serve without its database should say so in `management.endpoint.health.group.readiness.include`. Too much: an optional dependency added to that group drags every replica out of rotation when it degrades, and a Resilience4j breaker indicator is the usual culprit where `registerHealthIndicator` was enabled.
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes.

### Step 10 - Verify Findings

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and inline provenance annotation.

Two carve-outs. **Subagent runs skip this** - the parent verifies the merged set once. **A whole-service sweep has no diff**: run the claim-confirmation pass only and skip attribution and de-escalation, since every finding in a sweep is by definition untouched pre-existing code and de-escalating on that basis would strip `[Must]` from exactly the debt the sweep exists to surface. Record the tally as `inline (no diff)`.

### Step 11 - Write Report

**Subagent mode:** if invoked by `task-spring-review`, do not write a file. Return exactly these, and nothing else:

- `## Findings`, complete finding blocks. Every finding carries its label and citation; every `[Must]` carries the `System Risk` line the parent's report format needs, which for this lens is the Blast Radius restated as a system-level consequence.
- `## Next Steps`, which the parent merges.
- At `deep`, the `Failure-Mode and Blast-Radius Map`, which the parent preserves in its Depth Appendix.
- One trailing line `Not applicable: <steps or rows>` (or `Not applicable: None`) so the parent can tell a clean check from an unrun one - this replaces the Summary field, which subagents do not return.

Do not return the Summary block or `Recommendations`. Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-reliability` and every field the writer requires - `report_body`, `branch`, `base_ref`, `head_ref`, `base_sha`, `head_sha`, `mode: full`, `round` and `prior_head_sha` from Step 3's round gate, `scope: +rel`, `depth` as resolved, `stack = java-spring-boot`. Write the report file, then print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown; never wrap the whole report in a code fence, and never emit the italic parentheticals below, which are fill rules rather than content.

**Severity assignment:** High = data loss, corruption, duplicated side effects, or an outage under a plausible failure - whether the path is bounded or not. A bounded misconfiguration that guarantees an outage (a cluster pool total exceeding `max_connections`, an unbounded retry on a charge, an in-transaction dual write, at-most-once acking) is High. Medium = the failure is contained but recovery or degradation is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, missing timeout budget on a chained path, consumer not idempotent on a non-money path). Low = hardening with no immediate failure path (missing bulkhead, fail-fast where stale data would serve). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is a single edit on a money, provisioning, or shared-resource path; Low -> `[Recommend]`.

```markdown
## Spring Boot Reliability Review Summary

- **Stack Detected:** Java <version> / Spring Boot <version> / <database engine>
- **Resilience Library:** Resilience4j | Spring Retry | both | none detected _(append `- declared but not enabled` when the activating annotation or config is missing)_
- **Coverage:** <on a diff review, the changed surface plus the unchanged files it calls into; on a sweep, what was read and what was not>
- **Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(drop the parenthetical when K is 0; `inline (no diff)` on a sweep)_
- **Not applicable:** <rows whose surface is absent, grouped by step and named at whichever granularity is honest - a whole step when none of it applies ("Step 6 messaging"), the rows when only some do ("Step 5 external-call rows"); `None`>

## Findings

### High Impact

1. **[Must]**

   **Location:** [file:line] _(append `_(pre-existing)_`, `_(unverified: ...)_`, or a `verify: <assumption>` note when one applies; use `file#member` when the supplied diff has no hunk headers)_

   **Issue:** [name the gap: unbounded `RestClient` call, uncapped retry on a non-idempotent charge, in-tx dual write, breaker that cannot fire on slow calls, cluster pool overcommit, unordered multi-row lock, etc.]

   **Failure Mode:** [what fails and how: "payment-gateway latency spike blocks request threads until HikariCP exhausts (20/20)"]

   **Blast Radius:** [what else is affected: "all endpoints sharing the pool return 503"]

   **Fix:** [a construct the project has, or an explicit "add this dependency" when it does not]

### Medium Impact

[Same numbered-block structure, `[Recommend]` unless escalated; numbering continues across tiers]

### Low Impact

[Same numbered-block structure]

_Omit empty sections._

## Recommendations

[Structural resilience improvements not tied to a single finding]

## Prior Round Reconciliation _(round 2+ only)_

[Table returned by `review-prior-findings-reconcile`, plus its tally line]

## Failure-Mode and Blast-Radius Map _(deep only)_

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
- [ ] Step 2: stack confirmed including database engine (or pre-confirmed stack accepted from parent)
- [ ] Step 3: precondition check ran, handle received, or sweep path taken; diff + log read once where one exists; round gate resolved
- [ ] Step 4: external clients, composing services, listeners, scheduled/async, locking, side-effecting flows, resilience/pool/scheduler config, and the full dependency manifest read; annotation reachability considered for every proxy-dependent fix
- [ ] Step 5: timeouts, engine-side time bounds, no in-tx external I/O, retry safety and budget, a breaker configured to actually fire, bulkhead - each fix naming a construct the project has
- [ ] Step 6: idempotency keys, no in-tx dual write, consumer idempotency, ack discipline, and where failed messages land
- [ ] Step 7: fallback per critical dependency, failing closed on writes; fallbacks log; partial responses; load shedding
- [ ] Step 8: HikariCP bounded including the cluster total; executors bounded; scheduler pool and cross-replica scheduling; lock waits bounded and ordered; no unbounded accumulation
- [ ] Step 9: crash-safety, written state actually enforced, cross-aggregate compensation, readiness composition in both directions, migration rollout
- [ ] Step 10: `review-finding-verify` ran with the correct carve-out (skipped as subagent; claim-confirmation only on a sweep); tally recorded
- [ ] Step 11: standalone: report written via `review-report-writer` with every required field, confirmation printed; subagent: findings, Next Steps, and any deep-only Map returned, no file written
- [ ] Every finding names the failure mode and blast radius, never just the missing pattern, and carries exactly one label
- [ ] Depth honored: `deep` filled the Failure-Mode and Blast-Radius Map

## Avoid

- Reporting a missing pattern without the failure mode ("add a timeout" vs "unbounded call to payment-gateway exhausts HikariCP")
- Prescribing a Resilience4j annotation on a project that does not have Resilience4j
- Approving a circuit breaker on library defaults - it will not open for a dependency that is merely slow
- Overlapping into perf (throughput tuning) or observability (metric/log wiring) - name the failure-survival gap
- Recommending retries on non-idempotent ops without an idempotency key
- Treating broker retries, or a bounded error handler that discards the message, as a substitute for consumer idempotency and a DLT
- Approving an in-transaction `save` + `kafkaTemplate.send` dual write
- Citing MySQL server variables against a Postgres stack, or the reverse
