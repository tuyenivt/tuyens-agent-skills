---
name: ops-feature-flags
description: Feature flag lifecycle - design, gradual rollout, rollback triggers, and cleanup discipline for release workflows.
metadata:
  category: ops
  tags: [feature-flags, rollout, gradual-release, rollback, cleanup, multi-stack]
user-invocable: false
---

# Feature Flags

## When to Use

- Designing a flag for a new feature or risky change
- Planning a gradual rollout with cohort control
- Defining rollback criteria tied to observable signals
- Reviewing flag lifecycle and cleanup discipline

## Rules

- Every flag has a single named owner (a person, with their team); when no person is named yet, the owner slot reads `unassigned - <role to assign>`. Release and user-targeting flags get a cleanup target set at creation; permanent flags (kill switch, ops, permission) get documented valid states and a review date instead - quarterly unless the owner sets otherwise.
- Name flags positively for the new behavior (`pricing_v2_enabled`); never negations or double negatives (`disable_legacy_pricing_off`). A kill switch names the thing it stops, with `true` meaning stopped (`payments_v2_killed`) - the rule bans names that require a double negative to read, not the kill switch's inherent polarity.
- Every high-risk feature can be disabled without a redeploy. While a release flag exists, turning it off is the kill switch - no second flag. A separate, permanent kill switch is designed only when the risky path must be disabled independently of the release flag's state, or after the release flag is cleaned up.
- A flag takes effect within the provider's propagation bound, which the design measures and records rather than assumes: a streaming SDK in about a second; a polling client on its next poll (tens of seconds for server SDKs, minutes in the foreground and up to an hour in the background for mobile SDKs, by vendor default); plus any local cache TTL. It takes effect only when evaluated per request or per unit of work - a flag read once at process start is a deploy-time switch, not a flag. When the provider is unreachable, the SDK keeps serving its last known values for as long as the process lives; the coded default is served only when no value was ever fetched (cold start with no cache) or the key is unknown, so the coded default is the safe state (off for a release flag, running for a kill switch).
- Promotion to the next stage requires every promotion criterion green; rollback fires on any breach of a rollback trigger.
- One flag controls one behavior. Flags that gate multiple behaviors cannot be rolled back cleanly; a new flag never reuses the name of a non-compliant one - redesign that flag or add a new one.
- Flags never bypass auth or security checks.
- Reaching 100% rollout starts the cleanup clock; record the date and remove flag and dead branches within one sprint.
- A flag declared in config but read by no code is dead: implement it or delete it. Dead means no code outside the declaration reads its key - search the whole service, not one module.

## Patterns

### Flag Lifecycle

Release and user-targeting flags pass through four stages; skipping any creates technical debt. Permanent flags have no progression and no end state.

1. **Introduction** - flag created, feature hidden behind it, default off.
2. **Gradual Rollout** - enabled for widening cohorts.
3. **Full Rollout** - 100% of traffic. Feature is live.
4. **Cleanup** - flag and all conditional code removed.

### Flag Types

| Type           | Shape                                                            | Use For                                |
| -------------- | ---------------------------------------------------------------- | -------------------------------------- |
| release        | default false; cohorts are percentage buckets from the Gradual Rollout ladder | Simple toggles, gradual rollouts |
| user-targeting | default off; cohorts are named targets (internal-users, beta-group, tenant-id-X) widened in order | Internal testing, beta, a tenant-by-tenant rollout that ends at every tenant (one that never will is `permission`) |
| kill-switch    | permanent; default false (feature runs); true disables           | Emergency disable for high-risk paths  |
| ops            | permanent; documented valid states, no rollout progression       | Throttles, maintenance mode            |
| permission     | permanent; documented valid states, no rollout progression       | Entitlements                           |

The cohort key decides between the first two: a percentage bucket on a unit of work (user, tenant, session, order) is `release`; an identity list is `user-targeting`. A single identifiable caller is a target, not a percentage - when the risk still calls for a ladder inside that caller's traffic, the type is `release` and the cohort key is the unit of work, stated in Evaluation. A Critical release flag opens on an `internal` target before its first percentage bucket.

### Gradual Rollout

Cohorts are bucketed on a stable key and stay in treatment across stages (a user in the 1% bucket is still in at 5% and 25%) as long as the bucketing key and the flag's salt never change mid-rollout; per-request bucketing flips one user between behaviors and makes cohort metrics meaningless. Each stage below carries its soak, a floor: the stage runs until the soak has passed and the sample exists. The final stage has no soak and no promotion criteria (no control cohort remains) - it starts the cleanup clock. A user-targeting flag replaces the percentage stages with its targets in widening order, pairs them with the row's soaks in order (the last soak repeats for extra targets), and ends at its full target set in place of `100%`.

