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

# Go Performance Review

Go-aware review naming GORM `Preload` / `Joins` / `Select`, sqlx `In` / `NamedExecContext` / `SelectContext`, goroutine lifecycle, `context.Context` cancellation, `sync.Mutex` contention, allocation hotspots, pool sizing, Asynq / Kafka throughput, `golang-migrate` safety.

## When to Use

- Go/Gin PR or branch perf regression review
- Slow endpoint / Asynq task / Kafka consumer investigation
- Pre-merge perf pass on ORM queries, goroutine fan-out, channels, allocation paths
- Quarterly N+1 / pool / leak sweep

**Not for:** general review (`task-go-review`), security (`task-go-review-security`), pre-implementation (`task-go-implement`).

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format; they are rule sets here, and only this skill's Output Format is emitted. Where a check below and a loaded atomic disagree, the atomic's fact wins (`go-data-access` owns the pool arithmetic, `go-migration-safety` the lock-level table).

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | All steps |
| `deep` | Requested, handed down by `task-go-review`, or profiling data (pprof / OTel / benchmark output, including snapshots committed to the repo or an incident doc) is available | All + `### Capacity & Load Plan` under Sequencing |

Request deep by appending `deep` to the invocation (e.g. `/task-go-review-perf <branch> deep`).

**Whole-service sweep** (the quarterly N+1 / pool / leak pass, with no feature branch). When Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-14 repo-wide at `HEAD` (Step 12 confirmation-only, Step 13 on round 2+); Step 4's categories are read in full, not per changed file, and findings cite current code. Three things the sweep changes:

- **Writer inputs.** The fail-fast returns no handle, so resolve them here: `branch` = `base_ref` = `head_ref` = the trunk name; `base_sha` = `head_sha` = the full `git rev-parse <trunk>` - when the current branch is not the trunk, stop and ask the user to check out the trunk or name a feature branch; `scope` / `stack` as on a diff review. The fail-fast also returns no `prior_checkpoint`: read the frontmatter of `review-perf-<sanitized trunk>.md` in the repo root yourself, with `review-precondition-check`'s filename and validity rules, and use it as `report_path` / `prior_checkpoint` for Step 3's round paragraph and Step 13; Step 13's `diff` / `name_status` then span `<prior_head_sha>...<trunk sha>` with `<prior_head_sha>` as the reconciler's `base_ref`, overriding its full-range inputs: a sweep has no base, so the commits since the prior sweep separate touched files from untouched ones.
- **Verify attribution.** Run `review-finding-verify` for confirmation only, with an empty `diff`, against the code at `HEAD`; skip its attribution and de-escalation. Labels come from the tier; every heading carries `_(pre-existing)_` plus any annotation the confirmation returned. Tally `<N> confirmed, - reattributed, <U> unverified, <K> dropped`.
- **Depth.** A sweep defaults to `deep`. Fill the Summary's `Target:` slot with what was swept.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-perf` | Current branch vs base; on trunk, runs the whole-service sweep above |
| `/task-go-review-perf <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-perf pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs fetch) |

**Subagent runs** (e.g. spawned by `task-go-review`). The parent passes the `review-precondition-check` handle, `base_ref` / `head_ref`, `base_sha` / `head_sha`, the pre-read diff and commit log, depth, the pre-confirmed stack, and the data-access mix. Step 3 is skipped whole - never re-run git. Steps 12 and 13 are skipped (the parent verifies and reconciles the merged set once): labels come from the tier (High -> `[Must]`, Medium / Low -> `[Recommend]`), a finding whose cited line the diff did not add carries `_(pre-existing)_`, plus `_(unverified: <reason>)_` when Step 4 assigned it, and no `newly reachable via` (the parent's verify adds that) so the parent's verify pass starts from it, and the `Findings verified` and `Round` lines are omitted. Step 14 returns the entire Output Format - Summary (`Depth` as the parent passed it), Findings, Out of Lens, Recommendations, Verified Clean, Sequencing (with the Capacity & Load Plan at `deep`), Next Steps - instead of writing. Derive `Messaging` from the diff and `go.mod` when the parent did not send it.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. A subagent loads it too, unless the spawning prompt inlined its Rules.

### Step 2 - Stack and Data Access

Use skill: `stack-detect`. Accept pre-confirmed from parent. Versions come from `go.mod` - the Go version from the `go` directive, Gin / GORM / sqlx from the `require` lines - and override any version a `## Tech Stack` line declared (this step's one departure from `stack-detect`'s instruction-file precedence). `Data Access` is GORM / sqlx / database/sql, or `mixed - GORM <v> + sqlx <v>` when both are required. `Messaging` is `Asynq`, `Kafka`, `Asynq + Kafka`, or `none`, from `go.mod`: `hibiken/asynq` for Asynq; `twmb/franz-go`, `IBM/sarama` (`Shopify/sarama` before v1.40.0), `segmentio/kafka-go` or `confluentinc/confluent-kafka-go` for Kafka.

