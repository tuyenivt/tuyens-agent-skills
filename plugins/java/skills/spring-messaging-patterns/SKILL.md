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
- Replacing synchronous HTTP with async messaging - only when the caller does not need the result in-request; if it does, keep HTTP or use request-reply with a correlation ID (these patterns are fire-and-forget/event flows)
- Guaranteed delivery that must survive a crash between DB commit and broker publish
- In-process decoupling via Spring Application Events

## Rules

- Consumers idempotent - any message can be redelivered. Dedup on the producer's **event ID** (unique per logical event, header or payload field - wherever the producer put it), not the routing/partition key - one key can carry many distinct events. `markProcessed(id)` returns `true` when the ID is newly recorded (proceed), `false` when already seen (skip); back it with a unique-PK insert so the check is atomic under concurrency.
- The dedup insert shares the business transaction (record + effect commit or roll back together) - a separately-committed dedup row makes a failed business tx skip its own redelivery, losing the message. Under JPA a PK-violation insert marks the shared tx rollback-only, so implement `markProcessed` as `INSERT ... ON CONFLICT DO NOTHING` (JdbcTemplate/native) where `false` is a return value, not an exception.
- DLT / DLQ configured for every listener; permanent failures excluded from retry.
- Use the **transactional outbox** whenever a publish must atomically follow a DB commit. Never call `send()` inside `@Transactional` without it - rollback leaves phantom events.
- Payloads are records / primitives. Never serialize JPA entities (lazy proxies, schema coupling).
- Ack only after successful processing. Kafka: `enable-auto-commit: false` + `ack-mode: manual_immediate`. RabbitMQ: container default (AUTO) acks on normal return and nacks on exception - correct as long as the listener lets failures throw; `acknowledge-mode: manual` only when acking mid-method.
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
    private final OpsAlerts alerts;

    @RetryableTopic(
        attempts = "3",
        backoff = @Backoff(delay = 1000, multiplier = 2),
        dltStrategy = DltStrategy.FAIL_ON_ERROR,
        exclude = { ValidationException.class, IllegalArgumentException.class })
    @KafkaListener(topics = "order.placed", groupId = "fulfillment")
    public void onOrderPlaced(OrderPlacedEvent e,
                               @Header("eventId") String eventId,
                               Acknowledgment ack) {
        if (processed.markProcessed(eventId)) {  // false = already seen, skip
            fulfillment.initiate(e.orderId());
        }
        ack.acknowledge();  // manual_immediate: without this, offsets never commit and every rebalance replays the backlog
    }

    // Payload and headers are optional: a record that failed deserialization reaches the DLT
    // with a null payload, and a required @Payload would fail the DLT handler itself.
    @DltHandler
    public void dlt(@Payload(required = false) OrderPlacedEvent e,
                    @Header(name = "eventId", required = false) String eventId) {
        alerts.notifyOps("fulfillment-dlt", eventId, e);
    }
}
```

```yaml
spring:
  threads.virtual.enabled: true           # Boot 3.5: listener containers honor VTs
  kafka:
    producer:                             # "must never be lost" needs all three, plus
      acks: all                           # min.insync.replicas=2 on the topic/broker
      properties:
        enable.idempotence: true          # no duplicates from internal producer retries
    consumer:
      auto-offset-reset: earliest
      enable-auto-commit: false
      # Size against max.poll.interval.ms: records x per-record latency must fit inside it,
      # or a slow batch triggers a rebalance and replays the whole poll.
      max-poll-records: 50
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events
    listener:
      ack-mode: manual_immediate
      concurrency: 3
      observation-enabled: true           # emits Micrometer spans + metrics
    template:
      observation-enabled: true           # producer side lives under template.*, not producer.*
```

`ErrorHandlingDeserializer` is what keeps a poison pill from stalling the partition: a message that fails deserialization never reaches the listener or `@RetryableTopic`, so without the wrapper the container loops on `poll()` forever. Wrapped, the failure becomes a `DeserializationException` the error handler routes to the DLT.

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
public void handle(OrderPlacedEvent e, @Header("eventId") String eventId) {
    if (!processed.markProcessed(eventId)) return;  // false = already seen, skip
    fulfillment.initiate(e.orderId());
}
```

```yaml
spring:
  rabbitmq:
    publisher-confirm-type: simple        # enables waitForConfirmsOrDie inside template.invoke()
    template:
      mandatory: true                     # unroutable message -> ReturnsCallback, not a silent drop
      observation-enabled: true
    listener:
      simple:
        acknowledge-mode: auto            # container acks on return, nacks on exception
        default-requeue-rejected: false   # Boot defaults this TRUE, which requeues to the head of
                                          # the queue in a hot loop and never reaches the DLX
        prefetch: 20
        observation-enabled: true
        retry:
          enabled: true
          max-attempts: 4
          initial-interval: 1s
          multiplier: 2
```

Two Rabbit-specific traps the Kafka path does not have. Boot auto-configures **no** JSON converter for AMQP - without a `Jackson2JsonMessageConverter` bean both sides fall back to `SimpleMessageConverter`, i.e. Java serialization, which is a deserialization-gadget surface and locks both sides to one class version. And declare exchanges, queues and bindings as `@Bean`s, not by hand in the admin UI - a hand-made queue lacking `x-dead-letter-exchange` fails `PRECONDITION_FAILED` when Spring redeclares it, so apply the DLX with a broker policy first or drain and recreate the queue.

Retry/backoff via `spring.rabbitmq.listener.simple.retry.*`; messages that exhaust retries hit `order.dlx` and land in the DLQ bound to it. Throw `AmqpRejectAndDontRequeueException` for permanent failures - it is the Rabbit analog of `@RetryableTopic(exclude = ...)` and skips retry straight to the DLX.

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
    Instant claimedAt;      // stamped by the claim tx; null = unclaimed
    boolean published;
}

