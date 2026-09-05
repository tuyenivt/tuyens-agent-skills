---
name: system-boundary-design
description: Documents data ownership, contracts, failure isolation, and communication patterns for each module or service boundary in a system decomposition.
metadata:
  category: architecture
  tags: [architecture, boundaries, modules, decomposition, data-ownership]
user-invocable: false
---

# System Boundary Design

> Primary consumers: `task-migrate-architecture` Sections 2 and 3, `task-design-architecture` Section 2. Boundaries are drawn from data ownership and communication shape, not from language or framework, so no stack detection is run here.

## When to Use

- Defining module or service boundaries during architecture design
- Decomposing a monolith into bounded contexts
- A new feature requires establishing data ownership across modules
- Evaluating whether to split or merge components

## Rules

- Boundaries are defined by data ownership, not code structure - packages alone are not boundaries. The rules apply unchanged to modular monoliths: an in-process module call is a Sync API contract, network or not
- Each boundary has an explicit contract and a failure-isolation guarantee stated per inbound dependent - what still works for each caller when this boundary fails. Where the boundary is the one being protected from a flaky upstream, state that in the same cell from the dependent's side ("checkout serves a cached level when the WMS feed stalls"), since it is the same guarantee read in the other direction. Shared-nothing means no data flows in or out at all, by any route - synchronous, asynchronous, or batch
- One module owns each entity exclusively; cross-boundary access uses one of the four communication patterns below and never a direct DB query into another boundary's tables. Deliberate read-only copies (e.g., price snapshotted onto an order) are Data replication with the owner authoritative
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

**Good** - explicit ownership and isolation, one value per table column:

```
Boundary: OrderService
Owner: Squad Commerce
Data Owned: Order, OrderLineItem, OrderStatus
Exposed Contract: POST /orders, GET /orders/{id}, OrderCreatedEvent, OrderCompletedEvent
Hidden Internals: Internal state machine, pricing calculation, DB schema
Failure Isolation: OrderService failure does not affect PaymentService reads; pending payments remain queued
```

Contracts are listed at capability level (endpoints and event types, not payload schemas), and may state an obligation the consumer must honour, such as deduping by event ID. Where the source describes a capability only as "internal", name the contract for what it does (`ReservationRequested`, `AuthorizePayment`) and mark it `(inferred)`, so a reader knows the name is yours and not the system's. Mark a Pattern `(inferred)` on the same terms when nothing states whether the call is synchronous or an event - that choice sets the failure isolation, so it should not look settled when it is not. Exposed Contract lists only what the boundary provides; contracts it consumes appear as Communication Map rows. Internal queues or workers own no data and are not boundaries - record them under Hidden Internals.

A contested entity is assigned to the boundary that owns its lifecycle writes; when several boundaries write its lifecycle, the one writing the terminal (completing) transition owns it. Refunds are the standard example, and the answer follows the writes rather than the name: where settlement writes the closing status, refunds belong to payments; where the order's own status machine writes it, they belong to orders. Everyone else reads through one of the four patterns. Record which write decided it in the Ownership Rationale line.

### Communication patterns

This table is the canonical Pattern enum for the Communication Map.

| Pattern          | Use When                               | Trade-off                        |
| ---------------- | -------------------------------------- | -------------------------------- |
| Sync API         | Caller needs immediate response        | Temporal coupling, latency chain |
| Async event      | Consumer can process later             | Eventual consistency, complexity |
| Shared cache     | Read-heavy, staleness acceptable       | Invalidation risk, stale reads   |
| Data replication | Consumer needs local query flexibility | Sync lag, storage cost           |

Copy the Pattern and Trade-off strings into the Communication Map verbatim; add to a Trade-off only where this system makes it concrete. Shared cache is shared mutable state across a boundary, so a row using it states in Data Exchanged why that is intended.

### Decomposition signals

**Split when** two teams need independent deploys, data ownership is clearly separable, failure in one part should not affect the other, or scaling requirements differ significantly.

**Keep together when** strong transactional consistency is required between entities, or splitting would force distributed transactions. Being queried together is a read-coupling signal, not a keep-together one: it points at Data replication or a Shared cache.

**New module when** the capability has its own data and no existing boundary owns that data; **Extend an existing module when** the capability reads and writes data that boundary already owns.

