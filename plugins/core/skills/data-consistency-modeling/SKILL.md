---
name: data-consistency-modeling
description: Consistency strategy selection across data boundaries
metadata:
  category: architecture
  tags: [consistency, distributed-systems, eventual-consistency, saga, outbox]
user-invocable: false
---

# Data Consistency Modeling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During architecture design to choose consistency models per data boundary
- When a feature spans multiple services or modules with separate data stores
- When deciding between strong consistency and eventual consistency
- When designing compensation or rollback strategies for distributed operations

## Rules

- Default to strong consistency within a single module boundary
- Eventual consistency is a choice, not an accident -- document the staleness tolerance
- Every eventually consistent boundary must have a defined recovery mechanism
- Distributed transactions (2PC) are a last resort -- prefer saga or outbox patterns
- Schema changes must be backward compatible during rolling deployments

## Pattern

### Consistency Decision Matrix

| Scenario                         | Model            | Pattern                                  |
| -------------------------------- | ---------------- | ---------------------------------------- |
| Single DB, single service        | Strong           | Database transaction (framework-managed) |
| Cross-module, same DB            | Strong (careful) | Shared transaction                       |
| Cross-service, separate DBs      | Eventual         | Outbox + events                          |
| Long-running multi-step process  | Eventual         | Saga (orchestrated or choreographed)     |
| Read-heavy, staleness acceptable | Eventual         | CQRS + async sync                        |

### Outbox Pattern

Use when: publishing an event must be atomic with a database write.

```
1. Write business data + outbox record in same transaction
2. Background poller or CDC reads outbox
3. Publish event to message broker
4. Mark outbox record as published
```

Guarantees: at-least-once delivery. Consumers must be idempotent.

### Saga Pattern

Use when: a business operation spans multiple services and each must commit or compensate.

- **Orchestrated** -- central coordinator drives steps and compensation
- **Choreographed** -- each service reacts to events and publishes next event

For each saga step:

- Forward action (what it does)
- Compensating action (how to undo if a later step fails)
- Idempotency guarantee (safe to retry)

### Good: Explicit consistency choice with trade-off

```
Boundary: Order -> Payment
Model: Eventual consistency via outbox pattern
Staleness Tolerance: Up to 5 seconds between order creation and payment initiation
Partial Failure: If payment fails, OrderCompensationService reverts order to PENDING_PAYMENT
Recovery: Dead-letter queue with manual review for unrecoverable payment failures
```

### Bad: Implicit consistency assumption

```
Order creates a payment by calling PaymentService REST API inside the transaction.
```

### Schema Evolution Strategy

- Additive changes only during rolling deployments (new columns nullable, new fields optional)
- Rename = add new + migrate + remove old (three-phase)
- Never remove a column that active code reads
- Event schema versioning: consumers must tolerate unknown fields

## Avoid

- Assuming strong consistency across service boundaries without distributed transactions
- Eventual consistency without defining staleness tolerance or recovery
- Distributed transactions (2PC) when saga or outbox suffices
- Schema changes that break backward compatibility during deployment
- Ignoring idempotency requirements for at-least-once delivery patterns
