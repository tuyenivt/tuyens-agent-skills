---
name: spring-messaging-patterns
description: "Spring Kafka / RabbitMQ / Application Events: idempotent consumers, DLT/DLQ, transactional outbox, webhook handlers, AFTER_COMMIT dispatch."
metadata:
  category: backend
  tags: [kafka, rabbitmq, spring-events, messaging, async, outbox, idempotency]
user-invocable: false
---

# Spring Messaging Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Publishing / consuming events via Kafka or RabbitMQ
- Replacing synchronous HTTP with async messaging
- Implementing the transactional outbox for guaranteed delivery
- Spring Application Events for in-process decoupling

## Rules

- Consumers idempotent - messages can be redelivered
- DLT / DLQ configured for messages that exhaust retries
- Use the **transactional outbox** when at-least-once delivery must survive a crash between commit and publish
- Payloads carry IDs and primitive values - never serialized JPA entities
- Manual ack only after successful processing
- Catch only retryable exceptions in the listener; let unknowns reach the retry/DLT machinery

## Patterns

### Spring Kafka

```java
@Service @RequiredArgsConstructor
class OrderEventPublisher {
    private final KafkaTemplate<String, OrderPlacedEvent> kafka;

    public void publishOrderPlaced(OrderPlacedEvent event) {
        kafka.send("order.placed", event.orderId().toString(), event)
            .whenComplete((r, ex) -> {
                if (ex != null) log.error("Publish failed {}", event.orderId(), ex);
            });
    }
}

@Component
@Slf4j
class OrderPlacedConsumer {
    @KafkaListener(topics = "order.placed", groupId = "fulfillment-service")
    public void onOrderPlaced(OrderPlacedEvent event, Acknowledgment ack) {
        if (fulfillmentRepo.existsByOrderId(event.orderId())) {
            ack.acknowledge();  // already processed
            return;
        }
        fulfillmentService.initiate(event.orderId());
        ack.acknowledge();
    }
}
```

```yaml
spring.kafka:
  consumer:
    auto-offset-reset: earliest
    enable-auto-commit: false
    max-poll-records: 50
  listener:
    ack-mode: manual_immediate
    concurrency: 3
```

### `@RetryableTopic` (Kafka)

Creates retry topics + DLT automatically - no manual config:

```java
@Component
class FulfillmentConsumer {
    @RetryableTopic(
        attempts = "3",
        backoff = @Backoff(delay = 1000, multiplier = 2),
        autoCreateTopics = "true",
        dltStrategy = DltStrategy.FAIL_ON_ERROR,
        // Permanent failures skip retries
        exclude = { ValidationException.class, IllegalArgumentException.class })
    @KafkaListener(topics = "order.placed", groupId = "fulfillment-service")
    public void onOrderPlaced(OrderPlacedEvent event,
                               @Header(KafkaHeaders.RECEIVED_KEY) String messageKey) {
        // Canonical idempotency: processed_messages(message_id PK).
        // Redelivery triggers unique-constraint violation - skip silently.
        if (!processedMessages.markProcessed(messageKey)) return;
        fulfillmentService.initiate(event.orderId());
    }

    @DltHandler
    public void handleDlt(OrderPlacedEvent event) {
        log.error("Exhausted retries for order {} - DLT", event.orderId());
        alertService.notifyOps("fulfillment-failure", event.orderId());
    }
}
```

### RabbitMQ with DLQ

```java
@Configuration
class RabbitConfig {
    @Bean
    Queue fulfillmentQueue() {
        return QueueBuilder.durable("order.fulfillment")
            .withArgument("x-dead-letter-exchange", "order.dlx")
            .withArgument("x-dead-letter-routing-key", "fulfillment.failed")
            .build();
    }
    @Bean Queue deadLetterQueue() { return QueueBuilder.durable("order.fulfillment.dlq").build(); }
}

@Component
class FulfillmentConsumer {
    @RabbitListener(queues = "order.fulfillment")
    public void handle(OrderPlacedEvent event) {
        if (fulfillmentRepo.existsByOrderId(event.orderId())) return;
        fulfillmentService.initiate(event.orderId());
    }
}
```

### Transactional outbox

