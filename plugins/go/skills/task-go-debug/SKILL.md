---
name: task-go-debug
description: Debug Go errors: panics, context errors, SQL connectivity, data races, goroutine leaks, GORM association issues from stack traces or symptoms.
agent: go-architect
metadata:
  category: backend
  tags: [go, gin, debug, troubleshooting, stack-trace, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Debug Go Error

## When to Use

- Debugging a panic, nil pointer dereference, or runtime error in a Go service
- Diagnosing data race warnings from `go test -race` or production race detector
- Investigating goroutine leaks, context deadline exceeded, or database connectivity issues
- Tracking down intermittent errors (missing GORM Preload, race conditions, pool exhaustion)
- Analyzing background job failures (Asynq retry loops, Kafka consumer lag)

Not for adding new features (use `task-go-implement`) or general code review.

## Edge Cases

- **No stack trace provided**: User describes behavior ("it crashes sometimes") without a trace. Ask them to reproduce with `GOTRACEBACK=all` or check structured logs for the full panic output
- **Intermittent errors**: If the error happens only on some requests (e.g., "5% of the time"), suspect: missing GORM Preload (nil association), race condition, or connection pool exhaustion under load. Ask about request volume and whether it correlates with load
- **Production-only errors**: Error doesn't reproduce locally. Check for: environment differences (connection pool size, timeouts, TLS), missing `go test -race` in CI, or load-dependent issues (pool exhaustion, goroutine accumulation)
- **Multiple errors in trace**: Stack trace shows a chain of panics or multiple goroutines. Focus on the first panic (root cause) and trace its origin before looking at cascading failures
- **Third-party library panic**: Stack trace originates in a dependency, not application code. Identify the application frame that called into the library and check the inputs passed

## Workflow

### STEP 1 - INTAKE

Ask for: full stack trace or error output, the source file where the error originates, and what the user expected to happen. If a stack trace is provided, identify the first application-code frame (skip standard library frames) and read that file.

If the user provides only a partial error message or vague description ("it doesn't work"), ask clarifying questions: which command was run, what the expected vs actual behavior is, whether the error is reproducible, and how frequently it occurs (every time, intermittently, under load only).

**If "no error, just wrong behavior":** When the user reports "the value I sent in the body is empty in the DB" or "the field I added to the request gets ignored" with no exception, reframe as a boundary-loss question: at which layer does the value disappear? Trace the Go path: `c.Request.Body` -> `c.ShouldBindJSON(&req)` against a DTO struct (a body field with no matching DTO field is silently dropped unless `binder.EnableDecoderDisallowUnknownFields` is set on the JSON binding - default Gin does NOT reject unknown fields) -> validator tags (`validate:"required"` rejects zero-value, but nothing rejects "field doesn't exist on the struct") -> JSON tag presence (a field without `json:"tier"` decodes from the capitalized Go name `"Tier"` only - so `{"tier": "gold"}` lands in zero-value if the struct field is `Tier string` without a tag) -> service-layer copy / mapping (`mapstructure.Decode(reqMap, &order)`, `copier.Copy(&order, &req)`, hand-written `order.Tier = req.Tier` - any whitelist drop here loses the value) -> GORM column tag (`gorm:"column:user_tier"` mismatches migration column `tier`; or `gorm:"-"` excludes the field from persistence entirely) -> `db.Select("name", "total").Create(&order)` (explicit field allowlist - any field not in `Select` is not written; mirror smell: `db.Omit("tier")`) -> DB column. Same shape for Asynq tasks: enqueue site -> `json.Marshal(payload)` (unexported field has no JSON tag and is silently dropped because `encoding/json` ignores unexported fields entirely) -> `task.Payload()` bytes -> `json.Unmarshal(data, &p)` in worker (same DTO/tag mismatch surface as the HTTP path) -> `perform` body. The bug is almost always at one of these boundaries, not in the handler body. Identify which boundary lost the value before reading any code.

### STEP 2 - CLASSIFY

Match the error to one of these categories, then load the relevant atomic skill:

**Panic / Nil Dereference**

- `runtime error: invalid memory address or nil pointer dereference` -> trace where the nil originates. Common causes: unchecked error return (value is nil when err != nil), missing nil check on optional return, uninitialized struct field.
- `index out of range` -> check slice length before indexing.

**GORM-specific nil patterns** (extremely common): If the nil access is on an association field (e.g., `order.User.Email` where `User` is nil), the most likely cause is a missing `Preload` or `Joins` call. GORM does not load associations by default - they remain zero-value (nil for pointers, empty for slices):

```go
// Bad: User is nil because it wasn't preloaded
order, _ := db.First(&order, id)
fmt.Println(order.User.Email) // PANIC: nil pointer dereference

// Good: Preload the association
order, _ := db.Preload("User").First(&order, id)
// OR if filtering by association field:
order, _ := db.Joins("User").First(&order, id)
```

If the nil panic is **intermittent**, check whether some records have the association and others don't (nullable FK), or whether a caching layer returns partial objects.

**Context Errors**

- `context.DeadlineExceeded` -> timeout too short or downstream service too slow. Check `context.WithTimeout` duration and which call is taking too long.
- `context.Canceled` -> caller cancelled the request (client disconnect, parent context cancelled). Usually not a bug unless the cancellation is unexpected.

**Database / SQL Errors**

- `sql: connection refused` -> DB not running or wrong connection string. Check host, port, credentials. Use skill: `go-data-access`.
- `sql: too many connections` -> pool exhausted. Check `SetMaxOpenConns`, `SetMaxIdleConns`, `SetConnMaxLifetime`. Common cause: missing `rows.Close()` or unbounded goroutines each opening connections.
- `pq: duplicate key value violates unique constraint` -> duplicate record. Check unique indexes and use upsert or idempotency guard.
- `pq: could not serialize access` -> transaction serialization conflict under concurrent writes. Retry the transaction or use a less strict isolation level.

**Data Race**

- `WARNING: DATA RACE` -> concurrent read/write without synchronization. The race detector output shows the two goroutines and the memory address. The two stacks are the bug - find the shared field they both touch, then choose `sync.Mutex` / `sync.RWMutex` (shared state), channels (ownership transfer), or `sync/atomic` (single integer/pointer). Use skill: `go-concurrency` for the canonical patterns.

**Goroutine Leak**

- `runtime.NumGoroutine()` growing without bound -> goroutine started but never finishes. Check: is the context being cancelled? Is a channel being closed? Is there a `select` with a `done` case? Use skill: `go-concurrency`.
- Use `pprof` to inspect goroutine state: `go tool pprof http://localhost:6060/debug/pprof/goroutine` shows all goroutines and where they're blocked.

**Build / Import Errors**

- `undefined:` -> missing import, wrong package, or unexported identifier.
- `imported and not used` -> remove unused import or use `_` for side-effect imports.
- `cannot use X as type Y` -> type mismatch, check interface satisfaction.

**Background Job Errors (Asynq/Kafka)**

- Asynq task stuck in retry loop -> check idempotency and error classification. Use skill: `go-messaging-patterns`.
- Asynq worker not processing -> Redis connectivity, queue name mismatch, handler not registered.
- Kafka consumer lag growing -> consumer group offset issue, handler error causing reprocess loop.

### STEP 3 - LOCATE

1. Read the stack trace top-to-bottom; find the first application-code frame (not standard library)
2. Open that source file and read the failing function
3. Trace the data path: where does the problematic value originate? Follow it upstream through function parameters, interface implementations, or goroutine creation points
4. For nil dereferences on GORM associations: check the query that loaded the parent model - is `Preload` or `Joins` present for the accessed association?
5. For data races: identify both goroutines from the race detector output and find the shared memory access
6. For goroutine leaks: find the goroutine creation site and trace its exit path - check for missing `case <-ctx.Done()` in select loops

### STEP 4 - ROOT CAUSE

Explain **why** the error occurs, not just what it is. State confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (likely based on pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The nil pointer dereference occurs because Order.User is accessed at order.go:87
without Preload. GORM loads only the parent model by default - associations remain
nil. When the FK (user_id) references an existing user, User is still nil unless
explicitly preloaded. This is intermittent because the code path is only hit when
order.User.Email is needed (e.g., for notification dispatch), not on every request.
```

### STEP 5 - FIX

Provide before/after code. Fix must be minimal and address root cause, not symptoms. Use skill: `go-error-handling` to ensure error wrapping conventions are preserved.

### STEP 6 - PREVENTION

Add a guard so this class of error cannot recur:

- **Test** that exercises the exact code path (including the association access)
- **`go test -race`** for concurrency bugs (add to CI if not already there)
- **`go vet`** for common mistakes (especially `waitgroup` and `hostport` analyzers)
- For flaky async tests: replace `time.Sleep` with `testing/synctest`
- Prefer `sync.WaitGroup.Go` over manual `Add`/`Done` when possible
- For GORM association issues: add a repository-level integration test with testcontainers that verifies the association is loaded

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
- [ ] For GORM nil panics, Preload/Joins fix verified and integration test recommended

## Avoid

- Do not introduce `sync.Mutex` where a channel or `sync/atomic` is simpler
- Do not add `recover()` to suppress panics from nil dereference - fix the nil source
- Do not use `time.Sleep` in tests to wait for goroutines - use channels or `testing/synctest`
- Do not swallow errors with `_ =` to make a build error go away
- Do not use global variables to "fix" goroutine scope issues
- Do not add nil checks around GORM associations as a band-aid - fix the missing Preload at the query site
