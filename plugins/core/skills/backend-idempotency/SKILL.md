---
name: backend-idempotency
description: Design and review idempotency for retryable POST endpoints and event consumers - keys, dedup tables, atomic check-and-act, TTL. Stack-adaptive.
metadata:
  category: integration
  tags: [idempotency, retries, integration, safety, multi-stack]
user-invocable: false
---

# Idempotency

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- POST or PATCH operations with side effects
- Operations retried over unreliable networks
- Event and message consumers (webhooks, queues, brokers)

## Rules

- Repeated calls with the same idempotency key must return the same result without re-executing side effects. The two exceptions: a key whose first execution is still in flight gets the in-flight response below, and a key re-sent with a different payload is rejected.
- Idempotency state lives in the database (not memory, not cache alone). A domain table whose natural key is unique (one posting per event id) is itself the store when the side effect is database-local: replay re-reads the domain row, mismatch compares the request to the stored fields, and there is no in-flight state to report. An external side effect always needs the key table below.
- Database-local side effects: the idempotency check and the business operation run in a single transaction that ends by writing the stored response. External side effects (gateway, email): commit `processing` first - see Record schema and lifecycle.
- Use database-level uniqueness for atomicity: a unique constraint plus a conditional insert (`INSERT ... ON CONFLICT DO NOTHING` on PostgreSQL 9.5+ and SQLite 3.24+; on MySQL a plain `INSERT` catching error 1062 - `ON DUPLICATE KEY UPDATE` row counts flip under the `CLIENT_FOUND_ROWS` driver flag, and `INSERT IGNORE` downgrades duplicate, null, and foreign-key errors alike to warnings). Never check-then-act, even inside a transaction. An advisory lock serializes concurrent attempts but stores nothing, so a later retry re-executes; it complements the unique constraint, never replaces it.
- A key is required, not optional, on an endpoint whose side effect is financial or irreversible: a request without one is rejected with `400`, never processed unprotected.
- Set a TTL on stored idempotency records. It bounds growth, but it also bounds the guarantee: once a record expires the same key executes again as new. Set it longer than the longest retry window any client or broker can produce (HTTP client retries run hours; SQS retention reaches 14 days; manual replays are the long tail), not to whatever keeps the table small. A domain-table unique key has no TTL; that is the point of using it.
- Prefer natural business keys when one exists - they prevent duplicates across client sessions and across re-emitted events. Client-generated UUIDs and broker message IDs are the fallback: a message ID dedups deliveries, the natural key dedups the effect.

## Patterns

### Key strategy selection

| Strategy              | When to use                                                | Example                                                 |
| --------------------- | ---------------------------------------------------------- | ------------------------------------------------------- |
| Natural business key  | Operation has inherent uniqueness (one payment per order)  | `order_id + payment_type` as composite                  |
| Client-generated UUID | Generic POST endpoints with no natural key                 | `Idempotency-Key: "550e8400-e29b-41d4-a716-446655440000"` |
| Content hash          | Same payload should always produce the same result         | SHA-256 of normalized request body                      |
| Message ID            | Event consumer deduplicating broker redelivery only - a producer publishing the same business event twice mints fresh broker IDs, so end-to-end dedup keys on the payload's event `id` or a natural key | Kafka `(topic, partition, offset)`, SQS `MessageId` (redelivery); RabbitMQ has none unless the producer sets `message_id`; payload event `id` (end-to-end) |

A consumer's dedup key is `(handler, event id)`: two handlers of one event never share a row. Each consumer group keeps its own dedup state; another group consuming the same topic is irrelevant to it.

### Atomic check-and-act

