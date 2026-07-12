---
name: kotlin-spring-transaction
description: Kotlin / Spring @Transactional patterns: scope, propagation, self-invocation proxy bypass, rollback rules, coroutine-aware tx with suspend functions.
metadata:
  category: backend
  tags: [kotlin, transactions, database, spring, consistency, coroutines]
user-invocable: false
---

# Kotlin Transaction Management

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Managing transaction boundaries in Kotlin / Spring services
- Coordinating multi-step writes that must succeed together
- Wrapping `suspend` service methods with `@Transactional`

## Rules

- `@Transactional` on services only. Never on controllers or repositories.
- One transaction per use case. Keep short - no external I/O inside.
- `readOnly = true` for query-only paths.
- `rollbackFor = [Exception::class]` when Java collaborators throw checked exceptions (Kotlin has none).
- `kotlin("plugin.spring")` configured - otherwise `@Transactional` classes are `final` and CGLIB can't proxy them.
- `@Transactional` on `private` / `protected` / `final` / top-level functions is silently ignored.
- Self-invocation (`this.method()` from same bean) bypasses the proxy and the annotation does nothing.
- Inside `@Transactional suspend`, do not switch dispatchers via `withContext` - writes on the new dispatcher escape the transaction.

## Patterns

### Keep external I/O out of transactions

External calls hold the DB connection (and any row locks) through the network round-trip. On timeout/retry the side effect can fire twice (e.g. double-charge):

```kotlin
// Bad - Stripe call inside the transaction
@Transactional
fun placeOrder(req: OrderRequest): Order {
    val order = orderRepo.save(Order.from(req))
    paymentGateway.charge(order)               // external call - DO NOT do this here
    return orderRepo.save(order.copy(status = PAID))
}

// Good - split around the external call; TX methods live in a SEPARATE bean
// (same-class calls would self-invoke past the proxy - see next section)
@Service
class OrderProcessor(private val tx: OrderTxService, private val paymentGateway: PaymentGateway) {
    fun placeOrder(req: OrderRequest): Order {
        val order = tx.createPending(req)          // tx 1
        val receipt = paymentGateway.charge(order) // no transaction
        return tx.markPaid(order.id, receipt)      // tx 2
    }
}

@Service
class OrderTxService(private val orderRepo: OrderRepository) {
    @Transactional fun createPending(req: OrderRequest): Order = orderRepo.save(Order.from(req))
    @Transactional fun markPaid(id: Long, receipt: Receipt): Order = ...
}
```

Ordering depends on whether a failed external call may leave a persisted row:
- **No row may survive failure** (e.g. order must not exist if the charge fails): run the external call first, persist only on success.
- **A durable record is needed before the call** (audit trail, idempotency key, retry bookkeeping): persist a pending row in tx 1, call externally, then commit the outcome in tx 2 - the pending row is reconciled by a sweeper or the idempotency check on retry.

Pair with idempotency (next pattern) and `@TransactionalEventListener(AFTER_COMMIT)` (see `kotlin-spring-async-processing`) when a side effect must fire only after commit. When an external call sits in an idempotent flow, the idempotency pre-check and the committing write are `@Transactional`; the external call runs between them in a non-transactional orchestrator.

### Self-invocation bypass

```kotlin
// Bad - direct call, proxy bypassed; @Transactional ignored
@Service
class OrderService(private val orderRepo: OrderRepository) {
    fun create(req: OrderRequest): Order = createWithAudit(req)

    @Transactional
    fun createWithAudit(req: OrderRequest): Order { ... }
}

// Good - extract to a separate bean
@Service
class OrderService(private val auditService: OrderAuditService) {
    fun create(req: OrderRequest): Order = auditService.createWithAudit(req)
}
```

### `REQUIRES_NEW` for independent side effects

Audit / notification that must commit regardless of outer rollback:

```kotlin
@Service
class AuditService(private val repo: AuditRepository) {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    fun logAction(action: String, entityId: Long) = repo.save(AuditLog(action, entityId))
}
```

Opens a second DB connection. Avoid in tight loops.

### Rollback on checked exceptions from Java

Default rollback fires only on `RuntimeException` / `Error`. Java collaborators throwing checked exceptions commit despite failure:

```kotlin
@Transactional(rollbackFor = [Exception::class])
fun processPayment(order: Order) {
    orderRepo.save(order)
    paymentGateway.charge(order)    // Java method declared `throws PaymentException`
}
```

### Read-only services

```kotlin
@Service
@Transactional(readOnly = true)               // default: read-only
class OrderService(private val repo: OrderRepository) {
    fun search(spec: Specification<Order>, pageable: Pageable): Page<OrderDto> = ...

    @Transactional                            // override: write
    fun updateStatus(id: Long, status: OrderStatus): OrderDto = ...
}
```

### Idempotent writes

Unique constraint on the idempotency key is the authoritative barrier; the pre-check is an optimization, the catch handles the race. `runCatching` swallows `CancellationException` and is too broad - use try/catch with the explicit exception type:

```kotlin
@Transactional
fun processPayment(req: PaymentRequest): PaymentResponse {
    paymentRepository.findByIdempotencyKey(req.idempotencyKey)
        ?.let { return PaymentResponse.from(it) }

    return try {
        // saveAndFlush: plain save() defers the INSERT to commit - the violation
        // would surface after this block and the catch would never fire
        PaymentResponse.from(paymentRepository.saveAndFlush(Payment.from(req)))
    } catch (e: DataIntegrityViolationException) {
        PaymentResponse.from(
            paymentRepository.findByIdempotencyKey(req.idempotencyKey)
                ?: throw e
        )
    }
}
```

Same shape applies to find-or-create on a natural key (email, slug). The unique index is what makes this safe under concurrent insert; without it the catch never fires and you get duplicates.

### Transaction timeout

```kotlin
@Transactional(timeout = 10)        // seconds; fail fast on lock wait
fun processBatch(orders: List<Order>) = ...
```

Default is no timeout - risks connection pool exhaustion under contention.

### `@Transactional` on `suspend`

Works in Spring Boot 3.x. With JPA/JDBC the transaction binds to the thread that enters the method (ThreadLocal resources) - which is why dispatcher switches break it; with R2DBC it rides the coroutine context and survives them (see `kotlin-coroutines-spring`).

```kotlin
@Transactional
suspend fun placeOrderWithInventory(req: PlaceOrderRequest): Order {
    val order = orderRepo.save(Order(userId = req.userId))
    inventoryRepo.reserve(req.items)
    return order
}
```

**No `withContext(...)` inside** - the new dispatcher has no transaction attached and writes there escape the transaction. If the work needs a dispatcher switch or an external call, the transactional method should not be `suspend`: keep a `suspend` non-transactional coordinator that does the I/O, and delegate the DB-only writes to a separate blocking `@Transactional` bean.

## Output Format

```
Method: {class.method}
Propagation: {REQUIRED | REQUIRES_NEW | ...}
Read-Only: {yes | no}
Rollback: {default | rollbackFor = [Exception::class] | custom}
Timeout: {seconds | none}
Suspend: {yes | no}
Reason: {why}
```

## Avoid

- `@Transactional` on controllers, repositories, `private` / `protected` / `final` methods
- External I/O inside `@Transactional` - extract or use `@TransactionalEventListener(AFTER_COMMIT)`
- Self-invocation - extract to a separate bean
- Long-running transactions
- Mixing reads and writes without `readOnly = true`
- Default rollback when Java collaborators throw checked exceptions
- `withContext` switches inside `@Transactional suspend` bodies
- Manual `open` on `@Service` - use `kotlin("plugin.spring")`
