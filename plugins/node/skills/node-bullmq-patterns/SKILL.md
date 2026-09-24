---
name: node-bullmq-patterns
description: BullMQ background job patterns: idempotency, exponential backoff retry, priority queues, worker lifecycle, scheduled jobs, graceful shutdown.
metadata:
  category: backend
  tags: [node, typescript, bullmq, background-jobs, queues, redis, idempotency]
user-invocable: false
---

# BullMQ Patterns

> Load `Use skill: stack-detect` first. The detected framework picks the form below - NestJS: `@nestjs/bullmq` (`@Processor` / `WorkerHost`); any other framework or unknown: plain `Queue` / `Worker` - and surfaces only in the design block's `Stack:` line.

## When to Use

- Offloading work > 200ms or touching external services (email, webhooks, files)
- Scheduled / recurring jobs (cron-style) and delayed, cancellable one-shots
- Rate-limited external API integrations
- Fan-out: one event triggers multiple independent jobs

## Rules

- Jobs are **idempotent**: BullMQ is at-least-once - stalls, retries, and redelivery re-run a handler that already ran, sometimes concurrently with it. Make the side effect itself idempotent (a unique key, a vendor idempotency key, a terminal-state update guarded on the prior state) and return early only when the work is already done; a read-then-act status check alone lets two concurrent runs both act, and a claim that a failed run leaves behind makes its own retry skip the work
- Job data is JSON: pass IDs and primitives, never ORM entities or large objects. A `Buffer` round-trips to `{ type: "Buffer", data: [...] }` and a `Date` to a string
- Enqueue **after** the DB transaction commits, never inside it. A crash in the gap between `COMMIT` and `add` drops the job silently - when a sweep cannot reconcile that, use the outbox in `node-transaction-patterns`
- Every queue states its retry and retention once, in `defaultJobOptions` on the queue (`registerQueue` / `new Queue`); a per-`add` option overrides it. BullMQ's defaults are bare: `attempts` unset (literally `0`) means one try, then terminal; `removeOnComplete` / `removeOnFail` unset keep every job forever. Redis must run `maxmemory-policy noeviction` (BullMQ breaks when keys are evicted), so retention is the only thing bounding its memory - absent options are missing behaviour, not a style nit
- `attempts` + exponential `backoff` are for **transient** failures. Permanent ones (validation, unknown job name, vendor 4xx) throw `UnrecoverableError` so the job fails immediately instead of burning the budget
- Workers close before the process exits, and the shutdown grace period exceeds the longest job - SIGKILL orphans the lock and the job re-runs. Plain BullMQ: `worker.close()` in a `SIGTERM` handler. NestJS: `@nestjs/bullmq` closes `WorkerHost` workers on application shutdown, which runs on a signal only when `main.ts` (and a standalone `createApplicationContext` worker) calls `app.enableShutdownHooks()`
- A one-shot job whose producer can fire twice gets a stable `jobId`. It dedupes only while the job is retained, so `removeOnComplete` and `removeOnFail` must outlive the duplicate window. Custom ids must not contain `:` (BullMQ rejects them) - use `-`. Recurring jobs dedupe on the job scheduler id instead

## Patterns

### Queue + Enqueue (NestJS)

```typescript
import { InjectQueue } from "@nestjs/bullmq";
import { Queue } from "bullmq";

export const ORDER_QUEUE = "order-processing";
// Module: BullModule.registerQueue({ name: ORDER_QUEUE, defaultJobOptions: {
//   attempts: 3, backoff: { type: "exponential", delay: 2000 },
//   removeOnComplete: { age: 86_400 }, removeOnFail: { age: 7 * 86_400 } } })

@Injectable()
export class OrderService {
  constructor(
    private readonly prisma: PrismaService,
    @InjectQueue(ORDER_QUEUE) private readonly queue: Queue,
  ) {}

  async placeOrder(dto: CreateOrderDto): Promise<string> {
    const orderId = await this.prisma.$transaction(async (tx) =>
      (await tx.order.create({ data: { customerId: dto.customerId, total: dto.total } })).id,
    );
    // after commit; retry and retention come from defaultJobOptions - 24h retention is the dedupe window
    await this.queue.add("process-order", { orderId }, { jobId: `process-order-${orderId}` });
    return orderId;
  }
}
```