```sql
-- Bad - check-then-act races: two concurrent requests both pass the check
SELECT * FROM idempotency_keys WHERE idem_key = :k;   -- not found
-- ... execute business logic ...
INSERT INTO idempotency_keys (idem_key, ...) VALUES (:k, ...);

-- Good (PostgreSQL; SQLite 3.35+ for RETURNING) - the unique constraint decides the winner atomically
INSERT INTO idempotency_keys (idem_key, status, request_hash, expires_at)
VALUES (:k, 'processing', :hash, now() + :ttl)
ON CONFLICT (idem_key) DO NOTHING
RETURNING idem_key;
-- Row returned: this request owns the key - proceed.
-- No row: the conditional insert waited for the holder, so the holder has committed. Roll back this
--   transaction, then re-read in a new short transaction with a locking read held to its end
--   (SELECT ... FOR SHARE; MySQL 5.7 LOCK IN SHARE MODE; SQLite: a plain read inside a write transaction),
--   and branch inside it:
--   no row (a TTL sweep ran in between)  -> retry the insert once; a second miss is a 500
--   request_hash differs                 -> 422, whatever the status
--   processing                           -> in-flight response (below)
--   completed/failed                     -> replay the stored response
```

`idempotency_keys.idem_key` is declared `PRIMARY KEY` (or `UNIQUE`) - the constraint is the mechanism. `key` is a reserved word on MySQL; use a column name that is portable. MySQL: `INSERT` and catch 1062; `NOW() + INTERVAL :ttl_hours HOUR`; no `RETURNING`. SQLite: `datetime('now', '+' || :ttl_hours || ' hours')`. `:ttl` is set from the retry window (Rules), never a fixed literal.

### Record schema and lifecycle

Store enough to replay the original response and to reconcile: `idem_key`, `status` (`processing | completed | failed`), `request_hash`, `response_code`, `response_body`, `expires_at`, and for external side effects `provider_key` (the idempotency key sent to the provider) and `correlation_id` (stored in the provider's metadata); the domain row holds what is needed to rebuild the provider request. If the same key arrives with a different `request_hash`, reject with `422` - never replay a response for a different payload.

- Side effects inside the database: dedup insert, business operation, and the `UPDATE ... SET status = 'completed', response_code, response_body` in one transaction. A crash rolls everything back, so a retry re-executes cleanly; `processing` is never observed by others, and a transient error leaves no row.
- Side effects outside the database (payment gateway, email): commit `processing` first, execute, then commit `completed` with the response. A row stuck in `processing` past the operation timeout means outcome unknown - never silently re-execute. Reconciliation is a designed component, not a note: a periodic sweeper queries rows in `processing` older than the timeout and resolves each against the provider - within the provider's key lifetime (Stripe: 24 hours from first use) re-send the same request with `provider_key` and take the recorded outcome (a provider `409` means still in flight: wait, do not resend); past that lifetime look the operation up by `correlation_id`, never re-send - alerting on any it cannot settle. The timeout is the provider's own maximum response time plus a margin - shorter and you sweep live operations, longer and money sits unreconciled. An endpoint with external side effects and no sweeper is an incomplete implementation.
- `completed` and `failed` both replay the stored response. `failed` records deterministic business failures (e.g., insufficient funds).

### In-flight duplicate

When a key exists with `status = 'processing'`, the original is still running. Return `409 Conflict` (the response the Idempotency-Key draft specifies), optionally with `Retry-After` as advice. Do not start a second execution.

### Event / message consumer

```
# Bad - blind apply on every delivery
on payment_intent.succeeded(event):
    order.status = PAID
    order.save()

# Good - dedup row and state change in one transaction (database-local effect: no status column needed)
on payment_intent.succeeded(event):
    try:
        with transaction:
            if dedup.insert(handler, event.id, expires_at) == 0:   # the insert waited for the holder: it committed,
                return                                            # so the effect is applied - drop the redelivery
            if order.status == PAID: return               # terminal state - keep the dedup row, drop
            if order.status != AWAITING_PAYMENT:          # not applicable yet - roll back so nothing is recorded
                raise NotYetApplicable
            order.status = PAID
            order.save()
    except NotYetApplicable:
        park(event)                                       # its own transaction; or nack / leave uncommitted
# Crash mid-handler rolls back the dedup row too - the next delivery reprocesses
# instead of silently dropping the event.
```

A competing delivery's conditional insert blocks on the unique index until the holder commits or aborts, so `0` always means applied and a holder that aborted lets the insert succeed; a consumer whose effect is external (a send, a charge) uses the HTTP-style key table with `processing` and the in-flight rule instead. `park` writes in its own transaction - anything written inside the rolled-back one is lost. Redelivery after a rollback is broker-specific: SQS and RabbitMQ redeliver after the visibility timeout or nack (SQS FIFO blocks the whole message group until a redrive policy's `maxReceiveCount` sends it to the DLQ, or until retention expires when no redrive policy is set); Kafka does not - the consumer must not commit the offset and must `seek` back to it, or a later commit skips the record for good; Celery re-executes on `acks_late=True` worker loss and on `autoretry_for`, both retry paths the dedup must cover. External events may arrive out of order - check entity state, and distinguish "already applied" (consume) from "not applicable yet" (leave unconsumed) so the event is never lost; an event consumed without its effect applied is a lost event and in scope here.

