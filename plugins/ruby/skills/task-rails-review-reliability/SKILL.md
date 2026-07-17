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

- Rails PR / branch adding or changing an integration point (Faraday / `Net::HTTP` client, Sidekiq job / ActiveJob, cron rake task, ActionCable broadcast fan-out)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and at-least-once safety
- Hardening after a near-miss; recurring resilience-debt sweep
- Dual-write / outbox / `after_commit` / consumer-retry correctness under failure

**Not for:** general Rails review (`task-rails-review`), perf optimization (`task-rails-review-perf`), observability wiring (`task-rails-review-observability`), security (`task-rails-review-security`), a live incident (`/task-oncall-start` - mitigate first).

## Seam With Adjacent Lenses

- **vs. Perf:** perf tunes the AR pool, Sidekiq concurrency, and queries for throughput; this lens verifies they are bounded and that exhaustion fails fast and degrades gracefully. A slow query is perf; the untimed query holding a pooled connection until it is killed is reliability.
- **vs. Observability:** obs owns the breaker-state metric and the fallback log line; this lens owns the breaker and the fallback existing and being configured. An idempotency guard existing is reliability; its retry / dead-set metrics are obs.
- **vs. core correctness (`task-rails-review` Step 5):** core owns happy-path transaction correctness and Rails idioms; this lens owns partial failure, dependency failure, and saturation. Idempotency and post-commit dispatch sit at the seam - the umbrella dedups.

## Depth

| Depth      | When                                             | Steps Run                                 |
| ---------- | ------------------------------------------------ | ----------------------------------------- |
| `standard` | Default                                          | All except the Failure-Mode Map           |
| `deep`     | Requested, or handed down by `task-rails-review` | All + `Failure-Mode and Blast-Radius Map` |

At `deep`, use skill: `failure-propagation-analysis` to trace each new or changed dependency's failure path across shared resources (the AR connection pool, Redis, the Sidekiq queue) and name the loop-breaker that contains it (breaker, retry budget, dedicated queue, load shedding); fill the Failure-Mode and Blast-Radius Map.

Invocation forms (`/task-rails-review-reliability [<branch>|pr-<N>] [standard|deep] [--base <branch>]`) follow `task-code-review-reliability` - current branch vs base; fails fast on trunk. When invoked as subagent, the parent passes the pre-confirmed stack, the precondition handle, and pre-read diff and commit log; Steps 2-3 consume those instead of re-running.

