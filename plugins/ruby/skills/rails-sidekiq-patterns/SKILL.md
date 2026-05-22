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

Cross-references:
- DB pool sizing per worker thread -> `rails-connection-pool-sizing`
- RSS growth, jemalloc, `WorkerKiller`, chunked transactions inside jobs -> `rails-batch-processing-patterns`
- Locking, isolation tiers, advisory locks -> `rails-db-locking-patterns`
- Bulk push, work-splitter fan-out -> `rails-work-splitter-patterns`

## Rules

- Every job idempotent - check state before acting
- Pass IDs only, never AR objects
- Dispatch `.perform_async` **after** the DB transaction commits
- No HTTP / S3 / Redis calls inside `Model.transaction` - holds row locks for the network round-trip
- Rescue known errors; let unknown propagate to Sidekiq retry
- Job arg payload < 1 KB - large inputs go to S3 / a row, pass the key
- Never rely on request context (`current_user`, `session`, `request`)

## Patterns

### Idempotency

```ruby
def perform(order_id)
  order = Order.find(order_id)
  return if order.processed?

  Order.transaction do
    order.process!
  end
end
```

Strategies: state check, unique constraint, idempotency key forwarded to external API (`Stripe::Charge.create(idempotency_key: "order-#{id}")`), `sidekiq_options lock: :until_executed` from `sidekiq-unique-jobs`.

### Post-Commit Dispatch

```ruby
# Bad - worker races the commit
ActiveRecord::Base.transaction do
  order.update!(status: :processing)
  ShipmentNotificationJob.perform_async(order.id)
end

# Good - dispatch after commit
ActiveRecord::Base.transaction do
  order.update!(status: :processing)
end
ShipmentNotificationJob.perform_async(order.id)
```

When the service is itself called from a caller's transaction, dispatching "after the local block" still fires before the outer commit. Use `after_commit_everywhere`:

```ruby
require "after_commit_everywhere"

class FulfillOrder
  include AfterCommitEverywhere
  def call
    ActiveRecord::Base.transaction do
      @order.update!(status: :processing)
      after_commit { ShipmentNotificationJob.perform_async(@order.id) }
    end
  end
end
```

Model `after_commit` callback works when dispatch is tightly coupled to a state transition; explicit dispatch in services is easier to trace and test.

### `Sidekiq::Job` vs `ActiveJob` vs Rake

- **`Sidekiq::Job`** (renamed from `Sidekiq::Worker` in 6.3+): direct access to `sidekiq_options`, `sidekiq_retry_in`, `unique_for`, batches. Default choice.
- **`ApplicationJob` (ActiveJob)**: backend-agnostic wrapper; loses Sidekiq-specific features. Use only when swapping backends or for Action Mailer's `deliver_later`.
- **Rake task**: foreground, no retries/UI. Ops-triggered / cron maintenance - see `rails-rake-task-patterns`.

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

### Retry and Backoff

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
end
```

### Error Handling

```ruby
def perform(id)
  resource = Resource.find(id)
  ExternalApi.sync(resource)
rescue ExternalApi::RateLimitError => e
  self.class.perform_in(e.retry_after, id)
rescue ExternalApi::NotFoundError
  resource.update!(sync_status: :not_found)
# Unknown errors propagate -> Sidekiq retries
end
```

Bare `rescue => e; logger.error(...)` swallows errors and prevents retry.

### Network Calls Inside Transactions

External call inside `Model.transaction` holds row locks for the network round-trip. On upstream slowdown, fleet-wide lock-wait timeouts cascade.

```ruby
# Good - external call outside the transaction; idempotency key makes retry safe
def perform(order_id)
  order = Order.find(order_id)
  return if order.fulfilled?

  Stripe::Charge.capture(order.charge_id, idempotency_key: "fulfill-#{order_id}")

  Order.transaction do
    locked = Order.lock.find(order_id)
    next if locked.fulfilled?
    locked.update!(status: "fulfilled", fulfilled_at: Time.current)
  end
