---
name: rails-rake-task-patterns
description: Rails rake task patterns: idempotency, chunked transactions, leader lock, fan-out to Sidekiq, dry-run, structured logs, signal handling.
metadata:
  category: backend
  tags: [ruby, rails, rake, maintenance, backfill, ops]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Data backfills running alongside (not inside) a schema migration
- One-off operational tasks (re-process stuck records, regenerate derived data)
- Recurring maintenance jobs (cron, whenever, systemd, Kubernetes CronJob)
- Reporting/export tasks producing files or pushing to external systems
- Bootstrap/seeding beyond `db:seed`
- Tasks triggered from a deploy hook

Not for:

- Logic that belongs in a service object - rake task should call the service
- Long-running async work with retries - use a Sidekiq job
- Schema changes - use a migration
- User-triggered actions during a request - use a controller + service

## Rules

- Rake tasks are thin orchestrators - they parse input, set up logging, call services. Business logic lives in services or POROs under `app/`
- Every task that mutates data must support `DRY_RUN=1`
- Tasks mutating production data must require explicit confirmation (`CONFIRM=yes` or interactive) when `Rails.env.production?`
- Every task must be idempotent - running it twice must be safe; re-runs after partial failure must resume, not duplicate
- Always batch over large tables with `find_each` / `in_batches`
- Always use `task: :environment` when the task touches Rails
- Log progress with structured fields and exit non-zero on failure
- Pass IDs and primitives, not objects
- Group tasks under namespaces matching the domain
- Never call `exit` inside a task - raise or `abort "message"`

## Patterns

### Thin Orchestrator - Delegate to a Service

Bad - business logic embedded:

```ruby
namespace :orders do
  task fulfill_pending: :environment do
    Order.where(status: :pending).find_each do |order|
      order.update!(status: :processing, fulfilled_at: Time.current)
      order.line_items.each { |li| li.product.decrement!(:inventory, li.quantity) }
      ShipmentNotificationJob.perform_async(order.id)
    end
  end
end
```

Good - rake task is a thin shell around a service:

```ruby
# app/services/fulfill_pending_orders.rb
class FulfillPendingOrders
  def self.call(dry_run: false, batch_size: 500)
    new(dry_run: dry_run, batch_size: batch_size).call
  end

  def call
    Order.where(status: :pending).in_batches(of: @batch_size) do |batch|
      batch.each { |order| process(order) }
    end
    Result.success(processed: @processed, skipped: @skipped)
  end

  private

  def process(order)
    return @skipped += 1 if order.fulfilled_at.present?
    return @processed += 1 if @dry_run
    FulfillOrder.call(order: order)
    @processed += 1
  end
end

# lib/tasks/orders.rake
namespace :orders do
  desc "Fulfill all pending orders. ENV: DRY_RUN=1, BATCH_SIZE=500"
  task fulfill_pending: :environment do
    result = FulfillPendingOrders.call(
      dry_run: ENV["DRY_RUN"] == "1",
      batch_size: Integer(ENV.fetch("BATCH_SIZE", 500))
    )
    Rails.logger.info(task: "orders:fulfill_pending", **result.value)
  end
end
```

### Idempotency and Resumability

Bad - re-running re-emails everyone:

```ruby
task send_welcome_emails: :environment do
  User.find_each { |u| UserMailer.welcome(u).deliver_later }
end
```

Good - state-driven:

```ruby
User.where(welcome_sent_at: nil).find_each do |user|
  User.transaction do
    user.update!(welcome_sent_at: Time.current)
    UserMailer.welcome(user).deliver_later
  end
end
```

Or checkpoint-based when you can't mark per-row state:

```ruby
last_id = Integer(args[:since_id] || Rails.cache.read("reports:rebuild:cursor") || 0)
Order.where("id > ?", last_id).find_in_batches(batch_size: 1_000) do |batch|
  RebuildReportRows.call(orders: batch)
  Rails.cache.write("reports:rebuild:cursor", batch.last.id)
end
```

### Dry Run and Production Confirmation

```ruby
namespace :sessions do
  desc "Purge sessions inactive >90 days. ENV: DRY_RUN=1, CONFIRM=yes"
  task purge_stale: :environment do
    cutoff = 90.days.ago
    scope  = Session.where("last_seen_at < ?", cutoff)
    count  = scope.count

    if Rails.env.production? && ENV["CONFIRM"] != "yes"
      abort "Refusing to purge #{count} sessions in production without CONFIRM=yes"
    end

    if ENV["DRY_RUN"] == "1"
      Rails.logger.info(task: "sessions:purge_stale", dry_run: true, would_delete: count)
      next
    end

    deleted = scope.in_batches(of: 5_000).delete_all
    Rails.logger.info(task: "sessions:purge_stale", deleted: deleted)
  end
end
```

### Batch Processing at Scale

```ruby
task recompute_totals: :environment do
  Order.in_batches(of: 1_000) do |batch|
    Order.transaction do
      batch.includes(:line_items).each do |order|
        total = order.line_items.sum(&:price_cents)
        order.update_columns(total_cents: total) if order.total_cents != total
      end
    end
    sleep(Float(ENV.fetch("THROTTLE_S", 0.1)))
  end
end
```

`find_each` for per-row processing, `in_batches` when you operate on the relation. `update_columns` skips callbacks/validations - use deliberately on backfills.

For chunked-transaction shape, memory safety, and gotchas, see `rails-batch-processing-patterns`.

### Argument Parsing - Positional Args vs ENV

Positional for required identifiers; ENV for optional flags:

