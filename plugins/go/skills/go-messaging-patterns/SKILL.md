---
name: go-messaging-patterns
description: "Background job and async messaging patterns for Go. Asynq (Redis-backed jobs) with retry classification, Kafka consumers with franz-go, transactional outbox, and in-process worker pools."
metadata:
  category: backend
  tags: [asynq, kafka, messaging, background-jobs, async, redis, idempotency]
user-invocable: false
---

# Go Messaging Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Offloading work that takes > 200ms or touches external services (email, webhooks, file processing)
- Kafka event consumption in a Go service
- Periodic/scheduled background tasks
- In-process worker pools for bounded parallelism

## Rules

- Handlers must be **idempotent** - tasks can be retried; check state before acting
- Pass IDs and primitive values as task payloads - never pass structs with unexported fields or DB models
- Configure **max retries** and a **dead-letter** strategy for every task type
- Classify errors as **transient** (retry) or **permanent** (skip retry) - Asynq retries all errors by default
- Workers must respect `context.Context` for cancellation and graceful shutdown
- Dispatch background jobs **after** the database transaction commits, not inside it - if the job fires before commit, the worker may read stale data or a missing row
- Use `errgroup` to manage worker lifecycle - no goroutine without an owner

## Patterns

### Asynq (Redis-backed jobs - primary recommendation)

```go
// tasks/order_tasks.go
const TypeProcessOrder = "order:process"

type ProcessOrderPayload struct {
    OrderID string `json:"order_id"`
}

func NewProcessOrderTask(orderID string) (*asynq.Task, error) {
    payload, err := json.Marshal(ProcessOrderPayload{OrderID: orderID})
    if err != nil {
        return nil, err
    }
    return asynq.NewTask(TypeProcessOrder, payload,
        asynq.MaxRetry(3),
        asynq.Timeout(30*time.Second),
        asynq.Queue("default"),
    ), nil
}
```

### Dispatching After Transaction Commit

Enqueue background jobs only after the database transaction has committed successfully. If you enqueue inside the transaction, the worker may execute before the commit completes and read stale data:

```go
func (s *OrderService) PlaceOrder(ctx context.Context, req PlaceOrderRequest) (*Order, error) {
    // Step 1: database transaction
    order, err := s.repo.Create(ctx, req)
    if err != nil {
        return nil, fmt.Errorf("create order: %w", err)
    }

    // Step 2: enqueue AFTER commit (repo.Create committed the transaction)
    task, err := tasks.NewProcessOrderTask(order.ID)
    if err != nil {
        return nil, fmt.Errorf("build task: %w", err)
    }
    if _, err := s.client.EnqueueContext(ctx, task); err != nil {
        // Log but don't fail the request - the order was created successfully
        // A reconciliation job can pick up unprocessed orders later
        slog.Error("enqueue order task failed", "order_id", order.ID, "err", err)
    }
    return order, nil
}
```

### Worker Handler with Error Classification

Asynq retries all returned errors by default. Return `fmt.Errorf("...: %w", asynq.SkipRetry)` for permanent failures to prevent infinite retry loops:

```go
func HandleProcessOrder(repo OrderRepository, svc FulfillmentService) asynq.HandlerFunc {
    return func(ctx context.Context, t *asynq.Task) error {
        var p tasks.ProcessOrderPayload
        if err := json.Unmarshal(t.Payload(), &p); err != nil {
            // Permanent failure: malformed payload will never succeed on retry
            return fmt.Errorf("unmarshal payload: %w", asynq.SkipRetry)
        }

        order, err := repo.FindByID(ctx, p.OrderID)
        if err != nil {
            if errors.Is(err, ErrNotFound) {
                // Permanent failure: entity was deleted between enqueue and execution
                slog.Warn("order not found, skipping", "order_id", p.OrderID)
                return nil
            }
            return fmt.Errorf("find order: %w", err) // transient - will retry
        }

        // Idempotency check - already processed
        if order.Status == "processed" {
            return nil
        }

        if err := svc.Process(ctx, p.OrderID); err != nil {
            // Classify: is this retryable?
            if errors.Is(err, ErrPaymentDeclined) {
                return fmt.Errorf("process order: %w", asynq.SkipRetry) // permanent
            }
            return fmt.Errorf("process order: %w", err) // transient - will retry
        }
        return nil
    }
}
```

