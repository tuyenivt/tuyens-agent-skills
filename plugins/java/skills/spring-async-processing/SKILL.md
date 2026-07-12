---
name: spring-async-processing
description: "Spring @Async, @TransactionalEventListener, @Scheduled on Boot 3.2+ Virtual Threads: bounded vs VT executors, AFTER_COMMIT, retry, pinning."
metadata:
  category: backend
  tags: [async, threading, virtual-threads, events, idempotency]
user-invocable: false
---

# Async Processing

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Background tasks and non-blocking side effects
- Event-driven workflows tied to transaction phases
- Scheduled jobs

## Rules

- Unnamed `@Async` runs on the global executor: VT-per-task when `spring.threads.virtual.enabled=true` (Boot 3.2+), otherwise an unbounded platform-thread `SimpleAsyncTaskExecutor`. Name an executor (`@Async("name")`) whenever the workload differs from that global default
- Pick the executor by workload: `ThreadPoolTaskExecutor` (bounded + queue + back-pressure) for CPU-bound or rate-limited; Virtual Threads for IO-bound fan-out
- Async handlers should be idempotent where redelivery is possible (`@Retryable`, broker redelivery). In-process `@TransactionalEventListener(AFTER_COMMIT)` events are NOT redelivered - a crash after commit loses them; use a transactional outbox when the side effect must survive (see `spring-messaging-patterns`)
- `@Async` self-invocation is silently ignored (proxy bypass) - see `spring-transaction`
- Configure `AsyncUncaughtExceptionHandler` - unchecked exceptions on `void` returns are otherwise swallowed; for `CompletableFuture` returns use `.exceptionally(...)`
- Prefer `@TransactionalEventListener(AFTER_COMMIT)` over `@EventListener` when the handler must not run on rollback
- On JDK < 24, `synchronized` inside code that may run on a Virtual Thread pins the carrier (JEP 491 removes this in JDK 24+). On Java 21 LTS use `ReentrantLock`, `StampedLock`, or concurrent collections
- `@Scheduled(fixedRate)` on the Boot 3.2+ VT scheduler (`SimpleAsyncTaskScheduler`) overlaps itself when a run exceeds the interval; `fixedDelay` serializes within one JVM, ShedLock serializes across replicas

## Patterns

### Boot 3.2+ Virtual Threads (IO-bound default)

```properties
# application.properties - turns the global Spring executor into a VT-backed SimpleAsyncTaskExecutor
spring.threads.virtual.enabled=true
```

With this flag set, the default `applicationTaskExecutor` is a VT-per-task `SimpleAsyncTaskExecutor`. `@Async` without a name uses it; `@Scheduled` and Tomcat request threads also become virtual. No executor bean needed for IO-bound work.

### Explicit executors when you need control

```java
@Configuration @EnableAsync
class AsyncConfig implements AsyncConfigurer {

    // CPU-bound or external-API rate-limited: bounded pool with back-pressure
    @Bean("cpuExecutor")
    Executor cpuExecutor() {
        var ex = new ThreadPoolTaskExecutor();
        ex.setCorePoolSize(4);
        ex.setMaxPoolSize(16);
        ex.setQueueCapacity(200);
        ex.setThreadNamePrefix("cpu-");
        ex.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        ex.initialize();
        return ex;
    }

    // Dedicated VT executor only when you need isolation (slow downstream must not
    // starve other async work), per-executor metrics, or a TaskDecorator; otherwise
    // unnamed @Async on the global VT executor is correct for IO-bound work
    @Bean("ioExecutor")
    Executor ioExecutor() { return Executors.newVirtualThreadPerTaskExecutor(); }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) -> log.error("Async {} failed", method.getName(), ex);
    }
}

@Async("ioExecutor")
public CompletableFuture<Void> sendEmail(String to, String body) {
    emailClient.send(to, body);
    return CompletableFuture.completedFuture(null);
}
```

Virtual Threads do not help CPU-bound work - more context switches, no throughput gain. Use a bounded pool there.

### Avoid pinning on Virtual Threads

