---
name: node-prisma-patterns
description: Prisma ORM patterns for NestJS / Express: schema relations, N+1 prevention, transactions, cursor pagination, upsert, PrismaService DI.
metadata:
  category: backend
  tags: [node, typescript, prisma, orm, database, patterns]
user-invocable: false
---

# Prisma Patterns

> Load `Use skill: stack-detect` first; its `Database` field picks the engine notes below and surfaces in the design block's `**Engine:**` line (the Prisma version comes from `@prisma/client` in `package.json`). The patterns are PostgreSQL's. MySQL, SQL Server, and MongoDB never run `upsert` natively (always the select-then-write fallback); SQLite, SQL Server, and MongoDB do not support `skipDuplicates`; MySQL has no partial indexes (a soft-delete unique is a functional index, 8.0.13+: `CREATE UNIQUE INDEX ... ((CASE WHEN deletedAt IS NULL THEN email END))`) and maps `String` to `VARCHAR(191)` - set `@db.VarChar(255)` / `@db.Text` where values run longer. Prisma 7 adapters: `@prisma/adapter-pg` (PostgreSQL), `@prisma/adapter-mariadb` (MySQL / MariaDB; `new PrismaMariaDb({ host, port, user, password, database, connectionLimit })` - against MySQL 8's default `caching_sha2_password` add `allowPublicKeyRetrieval: true` or `ssl`), `@prisma/adapter-better-sqlite3`.

## When to Use

- Designing Prisma schema models, relations, enums, indexes
- Queries needing N+1 prevention, transactions, or pagination
- PrismaService DI in NestJS, or a client singleton in Express
- Batch operations and idempotent creates

## Rules

- `schema.prisma` is the single source of truth; constructs it cannot express live in hand-written migration SQL (below)
- Every FK and every filtered or sorted column set has an `@@index` matching the query's column order. Tenant-owned models carry the scoping column (`tenantId`) or, when never read without their parent, inherit it through the FK (`inherited via orderId` - the parent's key scopes the unique): it leads every index serving a tenant-scoped query (an index for a global sweep says so in its comment), every `@@unique` includes it (a unique that omits it collides across tenants - `[Must]`; a provider-issued id that is globally unique by contract is `global - <provider> ids are global`), and reads go through `findFirst({ where: { id, tenantId } })` (`node-security-patterns`; an inherited-scope model is read only through its tenant-checked parent). A global model states why it has none
- Read only what you use: `select` the columns needed. `include` only adds relations - it still reads every scalar column of the parent
- Use interactive `$transaction(async (tx) => ...)` for multi-step mutations and return scalars from it. Network I/O never runs inside it; outbox, lock-then-write, atomic guards (`updateMany` with the predicate - a stock check is that guard, run inside the transaction before the row that depends on it), and post-commit dispatch are `node-transaction-patterns`
- Money is `Decimal @db.Decimal(19, 4)` (a `Decimal.js` object in the client) or `Int` / `BigInt` minor units, never `Float`
- Map to DTOs at the API boundary (`const toOrderDto = (o: Pick<Order, "id" | "status" | "total">): OrderDto => ({ id: o.id, status: o.status, total: o.total.toString() })` - `Decimal` leaves as a string); never return Prisma models. Sensitive columns get a model-level `omit`, not call-site discipline
- The NestJS `PrismaService` disconnects in `onModuleDestroy`, which runs on `SIGTERM` only when `main.ts` calls `app.enableShutdownHooks()`
- Pool size, poolers, and serverless are `node-connection-pool-sizing`; migration commands and deploy ordering are `node-migration-safety`

## Patterns

### Schema

Use `@relation` with explicit FKs, enums for known statuses (one value per line), `@@index` on FK/filter columns, `@@unique` for composite keys, `@default(uuid())` / `cuid()` for PKs.

