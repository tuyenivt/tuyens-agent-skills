---
name: node-bullmq-patterns
description: BullMQ background job patterns: idempotency, exponential backoff retry, priority queues, worker lifecycle, scheduled jobs, graceful shutdown.
metadata:
  category: backend
  tags: [node, typescript, bullmq, background-jobs, queues, redis, idempotency]
user-invocable: false
---

# BullMQ Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Offloading work > 200ms or touching external services (email, webhooks, files)
- Scheduled / recurring jobs (cron-style)
- Rate-limited external API integrations
- Fan-out: one event triggers multiple independent jobs

## Rules

- Jobs are **idempotent**: check state before acting, safe to retry. BullMQ is at-least-once - stalls, retries, and redelivery all re-run a handler that already ran
- Job data is JSON: pass IDs and primitives, never ORM entities or large objects. A `Buffer` round-trips to `{ type: "Buffer", data: [...] }` and a `Date` to a string
- Enqueue **after** the DB transaction commits, never inside it. A crash in the gap between `COMMIT` and `add` drops the job silently - when a sweep cannot reconcile that, use the outbox in `node-transaction-patterns`
- Every queue has a dead-letter strategy (`removeOnFail` count or failed handler). BullMQ's defaults are bare - `attempts: 1` (one try, then terminal) and `removeOnComplete`/`removeOnFail` false (unbounded growth) - so absent options are missing behaviour, not a style nit
- `attempts` + exponential `backoff` are for **transient** failures. Permanent ones (validation, unknown job name, vendor 4xx) throw `UnrecoverableError` so the job fails immediately instead of burning the budget
- Workers close on `SIGTERM` before process exit, and the shutdown grace period exceeds the longest job - SIGKILL orphans the lock and the job re-runs
- Set a stable `jobId` to dedupe: mandatory on repeatable jobs, and on any one-shot job whose producer can fire twice. It dedupes only while the job is retained, so `removeOnComplete` must outlive the duplicate window

## Patterns

### Queue + Enqueue (NestJS)

```typescript
import { InjectQueue } from "@nestjs/bullmq";
import { Queue } from "bullmq";

export const ORDER_QUEUE = "order-processing";
// Module: BullModule.registerQueue({ name: ORDER_QUEUE })

@Injectable()
export class OrderService {
  constructor(@InjectQueue(ORDER_QUEUE) private queue: Queue) {}

  async placeOrder(dto: CreateOrderDto): Promise<Order> {
    const order = await this.prisma.$transaction((tx) =>
      tx.order.create({ data: Order.from(dto) }),
    );
    await this.queue.add(
      "process-order",
      { orderId: order.id },
      {
        attempts: 3,
        backoff: { type: "exponential", delay: 2000 },
        removeOnComplete: 100,
        removeOnFail: 50,
      },
    );
    return order;
  }
}
```

### Worker (NestJS Processor)

```typescript
@Processor(ORDER_QUEUE)
export class OrderProcessor extends WorkerHost {
  async process(job: Job<{ orderId: string }>): Promise<void> {
    const order = await this.orderRepo.findById(job.data.orderId);
    if (!order || order.status === "PROCESSED") return; // idempotent
    await this.fulfillmentService.process(order.id);
  }
}
```

### Multiple Job Types

Route by `job.name` through one queue when the job types share a latency class and a rate budget; split them into separate queues when they do not.

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
export const QUEUES = {
  CRITICAL: "critical", // payments, auth callbacks
  DEFAULT: "default",
  LOW: "bulk", // reports, analytics
};
await this.criticalQueue.add("charge-payment", { paymentId }, {
  attempts: 5, backoff: { type: "exponential", delay: 1000 },
});
```

Separate queues (isolated workers) beat per-job `priority` within one queue - a backlog of low jobs cannot starve critical ones. Use per-job `priority` only when jobs must interleave in a single queue.

### Rate-Limited Upstreams

`limiter` is **per queue**, not per key - one limiter cannot express "2 rps per store".

```typescript
import { Worker, DelayedError, UnrecoverableError } from "bullmq";

