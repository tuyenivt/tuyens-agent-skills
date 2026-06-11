---
name: ops-feature-flags
description: Feature flag lifecycle - design, gradual rollout, rollback triggers, and cleanup discipline for release workflows.
metadata:
  category: ops
  tags: [feature-flags, rollout, gradual-release, rollback, cleanup, multi-stack]
user-invocable: false
---

# Feature Flags

> Load `Use skill: stack-detect` first to identify the framework and any feature flag library in use.

## When to Use

- Designing a flag for a new feature or risky change
- Planning a gradual rollout with traffic percentage control
- Defining rollback criteria tied to observable signals
- Reviewing flag lifecycle and cleanup discipline

## Rules

- Every flag has a single, named owner. Release flags also get a cleanup target set at creation; permanent flags (kill switch, ops, permission) get documented valid states instead.
- Name flags positively for the new behavior (`pricing_v2_enabled`); never negations or double negatives (`disable_legacy_pricing_off`).
- Every high-risk feature has a **kill switch** that disables it without redeploy - the rollout flag itself when turning it off fully reverts behavior; a separate kill-switch flag only when the risky path must be disabled independently of rollout state.
- Promotion to the next stage requires meeting promotion criteria; rollback triggers fire on any breach.
- One flag controls one behavior. Flags that gate multiple behaviors cannot be rolled back cleanly.
- Flags never bypass auth or security checks.
- Reaching 100% rollout starts the cleanup clock; remove flag and dead branches within one sprint.

## Patterns

### Flag Lifecycle

Four stages; skipping any creates technical debt.

1. **Introduction** - flag created, feature hidden behind it, default off.
2. **Gradual Rollout** - enabled for increasing traffic or user cohorts.
3. **Full Rollout** - 100% of traffic. Feature is live.
4. **Cleanup** - flag and all conditional code removed.

### Flag Types

| Type            | Shape                                                            | Use For                                |
| --------------- | ---------------------------------------------------------------- | -------------------------------------- |
| Boolean on/off  | default false; rollout 0% -> 5% -> 25% -> 100%                   | Simple toggles, gradual rollouts       |
| User / group    | targeting: internal-users, beta-group, tenant-id-X; default off  | Internal testing, beta, tenant scoping |
| Kill switch     | default false (feature runs); when true, feature disables        | Emergency disable for high-risk paths  |

### Gradual Rollout

| Risk     | Sequence                              | Soak per Stage      |
| -------- | ------------------------------------- | ------------------- |
| Low      | 25% -> 100%                           | 15 min              |
| Medium   | 5% -> 25% -> 100%                     | 30 min              |
| High     | 1% -> 5% -> 25% -> 100%               | 1-4 h               |
| Critical | Internal -> 1% -> 5% -> 25% -> 100%   | 4+ h                |

**Promotion criteria** (all green before advancing):

- Error rate within baseline +/-10% for affected endpoints
- p99 latency within baseline +/-20%
- No unexpected exceptions in logs
- Business metrics not degraded

**Rollback triggers** (any one fires immediate disable):

- Error rate exceeds the threshold defined before rollout
- p99 latency spike >50% above baseline sustained >5 min
- Data corruption or consistency issue detected

### Rollback Procedure

1. Disable the flag (instant, no redeploy).
2. Verify error rate returns to baseline within 2-3 min.
3. Investigate root cause before re-enabling.
4. If the flag will not disable cleanly, escalate to code rollback.

Test the disable procedure in staging before production rollout.

### Flag Interactions

For `n` boolean flags in one code path, combinations grow as `2^n`. Limit concurrent flags in a path to 2-3. Document valid combinations, and test the critical ones explicitly when flags modify the same data flow.

### Code Placement

Evaluate the flag at the boundary, not inside business logic.

```
// Bad - flag scattered through downstream code
if (flags.newRecommendations) { ... }   // cart
if (flags.newRecommendations) { ... }   // checkout
if (flags.newRecommendations) { ... }   // analytics

// Good - single toggle point, strategy swapped at the boundary
const engine = flags.newRecommendations
  ? new NewRecommendationEngine()
  : new LegacyRecommendationEngine()
// Downstream code uses the engine interface, unaware of the flag
```

### Cleanup Checklist

- [ ] Flag removed from feature flag service / config
- [ ] All conditional branches removed from code (deleted, not commented)
- [ ] Tests no longer reference the flag
- [ ] Changelog updated if user-visible behavior changed

A flag at 100% that is not cleaned within a sprint becomes invisible technical debt: the dead branch stays in production as cognitive overhead and a future failure surface.

## Output Format

Use this template when designing or reviewing a flag.

```
## Feature Flag Design

**Flag name**: {descriptive-feature-name-enabled}
**Type**: {boolean | user-targeting | kill-switch}
**Default**: {on | off}
**Owner**: {team or engineer}
**Cleanup target**: {date or "within 1 sprint of 100% rollout"}

## Rollout Plan

| Stage    | Traffic        | Promotion Criteria       | Rollback Trigger      | Soak   |
| -------- | -------------- | ------------------------ | --------------------- | ------ |
| Internal | Internal users | No errors                | Any error             | 1 h    |
| Canary   | 5%             | Error rate <baseline+10% | Error rate >threshold | 30 min |
| Broad    | 50%            | Same                     | Same                  | 30 min |
| Full     | 100%           | Same                     | Same                  | 30 min |

## Rollback Procedure

1. {Specific flag disable step}
2. {Verify signal to confirm rollback worked}

## Cleanup Checklist

- [ ] Flag removed from config
- [ ] Conditional branches removed from code
- [ ] Tests updated
- [ ] Changelog entry added
```

## Avoid

- Flags without a cleanup plan (accumulate indefinitely).
- DB writes inside a flag conditional without dual-write (rollback corrupts data).
- Flags that bypass auth or security checks.
- Per-environment flag state without a single source of truth (config drift).
- One flag controlling multiple unrelated behaviors (cannot roll back cleanly).
- More than 2-3 active flags in one code path without combination testing.
