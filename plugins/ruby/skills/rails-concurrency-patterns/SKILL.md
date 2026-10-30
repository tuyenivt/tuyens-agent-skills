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
- Adopting the `async` gem or `Fiber::Scheduler` on a Rails 8.1+ codebase

## Rules

- I/O-bound: threads (Puma/Sidekiq) or fibers (Falcon, `async` gem). CPU-bound: Sidekiq fan-out when the work must be durable, else process forks, `open3` or `Ractor`. Threads cannot parallelize CPU under the GVL.
- `Thread.new` in a controller / job without a join and a bounded pool is a code smell - prefer `load_async`, Sidekiq fan-out, `Concurrent::Promises`, or fibers.
- Every spawned thread that runs application code runs its body inside `Rails.application.executor.wrap`, and AR work also inside `ActiveRecord::Base.connection_pool.with_connection { ... }` (`ActiveSupport::Dependencies.interlock.permit_concurrent_loads` around the wait is a no-op from 8.1 - omit it). Since 7.2 model queries check a connection out per query, but `lease_connection` / raw `connection` calls and an open transaction pin it to the thread - an HTTP call outside a transaction holds none. Fibers need more: under the default `config.active_support.isolation_level = :thread` the lease is keyed per thread, so every fiber in a thread gets the *same* connection back, so a second concurrent fiber query raises (mysql2 `This connection is in use by: #<Fiber>`, trilogy `Trilogy::SynchronizationError`) instead of running. Fiber-based AR concurrency requires `isolation_level = :fiber`, and so does adopting Falcon.
- Plain Ruby objects shared across Puma threads must be immutable or synchronized. A memoized class variable, a `Singleton` with a mutable hash, or a class-level registry filled lazily is a data race - freeze it at boot, or guard it with a `Mutex`.
- `load_async` for >=2 independent queries on the same request; serial chains stay serial.
- `Ractor` is experimental - only for measured CPU work that survives sharing constraints. ActiveRecord is not Ractor-safe; do DB work in the parent.
- `async` gem: outside an `Async { ... }` block (or Falcon) it adds nothing. Inside one, concurrency covers only IO that yields to the fiber scheduler - `net/http`, `mysql2` and `trilogy` all yield while waiting on a query; mysql2's connection setup (trilogy's connect yields) and non-socket C calls still block - verify per library.
- Durability boundary: fan-out that must survive a process restart starts from a Sidekiq job, never a web request. *Inside* a job, in-process futures with one aggregated write are fine when the job retries as a unit; split into child jobs when sources need independent retries.

## Patterns

### Primitive Selection

| Workload                            | Primitive                     | Why                                      |
| ----------------------------------- | ----------------------------- | ---------------------------------------- |
| 2-5 independent reads in a request  | `load_async`                  | Built-in, no scheduler change            |
| Same, on a fiber stack              | `Async {}`                    | Third-party gem that *installs* a fiber scheduler for the block; needs `isolation_level = :fiber`; mysql2 and trilogy both yield while a query waits |
| Many parallel HTTP fetches          | `async-http` inside `Async {}` (or Falcon) | One fiber per request, no thread cost |
| CPU-bound batch (durable, chunkable)| Sidekiq fan-out, chunk jobs   | Process-level parallelism + retries; run CPU queues at concurrency 1-2 *per process* and scale by adding processes/pods, not threads - threads in one process serialize under the GVL, so per-core thread counts buy nothing and release the AR connection before the CPU phase (scope reads inside `with_connection`; run the transform after the block) |
| CPU-bound transform, in-process     | Process forks (`Parallel` gem) / `Ractor` | GVL serializes threads for CPU |
| Fire-and-forget side effect         | Sidekiq job                   | Durable across restarts, retry semantics |
| I/O fan-out inside one request/job (results aggregated) | `Concurrent::Promises` / pool | Thread-friendly, releases GVL during I/O; aggregate into ONE write at the end |
| I/O-bound durable batch (many rows, restart-safe) | Sidekiq chunk jobs (sized per `rails-batch-processing-patterns`), each fanning out with `Concurrent::Promises` | Durability from the job, overlap from the futures; the one aggregated write is an upsert keyed on the unit so a retried chunk is safe; the width cap is per process, so a partner rate limit shared across pods needs a Redis token bucket (`rails-work-splitter-patterns`) |

