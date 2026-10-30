---
name: rails-connection-pool-sizing
description: Connection pool sizing: Puma + Sidekiq + CLI vs MySQL max_connections, deploy peaks, RDS Proxy / ProxySQL.
metadata:
  category: backend
  tags: [ruby, rails, database, mysql, connections, ops]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack; on `Database: unknown`, confirm `mysql2` or `trilogy` in the Gemfile and the `adapter:` in `config/database.yml`.

## When to Use

- Sizing `RAILS_MAX_THREADS`, Puma `workers`/`threads`, Sidekiq `concurrency`, `database.yml` `pool` together
- Diagnosing `ConnectionTimeoutError`, `Mysql2::Error: Too many connections`, `MySQL server has gone away`
- Capacity review before traffic increase, instance class change, or rolling deploy
- Adding a long-lived thread pool (`load_async`, ActionCable, custom executor)
- Deciding on RDS Proxy / ProxySQL

## Rules

- Each AR-calling thread checks out one connection - count threads, not pods.
- Per-process `pool == max_threads_in_that_process` (+ executor/Cable extras when `load_async` / ActionCable share the process - see Headroom; a Solid Queue `threads:` worker adds 2 on its queue database, a `fibers:` worker starts at 3-5 per process).
- Deployment-wide sum stays under DB `max_connections` with headroom: 15% only when the deploy peak is bounded and has been observed (a surge knob exists - `maxSurge`, bounded at any value, `100%` included, at 2x; Kamal `boot: limit:` - and someone measured the overlap); 25% otherwise - unmeasured, no surge knob (Capistrano, ASG), or an instance shared with analytics or another application. A neighbouring application on the same server is subtracted explicitly: its budget (or its measured draw) comes off `max_connections` before the headroom, not out of it. `available_for_app = (max_connections - neighbour) * (1 - headroom) - reserved_for_cli - reserved_for_ops`, and both steady state *and* deploy peak must fit under it.
- Rolling deploys hold old + new pool simultaneously - size for the peak.
- A long-running query holds the connection for its full duration.
- Never tune `pool` without re-deriving the deployment-wide total.
- `max_connections` belongs to a database *server*: a replica on its own host is its own budget, while logical databases on one server (primary, queue, cable, cache) share it. A process with `connects_to` reading and writing draws from both servers, and from every logical database it holds a pool for.

## Patterns

### Total-connection formula

```
# Steady-state app draw. Reserved (CLI + ops) is NOT added here - it is subtracted
# from max_connections to get available_for_app, so counting it twice under-provisions.
total =
    (puma_pods * max(puma_workers, 1) * puma_threads) # web; single mode (workers 0) is 1 process
  + (puma_pods * max(puma_workers, 1) * extras)       # executor + Cable threads (Headroom)
  + (sidekiq_pods * sidekiq_processes * concurrency)  # workers; concurrency = sum of capsules
  + (sq_pods * sq_processes * (sq_threads + 2))       # Solid Queue threads: workers (polling + heartbeat); 3-5 per fibers: process,
                                                      # plus supervisor / dispatcher / scheduler connections; + sq_threads on the primary pool
                                                      # when the queue database shares the server
  + (cron_pods * concurrent_scheduled_jobs)           # scheduled processes hold 1 each,
                                                      # x min(script threads, pool) when the script spawns threads
```

Example - 30 web (`workers=2, threads=5`) + 10 worker (`concurrency=15`), with 5 held back for CLI/ops:

```
30 * 2 * 5 + 10 * 15 = 450 steady-state app draw
Deploy peak (rolling, old + new alive): ~900   # reserved does not double - nobody
                                               # opens a second console for a deploy
```

On `db.t3.large` (~682 max_connections, minus the 5 reserved and 25% headroom for an unmeasured 2x peak -> ~506 available) the 450 steady state fits, but the ~900 deploy peak exhausts `max_connections` before new pods serve traffic.

### Per-process pool size

