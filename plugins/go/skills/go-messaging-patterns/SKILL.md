---
name: go-messaging-patterns
description: "Go async messaging: Asynq (Redis) jobs with retry classification, Kafka via franz-go, transactional outbox, in-process worker pools."
metadata:
  category: backend
  tags: [asynq, kafka, messaging, background-jobs, async, redis, idempotency]
user-invocable: false
---

# Go Messaging Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Offloading > 200ms work or external-service calls
- Kafka consumption
- Periodic / scheduled tasks
- In-process worker pools for bounded parallelism

## Rules

- Handlers must be idempotent - check state before acting (at-least-once delivery). A status guard is check-then-act and can still race a redelivery; when the side effect leaves the process (a charge, an email), carry an idempotency key derived from the entity ID so the provider deduplicates what the guard misses
- Payloads carry IDs / primitives, never structs with unexported fields or DB models
- Configure max retries, timeout, and dead-letter strategy per task type. A task with no timeout holds a worker slot for the broker's default and starves every queue on that server
- `task Timeout < server ShutdownTimeout < platform grace period`. Asynq's `ShutdownTimeout` defaults to 8s, so any task longer than that is cut off on every rolling deploy, then redelivered by lease expiry - which is how a non-idempotent handler duplicates its side effect
- Classify errors transient (retry) vs permanent (`asynq.SkipRetry`). A third class matters: an *indeterminate* outcome (the call timed out, so the side effect may or may not have happened) must be resolved by querying the provider, never by a blind retry
- Workers honor `ctx` for cancellation and shutdown
- Dispatch background jobs **after** the DB transaction commits, never inside
- Use `errgroup` for worker lifecycle

## Patterns

### Asynq Task Definition

```go
const TypeProcessOrder = "order:process"

type ProcessOrderPayload struct {
    OrderID string `json:"order_id"`
}

func NewProcessOrderTask(orderID string) (*asynq.Task, error) {
    payload, err := json.Marshal(ProcessOrderPayload{OrderID: orderID})
    if err != nil { return nil, err }
    return asynq.NewTask(TypeProcessOrder, payload,
        asynq.MaxRetry(3),
        asynq.Timeout(30*time.Second),
        asynq.Queue("default"),
    ), nil
}
```

### Dispatch After Commit

Enqueueing inside a transaction can race the commit - the worker may pick the task up before the row is visible.

```go
order, err := s.repo.Create(ctx, req) // commits internally
if err != nil { return nil, fmt.Errorf("create order: %w", err) }

task, _ := tasks.NewProcessOrderTask(order.ID)
if _, err := s.client.EnqueueContext(ctx, task); err != nil {
    // Logging is not the recovery. This is only safe because a scheduled
    // reconciliation re-enqueues orders with no task - without that backstop a
    // broker outage silently drops every dispatch in the window.
    slog.Error("enqueue failed", "order_id", order.ID, "err", err)
}
return order, nil
```

Asynq's persistence protects a task that reached Redis; it does nothing for one that never arrived. Pair post-commit enqueue with **one** of: a reconciliation job that finds entities missing their task, or a dispatch row written inside the business transaction and relayed (the outbox below). Choose by asking how long an undispatched entity may go unnoticed - and alert on the backlog, since a week to detection is usually the more expensive half.

### Handler with Error Classification

Asynq retries by default. Wrap permanent errors with `asynq.SkipRetry`.

```go
func HandleProcessOrder(repo OrderRepository, svc FulfillmentService) asynq.HandlerFunc {
    return func(ctx context.Context, t *asynq.Task) error {
        var p tasks.ProcessOrderPayload
        if err := json.Unmarshal(t.Payload(), &p); err != nil {
            // carry the cause - bare SkipRetry leaves a blank dead-task log
            return fmt.Errorf("unmarshal payload: %v: %w", err, asynq.SkipRetry) // permanent
        }

        order, err := repo.FindByID(ctx, p.OrderID)
        if errors.Is(err, ErrNotFound) {
            slog.Warn("order not found", "order_id", p.OrderID)
            return nil // deleted between enqueue and execute - skip
        }
        if err != nil { return fmt.Errorf("find order: %w", err) } // transient

        if order.Status == "processed" { return nil } // idempotency guard

        if err := svc.Process(ctx, p.OrderID); err != nil {
            if errors.Is(err, ErrPaymentDeclined) {
                return fmt.Errorf("process: %w", asynq.SkipRetry)
            }
            return fmt.Errorf("process: %w", err)
        }
        return nil
    }
}
```

### Server with Queue Priorities