When work is both CPU-bound and a durable batch, durability wins: Sidekiq chunk jobs over Ractor/forks. The Sidekiq rows apply to any job backend. Inside a job, bound the in-process width with the primitive's own limiter - `Async::Semaphore.new(8)` around each `task.async`, a fixed-size `Concurrent::FixedThreadPool` for futures, sized per process since every thread in the process (Puma or job worker) shares it - never one task per element, and size the width by memory as well as by connections: N concurrent `blob.download` calls on 20 MB files hold N x 20 MB in RSS, so stream (`blob.open`) and cap N; a latency target on a request ("result within 2 s") is met by the job plus a push to the page (Turbo stream / Action Cable) on completion, never by doing the work inside the request. Where the enqueue sits relative to the transaction is `rails-transaction-patterns`' rule. Solid Queue (the Rails 8 default) is the same budget: a worker's concurrency is its `threads` (or `fibers`, 1.6+ - needs `gem "async"` in the Gemfile and `isolation_level = :fiber`, and a fiber worker's queue pool starts at 3-5 per process) in `config/queue.yml` times `processes`; the pool arithmetic for either Puma-plugin mode is `rails-connection-pool-sizing`'s.

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
# ActiveSupport already loads concurrent-ruby; the canonical explicit require is `require "concurrent"`.
exec = Rails.application.executor   # app code on a spawned thread runs inside the executor
profile_f = Concurrent::Promises.future_on(:io) { exec.wrap { ProfileClient.fetch(user.id) } }
balance_f = Concurrent::Promises.future_on(:io) { exec.wrap { BillingClient.fetch(user.id) } }
prefs_f   = Concurrent::Promises.future_on(:io) { exec.wrap { PrefsClient.fetch(user.id) } }
profile, balance, prefs = Concurrent::Promises.zip(profile_f, balance_f, prefs_f).value!(2.0)

# Per-source degrade against one deadline
deadline_at = Process.clock_gettime(Process::CLOCK_MONOTONIC) + 2.0
resolve = lambda do |f|
  left = [deadline_at - Process.clock_gettime(Process::CLOCK_MONOTONIC), 0].max
  f.value!(left)   # nil = timed out
rescue StandardError => e
  Rails.error.report(e, handled: true)
  nil
end
profile, balance, prefs = [profile_f, balance_f, prefs_f].map(&resolve)
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

Without `with_connection` (and the executor wrap), a leased connection - a raw `connection` / `lease_connection` call, inside a gem too - stays checked out for the thread's lifetime (a transaction holds its connection only until its block exits) and exhausts the pool under load. A pool env shared by web and worker processes (`RAILS_MAX_THREADS` for both) sizes every process to the largest - give each process kind its own value (`rails-connection-pool-sizing`).

### Fiber Scheduler

Per-thread opt-in - `Fiber.set_scheduler` binds to the calling thread, so every Puma thread would need its own; use the `async` gem's scheduler rather than hand-rolling one:

```ruby
require "async"

Thread.new { Fiber.set_scheduler(Async::Scheduler.new); Fiber.schedule { sleep 0.05 } }.join   # Fiber.schedule starts the fiber at once; the scheduler drains it when the thread exits
```

Falcon (`gem "falcon"`) provides fiber-per-request serving in place of Puma - a deployment change; validate adapter support: mysql2 and trilogy both yield while a query waits, so prove interleaving under load with the app's adapter and gems before switching (`net/http` yields; mysql2's connect and any C call that waits on no socket stall every fiber in the process).

## Output Format

