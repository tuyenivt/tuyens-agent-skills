---
name: task-go-debug
description: Debug Go errors - panics, context errors, SQL connectivity, data races, goroutine leaks, GORM association issues from stack traces or symptoms.
agent: go-tech-lead
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

### STEP 0 - REPRODUCTION PROTOCOL

Before reading any code, lock the reproducer:

1. **Minimal trigger:** request, command, payload, or test that produces the failure
2. **Environment:** `go version`, `GOOS`/`GOARCH`, and the versions from `go.mod` for the suspect dependencies (Go bugs frequently track to a dependency upgrade not visible from the stack trace)
3. **Frequency:** every request, 5% of requests, only under load, only after N minutes uptime. Reconcile the reported rate with the conditional rate before classifying - "8% of requests panic" plus "the panic site executes 8% of the time" usually means **100% of the requests that reach the bug fail**, not a flaky bug.
4. **First seen:** commit, deploy, or dependency bump that introduced it (`git bisect` is cheap once a reproducer exists)

If the reporter cannot reproduce, ask for it before classifying - speculative debugging burns hours.

Gather STEP 0 and STEP 1 in the same exchange - the stack trace names the suspect dependencies, so one question round covers both.

### STEP 1 - INTAKE

Ask for the full stack trace or error, source file, expected behavior. For a stack trace, identify the first application frame and read that file.

For partial input ("it doesn't work"): ask which command, expected vs actual, reproducibility, frequency.

**For "no error, just wrong behavior"** (a field is empty in the DB / a request field is ignored): reframe as **at which layer does the value disappear**? Trace boundaries:

`c.Request.Body` -> `c.ShouldBindJSON(&dto)` -> validator tags -> JSON tag mapping (no tag = `Field` only; lowercase `field` drops) -> service-layer mapping (`mapstructure.Decode`, manual copy) -> GORM column tag (`gorm:"column:..."`, `gorm:"-"`) -> `db.Select(...)` allowlist or `db.Omit(...)` -> DB column.

Same shape for Asynq tasks: enqueue -> `json.Marshal` (unexported fields silently dropped) -> worker `json.Unmarshal` -> handler. Mirrored for response-side loss ("in the DB, missing from the API"): `db.Select(...)` allowlist -> struct scan -> response-DTO mapping -> `json:"-"` / `omitempty` dropping a legitimate zero value. Identify the lost-at boundary before reading code.

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

Intermittent: nullable FK, or cache returning partial objects. Adjacent smell: the same handler often masks all DB errors into a single status (`AbortWithStatus(404)` on every error path) - discriminate `errors.Is(err, gorm.ErrRecordNotFound)` from other errors. See `go-error-handling`.

**Context errors**
- `DeadlineExceeded` -> timeout too short or downstream slow
- `Canceled` -> client disconnected; usually not a bug

**Database / SQL**
- `connection refused` -> DB down or wrong DSN. Use skill: `go-data-access`
- `too many connections` -> pool exhaustion. Three root causes, in descending frequency: **(1) transaction held across external I/O** (HTTP call, broker dispatch) - the connection is pinned for the full round-trip; (2) missing `rows.Close()` after iterating `Rows`; (3) unbounded goroutines each calling `db.X`. Defaults are unbounded - check `SetMaxOpenConns` and the per-replica fan-in budget against the DB's `max_connections`.
- `duplicate key` -> use idempotent upsert
- `could not serialize access` -> transaction retry or isolation change

**Data race** - the two stacks in `-race` output are the bug. Find the shared field; choose `sync.Mutex` / channels / `sync/atomic`. Use skill: `go-concurrency`.

**Goroutine leak** - `runtime.NumGoroutine()` growing. Check context propagation, `select` with `<-ctx.Done()`, channel close. Use skill: `go-concurrency`.

`pprof` walkthrough:

```bash
# Snapshot the live goroutine profile
curl -s http://localhost:6060/debug/pprof/goroutine?debug=1 > goroutine.txt

# Or interactive
go tool pprof http://localhost:6060/debug/pprof/goroutine
(pprof) top              # dominant stacks - the leaked one is usually #1
(pprof) traces           # full stack per goroutine
(pprof) list <func>      # see which line is blocked
```

The dominant stack is the leaker. A growing count of goroutines parked on `chan receive`, `select`, or `sync.WaitGroup.Wait` indicates the producer never closed the channel / cancelled the context / called `Done()`. Take two snapshots minutes apart and diff: the stack that grew is the bug.

**Build / import**
- `undefined:` -> missing import, wrong package, unexported identifier
- `imported and not used` -> remove or `_` for side-effect imports
- `cannot use X as type Y` -> check interface satisfaction

**Background jobs**
- Asynq retry loop -> idempotency + error classification. Use skill: `go-messaging-patterns`
- Worker not processing -> Redis connectivity, queue name, handler registration
- Kafka lag growing -> consumer group offset, handler error reprocess loop

**Asynq dead-letter / archived tasks** - tasks exhausted retries land in the `archived` set. Triage with `asynqmon` (web UI) or `asynq.Inspector`:

```go
insp := asynq.NewInspector(asynq.RedisClientOpt{Addr: redisAddr})
archived, _ := insp.ListArchivedTasks("default", asynq.PageSize(50))
for _, t := range archived {
    slog.Info("archived", "type", t.Type, "id", t.ID, "err", t.LastErr, "payload", string(t.Payload))
}
```

Classify each:

| Pattern | Cause | Action |
|---------|-------|--------|
| Same error across many tasks | Code bug or downstream outage | Fix, then `insp.RunTask` to requeue |
| Payload-shape mismatch (`json: cannot unmarshal`) | Producer / consumer drift after deploy or dependency upgrade | Version the payload or write a migrator; `insp.DeleteTask` the unrecoverable |
| Transient (network, timeout) on a small slice | Real intermittent failure | Tune `MaxRetry` / backoff; requeue |
| Poisoned (input invalid) | Bad upstream data | Delete; fix the producer |

If archived count grows on every deploy, the payload contract is drifting - bump a `Version` field in the payload struct and gate handler logic on it.

**Build tags / integration tests**
- `// +build integration` or `//go:build integration` files require `go test -tags=integration ./...`. Symptom: tests pass locally but a regression slips through CI because the suite ran without the tag and silently skipped the file
- `// +build !race` excludes a file under `-race` - check before declaring `-race` clean
- Constraint matrix sanity: `go list -tags=integration -f '{{.GoFiles}} {{.TestGoFiles}}' ./...` shows what each tag pulls in

### STEP 3 - LOCATE

1. Read stack top-to-bottom; find first application frame
2. Read the failing function
3. Trace the problematic value through parameters, interfaces, goroutine spawn points
4. GORM nils: check the query that loaded the parent for `Preload` / `Joins`
5. Races: identify both goroutines and the shared access
6. Leaks: find the goroutine spawn site; check exit path

### STEP 4 - ROOT CAUSE

Explain **why**, not just what. State confidence: **HIGH** (reproduced/obvious), **MEDIUM** (pattern match), **LOW** (multiple candidates).

When the incident has multiple compounding causes (e.g., a slow downstream + missing timeout + uncapped pool + no backpressure all firing during the same minute), list each cause separately with its own confidence; don't compress them into a single sentence. The fix and prevention sections then map back to each cause.

```
ROOT CAUSE: [HIGH/MEDIUM/LOW]
[Why the error occurs, citing file:line.]
```

### STEP 5 - FIX

Before/after, minimal, root-cause-targeted. Use skill: `go-error-handling` to preserve wrapping. When a sibling smell (e.g., DB errors collapsed into 404) sits on the same line as the root-cause fix, address it inline rather than leaving a known regression hazard.

Re-run the STEP 0 reproducer against the fix (for load-shaped bugs, the captured load profile). An unverified fix is a hypothesis - report verification status either way.

### STEP 6 - PREVENTION

Add a guard so this class cannot recur:

- Test exercising the failing path
- `go test -race` for concurrency bugs (CI if not already)
- `go vet` (especially `waitgroup`, `hostport`)
- `testing/synctest` over `time.Sleep` for async tests
- For GORM nils: repository integration test (testcontainers) verifying the association loads
- For pool exhaustion: load test that holds external I/O at p99 latency; assert pool budget invariant at startup
- For incidents that combined a slow downstream with no backpressure: add a concurrency limiter / circuit breaker at the offending endpoint

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
[Why, citing file:line. For multi-cause cascades, one bullet per cause with its own confidence.]

## Fix
[Before/after code]
Verification: [reproducer re-run result | not verified - reason]

## Prevention
[Test, vet, race detector, or config]
```

## Self-Check

- [ ] Reproducer + env (Go version, dependency versions, frequency) captured before classification
- [ ] Classified before reading code or proposing fix
- [ ] Root cause cites file:line; confidence stated; multi-cause cascades enumerated
- [ ] Before/after fix is minimal and root-cause-targeted; adjacent smells on the same lines addressed
- [ ] Fix verified against the STEP 0 reproducer (or "not verified" stated with reason)
- [ ] Error wrapping preserved (`%w`); no global state added
- [ ] Prevention step included
- [ ] For concurrency: `-race` referenced; cancellation path included; pprof goroutine snapshot for leaks
- [ ] For GORM nil: `Preload` / `Joins` fix + integration test recommended
- [ ] For Asynq archived: classified (code bug / drift / transient / poisoned) before requeue or delete
- [ ] Build-tag matrix checked when CI green but issue reproduces locally

## Avoid

- `sync.Mutex` where a channel or `sync/atomic` would do
- `recover()` around nil dereferences (fix the nil source)
- `time.Sleep` in tests; use channels or `testing/synctest`
- `_ =` to silence build errors
- Global variables to "fix" goroutine scope
- Nil checks around GORM associations as a band-aid (fix the missing `Preload`)
- Buffering a channel "to stop it blocking" without addressing why the receiver isn't draining
