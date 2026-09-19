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
- Every state-mutating task supports `DRY_RUN=1` - dry runs write *nothing* (audit rows included) and log would-be actions; the shorter examples below elide the flag to show one concern each. "State" includes the job queue and external writes (S3 puts, API calls): a task whose only effect is `perform_async` in a loop still enqueues real work, so it needs the flag and the gate as much as one that writes rows
- Human-triggered production-mutating tasks require `CONFIRM=yes` when `Rails.env.production?`. Scheduled (cron) and deploy-hook tasks omit the gate - baking `CONFIRM=yes` into a manifest is ceremony; their safety is the leader lock plus reviewed, dry-run-tested code. A task with both triggers gates the manual path only
- Tasks needing durable proof write an audit row in the same transaction as the mutation - logs are not evidence. It needs one when the mutation is irreversible and someone may later have to prove what it touched: deletions and anonymisation of regulated data, money movement, permission changes. Reversible recomputes of derived values do not
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
# State-driven. The mail is enqueued after commit, not inside the transaction: enqueued
# inside, a rollback still leaves the job queued (and welcome_sent_at nil), so the re-run
# mails twice - the exact duplication this pattern exists to prevent.
User.where(welcome_sent_at: nil).find_each do |user|
  User.transaction { user.update!(welcome_sent_at: Time.current) }
  UserMailer.welcome(user).deliver_later
end

# Cursor - durable column/table for anything long; Rails.cache can evict mid-run and lose progress
last_id = Checkpoint.for("reports:rebuild").last_id.to_i   # `id > NULL` matches nothing on a fresh row
Order.where("id > ?", last_id).find_in_batches(batch_size: 1_000) do |batch|
  RebuildReportRows.call(orders: batch)
  Checkpoint.for("reports:rebuild").update!(last_id: batch.last.id)
end
```

Write the cursor after its batch commits - one transaction per batch, never one around the scan (`rails-batch-processing-patterns`). Inside an outer transaction the cursor rolls back with everything; written before its batch commits, it advances past unprocessed rows.

Loops over independent rows isolate failures: rescue per row, collect errors, log the summary, raise at the end if any failed - one bad record must not abort the remaining 10K. The loop and its rescues live in the service (the task stays a thin wrapper); after a fan-out rewrite the same rule moves to the job.

### Dry Run and Production Confirmation

```ruby
namespace :sessions do
  desc "Purge sessions inactive >90 days. ENV: DRY_RUN=1, CONFIRM=yes"
  task purge_stale: :environment do
    cutoff = 90.days.ago
    scope  = Session.where("last_seen_at < ?", cutoff)
    count  = scope.count

    if ENV["DRY_RUN"] == "1"   # dry run first: read-only, so no CONFIRM gate
      Rails.logger.info(task: "sessions:purge_stale", dry_run: true, would_delete: count)
      next
    end

    if Rails.env.production? && ENV["CONFIRM"] != "yes"
      abort "Refusing to purge #{count} sessions in production without CONFIRM=yes"
    end

    deleted = scope.in_batches(of: 5_000).delete_all
    Rails.logger.info(task: "sessions:purge_stale", deleted: deleted)
  end
end
```

### Argument Parsing

Positional for required identifiers; ENV for optional flags. zsh treats `[]` as globs, so document `rake 'customers:recompute[123]'` quoting in `desc`.

```ruby
namespace :customers do
  desc "Recompute LTV for one customer, or all. Quote in zsh: rake 'customers:recompute[123]'"
  task :recompute, [:customer_id] => :environment do |_, args|
    if args[:customer_id]
      RecomputeLtv.call(customer_id: Integer(args[:customer_id]))
    else
      Customer.find_each { |c| RecomputeLtv.call(customer_id: c.id) }
    end
  end
end
```

### Structured Logs and Exit Codes

Use `abort "message"` for expected refusals (preconditions); `raise` for unexpected errors. Both exit non-zero so cron / CI see the failure.

```ruby
namespace :users do
  desc "Backfill user rollups"
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
namespace :reports do
  desc "Rebuild report rows; resumable, SIGTERM-safe"
  task rebuild: :environment do
    interrupted = false
    Signal.trap("INT")  { interrupted = true }
    Signal.trap("TERM") { interrupted = true }

    checkpoint = Checkpoint.for("reports:rebuild")
    # Seed the scope FROM the checkpoint, or the next run redoes every completed batch.
    Order.where("id > ?", checkpoint.last_id.to_i).in_batches(of: 1_000) do |batch|
      RebuildReportRows.call(orders: batch)
      checkpoint.update!(last_id: batch.last.id)
      break if interrupted
    end
  end
