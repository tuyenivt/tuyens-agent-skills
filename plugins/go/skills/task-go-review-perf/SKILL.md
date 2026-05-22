---
name: task-go-review-perf
description: Go / Gin performance review: GORM/sqlx N+1, goroutine leaks, context cancellation, mutex contention, sync.Pool, pool sizing, Asynq/Kafka throughput.
agent: go-performance-engineer
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, performance, goroutine, pprof, asynq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Go Performance Review

Go-aware performance review naming GORM `Preload` / `Joins` / `Select`, sqlx `In` / `NamedExec` / `SelectContext`, goroutine lifecycle, `context.Context` cancellation, `sync.Mutex` contention, allocation hotspots, connection pool sizing, Asynq / Kafka throughput, and `golang-migrate` safety. Findings have measured or estimated impact (latency, throughput, query count, alloc/op, goroutine count) and concrete Go fixes.

## When to Use

- Go/Gin PR or branch perf regression review
- Slow endpoint / Asynq task / Kafka consumer investigation
- Pre-merge perf pass on ORM queries, goroutine fan-out, channel patterns, hot allocation paths
- Quarterly N+1 / pool-sizing / leak sweep against pprof / APM data

**Not for:**
- General Go review (`task-go-review`)
- Security review (`task-go-review-security`)
- Production incident (`/task-oncall-start`)
- Pre-implementation design (`task-go-implement`)

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `quick` | Single endpoint / repository | Steps 4 + 5 only |
| `standard` | Default | All steps |
| `deep` | Profiling-driven with pprof / OTel / benchmark data | All + capacity guidance + load plan |

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-perf` | Current branch vs base; fails fast on trunk |
| `/task-go-review-perf <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-perf pr-<N>` | PR head fetched into local branch `pr-<N>` |

When invoked as subagent, Step 2 is skipped and pre-read diff is reused.

## Workflow

### Step 1 - Confirm Stack and Detect Data Access

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. Record `Data Access` and `Messaging`.

### Step 2 - Resolve the Diff

Use skill: `review-precondition-check`. Read diff and log once via `git diff <base>...<head>` and `git log <base>..<head>`; reuse. Skip entirely as subagent with handle + pre-read.

If `review-precondition-check` fails fast, surface verbatim and stop.

### Step 3 - Read the Performance Surface

Cite real `file:line` per finding. Open:

**GORM:** every changed model (tags, associations), every changed repository (`Find` / `First` / `Preload` / `Joins` / `Where` / `Order` / `Group` / `Select`), every changed handler/service for context propagation, `cmd/api/main.go` / `internal/db/db.go` for `SetMaxOpenConns` / `SetMaxIdleConns` / `SetConnMaxLifetime` / GORM `Logger`.

**sqlx:** every changed query (raw SQL, named, `In`, `Select`, `Get`, `NamedExec`), every changed repository for `*Context` variants, `*sqlx.DB` setup for pool, prepared statement reuse.

**Both:** `migrations/` files; Asynq / Kafka producers and consumers; worker concurrency; new goroutines / `errgroup.Go` / `wg.Go`; channel patterns; `sync.Pool`.

If the diff is small but ripples into unchanged code (a new endpoint calling an existing repository with an N+1), read the unchanged file - the regression lives there.

### Step 4 - ORM Hotspots (GORM or sqlx)

Canonical patterns: Use skill: `go-data-access`. This step flags deviations - skip the sqlx subsection on GORM-only projects and vice versa.

- [ ] **N+1**: GORM `Preload` / `Joins` (multi-level: `Preload("Items.Product")`); sqlx batches via `sqlx.In(...)` + `db.Rebind`, never per-iteration `db.Get` over a parent list
- [ ] **Overfetch**: GORM `Preload("Items", func(db) { return db.Select(...) })`; sqlx `SELECT id, name` over `SELECT *`
- [ ] **Missing indexes** for `Where` / `Order` / `Group` columns - flag any predicate / sort column without `gorm:"index"` or `CREATE INDEX` migration
- [ ] **Unbounded reads**: list endpoints use `Limit` + keyset pagination (`Where("id > ?", lastID).Limit(N)`)
- [ ] **Per-row loops**: GORM `CreateInBatches(items, 100)`, `Clauses(clause.OnConflict{DoNothing: true})`; sqlx `db.NamedExec` with slice
- [ ] **Existence checks**: `db.Select("id").Where(...).First(...)` over fetch-then-`len`
- [ ] **`db.WithContext(ctx)` / sqlx `*Context` variants** - bare variants ignore `ctx.Done()`
- [ ] **`defer rows.Close()`** immediately after `QueryContext` / `QueryxContext`
- [ ] **Connection pool sized**: `db.SetMaxOpenConns(N) × replicas ≤ DB max_connections` (GORM default unlimited - foot-gun)
- [ ] **Prod-unsafe config**: GORM `Logger: logger.Info` in prod (every query at INFO); `db.Debug()` left in hot path

### Step 5 - Indexes and Migrations

Use skill: `go-migration-safety` for changes in `migrations/`.

- [ ] Every column in `Where` / `Order` / `Group` backed by an index
- [ ] Composite indexes match leftmost-prefix
- [ ] FK columns indexed (PostgreSQL does not auto-index FKs)
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY`
- [ ] `SET lock_timeout = '2s'` before DDL on large tables
- [ ] Unique constraints at the DB level, not just `gorm:"uniqueIndex"`
- [ ] Partial indexes for boolean/enum filters selecting a small subset
- [ ] No DDL on hot tables in a single migration (expand-then-contract)
- [ ] Backfill via keyset pagination (`WHERE id > $1 ORDER BY id LIMIT N`), never `WHERE col IS NULL LIMIT N`
- [ ] Data migrations isolated from DDL migrations
- [ ] Enum changes safe: PostgreSQL `ALTER TYPE ... ADD VALUE` cannot run in a transaction
- [ ] Every `up` has a matching `down`
- [ ] No `db.AutoMigrate` in production paths

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot - validate the index is needed (selectivity, shape), then assess safety. When the diff _adds a column_ also queried on, flag the missing index proactively.

