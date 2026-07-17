---
name: task-kotlin-review-reliability
description: "Kotlin / Spring Boot reliability review: coroutine deadlines, Resilience4j-kotlin breakers/retries, bounded dispatchers, idempotency, outbox."
agent: kotlin-reliability-engineer
metadata:
  category: backend
  tags: [kotlin, spring-boot, reliability, resilience, resilience4j, coroutines, idempotency, outbox, workflow]
  type: workflow
user-invocable: true
---

# Kotlin / Spring Boot Reliability Review

## Purpose

Kotlin-aware reliability review that leads with structured concurrency and names Resilience4j-kotlin, Spring Kafka / RabbitMQ, `@Transactional`, HikariCP, and coroutine `WebClient` idioms directly. Reliability = behavior under failure and saturation - the unhappy path: what happens when a dependency is slow or down, load spikes, a coroutine is cancelled, or a process crashes mid-operation. Findings name the failure mode and blast radius with concrete fixes for Kotlin 2.0+ / Spring Boot 3.5+.

Stack-specific delegate of `task-code-review-reliability`.

## Seam With Adjacent Lenses

- **vs. Perf:** perf tunes HikariCP / dispatchers / executors for throughput; this lens verifies they are bounded and that exhaustion degrades gracefully. A slow query is perf; the untimed `suspend` call holding a connection until DB `wait_timeout` is reliability.
- **vs. Observability:** obs owns the breaker-state metric and the fallback log line; this lens owns the breaker and the fallback existing and being configured.
- **vs. core correctness (Phase B):** Phase B owns happy-path transaction correctness; this lens owns partial failure, dependency failure, and saturation. Idempotency sits at the seam - the umbrella dedups.

## When to Use

- Kotlin / Spring Boot PR adding or changing an integration point (`WebClient` / `RestClient` suspend calls, `@KafkaListener` / `@RabbitListener`, `@Scheduled`, `CoroutineScope.launch`)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and delivery semantics
- Hardening after a near-miss; recurring resilience-debt sweep
- Dual-write / outbox / consumer-retry correctness under crash and cancellation

**Not for:** general review (`task-kotlin-review`), throughput optimization (`task-kotlin-review-perf`), observability wiring (`task-kotlin-review-observability`), security (`task-kotlin-review-security`), a live incident (`/task-oncall-start` - mitigate first).

## Depth Levels

| Depth      | When                                                | What runs                                          |
| ---------- | --------------------------------------------------- | -------------------------------------------------- |
| `standard` | Default                                             | All steps except the Failure-Mode Map              |
| `deep`     | Requested, or handed down by `task-kotlin-review`   | All steps + `Failure-Mode and Blast-Radius Map`    |

At `deep`, use skill: `failure-propagation-analysis` to trace each new / changed dependency's failure path across service boundaries and shared resources (HikariCP, dispatchers, broker) and name the loop-breaker that contains it.

## Invocation

| Invocation                                 | Meaning                                       |
| ------------------------------------------ | --------------------------------------------- |
| `/task-kotlin-review-reliability`          | Current branch vs base                        |
| `/task-kotlin-review-reliability <branch>` | `<branch>` vs base (3-dot diff)               |
| `/task-kotlin-review-reliability pr-<N>`   | PR head in `pr-<N>`                            |
| `/task-kotlin-review-reliability sweep`    | Whole-surface sweep (resilience-debt pass, no feature branch). Skips Step 3; Step 4 reads the full reliability surface, not just changed files; checkpoint `base_sha` = `head_sha` = `HEAD`. Allowed on trunk - read-only. |

When invoked as a subagent of `task-kotlin-review`, the parent passes the pre-confirmed stack, the precondition handle, and pre-read diff + log; Steps 2-3 consume those instead of re-running. A dispatch from `task-code-review-reliability` forwards arguments only (nothing pre-read) - run standalone.

## Workflow

