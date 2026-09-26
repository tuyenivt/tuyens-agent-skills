---
name: spring-messaging-patterns
description: "Spring Kafka / RabbitMQ / Application Events: idempotent consumers, DLT/DLQ, transactional outbox, AFTER_COMMIT, webhooks, observability."
metadata:
  category: backend
  tags: [kafka, rabbitmq, spring-events, messaging, async, outbox, idempotency]
user-invocable: false
---

# Spring Messaging Patterns

> Load `Use skill: stack-detect` first to determine the project stack. Its `Database` picks the dedup and claim SQL (PostgreSQL / MySQL variants below). The broker: a `Queue:` / `Broker:` / `Messaging:` key in stack-detect's `Additional` wins; otherwise the build file - `spring-boot-starter-kafka` / `spring-kafka` -> Kafka (on Boot 4 a `spring-kafka` with neither its starter, the `spring-boot-kafka` module nor `spring-boot-starter-classic` gets no auto-configuration - a finding), `spring-boot-starter-amqp` / `spring-rabbit` -> RabbitMQ, neither -> Spring Events or a DB queue. `Database: unknown` - the SQL is shown for PostgreSQL with the MySQL variant.

## When to Use

- Publishing / consuming events via Kafka or RabbitMQ; inbound webhooks
- Replacing synchronous HTTP with async messaging - only when the caller does not need the result in-request; if it does, keep HTTP or use request-reply with a correlation ID
- Guaranteed delivery that must survive a crash between DB commit and broker publish
- In-process decoupling via Spring Application Events
- Reviewing or diagnosing any of the above (duplicates, lost messages, stuck consumers)

## Rules

- Consumers are idempotent - any message can be redelivered. Dedup on the producer's **event ID** (unique per logical event, in a header or payload field), never on the routing/partition key - one key carries many events. `markProcessed(id)` returns `true` when the ID is newly recorded (proceed), `false` when already seen (skip), backed by a unique-key insert so the check is atomic under concurrency. An inbound message with no event ID (an external producer) dedups on the business key that identifies one logical event (`webOrderId` + message type), stated as such.
- The dedup insert and the business effect share one transaction, so they commit or roll back together - a separately committed dedup row makes a failed effect skip its own redelivery. The insert must not throw on a duplicate: on PostgreSQL any failed statement aborts the whole transaction (under JPA it is also marked rollback-only), so use `INSERT ... ON CONFLICT DO NOTHING` (MySQL: `INSERT IGNORE`) and read the update count (0 = already seen). An effect outside the database (HTTP call) is not rolled back - pass the event ID to it as an idempotency key.
- Every Kafka / RabbitMQ listener and DB-queue handler has a DLT / DLQ; permanent failures skip retry.
- A publish that must follow a DB commit goes through the **transactional outbox**. Never call `send()` inside `@Transactional` without it: a rollback leaves a phantom event - and a checked exception does not roll back by default (`spring-transaction`), so "failed" paths can still commit and publish.
- Payloads are records / primitives. Never serialize JPA entities (lazy proxies, schema coupling).
- Ack only after successful processing. Kafka: the default container ack mode (`BATCH`; `enable.auto.commit` defaults to false unless set explicitly - never set it true) already commits offsets only after the listener returns, and the error handler commits only recovered records - use `ack-mode: manual_immediate` only when acking conditionally, and then ack on every path, DLT handlers included. RabbitMQ: container `AUTO` acks on return and nacks on exception - correct as long as failures throw; `acknowledge-mode: manual` only when acking mid-method.
- Catch only what you can handle in a listener; let unknowns reach the retry / DLT machinery.
- Trace context crosses the broker only with observation enabled - it is off by default in Spring Kafka and Spring AMQP: `spring.kafka.template.observation-enabled` / `spring.kafka.listener.observation-enabled`, `spring.rabbitmq.template.observation-enabled` / `spring.rabbitmq.listener.simple.observation-enabled`, plus a Micrometer Tracing bridge on the classpath.

## Patterns

### Kafka producer + consumer

