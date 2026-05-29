---
name: task-rails-review-perf
description: Rails performance review - ActiveRecord N+1, query plans, Sidekiq throughput, caching, rendering, locking, connection pool.
agent: rails-performance-engineer
metadata:
  category: backend
  tags: [ruby, rails, performance, activerecord, sidekiq, workflow]
  type: workflow
user-invocable: true
---

# Rails Performance Review

Rails-aware performance review naming ActiveRecord, Sidekiq, and caching idioms directly. Findings carry measured or estimated impact (latency, throughput, query count) with concrete Rails 7.2+ fixes. Stack-specific delegate of `task-code-review-perf`.

## When to Use

- Reviewing a Rails PR or branch for perf regressions
- Investigating a slow controller, view, or Sidekiq job
- Pre-merge perf pass on changes touching ActiveRecord, scopes, job dispatch
- Quarterly N+1 / query-plan sweep against APM-flagged endpoints

**Not for:** general review (`task-code-review`), security (`task-code-review-security`), incident response (`/task-oncall-start`), feature design (`task-rails-implement`).

## Depth

| Depth      | When                                              | What Runs                                |
| ---------- | ------------------------------------------------- | ---------------------------------------- |
| `quick`    | Single endpoint or scope                          | Steps 4 + 5 only                         |
| `standard` | Default                                           | All steps                                |
| `deep`     | Profiling-driven (Bullet/Scout output)            | All steps + capacity + load-test         |

Default: `standard`.

## Invocation

| Form                               | Meaning                                             |
| ---------------------------------- | --------------------------------------------------- |
| `/task-rails-review-perf`          | Current branch vs base; fails fast on trunk         |
| `/task-rails-review-perf <branch>` | `<branch>` vs base (3-dot)                          |
| `/task-rails-review-perf pr-<N>`   | PR head fetched into local branch `pr-<N>`          |

When invoked as a subagent with pre-read artifacts, Steps 1-3 are skipped.

## Workflow

### Step 1 - Load Behavioral Rules

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. If not Rails, redirect to `/task-code-review-perf`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once, reuse. Skip if parent passed pre-read artifacts. Surface fail-fast verbatim and stop.

### Step 4 - ActiveRecord Hotspots

Use skill: `rails-activerecord-patterns`.

For N+1 on `update`/`save` paths (not list/index), also use skill: `rails-implicit-config-audit`. Source may be `touch:`, `autosave:`, `accepts_nested_attributes_for`, a callback, or missing `inverse_of` under `load_defaults <= 6.1`. Fix is to remove the source, not add `.includes`. Misdirected `.includes` on update/save (controller fetch precedes save-triggered loads) is flagged, not "already fixed".

- [ ] N+1 in controllers / serializers / views; associations touched in `each` preloaded upstream. Serializer-driven N+1 fixed on the controller
- [ ] Multi-level N+1: `includes(line_items: :product)` for nested `each`
- [ ] N+1 inside service objects: caller's preload contract doesn't extend through `Service.call(orders:)` - preload at the boundary
- [ ] Missing index on `where`/`order`/`group` columns
- [ ] `pluck`/`pick` over `.map(&:col)` for single-column reads
- [ ] `exists?` over `any?`/`present?`
- [ ] Iteration over >1k records uses `find_each`/`in_batches`
- [ ] `counter_cache` for counts displayed with lists
- [ ] Transactions tight: no HTTP / Sidekiq enqueues inside (use `after_commit`)

### Step 5 - Indexes and Migrations

