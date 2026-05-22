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

- Jobs are **idempotent**: check state before acting, safe to retry
- Pass IDs and primitives as job data, never ORM entities or large objects
- Enqueue **after** the DB transaction commits, never inside it
- Every queue has a dead-letter strategy (`removeOnFail` count or failed handler)
- Use `attempts` + exponential `backoff` for transient failures
- Workers close on `SIGTERM` before process exit
- Set a stable `jobId` on repeatable jobs to prevent duplicates on restart

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

Route by `job.name` through one queue:

```typescript
async process(job: Job): Promise<void> {
  switch (job.name) {
    case "send-confirmation-email": return this.email.send(job.data.orderId);
    case "charge-payment":          return this.payment.charge(job.data.paymentId);
    default: throw new Error(`Unknown job type: ${job.name}`);
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
  priority: 1, attempts: 5, backoff: { type: "exponential", delay: 1000 },
});
```

### Scheduled / Recurring

```typescript
await this.reportQueue.add("daily-cleanup", {}, {
  repeat: { pattern: "0 2 * * *" },
  jobId: "daily-cleanup-singleton",
});
```

### Fan-Out

```typescript
await Promise.all([
  this.orderQueue.add("send-confirmation-email", { orderId }),
  this.orderQueue.add("update-inventory", { orderId }),
  this.paymentQueue.add("charge-payment", { orderId }),
]);
```

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

- **NestJS**: `@nestjs/bullmq` - `@Processor` + `WorkerHost` for DI; register via `BullModule.registerQueue`
- **Express**: `bullmq` directly; wire `worker.close()` into app shutdown
- **Redis**: 6.2+; `ioredis` connection needs `maxRetriesPerRequest: null`
- **Monitoring**: Bull Board (`@bull-board/express` or `/nestjs`) behind admin auth

## Edge Cases

- **Stalled jobs after Redis reconnect**: workers auto-reconnect; in-flight jobs may retry - idempotency check handles it
- **Large payloads**: > ~50KB belongs in S3; pass only the key as job data
- **Concurrency vs DB pool**: `concurrency` higher than pool size blocks workers on connections - match them

## Output Format

```
## BullMQ Design

### Queues
| Queue | Priority | Job Types | Retry | Backoff |
|-------|----------|-----------|-------|---------|

### Workers
| Worker | Queue | Concurrency | Idempotency Check |
|--------|-------|-------------|-------------------|

### Scheduled Jobs
| Job | Schedule | jobId | Purpose |
|-----|----------|-------|---------|

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