end
```

### `SKIP LOCKED` Work Claim

```ruby
def perform
  loop do
    claimed = ApplicationRecord.transaction(isolation: :read_committed) do
      ids = WorkItem.where(state: "ready").order(:id).limit(100)
                    .lock("FOR UPDATE SKIP LOCKED").pluck(:id)
      WorkItem.where(id: ids).update_all(state: "claimed")
      ids
    end
    break if claimed.empty?
    claimed.each { |id| process_one(id) }
  end
end
```

MySQL: claim must hit a unique-index path (PK / unique secondary). Per-transaction `:read_committed` reduces gap-lock cascades. Do **not** set RC on the whole Sidekiq pool - shared services called from web (RR) get different semantics. See `rails-db-locking-patterns`.

### Bulk Enqueue

For >100 jobs, use `push_bulk` (one Redis round-trip):

```ruby
User.active.in_batches(of: 1_000) do |batch|
  Sidekiq::Client.push_bulk(
    "class" => UserWeeklyDigestJob,
    "args"  => batch.pluck(:id).map { |id| [id] }
  )
end
```

See `rails-work-splitter-patterns` for orchestrator -> per-record fan-out.

### Payload Discipline

Sidekiq stores every job's arguments in Redis as JSON. 10 KB x 100 K jobs = 1 GB.

- Pass IDs; fetch in `perform`
- For lists, pass ID arrays
- For large inputs, stage to S3 / a `JobInput` row, pass the key

### Uniqueness

`sidekiq-unique-jobs` prevents duplicate enqueues (webhook retries, after_commit on bulk updates):

```ruby
sidekiq_options lock: :until_executed,
                on_conflict: :log,
                lock_args_method: ->(args) { [args[0]] }
```

Ad-hoc with Redis `SET NX`:

```ruby
def perform(customer_id)
  fence = "sync_customer:#{customer_id}"
  return unless Redis.current.set(fence, "1", nx: true, ex: 60)
  # ... work ...
ensure
  Redis.current.del(fence)
end
```

### Graceful Shutdown

Sidekiq sends `SIGTERM` on deploy, then `SIGKILL` after `timeout` seconds (default 25).

- Keep `perform` short (>5 min: split)
- Every checkpoint = a transaction - on interrupt, the row is pre- or post-state, never half
- For long iterators, check `interrupted?` and raise `Sidekiq::Shutdown`:

```ruby
Batch.find(id).items.find_each do |item|
  raise Sidekiq::Shutdown if interrupted?
  process(item)
end
```

A re-enqueue on shutdown is safe because the job is idempotent.

### Deploy-Time Versioning

Jobs enqueued before a deploy may execute against new code. Version arguments when the contract changes:

```ruby
class ProcessOrderJob
  include Sidekiq::Job
  CURRENT_VERSION = 2

  def perform(order_id, version = 1)
    case version
    when 1 then process_v1(order_id)
    when 2 then process_v2(order_id)
    end
  end
end

ProcessOrderJob.perform_async(order.id, ProcessOrderJob::CURRENT_VERSION)
```

### Monitoring

```ruby
mount Sidekiq::Web => "/sidekiq"
Sidekiq::Web.use Rack::Auth::Basic do |u, p|
  ActiveSupport::SecurityUtils.secure_compare(u, ENV["SIDEKIQ_USER"]) &
    ActiveSupport::SecurityUtils.secure_compare(p, ENV["SIDEKIQ_PASSWORD"])
end

Sidekiq::DeadSet.new.size
Sidekiq::Queue.new("default").latency
```

## Output Format

```
Job: {class name}
Queue: {critical | default | mailers | low}
Trigger: {what causes enqueue}
Arguments: {names and types}
Idempotency: {guard - "return if order.processed?" or unique key}
Retry: {count and backoff strategy}
```

## Avoid

- AR objects as arguments (use IDs)
- Jobs > 30 minutes (split)
- Request context (`current_user`, `session`, `request`)
- `.perform_async` inside a DB transaction
- HTTP / S3 / Redis inside `Model.transaction`
- `rescue => e; log` that swallows errors and blocks retry
- Blanket `READ COMMITTED` on the Sidekiq pool
- Argument payloads > 1 KB
- `Sidekiq::Testing.inline!` outside tests
