---
name: rails-sidekiq-patterns
description: Sidekiq job patterns for Rails: idempotent design, retry/backoff, queue priority, error handling, batch processing, job versioning.
metadata:
  category: backend
  tags: [ruby, rails, sidekiq, background-jobs, async]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Adding background processing for async tasks (emails, notifications, API calls, reports)
- Designing retry and error handling for jobs that interact with external services
- Setting up queue priority for mixed workloads (critical payments vs. low-priority reports)
- Dispatching jobs after database transaction commits
- Handling deploy-time job versioning to prevent argument mismatches
- Debugging failed or stuck Sidekiq jobs

## Rules

- Every job must be idempotent - running it twice must produce the same result
- Pass IDs as arguments, never ActiveRecord objects - arguments must be JSON-serializable
- Dispatch `.perform_async` AFTER the DB transaction commits, never inside it - the worker may read stale data or a row that does not exist yet
- Rescue known errors explicitly, let unknown errors propagate for Sidekiq retry
- Never rescue `Exception` - only catch `StandardError` subclasses
- Keep jobs under 30 minutes - break long-running work into smaller jobs or batches
- Never rely on request context (`current_user`, `session`, `request`) in jobs

## Patterns

### Idempotent Jobs

Bad - no idempotency guard (double-processing on retry):

```ruby
class ProcessOrderJob
  include Sidekiq::Job

  def perform(order_id)
    order = Order.find(order_id)
    order.process!
    OrderMailer.confirmation(order).deliver_later
  end
end
```

Good - idempotency guard checks state before acting:

```ruby
class ProcessOrderJob
  include Sidekiq::Job

  def perform(order_id)
    order = Order.find(order_id)
    return if order.processed? # idempotency guard

    Order.transaction do
      order.process!
      OrderMailer.confirmation(order).deliver_later
    end
  end
end
```

**Idempotency strategies:**

- Check state before acting (`return if already_done?`)
- Use unique constraints to prevent duplicates
- Use `Sidekiq::Job.set(unique_for: 1.hour)` (Sidekiq Enterprise)
- Design jobs so running twice produces the same result

### Pass IDs, Not Objects

Bad - passes ActiveRecord object (serialization issues, stale data):

```ruby
ProcessOrderJob.perform_async(order)
```

Good - passes primitive ID:

```ruby
ProcessOrderJob.perform_async(order.id)
```

Job arguments must be JSON-serializable: strings, integers, floats, booleans, nil, arrays, hashes.

### Post-Transaction Dispatch

Bad - job enqueued inside transaction (worker may fire before commit):

```ruby
ActiveRecord::Base.transaction do
  order.update!(status: :processing)
  ShipmentNotificationJob.perform_async(order.id) # RACE CONDITION
end
```

Good - dispatch after transaction commits:

```ruby
ActiveRecord::Base.transaction do
  order.update!(status: :processing)
  decrement_inventory(order)
end
# Transaction committed - worker will find the row
ShipmentNotificationJob.perform_async(order.id)
```

Alternative - use `after_commit` callback when dispatch is tightly coupled to a model transition:

```ruby
class Order < ApplicationRecord
  after_commit :enqueue_shipment_notification, on: :update, if: :saved_change_to_status?

  private

  def enqueue_shipment_notification
    return unless status == "processing"
    ShipmentNotificationJob.perform_async(id)
  end
end
```

Prefer explicit post-transaction dispatch in services over `after_commit` callbacks - callbacks are harder to trace and test. Use callbacks only when the dispatch must always happen on a specific model transition regardless of which service triggers it.

When a service is itself called inside a caller's transaction, dispatching "after the local block" still fires before the outer commit. Either restructure so the service owns the outermost transaction, or use the `after_commit_everywhere` gem / `ActiveRecord::Base.connection.add_transaction_record(...)` to defer until the true outer commit:

```ruby
require "after_commit_everywhere"

class FulfillOrder
  include AfterCommitEverywhere

  def call
    ActiveRecord::Base.transaction do
      @order.update!(status: :processing)
      after_commit { ShipmentNotificationJob.perform_async(@order.id) }
    end
    Result.success(@order.reload)
  end
end
```