| Process              | `pool`                                                                   |
| -------------------- | ------------------------------------------------------------------------ |
| Puma worker          | `puma_threads` + executor concurrency + Cable worker threads (see Headroom) |
| Sidekiq process      | `concurrency` - the sum across capsules on Sidekiq 7+                     |
| Rails console / rake | whatever `database.yml` sets; holds 1 connection, since checkout is lazy - bump only if the script spawns threads. `db:migrate` holds 1 (the advisory lock rides the migration connection) |

```yaml
# Bad - the pool stops being a cap. AR opens connections lazily, so this reserves
# nothing at steady state; it just lets a thread leak or a rogue executor grow the
# process to 25 and blow the deployment-wide budget.
max_connections: 25  # threads=5
# Good (no in-process Cable, no async executor - otherwise add those extras) - same env
# var and fallback as puma.rb (the generator writes 3 there)
max_connections: <%= ENV.fetch("RAILS_MAX_THREADS") { 3 } %>   # the 8.1 key; legacy pool: is still read without warning - never both (a pool: that differs from max_connections:, or pool: beside min_connections:, raises "Ambiguous configuration")
```

8.1 adds three siblings to `max_connections`: `min_connections` (a floor the pool keeps open - those connections count in the steady-state sum, not just at peak), `keepalive` (on by default: idle connections are pinged every 600 s so a proxy or server idle timeout does not drop them - set it below the shortest idle timeout on the path, RDS Proxy or ProxySQL included) and `max_age` (recycle a connection N seconds after it was opened - total lifetime, not idle time). None changes the cap; `max_connections` remains the per-process number every formula above uses.

### Headroom for non-request work

`load_async` (Rails 7.0+, but inert until `config.active_record.async_query_executor` is set - only then does it draw connections), ActionCable worker threads (when the cable server is mounted in-process, whatever the adapter), ActiveStorage analyzers (only with an in-process `:async` job adapter), custom `Concurrent::FixedThreadPool` - all check out from the same pool. The async executor is one per process, shared across requests, sized by `global_executor_concurrency` (default 4) - 6 async queries in one request still cap at 4 extra connections. (`:multi_thread_pool` builds one executor per connection pool instead, sized by that database's `max_threads` in `database.yml`, default `min(max_connections, 5)`.) The executor checks out from whichever role's pool the query targets - the writer unless the call is inside `connected_to(role: :reading)`. Size `pool = puma_threads + executor_concurrency (+ Cable worker threads, default 4, if mounted in-process)`; the formula's `extras` line counts them fleet-wide. An oversized `pool` (25 over 5 threads) is a mis-sizing finding whose real extra draw is still only the executor and Cable threads.

### Sidekiq sizing

Sidekiq pods are a separate process from Puma - separate pool entry in the deployment-wide sum.

```yaml
:concurrency: 15
```

Set `RAILS_MAX_THREADS=15` in the Sidekiq deployment env so `pool=15` matches. A `database.yml` that hardcodes one `pool` for every process mis-sizes whichever tier's thread count differs.

Partition memory- or query-heavy queues onto a separate process or a Sidekiq 7+ capsule with lower `concurrency`; a capsule adds threads to its process, so that process's `pool` is the sum of its capsules. A queue running 10s SQL at `concurrency: 25` holds 25 connections for ten seconds.

Solid Queue (the Rails 8 default) is the same budget: a worker's concurrency is its `threads` in `config/queue.yml` times `processes`, and its database pool needs those threads plus Solid Queue's own polling and heartbeat connections (threads + 2 for a `threads:` worker, per its README; a `fibers:` worker, Solid Queue 1.6+, starts at 3-5 per process). Its jobs' own queries draw `threads` connections from the primary pool, separate from the queue database's threads + 2 (the install generator writes `config.solid_queue.connects_to = { database: { writing: :queue } }`). Its Puma plugin forks the supervisor, so the workers are separate processes with their own pools; `solid_queue_mode :async` (Solid Queue 1.3+) runs them as threads in the process that boots Puma (in single mode the web process itself; in cluster mode the master, which serves no requests), ignores `processes`, and draws `threads` from that process's primary pool and threads + 2 from its queue pool. Add up to 3 for the supervisor (heartbeat + prune timers, plus its main thread while it releases a crashed fork's claimed jobs), up to 3 per dispatcher (polling + heartbeat + one maintenance timer that concurrency and batch maintenance share), and for the scheduler, which runs when `config/recurring.yml` has tasks or `queue.yml` sets `scheduler: dynamic_tasks_enabled: true`, 1 heartbeat + 1 per recurring task (static or dynamic) firing on the same tick (+ 1 for the dynamic-task polling loop when enabled; at least 2); a process's pools for the queue, cable and cache databases add when they share a server.

