---
name: node-typeorm-patterns
description: TypeORM patterns for NestJS / Express: entities, repository with DataSource, QueryBuilder, transactions, N+1 prevention, migrations, pagination.
metadata:
  category: backend
  tags: [node, typescript, typeorm, orm, database, patterns]
user-invocable: false
---

# TypeORM Patterns

> Load `Use skill: stack-detect` first; its `Database` field picks the engine notes below and surfaces in the design block's `**Engine:**` line (a request that plans a move to another engine designs against the target: `MySQL -> PostgreSQL (planned)`). The TypeORM version comes from `typeorm` in `package.json` (`unknown` when absent). The notes are PostgreSQL's (node-`pg`), with the MySQL deltas inline. MySQL (`mysql2`) returns `DECIMAL` as a string too; TypeORM interpolates its parameters client-side, so a batch is bounded by `max_allowed_packet`, not a placeholder count. SQLite needs `simple-enum` instead of `type: "enum"`, caps bind parameters at 32,766 (999 before 3.32), and reads `decimal` back as a JS `number` - store money as integer minor units or `text` with a `decimal.js` `ValueTransformer`.

## When to Use

- Designing TypeORM entities, relations, enums, and indexes
- Writing queries that must avoid N+1 or require transactions
- Setting up repositories, QueryBuilder, pagination, streaming, or batch operations

## Rules

- `@Index()` on foreign keys (MySQL creates one per FK itself; PostgreSQL does not) and on every filtered or sorted column set, in the query's column order; `@Column({ unique: true })` (or class-level `@Unique(["idempotencyKey"])`) on every business key (an idempotency key, an external id) - the constraint is the claim, never a lookup first
- Load relations explicitly via `relations` or `leftJoinAndSelect`. `eager: true` joins the relation into every `find*` (QueryBuilder ignores it) - over-fetch on a large collection; lazy relations query once per entity on first `await` - N+1 across a list
- Every read and write inside a transaction goes through its manager (`m` / `qr.manager`): an injected repository uses another pooled connection, sees no uncommitted writes, and takes no lock
- Release every `QueryRunner` in a `finally` block
- `synchronize: true` is forbidden in production - migrations only (`node-migration-safety`); `synchronize: process.env.NODE_ENV !== "production"` runs it wherever the variable is unset, so default it off
- Map entities to DTOs at the API boundary; repository methods that feed a response return the DTO or a plain object, never the entity
- Enqueue background jobs only after the transaction commits
- Money is `decimal` / `numeric` and never passes through a JS `number`
- `findByIds` is deprecated and the positional `findOne(id)` was removed in 0.3: `findBy({ id: In(ids) })` / `findOneBy({ id })`. `findOneOrFail` throws `EntityNotFoundError`, which answers 500 unless a filter maps it - `findOneBy` + a 404 is the default

## Patterns

### Entity Definition

UUID PK, enum column, decimal money, indexed FK, bidirectional relation with `cascade`, timestamps.

```typescript
export enum OrderStatus { PENDING = "PENDING", CONFIRMED = "CONFIRMED", CANCELLED = "CANCELLED", EXPIRED = "EXPIRED" }

@Entity()
@Index(["status", "createdAt"])
export class Order {
  @PrimaryGeneratedColumn("uuid") id!: string;
  @Column({ type: "enum", enum: OrderStatus, default: OrderStatus.PENDING }) status!: OrderStatus;
  @Column({ type: "decimal", precision: 19, scale: 4, default: 0 }) total!: string;   // numeric arrives as a string

  @ManyToOne(() => Customer, { nullable: false })
  @JoinColumn({ name: "customerId" })
  customer!: Customer;
  @Index() @Column() customerId!: string;

  @OneToMany(() => OrderItem, (i) => i.order, { cascade: ["insert"] })
  items!: OrderItem[];

  @CreateDateColumn() createdAt!: Date;
  @UpdateDateColumn() updatedAt!: Date;
}
```

`@JoinColumn({ name: "customerId" })` ties the relation to the declared `customerId` column; the default name is the same, so the decorator documents the pairing and keeps it through a property rename. `OrderItem` mirrors the pattern: `@ManyToOne(() => Order, (o) => o.items)` with `@JoinColumn({ name: "orderId" })` and `@Index()`.

