---
name: kotlin-spring-transaction
description: Spring @Transactional scope, propagation levels, and common pitfalls in Kotlin covering read-only optimization, self-invocation proxy bypass, checked exception rollback, transaction timeout, and coroutine-aware @Transactional with suspend functions.
metadata:
  category: backend
  tags: [kotlin, transactions, database, spring, consistency, coroutines]
user-invocable: false
---

# Kotlin Transaction Management

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Managing consistency boundaries for database operations in Kotlin/Spring
- Coordinating multiple operations that must succeed together
- Controlling transaction scope and propagation
- Ensuring atomicity for payment processing or state machine transitions
- Wrapping `suspend` service methods with `@Transactional` (Spring Boot 3.x supports it)

## Rules

- Transactions only in service layer
- Avoid `@Transactional` on controller
- Avoid nested transactions
- Default propagation is REQUIRED
- Use REQUIRES_NEW only when justified
- One transaction per use case, avoid long-running transactions
- Use `readOnly = true` for query-only operations
- Rollback on runtime exception only (Kotlin has no checked exceptions, but Java collaborators do)
- Configure `kotlin("plugin.spring")` so `@Transactional` classes can be proxied (otherwise the class is `final` and CGLIB cannot subclass it)

## Patterns

### Keep External I/O Out of Transactions

A transactional method holds a database connection (and often row locks) for its entire duration. If the method calls an external HTTP API, message broker, or any slow I/O *inside* the transaction, the connection is held for that round-trip - leading to connection pool exhaustion, lock contention, and retry storms that produce duplicate side effects (e.g. double charges if the HTTP client retries on timeout while the transaction is still open).

```kotlin
// Bad: external HTTP call inside the transaction. Connection held for the network round-trip.
// On timeout-then-retry the gateway can charge twice while we're still committing the first attempt.
@Transactional
fun placeOrder(req: OrderRequest): Order {
    val order = orderRepo.save(Order.from(req))
    paymentGateway.charge(order)              // external call - DO NOT do this inside @Transactional
    order.status = PaymentStatus.PAID
    return orderRepo.save(order)
}

// Good: split the work so the external call happens outside the DB transaction.
// The transactional methods are short and only touch the database.
fun placeOrder(req: OrderRequest): Order {
    val order = createPending(req)            // tx 1: persist PENDING
    val receipt = paymentGateway.charge(order) // no transaction - long-running, can timeout/retry safely
    return markPaid(order.id, receipt)        // tx 2: persist PAID with receipt
}

@Transactional
internal fun createPending(req: OrderRequest): Order = orderRepo.save(Order.from(req))

@Transactional
internal fun markPaid(orderId: Long, receipt: Receipt): Order { ... }
```

Pair this split with idempotency (next pattern) and `@TransactionalEventListener(phase = AFTER_COMMIT)` (see `kotlin-spring-async-processing`) when the side effect must fire only after commit.

### Transaction Scope

Bad - Transactions in controller, nested:

```kotlin
@RestController
class OrderController(private val orderRepository: OrderRepository) {
    @PostMapping
    @Transactional
    fun create(@RequestBody req: OrderRequest): Order {
        val order = Order(req)
        return orderRepository.save(order) // Nested transaction
    }
}
```

Good - Transaction in service layer:

```kotlin
@Service
class OrderService(private val orderRepository: OrderRepository) {
    @Transactional
    fun create(req: OrderRequest): Order {
        val order = Order(req)
        return orderRepository.save(order)
    }
}
```

### `@Transactional` Visibility Requirements

Spring's CGLIB proxy can only intercept method calls it can override. That excludes:

- `private` and `protected` functions
- `final` functions and classes (use `kotlin("plugin.spring")` to mark `@Service`/`@Component`/`@Transactional` classes open automatically)
- Top-level functions (no class to proxy)

Kotlin's `internal` modifier compiles to `public` on the JVM, so it works with `@Transactional` - but be aware it's still callable from any module. Keep transactional methods `public` (or `internal`) and on a Spring-managed bean.

If `@Transactional` "doesn't seem to do anything", check visibility first, then check for self-invocation (next).

### Self-Invocation Proxy Bypass

`@Transactional` works via Spring's AOP proxy. Calling a `@Transactional` method from **within the same class** bypasses the proxy - no transaction is started:

```kotlin
// Bad: self-invocation - @Transactional on createWithAudit is ignored
@Service
class OrderService(private val orderRepo: OrderRepository) {
    fun create(req: OrderRequest): Order = createWithAudit(req) // calls directly, NOT through proxy

    @Transactional
    fun createWithAudit(req: OrderRequest): Order { /* ... */ }
}

// Good: extract to a separate Spring bean so the proxy intercepts
@Service
class OrderService(private val auditService: OrderAuditService) {
    fun create(req: OrderRequest): Order = auditService.createWithAudit(req) // goes through proxy
}
```

### REQUIRES_NEW for Isolated Side Effects

`REQUIRES_NEW` suspends the outer transaction and runs the method in its own transaction. Use it for audit logs or notifications that must commit regardless of whether the outer transaction rolls back:

```kotlin
@Service
class AuditService(private val auditRepo: AuditRepository) {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    fun logAction(action: String, entityId: Long) {
        auditRepo.save(AuditLog(action, entityId)) // commits independently
    }
}
```

Caution: REQUIRES_NEW opens a second DB connection - avoid in tight loops or high-throughput paths.

### Exception Rollback (Kotlin / Java Interop)

