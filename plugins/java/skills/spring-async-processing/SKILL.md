---
name: spring-async-processing
description: "Spring @Async, ApplicationEvent, @TransactionalEventListener, @Scheduled with Virtual Threads: executors, self-invocation, exception handling."
metadata:
  category: backend
  tags: [async, threading, events, idempotency]
user-invocable: false
---

# Async Processing

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Non-blocking side effects and background tasks
- Event publication and event-driven workflows
- Long-running operations that don't block user response

## Rules

- Do not use async for core transaction logic
- Avoid async inside transaction unless isolated
- Use managed executor with explicit thread pool sizing
- Async handlers must be idempotent
- Handle async failures explicitly, never swallow exceptions
- Prefer `@TransactionalEventListener` over `@EventListener` when the event must fire after commit
- `@Async` self-invocation is silently ignored - call through a Spring proxy (injected bean)

## Patterns

### ThreadPoolTaskExecutor Configuration

Bad - no executor named, falls back to `SimpleAsyncTaskExecutor` (unbounded, new thread per call, no queue back-pressure):

```java
@Async // no executor name - uses default SimpleAsyncTaskExecutor
public void sendEmail(String to, String body) { ... }
```

Good - named, bounded executor with caller-runs back-pressure:

```java
@Configuration
@EnableAsync
public class AsyncConfig {
    @Bean("asyncTaskExecutor")
    public Executor asyncTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("async-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.initialize();
        return executor;
    }
}

@Service
public class NotificationService {
    @Async("asyncTaskExecutor") // always name the executor explicitly
    public CompletableFuture<Void> sendEmail(String to, String body) {
        emailClient.send(to, body);
        return CompletableFuture.completedFuture(null);
    }
}
```

### Virtual Threads (Spring Boot 3.5+ / Java 21+)

Replace the thread pool executor with a virtual thread executor for I/O-bound async tasks:

```java
@Bean("asyncTaskExecutor")
public Executor asyncTaskExecutor() {
    return Executors.newVirtualThreadPerTaskExecutor();
}
```

Virtual threads have no max-pool overhead - each task gets its own lightweight thread. Do not use for CPU-bound work (no throughput gain and context-switch overhead).

### Self-Invocation Pitfall

`@Async` rides the Spring proxy: a `this.asyncMethod()` call runs synchronously with no error. See `spring-transaction` for the canonical fix patterns (extract to a separate bean; self-injection as a temporary measure).

### Exception Handling in Async Methods

Unchecked exceptions in `@Async` methods are silently swallowed unless you set an `AsyncUncaughtExceptionHandler`:

```java
@Configuration
@EnableAsync
public class AsyncConfig implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) ->
            log.error("Async method {} failed with params {}", method.getName(), params, ex);
    }
}
```

For `CompletableFuture`-returning methods, attach `.exceptionally()` at the call site:

```java
reportAsyncService.buildReport(id)
    .exceptionally(ex -> {
        log.error("Report generation failed for id={}", id, ex);
        return null;
    });
```

### Transactional Event Listener

Use `@TransactionalEventListener` when the async handler must run only after the publishing transaction commits (prevents processing events from rolled-back transactions):

```java
@Service
public class OrderService {
    private final ApplicationEventPublisher events;

    @Transactional
    public Order create(OrderRequest req) {
        Order order = orderRepository.save(new Order(req));
        events.publishEvent(new OrderCreatedEvent(order.getId()));
        return order; // event fires AFTER this transaction commits
    }
}

@Component
public class OrderCreatedListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Async("asyncTaskExecutor")
    public void onOrderCreated(OrderCreatedEvent event) {
        notificationService.sendConfirmation(event.orderId());
    }
}
```

Default phase is `AFTER_COMMIT`. Use `AFTER_ROLLBACK` for compensating actions.

### Retry for Transient Failures

For async operations that should retry on transient failures (e.g., email service timeout), combine `@Async` with `@Retryable`:

```java
@Async("asyncTaskExecutor")
@Retryable(retryFor = MailSendException.class, maxAttempts = 3, backoff = @Backoff(delay = 2000, multiplier = 2))
public void sendConfirmationEmail(Long orderId) {
    emailClient.sendOrderConfirmation(orderId);
}

@Recover
public void recoverSendEmail(MailSendException ex, Long orderId) {
    log.error("Failed to send confirmation email for order {} after retries", orderId, ex);
    // persist to retry queue or alert ops
}
```

Requires `@EnableRetry` on a configuration class and `spring-retry` dependency.

## Edge Cases

- **SecurityContext not propagated**: `@Async` methods run on a different thread - `SecurityContextHolder` is empty by default. Use `SecurityContextHolder.setStrategyName(MODE_INHERITABLETHREADLOCAL)` or pass the principal explicitly as a method parameter
- **MDC/tracing context lost**: SLF4J MDC is thread-local. Wrap the async executor with `MDCTaskDecorator` to copy trace IDs to async threads
- **Transaction already committed**: `@TransactionalEventListener(AFTER_COMMIT)` fires after the transaction commits. If the async handler needs to read the entity, it must re-fetch from the database - the original entity reference may be detached
- **Retry exhaustion**: When `@Retryable` exhausts all attempts and no `@Recover` method exists, the exception is silently swallowed. Always define a `@Recover` fallback

## Output Format

When applying async patterns, document the configuration:

```
Operation: {what is being done async}
Executor: {executor bean name}
Event Phase: {AFTER_COMMIT | AFTER_ROLLBACK | N/A}
Error Handling: {ASYNC_UNCAUGHT_HANDLER | EXCEPTIONALLY | RECOVER}
Idempotent: {Yes | No}
Idempotency Notes: {free text}
```

## Avoid

- Using async for critical transaction logic
- Swallowing exceptions in async handlers (no `AsyncUncaughtExceptionHandler` set)
- Unbounded thread pools (no `maxPoolSize`, no `queueCapacity`)
- Calling `@Async` methods within the same class (proxy bypass, silent no-op)
- Publishing events inside `@Async` methods that need transactional guarantees
- Using `@EventListener` when the handler must not run on rollback
