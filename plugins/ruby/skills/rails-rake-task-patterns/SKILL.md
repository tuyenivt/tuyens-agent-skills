---
name: rails-rake-task-patterns
description: Rails Rake task patterns: idempotency, batch processing, env safety guards, dry-run, structured logs, service composition, RSpec.
metadata:
  category: backend
  tags: [ruby, rails, rake, maintenance, backfill, ops]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing data backfills that run alongside (not inside) a schema migration
- One-off operational tasks (re-process stuck records, regenerate derived data, recompute counters)
- Recurring maintenance jobs invoked by cron, whenever, systemd timers, or Kubernetes CronJob
- Reporting/export tasks that produce files or push to external systems
- Bootstrap and seeding tasks beyond `db:seed` (per-environment fixtures, demo data)
- Any task triggered from a deploy hook (e.g., post-release cache warm, index rebuild)

Not for:

- Logic that belongs in a service object - the rake task should call the service, not reimplement it
- Long-running async work with retries - use a Sidekiq job (rake tasks have no retry, no dead set, no UI)
- Schema changes - use a migration, not a rake task
- User-triggered actions during a request - use a controller + service

## Rules

- Rake tasks are thin orchestrators - they parse input, set up logging, and call services. Business logic lives in services or PORO classes under `app/`, never in the `Rakefile` or `lib/tasks/*.rake`
- Every task that mutates data must support `DRY_RUN=1` and log what it would do without writing
- Tasks that mutate production data must require an explicit confirmation gate (`CONFIRM=yes` or interactive prompt) when `Rails.env.production?`
- Every task must be idempotent - running it twice must be safe. Re-runs after partial failure must resume, not duplicate
- Always batch over large tables with `find_each` / `in_batches` - never load entire tables into memory
- Always use `task: :environment` when the task touches Rails (models, config, services); never `require "config/environment"` manually
- Log progress with structured fields (count processed, count skipped, elapsed) and exit non-zero on failure so cron/CI can detect it
- Pass IDs and primitives as arguments, not objects. Prefer ENV vars for optional flags, positional task args for required identifiers
- Group tasks under a namespace that matches the domain (`namespace :orders do ... end`), never put loose tasks at the top level of `lib/tasks/`
- Never call `exit` from inside a task - raise an exception or `abort "message"` so Rake records failure correctly

## Patterns

### Thin Orchestrator - Delegate to a Service

Bad - business logic embedded in the rake file (untestable, unreusable, no Result handling):

```ruby
# lib/tasks/orders.rake
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

  def initialize(dry_run:, batch_size:)
    @dry_run = dry_run
    @batch_size = batch_size
    @processed = 0
    @skipped = 0
  end

  def call
    Order.where(status: :pending).in_batches(of: @batch_size) do |batch|
      batch.each { |order| process(order) }
    end
    Result.success(processed: @processed, skipped: @skipped)
  end

  private

  def process(order)
    return @skipped += 1 if order.fulfilled_at.present? # idempotency guard
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

The service is testable in isolation; the rake task is trivial enough that an integration test of the rake invocation is cheap.

### Idempotency and Resumability

Bad - no guard, re-running re-emails everyone:

```ruby
task send_welcome_emails: :environment do
  User.find_each { |u| UserMailer.welcome(u).deliver_later }
end
```

Good - state-driven idempotency, safe to re-run:

```ruby
task send_welcome_emails: :environment do
  User.where(welcome_sent_at: nil).find_each do |user|
    User.transaction do
      user.update!(welcome_sent_at: Time.current)
      UserMailer.welcome(user).deliver_later
    end
  end
end
```

For tasks that cannot mark per-row state, use a checkpoint:

```ruby
namespace :reports do
  task :rebuild, [:since_id] => :environment do |_, args|
    last_id = Integer(args[:since_id] || Rails.cache.read("reports:rebuild:cursor") || 0)
    Order.where("id > ?", last_id).find_in_batches(batch_size: 1_000) do |batch|
      RebuildReportRows.call(orders: batch)
      Rails.cache.write("reports:rebuild:cursor", batch.last.id)
    end
  end
end
```

### Dry Run and Production Confirmation

Bad - destructive task with no safeguards:

```ruby
task purge_stale_sessions: :environment do
  Session.where("last_seen_at < ?", 90.days.ago).delete_all
