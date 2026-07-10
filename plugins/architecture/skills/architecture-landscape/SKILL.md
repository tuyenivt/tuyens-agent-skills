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

- Map only what is known; mark every row **Confirmed** (authored documentation or code-verified) or **Inferred** (derived from config, naming, or convention - a compose file or IaC alone is Inferred; a system known only from another system's doc is Inferred). A row's confidence is that of its least-confirmed cell; note mixed confidence in Notes. Unknown cell values do not change confidence - confidence rates what is asserted
- Integration entries state protocol and coupling separately - sync/async belongs to protocol; tight/loose is coupling
- Risks cite landscape evidence (which services share what), not generic concerns
- Every entry cites a Source: doc path, code path, or config artifact (or "assessment brief" when facts arrive as a brief rather than artifacts). Unhedged brief statements are Confirmed - the brief is authored documentation; statements the brief hedges ("probably", "not sure") are Inferred
- Never invent values - unknown Owner/Stack cells say Unknown. Undocumented systems still get inventory rows; they are usually where the risk lives

## Pattern

### Coupling vs Protocol

- **Protocol**: how the call travels (sync REST/gRPC, async event, batch, direct DB)
- **Coupling**: how failure propagates - **Tight** = caller blocks on response and target failure propagates; **Loose** = caller continues on target failure

A sync call can be loose if the caller has a fallback; an async event can be tight if the consumer cannot make progress without it. When failure behavior cannot be determined from the sources, mark coupling Tight (worst case) and Inferred.

### Edge conventions

- One row per direct edge, From = initiator; describe a multi-hop chain in Notes, never as one aggregate row. Exception: a uniform fan-out (every service calls auth) may be one row with From "all services"; an unnamed caller population gets one aggregate row plus a Gap row for the unknown members
- Broker-mediated flows: one row per producer-consumer pair, Protocol async event, topic/queue named in Notes; the broker itself is inventoried as infrastructure
- Direct cross-service DB or cache access (read or write) is an integration row with Protocol direct DB/cache; To = the data's owning system with the DB/cache named in Notes (mirroring broker rows), or the infrastructure system itself when no single owner exists. A service's link to infrastructure only it uses (its own DB) is not an integration row
- External dependencies (SaaS, third-party APIs) are integration rows with To marked external (e.g., `Stripe (external)`); inventory one as infrastructure only when multiple systems share it

### Discovery when docs are incomplete

Read what is available; flag the rest as Inferred. Sources in decreasing reliability: code (HTTP clients, message-broker producers/consumers), infra config (gateway routes, service mesh, IaC), env vars and ConfigMaps for service hostnames, shared databases or FKs that reveal hidden coupling.

### Cross-System Risk Categories

- **Single points of failure** - systems whose failure takes multiple downstreams with them; shared infrastructure (DB, auth, broker) with no fallback
- **Shared data** - DBs, caches, queues with more than one writer; name the authoritative writer per shared resource, or write "writer unknown" and add a Gap row
- **Missing capability** - a capability implied by the landscape but unowned (e.g., audit logging assumed but no audit service)

When a finding fits two categories, file one row under the category driving its severity and name the other in Evidence. Stack divergence is a risk only when it causes operational friction or hiring strain - record it as an SPOF or shared-data risk row, not its own category.

**Severity rubric:** High = failure halts multiple systems, risks data loss/corruption, or breaches a stated regulatory/compliance obligation; Medium = degrades function or has a workaround; Low = friction or maintenance cost only. Severity rates consequence, not confidence - an Inferred-evidence risk keeps its severity; the evidence cell shows the confidence.

### Risks vs Gaps

A finding about the system's design is a **Risk**; a finding about your knowledge of the system is a **Gap** (undocumented system, unverifiable integration, unknown owner). The same subject may appear in both only when it carries both a design risk and an information hole.

## Output Format

```markdown
## System Landscape

### System Inventory

Shared infrastructure (DB, broker, cache, gateway, auth) gets rows with Role: infrastructure and Data Owned: N/A unless known.

| System | Owner          | Stack           | Role           | Data Owned | Confidence           | Source            |
| ------ | -------------- | --------------- | -------------- | ---------- | -------------------- | ----------------- |
| {name} | {team/Unknown} | {stack/Unknown} | {one sentence} | {entities} | Confirmed / Inferred | {doc/code/config} |

### Integration Map

| From (initiator) | To       | Protocol                                                  | Coupling    | Confidence           | Notes               |
| ---------------- | -------- | --------------------------------------------------------- | ----------- | -------------------- | ------------------- |
| {system}         | {system} | sync call (REST/gRPC/...) / async event / batch / direct DB/cache | Tight/Loose | Confirmed / Inferred | {topic, data flow}  |

### Cross-System Risks

| Risk   | Category            | Affected Systems | Severity     | Evidence            |
| ------ | ------------------- | ---------------- | ------------ | ------------------- |
| {risk} | SPOF/Shared/Missing | {systems}        | High/Med/Low | {what reveals this} |

### Gaps

| Gap                                  | Affected Systems | Consequence                  |
| ------------------------------------ | ---------------- | ---------------------------- |
| {unknown or unverifiable knowledge}  | {systems}        | {what cannot be assessed}    |
```

## Avoid

- Inventory without a risk section - inventory alone is an input, not the output
- Inventing integration details not supported by the source material
