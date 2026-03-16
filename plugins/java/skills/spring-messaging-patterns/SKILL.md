---
name: spring-messaging-patterns
description: Spring Kafka, RabbitMQ, and Spring Events patterns for reliable async messaging in Spring Boot 3.5+ covering idempotent consumers, dead-letter queues, and the transactional outbox pattern.
metadata:
  category: backend
  tags: [kafka, rabbitmq, spring-events, messaging, async, outbox, idempotency]
user-invocable: false
---

# Spring Messaging Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Publishing or consuming events via Kafka or RabbitMQ in a Spring Boot service
- Replacing synchronous HTTP calls with async messaging for non-critical side effects
- Implementing the transactional outbox pattern for guaranteed delivery
- Using Spring Application Events for in-process decoupling

## Rules

- Consumers must be **idempotent** - messages can be redelivered; check state before acting
- Always configure **dead-letter topics/queues** for messages that exhaust retries
- Use **transactional outbox** (persist event in same DB transaction as business data, publish separately) when at-least-once delivery is required
- Pass IDs and primitive values in message payloads - never serialized JPA entities
- Acknowledge only after successful processing; let exceptions trigger redelivery
- Virtual Thread compatibility: Kafka/RabbitMQ listener thread pools should use Virtual Threads

## Pattern

### Spring Kafka - Producer

```java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {
    private final KafkaTemplate<String, OrderPlacedEvent> kafkaTemplate;

    public void publishOrderPlaced(OrderPlacedEvent event) {
        kafkaTemplate.send("order.placed", event.orderId().toString(), event)
            .whenComplete((result, ex) -> {
                if (ex != null) log.error("Failed to publish OrderPlaced {}", event.orderId(), ex);
            });
    }
}
```

### Spring Kafka - Consumer

```java
@Component
@Slf4j
public class OrderPlacedConsumer {

    @KafkaListener(topics = "order.placed", groupId = "fulfillment-service")
    public void onOrderPlaced(OrderPlacedEvent event, Acknowledgment ack) {
        if (fulfillmentRepo.existsByOrderId(event.orderId())) {
            ack.acknowledge(); // already processed - idempotency check
            return;
        }
        fulfillmentService.initiate(event.orderId());
        ack.acknowledge();
    }
}
```

Kafka consumer config (application.yml):

```yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
      enable-auto-commit: false # manual ack only
      max-poll-records: 50
    listener:
      ack-mode: manual_immediate
      concurrency: 3
```

### RabbitMQ - Consumer

```java
@Component
@RabbitListener(queues = "order.fulfillment")
@Slf4j
public class FulfillmentConsumer {

    public void handle(OrderPlacedEvent event) {
        if (fulfillmentRepo.existsByOrderId(event.orderId())) return; // idempotent
        fulfillmentService.initiate(event.orderId());
    }
}
```

RabbitMQ config with dead-letter exchange:

```java
@Configuration
public class RabbitConfig {

    @Bean
    Queue fulfillmentQueue() {
        return QueueBuilder.durable("order.fulfillment")
            .withArgument("x-dead-letter-exchange", "order.dlx")
            .withArgument("x-dead-letter-routing-key", "fulfillment.failed")
            .build();
    }

    @Bean
    Queue deadLetterQueue() {
        return QueueBuilder.durable("order.fulfillment.dlq").build();
    }
}
```

### Transactional Outbox (Spring + JPA)

```java
@Entity
@Table(name = "outbox_events")
public class OutboxEvent {
    @Id @GeneratedValue UUID id;
    String aggregateType;
    String aggregateId;
    String eventType;
    String payload;       // JSON
    Instant createdAt;
    boolean published;
}

// Save outbox event in the same transaction as business data
@Transactional
public void placeOrder(PlaceOrderCommand cmd) {
    Order order = orderRepo.save(Order.from(cmd));
    outboxRepo.save(OutboxEvent.from(order, "OrderPlaced"));
}

// Scheduled publisher reads unpublished events and publishes to broker
@Scheduled(fixedDelay = 1000)
@Transactional
public void publishOutboxEvents() {
    outboxRepo.findByPublishedFalse().forEach(event -> {
        kafkaTemplate.send(event.eventType(), event.payload());
        event.setPublished(true);
    });
}
```

### Spring Application Events (in-process)

```java
// Event record
public record OrderCreatedEvent(UUID orderId, BigDecimal total) {}

// Publisher
@Service
@RequiredArgsConstructor
public class OrderService {
    private final ApplicationEventPublisher events;

    @Transactional
    public Order create(CreateOrderRequest req) {
        Order order = orderRepo.save(Order.from(req));
        events.publishEvent(new OrderCreatedEvent(order.getId(), order.getTotal()));
        return order;
    }
}

// Listener - runs in same transaction by default
@Component
public class OrderAuditListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        auditService.record(event); // fires after commit, not during
    }
}
```

## Stack-Specific Guidance

- **Kafka**: Use `spring-kafka`, configure `ConcurrentKafkaListenerContainerFactory` with Virtual Thread executor; use `@RetryableTopic` for automatic retry + DLT setup
- **RabbitMQ**: Use `spring-boot-starter-amqp`; configure `SimpleRabbitListenerContainerFactory` with `defaultRequeueRejected(false)` so failures route to DLQ
- **Spring Events**: `@TransactionalEventListener` with `AFTER_COMMIT` phase prevents handlers from running on rolled-back transactions

## Avoid

- `enable-auto-commit: true` on Kafka consumers (messages lost on crash before processing)
- Consumers that perform long-running synchronous DB operations without pagination - use `@KafkaListener` with `batch = true` and `findAllById`
- Publishing events inside `@Transactional` without the outbox pattern (event published, transaction rolls back → phantom event)
- Catching and swallowing all exceptions in a consumer - let retries and DLQ handle failures
- Passing JPA entity objects as message payloads - use dedicated event records with only IDs and primitives
