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
- Long-running rake task / Sidekiq job that grows memory or stalls behind locks
- Diagnosing OOM-kills, slow rollbacks, History List Length bloat, autovacuum starvation
- Sizing transaction boundaries inside `find_each` / `in_batches`
- Choosing between `find_each`, `in_batches`, `pluck` cursors, `update_all` / `insert_all` / `upsert_all`

## Rules

- One transaction per chunk - never one over the whole run, never one per row
- Idempotency at chunk granularity - mid-run failure must skip completed chunks on retry
- No HTTP / Redis / S3 inside an open chunk transaction
- No `find_each` inside `Model.transaction { ... }`
- `pluck(:id)` cursors over `find_each` when full AR objects aren't needed
- Size chunks by row weight, not just count
- Sidekiq `WorkerKiller` at 70-80% of container memory limit
- jemalloc or `MALLOC_ARENA_MAX=2` for long-running batch processes

## Patterns

### Three failure modes

**A - one transaction over the whole run.** MySQL undo log holds every pre-image until commit (10M-row update balloons undo by tens of GB); replication lag spikes; mid-run failure rolls back hours. PostgreSQL: blocks VACUUM across the database.

```ruby
# Bad
ApplicationRecord.transaction do
  Order.where(needs_recompute: true).find_each(&:recompute_total!)
end
```

**B - per-row transactions.** 10M rows = 10M fsyncs under `innodb_flush_log_at_trx_commit=1`. Fix the chunk size, not the flush mode.

```ruby
# Bad
Order.where(needs_recompute: true).find_each do |order|
  ApplicationRecord.transaction { order.recompute_total! }
end
```

**C - no transaction at all.** Multi-statement updates leave half-applied state on failure.

```ruby
# Bad
Order.where(state: "stale").update_all(state: "archived")
OrderItem.where(order_id: archived_ids).update_all(archived: true)
```

### Correct shape: chunked transactions

```ruby
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

`update_all` / `insert_all` / `upsert_all` are already one SQL statement, therefore one transaction. Wrapping `in_batches { |b| b.update_all(...) }` in an outer `Model.transaction` recreates Mode A.

### Chunk sizing

| Workload                              | Chunk size      |
| ------------------------------------- | --------------- |
| OLTP table with concurrent writers    | 500 - 1,000     |
| Cold backfill on quiet table          | 5,000 - 10,000  |
| Large JSON / TEXT rows (KB-MB each)   | 100 - 500       |
| Per-row external calls                | 100 or smaller  |

Treat as a tunable: `BATCH_SIZE` ENV in rake; `batch_size:` parameter in services.

### Idempotency at chunk granularity

```ruby
# (1) State column - scope excludes done work on retry
Order.where(needs_recompute: true).in_batches(of: 1_000) do |batch|
  ApplicationRecord.transaction do
    batch.each do |o|
      o.recompute_total!
      o.update_column(:needs_recompute, false)
    end
  end
end

# (2) Cursor in cache or column
last_id = Integer(Rails.cache.read("backfill:orders:cursor") || 0)
Order.where("id > ?", last_id).find_in_batches(batch_size: 1_000) do |batch|
  ApplicationRecord.transaction { batch.each(&:recompute_total!) }
  Rails.cache.write("backfill:orders:cursor", batch.last.id)
end

# (3) Separate progress table for very large multi-day backfills - see rails-work-splitter-patterns
```

### Why Ruby processes leak memory in batches

Even with `find_each`, RSS climbs:

1. Ruby's GC marks-and-sweeps without compacting by default - live objects pin pages; freed slots get reused but the OS doesn't reclaim the page
2. glibc `malloc` arenas fragment under multithreaded allocation
3. Connection pools, prepared statements, AR query cache retain memory across batches

A 200 MB process peaks at 1-2 GB and stays there. 10 Sidekiq workers × 1 GB = 10 GB on a 4 GB node.

### Memory mitigations (in leverage order)

**(a) jemalloc** - highest-leverage single change; typically 30-50% RSS reduction.

```dockerfile
RUN apt-get install -y libjemalloc2
ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2
```

**(b) `MALLOC_ARENA_MAX=2`** when jemalloc isn't available - caps glibc fragmentation.

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
Sidekiq.configure_server do |config|
  config.server_middleware do |chain|
    chain.add Sidekiq::WorkerKiller, max_rss: 800  # MB; 70-80% of pod limit
  end
end
```

**(g) Cap concurrency on memory-heavy queues.** `concurrency: 25` × 200 MB jobs = 5 GB peak. Lower or partition queues.

### The "peaky" job pattern

```ruby
# Bad - peaks at full batch in memory before write
batch = Order.where(needs_export: true).limit(10_000).to_a
results = batch.map { |o| ExportRow.from(o) }
ExportRow.insert_all(results.map(&:to_h))

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

Tools: `get_process_mem`, `memory_profiler` (one-off allocation reports), `derailed_benchmarks` (boot regression in CI), Sidekiq + Prometheus exporter for RSS per worker.

### Container memory limits

Set limit at 1.5-2x observed steady-state RSS, not at the peak. Pair with `Sidekiq::WorkerKiller` at 70-80%.

### MySQL gotchas

- `innodb_flush_log_at_trx_commit=1` (durable default) makes per-row transactions slow - fix chunk size, not flush mode
- Long transactions on RDS/Aurora trip History List Length; Aurora's `Aurora_MySQL_undo_log_records` is the metric
- Gap locks held by long write transactions interact with `REPEATABLE READ`, producing surprising read-stalls
- Very large backfills (>100M rows): evaluate `gh-ost` / `pt-online-schema-change` - they throttle on replication lag and disk

### PostgreSQL gotchas

- Long transactions block VACUUM. Watch `pg_stat_activity.xact_start` and `pg_stat_user_tables.n_dead_tup`
- Set `idle_in_transaction_session_timeout` so a crashed worker doesn't hold dead-tuple visibility hostage
- `SET LOCAL statement_timeout` per chunk caps runaway queries:

```ruby
Order.in_batches(of: 1_000) do |batch|
  ApplicationRecord.transaction do
    ActiveRecord::Base.connection.execute("SET LOCAL statement_timeout = '30s'")
    batch.each(&:recompute_total!)
  end
end
```

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

- Single outer `Model.transaction` around `find_each` / `in_batches` (Mode A)
- Per-row `Model.transaction { row.update! }` on hot paths (Mode B)
- Multi-statement related updates without any transaction (Mode C)
- HTTP / Redis / S3 inside an open chunk transaction
- Loading full AR objects when only IDs are needed
- Sizing chunks by row count alone
- Tuning `innodb_flush_log_at_trx_commit` away from 1 to mask Mode B
- Container memory limit set at observed peak with no `WorkerKiller` headroom
- `GC.start` without jemalloc expecting RSS to shrink - it consolidates the Ruby heap, not OS pages
