---
name: spring-async-processing
description: Non-blocking side effects and event handling patterns
metadata:
  category: backend
  tags: [async, threading, events, idempotency]
user-invocable: false
---

# Async Processing

## When to Use

- Non-blocking side effects and background tasks
- Event publication and event-driven workflows
- Long-running operations that don't block user response

## Rules

- Do not use async for core transaction logic
- Avoid async inside transaction unless isolated
- Use managed executor with limited thread pool size
- Async handlers must be idempotent
- Handle async failures explicitly, never swallow exceptions

## Pattern

Bad - Blocking task within transaction:

```java
@Transactional
public void processOrder(Order order) {
    saveOrder(order);
    asyncService.notifyUser(order); // Blocks transaction
}
```

Good - Async execution outside transaction:

```java
@Service
public class OrderService {
    public void processOrder(Order order) {
        Order saved = transactionService.saveOrder(order);
        asyncEventPublisher.publishAsync(new OrderCreatedEvent(saved));
    }
}
```

## Avoid

- Using async for critical transaction logic
- Swallowing exceptions in async handlers
- Unbounded thread pools without sizing
