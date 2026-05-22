---
name: rails-rake-task-patterns
description: Rails rake tasks: thin orchestrators, idempotency, chunked transactions, leader lock, fan-out, dry-run, structured logs, signal handling.
metadata:
  category: backend
  tags: [ruby, rails, rake, maintenance, backfill, ops]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Data backfills alongside (not inside) a schema migration
- One-off ops tasks (reprocess stuck records, regenerate derived data)
- Recurring maintenance (cron, whenever, systemd, Kubernetes CronJob)
- Reporting / export producing files
- Bootstrap / seeding beyond `db:seed`
- Tasks triggered from a deploy hook

Not for: logic that belongs in a service (call the service), long-running async with retries (Sidekiq), schema changes (migration), user-triggered actions during a request (controller + service).

## Rules

- Rake tasks are thin orchestrators - parse input, set up logging, call services
- Every data-mutating task supports `DRY_RUN=1`
- Production-mutating tasks require explicit `CONFIRM=yes` when `Rails.env.production?`
- Idempotent - re-runs after partial failure resume, not duplicate
- Always batch over large tables (`find_each` / `in_batches`)
- `task: :environment` when touching Rails
- Structured logs; exit non-zero on failure (raise or `abort`, never `exit`)
- Pass IDs and primitives, not objects
- Group under namespaces matching the domain

## Patterns

### Thin Orchestrator -> Service

```ruby
# Bad - logic in the task
namespace :orders do
  task fulfill_pending: :environment do
    Order.where(status: :pending).find_each do |order|
      order.update!(status: :processing, fulfilled_at: Time.current)
      order.line_items.each { |li| li.product.decrement!(:inventory, li.quantity) }
      ShipmentNotificationJob.perform_async(order.id)
    end
  end
end

# Good - task wires; service does the work
class FulfillPendingOrders
  def self.call(dry_run: false, batch_size: 500)
    new(dry_run: dry_run, batch_size: batch_size).call
  end
end

namespace :orders do
  desc "Fulfill pending orders. ENV: DRY_RUN=1, BATCH_SIZE=500"
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

State-driven (preferred when you can mark per-row):

```ruby
User.where(welcome_sent_at: nil).find_each do |user|
  User.transaction do
    user.update!(welcome_sent_at: Time.current)
    UserMailer.welcome(user).deliver_later
  end
end
```

Checkpoint-based when you can't:

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

### Argument Parsing

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

zsh requires `rake 'customers:recompute[123]'` (square brackets are globs) - document in `desc`.

### Structured Logs and Exit Codes

```ruby
task backfill: :environment do
  started_at = Time.current
  result = BackfillService.call
  Rails.logger.info(task: "users:backfill", status: "ok",
                    processed: result.value[:processed],
                    elapsed_s: (Time.current - started_at).round(2))
rescue => e
  Rails.logger.error(task: "users:backfill", status: "error",
                     class: e.class.name, message: e.message)
  raise  # non-zero exit
end
```

`abort "message"` for expected refusals; `raise` for unexpected errors.

### Rake vs Sidekiq vs Sidekiq Cron

| Need                                | Use                           |
| ----------------------------------- | ----------------------------- |
| One-off backfill, ops-triggered     | Rake task                     |
| Per-row async with retry semantics  | Sidekiq job                   |
| Recurring schedule + per-job retry  | Sidekiq cron                  |
| Recurring schedule, simple, visible | Rake + cron / whenever        |
| Deploy hook (once per release)      | Rake task in deploy script    |

A rake task can fan out to Sidekiq - often the right shape for large backfills.

### Signal Handling

```ruby
task :rebuild => :environment do
  interrupted = false
  Signal.trap("INT")  { interrupted = true }
  Signal.trap("TERM") { interrupted = true }

  Order.in_batches(of: 1_000) do |batch|
    RebuildReportRows.call(orders: batch)
    Rails.cache.write("reports:rebuild:cursor", batch.last.id)
    break if interrupted
  end
end
```

### Concurrent Invocation Guard

```ruby
task rebuild: :environment do
  acquired = ApplicationRecord.with_advisory_lock("reports:rebuild", timeout_seconds: 0) do
    RebuildReports.call
    true
  end
  abort "another reports:rebuild is running; exiting cleanly" unless acquired
end
```

See `rails-db-locking-patterns` for the full leader-election pattern.

### Fan-out to Sidekiq

```ruby
namespace :backfill do
  desc "Recompute totals across N shards. ENV: SHARD_COUNT=8"
  task recompute_totals: :environment do
    shard_count = Integer(ENV.fetch("SHARD_COUNT", 8))
    acquired = ApplicationRecord.with_advisory_lock("backfill:recompute_totals", timeout_seconds: 0) do
      jobs = (0...shard_count).map { |i| [i, shard_count] }
      Sidekiq::Client.push_bulk("class" => "BackfillShardJob", "args" => jobs, "queue" => "low")
      true
    end
    abort "another backfill:recompute_totals is running" unless acquired
  end
end
```

See `rails-work-splitter-patterns` for the decision matrix and `push_bulk` sizing.

### Composition

```ruby
namespace :reports do
  task :nightly => :environment do
    Rake::Task["reports:rebuild"].invoke
    Rake::Task["reports:export"].invoke
  end
end
```

`Rake::Task["foo"].reenable` if a chained task needs to run twice in one process.

### Testing

See `rails-testing-patterns` Rake Task Specs. Behavioral coverage on the service spec; rake spec only verifies wiring.

### File Layout

```
lib/tasks/
  orders.rake          # namespace :orders
  reports.rake         # namespace :reports
app/services/
  fulfill_pending_orders.rb
spec/tasks/
  orders_rake_spec.rb
```

One `.rake` per top-level namespace. Never define tasks in `Rakefile` itself.

## Output Format

```
Task: {namespace:name}
Description: {desc string}
Trigger: {manual | cron | deploy-hook | sidekiq-cron}
Arguments: {positional args and ENV with defaults}
Idempotency: {state-column | checkpoint | natural}
Dry-run: {DRY_RUN=1 supported}
Production gate: {CONFIRM=yes | none}
Service delegated to: {ServiceClassName | "trivial wiring only"}
Exit behavior: {raises on failure | abort on precondition fail}
```

## Avoid

- Business logic in `.rake` files
- Loading entire tables (`Model.all.each`)
- Forgetting `task: :environment`
- Destructive tasks without `DRY_RUN` and production confirmation
- `puts` for progress - use `Rails.logger` structured fields
- `exit 0` after failure - cron sees success; raise or `abort`
- AR objects through `Rake::Task#invoke`
- Top-level tasks (no namespace) - they collide
- Long tasks (>30 min) without resumability
- Re-implementing retry/backoff - use a Sidekiq job
- `default_scope` models inside backfills without `unscoped` - silent row skips
- Skipping `desc` - hidden from `rake -T`
