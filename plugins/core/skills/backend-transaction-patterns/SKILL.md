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

Owns the transaction **boundary** contract: what may run inside an open transaction, how side effects dispatch relative to commit, and how write transactions are bounded. Coordination *between* concurrent actors is `architecture-concurrency`'s (an in-process lock that fails to prevent a lost update is reported here as `LostUpdate`, since the missing guard is a boundary construct); dedup keys, replay semantics, and consumer idempotency are `backend-idempotency`'s findings, never reported here.

## When to Use

- Wrapping a multi-step write that must be atomic
- Dispatching a side effect (queue enqueue, HTTP call, email) tied to a database write
- Diagnosing "the email sent but the row rolled back" or "the worker ran before the row existed"
- Bounding a write path with lock, statement, and idle timeouts

## Rules

- **No I/O inside an open transaction.** No HTTP, no queue enqueue, no mailer, no third-party SDK. The connection is held for the duration of the network call, and a rollback cannot un-send what already left. I/O performed after commit but before the session is released still holds the connection: release first (`IoInSessionScope`).
- **Capture scalars inside, dispatch outside.** Return the IDs you need from the transaction, then perform side effects after commit returns. Never carry an ORM entity out and rely on its lazy relations.
- Single-statement reads run outside transactions - wrapping one buys no atomicity and costs pool pressure. A read-only transaction is justified only when several reads must see one consistent snapshot: `REPEATABLE READ` or `SERIALIZABLE` on PostgreSQL and InnoDB (PostgreSQL's default `READ COMMITTED` takes a snapshot per statement), `SNAPSHOT` isolation on SQL Server (its `REPEATABLE READ` is lock-based and still admits phantoms).
- One atomic unit is one transaction. Two sequential transactions have a non-atomic gap between them.
- Every write transaction is bounded three ways: a lock timeout, a statement timeout, and an idle-in-transaction timeout. The first two bound one wait and one statement; only the third catches a transaction sitting idle between statements while it holds locks - which is exactly what an I/O call inside a transaction produces.
- Lock-then-write when the new value depends on the current one (counters, balances, state machines). Skip the lock when a unique constraint or a conditional update already catches the conflict.
- Choose dispatch by durability requirement: post-commit dispatch for best-effort (notifications, analytics), transactional outbox for at-least-once (billing, contractual notifications). Outbox consumers must be idempotent; that requirement is stated in the `Dispatch` block and assessed by `backend-idempotency`.

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

### Post-Commit Dispatch (best-effort)

```
orderId = transaction:
    order = insert(orders, ...)
    insert(order_items, ..., orderId = order.id)
    return order.id                       -- scalar out, not the entity

queue.enqueue('send-receipt', orderId, dedupKey = "receipt:" + orderId)
analytics.track('order.placed', orderId)
```

Failure mode to document: a crash between commit and dispatch drops the side effect silently. Acceptable for receipts and analytics. Not acceptable for anything financial or contractual: a delivery whose result nobody needs back (an event, a contractual notification) goes through the outbox; a call whose result must land on the row (a payment charge and its reference) is Call-Then-Record below. Neither makes the external call atomic with the write; they move the leak from "money taken, no order" to "order committed, charge pending or parked", so the aggregate carries a `pending` state and a compensating action (void, refund, cancel) for a charge that finally fails.

### Call-Then-Record (I/O whose result is written back)

When the external call's result must land on the row (a gateway reference, a settled status), split it into three steps: commit the row as `pending` with the request id, call outside any transaction, then open a new transaction to record the outcome. A crash between the call and the record is the outcome-unknown case that `backend-idempotency`'s reconciliation sweeper resolves.

### Transactional Outbox (at-least-once)

The outbox row commits atomically with the business write, so a rollback discards both and there is no window where one exists without the other.

```
transaction:
    order = insert(orders, ...)
    insert(outbox, aggregateId = order.id, type = 'order.placed', payload = {...})

-- relay, running separately; the claim commits before any dispatch
claimed = transaction:
    UPDATE outbox
       SET claimed_at = now(), claimed_by = :relay_id, claims = claims + 1
     WHERE id IN (
       SELECT id FROM outbox
        WHERE processed_at IS NULL AND dead_lettered_at IS NULL
          AND attempts < :max_attempts AND claims < :max_claims
          AND (claimed_at IS NULL OR claimed_at < now() - interval '5 minutes')
        ORDER BY created_at LIMIT 20
        FOR UPDATE SKIP LOCKED)
    RETURNING *

for message in claimed:
    if UPDATE outbox SET claimed_at = now()                  -- renew the lease per message
        WHERE id = message.id AND claimed_by = :relay_id AND processed_at IS NULL
       returns 0 rows: break                                 -- lease lost: another relay owns the rest
    try:
        dispatch(message, timeout = :dispatch_timeout)       -- outside any transaction; bounded
        UPDATE outbox SET processed_at = now()
         WHERE id = message.id AND claimed_by = :relay_id AND processed_at IS NULL
    except DispatchError as e:                               -- record, continue the batch
        UPDATE outbox SET attempts = attempts + 1, last_error = :e,
               dead_lettered_at = CASE WHEN attempts + 1 >= :max_attempts THEN now() END
         WHERE id = message.id AND claimed_by = :relay_id
```

The details that carry the guarantee:

- **The claim is a lease, not a completion.** `processed_at` is set only after a successful dispatch. Marking it at claim time turns at-least-once into at-most-once, silently dropping any message whose relay crashed between claim and dispatch.
- **The claim commits before dispatch.** That is what keeps the network call out from under the row lock and off the connection.
- **The lease is owned and renewed.** The renewal, completion, and failure updates carry `claimed_by` and `processed_at IS NULL`, so a relay that lost its lease learns it (zero rows) and stops instead of overwriting a row a second relay has since processed; the dispatch timeout keeps one message from outliving the lease. Without the guard or the renewal, two relays dispatch the same row (`UnownedLease`).
- **Attempts count failed dispatches; claims count crashes.** `attempts` increments only when `dispatch` fails politely, so a crash at the head of a batch never burns an attempt for the rows behind it; `claims` increments at every claim with a higher cap (`:max_claims`) so a payload that crashes the relay is still dead-lettered. Past either cap the row is dead-lettered explicitly (`dead_lettered_at`, `last_error`) and a monitor alerts on it; a row that merely stops matching the claim predicate is parked silently, which is a dropped message with a delay.
- **`FOR UPDATE SKIP LOCKED`** lets multiple relay instances cooperate: without it a second relay blocks on the first's rows and the relays serialize (they do not double-dispatch; the row lock prevents that). PostgreSQL applies the locking clause before `LIMIT`, so each relay gets a full batch while enough unlocked rows exist.

`SKIP LOCKED`, `interval '5 minutes'`, and `RETURNING` above are PostgreSQL syntax; SQL Server uses `WITH (UPDLOCK, READPAST)` and the `OUTPUT` clause; MySQL 8.0+ has `SKIP LOCKED`, spells the interval `INTERVAL 5 MINUTE`, has no `RETURNING`, and rejects an `UPDATE` whose subquery reads the same table (error 1093) unless the subquery is a derived table that materializes (a `LIMIT` inside it, or a `NO_MERGE` hint - 8.0.14+ merges plain derived tables); SQLite has no row locks. On an unknown engine, state the claim as a requirement and name the mechanism engine-specific.

### Lock-Then-Write vs Atomic Guard

```
-- Lock-then-write: read the current value under a lock, decide, then write
BEGIN
  row = SELECT balance FROM wallets WHERE id = :id FOR UPDATE
  if row is null: ROLLBACK and fail (no such wallet)
  if row.balance < :amount: ROLLBACK and fail
  UPDATE wallets SET balance = balance - :amount WHERE id = :id
COMMIT
```

```
-- Atomic guard: the condition is part of the write
UPDATE wallets SET balance = balance - :amount
 WHERE id = :id AND balance >= :amount
-- zero rows: insufficient balance OR no such wallet - a follow-up read tells them apart
```

Without either, two concurrent transactions both read the old balance and both decrement, losing an update. Lock-then-write reads more clearly when several fields update conditionally; the atomic guard is cheaper for a single-field change. Pick one, never neither.

### Bounding the Write Transaction

Set the bounds transaction-scoped, inside the transaction. A session-scoped setting leaks to every later query sharing the pooled connection.

```
BEGIN
  SET LOCAL lock_timeout = '3s'                          -- stop waiting on a contended row
  SET LOCAL statement_timeout = '5s'                     -- stop a runaway statement holding locks
  SET LOCAL idle_in_transaction_session_timeout = '10s'  -- terminate the session when its open transaction idles between statements (9.6+)
  ...writes...
COMMIT
```

The idle timeout terminates the whole session, not just the transaction: locks and the pool slot are released and the driver sees a closed connection, which is the intended outcome for a transaction stuck behind an I/O call. Without a lock timeout, a transaction queued behind a row lock waits forever while holding its connection (PostgreSQL `lock_timeout` and SQL Server `LOCK_TIMEOUT` default to unbounded; InnoDB defaults to 50 s): pool exhaustion presents as a total outage with no slow query to blame. Do not apply a global statement timeout to the role that runs migrations; it will kill them mid-DDL. PostgreSQL 17 adds `transaction_timeout` for the whole transaction.

`SET LOCAL` is PostgreSQL. MySQL: the row-lock bound is `innodb_lock_wait_timeout` and the metadata-lock bound is `lock_wait_timeout` (both session-scoped: setting and resetting them around the transaction is required, and a bound left set on the session is `MissingTransactionBounds` - a leaked setting bounds the wrong transactions); there is no server-side statement timeout for writes (`max_execution_time` covers SELECT only) - bound writes with the driver's query timeout. On an unknown engine, state the bounds as requirements and name the mechanism engine-specific rather than emitting Postgres syntax.

### Savepoints

Justified only when a non-critical side write must be allowed to fail without rolling back the main one, such as an audit row or a denormalised projection. If the side write genuinely belongs with the main write, use one transaction and no savepoint. Reaching for savepoints to "make it more robust" adds a partial-failure path that then has to be reasoned about forever.

## Output Format

When authoring, apply Rules as constraints and emit the code plus one `Dispatch` entry per side effect. When reviewing, emit the block below. One finding per boundary defect: two missing bounds on one transaction are one `MissingTransactionBounds` finding listing both; two I/O calls in one transaction are two findings when their violations differ and one finding listing both sites when they match. A defect whose cause and symptom sit in two files anchors as `cause.ext:line -> symptom.ext:line`. Order findings by severity, High first.

```
## Transaction Assessment

**Stack:** {language / framework | unknown}

**Engine:** {database / version | unknown - bounds and claims stated as requirements}

### Findings                                    {when at least one finding}

- [Severity: High | Medium | Low] {file:line if available} - {description}
  - Violation: {IoInTransaction | IoInSessionScope | PreCommitDispatch | BestEffortOnDurableSideEffect | ReadInTransaction | SplitAtomicUnit | MissingTransactionBounds | LostUpdate | OutboxClaimAsCompletion | UnownedLease | RelayWithoutSkipLocked | MissingPoisonMessageCap | EntityEscapesTransaction | UnjustifiedSavepoint | DispatchUnspecified}
  - Risk: {one or more, comma-separated: pool exhaustion, pool pressure, side effect survives rollback, dispatch races commit, duplicated side effect, dropped side effect, poison message re-dispatched, message parked silently, partial write visible, lost update, unbounded lock wait, relay serialization, stale relation read, extra partial-failure path}
  - Fix: {concrete correction using the detected stack's transaction API; with Stack unknown, the construct named generically (transaction block, after-commit hook, outbox table); with Engine unknown, the requirement and the engine-specific mechanism to look up}

### No Findings                                 {instead, when none: one sentence stating the transaction boundaries are sound}

### Dispatch                                    {when the review or design covers a side effect - one entry per side effect}

- {side effect}: {post-commit | outbox + relay | call-then-record}, {best-effort | at-least-once | outcome-unknown pending reconciliation}; crash between commit and dispatch: {what happens}; consumer idempotency: {required - assessed by backend-idempotency | not needed}
```

Severity:

- **High**: I/O inside an open transaction; a side effect dispatched before commit; a lost update with no lock and no atomic guard; an outbox that marks completion at claim time; a financial or contractual side effect on best-effort dispatch (`BestEffortOnDurableSideEffect`).
- **Medium**: missing or session-leaked transaction bounds on a write path (pool exhaustion under contention, rated Medium because the outage needs a second fault to trigger it); I/O after commit with the session still held; one atomic unit split across two transactions; a relay whose completion updates are not lease-owned or renewed (`UnownedLease`, duplicated side effect); a relay claiming without a skip-locked mechanism on an engine that has one (`SKIP LOCKED`, `READPAST`); no attempts or claims cap, or no dead-letter, on the relay; a lazy-loading entity carried out of the transaction; a design that names a side effect but not its dispatch (`DispatchUnspecified`).
- **Low**: read-only query wrapped in a transaction (pool pressure); a savepoint used where one transaction would do.

In design mode with no code yet, list the risks the proposed design leaves open as Findings, omit `{file:line}`, and fill `Dispatch` for every side effect the design names. A construct outside the reviewed files that a finding depends on (the only caller of an outbox insert, the relay a design's "at-least-once" claim rests on) may be read to confirm the finding and is anchored at its own file when it is what breaks the reviewed write's guarantee; it is not otherwise a source of new findings.

## Avoid

- Returning a lazy-loading ORM entity out of a transaction and touching its relations afterwards; ORMs that return plain objects (Prisma) are exempt
- Lifecycle hooks that fire before or during commit (`afterInsert`, `after_save`, `BEFORE_COMMIT` listeners) for side effects; they race the commit. After-commit hooks (`after_commit`, `transaction.on_commit`, `AFTER_COMMIT`) run with the transaction's connection still bound and cannot release it themselves: use them to enqueue or schedule, and let the I/O run once the connection is returned - the Post-Commit Dispatch pattern
- An outbox relay without a skip-locked claim on an engine that has one; relay instances serialize on each other's rows
- Raising the pool acquisition timeout to "fix" exhaustion; it hides the shortage and lets requests pile up
