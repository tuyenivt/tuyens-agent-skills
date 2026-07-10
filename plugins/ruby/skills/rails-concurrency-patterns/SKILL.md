---
name: rails-concurrency-patterns
description: "Ruby 3.x concurrency in Rails: load_async, Fiber/Fiber::Scheduler, Ractor, Async gem, GVL, Thread vs Fiber vs Ractor selection."
metadata:
  category: backend
  tags: [ruby, rails, concurrency, fiber, ractor, async, gvl]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine Ruby version, server (Puma/Falcon), and adapter. Ruby 3.0+ for `Fiber::Scheduler` / `Ractor`; Falcon required for fiber-driven request handling.

## When to Use

- I/O-bound work touching multiple external services in one request or job
- Dashboards aggregating several independent queries
- Choosing between threads, fibers, and ractors for a workload
- Tuning Puma/Sidekiq concurrency when GVL is the bottleneck
- Adopting the `async` gem or `Fiber::Scheduler` on a Rails 7.2+ codebase

## Rules

- I/O-bound: threads (Puma/Sidekiq) or fibers (Falcon, `async` gem). CPU-bound: process forks or `Ractor`. Threads cannot parallelize CPU under the GVL.
- `Thread.new` in a controller / job is a code smell - use `load_async`, Sidekiq fan-out, `Concurrent::Promises`, or fibers.
- Every spawned thread / fiber that touches AR wraps DB work in `ActiveRecord::Base.connection_pool.with_connection { ... }`.
- `load_async` for >=2 independent queries on the same request; serial chains stay serial.
- `Ractor` is experimental - only for measured CPU work that survives sharing constraints. ActiveRecord is not Ractor-safe; do DB work in the parent.
- `async` gem: outside an `Async { ... }` block (or Falcon) it adds nothing. Inside one, concurrency covers only scheduler-aware IO (`net/http` 3.1+, `pg`; `mysql2` blocks) - verify per library.
- Durability boundary: fan-out that must survive a process restart starts from a Sidekiq job, never a web request. *Inside* a job, in-process futures with one aggregated write are fine when the job retries as a unit; split into child jobs when sources need independent retries.

## Patterns

### Primitive Selection

| Workload                            | Primitive                     | Why                                      |
| ----------------------------------- | ----------------------------- | ---------------------------------------- |
| 2-5 independent reads in a request  | `load_async` or `Async {}`    | Built-in, no scheduler change            |
| Many parallel HTTP fetches          | `async-http` (Falcon)         | One fiber per request, no thread cost    |
| CPU-bound batch (durable, chunkable)| Sidekiq fan-out, chunk jobs   | Process-level parallelism + retries; run CPU queues at concurrency ~1-2 per core (threads in one pod serialize under the GVL) and release the AR connection before the CPU phase |
| CPU-bound transform, in-process     | Process forks (`Parallel` gem) / `Ractor` | GVL serializes threads for CPU |
| Fire-and-forget side effect         | Sidekiq job                   | Durable across restarts, retry semantics |
| I/O fan-out inside one request/job (results aggregated) | `Concurrent::Promises` / pool | Thread-friendly, releases GVL during I/O; aggregate into ONE write at the end |

When work is both CPU-bound and a durable batch, durability wins: Sidekiq chunk jobs over Ractor/forks.

### Parallel Reads in a Request

Bad - serial wall clock:

```ruby
@orders   = Order.recent.limit(10).to_a       # 80ms
@products = Product.top_sellers.limit(5).to_a # 60ms
# total ~140ms
```

Good - `load_async` overlaps DB time:

```ruby
@orders   = Order.recent.limit(10).load_async
@products = Product.top_sellers.limit(5).load_async
# wall clock max(80, 60)
```

