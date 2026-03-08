---
name: system-boundary-design
description: Formal boundary modeling for module and service decomposition
metadata:
  category: architecture
  tags: [architecture, boundaries, modules, decomposition, data-ownership]
user-invocable: false
---

# System Boundary Design

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During architecture design to define module or service boundaries
- When decomposing a monolith into bounded contexts
- When a new feature requires establishing data ownership across modules
- When evaluating whether to split or merge components

## Rules

- Boundaries are defined by data ownership, not by code organization
- Every boundary must have an explicit contract (API, event, shared nothing)
- A module must not depend on the internal implementation of another module
- Shared mutable state across boundaries is a design smell -- make it explicit if intentional
- Boundary decisions must state failure isolation guarantees

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

### Data Ownership Rules

- One module owns each entity exclusively -- no shared tables across boundaries
- Cross-boundary data access uses APIs or events, never direct DB queries
- If two modules need the same data, one owns it and the other subscribes or queries

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

## Avoid

- Defining boundaries by code structure alone (packages are not boundaries)
- Shared databases across module boundaries without explicit ownership
- Boundaries without failure isolation assessment
- Premature decomposition before understanding data access patterns
- Ignoring the operational cost of each boundary (networking, serialization, monitoring)
