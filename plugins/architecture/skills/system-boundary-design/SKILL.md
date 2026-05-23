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

- Boundaries are defined by data ownership, not code structure (packages are not boundaries)
- Every boundary has an explicit contract (API, event, shared-nothing) and a failure-isolation guarantee
- One module owns each entity exclusively; cross-boundary access goes through API or event - never direct DB queries
- Shared mutable state across boundaries is a smell; if intentional, make it explicit

## Pattern

### Boundary entry (good vs bad)

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

### Boundary Communication

| Pattern          | Use When                               | Trade-off                        |
| ---------------- | -------------------------------------- | -------------------------------- |
| Sync API (REST)  | Caller needs immediate response        | Temporal coupling, latency chain |
| Async event      | Consumer can process later             | Eventual consistency, complexity |
| Shared cache     | Read-heavy, staleness acceptable       | Invalidation risk, stale reads   |
| Data replication | Consumer needs local query flexibility | Sync lag, storage cost           |

### Decomposition Signals

**Split when**: two teams need independent deploys; data ownership is clearly separable; failure in one part should not affect the other; scaling requirements differ significantly.

**Keep together when**: strong transactional consistency is required between entities; data is tightly coupled and queried together; splitting would require distributed transactions.

## Output Format

```markdown
## System Boundary Design

### Boundary Definitions

| Boundary      | Owner  | Data Owned | Exposed Contract | Hidden Internals       | Failure Isolation     |
| ------------- | ------ | ---------- | ---------------- | ---------------------- | --------------------- |
| {module name} | {team} | {entities} | {APIs, events}   | {domain logic, schema} | {isolation guarantee} |

### Boundary Communication Map

| From     | To       | Pattern                               | Data Exchanged | Trade-off                        |
| -------- | -------- | ------------------------------------- | -------------- | -------------------------------- |
| {module} | {module} | Sync API / Async event / Shared cache | {what crosses} | {coupling, latency, consistency} |

### Data Ownership Summary

| Entity   | Owning Boundary | Access Method for Others         | Consistency Model |
| -------- | --------------- | -------------------------------- | ----------------- |
| {entity} | {boundary}      | API / Event subscription / Cache | Strong / Eventual |
```

## Avoid

- Premature decomposition before understanding data access patterns
- Ignoring operational cost per boundary (networking, serialization, monitoring)
- Circular dependencies between boundaries - convert one direction to async or redraw the boundaries
