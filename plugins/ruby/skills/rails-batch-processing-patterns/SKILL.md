---
name: rails-batch-processing-patterns
description: Rails batch processing on MySQL: chunked transactions, memory safety (jemalloc, WorkerKiller), pluck cursors, InnoDB undo, replica lag.
metadata:
  category: backend
  tags: [ruby, rails, batch, performance, memory, transactions, mysql]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Backfill, recompute, export, migration over >100K rows
- Long-running rake / Sidekiq job that grows memory or stalls behind locks
- Diagnosing OOM kills, slow rollbacks, MySQL History List bloat, replica lag
- Sizing transaction boundaries inside `find_each` / `in_batches`
- Choosing between `find_each`, `in_batches`, `pluck` cursors, `update_all` / `insert_all` / `upsert_all`

## Rules

- One transaction per chunk - never one over the whole run, never one per row
- Idempotency at chunk granularity - retries skip completed chunks
- No HTTP / Redis / S3 / job enqueue inside an open chunk transaction
- Bulk write paths bypass per-row callbacks (`update_all` / `insert_all` / `upsert_all`; `update_columns` skips callbacks too but is still one UPDATE per row) or budget for them - `after_commit` jobs, `touch:` and broadcasts turn N rows into N side effects
- `find_each` yields records (per-row Ruby work); `in_batches` yields relations (bulk SQL per chunk, or an explicit transaction around per-row work); `pluck(:id)` cursors when full AR objects aren't needed
- Size chunks by row weight, not row count alone
- Cap concurrency on memory-heavy queues (`concurrency: 25` x 200 MB jobs = 5 GB peak) with a dedicated process or capsule - a queue weight caps nothing - and never above the process's DB `pool` (`rails-connection-pool-sizing`). Solid Queue (the Rails 8 default) is the same budget: a worker's concurrency is its `threads` in `config/queue.yml` times `processes`, and its database pool needs those threads plus Solid Queue's own polling and heartbeat connections (threads + 2, per its README)
- jemalloc or `MALLOC_ARENA_MAX=2` for any long-running batch process
- `Sidekiq::WorkerKiller` at 70-80% of container memory limit

## Patterns

### Transaction Shapes

| Shape                                              | Effect                                                                                | Fix                                |
| -------------------------------------------------- | ------------------------------------------------------------------------------------- | ---------------------------------- |
| (A) Outer `Model.transaction` around `find_each`   | MySQL undo balloons; replication lag; mid-run failure rolls back hours | Chunked transactions               |
| (B) `Model.transaction` per row                    | 10M rows = 10M fsyncs under `innodb_flush_log_at_trx_commit=1`                        | Wrap N rows per chunk              |
| (C) No transaction across multi-statement updates  | Half-applied state on failure                                                         | Wrap related statements per chunk  |

```ruby
# Correct shape
Order.where(needs_recompute: true).in_batches(of: 1_000) do |batch|
  ApplicationRecord.transaction do
    batch.each(&:recompute_total!)
  end
end

# Atomic multi-statement per chunk
Order.where(state: "stale").in_batches(of: 1_000) do |batch|
  ApplicationRecord.transaction do
    ids = batch.pluck(:id)
    Order.where(id: ids).update_all(state: "archived")
    OrderItem.where(order_id: ids).update_all(archived: true)
  end
end
```

`update_all` / `insert_all` / `upsert_all` are already one SQL statement, so one transaction. Wrapping `in_batches { |b| b.update_all(...) }` in an outer `Model.transaction` recreates Shape A. So does a read-only scan inside one transaction (an export wrapped in `transaction`, replica included): it pins one consistent-read snapshot for the whole run, so purge stops and History List Length grows on whichever server runs it. Read-only scans run with no wrapping transaction.

### Chunk Sizing

| Workload                              | Chunk size      |
| ------------------------------------- | --------------- |
| OLTP table with concurrent writers    | 500 - 1,000     |
| Cold backfill on quiet table          | 5,000 - 10,000  |
| Large JSON / TEXT rows (KB-MB each)   | 100 - 500       |
| Per-row external calls                | 100 or smaller  |

