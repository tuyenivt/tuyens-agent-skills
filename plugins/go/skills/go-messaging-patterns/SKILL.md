---
name: go-messaging-patterns
description: "Go async messaging: Asynq (Redis) jobs with retry classification, Kafka via franz-go, transactional outbox, in-process worker pools."
metadata:
  category: backend
  tags: [asynq, kafka, messaging, background-jobs, async, redis, idempotency]
user-invocable: false
---

# Go Messaging Patterns

> Load `Use skill: stack-detect` first. This skill reads the `Additional` lines that name a broker (`Queue:`, `Kafka:`), falling back to the `go.mod` require line (`hibiken/asynq`, `twmb/franz-go`) when none is declared; the Go version is the `go` directive in `go.mod` (a `## Tech Stack` `Language:` line may carry a version; the directive wins when they differ). Baseline: Go 1.25+ (`for range n` needs 1.22+), Asynq v0.25+, franz-go v1.18+. A project on another broker (NATS, RabbitMQ, Watermill) keeps the rules and the Output Format; the Asynq / franz-go API lines do not transfer and are omitted.

## When to Use

- Offloading > 200ms work or external-service calls
- Kafka consumption
- Periodic / scheduled tasks
- In-process worker pools for bounded parallelism

## Rules

- Handlers must be idempotent - check state before acting (at-least-once delivery). A status guard is check-then-act and can still race a redelivery; when the side effect leaves the process (a charge, an email), carry an idempotency key derived from the entity ID so the provider deduplicates what the guard misses
- Payloads carry IDs / primitives, never structs with unexported fields or DB models
- Configure max retries, timeout, and dead-letter strategy per task type. A task with no timeout holds a worker slot for the broker's default and starves every queue on that server
- `task Timeout < server ShutdownTimeout < platform grace period`. Asynq's `ShutdownTimeout` defaults to 8s; when it expires the server cancels the task's `ctx` and requeues the task straight to `pending`, and a SIGKILL after the grace period leaves it to lease expiry, which the recoverer counts as an attempt (retry set, or archived once `Retried >= MaxRetry`) - either way a surviving task is redelivered, which is how a non-idempotent handler duplicates its side effect on every rolling deploy
- Classify errors transient (retry) vs permanent (`asynq.SkipRetry`). A third class matters: an *indeterminate* outcome (the call timed out, so the side effect may or may not have happened) is resolved by re-sending under the same idempotency key (the provider replays the stored result; Stripe keeps keys for at least 24h, so the retry schedule must end inside that window) or by a read keyed on a reference you set (`metadata`, your order id - Stripe has no lookup by idempotency key, and its Search API lags by up to a minute, so a not-found right after a timeout proves nothing), never by a blind retry
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
        asynq.Unique(time.Hour), // one copy per queue + type + payload until it completes or the TTL lapses - a copy in the retry set or archive still holds it; a duplicate enqueue returns asynq.ErrDuplicateTask
    ), nil
}
```

### Dispatch After Commit

Enqueueing inside a transaction can race the commit - the worker may pick the task up before the row is visible.

```go
order, err := s.repo.Create(ctx, req) // commits internally
if err != nil { return nil, fmt.Errorf("create order: %w", err) }

task, _ := tasks.NewProcessOrderTask(order.ID)
if _, err := s.client.EnqueueContext(ctx, task); err != nil && !errors.Is(err, asynq.ErrDuplicateTask) { // a copy still holds the Unique lock - live, retrying or archived; the sweep re-checks after the TTL
    // Logging is not the recovery. This is only safe because a scheduled
    // reconciliation re-enqueues orders with no task - without that backstop a
    // broker outage silently drops every dispatch in the window.
    slog.Error("enqueue failed", "order_id", order.ID, "err", err)
}
return order, nil
```

Asynq's persistence protects a task that reached Redis - given AOF (`appendonly yes`; `appendfsync always`, or accept the ~1s loss window of `everysec`) and `maxmemory-policy noeviction`; it does nothing for a task that never arrived. Pair post-commit enqueue with a reconciliation sweep that finds entities missing their task; the outbox below is for Kafka and other external brokers. Size the sweep's interval by how long an undispatched entity may go unnoticed - and alert on the backlog, since a week to detection is usually the more expensive half.

### Handler with Error Classification

Asynq retries by default. Wrap permanent errors with `asynq.SkipRetry`; resolve indeterminate ones before deciding.

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

        err = svc.Process(ctx, p.OrderID) // Process sends Stripe the same idempotency key on every attempt
        switch {
        case err == nil:
            return nil
        case errors.Is(err, ErrPaymentDeclined):
            return fmt.Errorf("process: %v: %w", err, asynq.SkipRetry) // permanent
        case errors.Is(err, ErrIndeterminate):
            // The charge may exist. Ask the provider; only then succeed, retry, or park.
            if done, lookupErr := svc.LookupByOrderRef(ctx, p.OrderID); lookupErr == nil && done { // search by the order id you put in metadata
                return nil
            }
            return fmt.Errorf("process: %w", err) // retried under the same key - the provider dedupes
        default:
            return fmt.Errorf("process: %w", err) // transient
        }
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
if err := srv.Run(mux); err != nil { log.Fatalf("asynq: %v", err) } // Run blocks, traps SIGTERM/SIGINT, and shuts down itself
```

