---
name: kotlin-coroutines-spring
description: "Kotlin coroutines in Spring Boot: suspend controllers, Flow streaming, coroutine-aware @Transactional, Virtual Thread interop."
user-invocable: false
---

# Kotlin Coroutines with Spring Boot

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing or reviewing `suspend` services / controllers, `Flow` streaming, or parallel fan-out within a request
- Configuring application-scoped coroutine beans for background work
- Adding timeout / retry / cancellation behavior to coroutine-based service calls

Not for general Kotlin idioms (see `kotlin-idioms`) or coroutine test patterns (see `kotlin-testing-patterns`).

## Rules

- Never `GlobalScope.launch` - leaks on shutdown. Use a managed `CoroutineScope` bean.
- Never `runBlocking` in request handlers or Spring beans. Acceptable only at non-suspend framework boundaries (`@Scheduled`, CLI `main`, JPA lifecycle hooks).
- With Virtual Threads (Boot 3.2+, `spring.threads.virtual.enabled=true`), do not use `Dispatchers.IO` - the VT already absorbs blocking I/O. `Dispatchers.Default` only for CPU-bound work.
- `coroutineScope { }` for required fan-out (one failure cancels siblings). `supervisorScope { }` only when each optional child has an explicit fallback.
- Always rethrow `CancellationException` before catching `Exception` - otherwise structured cancellation is silently swallowed.
- Never switch dispatchers (`withContext(...)`) inside a `@Transactional suspend` body - the transaction is bound to the entering thread and writes on a new dispatcher escape it.

## Patterns

### `suspend` services and controllers

Spring Boot 3.5+ propagates coroutine context automatically:

```kotlin
@Service
class OrderService(private val repo: OrderRepository) {
    suspend fun findOrder(id: Long): Order = repo.findById(id) ?: throw OrderNotFoundException(id)
}

@RestController
class OrderController(private val service: OrderService) {
    @GetMapping("/api/orders/{id}")
    suspend fun get(@PathVariable id: Long): Order = service.findOrder(id)
}
```

### `Flow` streaming

```kotlin
interface OrderRepository : CoroutineCrudRepository<Order, Long> {
    fun findAllByUserId(userId: Long): Flow<Order>     // not suspend; Flow is cold
}

@GetMapping("/stream", produces = [MediaType.TEXT_EVENT_STREAM_VALUE])
fun stream(@RequestParam userId: Long): Flow<OrderSummary> =
    repo.findAllByUserId(userId).filter { it.status != CANCELLED }.map { it.toSummary() }
```

**`flowOn` (not `withContext` in `collect`) for blocking sources.** Shifts the producer; downstream stays on the caller's context.

```kotlin
// Good
flow { legacyJdbcDao.streamAll().forEach { emit(it) } }.flowOn(Dispatchers.IO)

// Bad - withContext inside collect doesn't move the producer
flow.collect { withContext(Dispatchers.IO) { ... } }
```

With Virtual Threads, `flowOn(Dispatchers.IO)` is usually unnecessary.

### `coroutineScope` vs `supervisorScope`

| Scope             | Child failure                          | Use when                                |
| ----------------- | -------------------------------------- | --------------------------------------- |
| `coroutineScope`  | Cancels siblings, rethrows             | All children required (all-or-nothing)  |
| `supervisorScope` | Siblings continue; each fails alone    | Optional children with fallbacks        |

```kotlin
// All required - one failure aborts the whole dashboard
suspend fun getDashboard(uid: Long): Dashboard = coroutineScope {
    val user = async { userService.find(uid) }
    val orders = async { orderService.recent(uid) }
    Dashboard(user.await(), orders.await())
}

// Optional - recommendations failure shouldn't break the profile
suspend fun getProfile(uid: Long): Profile = supervisorScope {
    val user = async { userService.find(uid) }
    val recs = async { recService.get(uid) }
    Profile(user.await(), runCatching { recs.await() }.getOrDefault(emptyList()))
}
```

**Mixed required + optional in one fan-out:** use the strict `coroutineScope` for the required children and guard each optional child individually with `runCatching` (rethrowing `CancellationException`). Don't reach for `supervisorScope` at the top - it would also stop a required child's failure from aborting the request.

```kotlin
suspend fun getDashboard(uid: Long): Dashboard = coroutineScope {
    val user = async { userService.find(uid) }                 // required
    val orders = async { orderService.recent(uid) }            // required
    val recs = async {                                         // optional
        runCatching { recService.get(uid) }
            .getOrElse { if (it is CancellationException) throw it else emptyList() }
    }
    Dashboard(user.await(), orders.await(), recs.await())
}
```

