---
name: node-connection-pool-sizing
description: Node.js DB pool math - Prisma connection_limit + workers + replicas + rolling deploys vs Postgres max_connections; PgBouncer / RDS Proxy.
metadata:
  category: backend
  tags: [node, typescript, prisma, typeorm, postgres, connection-pool, capacity, pgbouncer]
user-invocable: false
---

> Load `Use skill: stack-detect` first. Its `ORM` field picks the binding below (no `ORM` field: grep `package.json` for the client before choosing); for Prisma, an `@prisma/client` major of 7, any `@prisma/adapter-*` dependency, or a `prisma.config.ts` datasource selects the adapter binding, otherwise the Rust-engine one. The bindings and the pooler section are PostgreSQL's; on MySQL measure with `performance_schema.processlist` (8.0.22+; `information_schema.processlist` below) as a PROCESS-privileged user and skip the pooler caveats. The detection surfaces as the client suffix on the envelope's `Engine:` line.
> Load `Use skill: backend-connection-pooling` first - it owns the capacity equation, headroom, deploy-peak sizing, worker-concurrency rule, pooler tiers, and the Pool Sizing Assessment envelope. This skill owns the Node/ORM bindings and the Prisma-specific pooler caveats.

## When to Use

- Setting `connection_limit` / `extra.max` for the first time
- Scaling out: adding API replicas, BullMQ workers, or read replicas
- Investigating "too many connections", "remaining connection slots", `P2024`, or pool-exhaustion symptoms
- Switching to / from PgBouncer, RDS Proxy, Prisma Accelerate
- Moving any portion of the workload to serverless (Lambda, Cloud Run, Vercel)

## Rules

These are the Node bindings for the core equation:

- NestJS `PrismaService` / `DataSource` is singleton-scoped by default; audit for `new PrismaClient(` / `new DataSource(` outside the bootstrap path, and for `Scope.REQUEST` on the client provider or on anything it injects (request scope bubbles up). A per-request client fails the core `Client audit` and makes the verdict `Unbounded` - it is never sized as a row. `Scope.TRANSIENT` on the client provider builds one client per injecting consumer at bootstrap: bounded, counted as `consumers x pool` per process
- Per-process pool, by client. **Unset is not "small"**, and the defaults differ:
  - Prisma 5-6 (Rust query engine): `connection_limit` in the URL. Unset = `num_physical_cpus * 2 + 1`, counted from the host's **physical** cores, not the container's cgroup quota - a hyperthreaded m6i.8xlarge (32 vCPU, 16 cores) gives 33 to every pod on it. Exhaustion is `P2024` after `pool_timeout` (default 10s)
  - Prisma 6-7 / driver adapters: the pool is the adapter's node-`pg` pool (`new PrismaPg({ connectionString, max })` from adapter-pg 6.6; before 6.6 `new PrismaPg(pool)`, and the caller's `new pg.Pool({ max })` is the pool; default 10, no acquire timeout); a `connection_limit` or `pgbouncer=true` left in the URL is read by nothing - core `Config drift`. The adapter sends unnamed statements unless `statementNameGenerator` (Prisma 7) is set in the `PrismaPg` options, so by default none of the Prisma prepared-statement caveats below apply
  - TypeORM over node-`pg`: `extra.max`, else `poolSize`, else node-`pg`'s 10; `extra` wins when both are set. The default `connectionTimeoutMillis: 0` waits forever, so exhaustion is a hang, not an error. mysql2: `extra.connectionLimit`, else `poolSize`, else 10; it has no acquire timeout at all (`waitForConnections: true` + `queueLimit: 0` wait forever; `connectTimeout` bounds only connection establishment - TCP connect plus the MySQL handshake - and `acquireTimeout` is ignored with a warning, also when TypeORM forwards its own top-level `acquireTimeout`)
  - Sequelize: `pool.max`, default **5** (`acquire` 60s). Knex: `pool: { min: 2, max: 10 }`. Drizzle: whatever pool the caller builds (`pg.Pool` 10, postgres.js `max` 10)
