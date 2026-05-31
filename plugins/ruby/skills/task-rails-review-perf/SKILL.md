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

Rails-aware perf review naming ActiveRecord, Sidekiq, and caching idioms directly. Findings carry measured or estimated impact (latency, throughput, query count) with concrete Rails 7.2+ fixes. Stack-specific delegate of `task-code-review-perf`.

## When to Use

Reviewing a Rails PR for perf regressions; investigating a slow controller/view/job; pre-merge perf pass on AR/scope/job changes; quarterly N+1 sweep. Not for security, incident response, or feature design.

## Depth

| Depth      | What Runs                            |
| ---------- | ------------------------------------ |
| `quick`    | Steps 4 + 5 only                     |
| `standard` | All steps (default)                  |
| `deep`     | All steps + capacity + load-test     |

## Invocation

`/task-rails-review-perf [<branch>|pr-<N>] [quick|deep]` - current branch vs base; fails fast on trunk. When invoked as subagent with pre-read artifacts, Steps 1-3 are skipped.

## Workflow

### Step 1 - Load Behavioral Rules
Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack
Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Rails, redirect to `/task-code-review-perf`. Record the **database** (Postgres or MySQL) - DB-specific checks below apply only to the detected DB.

### Step 3 - Resolve the Diff
Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once. Skip if parent passed pre-read artifacts. Surface fail-fast verbatim and stop.

### Step 4 - ActiveRecord Hotspots

Use skill: `rails-activerecord-patterns`.

For N+1 on `update`/`save` paths (not list/index), also use skill: `rails-implicit-config-audit` - source is usually `touch:`, `autosave:`, `accepts_nested_attributes_for`, a callback, or missing `inverse_of` under `load_defaults <= 6.1`. Fix is to remove the source, not add `.includes`.

- [ ] **N+1** in controllers/serializers/views/helpers/jobs; preload at the boundary (controller, not serializer). Multi-level: `includes(line_items: :product)`. Service N+1: preload before passing AR collection in
- [ ] **Indexes** on every column in `where`/`order`/`group`; composite indexes match leftmost-prefix; FKs indexed
- [ ] `pluck`/`pick` over `.map(&:col)`; `exists?` over `any?`/`present?`
- [ ] Iteration over >1k records uses `find_each`/`in_batches`
- [ ] `counter_cache` for counts displayed with lists

### Step 5 - Migration Safety

Use skill: `rails-postgresql-migration-safety` **or** `rails-migration-safety` (MySQL) per detected DB - do not apply both.

- [ ] Large-table indexes built non-blocking for the detected DB (PG: `algorithm: :concurrently` + `disable_ddl_transaction!`; MySQL: `algorithm: :inplace` or `INSTANT`)
- [ ] Unique constraints at DB level, not just `validates :uniqueness`
- [ ] PG-only: partial indexes for selective boolean/enum filters

### Step 6 - Transactions and Async Boundaries

Single axis covering Sidekiq dispatch, mailers, HTTP, and lock scope. Use skill: `rails-sidekiq-patterns`.

- [ ] **No HTTP/S3/Stripe/SMTP/`.perform_async`/`deliver_now` inside `Model.transaction`** - move to `after_commit` (`after_commit_everywhere` for nested)
- [ ] Job arguments are primitive (IDs, not AR records)
- [ ] Idempotency guard at top of `perform`: re-fetch state, return early if done
- [ ] Retries bounded (`sidekiq_options retry: <N>`); queue priority explicit
- [ ] Long-running jobs split (single `perform` p50 < 30s); bulk dispatch uses `Sidekiq::Client.push_bulk` for >100 jobs

### Step 7 - Caching and Rendering

Skip when diff has no view, serializer, or cache change. Server-rendered: use skill `rails-view-templates`.

- [ ] Fragment cache keys include `updated_at` (`cache item`, pair with `belongs_to :parent, touch: true`); on hot keys add `race_condition_ttl`
- [ ] Per-user vs global cache scope - no authorized-data leakage
- [ ] HTTP caching (`fresh_when`, `stale?`) on read-heavy GETs
- [ ] Serializer associations included in the controller's `includes`
- [ ] Collection rendering: `render partial:, collection:, cached: true` for hot lists
- [ ] Helpers issuing SQL inside `each` -> move to a presenter or memoize
- [ ] Turbo Stream broadcasts in loops batched via `broadcast_replace_to` of a container

