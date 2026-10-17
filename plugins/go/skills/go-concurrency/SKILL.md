---
name: go-concurrency
description: "Go concurrency: goroutine lifecycle, channels, context cancellation, errgroup, worker pools, sync primitives, mixed required/optional fan-out."
metadata:
  category: backend
  tags: [go, concurrency, goroutine, channels, errgroup, sync, worker-pool]
user-invocable: false
---

# Go Concurrency

> Load `Use skill: stack-detect` first. The `go` directive in `go.mod` decides the version gates below (a `## Tech Stack` `Language:` line may carry a version; the directive wins when they differ). Baseline: Go 1.25+ (`WaitGroup.Go`, `testing/synctest`); the loop forms here need Go 1.22+ (per-iteration loop variables, `for range n`). An older project gets the inline below-floor note where one exists and no other adaptation.

## When to Use

- Designing concurrent pipelines, worker pools, or mixed required/optional fan-out
- Reviewing goroutine code for leaks or races
- Debugging hangs, deadlocks, or goroutine accumulation

## Rules

- Every goroutine has an owner and a termination path - no fire-and-forget. A panic in a goroutine kills the process; `gin.Recovery()` covers only the handler goroutine
- Pass `ctx` to any goroutine doing I/O or that can be cancelled
- The sender closes channels; never the receiver. With multiple senders no sender may close - the coordinator that outlives them closes after their `Wait` returns
- Every send that can block picks a backpressure policy (drop / block-with-cancel / evict) - a bare `ch <- v` to a stalled consumer leaks the sender
- `errgroup.WithContext` for groups that must all succeed - the first error cancels the derived ctx, and siblings stop only if they check it. A zero-value `errgroup.Group` cancels nothing
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

Anything spawned in a constructor (`NewX`) or in `init()` needs the same: take `ctx` or expose `Close()`, or every construction leaks a goroutine. A loop in `init()` has no owner at all - move it to a constructor.

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

    var optional sync.WaitGroup // WaitGroup.Go is Go 1.25+; earlier: Add(1) before go, defer Done() inside
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

Each goroutine sets its own `context.WithTimeout` inside the closure, as above - one group-wide deadline forces a 2s cache read and a 10s external call to share a budget. A batch where each item is independent (settle 50k orders) is neither shape: collect per-item errors with `errors.Join` and keep going, and abort only on an infrastructure-wide error - `ctx.Err()`, or the same dependency failing for every item in a row (a dead ledger connection), never a per-item rejection.

### Slow Consumer (bounded send)

A bare `ch <- v` to a consumer that may stall parks the sender forever. Every blocking send picks a policy:

| Policy | Shape | Use when |
|--------|-------|----------|
| Drop | `select { case ch <- v: default: dropped++ }` | telemetry, broadcasts, progress pings |
| Block with cancel | `select { case ch <- v: case <-ctx.Done(): return }` | required work; the owner controls the exit |
| Evict | non-blocking send fails -> `close(ch)` and delete the subscriber, both under the registry's write lock | pub/sub fan-out where a dead peer must not persist |

Never make a blocking send while holding a mutex - one stalled consumer then blocks every other operation on that lock, and `RWMutex` blocks new readers as soon as a writer queues. A non-blocking `select`/`default` send under the lock is fine, and Evict needs it: close and unregister under the same lock that guards the senders, or a concurrent `Publish` sends on a closed channel and panics.

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

`SetLimit` bounds concurrency, not rate. A provider quota (25 req/s) needs `x/time/rate`: `limiter.Wait(ctx)` before each call, shared by every worker. Size the limit against shared resources too - N workers each holding a DB connection need `N + every other consumer of that pool <= SetMaxOpenConns`, or the pool, not the limit, is the ceiling. Rate and pool limits are per replica; a shared provider quota divides by the replica count (sizing across replicas is a deployment decision, outside this skill).

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

`run(ctx)` sees the cancellation: in-flight units finish inside `drainBudget` or stop at the next `ctx.Done()` check; work that must survive persists progress per unit (a `processed_at` column) so the next run resumes. Timeouts on the deepest single path must sum to less than `drainBudget`, and `drainBudget` must be under the platform's kill deadline (k8s `terminationGracePeriodSeconds`) - otherwise SIGKILL lands mid-work. A job runner (Asynq) has its own shutdown budget and signal handling - see `go-messaging-patterns`; the code under its handler still honours `ctx`.

## Edge Cases

- Nil channel send/receive blocks forever
- Send on closed channel panics; `v, ok := <-ch` detects close
- WaitGroup: `Add` before `go`, never inside the goroutine. An `Add` that takes the counter from zero must happen before `Wait` starts; reuse is legal only after the previous `Wait` has returned - an `Add` before that can panic (`WaitGroup is reused before previous Wait has returned`)

## Leak Diagnosis (debugging)

