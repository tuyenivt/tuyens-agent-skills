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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Go Performance Review

## Purpose

Go-aware performance review that names GORM `Preload` / `Joins` / `Select`, sqlx `In` / `NamedExec` / `SelectContext`, goroutine lifecycle (leak vs unbounded fan-out vs scheduling overhead), `context.Context` cancellation propagation, `sync.Mutex` contention, allocation hotspots (`sync.Pool`, slice pre-allocation, string vs []byte), connection pool sizing (`SetMaxOpenConns`), Asynq / Kafka consumer throughput, and golang-migrate safety idioms directly instead of routing through the generic backend adapter. Produces findings with measured or estimated impact (latency, throughput, query count, alloc/op, goroutine count) and concrete fixes using idiomatic Go.

This workflow is the stack-specific delegate of `task-code-review-perf` for Go. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a Go/Gin PR or branch for performance regressions
- Investigating a slow endpoint, Asynq task, or Kafka consumer
- Pre-merge perf pass on changes touching ORM queries, goroutine fan-out, channel patterns, or hot allocation paths
- Quarterly N+1 / pool-sizing / leak-detection sweep against pprof / APM data

**Not for:**

- General Go code review (use `task-code-review` or `task-go-review`)
- Security review (use `task-code-review-security` or `task-go-review-security`)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-go-implement`)

## Depth Levels

| Depth      | When to Use                                              | What Runs                                          |
| ---------- | -------------------------------------------------------- | -------------------------------------------------- |
| `quick`    | Single endpoint or repository ("is this query ok?")      | Steps 4 + 5 only; ORM hotspots + migrations        |
| `standard` | Default - full Go perf review                            | All steps                                          |
| `deep`     | Profiling-driven review with pprof / OTel / benchmark data | All steps + capacity guidance and load plan      |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                      | Meaning                                                                                               |
| ------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-go-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-go-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-go-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Data-Access Mix

Use skill: `stack-detect` to confirm Go / Gin. If invoked as a delegate of `task-code-review-perf` or as a subagent of `task-go-review` (parent already detected Go), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Go, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Go 1.25+.

Detect data access:

- `gorm.io/gorm` import only → **GORM**
- `github.com/jmoiron/sqlx` import only → **sqlx**
- Both present → **mixed**
- Neither, only `database/sql` → **database/sql**

Detect messaging: Asynq (`hibiken/asynq`) vs franz-go Kafka (`twmb/franz-go`) vs none.

The data-access decision drives which checklists in Step 4 apply. Record `Data Access: GORM | sqlx | mixed | database/sql`, `Messaging: Asynq | Kafka | none` for the Summary block.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Performance Surface

Before applying the checklists, open the files that govern query and concurrency behavior so impact estimates ground in real code:

**GORM surface:**

- Every changed model (`gorm:"index"`, `gorm:"foreignKey"`, association tags)
- Every changed repository (`db.Find`, `db.First`, `db.Preload`, `db.Joins`, `db.Where`, `db.Order`, `db.Group`, `db.Select`)
- Every changed handler / service for sync vs async, context propagation (`db.WithContext(ctx)`)
- `cmd/api/main.go` / `internal/db/db.go` for `SetMaxOpenConns`, `SetMaxIdleConns`, `SetConnMaxLifetime`, GORM `Logger` config

**sqlx surface:**

- Every changed query (raw SQL, named queries, `In`, `Select`, `Get`, `NamedExec`)
- Every changed repository for context-aware variants (`SelectContext`, `GetContext`, `NamedExecContext`)
- `*sqlx.DB` setup for pool sizing
- Prepared statement reuse patterns

**Both:**

- golang-migrate files under `migrations/`
- Asynq / Kafka producers and consumers; worker concurrency settings
- Any new goroutines (`go fn()`, `errgroup.Group.Go(...)`, `wg.Go(...)` in Go 1.25+); channel patterns; `sync.Pool` usage

For each finding produced later, cite a real `file:line`. If the diff is small but ripples through code that is not in the diff (a new endpoint calling an existing repository whose query does an N+1), read the unchanged file too - the regression lives there even though the line count attributes it to the new caller.

### Step 4 - ORM Hotspots (GORM or sqlx)

> If `Data Access: GORM` was recorded in Step 1, **skip the sqlx subsection** below; likewise skip GORM on sqlx-only projects. The bifurcation exists for mixed codebases.

Canonical patterns live in `go-data-access`. This step is the **review-scoped scan** - flag deviations against the canonical owner; do not re-derive idioms here.

**Review-scoped scan** (GORM or sqlx, branching on `Data Access:`):

- [ ] **N+1**: association traversal after a list query is eager-loaded - GORM `Preload` / `Joins` (multi-level: `Preload("Items.Product")`); sqlx batches via `sqlx.In(...)` + `db.Rebind`, never per-iteration `db.Get` over a parent list
- [ ] **Overfetch**: payload bounded via projection - GORM `Preload("Items", func(db) { return db.Select("id", "sku") })`; sqlx `SELECT id, name` over `SELECT *` (default returns large `text` / `bytea`)
- [ ] **Missing indexes for `Where` / `Order` / `Group` columns** - flag any predicate / sort column without `gorm:"index"` or a `CREATE INDEX` migration
- [ ] **Unbounded reads**: list endpoints use `Limit` + keyset pagination (`Where("id > ?", lastID).Limit(N)`), not bare `Find`
- [ ] **Per-row loops** in place of bulk operations - GORM `CreateInBatches(items, 100)`, `Clauses(clause.OnConflict{DoNothing: true})`; sqlx `db.NamedExec` with slice
- [ ] **Existence checks**: `db.Select("id").Where(...).First(...)` / `SELECT EXISTS(SELECT 1 ...)` over fetch-then-`len`
- [ ] **`db.WithContext(ctx)` / sqlx `*Context` variants** on every query - `SelectContext` / `GetContext` / `NamedExecContext` propagate cancellation; bare variants ignore `ctx.Done()`
- [ ] **`defer rows.Close()`** immediately after `db.QueryContext` / `QueryxContext` succeeds - missing leaks a connection back to the pool
- [ ] **Connection pool sized**: `db.SetMaxOpenConns(N)` × replica count ≤ DB `max_connections` (GORM default is unlimited - foot-gun)
- [ ] **Prod-unsafe config**: GORM `Logger: logger.Info` in prod flagged (every query at INFO); `db.Debug()` left in hot path; sqlx project-specific query logging enabled in prod

### Step 5 - Indexes and Migrations

Use skill: `go-migration-safety` for safe-migration checks on any change in `migrations/` (golang-migrate).

- [ ] Every column referenced in `Where` / `Order` / `Group` is backed by an index
- [ ] Composite indexes match the leftmost-prefix pattern of the queries
- [ ] Foreign keys have indexes (PostgreSQL does not auto-index FKs)
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL); golang-migrate files contain raw SQL so this is explicit
- [ ] **`SET lock_timeout = '2s'`** before DDL on large tables to fail fast instead of blocking
- [ ] Unique constraints enforced at the database level, not just `gorm:"uniqueIndex"` on a non-managed column
- [ ] Partial indexes used for boolean/enum filters that select a small subset (`CREATE INDEX ... WHERE status = 'pending'`)
- [ ] No DDL on hot tables in a single migration (expand-then-contract: add column nullable, backfill, switch reads, drop old column in a later release)
- [ ] **Backfill via keyset pagination** (`WHERE id > $1 ORDER BY id LIMIT N`), never `WHERE col IS NULL LIMIT N` (re-scans the same rows on every iteration)
- [ ] Data migrations isolated from DDL migrations - separate golang-migrate files
- [ ] Enum changes safe: PostgreSQL `ALTER TYPE ... ADD VALUE` cannot run in a transaction; document workaround
- [ ] **Every `up` has a matching `down`**; `down` tested or documented as one-way
- [ ] **No `db.AutoMigrate`** in production code paths

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot in `WHERE` / `ORDER BY` / `GROUP BY` even if no query in the diff currently references it - someone is adding the index for a reason, and the migration is the load-bearing artifact. Validate the index is actually needed (column shape, expected selectivity), then assess migration safety. Conversely, when the diff _adds a column_ the application also queries on, flag the missing index proactively rather than waiting for a separate migration PR.

**Migration impact template.** Before approving any migration step on a hot table, state the impact: _"DDL on a 50M-row table without `CONCURRENTLY` blocks all writes for the duration of the index build (typically 5-30 min on Postgres at this scale). Acquires `ACCESS EXCLUSIVE`; every other transaction queues."_ If the row count is unknown, ask, or note "row count not in diff - confirm before deploy."

### Step 6 - Goroutine Lifecycle and Concurrency

Canonical patterns live in `go-concurrency`. Apply the **review-scoped scan** below.

> **Impact heuristic.** A leaked goroutine retains the request `context`, `gin.Context`, and captured DB connections / mutexes. Under sustained traffic, leaks compound (100/sec for an hour = 360k zombie goroutines) and eventually trigger OOM or scheduler degradation. Phrase impact as "compounding leak proportional to sustained traffic," not "this one request leaks." HTTP to a critical-path upstream inherits its tail latency: p99 = max(your work, upstream p99) - recommend `context.WithTimeout` + fallback, or async pattern (decision cache, `gobreaker`, fire-and-forget via Asynq).

- [ ] **Goroutine ownership + cancellation**: every `go fn()` has an owner (`errgroup.Group.Go`, `sync.WaitGroup`, Go 1.25+ `WaitGroup.Go`, or worker pool with shutdown); every blocking receive paired with `select { case ...: ; case <-ctx.Done(): return ctx.Err() }`. Bare `go fn()` in a request handler is a leak surface
- [ ] **Bounded fan-out**: `errgroup.SetLimit(N)` (Go 1.20+) or `semaphore.NewWeighted` over a list - unbounded fan-out exhausts pool / FDs / scheduler
- [ ] **`context.WithTimeout` / `WithDeadline`** on every outbound call: `ctx, cancel := context.WithTimeout(ctx, 500*time.Millisecond); defer cancel()` (`http.Client` without `Timeout` is effectively infinite)
- [ ] **HTTP clients package-level**: `http.Client` / `resty.Client` shared via constructor, not per-request - `Transport.MaxIdleConnsPerHost` reuse matters at scale
- [ ] **`sync.Mutex` not held across I/O**: drop lock before HTTP / DB / channel-send; if I/O must be serialized, use per-key mutex / `singleflight.Group`. Read-heavy maps use `sync.RWMutex`. `sync.Map` only for specific patterns (write-once / disjoint key sets) - `map + sync.RWMutex` faster for typical workloads
- [ ] **No CPU-heavy work on request goroutine without profiling**: hashing, image processing, large JSON marshalling → Asynq task / worker pool when measured to dominate latency
- [ ] **No external I/O inside `db.Transaction(...)`**: holds pooled connection for the upstream's tail latency, drains pool faster than QPS predicts. Capture inputs inside, dispatch after `Transaction` returns nil. Correctness lens (worker pickup before commit) is owned by `task-go-review`

### Step 7 - Allocation Hotspots and CPU Cost

_Skipped at `quick` depth unless the diff touches hot loops or large allocations._

- [ ] **Slice pre-allocation**: `make([]T, 0, n)` over `var s []T` then `append` in a loop with known capacity - avoids reallocation churn.
- [ ] **`sync.Pool` for hot temporary objects**: byte buffers (`bytes.Buffer`), large structs reused per request - reduces GC pressure. Don't use for objects with a long lifetime (defeats the pool).
- [ ] **`strings.Builder` over string concatenation in loops**: `var b strings.Builder; for _, s := range parts { b.WriteString(s) }; result := b.String()` - avoids quadratic allocation.
- [ ] **`json.Encoder` over `json.Marshal` for streaming**: `json.NewEncoder(w).Encode(v)` writes directly to `w` (often `gin.Context.Writer`); `json.Marshal` allocates the full byte slice first.
- [ ] **`jsoniter` / `easyjson` for hot JSON paths**: when profiling shows `encoding/json` dominates CPU, swap to `github.com/json-iterator/go` (drop-in) or generate `easyjson` marshallers for the specific types.
- [ ] **`[]byte` over `string` for transient data**: avoids unnecessary copies at API boundaries that take both.
- [ ] **Avoid reflection in hot paths**: `reflect.ValueOf(...)` is slow; if the type is known, use type switch or generics (Go 1.18+).
- [ ] **Map pre-sizing**: `make(map[K]V, n)` when capacity is known avoids rehashing.
- [ ] **Goroutine scheduler overhead**: spawning thousands of goroutines for short-lived work has overhead; use a worker pool with a fixed number of workers consuming from a channel.

### Step 8 - Caching and Response Performance

_Skipped at `quick` depth unless the diff touches caching primitives._

- [ ] **In-process cache**: `ristretto` (`dgraph-io/ristretto`) for LRU/LFU eviction; `groupcache` for shared distributed; `sync.Map` for tiny caches with simple semantics. TTL configured.
- [ ] **Redis cache (`go-redis/redis/v9` or `redis/go-redis/v9`)**: shared across replicas; `SetEx` for TTL; `Pipeline` for batched ops.
- [ ] **Cache stampede protection**: hot keys with expensive regeneration use single-flight (`golang.org/x/sync/singleflight`) to dedupe in-flight; for distributed cache, Redis `SET NX EX` lock.
- [ ] **Cache invalidation explicit** - no caches that never expire and never invalidate; document staleness budget.
- [ ] **HTTP caching** (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GET endpoints via Gin middleware (`c.Header("Cache-Control", ...)`).
- [ ] **Response compression** (`gin-contrib/gzip`) for JSON responses > 2KB.
- [ ] **Per-request memoization**: store on `gin.Context.Set(key, val)` for values used by multiple middlewares in the same request.

### Step 9 - Asynq / Kafka / Background Work

_Skipped at `quick` depth unless the diff touches Asynq or Kafka._

Canonical patterns live in `go-messaging-patterns`. Apply the **review-scoped scan** below (branch on `Messaging:`).

**If Asynq:**

- [ ] **Idempotent + ID payloads**: re-fetch state, return early if done; payload uses IDs / primitives, never ORM models. `asynq.TaskID(businessKey)` for client-side dedup
- [ ] **`client.Enqueue()` AFTER commit**: never inside `db.Transaction(...)` - worker may pick up before commit. Capture inputs inside, dispatch after the closure returns nil
- [ ] **Retry policy + archive**: `asynq.MaxRetry(N)`, `asynq.Retention(...)`, `asynq.Timeout(...)` explicit; archived tasks surfaced via observability, not ignored
- [ ] **Queue priorities + Server concurrency**: time-sensitive tasks on dedicated higher-weight queue; `asynq.Config{Concurrency: N}` aligned to downstream capacity, not just CPU count

**If Kafka (franz-go):**

- [ ] **Consumer group + manual commits**: `franz.WithConsumerGroup(...)`; `cl.CommitRecords(...)` after successful processing - auto-commit drops messages on processing failure
- [ ] **Idempotent consumers**: at-least-once delivery (retries + rebalances) - same requirement as Asynq
- [ ] **Bounded in-flight**: `franz.MaxConcurrentFetches`, `franz.FetchMaxBytes` tuned for memory budget

### Step 10 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

This step is intentionally narrow - depth on observability belongs to `task-go-review-observability`. From a perf perspective, confirm only:

- [ ] Slow paths reachable from this PR have **some** instrumentation (OTel span via `go.opentelemetry.io/otel` or Prometheus histogram via `prometheus/client_golang`); if not, raise as a Low/Recommendation finding and delegate to `task-go-review-observability` for a proper instrumentation pass rather than dictating the design here.
- [ ] GORM `Logger: logger.Info` not enabled in prod; sqlx `LogQueries` (project-specific) not enabled in prod - if visible in the diff. If neither is in the diff, skip.
- [ ] `net/http/pprof` endpoint registered (typically only in non-prod or behind auth) so live profiling is possible.

Anything beyond presence/absence (sampling rates, span attributes, correlation IDs, multi-process metric aggregation) → `task-go-review-observability` owns it. Note the gap, do not duplicate the audit here.


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Go / Gin; data-access mix (GORM / sqlx / mixed / database/sql) and messaging library recorded before any specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Performance surface read directly (models / repositories, handlers, config, migrations, Asynq / Kafka producers / consumers, goroutine launch sites)
- [ ] `go-data-access` consulted for the project's data-access mix; N+1, multi-level N+1, `Preload` overfetch, projection, upsert idempotency checked
- [ ] `go-migration-safety` consulted for any migration change; `lock_timeout`, concurrent index, keyset-pagination backfill, expand-contract verified
- [ ] `go-concurrency` consulted; goroutine ownership / cancellation, bounded fan-out, mutex contention, channel patterns audited
- [ ] `go-messaging-patterns` consulted for any Asynq / Kafka change; idempotency, retry policy, post-commit dispatch, queue priorities verified
- [ ] Connection pool sizing validated against worker / replica concurrency model **if pool config is in the diff**; otherwise note as Low / Recommendation and skip rather than fail the check
- [ ] Allocation hotspots assessed when the diff touches hot loops or large structs
- [ ] Caching strategy assessed (in-process vs Redis, single-flight, invalidation explicit)
- [ ] Every finding states impact - measured (`p95: 800ms -> 120ms`) when pprof / APM data exists, estimated otherwise (`adds ~N queries per request at K rows` or `each leaked goroutine retains M bytes`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 4 + 5; `standard` ran 4-10; `deep` adds capacity guidance and load-test plan
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

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
- **Issue:** [what the problem is - name the Go idiom: N+1 via per-iteration `db.Find` inside a `for` loop, missing `Preload`, missing index, sync `crypto.bcrypt.GenerateFromPassword` on request goroutine, leaked goroutine via missing `<-ctx.Done()` select, Asynq `Enqueue` inside transaction, GORM `Find` without `Limit`, etc.]
- **Impact:** [estimated effect - e.g., "N+1 in OrderHandler.List adds ~200 queries per request at 100 orders" or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [specific Go change with code example - `Preload`, `errgroup` with `SetLimit`, `db.WithContext`, post-commit Asynq `Enqueue`, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Switch list endpoint to keyset pagination", "Add Redis cache for product catalog reads", "Move PDF generation to Asynq task", "Replace `encoding/json` with `easyjson`-generated marshallers for `OrderResponse`"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, schema migration, or load-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `db.Preload(\"Items.Product\")` to OrderRepository.List"]
2. **[Delegate]** [High] [scope: schema] - [one-line action, e.g., "Add concurrent composite index on (tenant_id, created_at) - spawn DB migration subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting issues without naming the Go idiom ("this is slow" vs "N+1 from per-iteration `db.Find` inside loop; replace with `db.Preload`")
- Recommending generic backend advice when a Go pattern applies (say "use `Preload`", not "use eager loading")
- Suggesting `go fn()` to "make it concurrent" without bounding (`errgroup.SetLimit`) and without a cancellation path (`<-ctx.Done()`)
- Suggesting `interface{}` / `any` to "make it flexible" - generics (Go 1.18+) replace most legitimate uses; `any` defeats compile-time safety
- Suggesting caching without an invalidation strategy
- Conflating performance review with general code review or security review - delegate those to their workflows
- Treating Asynq retries as a substitute for idempotency - retries with non-idempotent tasks cause double-charging / double-emailing
- Recommending `db.AutoMigrate` for schema changes - migrations belong in golang-migrate files
- Reporting "missing index" without confirming the column actually appears in a `Where` / `Order` / `Group` in the diff
- Recommending `sync.Map` as a default - `map + sync.RWMutex` is faster for typical concurrent maps; `sync.Map` only wins on specific access patterns
- Recommending `sync.Pool` for objects with a long lifetime - pools are for transient hot-path objects only; long-lived pooled objects defeat GC and create complexity
- Approving `panic` for "this should never happen" - return a wrapped error and let callers decide