```java
// bad - synchronized pins the carrier, defeating VT scalability
@Async("ioExecutor")
public void update(String key) {
    synchronized (this) { cache.put(key, fetch(key)); }
}

// good - ReentrantLock parks the VT without pinning
private final ReentrantLock lock = new ReentrantLock();

@Async("ioExecutor")
public void update(String key) {
    lock.lock();
    try { cache.put(key, fetch(key)); } finally { lock.unlock(); }
}
```

Surface pinning sites with the JFR event `jdk.VirtualThreadPinned` (or legacy `-Djdk.tracePinnedThreads=short`). JDK 24+ (JEP 491) removes `synchronized` pinning entirely.

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

DB writes inside a non-`@Async` AFTER_COMMIT listener are silently lost - the listener runs in the already-committed transaction context, so joined writes never flush. Use `@Transactional(propagation = REQUIRES_NEW)`, or `@Async` (a new thread has no transaction to join).

### Retry transient failures

```java
@Async("ioExecutor")
@Retryable(retryFor = MailSendException.class, maxAttempts = 3,
           backoff = @Backoff(delay = 2000, multiplier = 2))
public void sendConfirmationEmail(Long orderId) { emailClient.sendOrderConfirmation(orderId); }

@Recover
public void recover(MailSendException ex, Long orderId) {
    log.error("Failed after retries for order {}", orderId, ex);
    // persist to retry queue or alert ops
}
```

Always define `@Recover` - without it, exhausted retries are swallowed. `@Async` needs `@EnableAsync`, `@Retryable`/`@Recover` need `@EnableRetry` (Spring Retry dependency) on a `@Configuration`; without them the annotations are silent no-ops.

### `@Scheduled`: overlap and error handling

```java
// bad - fixedRate fires on schedule; the Boot 3.2+ VT scheduler runs each tick
// on its own thread, so a run slower than the interval overlaps the next one
@Scheduled(fixedRate = 60_000)
public void reconcileInventory() { ... }

// good - fixedDelay counts from completion: never self-overlaps in this JVM
@Scheduled(fixedDelay = 60_000)
public void reconcileInventory() { ... }
```

- `fixedDelay` does not serialize across replicas - for cluster-wide single execution use ShedLock (`@SchedulerLock(name = "reconcileInventory", lockAtMostFor = "10m")`). ShedLock needs the provider dependency, a `LockProvider` bean, and `@EnableSchedulerLock` - the bare annotation is a silent no-op
- Exceptions from a `@Scheduled` method go to the scheduler's `ErrorHandler` (default: log, schedule continues) - the tick's work is lost, so make jobs idempotent/resumable and alert from the `ErrorHandler` when a lost tick matters

### Context propagation across the async boundary

- **MDC / trace IDs / SecurityContext**: wrap the executor with `ContextPropagatingTaskDecorator` (Micrometer Context Propagation). It copies registered `ThreadLocal`s including MDC, security, and trace. `InheritableThreadLocal` is unreliable with Virtual Threads - do not rely on it.
- **JPA Session**: not propagated. The async method must re-fetch entities and open its own transaction.

## Output Format

One block per async or scheduled operation:

```
Operation: {what runs async/scheduled}
Executor: {bean name | global VT | bounded pool | scheduler}
Workload: {IO-bound | CPU-bound | rate-limited}
Event Phase: {AFTER_COMMIT | AFTER_ROLLBACK | N/A}
Overlap Policy: {fixedDelay | ShedLock | N/A - not scheduled}
Error Handling: {AsyncUncaughtHandler | exceptionally | @Recover | scheduler ErrorHandler}
Idempotent: {Yes | No - rationale | N/A - no redelivery path}
Pinning Risk: {None | Present - unfixed | Fixed - synchronized -> ReentrantLock}
```

## Avoid

- `@Async` without an explicit executor name when the workload differs from the global default
- Calling `@Async` methods via `this.X()` (proxy bypass, silent no-op)
- `synchronized` blocks inside async methods that may run on Virtual Threads (carrier pinning on JDK < 24)
- `@Scheduled(fixedRate)` for jobs that must not overlap themselves
- CPU-bound work on Virtual Threads (use a bounded pool)
- `@EventListener` for handlers that must not run on rollback
- Relying on `InheritableThreadLocal` or `MODE_INHERITABLETHREADLOCAL` to carry context to Virtual Threads