### Worker (NestJS Processor)

```typescript
@Processor(ORDER_QUEUE)
export class OrderProcessor extends WorkerHost {
  constructor(private readonly prisma: PrismaService, private readonly fulfillment: FulfillmentService) {
    super();                                        // WorkerHost subclasses call super() before using `this`
  }

  async process(job: Job<{ orderId: string }>): Promise<void> {
    const { orderId } = job.data;
    const order = await this.prisma.order.findUnique({ where: { id: orderId }, select: { status: true } });
    if (!order || order.status === "SHIPPED") return;            // done or gone - nothing to redo
    // The side effect is keyed on the order: a concurrent or repeated run gets the same shipment back
    await this.fulfillment.createShipment(orderId, { idempotencyKey: `ship-${orderId}` });
    // Terminal transition guarded on the prior state - a second run's update matches nothing
    await this.prisma.order.updateMany({ where: { id: orderId, status: "PENDING" }, data: { status: "SHIPPED" } });
  }
}
```

### Multiple Job Types

Route by `job.name` through one queue when the job types share both a latency class and a rate budget; split them into separate queues when either differs (a shared per-key budget stays one Redis bucket across the queues). A job added to a queue whose processor has no case for its name reaches the `default` branch - that is the signal of a producer enqueuing to the wrong queue.

```typescript
async process(job: Job): Promise<void> {
  switch (job.name) {
    case "send-confirmation-email": return this.email.send(job.data.orderId);
    case "charge-payment":          return this.payment.charge(job.data.paymentId);
    default: throw new UnrecoverableError(`Unknown job type: ${job.name}`); // retry cannot fix a bad name
  }
}
```

### Priority via Separate Queues

```typescript
export const QUEUES = { CRITICAL: "critical", DEFAULT: "default", LOW: "bulk" };
await this.criticalQueue.add("charge-payment", { paymentId }, {
  attempts: 5, backoff: { type: "exponential", delay: 1000 },
});
```

Separate queues give critical jobs their own workers, concurrency, and limiter. In one queue, per-job `priority` orders prioritized jobs (1 is highest), but jobs added **without** a priority run before every prioritized one, so each job in the queue must carry one; and long-running low-priority jobs already in flight can still hold every concurrency slot and share the queue's limiter. Use per-job `priority` only when jobs must interleave in a single queue.

### Rate-Limited Upstreams

`limiter` is **per queue**, not per key - one limiter cannot express "2 rps per store". Match the throttle to the upstream's budget:

| Upstream budget | 429 or budget exhausted | Mechanism |
|-----------------|-------------------------|-----------|
| One shared budget (one vendor account) | pause the whole queue | `limiter` + `worker.rateLimit(ms)` then `throw Worker.RateLimitError()` |
| Per key (per store, per tenant, per user token) | defer only that key's job | shared token bucket + `job.moveToDelayed(ts, token)` then `throw new DelayedError()` |

```typescript
import { Worker, DelayedError } from "bullmq";

// Per-key upstream. The handler's 2nd argument is the lock token - moveToDelayed needs it
const worker = new Worker(QUEUE, async (job, token) => {
  // Budget BEFORE the call - checking after it throttles nothing and repeats the side effect
  const wait = await tokenBucket.take(`store:${job.data.storeId}`);  // Redis-backed, shared by every replica
  if (wait > 0) {
    await job.moveToDelayed(Date.now() + wait, token);
    throw new DelayedError();
  }
  const res = await callUpstream(job.data);
  if (res.status === 429) {                        // this key only; other stores keep flowing
    await job.moveToDelayed(Date.now() + (parseRetryAfter(res.headers.get("retry-after")) ?? 60_000), token);
    throw new DelayedError();
  }
}, { connection: redis });
```

