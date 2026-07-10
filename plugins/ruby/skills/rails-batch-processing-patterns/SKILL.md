---
name: rails-batch-processing-patterns
description: Rails batch processing: chunked transactions, memory safety (jemalloc, WorkerKiller), pluck cursors, MySQL undo, PG autovacuum.
metadata:
  category: backend
  tags: [ruby, rails, batch, performance, memory, transactions, mysql, postgresql]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Backfill, recompute, export, migration over >100K rows
- Long-running rake / Sidekiq job that grows memory or stalls behind locks
- Diagnosing OOM kills, slow rollbacks, MySQL History List bloat, autovacuum starvation
- Sizing transaction boundaries inside `find_each` / `in_batches`
- Choosing between `find_each`, `in_batches`, `pluck` cursors, `update_all` / `insert_all` / `upsert_all`

## Rules

- One transaction per chunk - never one over the whole run, never one per row
- Idempotency at chunk granularity - retries skip completed chunks
- No HTTP / Redis / S3 inside an open chunk transaction
- `find_each` yields records (per-row Ruby work); `in_batches` yields relations (bulk SQL per chunk, or an explicit transaction around per-row work); `pluck(:id)` cursors when full AR objects aren't needed
- Size chunks by row weight, not row count alone
- Cap concurrency on memory-heavy queues (`concurrency: 25` x 200 MB jobs = 5 GB peak)
- jemalloc or `MALLOC_ARENA_MAX=2` for any long-running batch process
- `Sidekiq::WorkerKiller` at 70-80% of container memory limit

## Patterns

### Transaction Shapes

| Shape                                              | Effect                                                                                | Fix                                |
| -------------------------------------------------- | ------------------------------------------------------------------------------------- | ---------------------------------- |
| (A) Outer `Model.transaction` around `find_each`   | MySQL undo balloons; replication lag; PG VACUUM blocked; mid-run failure rolls back hours | Chunked transactions               |
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

`update_all` / `insert_all` / `upsert_all` are already one SQL statement, so one transaction. Wrapping `in_batches { |b| b.update_all(...) }` in an outer `Model.transaction` recreates Mode A.

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

# Cursor in cache or column
last_id = Integer(Rails.cache.read("backfill:orders:cursor") || 0)
Order.where("id > ?", last_id).find_in_batches(batch_size: 1_000) do |batch|
  ApplicationRecord.transaction { batch.each(&:recompute_total!) }
  Rails.cache.write("backfill:orders:cursor", batch.last.id)
end
```

For multi-day backfills with retry/observability needs, use a shards table - see `rails-work-splitter-patterns`.

Per-chunk external side effects (POST a checksum, notify an API) get their own completion flag (`posted_at`) separate from the write's - restart then re-sends only un-posted chunks, never re-writes posted ones.

### Replication-Lag Throttle

Any backfill on a replicated primary - not just >100M gh-ost territory - can lag replicas. Poll between chunks and pause below the alarm threshold:

```ruby
def wait_for_replica(threshold: 1.5)  # seconds; ~half the paging alarm
  sleep(5) while replica_lag_seconds > threshold
end
# lag source: CloudWatch ReplicaLag / SHOW REPLICA STATUS / pg_stat_replication.replay_lag
```

### Memory Mitigations (leverage order)

Ruby's GC doesn't compact by default and glibc `malloc` arenas fragment, so a 200 MB process peaks at 1-2 GB and stays there. RSS doesn't shrink from `GC.start` - it consolidates the Ruby heap, not OS pages.

First check what's *allocating*: `includes(...)` eager-loads every association's rows as full AR objects per batch - the most common batch-OOM source. Load associations per chunk (or `update_all` them by FK) instead of eager-loading on the driving relation. `pluck` only the columns you need - plucking a 50KB payload column still materializes the strings.

**1. jemalloc** - single highest-leverage change; typically 30-50% RSS reduction.

```dockerfile
RUN apt-get install -y libjemalloc2
ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2
```

**2. `MALLOC_ARENA_MAX=2`** when jemalloc isn't available.

**3. `pluck` cursors** when full AR objects aren't needed:

```ruby
Order.in_batches(of: 5_000) do |relation|
  ids = relation.pluck(:id)
  Sidekiq::Client.push_bulk("class" => EnqueueExportJob, "args" => ids.map { |id| [id] })
