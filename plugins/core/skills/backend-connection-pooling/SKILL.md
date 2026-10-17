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

Owns the **whole-deployment** pool arithmetic. Per-process pool size is one configuration line in any stack; this skill makes that line survive replicas, background workers, rolling deploys, and a pooler tier.

## When to Use

- Setting a pool size for the first time
- Adding API replicas, worker replicas, or read replicas
- Investigating "too many connections" (MySQL), "sorry, too many clients already" or "remaining connection slots are reserved" (PostgreSQL), or requests timing out while acquiring a connection
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
  - API replicas
  - Worker processes: replicas (threaded) or replicas x prefork children (each child is a process with its own pool)
  - The scheduler, when its process constructs a database client: a database-backed queue (Oban, Solid Queue, GoodJob,
    pg-boss, delayed_job) enqueues by SQL insert and counts; a scheduler enqueueing to Redis, SQS, or RabbitMQ is 0
  - A per-request runtime (Lambda, Cloud Run scale-to-zero) connecting directly: concurrency cap x connections per
    execution environment - each live environment holds its own client; Lambda with no reserved concurrency is bounded
    only by its regional quota (default 1,000), far above any database: unbounded here; Cloud Run always has a cap
    (max-instances, default 100 per revision)
  - Surge processes during a rolling deploy: Kubernetes Deployment RollingUpdate adds ceil(replicas x maxSurge) per role
    (default 25%); ECS adds floor(desired x maximumPercent / 100) - desired (default maximumPercent 200 doubles the role); StatefulSet adds 0; DaemonSet adds its maxSurge
    (default 0); blue/green doubles every role
