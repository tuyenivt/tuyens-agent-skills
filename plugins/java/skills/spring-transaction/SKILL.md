---
name: spring-transaction
description: "Spring @Transactional scope, propagation, pitfalls: read-only optimization, self-invocation proxy bypass, checked exception rollback, timeout."
metadata:
  category: backend
  tags: [transactions, database, spring, consistency]
user-invocable: false
---

# Transaction Management

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Managing consistency boundaries for database operations
- Coordinating multiple operations that must succeed together
- Controlling transaction scope and propagation
- Ensuring atomicity for payment processing or state machine transitions

## Rules

- Transactions only in service layer
- Avoid `@Transactional` on controller
- Avoid nested transactions
- Default propagation is REQUIRED
- Use REQUIRES_NEW only when justified
- One transaction per use case, avoid long-running transactions
- Use `readOnly=true` for query-only operations
- Rollback on runtime exception only
- Explicit rollback rules for checked exceptions
- No remote IO (HTTP, broker publish, email) inside `@Transactional` - it holds the DB connection for the IO duration and exhausts the pool under load
- Side effects that must not run on rollback (events, emails, broker publishes) fire from `@TransactionalEventListener(AFTER_COMMIT)`, not from inside the transactional method
- `@Async` methods do not inherit the caller's transaction; pass identifiers, not managed entities

## Patterns

### Transaction Scope

Bad - Transactions in controller, nested:

```java
@RestController
public class OrderController {
    @PostMapping
    @Transactional
    public Order create(OrderRequest req) {
        Order order = new Order(req);
        return orderRepository.save(order); // Nested transaction
    }
}
```

Good - Transaction in service layer:

```java
@Service
public class OrderService {
    @Transactional
    public Order create(OrderRequest req) {
        Order order = new Order(req);
        return orderRepository.save(order);
    }
}
```

### Self-Invocation Proxy Bypass

`@Transactional` works via Spring's AOP proxy. Calling a `@Transactional` method from **within the same class** bypasses the proxy - no transaction is started:

```java
// Bad: self-invocation - @Transactional on createWithAudit is ignored
@Service
public class OrderService {
    public Order create(OrderRequest req) {
        return createWithAudit(req); // calls directly, NOT through proxy
    }

    @Transactional
    public Order createWithAudit(OrderRequest req) { ... }
}

// Good: extract to a separate Spring bean so the proxy intercepts
@Service
public class OrderService {
    private final OrderAuditService auditService; // injected bean

    public Order create(OrderRequest req) {
        return auditService.createWithAudit(req); // goes through proxy
    }
}
```

### No Remote IO Inside `@Transactional`

A DB connection is held for the duration of the transaction. A 2-second HTTP call inside the transaction holds a connection for 2 seconds; with a Hikari pool of 20 and 30 concurrent requests, the pool is exhausted and new requests block on `HikariPool-1 - Connection is not available`.

```java
// Bad: HTTP call + Kafka publish inside the transaction
@Transactional
public void placeOrder(OrderRequest req) {
    Order order = orderRepository.save(new Order(req));
    inventoryClient.reserve(order.getId());     // 1-3s HTTP - holds DB conn
    kafkaTemplate.send("orders", order);         // also holds DB conn
    emailClient.sendConfirmation(order);          // and again
}
```

```java
// Good: only the DB write is transactional. Side effects ride AFTER_COMMIT.
public Order placeOrder(OrderRequest req) {
    inventoryClient.reserve(req.itemId(), req.qty()); // pre-tx orchestration
    Order order = saveOrder(req);                      // narrow @Transactional below
    return order;
}

@Transactional
Order saveOrder(OrderRequest req) {
    Order order = orderRepository.save(new Order(req));
    events.publishEvent(new OrderPlacedEvent(order.getId())); // dispatched after commit
    return order;
}

@Component
class OrderPostCommit {
    @TransactionalEventListener(phase = AFTER_COMMIT)
    public void onPlaced(OrderPlacedEvent e) {
        kafkaTemplate.send("orders", e.orderId());
        emailClient.sendConfirmation(e.orderId()); // duplicates impossible: tx already committed
    }
}
```

If the side effect must survive a process crash between commit and publish, use the transactional outbox (see `spring-messaging-patterns`).

### `@Async` Crosses the Transaction Boundary

```java
// Bad: passing a managed entity to an async method
@Transactional
public void process(Long id) {
    Order order = orderRepository.findById(id).orElseThrow();
    asyncService.handle(order); // async thread has no Session; LIE on lazy access
}

// Good: pass identifiers, let the async method open its own transaction
@Transactional
public void process(Long id) {
    asyncService.handle(id);
}

@Async
@Transactional
public void handle(Long orderId) {
    Order order = orderRepository.findById(orderId).orElseThrow();
    // ...
}
```

