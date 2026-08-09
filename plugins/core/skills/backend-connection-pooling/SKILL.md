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
- Investigating "too many connections", "remaining connection slots", or requests timing out while acquiring a connection
- Introducing or removing a pooler (PgBouncer, RDS Proxy, or an equivalent)
- Moving any part of the workload to a scale-to-zero or per-request runtime

## The Capacity Equation

```
sum( per_process_pool_size * process_count )  +  headroom  <=  DB max_connections

process_count includes:
  - API replicas
  - Background worker replicas
  - One-shot containers (migrations, cron, scheduled tasks) while they run
  - The OLD deployment still draining during a rolling deploy
```

Headroom is 15-25%, reserved for ad-hoc sessions, migrations, and monitoring exporters. The equation assumes **one database client per process**; a client constructed per request or per job invalidates every number in it, so audit for construction outside the startup path first.

## Rules

- One database client per process, created at startup, never per request or per job.
- Per-process pool size expresses what that one process needs concurrently, not what the database can offer.
- Worker concurrency must not exceed the worker process's pool size. Exceeding it presents as a queue stall, not a database error, which is why it goes undiagnosed.
- Size against the **deploy peak**, not steady state. A rolling deploy holds old and new pools at once; that overlap is what breaches `max_connections`.
- Drain the old client on shutdown. On the termination signal, stop accepting work, await in flight, then close the pool explicitly, or the old connections linger until TCP timeout and the deploy peak doubles.
- Every one-shot container counts for its runtime. Schedule migrations and batch jobs away from peak.
- Run the equation per database endpoint. A read replica has its own `max_connections` and its own tally of the processes that point at it.
- A per-request or scale-to-zero runtime must not connect directly to the database. Cold starts multiplied by concurrent invocations exceed any reasonable `max_connections`; route through a pooler or defer the work to a long-running process.

## Patterns

### Worked Example

The failure is almost always in the deploy row, not the steady-state row.

```
max_connections              = 100
Reserved for superuser       = 3
Effective                    = 97

API replicas          4  x pool 10  =  40
Worker replicas       2  x pool 10  =  20    (worker concurrency 5, fits)
Migration container   1  x pool  5  =   5    (only during deploys)

Steady state    40 + 20 + 5  =  65   of 97, 32 spare        OK
Deploy peak     80 + 40 + 5  = 125   of 97                  BREACHES
                (old 4 + new 4 API, old 2 + new 2 workers)
```

Three fixes, in order of preference:

1. Cap deploy surge to one extra replica instead of a percentage, so the overlap is bounded and small.
2. Drain the old client before the new replicas come up, keeping the deploy at steady-state usage.
3. Drop the per-process pool until the deploy peak fits, accepting more queueing inside each process.

Adding a pooler is the fourth option, not the first; it solves the arithmetic by moving it, and brings its own caveats below.

### Worker Concurrency Against the Pool

```
Bad   worker concurrency 50, pool 10   ->  40 jobs block on connection acquisition
Good  worker concurrency  8, pool 10   ->  2 spare for health checks and non-job paths
```

If a job performs several sequential queries, only one connection is held at a time, so `concurrency + 2 <= pool size` holds. If a job fans out queries in parallel, multiply concurrency by the in-flight peak per job before comparing. This check applies to threaded workers sharing one pool; in a prefork model each child is its own process holding one connection - count children as processes in the equation and skip the check.

### Pooler Tiers

| Tier                       | Effect                                                        | Caveat                                                                                     |
| -------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| None                       | App pools are the real connections                            | The equation above is the whole story                                                      |
| Session-mode pooler        | Behaves like the database; connection held for the session    | No multiplexing benefit under long-lived connections; size as if absent                    |
| Transaction-mode pooler    | Connection returned per transaction; large multiplexing win   | Breaks prepared-statement caching, session-level `SET`, `LISTEN/NOTIFY`, and session-scoped advisory locks |
| Managed proxy              | Multiplexing handled for you                                  | Adds per-round-trip latency and imposes its own connection cap; long transactions and session state pin connections |

Under a transaction-mode pooler, transaction-scoped constructs stay safe because a transaction stays on one backend connection. Session-scoped ones do not. This is the distinction that decides whether transaction mode is usable at all, so check it before choosing the tier rather than after the first mysterious failure.

With any pooler in front, per-process pool size becomes a thin local queue and can drop to a very small number; the pooler holds the real connections. The equation then runs twice: the pooler's backend pool against `max_connections`, and the sum of app pools against the pooler's client cap.

## Output Format

```
## Pool Sizing Assessment

max_connections: N (reserved M, effective N-M)
API: replicas R x pool P = T
Workers: replicas R x pool P = T (concurrency C; check C + 2 <= P)
One-shots: total during runs
Deploy peak: {computed value} (old + new overlap)
Pooler tier: {none | session mode | transaction mode | managed proxy}
Steady state: U / effective ({percent}; target <= 75%)
Deploy peak: P / effective ({percent}; must be <= 100%)
Verdict: {Fits | Breaches at deploy peak | Breaches at steady state}
Action: {ship as is | cap deploy surge | drain old client on shutdown | reduce pool to X | route through pooler | defer work off a per-request runtime}
```

When any input is unknown, state the assumption inline and mark the verdict `Fits (assumed)` rather than omitting the row. A sizing assessment with a silent hole is indistinguishable from one that fits.

## Avoid

- Choosing a pool size that "looks reasonable" without running the equation
- Counting replicas at steady state when the deploy peak is what breaks production
- Worker concurrency above the worker's pool size
- Raising the acquisition timeout to mask exhaustion; it converts a fast failure into a pile-up
- Adding a pooler to avoid doing the arithmetic; the arithmetic moves, it does not disappear
