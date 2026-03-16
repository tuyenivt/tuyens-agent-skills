---
name: node-typeorm-patterns
description: TypeORM patterns for Express and NestJS - entity definition, repository pattern with DataSource, QueryBuilder for complex queries, transactions, N+1 prevention, migrations, pagination, connection pooling, and batch operations.
metadata:
  category: backend
  tags: [node, typescript, typeorm, orm, database, patterns]
user-invocable: false
---

# TypeORM Patterns

## When to Use

- Designing TypeORM entities, relations, and indexes
- Writing queries that must avoid N+1 problems or require transactions
- Setting up repositories, QueryBuilder, or connection pooling
- Implementing pagination or batch operations with TypeORM

## Rules

- Every entity gets `@Index()` on foreign keys and frequently-filtered columns
- Use `relations` option or `leftJoinAndSelect` to prevent N+1 - never rely on lazy loading
- Always release `QueryRunner` in a `finally` block
- `synchronize: true` is forbidden in production - use migrations only
- Never return entities directly from API endpoints - map to DTOs

## Patterns

### Entity Definition

- `@Entity()`, `@Column()`, `@PrimaryGeneratedColumn('uuid')`
- Relations: `@ManyToOne`, `@OneToMany`, `@ManyToMany` with `JoinColumn`/`JoinTable`
- `@Index()` on foreign keys and frequently-filtered columns
- `@CreateDateColumn()`, `@UpdateDateColumn()` for timestamps
- `@Column({ type: 'enum', enum: OrderStatus })` for status fields

### Repository Pattern

```typescript
@Injectable()
export class OrderRepository {
  constructor(private readonly dataSource: DataSource) {}

  private get repo() {
    return this.dataSource.getRepository(Order);
  }

  async findWithItems(orderId: string): Promise<Order | null> {
    return this.repo.findOne({
      where: { id: orderId },
      relations: ["items", "items.product", "customer"],
    });
  }
}
```

### QueryBuilder

Use QueryBuilder for complex filtering, joins, and aggregations that go beyond simple `find` options:

```typescript
async findOrdersWithFilters(filters: OrderFilterDto): Promise<[Order[], number]> {
  const qb = this.repo
    .createQueryBuilder("order")
    .leftJoinAndSelect("order.items", "item")
    .leftJoinAndSelect("order.customer", "customer");

  if (filters.status) qb.andWhere("order.status = :status", { status: filters.status });
  if (filters.minTotal) qb.andWhere("order.total >= :min", { min: filters.minTotal });

  return qb
    .orderBy("order.createdAt", "DESC")
    .skip((filters.page - 1) * filters.pageSize)
    .take(filters.pageSize)
    .getManyAndCount();
}
```

### N+1 Prevention

- `relations` option in find: `{ relations: ['items', 'customer'] }`
- QueryBuilder: `.leftJoinAndSelect('order.items', 'items')`
- Lazy loading: avoid - it fires a query per access. Prefer explicit eager loading in every query.

### Transactions

```typescript
// Simple form - EntityManager handles commit/rollback
await this.dataSource.transaction(async (manager) => {
  const order = manager.create(Order, { customerId, status: "PENDING" });
  await manager.save(order);
  const items = lineItems.map((li) => manager.create(OrderItem, { orderId: order.id, ...li }));
  await manager.save(items);
});

// QueryRunner - for manual control (savepoints, conditional commits)
const queryRunner = this.dataSource.createQueryRunner();
await queryRunner.connect();
await queryRunner.startTransaction();
try {
  await queryRunner.manager.save(order);
  await queryRunner.manager.save(items);
  await queryRunner.commitTransaction();
} catch (err) {
  await queryRunner.rollbackTransaction();
  throw err;
} finally {
  await queryRunner.release(); // always release, even on error
}
```

### Batch Operations

```typescript
// Bulk insert (chunks automatically)
await this.repo.save(items, { chunk: 500 });

// Bulk update
await this.repo
  .createQueryBuilder()
  .update(Order)
  .set({ status: "EXPIRED" })
  .where("status = :status AND createdAt < :cutoff", { status: "PENDING", cutoff: cutoffDate })
  .execute();
```

### Connection Pooling

```typescript
// DataSource options
{
  type: "postgres",
  extra: {
    max: 20,           // max connections in pool
    idleTimeoutMillis: 10000,
  },
}
```

### Migrations

- `typeorm migration:generate -d src/data-source.ts -n AddShipment` - auto-generates from entity diff
- `typeorm migration:create -n BackfillPhoneColumn` - empty migration for custom SQL
- `typeorm migration:run` - applies pending
- `typeorm migration:revert` - reverts last applied
- Always review generated migrations before applying
- Same zero-downtime rules as core (add nullable first, backfill, then NOT NULL)

## Edge Cases

- **QueryRunner not released after error**: Always use `finally { await queryRunner.release() }`. A leaked QueryRunner holds an open database connection permanently.
- **Entity listeners firing during bulk operations**: `save()` triggers `@BeforeInsert`/`@AfterInsert` listeners for each entity. For bulk inserts where listeners are not needed, use `createQueryBuilder().insert()` instead.
- **Relation loading in transactions**: When using `QueryRunner` transactions, load relations via `queryRunner.manager.findOne()` with `relations` option - do not use the default repository (it uses a different connection).

## Avoid

- `synchronize: true` in production (auto-syncs schema without migration history - can drop columns)
- Lazy loading without understanding it fires a query per access
- Raw SQL for simple CRUD (use repository/QueryBuilder)
- Not setting connection pool limits (defaults may exhaust database connections)
- Returning entities directly from API endpoints (use DTOs to control response shape)
- Not releasing QueryRunner in `finally` block (leaks database connections)
