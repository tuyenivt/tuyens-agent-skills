---
name: rails-sidekiq-patterns
description: Sidekiq job patterns: idempotency, post-commit dispatch, retry/backoff, queue priority, uniqueness, shutdown, versioning.
metadata:
  category: backend
  tags: [ruby, rails, sidekiq, background-jobs, async]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing or reviewing a Sidekiq job
- Choosing retry / backoff / queue placement
- Diagnosing "ran twice", `ActiveJob::DeserializationError`, lock-wait cascades from jobs
- Deploy-time job versioning, graceful shutdown, payload sizing

## Rules

- Every job idempotent - check state before mutating
- Pass IDs only - never AR objects, request context, or payloads > 1 KB
- Enqueue after the DB transaction commits - inside `Model.transaction` only when `Sidekiq.transactional_push!` or Active Job's `enqueue_after_transaction_commit` defers it (`rails-transaction-patterns`)
- No HTTP / S3 / Redis inside `Model.transaction` - holds row locks for the network round-trip
- Rescue known errors; let unknown propagate to Sidekiq retry
- Cap `perform` at ~5 min; longer jobs split or fan out
- The process's total threads - `concurrency` plus every capsule's `:concurrency:` - never exceed its DB `pool` (`RAILS_MAX_THREADS`), since each thread checks out its own connection - `rails-connection-pool-sizing`
- Bulk jobs bypass per-row callbacks (`update_all`) or budget for them - an `after_commit` enqueue per row turns one job into N

## Patterns

### Idempotency

Pick by requirement; combine when requirements combine (list every mechanism used in the Output Format):

| Requirement                                            | Mechanism                                          |
| ------------------------------------------------------ | -------------------------------------------------- |
| Re-run safety (always required)                         | State check in `perform` (DB column, S3 key, etc.); a naturally idempotent write (recompute from source, upsert on a key) is its own state check |
| Duplicate enqueues (webhook retries, after_commit bulk) | `sidekiq-unique-jobs` `lock: :until_executed`      |
| Mutual exclusion only (dups allowed, no overlap)        | `lock: :while_executing`                           |
| Both dedup and mutual exclusion                         | `lock: :until_and_while_executing`                 |
| No gem available                                        | Redis `SET NX` fence (exclusion; a lock manager already in the Gemfile, `redlock`, counts) + state or monotonic check (dedup) |

```ruby
def perform(order_id)
  order = Order.find(order_id)
  return if order.fulfilled?

  # third arg is `opts` - a trailing kwarg hash binds to `params` and Stripe rejects it
  Stripe::Charge.capture(order.charge_id, {}, idempotency_key: "fulfill-#{order_id}")
  Order.transaction { order.lock!; order.update!(status: "fulfilled", fulfilled_at: Time.current) }
end
```

For external side effects, also forward an idempotency key. For sources that deliver out of order (webhook retries), guard with a monotonic field: return early when the payload's `updated_at` <= the stored one.

```ruby
sidekiq_options lock: :until_executed, on_conflict: :log, lock_ttl: 1.hour.to_i,   # class body
                lock_args_method: ->(args) { [args[0]] }

RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0"

def perform(id)                                                                     # no gem: a Redis lease
  token = SecureRandom.uuid                                                         # per-run owner token
  acquired = Sidekiq.redis { |r| r.set("sync_customer:#{id}", token, nx: true, ex: 60) }
  return unless acquired
  # ...
ensure
  # compare-and-delete: a bare DEL after the 60 s lease expired would release another worker's lease
  Sidekiq.redis { |r| r.call("EVAL", RELEASE, 1, "sync_customer:#{id}", token) } if acquired   # Sidekiq 7 yields a redis-client
end
```

Give every `until_executed` lock a `lock_ttl` - a worker killed without the graceful path (OOM, SIGKILL) orphans the lock, blocking enqueues for those args until the gem's reaper (default every 10 min) or the TTL clears it. Size the TTL above worst-case runtime plus retry window. For mutual exclusion under load use `while_executing` with `on_conflict: { client: :log, server: :reschedule }` - the server strategy re-enqueues without touching the retry counter - rather than a hand-rolled rescue-and-`perform_in`.

A cron-fired job takes its period from the fire time: a sidekiq-cron entry's `args:` are static, so set `date_as_argument: true` (appends the fire epoch) and derive the period from it, or have the CronJob / rake enqueuer pass it (`perform_async(Date.yesterday.iso8601)`); computed inside `perform` or as a default argument, a retry after midnight processes the wrong day.