```ruby
namespace :customers do
  desc "Recompute LTV. Usage: rake customers:recompute[123] or rake customers:recompute"
  task :recompute, [:customer_id] => :environment do |_, args|
    if args[:customer_id]
      RecomputeLtv.call(customer_id: Integer(args[:customer_id]))
    else
      Customer.find_each { |c| RecomputeLtv.call(customer_id: c.id) }
    end
  end
end
```

zsh requires `rake 'customers:recompute[123]'` (square brackets are globs). Document in `desc`.

### Structured Logging and Exit Codes

```ruby
task backfill: :environment do
  started_at = Time.current
  result = BackfillService.call
  Rails.logger.info(
    task: "users:backfill", status: "ok",
    processed: result.value[:processed],
    elapsed_s: (Time.current - started_at).round(2)
  )
rescue => e
  Rails.logger.error(task: "users:backfill", status: "error",
                     class: e.class.name, message: e.message)
  raise # non-zero exit; cron/CI sees failure
end
```

`abort "message"` for expected refusals (failed precondition, missing CONFIRM); `raise` for unexpected errors.

### Rake Task vs Sidekiq Job vs Sidekiq Cron

| Need                                    | Use                           |
| --------------------------------------- | ----------------------------- |
| One-off backfill, run by ops once       | Rake task                     |
| Per-row async work with retry semantics | Sidekiq job                   |
| Recurring schedule with per-job retries | Sidekiq cron (`sidekiq-cron`) |
| Recurring schedule, simple, ops-visible | Rake task + cron / whenever   |
| Deploy hook (run once per release)      | Rake task in deploy script    |

A rake task can fan out to Sidekiq jobs - often the right shape for large backfills.

### Signal Handling

Long backfills get killed mid-run. Trap signals so the in-flight batch finishes cleanly and the cursor advances:

```ruby
task :rebuild => :environment do
  interrupted = false
  Signal.trap("INT")  { interrupted = true }
  Signal.trap("TERM") { interrupted = true }

  Order.in_batches(of: 1_000) do |batch|
    RebuildReportRows.call(orders: batch)
    Rails.cache.write("reports:rebuild:cursor", batch.last.id)
    if interrupted
      Rails.logger.warn(task: "reports:rebuild", status: "interrupted",
                        cursor: batch.last.id)
      break
    end
  end
end
```

### Concurrent Invocation Guard

Prevent two cron triggers (or manual run during cron) from racing:

```ruby
task rebuild: :environment do
  acquired = ApplicationRecord.with_advisory_lock("reports:rebuild", timeout_seconds: 0) do
    RebuildReports.call
    true
  end
  abort "another reports:rebuild is running; exiting cleanly" unless acquired
end
```

For full leader-election (raw `GET_LOCK` / `pg_try_advisory_lock`, transaction-scoped variants), see `rails-db-locking-patterns`.

### Fan-out to Sidekiq

Common production shape: cron rake task enqueues N Sidekiq jobs, one per shard. Rake is the *coordinator*; Sidekiq jobs are *executors*.

```ruby
namespace :backfill do
  desc "Recompute order totals across N shards. ENV: SHARD_COUNT=8"
  task recompute_totals: :environment do
    shard_count = Integer(ENV.fetch("SHARD_COUNT", 8))

    acquired = ApplicationRecord.with_advisory_lock("backfill:recompute_totals", timeout_seconds: 0) do
      jobs = (0...shard_count).map { |i| [i, shard_count] }
      Sidekiq::Client.push_bulk("class" => "BackfillShardJob",
                                "args" => jobs, "queue" => "low")
      true
    end
    abort "another backfill:recompute_totals is running" unless acquired
  end
end
```

For the work-splitting decision matrix and `push_bulk` sizing, see `rails-work-splitter-patterns`.

### Composition With Other Tasks

```ruby
namespace :reports do
  task :nightly => :environment do
    Rake::Task["reports:rebuild"].invoke
    Rake::Task["reports:export"].invoke
  end
end
```

If a chained task needs to run twice in one process, call `Rake::Task["foo"].reenable`.

### Testing

See `rails-testing-patterns` Rake Task Specs section. Behavioral coverage on the service spec; the rake spec only verifies wiring (ENV parsing, argument forwarding, exit behavior, production confirmation gate).

### File Layout

```
lib/tasks/
  orders.rake          # namespace :orders
  reports.rake         # namespace :reports
  maintenance.rake     # namespace :maintenance
app/services/
  fulfill_pending_orders.rb   # the actual logic
spec/tasks/
  orders_rake_spec.rb
```

One `.rake` per top-level namespace. Never define tasks in `Rakefile` itself.

## Output Format

```
Task: {namespace:name}
Description: {desc string}
Trigger: {manual | cron | deploy-hook | sidekiq-cron}
Arguments: {positional args and ENV vars with defaults}
Idempotency: {state-column guard | checkpoint | natural idempotence}
Dry-run: {DRY_RUN=1 supported, behavior described}
Production gate: {CONFIRM=yes required | none}
Service delegated to: {ServiceClassName or "trivial wiring only"}
Exit behavior: {raises on failure | abort with message on precondition fail}
```

## Avoid

- Business logic in `.rake` files - extract to a service
- Loading entire tables (`Model.all.each`) - always batch
- Forgetting `task: :environment`
- Destructive tasks without `DRY_RUN` and production confirmation
- `puts` for progress - use `Rails.logger` with structured fields
- `exit 0` after a failure - cron thinks the job succeeded; raise or `abort`
- Passing AR objects through `Rake::Task#invoke` - pass IDs
- Top-level tasks (no namespace) - they collide
- Long tasks (>30 min) without resumability - failure starts over from zero
- Re-implementing retry/backoff - if you need that, use a Sidekiq job
- `default_scope` models inside backfills without `unscoped` - silent row skips
- Skipping `desc` - tasks without `desc` are hidden from `rake -T`