### Server Setup with Queue Priorities

```go
// cmd/worker/main.go
srv := asynq.NewServer(
    asynq.RedisClientOpt{Addr: cfg.RedisAddr},
    asynq.Config{
        Queues: map[string]int{
            "critical": 6,
            "default":  3,
            "low":      1,
        },
        Concurrency: 10,
        ErrorHandler: asynq.ErrorHandlerFunc(func(ctx context.Context, task *asynq.Task, err error) {
            slog.Error("task failed", "type", task.Type(), "err", err)
        }),
    },
)

mux := asynq.NewServeMux()
mux.HandleFunc(tasks.TypeProcessOrder, handlers.HandleProcessOrder(repo, svc))

if err := srv.Run(mux); err != nil {
    log.Fatalf("asynq server: %v", err)
}
```

### Scheduled/Periodic Tasks

Use `asynq.Scheduler` for cron-style periodic tasks instead of `time.Ticker` in a goroutine:

```go
scheduler := asynq.NewScheduler(
    asynq.RedisClientOpt{Addr: cfg.RedisAddr},
    nil,
)

// Run every hour: reconcile unprocessed orders
task, _ := tasks.NewReconcileOrdersTask()
scheduler.Register("0 * * * *", task, asynq.Queue("low"))

if err := scheduler.Run(); err != nil {
    log.Fatalf("scheduler: %v", err)
}
```

### Kafka Consumer (franz-go)

```go
import "github.com/twmb/franz-go/pkg/kgo"

func RunKafkaConsumer(ctx context.Context, brokers []string, topic, groupID string, handler func([]byte) error) error {
    client, err := kgo.NewClient(
        kgo.SeedBrokers(brokers...),
        kgo.ConsumerGroup(groupID),
        kgo.ConsumeTopics(topic),
    )
    if err != nil {
        return fmt.Errorf("kafka client: %w", err)
    }
    defer client.Close()

    for {
        fetches := client.PollFetches(ctx)
        if fetches.IsClientClosed() || ctx.Err() != nil {
            return nil
        }
        fetches.EachError(func(_ string, _ int32, err error) {
            slog.Error("kafka fetch error", "err", err)
        })
        fetches.EachRecord(func(r *kgo.Record) {
            if err := handler(r.Value); err != nil {
                slog.Error("handle record failed", "topic", r.Topic, "err", err)
                // Decide: DLQ, skip, or stop consumer
            }
        })
        client.CommitUncommittedOffsets(ctx)
    }
}
```

### In-Process Worker Pool (no external broker)

```go
func RunWorkerPool(ctx context.Context, jobs <-chan Job, concurrency int) error {
    g, ctx := errgroup.WithContext(ctx)

    for range concurrency {
        g.Go(func() error {
            for {
                select {
                case job, ok := <-jobs:
                    if !ok {
                        return nil // channel closed, worker exits cleanly
                    }
                    if err := job.Execute(ctx); err != nil {
                        slog.Error("job failed", "id", job.ID, "err", err)
                        // continue processing other jobs
                    }
                case <-ctx.Done():
                    return ctx.Err()
                }
            }
        })
    }
    return g.Wait()
}
```

### Transactional Outbox Pattern (Kafka / reliable publishing)

Publishing a Kafka message inside a database transaction is a dual-write anti-pattern: the DB write and the Kafka publish are not atomic. If the Kafka publish succeeds but the DB rolls back (or vice versa), you get phantom messages or silent event loss.

**Bad - dual-write (not atomic):**

```go
func (s *OrderService) PlaceOrder(ctx context.Context, req PlaceOrderRequest) (*Order, error) {
    tx, _ := s.db.Begin(ctx)
    order, _ := s.repo.CreateTx(ctx, tx, req)
    tx.Commit(ctx) // DB committed

    // PROBLEM: Kafka publish is outside the transaction.
    // If this fails, DB is committed but event is never published.
    s.kafka.Produce("order.created", orderEvent(order))
    return order, nil
}
```

**Good - transactional outbox:**