```go
srv := asynq.NewServer(
    asynq.RedisClientOpt{Addr: cfg.RedisAddr},
    asynq.Config{
        Queues:      map[string]int{"critical": 6, "default": 3, "low": 1},
        Concurrency: 10,
        // Default is 8s - below almost every real task. Set it above the longest
        // task Timeout, and set the pod's grace period above this.
        ShutdownTimeout: 60 * time.Second,
        ErrorHandler: asynq.ErrorHandlerFunc(func(ctx context.Context, task *asynq.Task, err error) {
            slog.Error("task failed", "type", task.Type(), "err", err)
        }),
    },
)
mux := asynq.NewServeMux()
mux.HandleFunc(tasks.TypeProcessOrder, handlers.HandleProcessOrder(repo, svc))
if err := srv.Run(mux); err != nil { log.Fatalf("asynq: %v", err) } // Run blocks and shuts down on SIGTERM
```

Asynq's per-task timeout defaults to 30 minutes when `asynq.Timeout` is unset, so an untimed task holds its worker slot for that long. A task that genuinely needs longer than the grace period allows cannot be made legal by raising `Timeout` - split it into chunks that each fit.

### Scheduled Tasks

Prefer `asynq.Scheduler` over `time.Ticker` in a goroutine. A ticker runs once per replica, so N replicas do the work N times with no coordination; the scheduler enqueues once and one worker picks it up, and the work gains retries, a timeout, ctx cancellation, panic recovery, and queue visibility. Run the scheduler as a single instance.

```go
scheduler := asynq.NewScheduler(asynq.RedisClientOpt{Addr: cfg.RedisAddr}, nil)
task, _ := tasks.NewReconcileOrdersTask()
scheduler.Register("0 * * * *", task, asynq.Queue("low"))
if err := scheduler.Run(); err != nil { log.Fatalf("scheduler: %v", err) }
```

### Kafka Consumer (franz-go)

```go
client, err := kgo.NewClient(
    kgo.SeedBrokers(brokers...),
    kgo.ConsumerGroup(groupID),
    kgo.ConsumeTopics(topic),
    kgo.DisableAutoCommit(), // default autocommits polled offsets every 5s - even for records still in the handler
)
if err != nil { return fmt.Errorf("kafka client: %w", err) }
defer client.Close()

for {
    fetches := client.PollFetches(ctx)
    if fetches.IsClientClosed() || ctx.Err() != nil { return nil }
    fetches.EachError(func(_ string, _ int32, err error) {
        slog.Error("kafka fetch error", "err", err)
    })
    // EachRecord cannot break, so latch the first unresolvable error and skip the
    // rest rather than committing offsets for work that never happened.
    var fatal error
    fetches.EachRecord(func(r *kgo.Record) {
        if fatal != nil { return }
        fatal = handleRecord(ctx, client, r) // nil once the record is processed OR parked
    })
    if fatal != nil {
        return fmt.Errorf("consumer halted: %w", fatal) // restart and replay; do not commit
    }
    client.CommitUncommittedOffsets(ctx) // every record in the batch handled or DLQ'd
}
```

### Dead-Letter Queue

A record that can never succeed must leave the partition, or it blocks its consumer group indefinitely - the poison-message wedge. Bound both exits: permanent errors go straight to the DLQ, transient ones get a fixed attempt budget and then follow.

```go
// Returns nil when the record is resolved - processed, or parked in the DLQ.
// Non-nil only when neither was possible, because the alternative is committing
// an offset for work that never happened.
func handleRecord(ctx context.Context, cl *kgo.Client, r *kgo.Record) error {
    var last error
    for attempt := 1; attempt <= maxAttempts; attempt++ {
        if last = handler(ctx, r.Value); last == nil { return nil }
        if isPermanent(last) { break } // schema, version, unknown reference
        // backoff, honouring ctx
    }
    dlq := &kgo.Record{Topic: r.Topic + ".dlq", Key: r.Key, Value: r.Value,
        Headers: append(r.Headers,
            kgo.RecordHeader{Key: "dlq_reason", Value: []byte(last.Error())},
            kgo.RecordHeader{Key: "dlq_offset", Value: []byte(strconv.FormatInt(r.Offset, 10))})}
    if err := cl.ProduceSync(ctx, dlq).FirstErr(); err != nil {
        return fmt.Errorf("dlq produce (cause %v): %w", last, err)
    }
    return nil
}
```

Alert on DLQ depth and on Asynq's archived set; a task failing its full retry budget every day for a month is invisible without it. Consumer lag that grows linearly means arrival rate exceeds processing rate - add members up to the partition count first (members beyond that are idle), then take blocking I/O off the per-record path.

### In-Process Worker Pool

```go
g, ctx := errgroup.WithContext(ctx)
for range concurrency {
    g.Go(func() error {
        for {
            select {
            case job, ok := <-jobs:
                if !ok { return nil }
                if err := job.Execute(ctx); err != nil {
                    slog.Error("job failed", "id", job.ID, "err", err)
                }
            case <-ctx.Done(): return ctx.Err()
            }
        }
    })
}
return g.Wait()
```