end
```

**4. `Sidekiq::WorkerKiller`** - restart before the kernel does. A backstop, not a fix: it quiets then TERMs the process, so in-flight jobs are interrupted (idempotency/state columns make the restart resume, not redo). Rake processes have no equivalent - they rely on chunking + cursor resume. Derive the queue's concurrency cap the same way: `cap = (pod_limit x 0.7) / per_job_peak_rss`.

```ruby
Sidekiq.configure_server do |config|
  config.server_middleware do |chain|
    chain.add Sidekiq::WorkerKiller, max_rss: 800  # MB; 70-80% of pod limit
  end
end
```

**5. Periodic `GC.start` + `GC.compact` + `clear_query_cache`** for multi-hour runs (only meaningful when paired with jemalloc):

```ruby
Order.in_batches(of: 1_000).each_with_index do |batch, i|
  ApplicationRecord.transaction { batch.each(&:recompute_total!) }
  if (i % 50).zero?
    ActiveRecord::Base.connection.clear_query_cache
    GC.start(full_mark: true, immediate_sweep: true)
    GC.compact if GC.respond_to?(:compact)
  end
end
```

The same streaming discipline applies to file artifacts (CSV, PDF, exports): write rows to a tempfile/IO as you iterate - an artifact accumulated as an in-memory string is the peak that kills the pod, and it has phases (built / uploaded) that deserve their own completion flags.

### The "Peaky" Job

```ruby
# Bad - peaks at full batch in memory before write
batch = Order.where(needs_export: true).limit(10_000).to_a
ExportRow.insert_all(batch.map { |o| ExportRow.from(o).to_h })

# Good - stream batch -> derived -> write, bounded by inner chunk
Order.where(needs_export: true).in_batches(of: 1_000) do |relation|
  rows = relation.pluck(:id, :total, :customer_id).map { |id, total, cid|
    { order_id: id, total_cents: (total * 100).to_i, customer_id: cid,
      created_at: Time.current, updated_at: Time.current }
  }
  ExportRow.insert_all(rows)
end
```

### Telemetry

```ruby
def log_mem(tag)
  rss_kb = File.read("/proc/self/status")[/VmRSS:\s+(\d+)/, 1].to_i
  Rails.logger.info(tag: tag, rss_mb: rss_kb / 1024)
end
```

Tools: `get_process_mem`, `memory_profiler` (allocation reports), `derailed_benchmarks` (boot regression in CI), Sidekiq + Prometheus exporter for RSS per worker. Set container memory limit at 1.5-2x observed steady-state RSS (not peak); pair with `WorkerKiller` at 70-80%.

### MySQL Gotchas

- `innodb_flush_log_at_trx_commit=1` (durable default) makes per-row transactions slow - fix chunk size, not flush mode
- Long transactions on RDS/Aurora trip History List Length; Aurora's `Aurora_MySQL_undo_log_records` is the metric
- Gap locks held by long write transactions under `REPEATABLE READ` produce surprising read-stalls
- Backfills > 100M rows: evaluate `gh-ost` / `pt-online-schema-change` for replication-lag-aware throttling

### PostgreSQL Gotchas

- Long transactions block VACUUM; watch `pg_stat_activity.xact_start`, `pg_stat_user_tables.n_dead_tup`
- Set `idle_in_transaction_session_timeout` so a crashed worker doesn't hold dead-tuple visibility
- Cap per-chunk runtime with `SET LOCAL statement_timeout = '30s'` inside the transaction

## Output Format

```
Workload: {backfill | recompute | export | migration}
Volume: {row count, payload shape}
Database: {MySQL | PostgreSQL}
Chunk size: {N} (rationale: {OLTP contention | cold table | large payload})
Transaction shape: {chunked / per-statement / none}
Idempotency: {state column | cursor | progress table | natural}
External side effects: {none | per-chunk call with completion flag | post-commit only}
Throttle: {none | per-chunk sleep | replica-lag poll @ {threshold}s}
Memory mitigations: {jemalloc | MALLOC_ARENA_MAX | pluck cursor | WorkerKiller@N MB}
Concurrency cap: {Sidekiq queue concurrency, if relevant}
Telemetry: {RSS log every N batches | Prometheus | none}
```

## Avoid

- Single outer `Model.transaction` around `find_each` / `in_batches` (Mode A)
- Per-row `Model.transaction { row.update! }` on hot paths (Mode B)
- Multi-statement related updates without any transaction (Mode C)
- HTTP / Redis / S3 inside an open chunk transaction
- Loading full AR objects when only IDs are needed
- Tuning `innodb_flush_log_at_trx_commit` away from 1 to mask Mode B
- Container memory limit at observed peak with no `WorkerKiller` headroom
- `GC.start` without jemalloc expecting RSS to shrink
