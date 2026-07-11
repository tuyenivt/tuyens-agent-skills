---
name: node-typeorm-patterns
description: TypeORM patterns for NestJS / Express: entities, repository with DataSource, QueryBuilder, transactions, N+1 prevention, migrations, pagination.
metadata:
  category: backend
  tags: [node, typescript, typeorm, orm, database, patterns]
user-invocable: false
---

# TypeORM Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing TypeORM entities, relations, enums, and indexes
- Writing queries that must avoid N+1 or require transactions
- Setting up repositories, QueryBuilder, pagination, or batch operations

## Rules

- `@Index()` on foreign keys and frequently-filtered columns
- Load relations explicitly via `relations` or `leftJoinAndSelect` - never rely on lazy loading
- Always release `QueryRunner` in a `finally` block
- `synchronize: true` is forbidden in production - migrations only
- Map entities to DTOs at the API boundary; never return entities directly
- Enqueue background jobs only after the transaction commits

## Patterns

### Entity Definition

One block shows every convention: UUID PK, enum column, decimal money, indexed FK, bidirectional relation with `cascade`, timestamps.

```typescript
export enum OrderStatus { PENDING = "PENDING", CONFIRMED = "CONFIRMED", CANCELLED = "CANCELLED" }

@Entity()
export class Order {
  @PrimaryGeneratedColumn("uuid") id: string;
  @Column({ type: "enum", enum: OrderStatus, default: OrderStatus.PENDING }) status: OrderStatus;
  @Column({ type: "decimal", precision: 19, scale: 4 }) total: string; // pg returns numeric as string - see Edge Cases

  @ManyToOne(() => Customer, { nullable: false })
  @JoinColumn({ name: "customerId" })
  @Index()
  customer: Customer;
  @Column() customerId: string;

  @OneToMany(() => OrderItem, (i) => i.order, { cascade: ["insert"] })
  items: OrderItem[];

  @CreateDateColumn() createdAt: Date;
  @UpdateDateColumn() updatedAt: Date;
}
```

`OrderItem` mirrors the pattern: `@ManyToOne(() => Order, (o) => o.items)` with `@JoinColumn({ name: "orderId" })` and `@Index()`.

### Repository Pattern

```typescript
@Injectable()
export class OrderRepository {
  constructor(private readonly dataSource: DataSource) {}
  private get repo() { return this.dataSource.getRepository(Order); }

  findWithItems(id: string) {
    return this.repo.findOne({ where: { id }, relations: ["items", "customer"] });
  }
}
```

### QueryBuilder

For complex filtering, joins, and aggregations beyond simple `find` options:

```typescript
async findOrders(filters: OrderFilterDto): Promise<[Order[], number]> {
  const qb = this.repo.createQueryBuilder("order")
    .leftJoinAndSelect("order.items", "item")
    .leftJoinAndSelect("order.customer", "customer");

  if (filters.status) qb.andWhere("order.status = :status", { status: filters.status });
  if (filters.minTotal) qb.andWhere("order.total >= :min", { min: filters.minTotal });
  if (filters.customerId) qb.andWhere("order.customerId = :cid", { cid: filters.customerId });

  return qb.orderBy("order.createdAt", "DESC")
    .skip((filters.page - 1) * filters.pageSize)
    .take(filters.pageSize)
    .getManyAndCount();
}
```

### N+1 Prevention

- `find` options: `{ relations: ["items", "customer"] }`
- QueryBuilder: `.leftJoinAndSelect("order.items", "items")`
- Lazy loading fires a query per access - avoid

### Transactions

Prefer the callback form; commit/rollback is automatic:

```typescript
const order = await this.dataSource.transaction(async (m) => {
  const o = await m.save(m.create(Order, { customerId, status: OrderStatus.PENDING }));
  await m.save(lineItems.map((li) => m.create(OrderItem, { orderId: o.id, ...li })));
  return o;
});
await orderQueue.add("process-order", { orderId: order.id }); // after commit
```

Use `QueryRunner` only when you need manual control (savepoints, conditional commits). The non-negotiable shape:

```typescript
const qr = this.dataSource.createQueryRunner();
await qr.connect(); await qr.startTransaction();
try { /* qr.manager.save(...) */ await qr.commitTransaction(); }
catch (e) { await qr.rollbackTransaction(); throw e; }
finally { await qr.release(); }
```

### Batch Operations

```typescript
await this.repo.save(items, { chunk: 500 }); // bulk insert

await this.repo.createQueryBuilder().update(Order)
  .set({ status: OrderStatus.EXPIRED })
  .where("status = :s AND createdAt < :cutoff", { s: OrderStatus.PENDING, cutoff })
  .execute();
```

Bulk inserts via `createQueryBuilder().insert()` skip `@BeforeInsert`/`@AfterInsert` listeners.

### Pagination

```typescript
findPaginated(page: number, pageSize: number) {
  return this.repo.findAndCount({
    skip: (page - 1) * pageSize, take: pageSize,
    order: { createdAt: "DESC" }, relations: ["items"],
  });
}
```

### Connection Pooling

```typescript
{ type: "postgres", extra: { max: 20, idleTimeoutMillis: 10000 } }
```

### Migrations

See `node-migration-safety` for commands, deploy ordering, and zero-downtime DDL rules.

## Edge Cases

- **QueryRunner transactions**: load relations via `qr.manager.findOne(...)` - the default repository uses a different connection.
- **Decimal columns**: some drivers return strings; parse with `parseFloat` or use `decimal.js` for arithmetic.

## Output Format

```
## TypeORM Design

### Entities
| Entity | Columns | Relations | Indexes |
|--------|---------|-----------|---------|

### Enums
| Enum | Values |
|------|--------|

### Repository Methods
| Method | Query Type | Relations Loaded | Transaction |
|--------|-----------|------------------|-------------|

### Migrations
[Migration file names and what they create]
```

## Avoid

- `synchronize: true` in production (drops columns silently)
- Lazy loading (one query per access)
- Raw SQL for simple CRUD
- Unbounded connection pool
- Leaked `QueryRunner` (missing `finally release()`)
- Enqueuing jobs inside `dataSource.transaction` (fires before commit)
