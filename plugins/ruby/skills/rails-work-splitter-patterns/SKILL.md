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
- `push_bulk` in slices of ~1,000 - it pipelines its own Redis batches (`batch_size`, default 1,000), so the cost of an oversized call is the argument array you materialise; <100 wastes round-trips
- `SKIP LOCKED` claims are covered by one composite index over the filter plus the order key (`(state, id)`, `(name, state, id)`) - an uncovered scan locks and skips far more rows than it claims
- Persist cursor / shard state so SIGTERM doesn't lose progress
- Cap parallelism at the slowest shared resource (DB connections, replication lag, third-party rate limit)
- Bulk write paths bypass per-row callbacks (`update_all`) or budget for them - `recompute_total!` on a model with `after_commit` jobs fans out N side effects

## Patterns

### Decision Matrix

| Workload                                        | Pattern                            | Why                                       |
| ----------------------------------------------- | ---------------------------------- | ----------------------------------------- |
| Small table, uniform key, lock cost matters     | Modulo partitioning                | No lock cost - but N full scans (below)   |
| Stream of new work (queue-shaped)               | `SKIP LOCKED`                      | Drains naturally; tolerates crashes       |
| One-shot backfill of >100M rows, observable     | Shards table                       | Resumable, observable, throttle per-shard |
| Skewed data (60% in last 18 months)             | Shards table with equal-row ranges | Equal id-*width* ranges would skew        |
| Per-tenant batches                              | Shards table keyed on `tenant_id`  | Natural sharding key; modulo on it skews (below) |
| Ordered per key, parallel across keys (outbox)  | `SKIP LOCKED` claims the KEY       | Claim a per-key lease row (table unique on key, rows created with the first item); drain that key's items in `ORDER BY id`, stop on first failure (head-of-line blocking is the ordering guarantee); a head item past its attempt budget is marked failed and skipped, or the key stays wedged - decide per payload type; each delivery is bounded by a client timeout (`rails-http-client-patterns`); keys run parallel. Heartbeat the lease's `claimed_at` between items so the reaper frees only dead workers - reaping a live lease lets a second worker break ordering |
| Strict global ordering                          | Single-threaded consumer           | Row-level `SKIP LOCKED` won't preserve order. No Sidekiq Pro/Enterprise feature provides ordering - it takes a dedicated process at concurrency 1 (Sidekiq 7: a Capsule with `concurrency = 1`), or an ordered log outside Sidekiq |

### (a) Static Modulo Partitioning

No lock. The cost is hidden: `id % N` is non-sargable against the PK, so each of the N jobs scans the whole table - the fan-out buys parallelism at N full passes. (An expression index on `(id % N)` - PG, or MySQL 8.0.13+ functional key parts - can serve it, but it is pinned to one N and must be rebuilt whenever the shard count changes.) Fine on a small table, wrong on a large one; there, use disjoint `id BETWEEN` ranges (PK range scan) or a shards table. Modulo also skews on a stepped sequence (`auto_increment_increment > 1` leaves shards empty) or a non-uniform key such as `tenant_id`; it does *not* skew on time-clustered ids, which distribute evenly across residues.

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
                      .lock("FOR UPDATE SKIP LOCKED").pluck(:id)   # needs index on (state, id)
        WorkItem.where(id: ids).update_all(state: "claimed", claimed_at: Time.current)
        ids
      end
      break if claimed.empty?
      claimed.each { |id| process_one(id) }
    end
  end
