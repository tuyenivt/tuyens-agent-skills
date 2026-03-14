---
name: task-consolidate-services
description: Microservices consolidation plan - merge over-split services back into fewer, cohesive units. Use when you have too many nano-services, services that always deploy together, services sharing a database without clear boundaries, or more services than your team can operate. Also use when reversing a monolith decomposition that went too far. Not for breaking a monolith apart (use task-migrate-monolith-to-services) and not for upgrading the tech stack of existing services (use task-modernize-legacy).
metadata:
  category: architecture
  tags: [architecture, migration, microservices, consolidation, merge, simplification]
  type: workflow
user-invocable: true
---

# Microservices Consolidation -- Staff Edition

## Purpose

Staff-level planning for consolidating over-split microservices into fewer, better-bounded services. Focuses on:

- **Merge-first thinking** -- identify services that should never have been split
- **Operational cost reduction** -- fewer services = fewer deployments, less monitoring, less network hops
- **Data reunification** -- merge databases that were artificially separated
- **Incremental consolidation** -- merge services safely without big-bang
- **Boundary correction** -- the goal is right-sized services, not monolith restoration

This skill produces a consolidation plan. It does not generate implementation code.

## When to Use

- Microservices sprawl is increasing operational overhead without proportional benefit
- Services are too fine-grained (single-entity services, CRUD wrappers)
- Cross-service transactions are causing consistency issues that would not exist in a single service
- Team cannot effectively operate the number of services deployed
- Latency is dominated by inter-service communication for tightly coupled operations

## Inputs

| Input                | Required | Description                                                         |
| -------------------- | -------- | ------------------------------------------------------------------- |
| Service inventory    | Yes      | List of services, their responsibilities, and data ownership        |
| Consolidation driver | Yes      | Why consolidate (operational cost, latency, consistency, team size) |
| Constraints          | No       | Uptime requirements, team capacity, compliance                      |
| Service dependencies | No       | Call graph, event flows between services                            |
| Pain points          | No       | Specific issues caused by current decomposition                     |
| Traffic profile      | No       | Request volume and patterns per service                             |
| Depth                | No       | `quick`, `standard` (default), or `deep`                            |

Handle partial inputs gracefully. State assumptions explicitly when input is missing.

## Depth Levels

| Depth      | When to Use                                           | Sections Produced                                     |
| ---------- | ----------------------------------------------------- | ----------------------------------------------------- |
| `quick`    | Initial assessment, "which services should merge?"    | Smell detection + merge candidates + top risks        |
| `standard` | Default -- consolidation plan for leadership sign-off | All 7 sections                                        |
| `deep`     | Large service mesh, multi-team ownership              | All 7 sections + dependency deep-dive + latency model |

## Rules

- Consolidation must be justified by concrete operational or architectural problems
- Merge decisions are based on coupling analysis, not convenience
- Every merge must be incremental -- no big-bang service fusion
- Data reunification strategy must be planned explicitly
- Rollback must be possible at every stage
- The goal is right-sized services, not returning to a monolith
- Do not generate implementation code
- Omit empty sections

## Consolidation Model

### 1. Service Landscape Assessment

**Understand the current state before proposing merges.**

Use skill: `stack-detect` to identify the technology stack.
Use skill: `architecture-guardrail` to assess current boundary quality.
Use skill: `architecture-landscape` to build the service landscape map -- system inventory, integration map, and cross-system risks. This produces the coupling and ownership data that drives merge candidate identification in Section 2.

The `architecture-landscape` output replaces manual analysis of:

- **Service inventory** -- all services, their responsibilities, team ownership
- **Dependency graph** -- who calls whom, sync vs async, call frequency
- **Data ownership** -- which service owns which data, shared databases if any
- **Operational profile** -- deploy frequency, incident rate, monitoring overhead per service
- **Team mapping** -- which team owns which services, cognitive load per team

### 2. Over-Split Detection

**Identify services that are candidates for merging.**

Use smell detection to find merge candidates:

| Smell                   | Signal                                                          | Indicates                                    |
| ----------------------- | --------------------------------------------------------------- | -------------------------------------------- |
| Chatty services         | >5 sync calls between two services per user request             | Should be one service or use async           |
| Distributed monolith    | Services must deploy together; change in A requires change in B | Not independently deployable = not a service |
| Nano service            | Service wraps a single entity or single CRUD operation          | Too fine-grained; merge with parent domain   |
| Shared database         | Multiple services read/write the same tables                    | No real boundary; merge or fix ownership     |
| Circular dependencies   | A -> B -> A call chains                                         | Boundary drawn in wrong place                |
| Distributed transaction | Saga/2PC for what was a single DB transaction in monolith       | Artificial split; merge restores atomicity   |
| Single consumer         | Service exists only because one other service calls it          | Inline into the consumer                     |
| Proxy service           | Service adds no logic, just forwards requests                   | Remove the proxy, connect directly           |
| Team mismatch           | One person maintains 5+ services                                | Consolidate to match team capacity           |

For each smell detected, document:

- Which services exhibit the smell
- Evidence (call frequency, deploy coupling, shared tables)
- Merge recommendation

### 3. Merge Candidates and Grouping

**Propose which services to merge and into what.**

Use skill: `system-boundary-design` for boundary redesign.

For each merge group:

- **Services to merge** -- which services combine
- **Resulting service** -- name, responsibility, data ownership
- **Merge justification** -- which smells this resolves
- **Boundary improvement** -- how the new boundary is better than the split
- **What stays separate** -- services that should NOT be merged and why

Produce a merge map:

| Merge Group      | Services Merging             | Resulting Service | Justification               |
| ---------------- | ---------------------------- | ----------------- | --------------------------- |
| Order Processing | OrderSvc, OrderItemSvc       | OrderService      | Nano service, shared DB     |
| User Management  | UserSvc, ProfileSvc, AuthSvc | UserService       | Chatty, circular dependency |

### 4. Data Reunification

**Merging services means merging data. Plan explicitly.**

Use skill: `data-consistency-modeling` for consistency during migration.
Use skill: `backward-compatibility-analysis` for schema change safety.

For each merge group:

- **Current data layout** -- separate databases, schemas, or tables per service
- **Target data layout** -- unified schema in merged service's database
- **Migration strategy**:
  - **Already shared database** (services read/write the same DB): no data migration needed - focus on schema cleanup, removing artificial service boundaries, and merging ORM models. This is the simplest consolidation case.
  - Same DB engine, separate databases: schema merge with migration scripts
  - Different DB engines: pick target engine, migrate data
  - Event-sourced services: merge event stores or project to unified store
- **Data migration phases**:
  1. Dual-read: merged service reads from both sources
  2. Data migration: copy/transform data to unified schema
  3. Dual-write: write to both during transition
  4. Cutover: switch to unified schema, stop dual operations
  5. Cleanup: remove old schemas, sync jobs, compatibility code
- **Consistency during transition** -- how to handle reads/writes while migrating

### 5. Consolidation Phasing

**Merge incrementally, not all at once.**

Use skill: `strangler-fig-pattern` for incremental migration.
Use skill: `blast-radius-analysis` to assess merge risk.
Use skill: `dependency-impact-analysis` for merge ordering.

Determine merge order:

| Criterion       | Merge First                         | Merge Later                           |
| --------------- | ----------------------------------- | ------------------------------------- |
| Coupling        | Already tightly coupled (shared DB) | Loosely coupled (async events only)   |
| Blast radius    | Low-traffic, non-critical services  | Revenue-critical, high-traffic        |
| Data complexity | Same DB engine, simple schema merge | Different engines, complex transforms |
| Team readiness  | Same team owns both services        | Different teams, coordination needed  |
| Consumer impact | Internal consumers only             | External API consumers                |

For each consolidation phase:

- **What merges** -- which services combine in this phase
- **Prerequisites** -- what must be in place
- **API migration** -- how consumers migrate from old endpoints to new
- **Data migration** -- how data reunifies (see Section 4)
- **Traffic routing** -- how traffic shifts from old services to merged service
- **Verification** -- how to confirm the merge succeeded
- **Rollback** -- how to revert if the merge fails

### 6. Consumer Migration

**Services have consumers. Plan their transition.**

Use skill: `backward-compatibility-analysis` for API compatibility.
Use skill: `feature-flags` for consumer routing.

For each merged service:

- **Affected consumers** -- who calls the services being merged
- **API consolidation strategy**:
  - Facade: merged service exposes old APIs temporarily, routes internally
  - Versioned: new unified API alongside old endpoints, deprecation timeline
  - Direct: consumers update to new API (only if few consumers, coordinated deploy)