Kotlin has no checked exceptions, but Java collaborators do. By default, `@Transactional` only rolls back on `RuntimeException` and `Error`. If a Java method throws a checked exception that bubbles up, the transaction commits anyway:

```kotlin
// Bad: Java collaborator throws checked PaymentException - transaction commits despite failure
@Transactional
fun processPayment(order: Order) {
    orderRepo.save(order)
    paymentGateway.charge(order) // Java method declared `throws PaymentException`
}

// Good: explicit rollbackFor ensures rollback on checked exceptions from Java
@Transactional(rollbackFor = [Exception::class])
fun processPayment(order: Order) {
    orderRepo.save(order)
    paymentGateway.charge(order) // PaymentException now triggers rollback
}
```

For pure Kotlin, all exceptions are unchecked, so default rollback rules apply.

### Read-Only Optimization

`readOnly = true` tells Hibernate to skip dirty-checking for all entities loaded in the transaction - meaningful performance gain for read-heavy services:

```kotlin
@Service
@Transactional(readOnly = true) // default for all methods
class OrderQueryService(private val orderRepo: OrderRepository) {

    fun search(spec: Specification<Order>, pageable: Pageable): Page<OrderDto> =
        orderRepo.findAll(spec, pageable).map { OrderDto.from(it) }

    @Transactional // override: read-write for mutations only
    fun updateStatus(id: Long, status: OrderStatus): OrderDto {
        val order = orderRepo.findById(id).orElseThrow()
        order.status = status
        return OrderDto.from(orderRepo.save(order))
    }
}
```

### Idempotent Write with Optimistic Locking

For operations that must be idempotent (e.g., payment processing), combine find-or-create with `@Version` to prevent double-processing. Note the structure: the external `paymentGateway.charge(...)` call is deliberately *outside* any `@Transactional` boundary - the DB writes are split into two short transactions around it.

```kotlin
fun processPayment(req: PaymentRequest): PaymentResponse {
    val pending = reservePending(req) ?: return PaymentResponse.from(loadByKey(req.idempotencyKey))
    val receipt = paymentGateway.charge(pending)        // external call OUTSIDE any transaction
    return PaymentResponse.from(markCompleted(pending.id, receipt))
}

@Transactional
internal fun reservePending(req: PaymentRequest): Payment? {
    paymentRepository.findByIdempotencyKey(req.idempotencyKey)?.let { return null }  // already exists
    return paymentRepository.save(Payment.from(req).copy(status = PaymentStatus.PENDING))
}

@Transactional
internal fun markCompleted(id: Long, receipt: Receipt): Payment { ... }
```

If two concurrent requests arrive with the same idempotency key, the unique constraint on `idempotency_key` prevents double-insert. Catch `DataIntegrityViolationException` and re-fetch:

```kotlin
@Transactional
fun processPayment(req: PaymentRequest): PaymentResponse =
    try {
        doProcess(req)
    } catch (e: DataIntegrityViolationException) {
        // Concurrent insert won - return the existing record
        paymentRepository.findByIdempotencyKey(req.idempotencyKey)
            ?.let { PaymentResponse.from(it) }
            ?: throw PaymentGatewayException("Unexpected conflict", e)
    }
```

### Transaction Timeout

Set timeouts to prevent long-running transactions from holding database locks and connections. The default is no timeout, which risks connection pool exhaustion:

```kotlin
@Transactional(timeout = 10) // 10 seconds - fail fast if query or lock wait exceeds this
fun processBatch(orders: List<Order>) {
    orders.forEach { processOrder(it) }
}
```

### `@Transactional` with `suspend` Functions

Spring Boot 3.x supports `@Transactional` on `suspend` functions. The transaction context is propagated through the coroutine context. Important: do not call blocking JDBC inside a `suspend @Transactional` function unless Virtual Threads are enabled or you wrap in `withContext(Dispatchers.IO)`.

```kotlin
@Service
class OrderService(
    private val orderRepo: OrderRepository,
    private val inventoryRepo: InventoryRepository,
) {
    @Transactional
    suspend fun placeOrderWithInventory(req: PlaceOrderRequest): Order {
        val order = orderRepo.save(Order(userId = req.userId))
        inventoryRepo.reserve(req.items) // both run in same transaction
        return order
    }
}
```

Caveat: switching coroutine contexts inside the transactional method (`withContext(...)`) can break the transaction binding. Keep the transactional `suspend` body on the calling thread/dispatcher.

## Output Format

When applying transaction patterns, document the boundary:

```
Method: {class.method}
Propagation: {REQUIRED | REQUIRES_NEW | ...}
Read-Only: {yes | no}
Rollback: {default | rollbackFor = [Exception::class] | custom}
Timeout: {seconds | none}
Suspend: {yes | no}
Reason: {why this configuration was chosen}
```

## Avoid

- `@Transactional` on controllers or repositories
- External I/O (HTTP calls, message sends, file uploads) inside `@Transactional` - extract them out and use `@TransactionalEventListener(AFTER_COMMIT)` for post-commit side effects
- Long-running transactions (hold locks, exhaust connection pool)
- Mixing read and write operations without `readOnly`
- Calling `@Transactional` methods within the same class (self-invocation - proxy bypass)
- `@Transactional` on `private` or `protected` functions (proxy can't intercept)
- Relying on default rollback behavior when calling Java code that throws checked exceptions
- Omitting timeout on batch-processing or external-call transactions
- `withContext(Dispatchers.IO)` switches inside a `@Transactional suspend` body - can detach from the transaction
- Manual `open` on `@Service` classes - use `kotlin("plugin.spring")`
