---
name: kotlin-spring-messaging-patterns
description: Kotlin / Spring Kafka / RabbitMQ / Application Events: idempotent consumers, DLT/DLQ, transactional outbox, AFTER_COMMIT, sealed events, suspend caveats.
metadata:
  category: backend
  tags: [kotlin, kafka, rabbitmq, spring-events, messaging, async, outbox, idempotency, coroutines]
user-invocable: false
---

# Kotlin Spring Messaging Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Publishing / consuming events via Kafka or RabbitMQ from Kotlin / Spring
- Replacing synchronous HTTP with async messaging
- Guaranteed delivery that must survive a crash between DB commit and broker publish
- In-process decoupling via Spring Application Events

## Rules

- Consumers idempotent - any message can be redelivered.
- DLT / DLQ configured for every listener; permanent failures excluded from retry.
- Use the **transactional outbox** whenever a publish must atomically follow a DB commit. Never call `send()` inside `@Transactional` without it - rollback leaves phantom events.
- Payloads are `data class` / primitives with explicit Jackson use-site targets (`@field:JsonProperty`). Never serialize JPA entities (lazy proxies, schema coupling).
- Manual ack only after successful processing (`enable-auto-commit: false`, `ack-mode: manual_immediate`).
- Catch only retryable exceptions; let unknowns reach the retry / DLT machinery. `runCatching` is banned (swallows `CancellationException`).
- `@KafkaListener` / `@RabbitListener` are proxy-backed: the `kotlin-spring` plugin opens stereotype-annotated classes. The annotated method must not be `private` / `final`.
- Propagate trace context across the broker (`observation-enabled: true`). Inside `suspend` consumers, use `MDCContext` to keep correlation IDs.

## `suspend` consumer caveat

`@KafkaListener` / `@RabbitListener` are not coroutine-aware. A `suspend fun` listener method does not work - Spring invokes it as a regular method and the suspension continuation is never resumed. Two safe shapes:

```kotlin
// Bad - listener is suspend; framework can't drive it
@KafkaListener(topics = ["order.placed"])
suspend fun on(e: OrderPlacedEvent) = fulfillment.initiate(e.orderId)

// Good A - blocking listener; bridge to suspend at the edge
@KafkaListener(topics = ["order.placed"])
fun on(e: OrderPlacedEvent) = runBlocking(MDCContext()) {
    fulfillment.initiate(e.orderId)
}

// Good B - blocking listener delegates to a non-suspend service
@KafkaListener(topics = ["order.placed"])
fun on(e: OrderPlacedEvent) { fulfillment.initiate(e.orderId) }
```

`runBlocking` at the boundary is acceptable - the listener container thread is already blocking and Virtual Threads (Boot 3.5+ `spring.threads.virtual.enabled=true`) make it cheap.

## Patterns

### Sealed event hierarchy

Closed domain-event types keep `when` exhaustive and serialization explicit:

```kotlin
sealed interface OrderEvent {
    val orderId: UUID
    data class Placed(override val orderId: UUID, val total: BigDecimal) : OrderEvent
    data class Cancelled(override val orderId: UUID, val reason: String) : OrderEvent
    data class Shipped(override val orderId: UUID, val carrier: String) : OrderEvent
}
```

For Jackson polymorphism on the wire, register `@JsonTypeInfo(use = NAME, property = "type")` + `@JsonSubTypes` once on the sealed interface.

### Kafka producer + consumer

```kotlin
@Service
class OrderEventPublisher(private val kafka: KafkaTemplate<String, OrderPlacedEvent>) {
    fun publish(e: OrderPlacedEvent): CompletableFuture<SendResult<String, OrderPlacedEvent>> =
        kafka.send("order.placed", e.orderId.toString(), e)
}

@Component
class OrderPlacedConsumer(
    private val processed: ProcessedMessages,
    private val fulfillment: FulfillmentService,
    private val alerts: AlertService,
) {
    @RetryableTopic(
        attempts = "3",
        backoff = Backoff(delay = 1000, multiplier = 2.0),
        dltStrategy = DltStrategy.FAIL_ON_ERROR,
        exclude = [ValidationException::class, IllegalArgumentException::class],
    )
    @KafkaListener(topics = ["order.placed"], groupId = "fulfillment")
    fun onOrderPlaced(
        e: OrderPlacedEvent,
        @Header(KafkaHeaders.RECEIVED_KEY) key: String,
    ) {
        if (!processed.markProcessed(key)) return        // unique-PK insert; duplicate = skip
        fulfillment.initiate(e.orderId)
    }

    @DltHandler
    fun dlt(e: OrderPlacedEvent) = alerts.notifyOps("fulfillment-dlt", e.orderId)
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

```kotlin
@Bean
fun fulfillmentQueue(): Queue = QueueBuilder.durable("order.fulfillment")
    .withArgument("x-dead-letter-exchange", "order.dlx")
    .withArgument("x-dead-letter-routing-key", "fulfillment.failed")
    .build()

