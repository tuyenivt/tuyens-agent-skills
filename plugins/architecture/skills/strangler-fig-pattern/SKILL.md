---
name: strangler-fig-pattern
description: "Phased migration plan to incrementally route traffic from legacy to replacement: coexistence, verification gates, per-stage rollback."
metadata:
  category: architecture
  tags: [architecture, migration, strangler-fig, incremental, legacy, modernization]
user-invocable: false
---

# Strangler Fig Pattern

> Primary consumer: `task-migrate-architecture` Section 5 (Phasing and Cutover). The legacy and target stacks named in the Migration Overview come from the caller, which knows both; a single-project detection pass cannot supply the target system's stack, and nothing else in this skill branches on the stack, so none is run here.

## When to Use

- Migrating traffic from a legacy system to a new implementation incrementally
- Decomposing a monolith into services without big-bang rewrite
- Replacing a legacy technology while keeping the system running
- Assessing or unblocking a migration already in flight
- Any migration where parallel run and incremental cutover reduce risk

## Rules

- A capability is the unit of routing and rollback: the smallest slice that can be routed and reverted independently (an endpoint group, event flow, or job - not a single field, not a whole bounded context). Slice larger surfaces until each slice reverts alone
- Legacy and new coexist throughout; rollback to legacy is possible at every stage until decommission
- Every migrated capability passes a verification gate before promotion to higher traffic
- Data consistency between legacy and new is addressed explicitly per phase
- Migration order is set by risk and dependency, not convenience or team preference
- Traffic-percentage rollout is unsafe for non-idempotent writes - route writes deterministically (flag, tenant, partition) or make them idempotent first

## Pattern

### Five phases

1. **Intercept** - place a routing layer (proxy, gateway, facade) in front of legacy. All traffic still flows to legacy. Establish baseline metrics (latency, error rate, throughput) per capability and verify the routing layer adds no observable degradation.
2. **Build** - implement the target capability in the new system alongside legacy with no production traffic. Validate with tests and shadow traffic if possible - shadow WRITES only into a side-effect-free target (stubbed providers or isolated environment). Idempotency does not make shadowing safe: a write issued by the new system is a distinct operation with its own key, so it duplicates state whether or not retrying it would. Establish dual-write or data-sync if data ownership is migrating. If existing consumers cannot change (contractual notice periods, clients you do not control), preserve the legacy contract behind a facade at the routing layer and freeze it until those consumers migrate.
3. **Route** - shift traffic gradually with a bake period at each step (e.g., 5% -> 25% -> 100%; default one week per step at production-representative load, shorter only with explicit justification). Start with the lowest-risk segment (internal users, read-only operations, low-volume endpoints). Routing methods compose - per-tenant migration is typically data-based partitioning plus a feature-flag registry. Compare responses (shadow or canary).
4. **Verify** - the verification gate (below) is the promotion criterion at every traffic step; Route and Verify alternate until 100%, so a capability mid-ladder records the phase it is waiting on plus its current share. On a gate failure:

   - **Go to 0%** when the failure corrupts data - writes bad state a fallback cannot repair.
   - **Reduce** to the last share that passed the gate for any failure users can feel: elevated errors, or data divergence a re-sync can repair. Where no share has passed, that is 0%. Re-promotion re-enters Route at the failed step with a fresh bake period.
   - **Hold** at the current share for every other failure - latency outside its band, an untested rollback, an unchecked downstream consumer, an unhandled edge case. Nothing is harming users yet, and dropping traffic would not fix any of them; the capability simply stops advancing until it passes.

   Schedule pressure never overrides the gate. Only after the capability is stable at 100% does the next capability enter Route.
5. **Decommission** - verify zero traffic to legacy for migrated capabilities. Remove legacy code paths, data sync jobs, compatibility shims, routing rules, and feature flags. Archive legacy documentation.

### Routing Strategy

