---
name: backend-connection-pooling
description: Whole-deployment DB pool math - per-process pool x process count x rolling-deploy overlap vs max_connections, worker concurrency, pooler tiers.
metadata:
  category: backend
  tags: [connection-pool, capacity, postgres, pgbouncer, deployment, multi-stack]
user-invocable: false
---

# Connection Pool Sizing

> Load `Use skill: stack-detect` first to determine the project stack.

Owns the **whole-deployment** pool arithmetic: the per-process pool line must survive replicas, background workers, rolling deploys, and a pooler tier.

## When to Use

- Setting a pool size for the first time
- Adding API replicas, worker replicas, or read replicas
- Investigating "too many connections" / "too many clients" errors, or requests timing out while acquiring a connection
- Introducing or removing a pooler (PgBouncer, RDS Proxy, or an equivalent)
- Moving any part of the workload to a scale-to-zero or per-request runtime

## The Capacity Equation

```
effective     = max_connections - reserved slots (PostgreSQL: superuser_reserved_connections, plus reserved_connections
                on 16+; MySQL: 0 - its one admin connection sits above max_connections)
steady state  = sum over long-running roles ( per_process_pool x process_count )      target <= 80% of effective
window peak   = steady state + one-shots running in that window                       must be <= 100% of effective
deploy peak   = steady state + surge processes + one-shots overlapping the deploy      must be <= 100% of effective

process_count covers, per database endpoint:
  - API replicas x server processes per replica (each forked web-server worker - Puma cluster, gunicorn -w, uvicorn
    --workers, Node cluster - is a process with its own pool); a worker loop inside the API process shares its pool,
    and the API line checks C x F + S <= P, S being that process's request concurrency (server threads, or the async
    server's concurrent-request limit)
  - Worker processes: replicas (threaded) or replicas x prefork children (each child is a process with its own pool)
  - The scheduler, when its process constructs a database client: a database-backed queue (Oban, Solid Queue, GoodJob,
    pg-boss, delayed_job) enqueues by SQL insert and counts; a scheduler enqueueing to Redis, SQS, or RabbitMQ is 0
  - A per-request runtime (Lambda, Cloud Run scale-to-zero) connecting directly: concurrency cap x connections per
    execution environment - each live environment holds its own client; Lambda with no reserved concurrency is bounded
    only by its regional quota (default 1,000): unbounded here; Cloud Run always has a cap
    (max-instances, default 100 per revision)
  - Surge processes during a rolling deploy: Kubernetes Deployment RollingUpdate adds maxSurge per role when it is an
    absolute count, ceil(replicas x maxSurge%) when a percentage (maxSurge and maxUnavailable both default 25%), plus terminating old pods Q, which
    are not counted against maxSurge: the extra is min(2 x maxSurge + maxUnavailable, replicas) (a percentage maxUnavailable rounds down) when each scaled-down batch finishes
    terminating before the next new batch turns Available, otherwise terminating pods pile up and the extra is
    replicas (the role doubles; with no readiness probe new pods are Available at once, so assume doubling); ECS adds min(floor(desired x maximumPercent / 100) - desired + old tasks still draining, desired) (default maximumPercent 200 doubles
    the role; draining tasks: ALB deregistration delay, default 300 s, then stopTimeout, default 30 s,
    which maximumPercent does not count); StatefulSet adds 0; DaemonSet adds its maxSurge (default 0, a
    percentage rounds up against desired nodes); blue/green doubles every role
Replicas count at the autoscaler's maximum (HPA maxReplicas, the ECS service's max tasks) when one exists, and surge
is computed on that maximum.
One-shot containers (migrations, cron, batch jobs) are not in process_count; they are added to the window they run in.
```

`per_process_pool` is the client's hard maximum for one process: HikariCP `maximumPoolSize`; SQLAlchemy `pool_size + max_overflow` when `max_overflow >= 0` (`max_overflow=-1`, `pool_size=0`, or `NullPool` means no per-process cap at all). The equation assumes **one database client per process, constructed at startup**; a client constructed per request or per job makes the effective pool equal to the concurrent request count. Audit for construction outside the startup path first. The 20% headroom is the reserve for ad-hoc sessions and monitoring exporters at steady state; transient peaks (a deploy, a one-shot window) may consume it up to 100%.

