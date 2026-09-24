---
name: node-transaction-patterns
description: Node.js transactions - no I/O inside tx, post-commit dispatch, outbox, savepoints, lock-then-write, lock/statement timeouts, reads outside tx.
metadata:
  category: backend
  tags: [node, typescript, prisma, typeorm, transactions, outbox, postgres]
user-invocable: false
---

> Load `Use skill: stack-detect` first; `ORM` picks the Prisma or TypeORM binding and `Database` the SQL dialect, and both surface in the core envelope's `**Stack:**` / `**Engine:**` lines. The raw SQL below is PostgreSQL's; on MySQL or an unknown engine, use `backend-transaction-patterns`' engine notes instead of these statements.
> The transaction boundary contract - no I/O inside a transaction, post-commit dispatch, call-then-record, outbox semantics, lock-then-write, timeouts - and the Transaction Assessment envelope are owned by `backend-transaction-patterns`. Load it first. This skill owns only the Node/ORM bindings for them. Dedup keys and consumer idempotency are `backend-idempotency`'s.

## When to Use

- Wrapping a multi-step write that must be atomic
- Dispatching side effects (BullMQ enqueue, HTTP webhook, mailer, payment) tied to a DB write
- Resolving "we sent the email but the row rolled back" / "worker picked up the job before the row was visible"
- Adding savepoints for partial-failure tolerance within a transaction
- Tuning `lock_timeout` / `statement_timeout` on a write path

## Rules

`backend-transaction-patterns` carries the contract. These are the Node-specific bindings and hazards it cannot state:

- Dispatch after `prisma.$transaction(...)` or `dataSource.transaction(...)` **resolves**, or via `runOnTransactionCommit` under `typeorm-transactional`
- Return scalars from the transaction callback. Under TypeORM an entity with lazy relations carried out of the transaction queries outside its snapshot (`EntityEscapesTransaction`); a Prisma object is a plain value and exempt
- I/O whose result **gates** the commit (a fraud score, a payment authorization) runs before `BEGIN`, and the transaction consumes an already-known outcome. I/O whose result must be **written back** (a charge and its reference) is call-then-record: commit a `pending` row with the request id, call outside any transaction, record the outcome in a second transaction - persist the attempt first whenever a duplicate call would cost money
- `SET LOCAL lock_timeout` / `statement_timeout` / `idle_in_transaction_session_timeout` run **inside** the transaction; standalone they are no-ops, and a plain `SET` leaks to every later query sharing the pooled connection - either is `MissingTransactionBounds`. Under `@Transactional()`, run them through the transactional entity manager's `.query()` as the first statement
- Prisma's interactive transaction has its own bounds - `maxWait` (pool acquisition, default 2s) and `timeout` (wall-clock, default 5s, rolls back when exceeded) - set per call or once via `new PrismaClient({ transactionOptions })`; its `timeout` covers the idle-in-transaction bound. TypeORM has no client-side wall-clock bound: set `lock_timeout`, `statement_timeout`, and `idle_in_transaction_session_timeout` (and on PostgreSQL 17+ `transaction_timeout`)
- A consistent multi-read snapshot needs an isolation level: PostgreSQL's default `READ COMMITTED` snapshots per statement. Prisma `{ isolationLevel: Prisma.TransactionIsolationLevel.RepeatableRead }`; TypeORM `dataSource.transaction("REPEATABLE READ", fn)`. Under `SERIALIZABLE`, and under `REPEATABLE READ` once the transaction writes, PostgreSQL may abort with `40001` - retry the whole transaction on Prisma `P2034` / TypeORM `QueryFailedError` with `driverError.code === "40001"`
- One outbox row per (event, destination): a single row fanning out to two consumers cannot record partial success
- Never dispatch from `@AfterInsert` / `@AfterUpdate`, a subscriber's `afterInsert` / `afterUpdate` / `beforeTransactionCommit`, or a pre-commit `EventEmitter2` listener - they fire before `COMMIT` and race it. A subscriber's `afterTransactionCommit` runs after `COMMIT` and may enqueue; it receives no entity, so stash the ids per query runner
- BullMQ `jobId` dedupes only while the job is retained, so `removeOnComplete` **and** `removeOnFail` must outlive the redelivery window (`{ age: <seconds> }`); a job id must not contain `:`

