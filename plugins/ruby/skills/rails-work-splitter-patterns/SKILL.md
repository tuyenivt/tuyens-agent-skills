---
name: rails-work-splitter-patterns
description: Split batch work across Rake/Sidekiq: modulo shards, SKIP LOCKED cursors, shards-table, rake fan-out with leader lock and push_bulk.
metadata:
  category: backend
  tags: [ruby, rails, sidekiq, rake, batch, mysql, postgresql, concurrency]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Splitting a long backfill, recompute, or export across N parallel workers
- Designing a queue-shaped worker that drains items across multiple Sidekiq processes
- Building a cron-triggered rake task that fans out to Sidekiq with bounded parallelism
- Choosing between modulo partitioning, `SKIP LOCKED` cursors, and a shards table
- Reviewing a backfill that "loops over the whole table in one process" at 100M+ rows

## Rules

- Pick one idiom (modulo / SKIP LOCKED / shards-table) deliberately - mixing creates ambiguity about row ownership
- Idempotency at shard granularity - any single shard re-runnable without side effects
- A rake task that fans out must take a leader lock first
- `push_bulk` in batches of 1000 - larger blows Redis memory, smaller wastes round-trips
- `SKIP LOCKED` claim queries hit a unique-index path (PK or unique secondary), never a non-unique scan
- Persist cursor / shard state so process kill doesn't lose progress
- Cap parallelism at the slowest shared resource (DB connections, replication lag, third-party rate limit)

## Patterns

### Decision matrix

| Workload shape                                    | Pattern                | Why                                              |
| ------------------------------------------------- | ---------------------- | ------------------------------------------------ |
| Static dataset, uniform distribution              | Modulo partitioning    | No lock cost; reshard rare                       |
| Stream of new work items (queue-shaped)           | `SKIP LOCKED` cursor   | Naturally drains; tolerates worker crashes       |
| One-shot backfill of >100M rows, observability needed | Shards table       | Resumable, observable, throttle per-shard        |
| Skewed data (60% in last 18 months)               | Shards table with equal-row ranges | Modulo would skew badly                |
| Per-tenant or per-customer batches                | Modulo or shards table on tenant_id | Natural sharding key                  |
| Continuous queue with strict per-key ordering     | Single-worker queue / Sidekiq Pro | `SKIP LOCKED` doesn't preserve order  |

### Pattern (a): static modulo partitioning

Cheapest. No lock needed.

```ruby
class BackfillShardJob
  include Sidekiq::Job

  def perform(shard_index, shard_count)
    Order.where("id % ? = ?", shard_count, shard_index).find_each do |order|
      next if order.recomputed_at.present?
      order.recompute_total!
    end
  end
end

8.times { |i| BackfillShardJob.perform_async(i, 8) }
```

Pros: trivial, no contention. Cons: skew if data isn't uniform; reshard requires re-running everything.

### Pattern (b): cursor-based claim with `SKIP LOCKED`

Each worker claims a small batch, processes, marks done. Multiple workers safe by construction. MySQL 8.0+, PostgreSQL 9.5+.

```ruby
class DrainQueueJob
  include Sidekiq::Job
  BATCH = 100

  def perform
    loop do
      claimed_ids = ApplicationRecord.transaction(isolation: :read_committed) do
        ids = WorkItem.where(state: "ready").order(:id).limit(BATCH)
                      .lock("FOR UPDATE SKIP LOCKED").pluck(:id)
        WorkItem.where(id: ids).update_all(state: "claimed", claimed_at: Time.current)
        ids
      end
      break if claimed_ids.empty?
      claimed_ids.each { |id| process_one(id) }
    end
  end
end
```

**MySQL caveat:** the `SKIP LOCKED` query must hit a unique-index path (here `order(:id) limit N` uses the PK) to avoid gap-locking. Under default `REPEATABLE READ`, wrap the claim transaction in **per-transaction RC** at the call site (shown above). See `rails-db-locking-patterns` for the three-tier isolation framework.

**PostgreSQL note:** default RC makes the `isolation:` parameter unnecessary on PG.

**Idempotency:** `process_one` must be safe to re-run because a worker can crash after `claimed` but before completing.

### Pattern (c): shards table

For very large tables, pre-compute id ranges into a `backfill_shards` table. Each shard tracks its own cursor and retry count.

```ruby
class CreateBackfillShards < ActiveRecord::Migration[7.2]
  def change
    create_table :backfill_shards do |t|
      t.string  :name, null: false
      t.bigint  :start_id, null: false
      t.bigint  :end_id, null: false
      t.string  :state, null: false, default: "pending"
      t.bigint  :cursor
      t.integer :retries, null: false, default: 0
      t.text    :last_error
      t.datetime :claimed_at
      t.datetime :completed_at
      t.timestamps
    end
    add_index :backfill_shards, [:name, :state]
  end
end
```

Pre-compute shards once. **For skewed data, use equal-row ranges (not equal-id ranges)** - keyset-traverse with `OFFSET shard_size LIMIT 1` to find boundaries:

```ruby
def self.create_order_shards(name:, shard_size: 100_000)
  cursor = Order.minimum(:id) - 1
  while (boundary = Order.where("id > ?", cursor).order(:id).offset(shard_size - 1).limit(1).pick(:id))
    BackfillShard.create!(name: name, start_id: cursor + 1, end_id: boundary, state: "pending")
    cursor = boundary
  end
  # Last shard
  if (last_max = Order.where("id > ?", cursor).maximum(:id))
    BackfillShard.create!(name: name, start_id: cursor + 1, end_id: last_max, state: "pending")
  end
end
```

Worker claims a shard:

