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
- Idempotency at shard granularity (not relying on Sidekiq retries)
- Rake fan-out takes a leader lock first (`rails-rake-task-patterns`)
- `push_bulk` in batches of ~1,000 - >5,000 risks Redis client buffer; <100 wastes round-trips
- `SKIP LOCKED` claims hit a unique-index path (PK or unique secondary), never a non-unique scan
- Persist cursor / shard state so SIGTERM doesn't lose progress
- Cap parallelism at the slowest shared resource (DB connections, replication lag, third-party rate limit)

## Patterns

### Decision Matrix

| Workload                                        | Pattern                            | Why                                       |
| ----------------------------------------------- | ---------------------------------- | ----------------------------------------- |
| Static dataset, uniform distribution            | Modulo partitioning                | No lock cost; reshard rare                |
| Stream of new work (queue-shaped)               | `SKIP LOCKED`                      | Drains naturally; tolerates crashes       |
| One-shot backfill of >100M rows, observable     | Shards table                       | Resumable, observable, throttle per-shard |
| Skewed data (60% in last 18 months)             | Shards table with equal-row ranges | Modulo would skew                         |
| Per-tenant batches                              | Modulo or shards on `tenant_id`    | Natural sharding key                      |
| Ordered per key, parallel across keys (outbox)  | `SKIP LOCKED` claims the KEY       | Claim a per-key lease row (table unique on key, rows created with the first item); drain that key's items in `ORDER BY id`, stop on first failure (head-of-line blocking is the ordering guarantee); keys run parallel. Heartbeat the lease's `claimed_at` between items so the reaper frees only dead workers - reaping a live lease lets a second worker break ordering |
| Strict global ordering                          | Single-worker queue / Sidekiq Pro  | Row-level `SKIP LOCKED` won't preserve order |

### (a) Static Modulo Partitioning

No lock; cheapest. Skew if data isn't uniform; reshard requires re-running.

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

### (b) `SKIP LOCKED` Cursor

Each worker claims a batch, processes, marks done. Multiple workers safe by construction.

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

MySQL under default `REPEATABLE READ`: wrap the claim in per-transaction `:read_committed` (shown). Never set RC on the pool - web (RR) and Sidekiq would diverge. The `order(:id) LIMIT N` hits the PK; non-unique scans gap-lock. See `rails-db-locking-patterns`.

PostgreSQL default is RC, so the `isolation:` parameter is a no-op there but harmless.

Two non-negotiables for any claim shape:

- **Slow work happens outside the claim transaction.** The transaction flips state and commits; HTTP, mail, rendering run after - row locks held across IO are the lock-wait cascade source.
- **Crashed claims get reaped.** A worker can die after `claimed`, before done; without recovery, rows strand. Reap by staleness, idempotently (`process_one` must tolerate re-runs):

```ruby
WorkItem.where(state: "claimed").where("claimed_at < ?", 10.minutes.ago)
        .update_all(state: "ready", claimed_at: nil)   # cron, or head of each drain loop
```

### (c) Shards Table

For very large tables, pre-compute id ranges. Each shard tracks its own cursor and retry count.

```ruby
create_table :backfill_shards do |t|
  t.string   :name,       null: false
  t.bigint   :start_id,   null: false
  t.bigint   :end_id,     null: false
  t.string   :state,      null: false, default: "pending"
  t.bigint   :cursor
  t.integer  :retries,    null: false, default: 0
  t.text     :last_error
  t.datetime :claimed_at
  t.datetime :completed_at
  t.timestamps
end
add_index :backfill_shards, [:name, :state]
```

Seed with equal-row ranges (not equal-id) when data is skewed. The boundary scan below walks the whole table - run it against a read replica (or off-hours); it's index-only and read-only, but not free at 100M+ rows:

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

Worker claims via `SKIP LOCKED`, processes the range, updates state:

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

Observability: `SELECT state, COUNT(*) FROM backfill_shards GROUP BY state`. Throttle by varying worker count.

### Fan-out Shapes

- **Modulo:** rake (leader lock via `with_advisory_lock`, `timeout_seconds: 0`, abort cleanly) -> `push_bulk` N `(i, N)` job args. See `rails-rake-task-patterns`.
- **Shards table:** rake seeds the table once, then enqueues `BackfillShardWorker.perform_async(shard_name)` N times.
- **`SKIP LOCKED` draining:** Sidekiq cron enqueues `DrainQueueJob` N times - workers self-coordinate, no rake leader needed.

### `push_bulk` Sizing

```ruby
Order.where(state: "stale").in_batches(of: 1_000) do |batch|
  Sidekiq::Client.push_bulk("class" => ArchiveOrderJob,
                            "args" => batch.pluck(:id).map { |id| [id] })
end
```

### Sidekiq Batches (Pro / Enterprise)

For completion callbacks ("notify when all 1,000 jobs finish"):

```ruby
batch = Sidekiq::Batch.new
batch.description = "recompute_totals #{Time.current.iso8601}"
batch.on(:complete, "MyCallback", run_id: SecureRandom.uuid)
batch.jobs do
  Sidekiq::Client.push_bulk("class" => BackfillShardJob,
                            "args" => Order.where(state: "stale").pluck(:id).map { |id| [id] })
end
```

Without Pro: the shards-table `SELECT COUNT(*) WHERE state != 'done'` works.

### Throttling

Without a cap, N workers driving the DB at full tilt produce replication-lag spikes, connection exhaustion, lock-wait cascades.

- Sidekiq queue concurrency (`concurrency: 5` for memory- or query-heavy queues); use a dedicated queue so deploy quiet/TERM cycles don't starve it
- Per-shard `sleep(0.05)` between batches
- Replication-lag-aware throttle: in the worker's batch loop, poll lag (`SHOW REPLICA STATUS` / CloudWatch `ReplicaLag` / `pg_stat_replication.replay_lag`) every N batches; sleep until below ~half your alarm threshold
- Token bucket via Redis for rate-limited downstream services

Deriving worker count from a deadline: required rows/s = volume / deadline; run ONE worker on one shard to measure actual rows/s; N = ceil(required / measured) with 2-4x headroom for lag pauses and deploys - then verify lag stays under threshold as you step N up.

### Retry Budgets

Sidekiq default 25 retries is too many for systemic failure. Use `sidekiq_options retry: 5`, route exhausted to dead set with alerting. **Sidekiq retries are not resumability** - design for shard-level retry instead (the shards table's `retries` column). For non-idempotent side effects per item (email, charges), a crash between send and mark forces a choice - make it explicitly: flip state *before* the side effect = at-most-once (a crash loses the send; acceptable for emails), or flip after with an idempotency key the receiver dedupes on = at-least-once (required for charges/webhooks). "Send then mark" with retries and no key duplicates sends.

## Output Format

In review mode, precede the block with numbered findings citing the violated rule; the block describes the corrected design.

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

- Mixing two work-splitting idioms in one job (both workers claim the same rows)
- Modulo when data is skewed
- `SKIP LOCKED` on non-unique scans - gap-lock cascades on MySQL RR
- Cron fan-out without a leader lock - two triggers double-enqueue
- `push_bulk` calls of >5,000 args
- Missing cursor persistence - SIGTERM mid-shard loses progress
- Running backfill at full DB throughput - replication lag spikes
- Optimistic locking on the claim path - `StaleObjectError` storms
- Treating Sidekiq retries as resumability
