---
name: rails-connection-pool-sizing
description: Connection pool sizing for Rails: Puma + Sidekiq + console budget vs DB max_connections, deploy spikes, RDS Proxy / ProxySQL / PgBouncer.
metadata:
  category: backend
  tags: [ruby, rails, database, mysql, postgresql, connections, ops]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Sizing `RAILS_MAX_THREADS`, Puma `workers`/`threads`, Sidekiq `concurrency`, and `database.yml` `pool` together
- Diagnosing `ConnectionTimeoutError`, `Mysql2::Error: Too many connections`, `PG::ConnectionBad: remaining connection slots reserved`
- Capacity review before traffic increase, instance class change, or rolling deploy
- Adding a long-lived thread pool (`load_async`, Action Cable, custom executor)
- Deciding whether to put RDS Proxy / ProxySQL / PgBouncer in front of the database

## Rules

- Each thread that calls ActiveRecord checks out one connection - count threads, not pods
- Per-process pool must satisfy `pool >= max_threads_in_that_process` - more is wasted, less leaks `ConnectionTimeoutError`
- Sum across the whole deployment must stay under DB `max_connections` with 15-25% headroom for deploys
- Rolling deploys hold connections from old + new pods simultaneously - size for the peak
- A long-running query holds the connection for its full duration
- Never tune `pool` without re-deriving the deployment-wide total

## Patterns

### The total-connection formula

```
total =
    (puma_pods * puma_workers * puma_threads)        # web tier
  + (sidekiq_pods * sidekiq_processes * concurrency) # worker tier
  + reserved_for_cli                                 # console, dbconsole, rake one-offs
  + reserved_for_ops                                 # exporters, backups, schema tools
```

Worked example - 30 web pods (`workers=2, threads=5`) + 10 worker pods (`concurrency=15`) + 5 CLI/ops:

```
30 * 2 * 5 + 10 * 15 + 5 = 300 + 150 + 5 = 455 steady-state
Deploy peak (rolling, both old + new alive): ~910
```

On `db.t3.medium` (~340 max_connections), the deploy peak exhausts the pool before new pods serve traffic.

### Per-process pool size

| Process kind         | `pool` should be                                                           |
| -------------------- | -------------------------------------------------------------------------- |
| Puma worker          | `puma_threads` (`+1`/`+2` if `load_async` / Action Cable in same process)  |
| Sidekiq process      | `sidekiq.concurrency`                                                      |
| Rails console / rake | 1 (default); bump only if the script spawns its own threads                |

Bad - inflated pool size:

```yaml
# Puma threads = 5, but pool = 25
pool: 25
```

The extra 20 are reserved against `max_connections` for nothing.

Good - track in-process thread count:

```yaml
pool: <%= ENV.fetch("RAILS_MAX_THREADS") { 5 } %>
```

### Headroom for non-request work

These spawn threads that check out connections from the same pool:

- `load_async` queries (Rails 7.1+) - default `:global_thread_pool` is 4 threads
- ActionCable subscribers - one connection per active subscription
- ActiveStorage analyzers / previewers running inline
- Custom `Concurrent::FixedThreadPool` you spawn yourself

When any are in use, set `pool = RAILS_MAX_THREADS + 2`. Verify:

```ruby
ActiveRecord::Base.connection_pool.stat
# { size: 7, connections: 5, busy: 4, dead: 0, idle: 1, waiting: 0, checkout_timeout: 5.0 }
```

`waiting > 0` repeatedly means the pool is undersized.

### Sidekiq sizing

A Sidekiq process with `concurrency: 25` is twenty-five DB clients. Sidekiq pods are a separate process from Puma and need their own pool entry in the deployment-wide sum.

```yaml
# config/sidekiq.yml
:concurrency: 15
```

Set `RAILS_MAX_THREADS=15` in the Sidekiq Deployment env so `pool=15` matches.

Partition memory- or query-heavy queues onto a separate Sidekiq process with lower `concurrency` - a queue running 10-second SQL at `concurrency: 25` holds 25 connections per ten seconds.

### Deploy-window doubling

During a rolling deploy, both old and new ReplicaSets coexist (~60s). Each pod still holds its full pool. Effective peak ~2x steady-state.

Mitigations in leverage order:

1. **Connection multiplexer in front of the DB:**
   - MySQL: **RDS Proxy** (managed, IAM auth) or **ProxySQL** (self-hosted)
   - PostgreSQL: **PgBouncer** (transaction pooling, set `prepared_statements: false` for transaction mode) or **RDS Proxy for Postgres**
   - Essentially mandatory above ~200 backend processes
