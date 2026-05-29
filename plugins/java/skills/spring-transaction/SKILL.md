---
name: spring-transaction
description: "Design Spring @Transactional boundaries: propagation, self-invocation, rollback, read-only, pool exhaustion, AFTER_COMMIT side effects."
metadata:
  category: backend
  tags: [transactions, database, spring, consistency]
user-invocable: false
---

# Transaction Management

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Defining DB consistency boundaries on the service layer
- Diagnosing connection-pool exhaustion or "transaction not rolling back" bugs
- Coordinating multi-step writes plus side effects (Kafka, HTTP, email)

## Rules

- `@Transactional` on the service layer only - not controller, not repository
- Default propagation `REQUIRED`; deviate only with a written reason
- `readOnly = true` on query-only methods (skips Hibernate dirty-checking, hints driver)
- Checked exceptions need `rollbackFor` - Spring rolls back only on unchecked by default
- No remote IO (HTTP, broker, email, S3) inside a transaction - it pins the DB connection
- Side effects that must not run on rollback fire from `@TransactionalEventListener(AFTER_COMMIT)`
- Pass IDs across thread boundaries (`@Async`, virtual threads, executors), never managed entities
- Set `timeout` on long methods to bound pool exposure

## Patterns

### Self-invocation bypass

`@Transactional` rides Spring's AOP proxy. `this.method()` calls bypass the proxy - no transaction starts.

```java
// Bad - createWithAudit's @Transactional is ignored
class OrderService {
    Order create(OrderRequest req) { return createWithAudit(req); }
    @Transactional Order createWithAudit(OrderRequest req) { ... }
}

// Good - inject self so the proxy intercepts (or extract to a separate bean)
class OrderService {
    @Lazy private final OrderService self;
    Order create(OrderRequest req) { return self.createWithAudit(req); }
    @Transactional Order createWithAudit(OrderRequest req) { ... }
}
```

Prefer extracting to a collaborator bean when the inner method has a distinct responsibility; self-injection is fine for thin wrappers.

### Remote IO pins the connection pool

A 2-second HTTP call inside `@Transactional` holds a HikariCP connection for 2 seconds. Under load: `HikariPool-1 - Connection is not available`.

```java
// Bad
@Transactional
void placeOrder(OrderRequest req) {
    Order order = orderRepository.save(new Order(req));
    inventoryClient.reserve(order.getId());  // 1-3s HTTP, holds DB conn
    kafkaTemplate.send("orders", order);
}

// Good - narrow tx around DB work; side effects ride AFTER_COMMIT
void placeOrder(OrderRequest req) {
    inventoryClient.reserve(req.itemId(), req.qty());  // pre-tx, no DB conn held
    self.saveOrder(req);
}

@Transactional
void saveOrder(OrderRequest req) {
    Order order = orderRepository.save(new Order(req));
    events.publishEvent(new OrderPlacedEvent(order.getId()));
}

@TransactionalEventListener(phase = AFTER_COMMIT)
void onPlaced(OrderPlacedEvent e) { kafkaTemplate.send("orders", e.orderId()); }
```

If the side effect must survive a crash between commit and publish, use a transactional outbox - see `spring-messaging-patterns`.

Virtual threads (Java 21, Spring Boot 3.5+) do not change this: a parked HTTP call still holds the JDBC connection bound to that thread. Pool sizing matters more, not less.

### Checked exception rollback

```java
// Bad - PaymentException is checked → transaction COMMITS despite the failure
@Transactional
void processPayment(Order order) throws PaymentException { ... }

// Good
@Transactional(rollbackFor = Exception.class)
void processPayment(Order order) throws PaymentException { ... }
```

### Read-only services

`readOnly = true` lets Hibernate skip dirty-check snapshots and signals the JDBC driver/replica router. Apply at class level for query services, override per method for writes.

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

Suspends the outer tx and opens a second DB connection - avoid in tight loops (pool pressure, deadlock risk if both connections write the same row).

### Cross-thread boundaries: pass IDs

```java
// Bad - managed entity handed to another thread → no Session, lazy fields blow up
@Transactional
void process(Long id) {
    Order order = orderRepository.findById(id).orElseThrow();
    asyncService.handle(order);
}

// Good - the async method owns its own transaction
@Transactional
void process(Long id) { asyncService.handle(id); }

@Async @Transactional
void handle(Long orderId) { Order o = orderRepository.findById(orderId).orElseThrow(); ... }
```

Same rule applies to virtual-thread executors and `CompletableFuture` chains.

### Idempotent writes

Unique constraint on the idempotency key is the authoritative barrier; the pre-check is an optimization, the catch handles the race.

```java
@Transactional
PaymentResponse processPayment(PaymentRequest req) {
    return paymentRepository.findByIdempotencyKey(req.idempotencyKey())
        .map(PaymentResponse::from)
        .orElseGet(() -> {
            try { return PaymentResponse.from(paymentRepository.save(Payment.from(req))); }
            catch (DataIntegrityViolationException e) {
                return PaymentResponse.from(
                    paymentRepository.findByIdempotencyKey(req.idempotencyKey()).orElseThrow());
            }
        });
}
```

## Output Format

```
Method: {class.method}
Propagation: {REQUIRED | REQUIRES_NEW | MANDATORY | ...}
Read-Only: {Yes | No}
Rollback: {default | rollbackFor=Exception.class | custom}
Timeout: {seconds | none}
External-IO-In-Tx: {Yes | No}
Post-Commit Hooks: {AFTER_COMMIT events | none}
Reason: {why this configuration}
```

## Avoid

- `@Transactional` on controllers or repositories
- `this.X()` calls to `@Transactional` methods (proxy bypass)
- Remote IO inside a transaction (pool exhaustion)
- Passing managed entities to `@Async`, virtual threads, or executors
- `REQUIRES_NEW` in loops, or without a written reason
- Omitting `timeout` on batch or external-call transactions
