---
name: task-rails-review-reliability
description: Rails reliability review - timeouts, Sidekiq idempotency/retries/dead-set, Stoplight breakers, AR pool bounds, after_commit dispatch, outbox.
agent: rails-reliability-engineer
metadata:
  category: backend
  tags: [ruby, rails, reliability, resilience, sidekiq, idempotency, outbox, workflow]
  type: workflow
user-invocable: true
---

# Rails Reliability Review

Rails-aware reliability review naming Faraday / `Net::HTTP`, Sidekiq, `Stoplight`, ActiveRecord locking, and `after_commit` idioms directly. Reliability = behavior under failure and saturation: what happens when a dependency is slow or down, load spikes, or a process crashes mid-operation. Findings name the failure mode and blast radius, with concrete fixes for Rails 7.2+.

Stack-specific delegate of `task-code-review-reliability`.

## When to Use

- Rails PR / branch adding or changing an integration point (Faraday / `Net::HTTP` client, Sidekiq job / ActiveJob, cron rake task)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and at-least-once safety
- Hardening after a near-miss; recurring resilience-debt sweep
- Dual-write / outbox / `after_commit` / consumer-retry correctness under failure

**Not for:** general Rails review (`task-rails-review`), perf optimization (`task-rails-review-perf`), observability wiring (`task-rails-review-observability`), security (`task-rails-review-security`).

## Seam With Adjacent Lenses

- **vs. Perf:** perf tunes the AR pool, Sidekiq concurrency, and queries for throughput; this lens verifies they are bounded and that exhaustion fails fast and degrades gracefully. A slow query is perf; the untimed query holding a pooled connection until it is killed is reliability.
- **vs. Observability:** obs owns the breaker-state metric and the fallback log line; this lens owns the breaker and the fallback existing and being configured. An idempotency guard existing is reliability; its retry / dead-set metrics are obs.
- **vs. core correctness (`task-rails-review` Step 5):** core owns happy-path transaction correctness and Rails idioms; this lens owns partial failure, dependency failure, and saturation. Idempotency and post-commit dispatch sit at the seam - the umbrella dedups.

## Depth

| Depth      | When                                             | Steps Run                                 |
| ---------- | ------------------------------------------------ | ----------------------------------------- |
| `standard` | Default                                          | All except the Failure-Mode Map           |
| `deep`     | Requested by flag, or handed down by `task-rails-review` - the words "resilience-debt pass" in a request do not by themselves select it | All + `Failure-Mode and Blast-Radius Map` |

At `deep`, Use skill: `failure-propagation-analysis` in what-if mode, once per new or changed dependency, to trace its failure path across shared resources (the AR connection pool, Redis, the Sidekiq queue) and name the loop-breaker that contains it (breaker, retry budget, dedicated queue, load shedding); each run compresses into one row of the Failure-Mode and Blast-Radius Map - its own block is not emitted.

Invocation forms (`/task-rails-review-reliability [<branch>|pr-<N>] [standard|deep] [--base <branch>]`) follow `task-code-review-reliability` - current branch vs base; fails fast on trunk. When invoked as subagent, the parent passes the pre-confirmed stack, resolved `base_ref` / `head_ref`, depth, and pre-read diff and commit log; Steps 2-3 consume those instead of re-running.

