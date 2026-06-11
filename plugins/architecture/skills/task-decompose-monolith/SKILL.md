---
name: task-decompose-monolith
description: "Plan or review monolith-to-services migration: strangler fig, domain-first decomposition, risk-ordered extraction into bounded services."
metadata:
  category: architecture
  tags: [architecture, migration, monolith, microservices, decomposition, strangler-fig]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows. If a delegated skill is unavailable (standalone use), apply the section's inline instructions on judgment and say so in the output.

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
| `quick`    | Early feasibility check, "should we even decompose?"          | Sections 1 (deploy profile + pain points), 2, the Extraction Order Summary table from 4, top risks from 6, Staff-Level Summary |
| `standard` | Default -- migration plan for engineering leadership sign-off | All 8 sections                                             |
| `deep`     | Large monolith, multi-team, multi-quarter migration           | All 8 sections + dependency deep-dive + failure simulation |

At `quick`, keep template numbering, omit unproduced sections silently, waive Self-Check items for unproduced sections, and lead the deliverable with the Staff-Level Summary feasibility verdict. When the driver fails validation, the honest deliverable (any depth) is Sections 1-2 plus the Staff-Level Summary opening with **Not recommended** - duration and highest-risk fields become N/A, and two lines are added: "Why not recommended: {reason}" and "Recommended alternative: {modular monolith, CI/CD prerequisites, or do nothing}". Do not produce hypothetical extraction phases. When only the cadence gate fails (driver valid), proceed with the plan and make Phase 0 the gate's remedy.

**Deep depth adds (on top of standard):**

- Dependency deep-dive: for each module in the coupling matrix, enumerate all transitive dependencies (code, data, config) and classify as severable or requires-migration
- Failure simulation: walk through the highest-risk extraction end-to-end, identifying where coexistence creates data inconsistency, latency amplification, or partial failure

## Rules

- Domain analysis before technical decomposition; service lines follow bounded contexts
- All extraction is incremental with rollback per phase; no big-bang rewrite
- Plan data ownership transfer explicitly per service; shared-database separation work (schema separation, write-path inventory) starts first even when the owning services extract later
- Extraction order is set by risk and dependency analysis, not convenience
- No implementation code; omit empty sections

## Migration Model

### 1. Current State Assessment

Run first. Understand the monolith before decomposing it.

Use skill: `stack-detect` for the current stack.
Use skill: `architecture-guardrail` to assess current boundary quality.