### Post-Commit Dispatch

```ruby
# Bad - worker races the commit (or sees the row pre-commit and 404s on retry)
ActiveRecord::Base.transaction do
  order.update!(status: :processing)
  ShipmentNotificationJob.perform_async(order.id)
end

# Good
ActiveRecord::Base.transaction { order.update!(status: :processing) }
ShipmentNotificationJob.perform_async(order.id)
```

When the service runs inside a caller's transaction, "after the local block" still fires before the outer commit. Use `ActiveRecord.after_all_transactions_commit { Job.perform_async(id) }` (Rails 7.2+), or the `after_commit_everywhere` gem - whose method is `after_commit`, not the gem's own name: `include AfterCommitEverywhere` then `after_commit { Job.perform_async(id) }`, or call `AfterCommitEverywhere.after_commit { ... }` directly. A model `after_commit` callback works too. An Active Job `perform_later` is deferred by `enqueue_after_transaction_commit` - on Rails 7.2 under `load_defaults 7.2` (`:default`; the class attribute itself defaults to `:never`) it defers on every Sidekiq 7.x: Rails 7.2's bundled adapter inherits `AbstractAdapter#enqueue_after_transaction_commit?` (true), and the adapter Sidekiq ships from 7.3.3 answers true as well; on 8.0+ the adapter is never asked and the per-class boolean defaults to false, so it defers only where the job class sets `self.enqueue_after_transaction_commit = true`. Full transaction-boundary discipline and the version table: see `rails-transaction-patterns`.

### Backend Choice

| Choice           | Use When                                                                |
| ---------------- | ----------------------------------------------------------------------- |
| `Sidekiq::Job`   | Default. Direct access to `sidekiq_options`, `sidekiq_retry_in`         |
| `ApplicationJob` | Backend portability, ActiveJob callbacks / `retry_on`, or interop with code that calls `perform_later` |

Converting an existing `ApplicationJob` changes the enqueue API (`perform_later` -> `perform_async`) at every call site - flag it in review, don't silently convert. `sidekiq_options` inside an `ApplicationJob` is honoured, but `retry:` there plus `retry_on` is two retry channels - except `retry: 0`, which closes Sidekiq's channel so `retry_on` is the only one (on the Sidekiq adapter, Sidekiq otherwise adds its own 25 after `retry_on` gives up). Inside a `Sidekiq::Job`, mailers use `deliver_now`; the job is already the async boundary.

For foreground ops / cron without retries, use a rake task (`rails-rake-task-patterns`).

### Queue Priority

```yaml
# config/sidekiq.yml
:queues:
  - [critical, 6]
  - [default, 3]
  - [mailers, 2]
  - [low, 1]
```

Time-sensitive / financial -> `critical`. Reports / cleanup -> `low`. Email lands on `default`, not `mailers`, unless you say otherwise: `load_defaults 6.1`+ sets `config.action_mailer.deliver_later_queue_name = nil`, so a `mailers` queue in the YAML stays empty until you set that config. Per-mailer the knob is `self.deliver_later_queue_name = :mailers`, or `deliver_later(queue: "mailers")` per call - `queue_as` is an ActiveJob method and raises NoMethodError inside a mailer.

### Retry, Backoff, Error Handling

```ruby
class ImportDataJob
  include Sidekiq::Job
  sidekiq_options retry: 5, dead: true, backtrace: true

  sidekiq_retry_in do |count, exception|
    case exception
    when ExternalApi::RateLimitError then (exception.retry_after || 60 * (count + 1)) + rand(10)
    else (count ** 4) + 15 + (rand(10) * (count + 1))
    end
  end

  def perform(id)
    resource = Resource.find(id)
    ExternalApi.sync(resource)
  rescue ExternalApi::NotFoundError
    resource.update!(sync_status: :not_found)
  # Rate-limit and unknown errors propagate -> Sidekiq retries via sidekiq_retry_in
  end
end
```

Pick one retry channel per error class: either let it propagate (counted, `sidekiq_retry_in` controls delay) or rescue-and-`perform_in` (re-enqueue resets the retry counter - unbounded; avoid unless intentional). A `rescue` inside `perform` for a class also named in `retry_on` wins and silently disables that retry. Per-job `Retry-After` handling doesn't enforce a global rate budget - for hard provider limits, bound concurrency (dedicated low-concurrency queue/capsule) or share a Redis token bucket across processes (`rails-work-splitter-patterns`).

