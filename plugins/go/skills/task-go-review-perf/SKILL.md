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

**Not for:** general review (`task-go-review`), security (`task-go-review-security`), pre-implementation (`task-go-implement`).

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | All steps |
| `deep` | Requested, handed down by `task-go-review`, or profiling data (pprof / OTel / benchmark) is available | All + `### Capacity & Load Plan` subsection under Recommendations |

Request deep by appending `deep` to the invocation (e.g. `/task-go-review-perf <branch> deep`). At `deep` the Capacity & Load Plan carries four things: current measured state per breached signal, the connection budget (`replicas * SetMaxOpenConns` against `max_connections - reserved`), projected post-fix numbers labelled as projections, and a numbered re-measure plan naming which signal confirms which fix.

**Whole-service sweep** (the quarterly N+1 / pool / leak pass, with no feature branch): when Step 2 fails fast on trunk, do not stop - skip the diff gate and run Steps 3-10 repo-wide at `HEAD` (Step 3's categories read in full, not per changed file); findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`; fill the Summary's `Target:` slot with what was swept.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-perf` | Current branch vs base; on trunk, runs the whole-service sweep above |
| `/task-go-review-perf <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-perf pr-<N>` | PR head fetched into local branch `pr-<N>` |

**Subagent runs** (e.g. spawned by `task-go-review`). The parent passes `base_ref`, `head_ref`, the pre-read diff and commit log, depth, the pre-confirmed stack, and the data-access mix. Step 2 is skipped whole (including its SHA capture - never re-run git), the verify pass in Step 10 is skipped, and Step 11 returns the Output Format below to the parent instead of writing. Derive `Messaging` from the diff and `go.mod` when the parent did not send it.

## Workflow

### Step 1 - Stack and Data Access

Use skill: `stack-detect`. Accept pre-confirmed from parent. Record `Data Access` and `Messaging`.

### Step 2 - Resolve Diff

Standalone only - skip the whole step, SHA capture included, when a subagent received the handle.

Use skill: `review-precondition-check`. Read diff + log once; reuse. Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

**Resolve the round now, before any analysis.** Stat `review-perf-<branch>.md` in the writer's output directory (sanitizing the branch name per `review-report-writer`). Absent or frontmatter-less -> `round: 1`. Present and valid -> `round = prior.round + 1`, with its `head_sha` as `prior_head_sha`. **When that `head_sha` equals the current head and the invocation asks for nothing more (no deeper depth, no sweep where the prior was a diff review), print `No new commits on <branch> since prior perf review at <sha_short>. Prior report unchanged.` and stop** - do not re-review and do not overwrite. Doing this at Step 11 instead wastes the whole pass and destroys the prior round's findings.

If it fails fast on trunk, switch to the whole-service sweep under **Depth** - that is the quarterly-sweep path, not a stop.

If the clean-tree gate fails and **the only untracked file is this workflow's own prior report** (`review-perf-<branch>.md`), the gate is tripping on the artifact the last run wrote; every round-2 review would be unreachable. Say so, treat the tree as clean, continue, and tell the user to gitignore the report path. Any other fail-fast: surface verbatim and stop.

### Step 3 - Read the Performance Surface

Cite real `file:line`. Open:

**GORM:** changed models (tags, associations); changed repos (`Find` / `First` / `Preload` / `Joins` / `Where` / `Order` / `Group` / `Select`); handlers/services for context propagation; `cmd/api/main.go` / `internal/db/db.go` for pool config and GORM `Logger`.

**sqlx:** changed queries (raw SQL, named, `In`, `Select`, `Get`, `NamedExec`); changed repos for `*Context` variants; `*sqlx.DB` setup; prepared statement reuse.

**Both:** `migrations/`; Asynq / Kafka producers + consumers; worker concurrency; new goroutines / `errgroup.Go` / `wg.Go`; channel patterns; `sync.Pool`; pool config wherever it lives (`internal/db/*.go`, `cmd/*/main.go`). Pool sizing needs two numbers the diff rarely carries - replica count (deploy manifest, `values.yaml`) and DB `max_connections` (`CLAUDE.md`, infra config). Read them; if still unknown, run the check and state the assumption in the finding rather than skipping it.

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
- [ ] **Pool sized:** `db.SetMaxOpenConns(N) * replicas <= DB max_connections - reserved` (GORM default unlimited). Severity comes from the arithmetic, not from whether the pool line is in the diff: when the diff changes either side of that inequality - the pool value, the replica count, or worker `Concurrency` - anchor the finding on the changed line, cite the unchanged constraint, and rate it on the measured or computed consequence. Only a pool that is untouched on both sides drops to a Recommendation
- [ ] **Prod-unsafe config:** GORM `Logger: logger.Info` in prod (every query at INFO); `db.Debug()` in hot path

### Step 5 - Indexes and Migrations

Use skill: `go-migration-safety` for changes in `migrations/`.

- [ ] Every `Where` / `Order` / `Group` column backed by an index
- [ ] Composite indexes match leftmost-prefix
- [ ] FK columns indexed (Postgres does not auto-index FKs)
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY`
- [ ] `SET lock_timeout = '3s'` before DDL on large tables
- [ ] Unique constraints at DB level, not just `gorm:"uniqueIndex"`
- [ ] Partial indexes for boolean/enum filters selecting a small subset
- [ ] No DDL on hot tables in a single migration (expand-then-contract)
- [ ] Backfill via keyset pagination, never `WHERE col IS NULL LIMIT N`
- [ ] DDL separated from DML
- [ ] `ALTER TYPE ... ADD VALUE` cannot run in a transaction
- [ ] Every `up` has a matching `down`
- [ ] No `db.AutoMigrate` in production

**Reasoning rule.** When the diff _adds_ an index, validate the index is needed (selectivity, shape), then assess safety. When the diff _adds a column_ that will be queried, flag the missing index proactively.

**Migration impact template.** State impact before approving DDL on a hot table, naming the lock the statement actually takes - `go-migration-safety` owns the lock-level table: a non-concurrent `CREATE INDEX` takes `SHARE` (blocks writes, allows reads), while `ALTER TABLE` DDL takes `ACCESS EXCLUSIVE` (blocks both). _"`CREATE INDEX` without `CONCURRENTLY` on a 40M-row table takes `SHARE` for 5-30 min at this scale; every write queues."_ If row count unknown, note "row count not in diff - confirm before deploy."

**Consolidation.** Group by the edit that fixes it, not by the row that caught it. Several safety rows failing in one migration version - no `CONCURRENTLY`, no `lock_timeout`, DDL not separated from DML, unbatched backfill - are **one** finding at the strongest severity listing the failed rows, and the version's `up` and `down` files count as one version. A defect whose fix is a **different** file (a missing index that needs its own new migration) stays a separate finding even when the same version exposed it.

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

Skip when `Messaging` is `none` and the diff adds no producer or consumer; mark the step N/A. Otherwise use skill: `go-messaging-patterns`.

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

**Checks that ran clean.** A checklist row that was evaluated and passed goes in the `## Verified Clean` section, naming the row and its evidence. A reader cannot otherwise tell "checked and fine" from "never checked", and on a well-tuned service that distinction is most of the review's value.

### Step 10.5 - Verify Findings

Applies to every finding in the review, not just Step 10's. Assign each draft finding its label first (High -> `[Must]`, Medium / Low -> `[Recommend]`), since `review-finding-verify` takes labelled findings and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - it de-escalates `[Must]` to `[Recommend]` on untouched pre-existing code, and that survives onto the finding heading and into Next Steps; never re-derive a label from the impact tier after this step. Carry its provenance annotation onto the heading and its tally into the Summary's `Findings verified` slot. Subagent runs skip this - the parent verifies the merged set once - and return findings tagged by tier alone.

**Overlap with a sibling lens.** When a finding is equally owned by `+Rel` (in-tx dual write, unbounded fan-out) or `+Obs` (missing instrumentation), keep it - do not drop it in anticipation of another subagent. Record the overlap in the finding's `Issue` line as `Also owned by: +Rel | +Obs` so the parent's Step 6 merge dedups deliberately rather than by chance.

### Step 11 - Write Report

Standalone only - subagent runs return findings in the Output Format to the parent, which writes the single merged report.

The round was resolved in Step 2; pass it through. The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.

Use skill: `review-report-writer` with `report_type: review-perf` and every required input: `report_body`, `branch` (from the handle), refs from the precondition handle, `base_sha`/`head_sha` from Step 2 (whole-service sweep: both = `HEAD`), `stack: go-gin`, `scope: +perf`, `depth` as resolved from the Depth table, `mode: full`, and the `round` / `prior_head_sha` resolved above. Write before ending; print confirmation.

## Self-Check

Mark a line N/A when the diff has no matching surface (no messaging, no migrations, no goroutine fan-out). A whole-service sweep marks the diff-worded lines N/A and runs the rest repo-wide.

- [ ] `behavioral-principles` loaded (or accepted from parent)
- [ ] Stack confirmed; data-access mix and messaging recorded
- [ ] `review-precondition-check` ran (or handle received); diff/log read once and reused; trunk fail-fast routed to the whole-service sweep rather than stopping
- [ ] For `pr-ref` mode: user-run fetch surfaced; ref existed before review continued
- [ ] When `head_matches_current` was false: user approval obtained (skipped when subagent)
- [ ] Performance surface read directly (models / repos, handlers, config, migrations, Asynq / Kafka, goroutine launch sites); replica count and `max_connections` resolved or assumed explicitly
- [ ] `go-data-access` consulted; N+1, multi-level, overfetch, projection, upsert idempotency checked
- [ ] `go-migration-safety` consulted; `lock_timeout`, concurrent index, keyset backfill, expand-contract verified; per-file findings consolidated
- [ ] `go-concurrency` consulted; ownership, fan-out, mutex contention, channels audited
- [ ] `go-messaging-patterns` consulted when messaging is present; idempotency, retry, post-commit, queue priorities
- [ ] Pool sizing rated on the arithmetic, anchored on whichever side of the inequality the diff changed
- [ ] Allocation hotspots assessed when diff touches hot loops / large structs
- [ ] Caching assessed (in-process vs Redis, single-flight, invalidation)
- [ ] Every finding states impact, labelled `measured` (observed today), `projected` (post-fix estimate), or `estimated` (derived from row counts) - never a post-fix number labelled measured
- [ ] Findings ordered by impact; `### Sequencing` names quick wins vs structural
- [ ] Depth honored: `standard` ran all; `deep` filled all four parts of the Capacity & Load Plan
- [ ] Next Steps with `[Implement]` / `[Delegate]` tags, ordered Must > Recommend
- [ ] Report written via `review-report-writer` with the round resolved from `review-perf-<branch>.md` (standalone only; subagent runs return findings to the parent); confirmation printed

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Fill rules.** `Data Access` carries the detected value with its version (`GORM 1.25`); write `mixed` only when two access layers are both in use, then name them (`mixed - GORM 1.25 + sqlx 1.4`). `Overall` counts by impact tier: `Issues Found - <N> High / <N> Medium / <N> Low`. `Findings verified` is omitted on subagent runs (the parent verifies once). `Target` appears only on a whole-service sweep.

**Impact tiers.** High = the finding accounts for a measured breach, or scales with request volume or row count so it degrades on its own (N+1, unbounded read, pool oversubscription, a lock or transaction held across I/O, an allocation source dominating the profile). Medium = a real cost that is bounded and does not grow (a fixed overfetch, a missing `*Context`, one unbatched write loop, an unclamped client parameter). Low = hardening with no current cost path, or a fix worth making while the file is open. A finding whose evidence is `estimated` rather than `measured` is not capped by that - the tier follows consequence, not evidence quality.

**Each finding is its own numbered block** under its impact heading, headed `#### <n>. [Label] file:line - <short title> _(provenance annotation, when Step 10.5 assigned one)_`, numbered continuously across tiers so Next Steps and Recommendations can cite `finding <n>`. The `[Label]` and any `_(pre-existing)_` / `_(unverified: <reason>)_` come from Step 10.5 verbatim; on subagent runs, which skip that step, derive the label from the tier instead. Medium and Low are separate headings, each omitted when empty.

**Impact is labelled by provenance.** `measured` = a number observed today (pprof, OTel, APM, query log). `estimated` = derived from row counts or cart sizes in the repo. `projected` = a post-fix target. A post-fix number is never labelled measured.

```markdown
## Go Performance Review Summary

- **Stack Detected:** Go <version> / Gin <version>
- **Data Access:** GORM <version> | sqlx <version> | database/sql | mixed - <both, named>
- **Messaging:** Asynq | Kafka | none
- **Scope:** Backend (Go)
- **Target:** <what was swept> _(whole-service sweep only; omit on a diff review)_
- **Depth:** standard | deep
- **Overall:** Clean | Issues Found - <N> High / <N> Medium / <N> Low
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped _(omit on subagent runs)_

## Findings

### High Impact

#### 1. file:line - <short title>

- **Issue:** [Go idiom: N+1 via per-iteration `db.Find`, missing `Preload`, missing index, sync `bcrypt` on request goroutine, leaked goroutine via missing `<-ctx.Done()`, Asynq `Enqueue` inside transaction]
- **Impact:** [measured: "552,914 calls, 418s DB time over the run" / estimated: "adds ~200 queries per request at 100 orders" / projected: "~4 queries after batching"]
- **Fix:** [Go change with code]

#### 2. file:line - <short title>

[Same block]

### Medium Impact

[Same blocks, numbering continues]

### Low Impact

[Same blocks, numbering continues]

_Omit empty sections._

## Recommendations

[Structural improvements not tied to a single finding]

## Verified Clean

Checks that ran and passed, with their evidence - instrumentation present, pool correctly sized, retry policy explicit. Top-level so a parent merging by section heading cannot drop it.

## Sequencing

Quick wins (single-file, mechanical) vs structural (change the shape of the path), each citing finding numbers, plus the order to land them when findings compound.

### Capacity & Load Plan

_(`deep` only - omit at `standard`.)_ Current measured state per breached signal; connection budget (`replicas * SetMaxOpenConns` vs `max_connections - reserved`); projected post-fix numbers, labelled projections; numbered re-measure plan naming which signal confirms which fix.

## Next Steps

Each tagged `[Implement]` (localized code change this team owns) or `[Delegate]` (schema/migration work, another lens, or a cross-team dependency), with `[scope: schema | observability | reliability | security | cross-service | ops]` on delegated items. Order: Must > Recommend.
Impact maps to intent: High -> [Must]; Medium / Low -> [Recommend].

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
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
