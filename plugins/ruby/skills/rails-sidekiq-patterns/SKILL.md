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

State check is the default. For external side effects, also forward an idempotency key.

```ruby
def perform(order_id)
  order = Order.find(order_id)
  return if order.fulfilled?

  Stripe::Charge.capture(order.charge_id, idempotency_key: "fulfill-#{order_id}")
  Order.transaction { order.lock!; order.update!(status: "fulfilled", fulfilled_at: Time.current) }
end
```

For duplicate-enqueue prevention (webhook retries, after_commit on bulk updates), prefer `sidekiq-unique-jobs`:

```ruby
sidekiq_options lock: :until_executed, on_conflict: :log,
                lock_args_method: ->(args) { [args[0]] }
```

Ad-hoc fence with Redis `SET NX` when the gem isn't available:

```ruby
Sidekiq.redis { |r| r.set("sync_customer:#{id}", "1", nx: true, ex: 60) } or return
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
    when RateLimitError then 60 * (count + 1)
    else (count ** 4) + 15 + (rand(10) * (count + 1))
    end
  end

  def perform(id)
    resource = Resource.find(id)
    ExternalApi.sync(resource)
  rescue ExternalApi::RateLimitError => e
    self.class.perform_in(e.retry_after, id)
  rescue ExternalApi::NotFoundError
    resource.update!(sync_status: :not_found)
  # Unknown errors propagate -> Sidekiq retries
  end
end
```

Bare `rescue => e; logger.error(...)` swallows errors and blocks retry.

### Payload Discipline

Sidekiq stores every job's args in Redis as JSON. 10 KB x 100K jobs = 1 GB.

- Pass IDs; refetch in `perform`
- For lists, pass ID arrays (not record arrays)
- For large inputs, stage to S3 / a `JobInput` row, pass the key

For >100 enqueues at once, use `push_bulk`. Cross-process fan-out, sharding, and `SKIP LOCKED` claim shapes: see `rails-work-splitter-patterns`.

### Graceful Shutdown

Sidekiq sends `SIGTERM` on deploy, then `SIGKILL` after `timeout` seconds (default 25). Idempotent jobs are safe to re-enqueue. For long iterators, check `interrupted?`:

```ruby
Batch.find(id).items.find_each do |item|
  raise Sidekiq::Shutdown if interrupted?
  process(item)
end
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

```
Job: {class name}
Queue: {critical | default | mailers | low}
Trigger: {what causes enqueue}
Arguments: {names and types - IDs only}
Idempotency: {state check | unique key | sidekiq-unique-jobs | Redis fence}
Retry: {count and backoff strategy}
Dispatch: {post-commit | after_commit_everywhere | model after_commit}
```

## Avoid

- AR objects, request context (`current_user`, `session`), or payloads > 1 KB as args
- `.perform_async` or any HTTP / S3 / Redis call inside `Model.transaction`
- `rescue => e; log` that swallows errors and blocks retry
- Jobs > 30 min (split or fan out)
- `Sidekiq::Testing.inline!` outside tests
