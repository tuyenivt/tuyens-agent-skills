---
name: rust-messaging-patterns
description: "Review Rust messaging: Kafka (rdkafka), AMQP (lapin), in-proc Tokio queues, worker pools, idempotency, DLQ, retries, outbox."
metadata:
  category: backend
  tags: [rust, kafka, amqp, tokio, messaging, idempotency, outbox]
user-invocable: false
---

# Rust Messaging Patterns

> Load `Use skill: stack-detect` first to determine the project stack.
> Runtime/cancellation/JoinSet/channel mechanics: defer to `rust-async-patterns` and `rust-concurrency`. This skill covers messaging semantics only.

## When to Use

- Reviewing Kafka or AMQP consumer/producer code in a Rust service
- Reviewing in-proc Tokio job queues or worker pools
- Designing retries, idempotency, or dead-letter handling
- Publishing events alongside a DB write (outbox)

## Rules

- Disable broker auto-commit / auto-ack (`enable.auto.commit=false`, lapin `no_ack: false`). Ack only after the handler succeeds.
- Handlers are idempotent: dedupe on a stable broker-supplied or producer-set ID before any side effect. Never hash payload bytes.
- Errors classify as `Transient` vs `Permanent`. Only transient retries; permanent goes to DLQ with the original ID, payload, and reason.
- Bound every retry by attempt count and cap delay; use exponential backoff + jitter.
- Outbox or nothing. Never publish inside a DB transaction; never publish after `tx.commit()` as a dual write.
- In-proc queues use bounded `mpsc` for backpressure. Unbounded channels turn a slow consumer into OOM.
- Payloads carry IDs and primitives, not internal structs, ORM rows, or wall-clock timestamps used for dedup.
- No blocking calls (`std::thread::sleep`, sync I/O, `block_on`) inside an async consumer loop - they stall the poll and trigger broker rebalance.

## Patterns

### Kafka consumer (rdkafka): manual commit + classified errors

```rust
let consumer: StreamConsumer = ClientConfig::new()
    .set("bootstrap.servers", brokers)
    .set("group.id", group_id)
    .set("enable.auto.commit", "false")
    .create()?;
consumer.subscribe(&[topic])?;

while let Ok(msg) = consumer.recv().await {
    match handler(msg.payload().unwrap_or_default()).await {
        Ok(()) => consumer.commit_message(&msg, CommitMode::Async)?,
        Err(MsgError::Transient(_)) => { /* no commit -> rebalance redelivers */ }
        Err(MsgError::Permanent(e)) => {
            dlq.produce(msg.key(), msg.payload(), &e.to_string()).await?;
            consumer.commit_message(&msg, CommitMode::Async)?;   // advance past poison
        }
    }
}
```

Permanent errors must commit-and-DLQ, otherwise the partition stalls on the poison message. A single un-classified `anyhow::Error` collapses both branches and either retries forever or drops silently.

### AMQP consumer (lapin): ack/nack semantics

```rust
let mut consumer = channel.basic_consume(
    queue, tag,
    BasicConsumeOptions { no_ack: false, ..Default::default() },   // server ack required
    FieldTable::default(),
).await?;
while let Some(delivery) = consumer.next().await {
    let delivery = delivery?;
    match handler(&delivery.data).await {
        Ok(()) => delivery.ack(BasicAckOptions::default()).await?,
        Err(MsgError::Transient(_)) => delivery
            .nack(BasicNackOptions { requeue: true, multiple: false }).await?,
        Err(MsgError::Permanent(_)) => delivery
            .nack(BasicNackOptions { requeue: false, multiple: false }).await?,  // -> DLX
    }
}
```

`no_ack: true` is fire-and-forget; a panic loses the message. Bind the queue to a dead-letter exchange (`x-dead-letter-exchange`) so `requeue: false` lands in DLQ rather than vanishing.

### In-proc Tokio queue: bounded channel + worker pool

```rust
// Bad: unbounded backlog grows until OOM; producer never feels pressure
let (tx, mut rx) = mpsc::unbounded_channel::<Job>();
tokio::spawn(async move { while let Some(j) = rx.recv().await { handle(j).await; } });

// Good: bounded channel applies backpressure; JoinSet bounds concurrency
let (tx, rx) = mpsc::channel::<Job>(1024);
let rx = Arc::new(Mutex::new(rx));
let mut workers = JoinSet::new();
for _ in 0..WORKERS {
    let rx = rx.clone();
    workers.spawn(async move {
        while let Some(job) = { let mut g = rx.lock().await; g.recv().await } {
            if let Err(e) = handle(job).await { tracing::error!(?e, "job failed"); }
        }
    });
}
// producer: tx.send(job).await?  -- awaits when full
```