end
```

MySQL under default `REPEATABLE READ`: wrap the claim in per-transaction `:read_committed` (shown). Never set RC on the pool - web (RR) and Sidekiq would diverge. RC is what removes the gap locks, and that is the whole reason for the escalation: at RR InnoDB takes next-key locks on every index record it scans, and `SKIP LOCKED` does not suppress gap locking on the records it does return, so a claim still locks the gaps between claimed rows however narrow the index is. The `(state, id)` index bounds the *scan*, not the gaps. See `rails-db-locking-patterns`.

PostgreSQL default is RC - omit the parameter there: it buys nothing in production.

Either way the claim transaction must run flat. `isolation:` raises `TransactionIsolationError` inside any open transaction - transactional test fixtures included - and that is Active Record raising before it reaches the adapter, so it applies to the MySQL form above exactly as it does to PostgreSQL.

Two non-negotiables for any claim shape:

- **Slow work happens outside the claim transaction.** The transaction flips state and commits; HTTP, mail, rendering run after - row locks held across IO are the lock-wait cascade source.
- **Crashed claims get reaped.** A worker can die after `claimed`, before done; without recovery, rows strand. Reap by staleness, idempotently (`process_one` must tolerate re-runs):

```ruby
WorkItem.where(state: "claimed").where("claimed_at < ?", 10.minutes.ago)
        .update_all(state: "ready", claimed_at: nil)   # cron, or head of each drain loop
```

Size the staleness threshold above the worst-case gap between `claimed_at` writes: the claim above stamps one `claimed_at` for all `BATCH` rows and then processes them serially, so without a heartbeat the bound is whole-claim time, `BATCH x per-item`; with a per-batch heartbeat it is one batch plus any throttle sleep inside the loop (heartbeat after the sleep, not before). Size it per-item and the reaper resets the unprocessed tail of a live batch, which a second worker then redoes. The alternatives are re-stamping `claimed_at` per item, or claiming batches small enough that whole-batch time stays under the threshold. A threshold shorter than a slow-but-live worker reaps it mid-work, and on the ordered per-key shape that breaks ordering.

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
add_index :backfill_shards, [:name, :state, :id]     # covers the SKIP LOCKED claim below
add_index :backfill_shards, [:name, :start_id], unique: true   # makes re-seeding safe
```

Seed with equal-row ranges (not equal-id) when data is skewed. The boundary scan below walks the whole table - run it against a read replica (or off-hours); it's index-only and read-only, but not free at 100M+ rows. Seed under the same leader lock the fan-out uses and resume from the highest committed `end_id`: a re-run after a partial seed otherwise lays down a second, overlapping set of ranges and every row is processed twice - the `[:name, :start_id]` unique index is the backstop.

```ruby
def self.create_order_shards(name:, shard_size: 100_000)
  # Resume, don't bail: a crash mid-seed leaves shards 1..k committed, and a plain
  # `return if exists?` would then never seed the tail - silently skipping those rows.
  cursor = BackfillShard.where(name: name).maximum(:end_id) || (Order.minimum(:id) - 1)
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
  MAX_SHARD_RETRIES = 5
  STALE_CLAIM = 30.minutes

  def perform(shard_name)
    loop do
      reap_stale(shard_name)                 # every pass, so a shard reaped mid-run is re-claimed;
                                             # a worker that dies after the last claim is
                                             # recovered by cron or the next run
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

  # A worker lost to OOM / SIGKILL leaves its shard "claimed" forever; nothing else selects it.
  # Reaping counts as a retry, or a poison shard that kills every worker cycles forever.
  def reap_stale(shard_name)
    stale = BackfillShard.where(name: shard_name, state: "claimed").where("claimed_at < ?", STALE_CLAIM.ago)
    stale.where("retries >= ?", MAX_SHARD_RETRIES).update_all(state: "failed", last_error: "reaped past retry budget")
    stale.update_all("state = 'pending', claimed_at = NULL, retries = retries + 1")
  end

  def process_shard(shard)
    cursor = shard.cursor || (shard.start_id - 1)
    Order.where(id: (cursor + 1)..shard.end_id).in_batches(of: 1_000) do |batch|
      last_id = batch.last.id
      stamp   = Time.current
      owned = ApplicationRecord.transaction do
        batch.each(&:recompute_total!)
        # Heartbeat with the cursor, conditional on still owning the lease: without it
        # STALE_CLAIM would have to exceed whole-shard time, and a shard the reaper handed
        # to another worker must never be overwritten. Same txn, so commit and progress
        # advance together - and 0 rows rolls the batch back with it.
        BackfillShard.where(id: shard.id, state: "claimed", claimed_at: shard.claimed_at)
                     .update_all(cursor: last_id, claimed_at: stamp).nonzero? or raise ActiveRecord::Rollback
      end
      return unless owned   # lease lost: stop; the new owner resumes from the cursor
      shard.claimed_at = stamp
    end
    # Conditional: a worker whose claim was reaped must not mark a shard someone else owns.
    BackfillShard.where(id: shard.id, state: "claimed", claimed_at: shard.claimed_at)
                 .update_all(state: "done", completed_at: Time.current)
  rescue => e
    # back to "pending" keeps the shard claimable on retry (cursor makes the re-run resume);
    # "failed" is terminal - only after the budget is spent
    state = shard.retries + 1 < MAX_SHARD_RETRIES ? "pending" : "failed"
    BackfillShard.where(id: shard.id, state: "claimed", claimed_at: shard.claimed_at)   # same ownership guard
                 .update_all(state: state, retries: shard.retries + 1, last_error: e.message)
    raise
  end
end
```

