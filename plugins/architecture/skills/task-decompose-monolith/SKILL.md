---
name: task-decompose-monolith
description: "Plan or review monolith-to-services migration: strangler fig, domain-first decomposition, risk-ordered extraction into bounded services."
metadata:
  category: architecture
  tags: [architecture, migration, monolith, microservices, decomposition, strangler-fig]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Monolith to Services Migration -- Staff Edition

## Purpose

Staff-level plan to decompose a monolith into services (microservices, modular monolith, or hybrid): domain-first boundaries, strangler-fig incremental extraction, explicit data ownership transfer, and risk-ordered phasing with coexistence. Produces a plan; no implementation code.

## When to Use

- Breaking a monolith into independently deployable services
- Extracting a bounded context from a monolith into its own service
- Converting a monolith into a modular monolith with enforced boundaries
- Planning incremental decomposition over multiple quarters

## Inputs

| Input                | Required | Description                                                       |
| -------------------- | -------- | ----------------------------------------------------------------- |
| Current system       | Yes      | Description of the monolith (modules, data model, key flows)      |
| Migration driver     | Yes      | Why decompose (scaling, team autonomy, deployment velocity, etc.) |
| Target state         | No       | Desired end state if known (services, modular monolith, hybrid)   |
| Constraints          | No       | Timeline, team capacity, compliance, uptime requirements          |
| Domain knowledge     | No       | Business domains, bounded contexts already identified             |
| Traffic profile      | No       | Request volume, hotspots, read/write ratio per module             |
| Existing pain points | No       | Coupling hotspots, deployment bottlenecks, scaling limits         |
| Depth                | No       | `quick`, `standard` (default), or `deep`                          |

Handle partial inputs gracefully. State assumptions explicitly when input is missing.

## Depth Levels

| Depth      | When to Use                                                   | Sections Produced                                          |
| ---------- | ------------------------------------------------------------- | ---------------------------------------------------------- |
| `quick`    | Early feasibility check, "should we even decompose?"          | Domain analysis + extraction candidates + top risks        |
| `standard` | Default -- migration plan for engineering leadership sign-off | All 8 sections                                             |
| `deep`     | Large monolith, multi-team, multi-quarter migration           | All 8 sections + dependency deep-dive + failure simulation |

**Deep depth adds (on top of standard):**

- Dependency deep-dive: for each module in the coupling matrix, enumerate all transitive dependencies (code, data, config) and classify as severable or requires-migration
- Failure simulation: walk through the highest-risk extraction end-to-end, identifying where coexistence creates data inconsistency, latency amplification, or partial failure

## Rules

- Domain analysis before technical decomposition; service lines follow bounded contexts
- All extraction is incremental with rollback per phase; no big-bang rewrite
- Plan data ownership transfer explicitly per service; shared databases are tackled first
- Extraction order is set by risk and dependency analysis, not convenience
- No implementation code; omit empty sections
- If target stack differs from monolith, add an interoperability section in Section 3 (serialization contracts, client library strategy, contract testing)

## Migration Model

### 1. Current State Assessment

**Run first. Understand before you decompose.**

Use skill: `stack-detect` to identify the technology stack.
Use skill: `architecture-guardrail` to assess current boundary quality.

Analyze:

- **System overview** -- what the monolith does, its age, team structure
- **Module inventory** -- logical modules, their responsibilities, rough size
- **Data model** -- major entities, which modules access which tables
- **Coupling hotspots** -- modules with the most cross-dependencies
- **Deployment profile** -- deploy frequency, deploy duration, rollback frequency
- **Pain points** -- what is motivating decomposition (be specific)

Produce a coupling matrix:

| Module | Depends On          | Depended On By      | Shared Tables | Coupling Level |
| ------ | ------------------- | ------------------- | ------------- | -------------- |
| Orders | Inventory, Payments | Shipping, Reporting | orders, items | High           |

### 2. Domain Decomposition

**Identify bounded contexts before drawing service lines.**

Use skill: `system-boundary-design` for formal boundary modeling.

Define:

- **Bounded contexts** -- business capability clusters with clear data ownership
- **Context map** -- relationships between bounded contexts (upstream/downstream, conformist, ACL)
- **Entity ownership** -- which context owns which entities
- **Shared kernel** -- entities or logic shared across contexts (minimize this)
- **Domain events** -- key events that cross context boundaries