- The worker check is per **process**: sum `concurrency` across every `Worker` sharing one client (threaded). An API process that also hosts Workers adds its request concurrency to the same sum. A BullMQ sandboxed processor (a processor file path or URL; `useWorkerThreads` only makes the children threads instead of processes) runs each job in a child that builds its own client - prefork: `x children K` with K = concurrency, and the per-child check is `1 (x fan-out) + 2 <= P`. PM2 cluster mode and `node:cluster` multiply the process count
- Any `SET` other than `SET LOCAL` - including one inside a committed transaction - persists on the pooled connection for every later borrower; with no pooler at all, and worse behind one in transaction mode. It is a `Hazards` entry under every tier, `none` included
- Transaction-mode pooler and Prisma 5-6 (Rust engine): its named prepared statements work on PgBouncer 1.21+ with `max_prepared_statements > 0` (default 200 since 1.24, 0 on 1.21-1.23). Below 1.21, with it at 0, or on Supavisor's transaction port (6543), set `pgbouncer=true` in the Prisma URL or use session mode. TypeORM over node-`pg` uses unnamed statements and needs no flag - only the session-scoped constructs matter
- RDS Proxy accepts Prisma, but Prisma 5-6 sends every query as a named prepared statement, which pins each client connection to a backend: treat the proxy as a connection cap and failover layer, not a multiplexer - its backend count follows the app pools. For Prisma 7 check `DatabaseConnectionsCurrentlySessionPinned` rather than assume pinning
- Migrations bypass any transaction-mode pooler: Prisma 5-6 `directUrl` in `schema.prisma`, Prisma 7 the `datasource.url` in `prisma.config.ts` pointing at the direct host (Migrate takes a session advisory lock); a direct URL for `typeorm migration:run` (under `migrationsTransactionMode` `none` or `each`, statements outside a transaction - and any session `SET` a migration issues - land on different pooled backends)
- Prisma Accelerate is for serverless where no pooler tier is available; where one exists (RDS Proxy, PgBouncer, the platform's own), prefer it - same effect, one less vendor
- On `SIGTERM`, drain then release: `await worker.close()`, then `server.close()` on Express, then `await prisma.$disconnect()` / `dataSource.destroy()`. NestJS runs none of its shutdown hooks on a signal unless `main.ts` (and a standalone `createApplicationContext` worker) calls `app.enableShutdownHooks()` - without them the process exits on `SIGTERM` undrained (killed transactions). Node as PID 1 with no handler ignores `SIGTERM` entirely: the old pod holds its whole pool until SIGKILL. The Deployment controller does not count terminating pods toward `maxSurge`, so a slow or ignored shutdown adds `terminating pods x pool` on top of the surge - it is appended to the `Surge:` process list (`+ R terminating x pool P until SIGKILL`, R = the old ReplicaSet's pods still inside their grace period - when the drain is ignored, every old pod scaled down within one `terminationGracePeriodSeconds`, all of them when the rollout finishes inside one; `unknown - <signal handler> not read` when the drain code was not in the read set) and counted in `Deploy peak`; an incident the equation cannot reproduce is usually this term

## Patterns

The worked example and fix ordering live in `backend-connection-pooling`; run its equation with the per-process pool above.

### Measure Before Sizing

```sql
SELECT usename, application_name, state, count(*) FROM pg_stat_activity
WHERE backend_type = 'client backend'  -- autovacuum, checkpointer, walwriter hold no client slots
GROUP BY 1, 2, 3 ORDER BY 4 DESC;     -- who holds connections right now
-- MySQL (as a user with PROCESS - either table shows a user without it only its own threads; information_schema.processlist is deprecated, use it below 8.0.22):
--        SELECT user, db, command, count(*) FROM performance_schema.processlist WHERE command <> 'Daemon' GROUP BY 1, 2, 3 ORDER BY 4 DESC;
--        per-process attribution: set `connectAttributes: { program_name: 'orders-api' }` on mysql2 and read performance_schema.session_connect_attrs (needs SELECT on performance_schema; PROCESS does not grant it)
--        SHOW GLOBAL STATUS LIKE 'Max_used_connections';   -- high-water mark since restart
```

Size from measured holders, not from the deployment manifest: a leaked per-request client and a co-tenant application (a BI tool, another service) appear here and in no manifest. A co-tenant's pool goes into the envelope's `Boundary` as reserved (`max_connections 200 (reserved 33: superuser 3 + Metabase 30, effective 167)`). When measured holders exceed the formula, the difference is a leak, a co-tenant, or terminating pods - name which on the line it lands on. A read replica carries its **own** `max_connections` budget - routing reads to it (`@prisma/extension-read-replicas`, a second TypeORM `DataSource`) adds a second pool per process rather than discounting the first.

### Per-ORM Configuration

```bash
# Prisma 5-6 - in the URL
DATABASE_URL="postgresql://u:p@host:5432/db?connection_limit=10&pool_timeout=10"
# pool_timeout: seconds to wait for a pooled connection before P2024 (default 10)
```

```typescript
// TypeORM
new DataSource({
  type: "postgres",
  extra: {
    max: 10,                          // pool size (wins over poolSize)
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 5_000,   // give up acquiring; the default 0 waits forever
  },
});
// type: "mysql" (mysql2): extra: { connectionLimit: 10 } - no acquire timeout exists, and a query `timeout` starts only once a connection is acquired: race the query against a timer in the app, or cap the queue with `extra.queueLimit` (`extra.connectTimeout` is the handshake only)
```

### BullMQ Worker / DB Pool Interaction

```typescript
// Bad - worker can run 50 jobs concurrently; DB pool has 10
new Worker(QUEUE, processor, { concurrency: 50, connection: redis });   // 40 jobs wait on DB
// DATABASE_URL?connection_limit=10

// Good - concurrency + 2 <= pool (2 spare for health checks and non-job paths)
new Worker(QUEUE, processor, { concurrency: 8, connection: redis });
// DATABASE_URL?connection_limit=10
```

Sequential queries and a single `$transaction` hold one connection at a time. A processor that fans queries out in parallel (`Promise.all`) needs `concurrency x in-flight peak + 2 <= pool`.

### Rolling Deploy Overlap

```yaml
# k8s - cap overlap at 1 extra replica; the preStop pause lets the LB stop routing before SIGTERM
spec:
  strategy:
    rollingUpdate:
      maxSurge: 1                   # absolute, not the 25% default
      maxUnavailable: 0
  template:
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - lifecycle:
            preStop:
              sleep: { seconds: 15 }   # native sleep action (k8s 1.30+); an exec sleep needs a `sleep` binary, which distroless images lack
```

ECS: `maximumPercent: 200` starts a full new set before stopping the old - surge equals `desiredCount` per service (`Surge: ECS: floor(R x maximumPercent / 100) - R`). ECS deregisters the target from the ALB and waits out the deregistration delay before sending `SIGTERM`; `stopTimeout` is the grace period.

### PgBouncer (Transaction Mode) and Prisma

```bash
# Prisma 5-6, long-running process: size connection_limit to the process's own concurrency, and check
# the sum of app pools against max_client_conn; pgbouncer=true when PgBouncer is < 1.21 or max_prepared_statements = 0
DATABASE_URL="postgresql://u:p@pgbouncer:6432/db?connection_limit=10&pgbouncer=true"
```

`connection_limit=1` is the Lambda setting (one invocation per environment). In a long-running process it serialises every request through one connection (`P2024` under load) and deadlocks an interactive `$transaction` whose callback queries through the root client instead of `tx`. PgBouncer defaults when a proposal states none: `max_client_conn` 100, `default_pool_size` 20, `reserve_pool_size` 0 - mark them `(assumed)`. Transaction-scoped constructs - `SET LOCAL`, `pg_advisory_xact_lock` inside a transaction - are safe behind the pooler; `LISTEN` (not `NOTIFY`), session `SET`, and `pg_advisory_lock` need session mode or a direct connection.

### RDS Proxy

- Adds ~1-2ms latency per round trip; matters for high-QPS read paths
- `MaxConnectionsPercent` (default 100% of the target's `max_connections`) is the proxy's backend cap
- Pinning: session `SET`, SQL `PREPARE`, temp tables, `LISTEN`, session advisory locks, and every Prisma 5-6 connection pin until disconnect; a long transaction holds its backend until commit, which is not pinning. Watch `DatabaseConnectionsCurrentlySessionPinned` against `DatabaseConnectionsCurrentlyBorrowed`

### Serverless

```typescript
// Bad (Prisma 5-6) - direct URL, no connection_limit: every live environment opens the host-CPU default
const prisma = new PrismaClient();           // module scope, DATABASE_URL -> the database itself

// Good (Prisma 5-6) - same module-scope client (reused across warm invocations), pooler URL, one connection
// DATABASE_URL="postgresql://u:p@pooler:6432/db?connection_limit=1"   (+ pgbouncer=true per the rule above)
// Prisma 7: new PrismaClient({ adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL, max: 1 }) })
```

Each live execution environment holds its own client. Size from **peak concurrent environments**, never from request rate: Lambda reserved concurrency caps them (unset = the regional quota: `Per-request runtime: Lambda: no cap - unbounded`, behind Accelerate too - the cap is the runtime's, not the pooler's); provisioned concurrency is a floor, not reuse. Connections per environment = in-environment concurrency: 1 on Lambda; on Cloud Run (default concurrency 80) or Vercel Fluid, size the per-instance pool to the instance's concurrency and cap max-instances so `instances x pool` fits the pooler's client cap. In preference order:

1. **A pooler in front** - RDS Proxy, PgBouncer, or the platform's own (Supabase Supavisor, Neon pooler); absorbs bursts over the normal protocol. Behind it, cap the runtime's concurrency so the sum still fits the pooler's client cap
2. **Prisma Accelerate** - HTTP-based, no persistent DB connection; the answer when no pooler tier exists
3. **Queue the work** - if neither is available, hand it to a long-running worker

## Output Format

Emit `backend-connection-pooling`'s Pool Sizing Assessment envelope - its block count, lines, `Verdict:` producing rules, and `Action` enum - with these Node bindings. A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright (is scaling to N replicas safe?) gets one `Ruling:` line; both precede the envelope. A what-if replica count, or a proposed change to pool settings or deployment shape (a Lambda, a worker split), is a second assessment headed `## Pool Sizing Assessment (proposed: <what>)` - core's `(with <proxy>)` heading when the proposal is only a proxy - carrying its own `Overall:` line. A CronJob is a `One-shots` entry; a migration `initContainer` is a `One-shots` entry per surging pod.

- The core `Engine:` line carries the client as a suffix: `Engine: {PostgreSQL <version> | MySQL <version> | <database> <version> - reserved slots unverified | unknown} - {Prisma 5-6 (Rust engine) | Prisma 6-7 (adapter) | TypeORM | Sequelize | Knex | Drizzle | pg | mysql2 | unknown}{ (assumed: <what>)}`; no second Engine line
- `API:` / `Workers:` pool figures: a defaulted pool reads `pool P (default: 2 x N physical host cores + 1)`, `(default: node-pg 10)`, `(default: mysql2 10)`, `(default: Knex 10)`, `(default: postgres.js 10)`, or `(default: Sequelize 5)`; when the host core count is not in evidence, say so and suffix the Verdict `(assumed)`. A transient-scoped client reads its pool as `consumers N x pool P' (Scope.TRANSIENT at <file:line>)`. The worker check is the summed `concurrency` of the in-process Workers sharing one client, plus the API's in-flight request peak when the API process hosts them (`C = workers + requests`, `requests (assumed)` when not measured); sandboxed processors use the per-child check
- A client constructed per request or job is `Client audit: constructed per request or job at <file:line>` and the verdict is `Unbounded` - never its own row
- A co-tenant seen in `pg_stat_activity` or the instruction file is reserved in `Boundary`; unmeasured holders are an `(assumed: holders not measured - run pg_stat_activity)` suffix on `Boundary`
- `Pooler tier` uses the core values, product in parentheses: `transaction mode (PgBouncer)`, `managed proxy (RDS Proxy)`, `managed proxy (Prisma Accelerate)`, `transaction mode (Supavisor)`. Prisma 5-6 prepared statements on a transaction-mode pooler without `pgbouncer=true` (per the rule above) are a `Hazards` entry; Prisma 5-6 behind RDS Proxy is a `Hazards` entry `prepared statements pin every connection`, and its `Pooler backend` is `min(sum of app pools, MaxConnectionsPercent x max_connections)` - `MaxConnectionsPercent` must sit below 100 to leave room for reserved slots and direct roles. `Pooler backend` extends to `Prisma Accelerate: project connection limit = N` (`(assumed: limit not stated)` when the dashboard value is not in evidence) and `Supavisor: pool size = N`; under Accelerate the app-side block's `Boundary` is `pooler client cap: none (Prisma Accelerate - HTTP, no client connections)`, its percentage lines `n/a - no client cap`, and its Verdict follows the core RDS Proxy rule
- `Action` uses the core values, Node detail in parentheses (`add a drain hook (app.enableShutdownHooks() in main.ts)`, `construct the client at startup (hoist new PrismaClient() out of <file:line>)`). Node values extend it, each with its producing condition: `route migrations through a direct connection (directUrl / prisma.config.ts)` when a migration runs over a transaction-mode pooler URL; `cap <runtime> concurrency at X` when a per-request runtime behind a pooler has no concurrency cap; `set pgbouncer=true (or max_prepared_statements > 0)` for the prepared-statement hazard; `size app pools as if the proxy were absent` for the RDS Proxy pinning hazard; `lower MaxConnectionsPercent to X` when it is 100 (or leaves no room for the direct roles)

## Avoid

- Setting `connection_limit` to a number that "looks reasonable" without doing the equation
- `maxSurge: 25%` default on rolling deploys without checking that peak fits the DB budget
- Setting `pool_timeout` very high to "fix" pool exhaustion - hides the real shortage and lets requests pile up
- Counting replicas at "average" instead of `replicas + surge` (deploy peak is what breaks production)