Replicas count at the autoscaler's maximum (HPA maxReplicas, the ECS service's max tasks) when one exists - the
declared count is the floor, and a scale-out can coincide with a deploy; surge is computed on that maximum.
One-shot containers (migrations, cron, batch jobs) are not in process_count; they are added to the window they run in.
```

`per_process_pool` is the client's hard maximum for one process: HikariCP `maximumPoolSize`; SQLAlchemy `pool_size + max_overflow` when `max_overflow >= 0` (`max_overflow=-1`, `pool_size=0`, or `NullPool` means no per-process cap at all). The equation assumes **one database client per process, constructed at startup**; a client constructed per request or per job makes the effective pool equal to the concurrent request count. Audit for construction outside the startup path first; either unbounded case is the `Unbounded` verdict. The 20% headroom is the reserve for ad-hoc sessions and monitoring exporters at steady state; transient peaks (a deploy, a one-shot window) may consume it up to 100%, which is acceptable for the minutes they last and never at steady state.

## Rules

- One database client per process, created at startup, never per request or per job.
- Per-process pool size expresses what that one process needs concurrently, not what the database can offer.
- Worker concurrency plus two must not exceed the worker process's pool (the two are for health checks and non-job paths); a job that fans out queries in parallel multiplies its concurrency by the in-flight peak per job first. Exceeding it presents as a queue stall, not a database error, which is why it goes undiagnosed.
- Size against the **deploy peak**, not steady state. A rolling deploy holds old and new pools at once; that overlap is what breaches `max_connections`.
- Drain the old client on shutdown. On the termination signal, stop accepting work, await in flight, then close the pool explicitly: the surge window stays as short as the rollout, and in-flight transactions finish instead of being killed. A process killed without draining still releases its sockets on exit; the cost is the killed transactions, not lingering connections.
- Every one-shot container counts for the window it runs in. Schedule migrations and batch jobs away from the deploy window; a one-shot ordered before one role's rollout still overlaps every other role's rollout in the same release.
- Run the equation per database endpoint. A read replica has its own `max_connections` and its own tally of the processes that point at it.
- A per-request or scale-to-zero runtime must not connect directly to the database: live connections track live execution environments, which a concurrency cap bounds and nothing else does. Route through a pooler, or defer the work to a long-running process when the work is a continuous poll rather than request-shaped.
- Declared configuration that no code reads (a pool-size environment variable the client ignores) is a finding: the number in the deployment file is not the number in production.

## Patterns

The failure is almost always in the deploy row, not the steady-state row. Fixes, in order of preference:

1. Cap the surge to a small absolute count (`maxSurge: 1`) instead of a percentage, so the overlap is bounded.
2. Move one-shots out of the deploy window.
3. Drop the per-process pool until the deploy peak fits, accepting more queueing inside each process.

Adding a pooler is the fourth option, not the first; it solves the arithmetic by moving it, and brings its own caveats below.

### Worker Concurrency Against the Pool

```
Bad   worker concurrency 50, pool 10   ->  40 jobs block on connection acquisition
Good  worker concurrency  8, pool 10   ->  2 spare for health checks and non-job paths
```

If a job performs several sequential queries, only one connection is held at a time, so `concurrency + 2 <= pool` holds. If a job fans out queries in parallel, the check is `concurrency x in-flight peak per job + 2 <= pool`. The check applies to threaded workers sharing one pool; in a prefork model each child is its own process with its own pool - count `replicas x children` in the equation and run the check per child, where `C` is the child's thread count (1 for a single-threaded child) and `K` the child count (Celery `--concurrency` under the prefork pool; Sidekiq's `--concurrency` is threads, the threaded model).

### Pooler Tiers

| Tier                       | Effect                                                        | Caveat                                                                                     |
| -------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| None                       | App pools are the real connections                            | The equation above is the whole story                                                      |
| Session-mode pooler        | Behaves like the database; connection held for the session    | No multiplexing benefit under long-lived connections; size app pools as if absent, run the equation once |
| Transaction-mode pooler    | Connection returned per transaction; large multiplexing win   | Breaks session-level `SET`, `LISTEN` (`NOTIFY` is transactional and safe), session advisory locks (`pg_advisory_lock`), SQL-level `PREPARE`, `LOAD`, temporary tables that outlive the transaction (`ON COMMIT DROP` is safe), `WITH HOLD` cursors; protocol-level prepared statements work on PgBouncer 1.21+ (`max_prepared_statements`, default 200 since 1.24, 0 before) |
| Managed proxy (RDS Proxy)  | Multiplexing at transaction boundaries, handled for you       | Session state (session `SET` / `set_config`, temp tables, sequences or views, `LISTEN`, SQL `PREPARE` / `DEALLOCATE` / `EXECUTE`, `DISCARD`, `LOAD` (`auto_explain`), declared cursors, `nextval` / `setval`, session advisory locks) pins the client to one backend until it disconnects - correctness holds, multiplexing is lost; long transactions hold a backend until commit; adds per-round-trip latency; backend connections are capped at `MaxConnectionsPercent` of the target's `max_connections`, client connections not at all |

Under a transaction-mode pooler, transaction-scoped constructs (`SET LOCAL`, `pg_advisory_xact_lock`) stay safe because a transaction stays on one backend connection and the lock is released at commit; session-scoped ones do not. This is the distinction that decides whether transaction mode is usable at all, so check it before choosing the tier. Under RDS Proxy for PostgreSQL, `pg_advisory_xact_lock` does not pin, but AWS lists `SET` commands - with no `SET LOCAL` exemption - among the pinning triggers: the swap keeps correctness, not multiplexing; fixed session settings belong in the proxy's initialization query.

With a transaction-mode pooler or managed proxy in front, per-process pool size becomes a thin local queue and can drop to a very small number; the pooler holds the real connections. The equation then runs twice: the sum of app pools against the pooler's client cap, and the pooler's backend connections against `max_connections`. The client cap is PgBouncer `max_client_conn` (default 100); RDS Proxy has none. PgBouncer's backend count is the sum over its `(user, database)` pools of `pool_size + reserve_pool_size`, each database capped by `max_db_connections` and each user by `max_user_connections` (both default 0, unlimited); RDS Proxy's is `MaxConnectionsPercent x max_connections`. A role that connects directly is added to that backend tally as its own row.

## Output Format

One block per capacity boundary, blank-line separated; each database endpoint (the primary, each read replica) is its own boundary. With tier `none` or `session mode`, an endpoint has one block whose `Boundary` is `max_connections`. With `transaction mode` or `managed proxy`, two blocks: the app-side block is the full template minus `Pooler backend` (`Boundary` = the pooler's client cap, every role that goes through the pooler, `Hazards` carrying the tier check), then the backend block carries only `Boundary` = `max_connections`, `Pooler backend`, role lines for roles that connect directly (`none` otherwise), the three percentage lines, `Verdict`, and `Action`; the heading, `Engine`, `Client audit`, `Surge`, `Pooler tier`, `Config drift`, and `Drain` appear once per assessment, in its first block; a later endpoint whose tier differs carries its own `Pooler tier` and `Hazards`. A proxy the proposal only asks about is a second assessment after the as-written one, headed `## Pool Sizing Assessment (with <proxy>)`. The sizing arithmetic is carried by the role and percentage lines; an incident narrative belongs to the consuming workflow, not this block. Under RDS Proxy the app-side Boundary is `pooler client cap: none (RDS Proxy)`, its percentage lines read `n/a - no client cap`, and its Verdict is `Unbounded` when an `Unbounded` trigger fires, else `Fits`. Every role goes through the pooler unless the proposal or the deployment file routes it directly. Percentages divide by the block's own effective figure: `max_connections` minus reserved, or the client cap with nothing subtracted; the 80% target and the 100% ceiling apply to both. After the last block of each assessment, one `Overall:` line carries that assessment's worse Verdict (rank: `Unbounded` > `Breaches at steady state` > `Breaches at deploy peak` > `Breaches in a one-shot window` > `Over target at steady state` > `Fits`) and the merged Actions, app-side first.