For each bounded context:

- Name and business capability
- Owned entities
- Inbound dependencies (who calls this context)
- Outbound dependencies (what this context calls)
- Data access pattern (read-heavy, write-heavy, mixed)

### 3. Target Architecture

Define the end state.

Use skill: `architecture-landscape` if the monolith integrates with other systems or the migration affects org-wide services -- build the surrounding landscape before defining target service boundaries to ensure the new service lines account for org-wide coupling.
Use skill: `architecture-data-consistency` for inter-service consistency strategy.
Use skill: `ops-resiliency` for fault tolerance between services.
Use skill: `tradeoff-analysis` for communication model and integration pattern decisions.

Define:

- **Service inventory** -- target services, their responsibilities, data ownership
- **Communication model** -- sync (REST/gRPC) vs async (events) per interaction
- **Data ownership** -- one service owns each entity; no shared databases
- **Integration patterns** -- API gateway, service mesh, event bus, anti-corruption layers
- **Consistency model** -- which interactions require strong consistency vs eventual

### 4. Extraction Order and Phasing

**The core of the migration plan.**

Use skill: `strangler-fig-pattern` for incremental migration strategy.
Use skill: `review-blast-radius` to assess extraction risk per module.
Use skill: `dependency-impact-analysis` for extraction ordering.

**Deploy cadence prerequisite check:**

Before planning service extraction, verify the team can deploy frequently. Microservices require independent, frequent deployment - a team on monthly or bimonthly release cycles cannot safely operate a distributed system. If current deploy frequency is less than weekly:

- Treat this as a prerequisite, not a nice-to-have
- Recommend establishing continuous deployment (CI/CD pipeline, automated tests, canary tooling) before extracting services
- Consider a modular monolith (enforced module boundaries, single deployment) as an intermediate step

**Lowest-risk first candidates:**

Certain bounded contexts are universally safe to extract first regardless of architecture:

- **Analytics / reporting** - typically read-only, naturally isolated, failures don't affect core operations
- **Notifications** - can be eventually consistent, failures degrade UX but don't break core flows
- **Search** - usually read-only consumer of events, separated read model

Recommend one of these as Phase 1 unless they are unusually coupled in this specific system.

Determine extraction order using these criteria:

| Criterion               | Lower Risk (extract first)                          | Higher Risk (extract later)     |
| ----------------------- | --------------------------------------------------- | ------------------------------- |
| Coupling                | Few inbound/outbound dependencies                   | Many cross-cutting dependencies |
| Data sharing            | Owns its data, few shared tables                    | Heavily shared tables           |
| Business criticality    | Non-critical, failure tolerable (analytics, search) | Revenue-critical, zero-downtime |
| Team readiness          | Team experienced with target stack                  | Team needs training             |
| Bounded context clarity | Clear domain boundary                               | Fuzzy boundary, shared logic    |

For each extraction phase:

- **What is extracted** -- module/capability being moved
- **Prerequisites** -- what must be in place before extraction starts
- **Data migration strategy** -- how data ownership transfers (see Section 5)
- **Coexistence plan** -- how monolith and new service interact during transition
- **Verification criteria** -- what proves the extraction succeeded
- **Rollback plan** -- how to revert if extraction fails
- **Estimated duration** -- rough timeline for this phase

### 5. Data Ownership Transfer

**The hardest part of decomposition. Plan explicitly.**

Use skill: `architecture-data-consistency` for consistency during migration.
Use skill: `ops-backward-compatibility` for schema change safety.

For each extracted service's data:

- **Current state** -- where the data lives now (shared DB, monolith tables)
- **Target state** -- service owns its database/schema
- **Migration strategy**:
  - Shared DB -> schema separation (same DB, different schemas, enforced boundaries)
  - Schema separation -> separate DB (when ready for full isolation)
  - CDC/event sourcing for data sync during transition
  - Dual-write period with reconciliation
- **Transition period** -- how long both systems access the data
- **Consistency guarantee** -- what consistency model applies during transition
- **Reconciliation** -- how to detect and fix data drift between systems

Data migration phases per entity:

1. **Read path migration** -- new service reads from own store (populated by CDC/sync)
2. **Write path migration** -- new service becomes the write authority
3. **Legacy read removal** -- monolith stops reading directly, uses service API
4. **Legacy write removal** -- monolith stops writing, routes through service
5. **Sync removal** -- CDC/dual-write removed after full migration

### 6. Failure and Risk Analysis

Use skill: `ops-failure-classification` for failure categorization.
Use skill: `failure-propagation-analysis` for cascading failure assessment.
Use skill: `ops-resiliency` for mitigation patterns.

Analyze risks specific to decomposition:

- **Distributed transaction risk** -- operations that were atomic in monolith become distributed
- **Latency amplification** -- in-process calls become network calls
- **Data consistency during transition** -- dual-write conflicts, replication lag
- **Partial extraction failure** -- service extracted but monolith still has coupling
- **Operational complexity increase** -- more services = more deployments, monitoring, debugging
- **Team cognitive load** -- can the team operate the new distributed system

For each high-risk scenario:

- State the risk
- State the blast radius
- State the mitigation
- State the rollback approach

### 7. Observability and Verification

Use skill: `ops-observability` for monitoring patterns.

Define:

- **Migration dashboard** -- what to monitor during each extraction phase
- **Comparison metrics** -- how to compare monolith vs service behavior (latency, errors, data)
- **Distributed tracing** -- trace spans across monolith and new services during coexistence
- **Data reconciliation** -- automated checks for data consistency between systems
- **Success criteria** -- measurable signals that an extraction phase is complete

### 8. Migration Governance

Use skill: `ops-engineering-governance` for process guardrails.
Use skill: `ops-release-safety` for rollout safety.
Use skill: `ops-feature-flags` for migration feature flag strategy.

Define:

- **Decision gates** -- who approves proceeding to next extraction phase
- **Rollback triggers** -- what conditions force a rollback
- **Feature flag strategy** -- flags for routing traffic between monolith and service
- **Communication plan** -- how to keep stakeholders informed of migration progress
- **Cleanup discipline** -- removing monolith code, sync jobs, and compatibility shims after extraction

## Review Mode

When reviewing a monolith-to-services decomposition plan authored by someone else:

Use skill: `architecture-review-lens` for severity taxonomy, completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and verdict.

Supply this decomposition-plan-specific factor list to the completeness audit:

| Factor                          | What "Present" Looks Like                                                          |
| ------------------------------- | ---------------------------------------------------------------------------------- |
| Current state assessment        | Module inventory, deployment profile, pain points justifying decomposition         |
| Domain decomposition            | Bounded contexts identified; data ownership per service stated                     |
| Target architecture             | Services named with single-sentence responsibility and primary failure mode        |
| Extraction order                | Sequenced with rationale (lowest-coupling first, highest-pain first, etc.)         |
| Strangler-fig routing           | Coexistence phases, traffic routing strategy, sync between monolith and services   |
| Data ownership transfer         | Per-service: how data moves out of monolith DB; dual-write or read-replica phase   |
| Cross-cutting concerns          | Auth, observability, deployment pipeline addressed for new services                |
| Risks and mitigations           | Distributed-transaction risk, latency, operational overhead with mitigations       |
| Migration governance            | Decision gates, rollback triggers, feature flags, cleanup discipline               |
| Per-extraction rollback         | Each extraction has a rollback path; data un-extraction is feasible or flagged     |

Specific quality checks beyond the standard lens:

- **No extraction order rationale**: Major; "we will extract services" is not a plan
- **Shared database across services in steady state**: Blocker (distributed monolith) unless explicit transitional phase
- **No strangler-fig coexistence phase**: Blocker for production systems; big-bang decomposition is rarely safe
- **No cleanup plan for monolith code post-extraction**: Major; tech debt is the predictable outcome
- **Distributed transactions assumed to work like local transactions**: Blocker

Output header: `# Decomposition Plan Review` and use the output structure defined in `architecture-review-lens`. Skip the New Plan output template.

## Output

