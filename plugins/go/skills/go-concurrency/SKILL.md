---
name: go-concurrency
description: "Go concurrency patterns: goroutine lifecycle, channels, context cancellation, errgroup, worker pools, sync primitives, mixed required/optional fan-out, and common concurrency bugs."
metadata:
  category: backend
  tags: [go, concurrency, goroutine, channels, errgroup, sync, worker-pool]
user-invocable: false
---

# Go Concurrency

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing concurrent processing pipelines or worker pools
- Running parallel operations with mixed required/optional semantics
- Reviewing goroutine-based code for leaks or race conditions
- Debugging hangs, deadlocks, or unexpected goroutine accumulation
- Choosing between goroutines, channels, and sync primitives

## Rules

- Every goroutine must have an owner responsible for its termination
- Every goroutine must have a termination path - no fire-and-forget
- Pass context to every goroutine that does I/O or can be cancelled
- Channels: the sender closes, never the receiver
- Use `errgroup` for coordinated goroutine groups that need error collection
- Prefer `sync.Mutex` for simple shared state; prefer channels for ownership transfer

## Patterns

### Goroutine with Context and Lifecycle

```go
// Bad: no termination path, context ignored
go func() {
    for {
        doWork()
    }
}()

// Good: owner controls lifecycle via context
func startWorker(ctx context.Context, jobs <-chan Job) {
    go func() {
        for {
            select {
            case <-ctx.Done():
                return // clean shutdown
            case job, ok := <-jobs:
                if !ok {
                    return // channel closed
                }
                process(job)
            }
        }
    }()
}
```

### errgroup for Coordinated Goroutines (All Required)

Use `golang.org/x/sync/errgroup` when multiple goroutines must all succeed or all be cancelled:

```go
g, ctx := errgroup.WithContext(ctx)

g.Go(func() error {
    return fetchUsers(ctx)
})

g.Go(func() error {
    return fetchOrders(ctx)
})

if err := g.Wait(); err != nil {
    return fmt.Errorf("parallel fetch: %w", err)
}
```

### Mixed Required/Optional Fan-Out

When some parallel operations are required and others are best-effort (e.g., email is required but SMS and push notifications are optional), use separate errgroups or manual goroutine management:

```go
func (s *notificationService) NotifyPaymentConfirmed(ctx context.Context, payment *Payment) error {
    // Required operations - use errgroup, cancel on failure
    required, reqCtx := errgroup.WithContext(ctx)
    required.Go(func() error {
        ctx, cancel := context.WithTimeout(reqCtx, 5*time.Second)
        defer cancel()
        return s.emailSender.Send(ctx, payment.UserEmail, "Payment confirmed")
    })

    // Optional operations - use WaitGroup, log errors but don't fail
    var optional sync.WaitGroup
    for _, sender := range []struct {
        name string
        fn   func(context.Context) error
    }{
        {"sms", func(ctx context.Context) error { return s.smsSender.Send(ctx, payment.UserPhone) }},
        {"push", func(ctx context.Context) error { return s.pushSender.Send(ctx, payment.UserID) }},
    } {
        optional.Go(func() {
            ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
            defer cancel()
            if err := sender.fn(ctx); err != nil {
                slog.Warn("optional notification failed", "channel", sender.name, "err", err)
            }
        })
    }

    // Wait for required first - if it fails, return error
    if err := required.Wait(); err != nil {
        return fmt.Errorf("required notification failed: %w", err)
    }

    // Wait for optional to finish (they won't block long due to timeout)
    optional.Wait()
    return nil
}
```

### Per-Goroutine Timeouts

When different operations have different timeout requirements:

```go
g, ctx := errgroup.WithContext(ctx)

g.Go(func() error {
    ctx, cancel := context.WithTimeout(ctx, 2*time.Second) // fast call
    defer cancel()
    return fetchFromCache(ctx)
})

g.Go(func() error {
    ctx, cancel := context.WithTimeout(ctx, 10*time.Second) // slow external API
    defer cancel()
    return fetchFromExternalAPI(ctx)
})

if err := g.Wait(); err != nil {
    return fmt.Errorf("parallel fetch: %w", err)
}
```

### Worker Pool Pattern