Sizes count rows of the *driving* relation; when each chunk also writes child tables, budget total rows touched per transaction. When two tiers apply (OLTP + large payload), take the smaller. A per-chunk external call (checksum POST, API notify) pushes toward the larger end of the tier - chunk count is also call count. Per-row derived values (`anon_email(a)`) that block `update_all`: per-row `update!`/`update_columns` inside the chunk transaction is fine; push the computation into SQL only when it's expressible. Expose as `BATCH_SIZE` ENV in rake; `batch_size:` parameter in services.

### Chunk-Granular Idempotency

```ruby
# State column - scope excludes done work on retry
Order.where(needs_recompute: true).in_batches(of: 1_000) do |batch|
  ApplicationRecord.transaction do
    batch.each do |o|
      o.recompute_total!
      o.update_column(:needs_recompute, false)
    end
  end
end

# Cursor in a durable row (every Rails.cache store can evict and lose progress)
checkpoint = Checkpoint.find_or_create_by!(name: "backfill:orders")
Order.where("id > ?", checkpoint.last_id.to_i).find_in_batches(batch_size: 1_000) do |batch|
  ApplicationRecord.transaction do
    batch.each(&:recompute_total!)
    checkpoint.update!(last_id: batch.last.id)   # same transaction: writes and progress commit together
  end
end
```

The state column needs an index (or the scope is the PK range itself): without one each batch walks the PK past rows already done, and late batches re-scan most of the table. A backfill feeding a later NOT NULL ships the writer change first (new rows set the column), then the backfill, so the NULL scope drains; the constraint itself is `rails-migration-safety`'s.

For multi-day backfills with retry/observability needs, use a shards table - see `rails-work-splitter-patterns`.

Per-chunk external side effects (POST a checksum, notify an API) get their own completion flag (`posted_at`) separate from the write's - restart then re-sends only un-posted chunks, never re-writes posted ones. A crash between the partner's 2xx and the flag write re-sends that one chunk, so the call carries an idempotency key (the chunk id).

### Replication-Lag Throttle

Any backfill on a replicated primary can lag replicas. Poll between chunks and pause below the alarm threshold:

```ruby
def wait_for_replica(threshold: 1.5)  # seconds; ~half the paging alarm
  sleep(5) while replica_lag_seconds > threshold   # replica_lag_seconds: your probe, sources below
end
```

Poll lag on a replica connection: `SHOW REPLICA STATUS` `Seconds_Behind_Source` (8.0.22+; `SHOW SLAVE STATUS` / `Seconds_Behind_Master` before), or on Aurora `information_schema.replica_host_status.REPLICA_LAG_IN_MILLISECONDS` (milliseconds); a NULL lag means replication stopped - treat it as infinite and pause. CloudWatch `ReplicaLag` (seconds) / `AuroraReplicaLag` (milliseconds) is one-minute data - alarms, not the poll.

### Memory Mitigations (leverage order)

Ruby's GC doesn't compact by default and glibc `malloc` arenas fragment, so a 200 MB process peaks at 1-2 GB and stays there. RSS rarely shrinks after `GC.start`: freed slots stay in the Ruby heap and fragmented arena pages stay mapped.

First check what's *allocating*: `includes(...)` on the driving relation preloads every association per chunk as full AR objects - the most common batch-OOM source. Drop associations the work doesn't read, narrow columns, `update_all` children by FK, or shrink the chunk for high fan-out associations. `pluck` only the columns you need - plucking a 50KB payload column still materializes the strings.

**1. jemalloc** - single highest-leverage change; typically 30-50% RSS reduction. Rails 7.2+ generated apps already install it (7.2: preloaded in `bin/docker-entrypoint`; 8.0+: `ENV LD_PRELOAD` in the Dockerfile) - verify either location, don't re-add; the arch-independent Dockerfile form is:

```dockerfile
RUN apt-get update && apt-get install -y libjemalloc2 && rm -rf /var/lib/apt/lists/* && \
    ln -s /usr/lib/$(uname -m)-linux-gnu/libjemalloc.so.2 /usr/local/lib/libjemalloc.so
ENV LD_PRELOAD=/usr/local/lib/libjemalloc.so
```

**2. `MALLOC_ARENA_MAX=2`** when jemalloc isn't available.

**3. `pluck` cursors** when full AR objects aren't needed:

```ruby
Order.in_batches(of: 5_000) do |relation|
  ids = relation.pluck(:id)
  Sidekiq::Client.push_bulk("class" => EnqueueExportJob, "args" => ids.map { |id| [id] })   # a Sidekiq::Job class - push_bulk cannot enqueue Active Job
end
```