### Step 1 - Behavioral principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm stack

Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Kotlin / Spring Boot, stop and route the user to `/task-code-review-reliability`. Assumes Kotlin 2.0+ / Spring Boot 3.5+.

### Step 3 - Resolve diff

Use skill: `review-precondition-check`. Read diff + log once. Skip if parent passed handle, or in `sweep` mode (no diff - Steps 4-11 apply to the whole reliability surface; findings still cite `file:line`). Surface any fail-fast verbatim.

### Step 4 - Read the reliability surface

Read every changed file in these categories plus any unchanged file the diff calls into (a small diff ripples: a new service method calling an unchanged untimed client is a new failure path at the call site):

- External clients: `WebClient` / `RestClient` / `RestTemplate` beans + `suspend` call sites - deadlines, breakers, retries
- `suspend @Service` methods composing multiple downstream calls (`coroutineScope { async { } }` fan-out) - deadline budget, partial-failure handling
- `@KafkaListener` / `@RabbitListener` / `@JmsListener` - idempotency, ack mode, DLT, retry, `suspend` bridging
- `@Scheduled` / `@Async` / `CoroutineScope.launch` - overlap guards, bounded dispatchers / executors, failure isolation, `GlobalScope` leaks
- Side-effecting flows (payment, notification, provisioning) - idempotency keys, outbox
- `CoroutineScope` bean config - `SupervisorJob`, bounded dispatcher, `CoroutineExceptionHandler`
- `application.yml`: `resilience4j.*`, `spring.datasource.hikari.*`, `spring.kafka.*`, `spring.task.execution.pool.*`, `spring.threads.virtual.enabled`, `*.timeout` keys
- Dependency adds: `resilience4j-spring-boot3`, `resilience4j-kotlin`, `spring-retry`, outbox libraries

For each finding, cite a real `file:line`.

### Step 5 - Timeouts, deadlines, and cancellation

Use skill: `kotlin-coroutines-spring`.

- [ ] **Deadline on every external call** - `suspend` calls wrapped in `withTimeout(dur)` on the required path (propagates `TimeoutCancellationException`, cancels the fan-out) or `withTimeoutOrNull` on the optional path (null selects the fallback). Non-suspend `WebClient` / `RestClient` beans set explicit connect + read + response timeouts; no default-infinite waits.
- [ ] **`@Transactional(timeout = N)` on long reads** so a query cannot hold a HikariCP connection until DB `wait_timeout`.
- [ ] **Deadline budget on chained / fan-out calls** - a `coroutineScope { async { } }` fan-out sits under one `withTimeout`; structured concurrency cancels siblings automatically when the deadline fires. A slow first call leaves budget for the rest or fails fast.
- [ ] **Cancellation propagation** - `CancellationException` (and its subtype `TimeoutCancellationException`) is rethrown before any `catch (e: Exception)` / `runCatching`; swallowing it defeats the deadline and leaks the coroutine. Long CPU loops call `ensureActive()` / check `isActive` to stay cooperatively cancellable.
- [ ] **No `runBlocking` on the request path** - never in a `@RestController` / `@Service`; only at non-suspend framework boundaries (`@Scheduled`, listener). It blocks the carrier and ignores the caller's deadline.

### Step 6 - Retries, circuit breakers, and bulkheads

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns.

- [ ] **Retries bounded, backed off, jittered** - `resilience4j-kotlin` `retry.executeSuspendFunction { }` (or `@Retry`) with capped `maxAttempts`, exponential backoff, and jitter (`randomizedWaitFactor`). Retry transient only (5xx, timeouts, connect failures); never 4xx; never a non-idempotent op without an idempotency key.
- [ ] **Retry amplification bounded** - chained retries share a per-request budget; N hops x M attempts is not left to multiply. A retry nested in a `coroutineScope` under a `withTimeout` inherits the deadline rather than extending it.
- [ ] **Circuit breaker per external dependency** - `resilience4j-kotlin` `circuitBreaker.executeSuspendFunction { }` (or `@CircuitBreaker`) with explicit failure-rate threshold, wait duration, and half-open probes; breaker outermost when composed with retry so it opens on exhausted retries. State is metered (visibility gap -> `task-kotlin-review-observability`). A shared or unmonitored breaker counts as missing.
- [ ] **Bulkhead per failure domain** - concurrency to one slow dependency is bounded so it cannot exhaust a pool shared with others. Kotlin-native: a per-dependency `Dispatchers.IO.limitedParallelism(n)`, or `resilience4j-kotlin` `bulkhead.executeSuspendFunction`. Never route all downstreams through one unbounded scope or the shared `Dispatchers.IO`.

