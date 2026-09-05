---
name: rails-concurrency-patterns
description: "Ruby 3.x concurrency in Rails: load_async, Fiber/Fiber::Scheduler, Ractor, Async gem, GVL, Thread vs Fiber vs Ractor selection."
metadata:
  category: backend
  tags: [ruby, rails, concurrency, fiber, ractor, async, gvl]
user-invocable: false
---

> Load `Use skill: stack-detect` first for Ruby version and database adapter. The app server is not a stack-detect field - read it from the Gemfile and `config/puma.rb`. Ruby 3.0+ for `Fiber::Scheduler` / `Ractor`; Falcon required for fiber-driven request handling.

## When to Use

- I/O-bound work touching multiple external services in one request or job
- Dashboards aggregating several independent queries
- Choosing between threads, fibers, and ractors for a workload
- Tuning Puma/Sidekiq concurrency when GVL is the bottleneck
- Adopting the `async` gem or `Fiber::Scheduler` on a Rails 7.2+ codebase

## Rules

- I/O-bound: threads (Puma/Sidekiq) or fibers (Falcon, `async` gem). CPU-bound: process forks or `Ractor`. Threads cannot parallelize CPU under the GVL.
- `Thread.new` in a controller / job is a code smell - use `load_async`, Sidekiq fan-out, `Concurrent::Promises`, or fibers.
- Every spawned thread that touches AR wraps DB work in `ActiveRecord::Base.connection_pool.with_connection { ... }`. Fibers need more: under the default `config.active_support.isolation_level = :thread` the lease is keyed per thread, so every fiber in a thread gets the *same* connection back and concurrent fiber queries interleave on one socket. Fiber-based AR concurrency requires `isolation_level = :fiber`, and so does adopting Falcon.
- Plain Ruby objects shared across Puma threads must be immutable or synchronized. A memoized class variable, a `Singleton` with a mutable hash, or a class-level registry filled lazily is a data race - freeze it at boot, or guard it with a `Mutex`.
- `load_async` for >=2 independent queries on the same request; serial chains stay serial.
- `Ractor` is experimental - only for measured CPU work that survives sharing constraints. ActiveRecord is not Ractor-safe; do DB work in the parent.
- `async` gem: outside an `Async { ... }` block (or Falcon) it adds nothing. Inside one, concurrency covers only scheduler-aware IO (`net/http` 3.1+, `pg`; `mysql2` blocks) - verify per library.
- Durability boundary: fan-out that must survive a process restart starts from a Sidekiq job, never a web request. *Inside* a job, in-process futures with one aggregated write are fine when the job retries as a unit; split into child jobs when sources need independent retries.

## Patterns

### Primitive Selection

| Workload                            | Primitive                     | Why                                      |
| ----------------------------------- | ----------------------------- | ---------------------------------------- |
| 2-5 independent reads in a request  | `load_async`                  | Built-in, no scheduler change            |
| Same, on a fiber stack              | `Async {}`                    | Third-party gem that *installs* a fiber scheduler for the block; pg only, and needs `isolation_level = :fiber` |
| Many parallel HTTP fetches          | `async-http` (Falcon)         | One fiber per request, no thread cost    |
| CPU-bound batch (durable, chunkable)| Sidekiq fan-out, chunk jobs   | Process-level parallelism + retries; run CPU queues at concurrency 1-2 *per process* and scale by adding processes/pods, not threads - threads in one process serialize under the GVL, so per-core thread counts buy nothing and release the AR connection before the CPU phase (scope reads inside `with_connection`; run the transform after the block) |
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

`load_async` is inert until `config.active_record.async_query_executor` is set (default `nil` runs the query in the foreground - no error, no win). To confirm on a live app, read `Rails.application.config.active_record.async_query_executor` in a console rather than inferring from the absence of a setter. Set `:global_thread_pool` (one executor, `global_executor_concurrency` default 4); each in-flight query still checks a connection out of the *main* AR pool. Budget per request: `1 (request thread) + min(async queries, executor concurrency) + spawned AR threads` - at `pool: 5` with 4 async queries you are saturated, and the budget is *per request*: N concurrent Puma threads multiply the draw on one process pool. For pool math, use skill: `rails-connection-pool-sizing`.