Bare `rescue => e; logger.error(...)` swallows errors and blocks retry. `dead: true` (the default) parks exhausted jobs in the Dead set, which nothing watches by itself - alert on its size, or add a `sidekiq_retries_exhausted` block that reports and marks the record.

### Payload Discipline

Sidekiq stores every job's args in Redis as JSON. 10 KB x 100K jobs = 1 GB.

- Pass IDs; refetch in `perform`. Args round-trip through JSON: pass a `Date`, `Time` or `Symbol` as a string (Sidekiq 7 strict args raise on them at enqueue) and parse in `perform`
- For lists, pass ID arrays (not record arrays)
- For large inputs, stage to S3 / a `JobInput` row, pass the key; expire staged rows (TTL or sweep)
- `ActiveJob::DeserializationError` means a GlobalID argument no longer finds its row (deleted, or enqueued inside a rolled-back transaction) - Active Job serializes AR objects as GlobalIDs, so passing one is not the cause. Fix the cause (post-commit dispatch; `discard_on ActiveJob::DeserializationError` where a vanished row is expected), then `.delete` the entries across `Sidekiq::Queue`, `Sidekiq::RetrySet`, `Sidekiq::ScheduledSet` and `Sidekiq::DeadSet` - re-enqueueing fails on `find` again. Match on `record.display_class` (or `record.item["wrapped"]`): on the Active Job path `klass` is the adapter wrapper

For >100 enqueues at once, use `push_bulk`. Cross-process fan-out, sharding, and `SKIP LOCKED` claim shapes: see `rails-work-splitter-patterns`.

### Graceful Shutdown