### Sidekiq vs Rake Task

Sidekiq jobs give you retries, a dead set, a UI, and per-job concurrency. Rake tasks are simpler and run in the foreground - good for ops-triggered work and cron-driven maintenance. A rake task can fan out to Sidekiq jobs for large batches. See `rails-rake-task-patterns` for the decision matrix and fan-out pattern.

### Sidekiq vs ActiveJob

Direct `Sidekiq::Job` (the new name for `Sidekiq::Worker` since Sidekiq 6.3+) gives access to Sidekiq-specific features: `sidekiq_options`, `sidekiq_retry_in`, `unique_for`, batches. ActiveJob's `ApplicationJob` adds an abstraction layer that loses these. Default to `Sidekiq::Job` unless you need to swap backends or use Action Mailer's `deliver_later` (which goes through ActiveJob).

### Queue Priority

```yaml
# config/sidekiq.yml
:queues:
  - [critical, 6]
  - [default, 3]
  - [low, 1]
  - [mailers, 2]
```

| Queue      | Use For                   | Examples                      |
| ---------- | ------------------------- | ----------------------------- |
| `critical` | Time-sensitive, financial | Payments, auth tokens         |
| `default`  | Standard business logic   | Order processing, fulfillment |
| `mailers`  | Email delivery            | Notifications, confirmations  |
| `low`      | Non-urgent, deferrable    | Reports, analytics, cleanup   |

```ruby
class ShipmentNotificationJob
  include Sidekiq::Job
  sidekiq_options queue: :mailers

  def perform(order_id)
    order = Order.find(order_id)
    return unless order.processing? # idempotency guard
    OrderMailer.shipment_notification(order).deliver_now
  end
end
```

### Retry and Backoff

```ruby
class ImportDataJob
  include Sidekiq::Job
  sidekiq_options retry: 5,           # max retries (default: 25)
                  dead: true,          # send to dead set after exhaustion
                  backtrace: true      # store backtrace in Redis

  sidekiq_retry_in do |count, exception|
    case exception
    when RateLimitError then 60 * (count + 1) # linear backoff
    else (count ** 4) + 15 + (rand(10) * (count + 1)) # exponential
    end
  end

  def perform(import_id)
    # ...
  end
end
```

### Error Handling

Bad - rescuing all exceptions silently:

```ruby
def perform(resource_id)
  ExternalApi.sync(Resource.find(resource_id))
rescue => e
  Rails.logger.error(e.message) # swallowed - Sidekiq cannot retry
end
```

Good - rescue known errors explicitly, let unknown errors propagate:

```ruby
class SyncExternalDataJob
  include Sidekiq::Job
  sidekiq_options retry: 3

  def perform(resource_id)
    resource = Resource.find(resource_id)
    ExternalApi.sync(resource)
  rescue ExternalApi::RateLimitError => e
    # Known transient error - schedule retry with delay
    self.class.perform_in(e.retry_after, resource_id)
  rescue ExternalApi::NotFoundError
    # Known permanent error - don't retry, update state
    resource.update!(sync_status: :not_found)
  # Unknown errors propagate -> Sidekiq retries automatically
  end
end
```

### Batch Processing

Bad - single job processes entire dataset (timeout risk):

```ruby
class BulkEmailJob
  include Sidekiq::Job
  def perform
    User.active.each { |u| UserMailer.digest(u).deliver_now }
  end
end
```

Good - enqueue in batches:

```ruby
class BulkEmailJob
  include Sidekiq::Job

  def perform(user_ids)
    User.where(id: user_ids).find_each do |user|
      UserMailer.weekly_digest(user).deliver_later
    end
  end
end

# Enqueue in batches
User.active.in_batches(of: 100) do |batch|
  BulkEmailJob.perform_async(batch.pluck(:id))
end
```

### Argument Size and Payload Discipline

Sidekiq stores every job's arguments in Redis as JSON. A 10KB payload x 100K queued jobs = 1GB of Redis - the kind of incident that wakes the on-call. Keep job arguments small:

- **Pass IDs, fetch in `perform`**. Don't pass the order hash; pass the order ID.
- **For lists, pass ID arrays, not record arrays**. `BulkEmailJob.perform_async(user_ids)` not the user objects.
- **For genuinely large inputs** (a 5MB CSV, a multi-thousand-row report), stage the data: write to S3 / a `JobInput` table, pass the storage key.

Rough budget: a single job's argument payload should be under 1KB. Sidekiq Pro's `client_middleware` can enforce this in CI; failing that, log argument byte size in development to catch drift early.

### Uniqueness with `sidekiq-unique-jobs`

`sidekiq-unique-jobs` (community gem) prevents duplicate enqueues - useful when an event handler may fire several times for the same record (webhook retries, after_commit callbacks on bulk updates):

```ruby
class SyncCustomerJob
  include Sidekiq::Job
  sidekiq_options lock: :until_executed,        # one job per (class, args) until perform completes
                  on_conflict: :log,            # other strategies: :reject, :replace
                  lock_args_method: ->(args) { [args[0]] } # uniqueness based on customer_id only
end
```

`:until_executed` deduplicates from enqueue through completion; `:until_and_while_executing` also blocks new enqueues during processing. Choose the lock window deliberately - too tight allows duplicates, too loose blocks legitimate re-runs.

For ad-hoc dedup without the gem, use a `Redis::SETNX` fence inside `perform`:

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

Sidekiq sends jobs `SIGTERM` on deploy; the process has a configurable timeout (default 25s) to finish in-flight work before `SIGKILL`. Long jobs can be interrupted mid-write. Defenses:

- **Keep `perform` short** - if the work takes >5 minutes, break into smaller jobs.
- **Make every checkpoint a transaction** - on interrupt, the row reflects either pre- or post-state, never half.
- **Watch for `Sidekiq::Shutdown`** in long inner loops to exit cleanly:

```ruby
def perform(batch_id)
  Batch.find(batch_id).items.find_each do |item|
    raise Sidekiq::Shutdown if interrupted?
    process(item)
  end
end

private

def interrupted?
  Sidekiq::ProcessSet.new.find { |p| p["identity"] == Sidekiq.identity }&.fetch("quiet") == "true"
end
```

A re-enqueue on shutdown is fine because the job is idempotent (which it must be).

### Deploy-Time Job Versioning

Jobs enqueued before a deploy may run with new code. Version arguments to handle this:

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

# Always enqueue with current version
ProcessOrderJob.perform_async(order.id, ProcessOrderJob::CURRENT_VERSION)
```

### Monitoring

```ruby
# Sidekiq Web UI
# config/routes.rb
require "sidekiq/web"
mount Sidekiq::Web => "/sidekiq"

# Protect with authentication
Sidekiq::Web.use Rack::Auth::Basic do |username, password|
  ActiveSupport::SecurityUtils.secure_compare(username, ENV["SIDEKIQ_USER"]) &
    ActiveSupport::SecurityUtils.secure_compare(password, ENV["SIDEKIQ_PASSWORD"])
end

# Monitor dead set
dead = Sidekiq::DeadSet.new
dead.size
dead.each { |job| puts job.display_class }

# Queue latency (time jobs wait before processing)
Sidekiq::Queue.new("default").latency # in seconds
```

## Output Format

When generating Sidekiq jobs, document each job:

```
Job: {class name}
Queue: {critical | default | mailers | low}
Trigger: {what causes this job to be enqueued}
Arguments: {list of argument names and types}
Idempotency: {guard condition - e.g., "return if order.processed?"}
Retry: {count and backoff strategy}
```

## Avoid

- Passing AR objects as arguments - use IDs
- Jobs > 30 minutes - break into smaller jobs or use batches
- Request context in jobs - no `current_user`, `session`, `request`
- Non-idempotent jobs - always design for safe re-execution
- Catching all exceptions silently - let Sidekiq handle retries
- `Sidekiq::Testing.inline!` in production - it is for tests only
- Dispatching `.perform_async` inside a DB transaction - worker races the commit
- Missing idempotency guard on jobs that modify state
