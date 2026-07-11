---
name: task-go-review-perf
description: Go / Gin perf review - GORM/sqlx N+1, goroutine leaks, context cancellation, mutex contention, sync.Pool, pool sizing, Asynq/Kafka throughput.
agent: go-performance-engineer
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, performance, goroutine, pprof, asynq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Go Performance Review

Go-aware review naming GORM `Preload` / `Joins` / `Select`, sqlx `In` / `NamedExec` / `SelectContext`, goroutine lifecycle, `context.Context` cancellation, `sync.Mutex` contention, allocation hotspots, pool sizing, Asynq / Kafka throughput, `golang-migrate` safety. Findings carry measured or estimated impact (latency, throughput, query count, alloc/op, goroutine count) and concrete Go fixes.

## When to Use

- Go/Gin PR or branch perf regression review
- Slow endpoint / Asynq task / Kafka consumer investigation
- Pre-merge perf pass on ORM queries, goroutine fan-out, channels, allocation paths
- Quarterly N+1 / pool / leak sweep

**Not for:** general review (`task-go-review`), security (`task-go-review-security`), production incident (`/task-oncall-start`), pre-implementation (`task-go-implement`).

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | All steps |
| `deep` | Profiling-driven with pprof / OTel / benchmark data | All + capacity guidance + load plan (emitted as a `### Capacity & Load Plan` subsection under Recommendations) |

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-perf` | Current branch vs base; fails fast on trunk |
| `/task-go-review-perf <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-perf pr-<N>` | PR head fetched into local branch `pr-<N>` |

When invoked as subagent (e.g. by `task-go-review`), Step 2 is skipped, the pre-read diff is reused, and Step 11 returns findings instead of writing - the parent owns the report.

## Workflow

### Step 1 - Stack and Data Access

Use skill: `stack-detect`. Accept pre-confirmed from parent. Record `Data Access` and `Messaging`.

### Step 2 - Resolve Diff

Use skill: `review-precondition-check`. Read diff + log once; reuse. Skip if subagent received handle.

Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

### Step 3 - Read the Performance Surface

Cite real `file:line`. Open:

**GORM:** changed models (tags, associations); changed repos (`Find` / `First` / `Preload` / `Joins` / `Where` / `Order` / `Group` / `Select`); handlers/services for context propagation; `cmd/api/main.go` / `internal/db/db.go` for pool config and GORM `Logger`.

**sqlx:** changed queries (raw SQL, named, `In`, `Select`, `Get`, `NamedExec`); changed repos for `*Context` variants; `*sqlx.DB` setup; prepared statement reuse.

**Both:** `migrations/`; Asynq / Kafka producers + consumers; worker concurrency; new goroutines / `errgroup.Go` / `wg.Go`; channel patterns; `sync.Pool`.

If the diff is small but ripples into unchanged code (a new endpoint calling an existing repository with an N+1), read the unchanged file - the regression lives there.

### Step 4 - ORM Hotspots (GORM or sqlx)

Use skill: `go-data-access`. Skip sqlx subsection on GORM-only projects and vice versa.

- [ ] **N+1:** GORM `Preload` / `Joins` (multi-level: `Preload("Items.Product")`); sqlx batches via `sqlx.In(...)` + `db.Rebind`, never per-iteration `db.Get` over parent list
- [ ] **Overfetch:** GORM `Preload("Items", func(db) { return db.Select(...) })`; sqlx `SELECT id, name` over `SELECT *`
- [ ] **Missing indexes** for `Where` / `Order` / `Group` columns
- [ ] **Unbounded reads:** list endpoints use `Limit` + keyset pagination (`Where("id > ?", lastID).Limit(N)`)
- [ ] **Per-row loops:** GORM `CreateInBatches(items, 100)`, `Clauses(clause.OnConflict{DoNothing: true})`; sqlx `db.NamedExec` with slice
- [ ] **Existence checks:** `db.Select("id").Where(...).First(...)` over fetch-then-`len`
- [ ] **`db.WithContext(ctx)` / sqlx `*Context`** - bare variants ignore `ctx.Done()`
- [ ] **`defer rows.Close()`** immediately after `QueryContext` / `QueryxContext`
- [ ] **Pool sized:** `db.SetMaxOpenConns(N) * replicas <= DB max_connections` (GORM default unlimited)
- [ ] **Prod-unsafe config:** GORM `Logger: logger.Info` in prod (every query at INFO); `db.Debug()` in hot path

### Step 5 - Indexes and Migrations

Use skill: `go-migration-safety` for changes in `migrations/`.

- [ ] Every `Where` / `Order` / `Group` column backed by an index
- [ ] Composite indexes match leftmost-prefix
- [ ] FK columns indexed (Postgres does not auto-index FKs)
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY`
- [ ] `SET lock_timeout = '2s'` before DDL on large tables
- [ ] Unique constraints at DB level, not just `gorm:"uniqueIndex"`
- [ ] Partial indexes for boolean/enum filters selecting a small subset
- [ ] No DDL on hot tables in a single migration (expand-then-contract)
- [ ] Backfill via keyset pagination, never `WHERE col IS NULL LIMIT N`
- [ ] DDL separated from DML
- [ ] `ALTER TYPE ... ADD VALUE` cannot run in a transaction
- [ ] Every `up` has a matching `down`
- [ ] No `db.AutoMigrate` in production