### Repository Pattern

```typescript
@Injectable()
export class OrderRepository {
  constructor(private readonly dataSource: DataSource) {}
  private get repo() { return this.dataSource.getRepository(Order); }

  async findWithItems(id: string): Promise<OrderDto | null> {
    const o = await this.repo.findOne({ where: { id }, relations: { items: true, customer: true } });
    return o && toOrderDto(o);                  // DTO out
  }
}
```

### QueryBuilder

```typescript
async findOrders(f: OrderFilterDto): Promise<{ rows: OrderDto[]; total: number }> {
  const qb = this.repo.createQueryBuilder("order").leftJoinAndSelect("order.customer", "customer");  // to-one join: safe with skip/take

  if (f.status) qb.andWhere("order.status = :status", { status: f.status });
  if (f.minTotal) qb.andWhere("order.total >= :min", { min: f.minTotal });
  if (f.customerId) qb.andWhere("order.customerId = :cid", { cid: f.customerId });

  const [rows, total] = await qb.orderBy("order.createdAt", "DESC").addOrderBy("order.id", "DESC")   // unique tiebreaker
    .skip((f.page - 1) * f.pageSize).take(f.pageSize)
    .getManyAndCount();
  return { rows: rows.map(toOrderDto), total };
}
```

In a select builder, condition strings name columns through the alias (`order.createdAt`); a bare `createdAt` is not rewritten, and PostgreSQL folds the unquoted name to `createdat` and fails. In `update()` / `delete()` builders the reverse holds: the alias is not in scope, so write bare property names.

### Transactions

Prefer the callback form; commit and rollback are automatic:

```typescript
const orderId = await this.dataSource.transaction(async (m) => {
  const o = await m.save(m.create(Order, { customerId, status: OrderStatus.PENDING, total }));
  await m.save(lineItems.map((li) => m.create(OrderItem, { orderId: o.id, ...li })));
  return o.id;                                  // scalar out
});
await orderQueue.add("process-order", { orderId }, { jobId: `process-order-${orderId}` });   // after commit
```

Read-then-write inside it needs a lock: `m.findOne(Account, { where: { id }, lock: { mode: "pessimistic_write" } })` (or `.setLock("pessimistic_write")` on a builder); a plain find inside the transaction is an unlocked read. Lock several rows in a fixed order (by id) or concurrent transfers deadlock. Where contention is rare, `@VersionColumn` is the optimistic alternative: the read with `lock: { mode: "optimistic", version }` throws `OptimisticLockVersionMismatchError` when the row moved on; `save()` never checks the version, so guard the write with a builder `.update().where("version = :v")` and check `affected`.

Use `QueryRunner` only when you need manual control (savepoints, conditional commits):

```typescript
const qr = this.dataSource.createQueryRunner();
try {
  await qr.connect();
  await qr.startTransaction();
  /* qr.manager.save(...) */
  await qr.commitTransaction();
} catch (e) {
  if (qr.isTransactionActive) await qr.rollbackTransaction();
  throw e;
} finally {
  await qr.release();                           // also runs when connect/startTransaction threw
}
```

A nested `startTransaction()` on the same runner emits a `SAVEPOINT`: catching the inner failure and calling `rollbackTransaction()` returns to the savepoint and lets the outer transaction commit. Use it only when a non-critical side write must not lose the main write, and do not rethrow from the inner catch.

### Batch Operations

```typescript
await this.repo.insert(rows);                   // pure inserts: one INSERT per call, no per-row SELECT
await this.repo.save(entities, { chunk: 500 }); // save(): SELECTs rows that have ids, UPDATEs row by row

await this.dataSource.createQueryBuilder().update(Order)
  .set({ status: OrderStatus.EXPIRED })
  .where("status = :s AND createdAt < :cutoff", { s: OrderStatus.PENDING, cutoff })   // bare names: no alias here
  .execute();
```

