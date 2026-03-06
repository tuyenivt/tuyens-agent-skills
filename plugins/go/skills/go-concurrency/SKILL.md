---
name: go-concurrency
description: "Go concurrency patterns: goroutine lifecycle, channels, context cancellation, errgroup, worker pools, sync primitives (including WaitGroup.Go), and common concurrency bugs."
user-invocable: false
---

# Go Concurrency

## When to Use

- Designing concurrent processing pipelines or worker pools
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

### errgroup for Coordinated Goroutines

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
var wg sync.WaitGroup
wg.Go(func() {
    defer wg.Done()
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

### Race Detection

Always run tests with the race detector during development and CI:

```bash
go test -race ./...
go run -race main.go
```

Use `go vet` with the `waitgroup` analyzer to catch misuse of `sync.WaitGroup`.

## Anti-Patterns

```go
// Bad: goroutine without context (can't be cancelled)
go func() {
    result := callExternalService() // blocks forever if service hangs
    // ...
}()

// Bad: fire-and-forget goroutine (no ownership, no termination)
go doSomething()

// Bad: receiver closes channel (panics if sender sends after close)
go func() {
    close(ch) // only senders should close
}()

// Bad: defer in loop without function wrap (defer runs at function end, not loop iteration)
for _, file := range files {
    f, _ := os.Open(file)
    defer f.Close() // all closes happen at function return, not per iteration
}

// Good: wrap in immediately-invoked function
for _, file := range files {
    func() {
        f, _ := os.Open(file)
        defer f.Close() // runs at end of this closure
        process(f)
    }()
}
```

## Avoid

- Goroutines without a context and a termination path
- Closing channels from the receiver side
- Using `time.Sleep` as a synchronization mechanism
- Unbuffered channels in hot paths (causes goroutine pile-up under load)
- Ignoring the race detector output
- Sharing memory by communicating - Go's model is "communicate by sharing"... wait, the reverse: communicate to share, don't share memory directly