| Risk     | Stages (soak)                                                                 |
| -------- | ----------------------------------------------------------------------------- |
| Low      | 25% (15 min) -> 100%                                                          |
| Medium   | 5% (30 min) -> 25% (30 min) -> 100%                                           |
| High     | 1% (1 h) -> 5% (2 h) -> 25% (4 h) -> 100%                                     |
| Critical | internal (4 h) -> 1% (4 h) -> 5% (4 h) -> 25% (one full traffic cycle, 24 h minimum, extended until every criterion holds) -> 100% |

**Promotion criteria** (all green before advancing), measured on the treatment cohort against the baseline - the control cohort, the traffic still on the old path at that stage; on the final row, the pre-rollout measurement:

- Error rate not above 1.1x baseline (relative, never percentage points)
- p99 latency not above 1.2x baseline
- No unexpected exceptions in logs
- Business metrics not degraded

A rate comparison needs enough events in both arms to see the gap: a 10% relative change in a 1% error rate takes on the order of 10^5 requests per arm, a p99 comparison about 10^4 - at ordinary traffic no early stage reaches that inside its soak. A stage that cannot reach the sample in a soak it can afford replaces the rate criteria and the rate triggers with absolute counts (`0 unexpected errors in the stage`, `no request over <p99 ceiling>`) and records the extended soak and why.

**Rollback triggers** (any one fires immediate disable), recorded with their numbers before rollout:

- Error rate above the recorded threshold in the cohort, relative to baseline (1.5x unless recorded otherwise), or the absolute count for a small sample
- p99 latency above 1.5x baseline sustained 5 min, or the absolute ceiling for a small sample
- Data corruption or consistency issue detected

### Rollback Procedure

