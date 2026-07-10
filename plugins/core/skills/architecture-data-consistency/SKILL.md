---
name: architecture-data-consistency
description: Select consistency strategy across data boundaries - strong vs eventual, outbox, saga, compensation, schema evolution, anomaly classification.
metadata:
  category: architecture
  tags: [consistency, distributed-systems, eventual-consistency, saga, outbox]
user-invocable: false
---

# Data Consistency Modeling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing how data flows across services or modules with separate stores
- Choosing between strong and eventual consistency for a specific boundary
- Defining compensation, rollback, or recovery for distributed operations
- Planning schema changes that ship during rolling deployments

## Rules

- Default to strong consistency inside a single module boundary
- Eventual consistency is a choice - document the staleness tolerance and recovery path
- Distributed transactions (2PC) are a last resort; prefer outbox or saga
- Strong consistency across services or regions costs availability and write latency (CAP) - scope it per boundary and push back on blanket "strong everywhere" requirements
- At-least-once delivery requires idempotent consumers - state the idempotency key
- Schema changes during rolling deploys must be backward compatible

## Patterns

### Consistency Decision Matrix

| Scenario                         | Model            | Pattern                              |
| -------------------------------- | ---------------- | ------------------------------------ |
| Single DB, single service        | Strong           | Database transaction                 |
| Cross-module, same DB            | Strong (careful) | Shared transaction                   |
| Cross-service, separate DBs      | Eventual         | Outbox + events                      |
| Long-running multi-step process  | Eventual         | Saga (orchestrated or choreographed) |
| Read-heavy, staleness acceptable | Eventual         | CQRS + async sync                    |
| Multi-region writes              | Eventual         | Region-local strong + async replication |

### Outbox

Use when publishing an event must be atomic with a database write - the dual-write problem (DB and broker cannot share a transaction).

```
1. Write business data + outbox row in same transaction
2. Background poller or CDC reads outbox
3. Publish event; mark row published
```

Guarantee: at-least-once. Consumers must be idempotent.

### Saga

Use when a business operation spans services and each step must commit or compensate.

- **Orchestrated** - central coordinator drives steps and compensation. Prefer for 3+ steps, branching compensation, or when one place must own saga state.
- **Choreographed** - services react to events and emit the next event. Prefer for 2-3 steps with stable ordering and no central visibility need.

Each step declares: forward action, compensating action, idempotency key.

Step ordering:

- Place compensatable steps first; non-compensatable steps (email, push notification) last
- Within the compensatable prefix, place the most failure-prone step earliest to minimize compensation scope (compensatable-first wins if the two rules conflict)
- Identify the **pivot transaction** - the step after which the saga commits to forward-only completion. Steps before the pivot are reversible; steps after must succeed or be retried indefinitely.
- Example: reserve inventory (compensatable) -> charge payment (pivot) -> send confirmation (forward-only)

External API steps:

- Always send an idempotency key so the call is safe to retry after a network failure
- Persist the response in the same local transaction as the next state change
- Compensation is a separate API call (e.g. refund), not a rollback
- On a lost response, query the external state before compensating - avoid double-refund

Good - explicit boundary contract:

```
Boundary: Order -> Payment
Model: Eventual via outbox
Staleness: <= 5s between order creation and payment initiation
Failure: PaymentFailed event reverts Order to PENDING_PAYMENT
Recovery: DLQ with manual review for unrecoverable failures
```

Bad - implicit assumption:

```
Order calls PaymentService REST inside the transaction.
```

### Eventual Consistency Read Anomalies

For each eventually consistent boundary, name the tolerated anomaly and bound the window. Unknown tolerance is a Medium risk.

| Anomaly      | Cause                                       | Acceptable when                              |
| ------------ | ------------------------------------------- | -------------------------------------------- |
| Stale read   | Read before event propagates                | Window is bounded and documented             |
| Lost update  | Two writers update same entity concurrently | Never without explicit conflict resolution   |
| Phantom read | Background saga commits between reads       | Saga ordering or re-query strategy in place  |

### Schema Evolution

- Additive only during rolling deploys (new columns nullable, new fields optional)
- Rename = add new + dual-write/migrate + remove old (three-phase)
- Never remove a column or field active code reads
- Event consumers tolerate unknown fields; producers never reuse field IDs

## Output Format

```
## Data Consistency Assessment

### Boundaries Assessed

| Boundary | Model | Pattern | Staleness Tolerance | Recovery Mechanism |
| -------- | ----- | ------- | ------------------- | ------------------ |
| {e.g. Order -> Payment} | {Strong | Eventual} | {transaction | outbox | saga} | {N/A or duration} | {N/A or description} |

### Saga Steps

{Only when a boundary uses saga}

| Step | Forward Action | Compensation | Idempotency Key |
| ---- | -------------- | ------------ | --------------- |
| {1. name} | {action} | {action, or "pivot - forward-only after this"} | {key} |

### Risks

- [Severity: High | Medium | Low] {boundary} - {description}
  - Issue: {implicit assumption | dual write | missing recovery | distributed transaction | schema break | unknown staleness}
  - Recommendation: {concrete pattern for the detected stack}

### No Risks Found

{State explicitly if all boundaries have explicit strategies - do not omit this section silently}
```

Always produce the Boundaries Assessed table. Omit "No Risks Found" only when risks were listed. If boundaries are not yet defined, derive candidates from the described data flows, list each with its likely model, and flag a Medium risk per unconfirmed boundary.

## Avoid

- Assuming strong consistency across service boundaries without distributed transactions
- Eventual consistency without a staleness bound or recovery path
- 2PC when an outbox or saga would suffice
- Schema changes that break old readers mid-deploy
- Non-compensatable steps placed before compensatable ones in a saga
- External API calls in sagas without idempotency keys
- Compensating an external call without first reading its current state