### Stack-specific application

After stack-detect, wire the pattern using the detected ecosystem:

- Use the framework's transaction management to wrap the dedup insert, business operation, and completion write
- Use the engine's native conflict handling (`ON CONFLICT`, error 1062)
- For HTTP, implement as middleware or a service wrapper
- For background jobs, broker dedup covers only part of the flow: SQS FIFO deduplication IDs suppress duplicates for a fixed 5-minute window; Kafka exactly-once covers consume-transform-produce within Kafka. A consumer writing to an external store, or any retry window longer than the broker's, still needs application-layer dedup

When `Language` is `unknown`, apply the rules above, write `unknown` for **Stack**, and carry the framework-docs recommendation in the `Notes` line. If no datastore has been chosen yet, state idempotency as a requirement on that choice - the store must support an atomic conditional insert (unique constraint or conditional write) - as a `Gaps` entry with `Missing: store capability`.

## Output Format

Consuming workflows parse this structure. Order gaps by severity, High first. The stack-detect block is not emitted; its values fill the Stack line.

```
## Idempotency Assessment

**Stack:** {language / framework | unknown}

**Notes:** {"consult the framework's transaction docs to wire the pattern" when Stack is unknown | omitted otherwise}

### Gaps                                        {when at least one gap}

- [Severity: High | Medium | Low] {operation or endpoint} - {gap description}
  - Missing: {one or more, comma-separated: idempotency key, key not required, natural key unused, natural key not unique, dedup table, atomic conditional insert, transactional check, retry bound on re-read, processing commit before external call, completion write, reconciliation sweeper, reconciliation fields (provider key, correlation id), provider key lifetime, entity-state guard, in-flight response, handler-qualified key, payload mismatch guard, TTL (absent or shorter than the retry window), store capability}
  - Risk: {the duplicate or lost effect - e.g., double charge, double publish, double insert, lost event}
  - Recommendation: {concrete pattern and mechanism for the detected stack, citing the file where the fix lands even when it is outside the reviewed set, or the design component that must carry it}

### No Gaps Found                               {instead, when none: one sentence stating idempotency is adequate}
```

**Severity** - by the consequence of the defect (a duplicate or a lost effect), not by which element is missing:

- **High**: the duplicated or lost effect is financial or irreversible (a charge, a refund, an order shipped, an email or webhook sent, a payment event consumed unapplied), whatever element is missing - including a TTL shorter than the retry window and a key that is accepted but not required
- **Medium**: the duplicate or loss is a recoverable database write (a consumer without dedup on an idempotent update, a missing entity-state guard on a non-financial entity)
- **Low**: hygiene with no duplicate reachable today - a natural business key available but not used, a dedup key not qualified by handler where only one handler exists

One `Gaps` entry per operation, where an operation is one side effect with its own retry path (the endpoint's dedup and the gateway call it makes are two entries when their fixes differ); every missing element of that operation goes in its one `Missing` list. The reviewed set is the named operations; a defect in an adjacent file is reported when it sits on a named operation's retry path. In design mode (no code yet), `Gaps` holds the requirements the design must satisfy, with `Risk:` stating the consequence if omitted; a review mixing implemented and proposed side effects handles each in its own entry, and the code decides which is which when a document's labels are stale.

## Avoid

- Relying on client retries without server-side protection
- Check-then-act, inside or outside a transaction (race condition)
- Infinite retention of idempotency-key records (always TTL); domain-table unique keys are not records and keep no TTL
- Reusing the same key for semantically different operations (collisions across endpoints or handlers)
- Returning a fresh response on retry instead of the cached original
