---
name: kotlin-spring-async-processing
description: Kotlin / Spring async patterns: @Async, @TransactionalEventListener, @Scheduled, Virtual Threads, coroutine interop, self-invocation pitfalls.
metadata:
  category: backend
  tags: [kotlin, async, threading, events, idempotency, coroutines]
user-invocable: false
---

# Kotlin Async Processing

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Fire-and-forget side effects, background tasks, event-driven workflows in Kotlin / Spring
- Choosing between `@Async`, coroutine scope beans, or `@TransactionalEventListener`
- Configuring executors for Virtual Threads or thread pools

## Rules

- Async only for non-critical side effects, never core transaction logic.
- Async handlers idempotent. Exceptions handled explicitly - never swallowed.
- Always name the executor (`@Async("name")`) and configure pool size / queue capacity. Default `SimpleAsyncTaskExecutor` creates a thread per call.
- `@TransactionalEventListener(AFTER_COMMIT)` over `@EventListener` when the event must fire only after commit.
- `@Async` self-invocation is silently ignored - call through an injected bean.
- Managed `CoroutineScope` bean over `GlobalScope` (see `kotlin-coroutines-spring`).
- Configure `kotlin("plugin.spring")` - otherwise `@Async` classes are final.
- `synchronized` on a Virtual Thread carrier pins the carrier. Use `ReentrantLock` (sync code) or `kotlinx.coroutines.sync.Mutex` (suspend code) on Boot 3.2+ with `spring.threads.virtual.enabled=true`. Diagnose with `-Djdk.tracePinnedThreads=full`.

## `@Async` vs coroutines

| Situation                                                  | Choice                                          |
| ---------------------------------------------------------- | ----------------------------------------------- |
| Single fire-and-forget from a sync controller              | `@Async` with named executor                    |
| Service path already `suspend` end-to-end                  | Coroutine `launch` on injected scope            |
| Timeouts, retries, structured concurrency                  | Coroutines (`withTimeout`, `coroutineScope`)    |
| Java interop with `CompletableFuture`                      | `@Async` returning `CompletableFuture<T>`       |

Pick one per use case. Do not chain `@Async` → `runBlocking { ... }`.

## Patterns

### `ThreadPoolTaskExecutor`

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
class NotificationService(private val mail: MailClient) {
    @Async("asyncTaskExecutor")
    fun sendEmail(to: String, body: String): CompletableFuture<Void> {
        mail.send(to, body)
        return CompletableFuture.completedFuture(null)
    }
}
```

### Virtual Threads (Boot 3.5+ / Java 21+)

```kotlin
@Bean("asyncTaskExecutor")
fun asyncTaskExecutor(): Executor = Executors.newVirtualThreadPerTaskExecutor()
```

Lightweight thread per task. Do not use for CPU-bound work.

### `synchronized` pins Virtual Threads

```kotlin
// Bad - synchronized pins the VT carrier; throughput collapses under load
@Service
class CounterService {
    private var count = 0L
    @Synchronized
    fun increment(): Long = ++count
}

// Good - ReentrantLock parks the VT without pinning
@Service
class CounterService {
    private val lock = ReentrantLock()
    private var count = 0L
    fun increment(): Long = lock.withLock { ++count }
}

// Good (suspend code) - Mutex is coroutine-aware
@Service
class CounterService {
    private val mutex = Mutex()
    private var count = 0L
    suspend fun increment(): Long = mutex.withLock { ++count }
}
```

Same trap applies to `synchronized {}` blocks, `Collections.synchronizedMap`, and many `java.util.concurrent` internals that hold monitor locks. Diagnose with `-Djdk.tracePinnedThreads=full` - pinned-frame stack traces print to stderr on every pin event.

### Self-invocation bypass

```kotlin
// Bad - direct call, proxy bypassed, runs synchronously
@Service
class ReportService {
    fun generate(id: Long) { buildReport(id) }    // NOT async
    @Async("asyncTaskExecutor") fun buildReport(id: Long): CompletableFuture<Void> { ... }
}

