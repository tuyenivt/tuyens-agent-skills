---
name: task-rails-review-perf
description: Rails performance review: ActiveRecord N+1, query plans, Sidekiq throughput, caching, rendering, locking, connection pool.
agent: rails-performance-engineer
metadata:
  category: backend
  tags: [ruby, rails, performance, activerecord, sidekiq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing.

# Rails Performance Review

Rails-aware performance review naming ActiveRecord, Sidekiq, and caching idioms directly. Findings carry measured or estimated impact (latency, throughput, query count) with concrete Rails 7.2+ fixes. Stack-specific delegate of `task-code-review-perf` for Ruby/Rails.

## When to Use

- Reviewing a Rails PR or branch for perf regressions
- Investigating a slow controller, view, or Sidekiq job
- Pre-merge perf pass on changes touching ActiveRecord, scopes, job dispatch
- Quarterly N+1 / query-plan sweep against APM-flagged endpoints

**Not for:** general review (`task-code-review`), security (`task-code-review-security`), incident response (`/task-oncall-start`), feature design (`task-rails-implement`).

## Depth

| Depth      | When                                              | What Runs                                |
| ---------- | ------------------------------------------------- | ---------------------------------------- |
| `quick`    | Single endpoint or scope                          | Steps 3 + 4 only                         |
| `standard` | Default - full perf review                        | All steps                                |
| `deep`     | Profiling-driven (bullet/scout output)            | All steps + capacity + load-test         |

Default: `standard`.

## Invocation

| Form                               | Meaning                                             |
| ---------------------------------- | --------------------------------------------------- |
| `/task-rails-review-perf`          | Current branch vs base; fails fast on trunk         |
| `/task-rails-review-perf <branch>` | `<branch>` vs base (3-dot)                          |
| `/task-rails-review-perf pr-<N>`   | PR head fetched into local branch `pr-<N>`          |

When invoked as a subagent of `task-code-review-perf`, Step 2 is skipped - reuse parent's artifacts.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. If not Rails, redirect to `/task-code-review-perf`.

### Step 2 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once, reuse for all steps. Skip if running as subagent with pre-read artifacts. If `review-precondition-check` stops with a fail-fast message, surface verbatim and stop.

### Step 3 - ActiveRecord Hotspots

Use skill: `rails-activerecord-patterns`.

For N+1 surfacing on an `update`/`save` path (not a list/index), also use skill: `rails-implicit-config-audit`. The source may be `touch:` / `autosave:` / `accepts_nested_attributes_for` / a callback / missing `inverse_of` under `load_defaults <= 6.1`. Fix is to remove the source, not add `.includes`.

`.includes` / `preload` on an `update`/`save` action is suspect, not "a fix already in place". Controller fetch happens *before* save; loads triggered by `touch:` / `autosave:` / callbacks happen *during* save. Flag misdirected `.includes`.

- [ ] N+1 in controllers / serializers / views; every association touched in `each` is preloaded upstream. Serializer-driven N+1 is fixed on the controller
- [ ] Multi-level N+1: `includes(line_items: :product)` for nested `each`
- [ ] N+1 inside service objects: caller's preload contract doesn't extend through `Service.call(orders:)` - preload at the boundary
- [ ] Missing index on `where` / `order` / `group` columns
- [ ] `pluck`/`pick` over `.map(&:col)` when only a column is needed
- [ ] `exists?` (LIMIT 1) over `any?` / `present?`
- [ ] Iteration over >1k records uses `find_each` / `in_batches`; no `.all.each`
- [ ] `counter_cache` for counts displayed with lists
- [ ] Transactions tight: no HTTP / Sidekiq enqueues inside (use `after_commit`)

### Step 4 - Indexes and Migrations

Use skill: `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG).

- [ ] Every column in `where` / `order` / `group` backed by an index
- [ ] Composite indexes match leftmost-prefix of queries
- [ ] FKs have indexes
- [ ] Indexes on large tables: MySQL `algorithm: :inplace` (or `INSTANT` where supported); PG `algorithm: :concurrently` + `disable_ddl_transaction!`. `algorithm: :concurrently` raises on MySQL
- [ ] Unique constraints at the database level, not just `validates :uniqueness`
- [ ] **PG only**: partial indexes for boolean/enum filters; MySQL has no equivalent - flag `where:` in MySQL migrations

### Step 5 - Sidekiq and Jobs

Use skill: `rails-sidekiq-patterns`.

- [ ] Jobs dispatched **after** enclosing transaction commits (use `after_commit_everywhere` for nested) - never mid-transaction
- [ ] Job arguments primitive (IDs, not AR records)
- [ ] Idempotency guard at top of `perform`: re-fetch state, return early if done
- [ ] Retries bounded (`sidekiq_options retry: <N>`)
- [ ] Queue priority explicit
- [ ] Long-running jobs split (single `perform` p50 < 30s)
- [ ] Bulk dispatch uses `Sidekiq::Client.push_bulk` for >100 jobs
- [ ] No HTTP / S3 / Stripe inside `Model.transaction`

### Step 6 - Caching and Rendering

Server-rendered: use skill `rails-view-templates`. View-only diffs: queries fan out from a view live in the controller - re-apply Step 3.

- [ ] Per-row association access without preload - fix on controller side
- [ ] Fragment cache keys include `updated_at` (`cache item`, not `cache item.id`); pair with `belongs_to :parent, touch: true`
- [ ] Cache-stampede on hot keys: `Rails.cache.fetch(key, expires_in:, race_condition_ttl:)`
- [ ] Per-user vs global cache scope - no authorized data leakage
- [ ] HTTP caching (`fresh_when`, `stale?`) on read-heavy GETs
- [ ] Serializer associations included in controller's `includes`
- [ ] Collection rendering: `render partial:, collection:, cached: true` for hot lists
- [ ] Helper hot paths: helpers issuing SQL inside `each` - move to a presenter or memoize
- [ ] ViewComponent over partials rendered >50 times per request
- [ ] Turbo Stream broadcasts in loops batched via `broadcast_replace_to` of a container

### Step 7 - Connection Pool and External I/O

Use skill: `rails-connection-pool-sizing`.

- [ ] Per-process `pool >= in-process thread count` (Puma + 1-2 if `load_async`/ActionCable; Sidekiq pool >= concurrency)
- [ ] Deployment-wide total under DB `max_connections` with 15-25% headroom for rolling deploys
- [ ] Connection multiplexer (RDS Proxy / ProxySQL / PgBouncer) when total backend processes > ~200
- [ ] HTTP clients reused; timeouts on every external call; circuit breaker on flaky deps

### Step 8 - Locking and Work Splitting

Use skills: `rails-db-locking-patterns`, `rails-work-splitter-patterns`.

- [ ] MySQL row-locking: `with_lock` / `lock("FOR UPDATE")` by primary key only. Range scans under default RR flagged (gap-lock cascade)
- [ ] Cron rake tasks guarded by leader lock (`with_advisory_lock`)
- [ ] No network calls inside open transactions or held advisory locks
- [ ] No `find_each` inside `Model.transaction`
- [ ] `SKIP LOCKED` claims hit a unique-index path
- [ ] Batch fan-out: documented choice (modulo / `SKIP LOCKED` / shards-table)
- [ ] Isolation correct: default RR (MySQL) / RC (PG) with chunked transactions; per-transaction `isolation: :read_committed` only at specific call sites with rationale; no blanket per-connection RC unless documented
- [ ] `innodb_lock_wait_timeout` (MySQL) or `lock_timeout` (PG) at session level

### Step 9 - Batch Processing

Use skill: `rails-batch-processing-patterns`.

**Chunked-transaction shape:**

- [ ] No `Model.transaction { ... in_batches/find_each ... }` over a whole run (Mode A)
- [ ] No `find_each { |row| Model.transaction { row.update! } }` per-row commits (Mode B)
- [ ] Transaction boundary is one chunk: `in_batches(of: N) { |batch| Model.transaction { ... } }`
- [ ] Chunk size justified for row size + contention (500-1000 OLTP, 5000-10000 cold backfills, lower for big payloads)
- [ ] Idempotency at chunk granularity
- [ ] No HTTP / Redis / S3 calls inside chunk transactions

**Memory:**

- [ ] jemalloc or `MALLOC_ARENA_MAX=2` set for Sidekiq and long rake tasks
- [ ] Long tasks log RSS periodically
- [ ] Sidekiq `WorkerKiller` at 70-80% of container memory
- [ ] Memory-heavy queues run at lower `concurrency`
- [ ] `pluck(:id)` cursors over `find_each` when full AR objects aren't needed

### Step 10 - Observability

- [ ] Slow paths instrumented with `ActiveSupport::Notifications` or APM custom spans
- [ ] N+1 detection enabled in non-prod (Bullet) - flag any change disabling it
- [ ] Query log tags (`query_log_tags_enabled = true`) so APM attributes queries
- [ ] Slow-query inspection wired: MySQL `performance_schema.events_statements_summary_by_digest` / slow_query_log; PG `pg_stat_statements`
- [ ] Worker memory telemetry: Sidekiq + Prometheus exporter

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Print confirmation.

## Self-Check

- [ ] Stack confirmed; `review-precondition-check` ran (or handle received); diff/log read once
- [ ] When `head_matches_current` was false, explicit user approval obtained before review (skipped if parent gated)
- [ ] `rails-activerecord-patterns` consulted; N+1, multi-level, scope/index alignment checked
- [ ] For N+1 on update/save paths, `rails-implicit-config-audit` consulted before recommending `.includes`
- [ ] `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG) consulted for any `db/migrate/` change
- [ ] `rails-sidekiq-patterns` consulted; post-commit dispatch and idempotency verified
- [ ] `rails-connection-pool-sizing` consulted
- [ ] `rails-db-locking-patterns` consulted; lock-by-PK and isolation correctness verified
- [ ] `rails-work-splitter-patterns` consulted for any fan-out / batch parallelism change
- [ ] `rails-batch-processing-patterns` consulted; chunked-transaction shape and memory mitigations verified
- [ ] Caching strategy assessed (Russian-doll, low-level, HTTP); invalidation explicit
- [ ] For server-rendered apps: `rails-view-templates` consulted
- [ ] Every finding states impact - measured when APM data exists, estimated otherwise (`adds ~N queries at K rows`)
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Next Steps produced; each `[Implement]` / `[Delegate]` ordered High > Medium > Low
- [ ] Report written via `review-report-writer`; confirmation printed

## Output Format

```markdown
## Rails Performance Review Summary

**Stack Detected:** Ruby <version> / Rails <version>
**Scope:** Backend (Rails)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [Rails idiom named: N+1, missing index, mid-transaction enqueue]
- **Impact:** [estimated "N+1 in OrdersController#index adds ~200 queries at 100 orders" or measured "p95 800ms -> 120ms"]
- **Fix:** [specific Rails change with code]

### Medium Impact / Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural: "Enable Bullet in staging", "Add query_log_tags", "Counter_cache on Order#line_items_count"]

## Next Steps

Prioritized. Each `[Implement]` (localized) or `[Delegate]` (cross-cutting refactor, schema migration, load-test). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: schema] - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- Running state-changing git commands - the user runs these
- Reporting issues without naming the Rails idiom
- Generic backend advice when a Rails pattern applies
- Caching without an invalidation strategy
- Conflating performance with general or security review
- `joins` where `includes`/`preload` is correct (or vice versa)
- Treating Sidekiq retries as a substitute for idempotency
