---
name: rails-work-splitter-patterns
description: Split batch work across Rake/Sidekiq: modulo shards, SKIP LOCKED cursors, shards table, fan-out with leader lock and push_bulk.
metadata:
  category: backend
  tags: [ruby, rails, sidekiq, rake, batch, mysql, concurrency]
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

- One row-ownership scheme per job - each row is owned by exactly one of a modulo residue, an id range, a shard row, a claimed row, or a key lease; mixing two creates ambiguous ownership
- Idempotency at shard granularity (not relying on Sidekiq retries)
- Modulo and shards-table fan-out take a leader lock first - the rake task, or a cron-triggered Sidekiq job taking the same `with_advisory_lock` in `perform` before it enqueues (`rails-rake-task-patterns`); `SKIP LOCKED` draining needs none
- `push_bulk` in slices of ~1,000 - it pipelines its own Redis batches (`batch_size`, default 1,000), so the cost of an oversized call is the argument array you materialise; <100 wastes round-trips
- `SKIP LOCKED` claims are covered by one composite index over the filter plus the order key (`(state, id)`, `(name, state, id)`) - an uncovered scan locks and skips far more rows than it claims
- Persist cursor / shard state so SIGTERM doesn't lose progress
- Cap parallelism at the slowest shared resource (DB connections, replication lag, third-party rate limit); a process whose Sidekiq concurrency exceeds its DB `pool` is a finding, and the pool is then the binding cap (`rails-connection-pool-sizing`)
- Bulk write paths bypass per-row callbacks (`update_all`) or budget for them - `recompute_total!` on a model with `after_commit` jobs fans out N side effects

## Patterns

### Decision Matrix

| Workload                                        | Pattern                            | Why                                       |
| ----------------------------------------------- | ---------------------------------- | ----------------------------------------- |
| Small table, uniform key, lock cost matters     | Modulo partitioning                | No lock cost - but N full scans (below)   |
| Stream of new work (queue-shaped)               | `SKIP LOCKED`                      | Drains naturally; tolerates crashes       |
| One-shot backfill of >100M rows, observable     | Shards table                       | Resumable, observable, throttle per-shard |
| Sparse id space (mass deletes, id gaps)         | Shards table with equal-row ranges | Equal id-*width* ranges would hold unequal row counts |
| Per-tenant batches                              | Shards table keyed on `tenant_id`  | Natural sharding key; modulo on it skews (below). The schema below swaps `start_id`/`end_id` for `tenant_id`, unique on `[:name, :tenant_id]` |
| Ordered per key, parallel across keys (outbox)  | `SKIP LOCKED` claims the KEY       | Claim a per-key lease row (table unique on key, rows created with the first item); drain that key's items in `ORDER BY id`, stop on first failure (head-of-line blocking is the ordering guarantee); a head item past its attempt budget is marked failed and skipped, or the key stays wedged - decide per payload type; each delivery is bounded by a client timeout (`rails-http-client-patterns`); keys run parallel. Heartbeat the lease's `claimed_at` between items so the reaper frees only dead workers - reaping a live lease lets a second worker break ordering |
| Strict global ordering                          | Single-threaded consumer           | Row-level `SKIP LOCKED` won't preserve order. No Sidekiq Pro/Enterprise feature provides ordering - it takes exactly one Sidekiq process consuming the queue at concurrency 1 (Sidekiq 7+: a Capsule with `concurrency = 1`, booted by one process only), with `retry: 0` and in-process retry or parking, since a job sent to the retry set lets later jobs pass it (a rolling deploy that overlaps two processes, or super_fetch orphan recovery, briefly breaks "exactly one" - stop the old consumer first); or an ordered log outside Sidekiq |

`recurring bounded run` is a cron-armed split (a shards table named per run, or `SKIP LOCKED` draining); `one-shot migration` is a static backfill a schema change requires. A recurring sweep that calls a remote API per row narrows to the rows that need it (`synced_at < ?`, a change feed) before it splits - splitting a full-table sweep only parallelises waste.

### (a) Static Modulo Partitioning

No lock. The cost is hidden: `id % N` is non-sargable against the PK, so each of the N jobs scans the whole table - the fan-out buys parallelism at N full passes. (A MySQL 8.0.13+ functional index on `(id % N)` can serve it, but it is pinned to one N and must be rebuilt whenever the shard count changes.) Fine on a small table, wrong on a large one; there, use disjoint `id BETWEEN` ranges (PK range scan) or a shards table. Modulo also skews on a stepped sequence (`auto_increment_increment > 1` leaves shards empty) or a non-uniform key such as `tenant_id`; it does *not* skew on time-clustered ids, which distribute evenly across residues.

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

