---
name: node-bullmq-patterns
description: BullMQ background job patterns for Node.js/TypeScript - job design, idempotency, retry with exponential backoff, queue routing by priority, worker lifecycle, scheduled jobs, and graceful shutdown.
metadata:
  category: backend
  tags: [node, typescript, bullmq, background-jobs, queues, redis, idempotency]
user-invocable: false
---

# BullMQ Patterns

## When to Use

- Offloading work that takes > 200ms or touches external services (email, webhooks, file processing)
- Scheduled or recurring tasks (cron-style jobs)
- Rate-limited integrations with external APIs
- Fan-out processing: one event triggers multiple independent jobs

## Rules

- Jobs must be **idempotent** - check state before acting, safe to retry
- Pass IDs and primitive values as job data - never pass ORM entities or large objects
- Every queue must have a **dead-letter** strategy (`removeOnFail` or a failed job handler)
- Use `attempts` + exponential `backoff` for transient failures
- Workers must handle `SIGTERM` gracefully - close the worker before process exit
- Enqueue jobs AFTER the database transaction commits - never inside it

## Patterns

### Queue and Worker Setup (NestJS)

```typescript
// queues/order.queue.ts
import { InjectQueue } from "@nestjs/bullmq";
import { Queue } from "bullmq";

export const ORDER_QUEUE = "order-processing";

// Module registration
BullModule.registerQueue({ name: ORDER_QUEUE });

// Inject and enqueue
@Injectable()
export class OrderService {
  constructor(@InjectQueue(ORDER_QUEUE) private orderQueue: Queue) {}

  async placeOrder(dto: CreateOrderDto): Promise<Order> {
    const order = await this.orderRepo.save(Order.from(dto));
    await this.orderQueue.add(
      "process-order",
      { orderId: order.id }, // only IDs, no entity objects
      {
        attempts: 3,
        backoff: { type: "exponential", delay: 2000 },
        removeOnComplete: 100, // keep last 100 completed
        removeOnFail: 50,
      },
    );
    return order;
  }
}
```

### Worker (NestJS Processor)

```typescript
import { Processor, WorkerHost } from "@nestjs/bullmq";
import { Job } from "bullmq";

@Processor(ORDER_QUEUE)
export class OrderProcessor extends WorkerHost {
  async process(job: Job<{ orderId: string }>): Promise<void> {
    const { orderId } = job.data;

    // Idempotency check
    const order = await this.orderRepo.findById(orderId);
    if (!order || order.status === "processed") return;

    await this.fulfillmentService.process(orderId);
  }
}
```

### Queue Routing by Priority

```typescript
// Separate queues per priority
export const QUEUES = {
  CRITICAL: "critical", // payments, auth callbacks
  DEFAULT: "default", // standard business logic
  LOW: "bulk", // reports, analytics, cleanup
};

// Enqueue to specific queue
await this.criticalQueue.add(
  "charge-payment",
  { paymentId },
  {
    priority: 1, // lower number = higher priority within a queue
    attempts: 5,
    backoff: { type: "exponential", delay: 1000 },
  },
);
```

### Scheduled / Recurring Jobs

```typescript
// Register once at startup
await this.reportQueue.add(
  "daily-report",
  {},
  {
    repeat: { pattern: "0 8 * * *" }, // cron: every day at 08:00
    jobId: "daily-report-singleton", // prevents duplicates on restart
  },
);
```

### Graceful Shutdown

```typescript
// main.ts / app bootstrap
const worker = new Worker(ORDER_QUEUE, processor, { connection });

process.on("SIGTERM", async () => {
  await worker.close(); // finish in-progress job, stop accepting new ones
  process.exit(0);
});
```

### Plain Express Setup

```typescript
import { Worker, Queue } from "bullmq";
import { redis } from "./config/redis";

export const orderQueue = new Queue("orders", { connection: redis });

const worker = new Worker(
  "orders",
  async (job) => {
    if (job.name === "process-order") {
      await processOrder(job.data.orderId);
    }
  },
  {
    connection: redis,
    concurrency: 5,
  },
);

worker.on("failed", (job, err) => {
  logger.error({ jobId: job?.id, err }, "Job failed");
});
```

### Stack-Specific Guidance

- **NestJS**: Use `@nestjs/bullmq` - `@Processor` + `WorkerHost` integrates with NestJS DI; register queues in `BullModule.registerQueue`
- **Express**: Use `bullmq` directly - create `Queue` and `Worker` instances; wire into app lifecycle for graceful shutdown
- **Redis**: BullMQ requires Redis 6.2+; use `ioredis` connection with `maxRetriesPerRequest: null` (required by BullMQ)
- **Monitoring**: Use Bull Board (`@bull-board/express` or `@bull-board/nestjs`) for a web UI; expose `/queues` behind admin auth only

## Edge Cases

- **Job enqueued inside a transaction that rolls back**: The job fires but the database row it references does not exist. Always enqueue after the transaction commits.
- **Duplicate recurring jobs on restart**: Without a stable `jobId`, each app restart creates a new recurring job. Always set `jobId` on repeatable jobs to prevent duplicates.
- **Redis connection lost mid-processing**: BullMQ workers auto-reconnect, but in-progress jobs may be marked as stalled and retried. Ensure idempotency handles this - check state before acting.
- **Job data too large**: Redis is not designed for large payloads. If job data exceeds ~50KB, store the payload in S3/object storage and pass only the reference key as job data.

## Avoid

- Passing Prisma/TypeORM entities as job data - serialize only IDs and primitives
- Jobs > 5 minutes without chunking into smaller units
- Missing `attempts` configuration - all jobs should handle transient failures
- `removeOnFail: true` if you need failure visibility - keep some failed jobs for debugging
- Not calling `worker.close()` on shutdown - in-progress jobs get abandoned and requeued, causing duplicate processing
