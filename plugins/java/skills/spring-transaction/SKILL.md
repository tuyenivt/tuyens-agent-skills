---
name: spring-transaction
description: Spring @Transactional scope, propagation levels, and common pitfalls covering read-only optimization, self-invocation proxy bypass, checked exception rollback, and transaction timeout.
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

## Pattern

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

## Common Pitfalls

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

### Transaction Timeout

Set timeouts to prevent long-running transactions from holding database locks and connections. The default is no timeout, which risks connection pool exhaustion:

```java
@Transactional(timeout = 10) // 10 seconds - fail fast if query or lock wait exceeds this
public void processBatch(List<Order> orders) {
    orders.forEach(this::processOrder);
}
```

## Avoid

- `@Transactional` on controllers or repositories
- Long-running transactions (hold locks, exhaust connection pool)
- Mixing read and write operations without readOnly
- Calling `@Transactional` methods within the same class (self-invocation - proxy bypass)
- Relying on default rollback behavior when calling code that throws checked exceptions
- Omitting timeout on batch-processing or external-call transactions