```prisma
enum OrderStatus {
  PENDING
  CONFIRMED
  SHIPPED
  DELIVERED
  CANCELLED
  EXPIRED
}

model Order {
  id             String      @id @default(uuid())
  tenantId       String
  idempotencyKey String
  status         OrderStatus @default(PENDING)
  total          Decimal     @db.Decimal(19, 4)
  customerId     String
  customer       Customer    @relation(fields: [customerId], references: [id])
  items          OrderItem[]
  createdAt      DateTime    @default(now())

  @@unique([tenantId, idempotencyKey])     // keys are per tenant - a global unique leaks across tenants
  @@index([customerId])                    // FK - relation reads and Customer delete checks; customerId is tenant-unique
  @@index([tenantId, status, createdAt])
  @@index([tenantId, createdAt, id])       // serves the keyset list below
  @@index([status, createdAt])             // global maintenance sweep (expiry) - no tenant filter
}

model OrderItem {                          // tenant scope inherited through orderId; never queried without its order
  id        String  @id @default(uuid())
  orderId   String
  order     Order   @relation(fields: [orderId], references: [id])
  productId String
  product   Product @relation(fields: [productId], references: [id])
  quantity  Int
  price     Decimal @db.Decimal(19, 4)

  @@unique([orderId, productId])           // natural key - what makes createMany skipDuplicates meaningful
  @@index([productId])
}
```

`@default(autoincrement())` is `Int` / `BigInt` only - on a `String` id the schema will not generate. A `@@unique` added to a populated table dedupes the rows first (`node-migration-safety`).

### PrismaService (NestJS) and the Express singleton

```typescript
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "../generated/prisma/client";   // Prisma 7: the `prisma-client` generator's `output`; `@prisma/client` under the legacy `prisma-client-js` generator

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  constructor(config: ConfigService) {
    super({
      // Prisma 7 requires a driver adapter (or `accelerateUrl`); the pool is its `max`. Prisma 5-6 take the URL from schema.prisma instead
      adapter: new PrismaPg({ connectionString: config.getOrThrow("DATABASE_URL"), max: 10 }),
      log: process.env.NODE_ENV === "development" ? ["query", "warn", "error"] : ["error"],
    });
  }
  async onModuleInit() { await this.$connect(); }
  async onModuleDestroy() { await this.$disconnect(); }   // needs app.enableShutdownHooks()
}

// Express: one module-scoped client, disconnected in the SIGTERM handler after server.close()
export const prisma = new PrismaClient({ adapter: new PrismaPg({ connectionString: env.DATABASE_URL, max: 10 }) });
```

Prisma 7 keeps no `url` in `schema.prisma`: the CLI (`migrate`, `db`) reads it from `prisma.config.ts`, the client from the adapter. A second database is a second class (`BillingPrismaService`) with its own adapter, generator `output`, and config file, injected by class. `PrismaService extends PrismaClient` cannot be combined with `$extends` (the extension returns a new object, not the subclass) - when you need extensions (soft delete, read replicas), hold an extended client as a field instead of extending the class.

### Idempotent Create + Transaction

The unique key is the claim. Create inside the transaction and let the constraint decide - never look the key up first, which races:

```typescript
async createOrder(dto: CreateOrderDto): Promise<{ orderId: string; replay: boolean; status: OrderStatus }> {
  let orderId: string;
  try {
    orderId = await this.prisma.$transaction(async (tx) => {
      const o = await tx.order.create({ data: {
        tenantId: dto.tenantId, customerId: dto.customerId, idempotencyKey: dto.idempotencyKey, total: dto.total,
        items: { create: dto.items },
      }, select: { id: true } });
      return o.id;                                              // scalar out
    });
  } catch (e) {
    if (!(e instanceof Prisma.PrismaClientKnownRequestError && e.code === "P2002")) throw e;
    const existing = await this.prisma.order.findUniqueOrThrow({
      where: { tenantId_idempotencyKey: { tenantId: dto.tenantId, idempotencyKey: dto.idempotencyKey } },
      select: { id: true, status: true },
    });
    // PENDING: possibly still in flight - the caller answers 409 / 202 and re-enqueues (covers a crash
    // before the winner's enqueue); a settled order is returned as is, never processed again
    if (existing.status === "PENDING") await this.enqueue(existing.id);
    return { orderId: existing.id, replay: true, status: existing.status };
  }
  await this.enqueue(orderId);                                 // AFTER commit
  return { orderId, replay: false, status: "PENDING" };
}

private enqueue(orderId: string) {
  return this.orderQueue.add("process-order", { orderId }, { jobId: `process-order-${orderId}` });   // dedupes
}
```

