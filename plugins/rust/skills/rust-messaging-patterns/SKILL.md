---
name: rust-messaging-patterns
description: "Rust async messaging: Postgres job queue (SKIP LOCKED), Kafka via rdkafka, retry classification, transactional outbox, Tokio worker pools."
metadata:
  category: backend
  tags: [rust, kafka, rdkafka, messaging, background-jobs, tokio, idempotency, outbox]
user-invocable: false
---

# Rust Messaging Patterns

> Load `Use skill: stack-detect` first. This skill reads the `Additional` lines that name a broker or queue (`Queue:`, `Kafka:`), falling back to `Cargo.toml` dependencies (`rdkafka`, `lapin`, `apalis`) and to a `jobs` table claimed through `sqlx` when none is declared. In a Cargo workspace the crate under review decides: its own `[dependencies]` (resolved through `[workspace.dependencies]`) in place of the detected values. Baseline: Rust 1.94+ (edition 2024), Tokio 1.x with tokio-util (`CancellationToken`), sqlx 0.9 on PostgreSQL, rdkafka 0.36+. A project on another broker (lapin AMQP, NATS, SQS, apalis) keeps the rules and the Output Format; the job-table and rdkafka code does not transfer and is omitted. Task, cancellation and channel mechanics belong to `rust-async-patterns` and `rust-concurrency`; claim queries and pool sizing to `rust-db-access`.

## When to Use

- Offloading > 200ms work or external-service calls
- Kafka consumption or production
- Periodic / scheduled tasks
- In-process worker pools for bounded parallelism

## Rules