@Transactional
public void placeOrder(PlaceOrderCommand cmd) {
    Order o = orderRepo.save(Order.from(cmd));
    outboxRepo.save(OutboxEvent.of(o, "order.placed", "OrderPlaced"));
}
```

Relay and publisher are separate beans - `this.publishOne()` would bypass the `@Transactional` proxy (self-invocation) and run send + `setPublished` without a transaction:

```java
@Component @RequiredArgsConstructor
class OutboxRelay {
    private final OutboxPublisher publisher;

    // One event per publish tx → one failure doesn't block siblings.
    @Scheduled(fixedDelay = 1000)
    public void drain() {
        for (UUID id : publisher.claimBatch(100)) publisher.publishOne(id);
    }
}

@Component @RequiredArgsConstructor
class OutboxPublisher {
    private final OutboxEventRepository outboxRepo;
    private final KafkaTemplate<String, String> kafka;

    @Transactional  // stamps claimed_at (see SQL below) so later polls skip in-flight rows
    public List<UUID> claimBatch(int n) { return outboxRepo.claimBatch(n); }

    @Transactional
    public void publishOne(UUID id) {
        OutboxEvent e = outboxRepo.findById(id).orElseThrow();
        // Built as a Message so the eventId header the consumer dedups on is actually present -
        // a bare send(topic, key, payload) emits none and the consumer's @Header cannot resolve.
        kafka.send(MessageBuilder.withPayload(e.getPayload())
                .setHeader(KafkaHeaders.TOPIC, e.getTopic())
                .setHeader(KafkaHeaders.KEY, e.getAggregateId())
                .setHeader("eventId", e.getId().toString())
                .build()).join();                                     // fail tx on send error
        e.setPublished(true);
    }
}
```

The relay sends `payload` as a JSON *string* with `StringSerializer`, so there is no `__TypeId__` header for the consumer's `JsonDeserializer` to read - pair it with `spring.json.use.type.headers: false` and `spring.json.value.default.type` on the consumer, or serialize the typed object instead. Prune `published` rows and the dedup table on a schedule; both grow without bound.

```sql
-- Native query (JPQL lacks SKIP LOCKED). The FOR UPDATE lock releases when the claim
-- tx commits, so the claimed_at stamp is what keeps other instances (and the next
-- poll) off in-flight rows; the timeout reclaims rows from a crashed claimer.
-- Alternative topology: publish inside the claim tx and skip the stamp.
UPDATE outbox_events SET claimed_at = now()
WHERE id IN (
    SELECT id FROM outbox_events
    WHERE published = false
      AND (claimed_at IS NULL OR claimed_at < now() - INTERVAL '60 seconds')
    ORDER BY created_at
    LIMIT :n FOR UPDATE SKIP LOCKED)
RETURNING id;
```

### No broker available

When the stack has no Kafka or Rabbit, the outbox is still the answer and the queue moves into the database: fan the outbox row out to a `jobs` table keyed `(handler, dedup_key UNIQUE)`, claimed with the same `FOR UPDATE SKIP LOCKED` query. `status = 'DEAD'` after N attempts is the DLQ - alert on its depth and never auto-consume it. Every replica polls; SKIP LOCKED is what makes that safe, so no leader election is needed. Long handlers run **outside** any transaction: claim in a short tx, work untransacted, complete in a second short tx, and size the claim lease above the handler's worst-case runtime. Nothing auto-instruments this hop, so carry `traceparent` on the row and restore it in the worker.

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

External services (Stripe, GitHub) deliver via HTTP with at-least-once semantics: verify signature, dedupe by event ID, respond 200 fast. Inline `process()` is for quick work only - anything approaching the provider's delivery timeout gets stored (outbox row or job record) inside the request, 200 returned, and processed async.

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

Required delivery does not belong in an `AFTER_COMMIT` listener - an exception thrown there is logged by the tx-synchronization machinery and never retried. Route required events through the outbox (written inside the transaction); keep only best-effort side effects in the listener:

```java
@Transactional
public Payment complete(UUID paymentId) {
    Payment p = payments.markCompleted(paymentId);
    outboxRepo.save(OutboxEvent.of(p, "payment.completed", "PaymentCompleted"));  // required - survives crash
    events.publishEvent(new PaymentCompletedEvent(p));
    return p;
}

@TransactionalEventListener(phase = AFTER_COMMIT)
public void onPaymentCompleted(PaymentCompletedEvent e) {
    try { sms.send(e.phone(), "Payment confirmed"); }               // best-effort only
    catch (Exception ex) { log.warn("SMS failed for {}", e.paymentId(), ex); }
}
```

## Output Format

One block per message flow (each consumed or published topic/queue), including a terminal DLQ nothing consumes. Reviews put findings in prose before the blocks and emit an as-is block alongside the target one.

```
Broker: {Kafka | RabbitMQ | Spring Events | DB queue - Postgres outbox/jobs}
Topic/Queue: {name}
Producer: {class}
Consumer: {class | none by design - reason}
Delivery: {at-least-once | at-most-once | effectively-once - outbox + consumer dedup}
Idempotency: {dedup key + storage}
DLT/DLQ: {topic/queue name | not needed - reason}
Retry: {attempts, backoff, excluded exceptions} and/or {claim-expiry policy for an outbox relay} - a flow with both states both
Observability: {observation-enabled | manual instrumentation | n/a}
```

## Avoid

- Publishing inside `@Transactional` without the outbox (phantom events on rollback).
- JPA entities as payloads.
- Swallowing all exceptions in a consumer (defeats retry / DLT).
- Logging-only failure handling on producer futures (`whenComplete` that only logs loses messages silently - use the outbox or propagate).
