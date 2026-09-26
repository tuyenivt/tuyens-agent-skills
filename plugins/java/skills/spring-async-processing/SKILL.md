---
name: spring-async-processing
description: "Spring @Async, @TransactionalEventListener, @Scheduled on Virtual Threads: bounded vs VT executors, AFTER_COMMIT, retry, pinning."
metadata:
  category: backend
  tags: [async, threading, virtual-threads, events, idempotency]
user-invocable: false
---

# Async Processing

> Load `Use skill: stack-detect` first to determine the project stack. The rules below branch on the JDK version (pinning), the Boot version, and whether `spring.threads.virtual.enabled=true` is set. Read the JDK from `java.toolchain.languageVersion` / `<java.version>` / `sourceCompatibility`, Boot from the plugin or parent version, and the flag from `application*.yml`/`.properties`; write `unknown` for any that is absent (an unknown JDK is treated as < 24).

## When to Use

- Background tasks and non-blocking side effects
- Event-driven workflows tied to transaction phases
- Scheduled jobs
- Reviewing or diagnosing any of the above

## Rules

- While Boot's `applicationTaskExecutor` is active, an auto-configured `AsyncConfigurer` routes unnamed `@Async` to it (an application `AsyncConfigurer` whose `getAsyncExecutor()` returns `null` falls back to it too). It is VT-per-task when `spring.threads.virtual.enabled=true`, otherwise a `ThreadPoolTaskExecutor` with 8 core threads and an unbounded queue - no back-pressure. Once it backs off, Framework resolution applies: the single `TaskExecutor` bean if exactly one exists, else a bean named `taskExecutor`, else a `SimpleAsyncTaskExecutor` (one new platform thread per task, unbounded). Boot 4 registers no `taskExecutor` alias
- Declaring any `Executor` bean - a `ThreadPoolTaskScheduler` or a plain `ExecutorService` included - backs off `applicationTaskExecutor`. One added `ThreadPoolTaskExecutor` then silently becomes the target of every unnamed `@Async` (unless `@EnableScheduling`'s auto-configured `taskScheduler`, also a `TaskExecutor`, makes two); two, or a plain `Executor`/`ExecutorService`, drop unnamed `@Async` to the unbounded `SimpleAsyncTaskExecutor`. Keep the global default by declaring extra executors `@Bean(defaultCandidate = false)` (pattern below), or set `spring.task.execution.mode=force`; an application `AsyncConfigurer` whose `getAsyncExecutor()` returns an executor overrides both. (Boot 3.x: re-declare the default under the names `applicationTaskExecutor` and `taskExecutor`, or use `mode=force` on 3.5.) Symptom split: platform-thread counts in the thousands mean unnamed `@Async` fell to the thread-per-task `SimpleAsyncTaskExecutor`; slow delivery at a stable thread count means it was retargeted into another pool's queue
- Name an executor (`@Async("name")`) whenever the workload differs from the global default. Pick by workload: bounded `ThreadPoolTaskExecutor` (queue + back-pressure) for CPU-bound or rate-limited work; virtual threads for IO-bound fan-out
- Idempotency for redeliverable work is a stored claim, not an in-memory flag: transition the row (`UPDATE ... WHERE status = 'PENDING'`, or claim with `FOR UPDATE SKIP LOCKED`) or dedup on a persisted event ID before the side effect runs
- In-process `@TransactionalEventListener(AFTER_COMMIT)` events are not redelivered - a crash after commit, or an exception in the listener, loses them. A side effect that must happen goes through a durable record (outbox or job row, see `spring-messaging-patterns`); the listener is for best-effort work
- `@Async` self-invocation (`this.method()`) is silently ignored (proxy bypass) - see `spring-transaction`
- Configure `AsyncUncaughtExceptionHandler` - unchecked exceptions from `void` async methods are otherwise only logged by the default handler; `CompletableFuture` returns surface failures to the caller (`.exceptionally(...)`)
- `@TransactionalEventListener(AFTER_COMMIT)` over `@EventListener` when the handler must not run on rollback
- On JDK < 24, `synchronized` around blocking IO inside code that may run on a virtual thread pins the carrier (JEP 491 removes this in JDK 24+). On Java 21-23 use `ReentrantLock`, `StampedLock`, or concurrent collections
- `@Scheduled(fixedRate)` and `cron` on the VT scheduler (`SimpleAsyncTaskScheduler`) run each tick on a new thread and overlap themselves when a run exceeds the period. `fixedDelay` never self-overlaps, but on that scheduler fixed-delay tasks run on its single scheduler thread and a long one delays every other scheduled task. ShedLock prevents overlap on the same node and across replicas while the run stays under `lockAtMostFor`. A platform `ThreadPoolTaskScheduler` (VT off) never runs the same task concurrently

## Patterns

### Virtual Threads (IO-bound default)

```properties
spring.threads.virtual.enabled=true
```

The default `applicationTaskExecutor` becomes a VT-per-task `SimpleAsyncTaskExecutor`; unnamed `@Async`, `@Scheduled`, and Tomcat request threads become virtual. No executor bean is needed for IO-bound work.

### Explicit executors when you need control

```java
@Slf4j @Configuration @EnableAsync
class AsyncConfig implements AsyncConfigurer {

    // defaultCandidate = false keeps these beans from backing off Boot's applicationTaskExecutor,
    // so unnamed @Async keeps the global default; @Async("name") still resolves them.

    // CPU-bound or external-API rate-limited: bounded pool with back-pressure
    @Bean(name = "cpuExecutor", defaultCandidate = false)
    ThreadPoolTaskExecutor cpuExecutor(TaskDecorator contextDecorator) {
        var ex = new ThreadPoolTaskExecutor();
        ex.setCorePoolSize(4);
        ex.setMaxPoolSize(16);
        ex.setQueueCapacity(200);
        ex.setThreadNamePrefix("cpu-");
        ex.setTaskDecorator(contextDecorator);      // hand-built executors get no decorator automatically
        ex.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        ex.initialize();
        return ex;
    }

    // Dedicated VT executor when a slow downstream must not starve other async work:
    // the concurrency limit is the isolation (VTs share carriers with everything else)
    @Bean(name = "ioExecutor", defaultCandidate = false)
    SimpleAsyncTaskExecutor ioExecutor(TaskDecorator contextDecorator) {
        var ex = new SimpleAsyncTaskExecutor("io-");
        ex.setVirtualThreads(true);
        ex.setConcurrencyLimit(200);
        ex.setTaskDecorator(contextDecorator);
        return ex;
    }

    // Boot also applies this bean to applicationTaskExecutor. Boot 4.1: spring.task.execution.propagate-context=true
    // registers the same decorator - declare one or the other
    @Bean TaskDecorator contextDecorator() { return new ContextPropagatingTaskDecorator(); }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) -> log.error("Async {} failed", method.getName(), ex);
    }
}
```

At its concurrency limit a `SimpleAsyncTaskExecutor` blocks the submitting thread (here the request thread behind an `AFTER_COMMIT` listener); `setRejectTasksWhenLimitReached(true)` (Framework 6.2+) rejects instead - pair it with a drop-and-count path.

Virtual threads do not help CPU-bound work. Size a CPU-bound pool from the rate it must sustain: threads ~ arrival rate x service time (30/s x 0.4 s = 12), capped at the pod's cores - excess queues. A bounded pool caps concurrency per pod only: an account-wide external limit across N replicas needs a shared limiter (Redis-backed token bucket) or a per-pod share of limit/N, stated as such.

`CallerRunsPolicy` runs the rejected task on the submitting thread. Behind an `AFTER_COMMIT` listener that is the request thread, putting the work back on the response path - use a drop-and-count handler there so the loss is at least measured.

### Avoid pinning on Virtual Threads (JDK 21-23)

```java
// bad - synchronized around blocking IO pins the carrier
public void refresh() {
    synchronized (this) { token = httpClient.fetchToken(); }
}

// good - ReentrantLock parks the virtual thread without pinning
private final ReentrantLock lock = new ReentrantLock();

public void refresh() {
    lock.lock();
    try { token = httpClient.fetchToken(); } finally { lock.unlock(); }
}
```

Surface pinning with the JFR event `jdk.VirtualThreadPinned` (JDK 21-23 also accept `-Djdk.tracePinnedThreads=short`, removed in 24). On JDK 24+ `synchronized` no longer pins - report `None - JDK 24+`.

### `@TransactionalEventListener` for post-commit side effects

```java
@Transactional
public Order create(OrderRequest req) {
    Order order = orderRepository.save(new Order(req));
    events.publishEvent(new OrderCreatedEvent(order.getId()));
    return order;  // listener fires only if this commits
}

@TransactionalEventListener(phase = AFTER_COMMIT)
@Async("ioExecutor")
public void onOrderCreated(OrderCreatedEvent e) {
    notificationService.sendConfirmation(e.orderId());
}
```

AFTER_COMMIT listeners run in the transaction's `afterCompletion` callback. Three consequences:

- An exception thrown by a synchronous listener is caught and logged by Spring - it never reaches the caller, and the side effect is silently lost.
- A synchronous listener still holds the request's JDBC connection (released after the callbacks), so slow work belongs on `@Async`.
- A synchronous listener that writes needs `@Transactional(propagation = REQUIRES_NEW)`: a `REQUIRED` write in a callee joins the completed transaction and never commits. Spring 6.1+ fails startup when a `@TransactionalEventListener` method carries `@Transactional` with any other propagation than `REQUIRES_NEW` / `NOT_SUPPORTED` - an invalid combination is a finding, carried in the block's `Event Phase` as `AFTER_COMMIT - invalid @Transactional(<propagation>)`. An `@Async` listener already runs outside the committed transaction; its callee's plain `@Transactional` starts a new one.

### Durable async work (must survive a pod dying)

Write a job row in the business transaction (`status = PENDING`); workers claim with `SELECT ... FOR UPDATE SKIP LOCKED` and stamp `claimed_at`; a row whose claim is older than the lease (set above the worst-case run time) is reclaimable, which recovers work a dead pod left mid-flight. The listener or scheduler only wakes the worker; a claim-based sweep needs no ShedLock - SKIP LOCKED is the mutual exclusion. The claim stops a re-drive from repeating the whole job, not a crash between the external call and the completion write - pass the job ID to the provider as an idempotency key, or record `Idempotent: No - at-least-once send`. Emit the job table's DDL before the blocks. Outbox mechanics: `spring-messaging-patterns`.

### Retry transient failures

Framework 7's `@Retryable` (`org.springframework.resilience.annotation`, switched on by `@EnableResilientMethods`) replaces Spring Retry, which is archived and gone from Boot 4's BOM. It has no `@Recover`: after the last retry the exception reaches the caller. Split retry and async across two beans - the async bean dispatches and handles exhaustion, the retry bean holds `@Retryable`. On one method the proxies order async outermost, then retry, then `@Transactional` (each attempt runs in its own transaction on the async thread), but the Framework does not document that order - the split makes it explicit.

```java
@Async("ioExecutor")                                    // bean A - dispatch + exhaustion handling
public void sendConfirmationEmail(Long orderId) {
    try { mailer.send(orderId); }
    catch (MailSendException ex) { log.error("Failed after retries for order {}", orderId, ex); }   // persist to a retry table or alert
}

@Component
class Mailer {                                          // bean B - retry advice applies here
    @Retryable(includes = MailSendException.class, maxRetries = 2, delay = 2000, multiplier = 2)   // 1 call + 2 retries
    public void send(Long orderId) { emailClient.sendOrderConfirmation(orderId); }
}
```

"`@Retryable` never retries" - check, in order: `@EnableResilientMethods` on a configuration class (a project still on Spring Retry: `@EnableRetry`, an explicit `spring-retry` version, and AspectJ via `spring-boot-starter-aspectj` - on Boot 3.x the BOM manages `spring-retry`, AspectJ comes from `spring-boot-starter-aop`, and the form is `@Retryable(retryFor, maxAttempts, backoff = @Backoff(...))` + `@Recover`); `includes` matches the exception actually thrown (a `RestClient` throws `RestClientException` subtypes, not your domain type - translate at the client or list the client's types); the call goes through the proxy (no self-invocation). `@Async` needs `@EnableAsync`. An exhausted retry behind a `void` `@Async` method with no catch reaches only the `AsyncUncaughtExceptionHandler`.

### `@Scheduled`: overlap, time zone, errors

```java
// bad - fixedRate on the VT scheduler overlaps itself when a run outlasts the interval
@Scheduled(fixedRate = 60_000)
public void reconcileInventory() { ... }

// good for one replica on a pooled ThreadPoolTaskScheduler - fixedDelay counts from completion
// (on the VT scheduler it holds the single scheduler thread - see below)
@Scheduled(fixedDelay = 60_000)
public void reconcileInventory() { ... }

// good for N replicas - ShedLock also blocks same-node overlap while the lock is held
@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Tokyo")
@SchedulerLock(name = "nightlySettlement", lockAtMostFor = "30m", lockAtLeastFor = "1m")
public void nightlySettlement() { ... }
```

- ShedLock needs `net.javacrumbs.shedlock:shedlock-spring` plus a provider (`shedlock-provider-jdbc-template` and its `shedlock` table), a `LockProvider` bean, and `@EnableSchedulerLock(defaultLockAtMostFor = ...)` - the bare annotation is a silent no-op. `lockAtMostFor` above the worst-case run and below the interval; `lockAtLeastFor` covers clock skew so a fast run cannot re-fire on another replica. `fixedDelay` + ShedLock only when a run may exceed `lockAtMostFor`
- `cron` fires in the JVM default zone, which varies per container - set `zone` explicitly, and derive any business date inside the job from the same zone (`LocalDate.now(ZoneId.of("Asia/Tokyo"))`)
- Exceptions from a `@Scheduled` method go to the scheduler's `ErrorHandler` (default: log, schedule continues) - the tick's work is lost, so make jobs idempotent/resumable and alert from the `ErrorHandler` when a lost tick matters
- Long `fixedDelay` jobs on the VT scheduler: declare a `ThreadPoolTaskScheduler` bean with `setPoolSize(n > 1)` - it is an `Executor`, so it backs off `applicationTaskExecutor`; pair it with `spring.task.execution.mode=force` - or use `cron`/`fixedRate` with ShedLock

### Context propagation across the async boundary

- **Trace / MDC**: `ContextPropagatingTaskDecorator` copies the values registered with Micrometer's `ContextRegistry` - the observation scope, so `traceId`/`spanId` reach MDC through the tracing bridge. Other MDC keys need their own `ThreadLocalAccessor`. Boot applies `TaskDecorator` beans to every executor and scheduler built from its builders (the auto-configured ones included); a `new`-built executor calls `setTaskDecorator`. Boot 4.1's `spring.task.execution.propagate-context=true` registers the decorator for you when `io.micrometer:context-propagation` is on the classpath (`micrometer-tracing` brings it)
- **SecurityContext**: Spring Security 6.5+ registers `SecurityContextHolderThreadLocalAccessor` through ServiceLoader, so the `ContextPropagatingTaskDecorator` carries it; below 6.5 wrap the executor in `DelegatingSecurityContextAsyncTaskExecutor`
- **Scheduled and batch triggers** have no inbound request: each tick starts its own trace (Boot observes `@Scheduled` methods when an `ObservationRegistry` is present); log a job-run id alongside it
- `InheritableThreadLocal` copies only at thread creation - stale or foreign values on pooled executors, a shared mutable reference on per-task threads. Use a `TaskDecorator`
- **JPA Session**: not propagated. The async method re-fetches by ID and opens its own transaction

## Output Format

In every mode, emit the `**Stack:**` line once, before the first block, then one block per async or scheduled operation (configuration beans are not operations - their effect lands in each operation's `Executor` slot). When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, emit one finding per deviation - `### [Must|Recommend] file:line` (pasted input: `Class.method`), then `Issue:` and `Fix:` as separate paragraphs, `[Must]` first, `[Must]` when it loses work, duplicates a side effect, exhausts threads, carriers or the pool, fails startup, or runs a job on the wrong schedule, `[Recommend]` otherwise - then the blocks as the target state, carrying the current value as `was: ...` in each slot that changes. A cross-cutting gap (context propagation, a missing enabler) is one finding plus the affected slot in each block. A callee outside the reviewed files is `unknown - <callee> not reviewed` in the slot it affects.

```
**Stack:** Java {n | unknown}, Spring Boot {x.y | unknown}, virtual threads {on | off}
```

```
Operation: {what runs async/scheduled}

Executor: {bean name | global VT | applicationTaskExecutor - 8 threads, unbounded queue | retargeted to <bean> - sole TaskExecutor | SimpleAsyncTaskExecutor fallback - unbounded platform threads | scheduler | none - @Async bypassed by self-invocation}

Workload: {IO-bound | CPU-bound | rate-limited}

Event Phase: {AFTER_COMMIT | AFTER_ROLLBACK | AFTER_COMPLETION | BEFORE_COMMIT | @EventListener - runs on rollback | none - direct call inside the transaction | N/A}

Overlap Policy: {fixedDelay | ShedLock | fixedDelay + ShedLock | scheduler-serialised - ThreadPoolTaskScheduler, single replica | claim-based - SKIP LOCKED | none - overlaps <itself \| across replicas \| both> | N/A - not scheduled}

Error Handling: {AsyncUncaughtExceptionHandler | exceptionally | caller catch after @Retryable | @Recover - Spring Retry | scheduler ErrorHandler | none}

Idempotent: {Yes - mechanism | No - rationale | N/A - no redelivery path}

Context: {ContextPropagatingTaskDecorator | DelegatingSecurityContextAsyncTaskExecutor | SecurityContextHolderThreadLocalAccessor | missing - <what is lost> | not needed} - `+`-join when several apply

Pinning Risk: {None | None - JDK 24+ | Unknown - JDK not determined, treated as < 24 | Present - unfixed | Fixed - synchronized -> ReentrantLock | Fixed - synchronized -> StampedLock | Fixed - synchronized -> concurrent collection}
```

`Idempotent: N/A` only when redelivery is structurally impossible; write `No` when retry or a broker exists or is being added.

## Avoid

- `@Async` without an explicit executor name when the workload differs from the global default
- Declaring an `Executor` bean without `defaultCandidate = false` (or `mode=force`)
- Calling `@Async` methods via `this.X()` (proxy bypass, silent no-op)
- `synchronized` around blocking IO in code that may run on virtual threads on JDK < 24
- `@Scheduled(fixedRate)` or `cron` on the VT scheduler for jobs that must not overlap themselves; `cron` without `zone`
- CPU-bound work on Virtual Threads
- Required side effects in an AFTER_COMMIT listener without a durable record
- Relying on `InheritableThreadLocal` or `MODE_INHERITABLETHREADLOCAL` to carry context