// Good - inject a separate bean
@Service
class ReportService(private val async: ReportAsyncService) {
    fun generate(id: Long) { async.buildReport(id) }
}
```

### Exception handling

```kotlin
@Configuration
@EnableAsync
class AsyncConfig : AsyncConfigurer {
    private val log = LoggerFactory.getLogger(javaClass)
    override fun getAsyncUncaughtExceptionHandler() =
        AsyncUncaughtExceptionHandler { ex, method, args ->
            log.error("Async {} failed args={}", method.name, args.toList(), ex)
        }
}

// CompletableFuture-returning methods: attach exceptionally at the call site
async.buildReport(id).exceptionally { log.error("Report failed id=$id", it); null }
```

### `@TransactionalEventListener`

Fires only after the publishing transaction commits:

```kotlin
@Service
class OrderService(
    private val repo: OrderRepository,
    private val events: ApplicationEventPublisher,
) {
    @Transactional
    fun create(req: OrderRequest): Order {
        val order = repo.save(Order(req))
        events.publishEvent(OrderCreatedEvent(order.id))    // fires AFTER commit
        return order
    }
}

@Component
class OrderListener(private val notifier: NotificationService) {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Async("asyncTaskExecutor")
    fun on(event: OrderCreatedEvent) = notifier.sendConfirmation(event.orderId)
}
```

**Two silent-failure traps:**

1. **No active transaction at publish time → listener doesn't fire.** If publication runs from a non-transactional method (or `@Transactional` was bypassed by self-invocation / missing plugin / private visibility), the listener is skipped. Either publish inside an active transaction, or set `fallbackExecution = true`:

   ```kotlin
   @TransactionalEventListener(phase = AFTER_COMMIT, fallbackExecution = true)
   ```

2. **Listener exceptions cannot roll back the original transaction.** The TX is already committed. Listener errors propagate to the executor's exception handler and are gone. Treat post-commit work as needing its own retry / DLQ / outbox.

`AFTER_COMMIT` + `@Async` does not delay the controller response - the listener body just submits to the executor and returns.

### Retry on transient failures

```kotlin
@Async("asyncTaskExecutor")
@Retryable(retryFor = [MailSendException::class], maxAttempts = 3, backoff = Backoff(delay = 2000, multiplier = 2.0))
fun sendEmail(orderId: Long) { mail.send(orderId) }

@Recover
fun recover(ex: MailSendException, orderId: Long) {
    log.error("send failed orderId=$orderId after retries", ex)
}
```

Requires `@EnableRetry` and `spring-retry`.

### Coroutine alternative

When the surrounding code is suspend-based, use a managed scope bean instead of `@Async`. Pattern in `kotlin-coroutines-spring` § `CoroutineScope` bean.

## Edge Cases

- **SecurityContext not propagated**: `@Async` runs on a different thread - `SecurityContextHolder` is empty. Use `MODE_INHERITABLETHREADLOCAL` or `DelegatingSecurityContextExecutor`. For coroutines, use `ReactiveSecurityContextHolder` or pass principal.
- **MDC / tracing context lost**: wrap the executor with `TaskDecorator` (or `ContextPropagatingTaskDecorator` from Micrometer Context Propagation). For coroutines, `MDCContext` from `kotlinx-coroutines-slf4j`.
- **Retry exhaustion**: when `@Retryable` runs out and no `@Recover` is defined, the exception is swallowed. Always define `@Recover`.

## Output Format

```
Operation: {what runs async}
Mechanism: {@Async | CoroutineScope.launch | coroutineScope + async/withTimeout | @TransactionalEventListener}
Executor: {bean name | dispatcher}
Event Phase: {AFTER_COMMIT | AFTER_ROLLBACK | N/A}
Error Handling: {AsyncUncaughtExceptionHandler | exceptionally | @Recover | CoroutineExceptionHandler}
Idempotent: {yes | no - why}
```

## Avoid

- Async for critical transaction logic
- Swallowing exceptions (no `AsyncUncaughtExceptionHandler`)
- Unbounded thread pools
- `@Async` self-invocation
- Publishing events that need transactional guarantees from inside an `@Async` method
- `@EventListener` when the handler must not run on rollback
- `GlobalScope.launch`
- Mixing `@Async` and `runBlocking`
- Manual `open` on `@Async` services - use `kotlin("plugin.spring")`