```
## Pool Sizing Assessment

Engine: {PostgreSQL <version> | MySQL <version> | <database> <version> - reserved slots unverified | unknown}{ (assumed: <what>)}

Boundary: {max_connections N (reserved M, effective N-M) | pooler client cap N (effective N) | pooler client cap: none (RDS Proxy)}{ (assumed: <what>)}

Client audit: {one client per process, constructed at startup | constructed per request or job at <file:line>}

API: {replicas R x pool P = T | none}

Workers: {replicas R{ x children K} x pool P = T (concurrency C per process{ x fan-out F}; C{xF} + 2 <= P {holds | fails}; {threaded | prefork}) | none}

Scheduler: {replicas R x pool P = T | none - enqueues to <broker> only}

Per-request runtime: {<name>: cap C x connections per environment N = T | <name>: no cap - unbounded | none}

One-shots: {<name>: pool P during <window>{, overlaps deploy}, ... | none}

Pooler backend: {PgBouncer: sum over (user, database) pools of pool_size + reserve_pool_size = N | RDS Proxy: MaxConnectionsPercent x max_connections = N | n/a - tier none or session mode}

Surge: {Deployment: ceil(R x maxSurge) per role | ECS: floor(R x maximumPercent / 100) - R | StatefulSet: 0 | DaemonSet: maxSurge | blue/green: doubles}; {the processes it adds}{ (assumed: <what>)}

Pooler tier: {none | session mode | transaction mode | managed proxy}{ (assumed)}

Hazards: {none | comma-separated session-scoped constructs the codebase uses that the tier breaks or pins | n/a - tier none or session mode}

Config drift: {none | <declared value> in <file> vs <value the code uses> at <file:line>}

Drain: {pool closed on termination at <file:line or hook> | none - in-flight transactions are killed on rollout | n/a - per-request runtime, or a proposal with no code yet}

Steady state: {U / effective (percent; target <= 80%){, excluding the unbounded entries} | n/a - no client cap}

Deploy peak: {P / effective (percent; must be <= 100%){, excluding the unbounded entries} | n/a - no client cap}

Window peak: {W / effective (percent; must be <= 100%) for <one-shot window> | n/a - no one-shots | n/a - no client cap}

Verdict: {Fits | Over target at steady state | Breaches in a one-shot window | Breaches at deploy peak | Breaches at steady state | Unbounded}{ (assumed)}

Action: {ship as is | cap deploy surge | move one-shots off the deploy window | reduce pool to X | cap the per-process pool at X | cap worker concurrency at X | construct the client at startup | route <runtime> through a pooler | cap <runtime> concurrency at X | defer <work> to a long-running process | replace session-scoped constructs | bypass the pooler for <role> | use session mode | raise the pooler client cap to X | implement the declared pool config | add a drain hook}

Overall: {the worse Verdict across blocks} - {merged Actions}
```