## Patterns

### Why I/O Inside a Transaction Is Wrong

```typescript
// Bad - holds a DB connection while waiting for Stripe; if a later step fails the order rolls
// back but the charge stays; the worker may pick the job before commit
await prisma.$transaction(async (tx) => {
  const order = await tx.order.create({ data });
  await stripe.paymentIntents.create({ amount, currency: "usd", customer });   // HTTP - DB conn held
  await queue.add("send-receipt", { orderId: order.id });                      // may run before commit
});
```

### Pattern A - Post-Commit Dispatch (best-effort side effects)

```typescript
// Prisma
const orderId = await prisma.$transaction(async (tx) => {
  const order = await tx.order.create({ data });
  await tx.orderItem.createMany({ data: items.map((i) => ({ ...i, orderId: order.id })) });
  return order.id;                          // scalar out
});
await queue.add("send-receipt", { orderId }, { jobId: `receipt-${orderId}` });
```

```typescript
// TypeORM with typeorm-transactional - the hook is fire-and-forget: catch, or an unhandled
// rejection (Redis down) crashes the process on Node 15+
@Transactional()
async place(input: PlaceOrderDto): Promise<string> {
  const order = await this.orders.save(Order.from(input));
  runOnTransactionCommit(() => {
    void this.queue.add("send-receipt", { orderId: order.id }, { jobId: `receipt-${order.id}` })
      .catch((err) => this.logger.error({ err, orderId: order.id }, "receipt enqueue failed"));
  });
  return order.id;
}
```

Failure mode: a crash between `COMMIT` and dispatch drops the side effect. Acceptable for receipts and analytics. A delivery whose result nobody needs back (an event, a contractual webhook) uses Pattern B; a call whose result must land on the row (a charge) uses Pattern C.

### Pattern B - Transactional Outbox (at-least-once)

```prisma
model OutboxMessage {
  id             String    @id @default(cuid())
  aggregateId    String
  eventType      String
  destination    String                       // one row per (event, destination)
  payload        Json
  createdAt      DateTime  @default(now())
  claimedAt      DateTime?
  claimedBy      String?
  claims         Int       @default(0)        // crashes
  attempts       Int       @default(0)        // failed dispatches
  lastError      String?
  processedAt    DateTime?
  deadLetteredAt DateTime?
  @@index([processedAt, deadLetteredAt, createdAt])
}
```

```typescript
// write - the outbox row commits atomically with the business write
await prisma.$transaction(async (tx) => {
  const order = await tx.order.create({ data });
  await tx.outboxMessage.create({ data: {
    aggregateId: order.id, eventType: "order.placed", destination: "customer-webhooks",
    payload: { orderId: order.id },
  } });
});

// relay - lease a batch (the claim commits before any dispatch), then dispatch outside any transaction
const claimed = await prisma.$queryRaw<OutboxRow[]>`
  UPDATE "OutboxMessage" SET "claimedAt" = now(), "claimedBy" = ${relayId}, claims = claims + 1,
    "deadLetteredAt" = CASE WHEN claims >= 20 THEN now() END            -- crash cap: parks in the claim
  WHERE id IN (
    SELECT id FROM "OutboxMessage"
    WHERE "processedAt" IS NULL AND "deadLetteredAt" IS NULL AND attempts < 10
      AND ("claimedAt" IS NULL OR "claimedAt" < now() - interval '5 minutes')
    ORDER BY "createdAt" LIMIT 100 FOR UPDATE SKIP LOCKED
  )
  RETURNING *`;

for (const m of claimed) {
  if (m.deadLetteredAt) continue;                              // crash cap reached - never dispatched
  const owned = { id: m.id, claimedBy: relayId, processedAt: null };
  const { count } = await prisma.outboxMessage.updateMany({ where: owned, data: { claimedAt: new Date() } });   // renew
  if (count === 0) continue;                                   // lease lost - another relay owns it now
  try {
    // the queue's connection sets enableOfflineQueue: false - with Redis down, add fails fast instead of outliving the lease
    await queue.add(m.eventType, m.payload, { jobId: m.id, removeOnComplete: { age: 86_400 }, removeOnFail: { age: 604_800 } });
    await prisma.outboxMessage.updateMany({ where: owned, data: { processedAt: new Date() } });
  } catch (e) {
    await prisma.outboxMessage.updateMany({ where: owned, data: {
      attempts: { increment: 1 }, lastError: String(e),
      ...(m.attempts + 1 >= 10 && { deadLetteredAt: new Date() }),
    } });
  }
}
// alert on deadLetteredAt IS NOT NULL - a parked row is a dropped message with a delay
```