**Whole-service sweep** (resilience-debt pass with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and sweep. Scope = the named path(s) plus the clients, jobs, services, and config they touch; no path named = the whole `app/` + `config/` surface. Run Steps 4-10 against current code at `HEAD` (Step 4's categories read in full, not per changed file), then Step 11. Report `**Target:** <path>` in the Summary instead of checkpoint fields; skip `review-report-writer` checkpointing and write the report body directly.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Accept a pre-confirmed stack from a parent (`task-rails-review`) and skip detection. Standalone: use skill: `stack-detect`; if not Rails, stop and route the user to `/task-code-review-reliability`. This workflow assumes Rails 7.2+ / Ruby 3.4+. Record the **database** (MySQL or Postgres) and the **background runtime** (Sidekiq direct / ActiveJob adapter).

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Once the handle is emitted, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + artifacts pre-passed. Surface any fail-fast verbatim and stop.

### Step 4 - Read the Reliability Surface

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (a small diff ripples: a new service method calling an unchanged untimed client is a new failure path at the call site):

- External clients: `app/clients/*`, Faraday connections, `Net::HTTP` callsites, Stripe / S3 / SMTP SDK calls - timeouts, breakers, retries
- Service objects composing multiple downstream calls (`app/services/*`) - timeout budget, partial-failure handling
- Sidekiq jobs / ActiveJob classes - idempotency, `sidekiq_options retry:`, dead set, dispatch timing
- Cron rake tasks / scheduled jobs (`sidekiq-cron`, `whenever`) - overlap guard (leader lock)
- Side-effecting flows (payment, notification, provisioning) - idempotency keys, outbox / `after_commit`
- Config: `config/database.yml` (`pool`, `checkout_timeout`, `reaping_frequency`, `idle_timeout`), `config/sidekiq.yml`, `config/puma.rb` (`workers` / `threads`), `config/initializers/*` (`stoplight`, `retriable`, `rack-timeout`), `*.timeout` keys
- Gemfile adds: `stoplight`, `retriable`, `faraday-retry`, `sidekiq-unique-jobs`, `rack-timeout`

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns.

### Step 5 - Timeouts and Deadlines

Use skill: `rails-http-client-patterns`.

- [ ] **Timeouts on every external call** - Faraday sets explicit `open_timeout` (1-2s) and `timeout` (3-10s web / 10-30s job). `Net::HTTP` sets **both** `open_timeout` and `read_timeout` - each defaults to 60s, far beyond any request budget; a hung upstream pins a Puma thread and its pooled connection for a minute per call.
- [ ] **Request deadline** - `Rack::Timeout` (`service_timeout`) bounds any request; without it a slow controller holds a worker indefinitely under the GVL.
- [ ] **Timeout budget on chained calls** - a service fanning out to N clients caps total time; a slow first call leaves budget for the rest or fails fast. Web-path external timeout < remaining request budget; push longer work to Sidekiq.

```ruby
Net::HTTP.start(uri.host, uri.port)                          # bad - open + read default to 60s each
http = Net::HTTP.new(uri.host, uri.port)                     # good
http.open_timeout = 2; http.read_timeout = 5
```

### Step 6 - Retries, Circuit Breakers, and Isolation

Use skill: `rails-http-client-patterns`, `rails-sidekiq-patterns`.

- [ ] **Retries bounded, backoff + jitter** - Faraday `:retry` (`max: 2-3`, `backoff_factor: 2`, `interval_randomness`) or the `retriable` gem; in-process budget <5s web / <30s job. Sidekiq owns longer waits (`sidekiq_options retry: <N>`, `sidekiq_retry_in` with jitter). Do not stack Faraday + Retriable + Sidekiq - waits compound unpredictably.
- [ ] **Retry only transient errors** (5xx, timeouts, connection); never 4xx; never `POST` / non-idempotent ops without an `Idempotency-Key`. ActiveJob equivalent: `retry_on TransientError, wait: :polynomially_longer, attempts: N`; `discard_on` permanent errors.
- [ ] **Circuit breaker on high-volume synchronous request-path deps** - `Stoplight("dep").with_threshold(N).with_cool_off_time(S)`. In-process retries during a sustained outage cascade into Puma worker exhaustion. State is metered (visibility gap -> `task-rails-review-observability`). Low-volume background work needs none.
- [ ] **Recovery-herd control** - when the breaker closes, queued Sidekiq retries and live traffic re-fire together and re-trip the partner. Jittered `sidekiq_retry_in`; keep the threshold low enough to re-open fast on partial recovery.
- [ ] **Failure-domain isolation** - partition a flaky or slow dependency's jobs onto a dedicated low-concurrency Sidekiq queue / capsule so it cannot starve the shared pool (bulkhead). Hard provider quotas need proactive throttling (token bucket / low-concurrency queue), not reactive 429 alone.

### Step 7 - Idempotency and Delivery Semantics

Use skill: `backend-idempotency`, `rails-sidekiq-patterns`, `rails-transaction-patterns`.

- [ ] **Every Sidekiq job idempotent** - Sidekiq delivers at least once, so `perform` re-fetches state and returns early when done (`return if order.fulfilled?`). At-least-once + non-idempotent = double charge on retry or on the graceful-shutdown re-push.
- [ ] **Duplicate-enqueue guard** where the trigger can fire twice (webhook retries, `after_commit` bulk) - `sidekiq-unique-jobs` (`lock: :until_executed`) or a Redis `SET NX` fence, not a read-then-enqueue race.
- [ ] **External side effects forward an idempotency key** (`Idempotency-Key` header, Stripe `idempotency_key`); dedup atomic via unique index + `insert_all` / `upsert` (`on_duplicate`), not read-then-write.
- [ ] **No enqueue or external write inside `Model.transaction`** - `.perform_async` inside a transaction can run before commit and 404 on the not-yet-committed row; HTTP inside holds the row lock across the round-trip. Dispatch via `after_commit` (model) or `after_commit_everywhere` (nested service).
- [ ] **Dead set as DLQ** - `sidekiq_options retry: <N>, dead: true` routes exhausted jobs to the dead set for inspection / replay. Rescue-and-`perform_in` resets the counter and retries forever (alerting depth -> observability).
- [ ] **Out-of-order delivery** guarded by a monotonic field - return early when the payload's `updated_at` <= the stored value.

### Step 8 - Graceful Degradation and Load Shedding

- [ ] **Defined fallback per critical dependency** - decide `Stoplight` fail-open vs fail-closed per call site: serve a cached / last-known value (rate quotes, display data), or fail the operation for anything moving money - never a `0.0`-style sentinel.
- [ ] **Fallbacks log the original failure** at `warn` with context; no silent swallow that hides degradation until it compounds.
- [ ] **Partial responses** - an optional downstream (recommendations, enrichment) failing degrades the response, not the whole request.
- [ ] **Load shedding** - `Rack::Attack` throttles / returns 429; `Rack::Timeout` returns rather than piling requests on exhausted workers. Saturation sheds rather than queueing unboundedly.

### Step 9 - Resource Exhaustion and Saturation

Use skill: `rails-connection-pool-sizing` (config-change PRs), `rails-batch-processing-patterns`.

- [ ] **AR pool bounded and correct** - per-process `pool >= in-process thread count`; deployment-wide sum (Puma `workers` x `threads` + Sidekiq `concurrency` + CLI / ops) under DB `max_connections` with 15-25% headroom; size for the rolling-deploy peak. `checkout_timeout` fails fast rather than blocking indefinitely under exhaustion (`ConnectionTimeoutError`).
- [ ] **Puma bounds under the GVL** - worker / thread counts sized so CPU-bound work does not starve threads; `reaping_frequency` / `idle_timeout` reclaim dead / idle connections.
- [ ] **No unbounded `.all.each`** - iterate with `find_each` / `in_batches`; `pluck(:id)` cursors when AR objects are not needed; `WorkerKiller` / jemalloc for memory-heavy Sidekiq queues.
- [ ] **Pooled Redis** - non-Sidekiq Redis use goes through the `connection_pool` gem; a per-call `Redis.new` leaks connections under load.
- [ ] **Cron rake task overlap** - a task whose runtime can exceed its cadence carries a leader lock (`with_advisory_lock`) so slow runs do not stack.

### Step 10 - Recoverability and Consistency Under Failure

Use skill: `architecture-data-consistency`, `rails-transaction-patterns`, `rails-db-locking-patterns`.

- [ ] **Crash-safety** - a multi-step side effect interrupted mid-way (Sidekiq `SIGTERM` re-push, deploy) leaves recoverable state: checkpoint progress per chunk so the re-pushed job resumes; never swallow `Sidekiq::Shutdown` in a broad `rescue`.
- [ ] **Compensating action on partial failure** - a charge that succeeds before a failing DB write enqueues a reconciliation / refund job, not an inline refund that compounds failure. Cross-aggregate writes that cannot be one transaction have a compensation.
- [ ] **Race-prone updates safe under concurrency** - pessimistic `lock!` / `with_lock` / `lock("FOR UPDATE")` by primary key, or optimistic `lock_version` (rescue `StaleObjectError`); a read-modify-write on a hot counter is a lost-update bug without one.
- [ ] **Post-commit dispatch** - jobs, email, cache invalidation fire from `after_commit`, so a rolled-back transaction never acts on state that did not persist.
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes (use skill: `rails-postgresql-migration-safety` or `rails-migration-safety` per detected DB).

### Step 11 - Write Report

Standalone runs (resolved diff): use skill: `review-report-writer` with `report_type: review-reliability`. Assemble every checkpoint field the writer requires: `scope: +rel`, `depth` as invoked, `stack = ruby-rails`, `base_sha` / `head_sha` via `git rev-parse` on the handle's refs, and `mode: full`, `round: 1` - unless `review-reliability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha` (check for that file yourself; `review-precondition-check` looks up `review-<branch>.md`, a different report). Write the report file, then print confirmation. (Whole-service sweep skips the writer and writes the body directly - see Depth.)

Subagent runs (parent passed pre-read artifacts): skip the writer and return the findings in this skill's Output Format to the parent - the parent owns the report (`review-report-writer` rejects subagent writes). At `deep`, include the Failure-Mode and Blast-Radius Map with the returned findings - the parent preserves it as its own section.

## Output Format

**Severity assignment:** High = an unbounded failure path or data-loss / corruption risk under a plausible failure (missing `Net::HTTP` timeout on a hot call, uncapped retry, non-idempotent Sidekiq job, `.perform_async` inside a transaction, unbounded `.all.each` on a hot path, enqueue-before-commit); Medium = failure is bounded but recovery or containment is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, missing timeout / retry budget on a chained path, cron task with no overlap guard, missing `checkout_timeout`); Low = hardening with no immediate failure path (no dedicated queue / bulkhead, fail-fast where stale data would serve). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on a critical path; Low -> `[Recommend]` or `[Question]`.

```markdown
## Rails Reliability Review Summary

**Stack Detected:** Ruby <version> / Rails <version> / <database>
**Background Runtime:** Sidekiq | ActiveJob (<adapter>) | none detected
**Resilience Gems:** Stoplight | Retriable | faraday-retry | sidekiq-unique-jobs | none detected
**Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line]
   **Issue:** [name the gap: untimed `Net::HTTP` call, uncapped Faraday retry, `.perform_async` inside `Model.transaction`, non-idempotent Sidekiq job, unbounded `.all.each`, etc.]
   **Failure Mode:** [what fails and how: "shipper API stall pins Puma threads and their pooled connections until the AR pool exhausts"]
   **Blast Radius:** [what else is affected: "every endpoint sharing the pool raises `ConnectionTimeoutError`"]
   **Fix:** [Faraday / `Net::HTTP` timeout, `Stoplight` breaker + fallback, `after_commit` dispatch, idempotency guard, `find_each`, etc.]

### Medium Impact
[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins
[Same numbered-block structure]

_Omit empty sections._

## Recommendations

[Structural resilience improvements not tied to a single finding]

## Failure-Mode and Blast-Radius Map

_(`deep` only - omit at `standard`.)_
Per new / changed dependency: **what happens when it is down or slow**, the shared resource on the propagation path (AR pool, Redis, Sidekiq queue), and the loop-breaker that contains it (breaker, retry budget, dedicated queue, load shedding).

## Next Steps

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: platform] - [action]
3. **[Implement]** [Recommend] file:line - [action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra). Order Must > Recommend > Question. Omit if none._
```

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no external clients, no scheduled jobs).

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Rails 7.2+ / Ruby 3.4+ (or pre-confirmed stack accepted from parent); DB + background runtime recorded
- [ ] Step 3: precondition check ran (or handle received); diff + log read once
- [ ] Step 4: external clients, composing services, jobs, cron tasks, side-effecting flows, pool / Sidekiq / timeout config read; `ops-resiliency` consulted
- [ ] Step 5: Faraday + `Net::HTTP` timeouts, `Rack::Timeout` deadline, chained-call budget checked
- [ ] Step 6: retry safety / budget, `Stoplight` breaker, recovery-herd control, queue isolation checked
- [ ] Step 7: `backend-idempotency` consulted; idempotent jobs, duplicate-enqueue guard, keyed dedup, no in-transaction enqueue, dead set checked
- [ ] Step 8: fallback per critical dependency; fallbacks log; partial responses; load shedding verified
- [ ] Step 9: AR pool + Puma bounded; no unbounded `.all.each`; pooled Redis; cron overlap guarded
- [ ] Step 10: `architecture-data-consistency` consulted; crash-safety, compensation, locking, post-commit dispatch, migration rollout checked
- [ ] Step 11: standalone: report written via `review-report-writer` with `report_type: review-reliability`, confirmation printed; subagent: findings returned to parent, no file written
- [ ] Every finding names the failure mode and blast radius, never just the missing pattern
- [ ] Depth honored: `standard` ran all; `deep` filled the Failure-Mode and Blast-Radius Map (via `failure-propagation-analysis`)
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Avoid

- Reporting a missing pattern without the failure mode ("add a timeout" vs "untimed `Net::HTTP` call pins a Puma thread and its pooled connection until the upstream gives up")
- Overlapping into perf (throughput tuning) or observability (metric / log wiring) - name the failure-survival gap
- Treating Sidekiq retries as a substitute for idempotency
- Recommending retries on non-idempotent ops without an idempotency key
- Recommending a `Stoplight` breaker with no monitoring, or on every low-volume integration
- Approving `.perform_async` or an external write inside `Model.transaction`
- Mitigating a live incident here - route to `/task-oncall-start` first
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