**Migration impact template.** State the impact before approving migration steps on a hot table: _"DDL on a 50M-row table without `CONCURRENTLY` blocks writes for 5-30 min on Postgres at this scale. Acquires `ACCESS EXCLUSIVE`; every other transaction queues."_ If row count is unknown, ask, or note "row count not in diff - confirm before deploy."

### Step 6 - Goroutine Lifecycle and Concurrency

Canonical patterns: Use skill: `go-concurrency`.

**Impact heuristic.** A leaked goroutine retains the request `context`, `gin.Context`, and DB connections / mutexes. Under load, leaks compound (100/sec for an hour = 360k zombie goroutines). Phrase impact as "compounding leak proportional to sustained traffic," not "this one request leaks." HTTP to a critical-path upstream inherits its tail latency: p99 = max(your work, upstream p99); recommend `context.WithTimeout` + fallback, or async via decision cache / `gobreaker` / fire-and-forget Asynq.

- [ ] **Goroutine ownership + cancellation**: every `go fn()` has an owner (`errgroup.Group.Go`, `sync.WaitGroup`, Go 1.25+ `WaitGroup.Go`, worker pool with shutdown); blocking receive paired with `<-ctx.Done()`
- [ ] **Bounded fan-out**: `errgroup.SetLimit(N)` (Go 1.20+) or `semaphore.NewWeighted`; unbounded exhausts pool / FDs / scheduler
- [ ] **`context.WithTimeout` / `WithDeadline`** on outbound calls (`http.Client` without `Timeout` is effectively infinite)
- [ ] **HTTP clients package-level**: shared via constructor, not per-request - `Transport.MaxIdleConnsPerHost` reuse matters
- [ ] **`sync.Mutex` not held across I/O**: drop lock before HTTP / DB / channel-send. If serialization needed, use per-key mutex / `singleflight.Group`. Read-heavy maps use `sync.RWMutex`; `sync.Map` only for write-once / disjoint patterns
- [ ] **No CPU-heavy work on request goroutine without profiling**: hashing, image processing, large JSON marshal → Asynq / worker pool when latency-dominant
- [ ] **No external I/O inside `db.Transaction(...)`**: holds pooled connection for upstream tail latency. Capture inputs, dispatch after `Transaction` returns nil (worker-pickup correctness lens owned by `task-go-review`)