end
```

### Leader Lock and Fan-out

A rake task that mutates shared state (or fans out work) and can be triggered twice - cron, or cron plus a manual run - takes an advisory lock first; two cron triggers or a manual + cron overlap double-enqueue otherwise. A manual-only task relies on the operator. `timeout_seconds: 0` returns false instead of blocking.

```ruby
namespace :backfill do
  desc "Recompute totals across N shards. ENV: SHARD_COUNT=8, DRY_RUN=1"   # cron-triggered: no CONFIRM gate
  task recompute_totals: :environment do
    shard_count = Integer(ENV.fetch("SHARD_COUNT", 8))
    acquired = ApplicationRecord.with_advisory_lock("backfill:recompute_totals", timeout_seconds: 0) do
      jobs = (0...shard_count).map { |i| [i, shard_count] }
      if ENV["DRY_RUN"] == "1"
        Rails.logger.info(task: "backfill:recompute_totals", dry_run: true, would_enqueue: jobs.size)
      else
        Sidekiq::Client.push_bulk("class" => "BackfillShardJob", "args" => jobs, "queue" => "low")
      end
      true
    end
    unless acquired
      Rails.logger.info(task: "backfill:recompute_totals", skipped: "another run active")
      next   # leaves this task only. `exit 0` would end the whole process, so as a chained
             # child it would silently skip every remaining step and report success to cron
    end
  end
end
```

See `rails-db-locking-patterns` for leader-election, `rails-work-splitter-patterns` for the decision matrix and `push_bulk` sizing.

### Composition

```ruby
namespace :reports do
  desc "Rebuild then export report rows"
  task :nightly => :environment do
    Rake::Task["reports:rebuild"].invoke
    Rake::Task["reports:export"].invoke
  end
end
```

`invoke` chains fail fast - a raise in step 1 skips the rest, which is right when steps depend on each other. For independent steps, rescue per step, continue, and raise a summary at the end. The composite owns the cross-cutting pieces exactly once: one leader lock around the chain and one set of `Signal.trap`s (per-child traps overwrite each other in the same process; keep the interrupt flag in a shared home - a module attribute like `Maintenance.interrupted` - so children's batch loops can check it). Chain-only children don't lock; a child that also runs standalone (its own cron entry or routine manual use) keeps its own lock and its own traps, and skips both when chained - the composite sets `Maintenance.chained = true` before invoking and the child checks it. Re-entrancy is per lock *name*: only if the child requests the same name as the composite is the chained acquisition free. A differently-named child lock is a genuine second acquisition - harmless on PG and MySQL 5.7+, but not a no-op, so give it a distinct name deliberately rather than by accident. `Rake::Task["foo"].reenable` if a chained task needs to run twice in one process.

### Layout and Testing

```
lib/tasks/orders.rake          # namespace :orders
app/services/fulfill_pending_orders.rb
spec/tasks/orders_rake_spec.rb
```

Behavioral coverage lives on the service spec; the rake spec verifies wiring only. See `rails-testing-patterns` Rake Task Specs.

## Output Format

One block per task (a composite plus its children each get one). In review or diagnosis mode, precede the blocks with numbered findings, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Blocks describe the corrected tasks, so target state lives there. In build mode, a pre-existing violation the change touches, or a scenario fact the fixture contradicts (a cron entry the manifest lacks), is a numbered finding too. A task absent from every schedule file in scope is `manual`. A non-compliant field is written as the observed value plus ` - GAP`; the target lives in the findings and the rest of the block.

```
Task: {namespace:name}

Description: {desc string}

Trigger: {manual | cron (CronJob, whenever, systemd timer) | deploy-hook | chained (invoked by <composite>) - list all that apply, and add `schedule file not in scope` when the trigger is asserted but its manifest is not}

Arguments: {positional args and ENV with defaults}

Idempotency: {state-column | checkpoint | natural (the operation is inherently repeatable - a recompute from source, an upsert on a unique key) | n/a (composite - orchestrates only) | none - GAP}

Leader lock: {advisory lock "<name>", timeout_seconds: 0 | none - chain-only child, the composite holds "<name>" | none - manual-only trigger | none - non-mutating | none - GAP (cron or fan-out)}

Checkpoint / signal handling: {durable cursor + interrupt flag checked per batch | composite: shared trap, children check Maintenance.interrupted | natural - the idempotent scope re-derives progress | n/a - bounded run (minutes) | none - GAP for anything long-running}

Dry-run: {DRY_RUN=1 supported | n/a (read-only) | missing - GAP}

Production gate: {CONFIRM=yes (manual path) | none (scheduled or deploy-hook) | n/a (read-only) | missing - GAP (human-triggered, mutating)}

Audit trail: {row in mutation txn (compliance/GDPR) | logs only (no durable-proof need) | needed, table absent - GAP}

Service delegated to: {ServiceClassName | "trivial wiring only"}

Exit behavior: {raises on failure | abort on precondition fail | clean skip via `next` when the leader lock is held | `next` after a dry run - list all that apply}
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
