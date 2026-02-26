---
name: spring-transaction
description: Transaction scope and propagation management
metadata:
  category: backend
  tags: [transactions, database, spring, consistency]
user-invocable: false
---

# Transaction Management

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

## Avoid

- `@Transactional` on controllers or repositories
- Long-running transactions
- Mixing read and write operations without readOnly