A builder `.update()` still stamps `@UpdateDateColumn` (and bumps `@VersionColumn`) when the column is not in `.set()`, and builder inserts/updates still fire **subscribers** (`beforeInsert`, `afterUpdate`) unless `.callListeners(false)`. Entity-method listeners (`@BeforeInsert` on the class) run only when the value is an entity instance - build rows with `manager.create(Entity, {...})`; a plain object passed to `save()` or `.values()` skips them. Keep `rows per statement x bound columns per row` under the engine's cap (PostgreSQL 65,535; SQLite above). `save(..., { transaction: false })` drops one `BEGIN/COMMIT` pair and the atomicity across chunks with it - use it only when partial completion is acceptable. `repo.upsert(rows, ["idempotencyKey"])` is one `INSERT ... ON CONFLICT DO UPDATE` (MySQL `ON DUPLICATE KEY UPDATE`); the conflict columns must carry a unique index. On MySQL the bound is bytes, not placeholders: keep each statement under `max_allowed_packet` (default 64 MB on 8.0) by chunking on row size (rows x average serialised row, under a quarter of it).

### Pagination With a Collection Join

Paginating while joining a `@OneToMany` is the most common TypeORM performance bug, and the naive form is silently wrong:

```typescript
// Bad - limit/offset page the joined CARTESIAN rows, so a page holds < pageSize accounts
qb.leftJoinAndSelect("account.entries", "entry").limit(50).offset(off);

// Bad - skip/take wraps the query in a DISTINCT subquery over the root ids; sorting by a joined
// or computed column then pages wrong
qb.leftJoinAndSelect("order.items", "item").orderBy("item.price", "DESC").skip(0).take(50);

// Good - two phases: page the roots with no collection join, then hydrate those ids
const ids = (await this.repo.createQueryBuilder("order")
  .select("order.id", "id").where(...)
  .orderBy("order.createdAt", "DESC").addOrderBy("order.id", "DESC")   // unique tiebreaker, or pages overlap
  .limit(50).offset(off).getRawMany<{ id: string }>()).map((r) => r.id);

const rows = await this.repo.find({ where: { id: In(ids) }, relations: { items: true } });
// `In()` does not preserve order - restore phase 1's ordering explicitly
const byId = new Map(rows.map((r) => [r.id, r]));
const page = ids.flatMap((id) => byId.get(id) ?? []);   // a row deleted between phases drops out
```

`relationLoadStrategy: "query"` (per query or per DataSource) loads relations as separate queries instead of one join - it removes the cartesian blow-up and the DISTINCT wrapper, at extra round trips per relation (two per `OneToMany`). Prefer it over hand-rolling two phases unless the collection must appear in the `WHERE` or the `ORDER BY`.

`getManyAndCount()`'s count query drops `GROUP BY` and counts distinct root ids, so over a grouped query the total ignores the grouping (and a `HAVING` breaks it): run an explicit `COUNT(*)` over the grouped subquery, or `getRawMany()` for the groups. `orderBy()` is not parameterised: a user-selectable sort maps through a fixed whitelist (`{ date: "line.bookedAt", amount: "line.amount" }`) plus a unique tiebreaker.

Keyset paging over a large table: order by a unique key pair and seek past the last row seen, served by an index on `(createdAt, id)` (MySQL accepts the row constructor but may not drive the composite index with it - expand to `(order.createdAt < :at OR (order.createdAt = :at AND order.id < :id))` there - outer parentheses kept, since TypeORM joins `where` / `andWhere` strings unwrapped):

```typescript
qb.where("(order.createdAt, order.id) < (:at, :id)", { at: cursor.at, id: cursor.id })
  .orderBy("order.createdAt", "DESC").addOrderBy("order.id", "DESC").limit(50);
```

Streaming a large export: `qb.stream()` on a dedicated `QueryRunner`, ordered by a stable key, over the root table with no collection join. It yields raw alias-prefixed rows (`order_id`), not entities - no hydration, no transformers - and on PostgreSQL needs the `pg-query-stream` package (`mysql2` streams natively). Never `OFFSET` paging over hundreds of thousands of rows.

### Money and Numerics

