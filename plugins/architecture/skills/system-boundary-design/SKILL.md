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

- Boundaries are defined by data ownership, not code structure - packages alone are not boundaries. The rules apply unchanged to modular monoliths: an in-process module call is a Sync API contract, network or not, and so is an in-process synchronous event bus, since what the code does decides the pattern
- Each boundary has an explicit contract and a failure-isolation guarantee stated per inbound dependent - callers, event subscribers, shared-cache readers, replica holders, and direct-DB readers and writers - what still works for each when this boundary fails, or the failure it sees when nothing does; a named non-boundary consumer (a team reading a dashboard) is covered under the boundary that serves it. Where the boundary is the one being protected from a flaky upstream, state that too, prefixed with the failing party ("when the WMS feed fails: checkout serves a cached level"), so every clause names which component failed. A boundary with no data flow in or out, by any route - synchronous, asynchronous, or batch - is isolated
- One module owns each entity exclusively; cross-boundary access uses one of the four communication patterns below and never a direct DB query into another boundary's tables. Read-only copies held in the consumer's own schema and fed by the owner's events, an outbox-based CDC stream or an export (a catalog projected into search) are Data replication with the owner authoritative; a value captured at a point in time (a price snapshotted onto an order) is the capturing boundary's own data; a read replica of the owner's tables, or CDC tailing its internal tables, is a Direct DB read (violation). A column in another boundary's table is that boundary's schema, whoever owns the value conceptually
- Shared mutable state across boundaries is a smell; if intentional, make it explicit
- Owner is the accountable team. One team may own several boundaries; if no team is named, or more than one is named with no decision between them, write TBD - do not invent owners. An internal worker is owned by its parent boundary's team; a differing deploy cadence for it is a split signal, recorded in the Boundary Decision rationale when that worker's boundary is the decision's subject and otherwise in Ownership Rationale, not a second owner

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
Failure Isolation: when OrderService fails: PaymentService keeps processing already-published OrderCreatedEvents from its queue; when OrderService fails: POST /orders and GET /orders/{id} callers get errors and retry
```

Contracts are listed at capability level (endpoints and event types, not payload schemas), and may state an obligation the consumer must honour, such as deduping by event ID. Where the source describes a capability only as "internal", name the contract for what it does (`ReservationRequested`, `AuthorizePayment`) and mark it `(inferred)`, so a reader knows the name is yours and not the system's. Mark a Pattern `(inferred)` on the same terms when nothing states whether the call is synchronous or an event - that choice sets the failure isolation, so it should not look settled when it is not. Exposed Contract lists only what the boundary provides; contracts it consumes appear as Communication Map rows. Internal queues or workers are reached only through their parent, so they are not boundaries - record them under Hidden Internals, as you do a cache shared only among one boundary's own instances. A webhook is a Sync API contract on the receiver that carries an event; what the code does decides the Pattern, not what the hook is named.

A contested entity is assigned to the boundary that owns its lifecycle writes; when several boundaries write its lifecycle, the one writing the terminal (completing) transition owns it. Refunds are the standard example, and the answer follows the writes rather than the name: where settlement writes the closing status, refunds belong to payments; where the order's own status machine writes it, they belong to orders. Every other boundary reads through one of the four patterns and requests lifecycle changes through the owner's Exposed Contract. Record which write decided it in the Ownership Rationale line, or in the Boundary Decision rationale when the entity is that decision's subject.

### Communication patterns

This table, plus `Direct DB read (violation)` and `Direct DB write (violation)` for an existing violation, is the canonical Pattern enum for the Communication Map.

| Pattern          | Use When                               | Trade-off                        |
| ---------------- | -------------------------------------- | -------------------------------- |
| Sync API         | Caller needs immediate response        | Temporal coupling, latency chain |
| Async event      | Consumer can process later             | Eventual consistency, complexity |
| Shared cache     | Read-heavy, staleness acceptable       | Invalidation risk, stale reads   |
| Data replication | Consumer needs local query flexibility | Sync lag, storage cost           |

Copy the Pattern and Trade-off strings into the Communication Map verbatim, appending `(inferred)` to a Pattern the source does not state; add to a Trade-off only where this system makes it concrete. A direct query into another boundary's tables is `Direct DB read (violation)` with the trade-off "couples to the owner's schema - convert to Data replication or a Sync API"; a direct write into them is `Direct DB write (violation)` with the trade-off "couples to the owner's schema and bypasses its invariants - convert to a Sync API or Async event to the owner". Shared cache is shared mutable state across a boundary, so a row using it states in Data Exchanged why that is intended; its `From` is the boundary that writes the cache and its `To` the one that reads it.

### Decomposition signals

**Split when** two teams need independent deploys, data ownership is clearly separable, failure in one part should not affect the other, or scaling requirements differ significantly.

**Keep together when** strong transactional consistency is required between entities, or splitting would force distributed transactions. Being queried together is a read-coupling signal, not a keep-together one: it never blocks a split, and is recorded with Data replication, or a Shared cache whose map row states why the shared state is intended, named in the rationale, pointing at whatever the remaining signals point to. A keep-together signal points at `Keep as is` when the entities already share a boundary on the Boundary Definitions table as drawn before this decision, `Merge` when they sit in different boundaries there, and `Extend {module}` when the capability is new and must stay consistent with entities that module owns.

**New module when** the capability has its own data and no existing boundary owns that data; **Extend an existing module when** the capability reads and writes data that boundary already owns. These two are for a new capability; `Split`, `Merge` and `Keep as is` are for entities that already exist.

**When signals conflict** (consistency says keep the data together, failure isolation says split), consistency wins: keep the data in one boundary and isolate the failing concern inside it (internal queue or worker) instead of splitting the data. The tie-break binds transactional consistency only - read-coupling is resolved as above and does not force a merge. A stated target architecture outranks this tie-break - apply it only when the decision is open, and name any overridden signal in the rationale.

## Output Format

```markdown
## System Boundary Design

