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

# Go Reliability Review

Go-aware reliability review naming `context.Context` deadlines and cancellation, `sony/gobreaker`, `cenkalti/backoff`, `errgroup` / `semaphore.Weighted` structured concurrency, goroutine-leak and channel-backpressure control, `database/sql` pool bounds, and `http.Server.Shutdown`. Reliability = behavior under failure and saturation: what happens when a dependency is slow or down, load spikes, or a process crashes mid-operation. Every finding names the failure mode and blast radius, with concrete fixes for Go 1.25+ / Gin.

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

**Whole-service sweep** (resilience-debt pass with no feature branch, and the mode a "sweep before peak season" request asks for). When Step 3 fails fast on trunk, do not stop - skip the diff gate, keep Step 3's round paragraph (keyed to this lens's checkpoint on the trunk), and run Steps 4-14 repo-wide at `HEAD` (Step 12 confirmation-only, Step 13 on round 2+). Step 4's categories are read in full rather than per changed file, and every diff-worded rule downstream (the ripple clause, Step 4's `ops-resiliency` load gate) reads against the whole surface instead. Findings cite current code and are pre-existing by construction; a defect that is dormant today (an unreachable code path, a client no caller uses) keeps its severity, with the reachability stated under `Assumption`. Three things the sweep changes:

- **Refs.** The precondition emits no handle on a fail-fast, so resolve the writer's inputs directly: `branch` = `base_ref` = `head_ref` = the trunk branch name, `base_sha` = `head_sha` = the full `git rev-parse <trunk>` - when the current branch is not the trunk, stop and ask the user to check out the trunk or name a feature branch; `scope` / `stack` as on a diff review. The fail-fast also returns no `prior_checkpoint`: read the frontmatter of `review-reliability-<sanitized trunk>.md` in the repo root yourself, with `review-precondition-check`'s filename and validity rules, and use it as `report_path` / `prior_checkpoint` for Step 3's round paragraph and Step 13; Step 13's `diff` / `name_status` then span `<prior_head_sha>...<trunk sha>` with `<prior_head_sha>` as the reconciler's `base_ref`, overriding its full-range inputs: a sweep has no base, so the commits since the prior sweep separate touched files from untouched ones.
- **Verify attribution.** Run `review-finding-verify` for confirmation only - its Step 1, against the code at `HEAD`, with an empty `diff`. **Skip its attribution and de-escalation.** With no diff, every finding attributes `Pre-existing` and every `[Must]` de-escalates, which would empty a debt sweep of the blockers it exists to surface. Labels come from the tier; every heading carries `_(pre-existing)_` plus any annotation the confirmation returned. Tally `<N> confirmed, - reattributed, <U> unverified, <K> dropped`.
- **Depth.** A sweep defaults to `deep`: the Failure-Mode and Blast-Radius Map is the per-dependency loop-breaker table a standing-debt pass is asking for. Pass `standard` explicitly to suppress it.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-reliability` | Current branch vs base; on trunk, runs the whole-service sweep above |
| `/task-go-review-reliability <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-reliability pr-<N>` | PR head fetched into local branch (user runs fetch) |

Append `deep` to request the deep pass (e.g. `/task-go-review-reliability <branch> deep`).

**Subagent runs** (e.g. spawned by `task-go-review`). The parent passes the precondition handle, `base_ref` / `head_ref`, `base_sha` / `head_sha`, the pre-read diff and commit log, depth, the pre-confirmed stack, the data-access mix, messaging, and the acceptance criteria when a requirement source resolved. Steps 2 and 3 accept those instead of re-running - never re-run git. Steps 12 and 13 are skipped (the parent verifies and reconciles the merged set once): labels come from the tier, a finding whose cited line the diff did not add carries `_(pre-existing)_`, plus `_(unverified: <reason>)_` when the evidence rule assigned it, and no `newly reachable via` (the parent's verify adds that) so the parent's verify pass starts from it, and the `Findings verified` and `Round` lines are omitted. Step 14 returns the whole Output Format - Summary (`Depth` as the parent passed it), Findings, Out of Lens, Recommendations, Verified Clean, Next Steps, the `deep` Map - not the findings alone, and writes nothing.

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format, several with their own `## Findings`. They are rule sets here, not deliverables: emit this skill's Output Format only. Their blockquoted `Load stack-detect first` lines are satisfied by Step 2. Where a check below and a loaded atomic disagree, the sentence names which wins.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. A subagent loads it too, unless the spawning prompt inlined its Rules.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a parent and skip detection. If not Go, stop and route the user to `/task-code-review-reliability`.