### `@Transactional` on `suspend`

Works in Spring Boot 3.x. Keep the body on the inherited dispatcher - **no `withContext` inside the transactional body** (the new thread has no transaction attached, writes escape silently):

```kotlin
@Transactional
suspend fun placeOrder(req: PlaceOrderRequest): Order {
    val order = orderRepo.save(Order(userId = req.userId))
    inventoryRepo.reserve(req.items)        // same transaction; rollback applies
    return order
}
```

### `CoroutineScope` bean for background work

```kotlin
@Configuration
class CoroutineConfig {
    @Bean
    fun applicationScope(): CoroutineScope = CoroutineScope(
        SupervisorJob() + Dispatchers.IO + CoroutineExceptionHandler { _, t ->   // IO: notifier does blocking I/O, VTs off
            log.error("unhandled coroutine exception", t)
        }
    )

    @Bean
    fun shutdownScope(scope: CoroutineScope) = DisposableBean { scope.cancel() }
}
```

Pick the scope's dispatcher by the work it runs, same as `withContext`: omit it (or `Dispatchers.IO`) for blocking I/O like email/push when Virtual Threads are off; `Dispatchers.Default` only when the background work is CPU-bound. `Default` for blocking I/O starves its small fixed pool.

```kotlin
@Service
class OrderEventPublisher(private val scope: CoroutineScope, private val notifier: NotificationService) {
    fun publishCreated(order: Order) = scope.launch {
        notifier.sendConfirmation(order)    // fire-and-forget; failures hit the handler
    }
}
```

### Timeout and retry

```kotlin
suspend fun fetchWithTimeout(id: String): Product =
    withTimeout(3_000) { externalApi.fetchProduct(id) }

suspend fun <T> retryWithBackoff(maxRetries: Int = 3, initialDelay: Long = 100, block: suspend () -> T): T {
    var delay = initialDelay
    repeat(maxRetries - 1) {
        try { return block() }
        catch (e: CancellationException) { throw e }    // never swallow cancellation
        catch (e: Exception) { delay(delay); delay = (delay * 2).coerceAtMost(2000) }
    }
    return block()
}
```

### Dispatchers with Virtual Threads

| Dispatcher            | When                                                  |
| --------------------- | ----------------------------------------------------- |
| _(none / default)_    | I/O with Virtual Threads enabled                      |
| `Dispatchers.Default` | CPU-bound (image processing, crypto)                  |
| `Dispatchers.IO`      | Blocking I/O when Virtual Threads NOT active          |

```kotlin
suspend fun processImage(bytes: ByteArray) = withContext(Dispatchers.Default) { run(bytes) }
```

`WebClient`: `webClient.get().uri(...).retrieve().awaitBody()`.

### `@Scheduled` with coroutines

`@Scheduled` methods cannot be `suspend`. Bridge via a scope bean:

```kotlin
@Component
class ScheduledTasks(private val scope: CoroutineScope, private val service: OrderService) {
    @Scheduled(fixedRate = 60_000)
    fun cleanup() { scope.launch { service.cleanupExpired() } }
}
```

### `Flow` exception transparency

Throwing inside `collect { }` violates the contract. Use `catch` before `collect`:

```kotlin
flow.onEach { if (it.isInvalid()) throw ValidationException("invalid") }
    .catch { log.error("flow error", it) }
    .collect { process(it) }
```

### Cancellation cleanup

Suspend calls in `finally` after cancellation need `withContext(NonCancellable)`:

```kotlin
try { orderService.process(id) }
finally { withContext(NonCancellable) { auditService.logCompletion(id) } }
```

## Output Format

```
## Coroutine Design

Virtual Threads active: {yes | no}
Dispatchers.IO usage: {none | justified}
Dispatchers.Default usage: {CPU-bound locations}

### Suspend boundaries
| Layer      | Method  | suspend? | Rationale |

### Scope decisions
| Operation | Scope | Rationale |
```

## Avoid

- `GlobalScope` - use a managed scope bean
- `runBlocking` in request handlers, services, or any Spring bean
- Catching `Exception` without first rethrowing `CancellationException`
- `withContext(...)` inside `@Transactional suspend` - writes escape the transaction
- Blocking calls inside coroutines without VTs and without `withContext(Dispatchers.IO)`
- `Dispatchers.IO` when Virtual Threads are active
- `withContext(Dispatchers.IO)` inside `Flow.collect` to fix a blocking producer - use `flowOn` upstream
- `withContext(NonCancellable)` omitted for suspend cleanup in `finally`