`load_async` runs on the global async executor (default 4 threads) but each in-flight query checks a connection out of the *main* AR pool. Budget per request: `1 (request thread) + min(async queries, executor concurrency) + spawned AR threads` - at `pool: 5` with 4 async queries you are saturated, and the budget is *per request*: N concurrent Puma threads multiply the draw on one process pool. For pool math, use skill: `rails-connection-pool-sizing`.

Mixing both fan-outs in one action is the normal shape: kick off `load_async` queries first (DB time overlaps everything after), then the HTTP futures, then consume.

### Fan-Out Across HTTP Services

`Concurrent::Promises` (Puma-compatible, threads release GVL on I/O):

```ruby
require "concurrent-ruby"

profile_f = Concurrent::Promises.future(executor: :io) { ProfileClient.fetch(user.id) }
balance_f = Concurrent::Promises.future(executor: :io) { BillingClient.fetch(user.id) }
prefs_f   = Concurrent::Promises.future(executor: :io) { PrefsClient.fetch(user.id) }
profile, balance, prefs = Concurrent::Promises.zip(profile_f, balance_f, prefs_f).value!(2.0)
```

`value!` raises the first future's exception but **returns nil on timeout**. `zip(...).value!` is all-or-nothing - one failure or timeout takes the whole join. For per-service degradation, resolve futures individually (`f.value(deadline)`, rescue per future, substitute a fallback) with timeouts owned by each HTTP client. Pure-HTTP futures don't need `with_connection`; only AR-touching blocks do. Futures that each write the same row race - collect results and issue one write after the join.

`async` gem (only on Falcon or inside an `Async { }` block):

```ruby
require "async"

Async do |task|
  profile_t = task.async { ProfileClient.fetch(user.id) }
  balance_t = task.async { BillingClient.fetch(user.id) }
  prefs_t   = task.async { PrefsClient.fetch(user.id) }
  [profile_t.wait, balance_t.wait, prefs_t.wait]
end
```

### CPU-Bound Work

Threads do not parallelize Ruby code under the GVL. Options:

- Offload to a Sidekiq job - parallelism via worker processes.
- Shell out (`open3`) - separate OS process, no GVL.
- `Ractor` for measured, isolated work:

```ruby
ractors = inputs.map { |chunk| Ractor.new(chunk) { |c| heavy_transform(c) } }
results = ractors.map(&:take)
```

Arguments must be shareable: frozen primitives, objects passed through `Ractor.make_shareable`, or values copied at send time.

### Connection Pool Discipline

```ruby
ActiveRecord::Base.connection_pool.with_connection do
  Order.where(user_id: id).pluck(:total)
end
```

Without `with_connection`, the connection stays checked out for the thread's lifetime and exhausts the pool under load.

### Fiber Scheduler (Ruby 3.0+)

Per-process opt-in:

```ruby
Fiber.set_scheduler(MyScheduler.new)
Fiber.schedule { do_io }
```

Use the `Async` gem rather than hand-rolling a scheduler. Falcon (`gem "falcon"`) provides fiber-per-request serving in place of Puma - a deployment change; validate adapter support (pg works, mysql2 partial, `net/http` hooks since 3.1).

## Output Format

In review mode, precede the block with numbered findings citing the violated rule; the block describes the corrected design.

```
Workload: <I/O-bound | CPU-bound | mixed>
Primitive: <load_async | Concurrent::Promises | async gem | Ractor | Sidekiq fan-out>
Server: <Puma threads N | Falcon fibers | Sidekiq>
Connection budget: <queries x connections, vs pool size>
Risks: <GVL serialization | pool exhaustion | Ractor sharing | scheduler gaps>
```

## Avoid

- `Thread.new` in controllers / jobs without join or pool - leaks threads and connections
- `load_async` on a single query - pool pressure with no wall-clock win
- `Ractor` to "speed up" ActiveRecord - not Ractor-safe
- `async` gem under Puma expecting parallel I/O - no scheduler, no yield
- Missing `with_connection` in spawned threads - silent pool exhaustion under load
- In-process fan-out for durable work - loses Sidekiq retry / restart safety