**4. `Sidekiq::WorkerKiller`** - restart before the kernel does. A backstop, not a fix: it checks RSS after each job finishes, so it cannot stop one job's spike mid-run. Over the limit it quiets the process (TSTP), waits `grace_time` (default 900s) for in-flight jobs, TERMs, and sends `kill_signal` (SIGKILL) after `shutdown_wait` (30s) - a job longer than the grace is interrupted, so idempotency/state columns still make the restart resume, not redo. Deploy-time interruption (`terminationGracePeriodSeconds` vs Sidekiq `timeout`) is `rails-sidekiq-patterns`' rule. Rake processes have no equivalent - they rely on chunking + cursor resume. Derive the queue's concurrency cap the same way: `cap = (pod_limit x 0.7 - baseline_rss) / per_job_peak_rss`, baseline being the booted process (often 200-400 MB).

```ruby
require "sidekiq/worker_killer"   # gem "sidekiq-worker-killer" - Bundler's auto-require misses this path

Sidekiq.configure_server do |config|
  config.server_middleware do |chain|
    chain.add Sidekiq::WorkerKiller, max_rss: 800  # MB; 70-80% of pod limit
  end
end
```

**5. Periodic `GC.compact`** for multi-hour runs - complements jemalloc: compaction frees Ruby heap pages, jemalloc limits malloc-arena fragmentation. It runs a full GC first, so no separate `GC.start`:

```ruby
Order.in_batches(of: 1_000).each_with_index do |batch, i|
  ApplicationRecord.transaction { batch.each(&:recompute_total!) }
  GC.compact if (i % 50).zero?
end
```

The query cache is not a batch leak: since 7.1 it is a bounded LRU, and a plain rake task runs with it off.

The same streaming discipline applies to file artifacts (CSV, PDF, exports): write rows to a tempfile/IO as you iterate - an artifact accumulated as an in-memory string is the peak that kills the pod, and it has phases (built / uploaded) that deserve their own completion flags.

### The "Peaky" Job

```ruby
# Bad - peaks at full batch in memory before write
batch = Order.where(needs_export: true).limit(10_000).to_a
ExportRow.insert_all(batch.map { |o| ExportRow.row_for(o) })

# Good - stream batch -> derived -> write, bounded by inner chunk
Order.where(needs_export: true).in_batches(of: 1_000) do |relation|
  rows = relation.pluck(:id, :total, :customer_id).map { |id, total, cid|
    { order_id: id, total_cents: (total * 100).to_i, customer_id: cid }   # Rails sets timestamps
  }
  ApplicationRecord.transaction do
    ExportRow.insert_all(rows)
    relation.update_all(needs_export: false)   # same transaction: a retry skips this chunk
  end
end
```

### Telemetry

```ruby
def log_mem(tag)
  rss_kb = File.read("/proc/self/status")[/VmRSS:\s+(\d+)/, 1].to_i
  Rails.logger.info(tag: tag, rss_mb: rss_kb / 1024)
end
```

Tools: `get_process_mem`, `memory_profiler` (allocation reports), `derailed_benchmarks` (boot regression in CI), Sidekiq + Prometheus exporter for RSS per worker. The kernel kills at peak, so set the container memory limit above observed peak RSS (peak / 0.75) and `WorkerKiller` at 70-80% of it.

### MySQL Gotchas

- `innodb_flush_log_at_trx_commit=1` (durable default) makes per-row transactions slow - fix chunk size, not flush mode
- Long transactions trip History List Length. On Aurora MySQL the CloudWatch metric is `RollbackSegmentHistoryListLength` (writer instance); on plain RDS MySQL there is no such metric - read it from `SHOW ENGINE INNODB STATUS` ("History list length") or `information_schema.INNODB_METRICS`. Find the transaction holding it back with `SELECT trx_mysql_thread_id, trx_started FROM information_schema.INNODB_TRX ORDER BY trx_started LIMIT 5`
- Long write transactions under `REPEATABLE READ` hold next-key locks: the gap part blocks *inserts* into the range, the record part blocks locking reads and writes of those rows - plain SELECTs are served from the MVCC snapshot and never stall. The symptom is insert stalls and deadlocks, not slow reads
- `gh-ost` / `pt-online-schema-change` are online *schema-change* tools and cannot apply an UPDATE of computed values, so a computed-value backfill is app-level chunking with the replica-lag poll above. `pt-archiver --check-replica-lag` (`--check-slave-lag` before Percona Toolkit 3.6) throttles well but only copies rows to `--dest` or purges them - it cannot apply an in-place UPDATE either. Reach for gh-ost/pt-osc only for an accompanying ALTER
- No server-side timeout bounds a write's execution: `max_execution_time` covers SELECT only, `innodb_lock_wait_timeout` bounds only the wait for a row lock, and a client `read_timeout` abandons the statement without stopping it on the server. Bound each chunk by its row count, not by a timer
- `default_scope` on the driving model silently filters the batch - use `unscoped` or name the scope you mean

