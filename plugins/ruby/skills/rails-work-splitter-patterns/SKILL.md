---
name: rails-work-splitter-patterns
description: Split batch work across Rake/Sidekiq: modulo shards, SKIP LOCKED cursors, shards table, fan-out with leader lock and push_bulk.
metadata:
  category: backend
  tags: [ruby, rails, sidekiq, rake, batch, mysql, postgresql, concurrency]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Splitting a long backfill / recompute / export across N parallel workers
- Designing a queue-shaped worker draining items across Sidekiq processes
- Cron-triggered rake fanning out to Sidekiq with bounded parallelism
- Choosing between modulo, `SKIP LOCKED`, and a shards table
- Reviewing a backfill that "loops over the whole table in one process" at 100M+ rows

## Rules

- Pick one idiom (modulo / SKIP LOCKED / shards table) - mixing creates ambiguous row ownership
- Idempotency at shard granularity
- Rake task that fans out takes a leader lock first
- `push_bulk` in batches of 1000 - larger blows Redis memory, smaller wastes round-trips
- `SKIP LOCKED` claims hit a unique-index path (PK or unique secondary), never non-unique scan
- Persist cursor / shard state so SIGTERM doesn't lose progress
- Cap parallelism at the slowest shared resource (DB connections, replication lag, third-party rate limit)

## Patterns

### Decision matrix

| Workload                                        | Pattern             | Why                                       |
| ----------------------------------------------- | ------------------- | ----------------------------------------- |
| Static dataset, uniform distribution            | Modulo partitioning | No lock cost; reshard rare                |
| Stream of new work (queue-shaped)               | `SKIP LOCKED`       | Naturally drains; tolerates crashes       |
| One-shot backfill of >100M rows, observable     | Shards table        | Resumable, observable, throttle per-shard |
| Skewed data (60% in last 18 months)             | Shards table with equal-row ranges | Modulo would skew      |
| Per-tenant batches                              | Modulo or shards on tenant_id | Natural sharding key            |
| Continuous queue with strict per-key ordering   | Single-worker queue / Sidekiq Pro | `SKIP LOCKED` won't preserve order |

### (a) Static modulo partitioning

Cheapest. No lock.

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

### (b) `SKIP LOCKED` cursor

MySQL 8.0+, PostgreSQL 9.5+. Each worker claims a batch, processes, marks done. Multiple workers safe by construction.

```ruby
class DrainQueueJob
  include Sidekiq::Job
  BATCH = 100

  def perform
    loop do
      claimed = ApplicationRecord.transaction(isolation: :read_committed) do
        ids = WorkItem.where(state: "ready").order(:id).limit(BATCH)
                      .lock("FOR UPDATE SKIP LOCKED").pluck(:id)
        WorkItem.where(id: ids).update_all(state: "claimed", claimed_at: Time.current)
        ids
      end
      break if claimed.empty?
      claimed.each { |id| process_one(id) }
    end
  end
end
```

**MySQL caveat:** the claim hits a unique-index path (here `order(:id) limit N` uses PK). Under default RR, wrap the claim in per-transaction RC (shown). See `rails-db-locking-patterns`.

**PostgreSQL:** default RC makes the `isolation:` parameter unnecessary.

**Idempotency:** `process_one` must be safe to re-run - a worker can crash after `claimed` but before completing.

### (c) Shards table

For very large tables, pre-compute id ranges. Each shard tracks its own cursor and retry count.

```ruby
create_table :backfill_shards do |t|
  t.string   :name, null: false
  t.bigint   :start_id, null: false
  t.bigint   :end_id, null: false
  t.string   :state, null: false, default: "pending"
  t.bigint   :cursor
  t.integer  :retries, null: false, default: 0
  t.text     :last_error
  t.datetime :claimed_at
  t.datetime :completed_at
  t.timestamps
end
add_index :backfill_shards, [:name, :state]
```

For skewed data, use equal-row ranges (not equal-id):

```ruby
def self.create_order_shards(name:, shard_size: 100_000)
  cursor = Order.minimum(:id) - 1
  while (boundary = Order.where("id > ?", cursor).order(:id).offset(shard_size - 1).limit(1).pick(:id))
    BackfillShard.create!(name: name, start_id: cursor + 1, end_id: boundary, state: "pending")
    cursor = boundary
  end
  if (last_max = Order.where("id > ?", cursor).maximum(:id))
    BackfillShard.create!(name: name, start_id: cursor + 1, end_id: last_max, state: "pending")
  end
end
```

Worker:

```ruby
class BackfillShardWorker
  include Sidekiq::Job

  def perform(shard_name)
    loop do
      shard = ApplicationRecord.transaction(isolation: :read_committed) do
        s = BackfillShard.where(name: shard_name, state: "pending")
                         .order(:id).limit(1).lock("FOR UPDATE SKIP LOCKED").first
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

Full observability: `SELECT state, COUNT(*) FROM backfill_shards GROUP BY state`. Throttle by varying worker count.

### Rake fan-out with leader lock

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

Variants:
- Shards-table fan-out: rake seeds the table once, then enqueues `BackfillShardWorker.perform_async(shard_name)` N times
- `SKIP LOCKED` draining: replace rake with Sidekiq cron entry enqueuing `DrainQueueJob` N times - workers self-coordinate

### `push_bulk` sizing

```ruby
Order.where(state: "stale").in_batches(of: 1_000) do |batch|
  Sidekiq::Client.push_bulk("class" => ArchiveOrderJob,
                            "args" => batch.pluck(:id).map { |id| [id] })
end
```

>5000 args risks blowing the Redis client buffer; <100 wastes round-trips.

### Sidekiq Batches (Pro / Enterprise)

For completion callbacks ("notify when all 1000 jobs finish"):

```ruby
batch = Sidekiq::Batch.new
batch.description = "recompute_totals run #{Time.current.iso8601}"
batch.on(:complete, BackfillNotifier, run_id: SecureRandom.uuid)
batch.jobs do
  Order.where(state: "stale").in_batches(of: 1_000) do |b|
    Sidekiq::Client.push_bulk("class" => BackfillShardJob, "args" => b.pluck(:id).map { |id| [id] })
  end
end
```

Without Pro: the shards-table pattern's `SELECT COUNT(*) ... WHERE state != 'done'` works.

### Resumability and retry budgets

- Cursor persistence: `Rails.cache.write`, shard row, or state column on the work table
- Idempotency at chunk level: see `rails-batch-processing-patterns`
- Retry budget: Sidekiq default 25 is too many for systemic failure. `sidekiq_options retry: 5`, route exhausted to dead set with alerting
- Signal handling: trap SIGINT/SIGTERM in long rake tasks (see `rails-rake-task-patterns`)

### Throttling

Without a cap, N workers driving the DB at full tilt produce replication lag spikes, connection exhaustion, lock-wait cascades.

- Sidekiq concurrency per process (`concurrency: 5` for memory- or query-heavy queues)
- Per-shard sleep between batches (`sleep(0.05)`)
- Replication-lag-aware throttle - check `Aurora_replica_lag` / `pg_stat_replication.replay_lag`; pause if above threshold
- Token bucket via Redis for rate-limited downstream services
- `gh-ost` / `pt-online-schema-change` for very large MySQL backfills (built-in throttling on lag and disk)

### MySQL vs PostgreSQL for `SKIP LOCKED`

- MySQL 8.0+: works; under RR wrap in per-transaction RC for queue claims
- MySQL 5.7: no `SKIP LOCKED` - use modulo or shards table
- PostgreSQL 9.5+: works with default RC; no isolation override

### Anti-pattern

```ruby
# Bad - both workers claim the same rows
# Worker A
Order.where(state: "stale", region: "us").update_all(state: "archived")
# Worker B (parallel)
Order.where(state: "stale", region: "us").update_all(state: "archived")
```

Second update is a no-op but progress double-counts. Use one of the three documented patterns.

## Output Format

```
Workload: {static backfill | streaming queue | per-tenant batch | one-shot migration}
Volume: {row count, expected runtime}
Pattern: {modulo | SKIP LOCKED cursor | shards table}
Parallelism: {N workers, capped by {DB connections | replication lag | rate limit}}
Coordination: {leader lock for fan-out | row lock per claim | none}
Cursor / state: {where progress is persisted}
Idempotency: {state column | cursor | shard table | natural}
Retry budget: {Sidekiq retries: N, dead-set alerting: yes/no}
Throttling: {none | per-batch sleep | replication-lag check | gh-ost}
```

## Avoid

- Mixing two work-splitting idioms in one job
- Modulo when data is skewed
- `SKIP LOCKED` on non-unique scans - gap-lock cascades on MySQL RR
- Cron fan-out without a leader lock - two triggers double-enqueue
- `push_bulk` calls of >5000 args
- Missing cursor persistence - SIGTERM mid-shard loses progress
- Running backfill at full DB throughput - replication lag spikes
- Optimistic locking on the claim path - `StaleObjectError` storms
- Treating Sidekiq retries as resumability - design for shard-level retry instead