### Step 3 - Resolve Diff and Round

Standalone only - skip the whole step, SHA capture included, when a subagent received the handle.

Use skill: `review-precondition-check` with `report_type: review-perf`. A trunk fail-fast switches to the whole-service sweep under **Depth**; any other fail-fast: surface verbatim and stop. Read diff, log and `git diff --name-status <base_ref>...<head_ref>` once; reuse. Capture `base_sha = git rev-parse <base_ref>` and `head_sha = git rev-parse <head_ref>` (full SHAs). The writer's `branch` is the handle's `head_short_name`.

**Resolve the round from the handle, before any surface is read.** No `prior_checkpoint`, or `prior_checkpoint: legacy` -> `round: 1`. Valid -> `round = prior_checkpoint.round + 1`, `prior_head_sha = prior_checkpoint.head_sha`. **When `prior_checkpoint.head_sha` equals the current `head_sha` and no deeper depth than `prior_checkpoint.depth` was requested, print `No new commits on <branch> since prior perf review at <sha_short>. Prior report unchanged.` and stop** - do not re-review and do not overwrite.

### Step 4 - Read the Performance Surface

Cite real `file:line`. Open:

**GORM:** changed models (tags, associations); changed repos (`Find` / `First` / `Preload` / `Joins` / `Where` / `Order` / `Group` / `Select`); handlers/services for context propagation; `cmd/api/main.go` / `internal/db/db.go` for pool config and GORM `Logger`.

**sqlx:** changed queries (raw SQL, named, `In`, `Select`, `Get`, `NamedExecContext`); changed repos for `*Context` variants; `*sqlx.DB` setup; prepared statement reuse.

**Both:** `migrations/`; Asynq / Kafka producers + consumers; worker concurrency; new goroutines / `errgroup.Go` / `wg.Go`; channel patterns; `sync.Pool`; pool config wherever it lives (`internal/db/*.go`, `cmd/*/main.go`). Pool sizing needs numbers the diff rarely carries - replica count and surge per binary (deploy manifest, `values.yaml`), DB `max_connections` and the reserved slots (`CLAUDE.md`, infra config). Read them; when still unknown, run the check with `go-data-access`'s surge assumption (25% of replicas, rounded up) and 10 reserved slots, and mark each `(assumed)` in the finding rather than skipping it. A performance number from an incident doc or runbook is evidence when the tree still matches it; when the tree disagrees, the finding is `_(unverified: <reason>)_`.

