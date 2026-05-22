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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Debug Go Error

## When to Use

- Panics, nil dereferences, runtime errors
- Data race warnings (`-race`)
- Goroutine leaks, context-deadline exceeded, pool exhaustion
- Intermittent errors (missing Preload, race conditions, pool exhaustion under load)
- Background job failures (Asynq retry loops, Kafka consumer lag)

Not for: new features (`task-go-implement`), general review (`task-go-review`).

## Workflow

### STEP 1 - INTAKE

Ask for the full stack trace or error output, source file, expected behavior. For a stack trace, identify the first application frame and read that file.

For partial input ("it doesn't work"): ask which command was run, expected vs actual, reproducibility, frequency (every time / intermittent / under load).

**For "no error, just wrong behavior"** (a body field is empty in the DB / a request field is ignored): reframe as **at which layer does the value disappear**? Trace the boundaries:

`c.Request.Body` → `c.ShouldBindJSON(&dto)` → validator tags → JSON tag mapping (no tag = `Field` only, lowercase `field` drops) → service-layer mapping (`mapstructure.Decode`, manual copy) → GORM column tag (`gorm:"column:..."`, `gorm:"-"`) → `db.Select(...)` allowlist or `db.Omit(...)` → DB column.

Same shape for Asynq tasks: enqueue site → `json.Marshal` (unexported fields silently dropped) → worker `json.Unmarshal` → handler body. Identify the lost-at boundary before reading code.

### STEP 2 - CLASSIFY

Match to one category, then load the matching atomic skill.

**Panic / nil dereference**
- `invalid memory address` → trace nil origin: unchecked error return, missing nil guard, uninitialized field
- `index out of range` → check slice length before indexing

**GORM nil-association** (very common). Access on an association (`order.User.Email` with `User == nil`) usually means missing `Preload` / `Joins`:

```go
// Bad: User is nil because not preloaded
order, _ := db.First(&order, id)
fmt.Println(order.User.Email) // PANIC

// Good
order, _ := db.Preload("User").First(&order, id)
```

Intermittent: nullable FK, or cache returning partial objects.

**Context errors**
- `context.DeadlineExceeded` → timeout too short or downstream slow
- `context.Canceled` → client disconnected; usually not a bug

**Database / SQL**
- `connection refused` → DB down or wrong DSN. Use skill: `go-data-access`
- `too many connections` → pool exhaustion. Check `SetMaxOpenConns`; cause is often missing `rows.Close()` or unbounded goroutines
- `duplicate key` → use idempotent upsert
- `could not serialize access` → transaction retry or isolation change

**Data race** - the two stacks in the `-race` output are the bug. Find the shared field and choose `sync.Mutex` / channels / `sync/atomic`. Use skill: `go-concurrency`.

**Goroutine leak** - `runtime.NumGoroutine()` growing. Check: context propagation, `select` with `case <-ctx.Done()`, channel close. Use `go tool pprof http://...:6060/debug/pprof/goroutine`. Use skill: `go-concurrency`.

**Build / import**
- `undefined:` → missing import, wrong package, unexported identifier
- `imported and not used` → remove or `_` for side-effect imports
- `cannot use X as type Y` → check interface satisfaction

**Background jobs**
- Asynq retry loop → check idempotency + error classification. Use skill: `go-messaging-patterns`
- Worker not processing → Redis connectivity, queue name, handler registration
- Kafka lag growing → consumer group offset, handler error reprocess loop

### STEP 3 - LOCATE

1. Read stack top-to-bottom; find the first application frame
2. Open and read the failing function
3. Trace the problematic value upstream through parameters, interface implementations, goroutine spawn points
4. For GORM nils: check the query that loaded the parent; is `Preload` / `Joins` present?
5. For races: identify both goroutines and the shared access
6. For leaks: find the goroutine spawn site; check the exit path

### STEP 4 - ROOT CAUSE

Explain **why**, not just what. State confidence: **HIGH** (reproduced or obvious), **MEDIUM** (pattern match), **LOW** (multiple candidates).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW]
[Why the error occurs, citing file:line. Explain intermittency if relevant.]
```

### STEP 5 - FIX

Provide before/after. Minimal, root-cause-targeted. Use skill: `go-error-handling` to preserve wrapping conventions.

### STEP 6 - PREVENTION

Add a guard so this class of error cannot recur:

- Test exercising the failing code path
- `go test -race` for concurrency bugs (CI if not already)
- `go vet` (especially `waitgroup`, `hostport` analyzers)
- `testing/synctest` over `time.Sleep` for async tests
- For GORM nils: repository integration test (testcontainers) verifying the association loads

## Edge Cases

- **No stack trace**: ask user to reproduce with `GOTRACEBACK=all` or check structured logs
- **Intermittent (5% of requests)**: suspect missing Preload, race, or pool exhaustion under load
- **Prod-only**: check environment differences (pool size, timeouts, TLS), missing `-race` in CI, load-dependent issues
- **Cascading panics**: focus on the **first** panic; trace its origin before secondary failures
- **Third-party library panic**: identify the application frame calling in; check inputs

## Output Format

```
## Error Classification
[Category]: [specific type]

## Root Cause (confidence: HIGH/MEDIUM/LOW)
[Why, citing file:line]

## Fix
[Before/after code]

## Prevention
[Test, vet, race detector, or config]
```

## Self-Check

- [ ] Classified before reading code or proposing fix
- [ ] Root cause cites file:line; confidence stated
- [ ] Before/after fix is minimal and root-cause-targeted
- [ ] Error wrapping preserved (`%w`); no global state added
- [ ] Prevention step included
- [ ] For concurrency: `-race` referenced; cancellation path included
- [ ] For GORM nil: `Preload` / `Joins` fix + integration test recommended

## Avoid

- `sync.Mutex` where a channel or `sync/atomic` would do
- `recover()` around nil dereferences (fix the nil source)
- `time.Sleep` in tests; use channels or `testing/synctest`
- `_ =` to silence build errors
- Global variables to "fix" goroutine scope
- Nil checks around GORM associations as a band-aid; fix the missing `Preload`