**Whole-service sweep** (resilience-debt pass with no feature branch): when Step 3 fails fast on trunk AND the invocation asked for a sweep or named a path, do not stop - skip the diff gate and sweep. On a bare trunk invocation (no sweep intent stated, no path), surface the fail-fast and ask whether to sweep - a wrong-branch mistake should not trigger a whole-app pass. Scope = the named path(s), the clients, jobs, services, and config they touch, and the direct callers of a named file (one hop); no path named = the whole `app/`, `lib/tasks/` and `config/` surface. Run Steps 4-10 against current code at `HEAD` (Step 4's categories read in full, not per changed file), then Verify Findings in its sweep form, then Step 11. Atomic-load gates and "diff"-worded rows read as "the in-scope code" (pool config in scope loads `rails-connection-pool-sizing`). Fill the Summary's `Target:` slot, skip `review-report-writer` checkpointing, and emit the report body as the response - no file is written.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Accept a pre-confirmed stack from a parent (`task-rails-review`) and skip detection. Where the project's declared stack and its code disagree, record what the code does and note the divergence. Standalone: Use skill: `stack-detect`; if not Rails, stop and route the user to `/task-code-review-reliability`. This workflow's fixes target Rails 7.2+. A project below that is reviewed anyway - state the detected versions in the Summary and give the fix that its version supports; never stop on a version mismatch. Record the **database** (MySQL, Postgres, or `unknown` - on `unknown` read `config/database.yml` `adapter:`; MariaDB takes the MySQL branch) and the **background runtime** (Sidekiq direct / ActiveJob (<adapter>, or `async default - not configured`) / both / none detected - an app with ActiveJob classes *and* classes including `Sidekiq::Job` is `both` - presence in config and code decides it, not whether each is exercised, and Steps 6-7 check each runtime's own retry and idempotency surface).

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-reliability`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch). Surface any fail-fast verbatim and stop (trunk fail-fast only: the whole-service-sweep rule above may override - see the sweep paragraph; a sweep has no round gate). Skip when running as a subagent with artifacts pre-passed.

**Round gate (standalone only).** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface: a valid `prior_checkpoint` whose `head_sha` equals the captured `head_sha` and whose `depth` covers the requested one (`deep` covers `standard`) -> print `No new commits since prior reliability review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 11 write overwrites the file) -> `round: 1`, no `prior_head_sha`. Then read the diff and log once.

### Step 4 - Read the Reliability Surface

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (a small diff ripples: a new service method calling an unchanged untimed client is a new failure path at the call site):

- External clients: `app/clients/*`, Faraday connections, `Net::HTTP` callsites, Stripe / S3 / SMTP SDK calls - timeouts, breakers, retries
- Service objects composing multiple downstream calls (`app/services/*`) - timeout budget, partial-failure handling
- Sidekiq jobs / ActiveJob classes - idempotency, `sidekiq_options retry:`, dead set, dispatch timing
- Cron rake tasks / scheduled jobs (`sidekiq-cron`, `whenever`) - overlap guard (leader lock)
- Side-effecting flows (payment, notification, provisioning) - idempotency keys, outbox / `after_commit`
- Config: `config/database.yml` (`pool`, `checkout_timeout`, `reaping_frequency`, `idle_timeout`), `config/sidekiq.yml`, `config/puma.rb` (`workers` / `threads`), `config/initializers/*` (`stoplight`, `retriable`, `rack-timeout`), `*.timeout` keys
- Gemfile adds: `stoplight`, `retriable`, `faraday-retry`, `sidekiq-unique-jobs`, `rack-timeout`

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns (its assessment block is not emitted - each gap entry becomes a finding here) - load it when the surface above includes an external client, a fanning-out service, or breaker / retry / timeout config (it feeds Steps 5, 6, and 8). Skip it on a diff that is purely Sidekiq-idempotency, transaction, or locking work with no synchronous dependency - Steps 7, 9, and 10 carry their own atomics.

**Gating skips atomic loads, never checklist rows.** Every checklist row below runs on this skill's own text regardless of which atomics loaded; a row goes N/A only when the diff has no matching surface (the Self-Check rule). Also read the full `Gemfile` here (not just diff adds) to fill the Summary's `Resilience Gems:` field. Deploy topology and ceilings (pod counts, `max_connections`, row counts) come from repo config first, then committed docs (`CLAUDE.md`'s infra section, k8s manifests, `Procfile`), cited as such in the finding; still unknown -> the Step 9 assumption rule.

### Step 5 - Timeouts and Deadlines

Use skill: `rails-http-client-patterns`.

- [ ] **Timeouts on every external call** - Faraday sets explicit `open_timeout` (1-2s) and `timeout` (under 5s on the web path, 10-30s in a job). `Net::HTTP` sets `open_timeout`, `read_timeout` **and** `write_timeout` - each defaults to 60s, far beyond any request budget; `read_timeout` bounds each socket read, not the whole call, so an upstream that drips bytes holds the Puma thread and its pooled connection far past 60s - a real wall-clock cap needs `Rack::Timeout` or an explicit deadline around the call.
- [ ] **Request deadline** - `Rack::Timeout` (`service_timeout`) bounds any request; without it a slow controller pins its Puma thread and checked-out AR connection indefinitely (a blocked socket releases the GVL; the thread and connection are what run out).
- [ ] **Timeout budget on chained calls** - a service fanning out to N clients caps total time; a slow first call leaves budget for the rest or fails fast. Web-path external timeout < remaining request budget; push longer work to Sidekiq. A chain already inside a job caps each call so the total stays under the job's runtime budget.

```ruby
Net::HTTP.start(uri.host, uri.port)                          # bad - open + read default to 60s each
http = Net::HTTP.new(uri.host, uri.port)                     # good
http.open_timeout = 2; http.read_timeout = 5
```

### Step 6 - Retries, Circuit Breakers, and Isolation

Use skill: `rails-sidekiq-patterns` (`rails-http-client-patterns` already loaded in Step 5 - reuse it for the retry / breaker rules).

- [ ] **Retries bounded, backoff + jitter** - Faraday `:retry` (`max: 2-3`, `backoff_factor: 2`, `interval_randomness`) or the `retriable` gem; in-process budget <5s web / <30s job. Sidekiq owns longer waits (`sidekiq_options retry: <N>`, `sidekiq_retry_in` with jitter). Do not stack Faraday + Retriable + Sidekiq - waits compound unpredictably.
- [ ] **Retry only transient errors** - `500` / `502` / `503` / `504` (never `501` / `505`), timeouts, connection errors, and the retryable 4xx - `429`, `408`, `425 Too Early`, a `409` carrying `Retry-After`, a `401` once after a token refresh, `412` / `423` after re-reading state; never other 4xx; never `POST` / non-idempotent ops without an `Idempotency-Key`. ActiveJob equivalent: `retry_on TransientError, wait: :polynomially_longer, attempts: N`; `discard_on` permanent errors.
- [ ] **Circuit breaker on high-volume synchronous request-path deps** - `Stoplight("dep", threshold: N, cool_off_time: S).run { ... }` (the keyword form is Stoplight 5.x; 3.x and 4.x chain `.with_threshold` / `.with_cool_off_time`). A configured light that never calls `.run` executes nothing - flag that shape too. In-process retries during a sustained outage cascade into Puma worker exhaustion. State is metered (visibility gap -> `task-rails-review-observability`). Low-volume background work needs none.
- [ ] **Recovery-herd control** - when the breaker closes, queued Sidekiq retries and live traffic re-fire together and re-trip the partner. Jittered `sidekiq_retry_in`; keep the threshold low enough to re-open fast on partial recovery.
- [ ] **Failure-domain isolation** - partition a flaky or slow dependency's jobs onto a dedicated low-concurrency Sidekiq queue (a capsule on Sidekiq 7+) so it cannot starve the shared pool (bulkhead). Hard provider quotas need proactive throttling (token bucket / low-concurrency queue), not reactive 429 alone.

### Step 7 - Idempotency and Delivery Semantics

Use skill: `backend-idempotency`, `rails-transaction-patterns` (`rails-sidekiq-patterns` already loaded in Step 6 - reuse); assessment blocks are not emitted.

- [ ] **Every Sidekiq job idempotent** - Sidekiq delivers at least once, so `perform` re-fetches state and returns early when done (`return if order.fulfilled?`). At-least-once + non-idempotent = double charge on retry or on the graceful-shutdown re-push.
- [ ] **Duplicate-enqueue guard** where the trigger can fire twice (webhook retries, `after_commit` bulk) - `sidekiq-unique-jobs` (`lock: :until_executed` with a `lock_ttl`) or a Redis `SET NX` fence, not a read-then-enqueue race.
- [ ] **External side effects forward an idempotency key** (`Idempotency-Key` header, Stripe `idempotency_key`); dedup atomic via unique index + `insert_all` / `upsert` (`on_duplicate:` on the upsert form), not read-then-write.
- [ ] **No enqueue or external write inside `Model.transaction`** - `.perform_async` inside a transaction can run before commit and 404 on the not-yet-committed row; HTTP inside holds the row lock across the round-trip. Dispatch via `after_commit` (model) or, from inside a caller's transaction, Rails 7.2+'s `ActiveRecord.after_all_transactions_commit` / `Model.current_transaction.after_commit`; the `after_commit_everywhere` gem is the pre-7.2 equivalent and is fine where already in the Gemfile.
- [ ] **Dead set as DLQ** - `sidekiq_options retry: <N>` with the default `dead: true` parks exhausted jobs in the dead set; something must watch it (alert on its size, or a `sidekiq_retries_exhausted` hook). Rescue-and-`perform_in` resets the counter and retries forever; an in-`perform` rescue that swallows the error makes `retry_on` / `sidekiq_options retry:` unreachable - file that as High (alerting depth -> observability).
- [ ] **ActiveJob adapter is a persistent backend in production** - the `:async` default queues in process memory and is lost on restart or crash; `:inline` runs synchronously and never retries.
- [ ] **Out-of-order delivery** guarded by a monotonic field - return early when the payload's `updated_at` <= the stored value.

### Step 8 - Graceful Degradation and Load Shedding

- [ ] **Defined fallback per critical dependency** - decide `Stoplight` fail-open vs fail-closed per call site: serve a cached / last-known value (rate quotes, display data), or fail the operation for anything moving money - never a `0.0`-style sentinel.
- [ ] **Fallbacks log the original failure** at `warn` with context; no silent swallow that hides degradation until it compounds.
- [ ] **Partial responses** - an optional downstream (recommendations, enrichment) failing degrades the response, not the whole request.
- [ ] **Load shedding** - `Rack::Attack` throttles / returns 429; `Rack::Timeout` returns rather than piling requests on exhausted workers. Saturation sheds rather than queueing unboundedly.

### Step 9 - Resource Exhaustion and Saturation

Use skill: `rails-connection-pool-sizing` only on config-change PRs (pool / Puma / Sidekiq concurrency), `rails-batch-processing-patterns` only when the diff adds or changes batch / bulk iteration. Skip both when the surface is absent.

- [ ] **AR pool bounded and correct** - per-process `pool == in-process thread count` (+ documented executor / Cable extras); a pool above that is not a safety margin - it removes the cap; deployment-wide sum ((puma pods x `workers` x `threads`) + (sidekiq pods x processes x `concurrency`) + cron / scheduled processes - the pod and process multipliers are what make it deployment-wide) under DB `max_connections` minus the reserved CLI / ops slots, with 25% headroom (15% only when the rolling-deploy peak is bounded and has been observed). `checkout_timeout` defaults to 5s, so exhaustion already raises `ConnectionTimeoutError` rather than blocking - the finding is a value raised well above that default, which queues requests behind an exhausted pool instead of shedding them. When a ceiling (`max_connections`, deployed concurrency) is not in the diff, read the repo config for it; still unknown -> run the check anyway and state the assumption in the finding's Fix and in the Summary `Notes:` (`verify: max_connections unknown`) - never silently skip it.
- [ ] **Puma bounds under the GVL** - worker / thread counts sized so CPU-bound work does not starve threads; `reaping_frequency` / `idle_timeout` reclaim dead / idle connections.
- [ ] **No unbounded `.all.each`** - iterate with `find_each` / `in_batches`; `pluck(:id)` cursors when AR objects are not needed; `WorkerKiller` / jemalloc for memory-heavy Sidekiq queues.
- [ ] **Pooled Redis** - non-Sidekiq Redis use goes through the `connection_pool` gem; a per-call `Redis.new` leaks connections under load.
- [ ] **Cron rake task overlap** - a task whose runtime can exceed its cadence carries a leader lock (`with_advisory_lock`) so slow runs do not stack.

### Step 10 - Recoverability and Consistency Under Failure

Use skill: `rails-transaction-patterns`, `rails-db-locking-patterns`. Cross-aggregate consistency rule (inlined on purpose - do not re-delegate this to a separate consistency atomic; it overlaps the two atomics already loaded here, and its one distinct rule is captured below): writes that cannot share one DB transaction (a charge + a separate provisioning record, a local write + a remote call) need a compensating action or a reconciliation job on partial failure - never a best-effort inline rollback that can itself fail. Prefer one transaction; when impossible, make the second step idempotent and retriable so a re-run converges.

- [ ] **Crash-safety** - a multi-step side effect interrupted mid-way (Sidekiq `SIGTERM` re-push, deploy) leaves recoverable state: checkpoint progress per chunk so the re-pushed job resumes; never swallow `Sidekiq::Shutdown` - it descends from `Interrupt`, so a bare `rescue => e` never catches it and the shapes to flag are `rescue Exception` and an explicit `rescue Sidekiq::Shutdown` / `rescue Interrupt`.
- [ ] **Compensating action on partial failure** - a charge that succeeds before a failing DB write enqueues a reconciliation / refund job, not an inline refund that compounds failure. Cross-aggregate writes that cannot be one transaction have a compensation.
- [ ] **Race-prone updates safe under concurrency** - pessimistic `lock!` / `with_lock` / `lock("FOR UPDATE")` by primary key, or optimistic `lock_version` (rescue `StaleObjectError`); a read-modify-write on a hot counter is a lost-update bug without one.
- [ ] **Post-commit dispatch** - jobs, email, cache invalidation fire from `after_commit`, so a rolled-back transaction never acts on state that did not persist.
- [ ] **Dual write is recoverable** - a DB write plus a publish / enqueue is atomic through a transactional outbox, or the post-commit dispatch has a reconciliation pass that recovers a crash between commit and dispatch.
- [ ] **Lock-wait timeout set** where rows are held - PG `lock_timeout` (default 0 = wait forever), MySQL `innodb_lock_wait_timeout` (default 50s) - 5-10s per `rails-db-locking-patterns`.
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes (use skill: `rails-postgresql-migration-safety` or `rails-migration-safety` per detected DB).

### Verify Findings (before writing)

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns (`_(pre-existing)_`, `_(pre-existing; newly reachable via ...)_`, `_(unverified: ...)_`, `_(mechanism: ...)_`), and fill the Summary's `Findings verified:` line from its tally in the atomic's Summary form; dropped rows appear only in the tally, and reattributed rows publish at their corrected location. Whole-service sweeps skip it (the skill requires a diff; there is none): instead re-read each cited `file:line` at `HEAD`, drop findings the code does not support, and report `Findings verified: inline (no diff)`. On round 2+, after verification, re-project the prior report's findings - every tier, the file at the handle's `report_path` - into reconcile's parse shape - one `## High-Impact Findings` section, one `### [Label] file:line` heading per finding from its `Label:` line (the label alone - a trailing `_(carried from round <N>)_` group is re-emitted on the heading as its own group; when the prior report wrote no label, the one its tier maps to under Severity assignment) and the `file:line` prefix of its Location line, keeping a `_(pre-existing)_` annotation on the heading (verify's combined `_(pre-existing; newly reachable via ...)_` is written as two groups, `_(pre-existing)_ _(newly reachable via ...)_` - reconcile matches `_(pre-existing)_` exactly), with its `Issue` line written as `Issue:` (the smell) - then Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D` entry. Its table, note line and tally render as `## Prior Round Reconciliation`; `Still open` and `Needs re-check` rows carry into their prior tier at their prior label with `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the Label value and the prior Location annotation kept - the table row and a Next Steps entry are its only other appearances, and a carried finding this round's own pass re-derives publishes once, in the findings sections, not twice. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried; the reconciliation table is the one place a label outside `[Must]` / `[Recommend]` is written. Subagent runs skip verification and reconciliation both - the parent verifies and reconciles its own merged set once.

### Step 11 - Write Report

Standalone runs (resolved diff): Use skill: `review-report-writer` with `report_type: review-reliability` and every field the writer requires - `report_body` (the assembled body), `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the Step 3 round gate, `scope: +rel`, `depth` as invoked, `stack = ruby-rails`, `mode: full`, `round` and `prior_head_sha` from the round gate, and `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present. Emit the report body in chat, then the writer's confirmation line. Subagent runs (parent passed pre-read artifacts): skip the writer and return only `## Findings` with its tier sections and any `out of lens` lines - no Summary, no Recommendations, no Next Steps, no file - the parent owns the report - a subagent never invokes the writer; at `deep`, add the Failure-Mode and Blast-Radius Map after them - the parent preserves it as its own section. (A whole-service sweep skips the writer too and emits the body as the response - see the sweep paragraph under Depth.)

## Output Format

The fence below delimits the template for display only - it is not part of the report; the body is `report_body`, and the writer adds the frontmatter. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unbounded failure path or data-loss / corruption risk under a plausible failure (missing `Net::HTTP` timeout on a hot call, uncapped retry, non-idempotent Sidekiq job, `.perform_async` inside a transaction, unbounded `.all.each` on a hot path, enqueue-before-commit); High also covers a pool sized *below* its process's thread count - threads queue on checkout under ordinary load, not only under failure. Medium = failure is bounded but recovery or containment is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, missing timeout / retry budget on a chained path, cron task with no overlap guard, `checkout_timeout` raised far above its 5s default, unbounded iteration confined to a scheduled task); Low = hardening with no immediate failure path (no dedicated queue / bulkhead, fail-fast where stale data would serve). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the whole fix is a literal one-line config addition on a critical path - money movement, auth, or a synchronous request-path dependency - (a timeout value, a `retry:` option, `lock_timeout`, `checkout_timeout`) - a one-liner that also needs a gem the Gemfile lacks is not one; Low -> `[Recommend]`. An escalated or de-escalated finding keeps its severity tier - only its label changes. When the verify pass changed a finding's label, its verified `Label` wins over this mapping. No other label is written outside the reconciliation table.

Fill rules: `Findings verified:` carries the verify tally on standalone runs and the literal `inline (no diff)` on whole-service sweeps (subagent runs emit no Summary). Verify annotations appear on standalone runs with a diff only; a finding sits in the section matching its severity while its `Label:` line carries the published label, so a `[Recommend]` inside a higher section is correct, not a mismatch to fix. `Target:` appears only on sweeps (it replaces writer checkpointing); omit otherwise. **One defect, one finding.** Several checklist rows, or several call sites, that describe one underlying defect file once - at the site where the fix lands, with the other sites named in the Location line. Genuinely distinct defects at one site, with different fixes, stay separate. Anchor to the narrowest `file:line` the fix touches; a range only when the fix spans contiguous lines. There is no finding count to hit or stay under: file every defect that meets the severity bar and nothing that does not. Two findings are the same defect when one fix removes both; different fixes at one site, or one fix that only masks the second, are two. `Resilience Gems:` lists every detected resilience gem comma-separated (Stoplight, Retriable, faraday-retry, sidekiq-unique-jobs, rack-timeout, with_advisory_lock, connection_pool, sidekiq-iteration, sidekiq-worker-killer), or `none detected`. The Failure-Mode and Blast-Radius Map (`deep` only) is a table, one row per new / changed dependency, columns **Dependency**, **Failure behavior** (down or slow), **Shared resource** on the propagation path (AR pool, Redis, Sidekiq queue), **Loop-breaker** that contains it (breaker, retry budget, dedicated queue, load shedding).

```markdown
## Rails Reliability Review Summary

- **Stack Detected:** Ruby <version> / Rails <version> / <database>
- **Background Runtime:** Sidekiq direct | ActiveJob (<adapter>) | both | none detected
- **Resilience Gems:** <detected gems, comma-separated | none detected>
- **Depth:** standard | deep
- **Round:** <N>   {round 2+ only}
- **Target:** <path(s)>   {sweep only}
- **Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]
- **Findings verified:** <per fill rules: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}` from `review-finding-verify` | inline (no diff)>
- **Notes:** <the Step 2 declared-vs-code divergence, each stated assumption (`verify: max_connections unknown`); omit when none>

## Findings

### High Impact

1. **Location:** [file:line] [+ the verify Annotation - `_(pre-existing)_` / `_(pre-existing; newly reachable via ...)_` / `_(unverified: <reason>)_` / `_(mechanism: <actual>)_`]

   **Label:** [Must] | [Recommend]   {a carried finding appends `_(carried from round <N>)_`}

   **Issue:** [name the gap: untimed `Net::HTTP` call, uncapped Faraday retry, `.perform_async` inside `Model.transaction`, non-idempotent Sidekiq job, unbounded `.all.each`, etc.]

   **Failure Mode:** [what fails and how: "shipper API stall pins Puma threads and their pooled connections until the AR pool exhausts"]

   **Blast Radius:** [what else is affected: "every endpoint sharing the pool raises `ConnectionTimeoutError`"]

   **Fix:** [Faraday / `Net::HTTP` timeout, `Stoplight` breaker + fallback, `after_commit` dispatch, idempotency guard, `find_each`, etc.]

### Medium Impact
[Same numbered-block structure; numbering continues across tiers]

### Low Impact
[Same numbered-block structure]

_Omit empty sections; if all are omitted, state `No reliability gaps found.`_

## Prior Round Reconciliation

[table, note line and tally from `review-prior-findings-reconcile` - round 2+ standalone runs only; omit the section otherwise]

## Recommendations

[Structural resilience improvements not tied to a single finding]

## Failure-Mode and Blast-Radius Map   {deep only}

| Dependency | Failure behavior | Shared resource | Loop-breaker |
| ---------- | ---------------- | --------------- | ------------ |

## Next Steps

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: platform] - [action]
3. **[Implement]** [Recommend] file:line - [action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra). `[Implement]` / `[Delegate]` and `[Must]` / `[Recommend]` are independent axes - a `[Delegate]` may carry `[Must]`. Order Must > Recommend. Omit if none._
```


**A defect this lens does not own is reported, never dropped.** Another lens's category, a plain correctness bug, or something a gate excluded but the reading surfaced: one `- **out of lens:** file:line - <the defect in one sentence, and the workflow that owns it>` line at the end of `## Findings` - untiered, uncounted in `Overall`, absent from Next Steps; the parent drafts it as a finding. Atomics loaded by any step feed findings into this template; their own output blocks are not emitted. The exception is a defect that makes this lens's own findings unreachable or wrong (a query that always raises, a guard that never runs): that files here at its own severity, because it changes what the rest of the report means.