The claim is a **lease**, not a completion mark: `processedAt` is set only after a successful dispatch, so a relay crash re-delivers the row once the lease expires, and the consumer's idempotency (the `jobId`, an idempotent handler) absorbs the replay. Every update after the claim is guarded by `claimedBy` and `processedAt: null`, so a relay that lost its lease stops instead of overwriting a row another relay processed. `attempts` caps failed dispatches (the `catch` dead-letters) and `claims` caps crashes (the claim itself dead-letters on the 21st claim), so no row parks with `deadLetteredAt` null. The dispatch is bounded below the lease: a BullMQ producer connection with `enableOfflineQueue: false` rejects while Redis is down. Without `SKIP LOCKED` the relays serialize on each other's rows (they do not double-dispatch).

### Pattern C - Call-Then-Record (the result is written back)

```typescript
// 1. commit the attempt - the request id is the idempotency key the vendor dedupes on
const payout = await prisma.payout.create({ data: { transferId, status: "PENDING", requestId: randomUUID() } });
// 2. call outside any transaction
let result: { id: string } | undefined;
try {
  result = await bank.createPayout({ amount, account }, { idempotencyKey: payout.requestId });
} catch (e) {
  if (classify(e).preAcceptance) await prisma.payout.update({ where: { id: payout.id }, data: { status: "FAILED" } });
  throw e;                                  // ambiguous: leave PENDING for the reconciliation sweeper
}
// 3. record the outcome in a new transaction
await prisma.payout.update({ where: { id: payout.id }, data: { status: "SENT", externalId: result.id } });
```

Step 1 may commit in the same transaction as the business write that creates the aggregate (a transfer and its pending payout); only the call runs outside. A `PENDING` row older than the vendor's timeout is outcome-unknown: a sweeper re-issues the call with the same request id (the vendor returns the original result) or queries the vendor, then records. The aggregate carries the pending state and a compensating action for a call that finally fails.

### Lock-Then-Write (Counters, Balances, State Machines)

```typescript
await prisma.$transaction(async (tx) => {
  // lock both rows in a fixed order (by id), or two opposite transfers deadlock
  const ids = [fromId, toId].sort();
  const rows = await tx.$queryRaw<{ id: string; balance: Prisma.Decimal }[]>`   // numeric -> Decimal
    SELECT id, balance FROM "Account" WHERE id IN (${ids[0]}, ${ids[1]}) ORDER BY id FOR UPDATE`;
  const from = rows.find((r) => r.id === fromId);
  if (!from || rows.length < 2) throw new NotFoundError("account");
  if (from.balance.lt(amount)) throw new InsufficientFundsError();
  await tx.account.update({ where: { id: fromId }, data: { balance: { decrement: amount } } });
  await tx.account.update({ where: { id: toId },   data: { balance: { increment: amount } } });
});
```

TypeORM: `m.find(Account, { where: { id: In(ids) }, order: { id: "ASC" }, lock: { mode: "pessimistic_write" } })` inside `dataSource.transaction`. Without the lock, two concurrent transactions both read the old balance and both decrement - lost update.

For a single-field decrement, an atomic guard is cheaper:

```typescript
const { count } = await prisma.account.updateMany({
  where: { id: accountId, balance: { gte: amount } },
  data:  { balance: { decrement: amount } },
});
if (count === 0) {
  // insufficient funds OR no such account - read by id to tell them apart before translating
}
```

### Write Transaction Timeouts

```typescript
await prisma.$transaction(async (tx) => {
  await tx.$executeRaw`SET LOCAL lock_timeout = '3s'`;
  await tx.$executeRaw`SET LOCAL statement_timeout = '5s'`;
  /* ... writes ... */
}, { maxWait: 1_000, timeout: 8_000 });   // tuned for this path; defaults are 2s / 5s
```

