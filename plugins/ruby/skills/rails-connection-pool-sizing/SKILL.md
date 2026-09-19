---
name: rails-connection-pool-sizing
description: Connection pool sizing: Puma + Sidekiq + CLI vs DB max_connections, deploy peaks, RDS Proxy / ProxySQL / PgBouncer.
metadata:
  category: backend
  tags: [ruby, rails, database, mysql, postgresql, connections, ops]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Sizing `RAILS_MAX_THREADS`, Puma `workers`/`threads`, Sidekiq `concurrency`, `database.yml` `pool` together
- Diagnosing `ConnectionTimeoutError`, `Mysql2::Error: Too many connections`, `PG::ConnectionBad`
- Capacity review before traffic increase, instance class change, or rolling deploy
- Adding a long-lived thread pool (`load_async`, ActionCable, custom executor)
- Deciding on RDS Proxy / ProxySQL / PgBouncer

## Rules

- Each AR-calling thread checks out one connection - count threads, not pods.
- Per-process `pool == max_threads_in_that_process` (+ executor/Cable extras when `load_async` / ActionCable share the process - see Headroom).
- Deployment-wide sum stays under DB `max_connections` with headroom: 15% only when the deploy peak is bounded and has been observed (a surge knob exists and someone measured the overlap); 25% otherwise - unmeasured, no surge knob (Capistrano, ASG), or an instance shared with analytics. `available_for_app = max_connections * (1 - headroom) - reserved_for_cli - reserved_for_ops`, and both steady state *and* deploy peak must fit under it.
- Rolling deploys hold old + new pool simultaneously - size for the peak.
- A long-running query holds the connection for its full duration.
- Never tune `pool` without re-deriving the deployment-wide total.
- Each database (primary, replica, queue DB) has its own `max_connections`; a process with `connects_to` reading and writing draws from both, so budget one block per database.

## Patterns

### Total-connection formula

```
# Steady-state app draw. Reserved (CLI + ops) is NOT added here - it is subtracted
# from max_connections to get available_for_app, so counting it twice under-provisions.
total =
    (puma_pods * puma_workers * puma_threads)         # web
  + (sidekiq_pods * sidekiq_processes * concurrency)  # workers
  + (cron_pods * concurrent_scheduled_jobs)           # scheduled processes hold 1 each,
                                                      # x pool only if the script threads
```

Example - 30 web (`workers=2, threads=5`) + 10 worker (`concurrency=15`), with 5 held back for CLI/ops:

```
30 * 2 * 5 + 10 * 15 = 450 steady-state app draw
Deploy peak (rolling, old + new alive): ~900   # reserved does not double - nobody
                                               # opens a second console for a deploy
```

On `db.t3.large` (~683 max_connections, minus the 5 reserved and 25% headroom for an unmeasured 2x peak -> ~507 available) the 450 steady state fits, but the ~900 deploy peak exhausts the pool before new pods serve traffic.

### Per-process pool size

| Process              | `pool`                                                                   |
| -------------------- | ------------------------------------------------------------------------ |
| Puma worker          | `puma_threads` + executor concurrency + Cable worker threads (see Headroom) |
| Sidekiq process      | `sidekiq.concurrency`                                                    |
| Rails console / rake | whatever `database.yml` sets (5 by default); holds 1 connection, since checkout is lazy - bump only if the script spawns threads |

```yaml
# Bad - the pool stops being a cap. AR opens connections lazily, so this reserves
# nothing at steady state; it just lets a thread leak or a rogue executor grow the
# process to 25 and blow the deployment-wide budget.
pool: 25  # threads=5
# Good
pool: <%= ENV.fetch("RAILS_MAX_THREADS") { 5 } %>
```

### Headroom for non-request work