- Handlers must be idempotent - check state before acting (at-least-once delivery). A status guard is check-then-act and can still race a redelivery; when the side effect leaves the process (a charge, an email), carry an idempotency key derived from the entity ID so the provider deduplicates what the guard misses
- Payloads carry IDs / primitives, never `sqlx::FromRow` models or internal structs
- Configure max attempts, a per-job timeout, and a dead-letter state per job kind. A job with no timeout holds a worker for as long as the call hangs and starves every kind behind it
- `job timeout < drain budget < platform grace period` (Kubernetes default 30s). On SIGTERM the worker stops claiming and finishes its current job inside the drain budget; when the process exits first, dropping the runtime cancels the job at its next `.await`, the row stays `running` until its lease lapses, and it is redelivered - which is how a non-idempotent handler duplicates its side effect on every rolling deploy
- Classify errors transient (retry) vs permanent (dead-letter at once). A third class matters: an *indeterminate* outcome (the call timed out, or `tokio::time::timeout` dropped the future mid-request, so the side effect may or may not have happened) is resolved by re-sending under the same idempotency key (Stripe keeps keys for at least 24h, so the retry schedule must end inside that window) or by a read keyed on a reference you set (`metadata`, your order id - a not-found right after a timeout proves nothing while the provider's search index lags), never by a blind retry
- A job reaches its queue atomically with the state change: a Postgres job row is inserted **inside** the business transaction; an external broker (Kafka, Redis, AMQP) is never called inside it - publish through the outbox, or after commit backed by a reconciliation sweep
- Workers own their lifecycle: tracked in a `JoinSet`, stopped by a `CancellationToken`, never a detached `tokio::spawn`

## Patterns

### Job Definition and Transactional Enqueue

```rust
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Postgres, Transaction, types::Json};
use uuid::Uuid;

pub const KIND_PROCESS_ORDER: &str = "order.process";

#[derive(Serialize, Deserialize)]
pub struct ProcessOrder { pub order_id: Uuid } // the ID, never the row

// Called with the order insert's transaction: the job becomes visible exactly when the order does,
// so there is no "worker ran before commit" race and no lost dispatch on a crash after commit.
pub async fn enqueue_process_order(tx: &mut Transaction<'_, Postgres>, order_id: Uuid) -> Result<(), sqlx::Error> {
    sqlx::query("INSERT INTO jobs (kind, payload, max_attempts, timeout_secs) VALUES ($1, $2, 5, 30)")
        .bind(KIND_PROCESS_ORDER)
        .bind(Json(ProcessOrder { order_id }))
        .execute(&mut **tx)
        .await?;
    Ok(())
}
```

The job table is the default for a sqlx + PostgreSQL service: enqueue is transactional for free. Dispatching to Redis or a broker instead has the dual-write problem - after commit plus a sweep that re-enqueues entities missing their job, or the outbox below. Size the sweep's interval by how long an undispatched entity may go unnoticed, and alert on the backlog.

### Claim, Run, Settle

```rust
use std::time::Duration;
use tokio::time::error::Elapsed;
use tokio_util::sync::CancellationToken;

#[derive(sqlx::FromRow)]
pub struct Job { pub id: i64, pub kind: String, pub payload: serde_json::Value, pub attempts: i32, pub max_attempts: i32, pub timeout_secs: i32 }

#[derive(Debug, thiserror::Error)]
pub enum JobError {
    #[error("transient: {0}")] Transient(anyhow::Error),
    #[error("permanent: {0}")] Permanent(anyhow::Error),
    #[error("indeterminate: {0}")] Indeterminate(anyhow::Error),
}

// One statement, so the status + lease update IS the claim (the row lock ends with the statement).
// A lapsed lease - the worker died mid-job - is reclaimable: that is the redelivery path.
const CLAIM: &str = "UPDATE jobs SET status = 'running', attempts = attempts + 1,
       locked_until = now() + make_interval(secs => timeout_secs + 30)
 WHERE id IN (SELECT id FROM jobs
               WHERE (status = 'queued' AND run_at <= now()) OR (status = 'running' AND locked_until < now())
               ORDER BY run_at LIMIT 1 FOR UPDATE SKIP LOCKED)
 RETURNING id, kind, payload, attempts, max_attempts, timeout_secs";

pub async fn run_worker(pool: PgPool, deps: Deps, token: CancellationToken) {
    while !token.is_cancelled() { // shutdown stops the next claim, never the job in hand
        let job = match sqlx::query_as::<_, Job>(CLAIM).fetch_optional(&pool).await {
            Ok(j) => j,
            Err(e) => { tracing::warn!(error = %e, "claim failed"); None } // transient: never kill the worker
        };
        let Some(job) = job else {
            tokio::select! { _ = token.cancelled() => break, _ = tokio::time::sleep(Duration::from_secs(1)) => {} }
            continue;
        };
        let outcome = tokio::time::timeout(Duration::from_secs(job.timeout_secs as u64), dispatch(&deps, &job)).await;
        if let Err(e) = settle(&pool, &job, outcome).await { // lease lapses, job redelivers; handlers are idempotent
            tracing::error!(job_id = job.id, error = %e, "settle failed");
        }
    }
}

async fn settle(pool: &PgPool, job: &Job, outcome: Result<Result<(), JobError>, Elapsed>) -> Result<(), sqlx::Error> {
    let (status, err) = match outcome {
        Ok(Ok(())) => ("done", None),
        Ok(Err(e @ JobError::Permanent(_))) => ("dead", Some(e.to_string())),
        Ok(Err(e)) if job.attempts >= job.max_attempts => ("dead", Some(e.to_string())),
        Err(_) if job.attempts >= job.max_attempts => ("dead", Some("timeout, attempts exhausted".to_owned())),
        Ok(Err(e)) => ("queued", Some(e.to_string())), // transient or indeterminate: retried under the same key
        Err(_) => ("queued", Some("timeout - outcome indeterminate".to_owned())),
    };
    sqlx::query("UPDATE jobs SET status = $2, last_error = $3, locked_until = NULL,
                 run_at = now() + make_interval(secs => power(2, attempts)) WHERE id = $1")
        .bind(job.id).bind(status).bind(err).execute(pool).await?;
    Ok(())
}
```

`Deps` is the service's own bundle of repositories and clients. A job too long for the grace period cannot be made legal by raising `timeout_secs` - split it into chunks that each fit, each persisting its progress so a redelivery resumes.

### Handler with Error Classification

```rust
pub enum PaymentError { Declined(String), Timeout, Other(anyhow::Error) }

async fn dispatch(deps: &Deps, job: &Job) -> Result<(), JobError> {
    match job.kind.as_str() {
        KIND_PROCESS_ORDER => {
            let p: ProcessOrder = serde_json::from_value(job.payload.clone())
                .map_err(|e| JobError::Permanent(e.into()))?; // malformed payload never succeeds
            process_order(deps, p.order_id).await
        }
        other => Err(JobError::Permanent(anyhow::anyhow!("no handler for kind {other}"))),
    }
}

async fn process_order(deps: &Deps, order_id: Uuid) -> Result<(), JobError> {
    let order = match deps.orders.find(order_id).await {
        Ok(Some(o)) => o,
        Ok(None) => { tracing::warn!(%order_id, "order gone"); return Ok(()) } // deleted since enqueue: Ignore
        Err(e) => return Err(JobError::Transient(e.into())),
    };
    if order.processed { return Ok(()); } // idempotency guard
    // the same key on every attempt: the provider replays instead of charging twice
    match deps.payments.charge(&order, &format!("order-{order_id}")).await {
        Ok(_) => Ok(()),
        Err(PaymentError::Declined(r)) => Err(JobError::Permanent(anyhow::anyhow!("declined: {r}"))),
        Err(PaymentError::Timeout) => match deps.payments.find_by_order_ref(order_id).await {
            Ok(Some(_)) => Ok(()), // the charge landed
            _ => Err(JobError::Indeterminate(anyhow::anyhow!("charge outcome unknown"))),
        },
        Err(PaymentError::Other(e)) => Err(JobError::Transient(e)),
    }
}
```

### Scheduled Tasks

A bare `tokio::time::interval` runs once per replica, so N replicas do the work N times. Let every replica tick and insert the period's job under a unique `dedupe_key`; exactly one insert wins, and the work gains the queue's retries, timeout and visibility.

```rust
// inside the ticker loop, every replica; a unique index on dedupe_key lets one insert win
let hour = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_secs() / 3600;
sqlx::query("INSERT INTO jobs (kind, payload, dedupe_key) VALUES ('orders.reconcile', '{}', $1) ON CONFLICT (dedupe_key) DO NOTHING")
    .bind(format!("orders.reconcile:{hour}")).execute(&pool).await?;
```

### Kafka Consumer (rdkafka)

```rust
use rdkafka::config::ClientConfig;
use rdkafka::consumer::{CommitMode, Consumer, StreamConsumer};
use rdkafka::message::{BorrowedMessage, Message};

let consumer: StreamConsumer = ClientConfig::new()
    .set("bootstrap.servers", &brokers)
    .set("group.id", &group_id)
    // default true commits on a timer the offsets recv() already returned - a crash mid-handler loses the record
    .set("enable.auto.commit", "false")
    .create()?;
consumer.subscribe(&[topic])?;

loop {
    let msg = tokio::select! {
        _ = token.cancelled() => break, // a record dropped here was never committed: it replays
        r = consumer.recv() => match r {
            Ok(m) => m,
            // transient: librdkafka reconnects. `while let Ok(msg) = consumer.recv().await` exits on the first one
            Err(e) => { tracing::warn!(error = %e, "kafka recv"); continue }
        },
    };
    handle_record(&ctx, &msg).await?; // Err only when the record could be neither handled nor parked: halt, replay
    consumer.commit_message(&msg, CommitMode::Async)?;
}
```

Async commits still in flight at exit only cause replay. A blocking call (`std::thread::sleep`, sync I/O) in this loop stalls polling past `max.poll.interval.ms` and triggers a rebalance - see `rust-async-patterns`.

### Dead-Letter Topic

A record that can never succeed must leave the partition, or it blocks it indefinitely - the poison-message wedge (other partitions keep moving, so lag shows as one stuck partition). Permanent errors go straight to the DLQ, transient ones get a fixed attempt budget and then follow. A failure every record would share (the store is down) is neither: return it and halt - parking would drain valid records into the DLQ.

```rust
use rdkafka::message::{Header, OwnedHeaders};
use rdkafka::producer::{FutureProducer, FutureRecord};
use rdkafka::util::Timeout;

pub enum HandleError { Outage(anyhow::Error), Permanent(anyhow::Error), Transient(anyhow::Error) }

pub struct Ctx { pub producer: FutureProducer, pub handler: RecordHandler } // RecordHandler: the service's own

const MAX_ATTEMPTS: u32 = 5;
fn backoff(attempt: u32) -> Duration { Duration::from_millis(100 * 2_u64.pow(attempt)) }

async fn handle_record(ctx: &Ctx, msg: &BorrowedMessage<'_>) -> anyhow::Result<()> {
    let payload = msg.payload().unwrap_or_default();
    let mut last = String::new();
    for attempt in 1..=MAX_ATTEMPTS {
        match ctx.handler.handle(payload).await {
            Ok(()) => return Ok(()),
            Err(HandleError::Outage(e)) => return Err(e), // down for every record: halt and replay, never park
            Err(HandleError::Permanent(e)) => { last = e.to_string(); break } // schema, version, unknown reference
            Err(HandleError::Transient(e)) => { last = e.to_string(); tokio::time::sleep(backoff(attempt)).await }
        }
    }
    let offset = msg.offset().to_string();
    let headers = OwnedHeaders::new()
        .insert(Header { key: "dlq_reason", value: Some(last.as_str()) })
        .insert(Header { key: "dlq_offset", value: Some(offset.as_str()) });
    let dlq_topic = format!("{}.dlq", msg.topic());
    let record = FutureRecord::to(&dlq_topic).key(msg.key().unwrap_or_default()).payload(payload).headers(headers);
    ctx.producer.send(record, Timeout::After(Duration::from_secs(10))).await
        .map_err(|(e, _)| anyhow::anyhow!("dlq produce (cause {last}): {e}"))?; // never commit past an unparked record
    Ok(())
}
```

Alert on DLQ depth and on the job table's `dead` count; a job failing its full budget every day for a month is invisible without it. Consumer lag that grows linearly means arrival rate exceeds processing rate - add members up to the partition count first (members beyond that are idle), then take blocking I/O off the per-record path.

### In-Process Worker Pool

```rust
use std::sync::Arc;
use tokio::sync::{Mutex, mpsc};
use tokio::task::JoinSet;

let (tx, rx) = mpsc::channel::<Job>(1024); // bounded: tx.send(job).await is the backpressure; unbounded_channel is OOM
let rx = Arc::new(Mutex::new(rx));
let mut workers = JoinSet::new();
for _ in 0..concurrency {
    let (rx, token, deps) = (rx.clone(), token.clone(), deps.clone());
    workers.spawn(async move {
        loop {
            let job = tokio::select! {
                _ = token.cancelled() => break,
                j = async { rx.lock().await.recv().await } => match j { Some(j) => j, None => break },
            };
            if let Err(e) = dispatch(&deps, &job).await { tracing::error!(job_id = job.id, error = %e, "job failed"); }
        }
    });
}
while let Some(r) = workers.join_next().await { r?; } // a worker panic surfaces as JoinError, not a silent exit
```

An in-process queue has no redelivery: a job that must survive a crash is a job-table row, not a channel message.

### Transactional Outbox (Kafka / reliable publish)

Dual-write to DB + broker is not atomic. Write the event row in the same transaction; a relay publishes:

```rust
// In the business transaction
let mut tx = pool.begin().await?;
let order_id = insert_order(&mut tx, &req).await?;
sqlx::query("INSERT INTO outbox (aggregate_id, event_type, payload) VALUES ($1, 'order.created', $2)")
    .bind(order_id).bind(Json(&event)).execute(&mut *tx).await?;
tx.commit().await?;

// Relay (its own task or binary; consumers stay idempotent under double delivery).
// CLAIM_OUTBOX is one UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING id,
// aggregate_id::text AS key, payload::text AS body, setting claimed_at (see rust-db-access): the claim
// must be the mark - a bare SELECT double-publishes once the relay has two replicas. Rows whose
// claimed_at is older than the lease (5 min) are re-claimable: that is the retry path.
#[derive(sqlx::FromRow)]
struct OutboxEvent { id: i64, key: String, body: String }

let events: Vec<OutboxEvent> = sqlx::query_as(CLAIM_OUTBOX).bind(100_i64).fetch_all(&pool).await?;
for ev in events {
    let record = FutureRecord::to("orders").key(ev.key.as_str()).payload(ev.body.as_str());
    // send().await resolves on the broker ack; marking published before it loses the event on a nack
    if let Err((e, _)) = producer.send(record, Timeout::After(Duration::from_secs(10))).await {
        tracing::error!(id = ev.id, error = %e, "outbox publish"); // not marked - lease expiry retries it
        continue;
    }
    if let Err(e) = sqlx::query("UPDATE outbox SET published_at = now() WHERE id = $1").bind(ev.id).execute(&pool).await {
        tracing::error!(id = ev.id, error = %e, "outbox mark"); // republished once; consumers are idempotent
    }
}
```

Set `enable.idempotence=true` on the producer (it implies `acks=all`) so a librdkafka retry does not duplicate within a partition.

### Inbound Events (webhooks, consumed topics)

An inbound event is applied through an **inbox**: insert `(provider, event_id)` into a unique-keyed table in the same transaction as the state change; a unique violation (`sqlx::Error::Database(e) if e.is_unique_violation()`) means the event was already applied, so acknowledge without acting. A status guard alone races two concurrent deliveries. Outbound callbacks to a partner URL are jobs like any other: retry budget, timeout, a `2xx` is the ack, and the partner is told to expect duplicates.

## Stack Notes

- **Job table**: default for sqlx + PostgreSQL; `apalis` (Postgres or Redis backend) when already present - its retry and timeout layers replace the columns above
- **rdkafka**: builds its bundled librdkafka with a C toolchain and `make` (`cmake-build` switches to CMake, `dynamic-linking` to a system library); `lapin` for AMQP - `no_ack: false`, ack after success, `nack { requeue: false }` into a dead-letter exchange

## Output Format

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design | `## Messaging Design` with the five tables; code for each new job kind, consumer, relay or inbound handler follows under `### <Job, loop or inbound handler>` headings in table order; decisions with no column (grace-period change, worker count against the DB pool share - sizing in `rust-db-access`, job table vs outbox) are one sentence each under the tables |
| Review | `## Findings`, then `## Messaging Design` describing the system as it exists today |
| Incident | two opening lines `**Failing:**` and `**First fix:**`, then `## Findings`, then `## Messaging Design` as it exists today |

```
## Messaging Design

### Job Types
| Kind | Queue | Payload | Max Attempts | Timeout | Idempotency Check |
|------|-------|---------|--------------|---------|-------------------|

### Error Classification
| Error | Classification | Action |
|-------|----------------|--------|

### Kafka Topics
| Topic | Producer | Consumer Group | Delivery | Outbox? |
|-------|----------|----------------|----------|---------|

### Dispatch Timing
| Event | Dispatch Point |
|-------|----------------|

### Lifecycle
| Setting | Value | Rationale |
|---------|-------|-----------|
```

Cell values: `Classification` is `Transient | Permanent | Indeterminate | Ignore | Fatal` - `Ignore` for work that is no longer needed (entity deleted), `Fatal` for "cannot process and cannot park" or a dependency down for every record, which must stop the consumer rather than commit; on a review or incident it is the class the code **gives** the error today (an unclassified error bubbled with `?` takes whatever the worker's catch-all arm does with it), and the intended class goes in the finding's `Fix`. `Idempotency Check` is `status guard | provider key | inbox row | none`; a handler with two checks lists both joined by `+`. `Delivery` is `at-least-once | at-most-once | effectively-once` - `at-most-once` when an offset can be committed or a job marked done while its side effect is still in flight (`enable.auto.commit` left on, a commit before the handler returns, a publish not awaited before the mark); `effectively-once` is at-least-once plus an inbox row or provider key on every side effect; `unknown` when the consumer is not visible. `Producer` is this service's loop or binary, or `external`; a DLQ topic's producer is the consumer that parks into it. `Outbox?` is `Yes | No | n/a (external producer)` - `unknown` when the relay is visible but its insert site is not. `Consumer Group` is `none` for a topic this service only produces. `Queue` is the job table, apalis storage or broker queue. `Timeout` and `Max Attempts` state the effective value, naming the default when unset (the column default, or `none` when nothing bounds it). A job that cannot finish inside the grace period checkpoints per unit and re-enqueues its remainder; its `Timeout` still sits under the drain budget. `Fatal` is a consumer-loop class; a startup `expect` is not a classification row. A job kind enqueued with no dispatch arm keeps its `Job Types` row, `Idempotency Check` reading `none`. `Dispatch Timing` has one row per enqueue site, `Dispatch Point` reading `inside <transaction> (job row)`, `inside <transaction> (outbox row)`, `after <transaction> commits` (an autocommit write is its own transaction), or `inside <transaction> (external broker call)` - the last always paired with a finding; an enqueue with no state change to join (a ticker's period job) reads `no transaction (single statement)`; a job kind defined but never enqueued reads `never enqueued`; an inbound event (webhook, consumed record) reads `on receipt, inside the inbox transaction`, or `on receipt, no inbox` - paired with a finding unless every side effect carries a provider key. `Lifecycle` has one row per setting per process (drain budget, worker count, channel capacity, the platform grace period) and one row per loop that is not a job (outbox relay, consumer with its commit mode, ticker), naming its owner and exit. On a design engagement an existing job kept as-is is marked `(existing)`. A table with no rows (no Kafka, no job table) keeps its heading and holds the single line `None.` A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries. `**Failing:**` names the symptom; `**First fix:**` the one change that stops it - the rest follow in `## Findings` order.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol> | <job kind or subsystem>}

- Defect: {what goes wrong in production}
- Rule: {the messaging rule violated}
- Fix: {concrete edit}
```

Owned findings: `[Must]` for a duplicated or lost side effect, a dropped dispatch (a broker call inside the transaction, a `let _ =` on the enqueue), a wedged or unboundedly lagging consumer, a worker starved by untimed work, an unbounded retry, work lost on deploy, or a detached or panicking worker task; `[Recommend]` otherwise - judge by consequence, not by matching the list. Cite `file:line` when the input carries line numbers (a Kubernetes manifest is a file like any other), `file:<symbol>` or the job kind / subsystem when the input is incident evidence; a range is `file:start-end`. Order the blocks in four groups - owned `[Must]`, owned `[Recommend]`, then the not-owned blocks described below, `[Must]` then `[Recommend]` - and within a group by file in the order the input listed them (a listed directory's files in path order at the directory's position, a file listed twice at its first; files the input did not list after those, in path order), then position in the file. With no findings, `## Findings` holds the single line `None.` One root cause at several sites (the same unguarded handler shape in three job kinds) is one heading citing the first site in that order, with the rest named on the `Defect:` line; when distinct findings share one cause, say so - fixing idempotency and timeouts usually collapses most of an incident's list. An incident question is answered inside the `Defect:` line of the finding it concerns. A defect this skill does not own (webhook authentication, the HTTP handling of a webhook, DB pool sizing) is still reported, never dropped: one block per such defect in the last two groups, labelled `[Must]` when it risks incorrect behaviour, data loss or a security hole and `[Recommend]` otherwise, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- `let _ =` or `.ok()` on an enqueue or publish result
- `enable.auto.commit` left on while the handler can fail
- `while let Ok(msg) = consumer.recv().await` - the first broker error ends consumption silently
- `std::process::exit` or `panic!` inside a consumer loop - a broker election becomes a crash loop