Phantom-event symptom: consumer receives an event whose aggregate row never committed - a broker publish ran inside `@Transactional` and the transaction later rolled back. Fixes:

- **Outbox table** when the event must survive a crash between commit and publish.
- **`@TransactionalEventListener(AFTER_COMMIT)`** for in-process listeners (no crash survival).

```java
@Entity @Table(name = "outbox_events")
class OutboxEvent {
    @Id @GeneratedValue UUID id;
    String aggregateType;
    String aggregateId;   // Kafka partition key
    String topic;
    String eventType;
    String payload;       // JSON
    Instant createdAt;
    boolean published;
}

@Transactional
public void placeOrder(PlaceOrderCommand cmd) {
    Order order = orderRepo.save(Order.from(cmd));
    outboxRepo.save(OutboxEvent.from(order, "orders.events", "OrderPlaced"));
}

// Polling publisher: SKIP LOCKED so multiple instances don't double-publish.
// Each event in its own tx → one failure doesn't block others.
@Scheduled(fixedDelay = 1000)
public void publishOutbox() {
    for (UUID id : outboxRepo.claimBatchForPublish(100)) publishOne(id);
}

@Transactional
public void publishOne(UUID id) {
    OutboxEvent e = outboxRepo.findById(id).orElseThrow();
    kafka.send(e.getTopic(), e.getAggregateId(), e.getPayload());
    e.setPublished(true);  // flushed on commit
}

// Native query - JPQL has no SKIP LOCKED:
//   SELECT id FROM outbox_events WHERE published = false
//   ORDER BY created_at LIMIT :n FOR UPDATE SKIP LOCKED
```

### Spring Application Events (in-process)

```java
public record OrderCreatedEvent(UUID orderId, BigDecimal total) {}

@Service @RequiredArgsConstructor
class OrderService {
    private final ApplicationEventPublisher events;

    @Transactional
    public Order create(CreateOrderRequest req) {
        Order order = orderRepo.save(Order.from(req));
        events.publishEvent(new OrderCreatedEvent(order.getId(), order.getTotal()));
        return order;
    }
}

@Component
class OrderAuditListener {
    @TransactionalEventListener(phase = AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent e) { auditService.record(e); }
}
```

### Webhook handlers

External services (Stripe, GitHub) push via webhooks - process them like message consumers, with signature validation + idempotency:

```java
@RestController @RequestMapping("/webhooks") @RequiredArgsConstructor
class StripeWebhookController {
    private final StripeWebhookService webhookService;

    @PostMapping("/stripe")
    public ResponseEntity<Void> handle(@RequestBody String rawBody,
                                        @RequestHeader("Stripe-Signature") String signature) {
        webhookService.verifySignature(rawBody, signature);
        var event = webhookService.parse(rawBody);
        if (webhookService.isProcessed(event.getId())) return ResponseEntity.ok().build();
        webhookService.process(event);
        return ResponseEntity.ok().build();
    }
}
```

Store processed event IDs with a unique constraint - Stripe retries failed deliveries up to 3 days.

### Required vs optional notifications

Required notifications must propagate failures (Kafka publish, durable broker). Best-effort notifications (SMS, push) catch and log:

```java
@TransactionalEventListener(phase = AFTER_COMMIT)
public void onPaymentCompleted(PaymentCompletedEvent e) {
    kafka.send("payment.completed", e.paymentId().toString(), e);  // required
    try {
        notificationService.sendSms(e.userPhone(), "Payment confirmed");
    } catch (Exception ex) {
        log.warn("Optional SMS failed for payment {}", e.paymentId(), ex);
    }
}
```

## Output Format

```
Broker: {Kafka | RabbitMQ | Spring Events}
Topic/Queue: {name}
Producer: {class}
Consumer: {class}
Delivery: {at-least-once | at-most-once | exactly-once via outbox}
Idempotency: {how duplicates are detected}
DLT/DLQ: {configured | not needed - reason}
Retry: {attempts, backoff}
```

## Avoid

- `enable-auto-commit: true` on Kafka (loses messages on crash)
- Publishing inside `@Transactional` without the outbox (phantom events on rollback)
- JPA entities as message payloads
- Swallowing all exceptions in a consumer (defeats retry / DLT)