One block per workload, and one per process kind when the design spans a request and a job (the Puma block and the Sidekiq block each fill `Server` and `Connection budget` for their own process). A review spanning several artifacts folds them into the one workload they serve and carries the rest as numbered findings (unrelated workloads are separate blocks); a review ruling on proposals (competing or unrelated) emits one block per accepted design and gives every proposal a numbered finding with a verdict of `Accepted`, `Accepted with changes` or `Rejected` - a rejected proposal has its finding only, and when every proposal is rejected the block is the design that replaces them. A proposal item cites its document and section in place of `file:line`. In review or diagnosis mode, numbered findings precede the blocks, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Every block field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and when the enum value that matches already carries a `GAP`, `FIX` or `BLOCKER` marker in any spelling (` - GAP`, `(GAP)`, `(FIX)`, `(BLOCKER)`, a trailing parenthetical included), that value is the observed half and ` -> <corrected>` follows it. The marker applies to every field, whether or not its enum lists a `GAP` value; a field whose value is several named or `+`-joined parts marks only the violated part; `Join` under several primitives lists one entry per primitive, in kickoff order. A violation that belongs to no block - process or deploy config, a schema defect, a sibling skill's concern, a bug seen in passing - is a numbered finding with no block, naming the file and, for a sibling's concern, the owning skill. A violation whose block unit the code lacks (no client class, no transaction, no channel class) gets a block for the unit the fix introduces, its name suffixed `(proposed)`. When the request's premise or a document contradicts the code or schema, the code wins: say so in a finding and proceed on what the code shows. A request to add code, or to change code the request does not ask you to judge, is build mode: every block field holds the corrected value and no GAP marker (an enum value's own marker is dropped), and a pre-existing violation the change touches is still a numbered finding. A request that names existing code to assess, even when it also asks for the fix, is review mode.

```
Workload: <I/O-bound | CPU-bound | mixed (a CPU phase and an I/O phase in one unit of work)>

Primitive: <load_async / async_* calculations | Concurrent::Promises | threads (Thread.new + join, bounded pool) | async gem / async-http | Ractor | process forks (Parallel) | shell-out (open3) | job fan-out (Sidekiq / Solid Queue) | none - stays serial (say why) - list each one used, in kickoff order, and name any synchronous step interleaved between them>

Server: <Puma workers x threads N | Falcon fibers | Sidekiq processes x concurrency | Solid Queue processes x threads (or fibers) | Solid Queue async in Puma (threads; processes ignored) | not in evidence - config/puma.rb / Gemfile>

DB adapter: <mysql2 | trilogy | not in evidence - Gemfile>

Connection budget: <per process: Puma threads + min(async in flight, global_executor_concurrency) + spawned AR threads (+ Solid Queue threads when solid_queue_mode :async shares the process - single mode, or the cluster master alone) vs the primary pool, Solid Queue's threads + 2 per worker plus its dispatcher / scheduler / supervisor connections against the queue-database pool | job worker: concurrency (+ spawned AR threads; Solid Queue: threads (or fibers - its ceiling on concurrent primary queries) vs the primary pool, threads + 2 - or 3-5 per fibers process - vs the queue-database pool) vs pool per process, reads inside with_connection and released before a CPU phase; processes x concurrency is the fleet draw against max_connections | HTTP-only fan-out: none beyond the caller's | n/a - DB work in the parent only (Ractor, forks, open3) | leak: connections never returned (with_connection missing)>

Join: <all-or-nothing (zip.value!) | per-source degrade (value! each against one deadline, rescued, nil = timeout) | implicit on first read (load_async) | Promise#value (async_* calculations) | Thread#join (re-raises the first failure) | none - GAP (a thread nothing joins) | task.wait per child (async) | ractors.map(&:value) (Ruby 4.0+) / ractors.map(&:take) (3.4) | blocking call returns results (Parallel.map / Open3.capture3) | n/a>

Risks: <GVL serialization | pool exhaustion | fiber-shared connection (isolation_level :thread) | executor pool unbounded | missing executor wrap (leaked connection) | load_async inert (executor nil) | silent nil from value / value! on timeout | partner rate limit exceeded across pods | no client timeout (`rails-http-client-patterns`) | shared mutable state race (an AR object handed to a spawned thread included) | write race on one row | durability loss | Ractor sharing | scheduler gaps | memory: N concurrent downloads of large blobs - list all that apply>
```

## Avoid

- `load_async` on a single query - pool pressure with no wall-clock win
- `task.async` outside an `Async { }` block - no yield
- `@x = task.async { ... }` - stores the Task, not its value; read it with `.wait`
