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
- Deployment-wide sum stays under DB `max_connections` with 15-25% headroom.
- Rolling deploys hold old + new pool simultaneously - size for the peak.
- A long-running query holds the connection for its full duration.
- Never tune `pool` without re-deriving the deployment-wide total.

## Patterns

### Total-connection formula

```
total =
    (puma_pods * puma_workers * puma_threads)         # web
  + (sidekiq_pods * sidekiq_processes * concurrency)  # workers
  + reserved_for_cli                                  # console, rake one-offs
  + reserved_for_ops                                  # exporters, backups, schema tools
```

Example - 30 web (`workers=2, threads=5`) + 10 worker (`concurrency=15`) + 5 CLI/ops:

```
30 * 2 * 5 + 10 * 15 + 5 = 455 steady-state
Deploy peak (rolling, old + new alive): ~910
```

On `db.t3.medium` (~340 max_connections), the deploy peak exhausts the pool before new pods serve traffic.

### Per-process pool size

| Process              | `pool`                                                                   |
| -------------------- | ------------------------------------------------------------------------ |
| Puma worker          | `puma_threads` (`+1`/`+2` if `load_async` / ActionCable in same process) |
| Sidekiq process      | `sidekiq.concurrency`                                                    |
| Rails console / rake | 1 default; bump only if the script spawns threads                        |

```yaml
# Bad - reserves 20 unused connections
pool: 25  # threads=5
# Good
pool: <%= ENV.fetch("RAILS_MAX_THREADS") { 5 } %>
```

### Headroom for non-request work

`load_async` (Rails 7.1+), ActionCable subscribers, ActiveStorage analyzers, custom `Concurrent::FixedThreadPool` - all check out from the same pool. The async executor is one per process, shared across requests, sized by `global_executor_concurrency` (default 4) - 6 async queries in one request still cap at 4 extra connections. Size `pool = puma_threads + executor_concurrency (+ Cable worker threads, default 4, if mounted in-process)`. Count these extras in the deployment-wide sum as `pods x workers x (pool - threads)` - the formula's `threads` term misses them.

### Sidekiq sizing

Sidekiq pods are a separate process from Puma - separate pool entry in the deployment-wide sum.

```yaml
:concurrency: 15
```

Set `RAILS_MAX_THREADS=15` in the Sidekiq deployment env so `pool=15` matches.

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

RDS MySQL default: `max_connections = LEAST({DBInstanceClassMemory/12582880}, 16000)`.

| Instance         | Memory | Default `max_connections` |
| ---------------- | ------ | ------------------------- |
| `db.t3.micro`    | 1 GB   | ~85                       |
| `db.t3.small`    | 2 GB   | ~170                      |
| `db.t3.medium`  | 4 GB   | ~340                      |
| `db.t3.large`   | 8 GB   | ~683                      |
| `db.r6g.large`  | 16 GB  | ~1365                     |
| `db.r6g.xlarge` | 32 GB  | ~2730                     |

Aurora MySQL: per writer; readers have their own. RDS PG: similar formula (`/9531392`); per-connection memory higher. Always confirm the live value (`SHOW VARIABLES LIKE 'max_connections'` / `SHOW max_connections`) - parameter groups override the formula, and when observed errors contradict the computed budget, an override is the first suspect.

### Detection in production

```ruby
ActiveRecord::Base.connection_pool.stat
# { size: 7, connections: 5, busy: 4, dead: 0, idle: 1, waiting: 0 }
# waiting > 0 repeatedly = undersized
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

Reserve 5-10 connections.

### Fork resets

After fork (Puma `preload_app!`, Sidekiq Enterprise multi-process), reset connections on the child:

```ruby
on_worker_boot { ActiveRecord::Base.establish_connection }
```

### Multiplexer notes

- **RDS Proxy**: transparent to Rails; pinning on `LOCK TABLES`, temp tables, prepared-statements-without-parameters. Watch `DatabaseConnectionsBorrowedSerial`.
- **ProxySQL**: query routing, read/write splitting; more ops overhead than RDS Proxy.
- **PgBouncer**: transaction-pool mode multiplexes (what you usually want); it requires `prepared_statements: false` (per-query replan cost) unless PgBouncer >= 1.21 with `max_prepared_statements` set. Session-pool only bounds backend count - one client per backend, no multiplexing - useful as a connection cap, not a fleet-size fix. Statement-pool breaks transactions.

## Output Format

```
Database: {MySQL | PostgreSQL} on {RDS / Aurora / self-hosted, instance class}
max_connections: {value}
Headroom target: {%}
Reserved (CLI + ops): {N}
Available for app: {value}

Web tier: {pods} x {workers} x {threads} = {total}, pool = {N}
Worker tier: {pods} x {processes} x {concurrency} = {total}, pool = {N}
Cron / rake: {peak parallel scheduled app processes} = {total}   # ad-hoc console/ops live in Reserved

Steady-state total: {sum}
Deploy peak (rolling): {steady x (1 + maxSurge) bounded | ~2x full overlap | measured}
Result: {within budget | exceeds by {N} - mitigation: {RDS Proxy | reduce threads | larger instance | maxSurge=0}}
```

## Avoid

- `pool` higher than in-process thread count
- Sizing for steady-state only - the deploy peak causes the outage
- Forgetting Sidekiq is a separate process from Puma
- Direct connections >200 backend processes without a multiplexer
- Tuning `pool` without re-checking deployment-wide total
- Treating `max_connections` as hard ceiling - leave 15-25% headroom
- Assuming `load_async` is free - each async query holds an extra connection
