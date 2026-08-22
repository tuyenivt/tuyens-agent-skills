---
name: task-go-review-reliability
description: Go reliability review - context deadlines, gobreaker/backoff, errgroup fan-out, goroutine leaks & backpressure, pool bounds, graceful shutdown.
agent: go-reliability-engineer
metadata:
  category: backend
  tags: [go, gin, reliability, resilience, context, circuit-breaker, goroutine, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Go Reliability Review

Go-aware reliability review naming `context.Context` deadlines and cancellation, `sony/gobreaker`, `cenkalti/backoff/v4`, `errgroup` / `semaphore.Weighted` structured concurrency, goroutine-leak and channel-backpressure control, `database/sql` pool bounds, and `http.Server.Shutdown`. Reliability = behavior under failure and saturation: what happens when a dependency is slow or down, load spikes, or a process crashes mid-operation. Every finding names the failure mode and blast radius, with concrete fixes for Go 1.25+ / Gin.

Stack-specific delegate of `task-code-review-reliability` for Go.

## When to Use

- Go/Gin PR adding or changing a downstream call (`http.Client`, DB, Asynq / Kafka, gRPC)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and delivery semantics
- Hardening after a near-miss; recurring resilience-debt sweep
- New goroutine fan-out, channel pipeline, or worker pool reviewed for leaks and backpressure

**Not for:** general review (`task-go-review`), throughput / latency (`task-go-review-perf`), instrumentation wiring (`task-go-review-observability`), security (`task-go-review-security`).

## Seam With Adjacent Lenses

- **vs. Perf:** perf tunes the `database/sql` pool and goroutine fan-out for throughput; this lens verifies they are bounded and that exhaustion sheds or fails fast. A slow query is perf; the untimed query holding a pooled connection until the DB kills it is reliability.
- **vs. Observability:** obs owns the breaker-state metric and the fallback log line; this lens owns the breaker and the fallback existing and being wired. A missing `trace_id` is obs; a missing `context.WithTimeout` on the call is reliability.
- **vs. core Phase B:** `task-go-review` Phase B owns happy-path correctness and `go-concurrency` goroutine ownership; this lens owns partial failure, dependency failure, and saturation. Idempotency sits at the seam - the umbrella dedups.

## Depth

| Depth      | When                                            | Runs                                          |
| ---------- | ----------------------------------------------- | --------------------------------------------- |
| `standard` | Default                                         | All steps except the Failure-Mode Map         |
| `deep`     | Requested, or handed down by `task-go-review`   | All + `Failure-Mode and Blast-Radius Map`     |

At `deep`, trace each new or changed dependency's failure path with `failure-propagation-analysis` across goroutines and shared resources (the `database/sql` pool, worker pools, channels, the broker) and name the loop-breaker in the Failure-Mode and Blast-Radius Map.

**Whole-service sweep** (resilience-debt pass with no feature branch, and the mode a "sweep before peak season" request asks for). When Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-12 repo-wide at `HEAD`. Step 4's categories are read in full rather than per changed file, and every diff-worded rule downstream (the ripple clause, `ops-resiliency`'s "purely Asynq-idempotency" skip) reads against the whole surface instead. Findings cite current code and are pre-existing by construction.

Three things the sweep changes, all of which otherwise misfire:

- **Refs.** The precondition emits no handle on a fail-fast, so nothing supplies the writer's required refs. Resolve them directly: `branch` = `base_ref` = `head_ref` = the trunk branch name, `base_sha` = `head_sha` = the resolved SHA of `HEAD` (a full SHA, not the literal string).
- **Verify attribution.** Run `review-finding-verify` for confirmation only - its Step 1, against the code at `HEAD`. **Skip its attribution and de-escalation.** With no diff, every finding attributes `Pre-existing` and every `[Must]` de-escalates, which would empty a debt sweep of the blockers it exists to surface. Report the tally as `<N> confirmed, - reattributed, <K> dropped`.
- **Depth.** A sweep defaults to `deep`: the Failure-Mode and Blast-Radius Map is the per-dependency loop-breaker table a standing-debt pass is asking for. Pass `standard` explicitly to suppress it.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-reliability` | Current branch vs base; fails fast on trunk |
| `/task-go-review-reliability <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-reliability pr-<N>` | PR head fetched into local branch (user runs fetch) |

Append `deep` to request the deep pass (e.g. `/task-go-review-reliability <branch> deep`).

**Subagent runs** (e.g. spawned by `task-go-review`). The parent passes the precondition handle, `base_ref` / `head_ref`, `base_sha` / `head_sha`, the pre-read diff and commit log, depth, the pre-confirmed stack, the data-access mix, messaging, and the acceptance criteria when a requirement source resolved. Steps 2-3 consume those instead of re-running - never re-run git. The verify pass before Step 12 is skipped (the parent verifies the merged set once). Step 12 returns the whole Output Format - Summary, Findings, Recommendations, the `deep` Map, Next Steps - not the findings alone, and writes nothing.

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format, several with their own `## Findings`. They are rule sets here, not deliverables: emit this skill's Output Format only. Their blockquoted `Load stack-detect first` lines are likewise satisfied by Step 2 and are not a second obligation.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a parent (`task-go-review`) and skip detection. If not Go, stop and route the user to `/task-code-review-reliability`.

Detect data access (GORM / sqlx / database/sql / mixed) and messaging (Asynq / Kafka / none).

### Step 3 - Resolve the Diff

Standalone only - skip the whole step, SHA capture included, when running as a subagent with handle + artifacts pre-passed; the parent supplies the SHAs.

Use skill: `review-precondition-check`. Read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

**Resolve the round now, before any analysis.** Stat `review-reliability-<branch>.md` in the writer's output directory (sanitizing the branch name per `review-report-writer`). Absent or frontmatter-less -> `round: 1`. Present and valid -> `round = prior.round + 1`, with its `head_sha` as `prior_head_sha`. **When that `head_sha` equals the current head and the invocation asks for nothing more (no deeper depth, no sweep where the prior was a diff review), print `No new commits on <branch> since prior reliability review at <sha_short>. Prior report unchanged.` and stop** - do not re-review and do not overwrite the report. Doing this at Step 12 instead wastes the entire pass and destroys the prior round's findings.

**On a trunk fail-fast, switch to the whole-service sweep under Depth** - that is the resilience-debt path, not a stop.

If the clean-tree gate fails and **the only untracked file is this workflow's own prior report** (`review-reliability-<branch>.md`), the gate is tripping on the artifact the last run wrote; every round-2 review would be unreachable. Say so, treat the tree as clean, continue, and tell the user to gitignore the report path. Any other fail-fast: surface verbatim and stop.

### Step 4 - Read the Reliability Surface

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (a small diff ripples: a new service method calling an unchanged untimed `http.Client` is a new failure path at the call site). Read the full `go.mod` here (not just diff adds) to fill the Summary's Resilience Libraries field.

- External clients: `http.Client` construction / shared clients, gRPC dials, third-party SDKs - `Timeout`, `Transport` tuning, breaker, retry
- `service` methods composing multiple downstream calls - timeout budget, `errgroup` fan-out, partial-failure handling
- Goroutine launch sites: `go func()`, `errgroup.Go`, `wg.Go`, worker pools, channel pipelines - ownership, `<-ctx.Done()`, bounding
- Asynq / Kafka producers + consumers - idempotency, retry / `MaxRetry`, DLQ, post-commit enqueue
- Side-effecting flows (payment, notification, provisioning) - idempotency keys, outbox vs dual write
- Config / wiring: `cmd/api/main.go` / `internal/db/db.go` for `database/sql` pool bounds, `gobreaker` / `backoff` config, `http.Transport` setup, graceful-shutdown and recovery middleware
- Dependency adds: `sony/gobreaker`, `cenkalti/backoff/v4`, `golang.org/x/sync`

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns - load it when the surface includes an external client, a fanning-out service, or breaker / retry / timeout config; skip it only when **none** of those appear, which on a mixed surface means load it. Use skill: `failure-propagation-analysis` to trace how a failure at each new / changed dependency propagates through shared resources (the `database/sql` pool, a worker pool, a channel, the broker) - it is an analysis tool whose output feeds the `Blast Radius` field and, at `deep`, the Map; its own template is not emitted.