`Verdict` is produced by the percentages: `Breaches at steady state` when steady state exceeds 100%; else `Breaches at deploy peak` when the deploy peak exceeds 100%; else `Breaches in a one-shot window` when a window peak exceeds 100%; else `Over target at steady state` when steady state exceeds 80%; else `Fits`. `Unbounded` replaces all of these when the `Client audit` fails, a per-process pool has no cap, or a `Per-request runtime` has no cap: the percentage lines then carry the bounded entries only, marked `excluding the unbounded entries`. When any input is unknown (a tier the proposal does not state, a missing orchestrator field, `reserved_connections` on an unstated version), state the assumption inline on its line and suffix the verdict `(assumed)`; a sizing assessment with a silent hole is indistinguishable from one that fits. A single-role, single-tier mismatch (API through the proxy, workers direct) is not unknown: it is the two-block shape with the direct roles in the backend block.

`Action` lists the minimal set of remedies, comma-joined, one per violation in the order the template lines appear; `ship as is` is emitted when no other Action is produced, and only alone. A remedy whose value differs per role names the role (`reduce pool to 6 (API), 4 (workers)`); X in `reduce pool to X` is the largest pool at which the failing line meets its limit (100% for a peak, 80% at steady state), solved per role. `Verdict` grades capacity only, so a `Fits` verdict can sit beside a non-empty Action list from the worker check, hazards, config drift, or the drain line. Producing conditions: `cap deploy surge` when the deploy peak breaches and surge is its largest term, `move one-shots off the deploy window` when a one-shot overlaps a breaching deploy, `reduce pool to X` when a percentage still fails after those (a window breach: the one-shot's pool); `raise the pooler client cap to X` when an app-side block breaches and its backend block fits; `cap the per-process pool at X` when a per-process pool has no cap; `cap worker concurrency at X` when the worker check fails; `construct the client at startup` when the client audit fails; a direct-connecting per-request runtime produces `defer <work> to a long-running process` when its work is a continuous poll (a relay, a sweeper) and `route <runtime> through a pooler` when it is request-shaped; an uncapped runtime that already goes through the pooler produces `cap <runtime> concurrency at X`; a `Hazards` entry produces `replace session-scoped constructs` when a transaction-scoped equivalent exists (`pg_advisory_lock` -> `pg_advisory_xact_lock`; `SET` -> `SET LOCAL` under a transaction-mode pooler, the proxy's initialization query under RDS Proxy; SQL `PREPARE` -> protocol-level on PgBouncer 1.21+), `bypass the pooler for <role>` when the construct is inherent to one role (`LISTEN`, a temp table across transactions), and `use session mode` only when most roles need session constructs; `implement the declared pool config` when `Config drift` is not `none`; `add a drain hook` when `Drain` is `none`.

## Avoid

- Raising the acquisition timeout to mask exhaustion; it converts a fast failure into a pile-up
