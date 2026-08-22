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

A nested `startTransaction()` on the same runner emits a `SAVEPOINT`: catching the inner failure and calling `rollbackTransaction()` returns to the savepoint and lets the outer transaction commit. Use it only when a non-critical side write (audit row, denormalised view) must not lose the main write - and do not rethrow from the inner catch, or the outer rolls back anyway.

### Batch Operations

```typescript
await this.repo.save(items, { chunk: 500 }); // bulk insert

await this.repo.createQueryBuilder().update(Order)
  .set({ status: OrderStatus.EXPIRED })
  .where("status = :s AND createdAt < :cutoff", { s: OrderStatus.PENDING, cutoff })
  .execute();
```

`createQueryBuilder().insert()` / `.update()` skip **all** entity listeners and subscribers - `@BeforeInsert`, `@BeforeUpdate`, and `@UpdateDateColumn` alike. When a listener must run, use `save()` and build rows with `manager.create(Entity, {...})`: listeners are methods on the entity instance, so a plain object literal passed to `save()` silently skips them too. `save({ chunk, reload: false, transaction: false })` cuts the per-entity round trips; keep chunks under the 65,535 bind-parameter cap.

### Pagination With a Collection Join

Paginating while joining a `@OneToMany` is the most common TypeORM performance bug, and the naive form is silently wrong:

```typescript
// Bad - `limit`/`offset` page the joined CARTESIAN rows, so a page holds < pageSize orders
qb.leftJoinAndSelect("order.items", "item").limit(50);

// Bad - `skip`/`take` is correct-by-default but wraps the query in a DISTINCT subquery over
// the root ids; sorting by a joined or computed column then emits one row per item and the
// page comes back short. getManyAndCount() counts DISTINCT ids, so the total looks right.
qb.leftJoinAndSelect("order.items", "item").orderBy("item.price", "DESC").skip(0).take(50);

// Good - two phases: page the roots with no collection join, then hydrate those ids unbounded
const ids = (await this.repo.createQueryBuilder("order")
  .select("order.id", "id").where(...)
  .orderBy("order.createdAt", "DESC").addOrderBy("order.id", "DESC")   // unique tiebreaker, or pages overlap
  .limit(50).offset(off).getRawMany<{ id: string }>()).map(r => r.id);

const rows = await this.repo.find({ where: { id: In(ids) }, relations: ["items"] });
// `In()` does not preserve order - restore phase 1's ordering explicitly
const byId = new Map(rows.map(r => [r.id, r]));
const page = ids.map(id => byId.get(id)!);
```

`relationLoadStrategy: "query"` (TypeORM 0.3, per-query or per-DataSource) loads relations as separate queries instead of one join - it removes the cartesian blow-up and the DISTINCT wrapper entirely, at the cost of one extra round trip per relation. Prefer it over hand-rolling two phases unless the collection must appear in the `WHERE` or the `ORDER BY`.

Aggregates: `getManyAndCount()` does not survive `GROUP BY` - its count query counts grouped rows. Run an explicit `COUNT(*)` over the filtered subquery instead. `orderBy()` is not parameterised, so a user-selectable sort column must come from a fixed whitelist map.

Streaming a large export: `qb.stream()` on a dedicated `QueryRunner`, ordered by a stable key - never `OFFSET` paging over hundreds of thousands of rows.

### Connection Pooling

```typescript
{ type: "postgres", extra: { max: 20, idleTimeoutMillis: 10000 } }
```

### Migrations

See `node-migration-safety` for commands, deploy ordering, and zero-downtime DDL rules.

## Edge Cases

- **QueryRunner transactions**: load relations via `qr.manager.findOne(...)` - the default repository uses a different connection, so it sees pre-transaction state and takes no lock.
- **Decimal columns**: `pg` returns `numeric` as a **string**, and `COUNT`/`SUM` come back as strings too. Never `parseFloat` a money value - it is the float error the `decimal` column exists to prevent. Aggregate in SQL, and use `decimal.js` (or a `ValueTransformer`) at the boundary; transformers do not apply to bound parameters, so serialise those yourself.

## Output Format

When authoring, emit this block plus the entity and query code it describes. When reviewing or diagnosing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit one finding per deviation and use the tables below for the corrected target state. Name any entity referenced but not visible in the input rather than inventing its columns.

```
## TypeORM Design

### Entities
| Entity | Columns | Relations | Indexes |
|--------|---------|-----------|---------|

### Enums
| Enum | Values |
|------|--------|

### Repository Methods
| Method | Query Type | Relations Loaded | Pagination | Transaction {none / callback / QueryRunner} |
|--------|-----------|------------------|------------|---------------------------------------------|

### Money and Numeric Handling
[Column types, where arithmetic happens, string-boundary conversions]

### Migrations
[Migration file names and what they create - commands and ordering per `node-migration-safety`]
```

## Avoid

- `synchronize: true` in production (drops columns silently)
- Lazy loading (one query per access)
- Raw SQL for simple CRUD
- Unbounded connection pool
- Leaked `QueryRunner` (missing `finally release()`)
- Enqueuing jobs inside `dataSource.transaction` (fires before commit)
- `parseFloat` on a `decimal`/`numeric` column
- `limit`/`offset` on a query that joins a collection, and `getManyAndCount()` over a `GROUP BY`
- Interpolating a user-supplied sort column into `orderBy()`