- `/debug/pprof/goroutine?debug=1` groups goroutines by identical stack with a count per group; `?debug=2` lists every goroutine ungrouped in traceback form and shows how long each has been blocked (whole minutes, only once blocked 1 minute or more) - that separates "parked and cycling" from "parked since deploy"
- **Growth decides, signature explains.** Rank stacks by count growth across snapshots; only a growing stack is the leak. A flat count is a steady state even when its signature looks suspicious - say so rather than reporting it as a second leak. A flat count can still be a `[Must]` on the source (an uncancellable loop) - report it as a defect, not as the leak
- Counts carry structure: N blocked `heartbeat` goroutines means N live owners (N constructors called), not one
- Stack signature -> cause:
  - `chan send` = the receiver exited (owner must close / cancel), **or** it is alive and never drains (apply a backpressure policy)
  - `chan receive` / `for range ch` = sender never closes; a goroutine parked on `<-time.After(d)` also shows as `chan receive` or `select` with no timer frame on the stack
  - `sync.WaitGroup.Wait` / `errgroup.(*Group).Wait` = a worker never returns; both block until every goroutine returns - `WithContext` only cancels a ctx the workers must check
  - `select` = no arm can ever fire (nil channel, ctx never cancelled)
  - `time.Sleep` in a bare `for` = a background loop with no `ctx.Done()` arm
- Each leaked goroutine retains its stack plus everything it references, so RSS tracks goroutine count and never recovers without a restart; a sender blocked under a lock also stalls every other caller of that lock
- Dump line numbers come from the deployed build; when they differ from the tree, match on function name and say which build the dump is from. Working from a dump with no source: name the cause from the signature and mark the inferred clauses `(inferred)`
- `goleak.VerifyTestMain(m)` gates a whole package (`VerifyNone(t)` only the test it annotates); export `runtime.NumGoroutine()` as a gauge and alert on sustained growth

## Output Format

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design / implementation | `## Concurrency Design` with `### Goroutines`, `### Fan-Out`, `### Synchronization`, then top-level `## Verification` |
| Review | `## Findings`, then `## Concurrency Design` with the three subsections describing the code as it exists today, then `## Verification` |
| Debug (leak / hang) | two opening lines `**Failing:**` and `**First fix:**`, then `## Leak Diagnosis`, `## Findings`, `## Verification` - all three top-level |

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

## Leak Diagnosis
| Stack Signature | Count Trend | Root Cause | Fix |
|-----------------|-------------|------------|-----|

## Verification
| Check | Where |
|-------|-------|
```

Cell values: `Owner` is the function or type that starts the goroutine and waits for it (`Settler.SettleAll`, `main`); a goroutine the framework owns (Asynq worker, `http.Server` conn) gets one row naming the framework as `Owner`. `Termination Path` is the exit the code actually gives the goroutine (`ctx.Done()`, `channel closed`, `returns when done`, `none` when nothing closes or cancels it); the owner's join belongs in `Owner`. `Required?` is `Required | Optional`. `Failure Behavior` is `cancel siblings | record and continue | abort batch`. `Protection` is `Mutex | RWMutex | atomic | Once | channel | errgroup | WaitGroup | external (DB lock, limiter) | none`. `Count Trend` is `Growing | Flat | unknown` - one row per signature in the dump; code with no dump row is a Finding, not a row. `Timeout` is a duration or `none`. Every `Protection: none` row over state that more than one goroutine writes is also a `[Must]` finding - a Design engagement adds `## Findings` after `## Verification` to hold it. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries. `Verification` rows are the checks that would catch this class of defect - `goleak`, `go test -race`, a bounded-return-on-cancel test, a concurrency-ceiling assertion - each naming the package or CI step that runs it. `**Failing:**` names the symptom and the stack signature that carries it (`goroutines 1.2k -> 9.8k, chan send in Broadcaster.Publish`); `**First fix:**` names the one smallest edit that stops the growth - a second edit, even to the same type, is a Finding. `(inferred)` suffixes the clause it qualifies, not the whole cell. When the dump's frames disagree with the source, the dump wins and the `Defect:` line names the discrepancy. Every cell describes the code as written; the intended value goes in the finding's `Fix`.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {what goes wrong, and under what conditions if it is currently latent}
- Rule: {the concurrency rule violated}
- Fix: {concrete edit}
```

`[Must]` for a data race, a leak, a deadlock, a lost or silently dropped result, a goroutine that cannot be cancelled, or a panic reachable in production (an unrecovered goroutine panic ends the process); `[Recommend]` otherwise. A defect that is currently masked (by lock ordering, by a caller that happens to serialize) is still `[Must]` - say what unmasks it. Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not; a range is `file:start-end`. Order `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites is one heading citing the first site, with the rest named on the `Defect:` line. A defect this skill does not own (a swallowed error, a transaction held open, an authorization gap) is still reported, never dropped: one block per such defect after the owned findings, in the same file-then-line order, labelled by the criteria above, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- Goroutines without context + termination
- Closing channels from the receiver
- `time.Sleep` as synchronization
- Unbuffered channels in hot paths
- One errgroup for required + optional (the first error cancels the shared ctx, so optional work dies with the required)
- Sharing memory directly when channel ownership transfer fits
