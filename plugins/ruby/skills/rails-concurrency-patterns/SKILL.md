---
name: rails-concurrency-patterns
description: "Ruby 3.x concurrency in Rails: load_async, Fiber/Fiber::Scheduler, Ractor, Async gem, GVL, Thread vs Fiber vs Ractor selection."
metadata:
  category: backend
  tags: [ruby, rails, concurrency, fiber, ractor, async, gvl]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine Ruby version, server (Puma/Falcon), and adapter. Ruby 3.0+ for `Fiber::Scheduler` and `Ractor`; Falcon required for fiber-driven request handling.

## When to Use

- I/O-bound work touching multiple external services in one request or job
- Dashboards aggregating several independent queries
- Choosing between threads, fibers, and ractors for a workload
- Tuning Puma/Sidekiq concurrency when GVL is the bottleneck
- Adopting the `async` gem or `Fiber::Scheduler` on a Rails 7.2+ codebase

## Rules

- I/O-bound work: threads (Puma/Sidekiq default) or fibers (Falcon, `async` gem). CPU-bound: process forks or `Ractor`. Never use threads to parallelize CPU.
- `Thread.new` inside a controller or job is a code smell - use `load_async`, `Sidekiq` fan-out, `Concurrent::Promises`, or fibers instead.
- Every fiber/thread that opens an ActiveRecord connection must release it: `ActiveRecord::Base.connection_pool.with_connection { ... }`.
- `load_async` for >=2 independent queries on the same request; serial chains stay serial.
- `Ractor` is experimental in Ruby 3.x - only for measured CPU-bound work that survives sharing constraints (frozen literals, immutable args). Do not retrofit existing service objects.
- The `async` gem requires a fiber scheduler at the top of the stack (`Async { ... }` block, Falcon server). Mixing with Puma's thread model gives no parallelism.
- `Fiber.scheduler` is a hook, not a free upgrade - the gem under it (`net/http`, `pg`, `mysql2`) must opt in. Verify each library before assuming I/O yields.
- Background fan-out for cross-service writes belongs in Sidekiq, not in-process concurrency - it survives process restarts.

## Patterns

### Primitive Selection

| Workload                            | Primitive                     | Why                                             |
| ----------------------------------- | ----------------------------- | ----------------------------------------------- |
| 2-5 independent reads in a request  | `load_async` or `Async {}`    | Built-in, no scheduler change                   |
| Many parallel HTTP fetches          | `async-http` (Falcon)         | One fiber per request, no thread cost           |
| CPU-bound transform (hashing, math) | Process pool / `Ractor`       | GVL serializes threads for CPU                  |
| Fire-and-forget side effect         | Sidekiq job                   | Durable across restarts, retry semantics        |
| In-request parallelism (Puma)       | `Concurrent::Promises` / pool | Thread-friendly, releases GVL during I/O        |

### Parallel Reads in a Request

Bad - serial wall clock:

```ruby
@orders   = Order.recent.limit(10).to_a       # 80ms
@products = Product.top_sellers.limit(5).to_a # 60ms
# total: ~140ms
```

Good - `load_async` overlaps DB time:

```ruby
@orders   = Order.recent.limit(10).load_async
@products = Product.top_sellers.limit(5).load_async
# wall clock: max(80, 60)
```

`load_async` uses a thread pool sized by `config.active_record.async_query_executor` - tune in `config/application.rb` for high QPS endpoints. Each parallel query consumes one connection from the pool; see `rails-connection-pool-sizing`.

### Fan-Out Across HTTP Services

Bad - serial:

```ruby
profile  = ProfileClient.fetch(user.id)   # 120ms
balance  = BillingClient.fetch(user.id)   # 90ms
prefs    = PrefsClient.fetch(user.id)     # 70ms
# total: ~280ms
```

Good - thread pool with timeout (Puma-compatible):

```ruby
require "concurrent-ruby"

profile_f = Concurrent::Promises.future(executor: :io) { ProfileClient.fetch(user.id) }
balance_f = Concurrent::Promises.future(executor: :io) { BillingClient.fetch(user.id) }
prefs_f   = Concurrent::Promises.future(executor: :io) { PrefsClient.fetch(user.id) }

profile, balance, prefs = Concurrent::Promises.zip(profile_f, balance_f, prefs_f).value!(2.0)
```

Good - `async` gem (only on Falcon or inside an `Async { }` block):

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

- Offload to a Sidekiq job and process across worker processes
- Shell out to a CLI (`open3`) - separate OS process, no GVL
- `Ractor` for measured, isolated work:

```ruby
ractors = inputs.map { |chunk| Ractor.new(chunk) { |c| heavy_transform(c) } }
results = ractors.map(&:take)
```

Ractor constraints: arguments must be shareable (frozen primitives, `Ractor::SharedObject`, or copied). ActiveRecord is not Ractor-safe; do all DB work in the parent.

### Connection Pool Discipline

Every thread/fiber that touches AR must check out a connection:

```ruby
ActiveRecord::Base.connection_pool.with_connection do
  Order.where(user_id: id).pluck(:total)
end
```

Without `with_connection`, the connection is checked out for the life of the thread - exhausts the pool under load. See `rails-connection-pool-sizing` for sizing math.

### Fiber Scheduler (Ruby 3.0+)

Per-process opt-in:

```ruby
Fiber.set_scheduler(MyScheduler.new)
Fiber.schedule { do_io }
```

Use `Async` gem rather than hand-rolling a scheduler. Falcon (`gem "falcon"`) provides fiber-per-request server replacing Puma. Switching is a deployment change - validate gem compatibility (pg works; mysql2 partial; net/http hooks in 3.1+).

## Output Format

When recommending a concurrency approach:

```
Workload: <I/O-bound | CPU-bound | mixed>
Primitive: <load_async | Concurrent::Promises | async gem | Ractor | Sidekiq fan-out>
Server: <Puma threads N | Falcon fibers | Sidekiq>
Connection budget: <queries x connections, vs pool size>
Risks: <GVL serialization | pool exhaustion | Ractor sharing | scheduler gaps>
```

## Avoid

- `Thread.new` in controllers/jobs without join or pool - leaks threads and connections
- `load_async` on a single query - adds pool pressure with no wall-clock win
- Using `Ractor` to "speed up" ActiveRecord - not Ractor-safe; do DB in parent
- Mixing `async` gem with Puma and expecting parallel I/O - no scheduler, no yield
- Forgetting `with_connection` in spawned threads - silent pool exhaustion under load
- Replacing Sidekiq with in-process fan-out for durable work - loses retry/restart safety