`load_async` (Rails 7.0+, but inert until `config.active_record.async_query_executor` is set - only then does it draw connections), ActionCable subscribers, ActiveStorage analyzers, custom `Concurrent::FixedThreadPool` - all check out from the same pool. The async executor is one per process, shared across requests, sized by `global_executor_concurrency` (default 4) - 6 async queries in one request still cap at 4 extra connections. (`:multi_thread_pool` builds one executor per connection pool instead, sized by that database's `max_threads` in `database.yml`.) The executor checks out from whichever role's pool the query targets - the writer unless the call is inside `connected_to(role: :reading)`. Size `pool = puma_threads + executor_concurrency (+ Cable worker threads, default 4, if mounted in-process)`. Count these extras in the deployment-wide sum as `pods x workers x (pool - threads)` - the formula's `threads` term misses them. That only holds when `pool` was derived this way: an arbitrarily oversized `pool` (25 over 5 threads) is a mis-sizing finding, and its real extra draw is the executor and Cable threads, not `pool - threads`.

### Sidekiq sizing

Sidekiq pods are a separate process from Puma - separate pool entry in the deployment-wide sum.

```yaml
:concurrency: 15
```

Set `RAILS_MAX_THREADS=15` in the Sidekiq deployment env so `pool=15` matches. A `database.yml` that hardcodes one `pool` for every process mis-sizes whichever tier's thread count differs.

Partition memory- or query-heavy queues onto a separate Sidekiq process with lower `concurrency`. A queue running 10s SQL at `concurrency: 25` holds 25 connections for ten seconds.

### Deploy-window doubling

During rolling deploy, both ReplicaSets coexist (~60s). Worst case (full overlap) ~2x steady-state; with bounded surge, peak ≈ steady x (1 + maxSurge) per surging tier - compute both and size for the one your rollout strategy actually allows.

Mitigations, ordered for large fleets ("backend process" = OS process holding direct DB connections: puma pods x workers + sidekiq pods x processes):

1. **Connection multiplexer** in front of the DB - essentially mandatory above ~200 backend processes:
   - MySQL: **RDS Proxy** (managed) or **ProxySQL** (self-hosted)
   - PostgreSQL: **PgBouncer** transaction-pool or **RDS Proxy for Postgres**
2. **Lower per-process thread counts** - `threads=5` to `threads=3` cuts pool footprint by 40%
3. **`maxSurge=0`** in Kubernetes - old pods drain before new start; trades deploy speed for connection budget
4. **Size the DB instance class for peak**, not steady-state

Below ~200 processes, invert the order: raising `max_connections` (self-hosted with RAM to spare) or the instance class is simpler than operating a multiplexer.

### RDS / Aurora limits

RDS MySQL default: `max_connections = {DBInstanceClassMemory/12582880}` - a plain divide, no cap. (The 16000 figure often quoted is Aurora MySQL's hard ceiling, not an RDS MySQL default.)

| Instance         | Memory | Default `max_connections` |
| ---------------- | ------ | ------------------------- |
| `db.t3.micro`    | 1 GB   | ~85                       |
| `db.t3.small`    | 2 GB   | ~170                      |
| `db.t3.medium`  | 4 GB   | ~340                      |
| `db.t3.large`   | 8 GB   | ~683                      |
| `db.r6g.large`  | 16 GB  | ~1365                     |
| `db.r6g.xlarge` | 32 GB  | ~2730                     |

Aurora MySQL: per writer, readers have their own, and the default formula differs - the table above is RDS MySQL only (`db.r6g.large` defaults to ~1000 on Aurora, not 1365). RDS PG: `max_connections = LEAST({DBInstanceClassMemory/9531392}, 5000)` - unlike RDS MySQL this one *is* capped, so a bare divide over-predicts above ~45 GiB (a 128 GB `db.r6g.4xlarge` computes ~14,400 but caps at 5000); `db.r6g.large` 16 GB ~= 1800. Per-connection memory is higher on PG. Always confirm the live value (`SHOW VARIABLES LIKE 'max_connections'` / `SHOW max_connections`) - parameter groups override the formula, and when observed errors contradict the computed budget, an override is the first suspect.

### Detection in production

```ruby
ActiveRecord::Base.connection_pool.stat
# { size: 7, connections: 5, busy: 4, dead: 0, idle: 1, waiting: 0, checkout_timeout: 5.0 }
# waiting > 0 repeatedly = undersized; checkout_timeout is how long a thread waits
# before ConnectionTimeoutError
```

DB-side:

```sql
-- MySQL
SELECT user, host, state, COUNT(*) FROM information_schema.processlist GROUP BY user, host, state;
-- PostgreSQL
SELECT state, COUNT(*) FROM pg_stat_activity GROUP BY state;
```

| Error                                                | Meaning                              |
| ---------------------------------------------------- | ------------------------------------ |
| `ActiveRecord::ConnectionTimeoutError`               | In-process pool exhausted            |
| `Mysql2::Error: Too many connections`                | DB `max_connections` reached         |
| `PG: remaining connection slots are reserved`        | PG `max_connections` reached         |
| `Mysql2::Error: MySQL server has gone away`          | Network blip, DB restart, `wait_timeout` on idle |

### Reserved budget

Easy to forget; commonly the last 5% that pushes a deploy over:

- Rails console attached to prod (sometimes idle hours)
- Rake one-offs (parallel deploys spawn several)
- Datadog / New Relic / Prometheus exporters polling `pg_stat_activity`
- Backup tools (`mysqldump`, `pg_dump`)
- Schema tools (`db-ops`, `liquibase`, `gh-ost` heartbeat)

Reserve 5-10 connections - 10 when a backup or ETL tool connects on a schedule.

### Fork resets

Active Record discards parent connections in forked children automatically (Rails >= 6.1, via `ForkTracker`) - no `on_worker_boot { establish_connection }` needed, and its absence in a `puma.rb` is not a finding. What still needs an explicit fork reset (Puma `preload_app!`, Sidekiq Enterprise multi-process): non-AR clients holding sockets across fork - Redis pools, persistent HTTP connections, custom DB drivers.

### Multiplexer notes

- **RDS Proxy**: transparent to Rails; pinning on `LOCK TABLES`, temp tables, prepared-statements-without-parameters. Watch `DatabaseConnectionsCurrentlySessionPinned` for pinning, with `DatabaseConnectionsCurrentlyBorrowed` and `DatabaseConnectionsBorrowLatency` for pool pressure.
- **ProxySQL**: query routing, read/write splitting; more ops overhead than RDS Proxy.
- **PgBouncer**: transaction-pool mode multiplexes (what you usually want); `database.yml` points `url`/`host` at the PgBouncer listener and it requires `prepared_statements: false` (per-query replan cost) unless PgBouncer >= 1.21 with `max_prepared_statements` set. Session-pool only bounds backend count - one client per backend, no multiplexing - useful as a connection cap, not a fleet-size fix. Statement-pool breaks transactions.

## Output Format

One block per database instance (a read replica is its own budget; a documented replica no process connects to gets one line, no block). A proposal (N pods -> M) gets one block per state. Two independent symptoms get two `Result:` lines.

```
Database: {MySQL | PostgreSQL} on {RDS / Aurora / self-hosted, instance class}

max_connections: {value}

Headroom target: {15% bounded and measured deploy peak | 25% unmeasured, unbounded, or shared instance}

Reserved (CLI + ops): {N}

Available for app: {max_connections x (1 - headroom) - reserved} = {value}   # gates steady state AND deploy peak

Web tier: {pods} x {workers} x {threads} = {total}, pool = {N}

Executor / Cable extras: per process {pool - threads} provisioned vs {executor_concurrency + Cable threads} required; fleet {pods x workers x required}   # equal is correct; provisioned 0 with a required >0 is the GAP that causes timeouts; provisioned above required is the mis-sized pool

Worker tier: {pods} x {processes (1 per pod unless the manifest says otherwise)} x {concurrency} = {total}, pool = {N}   # name any job that holds a connection for minutes

Cron / rake: {peak parallel scheduled app processes - schedules that overlap in time count together} = {total}   # ad-hoc console/ops live in Reserved

Steady-state total: {sum}

Deploy peak (rolling): {steady x (1 + maxSurge) bounded - k8s | ~2x full overlap - default when the rollout has no surge knob (Capistrano, ASG) or no manifest is in scope | measured}

Result: {within budget | within budget, multiplexer not yet warranted (< ~200 backend processes) | a per-process pool is mis-sized - state which tier and the corrected pool (combines with either outcome) | exceeds by {N} - mitigation: {raise max_connections or larger instance (below ~200 backend processes) | multiplexer (RDS Proxy / PgBouncer / ProxySQL) | reduce threads | maxSurge=0}}
```

## Avoid

- `pool` higher than `puma_threads` + the documented executor / Cable extras
- Sizing for steady-state only - the deploy peak causes the outage
- Forgetting Sidekiq is a separate process from Puma
- Direct connections >200 backend processes without a multiplexer
- Tuning `pool` without re-checking deployment-wide total
- Treating `max_connections` as hard ceiling - leave 15-25% headroom
- Assuming `load_async` is free - the process-global executor adds up to `global_executor_concurrency` connections per process (not one per query)
