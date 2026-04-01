---
name: rails-sidekiq-patterns
description: Sidekiq background job patterns for Rails. Covers idempotent job design, retry/backoff strategy, queue priority, error handling, batch processing, deploy-time job versioning, and monitoring.
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