Without `lock_timeout`, a statement waiting on a row lock waits unbounded in both ORMs while holding its connection - Prisma's `timeout` rolls back an idle transaction but does not cancel a statement blocked on a lock. Without `statement_timeout`, one slow query holds its locks until the transaction ends.

### Read-Only Queries Outside Transactions

```typescript
// Bad - no atomicity benefit, pays the transaction overhead
const orders = await prisma.$transaction(async (tx) => tx.order.findMany({ where: { userId } }));

// Good
const orders = await prisma.order.findMany({ where: { userId } });
```

Transactions are for writes that must be atomic together; several reads needing one consistent snapshot take an isolation level (Rules).

### Savepoints (Use Sparingly)

```typescript
// TypeORM nested - the inner failure rolls back to the savepoint; the outer continues
await dataSource.transaction(async (tx) => {
  await tx.save(orderEntity);
  try {
    await tx.transaction(async (inner) => { await inner.save(optionalAuditEntity); });   // SAVEPOINT
  } catch (err) {
    logger.warn({ err }, "audit write failed");                  // swallowed on purpose, never silently
  }
});
```

Prisma has no nested `$transaction`: issue `` tx.$executeRaw`SAVEPOINT audit` ``, catch the inner failure and run `` ROLLBACK TO SAVEPOINT audit `` (otherwise every later statement fails with `25P02`), else `RELEASE SAVEPOINT audit`. Justified when a non-critical side write (audit log, denormalized view) must not roll back the main transaction.

## Output Format

Emit `backend-transaction-patterns`' output: when authoring, the code plus its `Dispatch` entries; when reviewing, diagnosing, or designing, its Transaction Assessment envelope, with the Node binding in every `Fix`. A build over existing code is authoring plus review - the envelope's findings for the existing defects the change touches, then the code. A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright gets one `Ruling:` line; both precede the envelope. The same violation in two transactions is two findings; within one transaction the core's grouping rule applies. In every mode, the block below is **additional** and follows the envelope (or the code, when authoring): one per boundary - each `$transaction` / `transaction()` call, each `@Transactional()` method, each relay claim, and each standalone write a pattern depends on (a call-then-record step, an atomic guard); a `Read-Outside-Tx` block goes on the read that was moved out - describing what it will be.

```
Pattern: {Post-Commit | Outbox | Call-Then-Record | Lock-Then-Write | Atomic-Guard | Savepoint | Read-Outside-Tx} - list every one that applies

ORM: {Prisma | TypeORM | <other> - generic bindings | unknown}

Transaction Scope: {what writes are inside, what was moved out, and what runs before BEGIN}

Side Effect Dispatch: {post-commit (after $transaction / dataSource.transaction resolves | runOnTransactionCommit) | outbox + relay | call-then-record | none}

Idempotency: {jobId / Idempotency-Key / unique constraint / state-transition guard (WHERE status = <from>) / N/A} - assessed by backend-idempotency

Timeouts: {Prisma maxWait + timeout | none (TypeORM)}; {PostgreSQL: SET LOCAL lock_timeout / statement_timeout / idle_in_transaction_session_timeout [/ transaction_timeout on 17+] | MySQL: session innodb_lock_wait_timeout + lock_wait_timeout set and reset, driver query timeout | unknown engine: bounds stated as requirements}

Failure Mode Documented: {what happens on a crash between commit and dispatch | none - no side effect}
```

## Avoid

- HTTP / queue / mailer calls inside `$transaction` - move them after commit, or use the outbox or call-then-record
- Returning TypeORM entities with lazy relations from inside a transaction and touching them afterwards
- Wrapping read-only queries in a transaction
- Chaining two `$transaction` calls where one would do - the gap is not atomic
- Side-effect listeners (`@AfterInsert`, a subscriber's pre-commit methods, EventEmitter2 fired pre-commit) that race the COMMIT
- An outbox relay without `FOR UPDATE SKIP LOCKED` - relay instances serialize on each other's rows
- Lock-then-write without a timeout - waits on contention with the connection held
- Setting `statement_timeout` globally on the DB role used by long-running migrations (it kills them)
- Savepoints to "make it more robust" - they add a partial-failure path for a rare case