### Step 7 - Idempotency and delivery semantics

Use skill: `kotlin-spring-messaging-patterns`. Use skill: `backend-idempotency` for key strategy and atomic dedup.

- [ ] **Idempotency keys** on money / notification / provisioning side effects; dedup atomic (`markProcessed(key)` unique-PK insert returning new/seen), not a read-then-write race.
- [ ] **No in-transaction dual write** - `repo.save(...)` + `kafka.send(...)` inside one `@Transactional` can commit the DB and lose the publish (or vice versa) on crash. Use a transactional outbox or `@TransactionalEventListener(AFTER_COMMIT)`. Also flag `withContext(...)` inside a `@Transactional suspend` body - writes on the new dispatcher escape the transaction.
- [ ] **Consumer idempotency** - `@KafkaListener` / `@RabbitListener` handlers re-fetch state, dedup, and return early on replay (at-least-once). `suspend` listeners bridge via `runBlocking(MDCContext())` at the boundary - never a `suspend fun` on the annotation (the container cannot resume the continuation).
- [ ] **Ack discipline** - offsets committed only after successful processing: the container defaults (`enable-auto-commit: false` + ack-mode `BATCH` / `RECORD`) qualify, as does `manual_immediate`; flag `enable-auto-commit: true` or acking before the work completes - that is at-most-once, silent loss on crash.
- [ ] **DLT / DLQ with bounded retry** - `@RetryableTopic` / Rabbit DLX routes poison messages to a dead-letter destination after capped attempts; no infinite in-place retry. `runCatching` is banned in consumers (swallows `CancellationException`).

### Step 8 - Graceful degradation and backpressure

- [ ] **Defined fallback per critical dependency** - a Resilience4j fallback (cached / default / partial data), `withTimeoutOrNull { } ?: fallback`, or an explicit fail-fast (503) rather than an unbounded wait.
- [ ] **Scope chosen by criticality** - required fan-out uses `coroutineScope` (one failure cancels siblings); only optional children with real fallbacks use `supervisorScope`. Mixed required + optional: strict `coroutineScope` plus a per-optional-child `runCatching` that rethrows `CancellationException`.
- [ ] **Fallbacks log the original failure** at WARN with context (parameterized SLF4J); no silent swallow that hides degradation until it compounds.
- [ ] **`Flow` backpressure** - hot producers bound with `buffer(capacity)` / `conflate()` / bounded `flatMapMerge(concurrency = N)`; no unbounded in-memory collection of a stream.
- [ ] **Load shedding** - saturation returns 429 / 503 or sheds load rather than queueing unboundedly.

### Step 9 - Resource exhaustion and saturation

Use skill: `kotlin-spring-async-processing`.

