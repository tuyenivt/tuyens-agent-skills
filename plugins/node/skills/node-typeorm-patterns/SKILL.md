---
name: node-typeorm-patterns
description: "TypeORM patterns for Express and NestJS: entity definition, repository pattern, query builder, migrations, relations, N+1 prevention, transactions, pagination, connection pooling, and batch operations."
user-invocable: false
---

Cover:

1. ENTITY DEFINITION:
   - @Entity(), @Column(), @PrimaryGeneratedColumn('uuid')
   - Relations: @ManyToOne, @OneToMany, @ManyToMany with JoinColumn/JoinTable
   - @Index() on foreign keys and frequently-filtered columns
   - @CreateDateColumn(), @UpdateDateColumn() for timestamps
   - @Column({ type: 'enum', enum: OrderStatus }) for status fields

2. REPOSITORY PATTERN:

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

3. QUERY BUILDER:

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

4. N+1 PREVENTION:
   - `relations` option in find: `{ relations: ['items', 'customer'] }`
   - QueryBuilder: `.leftJoinAndSelect('order.items', 'items')`
   - Lazy loading: avoid - it fires a query per access. Prefer explicit eager loading in every query.

5. TRANSACTIONS:

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

6. BATCH OPERATIONS:

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

7. CONNECTION POOLING:

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

8. MIGRATIONS:
   - `typeorm migration:generate -d src/data-source.ts -n AddShipment` - auto-generates from entity diff
   - `typeorm migration:create -n BackfillPhoneColumn` - empty migration for custom SQL
   - `typeorm migration:run` - applies pending
   - `typeorm migration:revert` - reverts last applied
   - Always review generated migrations before applying
   - Same zero-downtime rules as core (add nullable first, backfill, then NOT NULL)

9. ANTI-PATTERNS:
   - `synchronize: true` in production (auto-syncs schema without migration history - can drop columns)
   - Lazy loading without understanding it fires a query per access
   - Raw SQL for simple CRUD (use repository/query builder)
   - Not setting connection pool limits (defaults may exhaust database connections)
   - Returning entities directly from API endpoints (use DTOs to control response shape)
   - Not releasing QueryRunner in finally block (leaks database connections)
