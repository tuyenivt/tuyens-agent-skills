---
name: node-prisma-patterns
description: Prisma ORM patterns for NestJS and Express - schema design with enums and relations, N+1 prevention with include/select, interactive transactions, cursor-based pagination, batch operations, connection pooling, upsert for idempotency, and PrismaService as injectable.
metadata:
  category: backend
  tags: [node, typescript, prisma, orm, database, patterns]
user-invocable: false
---

# Prisma Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing Prisma schema models, relations, enums, and indexes
- Writing queries that must avoid N+1 problems or require transactions
- Setting up PrismaService in NestJS or Prisma in Express
- Implementing pagination, batch operations, idempotency, or connection pooling

## Rules

- `schema.prisma` is single source of truth for the data model
- Every foreign key and frequently-filtered column needs an `@@index`
- Always specify `include` or `select` explicitly - never rely on defaults
- Use interactive transactions (`$transaction` with callback) for multi-step mutations
- Never return Prisma models directly from API endpoints - map to DTOs

## Patterns

### Prisma Schema

- Relations: `@relation` with explicit foreign keys
- Enums for status fields with known values
- `@@index` for FK and filter columns
- `@@unique` for composite unique constraints
- `@default(uuid())` or `@default(cuid())` for primary keys

```prisma
enum OrderStatus {
  PENDING
  CONFIRMED
  SHIPPED
  DELIVERED
  CANCELLED
}

model Order {
  id         String      @id @default(uuid())
  status     OrderStatus @default(PENDING)
  total      Decimal     @db.Decimal(19, 4)
  customerId String
  customer   Customer    @relation(fields: [customerId], references: [id])
  items      OrderItem[]
  createdAt  DateTime    @default(now())
  updatedAt  DateTime    @updatedAt

  @@index([customerId])
  @@index([status])
  @@index([createdAt])
}

model OrderItem {
  id        String  @id @default(uuid())
  orderId   String
  order     Order   @relation(fields: [orderId], references: [id])
  productId String
  quantity  Int
  price     Decimal @db.Decimal(19, 4)

  @@index([orderId])
  @@index([productId])
}

model Payment {
  id             String @id @default(uuid())
  idempotencyKey String @unique
  // ...
}
```

### PrismaService (NestJS)

```typescript
@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit {
  constructor() {
    super({
      log:
        process.env.NODE_ENV === "development"
          ? ["query", "warn", "error"]
          : ["error"],
    });
  }
  async onModuleInit() {
    await this.$connect();
  }
}
```

### Transactions

Use interactive transactions (`$transaction` with callback) for multi-step mutations - this ensures all operations use the same connection and roll back together:

```typescript
const order = await this.prisma.$transaction(async (tx) => {
  const order = await tx.order.create({
    data: { customerId, status: "PENDING", total: calculatedTotal },
  });
  await tx.orderItem.createMany({
    data: items.map((item) => ({ orderId: order.id, ...item })),
  });
  return order;
});
// Enqueue background job AFTER transaction commits
await this.orderQueue.add("process-order", { orderId: order.id });
```

For simple sequential writes, the batch form is sufficient: `$transaction([op1, op2])`.

### Upsert for Idempotency

For operations that must be idempotent (e.g., payment processing, webhook handling), use `upsert` or find-then-create with a unique key:

```typescript
async processPayment(dto: ProcessPaymentDto): Promise<Payment> {
  // Check if already processed (idempotent)
  const existing = await this.prisma.payment.findUnique({
    where: { idempotencyKey: dto.idempotencyKey },
  });
  if (existing) return existing;

  return this.prisma.payment.create({
    data: { idempotencyKey: dto.idempotencyKey, ...dto },
  });
}
```

Note: Concurrent `upsert` calls can still throw P2002 if two processes check simultaneously. Wrap in a retry loop or catch P2002 and re-fetch.

### N+1 Prevention

Always specify exactly which relations to load - never rely on defaults:

```typescript
// Eager load specific relations
const orders = await this.prisma.order.findMany({
  include: {
    items: { include: { product: true } },
    customer: { select: { id: true, name: true, email: true } },
  },
});

// Select only needed fields (lighter response, no entity exposure)
const orderSummaries = await this.prisma.order.findMany({
  select: { id: true, status: true, total: true, createdAt: true },
});
```

- Fluent API (`order.items()`) fires a separate query per call - never use in loops

### Pagination

Use cursor-based pagination for large datasets (stable under concurrent writes) and offset for admin/backoffice where page numbers are needed:

```typescript
// Cursor-based (preferred for APIs)
const orders = await this.prisma.order.findMany({
  take: 20,
  skip: cursor ? 1 : 0,
  cursor: cursor ? { id: cursor } : undefined,
  orderBy: { createdAt: "desc" },
  include: { items: true },
});

// Offset-based (simpler, fine for small datasets)
const [orders, total] = await Promise.all([
  this.prisma.order.findMany({
    skip: (page - 1) * pageSize,
    take: pageSize,
    orderBy: { createdAt: "desc" },
  }),
  this.prisma.order.count(),
]);
```

### Batch Operations

```typescript
// Bulk create
await this.prisma.orderItem.createMany({ data: items, skipDuplicates: true });

// Bulk update
await this.prisma.order.updateMany({
  where: { status: "PENDING", createdAt: { lt: cutoffDate } },
  data: { status: "EXPIRED" },
});

// Bulk delete
await this.prisma.order.deleteMany({ where: { status: "EXPIRED" } });
```

### Connection Pooling

- `connection_limit` in URL: `?connection_limit=10`
- For serverless: use Prisma Accelerate or PgBouncer
- Default pool size is `num_cpus * 2 + 1` - explicitly set for production

### Migrations

- `prisma migrate dev` - development (creates + applies)
- `prisma migrate deploy` - production/CI (applies only, no generation)
- `prisma migrate reset` - for testing only
- `prisma db push` - for prototyping only, never production

## Edge Cases

- **Cursor-based pagination with deleted records**: If the cursor record was deleted between requests, the query returns from the start. Validate that the cursor exists or handle gracefully.
- **Transaction timeout**: Interactive transactions default to 5 seconds. For long-running transactions, set `timeout` in the `$transaction` options: `$transaction(fn, { timeout: 10000 })`.
- **Unique constraint on upsert race condition**: Concurrent `upsert` calls can still throw P2002 if two processes check simultaneously. Wrap upserts in a retry loop or use a database-level advisory lock.
- **Decimal precision**: Use `@db.Decimal(19, 4)` for monetary values in the schema, and handle `Decimal` objects in code (they are not plain numbers).

## Output Format

```
## Prisma Schema Design

### Models
| Model | Key Fields | Relations | Indexes |
|-------|-----------|-----------|---------|

### Enums
| Enum | Values |
|------|--------|

### Queries
| Operation | Method | Include/Select | Transaction |
|-----------|--------|----------------|-------------|

### Pagination Strategy
[Cursor-based or offset-based with rationale]
```

## Avoid

- `prisma db push` in production (no migration history, can lose data)
- Loading all relations by default (specify `include`/`select` explicitly per query)
- Raw queries for simple CRUD (use Prisma Client - it generates optimized SQL)
- Not setting `connection_limit` (defaults may be too high for production)
- Fluent API in loops (fires N+1 queries)
- Returning Prisma models directly from API endpoints (use DTOs to control response shape)
- Enqueuing background jobs inside `$transaction` (job fires before commit)