- [ ] **HikariCP bounded** - `maximumPoolSize` set and `maxLifetime` < DB `wait_timeout`; `connectionTimeout` fails fast (1-3s) rather than blocking the caller indefinitely under exhaustion.
- [ ] **Dispatchers / executors bounded** - coroutine bulkheads via `limitedParallelism(n)`; `@Async` `ThreadPoolTaskExecutor` has a max size, a bounded `queueCapacity`, and a rejection policy (`CallerRunsPolicy`); no default unbounded `SimpleAsyncTaskExecutor` on platform threads.
- [ ] **No `GlobalScope.launch` / unbounded launch-per-request** - fire-and-forget uses an injected managed `CoroutineScope` bean (`SupervisorJob` + bounded dispatcher + `CoroutineExceptionHandler`). `GlobalScope` leaks on shutdown; one unbounded `launch` per request piles up under load.
- [ ] **No unbounded accumulation** - in-memory collections, caches, and buffers that grow with load have a bound or eviction; large results streamed as `Flow<T>` / `Stream<T>`, not a fully buffered `List<T>`.
- [ ] **`@Scheduled` overlap** - long jobs guard against overlapping runs (`fixedDelay`, ShedLock `@SchedulerLock`, or a running-flag); every instance fires, so keep the job idempotent regardless. A body that launches into a `CoroutineScope` returns immediately - `fixedDelay` then guards nothing; guard or `join` the launched work itself.

### Step 10 - Recoverability and consistency under partial failure

Use skill: `architecture-data-consistency`. Use skill: `kotlin-spring-transaction` for boundary correctness.

- [ ] **Crash-safety** - a multi-step side effect interrupted mid-way leaves recoverable state (outbox pending, saga compensation, or a safe re-run), not a half-applied change.
- [ ] **Compensation / saga** - cross-aggregate or cross-service writes that cannot be one transaction have a compensating action on partial failure.
- [ ] **Cancellation cleanup** - suspend cleanup in `finally` after cancellation is wrapped in `withContext(NonCancellable)`; otherwise the cleanup call is itself cancelled and state is left dirty.
- [ ] **Readiness reflects dependencies** - the readiness probe gates on the dependencies the service needs to serve, so an unready instance sheds rather than accepts traffic it cannot handle (probe wiring depth -> `task-kotlin-review-observability`).
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes (use skill: `kotlin-spring-db-migration-safety`, `ops-backward-compatibility`).

### Step 11 - Write report

**Subagent carve-out:** when spawned by a parent review (`task-kotlin-review`), do **not** call `review-report-writer` - the parent owns the single report and passes no checkpoint fields. Return the findings inline (Output Format below) for the parent to synthesize; at `deep`, include the Failure-Mode and Blast-Radius Map with the returned findings for the parent to preserve as its own section. Skip the rest of this step.

Standalone: Use skill: `review-report-writer` with `report_type: review-reliability` and `scope: +rel`, `depth` as invoked, `stack = kotlin-spring-boot`, `base_sha` / `head_sha` via `git rev-parse` on the handle's refs (whole-surface sweep: both = `HEAD`), and `mode: full`, `round: 1` - unless `review-reliability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha` (check for that file yourself; `review-precondition-check` looks up `review-<branch>.md`, a different report). Print confirmation.

## Output Format

**Severity assignment:** High = an unbounded failure path or data-loss / corruption risk under a plausible failure (missing deadline on a hot external call, uncapped retry, non-idempotent retry, in-tx dual write, `GlobalScope.launch` / unbounded launch-per-request, swallowed `CancellationException`); Medium = failure is bounded but recovery or containment is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, missing deadline / retry budget on a chained path, non-idempotent consumer, unbounded `Flow` producer); Low = hardening with no immediate failure path (missing bulkhead, fail-fast where stale data would serve). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on a critical path; Low -> `[Recommend]` or `[Question]`.

