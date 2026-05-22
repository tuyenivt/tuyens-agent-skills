---
name: rust-messaging-patterns
description: "Review Rust messaging code: Kafka (rdkafka), AMQP (lapin), NATS consumers/producers, retries, idempotency, DLQ, transactional outbox."
metadata:
  category: backend
  tags: [rust, kafka, amqp, nats, messaging, idempotency, outbox]
user-invocable: false
---

# Rust Messaging Patterns

> Load `Use skill: stack-detect` first to determine the project stack.
> Tokio runtime, cancellation, JoinSet, channel selection: defer to `rust-async-patterns`. This skill covers messaging-specific concerns only.

## When to Use

- Reviewing Kafka, AMQP, or NATS consumer/producer code in a Rust service
- Designing retry, idempotency, or dead-letter handling for message processing
- Publishing events alongside a database write (outbox)

## Rules

- Disable broker auto-commit/auto-ack. Ack only after the handler succeeds.
- Handlers must be idempotent: dedupe on a stable message key before side effects.
- Every consumer has a bounded retry policy and a DLQ (or explicit drop) on exhaustion.
- Payloads carry IDs and primitives, not internal structs or DB models.
- Publish-after-DB-commit is a dual write. Use the transactional outbox.
- Transient vs. permanent errors are classified; only transient errors retry.

## Patterns

### Kafka Consumer (rdkafka): manual commit + classified errors

```rust
let consumer: StreamConsumer = ClientConfig::new()
    .set("bootstrap.servers", brokers)
    .set("group.id", group_id)
    .set("enable.auto.commit", "false")     // manual commit
    .set("auto.offset.reset", "earliest")
    .create()?;
consumer.subscribe(&[topic])?;

while let Ok(msg) = consumer.recv().await {
    match handler(msg.payload().unwrap_or_default()).await {
        Ok(()) => consumer.commit_message(&msg, CommitMode::Async)?,
        Err(MsgError::Transient(_)) => { /* no commit -> rebalance redelivers */ }
        Err(MsgError::Permanent(e)) => {
            dlq.produce(msg.key(), msg.payload(), &e.to_string()).await?;
            consumer.commit_message(&msg, CommitMode::Async)?;  // advance past poison
        }
    }
}
```

Permanent errors (deserialization, validation) must commit and route to DLQ, else
the partition stalls. Transient errors (DB down, 5xx) leave the offset uncommitted.

### AMQP Consumer (lapin): ack/nack semantics

```rust
let mut consumer = channel.basic_consume(queue, tag, opts, FieldTable::default()).await?;
while let Some(delivery) = consumer.next().await {
    let delivery = delivery?;
    match handler(&delivery.data).await {
        Ok(()) => delivery.ack(BasicAckOptions::default()).await?,
        Err(MsgError::Transient(_)) => delivery
            .nack(BasicNackOptions { requeue: true, multiple: false })
            .await?,
        Err(MsgError::Permanent(_)) => delivery
            .nack(BasicNackOptions { requeue: false, multiple: false })  // -> DLX
            .await?,
    }
}
```

Bind the queue to a dead-letter exchange (`x-dead-letter-exchange`) so
`requeue: false` lands in DLQ rather than vanishing.

### NATS JetStream: explicit ack with redelivery cap

```rust
let mut sub = js.pull_subscribe(subject, "workers").await?;
let batch = sub.fetch().max_messages(32).expires(Duration::from_secs(5)).messages().await?;
tokio::pin!(batch);
while let Some(msg) = batch.next().await {
    let msg = msg?;
    if msg.info()?.delivered > MAX_REDELIVERIES {
        publish_dlq(&js, &msg).await?;
        msg.ack().await?;
        continue;
    }
    match handler(&msg.payload).await {
        Ok(()) => msg.ack().await?,
        Err(_) => msg.ack_with(AckKind::Nak(Some(backoff(msg.info()?.delivered)))).await?,
    }
}
```

