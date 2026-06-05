---
name: node-connection-pool-sizing
description: Node.js DB pool math - Prisma connection_limit + workers + replicas + rolling deploys vs Postgres max_connections; PgBouncer / RDS Proxy.
metadata:
  category: backend
  tags: [node, typescript, prisma, typeorm, postgres, connection-pool, capacity, pgbouncer]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

Owns the **whole-deployment** pool math. `node-prisma-patterns` / `node-typeorm-patterns` set per-process pool size in one line; this skill makes that line correct in production across replicas, workers, rolling deploys, and the pooler tier.

## When to Use

- Setting `connection_limit` / `extra.max` for the first time
- Scaling out: adding API replicas, BullMQ workers, or read replicas
- Investigating "too many connections", "remaining connection slots", or pool-exhaustion symptoms
- Switching to / from PgBouncer, RDS Proxy, Prisma Accelerate
- Moving any portion of the workload to serverless (Lambda, Cloud Run, Vercel)

## The Capacity Equation

```
sum( per_process_pool_size * process_count )  +  headroom  <=  DB max_connections

where process_count includes:
  - API replicas (singleton DB client per process)
  - BullMQ worker replicas
  - One-shot containers (migrations, cron jobs, scheduled tasks)
  - OLD deployment still draining during rolling deploy
```

Headroom: 15-25% for ad-hoc psql sessions, migrations, monitoring exporters.

The math above assumes **one DB client per process**. NestJS `PrismaService` / `DataSource` is singleton-scoped by default; audit for `new PrismaClient(` / `new DataSource(` outside the bootstrap path - per-request clients silently break every number below.

## Rules

- One DB client per Node process - never construct per-request or per-job
- `connection_limit` (Prisma) / `extra.max` (TypeORM) reflects what **this one process** needs, not what the DB has
- BullMQ worker `concurrency` <= worker process's DB pool size; otherwise jobs wait on DB connections (visible as queue stall, not DB error)
- Rolling deploys briefly hold **old + new** pool simultaneously - size the equation against `2 * replicas` during a deploy, or use pre-stop hooks that drain the old client first
- PgBouncer **transaction mode** breaks Prisma prepared statements; use session mode, or set `pgbouncer=true` in the Prisma URL (disables prepared statements)
- RDS Proxy adds latency (~1-2ms) and a connection cap of its own; check `MaxConnectionsPercent` against the underlying DB
- Serverless (Lambda, Vercel, Cloud Run scale-to-zero): never connect directly to Postgres - use Prisma Accelerate, RDS Proxy, or PgBouncer with transaction-mode-safe settings. Cold start * concurrent invocations >> any reasonable `max_connections`
- Migrations and one-shot containers count toward `max_connections` for their runtime - schedule, don't overlap with peak load

## Patterns

### Worked Example - Mid-Size NestJS Deployment

```
Postgres max_connections     = 100      (managed Postgres default)
Reserved for superuser       = 3        (PG default)
Effective pool               = 97

API replicas                 = 4        Each PrismaClient connection_limit = 10
  -> 4 * 10 = 40

BullMQ worker replicas       = 2        Each PrismaClient connection_limit = 10
  Worker concurrency         = 5        (<= 10, OK)
  -> 2 * 10 = 20

Migration container          = 1        connection_limit = 5
  -> 5 (only during deploys; otherwise 0)

Rolling deploy overlap       = up to 6 extra API replicas briefly
  -> 6 * 10 = 60 PEAK (if old+new fully overlap)

Steady state         40 + 20 + 5  = 65    (within 97, with 32 headroom)
Deploy peak          60 + 60 + 20 = 140   >> 97 - BREACHES
```

Fix options:

1. Drop `connection_limit` to 5 per API process: peak `30 + 30 + 20 = 80`, within budget
2. Pre-stop hook that closes the old `PrismaClient` before the new replicas come up - keeps the math at steady state during deploys
3. Put a pooler (PgBouncer / RDS Proxy) in front; the app connects to the pooler, the pooler holds the DB connections (see below)

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
- Caveats: `LISTEN/NOTIFY`, `SET LOCAL` across statements, advisory locks, and `pg_advisory_xact_lock` work only in session mode

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

Even with module scope, every cold container is a new process and a new pool. Solutions:

1. **Prisma Accelerate** - HTTP-based, no persistent DB connection; works from any number of cold starts
2. **RDS Proxy** - traditional DB protocol, pooler absorbs the bursts
3. **PgBouncer with `pgbouncer=true`** - same idea, self-hosted
4. **Avoid direct Postgres from serverless** - if none of the above is available, queue the work to a long-running worker

## Output Format

```
Postgres max_connections: N (reserved: M, effective: N-M)
API: replicas R_api * connection_limit L_api = T_api
Workers: replicas R_w * connection_limit L_w = T_w (BullMQ concurrency C; check C+2 <= L_w)
One-shots: migrations / cron containers - L_m total during runs
Rolling deploy peak: T_api * (1 + maxSurge/replicas)  + T_w  + L_m
Pooler tier: {none | PgBouncer session | PgBouncer transaction (pgbouncer=true) | RDS Proxy | Prisma Accelerate}
Steady state usage: U / effective (target <= 75%)
Deploy peak usage: P / effective (must stay <= 100%; if not, action: drop L / preStop drain / add pooler)
Action: {ship as is | drop connection_limit to X | add preStop drain | route through pooler | switch serverless to Accelerate}
```

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