Versions come from `go.mod` - the Go version from the `go` directive, Gin / GORM / sqlx from the `require` lines - and override any version a `## Tech Stack` line declared (this step's one departure from `stack-detect`'s instruction-file precedence). `Data Access` is GORM / sqlx / database/sql, or `mixed - GORM <v> + sqlx <v>` when both are required. `Messaging` is `Asynq`, `Kafka`, `Asynq + Kafka`, or `none`, from `go.mod`: `hibiken/asynq` for Asynq; `twmb/franz-go`, `IBM/sarama` (`Shopify/sarama` before v1.40.0), `segmentio/kafka-go` or `confluentinc/confluent-kafka-go` for Kafka.

### Step 3 - Resolve the Diff and Round

Standalone only - skip the whole step, SHA capture included, when running as a subagent with handle + artifacts pre-passed.

Use skill: `review-precondition-check` with `report_type: review-reliability`. A trunk fail-fast switches to the whole-service sweep under **Depth**; any other fail-fast: surface verbatim and stop. Read `git diff <base>...<head>`, `git diff --name-status <base>...<head>` and `git log <base>..<head>` once and reuse. Capture `base_sha = git rev-parse <base_ref>` and `head_sha = git rev-parse <head_ref>` (full SHAs). The writer's `branch` is the handle's `head_short_name`.

**Resolve the round from the handle, before any surface is read.** No `prior_checkpoint`, or `prior_checkpoint: legacy` -> `round: 1`. Valid -> `round = prior_checkpoint.round + 1`, `prior_head_sha = prior_checkpoint.head_sha`. **When `prior_checkpoint.head_sha` equals the current `head_sha` and no deeper depth than `prior_checkpoint.depth` was requested, print `No new commits on <branch> since prior reliability review at <sha_short>. Prior report unchanged.` and stop** - do not re-review and do not overwrite. On a genuine round 2+, re-review the full range; Step 13 reconciles the prior findings.

### Step 4 - Read the Reliability Surface

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (a small diff ripples: a new service method calling an unchanged untimed `http.Client` is a new failure path at the call site). Read the full `go.mod` here (not just diff adds) to fill the Summary's Resilience Libraries field; a library is `(in use)` when any file in the tree imports it, `(declared, unused)` otherwise.

- External clients: `http.Client` construction / shared clients, gRPC dials, third-party SDKs - `Timeout`, `Transport` tuning, breaker, retry
- `service` methods composing multiple downstream calls - timeout budget, `errgroup` fan-out, partial-failure handling
- Goroutine launch sites: `go func()`, `errgroup.Go`, `wg.Go`, worker pools, channel pipelines - ownership, `<-ctx.Done()`, bounding
- Asynq / Kafka producers + consumers - idempotency, retry / `MaxRetry`, DLQ, post-commit enqueue
- Side-effecting flows (payment, notification, provisioning) - idempotency keys, outbox vs dual write
- Config / wiring: `cmd/api/main.go` / `internal/db/db.go` for `database/sql` pool bounds, `gobreaker` / `backoff` config, `http.Transport` setup, graceful-shutdown and recovery middleware; the deploy manifest for replica counts and the DB ceiling
- Dependency adds: `sony/gobreaker`, `cenkalti/backoff`, `golang.org/x/sync`, `golang.org/x/time`

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns - load it when the surface includes an external client, a fanning-out service, or breaker / retry / timeout config; skip it only when **none** of those appear, which on a mixed surface means load it. Use skill: `failure-propagation-analysis` to trace how a failure at each new / changed dependency propagates through shared resources (the `database/sql` pool, a worker pool, a channel, the broker) - it is an analysis tool whose output feeds the `Blast Radius` field and, at `deep`, the Map; its own template is not emitted.

**Config the code reads but the deployment does not set** is in scope here: a base URL, DSN, or credential introduced in the diff and absent from the deploy manifest fails every call at runtime rather than at boot. Check the manifest for each new setting the wiring reads, and say so when the manifest is not in the repo.