Alert on `state = 'failed'` rows - they are dead work needing a human.

Observability: `SELECT state, COUNT(*) FROM backfill_shards GROUP BY state`. Throttle by varying worker count.

### Fan-out Shapes

- **Modulo:** rake (leader lock via `with_advisory_lock`, `timeout_seconds: 0`; on lock-held, skip cleanly with `next` - not `abort`, which exits non-zero and trips cron alerting on a normal skip) -> `push_bulk` N `(i, N)` job args. See `rails-rake-task-patterns`.
- **Shards table:** rake seeds the table under the same leader lock (`with_advisory_lock`, `timeout_seconds: 0`), then enqueues `BackfillShardWorker.perform_async(shard_name)` N times.
- **`SKIP LOCKED` draining:** Sidekiq cron enqueues `DrainQueueJob` N times - workers self-coordinate, no rake leader needed.
- **Per-key lease (outbox):** the insert path enqueues one `DrainKeyJob(key)` per new item (deduped with `until_executed` or a SET NX fence); a cron sweep re-enqueues keys that have unsent items and no live lease.

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
  Order.where(state: "stale").in_batches(of: 1_000) do |b|      # chunk inside batch.jobs
    Sidekiq::Client.push_bulk("class" => ArchiveOrderJob,       # a per-id job, one arg each
                              "args" => b.pluck(:id).map { |id| [id] })
  end
end
```

Push the job whose `perform` arity matches the args: `ArchiveOrderJob#perform(id)` takes one, while `BackfillShardJob#perform(shard_index, shard_count)` takes two and would `ArgumentError` on every job. And chunk inside `batch.jobs` - a single `pluck` of the whole set both materialises every id in memory and blows the ~1,000-arg sizing rule.

Without Pro: the shards-table completion check is `SELECT COUNT(*) WHERE state NOT IN ('done', 'failed')`, because `!= 'done'` never reaches zero once a shard is terminally `failed`. A *stranded* shard is a different case and is deliberately still counted - it sits in `claimed`, which this predicate includes, and the reaper is what clears it. So alert on two things beside the completion count: the `failed` total, and any `claimed` row older than `STALE_CLAIM`, which means the reaper is not running.

### Throttling

Without a cap, N workers driving the DB at full tilt produce replication-lag spikes, connection exhaustion, lock-wait cascades.

- Worker concurrency cap for memory- or query-heavy work. `concurrency` is not per-queue: in Sidekiq 6 it is process-wide, so this takes a dedicated process (`-q heavy -c 5`); in Sidekiq 7 use a capsule (`config.capsule("heavy") { |c| c.concurrency = 5; c.queues = %w[heavy] }`). Either way give it its own queue so deploy quiet/TERM cycles don't starve it
- Per-shard `sleep(0.05)` between batches
- Replication-lag-aware throttle: in the worker's batch loop, poll lag (`SHOW REPLICA STATUS` / CloudWatch `ReplicaLag` / `pg_stat_replication.replay_lag`) every N batches; sleep until below ~half your alarm threshold
- Token bucket via Redis for rate-limited downstream services

Deriving worker count from a deadline: required rows/s = volume / deadline; run ONE worker on one shard to measure actual rows/s; N = ceil(required / measured) x 2-4 headroom for lag pauses and deploys - then verify lag stays under threshold as you step N up. An event-driven queue with no volume has no deadline math: size N to the claimable keys and the downstream timeout.

