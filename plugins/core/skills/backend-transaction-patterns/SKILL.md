---
name: backend-transaction-patterns
description: Transaction boundary contract - no I/O inside a transaction, post-commit dispatch, transactional outbox, lock-then-write, lock and statement timeouts.
metadata:
  category: backend
  tags: [transactions, outbox, atomicity, locking, postgres, multi-stack]
user-invocable: false
---

# Transaction Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

Owns the transaction **boundary** contract: what may run inside an open transaction, how side effects dispatch relative to commit, and how write transactions are bounded. Coordination *between* concurrent actors is `architecture-concurrency`; dedup keys and replay semantics are `backend-idempotency`.

## When to Use

- Wrapping a multi-step write that must be atomic
- Dispatching a side effect (queue enqueue, HTTP call, email) tied to a database write
- Diagnosing "the email sent but the row rolled back" or "the worker ran before the row existed"
- Bounding a write path with lock and statement timeouts

## Rules

- **No I/O inside an open transaction.** No HTTP, no queue enqueue, no mailer, no third-party SDK. The connection is held for the duration of the network call, and a rollback cannot un-send what already left.
- **Capture scalars inside, dispatch outside.** Return the IDs you need from the transaction, then perform side effects after commit returns. Never carry an ORM entity out and rely on its lazy relations.
- Single-statement reads run outside transactions - wrapping one buys no atomicity and costs pool pressure. A read-only transaction is justified only when several reads must see one consistent snapshot.
- One atomic unit is one transaction. Two sequential transactions have a non-atomic gap between them.
- Every write transaction sets a lock timeout and a statement timeout. Without them a single blocked or runaway query holds its connection and its locks indefinitely.
- Lock-then-write when the new value depends on the current one (counters, balances, state machines). Skip the lock when a unique constraint or a conditional update already catches the conflict.
- Choose dispatch by durability requirement: post-commit dispatch for best-effort (notifications, analytics), transactional outbox for at-least-once (billing, contractual notifications).
- Outbox consumers must be idempotent. At-least-once means replay is normal, not exceptional.

## Patterns

### Why I/O Inside a Transaction Is Wrong

```
BEGIN
  order = insert(orders, ...)
  charge = paymentProvider.charge(...)     -- HTTP, connection held
  queue.enqueue('send-receipt', order.id)  -- worker may run before COMMIT
COMMIT
```

Three distinct failures from one mistake:

1. **Pool starvation.** The connection idles through the network round trip. Under load the pool drains and unrelated requests fail.
2. **Worker races the commit.** The consumer can dequeue and read before `COMMIT` is visible, finding no row.
3. **Rollback leaks the side effect.** The provider charged; the order rolled back. Money taken, nothing to show for it.

### Post-Commit Dispatch (default)

```
orderId = transaction:
    order = insert(orders, ...)
    insert(order_items, ..., orderId = order.id)
    return order.id                       -- scalar out, not the entity

queue.enqueue('send-receipt', orderId, dedupKey = "receipt:" + orderId)
paymentProvider.charge(amount, idempotencyKey = orderId)
```

Failure mode to document: a crash between commit and dispatch drops the side effect silently. Acceptable for receipts and analytics. Not acceptable for anything financial or contractual, which needs the outbox.

### Transactional Outbox (at-least-once)

The outbox row commits atomically with the business write, so a rollback discards both and there is no window where one exists without the other.

```
transaction:
    order = insert(orders, ...)
    insert(outbox, aggregateId = order.id, type = 'order.placed', payload = {...})

-- relay, running separately
claimed = UPDATE outbox SET claimed_at = now()
          WHERE id IN (
            SELECT id FROM outbox
            WHERE processed_at IS NULL
              AND (claimed_at IS NULL OR claimed_at < now() - interval '5 minutes')
            ORDER BY created_at LIMIT 100
            FOR UPDATE SKIP LOCKED
          )
          RETURNING *

for message in claimed:
    dispatch(message)                                    -- outside any transaction
    UPDATE outbox SET processed_at = now() WHERE id = message.id
```

Two details carry the guarantee, and both are easy to get wrong:

- **The claim is a lease, not a completion.** `processed_at` is set only after a successful dispatch. Marking it at claim time turns at-least-once into at-most-once, silently dropping any message whose relay crashed between claim and dispatch.
- **`FOR UPDATE SKIP LOCKED`** lets multiple relay instances cooperate without contending, and keeps dispatch out from under a row lock.

Increment an `attempts` column on each claim and park the row (dead-letter) past a cap; otherwise a poison message re-dispatches every lease interval forever.

### Lock-Then-Write vs Atomic Guard

```
-- Lock-then-write: read the current value under a lock, decide, then write
BEGIN
  row = SELECT balance FROM wallets WHERE id = :id FOR UPDATE
  if row.balance < :amount: ROLLBACK and fail
  UPDATE wallets SET balance = balance - :amount WHERE id = :id
COMMIT
```

```
-- Atomic guard: the condition is part of the write; zero rows affected means conflict
UPDATE wallets SET balance = balance - :amount
 WHERE id = :id AND balance >= :amount
```

Without either, two concurrent transactions both read the old balance and both decrement, losing an update. Lock-then-write reads more clearly when several fields update conditionally; the atomic guard is cheaper for a single-field change. Pick one, never neither.

### Bounding the Write Transaction

Set both timeouts transaction-scoped, inside the transaction. A session-scoped setting leaks to every later query sharing the pooled connection.

```
BEGIN
  SET LOCAL lock_timeout = '3s'        -- stop waiting on a contended row
  SET LOCAL statement_timeout = '5s'   -- stop a runaway query holding locks
  ...writes...
COMMIT
```

Without a lock timeout, a transaction queued behind a row lock waits forever while holding its connection: pool exhaustion presents as a total outage with no slow query to blame. Do not apply a global statement timeout to the role that runs migrations; it will kill them mid-DDL.

### Savepoints

Justified only when a non-critical side write must be allowed to fail without rolling back the main one, such as an audit row or a denormalised projection. If the side write genuinely belongs with the main write, use one transaction and no savepoint. Reaching for savepoints to "make it more robust" adds a partial-failure path that then has to be reasoned about forever.

## Output Format

```
## Transaction Assessment

**Stack:** {detected language / framework | unknown}

### Findings

- [Severity: High | Medium | Low] {file:line if available} - {description}
  - Violation: {IoInTransaction | PreCommitDispatch | ReadInTransaction | SplitAtomicUnit | MissingLockTimeout | MissingStatementTimeout | LostUpdate | OutboxClaimAsCompletion | NonIdempotentConsumer | EntityEscapesTransaction | UnjustifiedSavepoint}
  - Risk: {pool exhaustion | side effect survives rollback | dispatch races commit | duplicated side effect | dropped side effect | lost update | unbounded lock wait}
  - Fix: {concrete correction using the detected stack's transaction API}

### No Findings

{State explicitly when the transaction boundaries are sound - do not omit silently.}
```

When proposing or reviewing a dispatch path, also state, once per side effect:

```
Dispatch: {post-commit | outbox + relay}
Durability: {best-effort | at-least-once}
Crash Behavior: {what happens on a crash between commit and dispatch}
```

Severity:

- **High**: I/O inside an open transaction; a side effect dispatched before commit; a lost update with no lock and no atomic guard; an outbox that marks completion at claim time.
- **Medium**: missing lock or statement timeout on a write path; one atomic unit split across two transactions; a non-idempotent outbox consumer.
- **Low**: read-only query wrapped in a transaction; a savepoint used where one transaction would do.

Omit "No Findings" when findings were listed. In design mode with no code yet, list the risks the proposed design leaves open as Findings and omit `{file:line}`.

## Avoid

- Returning a lazy-loading ORM entity out of a transaction and touching its relations afterwards; ORMs that return plain objects (Prisma) are exempt
- Framework lifecycle hooks (`afterInsert`, pre-commit event listeners) for side effects; they race the commit
- An outbox relay without `SKIP LOCKED` on the claim; every relay instance dispatches the same rows
- Raising the pool acquisition timeout to "fix" exhaustion; it hides the shortage and lets requests pile up