@Component
class OrderQueueConsumer(
    private val processed: ProcessedMessages,
    private val fulfillment: FulfillmentService,
) {
    @RabbitListener(queues = ["order.fulfillment"])
    fun handle(e: OrderPlacedEvent) {
        if (!processed.markProcessed(e.orderId.toString())) return
        fulfillment.initiate(e.orderId)
    }
}
```

Retry/backoff via `spring.rabbitmq.listener.simple.retry.*`; exhausted messages hit `order.dlx` and land in the DLQ bound to it.

### Transactional outbox

Use when the publish must survive a crash between DB commit and broker ack.

```kotlin
@Entity
@Table(name = "outbox_events")
class OutboxEvent(
    @Id @GeneratedValue val id: UUID = UUID.randomUUID(),
    val aggregateId: String,         // partition key
    val topic: String,
    val eventType: String,
    @Column(columnDefinition = "jsonb") val payload: String,   // JSON
    val createdAt: Instant = Instant.now(),
    var published: Boolean = false,
)

@Service
class OrderService(
    private val orderRepo: OrderRepository,
    private val outboxRepo: OutboxRepository,
) {
    @Transactional
    fun placeOrder(cmd: PlaceOrderCommand): Order {
        val order = orderRepo.save(Order.from(cmd))
        outboxRepo.save(OutboxEvent(
            aggregateId = order.id.toString(),
            topic = "order.placed",
            eventType = "OrderPlaced",
            payload = mapper.writeValueAsString(order),
        ))
        return order
    }
}

// One unpublished event per row, per tx -> one failure doesn't block siblings.
// SKIP LOCKED lets multiple instances poll without double-publishing.
@Component
class OutboxDrainer(
    private val outboxRepo: OutboxRepository,
    private val kafka: KafkaTemplate<String, String>,
) {
    @Scheduled(fixedDelay = 1000)
    fun drain() {
        outboxRepo.claimBatch(100).forEach(::publishOne)
    }

    @Transactional
    fun publishOne(id: UUID) {
        val e = outboxRepo.findById(id).orElseThrow()
        kafka.send(e.topic, e.aggregateId, e.payload).join()   // fail tx on send error
        e.published = true
    }
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

```kotlin
data class OrderCreatedEvent(val orderId: UUID, val total: BigDecimal)

@Service
class OrderCreateService(
    private val orderRepo: OrderRepository,
    private val events: ApplicationEventPublisher,
) {
    @Transactional
    fun create(req: CreateOrderRequest): Order {
        val order = orderRepo.save(Order.from(req))
        events.publishEvent(OrderCreatedEvent(order.id, order.total))
        return order
    }
}

@Component
class OrderAuditListener(private val audit: AuditService) {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    fun onCreated(e: OrderCreatedEvent) = audit.record(e)
}
```

### Webhook handlers

External services (Stripe, GitHub) deliver via HTTP with at-least-once semantics: verify signature, dedupe by event ID, respond 200 fast.

```kotlin
@RestController
class StripeWebhookController(
    private val webhooks: StripeWebhookService,
    private val processed: ProcessedMessages,
) {
    @PostMapping("/webhooks/stripe")
    fun stripe(
        @RequestBody raw: String,
        @RequestHeader("Stripe-Signature") sig: String,
    ): ResponseEntity<Void> {
        webhooks.verify(raw, sig)
        val event = webhooks.parse(raw)
        if (processed.markProcessed(event.id)) webhooks.process(event)
        return ResponseEntity.ok().build()
    }
}
```

### Required vs best-effort side effects

A listener may fan out to multiple channels with different durability needs. Let required failures propagate; isolate best-effort.

```kotlin
@Component
class PaymentCompletedHandler(
    private val kafka: KafkaTemplate<String, PaymentCompletedEvent>,
    private val sms: SmsClient,
    private val log: Logger = LoggerFactory.getLogger(PaymentCompletedHandler::class.java),
) {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    fun onPaymentCompleted(e: PaymentCompletedEvent) {
        kafka.send("payment.completed", e.paymentId.toString(), e)   // required - let it throw
        try {
            sms.send(e.phone, "Payment confirmed")                   // best-effort
        } catch (ex: Exception) {
            log.warn("SMS failed for {}", e.paymentId, ex)           // parameterized SLF4J, not string template
        }
    }
}
```

## Testing notes

- Mock suspend collaborators with `coEvery` / `coVerify` - never `every` / `verify`.
- Test `@RetryableTopic` with `@EmbeddedKafka` + Awaitility; assert DLT row count, not just log lines.
- Test outbox drain idempotency: insert event, drain twice, assert single `kafka.send`.
- For `@TransactionalEventListener`, use `@RecordApplicationEvents` to assert phase semantics.

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
Suspend: {yes - bridge at boundary | no}
Observability: {observation-enabled | manual instrumentation | n/a}
```

## Avoid

- Publishing inside `@Transactional` without the outbox (phantom events on rollback).
- JPA entities as payloads.
- `suspend fun` directly on `@KafkaListener` / `@RabbitListener` - framework can't resume them.
- Swallowing all exceptions in a consumer (defeats retry / DLT). `runCatching` in particular swallows `CancellationException`.
- Logging-only failure handling on producer futures (`whenComplete` that only logs loses messages silently - use the outbox or propagate).
- Kotlin string templates inside `log.info("...$x...")` - use parameterized SLF4J (`log.info("... {}", x)`).
- Listener methods marked `private` or `final` (`kotlin-spring` opens classes but not methods you explicitly closed).
