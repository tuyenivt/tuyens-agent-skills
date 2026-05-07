---
name: kotlin-spring-async-processing
description: Spring @Async, ApplicationEvent, @TransactionalEventListener, and @Scheduled patterns in Kotlin with Virtual Thread integration and coroutine interop for Spring Boot 3.5+. Covers executor configuration, self-invocation pitfalls, async exception handling, and the @Async vs coroutines decision.
metadata:
  category: backend
  tags: [kotlin, async, threading, events, idempotency, coroutines]
user-invocable: false
---

# Kotlin Async Processing

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Non-blocking side effects and background tasks in Kotlin/Spring
- Event publication and event-driven workflows
- Long-running operations that don't block user response
- Deciding between `@Async` and coroutine-based async (`suspend` + `CoroutineScope` bean)
- Configuring executor for Virtual Threads or thread pools

## Rules

- Do not use async for core transaction logic
- Avoid async inside transaction unless isolated
- Use managed executor with explicit thread pool sizing
- Async handlers must be idempotent
- Handle async failures explicitly, never swallow exceptions
- Prefer `@TransactionalEventListener` over `@EventListener` when the event must fire after commit
- `@Async` self-invocation is silently ignored - call through a Spring proxy (injected bean)
- For coroutine-based async, prefer a managed `CoroutineScope` bean over `GlobalScope` (see also `kotlin-coroutines-spring`)
- Configure `kotlin("plugin.spring")` so `@Async` classes are not `final`

## `@Async` vs Coroutines - Decision Guide

| Situation                                                          | Choice                                                  |
| ------------------------------------------------------------------ | ------------------------------------------------------- |
| Single fire-and-forget side effect from a sync controller          | `@Async` with named executor                            |
| Service path is already `suspend` end-to-end                       | Coroutine `launch` on injected `CoroutineScope` bean    |
| Need timeouts, retries, structured concurrency                     | Coroutines (`withTimeout`, `coroutineScope`)            |
| Mixing with WebFlux                                                | Coroutines (Spring Boot 3.x supports `suspend` handlers)|
| Java / Kotlin interop with `CompletableFuture`                     | `@Async` returning `CompletableFuture<T>`               |

Both can coexist. Pick one per use case; do not chain `@Async` -> `runBlocking { ... }` (worst of both).

## Patterns

### ThreadPoolTaskExecutor Configuration

Always define an explicit executor - Spring's default `SimpleAsyncTaskExecutor` creates a new thread per invocation:

```kotlin
@Configuration
@EnableAsync
class AsyncConfig {

    @Bean("asyncTaskExecutor")
    fun asyncTaskExecutor(): Executor = ThreadPoolTaskExecutor().apply {
        corePoolSize = 4
        maxPoolSize = 16
        queueCapacity = 200
        setThreadNamePrefix("async-")
        setRejectedExecutionHandler(ThreadPoolExecutor.CallerRunsPolicy())
        initialize()
    }
}

@Service
class NotificationService(private val emailClient: EmailClient) {
    @Async("asyncTaskExecutor") // always name the executor explicitly
    fun sendEmail(to: String, body: String): CompletableFuture<Void> {
        emailClient.send(to, body)
        return CompletableFuture.completedFuture(null)
    }
}
```

### Virtual Threads (Spring Boot 3.5+ / Java 21+)

Replace the thread pool executor with a virtual thread executor for I/O-bound async tasks:

```kotlin
@Bean("asyncTaskExecutor")
fun asyncTaskExecutor(): Executor = Executors.newVirtualThreadPerTaskExecutor()
```

Virtual threads have no max-pool overhead - each task gets its own lightweight thread. Do not use for CPU-bound work.

### Self-Invocation Pitfall

`@Async` is applied via Spring AOP proxy. Calling an `@Async` method from the same class bypasses the proxy - the method runs synchronously with no error:

```kotlin
// Bad: self-invocation - @Async is ignored, runs synchronously
@Service
class ReportService {
    fun generateReport(id: Long) {
        buildReport(id) // NOT async - direct call, proxy bypassed
    }

    @Async("asyncTaskExecutor")
    fun buildReport(id: Long): CompletableFuture<Void> { /* ... */ }
}

// Good: inject a separate Spring bean so the call goes through the proxy
@Service
class ReportService(private val reportAsyncService: ReportAsyncService) {
    fun generateReport(id: Long) {
        reportAsyncService.buildReport(id) // async - goes through proxy
    }
}
```

### Exception Handling in Async Methods

Unchecked exceptions in `@Async` methods are silently swallowed unless you set an `AsyncUncaughtExceptionHandler`:

```kotlin
@Configuration
@EnableAsync
class AsyncConfig : AsyncConfigurer {

    private val log = LoggerFactory.getLogger(javaClass)

    override fun getAsyncUncaughtExceptionHandler(): AsyncUncaughtExceptionHandler =
        AsyncUncaughtExceptionHandler { ex, method, params ->
            log.error("Async method ${method.name} failed with params ${params.toList()}", ex)
        }
}
```

For `CompletableFuture`-returning methods, attach `.exceptionally { }` at the call site:

```kotlin
reportAsyncService.buildReport(id)
    .exceptionally { ex ->
        log.error("Report generation failed for id=$id", ex)
        null
    }
```