// The handler's 2nd argument is the lock token - both escape hatches below need it
const worker = new Worker(QUEUE, async (job, token) => {
  const res = await callUpstream(job.data);

  // Whole-queue pause: honour an upstream Retry-After without spending an attempt
  if (res.status === 429) {
    await worker.rateLimit(parseRetryAfter(res.headers.get("retry-after")));
    throw Worker.RateLimitError();          // static factory - no `new`
  }

  // Per-key budget: defer just this job, leave the queue running for other keys
  const wait = await tokenBucket.take(job.data.storeId);
  if (wait > 0) {
    await job.moveToDelayed(Date.now() + wait, token);
    throw new DelayedError();
  }
}, { connection: redis, limiter: { max: 2, duration: 1_000 } });
```

`worker.rateLimit()` pauses the **whole queue**, so it is wrong when one key is throttled and others are idle. For a per-key budget (per tenant, per store), either give each key its own queue or use the token-bucket + `moveToDelayed` form above.

### Scheduled / Recurring

```typescript
// BullMQ 5.16+ - upsert by scheduler key; re-running on every boot is idempotent,
// and changing the cron updates in place. The older add({ repeat, jobId }) form
// orphans the previous schedule when the pattern changes.
await this.reportQueue.upsertJobScheduler(
  "daily-cleanup",                                  // scheduler id - the dedupe key
  { pattern: "0 2 * * *", tz: "UTC" },              // no tz = the worker's local zone
  { name: "daily-cleanup" },
);
```

### Fan-Out

A handful of independent jobs: add them directly. Thousands: `addBulk`, one round trip per batch. Children that must converge on a follow-up step: `FlowProducer` - the parent runs only after every child completes.

```typescript
// independent
await Promise.all([
  this.orderQueue.add("send-confirmation-email", { orderId }),
  this.paymentQueue.add("charge-payment", { orderId }),
]);

// bulk - chunk the input; one add() per row melts Redis
await this.exportQueue.addBulk(
  rows.map((r) => ({ name: "export-chunk", data: { rowId: r.id }, opts: { jobId: `chunk:${r.id}` } })),
);

// convergent - "email the report once all 50 chunks land"
await new FlowProducer({ connection: redis }).add({
  name: "finalize-report", queueName: "reports", data: { reportId },
  children: chunks.map((c) => ({ name: "export-chunk", queueName: "reports", data: c })),
});
```

A child that exhausts its attempts fails the parent; set `ignoreDependencyOnFailure: true` on children when one bad row must not wedge the flow.

### Graceful Shutdown

```typescript
process.on("SIGTERM", async () => {
  await worker.close(); // finish in-flight, stop accepting new
  process.exit(0);
});
```

### Plain Express

Same primitives without NestJS DI:

```typescript
import { Queue, Worker } from "bullmq";
export const orderQueue = new Queue("orders", { connection: redis });
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
  expect.objectContaining({ attempts: 3 }),
);
```

### Stack Notes

- **Redis**: 6.2+; `ioredis` connection needs `maxRetriesPerRequest: null`
- **Monitoring**: Bull Board (`@bull-board/express` or `/nestjs`) behind admin auth

## Edge Cases

- **Stalled jobs**: a worker renews its job lock on a timer (`lockDuration`, default 30s). A blocked event loop or a dropped Redis connection stops renewal, BullMQ declares the job stalled and re-runs it **concurrently with the original** - idempotency is what makes that safe, not `maxStalledCount` (default 1, after which the job fails). CPU-bound handlers need a sandboxed processor or a raised `lockDuration`
- **Long jobs**: chunk anything past ~5 minutes. Long jobs stall more often, and `worker.close()` waits for them, so they set the floor on `terminationGracePeriodSeconds`
- **Large payloads**: > ~50KB belongs in S3; pass only the key as job data
- **Concurrency vs DB pool**: the pool is per **process**, `concurrency` is per Worker - the sum of every Worker's `concurrency` in one process must fit that process's pool. Exceeding it presents as a queue stall, not a DB error

## Output Format

When authoring, emit this design block. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit this block as the target state and one finding per deviation from it.

```
## BullMQ Design

### Queues
| Queue | Priority | Job Types | Retry | Backoff | Rate Limit | Dead-Letter |
|-------|----------|-----------|-------|---------|------------|-------------|

### Workers
| Worker | Queue | Process | Concurrency | Idempotency Check | Stuck Signal |
|--------|-------|---------|-------------|-------------------|--------------|

### Scheduled Jobs
| Job | Schedule | tz | jobId | Purpose |
|-----|----------|----|-------|---------|

### Job Data Contracts
| Job Type | Data Fields | Types |
|----------|-------------|-------|
```

## Avoid

- Passing ORM entities as job data - serialize IDs and primitives only
- Jobs > 5 min without chunking
- Missing `attempts` - all jobs should handle transient failures
- `removeOnFail: true` when failure visibility is needed
- Skipping `worker.close()` on shutdown - causes duplicate processing
- Worker `concurrency` > DB connection pool size
