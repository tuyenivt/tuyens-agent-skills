---
name: strangler-fig-pattern
description: "Phased migration plan to incrementally route traffic from legacy to replacement: coexistence, verification gates, per-stage rollback."
metadata:
  category: architecture
  tags: [architecture, migration, strangler-fig, incremental, legacy, modernization]
user-invocable: false
---

# Strangler Fig Pattern

> Load `Use skill: stack-detect` first. Primary consumers: `task-decompose-monolith` Section 4, `task-modernize-legacy` Section 5.

## When to Use

- Migrating traffic from a legacy system to a new implementation incrementally
- Decomposing a monolith into services without big-bang rewrite
- Replacing a legacy technology while keeping the system running
- Any migration where parallel run and incremental cutover reduce risk

## Rules

- Legacy and new systems coexist throughout migration; rollback to legacy is possible at every stage until decommission
- Every migrated capability passes a verification gate before promotion
- Data consistency between legacy and new is addressed explicitly per phase
- Migration order is set by risk and dependency, not convenience or team preference

## Pattern

### Five phases

**1. Intercept** - Place a routing layer (proxy, gateway, facade) in front of legacy. All traffic still flows to legacy. Establish baseline metrics (latency, error rate, throughput) per capability and verify the routing layer adds no observable degradation.

**2. Build** - Implement the target capability in the new system, running alongside legacy with no production traffic. Validate functional correctness with tests and shadow traffic if possible. Establish dual-write or data-sync strategy if data ownership is migrating.

**3. Route** - Gradually shift traffic from legacy to new. Start with lowest-risk segment (internal users, read-only operations, low-volume endpoints). Use feature flags or traffic percentage to control rollout. Compare responses (shadow comparison or canary metrics). Promote only when error rate and latency stay within baseline and data consistency holds.

**4. Verify and Expand** - Confirm data consistency, monitor edge cases that surface at higher percentages, expand to the next capability only after the current is stable at 100%. Update routing to point migrated capability directly at the new system.

**5. Decommission** - Verify zero traffic to legacy for migrated capabilities. Remove legacy code paths, data sync jobs, compatibility shims, routing rules, and feature flags. Archive legacy documentation.

### Routing Strategy

| Method             | Use When                                         | Trade-off                                     |
| ------------------ | ------------------------------------------------ | --------------------------------------------- |
| URL-path routing   | Capabilities map cleanly to URL paths            | Simple; breaks if paths overlap               |
| Header-based       | Need to route same path to different backends    | Requires client cooperation or gateway logic  |
| Traffic percentage | Gradual rollout of same capability               | Requires stateless or sticky sessions         |
| Feature flag       | Per-user or per-tenant migration                 | More control; more complexity                 |
| Data-based         | Route by partition (tenant, region, entity)      | Enables per-tenant migration; complex routing |

### Data Migration Strategy

| Strategy                  | Use When                                      | Risk                                      |
| ------------------------- | --------------------------------------------- | ----------------------------------------- |
| Dual-write                | Both systems must have current data           | Write amplification, consistency risk     |
| CDC (change data capture) | Async replication acceptable                  | Replication lag, ordering issues          |
| Read from legacy          | New system queries legacy for unmigrated data | Coupling to legacy; latency               |
| Batch sync                | Freshness tolerance is hours/days             | Stale data, sync job failures             |
| Full migration            | Clean cutover possible for data partition     | Requires downtime or careful coordination |

### Migration Order

Default order, adapt to context: stateless read-only → stateless writes → stateful with simple data models → complex domain operations → shared infrastructure (auth, logging, config) last because its blast radius is widest.

### Verification Gate

Before promoting each migrated capability:

- [ ] Functional parity confirmed (same inputs produce equivalent outputs)
- [ ] Error rate and latency within baseline thresholds
- [ ] Data consistency verified (no loss, no duplicates)
- [ ] Rollback tested and confirmed working
- [ ] Downstream consumers unaffected
- [ ] Production-traffic edge cases handled

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
| Routing layer    | {gateway, proxy, or facade - chosen from Routing Strategy table}         |
| Data strategy    | {chosen from Data Migration Strategy table}                              |
| Estimated phases | {count}                                                                  |

### Capability Migration Sequence

| #   | Capability   | Current Phase                             | Routing Method | Data Strategy | Verification Status     | Rollback Method |
| --- | ------------ | ----------------------------------------- | -------------- | ------------- | ----------------------- | --------------- |
| 1   | {capability} | Intercept/Build/Route/Verify/Decommission | {method}       | {strategy}    | {gate checklist status} | {how to revert} |
```

## Avoid

- Migrating multiple capabilities simultaneously before any is verified
- Skipping the routing layer - direct client changes are irreversible
- Decommissioning legacy before confirming zero traffic
- Assuming functional parity without shadow comparison or canary verification
