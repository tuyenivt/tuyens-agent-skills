---
name: system-boundary-design
description: Documents data ownership, contracts, failure isolation, and communication patterns for each module or service boundary in a system decomposition.
metadata:
  category: architecture
  tags: [architecture, boundaries, modules, decomposition, data-ownership]
user-invocable: false
---

# System Boundary Design

> Load `Use skill: stack-detect` first. Primary consumers: `task-decompose-monolith` Section 2, `task-consolidate-services` Section 3, `task-design-architecture` Section 2.

## When to Use

- Defining module or service boundaries during architecture design
- Decomposing a monolith into bounded contexts
- A new feature requires establishing data ownership across modules
- Evaluating whether to split or merge components

## Rules

- Boundaries are defined by data ownership, not code structure - packages alone are not boundaries. The rules apply unchanged to modular monoliths: an in-process module call is a Sync API contract
- Each boundary has an explicit contract (API, event, or shared-nothing = no runtime communication) and a failure-isolation guarantee stated per inbound dependent
- One module owns each entity exclusively; cross-boundary access goes through API or event, never direct DB queries. Deliberate read-only copies (e.g., price snapshotted onto an order) are allowed - record them as Data replication with the owner authoritative
- Shared mutable state across boundaries is a smell; if intentional, make it explicit
- Owner is the accountable team. One team may own several boundaries; if no team is named, write TBD - do not invent owners

## Pattern

### Boundary entry

**Bad** - no ownership or isolation:

```
Module: OrderService
Does: Order stuff
Uses: Some tables in the shared database
```

**Good** - explicit ownership and isolation:

```
Module: OrderService
Owns: Order, OrderLineItem, OrderStatus
Exposes: POST /orders, GET /orders/{id}, OrderCreatedEvent, OrderCompletedEvent
Hidden: Internal state machine, pricing calculation, DB schema
Failure Isolation: OrderService failure does not affect PaymentService reads; pending payments remain queued
```

Contracts are listed at capability level (endpoints and event types, not payload schemas). Exposed Contract lists only what the boundary provides; contracts it consumes appear as Communication Map rows. Internal queues or workers own no data and are not boundaries - record them under Hidden Internals. A contested entity (refunds: orders or payments?) is assigned to the boundary that owns its lifecycle writes; everyone else reads via API, event, or replication.

### Communication patterns

This table is the canonical Pattern enum for the Communication Map.

| Pattern          | Use When                               | Trade-off                        |
| ---------------- | -------------------------------------- | -------------------------------- |
| Sync API (REST)  | Caller needs immediate response        | Temporal coupling, latency chain |
| Async event      | Consumer can process later             | Eventual consistency, complexity |
| Shared cache     | Read-heavy, staleness acceptable       | Invalidation risk, stale reads   |
| Data replication | Consumer needs local query flexibility | Sync lag, storage cost           |

### Decomposition signals

**Split when** two teams need independent deploys, data ownership is clearly separable, failure in one part should not affect the other, or scaling requirements differ significantly.

**Keep together when** strong transactional consistency is required between entities, data is tightly coupled and queried together, or splitting would force distributed transactions.

**When signals conflict** (consistency says merge, failure isolation says split), consistency wins: keep the data in one boundary and isolate the failing concern inside it (internal queue or worker) instead of splitting the data. A stated target architecture outranks this tie-break - apply it only when the decision is open, and name any overridden signal in the rationale.

## Output Format

```markdown
## System Boundary Design

### Boundary Definitions

| Boundary      | Owner  | Data Owned | Exposed Contract | Hidden Internals       | Failure Isolation     |
| ------------- | ------ | ---------- | ---------------- | ---------------------- | --------------------- |
| {module name} | {team} | {entities} | {APIs, events}   | {domain logic, schema} | {isolation guarantee} |

### Boundary Communication Map

| From     | To       | Pattern                                                   | Data Exchanged | Trade-off                        |
| -------- | -------- | --------------------------------------------------------- | -------------- | -------------------------------- |
| {module} | {module} | Sync API / Async event / Shared cache / Data replication  | {what crosses} | {coupling, latency, consistency} |
```

In a partially decomposed system, monolith-resident boundaries get rows too - note "in monolith" under Hidden Internals so the migration seam stays visible. Failure Isolation holds one clause per inbound dependent; move overflow to a note under the table.

When the task is a split/merge or placement decision, prepend this section:

```markdown
### Boundary Decision

**Recommendation:** {Split | Merge | New module | Extend {module}}

| Signal                  | Evidence        | Points To                                    |
| ----------------------- | --------------- | -------------------------------------------- |
| {decomposition signal}  | {scenario fact} | Split / Keep together / New module / Extend  |

{Rationale; name the tie-break applied if signals conflicted.}
```

Contracts may state idempotency obligations (e.g., consumers dedupe by event ID); the consistency mechanism itself belongs in `architecture-data-consistency` output, not here.

## Avoid

- Premature decomposition before understanding data access patterns
- Ignoring operational cost per boundary (networking, serialization, monitoring)
- Circular dependencies between boundaries - convert one direction to async or redraw the boundaries
