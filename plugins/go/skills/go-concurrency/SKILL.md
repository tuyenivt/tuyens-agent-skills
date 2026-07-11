---
name: go-concurrency
description: "Go concurrency: goroutine lifecycle, channels, context cancellation, errgroup, worker pools, sync primitives, mixed required/optional fan-out."
metadata:
  category: backend
  tags: [go, concurrency, goroutine, channels, errgroup, sync, worker-pool]
user-invocable: false
---

# Go Concurrency

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing concurrent pipelines, worker pools, or mixed required/optional fan-out
- Reviewing goroutine code for leaks or races
- Debugging hangs, deadlocks, or goroutine accumulation

## Rules

- Every goroutine has an owner and a termination path - no fire-and-forget
- Pass `ctx` to any goroutine doing I/O or that can be cancelled
- The sender closes channels; never the receiver
- `errgroup` for groups that must all succeed (cancels siblings on first error)
- `sync.Mutex` for shared state; channels for ownership transfer
- Run `go test -race` in CI for any package using goroutines / channels / sync

## Patterns

### Goroutine with Context

```go
// Bad: no termination path
go func() { for { doWork() } }()

// Good: owner controls lifecycle
func startWorker(ctx context.Context, jobs <-chan Job) {
    go func() {
        for {
            select {
            case <-ctx.Done(): return
            case job, ok := <-jobs:
                if !ok { return }
                process(job)
            }
        }
    }()
}
```

### errgroup (all required)

```go
g, ctx := errgroup.WithContext(ctx)
g.Go(func() error { return fetchUsers(ctx) })
g.Go(func() error { return fetchOrders(ctx) })
if err := g.Wait(); err != nil { return fmt.Errorf("parallel fetch: %w", err) }
```

### Mixed Required / Optional Fan-Out

`errgroup` cancels siblings on first error - wrong for optional ops. Use separate groups:

```go
func (s *notificationService) NotifyPaymentConfirmed(ctx context.Context, p *Payment) error {
    required, reqCtx := errgroup.WithContext(ctx)
    required.Go(func() error {
        ctx, cancel := context.WithTimeout(reqCtx, 5*time.Second)
        defer cancel()
        return s.emailSender.Send(ctx, p.UserEmail, "Payment confirmed")
    })

    var optional sync.WaitGroup // WaitGroup.Go requires Go 1.25+; earlier: Add(1)/defer Done()
    defer optional.Wait()       // every return path waits - no fire-and-forget on required failure
    for _, sender := range optionalSenders(s, p) {
        optional.Go(func() {
            ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
            defer cancel()
            if err := sender.fn(ctx); err != nil {
                slog.Warn("optional notification failed", "channel", sender.name, "err", err)
            }
        })
    }

    if err := required.Wait(); err != nil {
        return fmt.Errorf("required notification: %w", err)
    }
    return nil
}
```

### Per-Goroutine Timeouts

```go
g, ctx := errgroup.WithContext(ctx)
g.Go(func() error {
    ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
    defer cancel()
    return fetchFromCache(ctx)
})
g.Go(func() error {
    ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
    defer cancel()
    return fetchFromExternalAPI(ctx)
})
return g.Wait()
```

### Worker Pool

```go
func runWorkerPool(ctx context.Context, jobs <-chan Job, n int) error {
    g, ctx := errgroup.WithContext(ctx)
    for i := 0; i < n; i++ {
        g.Go(func() error {
            for {
                select {
                case <-ctx.Done(): return ctx.Err()
                case job, ok := <-jobs:
                    if !ok { return nil }
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

```go
func produce(ctx context.Context) <-chan int {
    ch := make(chan int)
    go func() {
        defer close(ch) // sender closes
        for i := 0; i < 10; i++ {
            select {
            case <-ctx.Done(): return
            case ch <- i:
            }
        }
    }()
    return ch
}
```

### sync Primitives

```go
// Protect shared state
type SafeCounter struct { mu sync.Mutex; value int }
func (c *SafeCounter) Increment() { c.mu.Lock(); defer c.mu.Unlock(); c.value++ }

// One-time init
var (instance *DB; once sync.Once)
func GetDB() *DB { once.Do(func() { instance = initDB() }); return instance }

// WaitGroup.Go (Go 1.25+) - no manual Add/Done
var wg sync.WaitGroup
wg.Go(func() { doWork() })
wg.Wait()

// Pool for short-lived objects
var bufPool = sync.Pool{New: func() any { return new(bytes.Buffer) }}
buf := bufPool.Get().(*bytes.Buffer); buf.Reset(); defer bufPool.Put(buf)
```

### Bounded Concurrency

```go
g, ctx := errgroup.WithContext(ctx)
g.SetLimit(maxConcurrency) // Go() blocks until a slot frees - at most n goroutines exist
for _, item := range items {
    g.Go(func() error { return process(ctx, item) })
}
return g.Wait()
```

Without errgroup, use a `chan struct{}` semaphore acquired *before* `go` - acquiring inside the goroutine spawns all N immediately and ignores ctx while blocked on the semaphore.

## Edge Cases

- Nil channel send/receive blocks forever
- Send on closed channel panics; `v, ok := <-ch` detects close
- WaitGroup: `Add` before `go`, never inside the goroutine; don't `Add` after `Wait` starts
- `errgroup.WithContext` cancels all siblings on first error - use separate groups for required + optional

## Leak Diagnosis (debugging)

- `/debug/pprof/goroutine?debug=1` groups goroutines by stack; a count growing under one stack is the leak
- Stack signature -> cause: `chan send` = receiver gone (guard sends with `select` on `ctx.Done()`); `chan receive` / `for range ch` = sender never closes; `sync.WaitGroup.Wait` = a worker never returns; `select` = no arm can ever fire
- `goleak.VerifyNone(t)` in tests catches leaks at PR time; `runtime.NumGoroutine()` trend confirms in prod

## Output Format

```
## Concurrency Design

### Goroutines
| Goroutine | Owner | Termination Path | Timeout |

### Fan-Out
| Operation | Required? | Failure Behavior | Timeout |

### Synchronization
| Shared State | Protection | Why |

### Leak Diagnosis (debug engagements only)
| Stack Signature | Count Trend | Root Cause | Fix |
```

## Avoid

- Goroutines without context + termination
- Closing channels from the receiver
- `time.Sleep` as synchronization
- Unbuffered channels in hot paths
- One errgroup for required + optional (it cancels everything on first error)
- Sharing memory directly when channel ownership transfer fits
