---
name: architecture-landscape
description: Build a landscape view of multiple systems - owners, stacks, integration points, data flows, and cross-system risks
metadata:
  category: architecture
  tags: [architecture, landscape, systems, portfolio, integration, cross-system]
user-invocable: false
---

# Architecture Landscape

> Composed by workflows; not invoked directly. Primary consumers: `task-consolidate-services` Section 1, `task-decompose-monolith` Section 3.

## When to Use

- A migration or design decision affects more than one system
- Assessing the current service landscape before consolidation or decomposition
- Building context from a docs repo rather than a live codebase
- Cross-system risks, redundancies, or stack divergence need to be surfaced

## Rules

- Map only what is known; mark entries Confirmed (documented or code-verified) vs Inferred (derived from config/naming)
- Integration entries state protocol, direction, and coupling separately - sync/async is protocol; tight/loose is coupling
- Risks cite landscape evidence (which services share what), not generic concerns
- Cite the source document for each system entry when reading from a docs repo

## Pattern

### Coupling vs Protocol

- **Protocol**: how the call travels (sync REST/gRPC, async event, batch)
- **Coupling**: how failure propagates - **Tight** = caller blocks on response and target failure propagates; **Loose** = caller continues on target failure

A sync call can be loose if the caller has a fallback; an async event can be tight if the consumer cannot make progress without it.

### Discovery when docs are incomplete

Read what is available; flag the rest as Inferred. Sources in decreasing reliability: code (HTTP clients, message-broker producers/consumers), infra config (gateway routes, service mesh, IaC), env vars and ConfigMaps for service hostnames, shared databases or FKs that reveal hidden coupling.

### Cross-System Risk Categories

- **Single points of failure** - systems whose failure takes multiple downstreams with them; shared infrastructure (DB, auth, broker) with no fallback
- **Shared data** - DBs, caches, queues with more than one writer; name the authoritative writer per shared resource
- **Missing capability** - a capability implied by the landscape but unowned (e.g., audit logging assumed but no audit service)

Stack divergence is a risk only when it causes operational friction or hiring strain - record it as an SPOF or shared-data risk row, not its own category.

## Output Format

```markdown
## System Landscape

### System Inventory

| System | Owner  | Stack   | Role           | Data Owned | Source     |
| ------ | ------ | ------- | -------------- | ---------- | ---------- |
| {name} | {team} | {stack} | {one sentence} | {entities} | {doc/code} |

### Integration Map

| From     | To       | Protocol            | Direction   | Coupling    | Confidence            | Notes     |
| -------- | -------- | ------------------- | ----------- | ----------- | --------------------- | --------- |
| {system} | {system} | REST/gRPC/event/... | Sync/Async  | Tight/Loose | Confirmed / Inferred  | {context} |

### Cross-System Risks

| Risk   | Category               | Affected Systems | Severity     | Evidence            |
| ------ | ---------------------- | ---------------- | ------------ | ------------------- |
| {risk} | SPOF/Shared/Missing    | {systems}        | High/Med/Low | {what reveals this} |

### Gaps

| Gap                             | Affected Systems | Consequence              |
| ------------------------------- | ---------------- | ------------------------ |
| {missing system or integration} | {systems}        | {what breaks or is lost} |
```

## Avoid

- Inventory without a risk section - inventory alone is an input, not the output
- Inventing integration details not supported by the source material