**Defects outside the diff or the lens.** A defect on a line the diff did not add: in this lens and made newly reachable or load-bearing by the diff -> a finding (Step 12 attributes it); in this lens and untouched by the diff -> a finding at its tier label with `_(pre-existing)_` (Step 12 de-escalates it to `[Recommend]`; on a subagent run the parent's verify does), at most the three most consequential on a diff review (a sweep publishes every one), the rest one line each under `## Out of Lens`; owned by another lens (a correctness bug, a leaked secret, a missing index) -> `## Out of Lens` with `file:line` and the owning lens. Out of Lens items never enter Next Steps. A finding that spans two files (a pool constant shared by two `main`s) anchors on the line that executes the failure and names the other file in `Issue`.

Gating skips atomic loads, never checklist rows. Every checklist row below runs on this skill's own text regardless of which atomics loaded; a row goes N/A only when the diff has no matching surface (the Self-Check rule).

### Step 5 - Timeouts and Deadlines (context.Context)

Use skill: `go-concurrency` for context propagation and per-goroutine timeouts.

- [ ] **`ctx` propagated end to end** - every downstream call (DB, HTTP, gRPC, Asynq enqueue) takes the request `ctx` (`c.Request.Context()`), threaded handler -> service -> repository. No `context.Background()` / `context.TODO()` swapped in mid-request (severs the deadline and cancellation).
- [ ] **Deadline on every outbound call** - `context.WithTimeout(ctx, d)` with `defer cancel()` on external I/O; `db.WithContext(ctx)` / sqlx `*Context` so a slow query is cancellable. A call with no deadline blocks until the socket or DB decides.
- [ ] **`http.Client` bounded** - shared package-level client with `Timeout` set AND a tuned `Transport` (`MaxIdleConns`, `MaxIdleConnsPerHost`, `IdleConnTimeout`); never `http.DefaultClient` / `http.Get` - no timeout, so a hung upstream pins the goroutine forever.
- [ ] **Timeout budget on chained / fan-out calls** - a handler fanning out to N downstreams caps total time; a slow first call leaves budget for the rest or fails fast (`context.WithDeadline` derived once, passed down). A missing or exceeded budget on a chained path is High, per `ops-resiliency`.
- [ ] **`ctx.Err()` honored** - long loops and blocking receives check `<-ctx.Done()` / `ctx.Err()` and return; no work continues on a cancelled request.

```go
// Bad - no timeout; a hung upstream pins this goroutine and its request ctx forever
resp, err := http.Get(url)

// Good - shared client with deadline + bounded transport, carrying the request ctx
req, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
resp, err := s.client.Do(req) // s.client = &http.Client{Timeout: 3*time.Second, Transport: tuned}
```

### Step 6 - Retries

- [ ] **Bounded backoff with jitter** - `cenkalti/backoff` (`NewExponentialBackOff` adds jitter) or a manual capped loop; never an uncapped `for` retry. On v4: `WithMaxRetries` + `backoff.WithContext(b, ctx)` so retries stop on cancellation. On v5 both wrappers are gone: `backoff.Retry(ctx, op, backoff.WithBackOff(b), backoff.WithMaxTries(n))`, with ctx cancellation built in. Read the major version from `go.mod`.
- [ ] **Transient + idempotent only** - retry 500 / 502 / 503 / 504, timeouts, `context.DeadlineExceeded`, connection resets, and 429 / 408 / 425, classified via `errors.Is`; a `Retry-After` header replaces the computed backoff, and a value beyond the remaining deadline means abandon, not wait; no other 4xx except, per `ops-resiliency`, a 409 carrying `Retry-After`, a 401 after one token refresh, and 412 / 423 after re-reading the state; never a non-idempotent write without an idempotency key (Step 8).
- [ ] **Retry amplification bounded** - chained services do not each retry independently (N x M call blowup); a per-request retry budget is decremented and passed downstream.
- [ ] **Non-retryable errors escape** - wrap them with `backoff.Permanent(err)` so the loop exits immediately instead of burning the budget.

### Step 7 - Circuit Breakers and Bounded Concurrency

- [ ] **Breaker per external dependency** - `sony/gobreaker` with explicit `MaxRequests`, `Interval`, `Timeout`, and a `ReadyToTrip` threshold; one breaker per dependency, its state metered (visibility gap -> `task-go-review-observability`). A shared or unmonitored breaker counts as missing.
- [ ] **Bounded fan-out** - `errgroup.WithContext` + `g.SetLimit(N)` or `golang.org/x/sync/semaphore.Weighted`; unbounded per-request goroutine fan-out exhausts the scheduler, FDs, and the pool. N/A only when the fan-out is a fixed set of legs rather than one per item.
- [ ] **Optional legs separated from required ones** - `errgroup` cancels siblings on first error, so an optional downstream inside it fails the whole request. Use a separate `sync.WaitGroup` for optional legs, waited on every return path. Checked independently of the bound above: a fixed four-leg fan-out needs no `SetLimit` and can still be fatally mixed.
- [ ] **Bulkhead isolation** - a worker pool or semaphore per downstream so one slow dependency cannot consume the concurrency budget others share (a Go bulkhead is a bounded semaphore / dedicated pool, not a thread pool).
- [ ] **Acquire before spawn** - the limit / semaphore is taken before `go func()`; acquiring inside the goroutine spawns all N immediately and ignores `ctx` while blocked.

### Step 8 - Idempotency and Delivery Semantics

Use skill: `go-data-access` for post-commit dispatch, the transactional outbox, and idempotent upsert. Use skill: `go-messaging-patterns` for Asynq / Kafka delivery. Use skill: `backend-idempotency` for key strategy and atomic dedup.

- [ ] **Idempotency keys** on money / notification / provisioning side effects; dedup is atomic - a unique constraint + `clause.OnConflict{DoNothing: true}` (or a `request_idempotency` table), not a read-then-write race.
- [ ] **No in-transaction dual write** - `tx.Create(...)` + `asynq.Enqueue(...)` / `kafka.Produce(...)` inside one `db.Transaction(...)` can commit the row and lose the publish, or enqueue then roll back and orphan the task. Dispatch **after** the transaction returns nil, or use a transactional outbox (`FOR UPDATE SKIP LOCKED` relay). GORM `AfterCreate` / `AfterUpdate` hooks fire inside the tx - same hazard.
- [ ] **Idempotent consumers** - Asynq / Kafka deliver at least once; handlers re-fetch state, check, and return early on replay. `asynq.TaskID(businessKey)` dedups at enqueue; the handler must still be replay-safe. For retries and consumers alike: High when the duplicated or lost effect is financial or irreversible (charge, email, webhook), Medium when it is a recoverable database write, per `backend-idempotency`.
- [ ] **DLQ / archive with bounded retry** - poison tasks land in Asynq's archive (its dead set) after capped `asynq.MaxRetry(N)` (`asynq.SkipRetry` archives a permanent failure immediately), or in a Kafka DLQ topic; no infinite in-place redelivery. Archive depth is monitored - an unwatched dead set is where a systematic failure goes to be invisible.
- [ ] **Shutdown budget exceeds the longest task timeout** - `asynq.Config.ShutdownTimeout` defaults to **8 seconds** when unset, so any task with a longer `Timeout` is cut off on every rolling deploy and requeued to pending by `Shutdown` (after a SIGKILL, recovered on lease expiry as a counted retry). Ordering: task `Timeout` < `ShutdownTimeout` < platform grace period. This is what turns a non-idempotent handler from a rare race into a scheduled one.

### Step 9 - Graceful Degradation, Fallbacks, and Backpressure

- [ ] **Fallback per critical dependency** - a breaker-open / timeout path returns cached / default / partial data or fails fast with 503, rather than an unbounded wait. It logs the original failure at WARN (`slog.WarnContext`) - no silent swallow that hides degradation until it compounds.
- [ ] **Partial-failure fan-out** - an optional downstream (recommendations, enrichment) failing degrades the response, not the whole request: a separate `sync.WaitGroup` from the required `errgroup`, log-and-continue on the optional leg.
- [ ] **Load shedding / backpressure** - a full work queue sheds via a buffered channel + `select` with a `default` (reject) rather than blocking the request goroutine; channel sends also select on `<-ctx.Done()`. The service returns a sentinel and the handler maps it to 429 - services never write responses (`go-gin-patterns`).
- [ ] **No unbounded queueing** - a Go channel's capacity is fixed at `make`; unbounded queueing is a slice- or list-backed job buffer, or a goroutine parked per pending send. Each has a cap; when full it rejects or blocks a bounded time.

```go
// Bad - blocks the request goroutine when the worker pool is saturated
jobs <- job

// Good - shed load under saturation; the handler maps ErrBusy to 429
select {
case jobs <- job:
    return nil
case <-ctx.Done():
    return ctx.Err()
default:
    return ErrBusy
}
```

### Step 10 - Resource Exhaustion and Goroutine-Leak Prevention

- [ ] **`database/sql` pool bounded** - `SetMaxOpenConns` / `SetMaxIdleConns` / `SetConnMaxLifetime` / `SetConnMaxIdleTime` set on the `*sql.DB` (GORM: `sqlDB, err := db.DB()`, error checked; sqlx and `database/sql` call them directly; the `database/sql` default is unlimited - one slow-query storm exhausts Postgres). Budget every process that opens the pool, per `go-data-access`: `sum over binaries of ((replicas + maxSurge) * SetMaxOpenConns) < max_connections - reserved`, a worker's pool sized from its own `Concurrency`, surge 25% and reserved 10 `(assumed)` when the manifest or DB config is absent. On `mixed`, sqlx wrapping GORM's pool (`sqlx.NewDb(sqlDB, driver)`) is one pool configured once; an sqlx pool opened separately is a second pool whose `SetMaxOpenConns` adds to that binary's term. A single shared `db.New` constant serving both binaries is itself the finding. When the ceiling is not in the repo, run the check anyway and state the assumption (`verify: max_connections unknown`), never silently skip it.
- [ ] **Every goroutine ctx-bound or with a guaranteed exit** - a `go func()` doing I/O selects on `<-ctx.Done()` and has an owner (`errgroup`, `WaitGroup`, worker pool with shutdown). A leak retains the request `ctx`, `gin.Context`, and a pooled DB conn; at 100/sec sustained it compounds into unbounded growth.
- [ ] **No unbounded per-request goroutine spawn** - a handler does not launch a goroutine per row / per item without a bound. Leak signature via `/debug/pprof/goroutine`: `chan send` = receiver exited, or alive and never draining (apply a backpressure policy); `chan receive` = sender never closes.
- [ ] **Bounded buffers and maps** - buffered channels sized deliberately; per-key maps (rate-limiter `clients`, dedup caches) swept / evicted, not grown forever.
- [ ] **No I/O under a held lock or inside `db.Transaction`** - a `sync.Mutex` held across HTTP / DB, or external I/O inside a transaction, pins the resource for the upstream tail latency and serializes the whole service.

### Step 11 - Recoverability and Crash-Safety

Use skill: `go-gin-patterns` for graceful shutdown, recovery middleware, and readiness.

Cross-aggregate consistency rule (inlined on purpose - do not re-delegate this to a separate consistency atomic; it overlaps the transaction atomic `go-data-access` already loaded in Step 8, and its one distinct rule is captured here): writes that cannot share one transaction (a charge + a separate provisioning record, a local write + a remote call) need a compensating action or a reconciliation job on partial failure - never a best-effort inline rollback that can itself fail. Prefer one transaction; when impossible, make the second step idempotent and retriable so a re-run converges.

- [ ] **Graceful shutdown** - `signal.NotifyContext(SIGTERM / SIGINT)`; `http.Server.Shutdown(ctx)` with a bounded timeout drains in-flight requests; Kafka: stop polling, finish in-flight records, `Flush(sctx)`, `CommitUncommittedOffsets(sctx)` with `sctx` a fresh `context.WithTimeout(context.Background(), d)` - the signal ctx is already cancelled and both return at once on it; nothing commits on `Close()` under `kgo.DisableAutoCommit()` - then `Close()` (`CloseAllowingRebalance()` only under `BlockRebalanceOnPoll`); another Kafka client follows the same order (stop fetching, finish in-flight records, flush, commit synchronously on a fresh bounded ctx, close) in its own API; the DB pool closed last (`sqlDB.Close()` - `*gorm.DB` has no `Close`). Never a bare `os.Exit` on the serving path. **Asynq is the exception to the ordering:** `asynq.Server.Run` installs its own signal handler and drains on SIGTERM concurrently with the HTTP drain, so an explicit `Shutdown()` later in `main` is already a no-op. What matters for Asynq is that `Config.ShutdownTimeout` (default **8s**) exceeds the longest task `Timeout` and fits inside the pod's grace period - check the budget, not the call order. Use `asynq.Server.Start` + `Shutdown` when the drain must be sequenced with anything else.
- [ ] **Panic safety** - Gin `Recovery()` middleware on the request path, AND a deferred `recover()` (or `sentry.Recover()`) at every goroutine boundary outside the request. A panic in a spawned goroutine crashes the whole process; Gin's recovery does not cover it.
- [ ] **Crash-safe side effects** - a multi-step side effect interrupted mid-way leaves recoverable state (outbox pending, an idempotency-guarded re-run), not a half-applied change. Post-commit dispatch a crash can drop is acceptable only if the operation is re-drivable.
- [ ] **Readiness on pod-local state only** - the readiness probe gates on a draining flag and initialised pools, so an unready replica sheds traffic it cannot serve; a readiness check that pings a shared dependency (DB, Redis) removes every replica when that dependency blips and is the High finding in this lens - this wins over `go-gin-patterns`' `Ready` example. Liveness stays dependency-free (probe-wiring depth -> `task-go-review-observability`).
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes (use skill: `go-migration-safety`, `ops-backward-compatibility`); a migration taking `ACCESS EXCLUSIVE` or `SHARE ROW EXCLUSIVE` on a hot table without `SET LOCAL lock_timeout` at the top of the file (up and down) is High, per `go-migration-safety`.

### Step 12 - Verify Findings

Assign each draft finding its label first (High -> `[Must]`, Medium / Low -> `[Recommend]`, escalating per the severity rules below), since `review-finding-verify` takes labelled findings and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - never re-derive one from the severity tier afterwards. Carry its `Annotation` column verbatim onto the finding heading (`_(pre-existing)_`, `_(pre-existing; newly reachable via <file:line>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`) and its tally into the Summary's `Findings verified` slot. The verify table is working material; only the tally and the surviving rows' labels and annotations reach the report. Subagent runs skip this step entirely (see Invocation); whole-service sweeps run confirmation only, per the Depth clause.

**Attribution when the diff changes the load, not the code.** `Pre-existing (newly reachable)` also covers an unchanged shared resource the diff makes newly load-bearing - a pool whose holds now span a broker round trip, a breaker whose dependency the diff put on the request path. No new caller is required; the character of the load changed. Cite the diff line that changed the load as the `via <file:line>` site, and retain the label rather than de-escalating.

### Step 13 - Reconcile Prior Findings (round 2+, standalone)

Skip on round 1. Otherwise read the prior report at the handle's `report_path` and project its findings into the reconciler's shape: `## High-Impact Findings` holding one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, label and `file:line` copied from the `#### <n>. [Label] file:line - <title>` heading, annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` becomes `_(pre-existing)_ _(newly reachable via X)_`). Use skill: `review-prior-findings-reconcile` with `prior_report` (the projection), `diff`, `name_status`, `head_sha`, and `head_files` (`git ls-tree -r --name-only <head_sha>`). Insert its table under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows re-enter `## Findings` under the impact heading they were last published under (this round's tier when re-drafted), with the label and every annotation group they were last published with plus `_(carried from round <N>)_` (N = the round that first raised it, written once) on the heading; when this round re-drafted the same defect at the same site, publish only the re-drafted finding with that annotation appended. The table keeps the prior label and line verbatim.

### Step 14 - Write Report

Standalone only - subagent runs return the Output Format to the parent, which writes the single merged report.

Use skill: `review-report-writer` with `report_type: review-reliability` and every required input: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3 (whole-service sweep: all five resolved per the Depth clause), `stack: go-gin`, `scope: +rel`, `depth` as resolved from the Depth table, `mode: full`, and the `round` / `prior_head_sha` resolved in Step 3. Write before ending; print confirmation.

## Self-Check

Mark a line N/A with its reason when the diff has no matching surface (no messaging, no goroutine fan-out), or when the invocation mode makes it inapplicable (subagent, whole-service sweep, round 1). A row whose subject is absent entirely - no retries anywhere - is N/A for its checks and, when the absence is itself a gap, a finding.

- [ ] Step 1: `behavioral-principles` loaded, or rules inlined in the spawning prompt
- [ ] Step 2: stack confirmed Go 1.25+ / Gin (or accepted from parent); versions from `go.mod`; data access and messaging recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-reliability` (or handle received; or trunk fail-fast routed to the sweep); diff, name-status and log read once; `base_sha` / `head_sha` captured; round resolved from the handle (sweep: from the self-read checkpoint); same-SHA no-op honoured; approval obtained when `head_matches_current` was false
- [ ] Step 4: surface categories read, full `go.mod` and manifest consulted; `ops-resiliency` loaded per the gate; `failure-propagation-analysis` used for blast radius; defects outside the diff or lens routed per the Step 4 rule
- [ ] Step 5: `ctx` propagation, per-call deadline, `http.Client` timeout + transport, chained budget, `ctx.Err()` honored
- [ ] Step 6: backoff + jitter capped per the pinned `backoff` major, transient-only status set, retry budget, `Permanent` escape
- [ ] Step 7: `gobreaker` per dependency, bounded fan-out, optional legs separated, bulkhead, acquire-before-spawn
- [ ] Step 8: `backend-idempotency` + `go-data-access` + `go-messaging-patterns` applied; idempotency keys, no in-tx dual write, idempotent consumers tiered by effect, DLQ, `ShutdownTimeout` budget
- [ ] Step 9: fallback per critical dependency that logs; partial-failure fan-out; shedding via sentinel; bounded buffers
- [ ] Step 10: pool budget per `go-data-access` with assumptions stated; every goroutine owned; leak signatures read; no I/O under lock or in tx
- [ ] Step 11: graceful shutdown sequence, panic recovery at goroutine boundaries, crash-safety, pod-local readiness, migration rollout; cross-aggregate consistency verified
- [ ] Step 12 (standalone): findings labelled before verify; labels and annotations carried verbatim; tally in the Summary (sweep: confirmation only)
- [ ] Step 13 (round 2+): prior report projected and reconciled with `head_sha`; table inserted; `Still open` / `Needs re-check` rows carried into Findings
- [ ] Step 14 (standalone): report written via `review-report-writer` with all checkpoint fields; confirmation printed. Subagent: Output Format returned, no file written
- [ ] Every finding names the failure mode and blast radius; passed and N/A rows recorded under `## Verified Clean`; `deep` filled the Failure-Mode and Blast-Radius Map
- [ ] Next Steps tagged and ordered Must > Recommend (omit if none)

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unbounded failure path, a data-loss / corruption risk under a plausible failure, **or a bounded failure whose blast radius is the whole service** (missing `context` deadline on a hot external call, `http.DefaultClient` with no timeout, uncapped retry, a missing or exceeded timeout / retry budget on a chained path, a duplicated or lost financial / irreversible effect from a retry or consumer, in-tx dual write, unbounded per-request goroutine spawn, unrecovered panic in a spawned goroutine, an optional dependency wired so its failure fails every request, a probe that removes every replica on one shared dependency); Medium = failure is bounded and contained to its own path but recovery or containment is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, a duplicated recoverable database write, an uncapped slice-backed buffer on a warm path); Low = hardening with no immediate failure path (missing bulkhead, fail-fast where stale data would serve). A dormant defect keeps the tier its failure path would have, with reachability under `Assumption`.

