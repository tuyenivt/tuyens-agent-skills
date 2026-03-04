---
name: go-messaging-patterns
description: Background job and async messaging patterns for Go. Asynq (Redis-backed jobs), Kafka consumers with franz-go/sarama, and in-process worker pools.
metadata:
  category: backend
  tags: [asynq, kafka, messaging, background-jobs, async, redis, idempotency]
user-invocable: false
---

# Go Messaging Patterns

## When to Use

- Offloading work that takes > 200ms or touches external services (email, webhooks, file processing)
- Kafka event consumption in a Go service
- Periodic/scheduled background tasks
- In-process worker pools for bounded parallelism

## Rules

- Handlers must be **idempotent** - tasks can be retried; check state before acting
- Pass IDs and primitive values as task payloads - never pass structs with unexported fields or DB models
- Configure **max retries** and a **dead-letter** strategy for every task type
- Workers must respect `context.Context` for cancellation and graceful shutdown
- Use `errgroup` to manage worker lifecycle - no goroutine without an owner

## Pattern

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

Enqueue from service:

```go
func (s *OrderService) PlaceOrder(ctx context.Context, req PlaceOrderRequest) (*Order, error) {
    order, err := s.repo.Create(ctx, req)
    if err != nil {
        return nil, fmt.Errorf("create order: %w", err)
    }

    task, err := tasks.NewProcessOrderTask(order.ID)
    if err != nil {
        return nil, fmt.Errorf("build task: %w", err)
    }
    if _, err := s.client.EnqueueContext(ctx, task); err != nil {
        return nil, fmt.Errorf("enqueue order task: %w", err)
    }
    return order, nil
}
```

Worker handler:

```go
// handlers/order_handler.go
func HandleProcessOrder(repo OrderRepository, svc FulfillmentService) asynq.HandlerFunc {
    return func(ctx context.Context, t *asynq.Task) error {
        var p tasks.ProcessOrderPayload
        if err := json.Unmarshal(t.Payload(), &p); err != nil {
            return fmt.Errorf("unmarshal payload: %w", err) // permanent failure, no retry
        }

        order, err := repo.FindByID(ctx, p.OrderID)
        if err != nil {
            return fmt.Errorf("find order: %w", err)
        }
        if order.Status == "processed" {
            return nil // idempotency check - already done
        }

        if err := svc.Process(ctx, p.OrderID); err != nil {
            return fmt.Errorf("process order: %w", err) // transient - will retry
        }
        return nil
    }
}
```

Server setup:

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

## Stack-Specific Guidance

- **Asynq**: Best fit for Redis-backed single-service job queues; integrates naturally with Gin services; use `asynqmon` for a web monitoring UI
- **franz-go**: Preferred Kafka client for Go (pure Go, low alloc); use `sarama` only if the project already depends on it
- **Graceful shutdown**: Call `srv.Shutdown()` on `SIGTERM` - asynq waits for in-progress tasks to complete before stopping
- **Scheduled tasks**: Use `asynq.Scheduler` for cron-style periodic tasks instead of a raw `time.Ticker` in a goroutine

## Avoid

- Passing large structs or DB models as task payloads - serialize only IDs and primitives
- Tasks without a timeout - always set `asynq.Timeout` to prevent runaway workers
- Ignoring return errors from `EnqueueContext` - log or handle enqueue failures explicitly
- Unbounded goroutines for fan-out - use a worker pool with `errgroup` and a semaphore instead
- Auto-committing Kafka offsets before processing - commit only after successful handler execution