| Method             | Use When                                         | Trade-off                                     |
| ------------------ | ------------------------------------------------ | --------------------------------------------- |
| URL-path routing   | Capabilities map cleanly to URL paths            | Simple; breaks if paths overlap               |
| Header-based       | Need to route same path to different backends    | Requires client cooperation or gateway logic  |
| Traffic percentage | Gradual rollout of same capability               | Requires stateless or sticky sessions; unsafe for non-idempotent writes, which must route deterministically instead |
| Feature flag       | Per-user or per-tenant migration                 | More control; more complexity                 |
| Data-based         | Route by partition (tenant, region, entity)      | Enables per-tenant migration; complex routing |
| Event subscription | Event-driven consumers with no request traffic   | Cut over per event type; needs dedupe while both consume |
| Job handover       | Batch/cron capabilities (no request traffic)     | Advances one partition at a time, never by percentage |

Batch and cron capabilities migrate by handing over job ownership - exactly one system runs the job per data partition at any time. A capability with a single partition therefore cuts over whole, in one step. Event consumers cut over per event type, with dedupe on the event ID for as long as both systems subscribe.

### Data Migration Strategy

| Strategy                  | Use When                                      | Risk                                           |
| ------------------------- | --------------------------------------------- | ---------------------------------------------- |
| Dual-write                | Both systems must have current data           | Write amplification, consistency risk          |
| CDC (change data capture) | Async replication acceptable                  | Replication lag, ordering issues               |
| Read from legacy          | New system queries legacy for unmigrated data | Coupling to legacy; latency                    |
| Batch sync                | Freshness tolerance is hours/days             | Stale data, sync job failures                  |
| Shared database           | Both systems use one DB during coexistence    | Schema coupling; migrations must stay additive |
| Allocator handover        | A single-writer resource (gapless sequence, ID allocator) moves whole | No gradual step; the other system calls the allocator until decommission |
| None - stateless          | The capability owns no data; it reads and acts    | Nothing to migrate, so the gate's data-consistency criterion is N/A |
| Reverse sync (new -> legacy) | Writes have moved but rollback must stay open | Runs alongside the forward strategy until decommission |
| Full migration            | Clean cutover possible for data partition     | Requires downtime or careful coordination      |

Gapless sequences need exactly one allocator at any instant: hand the role over atomically per partition, never split by percentage, and where a series cannot be partitioned at all keep one allocator and have the other system call it until decommission. Other ID schemes do not need this - UUIDs, ULIDs, snowflake IDs with per-node bits, and pre-allocated ranges are all safe to generate from both systems during coexistence. Once writes have moved, rollback needs the reverse-sync row above in addition to the forward strategy; state both per capability.

### Default Migration Order

Stateless read-only -> stateless writes -> stateful with simple data models -> complex domain operations -> shared infrastructure (auth, logging, config) last because its blast radius is widest.

### Verification Gate

Promote a capability only when all hold:

- Functional parity confirmed (same inputs produce equivalent outputs; for batch jobs, dry-run output diffing against the legacy run)
- Error rate at or below baseline; p99 latency within 10% of baseline (override these defaults explicitly if the plan needs different thresholds)
- Data consistency verified (no loss, no duplicates) against a stated freshness target (e.g., CDC lag < 5s p99). Where the strategy has no replication lag - shared database, read from legacy - the target is "no lag by construction" and the check is that the coupling still holds
- Rollback tested and confirmed working - re-validated at each promotion step, and covering the reverse-sync path once writes have moved
- Downstream consumers unaffected
- Production-traffic edge cases handled

A criterion without evidence scores Fail, not unknown - absence of verification is itself a gate failure. All six criteria appear in every Gate Assessment, each with its evidence or an empty cell that reads Fail.

### Example phase entry

Fields are blank-line separated, because these blocks are emitted into the delivered document where consecutive bare label lines collapse into one paragraph.

```
Capability: GET /orders/{id}

Phase: Route

Share: 25%

Routing: Traffic percentage at the gateway, 5% -> 25% -> 100%, 1-week bake per step

Data: CDC replication from monolith DB, lag SLO 5s p99

Verification: parity 99.97% over 4 days; error rate 0.31% vs 0.28% baseline; p99 244ms vs 210ms baseline; CDC lag 11s p99 against a 5s SLO; rollback last tested at 5%; downstream settlement batch unchecked; guest checkout routed to legacy

Rollback: gateway config flip, <1 min to 100% legacy; no reverse sync needed while writes remain on legacy
```