Post-commit enqueue is at-most-once: a crash between `COMMIT` and `add` drops the job, and a retry of the same request is what re-enqueues it here (the `jobId` makes the second `add` a no-op while the first is retained). When nobody will retry, use the outbox in `node-transaction-patterns`. The default interactive transaction bounds are `maxWait` 2s and `timeout` 5s; raise them per call with `$transaction(fn, { timeout: 10_000 })`. A batch `$transaction([op1, op2])` suffices for independent sequential writes.

On PostgreSQL, CockroachDB, and SQLite, `upsert` is a single native `INSERT ... ON CONFLICT DO UPDATE` when the `where` names one unique field (a compound `@@unique` counts), that value equals the same field in `create`, it touches one model, and there are no nested writes or nested reads. Otherwise Prisma falls back to select-then-insert/update, which can throw `P2002` under concurrency - keep a retry for that path only. On MySQL the native form is raw: `$executeRaw` with `INSERT ... ON DUPLICATE KEY UPDATE units = units + ${units}`.

```typescript
await this.prisma.usageDaily.upsert({
  where:  { subscriptionId_day: { subscriptionId, day } },   // @@unique([subscriptionId, day])
  create: { subscriptionId, day, units },
  update: { units: { increment: units } },                    // atomic, not read-then-write
});
```

### N+1 Prevention

```typescript
const orders = await this.prisma.order.findMany({
  where: { tenantId },
  select: {
    id: true, status: true, total: true,
    items: { select: { quantity: true, product: { select: { id: true, name: true } } } },
    customer: { select: { id: true, name: true } },
  },
});
```

