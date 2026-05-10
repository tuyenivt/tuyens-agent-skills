---
name: rails-sidekiq-patterns
description: Sidekiq job patterns: idempotent design, post-commit dispatch, retry/backoff, queue priority, error handling, job versioning.
metadata:
  category: backend
  tags: [ruby, rails, sidekiq, background-jobs, async]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Background processing for async tasks (emails, notifications, API calls, reports)
- Retry and error handling for jobs hitting external services
- Queue priority for mixed workloads
- Dispatching jobs after database transaction commits
- Deploy-time job versioning to prevent argument mismatches
- Debugging failed or stuck jobs

## Rules

- Every job must be idempotent
- Pass IDs as arguments, never AR objects
- Dispatch `.perform_async` AFTER the DB transaction commits
- Rescue known errors explicitly; let unknown errors propagate
- Never rescue `Exception` - only `StandardError` subclasses
- Keep jobs under 30 minutes - break long work into smaller jobs or batches
- Never rely on request context (`current_user`, `session`, `request`) in jobs

## Patterns

### Idempotent Jobs

Bad - no guard, double-processes on retry:

```ruby
def perform(order_id)
  order = Order.find(order_id)
  order.process!
  OrderMailer.confirmation(order).deliver_later
end
```

Good - guard checks state before acting:

```ruby
def perform(order_id)
  order = Order.find(order_id)
  return if order.processed?

  Order.transaction do
    order.process!
    OrderMailer.confirmation(order).deliver_later
  end
end
```

Idempotency strategies:

- Check state before acting (`return if already_done?`)
- Unique constraints to prevent duplicates
- Idempotency keys for external API calls (e.g., Stripe `idempotency_key: "order-#{id}"`)
- `Sidekiq::Job.set(unique_for: 1.hour)` (Sidekiq Enterprise)

### Pass IDs, Not Objects

```ruby
# Bad - serialization issues, stale data
ProcessOrderJob.perform_async(order)

# Good
ProcessOrderJob.perform_async(order.id)
```

Arguments must be JSON-serializable: strings, integers, floats, booleans, nil, arrays, hashes.

### Post-Transaction Dispatch

Bad - worker may fire before commit:

```ruby
ActiveRecord::Base.transaction do
  order.update!(status: :processing)
  ShipmentNotificationJob.perform_async(order.id) # RACE: worker reads stale or missing row
end
```

Good - dispatch after commit:

```ruby
ActiveRecord::Base.transaction do
  order.update!(status: :processing)
  decrement_inventory(order)
end
ShipmentNotificationJob.perform_async(order.id)
```

When the service is itself called inside a caller's transaction, dispatching "after the local block" still fires before the outer commit. Use `after_commit_everywhere`:

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

`after_commit` model callback works when dispatch is tightly coupled to a model transition - but explicit dispatch in services is easier to trace and test:

```ruby
after_commit :enqueue_shipment_notification, on: :update, if: :saved_change_to_status?
```

### Sidekiq vs Rake Task vs ActiveJob

- **Rake task**: foreground, no retries/UI/dead set. Good for ops-triggered work and cron maintenance. See `rails-rake-task-patterns` for the decision matrix.
- **`Sidekiq::Job`** (the new name for `Sidekiq::Worker` since 6.3+): direct access to `sidekiq_options`, `sidekiq_retry_in`, `unique_for`, batches.
- **`ApplicationJob` (ActiveJob)**: abstraction layer that loses Sidekiq-specific features. Default to `Sidekiq::Job` unless you need to swap backends or use Action Mailer's `deliver_later`.

### Queue Priority

```yaml
# config/sidekiq.yml
:queues:
  - [critical, 6]
  - [default, 3]
  - [mailers, 2]
  - [low, 1]
```

| Queue      | Use For                   | Examples                      |
| ---------- | ------------------------- | ----------------------------- |
| `critical` | Time-sensitive, financial | Payments, auth tokens         |
| `default`  | Standard business logic   | Order processing              |
| `mailers`  | Email delivery            | Notifications                 |
| `low`      | Non-urgent                | Reports, analytics, cleanup   |

```ruby
class ShipmentNotificationJob
  include Sidekiq::Job
  sidekiq_options queue: :mailers
end
```

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

Bad - swallows errors, Sidekiq cannot retry:

```ruby
def perform(id)
  ExternalApi.sync(Resource.find(id))
rescue => e
  Rails.logger.error(e.message)
end
```

Good - rescue known, propagate unknown:

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

### Bulk Enqueue

```ruby
class BulkEmailJob
  include Sidekiq::Job
  def perform(user_ids)
    User.where(id: user_ids).find_each do |user|
      UserMailer.weekly_digest(user).deliver_later
    end
  end
end

User.active.in_batches(of: 100) do |batch|
  BulkEmailJob.perform_async(batch.pluck(:id))
end
```

For >100 jobs, prefer `Sidekiq::Client.push_bulk` (one Redis round-trip). See `rails-work-splitter-patterns`.