# Enqueued by the leader-locked fan-out (Fan-out Shapes), in one push_bulk:
Sidekiq::Client.push_bulk("class" => BackfillShardJob, "args" => (0...8).map { |i| [i, 8] })
```

### (b) `SKIP LOCKED` Cursor

Each worker claims a batch, processes, marks done. Multiple workers safe by construction.

```ruby
class DrainQueueJob
  include Sidekiq::Job
  BATCH = 100
  MAX_ATTEMPTS = 5

  def perform
    loop do
      claimed = ApplicationRecord.transaction(isolation: :read_committed) do
        ids = WorkItem.where(state: "ready").where("attempts < ?", MAX_ATTEMPTS).order(:id).limit(BATCH)
                      .lock("FOR UPDATE SKIP LOCKED").pluck(:id)   # needs index on (state, id)
        WorkItem.where(id: ids)
                .update_all(["state = 'claimed', claimed_at = ?, attempts = attempts + 1", Time.current])
        ids
      end
      break if claimed.empty?
      claimed.each { |id| process_one(id) }
    end
  end
end
```

MySQL under default `REPEATABLE READ`: wrap the claim in per-transaction `:read_committed` (shown). Never set RC on the pool - web (RR) and Sidekiq would diverge. RC is what removes the gap locks, and that is the whole reason for the escalation: at RR InnoDB takes next-key locks on every index record it scans, and `SKIP LOCKED` does not suppress gap locking on the records it does return, so a claim still locks the gaps between claimed rows however narrow the index is. The `(state, id)` index bounds the *scan*, not the gaps. See `rails-db-locking-patterns`.

The claim transaction must run flat. `isolation:` raises `TransactionIsolationError` inside any open transaction, and that is Active Record raising before it reaches the adapter. Transactional test fixtures wrap each example in a non-joinable transaction, so even a flat `transaction(isolation:)` raises in specs; set `self.use_transactional_tests = false` on that spec - flattening does not help.

A per-key lease can also be claimed by compare-and-set - `UPDATE leases SET owner = ?, claimed_at = NOW() WHERE lease_key = ? AND (owner IS NULL OR claimed_at < ?)`, owning it only when one row changed. That is a guarded UPDATE, not `lock_version`.

Two non-negotiables for any claim shape:

- **Slow work happens outside the claim transaction.** The transaction flips state and commits; HTTP, mail, rendering run after - row locks held across IO are the lock-wait cascade source.
- **Crashed claims get reaped.** A worker can die after `claimed`, before done; without recovery, rows strand. Reap by staleness, idempotently (`process_one` must tolerate re-runs):

```ruby
stale = WorkItem.where(state: "claimed").where("claimed_at < ?", 10.minutes.ago)   # cron, or head of each drain loop
stale.where("attempts >= ?", DrainQueueJob::MAX_ATTEMPTS).update_all(state: "failed")
stale.update_all(state: "ready", claimed_at: nil)
```

Size the staleness threshold above the worst-case gap between `claimed_at` writes. `DrainQueueJob` stamps one `claimed_at` for all `BATCH` rows and processes them serially with no heartbeat, so its bound is whole-claim time, `BATCH x per-item` - or re-stamp `claimed_at` per item, or claim batches small enough that whole-batch time stays under the threshold. Size it per-item and the reaper resets the unprocessed tail of a live batch, which a second worker then redoes. The shards table below heartbeats per batch, so there the bound is one batch plus any throttle sleep inside the loop; a lag-aware wait that can outlast the threshold must heartbeat while it waits. A threshold shorter than a slow-but-live worker reaps it mid-work, and on the ordered per-key shape that breaks ordering.

Count attempts in the claim UPDATE (as above) and mark a row `failed` past its budget - a poison item that kills its worker is otherwise reaped and re-claimed forever.

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

Seed with equal-row ranges (not equal-id) when the id space is sparse; when ids are dense, equal id-width ranges (`start_id + k * width`) need no boundary scan at all. The boundary scan below is a full clustered-PK read - run it against a read replica (or off-hours); it is read-only, but not free at 100M+ rows. Seed under the same leader lock the fan-out uses and resume from the highest committed `end_id`: a re-run after a partial seed otherwise lays down a second, overlapping set of ranges and every row is processed twice - the `[:name, :start_id]` unique index is the backstop.

```ruby
def self.create_order_shards(name:, shard_size: 100_000)
  # Resume, don't bail: a crash mid-seed leaves shards 1..k committed, and a plain
  # `return if exists?` would then never seed the tail - silently skipping those rows.
  first_id = Order.minimum(:id) or return          # empty table: nothing to seed
  cursor = BackfillShard.where(name: name).maximum(:end_id) || (first_id - 1)
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
        next unless s                        # nil ends the loop below; `break` here exits the transaction non-locally
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
    # same budget as the rescue path below: this reap is attempt retries + 1
    stale.where("retries + 1 >= ?", MAX_SHARD_RETRIES)
         .update_all("state = 'failed', retries = retries + 1, last_error = 'reaped past retry budget'")
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