## Self-Check

Mark a line N/A when the diff (sweep: the in-scope code) has no matching surface (e.g. no external clients, no scheduled jobs).

- [ ] Step 1: behavioral principles loaded (subagent: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: detected Rails / Ruby versions recorded (in the Summary on standalone runs) and fixes given for that version (or pre-confirmed stack accepted from parent); DB + background runtime recorded
- [ ] Step 3: precondition check ran with `report_type: review-reliability` and the round decided from the handle before the diff was read (or the stop line printed; subagent: artifacts received; sweep: trunk fail-fast overridden per the sweep rule); diff + log read once (sweep: in-scope code read)
- [ ] Step 4: external clients, composing services, jobs, cron tasks, side-effecting flows, pool / Sidekiq / timeout config read; full `Gemfile` read for the Resilience Gems field; `ops-resiliency` consulted when a synchronous-dependency surface is present (skipped on idempotency/transaction/locking-only diffs)
- [ ] Step 5: Faraday + `Net::HTTP` timeouts, `Rack::Timeout` deadline, chained-call budget checked
- [ ] Step 6: retry safety / budget, `Stoplight` breaker, recovery-herd control, queue isolation checked
- [ ] Step 7: `backend-idempotency` consulted; idempotent jobs, duplicate-enqueue guard, keyed dedup, no in-transaction enqueue, dead set checked
- [ ] Step 8: fallback per critical dependency; fallbacks log; partial responses; load shedding verified
- [ ] Step 9: AR pool + Puma bounded; no unbounded `.all.each`; pooled Redis; cron overlap guarded
- [ ] Step 10: cross-aggregate compensation rule applied; crash-safety, compensation, locking, post-commit dispatch, migration rollout checked
- [ ] Verify pass ran (inline on a whole-service sweep; skipped as subagent - the parent verifies); tally or omission per fill rules; prior findings projected and reconciled on round 2+
- [ ] Step 11: standalone: report written via `review-report-writer` with `report_type: review-reliability`, confirmation printed; subagent: findings returned to parent, no file written; sweep: body emitted as the response
- [ ] Every finding names the failure mode and blast radius, never just the missing pattern
- [ ] Depth honored: `standard` ran every step but the Map; `deep` filled the Failure-Mode and Blast-Radius Map (via `failure-propagation-analysis`)
- [ ] `out of lens` lines emitted for defects outside the lens
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Avoid

- Reporting a missing pattern without the failure mode ("add a timeout" vs "untimed `Net::HTTP` call pins a Puma thread and its pooled connection until the upstream gives up")
- Overlapping into perf (throughput tuning) or observability (metric / log wiring) - name the failure-survival gap
- Treating Sidekiq retries as a substitute for idempotency
- Recommending retries on non-idempotent ops without an idempotency key
- Recommending a `Stoplight` breaker with no monitoring, or on every low-volume integration
- Approving `.perform_async` or an external write inside `Model.transaction`