Labels: High -> `[Must]`; Low -> `[Recommend]`; Medium -> `[Recommend]`, escalated to `[Must]` only when **all three** hold: the fix that fully resolves the failure mode is confined to one file, it needs no product or architectural decision (no fallback policy to choose, no new component), and the defect sits on a money, auth, or data-integrity path. Judge by the fix that resolves the failure mode, not the cheapest partial one. When any leg is arguable, leave it `[Recommend]` and say why in the finding - an escalation that two reviewers would split on is not a merge blocker.

**One finding per root cause, where the unit is the edit that fixes it.** A defect satisfying several checklist items (an unbounded fan-out hits Steps 7 and 10) is one finding at the strongest severity. Several defects in one construct that one rewrite resolves - a detached goroutine that is also unbounded and also unrecovered - are likewise one finding; enumerate them (a)/(b)/(c) inside `Failure Mode` and `Blast Radius`, and count it once in `Overall`. Two defects at one call site that need **separate** fixes, or that survive each other's fix, are two findings. Two instances of one missing policy across different dependencies are one finding when the fix is a shared module, and separate findings when each site must be edited on its own terms.

**Fill rules.** `Overall` counts every published finding, dormant ones included. `Findings verified` is omitted on subagent runs, its parenthetical when K is 0; a sweep writes `-` for reattributed. `Review shape` appears only on a sweep. `Resilience Libraries` lists, among `sony/gobreaker`, `cenkalti/backoff`, `golang.org/x/sync` and `golang.org/x/time`, every one `go.mod` declares. Each finding heading is `#### <n>. [Label] file:line - <short title> _(annotations)_` with the label and annotations from Step 12 verbatim (tier-derived label on subagent runs and sweeps; `_(pre-existing)_` on a subagent finding whose line the diff did not add and on every sweep finding, followed by any annotation verify's confirmation returned; `_(carried from round <N>)_` on carried findings); numbering continues across tiers.

```markdown
## Go Reliability Review Summary

- **Stack Detected:** Go <version> / Gin <version>
- **Data Access:** GORM <version> | sqlx <version> | database/sql | mixed - GORM <version> + sqlx <version>
- **Messaging:** Asynq | Kafka | Asynq + Kafka | none
- **Resilience Libraries:** every one detected, comma-separated with versions, each marked `(in use)` or `(declared, unused)`; `none detected` only when there are none
- **Review shape:** whole-service sweep at `HEAD` on <trunk>     {sweep only}
- **Depth:** standard | deep
- **Overall:** Resilient | Gaps Found - <N> High / <N> Medium / <N> Low
- **Round:** <N>                                                   {round 2 onward; omitted on subagent runs}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff)

## Prior Round Reconciliation     {round 2+ only; omit otherwise}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Findings

### High Impact

#### 1. [Must] file:line - <short title> _(annotations)_     {annotation groups only when the Fill rules assign any}

- **Issue:** [name the gap: `http.DefaultClient` with no timeout, missing `context.WithTimeout`, uncapped retry, in-tx `asynq.Enqueue`, unbounded goroutine fan-out, unrecovered panic in a goroutine, etc.]

- **Failure Mode:** [what fails and how: "payment-gateway stall blocks the request goroutine indefinitely; each retained request pins a pooled DB conn"]

- **Blast Radius:** [what else is affected: "SetMaxOpenConns(25) exhausts under sustained traffic; every endpoint sharing the pool returns 503"]

- **Fix:** [`http.Client{Timeout}` + `gobreaker`, `context.WithTimeout`, `errgroup.SetLimit`, outbox, idempotency key, `recover()` at the goroutine boundary, etc.]

- **Assumption:** [only when the finding rests on something the repo cannot settle - `verify: max_connections unknown`, `assumes no out-of-repo env source`, `dormant: no caller today`]

#### 2. [Must] file:line - <short title>

[Same block, numbering continues across tiers]

### Medium Impact / Low Impact

[Same blocks]

Omit empty sections. When every section is empty, write "No reliability issues found." Blank lines separate the field lines - consecutive bare `**Label:** value` lines collapse into one paragraph when the report renders.

## Out of Lens

[Defects another lens owns, and pre-existing in-lens defects beyond the three published - each with `file:line` and the owning lens. Omit when there are none.]

## Recommendations

[Structural resilience improvements not tied to a single finding]

## Verified Clean

Checklist rows that were evaluated and passed, with their evidence - pool budget correct, graceful shutdown complete, no in-transaction dual write, `ctx` propagated end to end. On an already-resilient service this is most of the review's value, and `Overall: Resilient` alone cannot carry it. Rows that went **N/A** belong here too, marked `N/A - <reason>`: "no fan-out exists" and "checked and correct" are different facts; a subsystem absent from the surface entirely gets one `N/A` row, not one per check. Top-level so a parent merging by section heading cannot drop it.

## Next Steps

Each tagged `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra; `[scope: <owner>]`). Order: Must > Recommend. Each item carries its finding's label as published; one row per finding, naming a shared edit on the row rather than repeating it.

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: platform] - [action]

_Omit if none._

## Failure-Mode and Blast-Radius Map     {deep only}

| Dependency (new / changed) | Down or slow | Shared resource on the propagation path | Loop-breaker |
| -------------------------- | ------------ | --------------------------------------- | ------------ |
| <name, and what the diff did to it> | <what fails, and how far it gets> | <the `database/sql` pool, a worker pool, a channel, the broker, the Service endpoint list> | Present (<what contains it>) \| Partial (<what is missing>) \| **Missing** (<what to add>) |

Follow the table with any **amplification loop** found - a cycle where the failure's own consequence feeds the cause (probe failure removing replicas, which raises load on the rest, which fails more probes) - naming the one change that breaks the cycle.
```

## Avoid

- `git fetch` / `git checkout` from this workflow
- Writing a report when invoked as a subagent - the parent owns it
- Reporting a missing pattern without the failure mode ("add a timeout" vs "`http.DefaultClient` with no timeout pins the goroutine and exhausts the DB pool")
- Recommending retries on non-idempotent ops without an idempotency key, or a breaker with no monitoring
- Treating Asynq / Kafka redelivery as a substitute for consumer idempotency
- Overlapping into perf (throughput tuning) or observability (metric / log wiring) - name the failure-survival gap
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
