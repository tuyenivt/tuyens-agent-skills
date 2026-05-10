---
name: rails-batch-processing-patterns
description: Batch processing for Rails: chunked transactions, memory safety (jemalloc, WorkerKiller), pluck cursors, MySQL undo log, PG autovacuum.
metadata:
  category: backend
  tags: [ruby, rails, batch, performance, memory, transactions, mysql, postgresql]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Backfill, recompute, export, or migration that touches >100K rows
- Long-running rake task or Sidekiq job that grows in memory or stalls behind locks
- Diagnosing OOM-kills, slow rollbacks, History List Length / undo bloat alarms, autovacuum starvation
- Sizing transaction boundaries inside `find_each` / `in_batches` loops
- Choosing between `find_each`, `in_batches`, `pluck` cursors, and `update_all` / `insert_all` / `upsert_all`

## Rules

- One transaction per chunk - never one transaction over the whole run, never one per row
- Idempotency at chunk granularity - a re-run after mid-batch failure must skip completed chunks
- No HTTP / Redis / S3 calls inside an open chunk transaction
- No `find_each` inside `Model.transaction { ... }` - the transaction holds the whole iteration
- `pluck(:id)` cursors over `find_each` when full AR objects aren't needed
- Bound chunk size by row weight, not just count - 1000 rows of 1 MB JSON is a 1 GB batch
- Sidekiq `WorkerKiller` at 70-80% of container memory limit
- jemalloc or `MALLOC_ARENA_MAX=2` for any process that batches in long-running loops

## Patterns

### Three failure modes

**Mode A - one transaction over the whole run.**

```ruby
# Bad
ApplicationRecord.transaction do
  Order.where(needs_recompute: true).find_each(&:recompute_total!)
end
```

On MySQL: undo log holds every row's pre-image until commit (a 10M-row update can balloon undo by tens of GB), replication lag spikes, mid-run failure rolls back hours of work, every touched row stays locked. On PostgreSQL: blocks `VACUUM` from reclaiming dead tuples on tables across the database.

**Mode B - per-row transactions.**

```ruby
# Bad - one fsync per row under default innodb_flush_log_at_trx_commit=1
Order.where(needs_recompute: true).find_each do |order|
  ApplicationRecord.transaction { order.recompute_total! }
end
```

For 10M rows that's 10M fsyncs - hours bottlenecked on disk. Don't "fix" by setting `innodb_flush_log_at_trx_commit=2` to skip fsyncs - fix the chunk size.

**Mode C - no transaction at all.**

```ruby
# Bad - half-applied state on failure between statements
Order.where(state: "stale").update_all(state: "archived")
OrderItem.where(order_id: archived_ids).update_all(archived: true)
```

### Correct shape: chunked transactions

```ruby
# One commit per chunk; failure at chunk K leaves 1..K-1 durably applied
Order.where(needs_recompute: true).in_batches(of: 1_000) do |batch|
  ApplicationRecord.transaction do
    batch.each(&:recompute_total!)
  end
end
```

Atomic multi-statement updates per chunk:

```ruby
Order.where(state: "stale").in_batches(of: 1_000) do |batch|
  ApplicationRecord.transaction do
    ids = batch.pluck(:id)
    Order.where(id: ids).update_all(state: "archived")
    OrderItem.where(order_id: ids).update_all(archived: true)
  end
end
```

`update_all` / `insert_all` / `upsert_all` are already a single SQL statement and therefore one transaction. Wrapping `in_batches { |b| b.update_all(...) }` in an outer `Model.transaction` recreates Mode A.

### Sizing the chunk

| Workload                                    | Chunk size      |
| ------------------------------------------- | --------------- |
| OLTP table with concurrent writers          | 500 - 1,000     |
| Cold backfill on quiet table                | 5,000 - 10,000  |
| Rows have large JSON / TEXT (KB-MB each)    | 100 - 500       |
| Per-row computation heavy (external calls)  | 100 or smaller  |