A column derivable in SQL updates with one `update_all` (or `UPDATE ... JOIN`) per batch in place of `batch.each(&:recompute_total!)` - fewer statements, and none of the per-row callbacks the bulk-write rule warns about.

Alert on `state = 'failed'` rows - they are dead work needing a human.

Observability: `SELECT state, COUNT(*) FROM backfill_shards WHERE name = ? GROUP BY state`. Throttle by varying worker count.

### Fan-out Shapes

- **Modulo:** rake (leader lock via `with_advisory_lock`, `timeout_seconds: 0`; on lock-held, skip cleanly with `next` - not `abort`, which exits non-zero and trips cron alerting on a normal skip) -> `push_bulk` N `(i, N)` job args. See `rails-rake-task-patterns`.
- **Shards table:** rake seeds the table under the same leader lock (`with_advisory_lock`, `timeout_seconds: 0`), then enqueues `BackfillShardWorker.perform_async(shard_name)` N times.
- **Cron-triggered Sidekiq fan-out:** the job takes the leader lock in `perform` before enqueuing. A recurring run that can outlast its interval also skips while the previous run's shards are unfinished, and names each run's shards (`name: "inventory_sync:#{run_at}"`) so re-arming never collides.
- **`SKIP LOCKED` draining:** a cron-scheduled launcher job push_bulks N `DrainQueueJob`s (one sidekiq-cron entry pushes one job per tick; N entries also work) - workers self-coordinate, no leader needed. A drain job that re-enqueues itself while work remains needs a dedupe fence, or every cron tick starts another chain.
- **Per-key lease (outbox):** the insert path enqueues one `DrainKeyJob(key)` per new item (deduped with sidekiq-unique-jobs' `until_executed` plus a `lock_ttl`, or a SET NX fence); a cron sweep re-enqueues keys that have unsent items and no live lease.

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
batch.on(:complete, "MyCallback", "run_id" => SecureRandom.uuid)   # options round-trip through JSON: string keys
batch.jobs do
  Order.where(state: "stale").in_batches(of: 1_000) do |b|      # chunk inside batch.jobs
    Sidekiq::Client.push_bulk("class" => ArchiveOrderJob,       # a per-id job, one arg each
                              "args" => b.pluck(:id).map { |id| [id] })
  end
end
```

Push the job whose `perform` arity matches the args: `ArchiveOrderJob#perform(id)` takes one, while `BackfillShardJob#perform(shard_index, shard_count)` takes two and would `ArgumentError` on every job. And chunk inside `batch.jobs` - a single `pluck` of the whole set both materialises every id in memory and blows the ~1,000-arg sizing rule.

Without Pro: the shards-table completion check is `SELECT COUNT(*) FROM backfill_shards WHERE name = ? AND state NOT IN ('done', 'failed')`, because `!= 'done'` never reaches zero once a shard is terminally `failed`. A *stranded* shard is a different case and is deliberately still counted - it sits in `claimed`, which this predicate includes, and the reaper is what clears it. So alert on two things beside the completion count: the `failed` total, and any `claimed` row older than `STALE_CLAIM`, which means the reaper is not running.

### Throttling

Without a cap, N workers driving the DB at full tilt produce replication-lag spikes, connection exhaustion, lock-wait cascades.

- Worker concurrency cap for memory- or query-heavy work. `concurrency` is not per-queue, so this takes a dedicated process (`-q heavy -c 5`) or, on Sidekiq 7+, a capsule (`config.capsule("heavy") { |c| c.concurrency = 5; c.queues = %w[heavy] }`). Either way give it its own queue, so only the capped process or capsule consumes those jobs
- Per-shard `sleep(0.05)` between batches
- Replication-lag-aware throttle: in the worker's batch loop, poll lag every few batches and sleep until it is below ~half your paging alarm. Poll lag on a replica connection: `SHOW REPLICA STATUS` `Seconds_Behind_Source` (8.0.22+; `SHOW SLAVE STATUS` / `Seconds_Behind_Master` before), or on Aurora `information_schema.replica_host_status.REPLICA_LAG_IN_MILLISECONDS` (milliseconds); a NULL lag means replication stopped - treat it as infinite and pause. CloudWatch `ReplicaLag` (seconds) / `AuroraReplicaLag` (milliseconds) is one-minute data - alarms, not the poll.
- Token bucket via Redis for rate-limited downstream services

Deriving worker count from a deadline: required rows/s = volume / deadline; run ONE worker on one shard to measure actual rows/s; N = ceil(required / measured) x 2-4 headroom for lag pauses and deploys - then verify lag stays under threshold as you step N up. An event-driven queue with no volume has no deadline math: size N to the claimable keys and the downstream timeout.

### Retry Budgets

Sidekiq default 25 retries is too many for systemic failure. Use `sidekiq_options retry: 5`, route exhausted to dead set with alerting. **Sidekiq retries are not resumability** - design for shard-level retry instead (the shards table's `retries` column). For non-idempotent side effects per item (email, charges), a crash between send and mark forces a choice - make it explicitly: flip state *before* the side effect = at-most-once (a crash loses the send; acceptable for emails), or flip after with an idempotency key the receiver dedupes on = at-least-once (required for charges/webhooks). "Send then mark" with retries and no key duplicates sends. Flipping state and sending in one transaction is the send-then-mark case in disguise - a rollback after the send re-sends - so the flip's commit and the send are never one atomic step.

## Output Format

One block per workload split. In review or diagnosis mode, precede the blocks with numbered findings, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. In review or diagnosis mode each field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and its numbered finding explains the fix. A build-mode block holds corrected values only, and build mode still numbers findings for the pre-existing violations it touches. A request to design or change code is build mode; one that assesses or diagnoses code as it stands is review or diagnosis mode. A scaffolded but unwired idiom (a shards table no job reads) is a finding against the pick-one-idiom rule; a shards table missing the pattern's columns or indexes is a finding naming each one; a scenario fact the schema or config contradicts (a source column that does not exist, a cron entry the schedule lacks) is a numbered finding. `Coordination`, `Idempotency` and `Throttling` each list every mechanism that applies, joined with ` + ` (the shards-table shape uses a leader lock for seeding plus a row lock per claim). `Parallelism` names every binding cap, tightest first. The `Reaper` threshold T is at least the gap between `claimed_at` writes (one batch plus throttle with a heartbeat, whole-claim time without). `Throttling: none` is a GAP for a backfill against a replicated or shared database.

```
Workload: {static backfill | one-shot migration (schema-driven) | recurring bounded run | streaming queue | ordered per key (outbox) | strict global order | per-tenant batch}

Volume: {row count, expected runtime | unknown - measure one worker on one shard or one key}

Pattern: {modulo | id-range | SKIP LOCKED row claim | per-key lease (SKIP LOCKED or CAS) | shards table | direct push_bulk fan-out | single-threaded consumer (strict ordering)}

Parallelism: {N workers, capped by {DB connections | replication lag | rate limit | memory | claimable keys | downstream timeout | ordering (N = 1)} - list all}

Sizing: {shard count x shard size, N workers -> projected completion vs deadline | shard count x shard size, N unknown until one worker is measured on one shard | n/a}

Coordination: {leader lock for fan-out | leader lock for seeding | row lock per claim | CAS lease (guarded UPDATE) | lease ownership guard (claimed_at match) | enqueue dedupe fence (until_executed / SET NX) | none}

Claim isolation: {per-transaction read_committed | none - GAP (claim under REPEATABLE READ) | n/a - single-row CAS update or no row claim}

Cursor / state: {where progress is persisted}

Reaper: {staleness threshold T, runs at loop head or cron, alert on claimed rows older than T | n/a - no claim | none - GAP}

Idempotency: {state column | cursor | shards table | natural | idempotency key (receiver dedupes) | none - GAP}

Delivery semantics: {at-most-once - state flipped before the side effect | at-least-once - idempotency key the receiver dedupes on | n/a - no external side effect}

Retry budget: {Sidekiq retries: N, dead-set alerting: yes/no | shard-level: max N then terminal "failed" | Sidekiq retries: 0, an attempts column owns backoff and the terminal state | both, stated separately | none - GAP | target job outside reviewed scope - not assessed}

Throttling: {none | n/a - drain paced by arrivals | per-batch sleep | replication-lag check | worker concurrency cap | Redis token bucket}
```

## Avoid

- Mixing two work-splitting idioms in one job (both workers claim the same rows)
- Modulo on a large table - N jobs, N full scans; no ordinary index serves `id % N`, and a functional one serves a single fixed N
- `SKIP LOCKED` claims with no covering index over filter + order key
- A claim shape with no reaper - one SIGKILL strands those rows permanently
- Seeding a shards table without an idempotency guard - a re-run overlaps ranges and doubles every row
- Modulo or shards-table cron fan-out without a leader lock - two triggers double-enqueue
- `push_bulk` calls that materialise the whole id set in one array
- Missing cursor persistence - SIGTERM mid-shard loses progress
- Running backfill at full DB throughput - replication lag spikes
- `lock_version` optimistic locking on the claim path - `StaleObjectError` storms
- Treating Sidekiq retries as resumability
