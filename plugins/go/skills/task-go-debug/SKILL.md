---
name: task-go-debug
description: Debug Go errors - panics, context errors, SQL connectivity, data races, goroutine leaks, GORM association issues from stack traces or symptoms.
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
- Intermittent errors (missing Preload, races, pool exhaustion under load)
- Background job failures (Asynq retry loops, Kafka consumer lag)

Not for: new features (`task-go-implement`), general review (`task-go-review`).

## Workflow

### STEP 1 - INTAKE

Ask for the full stack trace or error, source file, expected behavior. For a stack trace, identify the first application frame and read that file.

For partial input ("it doesn't work"): ask which command, expected vs actual, reproducibility, frequency.

**For "no error, just wrong behavior"** (a field is empty in the DB / a request field is ignored): reframe as **at which layer does the value disappear**? Trace boundaries:

`c.Request.Body` -> `c.ShouldBindJSON(&dto)` -> validator tags -> JSON tag mapping (no tag = `Field` only; lowercase `field` drops) -> service-layer mapping (`mapstructure.Decode`, manual copy) -> GORM column tag (`gorm:"column:..."`, `gorm:"-"`) -> `db.Select(...)` allowlist or `db.Omit(...)` -> DB column.

Same shape for Asynq tasks: enqueue -> `json.Marshal` (unexported fields silently dropped) -> worker `json.Unmarshal` -> handler. Identify the lost-at boundary before reading code.

### STEP 2 - CLASSIFY

**Panic / nil dereference**
- `invalid memory address` -> trace nil origin: unchecked error, missing nil guard, uninitialized field
- `index out of range` -> check slice length before indexing

**GORM nil-association** (very common). Access on an association (`order.User.Email` with `User == nil`) usually means missing `Preload`:

```go
// Bad
order, _ := db.First(&order, id)
fmt.Println(order.User.Email) // PANIC

// Good
order, _ := db.Preload("User").First(&order, id)
```

Intermittent: nullable FK, or cache returning partial objects.

**Context errors**
- `DeadlineExceeded` -> timeout too short or downstream slow
- `Canceled` -> client disconnected; usually not a bug

**Database / SQL**
- `connection refused` -> DB down or wrong DSN. Use skill: `go-data-access`
- `too many connections` -> pool exhaustion. Check `SetMaxOpenConns`; root cause often missing `rows.Close()` or unbounded goroutines
- `duplicate key` -> use idempotent upsert
- `could not serialize access` -> transaction retry or isolation change

**Data race** - the two stacks in `-race` output are the bug. Find the shared field; choose `sync.Mutex` / channels / `sync/atomic`. Use skill: `go-concurrency`.

**Goroutine leak** - `runtime.NumGoroutine()` growing. Check context propagation, `select` with `<-ctx.Done()`, channel close. `go tool pprof http://...:6060/debug/pprof/goroutine`. Use skill: `go-concurrency`.

**Build / import**
- `undefined:` -> missing import, wrong package, unexported identifier
- `imported and not used` -> remove or `_` for side-effect imports
- `cannot use X as type Y` -> check interface satisfaction

**Background jobs**
- Asynq retry loop -> idempotency + error classification. Use skill: `go-messaging-patterns`
- Worker not processing -> Redis connectivity, queue name, handler registration
- Kafka lag growing -> consumer group offset, handler error reprocess loop

### STEP 3 - LOCATE

1. Read stack top-to-bottom; find first application frame
2. Read the failing function
3. Trace the problematic value through parameters, interfaces, goroutine spawn points
4. GORM nils: check the query that loaded the parent for `Preload` / `Joins`
5. Races: identify both goroutines and the shared access
6. Leaks: find the goroutine spawn site; check exit path

### STEP 4 - ROOT CAUSE

Explain **why**, not just what. State confidence: **HIGH** (reproduced/obvious), **MEDIUM** (pattern match), **LOW** (multiple candidates).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW]
[Why the error occurs, citing file:line.]
```

### STEP 5 - FIX

Before/after, minimal, root-cause-targeted. Use skill: `go-error-handling` to preserve wrapping.

### STEP 6 - PREVENTION

Add a guard so this class cannot recur:

- Test exercising the failing path
- `go test -race` for concurrency bugs (CI if not already)
- `go vet` (especially `waitgroup`, `hostport`)
- `testing/synctest` over `time.Sleep` for async tests
- For GORM nils: repository integration test (testcontainers) verifying the association loads

## Edge Cases

- No stack trace: ask for `GOTRACEBACK=all` or check structured logs
- Intermittent (5% requests): suspect missing Preload, race, or pool exhaustion
- Prod-only: check env differences (pool size, timeouts, TLS), missing `-race` in CI, load-dependent
- Cascading panics: focus on the **first** panic; trace its origin
- Third-party library panic: identify the application frame calling in; check inputs

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
- Nil checks around GORM associations as a band-aid (fix the missing `Preload`)
