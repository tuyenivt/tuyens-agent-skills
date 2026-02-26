---
name: rails-sidekiq-patterns
description: "Sidekiq background job patterns for Rails. Job design, idempotency, retry strategy, queue priority, error handling, job versioning during deploys, Sidekiq Pro/Enterprise patterns."
user-invocable: false
---

## 1. Idempotent Jobs

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

## 2. Pass IDs, Not Objects

```ruby
# ✅ Pass primitive IDs
ProcessOrderJob.perform_async(order.id)

# ❌ NEVER pass ActiveRecord objects
ProcessOrderJob.perform_async(order) # serialization issues, stale data
```

Job arguments must be JSON-serializable: strings, integers, floats, booleans, nil, arrays, hashes.

## 3. Queue Priority

```ruby
# config/sidekiq.yml
:queues:
  - [critical, 6]
  - [default, 3]
  - [low, 1]
  - [mailers, 2]

# Job with specific queue
class ProcessPaymentJob
  include Sidekiq::Job
  sidekiq_options queue: :critical

  def perform(payment_id)
    # ...
  end
end
```

**Queue guidelines:**

- `critical` — payments, auth, time-sensitive
- `default` — standard business logic
- `mailers` — email delivery
- `low` — reports, analytics, cleanup

## 4. Retry Options

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

## 5. Error Handling

```ruby
class SyncExternalDataJob
  include Sidekiq::Job
  sidekiq_options retry: 3

  def perform(resource_id)
    resource = Resource.find(resource_id)
    ExternalApi.sync(resource)
  rescue ExternalApi::RateLimitError => e
    # Known error — retry with delay
    self.class.perform_in(e.retry_after, resource_id)
  rescue ExternalApi::NotFoundError
    # Known error — don't retry
    resource.update!(sync_status: :not_found)
  # Unknown errors propagate → Sidekiq retries automatically
  end
end
```

**Rules:**

- Rescue known errors, handle explicitly
- Let unknown errors propagate for Sidekiq retry
- Never rescue `Exception` — catch `StandardError` subclasses

## 6. Batch Processing

```ruby
# Process large datasets in chunks
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

## 7. Deploy-Time Job Versioning

```ruby
# Problem: jobs enqueued before deploy may run with new code
# Solution: version your job arguments

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

## 8. Monitoring

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

## Anti-Patterns

- ❌ Passing AR objects as arguments — use IDs
- ❌ Jobs > 30 minutes — break into smaller jobs or use batches
- ❌ Request context in jobs — no `current_user`, `session`, `request`
- ❌ Non-idempotent jobs — always design for safe re-execution
- ❌ Catching all exceptions silently — let Sidekiq handle retries
- ❌ Inline execution in production — `Sidekiq::Testing.inline!` is for tests only
