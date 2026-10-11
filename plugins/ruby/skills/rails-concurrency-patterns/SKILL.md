---
name: rails-concurrency-patterns
description: "Ruby 3.4+ concurrency in Rails: load_async, Fiber/Fiber::Scheduler, Ractor, Async gem, GVL, Thread vs Fiber vs Ractor selection."
metadata:
  category: backend
  tags: [ruby, rails, concurrency, fiber, ractor, async, gvl]
user-invocable: false
---

> Load `Use skill: stack-detect` first for the Ruby version (when `## Tech Stack` omits it, read `.ruby-version` or the Gemfile `ruby` line). The DB adapter gem (mysql2 / trilogy) and the app server are not stack-detect fields - read them from the Gemfile and `config/puma.rb`. Falcon is required for fiber-driven request handling.

## When to Use

- I/O-bound work touching multiple external services in one request or job
- Dashboards aggregating several independent queries
- Choosing between threads, fibers, and ractors for a workload
- Tuning Puma/Sidekiq concurrency when GVL is the bottleneck
- Adopting the `async` gem or `Fiber::Scheduler` on a Rails 7.2+ codebase

## Rules

- I/O-bound: threads (Puma/Sidekiq) or fibers (Falcon, `async` gem). CPU-bound: Sidekiq fan-out when the work must be durable, else process forks, `open3` or `Ractor`. Threads cannot parallelize CPU under the GVL.
- `Thread.new` in a controller / job without a join and a bounded pool is a code smell - prefer `load_async`, Sidekiq fan-out, `Concurrent::Promises`, or fibers.
- Every spawned thread that runs application code runs its body inside `Rails.application.executor.wrap`, and AR work also inside `ActiveRecord::Base.connection_pool.with_connection { ... }`; a request thread that blocks waiting on such threads wraps the wait in `ActiveSupport::Dependencies.interlock.permit_concurrent_loads`, or development reloading deadlocks. Since 7.2 model queries check a connection out per query, but `lease_connection` / raw `connection` calls and an open transaction pin it to the thread. Fibers need more: under the default `config.active_support.isolation_level = :thread` the lease is keyed per thread, so every fiber in a thread gets the *same* connection back and concurrent fiber queries interleave on one socket. Fiber-based AR concurrency requires `isolation_level = :fiber`, and so does adopting Falcon.
- Plain Ruby objects shared across Puma threads must be immutable or synchronized. A memoized class variable, a `Singleton` with a mutable hash, or a class-level registry filled lazily is a data race - freeze it at boot, or guard it with a `Mutex`.
- `load_async` for >=2 independent queries on the same request; serial chains stay serial.
- `Ractor` is experimental - only for measured CPU work that survives sharing constraints. ActiveRecord is not Ractor-safe; do DB work in the parent.
- `async` gem: outside an `Async { ... }` block (or Falcon) it adds nothing. Inside one, concurrency covers only IO that yields to the fiber scheduler (`net/http` does; `mysql2` blocks inside C without yielding) - verify per library, the DB adapter included.
- Durability boundary: fan-out that must survive a process restart starts from a Sidekiq job, never a web request. *Inside* a job, in-process futures with one aggregated write are fine when the job retries as a unit; split into child jobs when sources need independent retries.

## Patterns

### Primitive Selection

| Workload                            | Primitive                     | Why                                      |
| ----------------------------------- | ----------------------------- | ---------------------------------------- |
| 2-5 independent reads in a request  | `load_async`                  | Built-in, no scheduler change            |
| Same, on a fiber stack              | `Async {}`                    | Third-party gem that *installs* a fiber scheduler for the block; needs `isolation_level = :fiber` and a scheduler-aware DB adapter - not `mysql2`, so on mysql2 use `load_async` |
| Many parallel HTTP fetches          | `async-http` inside `Async {}` (or Falcon) | One fiber per request, no thread cost |
| CPU-bound batch (durable, chunkable)| Sidekiq fan-out, chunk jobs   | Process-level parallelism + retries; run CPU queues at concurrency 1-2 *per process* and scale by adding processes/pods, not threads - threads in one process serialize under the GVL, so per-core thread counts buy nothing and release the AR connection before the CPU phase (scope reads inside `with_connection`; run the transform after the block) |
| CPU-bound transform, in-process     | Process forks (`Parallel` gem) / `Ractor` | GVL serializes threads for CPU |
| Fire-and-forget side effect         | Sidekiq job                   | Durable across restarts, retry semantics |
| I/O fan-out inside one request/job (results aggregated) | `Concurrent::Promises` / pool | Thread-friendly, releases GVL during I/O; aggregate into ONE write at the end |
| I/O-bound durable batch (many rows, restart-safe) | Sidekiq chunk jobs (sized per `rails-batch-processing-patterns`), each fanning out with `Concurrent::Promises` | Durability from the job, overlap from the futures; the one aggregated write is an upsert keyed on the unit so a retried chunk is safe; the width cap is per process, so a partner rate limit shared across pods needs a Redis token bucket (`rails-work-splitter-patterns`) |

