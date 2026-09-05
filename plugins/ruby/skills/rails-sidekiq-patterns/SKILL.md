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
- Enqueue after the DB transaction commits (never inside `Model.transaction`)
- No HTTP / S3 / Redis inside `Model.transaction` - holds row locks for the network round-trip
- Rescue known errors; let unknown propagate to Sidekiq retry
- Cap `perform` at ~5 min; longer jobs split or fan out

## Patterns

### Idempotency

Pick by requirement; combine when requirements combine (list every mechanism used in the Output Format):

| Requirement                                            | Mechanism                                          |
| ------------------------------------------------------ | -------------------------------------------------- |
| Re-run safety (always required)                         | State check in `perform` (DB column, S3 key, etc.) |
| Duplicate enqueues (webhook retries, after_commit bulk) | `sidekiq-unique-jobs` `lock: :until_executed`      |
| Mutual exclusion only (dups allowed, no overlap)        | `lock: :while_executing`                           |
| Both dedup and mutual exclusion                         | `lock: :until_and_while_executing`                 |
| No gem available                                        | Redis `SET NX` fence                               |

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
sidekiq_options lock: :until_executed, on_conflict: :log,
                lock_args_method: ->(args) { [args[0]] }

Sidekiq.redis { |r| r.set("sync_customer:#{id}", "1", nx: true, ex: 60) } or return  # SET NX fence
```

Give every `until_executed` lock a `lock_ttl` - a worker killed without the graceful path (OOM, SIGKILL) orphans the lock, silently blocking all future enqueues for those args until it expires. Size the TTL above worst-case runtime plus retry window.

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

When the service runs inside a caller's transaction, "after the local block" still fires before the outer commit. Use the `after_commit_everywhere` gem - whose method is `after_commit`, not the gem's own name: `include AfterCommitEverywhere` then `after_commit { Job.perform_async(id) }`, or call `AfterCommitEverywhere.after_commit { ... }` directly. A model `after_commit` callback works too. Full transaction-boundary discipline: see `rails-transaction-patterns`.

### Backend Choice

| Choice           | Use When                                                                |
| ---------------- | ----------------------------------------------------------------------- |
| `Sidekiq::Job`   | Default. Direct access to `sidekiq_options`, `sidekiq_retry_in`         |
| `ApplicationJob` | Backend portability, ActiveJob callbacks / `retry_on`, or interop with code that calls `perform_later` |

Converting an existing `ApplicationJob` changes the enqueue API (`perform_later` -> `perform_async`) at every call site - flag it in review, don't silently convert. Inside a `Sidekiq::Job`, mailers use `deliver_now`; the job is already the async boundary.

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
    when ExternalApi::RateLimitError then exception.retry_after || 60 * (count + 1)
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

Pick one retry channel per error class: either let it propagate (counted, `sidekiq_retry_in` controls delay) or rescue-and-`perform_in` (re-enqueue resets the retry counter - unbounded; avoid unless intentional). Per-job `Retry-After` handling doesn't enforce a global rate budget - for hard provider limits, bound concurrency (dedicated low-concurrency queue/capsule or a rate limiter).

Bare `rescue => e; logger.error(...)` swallows errors and blocks retry.

### Payload Discipline

Sidekiq stores every job's args in Redis as JSON. 10 KB x 100K jobs = 1 GB.

- Pass IDs; refetch in `perform`
- For lists, pass ID arrays (not record arrays)
- For large inputs, stage to S3 / a `JobInput` row, pass the key; expire staged rows (TTL or sweep)
- `DeserializationError` from already-enqueued AR-object payloads: fix the enqueue site, then sweep the poisoned jobs - enumerate by class across `Sidekiq::Queue`, `Sidekiq::RetrySet`, and `Sidekiq::ScheduledSet`, then `.delete` or re-enqueue with fixed args

For >100 enqueues at once, use `push_bulk`. Cross-process fan-out, sharding, and `SKIP LOCKED` claim shapes: see `rails-work-splitter-patterns`.

### Graceful Shutdown

On deploy the supervisor - systemd, the k8s kubelet, the dyno manager - sends `SIGTERM` *to* Sidekiq. Sidekiq stops fetching, and at `timeout` seconds (default 25) it re-pushes every still-busy job to its queue **first**, then raises `Sidekiq::Shutdown` into those threads. That order is deliberate: running a job twice beats losing it. (The server-side re-push bypasses client middleware, so uniqueness locks don't drop it.) If the supervisor's own grace period is shorter than Sidekiq's `timeout`, SIGKILL lands before any of this runs and in-flight jobs are simply lost - keep `terminationGracePeriodSeconds` (or the Capistrano/systemd equivalent) above `timeout`. The job's duty is making the re-run resume, not detecting the signal:

- Persist progress per chunk (state column / checkpoint) so the re-pushed job skips completed work
- Never swallow `Sidekiq::Shutdown`. It descends from `Interrupt`, not `StandardError`, so a bare `rescue => e` never catches it - the shapes that do are `rescue Exception` and an explicit `rescue Sidekiq::Shutdown` / `rescue Interrupt`. Either way the re-push has already happened, so swallowing cannot prevent requeue; what it does is let the job keep working in a process about to die while a duplicate is already queued, guaranteeing the redo starts from an inconsistent point
- For cooperative checkpoint-and-interrupt on long iterators, use the `sidekiq-iteration` gem (`each_iteration`)

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

One block per job class (fan-out designs emit one per job). In review or diagnosis mode, precede the blocks with numbered findings citing the violated rule; blocks describe the corrected jobs, so target state lives there. A violation of these rules that does not belong to any job class - an HTTP call inside a transaction, `deliver_later` onto a queue no process consumes - is a numbered finding with no block; say which file it lives in. A field whose evidence is outside the reviewed files is `not in evidence` plus the file to read.

```
Job: {class name}

Queue: {critical | default | mailers | low | custom - name the isolation mechanism: a dedicated process (`-q x -c N`) or, on Sidekiq 7+, a capsule; a queue weight alone does not cap concurrency}

Trigger: {what causes enqueue | not in evidence}

Arguments: {names and types - IDs only; flag any mismatch between `perform`'s arity and what the call site passes}

Idempotency: {state check | sidekiq-unique-jobs lock: <until_executed | while_executing | until_and_while_executing> + lock_ttl | Redis SET NX fence | none - GAP on an at-least-once path - list all that apply}

Retry: {count and backoff strategy; name the single channel that owns it - `sidekiq_options retry:`, ActiveJob `retry_on`, or a bounded in-method loop, never two for one error class}

Dead-letter: {dead set + alerting | sidekiq_retries_exhausted hook | none - GAP}

Shutdown safety: {checkpointed per chunk - re-run resumes | short enough to finish inside `timeout` | GAP - long, uncheckpointed work}

Dispatch: {post-commit | after_commit_everywhere | model after_commit | cron/scheduler}
```

## Avoid

- AR objects, request context (`current_user`, `session`), or payloads > 1 KB as args
- `.perform_async` or any HTTP / S3 / Redis call inside `Model.transaction`
- `rescue => e; log` that swallows errors and blocks retry
- `perform` > ~5 min without splitting or fanning out
- rescue-and-`perform_in` for retryable errors - resets the retry counter
- `Sidekiq::Testing.inline!` outside tests