### Retry Budgets

Sidekiq default 25 retries is too many for systemic failure. Use `sidekiq_options retry: 5`, route exhausted to dead set with alerting. **Sidekiq retries are not resumability** - design for shard-level retry instead (the shards table's `retries` column). For non-idempotent side effects per item (email, charges), a crash between send and mark forces a choice - make it explicitly: flip state *before* the side effect = at-most-once (a crash loses the send; acceptable for emails), or flip after with an idempotency key the receiver dedupes on = at-least-once (required for charges/webhooks). "Send then mark" with retries and no key duplicates sends. Flipping state and sending in one transaction is the send-then-mark case in disguise - a rollback after the send re-sends - so the flip's commit and the send are never one atomic step.

## Output Format

One block per workload split. In review or diagnosis mode, precede the blocks with numbered findings, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. The block describes the corrected design - that is where target state lives. A non-compliant field is written as the observed value plus ` - GAP`; the target lives in the findings and the rest of the block. A scaffolded but unwired idiom (a shards table no job reads) is a finding against Rule 1; a shards table missing the pattern's columns or indexes is a finding naming each one. `Coordination`, `Idempotency` and `Throttling` each list every mechanism that applies, joined with ` + ` (the shards-table shape uses a leader lock for seeding plus a row lock per claim). `Parallelism` names every binding cap, tightest first.

```
Workload: {static backfill | one-shot migration (schema-driven) | recurring bounded run | streaming queue | ordered per key (outbox) | strict global order | per-tenant batch}

Volume: {row count, expected runtime | unknown - measure one worker on one shard or one key}

Pattern: {modulo | id-range | SKIP LOCKED row claim | per-key lease (SKIP LOCKED or CAS) | shards table | direct push_bulk fan-out | single-threaded consumer (strict ordering)}

Parallelism: {N workers, capped by {DB connections | replication lag | rate limit | memory | claimable keys | downstream timeout | ordering (N = 1)} - list all}

Sizing: {shard count x shard size, N workers -> projected completion vs deadline | n/a}

Coordination: {leader lock for fan-out | leader lock for seeding | row lock per claim | enqueue dedupe fence (until_executed / SET NX) | none - list all}

Claim isolation: {MySQL - per-transaction read_committed | PostgreSQL - default RC, no parameter | n/a - single-row CAS update or no row claim}

Cursor / state: {where progress is persisted}

Reaper: {staleness threshold N (>= the gap between claimed_at writes: one batch plus throttle with a heartbeat, whole-claim time without), runs at loop head or cron, alert on claimed rows older than N | n/a - no claim | none - GAP}

Idempotency: {state column | cursor | shard table | natural | idempotency key (receiver dedupes) | none - GAP}

Delivery semantics: {at-most-once - state flipped before the side effect | at-least-once - idempotency key the receiver dedupes on | n/a - no external side effect}

Retry budget: {Sidekiq retries: N, dead-set alerting: yes/no | shard-level: max N then terminal "failed" | Sidekiq retries: 0, an attempts column owns backoff and the terminal state | both, stated separately | none - GAP | target job outside reviewed scope - not assessed}

Throttling: {none | per-batch sleep | replication-lag check | worker concurrency cap | Redis token bucket}
```

## Avoid

- Mixing two work-splitting idioms in one job (both workers claim the same rows)
- Modulo on a large table - N jobs, N full scans, no index can serve `id % N`
- `SKIP LOCKED` claims with no covering index over filter + order key
- A claim shape with no reaper - one SIGKILL strands those rows permanently
- Seeding a shards table without an idempotency guard - a re-run overlaps ranges and doubles every row
- Cron fan-out without a leader lock - two triggers double-enqueue
- `push_bulk` calls that materialise the whole id set in one array
- Missing cursor persistence - SIGTERM mid-shard loses progress
- Running backfill at full DB throughput - replication lag spikes
- Optimistic locking on the claim path - `StaleObjectError` storms
- Treating Sidekiq retries as resumability
