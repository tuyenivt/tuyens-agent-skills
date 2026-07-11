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

- Handlers must be idempotent - check state before acting (at-least-once delivery)
- Payloads carry IDs / primitives, never structs with unexported fields or DB models
- Configure max retries, timeout, and dead-letter strategy per task type
- Classify errors transient (retry) vs permanent (`asynq.SkipRetry`)
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
    // Log; a reconciliation job picks up unprocessed orders
    slog.Error("enqueue failed", "order_id", order.ID, "err", err)
}
return order, nil
```

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
        ErrorHandler: asynq.ErrorHandlerFunc(func(ctx context.Context, task *asynq.Task, err error) {
            slog.Error("task failed", "type", task.Type(), "err", err)
        }),
    },
)
mux := asynq.NewServeMux()
mux.HandleFunc(tasks.TypeProcessOrder, handlers.HandleProcessOrder(repo, svc))
if err := srv.Run(mux); err != nil { log.Fatalf("asynq: %v", err) }
```

### Scheduled Tasks

Prefer `asynq.Scheduler` over `time.Ticker` in a goroutine:

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
    fetches.EachRecord(func(r *kgo.Record) {
        if err := handler(r.Value); err != nil {
            // resolve BEFORE the batch commit: DLQ-produce or stop.
            // Committing a failed record's offset is a silent skip.
            produceToDLQ(ctx, client, r, err)
        }
    })
    client.CommitUncommittedOffsets(ctx) // every record in the batch handled or DLQ'd
}
```

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

For Asynq (Redis-backed), post-commit enqueue is acceptable - Asynq's persistence handles retries. Use the outbox only for Kafka / external brokers requiring atomicity.

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

```
## Messaging Design

### Task Types
| Type | Queue | Payload | MaxRetry | Timeout | Idempotency Check |

### Error Classification
| Error | Classification | Action |

### Kafka Topics
| Topic | Producer | Consumer Group | Delivery | Outbox? |

### Dispatch Timing
| Event | After Which Commit |
```

## Avoid

- Large structs / DB models in payloads
- Tasks without timeout
- Ignoring `EnqueueContext` errors
- Enqueueing inside a transaction
- Retrying permanent failures
- Auto-committing Kafka offsets before handler success