```ruby
class BackfillShardWorker
  include Sidekiq::Job

  def perform(shard_name)
    loop do
      shard = ApplicationRecord.transaction(isolation: :read_committed) do
        s = BackfillShard.where(name: shard_name, state: "pending")
                         .order(:id).limit(1)
                         .lock("FOR UPDATE SKIP LOCKED").first
        break unless s
        s.update!(state: "claimed", claimed_at: Time.current)
        s
      end
      break unless shard
      process_shard(shard)
    end
  end

  private

  def process_shard(shard)
    cursor = shard.cursor || (shard.start_id - 1)
    Order.where(id: (cursor + 1)..shard.end_id).in_batches(of: 1_000) do |batch|
      ApplicationRecord.transaction { batch.each(&:recompute_total!) }
      shard.update_columns(cursor: batch.last.id)
    end
    shard.update!(state: "done", completed_at: Time.current)
  rescue => e
    shard.update!(state: "failed", retries: shard.retries + 1, last_error: e.message)
    raise
  end
end
```

Pros: full observability (`SELECT state, COUNT(*) FROM backfill_shards GROUP BY state`), recoverable on crash, throttle by varying worker count.

### Pattern: rake task fans out with leader lock

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

Variants:

- **Shards-table fan-out**: rake seeds the table once, then enqueues `BackfillShardWorker.perform_async(shard_name)` N times.
- **`SKIP LOCKED` queue draining**: replace rake with Sidekiq cron entry that enqueues `DrainQueueJob` N times - workers self-coordinate.

### `push_bulk` sizing

Batch in chunks of 1000:

```ruby
Order.where(state: "stale").in_batches(of: 1_000) do |batch|
  Sidekiq::Client.push_bulk("class" => ArchiveOrderJob,
                            "args" => batch.pluck(:id).map { |id| [id] })
end
```

>5000 args risks blowing Redis client buffer; <100 wastes round-trips.

### Sidekiq Batches (Pro / Enterprise)

For completion callbacks ("notify when all 1000 jobs finish"):

```ruby
batch = Sidekiq::Batch.new
batch.description = "recompute_totals run #{Time.current.iso8601}"
batch.on(:complete, BackfillNotifier, run_id: SecureRandom.uuid)
batch.jobs do
  Order.where(state: "stale").in_batches(of: 1_000) do |b|
    Sidekiq::Client.push_bulk("class" => BackfillShardJob,
                              "args" => b.pluck(:id).map { |id| [id] })
  end
end
```

Without Pro: the shards-table pattern's `SELECT COUNT(*) ... WHERE state != 'done'` works.

### Resumability and retry budgets

Every long splitter must answer:

- **Cursor persistence**: `Rails.cache.write`, shard row, or state column on the work table
- **Idempotency at chunk level**: see `rails-batch-processing-patterns`
- **Retry budget**: Sidekiq default 25 is too many for systemic failure. `sidekiq_options retry: 5` and route exhausted jobs to a dead set with alerting
- **Signal handling**: trap SIGINT/SIGTERM in long rake tasks (see `rails-rake-task-patterns`)

### Throttling

Without a cap, N workers driving the DB at full tilt produce replication lag spikes, connection exhaustion, lock-wait cascades.

Knobs:
- Sidekiq concurrency per process (`concurrency: 5` for memory- or query-heavy queues)
- Per-shard sleep between batches (`sleep(0.05)` after each `in_batches`)
- Replication-lag-aware throttle - check `Aurora_replica_lag` or `pg_stat_replication.replay_lag` between batches; pause if above threshold
- Token bucket via Redis for rate-limited downstream services
- `gh-ost` / `pt-online-schema-change` for very large MySQL backfills (built-in throttling on lag and disk usage)

### MySQL vs PostgreSQL specifics for `SKIP LOCKED`

- MySQL 8.0+: works; under default RR, wrap in per-transaction RC for queue claims
- MySQL 5.7: no `SKIP LOCKED` - use modulo or shards-table
- PostgreSQL 9.5+: works with default RC; no isolation override needed

### Anti-pattern: parallel workers updating overlapping ranges

```ruby
# Bad - both workers claim the same rows
# Worker A
Order.where(state: "stale", region: "us").update_all(state: "archived")
# Worker B (started in parallel)
Order.where(state: "stale", region: "us").update_all(state: "archived")
```

The second update is a no-op but progress reporting double-counts. Use one of the three documented patterns.

## Output Format

```
Workload: {static backfill | streaming queue | per-tenant batch | one-shot migration}
Volume: {row count, expected runtime}
Pattern: {modulo partitioning | SKIP LOCKED cursor | shards table}
Parallelism: {N workers, capped by {DB connections | replication lag | rate limit}}
Coordination: {leader lock for fan-out | row lock per claim | none}
Cursor / state: {where progress is persisted}
Idempotency: {state column | cursor | shard table | natural}
Retry budget: {Sidekiq retries: N, dead-set alerting: yes/no}
Throttling: {none | per-batch sleep | replication-lag check | gh-ost}
```

## Avoid

- Mixing two work-splitting idioms in the same job
- Modulo partitioning when data is skewed - use equal-row shards table
- `SKIP LOCKED` queries that hit non-unique scans - gap-lock cascades on MySQL RR
- Cron-fan-out without a leader lock - two simultaneous triggers double-enqueue
- `push_bulk` calls of >5000 args
- Forgetting cursor persistence - SIGTERM mid-shard loses progress
- Running backfill at full DB throughput - replication lag spikes
- Optimistic locking on the claim path - `StaleObjectError` storms
- Treating Sidekiq retries as the resumability strategy - design for shard-level retry instead
