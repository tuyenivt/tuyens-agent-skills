---
name: kotlin-coroutines-spring
description: "Patterns for Kotlin coroutines in Spring Boot 3.5+: suspend service/controller functions, Flow streaming, coroutine-aware transactions, Virtual Thread interop, structured concurrency with coroutineScope/supervisorScope, CoroutineScope bean configuration, and retry/timeout patterns."
user-invocable: false
---

# Kotlin Coroutines with Spring Boot

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing async service or controller methods in a Spring Boot + Kotlin project
- Streaming database results or HTTP responses with `Flow<T>`
- Running parallel operations within a single request (fan-out, scatter-gather)
- Configuring application-scoped coroutine beans for background work
- Adding timeout or retry behavior to coroutine-based service calls
- Reviewing coroutine usage for anti-patterns (GlobalScope, runBlocking in handlers)

Not for general Kotlin idioms (see `kotlin-idioms`) or test patterns for coroutines (see `kotlin-testing-patterns`).

## Rules

- Never use `GlobalScope.launch` - it escapes structured concurrency and leaks coroutines on shutdown
- Never use `runBlocking` in request handlers or Spring beans - it blocks the thread and defeats the purpose of coroutines
- Never use `Dispatchers.IO` alongside Virtual Threads (Spring Boot 3.2+ default) - they serve the same purpose; use `Dispatchers.Default` for CPU-bound work only
- Blocking calls inside a coroutine must be wrapped with `withContext(Dispatchers.IO)` if Virtual Threads are not active
- Use `coroutineScope { }` for parallel fan-out within a request - it cancels all children on failure
- Use `supervisorScope { }` only when some operations are optional and you have an explicit fallback for each failing child
- Always provide a `CoroutineExceptionHandler` or structured error handling when launching fire-and-forget background work

## Patterns

### suspend Functions in @Service

Spring Boot 3.5+ handles coroutine context automatically for `suspend` functions in `@Service` and `@RestController`:

```kotlin
@Service
class OrderService(private val repo: OrderRepository) {

    suspend fun findOrder(id: Long): Order {
        return repo.findById(id) ?: throw OrderNotFoundException(id)
    }

    suspend fun placeOrder(request: PlaceOrderRequest): Order {
        val order = Order(userId = request.userId, total = request.total)
        return repo.save(order)
    }
}

@RestController
@RequestMapping("/api/orders")
class OrderController(private val service: OrderService) {

    @GetMapping("/{id}")
    suspend fun getOrder(@PathVariable id: Long): Order {
        return service.findOrder(id)
    }
}
```

### Flow for Streaming Results

Use `Flow<T>` when results are large or produced incrementally:

```kotlin
// Repository returning a Flow (R2DBC or custom streaming)
interface OrderRepository : CoroutineCrudRepository<Order, Long> {
    fun findAllByUserId(userId: Long): Flow<Order>
}

// Service streaming results
@Service
class OrderService(private val repo: OrderRepository) {

    fun streamUserOrders(userId: Long): Flow<Order> =
        repo.findAllByUserId(userId)
            .filter { it.status != OrderStatus.CANCELLED }
            .map { it.toSummary() }
}

// Controller returning a Flow - Spring streams the response
@GetMapping("/stream", produces = [MediaType.TEXT_EVENT_STREAM_VALUE])
fun streamOrders(@RequestParam userId: Long): Flow<OrderSummary> =
    service.streamUserOrders(userId)
```

### Coroutine-Aware Transactions

`@Transactional` works with `suspend` functions in Spring Boot 3.5+:

```kotlin
@Service
class OrderService(
    private val orderRepo: OrderRepository,
    private val inventoryRepo: InventoryRepository,
) {

    @Transactional
    suspend fun placeOrderWithInventory(request: PlaceOrderRequest): Order {
        val order = orderRepo.save(Order(userId = request.userId))

        // Both run in the same transaction - if inventoryRepo.reserve throws, order is rolled back
        inventoryRepo.reserve(request.items)

        return order
    }
}
```

### coroutineScope vs supervisorScope

| Scope             | Child failure behavior                              | Use When                                                    |
| ----------------- | --------------------------------------------------- | ----------------------------------------------------------- |
| `coroutineScope`  | One child failure cancels all siblings and rethrows | All operations are required; partial failure = full failure |
| `supervisorScope` | Each child fails independently; siblings continue   | Optional operations; collect partial results                |