Capture deploy frequency/duration/rollback frequency (this gates Section 4's cadence check) and specific pain points (vague drivers produce vague plans). The coupling matrix in the Output template is the artifact.

### 2. Domain Decomposition

Identify bounded contexts before drawing service lines.

Use skill: `system-boundary-design` for formal boundary modeling.

Per context: owned entities, in/out dependencies, data access pattern. Surface shared-kernel entities explicitly (minimize) and the cross-context domain events that will eventually become integration contracts.

### 3. Target Architecture

Use skill: `architecture-landscape` when the migration affects org-wide services - build the surrounding landscape before drawing target boundaries.
Use skill: `architecture-data-consistency` for inter-service consistency strategy.
Use skill: `ops-resiliency` for fault tolerance between services.
Use skill: `tradeoff-analysis` for communication model and integration pattern decisions.

One service owns each entity (no shared databases in steady state). Name the communication model per interaction (sync vs async) and the consistency requirement (strong vs eventual). Map each target service to an owning team and flag services with no clear owner - team-autonomy drivers fail without Conway alignment. The service-inventory table in the Output template is the contract.

If the target stack differs from the monolith, add an interoperability subsection covering serialization contracts, client-library strategy, and contract testing across the language boundary.

### 4. Extraction Order and Phasing

**The core of the migration plan.**

Use skill: `strangler-fig-pattern` for incremental migration strategy.
Use skill: `review-blast-radius` to assess extraction risk per module.
Use skill: `dependency-impact-analysis` for extraction ordering.

**Deploy cadence prerequisite check:**

Before planning service extraction, verify the team can deploy frequently. Microservices require independent, frequent deployment. The test is literal: if current deploy frequency is less than weekly (every-2-weeks fails this test):

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

Per phase, the Output template specifies the fields: what extracts, prerequisites, data strategy, coexistence, verification, rollback, duration. Every phase must have a rollback path.

- Prerequisite work (CI/CD, event infrastructure such as broker/outbox when domain events are the integration plan, modular-monolith hardening) is **Phase 0** - include it in the Extraction Order Summary with Module = Foundation, and give it a phase block with inapplicable fields marked N/A
- A phase may extract a group of modules into one service when they share a transaction boundary; name the group in the phase header (the ownership unit is the service, not the module)
- When phases exceed a stated horizon, say so: cut scope or parallelize independent extractions - never compress verification or bake time

### 5. Data Ownership Transfer

The hardest part. Plan explicitly per extracted service.

Use skill: `architecture-data-consistency` for consistency during migration.
Use skill: `ops-backward-compatibility` for schema change safety.

**Migration paths:** shared DB -> schema separation -> separate DB; CDC or dual-write for sync; reconciliation job to detect drift. State the consistency guarantee during transition.

**Per-entity phases:** new service read path (from CDC) -> new service write authority -> remove monolith reads -> remove monolith writes -> remove sync infrastructure.

### 6. Failure and Risk Analysis

Use skill: `ops-failure-classification` for failure categorization.
Use skill: `failure-propagation-analysis` for cascading failure assessment.
Use skill: `ops-resiliency` for mitigation patterns.

Decomposition-specific risks: distributed transactions (formerly atomic), latency amplification (in-process -> network), dual-write conflicts during transition, partial-extraction smell (service exists but monolith still couples to it), operational overhead, team cognitive load. Per risk: blast radius, mitigation, rollback approach.

### 7. Observability and Verification

Use skill: `ops-observability` for monitoring patterns.

A migration dashboard tracks per-phase: comparison metrics (latency/error/data divergence between monolith and service), distributed traces spanning both, automated reconciliation jobs for data drift, and measurable success criteria for phase completion.

### 8. Migration Governance

Use skill: `ops-engineering-governance` for process guardrails.
Use skill: `ops-release-safety` for rollout safety.
Use skill: `ops-feature-flags` for migration feature flag strategy.

Name: decision gates (approver by role - EM, Staff, platform lead - not by individual), rollback triggers (specific conditions), feature flags for traffic routing, and cleanup discipline (removing monolith code and sync infrastructure post-extraction - tech debt is the predictable outcome otherwise).

## Review Mode

When reviewing a monolith-to-services decomposition plan authored by someone else:

Use skill: `architecture-review-lens` for severity taxonomy, completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and verdict.

Depth levels apply to plan authoring only; reviews run the full lens (standalone formatting defaults; the lens's skip rule covers steps that do not fit). This skill's planning content (cadence gate, extraction-order criteria, lowest-risk-first candidates) is valid review evidence - cite it as the bar the plan must meet.

Supply this decomposition-plan-specific factor list to the completeness audit. Required = Blocker-eligible when Missing; advisory (No) factors cap at Major:

| Factor                          | Required | What "Present" Looks Like                                                          |
| ------------------------------- | -------- | ---------------------------------------------------------------------------------- |
| Current state assessment        | No       | Module inventory, deployment profile, pain points justifying decomposition         |
| Domain decomposition            | Yes      | Bounded contexts identified; data ownership per service stated                     |
| Target architecture             | Yes      | Services named with single-sentence responsibility and primary failure mode        |
| Extraction order                | Yes      | Sequenced with rationale (lowest-coupling first, highest-pain first, etc.)         |
| Strangler-fig routing           | Yes      | Coexistence phases, traffic routing strategy, sync between monolith and services   |
| Data ownership transfer         | Yes      | Per-service: how data moves out of monolith DB; dual-write or read-replica phase   |
| Cross-cutting concerns          | No       | Auth, observability, deployment pipeline addressed for new services                |
| Risks and mitigations           | No       | Distributed-transaction risk, latency, operational overhead with mitigations       |
| Migration governance            | No       | Decision gates, rollback triggers, feature flags, cleanup discipline               |
| Per-extraction rollback         | Yes      | Each extraction has a rollback path; data un-extraction is feasible or flagged     |

Specific quality checks beyond the standard lens:

- **No extraction order rationale**: Major; "we will extract services" is not a plan
- **Shared database across services in steady state**: Blocker (distributed monolith) unless explicit transitional phase
- **No strangler-fig coexistence phase**: Blocker for production systems; big-bang decomposition is rarely safe
- **No cleanup plan for monolith code post-extraction**: Major; tech debt is the predictable outcome
- **Distributed transactions assumed to work like local transactions**: Blocker

Record each quality-check hit once, in the lens step that owns it (Missing factor -> Completeness; internal contradiction -> Internal Consistency; Present-but-wrong content -> Per-Factor Findings), folded with the factor finding per the lens's record-once rule.

Output header: `# Decomposition Plan Review` and use the output structure defined in `architecture-review-lens`. Skip the plan Output template below. In this mode the Review Self-Check replaces the authoring Self-Check:

- [ ] All factors audited with Required marking applied; verdict driven by highest severity
- [ ] Quality-check hits recorded once in the correct lens step and numbered
- [ ] Every finding cites a plan section; non-Approve verdict lists required changes

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

| Upstream Context | Downstream Context | Relationship                                         |
| ---------------- | ------------------ | ---------------------------------------------------- |
| {name}           | {name}             | Customer/Supplier, Conformist, ACL, Shared Kernel    |

### Domain Events

| Event | Producer | Consumers | Trigger |
| ----- | -------- | --------- | ------- |
| Name  | Context  | Contexts  | When    |

## 3. Target Architecture

### Service Inventory

| Service | Responsibility | Data Owned | Owning Team | Communication | Consistency Model |
| ------- | -------------- | ---------- | ----------- | ------------- | ----------------- |
| Name    | One sentence   | Entities   | Team        | Sync/Async    | Strong/Eventual   |

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
