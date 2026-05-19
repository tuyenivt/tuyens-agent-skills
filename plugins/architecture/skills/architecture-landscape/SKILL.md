---
name: architecture-landscape
description: Build a landscape view of multiple systems - owners, stacks, integration points, data flows, and cross-system risks
metadata:
  category: architecture
  tags: [architecture, landscape, systems, portfolio, integration, cross-system]
user-invocable: false
---

# Architecture Landscape

> This atomic is composed by workflows - do not invoke directly. Primary consumers: `task-consolidate-services` Section 1, `task-migrate-monolith-to-services` Section 3.

## When to Use

- When a migration or design decision affects more than one system
- When assessing the current service landscape before consolidation or decomposition
- When building context from a docs repo rather than a live codebase
- When cross-system risks, redundancies, or stack divergence need to be surfaced

## Rules

- Map only what is known; flag inferred systems explicitly
- Integration entries must state protocol and direction
- Risks must cite landscape evidence (which services share what), not generic concerns
- Flag stack divergence only when it creates operational or hiring friction
- Cite the source document for each system entry when reading from a docs repo

## Pattern

### System Inventory

For each system in scope:

| System | Owner (team) | Stack                 | Role         | Data Owned   |
| ------ | ------------ | --------------------- | ------------ | ------------ |
| Name   | Team         | Language/Framework/DB | What it does | Key entities |

### Integration Map

For each integration between systems:

| From     | To       | Protocol              | Direction  | Coupling Type | Notes                  |
| -------- | -------- | --------------------- | ---------- | ------------- | ---------------------- |
| System A | System B | REST/gRPC/Event/Batch | Sync/Async | Tight/Loose   | Frequency, criticality |

**Coupling classification:**

- **Tight**: caller blocks on response; failure in target propagates to caller
- **Loose**: async events or eventual sync; caller continues on target failure

### Discovery Methods

When the integration map cannot be read from documentation alone, use these discovery approaches:

- **Codebase scan**: Search for HTTP client instantiation, service URLs in config, message broker topic names, and queue consumer registrations
- **Infrastructure config**: Check API gateway routing rules, service mesh (Istio/Linkerd) configuration, or load balancer upstream definitions
- **Environment variables / secrets**: Service hostnames and API endpoints in `.env`, Kubernetes ConfigMaps/Secrets, or Terraform variables reveal integration targets
- **Database foreign keys and shared tables**: Cross-schema foreign keys or tables accessed from multiple services reveal hidden coupling
- **Message broker inspection**: List topics/queues and their producers/consumers from broker admin UI or infrastructure-as-code

Flag each integration entry with confidence: **Confirmed** (documented or code-verified) vs **Inferred** (derived from config or naming convention). Do not invent integrations.

### Cross-System Risk Assessment

After mapping the inventory and integrations, identify:

**Single points of failure**

- Systems that, if down, take multiple downstream systems with them
- Shared infrastructure (shared DB, shared auth service, shared message broker) with no fallback

**Stack divergence**

- Multiple systems solving the same concern with different technology choices (e.g., three different ORMs, two auth libraries)
- Flag only when divergence creates operational friction or hiring risk

**Shared data risks**

- Databases, caches, or queues accessed by more than one system (shared state = hidden coupling)
- Identify who is the authoritative writer for each shared resource

**Missing systems**

- Capabilities implied by the landscape but not represented by any system (e.g., audit logging implied but no audit service exists)

### Output Format

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

| Gap                             | Affected Systems             | Impact                   |
| ------------------------------- | ---------------------------- | ------------------------ |
| {missing system or integration} | {which systems are affected} | {consequence of the gap} |
```

## Avoid

- Listing systems without owners - ownership is as load-bearing as the stack
- Treating all integrations as equivalent - coupling type determines blast radius
- Producing inventory without a risk section - inventory is an input, not the output
- Inventing integration details not in source material