### REQUIRES_NEW for Isolated Side Effects

`REQUIRES_NEW` suspends the outer transaction and runs the method in its own transaction. Use it for audit logs or notifications that must commit regardless of whether the outer transaction rolls back:

```java
@Service
public class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void logAction(String action, Long entityId) {
        auditRepo.save(new AuditLog(action, entityId)); // commits independently
    }
}
```

Caution: REQUIRES_NEW opens a second DB connection - avoid in tight loops or high-throughput paths.

### Checked Exception Rollback

By default, `@Transactional` only rolls back on unchecked exceptions (RuntimeException). Checked exceptions commit the transaction, which is rarely what you want when a checked exception signals a failure:

```java
// Bad: checked exception commits the transaction - partial data persisted
@Transactional
public void processPayment(Order order) throws PaymentException {
    orderRepo.save(order);
    paymentGateway.charge(order); // throws PaymentException (checked) - transaction commits anyway
}

// Good: explicit rollbackFor ensures rollback on checked exceptions
@Transactional(rollbackFor = Exception.class)
public void processPayment(Order order) throws PaymentException {
    orderRepo.save(order);
    paymentGateway.charge(order); // PaymentException now triggers rollback
}
```

### Read-Only Optimization

`readOnly = true` tells Hibernate to skip dirty-checking for all entities loaded in the transaction - meaningful performance gain for read-heavy services:

```java
@Service
@Transactional(readOnly = true) // default for all methods
@RequiredArgsConstructor
public class OrderQueryService {

    public Page<OrderDto> search(Specification<Order> spec, Pageable pageable) {
        return orderRepo.findAll(spec, pageable).map(OrderDto::from);
    }

    @Transactional // override: read-write for mutations only
    public OrderDto updateStatus(Long id, OrderStatus status) {
        Order order = orderRepo.findById(id).orElseThrow();
        order.setStatus(status);
        return OrderDto.from(orderRepo.save(order));
    }
}
```

### Idempotent Write with Optimistic Locking

For operations that must be idempotent (e.g., payment processing), combine find-or-create with `@Version` to prevent double-processing:

```java
@Transactional
public PaymentResponse processPayment(PaymentRequest req) {
    // Idempotency check - return existing if already processed
    var existing = paymentRepository.findByIdempotencyKey(req.idempotencyKey());
    if (existing.isPresent()) {
        return PaymentResponse.from(existing.get());
    }

    Payment payment = Payment.from(req);
    payment = paymentRepository.save(payment);
    paymentGateway.charge(payment); // external call AFTER save
    payment.setStatus(PaymentStatus.COMPLETED);
    return PaymentResponse.from(paymentRepository.save(payment));
}
```

If two concurrent requests arrive with the same idempotency key, the unique constraint on `idempotency_key` prevents double-insert. Catch `DataIntegrityViolationException` and re-fetch:

```java
@Transactional
public PaymentResponse processPayment(PaymentRequest req) {
    try {
        return doProcess(req);
    } catch (DataIntegrityViolationException e) {
        // Concurrent insert won - return the existing record
        return paymentRepository.findByIdempotencyKey(req.idempotencyKey())
            .map(PaymentResponse::from)
            .orElseThrow(() -> new PaymentGatewayException("Unexpected conflict", e));
    }
}
```

### Transaction Timeout

Set timeouts to prevent long-running transactions from holding database locks and connections. The default is no timeout, which risks connection pool exhaustion:

```java
@Transactional(timeout = 10) // 10 seconds - fail fast if query or lock wait exceeds this
public void processBatch(List<Order> orders) {
    orders.forEach(this::processOrder);
}
```

## Output Format

When applying transaction patterns, document the boundary:

```
Method: {class.method}
Propagation: {REQUIRED | REQUIRES_NEW | NESTED | MANDATORY | NEVER | NOT_SUPPORTED | SUPPORTS}
Isolation: {DEFAULT | READ_COMMITTED | REPEATABLE_READ | SERIALIZABLE}
Read-Only: {Yes | No}
Rollback: {default | rollbackFor=Exception.class | custom}
Timeout: {seconds | none}
External-IO-In-Tx: {Yes | No}
Post-Commit Hooks: {AFTER_COMMIT events | none}
Reason: {why this configuration was chosen}
```

## Avoid

- `@Transactional` on controllers or repositories
- Long-running transactions (hold locks, exhaust connection pool)
- Mixing read and write operations without readOnly
- Calling `@Transactional` methods within the same class (self-invocation - proxy bypass)
- Relying on default rollback behavior when calling code that throws checked exceptions
- Omitting timeout on batch-processing or external-call transactions