**Reasoning rule.** When the diff _adds_ an index, validate the index is needed (selectivity, shape), then assess safety. When the diff _adds a column_ that will be queried, flag the missing index proactively.

**Migration impact template.** State impact before approving DDL on a hot table: _"DDL on a 50M-row table without `CONCURRENTLY` blocks writes for 5-30 min at this scale. Acquires `ACCESS EXCLUSIVE`; every transaction queues."_ If row count unknown, ask or note "row count not in diff - confirm before deploy."

### Step 6 - Goroutine Lifecycle and Concurrency

Use skill: `go-concurrency`.

**Impact heuristic.** A leaked goroutine retains the request `context`, `gin.Context`, DB connections, mutexes. Under load, leaks compound (100/sec for an hour = 360k zombies). Phrase as "compounding leak proportional to sustained traffic," not "this one request leaks." HTTP to a critical-path upstream inherits its tail latency: p99 = max(your work, upstream p99); recommend `context.WithTimeout` + fallback, or async via decision cache / `gobreaker` / fire-and-forget Asynq.

- [ ] **Goroutine ownership + cancellation:** every `go fn()` has an owner (`errgroup.Group.Go`, `sync.WaitGroup`, Go 1.25+ `WaitGroup.Go`, worker pool with shutdown); blocking receive paired with `<-ctx.Done()`
- [ ] **Bounded fan-out:** `errgroup.SetLimit(N)` or `semaphore.NewWeighted`; unbounded exhausts pool / FDs / scheduler
- [ ] **`context.WithTimeout` / `WithDeadline`** on outbound calls (`http.Client` without `Timeout` is infinite)
- [ ] **HTTP clients package-level:** shared via constructor, not per-request - `Transport.MaxIdleConnsPerHost` matters
- [ ] **`sync.Mutex` not held across I/O:** drop lock before HTTP / DB / channel-send. If serialization needed: per-key mutex / `singleflight.Group`. Read-heavy maps use `sync.RWMutex`; `sync.Map` only for write-once / disjoint patterns
- [ ] **No CPU-heavy work on request goroutine without profiling:** hashing, image processing, large JSON marshal -> Asynq / worker pool when latency-dominant
- [ ] **No external I/O inside `db.Transaction(...)`:** holds pooled connection for upstream tail latency. Capture inputs; dispatch after `Transaction` returns nil

### Step 7 - Allocation Hotspots

- [ ] **Slice pre-allocation:** `make([]T, 0, n)` over `var s []T` then `append` in a known-capacity loop
- [ ] **`sync.Pool` for hot temporary objects** (byte buffers, large structs reused per request) - not for long-lived objects (defeats the pool)
- [ ] **`strings.Builder` over `+`** in loops
- [ ] **`json.Encoder` over `json.Marshal`** for streaming
- [ ] **`jsoniter` / `easyjson`** for hot JSON when profiling shows `encoding/json` dominates
- [ ] **`[]byte` over `string`** for transient data at API boundaries
- [ ] **No reflection in hot paths** - use type switch or generics
- [ ] **Map pre-sizing:** `make(map[K]V, n)` avoids rehashing
- [ ] **Scheduler overhead:** thousands of short-lived goroutines vs a worker pool with fixed workers

### Step 8 - Caching

