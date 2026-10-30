---
name: architecture-data-consistency
description: Select consistency strategy across data boundaries - strong vs eventual, outbox, saga, compensation, schema evolution, anomaly classification.
metadata:
  category: architecture
  tags: [consistency, distributed-systems, eventual-consistency, saga, outbox]
user-invocable: false
---

# Data Consistency Modeling

> Load `Use skill: stack-detect` first to determine the project stack. It is consumed in one place: each Risk's `Recommendation` names the mechanism in the primitives of the detected `Language`, `Framework`, `Database` and `ORM`. A broker or migration tool reaches this skill only as an `Additional` line (`Queue: Kafka`); where none is present, or a field is `unknown` or omitted, recommend by role ("the project's broker client") rather than guessing a product. Every pattern below is otherwise stack-agnostic.

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
| Cross-module, same DB            | Strong           | Shared transaction (couples modules - flag as future split cost) |
| Cross-service, separate DBs      | Eventual         | Outbox + events                      |
| Long-running multi-step process  | Eventual         | Saga (orchestrated or choreographed) |
| Read-heavy, staleness acceptable | Eventual         | CQRS + async sync                    |
| Multi-region writes              | Eventual         | Region-local strong + async replication |

### Outbox

Use when publishing an event must be atomic with a database write - the dual-write problem. A shared transaction is unavailable or unacceptable in practice: most brokers are not XA resource managers, and where two-phase commit is available (a JMS broker such as ActiveMQ, or Kafka's KIP-939 2PC participation, whose producer API is not public as of Kafka 4.4) it costs more in coupling and latency than the outbox it would replace.

```
1. Write business data + outbox row in same transaction
2. Background poller or CDC reads outbox
3. Publish event; mark row published
```

Guarantee: at-least-once. Consumers must be idempotent. Ordering holds only per partition or ordering key; where one entity's events can travel under different keys, or a poller publishes in parallel, the consumer checks a per-entity version and discards older events.

Good - an explicit boundary contract, as one Boundaries Assessed row:

| Boundary | Model | Pattern | Staleness Tolerance | Tolerated Anomaly | Concurrent-Writer Resolution | Recovery Mechanism |
| -------- | ----- | ------- | ------------------- | ----------------- | ---------------------------- | ------------------ |
| Order -> Payment | Eventual | outbox + events | <= 5s to payment initiation | Stale read | N/A - single writer | PaymentFailed reverts Order to PENDING_PAYMENT; DLQ with manual review; consumer dedupes on the outbox event ID (one per payment attempt, stable across redelivery - an order ID would also drop the retry after a revert) |

Bad - implicit assumption:

```
Order calls PaymentService REST inside the transaction.
```

### Saga

Use when a business operation spans services and each step must commit or compensate.

- **Orchestrated** - central coordinator drives steps and compensation. Prefer for four or more steps, branching compensation, or when one place must own saga state.
- **Choreographed** - services react to events and emit the next event. Prefer for up to three steps with stable ordering and no central visibility need.

Each step declares: forward action, compensating action, idempotency key.

Step ordering:

- Place compensatable steps first; non-compensatable steps (email, push notification) last
- Within the compensatable prefix, place the most failure-prone step earliest to minimize compensation scope
- Identify the **pivot transaction** - the go/no-go point, the first step that is neither compensatable nor safely retriable. Fail before it and the saga unwinds; commit it and the saga must run forward to completion, so every step after it has to be retriable until it succeeds - a later non-compensatable step is simply post-pivot.
- Example: reserve inventory (compensatable; stock-outs are the common failure, so it goes first) -> charge payment (compensatable by refund) -> issue invoice (pivot: a tax record cannot be withdrawn, and re-issuing would duplicate it) -> send confirmation (retriable)

External API steps:

- Always send an idempotency key so the call is safe to retry after a network failure
- Persist the response in the same local transaction as the next state change
- Compensation is a separate API call (e.g. refund), not a rollback
- On a lost response, query the external state before compensating - avoid double-refund

### Eventual Consistency Read Anomalies

For each eventually consistent boundary, name the tolerated anomaly and bound the window. Unknown tolerance is a risk that starts at Medium.

| Anomaly              | Cause                                                        | Acceptable when                                       |
| -------------------- | ------------------------------------------------------------ | ----------------------------------------------------- |
| Stale read           | Read issued before the event propagates                      | The window is bounded and documented                  |
| Read-your-writes break | The writer's next read is routed to a lagging replica       | The writer's surfaces show an optimistic pending state, or never re-read the value within the lag window |
| Monotonic-read break | Consecutive reads land on replicas at different lag           | Staleness is invisible at this surface (no ordering cue shown) |
| Read skew            | A concurrent commit lands between two reads of one operation  | The two values are never compared or totalled          |

Concurrent writers are a separate problem from these read anomalies: a lost update is a write conflict, resolved by the mechanism below rather than tolerated as a window. This holds inside one service too: two handlers writing the same row (a cancel endpoint and a settlement webhook) sit on the single-DB row of the matrix and still name a mechanism - a row lock or a status precondition.

Conflict resolution options: last-write-wins is cheapest and accepts silent loss - document what is lost; a CRDT merge converges deterministically without routing, but constrains the data type to one with a commutative, associative, idempotent merge, and still discards a concurrent value where the type is a last-writer-wins register; single writer per entity (by home region or ownership key) avoids conflicts entirely at the cost of routing every write to its owner. Name the chosen mechanism on every boundary that admits concurrent writers.

### Schema Evolution

- Additive only during rolling deploys (new columns nullable, new fields optional)
- Rename = add new + dual-write and backfill + migrate readers + stop writing the old field (relax its NOT NULL or give it a default first, then ignore it in the ORM, whose inserts otherwise include every mapped column) + remove old - five phases, each a separate deploy verified before the next. Migrating readers is the phase that makes the rename safe under version skew; it is not optional
- Never remove a column or field active code reads
- Event consumers tolerate unknown fields; producers never reuse field IDs
- Rolling deploys create version skew across deployables: treat old-version code <-> new schema (and event producer -> consumer across a durable broker or outbox, even within one deployable, since an old replica's events reach a new one mid-rollout) as boundaries in the assessment; only an in-process producer and consumer that never persist the event roll together and have no skew. Their Pattern is `additive, backward compatible` (the nullable-column or optional-field case above), `dual-field contract versioning` (a rename: both fields live until readers migrate), or the defect `rename in one deploy` / `removal while read`

## Output Format

Rows describe what the boundary does TODAY when reviewing something already built, and what it will do when designing something new. A document containing both a current-state and a proposed section is a design: assess the proposed state and let the current state inform the risks. Fixes for a current-state defect go in Risks, never silently into the row. Where the design's own mechanism contradicts a stated requirement (last-write-wins where a requirement demands one writer), the row carries the design's mechanism and the contradiction is a High risk.

One row per From -> To pair and Pattern; symmetric bidirectional replication is one row written `A <-> B`; a rolling deploy adds a `Version-skew` row beside each flow row whose schema or contract it changes - one per consumer flow row, never one for the topic (old code to new schema, producer to consumer); a design that changes none has no `Version-skew` row; a call whose result is never persisted is out of scope - a saga step of that kind (an email) appears in Saga Steps only. Where the boundary itself was derived rather than stated, suffix the Model with `(derived)`; a stated boundary with an unstated mechanism keeps a bare Model, writes `unstated - see Risks` as its Pattern, and gets the Medium risk. An at-least-once row - outbox, CQRS, or replication - states its consumer idempotency key under Recovery Mechanism; for row-level replication that is the row's primary key (replica identity), applied as an upsert so a re-applied change is a no-op. A defect Pattern row keeps the Model the design claims or implies (Strong for a synchronous call inside a transaction) and the Risk states what it actually delivers. A shared cache or read replica fed from another boundary's data is a boundary row - Model Eventual, Pattern `CQRS + async sync` when events or replication keep it current, else the matching defect. A write sequence spanning boundaries is a saga whether or not the design names one: emit its Saga Steps, with Compensation `undefined - see Risks` wherever none is defined. Severity in Risks reflects what the boundary can lose, not the instruction that raised it: an unconfirmed boundary starts at Medium and rises if its blast radius warrants.

```
## Data Consistency Assessment

Assessing: {current state as built | proposed design}

### Boundaries Assessed

| Boundary | Model | Pattern | Staleness Tolerance | Tolerated Anomaly | Concurrent-Writer Resolution | Recovery Mechanism |
| -------- | ----- | ------- | ------------------- | ----------------- | ---------------------------- | ------------------ |
| {e.g. Order -> Payment} | {Strong / Eventual / Version-skew}{ (derived)} | {database transaction / shared transaction / outbox + events / saga, orchestrated or choreographed / CQRS + async sync / region-local strong + async replication / additive, backward compatible / dual-field contract versioning / unstated - see Risks; the defect, as found or as proposed: synchronous call in transaction / unguarded dual write / fire-and-forget call, no retry / non-durable in-process queue / distributed transaction / stale cache without invalidation / direct read into another boundary's tables / rename in one deploy / removal while read} | {N/A / duration / unbounded} | {N/A, also where only a write conflict applies; the anomaly name from the table above; or "loss - see Risks" where delivery is not guaranteed} | {N/A - single writer / single writer by home region / single writer by ownership key / row lock or status precondition / last-write-wins, losing {what} / CRDT merge / unresolved - see Risks} | {N/A or description} |

### Saga Steps {only when a boundary uses saga; one table per saga}

#### {saga name}

| Step | Forward Action | Compensation | Idempotency Key |
| ---- | -------------- | ------------ | --------------- |
| {1. name} | {action} | {pre-pivot: the compensating action, or "undefined - see Risks" when the design names none / pivot step: "pivot - go/no-go, no compensation defined" / post-pivot: "none - retry until success"} | {key} |

### Schema Evolution Plan {only when a boundary's Pattern is dual-field contract versioning, rename in one deploy, or removal while read}

| Phase | Change | Verify Before Next Phase |
| ----- | ------ | ------------------------ |
| {1..5} | {add / dual-write and backfill / migrate readers / relax constraint and stop writing old / remove} | {check that gates the next deploy} |

**Ships as planned:** {yes | no - <the phases the design collapses or skips>}

### Risks

- [Severity: High | Medium | Low] {boundary} - {description}
  - Issue: {implicit assumption / dual write / lost message / missing recovery / distributed transaction / schema break / unknown staleness / stale cache / direct cross-boundary read / missing, per-retry, or retry-colliding idempotency key / unnamed conflict resolution / mechanism contradicts requirement / unsupported claim - a design statement ("backward compatible", "easy to reverse", a built-in conflict rule) the mechanism or technology does not deliver / unnamed anomaly / out-of-order delivery / saga step ordering / bounded retry after the pivot / blind external compensation / cross-module shared transaction / unconfirmed boundary}
  - Recommendation: {concrete mechanism, named in the detected stack's own primitives}

### No Risks Found {instead, when Risks is empty}

{State explicitly that all boundaries have explicit strategies}
```

Always produce the Boundaries Assessed table. A saga gets one row per boundary pair its steps cross, in step order, skipping steps whose result is never persisted; each row repeats the end-to-end completion bound as its Staleness Tolerance, or `unbounded` when the design states none. If a boundary is not defined, or is described without its mechanism, derive it from the described data flows, list it with its likely model, and flag a Medium risk per unconfirmed boundary.

## Avoid

- Deduping an at-least-once consumer on an entity ID that a legitimate retry reuses
- Compensating an external call without first reading its current state