**Config the code reads but the deployment does not set** is in scope here: a base URL, DSN, or credential introduced in the diff and absent from the deploy manifest fails every call at runtime rather than at boot. Check the manifest for each new setting the wiring reads, and say so when the manifest is not in the repo.

Gating skips atomic loads, never checklist rows. Every checklist row below runs on this skill's own text regardless of which atomics loaded; a row goes N/A only when the diff has no matching surface (the Self-Check rule).

### Step 5 - Timeouts and Deadlines (context.Context)

Use skill: `go-concurrency` for context propagation and per-goroutine timeouts.

- [ ] **`ctx` propagated end to end** - every downstream call (DB, HTTP, gRPC, Asynq enqueue) takes the request `ctx` (`c.Request.Context()`), threaded handler -> service -> repository. No `context.Background()` / `context.TODO()` swapped in mid-request (severs the deadline and cancellation).
- [ ] **Deadline on every outbound call** - `context.WithTimeout(ctx, d)` with `defer cancel()` on external I/O; `db.WithContext(ctx)` / sqlx `*Context` so a slow query is cancellable. A call with no deadline blocks until the socket or DB decides.
- [ ] **`http.Client` bounded** - shared package-level client with `Timeout` set AND a tuned `Transport` (`MaxIdleConns`, `MaxIdleConnsPerHost`, `IdleConnTimeout`); never `http.DefaultClient` / `http.Get` - no timeout, so a hung upstream pins the goroutine forever.
- [ ] **Timeout budget on chained / fan-out calls** - a handler fanning out to N downstreams caps total time; a slow first call leaves budget for the rest or fails fast (`context.WithDeadline` derived once, passed down).
- [ ] **`ctx.Err()` honored** - long loops and blocking receives check `<-ctx.Done()` / `ctx.Err()` and return; no work continues on a cancelled request.

```go
// Bad - no timeout; a hung upstream pins this goroutine and its request ctx forever
resp, err := http.Get(url)

// Good - shared client with deadline + bounded transport, carrying the request ctx
req, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
resp, err := s.client.Do(req) // s.client = &http.Client{Timeout: 3*time.Second, Transport: tuned}
```

### Step 6 - Retries

`ops-resiliency` already loaded in Step 4 - reuse it for backoff, jitter, and retry-budget rules.