```markdown
## Kotlin / Spring Boot Reliability Review Summary

**Stack Detected:** Kotlin <version> / Spring Boot <version>
**Resilience Library:** Resilience4j (+ resilience4j-kotlin) | Spring Retry | structured concurrency only | none detected
**Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line]
   **Issue:** [name the gap: untimed `WebClient` suspend call, uncapped `@Retry`, swallowed `CancellationException`, in-tx dual write, `GlobalScope.launch`, unbounded `Flow`, non-idempotent listener, etc.]
   **Failure Mode:** [what fails and how: "recommendation-service latency spike blocks the request coroutine; with no `withTimeout` the caller waits until the HikariCP connection is reclaimed"]
   **Blast Radius:** [what else is affected: "all endpoints sharing the pool return 503"]
   **Fix:** [`withTimeout` + fallback, `circuitBreaker.executeSuspendFunction`, `limitedParallelism` bulkhead, outbox, idempotency key, etc.]

### Medium Impact
[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins
[Same numbered-block structure]

_Omit empty sections._

## Recommendations

[Structural resilience improvements not tied to a single finding]

## Failure-Mode and Blast-Radius Map

_(`deep` only - omit at `standard`.)_
Per new / changed dependency: **what happens when it is down or slow**, the shared resource on the propagation path (HikariCP, dispatcher, broker), and the loop-breaker that contains it (breaker, deadline, bulkhead, load shedding).

## Next Steps

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: platform] - [action]
3. **[Implement]** [Recommend] file:line - [action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra). Order Must > Recommend > Question. Omit if none._
```

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no messaging, no scheduled jobs).

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Kotlin 2.0+ / Spring Boot 3.5+ (or pre-confirmed stack accepted from parent)
- [ ] Step 3: precondition check ran (or handle received, or `sweep` mode); diff + log read once
- [ ] Step 4: external clients + suspend call sites, composing services, listeners, scheduled / async / scope-launch, side-effecting flows, `CoroutineScope` beans, resilience / pool / VT config read
- [ ] Step 5: `kotlin-coroutines-spring` consulted; deadlines (`withTimeout` / `withTimeoutOrNull`), `@Transactional(timeout)`, chained budget, cancellation propagation (no swallowed `CancellationException`), no `runBlocking` on the request path checked
- [ ] Step 6: `ops-resiliency` consulted; retries (capped / backoff / jitter / transient-only / idempotent-only), retry budget, breaker per dependency, bulkhead via `limitedParallelism` / Resilience4j checked
- [ ] Step 7: `backend-idempotency` + `kotlin-spring-messaging-patterns` consulted; idempotency keys, no in-tx dual write, consumer idempotency, ack, DLT checked
- [ ] Step 8: fallback per critical dependency; scope choice by criticality; fallbacks log; `Flow` backpressure; load shedding verified
- [ ] Step 9: `kotlin-spring-async-processing` consulted; HikariCP + dispatchers / executors bounded; no `GlobalScope` / unbounded launch-per-request; no unbounded accumulation; scheduled overlap guarded
- [ ] Step 10: `architecture-data-consistency` + `kotlin-spring-transaction` consulted; crash-safety, compensation, `NonCancellable` cleanup, readiness, migration rollout checked
- [ ] Step 11: standalone: report written via `review-report-writer` (`review-reliability`, `+rel`, checkpoint fields), confirmation printed; subagent: findings returned inline, no file written
- [ ] Every finding names the failure mode and blast radius, never just the missing pattern
- [ ] Depth honored: `standard` ran all; `deep` filled the Failure-Mode and Blast-Radius Map via `failure-propagation-analysis`
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Avoid

- Reporting a missing pattern without the failure mode ("add a timeout" vs "untimed suspend call to payment-gateway holds the request coroutine and its HikariCP connection until `wait_timeout`")
- Swallowing `CancellationException` in `runCatching` / `catch (e: Exception)` - defeats deadlines and structured cancellation; always rethrow it first
- Overlapping into perf (throughput tuning) or observability (breaker-state metric / fallback log wiring) - name the failure-survival gap
- Recommending retries on non-idempotent ops without an idempotency key
- Recommending a circuit breaker with no monitoring
- Treating broker retries as a substitute for consumer idempotency
- Approving an in-`@Transactional` `save` + `kafka.send` dual write (phantom events on rollback), or `withContext` inside a `@Transactional suspend` body
- Approving `GlobalScope.launch` or an unbounded `launch` / `@Async` per request - use a managed bounded `CoroutineScope` bean
- Recommending `Dispatchers.IO` as a bulkhead without `limitedParallelism(n)` (still unbounded)
- Mitigating a live incident here - route to `/task-oncall-start` first
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