The Verification line records the state of all six criteria, since any left without evidence scores Fail. This example fails four of the six: the combined error-rate-and-p99 criterion (0.31% against a 0.28% baseline, and 244ms against 210ms - 16% over a 10% band), data consistency (CDC lag misses its SLO), rollback (not re-validated at the current step), and downstream consumers (the settlement batch is unchecked). Functional parity and edge cases pass. It does not promote.

## Output Format

```markdown
## Strangler Fig Migration Plan

### Migration Overview

| Aspect            | Detail                                                            |
| ----------------- | ----------------------------------------------------------------- |
| Legacy system     | {name, stack - supplied by the caller}                            |
| Target system     | {name, stack - supplied by the caller}                            |
| Routing layer     | {gateway, proxy, or facade; "mixed - see sequence table" when HTTP, event and job capabilities need different mechanisms} |
| Data strategy     | {chosen from Data Migration Strategy table; "mixed - see sequence table" when capabilities differ} |
| Capabilities      | {count} ({n} not started / {n} in flight / {n} done){, {n} rolled back} |

### Capability Migration Sequence

| #   | Capability   | Phase | Share | Routing Method | Data Strategy | Verification Status | Rollback Method | Ordered before the next because |
| --- | ------------ | ----- | ----- | -------------- | ------------- | ------------------- | --------------- | ------------------------------- |
| 1   | {capability} | {Intercept / Build / Route / Verify / Decommission / Rolled back} | {current traffic share; "{n} of {m} partitions" or "{n} of {m} event types" for job and event capabilities} | {every composed method, each named from the Routing Strategy table} | {every strategy in play, each named from the Data Migration Strategy table} | {n of 6 criteria passing; "not started" before the first Route step; "not assessed" when it is past that step but no evidence was supplied} | {how to revert, and the reverse-sync path once writes have moved} | {the risk or dependency that fixes this position} |

### Capability Phase Entries

{One block per capability in the Example phase entry format: routing with promotion steps and bake time, data strategy with freshness target, evidence for all six gate criteria, rollback method and time-to-revert.}
```

Not started counts Intercept and Build, in flight counts Route and Verify, done counts Decommission, and a rolled-back capability is counted separately. A capability holding at 100% with legacy code still present has finished Route and Verify but not removed anything, so it sits in `Decommission` and counts as in flight until the legacy path, sync jobs and flags are gone.

Phase reflects status at the time of writing, so a forward-looking plan reads `Intercept` with `Share: 0%`, and its Verification column and phase entries carry the gate criteria as a plan - what will be measured and against what - rather than evidence. Capabilities may sit at Intercept or Build together; the one-at-a-time rule binds Route onward, so only one capability is being promoted at a time.

`#` is migration order, set by risk and dependency; the last column states which of the two put each capability where it is, and reads "last - nothing follows" for the final row. Where a capability couples to one still in the monolith, say so in its phase entry's Data line.

The sequence table doubles as the live tracker during execution: it carries current state, and a Gate Assessment is appended for each capability in Route or Verify. With none there, say so in one line rather than dropping the section silently.

For each capability in Route or Verify, append a gate assessment:

```markdown
### Gate Assessment - {capability} at {current traffic share}

| Gate Criterion | Status (Pass/Fail) | Evidence |
| -------------- | ------------------ | -------- |
| Functional parity | {Pass/Fail} | {evidence, or empty - which reads Fail} |
| Error rate and p99 | {Pass/Fail} | {evidence} |
| Data consistency | {Pass/Fail} | {evidence} |
| Rollback tested | {Pass/Fail} | {evidence} |
| Downstream consumers | {Pass/Fail} | {evidence} |
| Edge cases | {Pass/Fail} | {evidence} |

**Promotion allowed:** {Yes | No - failing criteria}

**Action:** {Promote to <share> | Hold at <share> | Reduce to <share> | Go to 0%} - {remediation, and what must pass before the next attempt}
```

## Avoid

- Migrating multiple capabilities simultaneously before any is verified
- Skipping the routing layer - direct client changes are irreversible
- Decommissioning legacy before confirming zero traffic
- Assuming functional parity without shadow comparison or canary verification
- Promoting to meet a deadline while gate criteria fail