### Network Calls Inside Transactions

Don't wrap Stripe / S3 / HTTP calls inside `Model.transaction` - the transaction holds row locks for the network round-trip duration. On Stripe slowdown, fleet-wide lock-wait timeouts cascade in seconds.

```ruby
# Bad
def perform(order_id)
  Order.transaction do
    order = Order.find(order_id)
    Stripe::Charge.capture(order.charge_id)   # network call holds locks
    order.update!(status: "fulfilled")
  end
end

# Good - external call outside the transaction; idempotency key makes retry safe
def perform(order_id)
  order = Order.find(order_id)
  return if order.fulfilled?

  Stripe::Charge.capture(order.charge_id, idempotency_key: "fulfill-#{order_id}")

  Order.transaction do
    locked = Order.lock.find(order_id)        # PK lock, short critical section
    next if locked.fulfilled?
    locked.update!(status: "fulfilled", fulfilled_at: Time.current)
  end
end
```

### `SKIP LOCKED` work claiming

For jobs claiming work from a queue table:

```ruby
def perform
  loop do
    claimed_ids = ApplicationRecord.transaction(isolation: :read_committed) do
      ids = WorkItem.where(state: "ready").order(:id).limit(100)
                    .lock("FOR UPDATE SKIP LOCKED").pluck(:id)
      WorkItem.where(id: ids).update_all(state: "claimed")
      ids
    end
    break if claimed_ids.empty?
    claimed_ids.each { |id| process_one(id) }
  end
end
```

**MySQL caveat:** the claim must hit a unique-index path (PK or unique secondary). Per-transaction `READ COMMITTED` reduces gap-lock cascades under contention. **Do not** blanket-set RC on the entire Sidekiq pool - shared services called from web (RR) get different semantics. See `rails-db-locking-patterns` "Three-tier framework" for the full escalation.

### Argument Size and Payload Discipline

Sidekiq stores every job's arguments in Redis as JSON. 10KB payload x 100K queued jobs = 1GB Redis. Keep job arguments small:

- **Pass IDs, fetch in `perform`** - not the order hash
- **For lists, pass ID arrays**, not record arrays
- **For genuinely large inputs**, stage to S3 / `JobInput` table, pass the storage key

Rough budget: <1KB per job's argument payload.

### Uniqueness with `sidekiq-unique-jobs`

Prevents duplicate enqueues - useful when an event handler fires multiple times (webhook retries, after_commit on bulk updates):

```ruby
sidekiq_options lock: :until_executed,
                on_conflict: :log,
                lock_args_method: ->(args) { [args[0]] }
```

`:until_executed` deduplicates from enqueue through completion; `:until_and_while_executing` also blocks during processing.

Ad-hoc dedup without the gem:

```ruby
def perform(customer_id)
  fence = "sync_customer:#{customer_id}"
  return unless Redis.current.set(fence, "1", nx: true, ex: 60)
  # ... real work ...
ensure
  Redis.current.del(fence)
end
```

### Graceful Shutdown

Sidekiq sends `SIGTERM` on deploy; the process has `timeout` seconds (default 25) before `SIGKILL`. Long jobs can be interrupted mid-write.

- Keep `perform` short (>5 min: split)
- Make every checkpoint a transaction - on interrupt, the row reflects pre- or post-state, never half
- Watch for `Sidekiq::Shutdown`:

```ruby
def perform(batch_id)
  Batch.find(batch_id).items.find_each do |item|
    raise Sidekiq::Shutdown if interrupted?
    process(item)
  end
end
```

A re-enqueue on shutdown is fine because the job is idempotent.

### Deploy-Time Job Versioning

Jobs enqueued before a deploy may run with new code. Version arguments:

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

### Cross-cuts

- Connection pool: each Sidekiq thread holds one DB connection. See `rails-connection-pool-sizing`.
- Memory: Ruby GC + glibc fragmentation cause RSS climb. See `rails-batch-processing-patterns` for jemalloc / `WorkerKiller` / partitioning memory-heavy queues.
- Batch shape inside jobs: chunk transactions, never wrap a whole `find_each` in `Model.transaction`. See `rails-batch-processing-patterns`.
- Locking and isolation: see `rails-db-locking-patterns`.

### Monitoring

```ruby
# Sidekiq Web UI
require "sidekiq/web"
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
Idempotency: {guard condition - e.g., "return if order.processed?"}
Retry: {count and backoff strategy}
```

## Avoid

- Passing AR objects as arguments
- Jobs > 30 minutes - break into smaller jobs
- Request context in jobs (no `current_user`, `session`, `request`)
- Non-idempotent jobs
- Catching all exceptions silently
- `Sidekiq::Testing.inline!` in production
- Dispatching `.perform_async` inside a DB transaction
- Network calls inside `Model.transaction` (lock-hold cascade)
- Blanket `READ COMMITTED` on the Sidekiq pool (shared services break silently)
- Missing idempotency guard on state-modifying jobs