```java
public record OrderPlacedEvent(UUID eventId, Long orderId) {}

@Service @RequiredArgsConstructor
class OrderEventPublisher {
    private final KafkaTemplate<String, OrderPlacedEvent> kafka;

    public CompletableFuture<SendResult<String, OrderPlacedEvent>> publish(OrderPlacedEvent e) {
        var record = new ProducerRecord<>("order.placed", e.orderId().toString(), e);
        record.headers().add("eventId", e.eventId().toString().getBytes(StandardCharsets.UTF_8));
        return kafka.send(record);   // caller propagates failure (or the event goes through the outbox)
    }
}

@Component @RequiredArgsConstructor
class OrderPlacedConsumer {
    private final FulfillmentService fulfillment;
    private final OpsAlerts alerts;

    @RetryableTopic(
        attempts = "3",
        backOff = @BackOff(delay = 1000, multiplier = 2),   // Spring Kafka 4; 3.x: backoff = @Backoff(...)
        dltStrategy = DltStrategy.FAIL_ON_ERROR,
        exclude = { ValidationException.class, IllegalArgumentException.class })
    @KafkaListener(topics = "order.placed", groupId = "fulfillment")
    public void onOrderPlaced(OrderPlacedEvent e, @Header("eventId") String eventId) {
        fulfillment.initiateOnce(eventId, e.orderId());   // one @Transactional method: markProcessed + effect
    }

    // A poison pill (failed deserialization) never reaches this handler - it fails the DLT container's
    // deserializer too. Alert on those from DLT lag or a raw-bytes DLT consumer
    // (value.deserializer=ByteArrayDeserializer); @Payload(required = false) covers tombstones.
    @DltHandler
    public void dlt(@Payload(required = false) OrderPlacedEvent e,
                    @Header(name = "eventId", required = false) String eventId) {
        alerts.notifyOps("fulfillment-dlt", eventId, e);
    }
}

@Service @RequiredArgsConstructor
class FulfillmentService {
    private final ProcessedMessages processed;

    @Transactional
    public void initiateOnce(String eventId, Long orderId) {
        if (!processed.markProcessed(eventId)) return;   // false = already seen
        // ... business writes; external calls carry eventId as their idempotency key
    }
}
```

```yaml
spring:
  threads.virtual.enabled: true           # listener containers run on virtual threads
  kafka:
    producer:                             # value serializer set by the customizer below
      acks: all                           # client defaults since Kafka 3.0 - pinned so no override weakens them;
      properties:                         # "must never be lost" also needs min.insync.replicas=2 on the topic
        enable.idempotence: true
    consumer:
      auto-offset-reset: earliest
      # Size against max.poll.interval.ms: records x per-record latency must fit, or a slow poll
      # triggers a rebalance and every record not yet committed is redelivered.
      max-poll-records: 50
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JacksonJsonDeserializer   # 3.x: JsonDeserializer
        spring.json.trusted.packages: com.example.events
        spring.json.use.type.headers: false               # don't trust the producer's __TypeId__ class name
    listener:
      concurrency: 3
      observation-enabled: true
    template:
      observation-enabled: true
```

