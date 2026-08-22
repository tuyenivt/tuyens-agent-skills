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
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  constructor() {
    super({ log: process.env.NODE_ENV === "development" ? ["query", "warn", "error"] : ["error"] });
  }
  async onModuleInit() { await this.$connect(); }
  async onModuleDestroy() { await this.$disconnect(); } // drain pool on shutdown
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

Concurrent calls can still throw P2002 - catch and re-fetch, and on that path **skip the post-commit side effects**: the winning caller already enqueued them. Default tx timeout is 5s; raise via `$transaction(fn, { timeout: 10000 })`. Batch form `$transaction([op1, op2])` suffices for simple sequential writes.

`upsert` handles the read-modify-write in one statement when the conflict target is a real unique constraint - use it for counters and rollups instead of find-then-create:

```typescript
await this.prisma.usageDaily.upsert({
  where:  { subscriptionId_day: { subscriptionId, day } },   // must be @@unique
  create: { subscriptionId, day, units },
  update: { units: { increment: units } },                    // atomic, not read-then-write
});
```

`upsert` still races on a missing constraint (it becomes find-then-create under the hood) and can throw P2002 under concurrency - keep the catch.

### N+1 Prevention

```typescript
// Eager load specific relations
const orders = await this.prisma.order.findMany({
  include: {
    items: { include: { product: true } },
    customer: { select: { id: true, name: true, email: true } },
    events: { take: 1, orderBy: { at: "desc" } },   // latest child PER parent, one query
  },
});
```

Fluent API (`order.items()`) fires one query per call - never use in loops. A nested `take` is per-parent (Prisma emits a window function), not a global top-N.

Sensitive columns need a model-level guard, not discipline at each call site - one `include: { author: true }` anywhere re-exposes them:

```typescript
new PrismaClient({ omit: { user: { passwordHash: true, bio: true } } });   // Prisma 5.16+
```

`PrismaService extends PrismaClient` cannot be combined with `$extends` (the extension returns a new object, not the subclass) - when you need extensions, wrap a client as a field instead of extending it.

### Pagination

Choose on the **requirement**, not the surface: keyset when the result must be stable while rows are written (any infinite scroll, and admin lists over hot tables); offset only when the user picks a page number.

```typescript
// Keyset - carry the sort-key VALUES in the cursor, not a row id.
// Prisma's `cursor: { id }` + `skip: 1` re-reads the anchor row, so a deleted anchor
// silently restarts from page one; encoded values have no anchor to lose.
const { at, id } = decodeCursor(token);            // base64url of the last row's sort key
await this.prisma.order.findMany({
  take: size + 1,                                  // +1 probe = hasMore, no count()
  where: at ? { OR: [{ createdAt: { lt: at } }, { createdAt: at, id: { lt: id } }] } : {},
  orderBy: [{ createdAt: "desc" }, { id: "desc" }], // must end in a unique column, or equal timestamps skip/duplicate rows
});

// Offset - count() scans; over ~1M rows use a reltuples estimate and cap the page number
const [rows, total] = await Promise.all([
  this.prisma.order.findMany({ skip: (page - 1) * size, take: size, orderBy: [{ createdAt: "desc" }, { id: "desc" }] }),
  this.prisma.order.count(),
]);
```

A malformed or expired cursor is a 400, never a silent page one.

### Batch Operations

```typescript
await this.prisma.orderItem.createMany({ data: items, skipDuplicates: true });   // chunk at ~1000 rows
```

`updateMany` / `deleteMany` run as **one statement in one transaction**: over a large predicate that is a long-held lock and a bloated WAL. Chunk anything past a few thousand rows, and re-assert the predicate inside each chunk so a concurrent writer's row is not clobbered:

```typescript
for (;;) {
  const ids = (await this.prisma.order.findMany({
    where: { status: "PENDING", createdAt: { lt: cutoff } }, select: { id: true }, take: 1_000,
  })).map((o) => o.id);
  if (ids.length === 0) break;
  await this.prisma.order.updateMany({
    where: { id: { in: ids }, status: "PENDING" },      // re-assert - the row may have moved on
    data: { status: "EXPIRED" },
  });
}
```

### Connection Pooling

- Set `?connection_limit=N` in URL; default `num_cpus * 2 + 1` is often too high
- Serverless: Prisma Accelerate or PgBouncer

### Migrations

See `node-migration-safety` for commands, deploy ordering, zero-downtime rules. Prisma-specific: `prisma db push` is prototyping only - no history, can lose data.

## Output Format

When authoring, emit this block plus the `schema.prisma` and query code it describes. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit this block as the target state and one finding per deviation from it. Name any model referenced but not visible in the input rather than inventing its shape.

```
## Prisma Schema Design

### Models
| Model | Key Fields | Relations | Indexes | Tenant Scope {scoping column \| global - reason} |
|-------|-----------|-----------|---------|--------------------------------------------------|

### Enums
| Enum | Values |
|------|--------|

### Queries
| Operation | Method | Include/Select | Transaction | Post-Commit Effects |
|-----------|--------|----------------|-------------|---------------------|

### Pagination Strategy
[Keyset or offset, the sort key, and the requirement that decided it]

### Constructs Not Expressible in schema.prisma
[Partial indexes, CONCURRENTLY, partitioning, RLS - and the hand-written migration that carries them]
```

## Avoid

- `prisma db push` in production
- Implicit full-row reads on wide/hot tables - be explicit with `select`; relations load only via explicit `include`
- Fluent API in loops (N+1)
- Raw queries for simple CRUD
- Unset `connection_limit` in production
- Enqueuing jobs inside `$transaction` (fires before commit)
- Unbounded `updateMany` / `deleteMany` over a large predicate - one statement, one lock, one transaction
- `Float` for money, and `@default(autoincrement())` on a `String` id (it is `Int`/`BigInt` only - the schema will not generate)
