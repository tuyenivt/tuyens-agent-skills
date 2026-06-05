---
name: node-transaction-patterns
description: Node.js transactions - no I/O inside tx, post-commit dispatch, outbox, savepoints, lock-then-write, lock/statement timeouts, reads outside tx.
metadata:
  category: backend
  tags: [node, typescript, prisma, typeorm, transactions, outbox, postgres]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

Owns the **cross-ORM** transaction contract. `node-prisma-patterns` / `node-typeorm-patterns` show ORM-specific syntax; this skill owns rules that apply regardless of ORM: what may run inside an open tx, how post-commit side effects dispatch, when to use the outbox, and how to bound write transactions with timeouts.

## When to Use

- Wrapping a multi-step write that must be atomic
- Dispatching side effects (BullMQ enqueue, HTTP webhook, mailer) tied to a DB write
- Resolving "we sent the email but the row rolled back" / "worker picked up the job before the row was visible"
- Adding savepoints for partial-failure tolerance within a transaction
- Tuning `lock_timeout` / `statement_timeout` on a write path

## Rules

- **No I/O inside an open transaction.** No `fetch` / `axios`, no `queue.add`, no `mailer.send`, no third-party SDK calls. They hold a pooled DB connection, and on rollback the side effect has already fired
- **Capture scalars before commit; dispatch after.** Pull the IDs / values you need inside the tx, then enqueue / call after `$transaction(...)` (Prisma) or `transaction(...)` (TypeORM) resolves
- Read-only queries run **outside** transactions. Wrapping a `SELECT` in `$transaction` adds latency and pool pressure for no benefit
- Multi-step writes that must be atomic go in **one** transaction - don't chain two `$transaction` calls; the gap between them can leave the system in an inconsistent state
- Every write transaction sets `lock_timeout` (avoid waiting forever on a row lock) and `statement_timeout` (avoid a runaway query holding locks)
- Use savepoints (`tx.$executeRawUnsafe('SAVEPOINT ...')` or TypeORM's nested transaction) only when partial failure must be tolerated **within** the transaction - rare; most cases want one atomic unit
- Lock-then-write (`SELECT ... FOR UPDATE` before mutate) when the update depends on the current value (counters, balances, state machines). Skip locking when the unique constraint or optimistic concurrency token catches the conflict
- For **at-least-once** dispatch under crashes (billing, payments, contractual notifications), use the transactional outbox. For best-effort (notifications, analytics), post-commit dispatch is enough
- Outbox consumers are idempotent - they use `jobId` (BullMQ) or `Idempotency-Key` (HTTP) so replay doesn't double-fire

## Patterns

### Why I/O Inside a Transaction Is Wrong

```typescript
// Bad - holds a DB connection while waiting for Stripe; on Stripe failure the row stays
await prisma.$transaction(async (tx) => {
  const order = await tx.order.create({ data });
  await stripe.charges.create({ amount, customer });    // HTTP - DB conn held
  await queue.add('send-receipt', { orderId: order.id }); // worker may pick before commit
});
```

Three concrete failures:

1. **Pool starvation** - the connection sits idle waiting on HTTP. Under load the pool exhausts.
2. **Worker races commit** - BullMQ workers can pick up the job before `COMMIT` returns; they read a non-existent row.
3. **Rollback leaks side effects** - Stripe charged, row rolled back. Money taken, no order.

### Pattern A - Post-Commit Dispatch (default)

```typescript
// Prisma
const orderId = await prisma.$transaction(async (tx) => {
  const order = await tx.order.create({ data });
  await tx.orderItem.createMany({ data: items.map(i => ({ ...i, orderId: order.id })) });
  return order.id;                          // scalar out, not the entity
});
await queue.add('send-receipt', { orderId }, { jobId: `receipt:${orderId}` });
await stripe.charges.create({ amount, metadata: { orderId } }, { idempotencyKey: orderId });
```

```typescript
// TypeORM with typeorm-transactional (NestJS) - runOnTransactionCommit
@Transactional()
async place(input: PlaceOrderDto): Promise<string> {
  const order = await this.orders.save(Order.from(input));
  runOnTransactionCommit(() => this.queue.add('send-receipt', { orderId: order.id }));
  return order.id;
}
```

Failure mode: process crash between `COMMIT` and dispatch drops the side effect. Acceptable for receipts, analytics; not for billing - use Pattern B.

### Pattern B - Transactional Outbox (at-least-once)

```typescript
// schema (Prisma)
model OutboxMessage {
  id          String   @id @default(cuid())
  aggregateId String
  eventType   String
  payload     Json
  createdAt   DateTime @default(now())
  processedAt DateTime?
  @@index([processedAt, createdAt])
}

// write
await prisma.$transaction(async (tx) => {
  const order = await tx.order.create({ data });
  await tx.outboxMessage.create({
    data: { aggregateId: order.id, eventType: 'order.placed', payload: { orderId: order.id, total: order.total } },
  });
});

// relay (BullMQ scheduler or interval) - claim atomically, dispatch outside any tx
const claimed = await prisma.$queryRaw<OutboxRow[]>`
  UPDATE "OutboxMessage" SET "processedAt" = NOW()
  WHERE id IN (
    SELECT id FROM "OutboxMessage" WHERE "processedAt" IS NULL
    ORDER BY "createdAt" LIMIT 100 FOR UPDATE SKIP LOCKED
  )
  RETURNING *`;

for (const m of claimed) {
  await queue.add(m.eventType, m.payload, { jobId: m.id });     // jobId dedupes replay
}
```

The outbox row commits **atomically with the business write**, so rollback drops both. The `UPDATE ... RETURNING` with `FOR UPDATE SKIP LOCKED` in the inner SELECT claims a batch in one statement - multiple relay instances cooperate without contention, no I/O is held under a row lock. BullMQ's `jobId` plus idempotent downstream handlers tolerate the rare double-dispatch when a relay crashes after claim and before `queue.add`.

### Lock-Then-Write (Counters, Balances, State Machines)

```typescript
// Prisma raw, or repository helper
await prisma.$transaction(async (tx) => {
  const [row] = await tx.$queryRaw<{ id: string; balance: number }[]>`
    SELECT id, balance FROM "Wallet" WHERE id = ${walletId} FOR UPDATE`;
  if (row.balance < amount) throw new InsufficientFundsError();
  await tx.wallet.update({ where: { id: walletId }, data: { balance: { decrement: amount } } });
});
```

Without `FOR UPDATE`, two concurrent transactions both see the old balance and both decrement - lost-update.

Alternative for simple counters: rely on the constraint and atomic increment:

```typescript
await prisma.wallet.update({
  where: { id: walletId, balance: { gte: amount } },     // atomic guard
  data:  { balance: { decrement: amount } },
});
// throws P2025 if no row matched (insufficient funds) - translate at the boundary
```

Both work; lock-then-write is clearer when multiple fields update conditionally; atomic-guard is cheaper for single-field decrements.

### Write Transaction Timeouts

```typescript
// Prisma - $transaction options
await prisma.$transaction(async (tx) => { /* ... */ }, {
  maxWait: 2_000,         // wait for a connection from the pool
  timeout: 5_000,         // total tx wall-clock
});

// Postgres-side - belt-and-braces, set per-session
await prisma.$executeRawUnsafe(`SET LOCAL lock_timeout = '3s'`);
await prisma.$executeRawUnsafe(`SET LOCAL statement_timeout = '5s'`);
```

Without `lock_timeout`, a transaction waiting on a row lock waits forever - the connection holds, the pool drains. Without `statement_timeout`, a single slow query holds locks for the entire session.

### Read-Only Queries Outside Transactions

```typescript
// Bad - no atomicity benefit, pays the tx overhead
const orders = await prisma.$transaction(async tx => tx.order.findMany({ where: { userId } }));

// Good
const orders = await prisma.order.findMany({ where: { userId } });
```

Transactions are for **writes that must be atomic together**, not for grouping reads. Reads inside a transaction also acquire read locks under `SERIALIZABLE`, which is rarely what you want.

### Savepoints (Use Sparingly)

```typescript
// TypeORM nested - the inner failure rolls back to the savepoint; outer continues
await dataSource.transaction(async (tx) => {
  await tx.save(orderEntity);
  try {
    await tx.transaction(async (inner) => {        // SAVEPOINT
      await inner.save(optionalAuditEntity);
    });
  } catch { /* audit failed - swallow, keep the order */ }
});
```

Justified when a non-critical side write (audit log, denormalized view) must not roll back the main transaction. If the side write **does** belong with the main one atomically, use a single transaction without the savepoint.

## Output Format

```
Pattern: {Post-Commit | Outbox | Lock-Then-Write | Atomic-Guard | Savepoint | Read-Outside-Tx}
ORM: {Prisma | TypeORM}
Transaction Scope: {what writes are inside, what was moved out}
Side Effect Dispatch: {after $transaction returns | runOnTransactionCommit | outbox + relay}
Idempotency: {jobId / Idempotency-Key / unique constraint / N/A}
Timeouts: {tx.timeout = N ms; SET LOCAL lock_timeout / statement_timeout}
Failure Mode Documented: {what happens on crash between commit and dispatch}
```

## Avoid

- HTTP / queue / mailer calls inside `$transaction` - move them after commit, or use the outbox
- Returning ORM entities from inside `$transaction` and using them afterwards - lazy relations may not be loaded; pull scalars instead
- Wrapping read-only queries in a transaction
- Chaining two `$transaction` calls where one would do - the gap is not atomic
- Side-effect listeners (`@AfterInsert`, EventEmitter2 fired pre-commit) that race the COMMIT
- Outbox relay without `FOR UPDATE SKIP LOCKED` on the claim - relay instances dispatch the same row repeatedly
- Outbox consumers that aren't idempotent - one relay restart and every receipt fires twice
- Lock-then-write without a timeout - waits forever on contention
- Setting `statement_timeout` globally on the DB role used by long-running migrations (it kills them)
- Savepoints to "make it more robust" - they add complexity for a rare partial-failure case