Treat chunk size as a tunable: `BATCH_SIZE` ENV in rake tasks, `batch_size:` parameter in services.

### Idempotency at chunk granularity

**(1) State column flipped per row** - scope naturally excludes done work on retry:

```ruby
Order.where(needs_recompute: true).in_batches(of: 1_000) do |batch|
  ApplicationRecord.transaction do
    batch.each do |o|
      o.recompute_total!
      o.update_column(:needs_recompute, false)
    end
  end
end
```

**(2) Processed-cursor in cache or column:**

```ruby
last_id = Integer(Rails.cache.read("backfill:orders:cursor") || 0)
Order.where("id > ?", last_id).find_in_batches(batch_size: 1_000) do |batch|
  ApplicationRecord.transaction { batch.each(&:recompute_total!) }
  Rails.cache.write("backfill:orders:cursor", batch.last.id)
end
```

**(3) Separate `backfill_progress` table** for very large multi-day backfills - cross-reference `rails-work-splitter-patterns`.

### Why Ruby processes leak memory in batch jobs

Even with `find_each`, RSS climbs and rarely shrinks:

1. Ruby's GC marks-and-sweeps without compacting (default). Live objects pin pages; freed slots get reused but the OS does not reclaim the page.
2. glibc `malloc` arenas fragment under multithreaded allocation. Threads each get an arena; arenas hold freed memory rarely returned to the OS.
3. Connection pools, prepared statements, AR query cache retain memory across batches.

A 200 MB process peaks at 1-2 GB and stays there. 10 Sidekiq workers x 1 GB = 10 GB on a node sized for 4 GB.

### Memory mitigations (in leverage order)

**(a) jemalloc** - highest-leverage single change. Typically 30-50% RSS reduction (measure your own).

```dockerfile
RUN apt-get update && apt-get install -y libjemalloc2
ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2
```

**(b) `MALLOC_ARENA_MAX=2`** if jemalloc isn't available - caps glibc fragmentation.

**(c) `pluck(:id)` cursors** when full records aren't needed:

```ruby
Order.in_batches(of: 5_000) do |relation|
  ids = relation.pluck(:id)
  Sidekiq::Client.push_bulk("class" => EnqueueExportJob, "args" => ids.map { |id| [id] })
end
```

**(d) Clear AR query cache between batches** for long runs:

```ruby
Order.in_batches(of: 1_000) do |batch|
  ApplicationRecord.transaction { batch.each(&:recompute_total!) }
  ActiveRecord::Base.connection.clear_query_cache
end
```

**(e) `GC.start` + `GC.compact` at chunk boundaries** for multi-hour runs (pair with jemalloc):

```ruby
Order.in_batches(of: 1_000).each_with_index do |batch, i|
  ApplicationRecord.transaction { batch.each(&:recompute_total!) }
  if (i % 50).zero?
    GC.start(full_mark: true, immediate_sweep: true)
    GC.compact if GC.respond_to?(:compact)
  end
end
```

**(f) `Sidekiq::WorkerKiller`** - restart the process before the kernel does:

```ruby
# config/initializers/sidekiq.rb
Sidekiq.configure_server do |config|
  config.server_middleware do |chain|
    chain.add Sidekiq::WorkerKiller, max_rss: 800 # MB; set at 70-80% of pod limit
  end
end
```

**(g) Cap concurrency on memory-heavy queues.** A `concurrency: 25` worker running 200-MB jobs peaks at 5 GB. Either lower concurrency or partition queues.

### The "peaky" job pattern

Bad - peaks at full batch in memory before write:

```ruby
batch = Order.where(needs_export: true).limit(10_000).to_a
results = batch.map { |o| ExportRow.from(o) }
ExportRow.insert_all(results.map(&:to_h))
```

Good - stream batch -> derived -> write, bounded by inner chunk:

```ruby
Order.where(needs_export: true).in_batches(of: 1_000) do |relation|
  rows = relation.pluck(:id, :total, :customer_id).map { |id, total, cid|
    { order_id: id, total_cents: (total * 100).to_i, customer_id: cid,
      created_at: Time.current, updated_at: Time.current }
  }
  ExportRow.insert_all(rows)
end
```

