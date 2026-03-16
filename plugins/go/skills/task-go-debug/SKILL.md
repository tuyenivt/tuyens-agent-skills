---
name: task-go-debug
description: Debug Go application errors - panics, context errors, SQL connectivity, data races, and goroutine leaks. Paste a stack trace or describe the unexpected behavior.
agent: go-architect
metadata:
  category: backend
  tags: [go, gin, debug, troubleshooting, stack-trace, workflow]
  type: workflow
user-invocable: true
---

## STEP 1 - INTAKE

Ask for: full stack trace or error output, the source file where the error originates, and what the user expected to happen. If a stack trace is provided, identify the first application-code frame (skip standard library frames) and read that file.

If the user provides only a partial error message or vague description ("it doesn't work"), ask clarifying questions: which command was run, what the expected vs actual behavior is, and whether the error is reproducible. Do not guess at root cause without sufficient input.

## STEP 2 - CLASSIFY

Match the error to one of these categories, then load the relevant atomic skill:

### Panic / Nil Dereference
- `runtime error: invalid memory address or nil pointer dereference` -> trace where the nil originates. Common causes: unchecked error return (value is nil when err != nil), missing nil check on optional return, uninitialized struct field.
- `index out of range` -> check slice length before indexing.

### Context Errors
- `context.DeadlineExceeded` -> timeout too short or downstream service too slow. Check `context.WithTimeout` duration and which call is taking too long.
- `context.Canceled` -> caller cancelled the request (client disconnect, parent context cancelled). Usually not a bug unless the cancellation is unexpected.

### Database / SQL Errors
- `sql: connection refused` -> DB not running or wrong connection string. Check host, port, credentials. Use skill: `go-data-access`.
- `sql: too many connections` -> pool exhausted. Check `SetMaxOpenConns`, `SetMaxIdleConns`, `SetConnMaxLifetime`. Common cause: missing `rows.Close()` or unbounded goroutines each opening connections.
- `pq: duplicate key value violates unique constraint` -> duplicate record. Check unique indexes and use upsert or idempotency guard.

### Data Race
- `WARNING: DATA RACE` -> concurrent read/write without synchronization. The race detector output shows the two goroutines and the memory address. Fix: use `sync.Mutex`, `sync.RWMutex`, channels, or `sync/atomic`.

```go
// BEFORE (data race - concurrent map access)
type Cache struct {
    data map[string]string
}
func (c *Cache) Get(key string) string { return c.data[key] }
func (c *Cache) Set(key, val string)   { c.data[key] = val }

// AFTER (sync.RWMutex protects concurrent access)
type Cache struct {
    mu   sync.RWMutex
    data map[string]string
}
func (c *Cache) Get(key string) string {
    c.mu.RLock()
    defer c.mu.RUnlock()
    return c.data[key]
}
func (c *Cache) Set(key, val string) {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.data[key] = val
}
```

### Goroutine Leak
- `runtime.NumGoroutine()` growing without bound -> goroutine started but never finishes. Check: is the context being cancelled? Is a channel being closed? Is there a `select` with a `done` case? Use skill: `go-concurrency`.

### Build / Import Errors
- `undefined:` -> missing import, wrong package, or unexported identifier.
- `imported and not used` -> remove unused import or use `_` for side-effect imports.
- `cannot use X as type Y` -> type mismatch, check interface satisfaction.

### Background Job Errors (Asynq/Kafka)
- Asynq task stuck in retry loop -> check idempotency and error classification. Use skill: `go-messaging-patterns`.
- Asynq worker not processing -> Redis connectivity, queue name mismatch, handler not registered.
- Kafka consumer lag growing -> consumer group offset issue, handler error causing reprocess loop.

## STEP 3 - LOCATE

1. Read the stack trace top-to-bottom; find the first application-code frame (not standard library)
2. Open that source file and read the failing function
3. Trace the data path: where does the problematic value originate? Follow it upstream through function parameters, interface implementations, or goroutine creation points
4. For data races: identify both goroutines from the race detector output and find the shared memory access
5. For goroutine leaks: find the goroutine creation site and trace its exit path

## STEP 4 - ROOT CAUSE

Explain **why** the error occurs, not just what it is. State confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (likely based on pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The data race occurs because Cache.data is a map accessed concurrently by
GetUserCached (read at user.go:45) and RefreshCache (write at user.go:62)
without synchronization. Maps in Go are not safe for concurrent use.
```

## STEP 5 - FIX

Provide before/after code. Fix must be minimal and address root cause, not symptoms. Use skill: `go-error-handling` to ensure error wrapping conventions are preserved.

## STEP 6 - PREVENTION

Add a guard so this class of error cannot recur:
- **Test** that exercises the exact code path
- **`go test -race`** for concurrency bugs (add to CI if not already there)
- **`go vet`** for common mistakes (especially `waitgroup` and `hostport` analyzers)
- For flaky async tests: replace `time.Sleep` with `testing/synctest`
- Prefer `sync.WaitGroup.Go` over manual `Add`/`Done` when possible

## Avoid

- Do not introduce `sync.Mutex` where a channel or `sync/atomic` is simpler
- Do not add `recover()` to suppress panics from nil dereference - fix the nil source
- Do not use `time.Sleep` in tests to wait for goroutines - use channels or `testing/synctest`
- Do not swallow errors with `_ =` to make a build error go away
- Do not use global variables to "fix" goroutine scope issues

## Output Format

```
## Error Classification
[Category]: [specific error type]

## Root Cause (confidence: HIGH/MEDIUM/LOW)
[Why the error occurs, referencing specific file:line]

## Fix
[Before/after code blocks]

## Prevention
[Test, go vet, race detector, or config change to prevent recurrence]
```

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal and addresses root cause, not symptom
- [ ] Go idioms preserved - errors wrapped with `%w`, no global state introduced
- [ ] Prevention step included (test, `go vet`, or race detector guidance)
- [ ] For concurrency bugs, `go test -race` referenced; for goroutine leaks, cancellation path included