end
```

Good - dry-run by default in production, explicit opt-in to write:

```ruby
namespace :sessions do
  desc "Purge sessions inactive >90 days. ENV: DRY_RUN=1 (default in prod), CONFIRM=yes to write"
  task purge_stale: :environment do
    cutoff = 90.days.ago
    scope = Session.where("last_seen_at < ?", cutoff)
    count = scope.count

    if Rails.env.production? && ENV["CONFIRM"] != "yes"
      abort "Refusing to purge #{count} sessions in production without CONFIRM=yes"
    end

    if ENV["DRY_RUN"] == "1"
      Rails.logger.info(task: "sessions:purge_stale", dry_run: true, would_delete: count, cutoff: cutoff)
      next
    end

    deleted = scope.in_batches(of: 5_000).delete_all
    Rails.logger.info(task: "sessions:purge_stale", deleted: deleted, cutoff: cutoff)
  end
end
```

### Batch Processing at Scale

Bad - loads entire table into memory; lock-prone:

```ruby
task recompute_totals: :environment do
  Order.all.each { |o| o.update!(total_cents: o.line_items.sum(:price_cents)) }
end
```

Good - batched, low-lock, throttled:

```ruby
task recompute_totals: :environment do
  Order.in_batches(of: 1_000) do |batch|
    Order.transaction do
      batch.includes(:line_items).each do |order|
        total = order.line_items.sum(&:price_cents)
        order.update_columns(total_cents: total) if order.total_cents != total
      end
    end
    sleep(Float(ENV.fetch("THROTTLE_S", 0.1))) # gentle on replicas
  end
end
```

`find_each` for per-row processing, `in_batches` when you can operate on the relation (`update_all`, `delete_all`). `update_columns` skips callbacks and validations - use deliberately on backfills where you know the data shape.

### Argument Parsing - Positional Args vs ENV

Use positional args for required identifiers; use ENV for optional flags:

```ruby
namespace :customers do
  desc "Recompute LTV for one customer or all. Usage: rake customers:recompute[123] or rake customers:recompute"
  task :recompute, [:customer_id] => :environment do |_, args|
    if args[:customer_id]
      RecomputeLtv.call(customer_id: Integer(args[:customer_id]))
    else
      Customer.find_each { |c| RecomputeLtv.call(customer_id: c.id) }
    end
  end
end
```

Quoting note: zsh requires `rake 'customers:recompute[123]'` (square brackets are globs). Document this in the `desc` to save users five minutes of debugging.

### Structured Logging and Exit Codes

Bad - `puts` only, swallows errors, exits 0 on failure:

```ruby
task backfill: :environment do
  begin
    BackfillService.call
    puts "done"
  rescue => e
    puts "error: #{e.message}"
  end
end
```

Good - structured log fields, propagates failure:

```ruby
task backfill: :environment do
  started_at = Time.current
  result = BackfillService.call
  Rails.logger.info(
    task: "users:backfill",
    status: "ok",
    processed: result.value[:processed],
    elapsed_s: (Time.current - started_at).round(2)
  )
rescue => e
  Rails.logger.error(task: "users:backfill", status: "error", class: e.class.name, message: e.message)
  raise # non-zero exit, cron/CI sees failure
end
```

`abort "message"` for expected refusals (failed precondition, missing CONFIRM); `raise` for unexpected errors so the backtrace surfaces.

### Rake Task vs Sidekiq Job vs Sidekiq Cron

| Need                                    | Use                           |
| --------------------------------------- | ----------------------------- |
| One-off backfill, run by ops once       | Rake task                     |
| Per-row async work with retry semantics | Sidekiq job                   |
| Recurring schedule with per-job retries | Sidekiq cron (`sidekiq-cron`) |
| Recurring schedule, simple, ops-visible | Rake task + cron / whenever   |
| Deploy hook (run once per release)      | Rake task in deploy script    |

Rule of thumb: if the work needs retries, a UI, or a dead set, it is a Sidekiq job. If it is fire-and-forget maintenance with cron-level retry semantics, it is a rake task. A rake task can fan out to Sidekiq jobs - that is often the right shape for large backfills.

```ruby
task backfill_user_segments: :environment do
  User.where(segment: nil).in_batches(of: 1_000) do |batch|
    SegmentBackfillJob.perform_bulk(batch.pluck(:id).map { |id| [id] })
  end
