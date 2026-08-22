---
name: node-transaction-patterns
description: Node.js transactions - no I/O inside tx, post-commit dispatch, outbox, savepoints, lock-then-write, lock/statement timeouts, reads outside tx.
metadata:
  category: backend
  tags: [node, typescript, prisma, typeorm, transactions, outbox, postgres]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.
> The transaction boundary contract - no I/O inside a transaction, post-commit dispatch, outbox semantics, lock-then-write, timeouts - is owned by `backend-transaction-patterns`. Load it first; it supplies the rules and severity taxonomy. This skill owns only the Node/ORM bindings for them.

## When to Use

- Wrapping a multi-step write that must be atomic
- Dispatching side effects (BullMQ enqueue, HTTP webhook, mailer) tied to a DB write
- Resolving "we sent the email but the row rolled back" / "worker picked up the job before the row was visible"
- Adding savepoints for partial-failure tolerance within a transaction
- Tuning `lock_timeout` / `statement_timeout` on a write path

## Rules

`backend-transaction-patterns` carries the contract. These are the Node-specific bindings and hazards it cannot state:

- Dispatch after `$transaction(...)` (Prisma) or `transaction(...)` (TypeORM) **resolves**, or via `runOnTransactionCommit` when using `typeorm-transactional`
- Return scalars from the transaction callback, never ORM entities. Under TypeORM a lazy relation accessed afterwards issues a query outside the transaction's snapshot; under Prisma the object is inert but stale, since later writes in the same transaction are not reflected in it
- I/O whose result **gates** the commit (a payment authorization the row depends on) cannot move after commit and must not run inside. Run it before `BEGIN`, persist an attempt row first, and reconcile orphans with a sweeper - the transaction then only consumes an already-known outcome
- `SET LOCAL lock_timeout` / `statement_timeout` must run **inside** the transaction; standalone it is a no-op, and plain `SET` leaks to every later query sharing the pooled connection. Under `@Transactional()`, run it through the transactional entity manager's `.query()` as the first statement
- Prisma's `maxWait` (pool acquisition) and `timeout` (total wall-clock) are separate from the Postgres-side timeouts; set both. TypeORM has no wall-clock equivalent - there, `statement_timeout` plus `idle_in_transaction_session_timeout` are the only bounds
- Outbox consumers dedupe with BullMQ `jobId` or an HTTP `Idempotency-Key`. A `jobId` only dedupes while the job is retained, so `removeOnComplete` must outlive the redelivery window
- One outbox row per (event, destination). A single row fanning out to two consumers has no way to record partial success, so one failing destination either blocks the other or gets marked done without being delivered
- Never dispatch from `@AfterInsert`, `@AfterUpdate`, or a pre-commit `EventEmitter2` listener - they fire before `COMMIT` and race it

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

The three failures - pool starvation, dispatch racing commit, the rollback-surviving charge - are stated in `backend-transaction-patterns`; this is what they look like in Prisma.

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
  claimedAt   DateTime?
  processedAt DateTime?
  attempts    Int      @default(0)
  @@index([processedAt, createdAt])
}

// write
await prisma.$transaction(async (tx) => {
  const order = await tx.order.create({ data });
  await tx.outboxMessage.create({
    data: { aggregateId: order.id, eventType: 'order.placed', payload: { orderId: order.id, total: order.total } },
  });
});

// relay (BullMQ scheduler or interval) - lease a batch, dispatch outside any tx, then mark done
const claimed = await prisma.$queryRaw<OutboxRow[]>`
  UPDATE "OutboxMessage" SET "claimedAt" = NOW(), attempts = attempts + 1
  WHERE id IN (
    SELECT id FROM "OutboxMessage"
    WHERE "processedAt" IS NULL AND attempts < 10
      AND ("claimedAt" IS NULL OR "claimedAt" < NOW() - INTERVAL '5 minutes')
    ORDER BY "createdAt" LIMIT 100 FOR UPDATE SKIP LOCKED
  )
  RETURNING *`;
// rows at attempts >= 10 are parked - alert on them; a poison message must not redispatch forever

for (const m of claimed) {
  await queue.add(m.eventType, m.payload, { jobId: m.id });     // jobId dedupes redelivery
  await prisma.outboxMessage.update({ where: { id: m.id }, data: { processedAt: new Date() } });
}
```

The outbox row commits **atomically with the business write**, so rollback drops both. The claim is a **lease**, not a completion mark: `processedAt` is set only after a successful `queue.add`, so a relay crash mid-batch re-delivers the row once the lease expires, and BullMQ's `jobId` plus idempotent handlers dedupe the replay - that is what makes it at-least-once. Marking `processedAt` at claim time would silently drop messages on a crash between claim and dispatch (at-most-once). `FOR UPDATE SKIP LOCKED` lets multiple relay instances cooperate without contention, and no I/O runs under a row lock.

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
// Prisma - $transaction options + Postgres-side belt-and-braces
// SET LOCAL is transaction-scoped: it must run INSIDE the tx (standalone it is a no-op,
// and plain SET would leak to other queries sharing the pooled connection)
await prisma.$transaction(async (tx) => {
  await tx.$executeRawUnsafe(`SET LOCAL lock_timeout = '3s'`);
  await tx.$executeRawUnsafe(`SET LOCAL statement_timeout = '5s'`);
  /* ... writes ... */
}, {
  maxWait: 2_000,         // wait for a connection from the pool
  timeout: 5_000,         // total tx wall-clock
});
```

Without `lock_timeout`, a transaction waiting on a row lock waits forever - the connection holds, the pool drains. Without `statement_timeout`, a single slow query holds locks for the entire session.

### Read-Only Queries Outside Transactions

```typescript
// Bad - no atomicity benefit, pays the tx overhead
const orders = await prisma.$transaction(async tx => tx.order.findMany({ where: { userId } }));

// Good
const orders = await prisma.order.findMany({ where: { userId } });
```

Transactions are for **writes that must be atomic together**, not for grouping reads; the contract's one carve-out - several reads needing one consistent snapshot - stands. Reads inside a transaction also acquire read locks under `SERIALIZABLE`, which is rarely what you want.

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

`backend-transaction-patterns`' Transaction Assessment envelope is always emitted - in review it carries the findings, in design it carries the residual risks. The block below is **additional**, not an alternative: emit one per transaction boundary, describing what that boundary will be. Where the two overlap, the envelope wins and the block is the Node detail behind it.

```
Pattern: {Post-Commit | Outbox | Lock-Then-Write | Atomic-Guard | Savepoint | Read-Outside-Tx} - list every one that applies; a real write path is usually two or three
ORM: {Prisma | TypeORM}
Transaction Scope: {what writes are inside, what was moved out, and what runs before BEGIN}
Side Effect Dispatch: {after $transaction returns | runOnTransactionCommit | outbox + relay claim}
Idempotency: {jobId / Idempotency-Key / unique constraint / atomic guard predicate / N/A}
Timeouts: {Prisma maxWait + timeout, or TypeORM none; SET LOCAL lock_timeout / statement_timeout - state N/A where the ORM has no equivalent}
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
