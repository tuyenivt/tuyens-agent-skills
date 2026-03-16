---
name: spring-async-processing
description: Spring @Async, ApplicationEvent, @TransactionalEventListener, and @Scheduled patterns with Virtual Thread integration for Spring Boot 3.5+. Covers executor configuration, self-invocation pitfalls, and async exception handling.
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

## ThreadPoolTaskExecutor Configuration

Always define an explicit executor - Spring's default `SimpleAsyncTaskExecutor` creates a new thread per invocation:

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

## Virtual Threads (Spring Boot 3.5+ / Java 21+)

Replace the thread pool executor with a virtual thread executor for I/O-bound async tasks:

```java
@Bean("asyncTaskExecutor")
public Executor asyncTaskExecutor() {
    return Executors.newVirtualThreadPerTaskExecutor();
}
```

Virtual threads have no max-pool overhead - each task gets its own lightweight thread. Do not use for CPU-bound work (no throughput gain and context-switch overhead).

## Self-Invocation Pitfall

`@Async` is applied via Spring AOP proxy. Calling an `@Async` method from the same class bypasses the proxy - the method runs synchronously with no error:

```java
// Bad: self-invocation - @Async is ignored, runs synchronously
@Service
public class ReportService {
    public void generateReport(Long id) {
        buildReport(id); // NOT async - direct call, proxy bypassed
    }

    @Async("asyncTaskExecutor")
    public CompletableFuture<Void> buildReport(Long id) { ... }
}

// Good: inject a separate Spring bean so the call goes through the proxy
@Service
public class ReportService {
    private final ReportAsyncService reportAsyncService; // injected

    public void generateReport(Long id) {
        reportAsyncService.buildReport(id); // async - goes through proxy
    }
}
```

## Exception Handling in Async Methods

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

## Transactional Event Listener

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

## Pattern

Bad - Blocking task within transaction:

```java
@Transactional
public void processOrder(Order order) {
    saveOrder(order);
    asyncService.notifyUser(order); // blocks transaction; event fires before commit
}
```

Good - Async execution outside transaction via event:

```java
@Service
public class OrderService {
    @Transactional
    public void processOrder(Order order) {
        Order saved = orderRepository.save(order);
        events.publishEvent(new OrderCreatedEvent(saved.getId()));
        // @TransactionalEventListener fires after commit
    }
}
```

## Avoid

- Using async for critical transaction logic
- Swallowing exceptions in async handlers (no `AsyncUncaughtExceptionHandler` set)
- Unbounded thread pools (no `maxPoolSize`, no `queueCapacity`)
- Calling `@Async` methods within the same class (proxy bypass, silent no-op)
- Publishing events inside `@Async` methods that need transactional guarantees
- Using `@EventListener` when the handler must not run on rollback
