---
name: task-rails-review-perf
description: Rails-specific performance review for ActiveRecord N+1, query plans, Sidekiq throughput, caching, and rendering hotspots. Use when reviewing a Rails PR or branch for perf regressions, or when a controller/job is slow. Stack-specific override of task-code-review-perf, invoked when stack-detect resolves to Ruby/Rails.
agent: rails-performance-engineer
metadata:
  category: backend
  tags: [ruby, rails, performance, activerecord, sidekiq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Rails Performance Review

## Purpose

Rails-aware performance review that names ActiveRecord, Sidekiq, and Rails caching idioms directly instead of routing through the generic backend adapter. Produces findings with measured or estimated impact (latency, throughput, query count) and concrete fixes using Rails 7.2+ patterns.

This workflow is the stack-specific delegate of `task-code-review-perf` for Ruby/Rails. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a Rails PR or branch for performance regressions
- Investigating a slow controller action, view, or Sidekiq job
- Pre-merge perf pass on changes touching ActiveRecord queries, scopes, or job dispatch
- Quarterly N+1 / query-plan sweep against APM-flagged endpoints

**Not for:**

- General Rails code review (use `task-code-review`)
- Security review (use `task-code-review-security` or its Rails delegate)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-rails-implement`)

## Depth Levels

| Depth      | When to Use                                                             | What Runs                                        |
| ---------- | ----------------------------------------------------------------------- | ------------------------------------------------ |
| `quick`    | Single endpoint or scope ("is this query ok?")                          | Steps 3 + 4 only; ActiveRecord + indexes         |
| `standard` | Default - full Rails perf review                                        | All steps                                        |
| `deep`     | Profiling-driven review with rack-mini-profiler / bullet / scout output | All steps + capacity guidance and load-test plan |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                         | Meaning                                                                                               |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-rails-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-rails-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-rails-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Ruby / Rails. If the detected stack is not Rails, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Rails 7.2+ idioms.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - ActiveRecord Hotspots

Use skill: `rails-activerecord-patterns` for the canonical patterns referenced below.

Inspect every changed `app/models/`, `app/controllers/`, `app/services/`, and `app/views/` file for:

- [ ] **N+1 in controller actions**: every association touched in a `each` (or in the response shape) is preloaded with `includes` (auto-pick), `preload` (separate IN-list query), or `eager_load` (single LEFT OUTER JOIN). Pick `eager_load` only when the join column appears in `where`/`order`; otherwise `preload` keeps the queries faster and simpler.
- [ ] **N+1 in serializers**: serializers (`ActiveModel::Serializer`, `Blueprinter`, `JSONAPI::Serializer`, `Jbuilder`) silently trigger N+1 when they reference an association the controller did not preload. The fix is on the _controller_ (add to `includes`), not in the serializer; alternatively, attach the preload contract to the serializer (e.g., `Blueprinter` `view` + a query object) so the controller cannot forget.
- [ ] **Multi-level N+1**: nested `each` over associations of associations (e.g., `orders.each { |o| o.line_items.each { |li| li.product.name } }`) - preload the full graph: `Order.includes(line_items: :product)`
- [ ] **N+1 inside service objects**: services that take a collection (e.g., `BulkRefund.call(orders:)`) and call `each` on associations - the controller's preload contract doesn't extend through the service unless the service preloads internally or accepts a pre-loaded relation. State the preload contract on the service's docstring or accept a relation argument and call `.includes(...)` at the boundary.
- [ ] **Missing scopes for filter/sort columns**: any `.where`, `.order`, or `.group` on a column without a backing index
- [ ] **`pluck` vs `select`**: when only one or two columns are needed, prefer `pluck`/`pick` to avoid hydrating models
- [ ] **`exists?` vs `present?`/`any?`**: existence checks must use `exists?` to issue a `LIMIT 1` query
- [ ] **`find_each` / `in_batches`** for any iteration over > 1k records
- [ ] **`counter_cache`** for any `count` displayed alongside a list (avoid `COUNT(*)` per row)
- [ ] **`enum` with integer mapping** (Rails 7+ default) - never store enum as string in hot paths
- [ ] **No `.all.each`** anywhere in production code paths
- [ ] **Transactions scoped tightly**: no HTTP calls or Sidekiq enqueues inside a transaction (use `after_commit` or `transaction.after_commit`)

### Step 4 - Indexes and Migrations

Use skill: `rails-migration-safety` for safe-migration checks on any change in `db/migrate/`.

- [ ] Every column referenced in `where` / `order` / `group` is backed by an index
- [ ] Composite indexes match the leftmost-prefix pattern of the queries
- [ ] Foreign keys have indexes (`add_reference :foo, :bar, foreign_key: true, index: true`)
- [ ] Indexes on large tables use `algorithm: :concurrently` and `disable_ddl_transaction!`
- [ ] Unique constraints are enforced at the database level (`add_index ..., unique: true`), not just `validates :uniqueness`
- [ ] Partial indexes used for boolean/enum filters that select a small subset (e.g., `where: "active IS true"`)

### Step 5 - Sidekiq and Background Jobs

Use skill: `rails-sidekiq-patterns` for retry/idempotency patterns.

Inspect changes under `app/jobs/`, `app/sidekiq/`, and any `.perform_later` / `.perform_async` callsite:

- [ ] Jobs are dispatched **after** the enclosing transaction commits (use `after_commit_on_create`, `after_commit`, or `Sidekiq.transactional_push`) - never enqueue mid-transaction
- [ ] Job arguments are primitive (IDs, not AR records) to avoid `DeserializationError` and bloated Redis payloads
- [ ] Idempotency guard at the top of `perform`: re-fetch state, check whether work was already done, return early if so
- [ ] Retries are bounded (`sidekiq_options retry: <N>`) - do not rely on the default 25 retries for non-idempotent jobs
- [ ] Queue priority assignment is explicit (no orphan jobs in the `default` queue for time-sensitive work)
- [ ] Long-running jobs are split (a single `perform` should target sub-30-second median latency at p50)
- [ ] Bulk dispatch uses `Sidekiq::Client.push_bulk` for > 100 jobs

### Step 6 - Caching and Rendering

For server-rendered apps (views beyond mailers), use skill: `rails-view-templates` for engine-specific rendering patterns and apply these checks to changed `.erb` / `.haml` / `.slim` files in addition to the cache checks below.

**View-only diffs**: when the diff touches only view files, the queries that fan out from the view live in the controller that feeds it - re-apply the relevant Step 3 checks (`includes`/`preload`, `counter_cache`, multi-level N+1) against that controller before concluding. View-side perf bugs almost never have view-side fixes.

View-side N+1 patterns to flag (the fix is upstream):

```slim
- @orders.each do |order|
  span = order.customer.name      / N+1 unless controller does .includes(:customer)
  span = order.line_items.count   / N COUNT queries; use counter_cache or pre-aggregate
  - order.shipments.each do |s|   / multi-level N+1; controller needs .includes(:shipments)
    span = s.tracking_number
```

Broken cache key (silent staleness):

```slim
/ Wrong - the id never changes, so the cache never invalidates after writes
- cache order.id do
  = render order

/ Right - cache_key_with_version includes updated_at; touch parents on child writes
- cache order do
  = render order
```

- [ ] Russian-doll caching (`cache @collection`, `cache item`) used in views that render large collections, with cache keys including `updated_at` and association timestamps (`belongs_to :parent, touch: true`)
- [ ] **Fragment cache keys include `updated_at`**: `cache item` (uses `cache_key_with_version`) is correct; `cache item.id` is broken - never invalidates
- [ ] Low-level caching (`Rails.cache.fetch`) used for expensive derived data, with explicit TTL and an invalidation strategy (touch parent on child write, or write-through on update)
- [ ] **Cache-stampede protection**: hot keys with expensive regeneration use `Rails.cache.fetch(key, expires_in: 5.minutes, race_condition_ttl: 30.seconds)` so concurrent expiries do not pile up against the source of truth
- [ ] Fragment caches keyed on the right scope (per-user vs. global) - no leakage of authorized data across users
- [ ] HTTP caching (`fresh_when`, `stale?`) on read-heavy GET endpoints
- [ ] No serializer (ActiveModel::Serializer, JSONAPI, Blueprinter, Jbuilder) loading associations not declared in `includes`
- [ ] **No view partial rendering an association inside an `each` without preload** - applies to all engines: `<% @orders.each do |o| %><%= o.customer.name %>` in ERB, `- @orders.each do |o|` + `= o.customer.name` in Slim/HAML. Fix on the controller side with `includes(:customer)`
- [ ] **Collection rendering with cache**: `render partial: 'order', collection: @orders, cached: true` is faster than per-item `cache` blocks for large lists (multi-key fetch in one Redis round-trip); flag missing `cached: true` on hot list pages
- [ ] **`render @orders` collection form**: each item must use the partial named for its class; verify the partial uses preloaded associations
- [ ] **Helper hot paths**: helpers called in tight `each` loops that issue queries (`current_user.can?(item)`, `item.shippable?` if it triggers SQL) - move to a presenter that takes a preloaded relation, or memoize per-request
- [ ] **ViewComponent over heavy helpers**: components compile templates once and are faster than `render partial:` for repeated UI; flag partials rendered > 50 times per request as candidates for ViewComponent migration
- [ ] **Turbo Stream broadcasts** during a loop (`broadcast_append_to` per item in a controller `each`) cause one WebSocket message per item - batch via `broadcast_replace_to` of a container or move to a single after-commit broadcast

### Step 7 - Concurrency and External I/O

- [ ] Connection pool sized correctly per process: web `DB_POOL >= RAILS_MAX_THREADS` (Puma threads per worker); Sidekiq runs as its own process so set its `DB_POOL >= sidekiq.concurrency` independently. The total connections at the database must accommodate `(puma_workers x RAILS_MAX_THREADS) + (sidekiq_processes x sidekiq.concurrency)` plus headroom for rails console / rake tasks
- [ ] HTTP clients (Faraday, HTTParty, Net::HTTP) reused, not instantiated per request
- [ ] Timeouts set on every external call (`open_timeout`, `read_timeout`)
- [ ] Circuit breaker (Stoplight, Semian) on flaky external dependencies
- [ ] No blocking I/O inside Puma worker threads beyond the configured timeout

### Step 8 - Observability for Perf

- [ ] Slow paths instrumented with `ActiveSupport::Notifications` or APM custom spans
- [ ] N+1 detection enabled in non-prod (Bullet gem) - flag any change that disables it
- [ ] Query log tags (`config.active_record.query_log_tags_enabled = true`) on so APM can attribute queries to controllers/jobs

## Self-Check

- [ ] Stack confirmed as Rails before any Rails-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] `rails-activerecord-patterns` consulted; N+1, multi-level N+1, scope/index alignment all checked
- [ ] `rails-migration-safety` consulted for any `db/migrate/` change; concurrent index and composite-index leftmost-prefix verified
- [ ] `rails-sidekiq-patterns` consulted for any job change; post-commit dispatch and idempotency guard verified
- [ ] Caching strategy assessed (Russian-doll, low-level, HTTP); invalidation explicit
- [ ] For server-rendered apps: `rails-view-templates` consulted; partial-render N+1, fragment cache key correctness, collection `cached: true`, helper hot paths, and Turbo Stream broadcast batching all checked against changed view files
- [ ] Every finding states impact - measured (`p95: 800ms -> 120ms`) when APM data exists, estimated otherwise (`adds ~N queries per request at K rows`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)

## Output Format

```markdown
## Rails Performance Review Summary

**Stack Detected:** Ruby <version> / Rails <version>
**Scope:** Backend (Rails)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [what the problem is - name the Rails idiom: N+1, missing index, mid-transaction enqueue, etc.]
- **Impact:** [estimated effect - e.g., "N+1 in OrdersController#index adds ~200 queries per request at 100 orders" or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [specific Rails change with code example - includes/preload/eager_load choice, after_commit dispatch, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Enable Bullet in staging", "Add query_log_tags for APM attribution", "Introduce counter_cache on Order#line_items_count"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, schema migration, or load-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `includes(:line_items, :customer)` to OrdersController#index"]
2. **[Delegate]** [High] [scope: schema] - [one-line action, e.g., "Add concurrent composite index on (tenant_id, created_at) - spawn DB migration subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting issues without naming the Rails idiom ("this is slow" vs "N+1 in serializer; preload `:line_items`")
- Recommending generic backend advice when a Rails-specific pattern applies (say "use `find_each`", not "use batch processing")
- Suggesting caching without an invalidation strategy (Russian-doll requires `touch: true` or it goes stale)
- Conflating performance review with general code review or security review - delegate those to their workflows
- Recommending `joins` where `includes`/`preload` is correct (or vice versa) - choose based on whether the join column is used for filtering vs. only for hydration
- Treating Sidekiq retries as a substitute for idempotency - retries with non-idempotent jobs cause double-processing