### Step 7 - Allocation Hotspots and CPU Cost

_Skipped at `quick` unless the diff touches hot loops or large allocations._

- [ ] **Slice pre-allocation**: `make([]T, 0, n)` over `var s []T` then `append` in a known-capacity loop
- [ ] **`sync.Pool` for hot temporary objects** (byte buffers, large structs reused per request) - reduces GC pressure. Not for long-lived objects (defeats the pool)
- [ ] **`strings.Builder` over `+`** in loops (avoids quadratic alloc)
- [ ] **`json.Encoder` over `json.Marshal` for streaming** (writes directly to `w`; no full allocation)
- [ ] **`jsoniter` / `easyjson`** for hot JSON when profiling shows `encoding/json` dominates CPU
- [ ] **`[]byte` over `string`** for transient data at API boundaries that take both
- [ ] **No reflection in hot paths** - use type switch or generics
- [ ] **Map pre-sizing**: `make(map[K]V, n)` avoids rehashing
- [ ] **Scheduler overhead**: thousands of short-lived goroutines vs a worker pool with fixed workers

### Step 8 - Caching and Response Performance

_Skipped at `quick` unless the diff touches caching primitives._

- [ ] **In-process**: `ristretto` for LRU/LFU; `groupcache` shared distributed; `sync.Map` for tiny caches. TTL configured
- [ ] **Redis cache** (`go-redis/redis/v9`): shared across replicas; `SetEx` for TTL; `Pipeline` for batched ops
- [ ] **Stampede protection**: hot keys with expensive regen use `golang.org/x/sync/singleflight`; for distributed, Redis `SET NX EX` lock
- [ ] **Invalidation explicit** - document staleness budget
- [ ] **HTTP caching** (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GETs via Gin middleware
- [ ] **Response compression** (`gin-contrib/gzip`) for JSON > 2KB
- [ ] **Per-request memoization** via `gin.Context.Set` for cross-middleware values

### Step 9 - Asynq / Kafka / Background Work

_Skipped at `quick` unless the diff touches Asynq or Kafka._

Use skill: `go-messaging-patterns`. Apply the review-scoped scan (branch on `Messaging:`).

**Asynq:**

- [ ] **Idempotent + ID payloads**: re-fetch state, return early if done; payload uses IDs / primitives. `asynq.TaskID(businessKey)` for client-side dedup
- [ ] **`client.Enqueue()` AFTER commit**: never inside `db.Transaction(...)`
- [ ] **Retry policy + archive**: `asynq.MaxRetry(N)`, `asynq.Retention(...)`, `asynq.Timeout(...)` explicit; archived tasks surfaced via observability
- [ ] **Queue priorities + Server concurrency**: time-sensitive on higher-weight queue; `asynq.Config{Concurrency: N}` aligned to downstream capacity

**Kafka (franz-go):**

- [ ] **Consumer group + manual commits**: `cl.CommitRecords(...)` after successful processing (auto-commit drops messages)
- [ ] **Idempotent consumers**: at-least-once delivery
- [ ] **Bounded in-flight**: `franz.MaxConcurrentFetches`, `franz.FetchMaxBytes` tuned for memory

### Step 10 - Observability for Perf (delegation handoff)

_Skipped at `quick`._

Depth on observability belongs to `task-go-review-observability`. Confirm only:

- [ ] Slow paths from this PR have **some** instrumentation (OTel span or Prometheus histogram); if not, raise as Low / Recommendation and delegate
- [ ] GORM `Logger: logger.Info` not enabled in prod; sqlx query logging not in prod (only if in diff)
- [ ] `net/http/pprof` registered (non-prod or behind auth)

Beyond presence/absence → `task-go-review-observability` owns it.

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Write before ending; print confirmation.

## Self-Check

- [ ] Stack confirmed as Go/Gin; data-access mix and messaging recorded
- [ ] `review-precondition-check` ran (or handle received); diff/log read once and reused
- [ ] For `pr-ref` mode: user-run fetch surfaced; ref existed before review continued
- [ ] When `head_matches_current` was false: user approval obtained (skipped when subagent)
- [ ] Performance surface read directly (models / repositories, handlers, config, migrations, Asynq / Kafka, goroutine launch sites)
- [ ] `go-data-access` consulted; N+1, multi-level, overfetch, projection, upsert idempotency checked
- [ ] `go-migration-safety` consulted; `lock_timeout`, concurrent index, keyset backfill, expand-contract verified
- [ ] `go-concurrency` consulted; ownership, fan-out, mutex contention, channels audited
- [ ] `go-messaging-patterns` consulted for Asynq / Kafka; idempotency, retry, post-commit dispatch, queue priorities verified
- [ ] Pool sizing validated against worker / replica concurrency **if pool config is in diff**; otherwise Low / Recommendation
- [ ] Allocation hotspots assessed when diff touches hot loops / large structs
- [ ] Caching assessed (in-process vs Redis, single-flight, invalidation)
- [ ] Every finding states impact - measured (`p95 800ms -> 120ms`) when pprof / APM data exists, estimated otherwise (`adds ~N queries per request at K rows`)
- [ ] Findings ordered by impact; quick wins separated from structural
- [ ] Depth honored: `quick` ran Steps 4 + 5; `standard` ran 4-10; `deep` adds capacity + load plan
- [ ] Next Steps with `[Implement]` / `[Delegate]` tags, ordered High > Medium > Low
- [ ] Review report written via `review-report-writer`; confirmation printed

## Output Format

```markdown
## Go Performance Review Summary

**Stack Detected:** Go <version> / Gin <version>
**Data Access:** GORM <version> | sqlx <version> | database/sql | mixed
**Messaging:** Asynq | Kafka | none
**Scope:** Backend (Go)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [Go idiom: N+1 via per-iteration `db.Find` inside loop, missing `Preload`, missing index, sync `bcrypt` on request goroutine, leaked goroutine via missing `<-ctx.Done()`, Asynq `Enqueue` inside transaction, etc.]
- **Impact:** [estimated: "N+1 in OrderHandler.List adds ~200 queries per request at 100 orders" / measured: "p95 800ms -> 120ms after fix"]
- **Fix:** [Go change with code: `Preload`, `errgroup.SetLimit`, `db.WithContext`, post-commit Asynq `Enqueue`, etc.]

### Medium Impact
[Same structure]

### Low Impact / Quick Wins
[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a finding - e.g., "Switch list endpoint to keyset pagination", "Add Redis cache for product catalog reads", "Replace `encoding/json` with `easyjson`-generated marshallers"]

## Next Steps

Each item tagged `[Implement]` or `[Delegate]`. Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: schema] - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- `git fetch` / `git checkout` from this workflow - user runs these
- Reporting issues without naming the Go idiom ("this is slow" vs "N+1 from per-iteration `db.Find`")
- Generic backend advice when a Go pattern applies (say "use `Preload`", not "use eager loading")
- Suggesting `go fn()` without bounding (`errgroup.SetLimit`) and cancellation
- Suggesting `interface{}` / `any` to "make it flexible" (generics replace most legitimate uses)
- Suggesting caching without invalidation strategy
- Conflating perf with general or security review
- Treating Asynq retries as a substitute for idempotency
- Recommending `db.AutoMigrate`
- Reporting "missing index" without confirming the column appears in `Where` / `Order` / `Group`
- Recommending `sync.Map` as a default (`map + sync.RWMutex` faster for typical workloads)
- Recommending `sync.Pool` for long-lived objects (defeats GC; pools are for transient hot-path)
- Approving `panic` for "this should never happen"