**When signals conflict** (consistency says merge, failure isolation says split), consistency wins: keep the data in one boundary and isolate the failing concern inside it (internal queue or worker) instead of splitting the data. The tie-break binds transactional consistency only - read-coupling ("queried together") is resolved with Data replication or Shared cache and does not force a merge. A stated target architecture outranks this tie-break - apply it only when the decision is open, and name any overridden signal in the rationale.

## Output Format

```markdown
## System Boundary Design

### Boundary Definitions

| Boundary      | Owner  | Data Owned | Exposed Contract | Hidden Internals       | Failure Isolation     |
| ------------- | ------ | ---------- | ---------------- | ---------------------- | --------------------- |
| {module name} | {team, or TBD} | {entities; "none - holds a replica of {owner}'s data" for a consumer-only boundary} | {APIs and event types, each with any obligation it places on consumers such as deduping by event ID; "none - consumes only"; "none (shared-nothing)"} | {domain logic, schema; "in monolith" while unextracted} | {one clause per inbound dependent; "n/a - no inbound dependents"} |

**Ownership Rationale:** {each contested entity, the boundary it went to, and the write that decided it; any placement a reader would not predict from the table; each conflicting signal overridden by the tie-break or by a stated target architecture. "None - every placement follows from data ownership" when clear. Where a Boundary Decision section is prepended, its rationale covers that one decision and this line covers the rest.}

### Boundary Communication Map

| From     | To       | Pattern                                                   | Data Exchanged | Trade-off                        |
| -------- | -------- | --------------------------------------------------------- | -------------- | -------------------------------- |
| {initiator}{ (external)} | {receiver} | Sync API / Async event / Shared cache / Data replication  | {what crosses; on a Data replication row the authoritative owner; on a Shared cache row why shared mutable state is intended here} | {the patterns table's trade-off, plus what makes it concrete here} |
```

`From` is the end that starts the flow, `To` is the end that receives it: the caller and the callee for a Sync API, the publisher and each subscriber for an Async event, the owner and the replica holder for Data replication. Where the source is not itself a boundary - an external system, or an ETL job - name it in `From` anyway and mark it `(external)`, so the seam is visible even though it gets no row of its own.

In a partially decomposed system, monolith-resident boundaries get rows too, marked "in monolith" under Hidden Internals so the migration seam stays visible. Failure Isolation overflow moves to a note under the table. A boundary with no cross-boundary data flow at all - sync, async, or batch - writes "none (shared-nothing)" and appears in no map row; an ETL-fed module does have a flow, so it is a Data replication consumer with one inbound row and "none - consumes only" as its contract. The map holds one row per From -> To pair: an event with N consumers yields N rows, and several sources feeding one consumer yield one row each. Where a consumer is an internal worker rather than a boundary, the row names the boundary that owns it, since the flow crosses a boundary even though the worker is not one. Name a flow the source material only implies, and mark it `(inferred)`.

Prepend this section only when the task IS a placement question - split, merge, keep, place anew, or absorb - naming the capability or entity in the Recommendation. Mapping a whole system does not become one because a contested entity turned up inside it: there the table is the answer and Ownership Rationale carries the reasoning, however many contests it resolves.

```markdown
### Boundary Decision

**Recommendation:** {Split | Merge | Keep as is | New module | Extend {module}}

| Signal                  | Evidence        | Points To                                              |
| ----------------------- | --------------- | ------------------------------------------------------ |
| {decomposition signal}  | {scenario fact} | Split / Merge / Keep as is / New module / Extend        |

{Rationale; name the tie-break applied if signals conflicted, and any signal it overrode.}
```

`Points To` and `Recommendation` use the same five values, so the recommendation is always one a signal row can point to. Where the consistency tie-break applies, "keep the data in one boundary" is `Merge` when the entities sit in different boundaries on the Boundary Definitions table today and `Keep as is` when they already share one - the table is the test, not team ownership or deploy cadence, since those are the pressures the tie-break is overriding. A merge that spans two owning teams keeps one Owner and records the other team's claim in Ownership Rationale.

The consistency mechanism behind a contract belongs in `architecture-data-consistency` output, not here.

## Avoid

- Premature decomposition before understanding data access patterns
- Ignoring operational cost per boundary (networking, serialization, monitoring)
- Circular dependencies between boundaries - convert one direction to async or redraw the boundaries
