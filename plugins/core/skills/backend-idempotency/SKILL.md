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

- Repeated calls with the same idempotency key must return the same result without re-executing side effects.
- Idempotency state lives in the database (not memory, not cache alone).
- Database-local side effects: the idempotency check and the business operation run in a single transaction. External side effects (gateway, email): commit `processing` first - see Record schema and lifecycle.
- Use database-level uniqueness for atomicity (`INSERT ... ON CONFLICT`, `INSERT IGNORE`, or advisory locks). Never check-then-act.
- Set a TTL on stored idempotency records (typically 24-48h) to bound growth.
- Prefer natural business keys when one exists - they prevent duplicates across client sessions. Client-generated UUIDs are the fallback.

## Patterns

### Key strategy selection

| Strategy              | When to use                                                | Example                                                 |
| --------------------- | ---------------------------------------------------------- | ------------------------------------------------------- |
| Natural business key  | Operation has inherent uniqueness (one payment per order)  | `order_id + payment_type` as composite                  |
| Client-generated UUID | Generic POST endpoints with no natural key                 | `Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000` |
| Content hash          | Same payload should always produce the same result         | SHA-256 of normalized request body                      |
| Message ID            | Event consumer where the broker assigns an ID              | Kafka offset, SQS message ID, event `id`                |

### Atomic check-and-act

```sql
-- Bad - check-then-act races: two concurrent requests both pass the check
SELECT * FROM idempotency WHERE key = :k;   -- not found
-- ... execute business logic ...
INSERT INTO idempotency (key, ...) VALUES (:k, ...);

-- Good - atomic insert decides the winner
INSERT INTO idempotency (key, status) VALUES (:k, 'processing')
ON CONFLICT (key) DO NOTHING;
-- If 1 row inserted: this request proceeds.
-- If 0 rows inserted: another request owns the key - return its cached response.
```

### Record schema and lifecycle

Store enough to replay the original response: `key`, `status` (`processing | completed | failed`), `response_code`, `response_body`, `request_hash`, `expires_at`. If the same key arrives with a different `request_hash`, reject with `422` - never replay a response for a different payload.

- Side effects inside the database: dedup insert and business operation in one transaction. A crash rolls everything back, so a retry re-executes cleanly; `processing` is never observed by others.
- Side effects outside the database (payment gateway, email): commit `processing` first, execute, then commit `completed` with the response. A row stuck in `processing` past the operation timeout means outcome unknown - surface it for reconciliation, never silently re-execute.
- `completed` and `failed` both replay the stored response. `failed` records deterministic business failures (e.g., insufficient funds); transient errors roll back and leave no row, so retries re-execute.

### In-flight duplicate

When a key exists with `status = 'processing'`, the original is still running. Return `409 Conflict` or `202 Accepted` with a `Retry-After` header. Do not start a second execution.

### Event / message consumer

```
# Bad - blind apply on every delivery
on payment_intent.succeeded(event):
    order.status = PAID
    order.save()

# Good - dedup insert and state change in one transaction
on payment_intent.succeeded(event):
    with transaction:
        if dedup.insert(event.id) == 0: return       # already processed
        if order.status != AWAITING_PAYMENT: return  # out-of-order or replay
        order.status = PAID
        order.save()
# Crash mid-handler rolls back the dedup row too - redelivery reprocesses
# instead of silently dropping the event.
```

External events may arrive out of order - check entity state, do not assume the event applies.

### Stack-specific application

After stack-detect, wire the pattern using the detected ecosystem:

- Use the framework's transaction management to wrap the dedup insert and business operation
- Use the engine's native conflict handling (`ON CONFLICT`, `INSERT IGNORE`, advisory locks)
- For HTTP, implement as middleware or a service wrapper
- For background jobs, leverage broker dedup features (Kafka exactly-once, SQS dedup ID) when available; otherwise dedup at the application layer

If the stack is unfamiliar, apply the rules above, emit `unknown` for **Stack**, and recommend the user consult their framework's transaction docs. If no datastore has been chosen yet, state idempotency as a requirement on that choice - the store must support an atomic conditional insert (unique constraint or conditional write) - rather than deferring the assessment.

## Output Format

Consuming workflows parse this structure.

```
## Idempotency Assessment

**Stack:** {detected language / framework, or `unknown` if detection fails}

### Gaps

- [Severity: High | Medium | Low] {operation or endpoint} - {gap description}
  - Missing: {idempotency key | dedup table | transactional check | TTL}
  - Risk: {duplicate side effect - e.g., double charge, double publish, double insert}
  - Recommendation: {concrete pattern and mechanism for the detected stack}

### No Gaps Found

{State explicitly if idempotency is adequate - do not omit this section silently}
```

**Severity:**

- **High**: POST with financial or irreversible side effects lacking idempotency protection
- **Medium**: Event consumer without dedup, or check outside the transaction boundary
- **Low**: Natural business key available but not used as the idempotency key; missing TTL on idempotency records

Severity follows impact: escalate any gap to High when the duplicated side effect is financial or irreversible.

Omit "No Gaps Found" if gaps were listed.

## Avoid

- Relying on client retries without server-side protection
- Check-then-act outside a single transaction (race condition)
- Infinite retention of idempotency records (always TTL)
- Reusing the same key for semantically different operations (collisions across endpoints)
- Returning a fresh response on retry instead of the cached original