## Output Format

One block per batch code path - a review covering a job and two rake tasks emits three. In review or diagnosis mode, precede the blocks with numbered findings, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Findings cite the shape letter (A/B/C) where one applies; in diagnosis mode they are ordered by leverage, the first fix first. A finding whose evidence is infrastructure (Dockerfile, a manifest, `sidekiq.yml`) is a numbered finding with no block. In review or diagnosis mode each field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and its numbered finding explains the fix. A build-mode block holds corrected values only, and build mode still numbers findings for the pre-existing violations it touches. A request to design or change code is build mode; one that assesses or diagnoses code as it stands is review or diagnosis mode. A field whose evidence is outside the reviewed files is `not in evidence` plus the file to read. `Memory mitigations`, `Throttle` and `Telemetry` list every applied value, joined with ` + `; `Idempotency` lists one value per phase when the write and an external call differ.

```
Workload: {backfill | recompute | export | migration | fan-out dispatch (enqueues work, computes nothing)}

Volume: {unknown - count with <query> | driving rows per invocation, or jobs x rows per job; child rows touched stated separately; the aggregate stated separately when the code is scoped per tenant or date range}

Database: {MySQL | unknown - read config/database.yml}

Chunk size: {N} (rationale: {OLTP contention | cold table | large payload | per-row external calls | id-only dispatch (no row payload)}) | unchunked - GAP

Transaction shape: {chunked | per-statement (one bulk SQL statement per chunk) | single outer - GAP (Shape A) | one transaction around a read-only scan - GAP (pins the snapshot) | per-row - GAP (Shape B, including per-row save! auto-commits) | one unchunked transaction around the whole job - GAP | single statement, no loop - compliant | no transaction across multi-statement writes - GAP (Shape C) | none - compliant for read-only chunks}

Idempotency: {state column | cursor | natural | none - one-shot, safe to rerun | none - GAP (restartable run)}

Cursor store: {durable table | Rails.cache - GAP (every cache store can evict) | n/a - no cursor (state column, natural, or none)}

External side effects: {none | per-chunk call with completion flag | post-commit only | whole-job (non-chunked) | per-row unbatched - GAP | inside the open chunk transaction - GAP}

Throttle: {none - read-only or unreplicated | none - GAP (write backfill on a replicated primary) | per-chunk sleep | replica-lag poll @ {threshold}s (~half the paging alarm)}

Memory mitigations: {drop eager-load / narrow columns | jemalloc | MALLOC_ARENA_MAX | pluck cursor | WorkerKiller@N MB | periodic GC.compact | streamed artifact to tempfile/IO | none (short run, bounded RSS)}

Concurrency cap: {N - the Sidekiq concurrency of the process or capsule that runs this queue (a queue weight does not cap it) | N - Solid Queue threads x processes of the worker that runs this queue | n/a - rake process, one connection}

Telemetry: {RSS log every N batches | statsd | Prometheus | none}
```

## Avoid

- Single outer `Model.transaction` around `find_each` / `in_batches` (Shape A)
- Per-row `Model.transaction { row.update! }` on hot paths (Shape B)
- Multi-statement related updates without any transaction (Shape C)
- HTTP / Redis / S3 / job enqueue inside an open chunk transaction
- Loading full AR objects when only IDs are needed
- Tuning `innodb_flush_log_at_trx_commit` away from 1 to mask Shape B
- Container memory limit at observed peak with no `WorkerKiller` headroom
- `GC.start` without jemalloc expecting RSS to shrink