`pg` returns `numeric` as a **string**, and `SUM` / `COUNT` come back as strings too. Never `parseFloat` a money value - aggregate in SQL and carry `decimal.js` at the boundary, either as the `string` entity column above or through a `ValueTransformer` that yields `Decimal` on the entity - one convention per codebase. A transformer's `to` is applied to entity saves, builder `.set()` / `.values()`, and find-options `where` values; it is **not** applied to `:named` parameters in a QueryBuilder condition string or to `query()` - serialise those yourself.

### Connection Pooling

`extra.max` (else `poolSize`, else node-`pg`'s 10) is the per-process pool - on MySQL `extra.connectionLimit` (else `poolSize`, else `mysql2`'s 10); size it with `node-connection-pool-sizing`.

### Migrations

See `node-migration-safety` for commands, deploy ordering, and zero-downtime DDL rules. Moving MySQL -> PostgreSQL: PostgreSQL creates no index for a FK (`@Index()` every FK, as above); `enum` columns become named types (`<table>_<column>_enum`; a generated migration for a new value renames and recreates the type and rewrites the column - hand-edit it to `ALTER TYPE ... ADD VALUE`, `node-migration-safety`); `datetime` becomes `timestamptz` (`@Column({ type: "timestamptz" })`, and `@CreateDateColumn({ type: "timestamptz" })` / `@UpdateDateColumn` likewise - they default to `TIMESTAMP` without zone); uuids are generated server-side - `uuid_generate_v4()` (uuid-ossp) by default, `gen_random_uuid()` with `uuidExtension: "pgcrypto"` - where MySQL made them client-side; `DECIMAL` arrives as a string on both. Baseline the target with one generated migration (`<timestamp>-Baseline`) before any data move.

## Output Format

When authoring, emit this block plus the entity and query code it describes; a build over existing code is authoring plus review - findings for the existing defects the change touches, then the block. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file) followed by `Issue:` and `Fix:` lines, `[Must]` first - `[Must]` when it risks incorrect behaviour, data loss, or a security hole (a page holding fewer rows than `pageSize`, money through a `number`, an enqueue before commit, an unlocked read-then-write), `[Recommend]` otherwise (a missing index, an over-fetch). A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright gets one `Ruling:` line; both precede the findings, which cover the causes first and then any other defect in the files read. After the findings, emit this block as the target state: every row shows the corrected value, and a row the current code violates ends ` - GAP (was: <observed>)` - an entity lacking a column the code needs is such a row (the Columns cell lists the column), and under a planned engine the GAP compares the current code with the target engine's form. Name any entity referenced but not visible in the input rather than inventing its columns. A defect outside this skill's lens (`save(req.body)`, an entity-vs-migration drift, worker concurrency against the pool) goes on one `Out of scope: <defect> -> <owning skill>` line after the findings and before the block. A multi-value cell marks the GAP per value; a query site with no repository (router code) is a row reading `n/a - no repository` in Method and naming the file. Repository Methods cells: Query Type `{find | locked find | save | insert/upsert | QueryBuilder | raw}`, Pagination `{none | skip/take | limit/offset (no collection join) | two-phase | relationLoadStrategy query | keyset | stream}`, Transaction `{none | callback | QueryRunner}`, Returns `{DTO | plain}`.

```
## TypeORM Design

**Engine:** {PostgreSQL | MySQL | SQLite | other | unknown}{ -> <target> (planned)} - TypeORM {version from package.json | unknown}

### Entities
| Entity | Columns | Relations (load strategy) | Indexes |
|--------|---------|---------------------------|---------|

### Enums
| Enum | Values |
|------|--------|

### Repository Methods
| Method | Query Type | Relations Loaded | Pagination | Transaction | Returns |
|--------|-----------|------------------|------------|-------------|---------|

### Money and Numeric Handling
{column types, where arithmetic happens, string-boundary conversions}

### Migrations
{migration file names and what they create - commands and ordering per node-migration-safety}
```

## Avoid

- Raw SQL for simple CRUD
- Pool `max` not sized against `max_connections / processes`
- `limit`/`offset` on a query that joins a collection, and `getManyAndCount()` over a `GROUP BY`
- Interpolating a user-supplied sort column into `orderBy()`
