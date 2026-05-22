---
name: node-prisma-patterns
description: Prisma ORM patterns for NestJS / Express: schema relations, N+1 prevention, transactions, cursor pagination, upsert, PrismaService DI.
metadata:
  category: backend
  tags: [node, typescript, prisma, orm, database, patterns]
user-invocable: false
---

# Prisma Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing Prisma schema models, relations, enums, indexes
- Queries needing N+1 prevention, transactions, or pagination
- PrismaService DI in NestJS / Express
- Batch operations, idempotency, connection pooling

## Rules

- `schema.prisma` is single source of truth
- Every FK and frequently-filtered column needs `@@index`
- Always specify `include` or `select` explicitly
- Use interactive `$transaction(async (tx) => ...)` for multi-step mutations
- Map to DTOs at the API boundary; never return Prisma models

## Patterns

### Schema

Use `@relation` with explicit FKs, enums for known statuses, `@@index` on FK/filter columns, `@@unique` for composite keys, `@default(uuid())` / `cuid()` for PKs.

```prisma
enum OrderStatus { PENDING CONFIRMED SHIPPED DELIVERED CANCELLED }

model Order {
  id             String      @id @default(uuid())
  idempotencyKey String      @unique
  status         OrderStatus @default(PENDING)
  total          Decimal     @db.Decimal(19, 4)
  customerId     String
  customer       Customer    @relation(fields: [customerId], references: [id])
  items          OrderItem[]
  createdAt      DateTime    @default(now())

  @@index([customerId])
  @@index([status, createdAt])
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
```

Use `@db.Decimal(19, 4)` for money; `Decimal` values are objects, not numbers.

### PrismaService (NestJS)

```typescript
@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit {
  constructor() {
    super({ log: process.env.NODE_ENV === "development" ? ["query", "warn", "error"] : ["error"] });
  }
  async onModuleInit() { await this.$connect(); }
}
```

### Idempotent Create + Transaction

```typescript
async createOrder(dto: CreateOrderDto): Promise<Order> {
  const existing = await this.prisma.order.findUnique({ where: { idempotencyKey: dto.idempotencyKey } });
  if (existing) return existing;

  const order = await this.prisma.$transaction(async (tx) => {
    const o = await tx.order.create({ data: { customerId: dto.customerId, idempotencyKey: dto.idempotencyKey, total: dto.total } });
    await tx.orderItem.createMany({ data: dto.items.map((i) => ({ orderId: o.id, ...i })) });
    return o;
  });
  await this.orderQueue.add("process-order", { orderId: order.id }); // AFTER commit
  return order;
}
```

Concurrent calls can still throw P2002 - catch and re-fetch. Default tx timeout is 5s; raise via `$transaction(fn, { timeout: 10000 })`. Batch form `$transaction([op1, op2])` suffices for simple sequential writes.

### N+1 Prevention

```typescript
// Eager load specific relations
const orders = await this.prisma.order.findMany({
  include: {
    items: { include: { product: true } },
    customer: { select: { id: true, name: true, email: true } },
  },
});
```

Fluent API (`order.items()`) fires one query per call - never use in loops.

### Pagination

Cursor for APIs (stable under writes); offset for admin where page numbers matter.

```typescript
// Cursor
await this.prisma.order.findMany({
  take: 20,
  skip: cursor ? 1 : 0,
  cursor: cursor ? { id: cursor } : undefined,
  orderBy: { createdAt: "desc" },
  include: { items: true },
});

// Offset
const [rows, total] = await Promise.all([
  this.prisma.order.findMany({ skip: (page - 1) * size, take: size, orderBy: { createdAt: "desc" } }),
  this.prisma.order.count(),
]);
```

If the cursor record was deleted, results restart from the top - validate or handle gracefully.

### Batch Operations

```typescript
await this.prisma.orderItem.createMany({ data: items, skipDuplicates: true });
await this.prisma.order.updateMany({ where: { status: "PENDING", createdAt: { lt: cutoff } }, data: { status: "EXPIRED" } });
```

### Connection Pooling

- Set `?connection_limit=N` in URL; default `num_cpus * 2 + 1` is often too high
- Serverless: Prisma Accelerate or PgBouncer

### Migrations

See `node-migration-safety` for commands, deploy ordering, zero-downtime rules. Prisma-specific: `prisma db push` is prototyping only - no history, can lose data.

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

- `prisma db push` in production
- Default relation loading - always specify `include`/`select`
- Fluent API in loops (N+1)
- Raw queries for simple CRUD
- Unset `connection_limit` in production
- Enqueuing jobs inside `$transaction` (fires before commit)