Mixing both fan-outs in one action is the normal shape: kick off `load_async` queries first (DB time overlaps everything after), then the HTTP futures, then consume.

### Fan-Out Across HTTP Services

`Concurrent::Promises` (Puma-compatible, threads release GVL on I/O):

```ruby
# ActiveSupport already loads concurrent-ruby; if requiring it explicitly the
# file is "concurrent" - `require "concurrent-ruby"` raises LoadError.
profile_f = Concurrent::Promises.future_on(:io) { ProfileClient.fetch(user.id) }
balance_f = Concurrent::Promises.future_on(:io) { BillingClient.fetch(user.id) }
prefs_f   = Concurrent::Promises.future_on(:io) { PrefsClient.fetch(user.id) }
profile, balance, prefs = Concurrent::Promises.zip(profile_f, balance_f, prefs_f).value!(2.0)
```

`Promises.future` takes no options - `future(executor: :io) { }` passes the hash to the block and silently ignores it. `future_on(:io)` is the form that selects an executor. That `:io` pool is unbounded by default, so cap the fan-out width yourself rather than letting a slow dependency spawn threads without limit.

`value!` raises the first future's exception but **returns nil on timeout**. `zip(...).value!` is all-or-nothing - one failure or timeout takes the whole join. For per-service degradation resolve futures individually with `f.value!(deadline)` and rescue around each: the non-bang `f.value` never raises - it returns nil both on timeout and on rejection, so a `rescue` around it is dead code and every failure degrades silently to nil. Pure-HTTP futures don't need `with_connection`; only AR-touching blocks do. Futures that each write the same row race - collect results and issue one write after the join.

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
results = ractors.map(&:value)   # Ruby 3.5+; use `&:take` on 3.0-3.4
```

`Ractor.new(*args)` deep-copies non-shareable arguments, so passing a plain chunk works. The real constraint is the block: it must capture no outer local variables (`ArgumentError: can not isolate a Proc` otherwise) and touch only shareable constants and globals.

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

Use the `Async` gem rather than hand-rolling a scheduler. Falcon (`gem "falcon"`) provides fiber-per-request serving in place of Puma - a deployment change; validate adapter support (pg works; mysql2 implements no scheduler hooks - one query stalls every fiber in the process, so don't adopt Falcon on mysql2; `net/http` hooks since 3.1).

## Output Format

One block per workload. A review spanning several artifacts folds them into the one workload they serve and carries the rest as numbered findings; a review ruling on competing proposals emits one block for the recommended design and gives every rejected proposal a numbered finding with its verdict. In review mode, precede the blocks with numbered findings citing the violated rule; the block describes the corrected design, so target state lives there.

```
Workload: <I/O-bound | CPU-bound | mixed>

Primitive: <load_async | Concurrent::Promises | async gem / async-http | Ractor | process forks (Parallel) | shell-out (open3) | Sidekiq fan-out | none - stays serial (say why) - list each one used, in kickoff order, and name any synchronous step interleaved between them>

Server: <Puma threads N | Falcon fibers | Sidekiq>

Connection budget: <queries x connections, vs pool size>

Risks: <GVL serialization | pool exhaustion | executor pool unbounded | shared mutable state race | write race on one row | durability loss | Ractor sharing | scheduler gaps - list all that apply>
```

## Avoid

- `Thread.new` in controllers / jobs without join or pool - leaks threads and connections
- `load_async` on a single query - pool pressure with no wall-clock win
- `Ractor` to "speed up" ActiveRecord - not Ractor-safe
- `task.async` outside an `Async { }` block, or any fiber IO through a blocking adapter (mysql2) inside one - no yield either way
- Missing `with_connection` in spawned threads - silent pool exhaustion under load
- In-process fan-out for durable work - loses Sidekiq retry / restart safety