```go
func runWorkerPool(ctx context.Context, jobs <-chan Job, workerCount int) error {
    g, ctx := errgroup.WithContext(ctx)

    for i := 0; i < workerCount; i++ {
        g.Go(func() error {
            for {
                select {
                case <-ctx.Done():
                    return ctx.Err()
                case job, ok := <-jobs:
                    if !ok {
                        return nil // channel closed, no more work
                    }
                    if err := process(ctx, job); err != nil {
                        return fmt.Errorf("worker: %w", err)
                    }
                }
            }
        })
    }

    return g.Wait()
}
```

### Channel Ownership

The goroutine that creates a channel owns it and is responsible for closing it:

```go
// Good: producer owns and closes the channel
func produce(ctx context.Context) <-chan int {
    ch := make(chan int)
    go func() {
        defer close(ch) // sender closes
        for i := 0; i < 10; i++ {
            select {
            case <-ctx.Done():
                return
            case ch <- i:
            }
        }
    }()
    return ch
}
```

### sync Primitives

```go
// sync.Mutex for protecting shared state
type SafeCounter struct {
    mu    sync.Mutex
    value int
}

func (c *SafeCounter) Increment() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.value++
}

// sync.Once for one-time initialization
var (
    instance *DB
    once     sync.Once
)

func GetDB() *DB {
    once.Do(func() {
        instance = initDB()
    })
    return instance
}

// sync.WaitGroup.Go (Go 1.25+) for safer goroutine accounting
// Go() calls Add(1) before launching and Done() on return - no manual Add/Done needed
var wg sync.WaitGroup
wg.Go(func() {
    doWork()
})
wg.Wait()

// sync.Pool for reusing short-lived objects
var bufPool = sync.Pool{
    New: func() any { return new(bytes.Buffer) },
}

buf := bufPool.Get().(*bytes.Buffer)
buf.Reset()
defer bufPool.Put(buf)
```

### Semaphore for Bounded Concurrency

When you need to limit parallelism without a full worker pool:

```go
sem := make(chan struct{}, maxConcurrency)

g, ctx := errgroup.WithContext(ctx)
for _, item := range items {
    g.Go(func() error {
        sem <- struct{}{}        // acquire
        defer func() { <-sem }() // release
        return process(ctx, item)
    })
}
return g.Wait()
```

### Race Detection

Always run tests with the race detector during development and CI:

```bash
go test -race ./...
go run -race main.go
```

Use `go vet` with the `waitgroup` analyzer to catch misuse of `sync.WaitGroup`.

## Edge Cases

- **Nil channel**: sending to or receiving from a nil channel blocks forever - ensure channels are initialized before use
- **Closed channel**: sending to a closed channel panics; receiving from a closed channel returns the zero value immediately - always use `val, ok := <-ch` to detect closure
- **Empty select**: `select {}` blocks forever - useful only for intentional blocking (e.g., keeping main alive), but usually indicates a missing `case <-ctx.Done()`
- **WaitGroup reuse**: do not call `wg.Add()` after `wg.Wait()` has started - add all goroutines before waiting or use `errgroup` instead
- **errgroup cancels siblings on first error**: if one goroutine returns an error, the context from `errgroup.WithContext` is cancelled, which cancels all other goroutines. This is the desired behavior for all-required operations but wrong for mixed required/optional - use separate groups for those

## Output Format

```
## Concurrency Design

### Goroutine Inventory
| Goroutine | Owner | Termination Path | Timeout |
|-----------|-------|-----------------|---------|
| {name} | {parent function} | {context cancellation / channel close} | {duration} |

### Fan-Out Strategy
| Operation | Required? | Failure Behavior | Timeout |
|-----------|-----------|-----------------|---------|
| {email} | yes | cancel all, return error | 5s |
| {SMS} | no | log warning, continue | 5s |

### Synchronization
| Shared State | Protection | Why |
|-------------|-----------|-----|
| {cache map} | sync.RWMutex | concurrent read/write from handlers |
| {counter} | sync/atomic | simple increment, no complex logic |
```

## Avoid

- Goroutines without a context and a termination path
- Closing channels from the receiver side
- Using `time.Sleep` as a synchronization mechanism
- Unbuffered channels in hot paths (causes goroutine pile-up under load)
- Ignoring the race detector output
- Sharing memory directly - Go's model is "do not communicate by sharing memory; instead, share memory by communicating" (use channels to transfer ownership)
- Using a single errgroup when some operations are optional (it cancels all on first error)