```kotlin
// coroutineScope: all-or-nothing - if ANY child throws, siblings are cancelled
suspend fun getDashboard(userId: Long): Dashboard = coroutineScope {
    val user = async { userService.findUser(userId) }       // required
    val orders = async { orderService.getRecentOrders(userId) } // required

    Dashboard(user = user.await(), orders = orders.await())
    // If userService throws, orderService is cancelled and exception propagates
}

// supervisorScope: best-effort - collect what succeeds, tolerate failures
suspend fun getEnrichedProfile(userId: Long): Profile = supervisorScope {
    val user = async { userService.findUser(userId) }               // required
    val recommendations = async { recommendationService.get(userId) } // optional

    val recs = try {
        recommendations.await()
    } catch (e: Exception) {
        emptyList() // fallback - recommendation failure doesn't break the profile
    }

    Profile(user = user.await(), recommendations = recs)
}
```

### CoroutineScope Bean for Background Work

Spring beans that need to launch fire-and-forget work (events, notifications) require a managed `CoroutineScope` that shuts down cleanly with the application:

```kotlin
@Configuration
class CoroutineConfig {

    @Bean
    fun applicationScope(): CoroutineScope =
        CoroutineScope(
            SupervisorJob() +
            Dispatchers.Default +
            CoroutineExceptionHandler { _, throwable ->
                log.error("Unhandled coroutine exception", throwable)
            }
        )

    @Bean
    fun cleanupOnShutdown(scope: CoroutineScope): DisposableBean = DisposableBean {
        scope.cancel()
    }
}

// Usage: inject the scope for background work
@Service
class OrderEventPublisher(
    private val scope: CoroutineScope,
    private val notificationService: NotificationService,
) {

    fun publishOrderCreated(order: Order) {
        scope.launch {
            // fire-and-forget - failure is logged by CoroutineExceptionHandler, not propagated
            notificationService.sendOrderConfirmation(order)
        }
    }
}

// Bad: GlobalScope - leaks on shutdown, no error handling
fun publishOrderCreated(order: Order) {
    GlobalScope.launch { notificationService.sendOrderConfirmation(order) }
}
```

### Timeout and Retry Patterns

```kotlin
// Timeout: use withTimeout for time-bounded operations
suspend fun fetchProductWithTimeout(id: String): Product =
    withTimeout(Duration.ofSeconds(5).toMillis()) {
        externalApiClient.fetchProduct(id)
    }

// Retry with exponential backoff
suspend fun <T> retryWithBackoff(
    maxRetries: Int = 3,
    initialDelay: Long = 100,
    maxDelay: Long = 2000,
    block: suspend () -> T,
): T {
    var currentDelay = initialDelay
    repeat(maxRetries - 1) {
        try {
            return block()
        } catch (e: Exception) {
            delay(currentDelay)
            currentDelay = (currentDelay * 2).coerceAtMost(maxDelay)
        }
    }
    return block() // last attempt - let exception propagate
}

// Usage
suspend fun fetchWithRetry(id: String): Product =
    retryWithBackoff(maxRetries = 3) {
        withTimeout(3_000) {
            externalApiClient.fetchProduct(id)
        }
    }
```

### WebClient with Coroutines

```kotlin
@Service
class ExternalApiClient(private val webClient: WebClient) {

    suspend fun fetchProduct(id: String): Product =
        webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .awaitBody<Product>() // suspend - no blocking

    suspend fun fetchWithFullResponse(id: String): ResponseEntity<Product> =
        webClient.get()
            .uri("/products/{id}", id)
            .awaitExchange { response ->
                if (response.statusCode().is2xxSuccessful) {
                    ResponseEntity.ok(response.awaitBody<Product>())
                } else {
                    ResponseEntity.status(response.statusCode()).build()
                }
            }
}
```

### Dispatchers Usage with Virtual Threads

Spring Boot 3.2+ enables Virtual Threads by default (`spring.threads.virtual.enabled=true`). With Virtual Threads active:

| Dispatcher            | When to Use                                                        |
| --------------------- | ------------------------------------------------------------------ |
| _(none - default)_    | I/O operations with Virtual Threads enabled (safe on VT)           |
| `Dispatchers.Default` | CPU-bound work only (image processing, crypto, heavy computation)  |
| `Dispatchers.IO`      | Only when Virtual Threads are NOT active and you have blocking I/O |

```kotlin
// Good: let Virtual Threads handle I/O automatically - no Dispatchers.IO needed
suspend fun fetchData(): Data {
    return repo.findAll() // blocking JDBC call is safe on Virtual Thread
}

// Good: Dispatchers.Default only for CPU-bound work
suspend fun processImage(bytes: ByteArray): ByteArray =
    withContext(Dispatchers.Default) {
        runImageProcessing(bytes) // CPU-intensive
    }

// Bad: redundant Dispatchers.IO when Virtual Threads are active
suspend fun fetchData(): Data =
    withContext(Dispatchers.IO) { // unnecessary - Virtual Thread already handles this
        repo.findAll()
    }
```

## Edge Cases

**Mixed blocking and coroutine codebases**: When a project has both blocking (JDBC/JPA) and coroutine-based (R2DBC) code paths, keep them in separate service classes. Do not mix `suspend` and blocking calls in the same service without explicit dispatcher management.

**Spring `@Scheduled` with coroutines**: `@Scheduled` methods cannot be `suspend`. Use a `CoroutineScope` bean:

```kotlin
@Component
class ScheduledTasks(private val scope: CoroutineScope, private val service: OrderService) {

    @Scheduled(fixedRate = 60_000)
    fun cleanupExpiredOrders() {
        scope.launch { service.cleanupExpired() }
    }
}
```

**Exception handling in Flow**: Exceptions thrown inside `Flow.collect` violate exception transparency. Use the `catch` operator before `collect`:

```kotlin
// Bad: throwing inside collect violates exception transparency
flow.collect { value ->
    if (value.isInvalid()) throw ValidationException("invalid") // breaks Flow contract
}

// Good: catch operator before collect
flow
    .onEach { value -> if (value.isInvalid()) throw ValidationException("invalid") }
    .catch { e -> log.error("Flow error", e) }
    .collect { value -> process(value) }
```

**Spring WebMVC vs WebFlux**: `suspend` controllers work in both WebMVC and WebFlux. With WebMVC + Virtual Threads, `suspend` functions still work but the performance benefit is marginal since VTs already handle I/O efficiently. Choose `suspend` when the service layer genuinely benefits from structured concurrency (parallel fan-out, timeouts), not just because it's available.

**Cancellation and cleanup**: When a coroutine is cancelled (e.g., HTTP client disconnects), cleanup code in `finally` blocks runs but cannot call other suspend functions unless wrapped in `withContext(NonCancellable)`:

```kotlin
suspend fun processOrder(id: Long) {
    try {
        orderService.process(id)
    } finally {
        withContext(NonCancellable) {
            auditService.logCompletion(id) // suspend call in finally needs NonCancellable
        }
    }
}
```

## Output Format

```
## Coroutine Design

### Suspend Boundaries
| Layer | Method | suspend? | Rationale |
|-------|--------|----------|-----------|
| Controller | {method} | {yes/no} | {why} |
| Service | {method} | {yes/no} | {why} |
| Repository | {method} | {yes/no} | {why} |

### Scope Decisions
| Operation | Scope Type | Rationale |
|-----------|------------|-----------|
| {operation} | {coroutineScope / supervisorScope / applicationScope bean} | {why} |

### Dispatcher Configuration
- Virtual Threads active: {yes / no}
- Dispatchers.IO usage: {none / justified locations}
- Dispatchers.Default usage: {CPU-bound locations}

### Warnings
- {any edge cases or anti-patterns found}
```

## Avoid

- `GlobalScope` - always use `coroutineScope { }` or a managed scope bean
- `runBlocking` in request handlers or service beans
- Blocking calls inside coroutines without `withContext(Dispatchers.IO)` (when not using Virtual Threads)
- `Dispatchers.IO` when Virtual Threads are active (Spring Boot 3.2+)
- Mixing `suspend` and blocking calls in the same service class without explicit dispatcher management
- Forgetting `withContext(NonCancellable)` for suspend cleanup in `finally` blocks
- Forgetting to use `coEvery` / `coVerify` in MockK for `suspend` function mocks
