---
name: spring-messaging-patterns
description: "Spring Kafka / RabbitMQ / Application Events: idempotent consumers, DLT/DLQ, transactional outbox, AFTER_COMMIT, webhooks, observability."
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
- Guaranteed delivery that must survive a crash between DB commit and broker publish
- In-process decoupling via Spring Application Events

## Rules

- Consumers idempotent - any message can be redelivered.
- DLT / DLQ configured for every listener; permanent failures excluded from retry.
- Use the **transactional outbox** whenever a publish must atomically follow a DB commit. Never call `send()` inside `@Transactional` without it - rollback leaves phantom events.
- Payloads are records / primitives. Never serialize JPA entities (lazy proxies, schema coupling).
- Manual ack only after successful processing (`enable-auto-commit: false`, `ack-mode: manual_immediate`).
- Catch only retryable exceptions in listeners; let unknowns reach the retry / DLT machinery.
- Propagate trace context across the broker (Micrometer Observation auto-instruments Spring Kafka / Rabbit when `ObservationRegistry` is on the classpath).

## Patterns

### Kafka producer + consumer

```java
@Service @RequiredArgsConstructor
class OrderEventPublisher {
    private final KafkaTemplate<String, OrderPlacedEvent> kafka;

    public CompletableFuture<SendResult<String, OrderPlacedEvent>> publish(OrderPlacedEvent e) {
        return kafka.send("order.placed", e.orderId().toString(), e);  // caller handles failure
    }
}

@Component @RequiredArgsConstructor
class OrderPlacedConsumer {
    private final ProcessedMessages processed;
    private final FulfillmentService fulfillment;

    @RetryableTopic(
        attempts = "3",
        backoff = @Backoff(delay = 1000, multiplier = 2),
        dltStrategy = DltStrategy.FAIL_ON_ERROR,
        exclude = { ValidationException.class, IllegalArgumentException.class })
    @KafkaListener(topics = "order.placed", groupId = "fulfillment")
    public void onOrderPlaced(OrderPlacedEvent e,
                               @Header(KafkaHeaders.RECEIVED_KEY) String key) {
        if (!processed.markProcessed(key)) return;  // unique-PK insert; duplicate = skip
        fulfillment.initiate(e.orderId());
    }

    @DltHandler
    public void dlt(OrderPlacedEvent e) { alerts.notifyOps("fulfillment-dlt", e.orderId()); }
}
```

```yaml
spring:
  threads.virtual.enabled: true           # Boot 3.5: listener containers honor VTs
  kafka:
    consumer:
      auto-offset-reset: earliest
      enable-auto-commit: false
      max-poll-records: 50
    listener:
      ack-mode: manual_immediate
      concurrency: 3
      observation-enabled: true           # emits Micrometer spans + metrics
    producer:
      observation-enabled: true
```

`@RetryableTopic` auto-creates `order.placed-retry-0`, `-retry-1`, `order.placed-dlt`. `exclude` skips retry for non-retryable exceptions and routes them straight to DLT.

### RabbitMQ with DLQ

```java
@Bean Queue fulfillmentQueue() {
    return QueueBuilder.durable("order.fulfillment")
        .withArgument("x-dead-letter-exchange", "order.dlx")
        .withArgument("x-dead-letter-routing-key", "fulfillment.failed")
        .build();
}

@RabbitListener(queues = "order.fulfillment")
public void handle(OrderPlacedEvent e) {
    if (!processed.markProcessed(e.orderId().toString())) return;
    fulfillment.initiate(e.orderId());
}
```

Retry/backoff via `spring.rabbitmq.listener.simple.retry.*`; messages that exhaust retries hit `order.dlx` and land in the DLQ bound to it.

### Transactional outbox

Use when the publish must survive a crash between DB commit and broker ack.

```java
@Entity @Table(name = "outbox_events")
class OutboxEvent {
    @Id @GeneratedValue UUID id;
    String aggregateId;     // partition key
    String topic;
    String eventType;
    String payload;         // JSON
    Instant createdAt;
    boolean published;
}

@Transactional
public void placeOrder(PlaceOrderCommand cmd) {
    Order o = orderRepo.save(Order.from(cmd));
    outboxRepo.save(OutboxEvent.of(o, "order.placed", "OrderPlaced"));
}

// One unpublished event per row, per tx → one failure doesn't block siblings.
// SKIP LOCKED lets multiple instances poll without double-publishing.
@Scheduled(fixedDelay = 1000)
public void drain() {
    for (UUID id : outboxRepo.claimBatch(100)) publishOne(id);
}

@Transactional
public void publishOne(UUID id) {
    OutboxEvent e = outboxRepo.findById(id).orElseThrow();
    kafka.send(e.getTopic(), e.getAggregateId(), e.getPayload()).join();  // fail tx on send error
    e.setPublished(true);
}
```

```sql
-- Native query (JPQL lacks SKIP LOCKED):
SELECT id FROM outbox_events
WHERE published = false
ORDER BY created_at
LIMIT :n FOR UPDATE SKIP LOCKED;
```

### Spring Application Events (in-process, same JVM)

Use `AFTER_COMMIT` so listeners never see uncommitted state. No crash survival - if that matters, use the outbox.

```java
public record OrderCreatedEvent(UUID orderId, BigDecimal total) {}

@Transactional
public Order create(CreateOrderRequest req) {
    Order o = orderRepo.save(Order.from(req));
    events.publishEvent(new OrderCreatedEvent(o.getId(), o.getTotal()));
    return o;
}

@TransactionalEventListener(phase = AFTER_COMMIT)
public void onOrderCreated(OrderCreatedEvent e) { auditService.record(e); }
```

### Webhook handlers

External services (Stripe, GitHub) deliver via HTTP with at-least-once semantics: verify signature, dedupe by event ID, respond 200 fast.

```java
@PostMapping("/webhooks/stripe")
public ResponseEntity<Void> stripe(@RequestBody String raw,
                                    @RequestHeader("Stripe-Signature") String sig) {
    webhooks.verify(raw, sig);
    var event = webhooks.parse(raw);
    if (processed.markProcessed(event.getId())) webhooks.process(event);
    return ResponseEntity.ok().build();
}
```

### Required vs best-effort side effects

A listener may fan out to multiple channels with different durability needs. Let required failures propagate; isolate best-effort.

```java
@TransactionalEventListener(phase = AFTER_COMMIT)
public void onPaymentCompleted(PaymentCompletedEvent e) {
    kafka.send("payment.completed", e.paymentId().toString(), e);   // required - let it throw
    try { sms.send(e.phone(), "Payment confirmed"); }               // best-effort
    catch (Exception ex) { log.warn("SMS failed for {}", e.paymentId(), ex); }
}
```

## Output Format

```
Broker: {Kafka | RabbitMQ | Spring Events}
Topic/Queue: {name}
Producer: {class}
Consumer: {class}
Delivery: {at-least-once | at-most-once | exactly-once via outbox}
Idempotency: {dedup key + storage}
DLT/DLQ: {topic/queue name | not needed - reason}
Retry: {attempts, backoff, excluded exceptions}
Observability: {observation-enabled | manual instrumentation | n/a}
```

## Avoid

- Publishing inside `@Transactional` without the outbox (phantom events on rollback).
- JPA entities as payloads.
- Swallowing all exceptions in a consumer (defeats retry / DLT).
- Logging-only failure handling on producer futures (`whenComplete` that only logs loses messages silently - use the outbox or propagate).