### Transactional Outbox (Kafka / reliable publish)

Dual-write to DB + broker is not atomic. Write the event row in the same transaction; a relay publishes:

```go
// In the business transaction
err := s.db.RunInTx(ctx, func(tx pgx.Tx) error {
    order, err = s.repo.CreateTx(ctx, tx, req)
    if err != nil { return err }
    return s.outboxRepo.InsertTx(ctx, tx, OutboxEvent{
        AggregateID: order.ID,
        EventType:   "order.created",
        Payload:     mustMarshal(orderEvent(order)),
    })
})

// Relay (separate goroutine/process; consumers stay idempotent under double-delivery).
// ClaimPending uses FOR UPDATE SKIP LOCKED (see go-data-access) - bare SELECT double-publishes
// every event once the relay runs more than one replica.
events, _ := r.outboxRepo.ClaimPending(ctx, 100)
for _, ev := range events {
    // ProduceSync: async Produce returns before broker ack - marking published on a nack loses the event
    if err := r.kafka.ProduceSync(ctx, recordFor(ev)).FirstErr(); err != nil {
        slog.Error("kafka produce", "id", ev.ID, "err", err)
        continue // not marked - claim expiry returns it for retry
    }
    r.outboxRepo.MarkPublished(ctx, ev.ID)
}
```

For Asynq (Redis-backed), post-commit enqueue plus a reconciliation sweep is the default - Asynq's persistence covers a task that reached Redis, and the sweep covers one that never did. Reserve the outbox for Kafka and other external brokers, where a lost publish has no equivalent backstop. Size the sweep's interval by how long an undispatched entity may go unnoticed; a nightly job means a broker blip is invisible until tomorrow.

## Stack Notes

- **Asynq**: best fit for Redis-backed single-service queues; `asynqmon` for web UI
- **franz-go**: preferred Kafka client (pure Go, low alloc); use `sarama` only if already present
- **Graceful shutdown**: `srv.Shutdown()` on `SIGTERM` waits for in-progress tasks

## Edge Cases

- Malformed payload: permanent error (`asynq.SkipRetry`)
- Entity deleted between enqueue and execute: return nil, don't retry
- Redis unavailable at enqueue: degrade per use case (log + continue if best-effort, fail otherwise)
- At-least-once means duplicates: always idempotency-guard before side effects
- Auto-commit Kafka offsets before processing drops messages on crash - manual commit only

## Output Format

Design engagements emit `## Messaging Design`. Review and incident engagements emit `## Findings` first, then the design tables describing the system **as it exists today**.

```
## Messaging Design

### Task Types
| Type | Queue | Payload | MaxRetry | Timeout | Idempotency Check |
|------|-------|---------|----------|---------|-------------------|

### Error Classification
| Error | Classification | Action |
|-------|----------------|--------|

### Kafka Topics
| Topic | Producer | Consumer Group | Delivery | Outbox? |
|-------|----------|----------------|----------|---------|

### Dispatch Timing
| Event | After Which Commit |
|-------|--------------------|

### Lifecycle
| Setting | Value | Rationale |
|---------|-------|-----------|
```

Cell values: `Classification` is `Transient | Permanent | Indeterminate | Ignore | Fatal` - `Ignore` for work that is no longer needed (entity deleted), `Fatal` for "cannot process and cannot park", which must stop the consumer rather than commit. `Delivery` is `at-least-once | at-most-once | effectively-once`. `Outbox?` is `Yes | No`. `Timeout` and `MaxRetry` state the effective value, naming the default when unset. `Lifecycle` carries `ShutdownTimeout`, `Concurrency`, queue weights, and the platform grace period - the settings the timeout invariant depends on. A cell the input does not supply is `unknown`. Loops that are not broker tasks (outbox relay, consumer) get a `Lifecycle` row, not a `Task Types` row. On a review or incident engagement the tables describe what the code does today, so `Action` and `Rationale` record the observed behaviour and its consequence - the corrected value belongs in the finding's `Fix`, not the table.

```
## Findings

### [Must] file:line

- Defect: {what goes wrong in production}
- Rule: {the messaging rule violated}
- Fix: {concrete edit}
```

`[Must]` for a duplicated or lost side effect, a dropped dispatch, a wedged or unboundedly lagging consumer, a queue starved by untimed work, an unbounded retry, or work lost on deploy; `[Recommend]` otherwise - judge by consequence, not by matching the list. Order `[Must]` first. When the input is incident evidence rather than code, cite the task type or subsystem in place of `file:line` and fill unavailable cells with `unknown`. When several findings share one cause, say so - fixing idempotency and timeouts usually collapses most of an incident's list.

## Avoid

- Large structs / DB models in payloads
- Tasks without timeout
- Ignoring `EnqueueContext` errors
- Enqueueing inside a transaction
- Retrying permanent failures
- Auto-committing Kafka offsets before handler success