2. **Lower per-process thread counts** - `threads=5` to `threads=3` cuts pool footprint by 40%
3. **Surge `maxSurge=0`** in Kubernetes - old pods drain before new start, trades deploy speed for connection budget
4. **Size the DB instance class for peak**, not steady-state

### RDS / Aurora connection limits

RDS MySQL `max_connections` default: `LEAST({DBInstanceClassMemory/12582880}, 16000)`.

| Instance class    | Memory | Default `max_connections` |
| ----------------- | ------ | ------------------------- |
| `db.t3.micro`     | 1 GB   | ~85                       |
| `db.t3.small`     | 2 GB   | ~170                      |
| `db.t3.medium`    | 4 GB   | ~340                      |
| `db.t3.large`     | 8 GB   | ~683                      |
| `db.r6g.large`    | 16 GB  | ~1365                     |
| `db.r6g.xlarge`   | 32 GB  | ~2730                     |

Aurora MySQL: per writer node; readers have their own budget. RDS PG: similar formula (`/9531392`); per-connection memory higher, so practical ceilings are lower.

### Detection in production

```ruby
ActiveRecord::Base.connection_pool.stat   # waiting > 0 = pool undersized
```

DB-side:

```sql
-- MySQL
SELECT user, host, state, COUNT(*) FROM information_schema.processlist GROUP BY user, host, state;
-- PostgreSQL
SELECT state, COUNT(*) FROM pg_stat_activity GROUP BY state;
```

Error signatures:

| Error                                                                  | Meaning                                                |
| ---------------------------------------------------------------------- | ------------------------------------------------------ |
| `ActiveRecord::ConnectionTimeoutError`                                 | In-process pool exhausted - too many threads for `pool` |
| `Mysql2::Error: Too many connections`                                  | DB-side `max_connections` reached                      |
| `Mysql2::Error: Can't connect`                                         | DB cap reached or network                              |
| `PG: remaining connection slots are reserved`                          | PG `max_connections` reached                           |
| `PG::ConnectionBad: timeout`                                           | Pool full or network timeout                           |
| `Mysql2::Error: MySQL server has gone away`                            | Network blip, DB restart, or `wait_timeout` on idle    |

### Reserved budget for CLI and ops

Easy to forget; commonly the last 5% that pushes a deploy over the limit:

- Rails console attached to production (1/session, sometimes idle hours)
- `rake` one-offs (1 each, parallel deploys spawn several)
- Datadog / New Relic / Prometheus exporters polling `pg_stat_activity` / `information_schema`
- Backup tools (`mysqldump`, `pg_dump`)
- Schema tools (`db-ops`, `liquibase`, `gh-ost` heartbeat)

Reserve 5-10 connections.

### Sidekiq sharp edges

- A 10-second SQL inside a job holds the connection for ten seconds, starving siblings on the same process. Long jobs with rare slow queries should partition onto a separate process or queue.
- After fork (Puma `preload_app!`, Sidekiq Enterprise multi-process), reset connections on the child:

```ruby
on_worker_boot { ActiveRecord::Base.establish_connection }
```

### Connection multiplexer notes

- **RDS Proxy**: transparent to Rails; pinning happens on `LOCK TABLES`, temp tables, prepared-statements-without-parameters. Watch `DatabaseConnectionsBorrowedSerial`.
- **ProxySQL**: query routing, read/write splitting, query rewriting; more ops overhead than RDS Proxy.
- **PgBouncer**: transaction-pool mode requires `prepared_statements: false`; session-pool bounds backends without breaking statement semantics; statement-pool breaks transactions and is rarely useful for Rails.

## Output Format

```
Database: {MySQL | PostgreSQL} on {RDS / Aurora / self-hosted, instance class}
max_connections: {value} (default formula or override)
Headroom target: {%}
Reserved (CLI + ops): {N}
Available for app: {value}

Web tier: {pods} x {workers} x {threads} = {total}, pool = {N}
Worker tier: {pods} x {processes} x {concurrency} = {total}, pool = {N}
Cron / rake: {peak parallel count} = {total}

Steady-state total: {sum}
Deploy peak (rolling): {~2x or measured}
Result: {within budget | exceeds by {N} - mitigation: {RDS Proxy | reduce threads | larger instance | maxSurge=0}}
```

## Avoid

- Setting `pool` higher than the in-process thread count - reserves unusable connections
- Sizing for steady-state only - the deploy peak causes the outage
- Forgetting Sidekiq is a separate process from Puma
- Connecting >200 backend processes directly to the DB without a multiplexer
- Tuning `pool` without re-checking the deployment-wide total
- Treating `max_connections` as a hard ceiling - leave 15-25% headroom
- Assuming `load_async` is free - each async query holds an extra connection