- [ ] **In-process:** `ristretto` for LRU/LFU; `groupcache` shared distributed; `sync.Map` for tiny caches. TTL configured
- [ ] **Redis cache:** shared across replicas; `SetEx` for TTL; `Pipeline` for batched ops
- [ ] **Stampede protection:** hot keys with expensive regen use `golang.org/x/sync/singleflight`; distributed via Redis `SET NX EX` lock
- [ ] **Invalidation explicit** - document staleness budget
- [ ] **HTTP caching** (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GETs via Gin middleware
- [ ] **Response compression** (`gin-contrib/gzip`) for JSON > 2KB
- [ ] **Per-request memoization** via `gin.Context.Set`

### Step 9 - Asynq / Kafka / Background Work

Use skill: `go-messaging-patterns`.

**Asynq:**

- [ ] **Idempotent + ID payloads:** re-fetch state, return early if done; payload uses IDs / primitives. `asynq.TaskID(businessKey)` for client-side dedup
- [ ] **`client.Enqueue()` AFTER commit:** never inside `db.Transaction(...)`
- [ ] **Retry policy + archive:** `asynq.MaxRetry(N)`, `asynq.Retention(...)`, `asynq.Timeout(...)` explicit; archived tasks surfaced via observability
- [ ] **Queue priorities + Server concurrency:** time-sensitive on higher-weight queue; `asynq.Config{Concurrency: N}` aligned to downstream capacity

**Kafka (franz-go):**

- [ ] **Consumer group + manual commits:** `cl.CommitRecords(...)` after successful processing
- [ ] **Idempotent consumers** (at-least-once delivery)
- [ ] **Bounded in-flight:** `franz.MaxConcurrentFetches`, `franz.FetchMaxBytes` tuned for memory

### Step 10 - Observability for Perf (delegation handoff)

Depth belongs to `task-go-review-observability`. Confirm only:

- [ ] Slow paths from this PR have **some** instrumentation (OTel span or Prometheus histogram); if not, raise Low / Recommendation and delegate
- [ ] GORM `Logger: logger.Info` not enabled in prod; sqlx query logging not in prod (only if in diff)
- [ ] `net/http/pprof` registered (non-prod or behind auth)

Beyond presence/absence -> `task-go-review-observability` owns it.

### Step 11 - Write Report

Standalone only - subagent runs return findings in the Output Format to the parent, which writes the single merged report.

Use skill: `review-report-writer` with `report_type: review-perf` and every required input: `report_body`, `branch` (from the handle), refs from the precondition handle, `base_sha`/`head_sha` from Step 2, `stack: go-gin`, `scope: +perf`, `depth` as resolved from the Depth table, and `mode: full`, `round: 1` - unless `review-perf-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`. (The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.) Write before ending; print confirmation.

## Self-Check

- [ ] Stack confirmed; data-access mix and messaging recorded
- [ ] `review-precondition-check` ran (or handle received); diff/log read once and reused
- [ ] For `pr-ref` mode: user-run fetch surfaced; ref existed before review continued
- [ ] When `head_matches_current` was false: user approval obtained (skipped when subagent)
- [ ] Performance surface read directly (models / repos, handlers, config, migrations, Asynq / Kafka, goroutine launch sites)
- [ ] `go-data-access` consulted; N+1, multi-level, overfetch, projection, upsert idempotency checked
- [ ] `go-migration-safety` consulted; `lock_timeout`, concurrent index, keyset backfill, expand-contract verified
- [ ] `go-concurrency` consulted; ownership, fan-out, mutex contention, channels audited
- [ ] `go-messaging-patterns` consulted for Asynq / Kafka; idempotency, retry, post-commit, queue priorities
- [ ] Pool sizing validated against worker / replica concurrency **if pool config in diff**; otherwise Low / Recommendation
- [ ] Allocation hotspots assessed when diff touches hot loops / large structs
- [ ] Caching assessed (in-process vs Redis, single-flight, invalidation)
- [ ] Every finding states impact - measured (`p95 800ms -> 120ms`) when pprof / APM data exists, estimated otherwise (`adds ~N queries at K rows`)
- [ ] Findings ordered by impact; quick wins separated from structural
- [ ] Depth honored: `standard` ran all; `deep` adds capacity + load plan
- [ ] Next Steps with `[Implement]` / `[Delegate]` tags, ordered Must > Recommend > Question
- [ ] Report written via `review-report-writer` with all required checkpoint fields (standalone only; subagent runs return findings to the parent); confirmation printed

## Output Format

```markdown
## Go Performance Review Summary

**Stack Detected:** Go <version> / Gin <version>
**Data Access:** GORM <version> | sqlx <version> | database/sql | mixed
**Messaging:** Asynq | Kafka | none
**Scope:** Backend (Go)
**Overall:** Clean | Issues Found - [count by impact]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [Go idiom: N+1 via per-iteration `db.Find`, missing `Preload`, missing index, sync `bcrypt` on request goroutine, leaked goroutine via missing `<-ctx.Done()`, Asynq `Enqueue` inside transaction]
- **Impact:** [estimated: "N+1 adds ~200 queries per request at 100 orders" / measured: "p95 800ms -> 120ms after fix"]
- **Fix:** [Go change with code]

### Medium Impact / Low Impact

[Same structure]

_Omit empty sections._

## Recommendations

[Structural improvements not tied to a finding]

## Next Steps

Each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question.
Impact maps to intent: High -> [Must]; Medium / Low -> [Recommend]; [Question] when impact depends on data only the author has (row counts, traffic).

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: schema] - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- `git fetch` / `git checkout` from this workflow
- Chaining `mode` / `round` off the general review's checkpoint instead of `review-perf-<branch>.md`
- Writing a report when invoked as a subagent - the parent owns it
- Reporting without naming the idiom ("this is slow" vs "N+1 from per-iteration `db.Find`")
- Generic advice when a Go pattern applies (say "use `Preload`", not "use eager loading")
- `go fn()` without bounding (`errgroup.SetLimit`) and cancellation
- `interface{}` / `any` to "make it flexible" (generics replace most uses)
- Caching without invalidation strategy
- Conflating perf with general or security review
- Treating Asynq retries as a substitute for idempotency
- `db.AutoMigrate`
- "Missing index" without confirming the column appears in `Where` / `Order` / `Group`
- `sync.Map` as a default (`map + sync.RWMutex` faster for typical workloads)
- `sync.Pool` for long-lived objects
- `panic` for "this should never happen"
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