The bucket state lives in Redis (an atomic Lua script or `INCR` + `PEXPIRE` per window), never in process memory - every worker replica draws from the same budget. `worker.rateLimit()` pauses the **whole queue**; on a per-key upstream one throttled store stops every store. Give each key its own queue only when the key set is small and fixed.

### Scheduled / Recurring

```typescript
// BullMQ 5.16+ - upsert by scheduler id; re-running on every boot is idempotent, and changing
// the pattern updates in place. The older add({ repeat }) form orphans the previous schedule
// when the pattern changes.
await this.reportQueue.upsertJobScheduler(
  "daily-cleanup",                                  // scheduler id - the dedupe key
  { pattern: "0 2 * * *", tz: "UTC" },
  { name: "daily-cleanup" },
);

// Per-tenant local time: one scheduler per tenant, re-upserted when the tenant's zone changes
for (const t of tenants) {
  await this.digestQueue.upsertJobScheduler(`digest-${t.id}`,
    { pattern: "0 7 * * *", tz: t.timezone }, { name: "daily-digest", data: { tenantId: t.id } });
}
```

Always set `tz`. Without it the next run is computed in the local zone of whichever process computes it - the producer that upserts first, the worker afterwards - so the first fire and the rest can disagree.

### Delayed, Cancellable One-Shot

```typescript
// "Remind 2h after the cart goes idle, unless they order first"
await queue.add("cart-reminder", { cartId }, { delay: 2 * 3_600_000, jobId: `cart-reminder-${cartId}` });

// on order: cancel. remove() returns 0 and removes nothing when the job is already running,
// so the processor re-checks state at run time as well - cancel and run can race
await queue.remove(`cart-reminder-${cartId}`);

// on new activity: push the still-delayed job back in place
const job = await queue.getJob(`cart-reminder-${cartId}`);
if (job && (await job.isDelayed())) await job.changeDelay(2 * 3_600_000);
```

A remove-then-add with the same `jobId` silently deduplicates when the remove found the job running; `changeDelay` re-arms without that race.

### Fan-Out

A handful of independent jobs: add them directly. Thousands: `addBulk` in chunks - one `addBulk` is one Redis `MULTI`, and an unchunked call blocks Redis. Children that must converge on a follow-up step: `FlowProducer` - the parent runs only after every child completes.

```typescript
// bulk - chunk the input
for (const chunk of chunked(rows, 500)) {
  await this.exportQueue.addBulk(chunk.map((r) => ({
    name: "export-chunk",
    data: { exportId, rowId: r.id },
    opts: { jobId: `export-${exportId}-row-${r.id}` },   // scoped to the run, or a later export's row dedupes away
  })));
}

// convergent - one long-lived FlowProducer (NestJS: @InjectFlowProducer), closed on shutdown
await this.flowProducer.add({
  name: "finalize-report", queueName: "reports", data: { reportId },
  children: chunks.map((c) => ({ name: "export-chunk", queueName: "reports", data: c })),
});
```

By default a child that exhausts its attempts leaves the parent in `waiting-children` forever. Set `failParentOnFailure: true` on children to fail the parent, or `ignoreDependencyOnFailure: true` when one bad row must not wedge the flow.

### Graceful Shutdown

```typescript
// Plain BullMQ
process.on("SIGTERM", async () => {
  await worker.close(); // finish in-flight, stop accepting new
  process.exit(0);
});
```

NestJS: call `app.enableShutdownHooks()` after `NestFactory.create` / `createApplicationContext`; `@nestjs/bullmq` then closes every `WorkerHost` worker in the shutdown lifecycle.

### Plain Express

```typescript
import { Queue, Worker } from "bullmq";
export const orderQueue = new Queue("orders", { connection: redis, defaultJobOptions: {
  attempts: 3, backoff: { type: "exponential", delay: 2000 },
  removeOnComplete: { age: 86_400 }, removeOnFail: { age: 7 * 86_400 },
} });
const worker = new Worker("orders", handler, { connection: redis, concurrency: 5 });
worker.on("failed", (job, err) => logger.error({ jobId: job?.id, err }, "failed"));
```

### Testing

Mock the queue token and assert enqueue args:

