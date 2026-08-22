---
name: node-connection-pool-sizing
description: Node.js DB pool math - Prisma connection_limit + workers + replicas + rolling deploys vs Postgres max_connections; PgBouncer / RDS Proxy.
metadata:
  category: backend
  tags: [node, typescript, prisma, typeorm, postgres, connection-pool, capacity, pgbouncer]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.
> The capacity equation, headroom, deploy-peak sizing, worker-concurrency rule, and pooler-tier trade-offs are owned by `backend-connection-pooling`. Load it first; it supplies the arithmetic and the output contract. This skill owns the Node/ORM bindings and the Prisma-specific pooler caveats.

## When to Use

- Setting `connection_limit` / `extra.max` for the first time
- Scaling out: adding API replicas, BullMQ workers, or read replicas
- Investigating "too many connections", "remaining connection slots", or pool-exhaustion symptoms
- Switching to / from PgBouncer, RDS Proxy, Prisma Accelerate
- Moving any portion of the workload to serverless (Lambda, Cloud Run, Vercel)

## Rules

`backend-connection-pooling` carries the equation and the generic rules. These are the Node-specific bindings:

- NestJS `PrismaService` / `DataSource` is singleton-scoped by default; audit for `new PrismaClient(` / `new DataSource(` outside the bootstrap path - per-request clients silently break every number in the equation and scale with request rate, not replica count
- Per-process pool size is `connection_limit` in the Prisma URL, `extra.max` on a TypeORM `DataSource`. **Unset is not "small"**, and the two defaults differ: Prisma uses `num_physical_cpus * 2 + 1` read from the host rather than the container's cgroup quota, so a 4-vCPU pod on a 32-core node opens ~65; TypeORM over node-`pg` uses a flat `max: 10` with `connectionTimeoutMillis: 0`, which waits forever instead of erroring. Exhaustion surfaces as Prisma `P2024`, and as a hang on node-`pg`
- A standalone `SET` (not `SET LOCAL`, not inside a transaction) contaminates whatever pooled connection ran it for every later borrower - true with no pooler at all, and worse behind one in transaction mode
- BullMQ worker `concurrency` above the worker's pool presents as a **queue stall, not a DB error**, which is why it goes undiagnosed
- PgBouncer **transaction mode** breaks Prisma prepared statements; use session mode, or set `pgbouncer=true` in the Prisma URL to disable them. TypeORM over node-`pg` caches no prepared statements and needs no flag - only the session-scoped constructs below matter
- RDS Proxy is compatible with Prisma without `pgbouncer=true`; it multiplexes internally
- Migrations bypass any transaction-mode pooler: `directUrl` in `schema.prisma`, a direct URL for `typeorm migration:run`. Prisma takes a session-scoped advisory lock that a multiplexed connection breaks; TypeORM takes no lock but still runs long DDL that must not be interrupted mid-statement
- Prisma Accelerate is for serverless where no pooler tier is available; where one exists (RDS Proxy, PgBouncer, the platform's own), prefer it - same effect, one less vendor
- On `SIGTERM`, drain then release: `await worker.close()`, then `server.close()` + `closeIdleConnections()` on Express, then `await prisma.$disconnect()` / `dataSource.destroy()`. NestJS registers no `SIGTERM` handler at all unless `app.enableShutdownHooks()` is called in `main.ts`, and as PID 1 a container without one just ignores the signal - that omission is the usual reason the old pool lingers through the deploy overlap

## Patterns

The worked example and fix ordering live in `backend-connection-pooling`; run its equation with `connection_limit` (or `extra.max`) as the per-process pool.

### Measure Before Sizing

```sql
SELECT usename, application_name, state, count(*) FROM pg_stat_activity
GROUP BY 1, 2, 3 ORDER BY 4 DESC;     -- who holds connections right now
```

Size from measured holders, not from the deployment manifest: a leaked per-request client and a co-tenant application appear here and in no manifest. A read replica carries its **own** `max_connections` budget - routing reads to it (`@prisma/extension-read-replicas`, a second TypeORM `DataSource`) adds a second pool per process rather than discounting the first.

### Per-ORM Configuration

```typescript
// Prisma - connection_limit in the URL
DATABASE_URL="postgresql://u:p@host:5432/db?connection_limit=10&pool_timeout=10"

// pool_timeout: seconds to wait for a connection from the pool before throwing
// Default 10s; lower in latency-sensitive paths so a stalled pool surfaces fast

// TypeORM - DataSource extra
new DataSource({
  type: 'postgres',
  extra: {
    max: 10,                          // pool size
    idleTimeoutMillis: 30_000,        // close idle connections
    connectionTimeoutMillis: 5_000,   // give up acquiring a conn
  },
});
```

### BullMQ Worker / DB Pool Interaction

```typescript
// Bad - worker can run 50 jobs concurrently; DB pool has 10
new Worker(QUEUE, processor, { concurrency: 50, connection: redis });   // 40 jobs wait on DB
// DATABASE_URL?connection_limit=10

// Good - concurrency <= DB pool with headroom for non-DB awaits
new Worker(QUEUE, processor, { concurrency: 8, connection: redis });
// DATABASE_URL?connection_limit=10  (2 spare for non-job paths like health checks)
```

If a processor calls multiple sequential DB queries, `concurrency` * (queries-in-flight peak) must still fit the pool. The simple rule: `concurrency` + 2 <= pool size, per worker process.

### Rolling Deploy Overlap

```yaml
# k8s - cap overlap at 1 extra replica; sleep lets the LB stop sending traffic before SIGTERM
spec:
  strategy:
    rollingUpdate:
      maxSurge: 1                   # absolute, not 25%
      maxUnavailable: 0
  template:
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - lifecycle:
            preStop:
              exec:
                command: ["sh", "-c", "sleep 15"]
```

Application-side: on `SIGTERM`, stop accepting new requests, await in-flight, then `await prisma.$disconnect()` (or `dataSource.destroy()`). Otherwise the old client holds its pool until TCP timeout and the deploy peak doubles.

### PgBouncer (Transaction Mode) and Prisma

```
DATABASE_URL="postgresql://u:p@pgbouncer:6432/db?pgbouncer=true&connection_limit=1"
```

- `pgbouncer=true` disables Prisma's prepared statement caching - required for transaction mode (each statement may land on a different server connection)
- `connection_limit=1` per process is fine - the pooler holds the real connections. The app's pool is now a thin queue
- Caveats: `LISTEN/NOTIFY`, session-level `SET`, and session-scoped advisory locks (`pg_advisory_lock`) need session mode. Transaction-scoped constructs - `SET LOCAL` and `pg_advisory_xact_lock` inside a transaction - are safe: a transaction stays on one server connection

PgBouncer session mode: behaves like a normal Postgres - keep prepared statements on, size pools as in the equation above.

### RDS Proxy

- Adds ~1-2ms latency per round trip; matters for high-QPS read paths
- `MaxConnectionsPercent` (default 100% of cluster max) - check `MaxIdleConnectionsPercent` for tail bursts
- Compatible with Prisma without `pgbouncer=true` (it manages multiplexing internally)
- Pinning: long transactions, `SET`, prepared statements pin the underlying connection - watch `DatabaseConnectionsCurrentlyBorrowed` vs `PinsRequested`

### Serverless

```typescript
// Bad - cold start spawns a new client; under burst, max_connections is overwhelmed
const prisma = new PrismaClient();           // module scope
export const handler = async (e) => prisma.user.findUnique(...);
```

Module scope reuses the client only inside one warm instance; every additional concurrent instance is a new process and a new pool. Platforms that reuse an instance across concurrent invocations (Vercel Fluid, provisioned concurrency) change how many instances exist, not the rule - size from **peak concurrent instances**, never from request rate. In preference order:

1. **A pooler in front** - RDS Proxy, PgBouncer, or the platform's own (Supabase Supavisor, Neon pooler); absorbs bursts over the normal protocol
2. **Prisma Accelerate** - HTTP-based, no persistent DB connection; the answer when no pooler tier exists
3. **Queue the work** - if neither is available, hand it to a long-running worker

## Output Format

Emit `backend-connection-pooling`'s Pool Sizing Assessment envelope - including its `Verdict:` row. Node bindings for its rows:

- Per-process pool = `connection_limit` (Prisma URL) or `extra.max` (TypeORM); when it is unset, state the inferred default and its basis - the host CPU count for Prisma, the flat `10` for node-`pg`. The worker row's concurrency check is BullMQ `concurrency + 2 <= pool`
- A per-request client gets its own row, sized as request rate x idle-reap window (node-`pg` default `idleTimeoutMillis` 10s), not as replica count
- `Action` includes `measure pg_stat_activity first` when the audit has not run; emit it instead of a sizing number rather than guessing
- `Pooler tier` is per row, not per system - components on different tiers each get their own row. Values extend to: {none | PgBouncer session | PgBouncer transaction | RDS Proxy | Prisma Accelerate | other managed pooler (name it)}. For a transaction-mode pooler, state the client-side flag separately - `pgbouncer=true` for Prisma, none for TypeORM - and check the app pools against the pooler's own client cap as well as against `max_connections`
- `Action` values extend to: {set connection_limit to X | drop connection_limit to X | hoist per-request client to bootstrap | add preStop drain | call enableShutdownHooks | pin a session-scoped construct to a dedicated connection | route migrations through directUrl | put a pooler in front of serverless}

## Avoid

- Setting `connection_limit` to a number that "looks reasonable" without doing the equation
- `new PrismaClient()` / `new DataSource(...)` outside the bootstrap path - per-request clients exhaust pools instantly
- BullMQ `concurrency` greater than the worker's DB pool size
- `maxSurge: 25%` default on rolling deploys without checking that peak fits the DB budget
- PgBouncer transaction mode without `pgbouncer=true` (Prisma prepared statements break randomly)
- Serverless functions connecting directly to Postgres without a pooler
- Skipping `await prisma.$disconnect()` on SIGTERM - the old pool lingers through the deploy overlap
- Setting `pool_timeout` very high to "fix" pool exhaustion - hides the real shortage and lets requests pile up
- Counting replicas at "average" instead of `replicas + maxSurge` (deploy peak is what breaks production)