On deploy the supervisor - systemd, the k8s kubelet, the dyno manager - sends `SIGTERM` to Sidekiq, which stops fetching and at `timeout` seconds (default 25) re-pushes every still-busy job to its queue **first**, then raises `Sidekiq::Shutdown` into those threads: running a job twice beats losing it. (The server-side re-push bypasses client middleware, so uniqueness locks don't drop it.) If the supervisor's own grace period is shorter than Sidekiq's `timeout`, SIGKILL lands before any of this runs and in-flight jobs are simply lost - keep `terminationGracePeriodSeconds` (or the Capistrano/systemd equivalent) above `timeout`. The job's duty is making the re-run resume, not detecting the signal:

- Persist progress per chunk (state column / checkpoint) so the re-pushed job skips completed work
- Never swallow `Sidekiq::Shutdown`. It descends from `Interrupt`, not `StandardError`, so a bare `rescue => e` never catches it - `rescue Exception` and an explicit `rescue Sidekiq::Shutdown` / `rescue Interrupt` do. The re-push has already happened, so swallowing cannot prevent requeue; it lets the job keep working in a dying process while a duplicate is queued, so the redo starts from an inconsistent point
- For cooperative checkpoint-and-interrupt on long iterators, `include Sidekiq::IterableJob` (7.3+: `build_enumerator(*args, cursor:)` returns an Enumerator of `[item, cursor]` pairs, `each_iteration(item, *args)` does the work, the cursor is flushed every 5 s and on shutdown); below 7.3 the `sidekiq-iteration` gem

### Fan-out and Fan-in

Open-source Sidekiq has no Batches, so a completion step is yours: the parent seeds a counter (`INCRBY run:<id>:remaining N` with a TTL past the deadline) and enqueues the children with `push_bulk`; each child runs `DECR` after its idempotent write and enqueues the finalizer when it reads 0. A crash between the `DECR` and the end of `perform` decrements twice on retry, so the counter only *triggers* the finalizer: it re-checks the source (every row's output exists) before marking the run done, and a sweep at the deadline catches a counter that never reaches zero. A heavy or rate-limited child class runs in its own capsule:

```yaml
# config/sidekiq.yml - capsules cap concurrency per queue; a weight alone does not
:capsules:
  pdf:
    :concurrency: 4
    :queues: [pdf]
```

### Deploy-Time Versioning

Jobs enqueued before a deploy may run against new code. Version args when the contract changes:

```ruby
class ProcessOrderJob
  include Sidekiq::Job
  CURRENT_VERSION = 2

  def perform(order_id, version = 1)
    version == 2 ? process_v2(order_id) : process_v1(order_id)
  end
end

ProcessOrderJob.perform_async(order.id, ProcessOrderJob::CURRENT_VERSION)
```

## Output Format

One block per concrete job class in the read set (an abstract base such as `ApplicationJob` gets none - its settings appear in each child's `Retry`); fan-out designs emit one per job. In review or diagnosis mode, numbered findings precede the blocks, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Every block field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and when the enum value that matches already carries a `GAP`, `FIX` or `BLOCKER` marker in any spelling (` - GAP`, `(GAP)`, `(FIX)`, `(BLOCKER)`, a trailing parenthetical included), that value is the observed half and ` -> <corrected>` follows it. The marker applies to every field, whether or not its enum lists a `GAP` value; a field whose value is several named or `+`-joined parts marks only the violated part. A violation that belongs to no block - process or deploy config, a schema defect, a sibling skill's concern, a bug seen in passing - is a numbered finding with no block, naming the file and, for a sibling's concern, the owning skill. A violation whose block unit the code lacks (no client class, no transaction, no channel class) gets a block for the unit the fix introduces, its name suffixed `(proposed)`. When the request's premise or a document contradicts the code or schema, the code wins: say so in a finding and proceed on what the code shows. A request to design or change code is build mode: every block field holds the corrected value and no GAP marker (an enum value's own marker is dropped), and a pre-existing violation the change touches is still a numbered finding.

```
Job: {class name}

Queue: {critical | default | mailers | low | custom - name the isolation: a dedicated process (`-q x -c N`) or a Sidekiq 7+ capsule; a weight alone caps nothing | shared weighted pool, no isolation - GAP when the job is heavy (minutes per run) or rate-limited | queue no process consumes - GAP}

Trigger: {what causes enqueue | parent job fan-out | two schedulers (sidekiq-cron plus a CronJob) - GAP (one owner) | not in evidence}

Rate budget: {none - GAP (a hard quota is named and nothing enforces it) | capsule or dedicated process at concurrency N | Redis token bucket N per second or minute, shared across processes | n/a - no hard quota | unknown - not in evidence}

Arguments: {names and types - IDs only; flag any mismatch between `perform`'s arity and what the call site passes}

Idempotency: {state check | natural (recompute from source) | external idempotency key forwarded | monotonic guard (updated_at) | sidekiq-unique-jobs lock: <until_executed | while_executing | until_and_while_executing> + lock_ttl | Redis SET NX fence | none - GAP on an at-least-once path - list all that apply}

Retry: {count and backoff; channel: `sidekiq_options retry:` + `sidekiq_retry_in` | ActiveJob `retry_on` | rescue-and-`perform_in` - GAP (resets the counter) | rescue swallows, nothing retries - GAP | two channels for one class - GAP (`retry: 0` beside `retry_on` is one channel) | two channels plus an inner rescue of the same class - GAP (the rescue wins; keep `retry_on` on an Active Job class) | inherited from ApplicationJob (`retry_on` there, plus Sidekiq's own 25 unless `retry: 0`) - state both | `retry: 25` (the default) on a non-idempotent side effect - GAP (bound it)}

Dead-letter: {dead set + alerting on its size | sidekiq_retries_exhausted hook | dead set, no alerting - GAP | dead set, alerting not in evidence | dead set on first failure (`retry: 0`, `dead` left true) | unreachable - perform swallows every error - GAP | none - GAP (retry: false or dead: false)}

Shutdown safety: {checkpointed per chunk - re-run resumes | short enough to finish inside `timeout` | GAP - long, uncheckpointed work | GAP - supervisor grace shorter than `timeout` (both values; later blocks write `see <first job>`)}

Dispatch: {post-commit | after_all_transactions_commit / after_commit_everywhere | model after_commit | cron/scheduler | rake task | parent job | not in evidence (call site outside the read set) | perform_later inside a transaction - GAP unless enqueue_after_transaction_commit defers it (rails-transaction-patterns) | perform_async inside a transaction - GAP unless Sidekiq.transactional_push! is on (rails-transaction-patterns)}

Versioning: {args carry a version (CURRENT_VERSION) | n/a - the arg contract is unchanged | none - GAP (the contract changes under queued jobs)}
```

## Avoid

- `.perform_async` (undeferred) or any HTTP / S3 / Redis call inside `Model.transaction`
- rescue-and-`perform_in` for retryable errors - resets the retry counter
- `Sidekiq::Testing.inline!` outside tests