JetStream tracks delivery count; gate DLQ on it rather than a local counter.

### Idempotency: dedupe before side effects

```rust
// Bad: side effect first, dedupe attempt later (double-send on retry)
send_email(&user).await?;
sqlx::query!("INSERT INTO processed (msg_id) VALUES ($1)", msg_id).execute(pool).await?;

// Good: claim the message_id atomically; ON CONFLICT skips replays
let claimed = sqlx::query_scalar!(
    "INSERT INTO processed (msg_id) VALUES ($1) ON CONFLICT DO NOTHING RETURNING msg_id",
    msg_id
).fetch_optional(pool).await?;
if claimed.is_some() { send_email(&user).await?; }
```

Use the broker-supplied message ID or a producer-set idempotency key. Never hash payload bytes (replays with timestamps differ).

### Retry with exponential backoff + jitter

```rust
use rand::Rng;
let mut delay = Duration::from_millis(100);
for attempt in 0..MAX_RETRIES {
    match call().await {
        Ok(v) => return Ok(v),
        Err(e) if !e.is_transient() => return Err(e),
        Err(_) if attempt + 1 == MAX_RETRIES => break,
        Err(_) => {
            let jitter = rand::thread_rng().gen_range(0..delay.as_millis() as u64);
            tokio::time::sleep(delay + Duration::from_millis(jitter)).await;
            delay = (delay * 2).min(Duration::from_secs(30));
        }
    }
}
```

Bound retries by attempt count and cap delay. In-process retry only for fast transients; otherwise let the broker redeliver.

### Transactional Outbox: atomic DB + event publication

```rust
// Bad: dual write - DB commits, broker publish fails -> phantom state
let order = insert_order(pool, &req).await?;
kafka.produce("order.created", &payload).await?;

// Good: outbox row writes in the same transaction as the business state
let mut tx = pool.begin().await?;
let order = insert_order(&mut *tx, &req).await?;
sqlx::query!(
    "INSERT INTO outbox (aggregate_id, event_type, payload) VALUES ($1, $2, $3)",
    order.id, "order.created", serde_json::to_value(&order)?,
).execute(&mut *tx).await?;
tx.commit().await?;

// Relay polls outbox, publishes, marks sent. Publish is idempotent on outbox.id.
```

Relay must use `SELECT ... FOR UPDATE SKIP LOCKED` to allow horizontal scaling.

### Producer Idempotence

- Kafka: set `enable.idempotence=true` + `acks=all` on the producer config.
- AMQP: use publisher confirms (`channel.confirm_select`) and retry on nack.
- NATS JetStream: set `Nats-Msg-Id` header for server-side dedupe.

## Output Format

Workflows parse this contract.

```
Findings:
  - [Severity: {Blocker|High|Medium|Low}] [Category: {Idempotency|DLQ|Retry|Outbox|Ack|Producer|Schema}]
    File: <path>:<line>
    Issue: <one-line description>
    Fix: <prescribed change, referencing a Pattern by name>

Risk Summary:
  Message Loss Risk: {None|Low|Medium|High}
  Duplicate Processing Risk: {None|Low|Medium|High}
  Poison Pill Risk: {None|Low|Medium|High}

Stack Detected: {Kafka(rdkafka) | AMQP(lapin) | NATS | Unknown}
Notes: <unresolved questions, partial info, or "n/a">
```

If the broker library is unknown, emit `Stack Detected: Unknown` and review against generic Rules only.

## Avoid

- Auto-commit / auto-ack enabled while a handler can fail.
- Publishing inside a DB transaction (broker call is not transactional).
- Dedup table inserted after the side effect rather than before.
- Retrying permanent errors (validation, deserialization) - they will never succeed.
- DLQ without a key/headers carrying the original failure reason.
- Reusing the same consumer group ID across environments (prod consumes staging offsets).
- Payloads embedding entire DB rows or timestamps used for dedup hashing.
