---
name: spring-async-processing
description: "Spring @Async, @TransactionalEventListener, @Scheduled with Virtual Threads: bounded executors, AFTER_COMMIT, exception handling, retry."
metadata:
  category: backend
  tags: [async, threading, events, idempotency]
user-invocable: false
---

# Async Processing

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Background tasks and non-blocking side effects
- Event-driven workflows tied to transaction phases
- Scheduled jobs

## Rules

- Always name the executor on `@Async("name")` - the unnamed default is `SimpleAsyncTaskExecutor` (unbounded, no queue)
- Async handlers must be idempotent (retries / redelivery are expected)
- `@Async` self-invocation is silently ignored (proxy bypass) - see `spring-transaction`
- Bounded `ThreadPoolTaskExecutor` (corePoolSize, maxPoolSize, queueCapacity, `CallerRunsPolicy`) or `Executors.newVirtualThreadPerTaskExecutor()` for IO-bound work
- Configure `AsyncUncaughtExceptionHandler` - unchecked exceptions on `void` returns are swallowed by default
- Prefer `@TransactionalEventListener(AFTER_COMMIT)` over `@EventListener` when the handler must not run on rollback

## Patterns

### Bounded executor vs Virtual Threads

```java
@Configuration @EnableAsync
class AsyncConfig implements AsyncConfigurer {

    // Option A: bounded pool with back-pressure
    @Bean("asyncTaskExecutor")
    Executor asyncTaskExecutor() {
        var ex = new ThreadPoolTaskExecutor();
        ex.setCorePoolSize(4);
        ex.setMaxPoolSize(16);
        ex.setQueueCapacity(200);
        ex.setThreadNamePrefix("async-");
        ex.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        ex.initialize();
        return ex;
    }

    // Option B (Spring Boot 3.2+, IO-bound): Virtual Threads
    // @Bean("asyncTaskExecutor")
    // Executor asyncTaskExecutor() { return Executors.newVirtualThreadPerTaskExecutor(); }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) -> log.error("Async {} failed {}", method.getName(), params, ex);
    }
}

@Async("asyncTaskExecutor")
public CompletableFuture<Void> sendEmail(String to, String body) {
    emailClient.send(to, body);
    return CompletableFuture.completedFuture(null);
}
```

Virtual Threads suit IO-bound work; do not use for CPU-bound (no throughput gain, more context switches).

### `@TransactionalEventListener` for post-commit side effects

```java
@Transactional
public Order create(OrderRequest req) {
    Order order = orderRepository.save(new Order(req));
    events.publishEvent(new OrderCreatedEvent(order.getId()));
    return order;  // listener fires only if this commits
}

@TransactionalEventListener(phase = AFTER_COMMIT)
@Async("asyncTaskExecutor")
public void onOrderCreated(OrderCreatedEvent e) {
    notificationService.sendConfirmation(e.orderId());
}
```

### Retry transient failures

```java
@Async("asyncTaskExecutor")
@Retryable(retryFor = MailSendException.class, maxAttempts = 3,
           backoff = @Backoff(delay = 2000, multiplier = 2))
public void sendConfirmationEmail(Long orderId) { emailClient.sendOrderConfirmation(orderId); }

@Recover
public void recover(MailSendException ex, Long orderId) {
    log.error("Failed after retries for order {}", orderId, ex);
    // persist to retry queue or alert ops
}
```

Always define `@Recover` - without it, exhausted retries are swallowed.

### Context propagation across the async boundary

- **SecurityContext**: not inherited. Pass principal as a method parameter, or set `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL`.
- **MDC / trace IDs**: wrap the executor with a `TaskDecorator` (`ContextPropagatingTaskDecorator` from Micrometer Context Propagation copies MDC, security, and trace context).
- **JPA Session**: not propagated. The async method must re-fetch entities and open its own transaction.

## Output Format

```
Operation: {what runs async}
Executor: {bean name | virtualThread}
Event Phase: {AFTER_COMMIT | AFTER_ROLLBACK | N/A}
Error Handling: {AsyncUncaughtHandler | exceptionally | @Recover}
Idempotent: {Yes | No - rationale}
```

## Avoid

- `@Async` without an explicit executor name (uses unbounded default)
- Calling `@Async` methods via `this.X()` (proxy bypass, silent no-op)
- Publishing events from inside `@Async` when transactional semantics matter
- `@EventListener` for handlers that must not run on rollback
