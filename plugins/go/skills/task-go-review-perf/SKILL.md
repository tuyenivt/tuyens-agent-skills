---
name: task-go-review-perf
description: Go performance review for GORM / sqlx N+1, goroutine leaks and unbounded fan-out, missing context cancellation, sync.Mutex contention, sync.Pool / allocation hotspots, connection pool sizing, Asynq / Kafka throughput, JSON marshalling cost, and migration safety. Stack-specific override of task-code-review-perf, invoked when stack-detect resolves to Go / Gin.
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

Use skill: `stack-detect` to confirm Go / Gin. If the detected stack is not Go, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Go 1.25+.

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

> If `Data Access: GORM` was recorded in Step 1, **skip the sqlx subsection entirely** below; do not scan it for non-applicable bullets. Likewise skip the GORM subsection on sqlx-only projects. The bifurcation exists for mixed codebases - on monoglot projects it should be one read, not two.

**If GORM** - use skill: `go-data-access`:

Inspect every changed model, repository, service, and handler for:

- [ ] **N+1 in queries**: any traversal of an association (`order.Items`) after a `Find` is preloaded with `db.Preload("Items").Find(...)` or `db.Joins("Items").Find(...)`. GORM's lazy access (`order.Items` triggering a query) is the smell - eager-load with `Preload` instead.
- [ ] **Multi-level N+1**: nested traversal across two associations (`order.Items` → `item.Product`) - resolve with chained `db.Preload("Items.Product").Find(...)`.
- [ ] **`Preload` overfetch**: pulling full child rows when only one column is needed - use `db.Preload("Items", func(db *gorm.DB) *gorm.DB { return db.Select("id", "sku") })` to bound payload size.
- [ ] **Missing indexes for filter/sort columns**: any field used in `Where` / `Order` / `Group` without `gorm:"index"` on the model or a `CREATE INDEX` migration.
- [ ] **`Find` without pagination**: any read of an unbounded collection - require `Limit` + `Offset` or keyset pagination (`Where("id > ?", lastID).Limit(N)`) for any list endpoint that can grow.
- [ ] **Existence checks**: `db.Select("id").Where(...).First(...)` over `db.Find(...)` then `len(rows) > 0`; for hot paths use raw `EXISTS` via `db.Raw("SELECT EXISTS(...)")`.
- [ ] **Bulk operations**: `db.CreateInBatches(items, 100)` over per-row `db.Create`; `db.Clauses(clause.OnConflict{DoNothing: true})` for idempotent bulk inserts; `db.Updates` / `db.Where(...).Updates(...)` for batch updates.
- [ ] **Upsert for idempotency**: `db.Clauses(clause.OnConflict{Columns: [...], DoUpdates: clause.AssignmentColumns([...])}).Create(...)` over `Find` + `if/else` create/update - races less, fewer round trips.
- [ ] **Transactions**: `db.Transaction(func(tx *gorm.DB) error {...})` (auto-rollback on error return) over manual `Begin` / `Commit` / `Rollback`. `db.Clauses(clause.Locking{Strength: "UPDATE"})` for row-level locks. Long transactions (HTTP I/O inside `tx`) hold a connection for the duration - extract I/O outside the closure.
- [ ] **Connection pool sizing**: `db.SetMaxOpenConns(N)`, `SetMaxIdleConns`, `SetConnMaxLifetime` documented; total `MaxOpenConns × replica count ≤ DB-side max_connections`. Default is unlimited - that's a foot-gun under load.
- [ ] **GORM logger in prod**: `Logger: logger.Default.LogMode(logger.Info)` flagged - logs every query at INFO; should be `logger.Warn` or `logger.Error` in prod, or use OTel instrumentation via `go-gorm/opentelemetry`.
- [ ] **`db.Debug()` left in code**: `db.Debug().Find(...)` enables per-query debug logging for that statement; harmless but not for production hot paths.

**If sqlx** - use skill: `go-data-access`:

- [ ] **N+1 in queries**: any traversal that issues a per-iteration `db.Get` / `db.Select` over a parent list - resolve with a single JOIN query or batch via `sqlx.In`.
- [ ] **`sqlx.In` for batch IN clauses**: `query, args, err := sqlx.In("SELECT * FROM orders WHERE id IN (?)", ids); query = db.Rebind(query)` - never `fmt.Sprintf("(%s)", strings.Join(...))`.
- [ ] **Prepared statements for repeated queries**: `db.PrepareNamed(...)` reused across calls in hot paths; per-call `db.NamedExec` re-parses the SQL.
- [ ] **`SelectContext` / `GetContext` / `NamedExecContext`**: every call uses the `Context` variant so cancellation propagates; bare `db.Select` ignores `ctx.Done()`.
- [ ] **Column projection**: `SELECT id, name FROM ...` to bound payload - default `SELECT *` returns all columns including large `text` / `bytea`.
- [ ] **Existence checks**: `SELECT EXISTS(SELECT 1 FROM ... WHERE ...)` over fetching the row and counting.
- [ ] **`defer rows.Close()` immediately after `db.QueryxContext` succeeds**: forgetting leaks a connection back to the pool.
- [ ] **Connection pool sizing**: `db.DB.SetMaxOpenConns(N)` etc. documented; same constraint as GORM.

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

Use skill: `go-concurrency` for canonical patterns.

Inspect changes touching goroutines, channels, `errgroup`, `sync` primitives, and worker pools:

