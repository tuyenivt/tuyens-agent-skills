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
- The idempotency check and the business operation run in a single transaction.
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

### In-flight duplicate

When a key exists with `status = 'processing'`, the original is still running. Return `409 Conflict` or `202 Accepted` with a `Retry-After` header. Do not start a second execution.

### Event / message consumer

```
# Bad - blind apply on every delivery
on payment_intent.succeeded(event):
    order.status = PAID
    order.save()

# Good - dedup by message ID, verify entity state
on payment_intent.succeeded(event):
    if dedup.insert(event.id) == 0: return    # already processed
    if order.status != AWAITING_PAYMENT: return  # out-of-order or replay
    order.status = PAID
    order.save()
```

External events may arrive out of order - check entity state, do not assume the event applies.

### Stack-specific application

After stack-detect, wire the pattern using the detected ecosystem:

- Use the framework's transaction management to wrap the dedup insert and business operation
- Use the engine's native conflict handling (`ON CONFLICT`, `INSERT IGNORE`, advisory locks)
- For HTTP, implement as middleware or a service wrapper
- For background jobs, leverage broker dedup features (Kafka exactly-once, SQS dedup ID) when available; otherwise dedup at the application layer

If the stack is unfamiliar, apply the rules above and recommend the user consult their framework's transaction docs.

## Output Format

Consuming workflows parse this structure.

```
## Idempotency Assessment

**Stack:** {detected language / framework}

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
- **Low**: Natural business key available but not used as the idempotency key

Omit "No Gaps Found" if gaps were listed.

## Avoid

- Relying on client retries without server-side protection
- Check-then-act outside a single transaction (race condition)
- Infinite retention of idempotency records (always TTL)
- Reusing the same key for semantically different operations (collisions across endpoints)
- Returning a fresh response on retry instead of the cached original