- [ ] **Bounded backoff with jitter** - `cenkalti/backoff/v4` (`NewExponentialBackOff` adds jitter; cap with `WithMaxRetries`) or a manual capped loop; never an uncapped `for` retry. Wrap with `backoff.WithContext(b, ctx)` so retries stop on cancellation.
- [ ] **Transient + idempotent only** - retry 5xx / timeouts / `context.DeadlineExceeded` / connection resets classified via `errors.Is`; never 4xx (won't succeed), never a non-idempotent write without an idempotency key (Step 8).
- [ ] **Retry amplification bounded** - chained services do not each retry independently (N x M call blowup); a per-request retry budget is decremented and passed downstream.
- [ ] **Non-retryable errors escape** - wrap them with `backoff.Permanent(err)` so the loop exits immediately instead of burning the budget.

### Step 7 - Circuit Breakers and Bounded Concurrency

`go-concurrency` already loaded in Step 5 - reuse it for `errgroup` / `semaphore.Weighted` bounding.

- [ ] **Breaker per external dependency** - `sony/gobreaker` with explicit `MaxRequests`, `Interval`, `Timeout`, and a `ReadyToTrip` threshold; one breaker per dependency, its state metered (visibility gap -> `task-go-review-observability`). A shared or unmonitored breaker counts as missing.
- [ ] **Bounded fan-out** - `errgroup.WithContext` + `g.SetLimit(N)` or `golang.org/x/sync/semaphore.Weighted`; unbounded per-request goroutine fan-out exhausts the scheduler, FDs, and the pool. N/A only when the fan-out is a fixed set of legs rather than one per item.
- [ ] **Optional legs separated from required ones** - `errgroup` cancels siblings on first error, so an optional downstream inside it fails the whole request. Use a separate `sync.WaitGroup` for optional legs, waited on every return path. Checked independently of the bound above: a fixed four-leg fan-out needs no `SetLimit` and can still be fatally mixed.
- [ ] **Bulkhead isolation** - a worker pool or semaphore per downstream so one slow dependency cannot consume the concurrency budget others share (a Go bulkhead is a bounded semaphore / dedicated pool, not a thread pool).
- [ ] **Acquire before spawn** - the limit / semaphore is taken before `go func()`; acquiring inside the goroutine spawns all N immediately and ignores `ctx` while blocked.

### Step 8 - Idempotency and Delivery Semantics

Use skill: `go-data-access` for post-commit dispatch, the transactional outbox, and idempotent upsert. Use skill: `go-messaging-patterns` for Asynq / Kafka delivery. Use skill: `backend-idempotency` for key strategy and atomic dedup.

- [ ] **Idempotency keys** on money / notification / provisioning side effects; dedup is atomic - a unique constraint + `clause.OnConflict{DoNothing: true}` (or a `request_idempotency` table), not a read-then-write race.
- [ ] **No in-transaction dual write** - `tx.Create(...)` + `asynq.Enqueue(...)` / `kafka.Produce(...)` inside one `db.Transaction(...)` can commit the row and lose the publish, or enqueue then roll back and orphan the task. Dispatch **after** the transaction returns nil, or use a transactional outbox (`FOR UPDATE SKIP LOCKED` relay). GORM `AfterCreate` / `AfterUpdate` hooks fire inside the tx - same hazard.
- [ ] **Idempotent consumers** - Asynq / Kafka deliver at least once; handlers re-fetch state, check, and return early on replay. `asynq.TaskID(businessKey)` dedups at enqueue; the handler must still be replay-safe.
- [ ] **DLQ / archive with bounded retry** - poison tasks land in Asynq's archive (its dead set) after capped `asynq.MaxRetry(N)` (`asynq.SkipRetry` archives a permanent failure immediately), or in a Kafka DLQ topic; no infinite in-place redelivery. Archive depth is monitored - an unwatched dead set is where a systematic failure goes to be invisible.
- [ ] **Shutdown budget exceeds the longest task timeout** - `asynq.Config.ShutdownTimeout` defaults to **8 seconds** when unset, so any task with a longer `Timeout` is cut off on every rolling deploy and redelivered by lease expiry. Ordering: task `Timeout` < `ShutdownTimeout` < platform grace period. This is what turns a non-idempotent handler from a rare race into a scheduled one.

### Step 9 - Graceful Degradation, Fallbacks, and Backpressure

`ops-resiliency` already loaded in Step 4 - reuse it for fallback patterns.

- [ ] **Fallback per critical dependency** - a breaker-open / timeout path returns cached / default / partial data or fails fast with 503, rather than an unbounded wait. It logs the original failure at WARN (`slog.WarnContext`) - no silent swallow that hides degradation until it compounds.
- [ ] **Partial-failure fan-out** - an optional downstream (recommendations, enrichment) failing degrades the response, not the whole request: a separate `sync.WaitGroup` from the required `errgroup`, log-and-continue on the optional leg.
- [ ] **Load shedding / backpressure** - a full work queue sheds via a buffered channel + `select` with a `default` (429 / drop) rather than blocking the request goroutine or growing unboundedly. Channel sends also select on `<-ctx.Done()`.
- [ ] **No unbounded queueing** - an in-memory job channel / buffer has a cap; when full it rejects or blocks a bounded time, never accumulates without limit.

```go
// Bad - blocks the request goroutine when the worker pool is saturated
jobs <- job

// Good - shed load under saturation instead of stalling the caller
select {
case jobs <- job:
case <-ctx.Done():
    return ctx.Err()
default:
    c.AbortWithStatusJSON(http.StatusTooManyRequests, ErrorResponse{Error: "busy"})
    return nil
}
```

### Step 10 - Resource Exhaustion and Goroutine-Leak Prevention

`go-data-access` already loaded in Step 8 - reuse it for `database/sql` pool bounds. `go-concurrency` already loaded in Step 5 - reuse it for goroutine ownership and leak diagnosis.

- [ ] **`database/sql` pool bounded** - `SetMaxOpenConns` / `SetMaxIdleConns` / `SetConnMaxLifetime` / `SetConnMaxIdleTime` set. Budget every process that opens the pool, not just the API: `(api_replicas * api_max_open) + (worker_replicas * worker_max_open) < max_connections - reserved`, where a worker's pool is sized from its own `Concurrency`, not from its replica count. A single shared `db.New` constant serving both binaries is itself the finding. GORM / sqlx default to unbounded open conns - one slow-query storm exhausts Postgres. When the ceiling is not in the diff, read repo config; still unknown, run the check anyway and state the assumption in the finding (`verify: max_connections unknown`), never silently skip it.
- [ ] **Every goroutine ctx-bound or with a guaranteed exit** - a `go func()` doing I/O selects on `<-ctx.Done()` and has an owner (`errgroup`, `WaitGroup`, worker pool with shutdown). A leak retains the request `ctx`, `gin.Context`, and a pooled DB conn; at 100/sec sustained it compounds into unbounded growth.
- [ ] **No unbounded per-request goroutine spawn** - a handler does not launch a goroutine per row / per item without a bound. Leak signature via `/debug/pprof/goroutine`: `chan send` = receiver gone; `chan receive` = sender never closes.
- [ ] **Bounded channels and maps** - buffered channels sized deliberately; per-key maps (rate-limiter `clients`, dedup caches) swept / evicted, not grown forever.
- [ ] **No I/O under a held lock or inside `db.Transaction`** - a `sync.Mutex` held across HTTP / DB, or external I/O inside a transaction, pins the resource for the upstream tail latency and serializes the whole service.

### Step 11 - Recoverability and Crash-Safety

Use skill: `go-gin-patterns` for graceful shutdown, recovery middleware, and readiness.

Cross-aggregate consistency rule (inlined on purpose - do not re-delegate this to a separate consistency atomic; it overlaps the transaction atomic `go-data-access` already loaded in Step 8, and its one distinct rule is captured here): writes that cannot share one transaction (a charge + a separate provisioning record, a local write + a remote call) need a compensating action or a reconciliation job on partial failure - never a best-effort inline rollback that can itself fail. Prefer one transaction; when impossible, make the second step idempotent and retriable so a re-run converges.

- [ ] **Graceful shutdown** - `signal.NotifyContext(SIGTERM / SIGINT)`; `http.Server.Shutdown(ctx)` with a bounded timeout drains in-flight requests; Kafka `Close()` drains and commits; `db.Close()` last. Never a bare `os.Exit` on the serving path. **Asynq is the exception to the ordering:** `asynq.Server.Run` installs its own signal handler and drains on SIGTERM concurrently with the HTTP drain, so an explicit `Shutdown()` later in `main` is already a no-op. What matters for Asynq is that `Config.ShutdownTimeout` (default **8s**) exceeds the longest task `Timeout` and fits inside the pod's grace period - check the budget, not the call order. Use `asynq.Server.Start` + `Shutdown` when the drain must be sequenced with anything else.
- [ ] **Panic safety** - Gin `Recovery()` middleware on the request path, AND a deferred `recover()` (or `sentry.Recover()`) at every goroutine boundary outside the request. A panic in a spawned goroutine crashes the whole process; Gin's recovery does not cover it.
- [ ] **Crash-safe side effects** - a multi-step side effect interrupted mid-way leaves recoverable state (outbox pending, an idempotency-guarded re-run), not a half-applied change. Post-commit dispatch a crash can drop is acceptable only if the operation is re-drivable.
- [ ] **Readiness reflects dependencies** - `/readyz` gates on own-pod dependencies (DB pool `PingContext`, Asynq client) so an unready replica sheds rather than accepts traffic it cannot serve; `/livez` stays dependency-free (probe-wiring depth -> `task-go-review-observability`).
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes (use skill: `go-migration-safety`, `ops-backward-compatibility`).

### Step 11.5 - Verify Findings

Assign each draft finding its label first (High -> `[Must]`, Medium -> `[Recommend]`, escalating per the severity rules below), since `review-finding-verify` takes labelled findings and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - never re-derive one from the severity tier afterwards. Carry its provenance annotation onto the finding heading and its tally into the Summary's `Findings verified` slot. Subagent runs skip this; whole-service sweeps run confirmation only, per the Depth clause. A subagent still knows which findings sit on code the diff did not add - carry that as `_(pre-existing)_` or `_(pre-existing; newly load-bearing)_` on the finding heading so the parent's verify pass starts from it rather than re-deriving it.

**Attribution when the diff changes the load, not the code.** `Pre-existing (newly reachable)` also covers an unchanged shared resource the diff makes newly load-bearing - a pool whose holds now span a broker round trip, a breaker whose dependency the diff put on the request path. No new caller is required; the character of the load changed. Retain the label rather than de-escalating.

### Step 12 - Write Report

Standalone only - subagent runs return the Output Format to the parent, which writes the single merged report. At `deep`, a subagent returns the Failure-Mode and Blast-Radius Map with its findings so the parent can preserve it as its own section.

The round was resolved in Step 3; pass it through. The handle's `prior_checkpoint` is keyed to the general review report - do not use it here. On round 2+, note in the Summary which prior findings are still open; this lens has no reconciliation table, so the prior report remains the audit trail and is overwritten only when the round genuinely advanced.

Use skill: `review-report-writer` with `report_type: review-reliability` and every required input: `report_body`, `branch`, `base_ref` / `head_ref`, `base_sha` / `head_sha` from Step 3 (whole-service sweep: all five resolved per the Depth clause), `stack: go-gin`, `scope: +rel`, `depth` as resolved from the Depth table, `mode: full`, and the `round` / `prior_head_sha` resolved above. Write before ending; print confirmation.

## Self-Check

Mark a line N/A with its reason when the diff has no matching surface (no messaging, no goroutine fan-out), or when the invocation mode makes it inapplicable (subagent, whole-service sweep). A row whose subject is absent entirely - no retries anywhere - is N/A for its checks and, when the absence is itself a gap, a finding.

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Go 1.25+ / Gin (or pre-confirmed stack accepted from parent); data-access and messaging recorded
- [ ] Step 3: precondition check ran (or handle received); diff + log read once; SHAs captured, or supplied by the parent, or resolved per the sweep clause
- [ ] Step 4: external clients, composing services, goroutine launch sites, listeners, side-effecting flows, pool / breaker / shutdown config read; `failure-propagation-analysis` used for blast radius
- [ ] Step 5: `ctx` propagation, per-call deadline, `http.Client` timeout + transport, timeout budget, `ctx.Err()` honored
- [ ] Step 6: `ops-resiliency` consulted; backoff + jitter, capped, transient / idempotent-only, retry budget checked
- [ ] Step 7: `go-concurrency` consulted; `gobreaker` per dependency, bounded fan-out (`SetLimit` / `semaphore`), bulkhead, acquire-before-spawn
- [ ] Step 8: `backend-idempotency` + `go-data-access` + `go-messaging-patterns` consulted; idempotency keys, no in-tx dual write, idempotent consumers, DLQ checked
- [ ] Step 9: fallback per critical dependency that logs; partial-failure fan-out; load shedding / channel backpressure verified
- [ ] Step 10: `database/sql` pool bounded; every goroutine ctx-bound / owned; no unbounded spawn or channels; no I/O under lock or in tx
- [ ] Step 11: graceful shutdown, panic recovery at goroutine boundaries, crash-safety, readiness, migration rollout checked; cross-aggregate consistency (compensating action / reconciliation on partial failure) verified
- [ ] Step 11.5: findings labelled before verify, verify's labels and annotations carried onto the headings verbatim, tally in the Summary (subagent: skipped; sweep: confirmation only)
- [ ] Step 12: standalone: report written via `review-report-writer` with the round resolved from `review-reliability-<branch>.md`, confirmation printed; subagent: Output Format returned, no file written
- [ ] Every finding names the failure mode and blast radius, never just the missing pattern
- [ ] Checks that passed recorded under `### Verified Clean`, not left implicit
- [ ] Depth honored: `standard` ran all; `deep` filled the Failure-Mode and Blast-Radius Map
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unbounded failure path, a data-loss / corruption risk under a plausible failure, **or a bounded failure whose blast radius is the whole service** (missing `context` deadline on a hot external call, `http.DefaultClient` with no timeout, uncapped retry, non-idempotent retry, in-tx dual write, unbounded per-request goroutine spawn, unrecovered panic in a spawned goroutine, an optional dependency wired so its failure fails every request, a probe that removes every replica on one shared dependency); Medium = failure is bounded and contained to its own path but recovery or containment is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, missing timeout / retry budget on a chained path, consumer not idempotent, unbounded channel on a warm path); Low = hardening with no immediate failure path (missing bulkhead, fail-fast where stale data would serve).