```markdown
# Monolith to Services Migration Plan

## 1. Current State Assessment

System Overview:
Module Inventory:
Deployment Profile:
Pain Points:

### Coupling Matrix

| Module | Depends On | Depended On By | Shared Tables | Coupling Level |
| ------ | ---------- | -------------- | ------------- | -------------- |
| Name   | Modules    | Modules        | Tables        | High/Med/Low   |

## 2. Domain Decomposition

### Bounded Contexts

| Context | Business Capability | Owned Entities | Dependencies | Data Pattern |
| ------- | ------------------- | -------------- | ------------ | ------------ |
| Name    | Capability          | Entities       | In/Out       | Read/Write   |

### Context Map

[Upstream/downstream relationships, conformist/ACL boundaries]

### Domain Events

| Event | Producer | Consumers | Trigger |
| ----- | -------- | --------- | ------- |
| Name  | Context  | Contexts  | When    |

## 3. Target Architecture

### Service Inventory

| Service | Responsibility | Data Owned | Communication | Consistency Model |
| ------- | -------------- | ---------- | ------------- | ----------------- |
| Name    | One sentence   | Entities   | Sync/Async    | Strong/Eventual   |

## 4. Extraction Plan

### Phase 1: {Module Name}

What: {capability being extracted}
Prerequisites: {what must be in place}
Data strategy: {how data ownership transfers}
Coexistence: {how monolith and service interact}
Verification: {success criteria}
Rollback: {revert plan}
Duration: {estimate}

[Repeat for each phase]

### Extraction Order Summary

| Phase | Module | Risk Level | Duration | Key Dependency        |
| ----- | ------ | ---------- | -------- | --------------------- |
| 1     | Name   | Low/Med    | Weeks    | What must exist first |

## 5. Data Ownership Transfer

### {Entity/Table Group}

| Aspect                | Detail                              |
| --------------------- | ----------------------------------- |
| Current location      | Monolith DB, schema X               |
| Target location       | Service DB                          |
| Migration strategy    | CDC / Dual-write / Batch sync       |
| Transition period     | N weeks                             |
| Consistency guarantee | Eventual / Strong during transition |
| Reconciliation        | Automated comparison job            |

## 6. Risks and Mitigations

| Risk                    | Blast Radius | Mitigation               | Rollback               |
| ----------------------- | ------------ | ------------------------ | ---------------------- |
| Distributed transaction | Moderate     | Saga with compensation   | Route back to monolith |
| Latency amplification   | Narrow       | Circuit breaker, caching | Feature flag disable   |

## 7. Observability

### Migration Dashboard

| Signal                                 | Threshold       | Source | Action When Breached          |
| -------------------------------------- | --------------- | ------ | ----------------------------- |
| Error rate delta (monolith vs service) | > 1% divergence | APM    | Pause extraction, investigate |

### Data Reconciliation

| Data Entity | Comparison Method    | Frequency | Acceptable Drift |
| ----------- | -------------------- | --------- | ---------------- |
| {entity}    | Row count + checksum | Hourly    | < 0.1%           |

### Phase Success Criteria

| Phase   | Criterion             | Measurement    | Target      |
| ------- | --------------------- | -------------- | ----------- |
| {phase} | {what proves success} | {how measured} | {threshold} |

## 8. Migration Governance

Decision Gates:
Rollback Triggers:
Feature Flag Strategy:
Cleanup Plan:

## Staff-Level Summary

- Migration feasibility: Feasible / Feasible with caveats / Not recommended
- Estimated total duration: {quarters}
- Highest-risk extraction: {which phase and why}
- Long-term evolution notes:
```

## Self-Check

- [ ] Domain decomposition based on business capabilities; every bounded context has clear data ownership
- [ ] Coupling matrix populated for major modules (Section 1)
- [ ] Communication model (sync vs async) defined per service interaction (Section 3)
- [ ] Extraction order considers coupling, risk, dependencies; rollback at every phase
- [ ] Data ownership transfer has explicit per-entity strategy; coexistence addresses data consistency
- [ ] Operational complexity increase acknowledged with mitigations
- [ ] Observability signals and success criteria per phase (Section 7); decision gates and rollback triggers (Section 8)

## Avoid

- Drawing service lines by code package instead of domain boundary
- Extracting the hardest, most-coupled module first
- Assuming shared database is acceptable long-term
- Decomposing for the sake of it - validate the migration driver