Use skill: `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG).

- [ ] Every column in `where`/`order`/`group` backed by an index; composite indexes match leftmost-prefix; FKs indexed
- [ ] Large-table indexes: MySQL `algorithm: :inplace` (or `INSTANT`); PG `algorithm: :concurrently` + `disable_ddl_transaction!`. `:concurrently` raises on MySQL
- [ ] Unique constraints at DB level, not just `validates :uniqueness`
- [ ] **PG only**: partial indexes for boolean/enum filters; flag `where:` in MySQL migrations

### Step 6 - Sidekiq and Jobs

Use skill: `rails-sidekiq-patterns`.

- [ ] Jobs dispatched **after** enclosing transaction commits (`after_commit_everywhere` for nested) - never mid-transaction
- [ ] Job arguments primitive (IDs, not AR records)
- [ ] Idempotency guard at top of `perform`: re-fetch state, return early if done
- [ ] Retries bounded (`sidekiq_options retry: <N>`); queue priority explicit
- [ ] Long-running jobs split (single `perform` p50 < 30s)
- [ ] Bulk dispatch uses `Sidekiq::Client.push_bulk` for >100 jobs
- [ ] No HTTP / S3 / Stripe inside `Model.transaction`

### Step 7 - Caching and Rendering

Server-rendered: use skill `rails-view-templates`. For view-only diffs whose queries fan out from the view, re-apply Step 4 in the controller.

- [ ] Fragment cache keys include `updated_at` (`cache item`, not `cache item.id`); pair with `belongs_to :parent, touch: true`
- [ ] Cache-stampede on hot keys: `Rails.cache.fetch(key, expires_in:, race_condition_ttl:)`
- [ ] Per-user vs global cache scope - no authorized data leakage
- [ ] HTTP caching (`fresh_when`, `stale?`) on read-heavy GETs
- [ ] Serializer associations included in controller's `includes`
- [ ] Collection rendering: `render partial:, collection:, cached: true` for hot lists
- [ ] Helpers issuing SQL inside `each` - move to a presenter or memoize
- [ ] Turbo Stream broadcasts in loops batched via `broadcast_replace_to` of a container

### Step 8 - Connection Pool and External I/O

Use skill: `rails-connection-pool-sizing`.

- [ ] Per-process `pool >= in-process thread count` (Puma + 1-2 if `load_async`/ActionCable; Sidekiq pool >= concurrency)
- [ ] Deployment-wide total under DB `max_connections` with 15-25% headroom
- [ ] Connection multiplexer (RDS Proxy / PgBouncer / ProxySQL) when total backend processes > ~200
- [ ] HTTP clients reused; timeouts on every external call; circuit breaker on flaky deps

### Step 9 - Locking, Batching, Memory

Use skills: `rails-db-locking-patterns`, `rails-work-splitter-patterns`, `rails-batch-processing-patterns`.

- [ ] Row-locking by primary key only (MySQL `with_lock` / `lock("FOR UPDATE")`); range scans under default RR flagged (gap-lock cascade)
- [ ] Cron rake tasks guarded by leader lock (`with_advisory_lock`); no network calls inside open transactions or held locks
- [ ] No `find_each` inside `Model.transaction`
- [ ] `SKIP LOCKED` claims hit a unique-index path
- [ ] Isolation correct: default RR (MySQL) / RC (PG) with chunked transactions; per-transaction `isolation: :read_committed` only with rationale
- [ ] Session-level `innodb_lock_wait_timeout` (MySQL) / `lock_timeout` (PG)
- [ ] **Chunked-transaction shape**: `in_batches(of: N) { |batch| Model.transaction { ... } }`, not whole-run or per-row commits
- [ ] Chunk size justified for row size + contention (500-1000 OLTP, 5000-10000 cold backfills)
- [ ] Idempotency at chunk granularity; no HTTP/Redis/S3 inside chunk transactions
- [ ] Memory: jemalloc or `MALLOC_ARENA_MAX=2` for Sidekiq and long rake tasks; `WorkerKiller` at 70-80% memory; memory-heavy queues at lower concurrency; `pluck(:id)` cursors when full AR objects aren't needed

### Step 10 - Observability Hooks

- [ ] Slow paths instrumented with `ActiveSupport::Notifications` or APM custom spans
- [ ] Bullet enabled in non-prod; flag any change disabling it
- [ ] `query_log_tags_enabled = true` so APM attributes queries
- [ ] Slow-query inspection wired: MySQL `events_statements_summary_by_digest` / slow_query_log; PG `pg_stat_statements`
- [ ] Sidekiq + memory telemetry via `sidekiq-prometheus-exporter` or APM gem

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Print confirmation.

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

[Structural: "Enable Bullet in staging", "Add query_log_tags", "counter_cache on Order#line_items_count"]

## Next Steps

Prioritized. Each `[Implement]` (localized) or `[Delegate]` (cross-cutting refactor, schema migration, load-test). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: schema] - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed (or accepted from parent)
- [ ] Step 3: `review-precondition-check` ran (or handle received); diff/log read once
- [ ] Step 4: `rails-activerecord-patterns` consulted; N+1, multi-level, scope/index alignment checked; for N+1 on update/save, `rails-implicit-config-audit` consulted before recommending `.includes`
- [ ] Step 5: migration-safety skill consulted for any `db/migrate/` change
- [ ] Step 6: `rails-sidekiq-patterns` consulted; post-commit dispatch and idempotency verified
- [ ] Step 7: caching strategy assessed; invalidation explicit; view-only diffs traced back to controller
- [ ] Step 8: `rails-connection-pool-sizing` consulted
- [ ] Step 9: locking, work-splitter, and batch-processing skills consulted; chunked-transaction shape and memory mitigations verified
- [ ] Step 10: observability hooks (instrumentation, query tags, slow-query, memory telemetry) verified
- [ ] Step 11: report written via `review-report-writer`; confirmation printed
- [ ] Every finding states impact - measured when APM data exists, estimated otherwise (`adds ~N queries at K rows`)
- [ ] Findings ordered by impact; Next Steps `[Implement]`/`[Delegate]` ordered High > Medium > Low

## Avoid

- Running state-changing git commands
- Reporting issues without naming the Rails idiom
- Generic backend advice when a Rails pattern applies
- Caching without an invalidation strategy
- `joins` where `includes`/`preload` is correct (or vice versa)
- Treating Sidekiq retries as a substitute for idempotency
- Conflating performance with general or security review