### Transactional Event Listener

Use `@TransactionalEventListener` when the async handler must run only after the publishing transaction commits:

```kotlin
@Service
class OrderService(
    private val orderRepository: OrderRepository,
    private val events: ApplicationEventPublisher,
) {
    @Transactional
    fun create(req: OrderRequest): Order {
        val order = orderRepository.save(Order(req))
        events.publishEvent(OrderCreatedEvent(order.id))
        return order // event fires AFTER this transaction commits
    }
}

@Component
class OrderCreatedListener(private val notificationService: NotificationService) {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Async("asyncTaskExecutor")
    fun onOrderCreated(event: OrderCreatedEvent) {
        notificationService.sendConfirmation(event.orderId)
    }
}
```

Default phase is `AFTER_COMMIT`. Use `AFTER_ROLLBACK` for compensating actions.

### Async Outside Transaction

Bad - Blocking task within transaction:

```kotlin
@Transactional
fun processOrder(order: Order) {
    saveOrder(order)
    asyncService.notifyUser(order) // blocks transaction; event fires before commit
}
```

Good - Async execution outside transaction via event:

```kotlin
@Service
class OrderService(
    private val orderRepository: OrderRepository,
    private val events: ApplicationEventPublisher,
) {
    @Transactional
    fun processOrder(order: Order) {
        val saved = orderRepository.save(order)
        events.publishEvent(OrderCreatedEvent(saved.id))
    }
}
```

### Retry for Transient Failures

For async operations that should retry on transient failures (e.g., email service timeout), combine `@Async` with `@Retryable`:

```kotlin
@Async("asyncTaskExecutor")
@Retryable(retryFor = [MailSendException::class], maxAttempts = 3, backoff = Backoff(delay = 2000, multiplier = 2.0))
fun sendConfirmationEmail(orderId: Long) {
    emailClient.sendOrderConfirmation(orderId)
}

@Recover
fun recoverSendEmail(ex: MailSendException, orderId: Long) {
    log.error("Failed to send confirmation email for order $orderId after retries", ex)
}
```

Requires `@EnableRetry` on a configuration class and `spring-retry` dependency.

### Coroutine Alternative (CoroutineScope Bean)

When the surrounding code is already coroutine-based, use a managed scope bean instead of `@Async`:

```kotlin
@Configuration
class CoroutineConfig {
    @Bean
    fun applicationScope(): CoroutineScope =
        CoroutineScope(SupervisorJob() + Dispatchers.Default + CoroutineExceptionHandler { _, e ->
            LoggerFactory.getLogger("AppScope").error("Unhandled coroutine exception", e)
        })

    @Bean
    fun cleanupOnShutdown(scope: CoroutineScope): DisposableBean = DisposableBean { scope.cancel() }
}

@Component
class OrderEventPublisher(
    private val scope: CoroutineScope,
    private val notificationService: NotificationService,
) {
    fun publishOrderCreated(order: Order) {
        scope.launch {
            notificationService.sendOrderConfirmation(order)
        }
    }
}
```

Never use `GlobalScope` - it leaks on shutdown and bypasses your error handler.

## Edge Cases

- **SecurityContext not propagated**: `@Async` methods run on a different thread - `SecurityContextHolder` is empty by default. Use `SecurityContextHolder.setStrategyName(MODE_INHERITABLETHREADLOCAL)` or `DelegatingSecurityContextExecutor`. For coroutines, use `ReactiveSecurityContextHolder` or pass principal explicitly
- **MDC/tracing context lost**: SLF4J MDC is thread-local. Wrap the async executor with a `TaskDecorator` (or `ContextPropagatingTaskDecorator` from Micrometer Context Propagation) to copy trace IDs to async threads. For coroutines, use the `MDCContext` element from `kotlinx-coroutines-slf4j`
- **Transaction already committed**: `@TransactionalEventListener(AFTER_COMMIT)` fires after commit. The original entity reference may be detached - re-fetch from the database
- **Retry exhaustion**: When `@Retryable` exhausts all attempts and no `@Recover` method exists, the exception is silently swallowed. Always define a `@Recover` fallback

## Output Format

When applying async patterns, document the configuration:

```
Operation: {what is being done async}
Mechanism: {@Async | CoroutineScope.launch | @TransactionalEventListener}
Executor: {executor bean name | dispatcher}
Event Phase: {AFTER_COMMIT | AFTER_ROLLBACK | N/A}
Error Handling: {AsyncUncaughtExceptionHandler | exceptionally() | @Recover | CoroutineExceptionHandler}
Idempotent: {yes | no - why}
```

## Avoid

- Using async for critical transaction logic
- Swallowing exceptions in async handlers (no `AsyncUncaughtExceptionHandler` set)
- Unbounded thread pools (no `maxPoolSize`, no `queueCapacity`)
- Calling `@Async` methods within the same class (proxy bypass, silent no-op)
- Publishing events inside `@Async` methods that need transactional guarantees
- Using `@EventListener` when the handler must not run on rollback
- `GlobalScope.launch { ... }` for fire-and-forget - leaks on shutdown
- Mixing `@Async` and `runBlocking { ... }` - pick one mechanism
- Manual `open` on `@Service` classes hosting `@Async` methods - use `kotlin("plugin.spring")`