Labels: High -> `[Must]`; Low -> `[Recommend]`; Medium -> `[Recommend]`, escalated to `[Must]` only when **all three** hold: the fix that fully resolves the failure mode is confined to one file, it needs no product or architectural decision (no fallback policy to choose, no new component), and the defect sits on a money, auth, or data-integrity path. Judge by the fix that resolves the failure mode, not the cheapest partial one. When any leg is arguable, leave it `[Recommend]` and say why in the finding - an escalation that two reviewers would split on is not a merge blocker.

**One finding per root cause, where the unit is the edit that fixes it.** A defect satisfying several checklist items (an unbounded fan-out hits Steps 7 and 10) is one finding at the strongest severity. Several defects in one construct that one rewrite resolves - a detached goroutine that is also unbounded and also unrecovered - are likewise one finding; enumerate them (a)/(b)/(c) inside `Failure Mode` and `Blast Radius`. Two defects at one call site that need **separate** fixes, or that survive each other's fix, are two findings. Two instances of one missing policy across different dependencies are one finding when the fix is a shared module, and separate findings when each site must be edited on its own terms.

```markdown
## Go Reliability Review Summary

- **Stack Detected:** Go <version> / Gin <version>
- **Data Access:** GORM <version> | sqlx <version> | database/sql | mixed
- **Messaging:** Asynq | Kafka | none
- **Resilience Libraries:** every one detected, comma-separated with versions, each marked `(in use)` or `(declared, unused)` - a dependency present in `go.mod` and imported nowhere is the most decision-relevant state this field can report; `none detected` only when there are none
- **Review shape:** diff review of `<base>...<head>` | whole-service sweep at `HEAD` on `<branch>` _(sweep only - explains why base_sha equals head_sha)_
- **Depth:** standard | deep
- **Overall:** Resilient | Gaps Found - <N> High / <N> Medium / <N> Low
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(parenthetical omitted when K is 0; whole line omitted on subagent runs; sweep reports `-` for reattributed)_

## Findings

### High Impact

#### 1. [Label] file:line - <short title> _(provenance annotation, when Step 11.5 assigned one)_

- **Issue:** [name the gap: `http.DefaultClient` with no timeout, missing `context.WithTimeout`, uncapped retry, in-tx `asynq.Enqueue`, unbounded goroutine fan-out, unrecovered panic in a goroutine, etc.]

- **Failure Mode:** [what fails and how: "payment-gateway stall blocks the request goroutine indefinitely; each retained request pins a pooled DB conn"]

- **Blast Radius:** [what else is affected: "SetMaxOpenConns(25) exhausts under sustained traffic; every endpoint sharing the pool returns 503"]

- **Fix:** [`http.Client{Timeout}` + `gobreaker`, `context.WithTimeout`, `errgroup.SetLimit`, outbox, idempotency key, `recover()` at the goroutine boundary, etc.]

- **Assumption:** [only when the finding rests on something the repo cannot settle - `verify: max_connections unknown`, `assumes no out-of-repo env source`]

#### 2. [Label] file:line - <short title>

[Same block, numbering continues across tiers]

### Medium Impact

[Same blocks]

### Low Impact / Quick Wins

[Same blocks]

Omit empty sections. Blank lines separate the field lines - consecutive bare `**Label:** value` lines collapse into one paragraph when the report renders, which is how a five-field finding becomes one run-on sentence.

## Recommendations

[Structural resilience improvements not tied to a single finding]

## Verified Clean

Checklist rows that were evaluated and passed, with their evidence - pool bounds correct at `N x M < ceiling`, graceful shutdown complete, no in-transaction dual write, `ctx` propagated end to end. On an already-resilient service this is most of the review's value, and `Overall: Resilient` alone cannot carry it. Rows that went **N/A** belong here too, marked `N/A - <reason>`: "no fan-out exists" and "checked and correct" are different facts, and a reader needs both. Top-level so a parent merging by section heading cannot drop it.

## Out of Lens

Defects noticed while reading the reliability surface that another lens owns - a correctness bug, a leaked secret, a missing index. Each with its `file:line` and the owning lens, so it can be routed rather than dropped. Omit when there are none.

## Next Steps

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: platform] - [action]
3. **[Implement]** [Recommend] file:line - [action]

Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra). Order Must > Recommend. One row per finding; when several findings share one edit, say so on the row rather than repeating the fix. Omit if none.

## Failure-Mode and Blast-Radius Map

_(`deep` only - omit at `standard`.)_

| Dependency (new / changed) | Down or slow | Shared resource on the propagation path | Loop-breaker |
| -------------------------- | ------------ | --------------------------------------- | ------------ |
| <name, and what the diff did to it> | <what fails, and how far it gets> | <the `database/sql` pool, a worker pool, a channel, the broker, the Service endpoint list> | Present (<what contains it>) \| Partial (<what is missing>) \| **Missing** (<what to add>) |

Follow the table with any **amplification loop** found - a cycle where the failure's own consequence feeds the cause (probe failure removing replicas, which raises load on the rest, which fails more probes) - naming the one change that breaks the cycle.

```

## Avoid

- Reporting a missing pattern without the failure mode ("add a timeout" vs "`http.DefaultClient` with no timeout pins the goroutine and exhausts the DB pool")
- `http.DefaultClient` / `http.Get` on a downstream call (no timeout)
- Swapping `context.Background()` / `context.TODO()` in mid-request (severs the deadline and cancellation)
- Recommending retries on non-idempotent ops without an idempotency key
- Recommending a `sony/gobreaker` breaker with no monitoring
- `go func()` without an owner, a `<-ctx.Done()` arm, or a bound (`errgroup.SetLimit` / `semaphore`)
- Treating Asynq / Kafka redelivery as a substitute for consumer idempotency
- Approving an in-transaction `tx.Create` + `asynq.Enqueue` / `kafka.Produce` dual write
- Ignoring a panic path in a spawned goroutine (crashes the process; Gin `Recovery()` does not cover it)
- Overlapping into perf (throughput tuning) or observability (metric / log wiring) - name the failure-survival gap
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
