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

Spring-aware reliability review naming Resilience4j, Spring Retry, Spring Kafka / RabbitMQ, `@Transactional`, HikariCP, and `RestClient` / `WebClient` idioms directly. Reliability = behavior under failure and saturation: what happens when a dependency is slow or down, load spikes, or a process crashes mid-operation. Findings name the failure mode and blast radius, with concrete fixes for Java 21+ / Spring Boot 3.5+.

Stack-specific delegate of `task-code-review-reliability`.

## When to Use

- Spring Boot PR / branch adding or changing an integration point (`RestClient` / `WebClient` / Feign, `@KafkaListener` / `@RabbitListener`, `@Scheduled`)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and exactly-once semantics
- Hardening after a near-miss; recurring resilience-debt sweep
- Dual-write / outbox / consumer-retry correctness under failure

**Not for:** general Spring review (`task-code-review`), perf optimization (`task-spring-review-perf`), observability wiring (`task-spring-review-observability`), security (`task-spring-review-security`), a live incident (`/task-oncall-start` - mitigate first).

## Seam With Adjacent Lenses

- **vs. Perf:** perf tunes HikariCP / executors for throughput; this lens verifies they are bounded and that exhaustion degrades gracefully. A slow query is perf; the untimed query holding a connection until `wait_timeout` is reliability.
- **vs. Observability:** obs owns the breaker-state metric and the fallback log line; this lens owns the breaker and the fallback existing and being configured.
- **vs. core Phase B:** Phase B owns happy-path transaction correctness; this lens owns partial failure, dependency failure, and saturation. Idempotency sits at the seam - the umbrella dedups.

## Depth

| Depth      | When                                                        | Steps Run                                       |
| ---------- | ----------------------------------------------------------- | ----------------------------------------------- |
| `standard` | Default                                                     | All except the Failure-Mode Map                 |
| `deep`     | Requested, or handed down by `task-spring-review`           | All + `Failure-Mode and Blast-Radius Map`       |

At `deep`, trace each new or changed dependency's failure path across service boundaries and shared resources (HikariCP, executors, broker) and name the loop-breaker.

Invocation forms (`/task-spring-review-reliability [<branch>|pr-<N>] [standard|deep] [--base <branch>]`) follow `task-code-review-reliability`. When invoked as subagent, parent passes the pre-confirmed stack, the precondition handle, and pre-read diff and commit log; Steps 2-3 consume those instead of re-running.

