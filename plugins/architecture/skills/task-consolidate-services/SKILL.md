---
name: task-consolidate-services
description: "Plan or review microservices consolidation: smell detection, merge candidates, data reunification, phased execution with rollback."
metadata:
  category: architecture
  tags: [architecture, migration, microservices, consolidation, merge, simplification]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Microservices Consolidation -- Staff Edition

## Purpose

Staff-level plan to consolidate over-split microservices into fewer, well-bounded services through smell detection, merge candidates, data reunification, and incremental phasing with rollback. The goal is right-sized services, not monolith restoration. Produces a plan; no implementation code.

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

For inputs naming only 1-3 specific services, skip the full landscape map and focus smell detection on the named services and their immediate dependencies only. If `stack-detect` finds no stack, proceed with stack-agnostic guidance.

## Depth Levels

| Depth      | When to Use                                           | Sections Produced                                     |
| ---------- | ----------------------------------------------------- | ----------------------------------------------------- |
| `quick`    | Initial assessment, "which services should merge?"    | Smell detection + merge candidates + top risks        |
| `standard` | Default -- consolidation plan for leadership sign-off | All 7 sections                                        |
| `deep`     | Large service mesh, multi-team ownership              | All 7 sections + dependency deep-dive + latency model |

## Rules

- Justify every merge by a concrete smell or operational problem; coupling analysis, not convenience
- Every merge is incremental with rollback at each phase; no big-bang fusion
- Plan data reunification explicitly per merge group
- Goal is right-sized services, not monolith restoration
- No implementation code; omit empty sections

## Consolidation Model

### 1. Service Landscape Assessment [standard/deep only]

Use skill: `stack-detect`, `architecture-guardrail`, `architecture-landscape`.

`architecture-landscape` produces the system inventory, integration map, ownership, and cross-system risks that drive Section 2's merge candidate identification. If the user supplied a raw service inventory, feed it as input to `architecture-landscape` to enrich.

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

Per smell detected: services affected, evidence (call frequency, deploy coupling, shared tables), recommendation. The Smells Detected table in the Output template is the contract.

### 3. Merge Candidates and Grouping

**Propose which services to merge and into what.**

Use skill: `system-boundary-design` for boundary redesign.
Use skill: `tradeoff-analysis` for merge vs keep-separate decisions on borderline candidates.

Per merge group: which services combine, resulting service (name, responsibility, data ownership), smells resolved, boundary improvement vs. the split. Also list services that stay separate and why. Produce a merge map:

| Merge Group      | Services Merging             | Resulting Service | Justification               |
| ---------------- | ---------------------------- | ----------------- | --------------------------- |
| Order Processing | OrderSvc, OrderItemSvc       | OrderService      | Nano service, shared DB     |
| User Management  | UserSvc, ProfileSvc, AuthSvc | UserService       | Chatty, circular dependency |

### 4. Data Reunification [standard/deep only]

**Merging services means merging data. Plan explicitly.**

Use skill: `architecture-data-consistency` for consistency during migration.
Use skill: `ops-backward-compatibility` for schema change safety.

Per merge group: current layout (DBs/schemas/tables), target unified schema, migration strategy, consistency during transition.

**Migration strategy by case:**

- **Already shared DB** (services share one instance): no data migration - schema cleanup, remove artificial boundaries, merge ORM models. Simplest case; do not apply the full 5-phase template.
- **Same engine, separate DBs:** schema merge with migration scripts.
- **Different engines:** pick target, migrate data.
- **Event-sourced:** merge event stores or project to a unified store.

**Full 5-phase template** (only when data physically relocates): dual-read -> migrate/transform -> dual-write -> cutover -> cleanup.

### 5. Consolidation Phasing [standard/deep only]

**Merge incrementally, not all at once.**

Use skill: `strangler-fig-pattern` for incremental migration.
Use skill: `review-blast-radius` to assess merge risk.
Use skill: `dependency-impact-analysis` for merge ordering.

Determine merge order:

| Criterion       | Merge First                         | Merge Later                           |
| --------------- | ----------------------------------- | ------------------------------------- |
| Coupling        | Already tightly coupled (shared DB) | Loosely coupled (async events only)   |
| Blast radius    | Low-traffic, non-critical services  | Revenue-critical, high-traffic        |
| Data complexity | Same DB engine, simple schema merge | Different engines, complex transforms |
| Team readiness  | Same team owns both services        | Different teams, coordination needed  |
| Consumer impact | Internal consumers only             | External API consumers                |

Per phase, the Output template specifies the fields: what merges, prerequisites, API migration, data migration, routing, verification, rollback. Every phase needs a rollback path - undoing a merge is harder than undoing a split.

### 6. Consumer Migration [standard/deep only]

**Services have consumers. Plan their transition.**

Use skill: `ops-backward-compatibility` for API compatibility.
Use skill: `ops-feature-flags` for consumer routing.

Per merged service: affected consumers, strategy, deprecation timeline, coordination plan.

**API consolidation strategies:**

- **Facade:** merged service exposes old APIs temporarily, routes internally. Lowest consumer disruption.
- **Versioned:** new unified API alongside old endpoints with a deprecation window.
- **Direct:** consumers update to new API. Only safe with few consumers and coordinated deploys.

### 7. Risk Analysis

Use skill: `ops-failure-classification` for failure categorization.
Use skill: `failure-propagation-analysis` for cascading failure assessment.

Consolidation-specific risks: blast-radius increase (merged service failure affects more capabilities), scaling mismatch (different sub-capability needs), deploy coupling (formerly independent), data migration loss/corruption, rollback complexity (undoing a merge is expensive), team ownership ambiguity. Per high-risk scenario: blast radius, mitigation, rollback.

## Review Mode

When reviewing a service-consolidation plan authored by someone else:

Use skill: `architecture-review-lens` for severity taxonomy, completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and verdict.

Supply this consolidation-plan-specific factor list to the completeness audit:

| Factor                       | What "Present" Looks Like                                                       |
| ---------------------------- | ------------------------------------------------------------------------------- |
| Service landscape            | Inventory, dependency graph, operational overhead justifying consolidation      |
| Over-split detection         | Specific signals (sync-call count, shared DB, single team owns many services)   |
| Merge candidates             | Named target service(s) with bounded-context rationale, not just "merge these"  |
| Target boundaries            | Post-merge module boundaries explicit; data ownership clear                     |
| Data reunification           | How separate DBs/schemas merge; foreign-key reintroduction; backfill plan       |
| Consumer migration           | Old service endpoints kept compatible or migration window stated per consumer   |
| Consolidation phases         | Stepwise: code merge -> data merge -> endpoint deprecation -> decommission      |
| Backward compatibility       | Old endpoints, events, and contracts remain consumable during transition        |
| Risks and mitigations        | Re-coupling risk, blast-radius expansion, single-deploy risk with mitigations   |
| Rollback per phase           | Each phase has a rollback path; data un-merging is feasible or flagged          |

Specific quality checks beyond the standard lens:

- **Merge target without bounded-context rationale**: Major; consolidation that ignores bounded contexts recreates the original problem
- **Big-bang code-and-data merge in one deploy**: Blocker for production systems
- **No consumer migration plan**: Blocker if consumers are external or cross-team
- **Recombined service that exceeds the team's deploy/operate capacity**: Major
- **Endpoints unified but data stays sharded across the old service DBs**: Major; partial consolidation often worse than none

Output header: `# Consolidation Plan Review` and use the output structure defined in `architecture-review-lens`. Skip the New Plan output template.

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

- [ ] Every merge justified by a concrete smell; merge groups respect domain boundaries
- [ ] Data reunification has explicit per-group strategy
- [ ] Consumer migration plan with deprecation timeline; every phase has rollback
- [ ] Services that stay separate are listed with reasons
- [ ] Blast radius increase from merging is acknowledged with mitigations
- [ ] Section 1 landscape completed before smell detection
- [ ] If depth = deep: dependency deep-dive and latency model present

## Avoid

- Merging across unrelated domains just to reduce service count
- Assuming merge is simpler than split - undoing a merge is expensive
- Consolidation without clear operational or architectural justification