### Deploy-window doubling

During rolling deploy, both ReplicaSets coexist (~60s). Worst case (full overlap) ~2x steady-state; with bounded surge, peak ≈ steady x (1 + maxSurge) per surging tier - compute both and size for the one your rollout strategy actually allows. Kubernetes does not count terminating pods against `maxSurge`, so the surge form is a lower bound when draining (Puma shutdown, Sidekiq `timeout`) outlasts startup - add the draining pods, or use ~2x.

Mitigations, ordered for large fleets ("backend process" = OS process holding direct DB connections: puma pods x workers + sidekiq pods x processes, counted at deploy peak):

1. **Connection multiplexer** in front of the DB - essentially mandatory above ~200 backend processes: **RDS Proxy** (managed) or **ProxySQL** (self-hosted)
2. **Lower per-process thread counts** - `threads=5` to `threads=3` cuts pool footprint by 40%
3. **`maxSurge=0`** in Kubernetes (with `maxUnavailable >= 1`, which Kubernetes requires) - pods are replaced `maxUnavailable` at a time, so overlap is bounded to about that many pods' connections while they drain; trades serving capacity during the rollout for connection budget
4. **Kamal**: it boots the new container before stopping the old one on each host, so overlap is bounded by how many hosts deploy at once - cap it with `boot: limit:` (and `boot: wait:`) in `config/deploy.yml`
5. **Size the DB instance class for peak**, not steady-state

Below ~200 processes, invert the order: raising `max_connections` (a custom parameter group on RDS/Aurora, `my.cnf` self-hosted, with RAM to spare) or the instance class is simpler than operating a multiplexer.

### RDS / Aurora limits

