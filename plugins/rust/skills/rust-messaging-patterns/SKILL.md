---
name: rust-messaging-patterns
description: Background job and async messaging patterns for Rust. Tokio task queues, Kafka consumers with rdkafka, AMQP with lapin, and in-process worker pools.
metadata:
  category: backend
  tags: [rust, kafka, amqp, messaging, background-jobs, async, tokio, idempotency]
user-invocable: false
---

# Rust Messaging Patterns

## When to Use

- Offloading work that takes > 200ms or touches external services (email, webhooks, file processing)
- Kafka event consumption in a Rust service
- AMQP (RabbitMQ) message processing
- In-process background task queues with Tokio

## Rules

- Handlers must be **idempotent** - tasks can be retried; check state before acting
- Pass IDs and primitive values as task payloads - never pass complex structs with internal state
- Configure **max retries** and a **dead-letter** strategy for every task type
- Workers must respect `CancellationToken` for graceful shutdown
- Use bounded channels for backpressure - never unbounded queues

## Patterns

### Tokio-Based Task Queue

```rust
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

#[derive(Debug)]
struct Task {
    id: String,
    payload: serde_json::Value,
}

async fn run_worker(
    token: CancellationToken,
    mut rx: mpsc::Receiver<Task>,
    pool: PgPool,
) {
    loop {
        tokio::select! {
            _ = token.cancelled() => {
                tracing::info!("worker shutting down gracefully");
                return;
            }
            Some(task) = rx.recv() => {
                if let Err(e) = handle_task(&pool, &task).await {
                    tracing::error!(task_id = %task.id, "task failed: {e}");
                    // TODO: retry logic or DLQ
                }
            }
        }
    }
}

async fn handle_task(pool: &PgPool, task: &Task) -> anyhow::Result<()> {
    // Idempotency check
    let already_processed = sqlx::query_scalar!(
        "SELECT EXISTS(SELECT 1 FROM processed_tasks WHERE task_id = $1)",
        &task.id
    )
    .fetch_one(pool)
    .await?
    .unwrap_or(false);

    if already_processed {
        return Ok(()); // already done
    }

    // Process task...
    process(&task.payload).await?;

    // Mark as processed
    sqlx::query!("INSERT INTO processed_tasks (task_id) VALUES ($1)", &task.id)
        .execute(pool)
        .await?;

    Ok(())
}
```

### Kafka Consumer (rdkafka)

```rust
use rdkafka::consumer::{Consumer, StreamConsumer};
use rdkafka::config::ClientConfig;
use rdkafka::Message;

async fn run_kafka_consumer(
    brokers: &str,
    topic: &str,
    group_id: &str,
    token: CancellationToken,
    handler: impl Fn(&[u8]) -> anyhow::Result<()> + Send + Sync,
) -> anyhow::Result<()> {
    let consumer: StreamConsumer = ClientConfig::new()
        .set("bootstrap.servers", brokers)
        .set("group.id", group_id)
        .set("enable.auto.commit", "false")
        .set("auto.offset.reset", "earliest")
        .create()?;

    consumer.subscribe(&[topic])?;

    loop {
        tokio::select! {
            _ = token.cancelled() => {
                tracing::info!("kafka consumer shutting down");
                return Ok(());
            }
            message = consumer.recv() => {
                match message {
                    Ok(msg) => {
                        if let Some(payload) = msg.payload() {
                            if let Err(e) = handler(payload) {
                                tracing::error!("message handler failed: {e}");
                                // Decide: DLQ, skip, or stop consumer
                            }
                        }
                        consumer.commit_message(&msg, rdkafka::consumer::CommitMode::Async)?;
                    }
                    Err(e) => {
                        tracing::error!("kafka recv error: {e}");
                    }
                }
            }
        }
    }
}
```

### Worker Pool with JoinSet

```rust
use tokio::task::JoinSet;

async fn run_worker_pool(
    mut rx: mpsc::Receiver<Job>,
    concurrency: usize,
    token: CancellationToken,
) -> anyhow::Result<()> {
    let mut set = JoinSet::new();

    loop {
        // Wait for capacity
        while set.len() >= concurrency {
            if let Some(result) = set.join_next().await {
                if let Err(e) = result {
                    tracing::error!("worker task panicked: {e}");
                }
            }
        }

        tokio::select! {
            _ = token.cancelled() => {
                // Drain remaining tasks
                while let Some(result) = set.join_next().await {
                    let _ = result;
                }
                return Ok(());
            }
            Some(job) = rx.recv() => {
                set.spawn(async move {
                    if let Err(e) = job.execute().await {
                        tracing::error!(job_id = %job.id, "job failed: {e}");
                    }
                });
            }
        }
    }
}
```

## Stack-Specific Guidance

- **rdkafka**: Rust binding to librdkafka - high performance, production-grade Kafka client; disable auto-commit and commit after successful processing
- **lapin**: AMQP client for RabbitMQ - async, tokio-native; use `basic_ack` after processing, `basic_nack` with requeue for transient failures
- **Graceful shutdown**: Use `CancellationToken` - cancel on SIGTERM, workers drain in-progress tasks before stopping
- **Scheduled tasks**: Use `tokio-cron-scheduler` for cron-style periodic tasks instead of raw `tokio::time::interval`

## Avoid

- Passing large structs or DB models as task payloads - serialize only IDs and primitives
- Tasks without a timeout - always set timeouts on spawned work
- Ignoring send errors on channels - log or handle failures explicitly
- Unbounded channels for fan-out - use bounded channels with backpressure
- Auto-committing Kafka offsets before processing - commit only after successful handler execution