## Rules

- Per-process pool size expresses what that one process needs concurrently, not what the database can offer.
- Worker concurrency plus two must not exceed a threaded worker process's pool (the two are for health checks and non-job paths); a prefork child's concurrency (its thread count, 1 when single-threaded; Celery `--concurrency` is the child count K, Sidekiq's is threads) must not exceed its own pool; a job that fans out queries in parallel multiplies its concurrency by the in-flight peak per job first. Exceeding it presents as a queue stall, not a database error.
- Size against the **deploy peak**, not steady state.
- Drain the old client on shutdown. On the termination signal, stop accepting work, await in flight, then close the pool explicitly: the surge window stays as short as the rollout, and in-flight transactions finish instead of being killed. Closing the pool without awaiting in-flight work (goroutines or tasks the shutdown path does not join) is a partial drain.
- Every one-shot container counts for the window it runs in. Schedule migrations and batch jobs away from the deploy window; a one-shot ordered before one role's rollout still overlaps every other role's rollout in the same release, while a hook that completes before any rollout starts (Argo CD `PreSync`, Helm `pre-upgrade`) runs in its own window.
- Run the equation per database endpoint. A read replica has its own `max_connections` and its own tally of the processes that point at it.
- A per-request or scale-to-zero runtime must not connect directly to the database: live connections track live execution environments, bounded only by a concurrency cap. Route through a pooler, or defer the work to a long-running process when the work is a continuous poll rather than request-shaped.
- Declared configuration that no code reads (a pool-size environment variable the client ignores) is a finding: the number in the deployment file is not the number in production.

## Patterns

Fixes, in order of preference:

1. Cap the surge to a small absolute count (`maxSurge: 1`) instead of a percentage, and keep the old pod's drain shorter than the new pod's time to Available, so at most one terminating batch overlaps the surge and the extra stays at 2 x maxSurge + maxUnavailable.
2. Move one-shots out of the deploy window.
3. Drop the per-process pool until the deploy peak fits, accepting more queueing inside each process.

Adding a pooler is the fourth option, not the first; it moves the arithmetic, with the caveats below.

### Pooler Tiers

| Tier                       | Effect                                                        | Caveat                                                                                     |
| -------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Session-mode pooler        | Connection held for the session; no multiplexing              | Each `(user, database)` pool still caps backends at `default_pool_size` (20); app connections beyond it wait, then fail with `query_wait_timeout` (120 s default), and long-lived app pools never clear the queue - the per-pool block shape below, without the transaction-mode hazards |
| Transaction-mode pooler    | Connection returned per transaction; large multiplexing win   | Breaks session-level `SET`, `LISTEN` (`NOTIFY` is transactional and safe), session advisory locks (`pg_advisory_lock`), SQL-level `PREPARE`, `LOAD`, temporary tables that outlive the transaction (`ON COMMIT DROP` is safe), `WITH HOLD` cursors; protocol-level prepared statements work on PgBouncer 1.21+ (`max_prepared_statements`, default 200 since 1.24, 0 before) |
| Managed proxy (RDS Proxy)  | Multiplexing at transaction boundaries, handled for you       | Session state (session `SET` / `set_config`, temp tables, sequences or views, `LISTEN`, SQL `PREPARE` / `DEALLOCATE` / `EXECUTE`, `DISCARD`, `LOAD` (`auto_explain`), declared cursors, `nextval` / `setval`, session advisory locks) pins the client to one backend until it disconnects - correctness holds, multiplexing is lost; long transactions hold a backend until commit; adds per-round-trip latency; backend connections are capped at `MaxConnectionsPercent` of the target's `max_connections`, client connections not at all |

Under a transaction-mode pooler, transaction-scoped constructs (`SET LOCAL`, `pg_advisory_xact_lock`) stay safe because a transaction stays on one backend connection and the lock is released at commit; session-scoped ones do not. Under RDS Proxy for PostgreSQL, `pg_advisory_xact_lock` does not pin, but AWS lists `SET` commands - with no `SET LOCAL` exemption - among the pinning triggers: the swap keeps correctness, not multiplexing; fixed session settings belong in the proxy's initialization query.

With a transaction-mode pooler or managed proxy, the per-process pool becomes a thin local queue; the pooler holds the real connections. With any pooler the equation runs twice: the sum of app pools against the pooler's client cap, and the pooler's backend connections against `max_connections`. The client cap is PgBouncer `max_client_conn` (default 100); RDS Proxy has none. PgBouncer's limits apply per PgBouncer process (each `so_reuseport` process is one; at the deploy peak add the pooler's own surge): its backend count is instances x the sum over its `(user, database)` pools of `pool_size + reserve_pool_size`, and the client cap is instances x `max_client_conn`. Its per-database and per-user limits span every pool of that database or user and default to 0 (unlimited): `max_db_connections` / `max_user_connections` cap server connections, so a database or user with one set contributes min(instances x that limit, instances x its pools' `pool_size + reserve_pool_size`) to the backend count; `max_db_client_connections` / `max_user_client_connections` (1.24+) cap clients, and each one set gets its own app-side block (below). RDS Proxy's backend count is `MaxConnectionsPercent / 100 x max_connections`.

## Output Format

One block per capacity boundary, blank-line separated; each database endpoint (the primary, each read replica) that any process points at is its own boundary, and an endpoint no process points at gets no block. With tier `none`, an endpoint has one block whose `Boundary` is `max_connections`. With any pooler tier, an app-side block, zero or more extra app-side blocks, then a backend block: the app-side block is the full template minus `Pooler backend` (`Boundary` = the pooler's client cap, every role that goes through the pooler, `Hazards` carrying the tier check), then one extra app-side block per PgBouncer per-database or per-user client limit that is set (`Boundary` = instances x that limit, the roles on that database or user) and, under session mode, one per `(user, database)` pool (`Boundary` = instances x `pool_size + reserve_pool_size`, the roles on that pool) - an extra block carries `Boundary`, its role lines, the three percentage lines, `Verdict`, and `Action` - then the backend block carries only `Boundary` = `max_connections`, `Pooler backend`, role lines for roles that connect directly (`none` otherwise), the three percentage lines, `Verdict`, and `Action`; the heading, `Engine`, `Client audit`, `Surge`, `Pooler tier`, `Config drift`, and `Drain` appear once per assessment, in its first block; a later endpoint whose tier differs carries its own `Pooler tier` and `Hazards`. A proxy the proposal only asks about is a second assessment after the as-written one, headed `## Pool Sizing Assessment (with <proxy>)`. The sizing arithmetic is carried by the role and percentage lines; an incident narrative belongs to the consuming workflow, not this block. Under RDS Proxy the app-side Boundary is `pooler client cap: none (RDS Proxy)`, its percentage lines read `n/a - no client cap`, and its Verdict is `Unbounded` when an `Unbounded` trigger fires, else `Fits`. Every role goes through the pooler unless the proposal or the deployment file routes it directly. Percentages divide by the block's own effective figure; the 80% target and 100% ceiling apply to every block. After the last block of each assessment, one `Overall:` line carries that assessment's worse Verdict (rank: `Unbounded` > `Breaches at steady state` > `Breaches at deploy peak` > `Breaches in a one-shot window` > `Over target at steady state` > `Fits`) and the merged Actions, app-side first.

```
## Pool Sizing Assessment

Engine: {PostgreSQL <version> | MySQL <version> | <database> <version> - reserved slots unverified | unknown}{ (assumed: <what>)}

Boundary: {max_connections N (reserved M, effective N-M) | pooler client cap N (effective N) | pooler <limit name> <database or user> N (effective N) | pooler pool <user/database> N (effective N) | pooler client cap: none (RDS Proxy)}{ (assumed: <what>)}

Client audit: {one client per process, constructed at startup | constructed per request or job at <file:line>}

API: {replicas R{ x processes K} x pool P = T{ (in-process worker loop: C{xF} + S <= P {holds | fails})} | none}

Workers: {replicas R{ x children K} x pool P = T (concurrency C per process{ x fan-out F}; {C{xF} + 2 <= P, threaded | C{xF} <= P per child, prefork} {holds | fails}) | none}

Scheduler: {replicas R x pool P = T | none - enqueues to <broker> only}

Per-request runtime: {<name>: cap C x connections per environment N = T | <name>: no cap - unbounded | none}

One-shots: {<name>: pool P during <window>{, overlaps deploy}, ... | none}

Pooler backend: {PgBouncer: instances I (I + G at deploy peak, G the pooler's own surge) x sum over (user, database) pools of pool_size + reserve_pool_size, a database or user with max_db_connections / max_user_connections set taking min(I x limit, I x its pools' sum) = N steady / N' deploy peak | RDS Proxy: MaxConnectionsPercent / 100 x max_connections = N (unstated: 100, or 10 on RDS for SQL Server, marked assumed) | n/a - tier none}

Surge: {Deployment: min(2 x maxSurge + maxUnavailable, R) per role (maxSurge absolute or ceil(R x maxSurge%), maxUnavailable absolute or floor(R x maxUnavailable%); terminating pods Q = extra - maxSurge) | Deployment: R per role (terminating pods pile up) | ECS: min(floor(R x maximumPercent / 100) - R + draining tasks D, R) | StatefulSet: 0 | DaemonSet: maxSurge | blue/green: doubles}; {the processes it adds}{ (assumed: <what>)}

Pooler tier: {none | session mode | transaction mode | managed proxy}{ (assumed)}

Hazards: {none | comma-separated session-scoped constructs the codebase uses that the tier breaks or pins, and a transaction held open across an external call | n/a - tier none or session mode}

Config drift: {none | <declared value> in <file> vs <value the code uses> at <file:line>}

Drain: {pool closed on termination at <file:line or hook> after awaiting in-flight work | partial - pool closed at <file:line> without awaiting in-flight work | none - in-flight transactions are killed on rollout | n/a - per-request runtime, or a proposal with no code yet}

Steady state: {U / effective (percent; target <= 80%){, excluding the unbounded entries} | n/a - no client cap}

Deploy peak: {P / effective (percent; must be <= 100%){, excluding the unbounded entries} | n/a - no client cap}

Window peak: {W / effective (percent; must be <= 100%) for <one-shot window> | n/a - no one-shots | n/a - no client cap}

Verdict: {Fits | Over target at steady state | Breaches in a one-shot window | Breaches at deploy peak | Breaches at steady state | Unbounded}{ (assumed)}

Action: {ship as is | cap deploy surge at X | move one-shots off the deploy window | reduce pool to X | cap the per-process pool at X | cap worker concurrency at X | cap threads per child at X | construct the client at startup | route <runtime> through a pooler | cap <runtime> concurrency at X | defer <work> to a long-running process | replace session-scoped constructs | bypass the pooler for <role> | use session mode | raise the pooler client cap to X | raise <limit name> to X | shorten old-pod drain below new-pod time to Available | commit before the external call | implement the declared pool config | add a drain hook}

Overall: {the worse Verdict across blocks} - {merged Actions}
```

`Verdict` is produced by the percentages: `Breaches at steady state` when steady state exceeds 100%; else `Breaches at deploy peak` when the deploy peak exceeds 100%; else `Breaches in a one-shot window` when a window peak exceeds 100%; else `Over target at steady state` when steady state exceeds 80%; else `Fits`. `Unbounded` replaces all of these when the `Client audit` fails, a per-process pool has no cap, or a `Per-request runtime` has no cap: the percentage lines then carry the bounded entries only, marked `excluding the unbounded entries`. When any input is unknown (a tier the proposal does not state, a missing orchestrator field, `reserved_connections` on an unstated version), state the assumption inline on its line and suffix the verdict `(assumed)`.

`Action` lists the minimal set of remedies, comma-joined, one per violation in the order the template lines appear; `ship as is` is emitted when no other Action is produced, and only alone. A remedy whose value differs per role names the role (`reduce pool to 6 (API), 4 (workers)`); X in `reduce pool to X` is the per-process cap (`pool_size + max_overflow` for a SQLAlchemy-style pool; the split is the client's choice), solved by scaling every long-running role's pool by the same factor until every failing line meets its limit (100% for a peak, 80% at steady state) - a window breach alone instead reduces the one-shot's pool to the largest value at which the window peak meets 100% -, never below a worker role's `C x F + 2` (threaded), `C x F` (prefork child), or the API role's `C x F + S` when it runs an in-process worker loop - when that floor binds, X' being the scaled pool before the floor was applied, emit `cap worker concurrency at max(1, floor((X' - 2) / F))` (threaded; `(X' - S) / F` for the API loop) or `cap threads per child at max(1, floor(X' / F))` (prefork) beside `reduce pool to X'`, and when even concurrency 1 does not fit (X' below F + 2 threaded, F prefork, F + S for the API loop), emit `cap worker concurrency at 1` (or `cap threads per child at 1`) beside `reduce pool to F + 2` (`F`, `F + S`) and let the percentage line keep failing. `Verdict` grades capacity only, so a `Fits` verdict can sit beside a non-empty Action list from the worker check, hazards, config drift, or the drain line. Producing conditions: `cap deploy surge at X` (the `maxSurge`, with the `maxUnavailable` whenever a terminating batch Q is in the surge, that makes min(2 x maxSurge + maxUnavailable, replicas) fit, or for ECS the `maximumPercent` that fits; blue/green has no tunable surge and produces `reduce pool to X` instead) when the deploy peak breaches while steady state does not and the surge processes' connections exceed those of the one-shots overlapping the deploy - when the surge extra is `replicas` (Kubernetes pile-up) or ECS draining tasks D fill the min(..., R) cap, `shorten old-pod drain below new-pod time to Available` (Kubernetes: the old pod's drain; ECS: the target group's `deregistration_delay.timeout_seconds` plus `stopTimeout`) is emitted before it, and X is solved for the 2 x maxSurge + maxUnavailable shape (Kubernetes) or for floor(R x maximumPercent / 100) - R + D with D the tasks still draining after the shortened delay (ECS); `move one-shots off the deploy window` when a one-shot overlaps a breaching deploy, `reduce pool to X` when steady state exceeds 80% or a peak still fails after those two (a window breach: the one-shot's pool); `raise the pooler client cap to X` when an app-side block breaches and its backend block fits, in place of `reduce pool to X` for that block (an extra block emits `raise <limit name> to X` for the limit that is its Boundary instead, and the backend block is recomputed with it); `cap the per-process pool at X` when a per-process pool has no cap; `cap worker concurrency at X` when a threaded worker check (or the API in-process loop check) fails, `cap threads per child at X` when a prefork per-child check fails; `construct the client at startup` when the client audit fails; a direct-connecting per-request runtime produces `defer <work> to a long-running process` when its work is a continuous poll (a relay, a sweeper) and `route <runtime> through a pooler` when it is request-shaped; an uncapped runtime that already goes through the pooler produces `cap <runtime> concurrency at X`; a `Hazards` entry produces `replace session-scoped constructs` when a transaction-scoped equivalent exists (`pg_advisory_lock` -> `pg_advisory_xact_lock`; `SET` -> `SET LOCAL` under a transaction-mode pooler, the proxy's initialization query under RDS Proxy; SQL `PREPARE` -> protocol-level on PgBouncer 1.21+), `bypass the pooler for <role>` when the construct is inherent to one role (`LISTEN`, a temp table across transactions), and `use session mode` only when most roles need session constructs; a transaction held open across an external call (listed under transaction mode or a managed proxy, where it holds a backend connection for the call's duration) produces `commit before the external call` - the restructuring is `backend-transaction-patterns`'; `implement the declared pool config` when `Config drift` is not `none`; `add a drain hook` when `Drain` is `partial` or `none`.

## Avoid

- Raising the acquisition timeout to mask exhaustion; it converts a fast failure into a pile-up