**Whole-service sweep** (resilience-debt pass with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-10 repo-wide at `HEAD` (Step 4's categories read in full, not per changed file); findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Accept a pre-confirmed stack from a parent (`task-spring-review`) and skip detection. Standalone: use skill: `stack-detect`; if not Spring Boot, stop and route the user to `/task-code-review-reliability`. This workflow assumes Java 21+ and Spring Boot 3.5+.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Once the handle is emitted, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + artifacts pre-passed. Surface any fail-fast verbatim.

### Step 4 - Read the Reliability Surface

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (a small diff ripples: a new service method calling an unchanged untimed client is a new failure path at the call site):

- External clients: `RestClient` / `WebClient` / `RestTemplate` / Feign beans - timeouts, breakers, retries
- `@Service` methods composing multiple downstream calls - timeout budget, partial-failure handling
- `@KafkaListener` / `@RabbitListener` / `@JmsListener` - idempotency, ack mode, DLT, retry
- `@Scheduled` / `@Async` - overlap guards, bounded executors, failure isolation
- Side-effecting flows (payment, notification, provisioning) - idempotency keys, outbox
- `application.yml`: `resilience4j.*`, `spring.datasource.hikari.*`, `spring.kafka.*`, `spring.task.execution.pool.*`, `*.timeout` keys
- Dependency adds: `resilience4j-spring-boot3`, `spring-retry`, outbox libraries

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns - load it when the surface includes an external client (`RestClient` / `WebClient` / Feign), a fanning-out `@Service`, or breaker / retry / timeout config; skip it on a diff that is purely Spring-async / messaging-idempotency, `@Transactional`, or locking work with no synchronous dependency.

Read the full dependency manifest (`pom.xml` / `build.gradle`) here, not just diff adds, to fill the Summary's Resilience Library field (Resilience4j / Spring Retry detection).

**Gating vs. checklist:** gating skips atomic loads, never checklist rows. Every checklist row below runs on this skill's own text regardless of which atomics loaded; a row goes N/A only when the diff has no matching surface (the Self-Check rule).

### Step 5 - Timeouts, Retries, Circuit Breakers

Use skill: `spring-async-processing` for executor and non-blocking concerns.

- [ ] **Timeouts on every external call** - `RestClient` / `WebClient` / `RestTemplate` beans set explicit connect + read + response timeouts; no default-infinite waits. `@Transactional(timeout = N)` on long reads so a query cannot hold a connection until DB `wait_timeout`.
- [ ] **No external I/O inside `@Transactional`** - an HTTP / SDK call inside the transaction holds its HikariCP connection (and any row locks) for the upstream's tail latency; a dependency slowdown exhausts the pool. Move the call outside the boundary or split the transaction.
- [ ] **Timeout budget on chained calls** - a request fanning out to multiple downstreams caps total time; a slow first call leaves budget for the rest or fails fast.
- [ ] **Retries bounded and safe** - Resilience4j `@Retry` / Spring `@Retryable` with capped `maxAttempts`, exponential backoff, and jitter. Retry only transient errors (5xx, timeouts, connection); never 4xx; never non-idempotent ops without an idempotency key.
- [ ] **Retry amplification** - chained retries share a per-request budget; N services x M retries is not left to multiply.
- [ ] **Circuit breaker per external dependency** - Resilience4j `@CircuitBreaker` with explicit failure-rate threshold, wait duration, and half-open probes; state is metered (visibility gap -> `task-spring-review-observability`). A shared or unmonitored breaker counts as missing.
- [ ] **Bulkhead isolation** - Resilience4j `@Bulkhead` or separate executors per downstream so one slow dependency cannot exhaust the pool others share.

### Step 6 - Idempotency and Delivery Semantics

Use skill: `spring-messaging-patterns`. Use skill: `backend-idempotency` for key strategy and atomic dedup.

- [ ] **Idempotency keys** on money / notification / provisioning side effects; dedup atomic (unique constraint or dedup table), not a read-then-write race.
- [ ] **No in-transaction dual write** - `save` + `kafkaTemplate.send` inside one `@Transactional` can commit the DB and lose the publish (or vice versa) on crash. Use a transactional outbox or `@TransactionalEventListener(phase = AFTER_COMMIT)`.
- [ ] **Consumer idempotency** - at-least-once delivery means handlers re-fetch state, check, and return early on replay.
- [ ] **Ack discipline** - offsets / acks committed only after successful processing. Spring Kafka's container defaults (`enable.auto.commit=false` + `AckMode.BATCH` / `RECORD`) qualify, as does `MANUAL_IMMEDIATE`; flag `enable.auto.commit=true` or acking before the work completes - that is at-most-once, silent loss on crash.
- [ ] **DLT / DLQ with bounded retry** - poison messages route to a dead-letter topic after capped attempts (`@RetryableTopic`, or `DefaultErrorHandler` + `DeadLetterPublishingRecoverer`); no infinite in-place retry.

### Step 7 - Graceful Degradation and Fallbacks

- [ ] **Defined fallback per critical dependency** - Resilience4j `fallbackMethod` returning cached / default / partial data, or an explicit fail-fast (503) rather than an unbounded wait.
- [ ] **Fallbacks log the original failure** at WARN with context; no silent swallow that hides degradation until it compounds.
- [ ] **Partial responses** - an optional downstream (recommendations, enrichment) failing degrades the response, not the whole request.
- [ ] **Load shedding / backpressure** - saturation returns 429 / 503 or sheds load rather than queueing unboundedly.

### Step 8 - Resource Exhaustion and Saturation

- [ ] **HikariCP bounded** - `maximumPoolSize` set and `< DB wait_timeout` on `maxLifetime`; `connectionTimeout` fails fast (1-3s) rather than blocking the caller indefinitely under exhaustion. When the ceiling (DB `max_connections`, deployed instance count x pool size) is not in the diff, read repo config; still unknown -> run the check anyway and state the assumption in the finding (e.g. `verify: max_connections unknown`), never silently skip it.
- [ ] **Executors bounded** - `@Async` / `spring.task.execution.pool.*` have a max size and a bounded queue with a defined rejection policy; no unbounded `queueCapacity`.
- [ ] **No unbounded accumulation** - in-memory collections, caches, and buffers that grow with load have a bound or eviction; large payloads streamed, not fully buffered.
- [ ] **`@Scheduled` overlap** - long jobs guard against overlapping runs (`ShedLock`, `fixedDelay`, or a running-flag) so a slow run does not stack.

### Step 9 - Recoverability and Consistency Under Failure

Cross-aggregate consistency rule (inlined on purpose - do not re-delegate this to a separate consistency atomic; it overlaps the transaction atomic already loaded here, and its one distinct rule is captured below): writes that cannot share one transaction (a charge + a separate provisioning record, a local write + a remote call) need a compensating action or a reconciliation job on partial failure - never a best-effort inline rollback that can itself fail. Prefer one transaction; when impossible, make the second step idempotent and retriable so a re-run converges. Use skill: `spring-transaction` for boundary correctness.

- [ ] **Crash-safety** - a multi-step side effect interrupted mid-way leaves recoverable state (outbox pending, saga compensation, or a safe re-run), not a half-applied change.
- [ ] **Compensation / saga** - cross-aggregate or cross-service writes that cannot be one transaction have a compensating action on partial failure.
- [ ] **Health probes reflect readiness** - readiness gates on the dependencies the service needs to serve, so an unready instance sheds rather than accepts traffic it cannot handle (probe wiring depth -> `task-spring-review-observability`).
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes (use skill: `spring-db-migration-safety`, `ops-backward-compatibility`).

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary. Subagent runs skip this - the parent verifies the merged set once.

### Step 10 - Write Report

**Subagent mode:** if invoked by `task-spring-review`, do not write a file - return the findings in this skill's Output Format for the parent to merge (the parent owns the report; `review-report-writer` rejects subagent writes). At `deep`, include the Failure-Mode and Blast-Radius Map with the returned findings - the parent preserves it as its own section. Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-reliability`. Assemble every checkpoint field the writer requires: `scope: +rel`, `depth` as invoked, `stack = java-spring-boot`, `base_sha` / `head_sha` via `git rev-parse` on the handle's refs (whole-service sweep: both = `HEAD`), and `mode: full`, `round: 1` - unless `review-reliability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha` (check for that file yourself; `review-precondition-check` looks up `review-<branch>.md`, a different report). Write to the report file, then print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unbounded failure path or data-loss / corruption risk under a plausible failure (missing timeout on a hot external call, uncapped retry, non-idempotent retry, in-tx dual write, unbounded queue on a hot path); Medium = failure is bounded but recovery or containment is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, missing timeout / retry budget on a chained path, consumer not idempotent); Low = hardening with no immediate failure path (missing bulkhead, fail-fast where stale data would serve). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on a critical path; Low -> `[Recommend]`.

```markdown
## Spring Boot Reliability Review Summary

**Stack Detected:** Java <version> / Spring Boot <version>
**Resilience Library:** Resilience4j | Spring Retry | none detected
**Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line]
   **Issue:** [name the gap: unbounded `RestClient` call, uncapped `@Retry`, in-tx dual write, unbounded `@Async` queue, non-idempotent listener, etc.]
   **Failure Mode:** [what fails and how: "payment-gateway latency spike blocks request threads until HikariCP exhausts (40/40)"]
   **Blast Radius:** [what else is affected: "all endpoints sharing the pool return 503"]
   **Fix:** [`@CircuitBreaker` + `fallbackMethod`, outbox, bounded executor, idempotency key, etc.]

### Medium Impact
[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins
[Same numbered-block structure]

_Omit empty sections._

## Recommendations

[Structural resilience improvements not tied to a single finding]

## Failure-Mode and Blast-Radius Map

_(`deep` only - omit at `standard`.)_
Per new / changed dependency: **what happens when it is down or slow**, the shared resource on the propagation path, and the loop-breaker that contains it (breaker, retry budget, load shedding).

## Next Steps

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: platform] - [action]
3. **[Implement]** [Recommend] file:line - [action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra). Order Must > Recommend. Omit if none._
```

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no messaging, no scheduled jobs).

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Spring Boot 3.5+ / Java 21+ (or pre-confirmed stack accepted from parent)
- [ ] Step 3: precondition check ran (or handle received); diff + log read once
- [ ] Step 4: external clients, composing services, listeners, scheduled/async, side-effecting flows, resilience/pool config read; full `pom.xml` / `build.gradle` read for the Resilience Library field
- [ ] Step 5: `ops-resiliency` consulted when the gate loaded it; timeouts, no in-tx external I/O, retry safety/budget, breaker, bulkhead checked
- [ ] Step 6: `backend-idempotency` + `spring-messaging-patterns` consulted; idempotency keys, no in-tx dual write, consumer idempotency, ack, DLT checked
- [ ] Step 7: fallback per critical dependency; fallbacks log; partial responses; load shedding verified
- [ ] Step 8: HikariCP + executors bounded; no unbounded accumulation; scheduled overlap guarded
- [ ] Step 9: `spring-transaction` consulted; crash-safety, cross-aggregate compensation / reconciliation, readiness, migration rollout checked
- [ ] Step 10: standalone: report written via `review-report-writer`, confirmation printed; subagent: findings returned to parent, no file written
- [ ] Every finding names the failure mode and blast radius, never just the missing pattern
- [ ] Depth honored: `standard` ran all; `deep` filled the Failure-Mode and Blast-Radius Map
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Avoid

- Reporting a missing pattern without the failure mode ("add a timeout" vs "unbounded call to payment-gateway exhausts HikariCP")
- Overlapping into perf (throughput tuning) or observability (metric/log wiring) - name the failure-survival gap
- Recommending retries on non-idempotent ops without an idempotency key
- Recommending a circuit breaker with no monitoring
- Treating broker retries as a substitute for consumer idempotency
- Approving an in-transaction `save` + `kafkaTemplate.send` dual write
- Mitigating a live incident here - route to `/task-oncall-start` first
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
