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
- The sender closes channels; never the receiver. With multiple senders no sender may close - the coordinator that outlives them closes after their `Wait` returns
- Every send that can block picks a backpressure policy (drop / block-with-cancel / evict) - a bare `ch <- v` to a stalled consumer leaks the sender
- `errgroup` for groups that must all succeed (cancels siblings on first error)
- `sync.Mutex` for shared state; channels for ownership transfer
- Run `go test -race` in CI for any package using goroutines / channels / sync

## Patterns

### Goroutine with Context

```go
// Bad: no termination path - time.Sleep has no cancel arm
go func() { for { time.Sleep(30 * time.Second); doWork() } }()

// Good: owner passes ctx; the ticker arm and the cancel arm share one select
go func() {
    t := time.NewTicker(30 * time.Second)
    defer t.Stop()
    for {
        select {
        case <-ctx.Done(): return
        case <-t.C: doWork()
        }
    }
}()
```

Anything spawned in a constructor (`NewX`) needs the same: take `ctx` or expose `Close()`, or every construction leaks a goroutine.

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

Each goroutine sets its own `context.WithTimeout` inside the closure, as above - one group-wide deadline forces a 2s cache read and a 10s external call to share a budget.

### Slow Consumer (bounded send)

A bare `ch <- v` to a consumer that may stall parks the sender forever. Every blocking send picks a policy:

| Policy | Shape | Use when |
|--------|-------|----------|
| Drop | `select { case ch <- v: default: dropped++ }` | telemetry, broadcasts, progress pings |
| Block with cancel | `select { case ch <- v: case <-ctx.Done(): return }` | required work; the owner controls the exit |
| Evict | drop, then close the channel and unregister the consumer | pub/sub fan-out where a dead peer must not persist |

Never send while holding a mutex - one stalled consumer then blocks every other operation on that lock, and `RWMutex` blocks new readers as soon as a writer queues.

### Worker Pool

```go
func runWorkerPool(ctx context.Context, jobs <-chan Job, n int) error {
    g, ctx := errgroup.WithContext(ctx)
    for range n {
        g.Go(func() error {
            for {
                select {
                case <-ctx.Done(): return ctx.Err()
                case job, ok := <-jobs:
                    if !ok { return nil } // sender closed: clean exit
                    if err := process(ctx, job); err != nil { return fmt.Errorf("worker: %w", err) }
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

**Worker pool or bounded concurrency:** a known slice of items, each processed once -> `errgroup.SetLimit`. An open-ended channel consumed by N long-lived goroutines -> worker pool. A pipeline uses both: `SetLimit` on the producing stage, worker pool on the consuming stage.

### Graceful Shutdown

```go
ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
defer stop()

done := make(chan error, 1) // buffered: the sender exits even if nobody receives
go func() { done <- run(ctx) }()

select {
case err := <-done:
    return err
case <-ctx.Done():
    stop() // a second signal now kills the process outright
    select {
    case err := <-done:
        return err
    case <-time.After(drainBudget):
        return errors.New("drain exceeded budget")
    }
}
```

Timeouts on the deepest single path must sum to less than `drainBudget`, and `drainBudget` must be under the platform's kill deadline (k8s `terminationGracePeriodSeconds`) - otherwise SIGKILL lands mid-work.

## Edge Cases

- Nil channel send/receive blocks forever
- Send on closed channel panics; `v, ok := <-ch` detects close
- WaitGroup: `Add` before `go`, never inside the goroutine; don't `Add` after `Wait` starts

## Leak Diagnosis (debugging)

- `/debug/pprof/goroutine?debug=1` groups goroutines by stack; `?debug=2` adds how long each has been blocked, separating "parked and cycling" from "parked since deploy"
- **Growth decides, signature explains.** Rank stacks by count growth across snapshots; only a growing stack is the leak. A flat count is a steady state even when its signature looks suspicious - say so rather than reporting it as a second leak
- Stack signature -> cause:
  - `chan send` = the receiver exited (owner must close / cancel), **or** it is alive and never drains (apply a backpressure policy)
  - `chan receive` / `for range ch` = sender never closes
  - `sync.WaitGroup.Wait` = a worker never returns; `WaitGroup` has no cancel arm, `errgroup.WithContext` does
  - `select` = no arm can ever fire (nil channel, ctx never cancelled)
  - `time.Sleep` / `time.After` in a bare `for` = a background loop with no `ctx.Done()` arm
- Each leaked goroutine retains its stack plus everything it references, so RSS tracks goroutine count and never recovers without a restart
- Working from a dump with no source: name the cause from the signature and mark those rows `(inferred)`
- `goleak.VerifyTestMain(m)` gates a whole package (`VerifyNone(t)` only the test it annotates); export `runtime.NumGoroutine()` as a gauge and alert on sustained growth

## Output Format

Emit the sections for the engagement, in this order:

| Engagement | Emits |
|------------|-------|
| Design / implementation | Goroutines, Fan-Out, Synchronization, Verification |
| Review | Findings, Goroutines, Fan-Out, Synchronization, Verification |
| Debug (leak / hang) | Leak Diagnosis, Findings, Verification |

`## Findings` is its own top-level heading, before or after `## Concurrency Design` as the order above dictates - never nested inside it.

```
## Concurrency Design

### Goroutines
| Goroutine | Owner | Termination Path | Timeout |
|-----------|-------|------------------|---------|

### Fan-Out
| Operation | Required? | Failure Behavior | Timeout |
|-----------|-----------|------------------|---------|

### Synchronization
| Shared State | Protection | Why |
|--------------|------------|-----|

### Leak Diagnosis
| Stack Signature | Count Trend | Root Cause | Fix |
|-----------------|-------------|------------|-----|

### Verification
| Check | Where |
|-------|-------|
```

Cell values: `Required?` is `Required | Optional`. `Protection` is `Mutex | RWMutex | atomic | channel | errgroup | WaitGroup | none`. `Count Trend` is `Growing | Flat | Unknown`. `Timeout` is a duration or `none`. Anything the input does not supply is `unknown`. `Verification` rows are the checks that would catch this class of defect - `goleak`, `go test -race`, a bounded-return-on-cancel test, a concurrency-ceiling assertion - each naming the package or CI step that runs it.

Every finding carries exactly one label:

```
## Findings

### [Must] file:line

- Defect: {what goes wrong, and under what conditions if it is currently latent}
- Rule: {the concurrency rule violated}
- Fix: {concrete edit}
```

`[Must]` for a data race, a leak, a deadlock, a lost or silently dropped result, or a goroutine that cannot be cancelled; `[Recommend]` otherwise. A defect that is currently masked (by lock ordering, by a caller that happens to serialize) is still `[Must]` - say what unmasks it. Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not.

## Avoid

- Goroutines without context + termination
- Closing channels from the receiver
- `time.Sleep` as synchronization
- Unbuffered channels in hot paths
- One errgroup for required + optional (it cancels everything on first error)
- Sharing memory directly when channel ownership transfer fits