end
```

### Signal Handling and Concurrent Invocation Guard

Long backfills get killed mid-run - by Kubernetes when the pod is rescheduled, by an ops engineer typing Ctrl-C, by systemd on host reboot. Trap signals so the in-flight batch finishes cleanly and the cursor advances. Without this, the next run repeats the killed batch (wasted work) or skips it (lost work, depending on idempotency).

```ruby
namespace :reports do
  task :rebuild => :environment do
    interrupted = false
    Signal.trap("INT")  { interrupted = true }
    Signal.trap("TERM") { interrupted = true }

    Order.in_batches(of: 1_000) do |batch|
      RebuildReportRows.call(orders: batch)
      Rails.cache.write("reports:rebuild:cursor", batch.last.id)
      if interrupted
        Rails.logger.warn(task: "reports:rebuild", status: "interrupted", cursor: batch.last.id)
        break
      end
    end
  end
end
```

Use a PostgreSQL advisory lock to prevent two cron triggers (or a manual run during cron) from racing on the same dataset:

```ruby
task backfill: :environment do
  ActiveRecord::Base.connection.execute("SELECT pg_advisory_lock(#{"backfill".hash})")
  begin
    BackfillService.call
  ensure
    ActiveRecord::Base.connection.execute("SELECT pg_advisory_unlock(#{"backfill".hash})")
  end
end
```

The second invocation blocks until the first releases - or use `pg_try_advisory_lock` and `abort` immediately if the lock is held, depending on the desired behavior.

### Composition With Other Tasks

Use `Rake::Task#invoke` for one-time chaining; use `enhance` to add steps to an existing task. Avoid `prerequisites` for slow tasks that you do not always want to run.

```ruby
namespace :reports do
  task :nightly => :environment do
    Rake::Task["reports:rebuild"].invoke
    Rake::Task["reports:export"].invoke
  end
end
```

If a chained task needs to run twice in one process (e.g., during tests), call `Rake::Task["foo"].reenable` between invocations.

### Testing Rake Tasks

See `rails-testing-patterns` (Rake Task Specs section) for the recipe. The rule: behavioral coverage lives on the service spec; the rake spec only verifies wiring - ENV parsing, argument forwarding, exit behavior, and any production confirmation gate. Load tasks with `Rails.application.load_tasks` once per suite and `task.reenable` after each example.

### File Layout

```
lib/tasks/
  orders.rake          # namespace :orders
  reports.rake         # namespace :reports
  maintenance.rake     # namespace :maintenance (purge, vacuum, reindex)
app/services/
  fulfill_pending_orders.rb   # the actual logic, called by the rake task
spec/tasks/
  orders_rake_spec.rb
```

One `.rake` file per top-level namespace. Never define tasks in `Rakefile` itself - it should only require the Rails application.

## Output Format

When generating a rake task, document each task:

```
Task: {namespace:name}
Description: {desc string - shown in `rake -T`}
Trigger: {manual | cron | deploy-hook | sidekiq-cron}
Arguments: {positional args and ENV vars with defaults}
Idempotency: {state-column guard | checkpoint | natural idempotence}
Dry-run: {DRY_RUN=1 supported, behavior described}
Production gate: {CONFIRM=yes required | none | not-applicable}
Service delegated to: {ServiceClassName or "none - trivial wiring only"}
Exit behavior: {raises on failure | abort with message on precondition fail}
```

## Avoid

- Business logic in `.rake` files - extract to a service or PORO under `app/`
- Loading entire tables (`Model.all.each`) - always batch with `find_each` / `in_batches`
- Forgetting `task: :environment` - the task will fail at the first model reference
- Destructive tasks without `DRY_RUN` and without a production confirmation gate
- `puts` for progress - use `Rails.logger` with structured fields so cron/log aggregation can parse it
- Calling `exit 0` after a failure - cron will think the job succeeded; raise or `abort` instead
- Passing ActiveRecord objects through `Rake::Task#invoke` - pass IDs
- Defining tasks at the top level (no namespace) - they collide and pollute `rake -T`
- Long-running tasks (>30 min) without resumability - on failure you start over from zero
- Re-implementing retry/backoff in a rake task - if you need that, the work belongs in a Sidekiq job
- Using `default_scope` models inside backfills without `unscoped` - silent row skips
- Skipping the `desc` line - tasks without `desc` are hidden from `rake -T` and forgotten
