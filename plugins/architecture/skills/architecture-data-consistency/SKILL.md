---
name: architecture-data-consistency
description: Select consistency strategy across data boundaries - strong vs eventual, outbox, saga, compensation, schema evolution, anomaly classification.
metadata:
  category: architecture
  tags: [consistency, distributed-systems, eventual-consistency, saga, outbox]
user-invocable: false
---

# Data Consistency Modeling

> Load `Use skill: stack-detect` first to determine the project stack. It is consumed in one place: each Risk's `Recommendation` names the mechanism in the primitives of the detected Language, Framework, Database and ORM. Where a broker or migration tool is not among the detected fields, recommend by role ("the project's broker client") rather than guessing a product. Every pattern below is otherwise stack-agnostic.

## When to Use

- Designing how data flows across services or modules with separate stores
- Choosing between strong and eventual consistency for a specific boundary
- Defining compensation, rollback, or recovery for distributed operations
- Planning schema changes that ship during rolling deployments

## Rules

- Default to strong consistency inside a single module boundary
- Eventual consistency is a choice - document the staleness tolerance and recovery path
- Distributed transactions (2PC) are a last resort; prefer outbox or saga
- Strong consistency across services or regions costs availability during a partition (CAP) and write latency the rest of the time (PACELC's latency branch) - scope it per boundary and push back on blanket "strong everywhere" requirements
- At-least-once delivery requires idempotent consumers - state the idempotency key
- Schema changes during rolling deploys must be backward compatible

## Patterns

### Consistency Decision Matrix

| Scenario                         | Model            | Pattern                              |
| -------------------------------- | ---------------- | ------------------------------------ |
| Single DB, single service        | Strong           | Database transaction                 |
| Cross-module, same DB            | Strong (couples modules - flag as future split cost) | Shared transaction |
| Cross-service, separate DBs      | Eventual         | Outbox + events                      |
| Long-running multi-step process  | Eventual         | Saga (orchestrated or choreographed) |
| Read-heavy, staleness acceptable | Eventual         | CQRS + async sync                    |
| Multi-region writes              | Eventual         | Region-local strong + async replication |

### Outbox

Use when publishing an event must be atomic with a database write - the dual-write problem. A shared transaction is unavailable or unacceptable in practice: most brokers are not XA resource managers, and where two-phase commit is available (a JMS broker such as ActiveMQ, or Kafka 4.0's externally coordinated 2PC) it costs more in coupling and latency than the outbox it would replace.

```
1. Write business data + outbox row in same transaction
2. Background poller or CDC reads outbox
3. Publish event; mark row published
```

Guarantee: at-least-once. Consumers must be idempotent.

### Saga

Use when a business operation spans services and each step must commit or compensate.

- **Orchestrated** - central coordinator drives steps and compensation. Prefer for four or more steps, branching compensation, or when one place must own saga state.
- **Choreographed** - services react to events and emit the next event. Prefer for up to three steps with stable ordering and no central visibility need.

Each step declares: forward action, compensating action, idempotency key.

Step ordering:

- Place compensatable steps first; non-compensatable steps (email, push notification) last
- Within the compensatable prefix, place the most failure-prone step earliest to minimize compensation scope
- Identify the **pivot transaction** - the go/no-go point, the step that is neither compensatable nor safely retriable. Fail before it and the saga unwinds; commit it and the saga must run forward to completion, so every step after it has to be retriable until it succeeds.
- Example: reserve inventory (compensatable) -> charge payment (compensatable by refund) -> issue invoice (pivot: a tax record cannot be withdrawn, and re-issuing would duplicate it) -> send confirmation (retriable)

External API steps:

- Always send an idempotency key so the call is safe to retry after a network failure
- Persist the response in the same local transaction as the next state change
- Compensation is a separate API call (e.g. refund), not a rollback
- On a lost response, query the external state before compensating - avoid double-refund

Good - an explicit boundary contract, as one Boundaries Assessed row:

| Boundary | Model | Pattern | Staleness Tolerance | Tolerated Anomaly | Concurrent-Writer Resolution | Recovery Mechanism |
| -------- | ----- | ------- | ------------------- | ----------------- | ---------------------------- | ------------------ |
| Order -> Payment | Eventual | outbox + events | <= 5s to payment initiation | Stale read | N/A - single writer | PaymentFailed reverts Order to PENDING_PAYMENT; DLQ with manual review; consumer dedupes on order ID |

Bad - implicit assumption:

```
Order calls PaymentService REST inside the transaction.
```

### Eventual Consistency Read Anomalies

For each eventually consistent boundary, name the tolerated anomaly and bound the window. Unknown tolerance is a Medium risk.

| Anomaly              | Cause                                                        | Acceptable when                                       |
| -------------------- | ------------------------------------------------------------ | ----------------------------------------------------- |
| Stale read           | Read issued before the event propagates                      | The window is bounded and documented                  |
| Read-your-writes     | The writer's next read is routed to a lagging replica         | The writer's own surfaces read from the primary        |
| Monotonic-read break | Consecutive reads land on replicas at different lag           | Staleness is invisible at this surface (no ordering cue shown) |
| Read skew            | A concurrent commit lands between two reads of one operation  | The two values are never compared or totalled          |

Concurrent writers are a separate problem from these read anomalies: a lost update is a write conflict, resolved by the mechanism below rather than tolerated as a window.

Conflict resolution, in order of increasing strength: last-write-wins is cheapest and accepts silent loss - document what is lost; single writer per entity (by home region or ownership key) avoids conflicts entirely at the cost of routing every write to its owner; a CRDT merge converges deterministically without routing, but constrains the data type to one with a commutative, associative, idempotent merge, and still discards a concurrent value where the type is register-like. Name the chosen mechanism on every boundary that admits concurrent writers.

### Schema Evolution

- Additive only during rolling deploys (new columns nullable, new fields optional)
- Rename = add new + dual-write and backfill + migrate readers + remove old - four phases, each a separate deploy verified before the next. Migrating readers is the phase that makes the rename safe under version skew; it is not optional
- Never remove a column or field active code reads
- Event consumers tolerate unknown fields; producers never reuse field IDs
- Rolling deploys create version skew: treat old-version code <-> new schema (and event producer -> consumer) as boundaries in the assessment

## Output Format

Rows describe what the boundary does TODAY when reviewing something already built, and what it will do when designing something new. A document containing both a current-state and a proposed section is a design: assess the proposed state and let the current state inform the risks. Fixes for a current-state defect go in Risks, never silently into the row.

One row per boundary, including each version-skew boundary a rolling deploy creates (old code to new schema, producer to consumer). Where boundaries were derived rather than stated, suffix the Model with `(derived)`. An at-least-once row - outbox, CQRS, or replication - states its consumer idempotency key under Recovery Mechanism. Severity in Risks reflects what the boundary can lose, not the instruction that raised it: an unconfirmed boundary starts at Medium and rises if its blast radius warrants.

```
## Data Consistency Assessment

Assessing: {current state as built | proposed design}

### Boundaries Assessed

| Boundary | Model | Pattern | Staleness Tolerance | Tolerated Anomaly | Concurrent-Writer Resolution | Recovery Mechanism |
| -------- | ----- | ------- | ------------------- | ----------------- | ---------------------------- | ------------------ |
| {e.g. Order -> Payment} | {Strong / Eventual / Version-skew}{ (derived)} | {database transaction / shared transaction / outbox + events / saga / CQRS + async sync / region-local strong + async replication / dual-field contract versioning; when reviewing, the defect as found: synchronous call in transaction / unguarded dual write / distributed transaction} | {N/A / duration / unbounded} | {N/A, or the anomaly name from the table above} | {N/A - single writer / single writer by home region / single writer by ownership key / last-write-wins, losing {what} / CRDT merge} | {N/A or description} |

### Saga Steps

{Only when a boundary uses saga; one table per saga, headed by the saga's name}

| Step | Forward Action | Compensation | Idempotency Key |
| ---- | -------------- | ------------ | --------------- |
| {1. name} | {action} | {pre-pivot: the compensating action / pivot step: "pivot - go/no-go, no compensation defined" / post-pivot: "none - retry until success"} | {key} |

### Schema Evolution Plan

{Only when a schema or event-schema change ships during rolling deploys}

| Phase | Change | Verify Before Next Phase |
| ----- | ------ | ------------------------ |
| {1..4} | {add / dual-write and backfill / migrate readers / remove} | {check that gates the next deploy} |

### Risks

- [Severity: High | Medium | Low] {boundary} - {description}
  - Issue: {implicit assumption / dual write / missing recovery / distributed transaction / schema break / unknown staleness / missing idempotency key / unnamed conflict resolution / unnamed anomaly / saga step ordering / blind external compensation / cross-module shared transaction / unconfirmed boundary}
  - Recommendation: {concrete mechanism, named in the detected stack's own primitives}

### No Risks Found

{State explicitly if all boundaries have explicit strategies - do not omit this section silently}
```

Always produce the Boundaries Assessed table. A saga gets one row per boundary pair it crosses; its Staleness Tolerance is the end-to-end completion bound. Omit "No Risks Found" only when risks were listed. If boundaries are not yet defined, derive candidates from the described data flows, list each with its likely model, and flag a Medium risk per unconfirmed boundary.

## Avoid

- Assuming strong consistency across service boundaries without distributed transactions
- Eventual consistency without a staleness bound or recovery path
- 2PC when an outbox or saga would suffice
- Schema changes that break old readers mid-deploy
- Non-compensatable steps placed before compensatable ones in a saga
- External API calls in sagas without idempotency keys
- Compensating an external call without first reading its current state