- [ ] **Every goroutine has an owner**: `go fn()` in a request handler is a leak waiting to happen. Use `errgroup.Group.Go(...)` (returns error from group), `sync.WaitGroup` (or Go 1.25+ `WaitGroup.Go`), or a worker pool with explicit shutdown. Bare goroutine launches in long-running services are flagged.
- [ ] **Goroutine cancellation path**: every goroutine selects on `<-ctx.Done()` or has a clear shutdown signal; goroutines blocked on a channel send/receive with no possible counterpart are leaks. Pair every blocking receive with `select { case x := <-ch: ... case <-ctx.Done(): return ctx.Err() }`.
- [ ] **Bounded fan-out**: fan-out over a list uses a bounded `errgroup` with `g.SetLimit(N)` (Go 1.20+) or a semaphore (`golang.org/x/sync/semaphore`); unbounded `errgroup.Group.Go(...)` over a 10k-row list will exhaust DB connections / file descriptors / goroutine scheduler overhead.
- [ ] **`context.WithTimeout` / `WithDeadline` on every external call**: `ctx, cancel := context.WithTimeout(ctx, 500*time.Millisecond); defer cancel()`; explicit timeout per outbound HTTP / DB call beats relying on Go's defaults (which are effectively infinite for `http.Client` without `Timeout` set).
- [ ] **HTTP clients reused**: `http.Client` instance / `resty.Client` shared at package level (often via constructor), not instantiated per request - connection reuse via `Transport.MaxIdleConnsPerHost` matters at scale.
- [ ] **Channel buffer sizes intentional**: unbuffered `make(chan T)` is fine when synchronization is the goal; buffered `make(chan T, N)` with non-obvious `N` should have a comment justifying the size.
- [ ] **`sync.Mutex` held across I/O**: `mu.Lock(); db.Query(...); mu.Unlock()` serializes the I/O across all callers. Drop the lock before I/O; if state must be consistent across the I/O, use a different pattern (per-key mutex, optimistic locking, single-flight via `golang.org/x/sync/singleflight`).
- [ ] **`sync.RWMutex` for read-heavy maps**: `RLock` / `RUnlock` for reads; `Lock` / `Unlock` only for writes. `sync.Mutex` on a read-mostly cache forces unnecessary serialization.
- [ ] **`sync.Map` only when justified**: `sync.Map` is faster than `map + sync.Mutex` only for specific access patterns (write-once, read-many; disjoint key sets per goroutine). For typical concurrent maps, `map + sync.RWMutex` is faster.
- [ ] **No CPU-heavy work on the hot path without profiling**: hashing, image processing, large JSON marshalling on a request goroutine should be moved to an Asynq task or a worker pool when measured to dominate latency.
- [ ] **No external I/O inside a DB transaction**: `http.Client.Do(...)` / `client.Enqueue(...)` (Asynq) inside `db.Transaction(...)` holds a pooled connection for the network roundtrip. Under load this drains the pool faster than QPS would predict, and locked rows stay locked for the upstream's tail latency. Recommend: capture inputs inside the transaction, dispatch the side effect after `db.Transaction` returns nil.

> **Impact heuristic - blast radius of a leaked goroutine.** A leaked goroutine is not just memory - it holds references to the request `context`, `gin.Context`, captured variables (potentially including DB connections, mutexes, channels). Under sustained traffic, leaked goroutines compound: 100 leaks/sec for an hour = 360k zombie goroutines + their captured state, eventually triggering OOM or scheduler degradation. Phrase the impact as "compounding leak proportional to sustained traffic," not "this one request leaks."

> **Synchronous external dependency on the request path.** Even when the call uses `http.Client` correctly, a request to a critical-path service (fraud, auth, pricing) inherits the upstream's tail latency: your p99 = max(your work, upstream p99). Recommend async patterns (decision cache, circuit breaker via `gobreaker`, fire-and-forget via Asynq) when the call is non-blocking-business; recommend strict timeouts (`context.WithTimeout`) plus fallback values when blocking-business.

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

Use skill: `go-messaging-patterns` for canonical patterns.

**If Asynq:**

- [ ] **Tasks idempotent**: re-fetch state, check if work was done, return early. Pass IDs / simple types as `Payload`, never ORM models (lazy loads, stale data, serialization issues).
- [ ] **Task IDs for dedup**: `asynq.NewTask(typ, payload, asynq.TaskID(businessKey))` where business-key collisions are intentional (Asynq rejects duplicate `TaskID` while another exists).
- [ ] **Retry strategy declared**: `asynq.MaxRetry(N)`, `asynq.Retention(...)` per-task or via server config; `asynq.Timeout(...)` for per-task deadline.
- [ ] **Failed-tasks queue / archive**: tasks that exceed retries move to `archived` set; processor logic / observability surfaces them.
- [ ] **Queue priorities**: time-sensitive tasks on a dedicated queue with higher priority weight; mixed-priority on one queue starves urgent work.
- [ ] **`client.Enqueue()` AFTER the DB transaction commits**: dispatching inside `db.Transaction(func(tx *gorm.DB) error {...})` means the worker may pick it up before the row is visible.
- [ ] **`Server` concurrency** set explicitly via `asynq.Config{Concurrency: N}`; align with downstream capacity, not just CPU count.

**If Kafka (franz-go):**

- [ ] **Consumer groups for parallelism**: `franz.WithConsumerGroup(...)` so partitions are distributed across consumer instances.
- [ ] **Manual commits**: `cl.CommitRecords(...)` after successful processing - never auto-commit on a message that may fail processing (at-least-once delivery requires explicit commit).
- [ ] **Idempotent consumers**: same idempotency requirement as Asynq - retries / rebalances cause re-delivery.
- [ ] **Bounded in-flight**: `franz.MaxConcurrentFetches`, `franz.FetchMaxBytes` tuned for memory budget.

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