```typescript
const mockQueue = { add: jest.fn() };
// providers: [{ provide: getQueueToken(ORDER_QUEUE), useValue: mockQueue }]
await service.placeOrder(dto);
expect(mockQueue.add).toHaveBeenCalledWith(
  "process-order",
  { orderId: expect.any(String) },
  expect.objectContaining({ jobId: expect.stringMatching(/^process-order-/) }),
);
```

### Stack Notes

- **Redis**: 6.2+, `maxmemory-policy noeviction`; the Worker's `ioredis` connection needs `maxRetriesPerRequest: null`
- **Monitoring**: Bull Board (`@bull-board/express` or `/nestjs`) behind admin auth

## Edge Cases

- **Stalled jobs**: a worker renews its job lock on a timer (`lockDuration`, default 30s). A blocked event loop or a dropped Redis connection stops renewal; BullMQ declares the job stalled and re-runs it **concurrently with the original** - the idempotent side effect is what makes that safe, not `maxStalledCount` (default 1, after which the job fails with "job stalled more than allowable limit"). CPU-bound handlers need a sandboxed processor or a raised `lockDuration`
- **Long jobs**: chunk anything past ~5 minutes. Long jobs stall more often, and `worker.close()` waits for them, so they set the floor on `terminationGracePeriodSeconds`
- **Large payloads**: > ~50KB belongs in S3; pass only the key as job data
- **Concurrency vs DB pool**: the pool is per **process**, `concurrency` is per Worker - the sum of every Worker's `concurrency` in one process must fit that process's pool (`node-connection-pool-sizing` owns the arithmetic). Exceeding it presents as a queue stall, or as pool-timeout errors (Prisma `P2024`) - never as a database-side error

## Output Format

When authoring, emit this design block plus the queue, worker, and scheduler code it describes; a build over existing code is authoring plus review - findings for the existing defects the change touches, then the block. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file) followed by `Issue:` and `Fix:` lines, `[Must]` first - `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright gets one `Ruling:` line; both precede the findings. After the findings, emit this block as the target state: every row shows the corrected value, and a row the current code violates ends ` - GAP (was: <observed>)`.

```
## BullMQ Design

**Stack:** {NestJS (@nestjs/bullmq) | plain BullMQ} on Redis {version}, maxmemory-policy {noeviction | other - GAP}

### Queues
| Queue | Job Types | Enqueue Point | Dedupe (jobId pattern) | Retry | Non-retryable | Backoff | Rate Limit | Retention (complete / fail) |
|-------|-----------|---------------|------------------------|-------|---------------|---------|------------|-----------------------------|

### Workers
| Worker | Queue | Process | Concurrency (sum per process vs pool) | Idempotency (side-effect key / guarded update) | Max Job / Grace | Stuck Signal |
|--------|-------|---------|---------------------------------------|------------------------------------------------|-----------------|--------------|

### Scheduled and Delayed Jobs
| Job | Scheduler ID or jobId | Schedule or Delay | tz | Purpose |
|-----|-----------------------|-------------------|----|---------|

### Job Data Contracts
| Job Type | Data Fields | Types |
|----------|-------------|-------|
```

Column values: `Enqueue Point` is `after commit` \| `outbox relay` \| `no transaction (scheduler, user event, read-only fan-out)` \| `inside tx - GAP`. `Non-retryable` names what throws `UnrecoverableError` (`validation, unknown name, vendor 4xx`) or `none - GAP`. `Rate Limit` names the budget shape (`queue limiter N/s` \| `per-key bucket <key>` \| `none`). `Stuck Signal` is what pages when the worker stops making progress - the `stalled` event count, failures reading "job stalled more than allowable limit", or a waiting-count / oldest-waiting-age alert.

## Avoid

- Passing ORM entities as job data - serialize IDs and primitives only
- Jobs > 5 min without chunking
- Missing `attempts` - all jobs should handle transient failures
- `removeOnFail: true` when failure visibility is needed
- Skipping worker close on shutdown - causes duplicate processing
- Summed Worker `concurrency` in one process above that process's DB pool
