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
- Assessing or unblocking a migration already in flight
- Any migration where parallel run and incremental cutover reduce risk

## Rules

- Legacy and new coexist throughout; rollback to legacy is possible at every stage until decommission
- Every migrated capability passes a verification gate before promotion to higher traffic
- Data consistency between legacy and new is addressed explicitly per phase
- Migration order is set by risk and dependency, not convenience or team preference
- Traffic-percentage rollout is unsafe for non-idempotent writes - route writes deterministically (flag, tenant, partition) or make them idempotent first

## Pattern

### Five phases

1. **Intercept** - place a routing layer (proxy, gateway, facade) in front of legacy. All traffic still flows to legacy. Establish baseline metrics (latency, error rate, throughput) per capability and verify the routing layer adds no observable degradation.
2. **Build** - implement the target capability in the new system alongside legacy with no production traffic. Validate with tests and shadow traffic if possible. Establish dual-write or data-sync if data ownership is migrating. If existing consumers cannot change (contractual notice periods, clients you do not control), preserve the legacy contract behind a facade at the routing layer and freeze it until those consumers migrate.
3. **Route** - shift traffic gradually with a bake period at each step (e.g., 5% -> 25% -> 100%; default one week per step at production-representative load, shorter only with explicit justification). Start with the lowest-risk segment (internal users, read-only operations, low-volume endpoints). Routing methods compose - per-tenant migration is typically data-based partitioning plus a feature-flag registry. Compare responses (shadow or canary).
4. **Verify** - the verification gate (below) is the promotion criterion at every traffic step; Route and Verify alternate until 100%. A capability that fails the gate holds or reduces its traffic share until remediated - reduce when the failure harms users (data inconsistency, errors), hold when it is performance-only within tolerances. Schedule pressure never overrides the gate. Only after the capability is stable at 100% does the next capability enter Route.
5. **Decommission** - verify zero traffic to legacy for migrated capabilities. Remove legacy code paths, data sync jobs, compatibility shims, routing rules, and feature flags. Archive legacy documentation.

### Routing Strategy

| Method             | Use When                                         | Trade-off                                     |
| ------------------ | ------------------------------------------------ | --------------------------------------------- |
| URL-path routing   | Capabilities map cleanly to URL paths            | Simple; breaks if paths overlap               |
| Header-based       | Need to route same path to different backends    | Requires client cooperation or gateway logic  |
| Traffic percentage | Gradual rollout of same capability               | Requires stateless or sticky sessions         |
| Feature flag       | Per-user or per-tenant migration                 | More control; more complexity                 |
| Data-based         | Route by partition (tenant, region, entity)      | Enables per-tenant migration; complex routing |
| Job handover       | Batch/cron capabilities (no request traffic)     | No gradual rollout; cut over per partition    |

Batch and cron capabilities migrate by handing over job ownership - exactly one system runs the job per data partition at any time.

### Data Migration Strategy

| Strategy                  | Use When                                      | Risk                                           |
| ------------------------- | --------------------------------------------- | ---------------------------------------------- |
| Dual-write                | Both systems must have current data           | Write amplification, consistency risk          |
| CDC (change data capture) | Async replication acceptable                  | Replication lag, ordering issues               |
| Read from legacy          | New system queries legacy for unmigrated data | Coupling to legacy; latency                    |
| Batch sync                | Freshness tolerance is hours/days             | Stale data, sync job failures                  |
| Shared database           | Both systems use one DB during coexistence    | Schema coupling; migrations must stay additive |
| Full migration            | Clean cutover possible for data partition     | Requires downtime or careful coordination      |

Single-writer invariants (gapless sequences, ID generation) need exactly one writer at any instant: hand over the writer role atomically per partition - never split writes by percentage. For a global sequence that cannot be partitioned, keep one allocator (legacy or new) and have the other system call it until decommission. Rollback after writes have moved requires a reverse-sync path (new -> legacy) until decommission; state it per capability.

### Default Migration Order

Stateless read-only -> stateless writes -> stateful with simple data models -> complex domain operations -> shared infrastructure (auth, logging, config) last because its blast radius is widest.

### Verification Gate

Promote a capability only when all hold:

- Functional parity confirmed (same inputs produce equivalent outputs; for batch jobs, dry-run output diffing against the legacy run)
- Error rate at or below baseline; p99 latency within 10% of baseline (override these defaults explicitly if the plan needs different thresholds)
- Data consistency verified (no loss, no duplicates) against a stated freshness target (e.g., CDC lag < 5s p99)
- Rollback tested and confirmed working - re-validated at each promotion step
- Downstream consumers unaffected
- Production-traffic edge cases handled

A criterion without evidence scores Fail, not unknown - absence of verification is itself a gate failure.

### Example phase entry

```
Capability: GET /orders/{id} | Phase: Route
Routing: gateway %, 5% -> 25% -> 100%, 1-week bake per step (gated on canary metrics)
Data: CDC replication from monolith DB, lag SLO 5s p99
Verification: shadow comparison >99.9%, p99 within 10% of baseline
Rollback: gateway config flip, <1 min to 100% legacy
```

## Output Format

```markdown
## Strangler Fig Migration Plan

### Migration Overview

| Aspect            | Detail                                                            |
| ----------------- | ----------------------------------------------------------------- |
| Legacy system     | {name, stack}                                                     |
| Target system     | {name, stack}                                                     |
| Routing layer     | {gateway, proxy, or facade - chosen from Routing Strategy table}  |
| Data strategy     | {chosen from Data Migration Strategy table}                       |
| Capabilities      | {count} ({n} not started / {n} in flight / {n} done)              |

### Capability Migration Sequence

| #   | Capability   | Phase                                     | Routing Method | Data Strategy | Verification Status     | Rollback Method |
| --- | ------------ | ----------------------------------------- | -------------- | ------------- | ----------------------- | --------------- |
| 1   | {capability} | Intercept/Build/Route/Verify/Decommission | {every composed method} | {strategy} | {gate checklist status} | {how to revert} |

### Capability Phase Entries

{One block per capability in the Example phase entry format: routing with promotion steps and bake time, data strategy with freshness target, verification criteria, rollback method and time-to-revert.}
```

Phase reflects status at the time of writing - "Intercept (not started)" for forward-looking plans; the sequence table doubles as the live tracker during execution.

For an in-flight migration, append a gate assessment:

```markdown
### Gate Assessment - {capability} at {current traffic share}

| Gate Criterion | Status (Pass/Fail) | Evidence |
| -------------- | ------------------ | -------- |

**Promotion allowed:** {Yes | No - failing criteria}
**Remediation:** {actions, and the traffic share to hold or fall back to until the gate passes}
```

## Avoid

- Migrating multiple capabilities simultaneously before any is verified
- Skipping the routing layer - direct client changes are irreversible
- Decommissioning legacy before confirming zero traffic
- Assuming functional parity without shadow comparison or canary verification
- Promoting to meet a deadline while gate criteria fail
