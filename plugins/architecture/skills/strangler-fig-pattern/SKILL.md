---
name: strangler-fig-pattern
description: "Phased migration plan to incrementally route traffic from legacy to replacement: coexistence, verification gates, per-stage rollback."
metadata:
  category: architecture
  tags: [architecture, migration, strangler-fig, incremental, legacy, modernization]
user-invocable: false
---

# Strangler Fig Pattern

> Load `Use skill: stack-detect` first to determine the project stack. Primary consumers: `task-migrate-monolith-to-services` Section 4, `task-modernize-legacy` Section 5.

## When to Use

- Migrating traffic from a legacy system to a new implementation incrementally
- Decomposing a monolith into services without big-bang rewrite
- Replacing a legacy technology while keeping the system running
- Any migration where parallel run and incremental cutover reduce risk

## Rules

- Migration is always incremental; legacy and new systems coexist throughout
- Every migrated capability passes a verification gate before promotion
- Rollback to legacy is possible at every stage until decommission
- Data consistency between legacy and new is addressed explicitly per phase
- Migration order is set by risk and dependency, not convenience

## Pattern

### Migration Phases

Every strangler fig migration follows five phases:

**Phase 1: Intercept** - Place a routing layer (proxy, gateway, facade) in front of the legacy system.

- All traffic flows through the routing layer to legacy (no behavior change)
- Establish baseline metrics: latency, error rate, throughput per capability
- Verify the routing layer adds no observable degradation

**Phase 2: Build** - Implement the target capability in the new system.

- New system runs alongside legacy but receives no production traffic
- Validate functional correctness with tests and shadow traffic if possible
- Establish data sync or dual-write strategy if data ownership is migrating

**Phase 3: Route** - Gradually shift traffic from legacy to new system.

- Start with lowest-risk traffic segment (internal users, read-only operations, low-volume endpoints)
- Use feature flags or traffic percentage routing to control rollout
- Compare responses between legacy and new (shadow comparison or canary metrics)
- Promotion criteria: error rate within baseline, latency within baseline, data consistency verified

**Phase 4: Verify and Expand** - Validate migrated capability and proceed to next.

- Confirm data consistency between legacy and new system
- Monitor for edge cases that only surface at higher traffic percentages
- Expand to next capability only after current capability is stable at 100%
- Update routing layer to point migrated capability directly to new system

**Phase 5: Decommission** - Remove legacy capability after full migration.

- Verify zero traffic to legacy for migrated capabilities
- Remove legacy code paths, data sync jobs, and compatibility shims
- Clean up routing rules, feature flags, and dual-write logic
- Archive legacy system documentation for reference

### Routing Strategy

| Routing Method     | Use When                                         | Trade-off                                     |
| ------------------ | ------------------------------------------------ | --------------------------------------------- |
| URL-path routing   | Capabilities map cleanly to URL paths            | Simple; breaks if paths overlap               |
| Header-based       | Need to route same path to different backends    | Requires client cooperation or gateway logic  |
| Traffic percentage | Gradual rollout of same capability               | Requires stateless or sticky sessions         |
| Feature flag       | Per-user or per-tenant migration                 | More control; more complexity                 |
| Data-based         | Route by data partition (tenant, region, entity) | Enables per-tenant migration; complex routing |

### Data Migration During Strangler Fig

| Strategy                  | Use When                                      | Risk                                      |
| ------------------------- | --------------------------------------------- | ----------------------------------------- |
| Dual-write                | Both systems must have current data           | Write amplification, consistency risk     |
| CDC (change data capture) | Async replication acceptable                  | Replication lag, ordering issues          |
| Read from legacy          | New system queries legacy for unmigrated data | Coupling to legacy; latency               |
| Batch sync                | Data freshness tolerance is hours/days        | Stale data, sync job failures             |
| Full migration            | Clean cutover possible for data partition     | Requires downtime or careful coordination |

### Migration Order Heuristics

Migrate capabilities in this order (adapt based on context):

1. **Stateless read-only endpoints** - lowest risk, easiest to verify
2. **Stateless write endpoints** - verify data writes to new system
3. **Stateful operations with simple data models** - test data ownership transfer
4. **Complex domain operations** - highest risk, most dependencies
5. **Shared infrastructure** (auth, logging, config) - migrate last, highest blast radius

### Verification Gate

Before promoting each migrated capability:

- [ ] Functional parity confirmed (same inputs produce equivalent outputs)
- [ ] Error rate within baseline threshold
- [ ] Latency within baseline threshold
- [ ] Data consistency verified (no data loss, no duplicates)
- [ ] Rollback tested and confirmed working
- [ ] Downstream consumers unaffected
- [ ] Edge cases from production traffic handled

### Example phase entry

```
Capability: GET /orders/{id} | Phase: Route
Routing: gateway %, week 1: 5% -> week 3: 100% (gated on canary metrics)
Data: CDC replication from monolith DB
Verification: shadow comparison >99.9%, p99 within 10% of baseline
Rollback: gateway config flip, <1 min to 100% legacy
```

## Output Format

```markdown
## Strangler Fig Migration Plan

### Migration Overview

| Aspect           | Detail                                                                   |
| ---------------- | ------------------------------------------------------------------------ |
| Legacy system    | {name, stack}                                                            |
| Target system    | {name, stack}                                                            |
| Routing layer    | {gateway, proxy, or facade -- chosen method from Routing Strategy table} |
| Data strategy    | {chosen method from Data Migration table}                                |
| Estimated phases | {count}                                                                  |

### Capability Migration Sequence

| #   | Capability   | Current Phase                             | Routing Method | Data Strategy | Verification Status     | Rollback Method |
| --- | ------------ | ----------------------------------------- | -------------- | ------------- | ----------------------- | --------------- |
| 1   | {capability} | Intercept/Build/Route/Verify/Decommission | {method}       | {strategy}    | {gate checklist status} | {how to revert} |

### Decommission Checklist

- [ ] Zero traffic confirmed to legacy for all migrated capabilities
- [ ] Legacy code paths removed
- [ ] Data sync jobs stopped and removed
- [ ] Routing rules cleaned up
- [ ] Feature flags removed
- [ ] Legacy documentation archived
```

## Avoid

- Migrating multiple capabilities simultaneously before any is verified
- Skipping the routing layer - direct client changes are irreversible
- Decommissioning legacy before confirming zero traffic
- Assuming functional parity without shadow comparison or canary verification
