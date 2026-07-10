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

Not here: logic that belongs in a service (call it from the task); long-running async with retries (`rails-sidekiq-patterns`); schema changes (migration); user-triggered work in a request (controller + service).

## Rules

- Thin orchestrator - parse input, set up logging, call a service
- `task: :environment` whenever touching Rails
- Idempotent - re-runs after partial failure resume, never duplicate
- Batch over large tables (`find_each` / `in_batches`); see `rails-batch-processing-patterns`
- Every data-mutating task supports `DRY_RUN=1` - dry runs write *nothing* (audit rows included) and log would-be actions
- Human-triggered production-mutating tasks require `CONFIRM=yes` when `Rails.env.production?`. Scheduled (cron) tasks omit the gate - baking `CONFIRM=yes` into a manifest is ceremony; their safety is the leader lock plus reviewed, dry-run-tested code
- Tasks needing durable proof (compliance, GDPR) write an audit row in the same transaction as the mutation - logs are not evidence
- Structured logs via `Rails.logger` (no PII in log fields); exit non-zero on failure (`raise` or `abort`, never `exit 0` after an error)
- Pass IDs and primitives through `Rake::Task#invoke`, not AR objects
- Namespace per domain, one `.rake` per top-level namespace, always include `desc`

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

Prefer a state column when you can mark per-row; fall back to a cursor. For multi-day backfills with retry/observability, use a shards table - see `rails-work-splitter-patterns`.

```ruby
# State-driven
User.where(welcome_sent_at: nil).find_each do |user|
  User.transaction do
    user.update!(welcome_sent_at: Time.current)
    UserMailer.welcome(user).deliver_later
  end
end

# Cursor - durable column/table for anything long; Rails.cache can evict mid-run and lose progress
last_id = Checkpoint.for("reports:rebuild").last_id
Order.where("id > ?", last_id).find_in_batches(batch_size: 1_000) do |batch|
  RebuildReportRows.call(orders: batch)
  Checkpoint.for("reports:rebuild").update!(last_id: batch.last.id)
end
```

Loops over independent rows isolate failures: rescue per row, collect errors, log the summary, raise at the end if any failed - one bad record must not abort the remaining 10K. The loop and its rescues live in the service (the task stays a thin wrapper); after a fan-out rewrite the same rule moves to the job.

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

Positional for required identifiers; ENV for optional flags. zsh treats `[]` as globs, so document `rake 'customers:recompute[123]'` quoting in `desc`.

```ruby
task :recompute, [:customer_id] => :environment do |_, args|
  if args[:customer_id]
    RecomputeLtv.call(customer_id: Integer(args[:customer_id]))
  else
    Customer.find_each { |c| RecomputeLtv.call(customer_id: c.id) }
  end
end
```

### Structured Logs and Exit Codes

Use `abort "message"` for expected refusals (preconditions); `raise` for unexpected errors. Both exit non-zero so cron / CI see the failure.

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
  raise
end
```

### Rake vs Sidekiq vs Sidekiq Cron

| Need                                | Use                           |
| ----------------------------------- | ----------------------------- |
| One-off backfill, ops-triggered     | Rake task                     |
| Per-row async with retry semantics  | Sidekiq job                   |
| Recurring schedule + per-job retry  | Sidekiq cron                  |
| Recurring schedule, simple, visible | Rake + cron / whenever        |
| Deploy hook (once per release)      | Rake task in deploy script    |

A rake task often fans out to Sidekiq for large backfills.

### Signal Handling

Persist the cursor (durable checkpoint, per Idempotency) before checking the interrupt flag - on SIGTERM the next run resumes at the last completed batch.

```ruby
task :rebuild => :environment do
  interrupted = false
  Signal.trap("INT")  { interrupted = true }
  Signal.trap("TERM") { interrupted = true }

  Order.in_batches(of: 1_000) do |batch|
    RebuildReportRows.call(orders: batch)
    Checkpoint.for("reports:rebuild").update!(last_id: batch.last.id)
    break if interrupted
  end
end
```

### Leader Lock and Fan-out

A rake task that mutates shared state (or fans out work) takes an advisory lock first - two cron triggers or a manual + cron overlap double-enqueue otherwise. `timeout_seconds: 0` returns false instead of blocking.

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
    unless acquired
      Rails.logger.info(task: "backfill:recompute_totals", skipped: "another run active")
      exit 0   # skip-if-held is expected, not a failure - nonzero would trip cron alerting
    end
  end
end
```

See `rails-db-locking-patterns` for leader-election, `rails-work-splitter-patterns` for the decision matrix and `push_bulk` sizing.

### Composition

```ruby
namespace :reports do
  task :nightly => :environment do
    Rake::Task["reports:rebuild"].invoke
    Rake::Task["reports:export"].invoke
  end
end
```

`invoke` chains fail fast - a raise in step 1 skips the rest, which is right when steps depend on each other. For independent steps, rescue per step, continue, and raise a summary at the end. The composite owns the cross-cutting pieces exactly once: one leader lock around the chain (children don't re-lock) and one set of `Signal.trap`s (per-child traps overwrite each other in the same process). `Rake::Task["foo"].reenable` if a chained task needs to run twice in one process.

### Layout and Testing

```
lib/tasks/orders.rake          # namespace :orders
app/services/fulfill_pending_orders.rb
spec/tasks/orders_rake_spec.rb
```

Behavioral coverage lives on the service spec; the rake spec verifies wiring only. See `rails-testing-patterns` Rake Task Specs.

## Output Format

One block per task (a composite plus its children each get one). In review mode, precede the blocks with numbered findings citing the violated rule; blocks describe the corrected tasks.

```
Task: {namespace:name}
Description: {desc string}
Trigger: {manual | cron | deploy-hook | sidekiq-cron}
Arguments: {positional args and ENV with defaults}
Idempotency: {state-column | checkpoint | natural}
Dry-run: {DRY_RUN=1 supported | n/a (read-only)}
Production gate: {CONFIRM=yes | none (scheduled) | n/a (read-only)}
Service delegated to: {ServiceClassName | "trivial wiring only"}
Exit behavior: {raises on failure | abort on precondition fail}
```

## Avoid

- Business logic in `.rake` files
- Loading entire tables (`Model.all.each`)
- Destructive tasks without `DRY_RUN` and production confirmation
- `puts` for progress - use structured `Rails.logger` fields
- `exit 0` after failure - cron reads success; raise or `abort`
- Top-level tasks (no namespace) - they collide
- Long tasks (>30 min) without resumability
- Re-implementing retry/backoff - use a Sidekiq job
- `default_scope` models inside backfills without `unscoped` - silent row skips
- Cron fan-out without a leader lock - two triggers double-enqueue
