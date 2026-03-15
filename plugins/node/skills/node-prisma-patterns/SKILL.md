---
name: node-prisma-patterns
description: "Prisma ORM patterns for NestJS and Express: schema design, migrations, N+1 prevention (include/select), transactions, pagination, batch operations, connection pooling, and PrismaService as injectable."
user-invocable: false
---

Cover:

1. PRISMA SCHEMA:
   - schema.prisma as single source of truth for data model
   - Relations: @relation with explicit foreign keys
   - Enums for status fields
   - @@index for FK and filter columns - every foreign key and frequently-filtered column needs an index
   - @@unique for composite unique constraints

2. PRISMA IN NESTJS:
   - PrismaService extends PrismaClient, implements OnModuleInit
   - Inject PrismaService in repositories/services
   - Enable query logging in development:

```typescript
@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit {
  constructor() {
    super({ log: process.env.NODE_ENV === "development" ? ["query", "warn", "error"] : ["error"] });
  }
  async onModuleInit() {
    await this.$connect();
  }
}
```

3. TRANSACTIONS:

   Use interactive transactions (`$transaction` with callback) for multi-step mutations - this ensures all operations use the same connection and roll back together:

```typescript
await this.prisma.$transaction(async (tx) => {
  const order = await tx.order.create({ data: { customerId, status: "PENDING" } });
  await tx.orderItem.createMany({
    data: items.map((item) => ({ orderId: order.id, ...item })),
  });
  return order;
});
```

   For simple sequential writes, the batch form is sufficient: `$transaction([op1, op2])`.

4. N+1 PREVENTION:

   Always specify exactly which relations to load - never rely on defaults:

```typescript
// Eager load specific relations
const orders = await this.prisma.order.findMany({
  include: {
    items: { include: { product: true } }, // nested eager loading
    customer: { select: { id: true, name: true, email: true } }, // partial fields
  },
});

// Select only needed fields (lighter response, no entity exposure)
const orderSummaries = await this.prisma.order.findMany({
  select: { id: true, status: true, total: true, createdAt: true },
});
```

   - Fluent API (`order.items()`) fires a separate query per call - never use in loops

5. PAGINATION:

   Use cursor-based pagination for large datasets (stable under concurrent writes) and offset for admin/backoffice where page numbers are needed:

```typescript
// Cursor-based (preferred for APIs)
const orders = await this.prisma.order.findMany({
  take: 20,
  skip: cursor ? 1 : 0, // skip the cursor itself
  cursor: cursor ? { id: cursor } : undefined,
  orderBy: { createdAt: "desc" },
});

// Offset-based (simpler, fine for small datasets)
const orders = await this.prisma.order.findMany({
  skip: (page - 1) * pageSize,
  take: pageSize,
});
```

6. BATCH OPERATIONS:

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

7. CONNECTION POOLING:
   - connection_limit in URL: `?connection_limit=10`
   - For serverless: use Prisma Accelerate or PgBouncer
   - Default pool size is `num_cpus * 2 + 1` - explicitly set for production

8. MIGRATIONS:
   - `prisma migrate dev` - development (creates + applies)
   - `prisma migrate deploy` - production/CI (applies only, no generation)
   - `prisma migrate reset` - for testing only
   - `prisma db push` - for prototyping only, never production

9. ANTI-PATTERNS:
   - `prisma db push` in production (no migration history, can lose data)
   - Loading all relations by default (specify include/select explicitly per query)
   - Raw queries for simple CRUD (use Prisma Client - it generates optimized SQL)
   - Not setting connection_limit (defaults may be too high for production)
   - Fluent API in loops (fires N+1 queries)
   - Returning Prisma models directly from API endpoints (use DTOs to control response shape)
