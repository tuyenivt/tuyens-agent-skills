---
name: spring-transaction
description: "Spring @Transactional: scope, propagation, self-invocation bypass, rollback rules, read-only, IO-in-tx, AFTER_COMMIT events, timeouts."
metadata:
  category: backend
  tags: [transactions, database, spring, consistency]
user-invocable: false
---

# Transaction Management

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Defining DB consistency boundaries
- Coordinating multi-step writes that must commit/rollback together
- Idempotent writes (payments, state machines)

## Rules

- `@Transactional` lives on the service layer - never controller or repository
- Default propagation `REQUIRED`; `REQUIRES_NEW` only with a written reason
- `readOnly = true` on query-only methods (skips dirty-checking)
- Checked exceptions need explicit `rollbackFor` - default rolls back unchecked only
- No remote IO (HTTP, broker, email) inside a transaction - it holds the DB connection
- Side effects that must not run on rollback fire from `@TransactionalEventListener(AFTER_COMMIT)`
- `@Async` methods do not inherit the caller's transaction - pass IDs, not managed entities
- Set `timeout` on long methods to bound connection-pool exposure

## Patterns

### Self-invocation bypass

`@Transactional` rides Spring's AOP proxy. `this.method()` calls bypass the proxy - no transaction starts.

```java
// Bad - @Transactional on createWithAudit is ignored
@Service
class OrderService {
    Order create(OrderRequest req) { return createWithAudit(req); }
    @Transactional Order createWithAudit(OrderRequest req) { ... }
}

// Good - extract to a separate bean so the proxy intercepts
class OrderService {
    private final OrderAuditService auditService;
    Order create(OrderRequest req) { return auditService.createWithAudit(req); }
}
```

### No remote IO inside `@Transactional`

A 2-second HTTP call holds a HikariCP connection for 2 seconds. Under load the pool exhausts and requests block on `HikariPool-1 - Connection is not available`.

```java
// Bad
@Transactional
void placeOrder(OrderRequest req) {
    Order order = orderRepository.save(new Order(req));
    inventoryClient.reserve(order.getId());  // 1-3s HTTP, holds DB conn
    kafkaTemplate.send("orders", order);     // also holds DB conn
}

// Good - only DB work transactional; side effects ride AFTER_COMMIT
void placeOrder(OrderRequest req) {
    inventoryClient.reserve(req.itemId(), req.qty());  // pre-tx
    saveOrder(req);                                     // narrow tx below
}

@Transactional
void saveOrder(OrderRequest req) {
    Order order = orderRepository.save(new Order(req));
    events.publishEvent(new OrderPlacedEvent(order.getId()));
}

@TransactionalEventListener(phase = AFTER_COMMIT)
void onPlaced(OrderPlacedEvent e) {
    kafkaTemplate.send("orders", e.orderId());
}
```

If the side effect must survive a crash between commit and publish, use the transactional outbox - see `spring-messaging-patterns`.

### `@Async` crosses the transaction boundary

```java
// Bad - managed entity touched on a thread with no Session → LIE on lazy access
@Transactional
void process(Long id) {
    Order order = orderRepository.findById(id).orElseThrow();
    asyncService.handle(order);
}

// Good - pass ID; async opens its own transaction
@Transactional
void process(Long id) { asyncService.handle(id); }

@Async @Transactional
void handle(Long orderId) { Order o = orderRepository.findById(orderId).orElseThrow(); ... }
```

### Checked exception rollback

```java
// Bad - PaymentException is checked → transaction COMMITS despite the failure
@Transactional
void processPayment(Order order) throws PaymentException {
    orderRepo.save(order);
    paymentGateway.charge(order);
}

// Good
@Transactional(rollbackFor = Exception.class)
void processPayment(Order order) throws PaymentException { ... }
```

### Read-only services

```java
@Service @Transactional(readOnly = true) @RequiredArgsConstructor
class OrderQueryService {
    public Page<OrderDto> search(Specification<Order> spec, Pageable p) {
        return orderRepo.findAll(spec, p).map(OrderDto::from);
    }

    @Transactional  // override for writes
    public OrderDto updateStatus(Long id, OrderStatus s) { ... }
}
```

### `REQUIRES_NEW` for isolated side effects

Audit/notification rows that must commit even if the outer transaction rolls back:

```java
@Transactional(propagation = REQUIRES_NEW)
void logAction(String action, Long entityId) { auditRepo.save(...); }
```

Opens a second DB connection - avoid in tight loops.

### Idempotent writes

```java
@Transactional
PaymentResponse processPayment(PaymentRequest req) {
    return paymentRepository.findByIdempotencyKey(req.idempotencyKey())
        .map(PaymentResponse::from)
        .orElseGet(() -> {
            try {
                Payment p = paymentRepository.save(Payment.from(req));
                paymentGateway.charge(p);
                p.setStatus(COMPLETED);
                return PaymentResponse.from(paymentRepository.save(p));
            } catch (DataIntegrityViolationException e) {
                // concurrent insert won - re-fetch
                return PaymentResponse.from(
                    paymentRepository.findByIdempotencyKey(req.idempotencyKey()).orElseThrow());
            }
        });
}
```

Unique constraint on `idempotency_key` is the authoritative barrier; the pre-check is just an optimization.

## Output Format

```
Method: {class.method}
Propagation: {REQUIRED | REQUIRES_NEW | ...}
Read-Only: {Yes | No}
Rollback: {default | rollbackFor=Exception.class | custom}
Timeout: {seconds | none}
External-IO-In-Tx: {Yes | No}
Post-Commit Hooks: {AFTER_COMMIT events | none}
Reason: {why this configuration}
```

## Avoid

- `@Transactional` on controllers or repositories
- Calling `@Transactional` methods via `this.X()` (proxy bypass)
- Holding DB connections through remote calls
- Omitting `timeout` on batch / external-call transactions