`srv.Run` installs its own signal handler; `srv.Shutdown()` is for the `srv.Start` form, and either waits at most `ShutdownTimeout` for in-progress tasks. Asynq's per-task timeout defaults to 30 minutes when `asynq.Timeout` is unset, so an untimed task holds its worker slot for that long. A task that genuinely needs longer than the grace period allows cannot be made legal by raising `Timeout` - split it into chunks that each fit, each chunk persisting its progress so a redelivery resumes.

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
    kgo.DisableAutoCommit(), // default marks the previous poll's offsets committable at the next poll and commits on revoke - a record still in flight at a rebalance, or handled concurrently, is lost
)
if err != nil { return fmt.Errorf("kafka client: %w", err) }
defer client.Close()

for {
    fetches := client.PollFetches(ctx)
    if fetches.IsClientClosed() || ctx.Err() != nil { return nil }
    fetches.EachError(func(_ string, _ int32, err error) {
        slog.Error("kafka fetch error", "err", err) // transient: the next poll retries; never log.Fatal here
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

A record that can never succeed must leave the partition, or it blocks its own partition indefinitely - the poison-message wedge (other partitions keep moving, so lag shows as one stuck partition). Bound both exits: permanent errors go straight to the DLQ, transient ones get a fixed attempt budget and then follow.

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
var order Order
err := s.db.RunInTx(ctx, func(tx pgx.Tx) error {
    o, err := s.repo.CreateTx(ctx, tx, req)
    if err != nil { return err }
    order = o
    return s.outboxRepo.InsertTx(ctx, tx, OutboxEvent{
        AggregateID: order.ID,
        EventType:   "order.created",
        Payload:     mustMarshal(orderEvent(order)),
    })
})

// Relay (separate goroutine/process; consumers stay idempotent under double-delivery).
// ClaimPending is one UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING * that
// sets status = 'processing' and claimed_at (see go-data-access): the row lock ends with the claiming transaction (autocommit here, so with the statement),
// so the claim must be the mark - a bare SELECT double-publishes once the relay has two replicas.
// Rows whose claimed_at is older than the lease (5 min) are re-claimable: that is the retry path.
events, err := r.outboxRepo.ClaimPending(ctx, 100)
if err != nil { return err }
for _, ev := range events {
    // ProduceSync: async Produce returns before broker ack - marking published on a nack loses the event
    if err := r.kafka.ProduceSync(ctx, recordFor(ev)).FirstErr(); err != nil {
        slog.Error("kafka produce", "id", ev.ID, "err", err)
        continue // not marked - lease expiry returns it for retry
    }
    if err := r.outboxRepo.MarkPublished(ctx, ev.ID); err != nil {
        slog.Error("outbox mark", "id", ev.ID, "err", err) // will republish once; consumers are idempotent
    }
}
```

For Asynq (Redis-backed), post-commit enqueue plus a reconciliation sweep is the default (see Dispatch After Commit); the outbox is for Kafka and other external brokers, where a lost publish has no equivalent backstop.

### Inbound Events (webhooks, consumed topics)

An inbound event is applied through an **inbox**: insert `(provider, event_id)` into a unique-keyed table in the same transaction as the state change; a duplicate-key error means the event was already applied, so acknowledge without acting. A status guard alone (`if order.Status == refunded { return }`) races two concurrent deliveries. Outbound callbacks to a partner URL are tasks like any other: retry budget, timeout, a `2xx` is the ack, and the partner is told to expect duplicates.

## Stack Notes

- **Asynq**: best fit for Redis-backed single-service queues; `asynqmon` for web UI; Redis needs AOF + `noeviction` for the persistence claim to hold
- **franz-go**: preferred Kafka client (pure Go, low alloc); use `sarama` only if already present
- **Graceful shutdown**: `srv.Run` handles `SIGTERM` itself and waits up to `ShutdownTimeout`; the pod's grace period must exceed it

## Edge Cases

- Malformed payload: permanent error (`asynq.SkipRetry`)
- Entity deleted between enqueue and execute: return nil, don't retry
- Redis unavailable at enqueue: degrade per use case (log + continue if best-effort, fail otherwise)
- At-least-once means duplicates: always idempotency-guard before side effects
- Auto-commit makes the previous poll's offsets committable at the next poll and commits them on revoke; a record still in flight at a rebalance or crash is lost - manual commit only

## Output Format

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design | `## Messaging Design` with the five tables; code for each new task, consumer, relay or inbound handler follows under `### <Task, loop or inbound handler>` headings in table order; decisions with no column (grace-period change, worker `Concurrency` against the DB pool share - sizing in `go-data-access`, outbox vs sweep) are one sentence each under the tables |
| Review | `## Findings`, then `## Messaging Design` describing the system as it exists today |
| Incident | two opening lines `**Failing:**` and `**First fix:**`, then `## Findings`, then `## Messaging Design` as it exists today |

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

Cell values: `Classification` is `Transient | Permanent | Indeterminate | Ignore | Fatal` - `Ignore` for work that is no longer needed (entity deleted), `Fatal` for "cannot process and cannot park", which must stop the consumer rather than commit; on a review or incident it is the class the code **gives** the error today (a bare `return err` is `Transient`), and the intended class goes in the finding's `Fix`. `Idempotency Check` is `status guard | provider key | inbox row | none`; a handler with two checks lists both joined by `+`. `Delivery` is `at-least-once | at-most-once | effectively-once` - `at-most-once` when an offset can be committed or a task marked done while its side effect is still in flight (autocommit with concurrent handling, commit-on-revoke, an async produce followed by the mark); `effectively-once` is at-least-once plus an inbox row or provider key on every side effect; `unknown` when the consumer is not visible. `Producer` is this service's loop or binary, or `external`; a DLQ topic's producer is the consumer that parks into it. `Outbox?` is `Yes | No | n/a (external producer)` - `unknown` when the relay is visible but its insert site is not. `Consumer Group` is `none` for a topic this service only produces. `Timeout` and `MaxRetry` state the effective value, naming the default when unset (Asynq: `MaxRetry` 25, `Timeout` 30 min). A task that cannot finish inside the grace period checkpoints per unit and re-enqueues its remainder; its `Timeout` still sits under `ShutdownTimeout`. `Fatal` is a consumer-loop class; a startup `log.Fatalf` is not a classification row. `Dispatch Timing` has one row per enqueue site; a task type defined but never enqueued reads `never enqueued`; an inbound event (webhook, consumed record) reads `on receipt, inside the inbox transaction`. `Lifecycle` has one row per setting per process (`ShutdownTimeout`, `Concurrency`, queue weights, the platform grace period) and one row per loop that is not a broker task (outbox relay, consumer with its commit mode, ticker, scheduler entry), naming its owner and exit. On a design engagement an existing task kept as-is is marked `(existing)`. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries. `**Failing:**` names the symptom; `**First fix:**` the one change that stops it - the rest follow in `## Findings` order.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol> | <task type or subsystem>}

- Defect: {what goes wrong in production}
- Rule: {the messaging rule violated}
- Fix: {concrete edit}
```

`[Must]` for a duplicated or lost side effect, a dropped dispatch (including an enqueue client that can be nil), a wedged or unboundedly lagging consumer, a queue starved by untimed work, an unbounded retry, work lost on deploy, or a panic in a handler or consumer goroutine; `[Recommend]` otherwise - judge by consequence, not by matching the list. Cite `file:line` when the input carries line numbers (a Kubernetes manifest is a file like any other), `file:<symbol>` or the task type / subsystem when the input is incident evidence; a range is `file:start-end`. Order `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites (the same unguarded handler shape in three task types) is one heading citing the first site, with the rest named on the `Defect:` line; when distinct findings share one cause, say so - fixing idempotency and timeouts usually collapses most of an incident's list. An incident question is answered inside the `Defect:` line of the finding it concerns. A defect this skill does not own (webhook authentication, the HTTP handling of a webhook, DB pool sizing) is still reported, never dropped: one block per such defect after the owned findings, in the same file-then-line order, labelled by the criteria above, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- Large structs / DB models in payloads
- Tasks without timeout
- Ignoring `EnqueueContext` errors
- Enqueueing inside a transaction
- Retrying permanent failures, or blind-retrying indeterminate ones
- Auto-committing Kafka offsets before handler success
- `log.Fatal` inside a consumer loop - a broker election becomes a crash loop that skips polled records