### Detection and telemetry

```ruby
# Cheap RSS log inside the loop
def log_mem(tag)
  rss_kb = File.read("/proc/self/status")[/VmRSS:\s+(\d+)/, 1].to_i
  Rails.logger.info(tag: tag, rss_mb: rss_kb / 1024)
end
```

Tools: `get_process_mem` gem, `memory_profiler` (one-off allocation reports), `derailed_benchmarks` (boot regression in CI), Sidekiq + Prometheus exporter for RSS gauge per worker.

### Container memory limits

- Set the limit at 1.5-2x observed steady-state RSS, not at the peak.
- Pair with `Sidekiq::WorkerKiller` at 70-80% of the limit.

### MySQL-specific gotchas

- `innodb_flush_log_at_trx_commit=1` (durable default) makes per-row transactions painfully slow - fix the chunk size, not the flush mode.
- Long transactions on RDS/Aurora MySQL trip History List Length. Aurora's `Aurora_MySQL_undo_log_records` is the right metric to watch.
- Gap locks held by a long write transaction interact with `REPEATABLE READ` and produce surprising read-stalls on tables sharing an index range.
- For very large backfills (>100M rows), evaluate `gh-ost` or `pt-online-schema-change` - they throttle on replication lag and disk usage automatically.

### PostgreSQL-specific gotchas

- Long transactions block `VACUUM`. Watch `pg_stat_activity.xact_start` and `pg_stat_user_tables.n_dead_tup`.
- Set `idle_in_transaction_session_timeout` so a crashed worker doesn't hold dead-tuple visibility hostage.
- `SET LOCAL statement_timeout` per chunk caps a runaway query:

```ruby
Order.in_batches(of: 1_000) do |batch|
  ApplicationRecord.transaction do
    ActiveRecord::Base.connection.execute("SET LOCAL statement_timeout = '30s'")
    batch.each(&:recompute_total!)
  end
end
```

### Cross-cuts

- `rails-db-locking-patterns`: chunked transactions bound advisory-lock and row-lock hold times.
- `rails-work-splitter-patterns`: each shard processes its slice with the chunked-transaction shape.
- `rails-rake-task-patterns` / `rails-sidekiq-patterns`: long rake tasks and Sidekiq jobs use chunked transactions; the job is the unit of retry.
- `rails-connection-pool-sizing`: a long batch holds one connection for its duration.

## Output Format

```
Workload: {backfill | recompute | export | migration}
Volume: {row count, payload shape}
Database: {MySQL | PostgreSQL}
Chunk size: {N} (rationale: {OLTP contention | cold table | large payload})
Transaction shape: {chunked / per-statement / none}
Idempotency: {state column | cursor | progress table | natural}
Memory mitigations: {jemalloc | MALLOC_ARENA_MAX | pluck cursor | WorkerKiller@N MB}
Concurrency cap: {Sidekiq queue concurrency, if relevant}
Telemetry: {RSS log every N batches | Prometheus | none}
```

## Avoid

- Wrapping `find_each` / `in_batches` in a single outer `Model.transaction` (Mode A: undo bloat, replication lag, all-or-nothing rollback)
- Per-row `Model.transaction { row.update! }` on hot paths (Mode B: fsync-bound throughput)
- Multi-statement related updates without any transaction (Mode C: half-applied state)
- HTTP / Redis / S3 calls inside an open chunk transaction
- Loading full AR objects when only IDs are needed - use `pluck(:id)`
- Sizing chunks by row count alone - row weight matters
- Tuning `innodb_flush_log_at_trx_commit` away from 1 to mask Mode B - fix the chunk size
- Setting Kubernetes memory limit at the observed peak with no `WorkerKiller` headroom
- Forcing `GC.start` without jemalloc and expecting RSS to shrink - it consolidates the Ruby heap, not OS pages