### Boundary Definitions

| Boundary      | Owner  | Data Owned | Exposed Contract | Hidden Internals       | Failure Isolation     |
| ------------- | ------ | ---------- | ---------------- | ---------------------- | --------------------- |
| {module name} | {team, or TBD} | {entities} | {APIs and event types, each with any obligation it places on consumers} | {domain logic, schema, internal workers}{ (in monolith)} | {"when {this boundary} fails: {dependent} {what still works, or the failure it sees when nothing does}" per inbound dependent}{; "when {upstream} fails: {what this boundary still does}"} |

**Failure Isolation notes:** {only when a cell holds more than two clauses} {boundary}: {clauses beyond the first two}

**Ownership Rationale:** {contested entity -> boundary, deciding write; unpredicted placements; overridden signals; internal-worker split signals; a merged boundary's second team}

### Boundary Communication Map

| From     | To       | Pattern                                                   | Data Exchanged | Trade-off                        |
| -------- | -------- | --------------------------------------------------------- | -------------- | -------------------------------- |
| {initiator}{ (external)} | {receiver}{ (external)} | Sync API / Async event / Shared cache / Data replication / Direct DB read (violation) / Direct DB write (violation){ (inferred)} | {what crosses}{ (inferred flow)} | {the pattern's trade-off string}{; what makes it concrete here} |
```

Boundary Definitions values. `Data Owned` lists any Data replication copy as `replica of {owner}'s {entity}` (a read replica of the owner's tables is a Direct DB read and is not listed); a consumer-only boundary reads `none - replica of {owner}'s {entity} only` or `none - reads {owner}'s data through {pattern}`; `unknown - source names none` when the source names no data at all. `Exposed Contract` marks `(inferred)` the names you supplied, reads `none - consumes only` for a consumer-only boundary and `none (isolated)` for one with no data flow in or out. `Hidden Internals` appends `(in monolith)` while the boundary is unextracted, so the migration seam stays visible. `Failure Isolation` reads `n/a - no inbound dependents` when neither clause form applies; a cell keeps its first two clauses and the notes line carries the rest. `Ownership Rationale` reads `None - every placement follows from data ownership` when none of its slot items applies; where a Boundary Decision section is present, its rationale covers that one decision and this line covers the rest.

Communication Map values. `From` is the caller for a Sync API, the querying or writing boundary for a Direct DB read or write (violation), and the data source for every other pattern - publisher, cache writer, or owner; `To` is the callee, the boundary whose tables are touched, each subscriber, each reader, or the replica holder. A file or batch feed from an external system is Data replication with the external source authoritative. Where the source is an external system, name it in `From` and mark it `(external)`; an external receiver is marked the same way in `To`; neither gets a row of its own. Where an ETL job copies a boundary's data from events, an export or an outbox stream the owner publishes, `From` is the owning boundary and the job is named in Data Exchanged; an ETL job that queries the owner's tables or tails its internal tables is a `Direct DB read (violation)` with the consuming boundary in `From` and the job named in Data Exchanged. On a Data replication row Data Exchanged names the authoritative owner; on a Shared cache row it says why shared mutable state is intended here; a flow the source material only implies is marked `(inferred flow)`, and a read replica of another boundary's tables is still a direct read. The map holds one row per From -> To pair and Pattern: an event with N consumers yields N rows, and several sources feeding one consumer yield one row each. Where a consumer is an internal worker rather than a boundary, the row names the boundary that owns it, since the flow crosses a boundary even though the worker is not one. An isolated boundary appears in no map row; an ETL-fed module does have a flow, so it gets one map row per source under the ETL rule above and, when nothing depends on it, `none - consumes only` as its contract.

Insert the section below directly under `## System Boundary Design`, before `### Boundary Definitions`, only when the task IS a placement question - split, merge, keep, place anew, or absorb - naming the capability or entity in the Recommendation. Mapping a whole system does not become one because a contested entity turned up inside it: there the table is the answer and Ownership Rationale carries the reasoning, however many contests it resolves. For a placement question, Boundary Definitions and the map cover the boundaries the decision touches, not the whole system; otherwise a map of a design or target state covers the boundaries the source describes plus every existing boundary that exchanges data with one of them, and an existing boundary's Failure Isolation names only the dependents on the table or named in the source. The tie-break clause is emitted only when signals conflicted and no stated target architecture decided; the target-architecture clause only when one did.

```markdown
### Boundary Decision

**Recommendation:** {Split | Merge | Keep as is | New module | Extend {module}} - {capability or entity}

| Signal                  | Evidence        | Points To                                              |
| ----------------------- | --------------- | ------------------------------------------------------ |
| {decomposition signal}  | {scenario fact} | Split / Merge / Keep as is / New module / Extend {module} |

{Rationale}{; tie-break applied: consistency over {signal}}{; target architecture overrides {signal}}
```

`Points To` and `Recommendation` use the same five values, so the recommendation is always one a signal row can point to. Where the consistency tie-break applies, "keep the data in one boundary" is `Merge` when the entities sit in different boundaries on the Boundary Definitions table as drawn before this decision (for a greenfield design, the boundaries drawn so far) and `Keep as is` when they already share one; for a new capability it is `Extend {module}`, naming the module that owns the entities it must stay consistent with - that table is the test, not team ownership or deploy cadence, since those are the pressures the tie-break is overriding. A merge that spans two owning teams keeps one Owner, TBD when nothing decides between them, and records the other team's claim (both teams' claims under TBD) in the Boundary Decision rationale when that merge is the decision's subject, otherwise in Ownership Rationale. The consistency mechanism behind a contract belongs in `architecture-data-consistency` output, not here.

## Avoid

- Premature decomposition before understanding data access patterns
- Ignoring operational cost per boundary (networking, serialization, monitoring)
- Circular dependencies between boundaries - convert one direction to async or redraw the boundaries