```go
// Step 1: Write order AND outbox record in one DB transaction
func (s *OrderService) PlaceOrder(ctx context.Context, req PlaceOrderRequest) (*Order, error) {
    var order *Order
    err := s.db.RunInTx(ctx, func(tx pgx.Tx) error {
        var err error
        order, err = s.repo.CreateTx(ctx, tx, req)
        if err != nil {
            return err
        }
        // Write outbox record atomically with the order
        return s.outboxRepo.InsertTx(ctx, tx, OutboxEvent{
            AggregateID: order.ID,
            EventType:   "order.created",
            Payload:     mustMarshal(orderEvent(order)),
        })
    })
    return order, err
}

// Step 2: A relay worker polls the outbox and publishes to Kafka
// This runs in a separate goroutine/process; retries on failure
func (r *OutboxRelay) Run(ctx context.Context) error {
    for {
        events, _ := r.outboxRepo.FetchPending(ctx, 100)
        for _, ev := range events {
            if err := r.kafka.Produce(ev.EventType, ev.Payload); err != nil {
                slog.Error("kafka produce failed", "id", ev.ID, "err", err)
                continue
            }
            r.outboxRepo.MarkPublished(ctx, ev.ID)
        }
        select {
        case <-ctx.Done():
            return nil
        case <-time.After(5 * time.Second):
        }
    }
}
```

For Asynq (Redis-backed), enqueue after `repo.Create` is acceptable because Asynq's persistence layer handles retries. Use the outbox pattern only when publishing to Kafka or external message brokers where dual-write atomicity is required.

## Stack-Specific Guidance

- **Asynq**: Best fit for Redis-backed single-service job queues; integrates naturally with Gin services; use `asynqmon` for a web monitoring UI
- **franz-go**: Preferred Kafka client for Go (pure Go, low alloc); use `sarama` only if the project already depends on it
- **Graceful shutdown**: Call `srv.Shutdown()` on `SIGTERM` - asynq waits for in-progress tasks to complete before stopping
- **Scheduled tasks**: Use `asynq.Scheduler` for cron-style periodic tasks instead of a raw `time.Ticker` in a goroutine

## Edge Cases

- **Empty or malformed payload**: always validate payload after unmarshal - return a permanent (non-retryable) error for malformed payloads to avoid infinite retry loops
- **Task enqueued but entity deleted**: the handler must handle "entity not found" gracefully (log and return nil, not an error) since the entity may have been deleted between enqueue and execution
- **Redis unavailable at enqueue time**: decide per use case whether to fail the request or degrade gracefully (e.g., log and continue if the job is best-effort)
- **Duplicate delivery**: Asynq guarantees at-least-once delivery, not exactly-once - always check current state before acting (idempotency guard)
- **Enqueue inside transaction**: if you enqueue inside a `db.Transaction` callback, the worker may execute before the transaction commits. Always enqueue after the transaction function returns nil

## Output Format

```
## Messaging Design

### Task Types
| Task Type | Queue | Payload Fields | Max Retry | Timeout | Idempotency Check |
|-----------|-------|---------------|-----------|---------|-------------------|
| order:process | default | order_id | 3 | 30s | check order.status |

### Error Classification
| Error | Classification | Action |
|-------|---------------|--------|
| malformed payload | permanent | SkipRetry |
| entity not found | permanent | log + return nil |
| external API timeout | transient | retry (up to max) |
| payment declined | permanent | SkipRetry |

### Kafka Topics (if applicable)
| Topic | Producer | Consumer Group | Delivery | Outbox? |
|-------|----------|---------------|----------|---------|
| order.created | order-service | analytics-consumer | at-least-once | yes |

### Dispatch Timing
| Event | Dispatched After |
|-------|-----------------|
| {task type} | {which transaction commits} |
```

## Avoid

- Passing large structs or DB models as task payloads - serialize only IDs and primitives
- Tasks without a timeout - always set `asynq.Timeout` to prevent runaway workers
- Ignoring return errors from `EnqueueContext` - log or handle enqueue failures explicitly
- Unbounded goroutines for fan-out - use a worker pool with `errgroup` and a semaphore instead
- Auto-committing Kafka offsets before processing - commit only after successful handler execution
- Enqueueing inside a database transaction - worker may race the commit
- Retrying permanent failures (malformed payload, entity deleted) - use `asynq.SkipRetry`