1. Disable the flag (no redeploy; takes effect within the recorded propagation bound).
2. Verify on the cohort signal once the bound has elapsed; the flag's evaluation telemetry confirms later (SDKs flush it on an interval and dashboards aggregate over minutes), so it is the audit trail, not the prompt signal.
3. Reconcile anything the flagged branch wrote while it was on - disabling stops new writes but does not undo those already made. Identify the affected rows (a flag-version column or the rollout window's timestamps), then correct or quarantine them.
4. Investigate root cause before re-enabling.
5. If the flag will not disable cleanly, escalate to code rollback.

Rehearse the disable in staging before production rollout.

Design step 3 out of existence where you can: a branch that writes both shapes in one transaction, writes the old shape with the values the legacy path would have written, and mutates no shared state, or that computes into a shadow column read only when the flag is on, leaves no database state to reconcile. External side effects the branch emitted (charges, emails, webhooks, published events) are not undone by any of this and still need step 3.

### Flag Interactions

For `n` boolean flags in one code path, combinations grow as `2^n`. Limit concurrent flags in a path to 2-3. Document valid combinations, and test the critical ones explicitly when flags modify the same data flow.

### Code Placement

Evaluate the flag once per request at the boundary, with the evaluation context the rollout needs, and pass the chosen strategy down; never scatter the check through business logic.

```
// Bad - flag scattered through downstream code, and read without context
if (flags.isEnabled("recommendations_v2_enabled")) { ... }   // cart
if (flags.isEnabled("recommendations_v2_enabled")) { ... }   // checkout

// Good - one evaluation per request, cohort key supplied, coded default, strategy swapped at the boundary
const engine = flags.isEnabled("recommendations_v2_enabled", { userId: req.user.id }, false)
  ? new NewRecommendationEngine()
  : new LegacyRecommendationEngine()
// Downstream code uses the engine interface, unaware of the flag
```

### Cleanup

A flag at 100% that is not cleaned within a sprint becomes invisible technical debt: the dead branch stays in production as cognitive overhead and a future failure surface. The Cleanup Checklist in the Output Format is the record; branches are deleted, not commented out.

## Output Format

Release and user-targeting flags use this template. The Rollout Plan has one row per stage of the assessed risk's ladder (targets in widening order for a user-targeting flag); the final row is `100%` or the full target set, with `n/a` promotion criteria and soak.

```
## Feature Flag Design

**Flag name**: {feature_name_enabled}

**Type**: {release | user-targeting}

**Risk**: {Low | Medium | High | Critical} - {why}

**Default**: false - {what the off state serves: the legacy path, or the response returned when no legacy path exists}

**Owner**: {person (team) | unassigned - <role to assign>}

**Kill switch**: {this flag - off fully reverts | separate kill-switch `<name>` - why the path must be disabled independently}

**Evaluation**: {where the flag is read per request, the cohort key, the control cohort the criteria compare against, and the measured propagation bound}

**Interacting flags**: {other flags on the same path and the combinations tested, or "none"}

**Cleanup target**: {date, or "within 1 sprint of 100% rollout"}

**Reached 100% on**: {date, or "not yet"}

## Rollout Plan

| Stage | Cohort | Promotion Criteria | Rollback Trigger | Soak |
| ----- | ------ | ------------------ | ---------------- | ---- |
| {1..n} | {internal \| 1% \| 5% \| 25% \| 100% \| <target name>} | {error rate <= 1.1x baseline, p99 <= 1.2x baseline, no unexpected exceptions, business metrics held; or the absolute counts for a small sample} | {error rate > 1.5x baseline or >= N errors, p99 > 1.5x baseline for 5 min or > ceiling, corruption} | {ladder soak, or the extended soak and why} |

## Rollback Procedure

1. {disable step and the recorded propagation bound}
2. {cohort signal that confirms the old path after the bound; evaluation telemetry as the later audit}
3. {reconciliation of writes made while on, or "none - single-transaction dual-write / shadow column"; external side effects and their handling}
4. {root-cause gate before re-enable}
5. {code-rollback escalation condition}

Rehearsed in staging on: {date, or "pending"}

## Cleanup Checklist

- [ ] Flag removed from feature flag service / config
- [ ] All conditional branches removed from code (deleted, not commented)
- [ ] Tests no longer reference the flag
- [ ] Changelog updated if user-visible behavior changed
```

A permanent flag (kill-switch, ops, permission) has no rollout progression and no end state, so it drops `Risk`, the Rollout Plan, and the Cleanup Checklist, keeps the Rollback Procedure as the path back to its default state, and replaces `Cleanup target` and `Reached 100% on` with the states it is allowed to hold and its review date. `Default` is `false - feature runs` for a kill switch; ops and permission flags state the value and its meaning:

```
## Feature Flag Design

**Flag name**: {name}

**Type**: {kill-switch | ops | permission}

**Default**: {value} - {what that state means}

**Owner**: {person (team) | unassigned - <role to assign>}

**Kill switch**: {this flag | how the path it gates is disabled without a redeploy | n/a - not a high-risk path}

**Evaluation**: {where the flag is read per request, and the measured propagation bound}

**Interacting flags**: {as above}

**Valid states**: {each state, what it does, and who may set it}

**Review date**: {date the owner re-confirms this flag is still needed; one quarter out unless the owner sets otherwise}

## Rollback Procedure

1. {step that returns the flag to its default state, and the bound}
2. {signal that confirms the default path is served}
3. {reconciliation of writes made in the non-default state, or "none"}
4. {root-cause gate before leaving the default state again}
5. {code-rollback escalation condition}

Rehearsed in staging on: {date, or "pending"}
```

When reviewing existing flags rather than designing one, output findings instead, one entry per flag listing every violation; the entry's severity is the highest tier among its violations:

```
## Flag Review Findings

- [Severity: High | Medium | Low] {flag name} - {violations, comma-separated}
  - Fix: {one or more of: rename, cleanup, split, assign owner, add kill switch, add dual-write so disable is reversible, remove auth/security bypass, define promotion criteria and triggers, implement or delete (dead flag), record 100% date, set cleanup target, set review date, document valid states, document interactions}
```

Severity: High = auth/security bypass, un-rollback-able data writes, or no working disable on a path that needs a kill switch (a dead flag there included); Medium = stale at 100%, multi-behavior flag, missing owner, missing promotion criteria or rollback triggers, a dead ops or permission flag, undocumented valid states on a permanent flag; Low = naming, missing cleanup target, review date, or 100% date, undocumented interactions, any other dead flag.

## Avoid

- Flags without a cleanup plan (accumulate indefinitely).
- DB writes inside a flag conditional with neither single-transaction dual-write nor a shadow column (disabling leaves new-shape rows the old path misreads).
- Flags that bypass auth or security checks.
- Per-environment flag state without a single source of truth (config drift).
- One flag controlling multiple unrelated behaviors (cannot roll back cleanly).
- More than 2-3 active flags in one code path without combination testing.
