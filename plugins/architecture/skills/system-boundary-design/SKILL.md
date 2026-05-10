---
name: system-boundary-design
description: Documents data ownership, contracts, failure isolation, and communication patterns for each module or service boundary in a system decomposition.
metadata:
  category: architecture
  tags: [architecture, boundaries, modules, decomposition, data-ownership]
user-invocable: false
---

# System Boundary Design

> Load `Use skill: stack-detect` first to determine the project stack. Primary consumers: `task-migrate-monolith-to-services` Section 2, `task-consolidate-services` Section 3, `task-design-architecture` Section 2.

## When to Use

- During architecture design to define module or service boundaries
- When decomposing a monolith into bounded contexts
- When a new feature requires establishing data ownership across modules
- When evaluating whether to split or merge components

## Rules

- Boundaries are defined by data ownership, not code structure (packages are not boundaries)
- Every boundary has an explicit contract (API, event, shared-nothing) and a failure-isolation guarantee
- One module owns each entity exclusively; cross-boundary access goes through API or event - never direct DB queries
- Shared mutable state across boundaries is a smell - make it explicit if intentional

## Pattern

### Boundary Definition

For each boundary, define:

1. **Owner** -- which module owns this boundary
2. **Data owned** -- entities and state managed exclusively by this module
3. **Contract** -- what is exposed (API endpoints, events published, queries available)
4. **Hidden** -- what must NOT leak across the boundary (domain internals, storage schema)
5. **Failure isolation** -- does a failure inside propagate outside?

### Good: Explicit boundary with ownership

```
Module: OrderService
Owns: Order, OrderLineItem, OrderStatus
Exposes: POST /orders, GET /orders/{id}, OrderCreatedEvent, OrderCompletedEvent
Hidden: Internal order state machine, pricing calculation logic, DB schema
Failure Isolation: OrderService failure does not affect PaymentService reads; pending payments remain in queue
```

### Bad: Boundary without ownership or isolation

```
Module: OrderService
Does: Order stuff
Uses: Some tables in the shared database
```

### Boundary Communication

| Pattern          | Use When                               | Trade-off                        |
| ---------------- | -------------------------------------- | -------------------------------- |
| Sync API (REST)  | Caller needs immediate response        | Temporal coupling, latency chain |
| Async event      | Consumer can process later             | Eventual consistency, complexity |
| Shared cache     | Read-heavy, staleness acceptable       | Invalidation risk, stale reads   |
| Data replication | Consumer needs local query flexibility | Sync lag, storage cost           |

### Decomposition Signals

Split a module when:

- Two teams need to deploy independently
- Data ownership is clearly separable
- Failure in one part should not affect the other
- Scaling requirements differ significantly

Keep together when:

- Strong transactional consistency is required between entities
- Data is tightly coupled and queried together
- Splitting would require distributed transactions

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
- Ignoring the operational cost of each boundary (networking, serialization, monitoring)
- Circular dependencies between boundaries - convert one direction to async or redraw the boundaries
