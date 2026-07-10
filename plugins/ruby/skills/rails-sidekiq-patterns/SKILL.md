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

  Stripe::Charge.capture(order.charge_id, idempotency_key: "fulfill-#{order_id}")
  Order.transaction { order.lock!; order.update!(status: "fulfilled", fulfilled_at: Time.current) }
end
```

For external side effects, also forward an idempotency key. For sources that deliver out of order (webhook retries), guard with a monotonic field: return early when the payload's `updated_at` <= the stored one.

```ruby
sidekiq_options lock: :until_executed, on_conflict: :log,
                lock_args_method: ->(args) { [args[0]] }

Sidekiq.redis { |r| r.set("sync_customer:#{id}", "1", nx: true, ex: 60) } or return  # SET NX fence
```

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

When the service runs inside a caller's transaction, "after the local block" still fires before the outer commit. Use `after_commit_everywhere { Job.perform_async(id) }` or a model `after_commit` callback. Full transaction-boundary discipline: see `rails-transaction-patterns`.

### Backend Choice

| Choice           | Use When                                                                |
| ---------------- | ----------------------------------------------------------------------- |
| `Sidekiq::Job`   | Default. Direct access to `sidekiq_options`, `sidekiq_retry_in`         |
| `ApplicationJob` | Only when swapping backends or using `deliver_later` / `Mail#deliver_later` |

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

Time-sensitive / financial -> `critical`. Email -> `mailers`. Reports / cleanup -> `low`.

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
- `DeserializationError` from already-enqueued AR-object payloads: fix the enqueue site, then drain or discard the poisoned jobs

For >100 enqueues at once, use `push_bulk`. Cross-process fan-out, sharding, and `SKIP LOCKED` claim shapes: see `rails-work-splitter-patterns`.

### Graceful Shutdown

Sidekiq sends `SIGTERM` on deploy, stops fetching, and at `timeout` seconds (default 25) raises `Sidekiq::Shutdown` into still-busy threads and re-pushes their jobs - no opt-in needed. (The server-side re-push bypasses client middleware, so uniqueness locks don't drop it.) The job's duty is making that re-run resume, not detecting the signal:

- Persist progress per chunk (state column / checkpoint) so the re-pushed job skips completed work
- Never swallow `Sidekiq::Shutdown` in a broad `rescue` - let it propagate so the re-push happens
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

One block per job class (fan-out designs emit one per job):

```
Job: {class name}
Queue: {critical | default | mailers | low | custom (state why - e.g. dedicated concurrency cap)}
Trigger: {what causes enqueue}
Arguments: {names and types - IDs only}
Idempotency: {state check | sidekiq-unique-jobs | Redis fence - list all that apply}
Retry: {count and backoff strategy}
Dispatch: {post-commit | after_commit_everywhere | model after_commit | cron/scheduler}
```

## Avoid

- AR objects, request context (`current_user`, `session`), or payloads > 1 KB as args
- `.perform_async` or any HTTP / S3 / Redis call inside `Model.transaction`
- `rescue => e; log` that swallows errors and blocks retry
- `perform` > ~5 min without splitting or fanning out
- rescue-and-`perform_in` for retryable errors - resets the retry counter
- `Sidekiq::Testing.inline!` outside tests