RDS MySQL default: `max_connections = {DBInstanceClassMemory/12582880}` - a plain divide, no cap. (The 16000 figure often quoted is Aurora MySQL's hard ceiling, not an RDS MySQL default.)

| Instance         | Memory | Default `max_connections` (upper bound - `DBInstanceClassMemory` is below nominal) |
| ---------------- | ------ | ------------------------- |
| `db.t3.micro`    | 1 GB   | ~85                       |
| `db.t3.small`    | 2 GB   | ~170                      |
| `db.t3.medium`  | 4 GB   | ~341                      |
| `db.t3.large`   | 8 GB   | ~682                      |
| `db.r6g.large`  | 16 GB  | ~1365                     |
| `db.r6g.xlarge` | 32 GB  | ~2730                     |

Aurora MySQL: per writer, readers have their own, and the default formula differs - the table above is RDS MySQL only (`db.r6g.large` defaults to ~1000 on Aurora, not 1365). Self-hosted MySQL 8.0 defaults to 151. Always confirm the live value (`SHOW VARIABLES LIKE 'max_connections'`) - parameter groups override the formula. When the computed peak fits but the error still fires, check in order: a parameter-group override, other tenants on the same server (a staging schema, analytics, ETL), a replica host the fleet also connects to, then `Max_used_connections` against the computed peak.

### Detection in production

```ruby
ActiveRecord::Base.connection_pool.stat
# { size: 7, connections: 5, busy: 4, dead: 0, idle: 1, waiting: 0, checkout_timeout: 5.0 }
# waiting > 0 repeatedly = undersized; checkout_timeout is how long a thread waits
# before ConnectionTimeoutError
```

DB-side:

```sql
-- host is host:port for TCP clients - strip the port or every connection is its own group
SELECT user, SUBSTRING_INDEX(host, ':', 1) AS client, command, COUNT(*)
FROM performance_schema.processlist GROUP BY user, client, command;   -- 8.0.22+, Performance Schema on;
                                                                      -- else information_schema.processlist
SHOW GLOBAL STATUS LIKE 'Max_used_connections';   -- high-water mark since restart
```

| Error                                                | Meaning                              |
| ---------------------------------------------------- | ------------------------------------ |
| `ActiveRecord::ConnectionTimeoutError`               | In-process pool exhausted            |
| MySQL 1040 `Too many connections` (`ActiveRecord::ConnectionNotEstablished` at connect; `Mysql2::Error` / `Trilogy::BaseError` underneath) | DB `max_connections` reached |
| MySQL 2006 / 2013 `server has gone away` / `Lost connection` (`Mysql2::Error`; `Trilogy::EOFError` / `Trilogy::ConnectionClosed` on trilogy; `ActiveRecord::ConnectionFailed` after Rails' reconnect retry) | Network blip, DB restart, a proxy/NAT/load-balancer idle timeout, an oversized packet (`max_allowed_packet`); `wait_timeout` only when `database.yml` overrides the session value Rails sets |

### Reserved budget

Easy to forget; commonly what pushes a deploy over:

- Rails console attached to prod (sometimes idle hours)
- Rake one-offs (parallel deploys spawn several)
- Datadog / New Relic / `mysqld_exporter` polling `performance_schema`
- Backup tools (`mysqldump`, `mysqlsh` dump utilities, `xtrabackup`)
- Schema tools (`gh-ost` heartbeat, `pt-online-schema-change`, `liquibase`)

Reserve 5 connections; 10 when a backup, ETL or online schema tool (gh-ost, pt-osc) is named in the read set; when the consumers are enumerated (4 consoles, an 8-connection reporting script), reserve their sum.

### Fork resets

Active Record resets connections in forked children itself (`ForkTracker`), so a missing `on_worker_boot { establish_connection }` is not a finding; only non-AR clients holding sockets across fork (Redis pools, persistent HTTP connections) need an explicit reset.

### Multiplexer notes

- **RDS Proxy**: session state pins a client to one backend connection (`LOCK TABLES`, temporary tables, session variables), and the session `SET` the mysql2 / trilogy adapter issues on connect may pin every session - no parameter group or Rails setting prevents it. Measure `DatabaseConnectionsCurrentlySessionPinned` after rollout; when pinning shows, accept it or use ProxySQL. `MaxConnectionsPercent` caps the proxy's share of `max_connections`; the app's pools then size against the proxy.
- **ProxySQL**: query routing, read/write splitting; more ops overhead than RDS Proxy.

## Output Format

A question the request asks ("is it safe?", "do we need a proxy?") gets a one-line answer above the blocks. The Gemfile decides the worker tier's shape (`sidekiq` or `solid_queue`); a README that says otherwise is a one-line contradiction above the blocks. Two sources disagreeing on `max_connections`: a parameter group or a measured `SHOW VARIABLES` value wins over the instance-class table; state both. A build request with no `config/puma.rb` or `config/database.yml` yet assumes the generator defaults (`threads 3`, one Puma process per pod - the generated `puma.rb` sets no `workers`, and Puma reads `WEB_CONCURRENCY` as the `workers` default only when it is set), states the assumption, and follows the blocks with the `puma.rb` and `database.yml` lines the sizing implies in one fenced block; a proposal on an existing config ends the same way, with the changed `puma.rb` / `database.yml` / `queue.yml` lines. `Available for app` gates steady state and deploy peak alike. In `Executor / Cable extras`, provisioned equal to required is correct, provisioned below required is the GAP that causes timeouts, provisioned above required is a mis-sized pool. `Worker tier` names any job that holds a connection for minutes. `Cron / rake` counts schedules that overlap in time together (a CronJob at `concurrencyPolicy: Allow` whose run can outlast its interval counts twice); ad-hoc console and ops live in Reserved. `Deploy peak` is ~2x when the rollout has no surge knob (Capistrano, ASG, Kamal without `boot: limit:`) or no manifest is in scope; a Kubernetes Deployment with no `strategy` block takes the default `maxSurge: 25%`, `maxUnavailable: 25%` - a proposed tier with no manifest takes ~2x on its own while existing tiers keep the surge form. In `Result`, the mis-sized-pool value combines with any outcome, and the multiplexer threshold is ~200 backend processes at peak; a connection held across an external call (an HTTP request inside a transaction or `lock!`) is its own `Result` value, since every stalled thread holds one connection for the partner's timeout. One block per database server (a read replica on its own host is its own budget; a documented replica no process connects to gets one line, no block); logical databases sharing a server (queue, cable, cache) fold into its block, each tier line summing every pool that tier's processes hold on it. A proposal (N pods -> M) gets one block per state, the as-configured state first when its pools are mis-sized; an incident's fix is a proposal, so it gets the same second block. Two independent symptoms get two `Result:` lines. A field whose evidence is outside the reviewed files is `not in evidence` plus the file to read.

```
Engine: MySQL on {RDS / Aurora / self-hosted, instance class}

max_connections: {value}

Headroom target: {15% bounded and measured deploy peak | 25% unmeasured, unbounded, or shared instance}

Reserved (CLI + ops): {N}

Available for app: {(max_connections - neighbour) x (1 - headroom) - reserved} = {value}; neighbour = {0 - no other application or schema on this server | N - its budget or measured draw (`performance_schema.threads` by user or schema) | not in evidence - name where to measure, and state the break-even draw}

Web tier: {pods} x {max(workers, 1)} x {threads} = {total}, pool = {N}{ + {N} per other logical database on this server}

Executor / Cable extras: per process {pool - threads} provisioned vs {executor_concurrency + Cable threads} required; fleet {pods x max(workers, 1) x min(required, pool - threads)}

Worker tier: {pods} x {processes} x {concurrency | threads + 2 (Solid Queue threads:) | 3-5 (Solid Queue fibers:)} = {total}, pool = {N}{ + {N} per other logical database on this server}{ + 3 supervisor + 3 per dispatcher + {1 + recurring tasks sharing a tick (+ 1 with dynamic_tasks_enabled), min 2} scheduler (Solid Queue; scheduler only when recurring.yml has tasks or dynamic_tasks_enabled is set)}

Cron / rake: {peak parallel scheduled app processes} = {total}

Steady-state total: {web + extras fleet + worker + cron} - each tier at its own tier line's per-process figure x processes, capped per process and per database at that database's pool (web and extras share the Puma process's pool: min(threads + required extras, pool)) - an oversized pool is a mis-sizing finding, not draw

Deploy peak (rolling): {steady x (1 + maxSurge) | steady x (1 + maxSurge) + draining pods | steady + booting hosts' share (Kamal boot: limit) | ~2x full overlap | measured} - computed per tier when tiers differ in surge, then summed

Result: {within budget | within budget, multiplexer not yet warranted | within budget on paper, symptom unexplained - suspects in check order | within budget, connections held across an external call - {call site}; fix: move the call out of the transaction / lock and bound its timeout (`rails-http-client-patterns`) | a per-process pool is mis-sized - {tier} pool {N} -> {N} | exceeds by {N} - mitigation: {raise max_connections or larger instance | multiplexer (RDS Proxy / ProxySQL) | reduce threads | maxSurge=0 | Kamal boot: limit}}
```

## Avoid

- Forgetting Sidekiq is a separate process from Puma
- Direct connections >200 backend processes without a multiplexer
- Assuming `load_async` is free - the process-global executor adds up to `global_executor_concurrency` connections per process (not one per query)