In-proc queues have no broker redelivery. Persist the job (DB row or outbox) before enqueueing if loss on crash is unacceptable. Drain on shutdown via `CancellationToken` + `workers.join_all().await`.

### Idempotency: dedupe before side effects

```rust
// Bad: side effect first, dedupe second -> double-send on retry
send_email(&user).await?;
sqlx::query!("INSERT INTO processed (msg_id) VALUES ($1)", msg_id).execute(pool).await?;

// Good: claim the id atomically; ON CONFLICT skips replays
let claimed = sqlx::query_scalar!(
    "INSERT INTO processed (msg_id) VALUES ($1) ON CONFLICT DO NOTHING RETURNING msg_id",
    msg_id,
).fetch_optional(pool).await?;
if claimed.is_some() { send_email(&user).await?; }
```

Use the broker-supplied ID (Kafka offset+partition+topic, AMQP `message_id`) or a producer-set idempotency key. Hashing payload bytes breaks when producers re-serialize or embed timestamps.

### Retry with exponential backoff + jitter

```rust
let mut delay = Duration::from_millis(100);
for attempt in 0..MAX_RETRIES {
    match call().await {
        Ok(v) => return Ok(v),
        Err(e) if !e.is_transient() => return Err(e),          // permanent: stop
        Err(_) if attempt + 1 == MAX_RETRIES => break,
        Err(_) => {
            let jitter = rand::thread_rng().gen_range(0..delay.as_millis() as u64);
            tokio::time::sleep(delay + Duration::from_millis(jitter)).await;
            delay = (delay * 2).min(Duration::from_secs(30));
        }
    }
}
```

In-process retry only for fast transients (sub-second). For slow transients (DB down, downstream 5xx for minutes), surface the error and let broker redelivery handle it - otherwise the consumer loop blocks and offsets stall.

### Transactional outbox: atomic DB + event publication

```rust
// Bad: publish inside the transaction - broker call is not transactional,
// rollback leaves a phantom event in the topic
let mut tx = pool.begin().await?;
let order = insert_order(&mut *tx, &req).await?;
kafka.produce("order.created", &payload).await?;   // not rolled back on failure below
tx.commit().await?;

// Good: outbox row in the same tx; a relay publishes from the table
let mut tx = pool.begin().await?;
let order = insert_order(&mut *tx, &req).await?;
sqlx::query!(
    "INSERT INTO outbox (id, aggregate_id, event_type, payload)
     VALUES ($1, $2, $3, $4)",
    Uuid::new_v4(), order.id, "order.created", serde_json::to_value(&order)?,
).execute(&mut *tx).await?;
tx.commit().await?;
```

Relay polls with `SELECT ... FOR UPDATE SKIP LOCKED` for horizontal scaling. Consumers dedupe on `outbox.id` since the relay may re-publish after a crash between publish and mark-sent.

### Producer idempotence

- Kafka: `enable.idempotence=true` + `acks=all` on producer config.
- AMQP: `channel.confirm_select()` + retry on nack.
- In-proc: pair the enqueue with an outbox row so the job survives restart.

## Output Format

Workflows parse this contract.

```
Findings:
  - [Severity: {Blocker|High|Medium|Low}] [Category: {Idempotency|DLQ|Retry|Outbox|Ack|Producer|Backpressure|Blocking|Schema}]
    File: <path>:<line>
    Issue: <one-line description>
    Fix: <prescribed change, referencing a Pattern by name>

Risk Summary:
  Message Loss Risk: {None|Low|Medium|High}
  Duplicate Processing Risk: {None|Low|Medium|High}
  Poison Pill Risk: {None|Low|Medium|High}
  Backpressure Risk: {None|Low|Medium|High}

Stack Detected: {Kafka(rdkafka) | AMQP(lapin) | InProc(tokio) | Unknown}
Notes: <unresolved questions, partial info, or "n/a">
```

If the broker library is unknown, emit `Stack Detected: Unknown` and review against generic Rules only.

## Avoid

- Auto-commit / auto-ack (`no_ack: true`) while a handler can fail.
- Publishing inside a DB transaction, or after commit as a dual write.
- Dedup insert after the side effect rather than before.
- Retrying permanent errors (validation, deserialization) - they will never succeed.
- DLQ without the original ID, payload, and failure reason in headers.
- Unbounded `mpsc` or `tokio::spawn` per message - no backpressure, no shutdown.
- Reusing one consumer group ID across environments (prod consumes staging offsets).
- Blocking calls (`std::thread::sleep`, sync I/O, `block_on`) inside the consumer loop.
- Rolling your own redelivery instead of leveraging broker semantics.