- **Deprecation timeline** -- when old endpoints are removed
- **Consumer communication** -- how to notify and coordinate with consumer teams

### 7. Risk Analysis

Use skill: `failure-classification` for failure categorization.
Use skill: `failure-propagation-analysis` for cascading failure assessment.

Analyze consolidation-specific risks:

- **Blast radius increase** -- merged service failure now affects more capabilities
- **Scaling mismatch** -- merged capabilities may have different scaling needs
- **Deploy coupling** -- previously independent deploys now coupled
- **Data migration risk** -- data loss or corruption during reunification
- **Rollback complexity** -- undoing a merge is harder than undoing a split
- **Team ownership** -- who owns the merged service if original services had different owners

For each high-risk scenario:

- State the risk
- State the blast radius
- State the mitigation
- State the rollback approach

## Output

```markdown
# Microservices Consolidation Plan

## 1. Service Landscape

Service Count:
Dependency Graph Summary:
Operational Overhead:

### Service Inventory

| Service | Responsibility | Data Owned | Consumers | Team | Deploy Freq |
| ------- | -------------- | ---------- | --------- | ---- | ----------- |
| Name    | One sentence   | Entities   | Count     | Team | Weekly/etc  |

## 2. Over-Split Detection

### Smells Detected

| Smell  | Services Affected | Evidence                  | Recommendation |
| ------ | ----------------- | ------------------------- | -------------- |
| Chatty | A, B              | 12 sync calls per request | Merge          |

## 3. Merge Candidates

### Merge Map

| Merge Group | Services Merging | Resulting Service | Justification  |
| ----------- | ---------------- | ----------------- | -------------- |
| Group name  | A, B             | MergedService     | Smell resolved |

### Services That Stay Separate

| Service | Reason to Keep Separate                     |
| ------- | ------------------------------------------- |
| Name    | Independent domain, different scaling needs |

## 4. Data Reunification

### {Merge Group}

| Aspect             | Detail                        |
| ------------------ | ----------------------------- |
| Current layout     | Separate DBs / schemas        |
| Target layout      | Unified schema                |
| Migration strategy | Schema merge / data migration |
| Transition period  | N weeks                       |
| Consistency        | Dual-read/write during merge  |

## 5. Consolidation Phases

### Phase 1: {Merge Group}

What: {services merging}
Prerequisites: {what must be in place}
API migration: {facade / versioned / direct}
Data migration: {strategy}
Verification: {success criteria}
Rollback: {revert plan}
Duration: {estimate}

### Phase Summary

| Phase | Merge Group | Risk Level | Duration | Key Dependency        |
| ----- | ----------- | ---------- | -------- | --------------------- |
| 1     | Name        | Low        | Weeks    | What must exist first |

## 6. Consumer Migration

| Consumer | Current Endpoints | New Endpoint | Migration Strategy | Timeline |
| -------- | ----------------- | ------------ | ------------------ | -------- |
| Name     | Old APIs          | New API      | Facade/Versioned   | Weeks    |

## 7. Risks and Mitigations

| Risk                  | Blast Radius | Mitigation              | Rollback           |
| --------------------- | ------------ | ----------------------- | ------------------ |
| Blast radius increase | Wide         | Bulkhead within service | Re-split if needed |

## Staff-Level Summary

- Consolidation feasibility: Recommended / Conditional / Not recommended
- Services before: {N} -> Services after: {N}
- Estimated duration: {quarters}
- Highest-risk merge: {which and why}
- Operational cost reduction: {qualitative or quantitative}
```

## Self-Check

- [ ] Every merge is justified by a concrete smell or operational problem
- [ ] Merge groups respect domain boundaries -- not merging unrelated services
- [ ] Data reunification has an explicit strategy per merge group
- [ ] Consumer migration is planned with deprecation timeline
- [ ] Every consolidation phase has a rollback plan
- [ ] Services that should stay separate are explicitly listed with reasons
- [ ] No big-bang merge -- every phase is incremental
- [ ] Blast radius increase from merging is acknowledged with mitigations

## Avoid

- Merging everything back into a monolith -- the goal is right-sized services
- Merging services from different domains just to reduce count
- Ignoring data reunification -- separate databases do not magically merge
- Big-bang consolidation -- merge incrementally
- Merging without consumer migration plan
- Consolidation without clear operational or architectural justification
- Assuming merge is simpler than split -- undoing a merge is expensive
