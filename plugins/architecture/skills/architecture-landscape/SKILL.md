---
name: architecture-landscape
description: Build a landscape view of multiple systems - owners, stacks, integration points, data flows, and cross-system risks
metadata:
  category: architecture
  tags: [architecture, landscape, systems, portfolio, integration, cross-system]
user-invocable: false
---

# Architecture Landscape

> Composed by workflows; not invoked directly. Primary consumers: `task-consolidate-services` Section 1, `task-migrate-monolith-to-services` Section 3.

## When to Use

- A migration or design decision affects more than one system
- Assessing the current service landscape before consolidation or decomposition
- Building context from a docs repo rather than a live codebase
- Cross-system risks, redundancies, or stack divergence need to be surfaced

## Rules

- Map only what is known; flag inferred systems explicitly (Confirmed vs Inferred)
- Integration entries state protocol AND direction; coupling type determines blast radius
- Risks cite landscape evidence (which services share what), not generic concerns
- Flag stack divergence only when it creates operational or hiring friction
- Cite the source document for each system entry when reading from a docs repo
- Every entry has an owner; ownership is as load-bearing as the stack

## Pattern

### Coupling classification

- **Tight**: caller blocks on response; failure in target propagates to caller
- **Loose**: async events or eventual sync; caller continues on target failure

### Discovery Methods

When the integration map cannot be read from docs alone:

- **Codebase scan**: HTTP client instantiation, service URLs in config, message-broker topic names, queue consumer registrations
- **Infrastructure config**: API gateway routing, service mesh (Istio/Linkerd), load balancer upstream definitions
- **Environment variables / secrets**: service hostnames in `.env`, ConfigMaps/Secrets, Terraform variables
- **Database FKs and shared tables**: cross-schema FKs or tables accessed from multiple services reveal hidden coupling
- **Message broker inspection**: topics/queues with their producers/consumers, from broker admin UI or IaC

Tag each integration **Confirmed** (documented or code-verified) or **Inferred** (derived from config/naming).

### Cross-System Risk Assessment

After mapping, identify:

- **Single points of failure** - systems that take multiple downstreams with them; shared infrastructure (DB, auth, broker) with no fallback
- **Stack divergence** - multiple systems solving the same concern with different tech, only when it creates operational friction or hiring risk
- **Shared data risks** - DBs, caches, queues accessed by more than one system; identify the authoritative writer per shared resource
- **Missing systems** - capabilities implied by the landscape but not represented (e.g., audit logging implied but no audit service)

## Output Format

```markdown
## System Landscape

### System Inventory

| System | Owner  | Stack   | Role           | Data Owned |
| ------ | ------ | ------- | -------------- | ---------- |
| {name} | {team} | {stack} | {one sentence} | {entities} |

### Integration Map

| From     | To       | Protocol   | Direction  | Coupling    | Notes     |
| -------- | -------- | ---------- | ---------- | ----------- | --------- |
| {system} | {system} | {protocol} | Sync/Async | Tight/Loose | {context} |

### Cross-System Risks

| Risk   | Affected Systems | Severity     | Evidence            |
| ------ | ---------------- | ------------ | ------------------- |
| {risk} | {systems}        | High/Med/Low | {what reveals this} |

### Gaps

| Gap                             | Affected Systems | Impact                   |
| ------------------------------- | ---------------- | ------------------------ |
| {missing system or integration} | {systems}        | {consequence of the gap} |
```

## Avoid

- Inventory without a risk section - inventory is an input, not the output
- Inventing integration details not in source material