The Fluent API chains off a query - `prisma.order.findUnique({ where: { id } }).items()` - and a sequential `await` loop of them is one query per row. (Calls issued in the same tick are batched by Prisma's dataloader, so `Promise.all(ids.map(...))` over `findUnique` is not N+1.)

A nested `take` is per parent. Without the `relationJoins` preview (or with `relationLoadStrategy: "query"`) each relation level is a separate query and the per-parent `take` is applied after every child row is loaded - bounded output, unbounded read. With the preview enabled, `"join"` is the default and does it in one query: `LATERAL` joins on PostgreSQL, correlated subqueries on MySQL.

Sensitive columns need a model-level guard, not discipline at each call site - one `include: { customer: true }` anywhere re-exposes them:

```typescript
new PrismaClient({ adapter, omit: { customer: { taxId: true } } });   // GA in 6.2.1; 5.16-6.1 need previewFeatures = ["omitApi"]
```

On a version without `omit`, `select` everywhere and a lint rule against bare `include` of that model.

### Soft Delete

A `deletedAt DateTime?` column, a partial unique index so a deleted row does not block re-creation (hand-written SQL, below), and a `deletedAt: null` filter on every read. A client extension (held as a field, not `extends PrismaClient`) intercepts only top-level operations - a relation read through `include` / `select` still needs its own `where: { deletedAt: null }`; a database view or RLS policy covers every path.

### Pagination

Choose on the **requirement**, not the surface: keyset when the result must be stable while rows are written (any infinite scroll, and admin lists over hot tables); offset only when the user picks a page number. The controller caps `size` and the page number before either reaches the query.

```typescript
// Keyset - carry the sort-key VALUES in the cursor, not a row id.
// Prisma's `cursor: { id }` + `skip: 1` resolves the anchor row's sort values by subquery; a deleted
// anchor matches nothing and returns an empty page (looks like the end of the list).
const encodeCursor = (r: { createdAt: Date; id: string }) =>
  Buffer.from(JSON.stringify([r.createdAt.toISOString(), r.id])).toString("base64url");
const decodeCursor = (t: string): { at: Date; id: string } => {
  let v: unknown;
  try { v = JSON.parse(Buffer.from(t, "base64url").toString()); } catch { v = null; }
  const at = Array.isArray(v) ? new Date(v[0]) : new Date(NaN);
  if (!Array.isArray(v) || typeof v[1] !== "string" || Number.isNaN(at.getTime())) {
    throw new BadRequestException("invalid cursor");           // never a silent page one
  }
  return { at, id: v[1] };
};

const c = token ? decodeCursor(token) : null;
const rows = await this.prisma.order.findMany({
  take: size + 1,                                  // +1 probe = hasMore, no count()
  where: { tenantId, ...(c && { OR: [{ createdAt: { lt: c.at } }, { createdAt: c.at, id: { lt: c.id } }] }) },
  orderBy: [{ createdAt: "desc" }, { id: "desc" }], // must end in a unique column, or equal timestamps skip/duplicate rows
  select: { id: true, createdAt: true, status: true, total: true },
});

// Offset - count() scans; cap it (SELECT count(*) FROM (SELECT 1 ... LIMIT 10001) s) and cap the page number;
// pg_class.reltuples estimates only a whole unfiltered table
const [page, total] = await Promise.all([
  this.prisma.order.findMany({ where: { tenantId }, skip: (n - 1) * size, take: size,
    orderBy: [{ createdAt: "desc" }, { id: "desc" }], select: { id: true, status: true } }),
  this.prisma.order.count({ where: { tenantId } }),
]);
```

Add an issued-at element to the tuple if cursors must expire.

### Batch Operations

```typescript
await this.prisma.orderItem.createMany({ data: items, skipDuplicates: true });   // chunk at ~1000 rows
```

`skipDuplicates` drops conflicting rows and returns only `{ count }` of inserted rows, never which were skipped - right for bulk inserts whose replay needs no answer; a create whose replay must answer (an order, an inbound webhook keyed `@@unique([provider, eventId])`) takes the `P2002` path above.

`updateMany` / `deleteMany` run as **one statement in one transaction**: over a large predicate that is a long-held lock and one WAL burst that every replica replays serially - replica lag. Chunk anything past a few thousand rows, and re-assert the predicate inside each chunk so a concurrent writer's row is not clobbered:

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

### Constructs Not Expressible in schema.prisma

Partial and expression indexes, `CREATE INDEX CONCURRENTLY`, table partitioning, check constraints (`CHECK (quantity >= 0)` is the floor under an atomic decrement), and RLS policies: create the migration with `prisma migrate dev --create-only`, hand-edit its `migration.sql`, and keep `schema.prisma` in step where it can describe the result (`@@index(..., map: "<name>")`). A partitioned table's primary key must include the partition key. `node-migration-safety` owns `CONCURRENTLY` and deploy ordering.

## Output Format

When authoring, emit this block plus the `schema.prisma` and query code it describes; a build over existing code is authoring plus review - findings for the existing defects the change touches, then the block. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file) followed by `Issue:` and `Fix:` lines, `[Must]` first - `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright gets one `Ruling:` line; both precede the findings, which cover the causes first and then any other defect in the files read. A defect outside this skill's lens (a spec, a controller, `data: req.body`) goes on one `Out of scope:` line naming the owning skill. After the findings, emit this block as the target state: every row shows the corrected value, and a row the current code violates ends ` - GAP (was: <observed>)` - the finding carries the defect, the row its corrected value. Name any model or enum value referenced but not visible in the input (`<name> - not visible in input` in its row) rather than inventing it. The Models table's Tenant Scope cell is `{scoping column | inherited via <fk> | global - <reason>}`.

```
## Prisma Schema Design

**Engine:** {PostgreSQL | MySQL | SQLite | other | unknown} - Prisma {version from @prisma/client | unknown}

**Lifecycle:** {PrismaService onModuleDestroy + enableShutdownHooks | Express singleton disconnected on SIGTERM | missing - GAP | unknown - entry point not read}

### Models
| Model | Key Fields | Relations | Indexes | Tenant Scope | Omitted (sensitive) |
|-------|-----------|-----------|---------|--------------|---------------------|

### Enums
| Enum | Values |
|------|--------|

### Queries
| Operation | Method | Select/Include | Transaction | Post-Commit Effects |
|-----------|--------|----------------|-------------|---------------------|

### Pagination Strategy
[Keyset or offset, the sort key and its index, and the requirement that decided it]

### Constructs Not Expressible in schema.prisma
[Partial indexes, CONCURRENTLY, partitioning, RLS, soft-delete uniqueness - and the hand-written migration that carries them]
```

## Avoid

- `prisma db push` in production
- Raw queries for simple CRUD
- Looking a unique key up before the create - the constraint is the claim
