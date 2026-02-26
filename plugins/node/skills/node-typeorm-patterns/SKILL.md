---
name: node-typeorm-patterns
description: "TypeORM patterns for Express: entity definition, repository pattern, query builder, migrations, relations, eager/lazy loading, connection pooling, and transaction management."
user-invocable: false
---

Cover:

1. ENTITY DEFINITION:
   - @Entity(), @Column(), @PrimaryGeneratedColumn()
   - Relations: @ManyToOne, @OneToMany, @ManyToMany with JoinColumn/JoinTable
   - @Index() for query optimization
   - @CreateDateColumn(), @UpdateDateColumn() for timestamps

2. REPOSITORY PATTERN:
   - Custom repository extending Repository<Entity>
   - Use DataSource.getRepository() or custom Repository class
   - QueryBuilder for complex queries: .createQueryBuilder('order').leftJoinAndSelect(...)

3. N+1 PREVENTION:
   - relations option in find: { relations: ['items', 'customer'] }
   - QueryBuilder: .leftJoinAndSelect('order.items', 'items')
   - Lazy loading: avoid, prefer explicit eager loading

4. TRANSACTIONS:
   - DataSource.transaction(async (manager) => { ... })
   - QueryRunner for manual transaction control

5. MIGRATIONS:
   - typeorm migration:generate — auto-generates from entity diff
   - typeorm migration:run — applies pending
   - Always review generated migrations
   - Same zero-downtime rules as core

6. ANTI-PATTERNS:
   - ❌ Synchronize: true in production (auto-syncs schema, dangerous)
   - ❌ Lazy loading without explicit configuration
   - ❌ Raw SQL for simple operations (use repository/query builder)
   - ❌ Not setting connection pool limits