**Defects outside the diff or the lens.** A defect on a line the diff did not add: in this lens and made newly reachable by the diff (a new endpoint calling an existing repository with an N+1) -> read the unchanged file and file a finding anchored on the defect, citing the new call site as the trigger (Step 12 attributes it); in this lens and untouched by the diff -> a finding at its tier label with `_(pre-existing)_` (Step 12 de-escalates it to `[Recommend]`; on a subagent run the parent's verify does), at most the three most consequential on a diff review (a sweep publishes every one), the rest one line each under `## Out of Lens`; owned by another lens (a dual write with no outbox is `+rel`, a missing span is `+obs`) -> `## Out of Lens` with `file:line` and the owning lens. A finding on this lens's path that a sibling lens also owns (an in-tx enqueue, unbounded fan-out) is kept here with `Also owned by: +rel | +obs` on its `Issue` line, so the parent's merge dedups deliberately. A finding that spans two changed files anchors on the line that executes the cost and names the other file in `Issue`.

### Step 5 - ORM Hotspots (GORM or sqlx)

Use skill: `go-data-access`. Skip the sqlx rows on GORM-only projects and vice versa.

- [ ] **N+1:** GORM `Preload` / `Joins` (multi-level: `Preload("Items.Product")`); sqlx batches via `sqlx.In(...)` + `db.Rebind`, never per-iteration `db.GetContext` over a parent list
- [ ] **Overfetch:** GORM `Preload("Items", func(db *gorm.DB) *gorm.DB { return db.Select("id", "order_id", "name") })` - the projection must include the foreign key; sqlx `SELECT id, name` over `SELECT *`
- [ ] **Unbounded reads:** list endpoints use keyset pagination with a deterministic order (`Where("id > ?", lastID).Order("id").Limit(N)`); `OFFSET` paging on a growing table is a High finding once the page depth is unbounded
- [ ] **Per-row loops:** GORM `CreateInBatches(items, 100)`, `Clauses(clause.OnConflict{DoNothing: true})`; sqlx `db.NamedExecContext(ctx, q, items)` with a slice (chunk at `65535 / columns` rows on PostgreSQL)
- [ ] **Existence checks:** `db.Select("id").Where(...).Limit(1).Find(&x)` + `RowsAffected` over fetch-then-`len`; `First` adds `ORDER BY` primary key and logs `ErrRecordNotFound`
- [ ] **`db.WithContext(ctx)` / sqlx `*Context`** - bare variants ignore `ctx.Done()`
- [ ] **`defer rows.Close()`** immediately after `QueryContext` / `QueryxContext`
- [ ] **Pool sized:** `sqlDB, _ := db.DB(); sqlDB.SetMaxOpenConns(N)` (the `database/sql` default is 0, unlimited), with `sum over binaries of ((replicas + maxSurge) * SetMaxOpenConns) < max_connections - reserved` - api and worker binaries counted separately. Severity comes from the arithmetic, not from whether the pool line is in the diff: when the diff changes either side of that inequality - the pool value, a replica count, or worker `Concurrency` - anchor the finding on the changed line, cite the unchanged constraint, and rate it on the computed consequence. A pool untouched on both sides is tiered by the same arithmetic and attributed `_(pre-existing)_`
- [ ] **Prod-unsafe config:** GORM `Logger: logger.Default.LogMode(logger.Info)` (or any logger at `logger.Info`) in prod; `db.Debug()` in a hot path; `db.AutoMigrate` in a production binary (High: unversioned, unreviewed DDL with no lock timeout on any boot where a model drifts from the schema)

### Step 6 - Indexes and Migrations

Use skill: `go-migration-safety` for changes in `migrations/`; it owns the lock-level table and the per-file rules. Checks this lens adds:

- [ ] Every `Where` / `Order` / `Group` column added or newly queried by the diff is backed by an index; composite indexes match the leftmost prefix; FK columns indexed (PostgreSQL does not auto-index FKs); partial indexes for boolean / enum filters selecting a small subset
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY` in a single-statement file with no `SET`; a file, up or down, taking `ACCESS EXCLUSIVE` or `SHARE ROW EXCLUSIVE` on a hot table opens with `SET LOCAL lock_timeout = '3s'`
- [ ] Unique constraints at DB level, not just `gorm:"uniqueIndex"`
- [ ] Expand-then-contract; DDL separated from DML; backfill via keyset pagination, never `WHERE col IS NULL LIMIT N`
- [ ] `ALTER TYPE ... ADD VALUE` (PG12+) may run in a transaction, but the new value is unusable until commit - no statement in the same file may reference it
- [ ] Every `up` has a matching `down`

**Reasoning rule.** When the diff _adds_ an index, validate the index is needed (selectivity, shape), then assess safety. When the diff _adds a column_ that will be queried, flag the missing index proactively.

**Migration impact template.** State impact before approving DDL on a hot table, naming the lock from `go-migration-safety`'s table: a non-concurrent `CREATE INDEX` takes `SHARE` (blocks writes, allows reads); most `ALTER TABLE` DDL takes `ACCESS EXCLUSIVE` (blocks both), while `ADD ... FOREIGN KEY ... NOT VALID` takes `SHARE ROW EXCLUSIVE` and `VALIDATE CONSTRAINT` takes `SHARE UPDATE EXCLUSIVE`. _"`CREATE INDEX` without `CONCURRENTLY` on a 40M-row table takes `SHARE` for 5-30 min at this scale; every write queues."_ If row count unknown, note "row count not in diff - confirm before deploy."

**Consolidation.** Group by the edit that fixes it, not by the row that caught it. Several safety rows failing in one migration version - no `CONCURRENTLY`, DDL not separated from DML, unbatched backfill, no `SET LOCAL lock_timeout` on its `ACCESS EXCLUSIVE` / `SHARE ROW EXCLUSIVE` files - are **one** finding at the strongest severity listing the failed rows, and the version's `up` and `down` files count as one version. A defect whose fix is a **different** file (a missing index that needs its own new migration, numbered after the highest version on the branch) stays a separate finding even when the same version exposed it.

### Step 7 - Goroutine Lifecycle and Concurrency

Use skill: `go-concurrency`.

**Impact heuristic.** A leaked goroutine retains the request `context`, `gin.Context`, DB connections, mutexes. Under load, leaks compound (100/sec for an hour = 360k zombies). Phrase as "compounding leak proportional to sustained traffic," not "this one request leaks."

- [ ] **Goroutine ownership + cancellation:** every `go fn()` has an owner (`errgroup.Group.Go`, `sync.WaitGroup`, Go 1.25+ `WaitGroup.Go`, worker pool with shutdown); blocking receive paired with `<-ctx.Done()`
- [ ] **Bounded fan-out:** `errgroup.SetLimit(N)` or `semaphore.NewWeighted`; unbounded exhausts pool / FDs / scheduler
- [ ] **`context.WithTimeout` / `WithDeadline`** on outbound calls (`http.Client` without `Timeout` is infinite)
- [ ] **HTTP clients package-level:** one shared `*http.Client` via constructor; a per-request `&http.Transport{}` is what defeats connection reuse (`MaxIdleConnsPerHost`)
- [ ] **`sync.Mutex` not held across I/O:** drop the lock before HTTP / DB / channel send. If serialization is needed: per-key mutex / `singleflight.Group`. Read-heavy maps use `sync.RWMutex`; `sync.Map` only for write-once / disjoint-key patterns
- [ ] **No CPU-heavy work on the request goroutine without profiling:** hashing, image processing, large JSON marshal -> Asynq / worker pool when latency-dominant
- [ ] **No external I/O inside `db.Transaction(...)`:** holds a pooled connection for the upstream's tail latency. Capture inputs; dispatch after `Transaction` returns nil

### Step 8 - Allocation Hotspots

- [ ] **Slice pre-allocation:** `make([]T, 0, n)` over `var s []T` then `append` in a known-capacity loop; `make(map[K]V, n)` avoids rehashing
- [ ] **`sync.Pool` for hot temporary objects** (byte buffers, large structs reused per request) - not for long-lived objects (defeats the pool)
- [ ] **`strings.Builder` over `+`** in loops
- [ ] **`json.Encoder` over `json.Marshal`** for streaming; when profiling shows `encoding/json` dominates: Go 1.25+ `encoding/json/v2` under `GOEXPERIMENT=jsonv2` (experimental), or code-generated `easyjson`
- [ ] **No reflection in hot paths** - type switch or generics
- [ ] **Scheduler overhead:** thousands of short-lived goroutines vs a worker pool with fixed workers

### Step 9 - Caching

- [ ] **In-process:** `ristretto` (TinyLFU admission, per-item TTL via `SetWithTTL`); `groupcache` only for immutable keys (no TTL, no invalidation - version the key instead); `map` + `sync.RWMutex` with an expiry field for tiny caches
- [ ] **Redis cache:** shared across replicas; `SetEx` for TTL; `Pipeline` for batched ops
- [ ] **Stampede protection:** hot keys with expensive regen use `golang.org/x/sync/singleflight`; distributed via Redis `SET NX EX` lock
- [ ] **Invalidation explicit** - document the staleness budget
- [ ] **HTTP caching** (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GETs via Gin middleware
- [ ] **Response compression** via `gzip.Gzip(gzip.DefaultCompression, gzip.WithMinLength(2048))` (gin-contrib/gzip v1.2.6+; earlier versions compress every response)
- [ ] **Per-request memoization** via `gin.Context.Set`

### Step 10 - Asynq / Kafka / Background Work

Skip when `Messaging` is `none` and the diff adds no producer or consumer; mark the step N/A. Otherwise use skill: `go-messaging-patterns`.

**Asynq:**

- [ ] **Idempotent + ID payloads:** re-fetch state, return early if done; payload uses IDs / primitives. `asynq.TaskID(businessKey)` as an enqueue option for client-side dedup
- [ ] **`client.Enqueue()` AFTER commit:** never inside `db.Transaction(...)`
- [ ] **Retry policy explicit:** `asynq.MaxRetry(N)` and `asynq.Timeout(...)` (defaults 25 and 30 min); archived tasks surfaced via observability. `asynq.Retention` governs completed tasks only
- [ ] **Queue priorities + Server concurrency:** time-sensitive work on a higher-weight queue; `asynq.Config{Concurrency: N}` aligned to downstream capacity and to the pool budget in Step 5

**Kafka (franz-go, package `kgo`; on sarama / kafka-go / confluent-kafka-go apply the same three checks with that client's commit and fetch settings):**

- [ ] **Consumer group + manual commits:** `kgo.DisableAutoCommit()` set, `cl.CommitRecords(ctx, ...)` after successful processing
- [ ] **Idempotent consumers** (at-least-once delivery)
- [ ] **Bounded in-flight:** `kgo.MaxConcurrentFetches(n)` (default unbounded) and `kgo.FetchMaxBytes(b)` tuned for memory

### Step 11 - Observability for Perf (delegation handoff)

Depth belongs to `task-go-review-observability`. Confirm only:

- [ ] Slow paths from this PR have **some** instrumentation (OTel span or Prometheus histogram); if not, raise a Low-impact finding (`[Recommend]`) and delegate
- [ ] GORM logger not at `logger.Info` in prod; sqlx query logging not in prod (only if in diff)
- [ ] `net/http/pprof` registered (non-prod or behind auth)

**Checks that ran clean.** A checklist row that was evaluated and passed goes in `## Verified Clean`, naming the row and its evidence.

### Step 12 - Verify Findings

Applies to every finding in the review. Assign each draft finding its label first (High -> `[Must]`, Medium / Low -> `[Recommend]`), since `review-finding-verify` takes labelled findings and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - it de-escalates `[Must]` to `[Recommend]` on untouched pre-existing code, and that survives onto the finding heading and into Next Steps. Carry its `Annotation` column verbatim onto the heading (every group it returned: `_(pre-existing)_`, `_(pre-existing; newly reachable via <file:line>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`) and its tally into the Summary's `Findings verified` slot; the tally counts this round's drafts only.

Subagent runs skip this step entirely (see Invocation); whole-service sweeps run confirmation only (see Depth).

### Step 13 - Reconcile Prior Findings (round 2+, standalone)

Skip on round 1. Otherwise read the prior report at the handle's `report_path` and project its findings into the reconciler's shape: `## High-Impact Findings` holding one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, label and `file:line` copied from the `#### <n>. [Label] file:line - <title>` heading, annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` becomes `_(pre-existing)_ _(newly reachable via X)_`). Use skill: `review-prior-findings-reconcile` with `prior_report` (the projection), `diff`, `name_status`, `head_sha`, and `head_files` (`git ls-tree -r --name-only <head_sha>`). Insert its table under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows re-enter `## Findings` under the impact heading they were last published under (re-tiered when this round re-drafted the defect and its cost grew), with the label and every annotation group they were last published with plus `_(carried from round <N>)_` (N = the round that first raised it, written once) on the heading; when this round re-drafted the same defect at the same site, publish only the re-drafted finding with that annotation appended. The table keeps the prior label and line verbatim.

### Step 14 - Write Report

Standalone only - subagent runs return the Output Format to the parent, which writes the single merged report.

Use skill: `review-report-writer` with `report_type: review-perf` and every required input: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3 (whole-service sweep: all five per the Depth clause), `stack: go-gin`, `scope: +perf`, `depth` as resolved from the Depth table, `mode: full`, and the `round` / `prior_head_sha` resolved in Step 3. Write before ending; print confirmation.

## Self-Check

Mark a line N/A with its reason when the diff has no matching surface (no messaging, no migrations, no goroutine fan-out), or when the invocation mode makes it inapplicable (subagent, sweep, round 1).

- [ ] Step 1: `behavioral-principles` loaded, or rules inlined in the spawning prompt
- [ ] Step 2: stack confirmed; versions from `go.mod`; data-access mix and messaging recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-perf` (or handle received; or trunk fail-fast routed to the sweep); diff, log and name-status read once; `base_sha` / `head_sha` captured; round resolved from the handle (sweep: from the self-read checkpoint); same-SHA no-op honoured; approval obtained when `head_matches_current` was false
- [ ] Step 4: performance surface read directly; replica count, surge, `max_connections` and reserved resolved or marked `(assumed)`; defects outside the diff or lens routed per the Step 4 rule; sibling overlap marked `Also owned by`
- [ ] Step 5: `go-data-access` applied; N+1, overfetch, pagination, batching, context, pool arithmetic anchored on the changed side, prod-unsafe config
- [ ] Step 6: `go-migration-safety` applied; indexes, `CONCURRENTLY`, `SET LOCAL lock_timeout`, expand-contract, backfill; lock named from its table; per-version findings consolidated
- [ ] Step 7: `go-concurrency` applied; ownership, fan-out, timeouts, shared client, mutex across I/O, I/O inside transactions
- [ ] Step 8: allocation hotspots assessed when the diff touches hot loops / large structs
- [ ] Step 9: caching assessed (in-process vs Redis, single-flight, invalidation, compression)
- [ ] Step 10: `go-messaging-patterns` applied when messaging is present (or N/A); idempotency, post-commit enqueue, retry policy, concurrency, manual commits, bounded fetches
- [ ] Step 11: instrumentation presence confirmed; clean rows recorded under `## Verified Clean`
- [ ] Step 12 (standalone): findings labelled before verify; labels and annotations carried verbatim; tally in the Summary (sweep: confirmation only)
- [ ] Step 13 (round 2+): prior report projected and reconciled with `head_sha`; table inserted; `Still open` / `Needs re-check` rows carried into Findings
- [ ] Step 14 (standalone): report written via `review-report-writer` with all checkpoint fields; confirmation printed. Subagent: Output Format returned, no file written
- [ ] Every finding states impact labelled `measured`, `estimated`, or `projected`; findings ordered by impact; `## Sequencing` names quick wins vs structural; `deep` filled all four parts of the Capacity & Load Plan
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Fill rules.** `Overall` counts by impact tier: `Issues Found - <N> High / <N> Medium / <N> Low`. `Findings verified` is omitted on subagent runs, its parenthetical when K is 0; a sweep writes `-` for reattributed. `Target` and `Review shape` appear only on a whole-service sweep. Placement is by tier and the label by Step 12 (Step 13 for carried findings): a High finding de-escalated to `[Recommend]` stays under `### High Impact`. `Depth` is this run's, whatever a prior round ran. Any field the repo cannot settle takes the value plus `(inferred from <evidence>)`.

**Impact tiers.** High = the finding accounts for a measured breach, or scales with request volume or row count so it degrades on its own (N+1, unbounded read, pool oversubscription, a lock or transaction held across I/O, an allocation source dominating the profile). Medium = a real cost that is bounded and does not grow (a fixed overfetch, a missing `*Context`, one unbatched write loop, an unclamped client parameter). Low = hardening with no current cost path, or a fix worth making while the file is open. The tier follows consequence, not evidence quality: `estimated` evidence does not cap it. **Impact is labelled by provenance.** `measured` = a number observed today (pprof, OTel, APM, query log). `estimated` = derived from row counts or cart sizes in the repo. `projected` = a post-fix target; never labelled measured.

**Each finding is its own numbered block** under its impact heading, headed `#### <n>. [Label] file:line - <short title> _(annotations)_` where the label is exactly one of `[Must]` / `[Recommend]` and, with the annotations, comes from Step 12 verbatim (Step 13 for carried findings; the subagent-run and sweep rules above on those runs). Numbering continues across tiers so Sequencing and Next Steps can cite `finding <n>`. Blank lines separate the field lines.

```markdown
## Go Performance Review Summary

- **Stack Detected:** Go <version> / Gin <version>
- **Data Access:** GORM <version> | sqlx <version> | database/sql | mixed - GORM <version> + sqlx <version>
- **Messaging:** Asynq | Kafka | Asynq + Kafka | none
- **Scope:** Backend (Go)
- **Review shape:** whole-service sweep at `HEAD` on <trunk>     {sweep only}
- **Target:** <what was swept>                                    {sweep only}
- **Depth:** standard | deep
- **Overall:** Clean | Issues Found - <N> High / <N> Medium / <N> Low
- **Round:** <N>                                                   {round 2 onward; omitted on subagent runs}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff)

## Prior Round Reconciliation     {round 2+ only; omit otherwise}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Findings

### High Impact

#### 1. [Must] file:line - <short title> _(annotations)_     {annotation groups only when the Fill rules assign any}

- **Issue:** [Go idiom: N+1 via per-iteration `db.Find`, missing `Preload`, missing index, sync `bcrypt` on the request goroutine, leaked goroutine via missing `<-ctx.Done()`, Asynq `Enqueue` inside a transaction; `Also owned by: +rel | +obs` when a sibling lens shares it]

- **Impact:** [measured: "552,914 calls, 418s DB time over the run" / estimated: "adds ~200 queries per request at 100 orders" / projected: "~4 queries after batching"]

- **Fix:** [Go change with code]

#### 2. [Must] file:line - <short title>

[Same block]

### Medium Impact / Low Impact

[Same blocks, numbering continues]

Omit empty sections. When every section is empty, write "No performance issues found."

## Out of Lens

[Defects another lens owns, and pre-existing in-lens defects beyond the three published - each with `file:line` and the owning lens. Omit when there are none.]

## Recommendations

[Structural improvements not tied to a single finding]

## Verified Clean

Checks that ran and passed, with their evidence - instrumentation present, pool correctly sized, retry policy explicit. Top-level so a parent merging by section heading cannot drop it.

## Sequencing

Quick wins (single-file, mechanical) vs structural (change the shape of the path), each citing finding numbers, plus the order to land them when findings compound.

### Capacity & Load Plan     {deep only}

Current measured state per breached signal; connection budget (`sum over binaries of ((replicas + maxSurge) * SetMaxOpenConns)` vs `max_connections - reserved`, assumptions marked); projected post-fix numbers, labelled projections; numbered re-measure plan naming which signal confirms which fix.

## Next Steps

Each tagged `[Implement]` (localized code change this team owns) or `[Delegate]` (schema/migration work, another lens, or a cross-team dependency), with `[scope: schema | observability | reliability | security | cross-service | ops]` on delegated items. Order: Must > Recommend. Each item carries its finding's label as published; one row per finding, naming a shared edit on the row rather than repeating it.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: schema] - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- `git fetch` / `git checkout` from this workflow
- Writing a report when invoked as a subagent - the parent owns it
- Reporting without naming the idiom ("this is slow" vs "N+1 from per-iteration `db.Find`"); generic advice when a Go pattern applies ("use `Preload`", not "use eager loading")
- "Missing index" without confirming the column appears in `Where` / `Order` / `Group`
