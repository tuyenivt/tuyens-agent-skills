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

| Depth      | What Runs                                                                                                                              |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `standard` | All steps (default); diff hunks plus immediate context |
| `deep`     | All steps; each touched file read in full; Step 8 ceiling checks run even without a config-change trigger; standalone runs emit a load-test plan as one `[Delegate]` `[Recommend]` Next Step line carrying tool, scenario, target p95, dataset scale - a value the user did not supply is assumed and marked `(assumed)` (even with no findings) |

## Invocation

`/task-rails-review-perf [<branch>|pr-<N>] [standard|deep] [--base <branch>]` - current branch vs base; fails fast on trunk. When invoked as subagent with pre-read artifacts, Step 2's detection and Step 3 are skipped (Step 1 still runs - behavioral rules are per-context); Step 2's recordings (database, versions) are still made from the artifacts.

**Investigation mode** (no PR/diff: slow endpoint, quarterly N+1 sweep): skip Step 3. Scope = the named actions plus every other action in a named file, the models, serializers, views, helpers, and jobs they touch, plus the pool / Puma / Sidekiq config governing them - Step 8's ceiling checks run in this mode whenever that config is in scope, since there is no diff to trigger them; run Steps 4-10 against current code. Impact numbers: use APM/log figures the user supplied; otherwise estimate and label them. When the reported symptom does not reproduce from the code as read, say so in `Notes:` and file what the code does show. Fill the Summary's `Target:` slot, skip `review-report-writer` checkpointing, and emit the report body as the response - no file is written. Every "skip when the diff ..." gate reads as "skip when the in-scope code has no such surface": gating removes atomic loads and rows with no matching code, never a row whose surface is present.

## Workflow

### Step 1 - Load Behavioral Rules
Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack
Use skill: `stack-detect`. Accept pre-confirmed from parent. Where the project's declared stack and its code disagree, record what the code does and note the divergence.  If not Rails, redirect to `/task-code-review-perf`. Record the **database** (MySQL 8.0.x, or `unknown` - on `unknown` read `config/database.yml` `adapter:`). Versions: `stack-detect` carries them only when `## Tech Stack` declares them - otherwise read Ruby / Rails from `.ruby-version` / `Gemfile.lock` and the MySQL patch level from ops docs or the server, else `unknown`; `rails-migration-safety`'s INSTANT / functional-index / CHECK gates read that patch level. An adapter other than `mysql2` / `trilogy`, or a server below 8.0, is outside this plugin's MySQL 8.0 scope: say so in `Notes:` and caveat the InnoDB-specific rows.

### Step 3 - Resolve the Diff
Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-perf`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch). Surface fail-fast verbatim and stop. Skip if parent passed pre-read artifacts.

**Round gate (standalone only).** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface: a valid `prior_checkpoint` whose `head_sha`, `base_ref`, and `base_sha` equal the captured ones and whose `depth` covers the requested one (`deep` covers `standard`) -> print `No new commits since prior perf review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 10 write overwrites the file) -> `round: 1`, no `prior_head_sha`. Then read the diff and log once.

### Step 4 - ActiveRecord Hotspots

Use skill: `rails-activerecord-patterns`.

For N+1 on `update`/`save` paths (not list/index), also Use skill: `rails-implicit-config-audit` - source is usually `touch:`, `accepts_nested_attributes_for`, a required `belongs_to`'s parent SELECT (below `load_defaults 7.1`, or when the FK changes), a callback, or a missing `inverse_of` on a scoped association below `load_defaults 7.0` (or, at any version, one whose `foreign_key:` / `:through` defeats automatic inversion). Fix is to remove the source, not add `.includes`. (`autosave:` on a loaded association adds one UPDATE per dirty child, not a load.)

- [ ] **N+1** in controllers/serializers/views/helpers/jobs; preload at the boundary (controller, not serializer). Multi-level: `includes(line_items: :product)`. Service N+1: preload before passing AR collection in
- [ ] **Ruby-side aggregation** (`group_by`/`sum`/`count` over loaded records) -> push into SQL (`group`, `sum`, grouped selects)
- [ ] **Indexes** on every column in `where`/`order`/`group`; composite indexes match leftmost-prefix; association columns without an FK constraint indexed (InnoDB auto-indexes FK constraint columns)
- [ ] `pluck`/`pick` over `.map(&:col)`; existence checks: `exists?` or blockless `any?` (equivalent on unloaded relations) over `.present?`/`count > 0`; on already-loaded associations prefer `any?`/`size` - `exists?`/`count` re-query
- [ ] Iteration over >1k records uses `find_each`/`in_batches`
- [ ] `counter_cache` for counts displayed with lists