- The target type is set per listener - `@KafkaListener(..., properties = "spring.json.value.default.type=com.example.events.OrderPlacedEvent")` - never globally, or every listener deserializes into one class.
- `ErrorHandlingDeserializer` keeps a poison pill (or a producer's schema change) from stalling the partition: without it the container fails in `poll()` and loops on the same record forever; wrapped, the failure becomes a `DeserializationException` the error handler sends to the DLT. The DLT publisher republishes the original `byte[]`, and the outbox relay sends pre-serialized JSON strings, so one producer serializer handles all three types:

```java
@Bean DefaultKafkaProducerFactoryCustomizer valueSerializer() {
    var byType = new LinkedHashMap<Class<?>, Serializer<?>>();   // ordered: first assignable match wins
    byType.put(byte[].class, new ByteArraySerializer());          // DLT republish of raw bytes
    byType.put(String.class, new StringSerializer());             // outbox payloads, already JSON
    byType.put(Object.class, new JacksonJsonSerializer<>());      // typed events (Jackson 3; 3.x: JsonSerializer)
    return pf -> pf.setValueSerializer(new DelegatingByTypeSerializer(byType, true));
}
```

  Without the `byte[]` entry the DLT receives a base64 JSON string instead of the original bytes.
- `@RetryableTopic` auto-creates `order.placed-retry-0`, `-retry-1`, `order.placed-dlt`; `exclude` sends non-retryable exceptions straight to the DLT.

### RabbitMQ with DLQ

```java
@Bean DirectExchange orderDlx() { return new DirectExchange("order.dlx"); }
@Bean Queue fulfillmentDlq() { return QueueBuilder.durable("order.fulfillment.dlq").build(); }
@Bean Binding dlqBinding() { return BindingBuilder.bind(fulfillmentDlq()).to(orderDlx()).with("fulfillment.failed"); }

@Bean Queue fulfillmentQueue() {
    return QueueBuilder.durable("order.fulfillment")
        .withArgument("x-dead-letter-exchange", "order.dlx")
        .withArgument("x-dead-letter-routing-key", "fulfillment.failed")
        .build();
}

@Bean JacksonJsonMessageConverter jsonConverter() { return new JacksonJsonMessageConverter(); }   // 3.x: Jackson2JsonMessageConverter

// Permanent failures skip listener retry (the policy retries every other exception); excludes match the cause
// chain and go straight to the recoverer. Boot 3.x: a RabbitRetryTemplateCustomizer with a SimpleRetryPolicy
@Bean RabbitListenerRetrySettingsCustomizer noRetryOnPermanent() {
    return settings -> settings.getExceptionExcludes().addAll(List.of(
        AmqpRejectAndDontRequeueException.class, MessageConversionException.class));
}

@RabbitListener(queues = "order.fulfillment")
public void handle(OrderPlacedEvent e, @Header("eventId") String eventId) {
    fulfillment.initiateOnce(eventId, e.orderId());
}
```

```yaml
spring:
  rabbitmq:
    publisher-confirm-type: simple        # the relay's waitForConfirmsOrDie needs simple
    publisher-returns: true               # with template.mandatory, unroutable messages reach the ReturnsCallback
    template:
      mandatory: true
      observation-enabled: true
    listener:
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false   # container default is true: with retry off, a failing message
                                          # requeues to the head of the queue in a hot loop
        prefetch: 20
        observation-enabled: true
        retry:                            # exhausted -> RejectAndDontRequeueRecoverer -> DLX
          enabled: true
          max-retries: 3                  # after the first delivery; Boot 3.x: max-attempts: 4
          initial-interval: 1s
          multiplier: 2
```

- Boot configures **no** JSON converter for AMQP: without a `JacksonJsonMessageConverter` bean both sides use `SimpleMessageConverter` - record payloads are rejected at send (not `Serializable`), and `Serializable` ones couple both sides to one class version.
- Register a `ReturnsCallback` on the `RabbitTemplate` that alerts or persists - `mandatory` alone drops nothing silently only when someone handles the return.
- Declare exchanges, queues and bindings as `@Bean`s, not in the admin UI. A hand-made queue whose arguments differ from the `@Bean` (e.g. missing `x-dead-letter-exchange`) fails redeclaration with `PRECONDITION_FAILED`: drop the `x-dead-letter-*` arguments from the `@Bean` and set the DLX with a broker policy, or drain and recreate the queue. A DLX with no queue bound to it discards what it receives.
- Fan-out: one exchange, one queue per consuming service (`sale.completed` -> `sales.loyalty`, `sales.accounting`), each with its own DLQ - never two services on one queue or a shovel between them.

### Transactional outbox

Use when a publish must survive a crash between DB commit and broker ack.

```java
@Getter @Setter @Entity @Table(name = "outbox_events")
class OutboxEvent {
    @Id UUID id;               // the event ID consumers dedup on
    String aggregateId;        // partition / routing key
    String topic;
    String payload;            // JSON
    Instant createdAt;
    Instant claimedAt;         // null = unclaimed
    boolean published;

    static OutboxEvent of(UUID id, String topic, String aggregateId, Object event, JsonMapper json) { /* payload = json.writeValueAsString(event) */ }   // 3.x: ObjectMapper
}

@Transactional
public void placeOrder(PlaceOrderCommand cmd) {
    Order o = orderRepo.save(Order.from(cmd));
    UUID eventId = UUID.randomUUID();   // becomes the outbox row id and the header consumers dedup on
    outboxRepo.save(OutboxEvent.of(eventId, "order.placed", o.getId().toString(), new OrderPlacedEvent(eventId, o.getId()), json));
}
```

Relay and publisher are separate beans (`this.publishOne()` would bypass the `@Transactional` proxy):

```java
@Slf4j @Component @RequiredArgsConstructor
class OutboxRelay {
    private final OutboxPublisher publisher;

    @Scheduled(fixedDelay = 1000)
    public void drain() {
        for (UUID id : publisher.claimBatch(100)) {
            try { publisher.publishOne(id); }
            catch (RuntimeException ex) { log.warn("outbox publish failed {}", id, ex); }   // sibling rows still go
        }
    }
}

@Component @RequiredArgsConstructor
class OutboxPublisher {
    private final OutboxEventRepository outboxRepo;
    private final JdbcTemplate jdbc;
    private final KafkaTemplate<String, Object> kafka;   // Boot's template: observed; String payloads pass through as-is

    @Transactional   // stamps claimed_at so later polls skip in-flight rows
    public List<UUID> claimBatch(int n) { return jdbc.queryForList(CLAIM_SQL, UUID.class, n); }

    @Transactional
    public void publishOne(UUID id) {
        OutboxEvent e = outboxRepo.findById(id).orElseThrow();
        kafka.send(MessageBuilder.withPayload(e.getPayload())
                .setHeader(KafkaHeaders.TOPIC, e.getTopic())
                .setHeader(KafkaHeaders.KEY, e.getAggregateId())
                .setHeader("eventId", e.getId().toString())
                .build()).join();                                 // fail the tx on send error
        e.setPublished(true);
    }
}
```

The consumer reads the JSON string without a `__TypeId__` header - pair it with `spring.json.use.type.headers: false` and the per-listener default type. The claim lease must exceed a batch's worst case (100 sends x `delivery.timeout.ms`), or lower the batch size / timeout - an expired lease re-publishes rows still in flight, which consumer dedup absorbs. Prune `published` rows and the dedup table on a schedule.

RabbitMQ relay - send the stored bytes, bypassing the JSON converter (it would re-encode the string), with the header the consumer reads:

```java
rabbitTemplate.invoke(t -> {
    var props = new MessageProperties();
    props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
    props.setMessageId(eventId);
    props.setHeader("eventId", eventId);
    t.send(exchange, routingKey, new Message(payload.getBytes(StandardCharsets.UTF_8), props));
    t.waitForConfirmsOrDie(10_000);
    return null;
});
```

```sql
-- CLAIM_SQL, PostgreSQL. The FOR UPDATE lock ends when the claim tx commits; the claimed_at
-- stamp keeps other instances off in-flight rows; the lease reclaims rows from a crashed claimer.
UPDATE outbox_events SET claimed_at = now()
WHERE id IN (
    SELECT id FROM outbox_events
    WHERE published = false
      AND (claimed_at IS NULL OR claimed_at < now() - INTERVAL '60 seconds')
    ORDER BY created_at
    LIMIT ? FOR UPDATE SKIP LOCKED)
RETURNING id;

-- MySQL 8.0 (no RETURNING): claimBatch runs two statements in its @Transactional -
-- select the ids (a CHAR(36) id maps with UUID.fromString(rs.getString(1))), then update them
--   SELECT id FROM outbox_events WHERE published = false
--     AND (claimed_at IS NULL OR claimed_at < NOW(6) - INTERVAL 60 SECOND)
--   ORDER BY created_at LIMIT ? FOR UPDATE SKIP LOCKED;
--   UPDATE outbox_events SET claimed_at = NOW(6) WHERE id IN (...selected ids...);
```

### No broker available

The outbox is still the answer and the queue moves into the database: fan the outbox row out to a `jobs` table keyed `(handler, dedup_key UNIQUE)`, claimed with the same `FOR UPDATE SKIP LOCKED` query. `status = 'DEAD'` after N attempts is the DLQ - alert on its depth and never auto-consume it. Every replica polls; SKIP LOCKED makes that safe without leader election. Long handlers run **outside** any transaction: claim in a short tx, work untransacted, complete in a second short tx, with the claim lease above the handler's worst-case runtime. Nothing auto-instruments this hop - carry `traceparent` on the row and restore it in the worker.

### Spring Application Events (in-process, same JVM)

`AFTER_COMMIT` so listeners never see uncommitted state. No crash survival - use the outbox when it matters.

```java
public record OrderCreatedEvent(Long orderId, BigDecimal total) {}

@Transactional
public Order create(CreateOrderRequest req) {
    Order o = orderRepo.save(Order.from(req));
    events.publishEvent(new OrderCreatedEvent(o.getId(), o.getTotal()));
    return o;
}

@TransactionalEventListener(phase = AFTER_COMMIT)
@Transactional(propagation = REQUIRES_NEW)   // it writes; Spring 6.1+ accepts only REQUIRES_NEW or NOT_SUPPORTED here
public void onOrderCreated(OrderCreatedEvent e) { auditService.record(e); }
```

### Required vs best-effort side effects

An exception in an `AFTER_COMMIT` listener is caught and logged by the transaction machinery and never retried - required delivery goes through the outbox (written inside the transaction); only best-effort effects stay in the listener:

```java
public record PaymentCompletedEvent(UUID paymentId, String phone) {}          // in-process, best-effort
public record PaymentCompletedMessage(UUID eventId, UUID paymentId) {}      // outbox payload

@Transactional
public Payment complete(UUID paymentId) {
    Payment p = payments.markCompleted(paymentId);
    UUID eventId = UUID.randomUUID();
    outboxRepo.save(OutboxEvent.of(eventId, "payment.completed", p.getId().toString(), new PaymentCompletedMessage(eventId, p.getId()), json));
    events.publishEvent(new PaymentCompletedEvent(p.getId(), p.getPhone()));
    return p;
}

@TransactionalEventListener(phase = AFTER_COMMIT)
public void onPaymentCompleted(PaymentCompletedEvent e) {
    try { sms.send(e.phone(), "Payment confirmed"); }               // best-effort only
    catch (Exception ex) { log.warn("SMS failed for {}", e.paymentId(), ex); }
}
```

### Webhook handlers

Providers deliver over HTTP at-least-once; Stripe and Adyen retry any non-2xx, GitHub does not retry at all (reconcile misses through its redeliver API): verify the signature (constant-time compare, `MessageDigest.isEqual`), dedupe on the provider's event ID, answer 2xx fast. Work that makes a remote call or can approach the provider's delivery timeout is stored (outbox or job row, inside the request's transaction) and processed async; only pure local DB updates run inline.

```java
@PostMapping("/webhooks/stripe")
public ResponseEntity<Void> stripe(@RequestBody byte[] raw, @RequestHeader("Stripe-Signature") String sig) {
    webhooks.verify(raw, sig);                    // throws -> 400; alert on verification failures (a rotated secret fails genuine events too)
    webhooks.acceptOnce(webhooks.parse(raw));     // @Transactional: markProcessed(event.id) + store job row
    return ResponseEntity.ok().build();
}
```

## Output Format

In every mode, emit the `**Engine:**` line once, then one block per message flow - each consumed or published topic/queue, one block per queue on a fan-out, including a terminal DLQ nothing consumes. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, list findings first - `### [Must|Recommend] file:line` (pasted input: `Class.method`), then `Issue:` and `Fix:` as separate paragraphs, `[Must]` first, `[Must]` when it loses messages, duplicates an effect, stalls a consumer, accepts forged input, or deserializes untrusted types (`trusted.packages: "*"`), `[Recommend]` otherwise - then per flow (one per queue or topic, all symptoms on it together) an as-is block and a target block. A class outside the reviewed files is `unknown - <class> not reviewed` in the slot it affects. An effect over HTTP carries the event ID as its idempotency key: `restClient.post().uri(...).header("Idempotency-Key", eventId)`.

```
**Engine:** {PostgreSQL | MySQL | <other> - adapt the SQL | unknown - PostgreSQL shown, MySQL variant given | none - publish-only service}
```

```
Broker: {Kafka | RabbitMQ | Spring Events | DB queue - outbox/jobs | Webhook (HTTP inbound)}

Topic/Queue: {name}

Producer: {class | external - <provider>}

Consumer: {class | none by design - reason}

Publish: {outbox relay | synchronous send, failure propagates | fire-and-forget - lost on failure | n/a - inbound}

Delivery: {at-least-once | at-most-once | effectively-once - outbox + consumer dedup}

Idempotency: {dedup key + storage}

DLT/DLQ: {topic/queue name | not needed - reason}

Retry: {attempts, backoff, excluded exceptions | claim-expiry policy for an outbox relay | provider-owned redelivery} - a flow with several states lists each

Observability: {observation-enabled | manual instrumentation | none}
```

## Avoid

- Publishing inside `@Transactional` without the outbox (phantom events on rollback)
- A dedup row committed separately from the effect it guards
- JPA entities as payloads
- Swallowing all exceptions in a consumer (defeats retry / DLT)
- Logging-only failure handling on producer futures (`whenComplete` that only logs loses messages silently)
- Two services consuming one queue, or a shovel between them
