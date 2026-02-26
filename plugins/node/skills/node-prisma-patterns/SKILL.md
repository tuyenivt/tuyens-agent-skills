---
name: node-prisma-patterns
description: "Prisma ORM patterns for NestJS: schema design, migrations, N+1 prevention (include/select), transactions, connection pooling, raw queries, and PrismaService as injectable."
user-invocable: false
---

Cover:

1. PRISMA SCHEMA:
   - schema.prisma as single source of truth for data model
   - Relations: @relation with explicit foreign keys
   - Enums for status fields
   - @@index for query optimization
   - @@unique for composite unique constraints

2. PRISMA IN NESTJS:
   - PrismaService extends PrismaClient, implements OnModuleInit
   - Inject PrismaService in repositories/services
   - Use $transaction for multi-operation transactions:

```typescript
     await this.prisma.$transaction(async (tx) => {
       const order = await tx.order.create({ data: {...} });
       await tx.orderItem.createMany({ data: items });
       return order;
     });
```

3. N+1 PREVENTION:
   - include: { items: true } for eager loading relations
   - select: { id: true, total: true } for partial field loading
   - Fluent API: order.items() for lazy relation loading (avoid in loops)
   - Prisma Client generates optimized queries — trust it, but verify with logging

4. CONNECTION POOLING:
   - datasource db { url = env("DATABASE_URL") }
   - connection_limit in URL: ?connection_limit=10
   - For serverless: use Prisma Accelerate or PgBouncer

5. MIGRATIONS:
   - prisma migrate dev — development
   - prisma migrate deploy — production (CI/CD)
   - prisma migrate reset — for testing
   - prisma db push — for prototyping only, NOT production

6. ANTI-PATTERNS:
   - ❌ prisma db push in production (no migration history)
   - ❌ Loading all relations by default (specify include/select explicitly)
   - ❌ Raw queries for simple CRUD (use Prisma Client)
   - ❌ Not setting connection_limit (defaults may be too high)