When work is both CPU-bound and a durable batch, durability wins: Sidekiq chunk jobs over Ractor/forks. The Sidekiq rows apply to any job backend. Solid Queue (the Rails 8 default) is the same budget: a worker's concurrency is its `threads` in `config/queue.yml` times `processes`, and its database pool needs those threads plus Solid Queue's own polling and heartbeat connections (threads + 2, per its README).

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

`load_async` is inert until `config.active_record.async_query_executor` is set (default `nil` runs the query in the foreground - no error, no win). Confirm it in a console on a live app, not from the absence of a setter. Set `:global_thread_pool` (one executor per process, shared by every request, `global_executor_concurrency` default 4); each in-flight query still checks a connection out of the *main* AR pool. Worst-case budget per process (every Puma thread holding a connection - an open transaction or a lease): `Puma threads + min(async queries in flight across all requests, global_executor_concurrency) + spawned AR threads` against `pool` - the executor caps the async extras for the whole process, so N Puma threads do not multiply them. At `threads 5, pool: 5` under that load an async query waits up to `checkout_timeout`, or runs in the foreground when its relation is read first - slower, not a failure. When the budget exceeds `pool`, raise `pool` to threads + executor concurrency and re-derive the fleet total, or lower `global_executor_concurrency`; for the fleet math see `rails-connection-pool-sizing`.

Terminal calculations (`count`, `sum`) run inline; the `async_*` forms (`async_count`, `async_sum`, 7.1+) go through the executor and return an `ActiveRecord::Promise` - read it with `.value`. Mixing both fan-outs in one action is the normal shape: kick off `load_async` queries first (DB time overlaps everything after), then the HTTP futures, then consume.

### Fan-Out Across HTTP Services

`Concurrent::Promises` (Puma-compatible, threads release GVL on I/O):

```ruby
# ActiveSupport already loads concurrent-ruby; if requiring it explicitly the
# file is "concurrent" - `require "concurrent-ruby"` raises LoadError.
exec = Rails.application.executor   # app code on a spawned thread runs inside the executor
profile_f = Concurrent::Promises.future_on(:io) { exec.wrap { ProfileClient.fetch(user.id) } }
balance_f = Concurrent::Promises.future_on(:io) { exec.wrap { BillingClient.fetch(user.id) } }
prefs_f   = Concurrent::Promises.future_on(:io) { exec.wrap { PrefsClient.fetch(user.id) } }
loads = ActiveSupport::Dependencies.interlock   # the request thread blocks on app code: let loads proceed
profile, balance, prefs = loads.permit_concurrent_loads { Concurrent::Promises.zip(profile_f, balance_f, prefs_f).value!(2.0) }

# Per-source degrade against one deadline
deadline_at = Process.clock_gettime(Process::CLOCK_MONOTONIC) + 2.0
resolve = lambda do |f|
  left = [deadline_at - Process.clock_gettime(Process::CLOCK_MONOTONIC), 0].max
  f.value!(left)   # nil = timed out
rescue StandardError => e
  Rails.error.report(e, handled: true)
  nil
end
profile, balance, prefs = loads.permit_concurrent_loads { [profile_f, balance_f, prefs_f].map(&resolve) }
```

`Promises.future` takes no options - `future(executor: :io) { }` passes the hash to the block and silently ignores it. `future_on(:io)` is the form that selects an executor. That `:io` pool is unbounded by default, so cap the fan-out width yourself rather than letting a slow dependency spawn threads without limit.

`zip(...).value!` waits for every input, then raises the failure (`Concurrent::MultipleErrors` when several failed) - and **returns nil on timeout**. It is all-or-nothing: one failure or timeout takes the whole join. Per-service degradation resolves each future against one shared deadline, as above - each call's timeout is relative, so three sequential 2s waits add up to 6s. The non-bang `f.value` never raises - it returns nil both on timeout and on rejection, so a `rescue` around it is dead code and every failure degrades silently to nil. Pure-HTTP futures don't need `with_connection`; only AR-touching blocks do. Futures that each write the same row race - collect results and issue one write after the join. Dependent steps (upload, then email the link) stay serial: futures overlap only calls that need nothing from each other.

`async` gem (only on Falcon or inside an `Async { }` block):

```ruby
require "async"

profile, balance, prefs = Async do |task|   # Async {} returns the task; .wait yields the block's value
  profile_t = task.async { ProfileClient.fetch(user.id) }
  balance_t = task.async { BillingClient.fetch(user.id) }
  prefs_t   = task.async { PrefsClient.fetch(user.id) }
  [profile_t.wait, balance_t.wait, prefs_t.wait]
end.wait
```

### CPU-Bound Work

Threads do not parallelize Ruby code under the GVL. Options:

- Offload to a Sidekiq job - parallelism via worker processes.
- Shell out (`open3`) - separate OS process, no GVL.
- `Ractor` for measured, isolated work:

```ruby
ractors = inputs.map { |chunk| Ractor.new(chunk) { |c| Transform.call(c) } }   # a module method - self in the block is the Ractor
results = ractors.map(&:value)   # Ruby 4.0+; `&:take` on 3.4 (removed in 4.0)
```

`Ractor.new(*args)` deep-copies non-shareable arguments, so passing a plain chunk works. The real constraint is the block: it must capture no outer local variables (`ArgumentError: can not isolate a Proc` otherwise), touch only shareable constants, and no process-wide globals (`$foo` raises `Ractor::IsolationError`; `$stdout` / `$stderr` and the regexp/exception specials are Ractor-local).

### Connection Pool Discipline

```ruby
ActiveRecord::Base.connection_pool.with_connection do
  Order.where(user_id: id).pluck(:total)
end
```

Without `with_connection` (and the executor wrap), any leased connection - a raw `connection` call, a gem's SQL, an open transaction - stays checked out for the thread's lifetime and exhausts the pool under load.

### Fiber Scheduler

Per-thread opt-in (`Fiber.set_scheduler` binds to the calling thread; every Puma thread would need its own):

```ruby
Fiber.set_scheduler(MyScheduler.new)
Fiber.schedule { do_io }
```

Use the `Async` gem rather than hand-rolling a scheduler. Falcon (`gem "falcon"`) provides fiber-per-request serving in place of Puma - a deployment change; validate adapter support (mysql2 blocks inside C without yielding to the scheduler - one query stalls every fiber in the process, so don't adopt Falcon on mysql2; on trilogy, prove queries interleave under load before switching; `net/http` yields).

## Output Format

One block per workload. A review spanning several artifacts folds them into the one workload they serve and carries the rest as numbered findings; a review ruling on proposals (competing or unrelated) emits one block per accepted design and gives every proposal a numbered finding with a verdict of `Accepted`, `Accepted with changes` or `Rejected` - a rejected proposal has its finding only, and when every proposal is rejected the block is the design that replaces them. A proposal item cites its document and section in place of `file:line`. In review or diagnosis mode, precede the blocks with numbered findings, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. In review or diagnosis mode each field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and its numbered finding explains the fix. A build-mode block holds corrected values only, and build mode still numbers findings for the pre-existing violations it touches. A request to design or change code is build mode; one that assesses or diagnoses code as it stands is review or diagnosis mode.

```
Workload: <I/O-bound | CPU-bound | mixed (a CPU phase and an I/O phase in one unit of work)>

Primitive: <load_async / async_* calculations | Concurrent::Promises | threads (Thread.new + join, bounded pool) | async gem / async-http | Ractor | process forks (Parallel) | shell-out (open3) | job fan-out (Sidekiq / Solid Queue) | none - stays serial (say why) - list each one used, in kickoff order, and name any synchronous step interleaved between them>

Server: <Puma workers x threads N | Falcon fibers | Sidekiq processes x concurrency | Solid Queue processes x threads | not in evidence - config/puma.rb / Gemfile>

DB adapter: <mysql2 | trilogy | not in evidence - Gemfile>

Connection budget: <per process: Puma threads + min(async in flight, global_executor_concurrency) + spawned AR threads vs pool | job worker: concurrency (+ spawned AR threads; Solid Queue threads + 2) vs pool per process, reads inside with_connection and released before a CPU phase; processes x concurrency is the fleet draw against max_connections | HTTP-only fan-out: none beyond the caller's | n/a - DB work in the parent only (Ractor, forks, open3) | leak: connections never returned (with_connection missing)>

Join: <all-or-nothing (zip.value!) | per-source degrade (value! each against one deadline, rescued, nil = timeout) | implicit on first read (load_async / async_*) | Thread#join (re-raises the first failure) | task.wait per child (async) | ractors.map(&:value) (Ruby 4.0+) / ractors.map(&:take) (3.4) | blocking call returns results (Parallel.map / Open3.capture3) | n/a>

Risks: <GVL serialization | pool exhaustion | fiber-shared connection (isolation_level :thread) | executor pool unbounded | load_async inert (executor nil) | silent nil from value / value! on timeout | partner rate limit exceeded across pods | no client timeout (`rails-http-client-patterns`) | shared mutable state race | write race on one row | durability loss | Ractor sharing | scheduler gaps - list all that apply>
```

## Avoid

- `Thread.new` in controllers / jobs without join or pool - leaks threads and connections
- `load_async` on a single query - pool pressure with no wall-clock win
- `Ractor` to "speed up" ActiveRecord - not Ractor-safe
- `task.async` outside an `Async { }` block, or any fiber IO through a blocking adapter (mysql2) inside one - no yield either way
- `@x = task.async { ... }` - stores the Task, not its value; read it with `.wait`
- Missing `with_connection` in spawned threads - silent pool exhaustion under load
- In-process fan-out for durable work - loses Sidekiq retry / restart safety
