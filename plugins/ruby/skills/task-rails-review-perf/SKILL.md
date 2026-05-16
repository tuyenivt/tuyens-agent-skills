---
name: task-rails-review-perf
description: Rails performance review: ActiveRecord N+1, query plans, Sidekiq throughput, caching, rendering hotspots.
agent: rails-performance-engineer
metadata:
  category: backend
  tags: [ruby, rails, performance, activerecord, sidekiq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing.

# Rails Performance Review

## Purpose

Rails-aware performance review naming ActiveRecord, Sidekiq, and Rails caching idioms directly. Produces findings with measured or estimated impact (latency, throughput, query count) and concrete fixes using Rails 7.2+ patterns.

Stack-specific delegate of `task-code-review-perf` for Ruby/Rails.

## When to Use

- Reviewing a Rails PR or branch for performance regressions
- Investigating a slow controller action, view, or Sidekiq job
- Pre-merge perf pass on changes touching ActiveRecord, scopes, or job dispatch
- Quarterly N+1 / query-plan sweep against APM-flagged endpoints

**Not for:**

- General Rails code review (use `task-code-review`)
- Security review (use `task-code-review-security`)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-rails-implement`)

## Depth Levels

| Depth      | When to Use                                                     | What Runs                                |
| ---------- | --------------------------------------------------------------- | ---------------------------------------- |
| `quick`    | Single endpoint or scope                                        | Steps 3 + 4 only                         |
| `standard` | Default - full Rails perf review                                | All steps                                |
| `deep`     | Profiling-driven review with bullet/scout output                | All steps + capacity guidance + load-test |

Default: `standard`.

## Invocation

| Invocation                         | Meaning                                                              |
| ---------------------------------- | -------------------------------------------------------------------- |
| `/task-rails-review-perf`          | Review current branch vs base; fails fast on a trunk branch          |
| `/task-rails-review-perf <branch>` | Review `<branch>` vs base (3-dot diff)                               |
| `/task-rails-review-perf pr-<N>`   | Review PR head fetched into local branch `pr-<N>`                    |

When invoked as a subagent of `task-code-review-perf`, Step 2 is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect`. If invoked as a delegate (parent already detected Rails), accept the pre-confirmed stack and skip re-detection. If not Rails, stop and tell the user to invoke `/task-code-review-perf` instead.

### Step 2 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read the diff and commit log once via `git diff <base>...<head>` and `git log <base>..<head>`, then reuse them for all subsequent steps. Skip if running as a subagent and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface it verbatim and stop. Do not run state-changing git commands.

### Step 3 - ActiveRecord Hotspots

Use skill: `rails-activerecord-patterns`.

For any N+1 surfacing on an `update`/`save` path (not a list/index), also use skill: `rails-implicit-config-audit` to check whether the source is `touch:` / `autosave:` / `accepts_nested_attributes_for` / a callback / missing `inverse_of` under `load_defaults <= 6.1`. The fix is to remove the source, not to add `.includes` in the controller.

- [ ] **N+1 in controllers / serializers / views**: every association touched in `each` is preloaded upstream. Serializer-driven N+1 is fixed on the controller, not the serializer
- [ ] **Multi-level N+1**: nested `each` over associations of associations - `includes(line_items: :product)`
- [ ] **N+1 inside service objects**: caller's preload contract doesn't extend through `Service.call(orders:)` - preload at the boundary or document the relation contract
- [ ] **Missing index on `where` / `order` / `group` columns**
- [ ] **Hydration waste**: `pluck`/`pick` instead of `.map(&:col)` when only a column is needed
- [ ] **Existence checks use `exists?`** (LIMIT 1), not `any?`/`present?`
- [ ] **Iteration over >1k records uses `find_each` / `in_batches`**; no `.all.each`
- [ ] **`counter_cache`** for any `count` displayed alongside a list
- [ ] **Transactions scoped tightly**: no HTTP / Sidekiq enqueues inside (use `after_commit`)

### Step 4 - Indexes and Migrations

Use skill: `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG).

- [ ] Every column referenced in `where` / `order` / `group` is backed by an index
- [ ] Composite indexes match the leftmost-prefix pattern of queries
- [ ] FKs have indexes
- [ ] Indexes on large tables use the right algorithm: MySQL `algorithm: :inplace` (or `INSTANT` for index ops where supported); PG `algorithm: :concurrently` + `disable_ddl_transaction!`. **`algorithm: :concurrently` raises on MySQL** - flag if seen
- [ ] Unique constraints at the database level, not just `validates :uniqueness`
- [ ] **PG only**: partial indexes for boolean/enum filters selecting a small subset. MySQL has no partial-index equivalent; flag `where:` clauses in MySQL migrations

### Step 5 - Sidekiq and Background Jobs

Use skill: `rails-sidekiq-patterns`.

- [ ] Jobs dispatched **after** the enclosing transaction commits (use `after_commit_everywhere` for nested transactions) - never enqueue mid-transaction
- [ ] Job arguments primitive (IDs, not AR records)
- [ ] Idempotency guard at the top of `perform`: re-fetch state, return early if done
- [ ] Retries bounded (`sidekiq_options retry: <N>`) - don't rely on the default 25 for non-idempotent jobs
- [ ] Queue priority assignment explicit
- [ ] Long-running jobs split (single `perform` targets sub-30-second p50)
- [ ] Bulk dispatch uses `Sidekiq::Client.push_bulk` for >100 jobs
- [ ] No network calls (Stripe, S3) inside `Model.transaction`

### Step 6 - Caching and Rendering

For server-rendered apps, use skill: `rails-view-templates`.

**View-only diffs**: queries that fan out from a view live in the controller - re-apply Step 3 against that controller.

- [ ] **Per-row association access without preload** in any engine - flag and fix on the controller side
- [ ] **Fragment cache keys include `updated_at`**: `cache item` is correct; `cache item.id` never invalidates. Russian-doll caching paired with `belongs_to :parent, touch: true`
- [ ] **Cache-stampede protection** on hot keys: `Rails.cache.fetch(key, expires_in:, race_condition_ttl:)`
- [ ] **Per-user vs global cache scope** - no authorized data leakage
- [ ] **HTTP caching** (`fresh_when`, `stale?`) on read-heavy GET endpoints
- [ ] **Serializer associations** included in the controller's `includes`
- [ ] **Collection rendering**: `render partial:, collection:, cached: true` for hot lists
- [ ] **Helper hot paths**: helpers issuing SQL inside `each` - move to a presenter or memoize
- [ ] **ViewComponent over partials** rendered >50 times per request
- [ ] **Turbo Stream broadcasts in loops**: batch via `broadcast_replace_to` of a container

### Step 7 - Connection Pool and External I/O

Use skill: `rails-connection-pool-sizing`.

- [ ] Per-process pool sized to in-process thread count (Puma `pool >= RAILS_MAX_THREADS`, +1-2 if `load_async`/Action Cable; Sidekiq `pool >= concurrency`)
- [ ] Deployment-wide total stays under DB `max_connections` with 15-25% headroom for the rolling-deploy window
- [ ] Connection multiplexer (RDS Proxy / ProxySQL / PgBouncer) when total backend processes exceed ~200
- [ ] HTTP clients reused, not instantiated per request
- [ ] Timeouts set on every external call (`open_timeout`, `read_timeout`)
- [ ] Circuit breaker (Stoplight, Semian) on flaky dependencies

### Step 8 - Locking and Work Splitting

Use skills: `rails-db-locking-patterns` and `rails-work-splitter-patterns`.

- [ ] **MySQL row-locking**: `with_lock` / `lock("FOR UPDATE")` paths lock by primary key only. Range scans under default RR flagged for review (gap-lock cascade)
- [ ] Cron rake tasks guarded by leader lock (`with_advisory_lock` gem)
- [ ] No network calls inside open transactions or held advisory locks
- [ ] No `find_each` inside `Model.transaction { ... }`
- [ ] `SKIP LOCKED` claim queries hit a unique-index path
- [ ] Batch fan-out documented choice (modulo / `SKIP LOCKED` / shards-table)
- [ ] **Isolation tiers correct**: default RR (MySQL) / RC (PG) with chunked transactions; per-transaction `isolation: :read_committed` only at specific call sites with rationale; no blanket per-connection RC unless documented
- [ ] `innodb_lock_wait_timeout` (MySQL) or `lock_timeout` (PG) at session level

### Step 9 - Batch Processing Safety

Use skill: `rails-batch-processing-patterns`.

**Chunked-transaction shape:**

- [ ] No `Model.transaction { ... in_batches/find_each ... }` over a whole batch run (Mode A)
- [ ] No `find_each { |row| Model.transaction { row.update! } }` per-row commits (Mode B)
- [ ] Transaction boundary is one chunk: `in_batches(of: N) { |batch| Model.transaction { ... } }`
- [ ] Chunk size justified for row size and contention (500-1000 OLTP, 5000-10000 cold backfills, lower for big payloads)
- [ ] Idempotency at chunk granularity
- [ ] No HTTP / Redis / S3 calls inside chunk transactions

**Memory:**

- [ ] jemalloc or `MALLOC_ARENA_MAX=2` set for Sidekiq and long rake tasks
- [ ] Long rake tasks log RSS periodically
- [ ] Sidekiq `WorkerKiller` at 70-80% of container memory limit
- [ ] Memory-heavy queues run at lower `concurrency`
- [ ] `pluck(:id)` cursors over `find_each` when full AR objects aren't needed

### Step 10 - Observability

- [ ] Slow paths instrumented with `ActiveSupport::Notifications` or APM custom spans
- [ ] N+1 detection enabled in non-prod (Bullet) - flag any change that disables it
- [ ] Query log tags (`config.active_record.query_log_tags_enabled = true`) so APM attributes queries
- [ ] **Slow-query inspection**: MySQL `performance_schema.events_statements_summary_by_digest` or slow_query_log; PG `pg_stat_statements`
- [ ] **Worker memory telemetry**: Sidekiq + Prometheus exporter

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Write the report to file before ending. Print the confirmation line.

## Self-Check

- [ ] Stack confirmed as Rails before any Rails-specific check applied
- [ ] `review-precondition-check` ran (or handle received from parent); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log read once and reused
- [ ] When `head_matches_current` was false, explicit user approval obtained before review (skipped if parent already gated)
- [ ] `rails-activerecord-patterns` consulted; N+1, multi-level N+1, scope/index alignment checked
- [ ] For N+1 on update/save paths, `rails-implicit-config-audit` consulted to identify the source (`touch:` / `autosave:` / nested-attributes / callback / missing `inverse_of`) before recommending `.includes`
- [ ] `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG) consulted for any `db/migrate/` change
- [ ] `rails-sidekiq-patterns` consulted; post-commit dispatch and idempotency verified
- [ ] `rails-connection-pool-sizing` consulted
- [ ] `rails-db-locking-patterns` consulted; lock-by-PK and isolation-tier correctness verified
- [ ] `rails-work-splitter-patterns` consulted for any fan-out / batch parallelism change
- [ ] `rails-batch-processing-patterns` consulted; chunked-transaction shape and memory mitigations verified
- [ ] Caching strategy assessed (Russian-doll, low-level, HTTP); invalidation explicit
- [ ] For server-rendered apps: `rails-view-templates` consulted
- [ ] Every finding states impact - measured (`p95: 800ms -> 120ms`) when APM data exists, estimated otherwise (`adds ~N queries per request at K rows`)
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Next Steps section produced; each item tagged `[Implement]` or `[Delegate]` ordered High > Medium > Low
- [ ] Report written to file via `review-report-writer`; confirmation printed

## Output Format

```markdown
## Rails Performance Review Summary

**Stack Detected:** Ruby <version> / Rails <version>
**Scope:** Backend (Rails)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [name the Rails idiom: N+1, missing index, mid-transaction enqueue]
- **Impact:** [estimated effect, e.g., "N+1 in OrdersController#index adds ~200 queries per request at 100 orders" or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [specific Rails change with code]

### Medium Impact / Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements: "Enable Bullet in staging", "Add query_log_tags", "Introduce counter_cache on Order#line_items_count"]

## Next Steps

Prioritized action list. Each tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting refactor, schema migration, load-test). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: schema] - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command - the user must run these
- Reporting issues without naming the Rails idiom ("this is slow" vs "N+1 in serializer; preload `:line_items`")
- Generic backend advice when a Rails-specific pattern applies
- Suggesting caching without an invalidation strategy (Russian-doll requires `touch: true`)
- Conflating performance review with general code review or security review
- `joins` where `includes`/`preload` is correct (or vice versa)
- Treating Sidekiq retries as a substitute for idempotency