### Step 8 - I/O and Resource Ceilings

Skip the connection-pool checks unless the diff changes pool config, Puma/Sidekiq concurrency, or process count. Use skills: `rails-connection-pool-sizing` (when applicable), `rails-db-locking-patterns`, `rails-batch-processing-patterns`, `rails-work-splitter-patterns` (when explicit work-splitting is involved).

- [ ] **Pool sizing** (config-change PRs only): per-process `pool >= in-process thread count`; total backend processes under DB `max_connections` with 15-25% headroom; multiplexer (RDS Proxy / PgBouncer / ProxySQL) when >~200
- [ ] **HTTP clients** reused; timeouts on every external call; circuit breaker on flaky deps
- [ ] **Row locking** by primary key only; range scans under default RR on MySQL flagged (gap-lock); `SKIP LOCKED` claims hit a unique-index path
- [ ] **No `find_each` inside `Model.transaction`**; chunked-transaction shape is `in_batches(of: N) { |batch| Model.transaction { ... } }`, not whole-run or per-row
- [ ] **Chunk size** justified for row size + contention (500-1000 OLTP, 5000-10000 cold backfills); idempotent at chunk granularity
- [ ] **No HTTP/Redis/S3 inside chunk transactions**, no network in held locks
- [ ] **Cron rake tasks** guarded by leader lock (`with_advisory_lock`)
- [ ] **Lock-wait timeout** set when contention expected (PG: `lock_timeout`; MySQL: `innodb_lock_wait_timeout`)
- [ ] **Memory**: jemalloc or `MALLOC_ARENA_MAX=2` for Sidekiq and long rake tasks; `WorkerKiller` at 70-80%; memory-heavy queues at lower concurrency; `pluck(:id)` cursors when AR objects aren't needed

### Step 9 - Observability Hooks

One rule: if a new hot path lands without instrumentation, flag it. Concretely:

- [ ] Slow paths emit `ActiveSupport::Notifications` or APM custom spans; `query_log_tags_enabled = true` so APM attributes queries; Bullet enabled in non-prod (flag any change disabling it)

Depth owned by `task-rails-review-observability`; do not duplicate.

### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Print confirmation.

## Output Format

```markdown
## Rails Performance Review Summary

**Stack Detected:** Ruby <version> / Rails <version> / <database>
**Scope:** Backend (Rails)
**Overall:** Clean | Issues Found - [High/Medium/Low count]

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

- [ ] Steps 1-3 ran (or accepted from parent); diff/log read once; DB recorded
- [ ] Step 4: N+1, indexes, batching covered; for update/save N+1, source diagnosed via `rails-implicit-config-audit` before recommending `.includes`
- [ ] Step 5: migration-safety skill for the detected DB consulted on `db/migrate/` change
- [ ] Step 6: every transaction boundary checked for HTTP/job/mailer leak; idempotency verified
- [ ] Step 7: caching/rendering applied when diff touches views/serializers/cache
- [ ] Step 8: pool sizing skipped unless config changed; locking/batching/memory applied where relevant
- [ ] Step 9: instrumentation gap flagged on new hot paths
- [ ] Step 10: report via `review-report-writer`; confirmation printed
- [ ] Every finding states impact - measured when APM data exists, estimated otherwise (`adds ~N queries at K rows`)
- [ ] Findings ordered High > Medium > Low; Next Steps `[Implement]`/`[Delegate]` in same order

## Avoid

- Reporting issues without naming the Rails idiom
- Generic backend advice when a Rails pattern applies
- Caching without an invalidation strategy
- `joins` where `includes`/`preload` is correct (or vice versa)
- Treating Sidekiq retries as a substitute for idempotency
- Walking through DB-specific bullets for the wrong DB
- Re-running the connection-pool checklist when the PR doesn't touch pool config