### Step 5 - Migration Safety

Skip when nothing under `db/migrate/` changed (investigation mode: skip unless a named path includes a migration - never audit migration history). Use skill: `rails-migration-safety`. A verdict of `Safety: Blocked` (required tool or dependency absent) or `Maintenance Window` files as a finding tiered by the lock the operation would otherwise take, its Fix naming the out-of-band step (the tool to install, the window).

- [ ] `add_index`: `algorithm: :inplace` - online with concurrent DML for a B-tree secondary index (Rails emits no LOCK clause; an exact `LOCK=NONE` needs `execute`; a FULLTEXT or SPATIAL index add blocks writes, and a table's first FULLTEXT also rebuilds it); never `algorithm: :concurrently`, which the MySQL adapter rejects. Past ~100M rows any index build goes through gh-ost, or pt-online-schema-change when the table is an FK child or parent - gh-ost refuses both
- [ ] Unique constraints at DB level, not just `validates :uniqueness`
- [ ] A lone index on a low-selectivity boolean/enum flag rarely helps - composite it with a non-PK range/sort column (`[settled, created_at]`) - InnoDB already appends the PK, so `[settled]` serves `ORDER BY id` - or rely on the PK scan
- [ ] New flag column with a default makes the *entire table* eligible for the first consuming job/query - require a scope plan (or a per-row correction of the default) in the PR

### Step 6 - Transactions and Async Boundaries

Skip when the in-scope code has no job, transaction, or dispatch (a model callback that enqueues counts). Use skills: `rails-sidekiq-patterns`, `rails-transaction-patterns`.

- [ ] **No HTTP / S3 / Stripe / SMTP / `.perform_async` / `deliver_later` / `deliver_now` inside `Model.transaction`** - move to `after_commit` (`ActiveRecord.after_all_transactions_commit` on 7.2+ when the dispatch sits inside a caller's transaction; the `after_commit_everywhere` gem is the pre-7.2 form). An Active Job `perform_later` / `deliver_later` deferred to commit by `enqueue_after_transaction_commit`, or Sidekiq `perform_async` under `Sidekiq.transactional_push!`, is not a finding - read the setting per `rails-transaction-patterns`; when it is not in evidence, file the finding and name the setting to check in its Fix.
- [ ] Job arguments are primitive (IDs, not AR records)
- [ ] Idempotency guard at top of `perform`: re-fetch state, return early if done
- [ ] Retries bounded through one channel - `sidekiq_options retry: <N>` on a `Sidekiq::Job`, `retry_on ... attempts:` on an Active Job (on the Sidekiq adapter also `sidekiq_options retry: 0`, or Sidekiq adds its own 25 after `retry_on` gives up; Solid Queue retries nothing on its own); queue priority explicit
- [ ] Long-running jobs split (single `perform` under ~5 min per `rails-sidekiq-patterns`; a request-path job p50 < 30s); bulk dispatch for >100 jobs uses `Sidekiq::Client.push_bulk` (`Sidekiq::Job`) or `ActiveJob.perform_all_later` (Active Job)
- [ ] Scheduled jobs whose runtime can exceed their cadence carry an overlap guard (uniqueness lock or leader lock)

### Step 7 - Caching and Rendering

Skip when the diff has no view, serializer, or cache change. An API-only controller shaping its own response (`render json:` with `as_json`, `include:`, or a hand-built hash) is a serializer surface for this gate. Server-rendered: Use skill: `rails-view-templates`.

- [ ] Fragment cache keys include `updated_at` (`cache item`, pair with `belongs_to :parent, touch: true`); `race_condition_ttl` does **not** apply here - it is a `Cache::Store#fetch` option requiring `expires_in`, and fragment caching goes through `read_fragment`/`write_fragment`; put it on a controller-side `Rails.cache.fetch` for the expensive aggregate instead
- [ ] Per-user vs global cache scope - no authorized-data leakage
- [ ] HTTP caching (`fresh_when`, `stale?`) on read-heavy GETs
- [ ] Serializer associations included in the controller's `includes`
- [ ] Collection rendering: `render partial:, collection:, cached: true` for hot lists (a lambda key when `locals:` vary the output - `cached: true` keys on the record alone)
- [ ] Helpers issuing SQL inside `each` -> preload at the boundary or push into SQL; memoize only a loop-invariant value
- [ ] Turbo Stream broadcasts in loops batched via one `broadcast_replace_later_to` of a container

### Step 8 - I/O and Resource Ceilings

Skip the connection-pool checks unless the diff changes pool config, Puma/Sidekiq concurrency, or process count (at `deep`, run them regardless - Depth table). Use skills: `rails-connection-pool-sizing` (whenever the pool-sizing row runs), `rails-concurrency-patterns` (threads, fibers / the `async` gem, `load_async`, or fan-out in scope), `rails-db-locking-patterns` (row locks, advisory locks, `SKIP LOCKED` claims), `rails-batch-processing-patterns` (batch or bulk iteration), `rails-work-splitter-patterns` (explicit work-splitting). Skip an atomic whose surface is absent; the rows below still run.

- [ ] **Pool sizing** (config-change PRs, or `deep`): per-process `pool == max_threads_in_that_process` (+ documented executor / Cable extras when `load_async` - live only once `async_query_executor` is set - or ActionCable share the process); AR checks out lazily, so an oversized pool reserves nothing at steady state - it removes the cap, letting a leak grow the process and blow the deployment-wide budget; deployment-wide connections - (web pods x max(`workers`, 1) x (`threads` + executor / Cable extras, 0 when neither runs in the process)) + (Sidekiq pods x processes x `concurrency`) + (Solid Queue pods x processes x (`threads` + 2), plus supervisor and dispatchers per pod) + cron / scheduled processes, summed per database server (logical databases on one server share it) - fit under `max_connections` minus the reserved CLI / ops slots with 25% headroom (15% only when the rolling-deploy peak is bounded and has been observed), at steady state and at the rolling-deploy peak; a multiplexer (RDS Proxy / ProxySQL) once backend processes (pods x workers, plus Sidekiq pods x processes) pass ~200 at deploy peak. A ceiling not in the repo is assumed (the provider's documented default for the instance class, cited), stated in the Fix and in Notes (`verify: max_connections unknown`), never skipped
- [ ] **HTTP clients** reused; timeouts on every external call; circuit breaker on flaky deps; a response that serves many requests unchanged (rates, partner catalog) cached with an expiry rather than fetched per request
- [ ] **Row locking** by primary key only; range scans under default RR on MySQL flagged (gap-lock); a `SKIP LOCKED` claim needs one composite index over the filter plus the order key (`(state, id)`) - a claim filters a non-unique state column, so no unique index serves it - and a per-transaction `isolation: :read_committed`; an indexed claim under RR still gap-locks
- [ ] **No `find_each` inside `Model.transaction`**; chunked-transaction shape is `in_batches(of: N) { |batch| Model.transaction { ... } }`, not whole-run or per-row. When the same loop also fails Step 4's batching bullet, file one finding anchored at the chunked-transaction fix
- [ ] **Chunk size** justified for row size + contention (500-1000 OLTP, 5000-10000 cold backfills); idempotent at chunk granularity
- [ ] **No HTTP / Redis / S3 inside chunk transactions**, no network in held locks
- [ ] **Cron rake tasks** guarded by leader lock (`with_advisory_lock`)
- [ ] **Lock-wait timeout** set when contention expected (`innodb_lock_wait_timeout`, default 50s)
- [ ] **Memory**: jemalloc or `MALLOC_ARENA_MAX=2` for Sidekiq and long rake tasks; `WorkerKiller` at 70-80%; memory-heavy queues at lower concurrency; `pluck(:id)` cursors when AR objects aren't needed

### Step 9 - Observability Hooks

No atomic is loaded here - these are inline checks; depth belongs to `task-rails-review-observability`.

If a new hot path lands without instrumentation, flag it (file under Quick Wins):

- [ ] Slow paths emit `ActiveSupport::Notifications` or APM custom spans; `query_log_tags_enabled = true` so APM attributes queries; Bullet enabled in non-prod (flag any change disabling it)

### Step 9.5 - Verify and Reconcile

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns, and fill the Summary's `Findings verified:` line from its tally in the atomic's Summary form; dropped rows appear only in the tally, never in the body. A finding anchored in a file the diff does not touch carries `_(pre-existing)_` even when verify attached no such group (an `Unverified` row carries only `_(unverified: ...)_`) - without it, reconcile marks such a finding `Addressed` (reverted to base state) without reading the file. Subagent runs skip the delegation - the parent verifies the merged set once - but still re-read each cited `file:line` before handing off. Investigation mode also skips it (the skill requires a diff; there is none): instead re-read each cited `file:line` at `HEAD`, drop findings the code does not support, and report `Findings verified: inline (no diff)`. On round 2+, after verification, re-project the prior report's findings - every tier, the file at the handle's `report_path` - into reconcile's parse shape - one `## High-Impact Findings` section, one `### [Label] file:line` heading per finding from its `Label:` line (the label alone - a trailing `_(carried from round <N>)_` group is re-emitted on the heading as its own group; when the prior report wrote no label, the one its tier maps to in Next Steps) and the `file:line` prefix of its Location line, keeping a `_(pre-existing)_` annotation on the heading (verify's combined `_(pre-existing; newly reachable via ...)_` is written as two groups, `_(pre-existing)_ _(newly reachable via ...)_` - reconcile matches `_(pre-existing)_` exactly), with its `Issue` line written as `Issue:` (the smell) - then Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D` entry. Its table, note line and tally render as `## Prior Round Reconciliation`; `Still open` and `Needs re-check` rows carry into their prior tier at their prior label with `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the Label value and the prior Location annotation kept - the table row and a Next Steps entry are its only other appearances, and a carried finding this round's own pass re-derives publishes once, in the findings sections, not twice. A carried finding cites its current `file:line` when the site moved (the table row keeps the prior one verbatim); one this round re-derives went through verify with the rest, one it did not re-derive is not verified and stays out of the tally. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried; the reconciliation table is the one place a label outside `[Must]` / `[Recommend]` is written. Subagent runs skip verification and reconciliation both - the parent verifies and reconciles its own merged set once.

### Step 10 - Write Report

Standalone runs (resolved diff): Use skill: `review-report-writer` with `report_type: review-perf` and every field the writer requires - `report_body` (the assembled body), `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the Step 3 round gate, `scope: +perf`, `depth` as invoked, `stack = ruby-rails`, `mode: full`, `round` and `prior_head_sha` from the round gate, and `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present. Emit the report body in chat, then the writer's confirmation line. Subagent runs (parent passed pre-read artifacts): skip the writer and return only `## Findings` with its tier sections and any `out of lens` lines - no Summary, no Recommendations, no Next Steps, no file - the parent owns the report. (Investigation mode skips the writer too and emits the body as the response - see Invocation.)

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

Fill rules: `Findings verified:` carries the verify tally on standalone runs and the literal `inline (no diff)` in investigation mode (subagent runs emit no Summary). Verify annotations appear on standalone runs only, except `_(unverified: <reason>)_`, which investigation mode also writes on a finding resting on code outside the repo; a finding sits in the section matching its severity while its `Label:` line carries the published label, so a `[Recommend]` inside a higher section is correct, not a mismatch to fix. `Target:` appears only in investigation mode (it replaces writer checkpointing); omit otherwise. **One defect, one finding.** Several checklist rows, or several call sites, that describe one underlying defect file once - at the site where the fix lands, with the other sites named in the Location line. Genuinely distinct defects at one site, with different fixes, stay separate. Anchor to the narrowest `file:line` the fix touches; a range only when the fix spans contiguous lines. There is no finding count to hit or stay under: file every defect that meets the severity bar and nothing that does not. Two findings are the same defect when one fix removes both; different fixes at one site, or one fix that only masks the second, are two.

```markdown
## Rails Performance Review Summary

- **Stack Detected:** Ruby <version> / Rails <version> / <database>
- **Scope:** Backend (Rails)
- **Depth:** standard | deep
- **Round:** <N>   {round 2+ only}
- **Target:** <path(s)>   {investigation mode only}
- **Overall:** Clean | Issues Found - [High/Medium/Low/Quick Win count, zeros included]
- **Steps skipped:** <each numbered step skipped, with its trigger - e.g. `Step 7 (no view / serializer / cache change)`; atomic loads a gate removed inside a step that ran are not listed; `none` when all ran>
- **Findings verified:** <per fill rules: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}` from `review-finding-verify` | inline (no diff)>
- **Notes:** <the Step 2 declared-vs-code divergence, each stated assumption (`verify: max_connections unknown`), the investigation-mode non-reproduction note, the handle's `notes` (base fallback); omit when none>

## Findings

Tier by effect on the reviewed path: **High** = the dominant cost, or an
unbounded growth in queries / memory / lock-hold with load; **Medium** = a measurable but
bounded cost; **Low** = a cost too small to notice today that the pattern will grow;
**Quick Win** = a Low-effect fix of one line or one option; tier by effect first, so a one-line `.includes` closing a High N+1 stays High.

### High Impact

- **Location:** [file:line] [+ the verify Annotation - `_(pre-existing)_` / `_(pre-existing; newly reachable via ...)_` / `_(unverified: <reason>)_` / `_(mechanism: <actual>)_`]
- **Label:** [Must] | [Recommend]   {the verified Label; else High -> Must, Medium / Low / Quick Win -> Recommend; a carried finding appends `_(carried from round <N>)_`}
- **Issue:** [Rails idiom named: N+1, missing index, mid-transaction enqueue]
- **Impact:** [estimated "N+1 in OrdersController#index adds ~200 queries at 100 orders" or measured "p95 800ms -> 120ms"]
- **Fix:** [specific Rails change with code; a multi-line snippet is a fenced block indented under this bullet]

### Medium Impact

[Same structure]

### Low Impact

[Same structure]

### Quick Wins

[Same structure]

_Omit sections with no findings; if all are omitted, state `No performance issues found.`_

## Prior Round Reconciliation

[table, note line and tally from `review-prior-findings-reconcile` - round 2+ standalone runs only; omit the section otherwise]

## Recommendations

[Structural: "Enable Bullet in staging", "Add query_log_tags", "counter_cache on Order#line_items_count"]

## Next Steps

Prioritized. Each `[Implement]` (localized, incl. a one-file migration fix) or `[Delegate]` (work leaving the PR's scope: cross-cutting refactor, coordinated schema change, load-test). `[Implement]` / `[Delegate]` and `[Must]` / `[Recommend]` are independent axes - a `[Delegate]` may carry `[Must]`. Order: Must > Recommend. Intent per finding: High Impact -> [Must]; Medium/Low/Quick Win -> [Recommend]; when the verify pass changed a finding's label, its verified `Label` wins over this mapping. No other label is written.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: schema] - [one-line action]

_Omit if no actionable findings and no `deep` load-test line._
```


**A defect this lens does not own is reported, never dropped.** Another lens's category, a plain correctness bug, or something a gate excluded but the reading surfaced: one `- **out of lens:** file:line - <the defect in one sentence> - owner: <workflow>` line, placed after the last tier section (Quick Wins included) and still inside `## Findings` (with no tier section, directly under the `No ... found.` line); owners are `task-rails-review` (correctness, architecture) and the other `/task-rails-review-*` lenses (security, observability, perf, reliability). Untiered, uncounted in `Overall`, absent from Next Steps; the parent drafts it as a finding. Atomics loaded by any step feed findings into this template; their own output blocks are not emitted. The exception is a defect that makes this lens's own findings unreachable or wrong (a query that always raises, a guard that never runs): that files here at its own severity, because it changes what the rest of the report means.

## Self-Check

- [ ] Steps 1-3 ran (or accepted from parent; investigation mode: Step 3 skipped, in-scope code read); `report_type: review-perf` passed; round decided from the handle before the diff was read (or the stop line printed); diff/log read once; DB recorded
- [ ] Step 4: N+1, indexes, batching covered; for update/save N+1, source diagnosed via `rails-implicit-config-audit` before recommending `.includes`
- [ ] Step 5: `rails-migration-safety` consulted on a `db/migrate/` change; `Blocked` / `Maintenance Window` verdicts filed with the out-of-band step
- [ ] Step 6: every transaction boundary checked for HTTP / job / mailer leak; idempotency verified
- [ ] Step 7: caching/rendering applied when diff touches views/serializers/cache
- [ ] Step 8: pool sizing ran at `deep` regardless, at `standard` only on a config change, and in investigation mode whenever the governing config is in scope; locking / batching / memory applied where relevant
- [ ] Step 9: instrumentation gap flagged on new hot paths
- [ ] Step 9.5: verify pass ran (inline in investigation mode; skipped as subagent - the parent verifies); tally or omission per fill rules; prior findings projected and reconciled on round 2+
- [ ] Step 10: report via `review-report-writer` (subagent: findings returned to parent; investigation mode: body emitted as the response); confirmation printed when the writer ran; every finding states impact - measured when APM data exists, estimated otherwise (`adds ~N queries at K rows`); findings tiered by impact; Next Steps `[Implement]`/`[Delegate]` ordered Must > Recommend; Summary `Steps skipped:` and `Notes:` filled; `out of lens` lines emitted for defects outside the lens; `deep` load-test line emitted on standalone runs

## Avoid

- Reporting issues without naming the Rails idiom
- Generic backend advice when a Rails pattern applies
- Caching without an invalidation strategy
- `joins` where `includes`/`preload` is correct (or vice versa)
- Treating Sidekiq retries as a substitute for idempotency
- Applying INSTANT / functional-index advice without the server's 8.0.x patch level
- Re-running the connection-pool checklist at `standard` depth when the PR doesn't touch pool config
