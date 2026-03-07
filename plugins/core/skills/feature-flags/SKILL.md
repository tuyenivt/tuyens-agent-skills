---
name: feature-flags
description: Feature flag lifecycle - flag design, gradual rollout, rollback, and cleanup discipline. Used by release planning and feature implementation workflows.
metadata:
  category: ops
  tags: [feature-flags, rollout, gradual-release, rollback, cleanup, multi-stack]
user-invocable: false
---

# Feature Flags

> Load `Use skill: stack-detect` first to identify the framework and any feature flag library in use.

## When to Use

- Designing a feature flag for a new feature or risky change
- Planning a gradual rollout with traffic percentage control
- Defining rollback criteria tied to observable signals
- Reviewing flag lifecycle and cleanup discipline

## Flag Lifecycle

Every feature flag goes through four stages. Skipping any stage creates technical debt.

**1. Introduction** - Flag created, feature hidden behind it. Default: off.

**2. Gradual Rollout** - Flag enabled for increasing percentages of traffic or users.

**3. Full Rollout** - Flag enabled for 100% of traffic. Feature is live.

**4. Cleanup** - Flag and all conditional code removed. This is non-negotiable.

## Flag Design Patterns

### Boolean On/Off Flag (most common)

```
flag: feature-X-enabled
default: false
rollout: 0% → 5% → 25% → 100%
```

Use for: simple feature toggles, kill switches, gradual rollouts.

### User/Group Flag

```
flag: feature-X-enabled
targeting: [internal-users, beta-group, tenant-id-123]
default: false
```

Use for: internal testing, beta programs, tenant-specific features.

### Kill Switch

```
flag: feature-X-kill-switch
default: false (feature runs normally)
when true: disables the feature immediately
```

Use for: emergency disable without redeployment. Every high-risk feature should have one.

## Gradual Rollout Strategy

| Risk Level | Rollout Sequence                | Soak Time per Stage  |
| ---------- | ------------------------------- | -------------------- |
| Low        | 25% → 100%                      | 15 minutes           |
| Medium     | 5% → 25% → 100%                 | 30 minutes per stage |
| High       | 1% → 5% → 25% → 100%            | 1-4 hours per stage  |
| Critical   | Internal → 1% → 5% → 25% → 100% | 4+ hours per stage   |

**Promotion criteria** (must be green before advancing):

- Error rate for affected endpoints within baseline ±10%
- p99 latency within baseline ±20%
- No unexpected exceptions in logs
- Business metrics (if applicable) not degraded

**Rollback trigger** (any of these = disable flag immediately):

- Error rate exceeds rollback threshold (define before rollout)
- p99 latency spike >50% above baseline sustained for >5 minutes
- Data corruption or consistency issue detected

## Rollback Procedure

1. Disable the flag (instant, no redeployment required)
2. Verify error rate returns to baseline (within 2-3 minutes)
3. Investigate root cause before re-enabling
4. If flag cannot be disabled cleanly, escalate to code rollback

**Rollback must be testable before production rollout.** Run through the disable procedure in staging.

## Cleanup Discipline

Flags are temporary. Every flag must have:

- An owner responsible for cleanup
- A cleanup target date (set when the flag reaches 100% rollout)
- A ticket in the backlog before full rollout

**Cleanup checklist:**

- [ ] Flag removed from feature flag service/config
- [ ] All `if (flagEnabled)` / `when (flag)` branches removed from code
- [ ] Dead code branch deleted (not commented out)
- [ ] Tests updated - no tests should reference the flag after cleanup
- [ ] Flag documented in changelog if it changed user-visible behavior

**Stale flag risk:** A flag at 100% that is not cleaned up within one sprint becomes invisible technical debt. The conditional code path stays in production, adding cognitive overhead and a future failure surface.

## Anti-Patterns

| Anti-Pattern                                               | Risk                            | Fix                                                                  |
| ---------------------------------------------------------- | ------------------------------- | -------------------------------------------------------------------- |
| Flag with no cleanup plan                                  | Accumulates indefinitely        | Set cleanup date at flag creation                                    |
| Database writes inside flag conditional without dual-write | Data inconsistency on rollback  | Use dual-write or separate writes from flag scope                    |
| Flag that bypasses auth or security checks                 | Security gap                    | Never use flags to bypass security - use separate auth configuration |
| Flag per environment without a single source of truth      | Config drift                    | Centralize flag state; environment overrides only for testing        |
| Flag that controls multiple unrelated behaviors            | Impossible to roll back cleanly | One flag, one behavior                                               |

## Output Format

When designing or reviewing a feature flag:

```markdown
## Feature Flag Design

**Flag name**: [descriptive-feature-name-enabled]
**Type**: [boolean | user-targeting | kill-switch]
**Default**: [on | off]
**Owner**: [team or engineer]
**Cleanup target**: [date or "within 1 sprint of 100% rollout"]

## Rollout Plan

| Stage    | Traffic        | Promotion Criteria       | Rollback Trigger      | Soak   |
| -------- | -------------- | ------------------------ | --------------------- | ------ |
| Internal | Internal users | No errors                | Any error             | 1 hour |
| Canary   | 5%             | Error rate <baseline+10% | Error rate >threshold | 30 min |
| Broad    | 50%            | Same                     | Same                  | 30 min |
| Full     | 100%           | Same                     | Same                  | 30 min |

## Rollback Procedure

1. [Specific flag disable step]
2. [Verify signal to confirm rollback worked]

## Cleanup Checklist

- [ ] Flag removed from config
- [ ] Conditional branches removed from code
- [ ] Tests updated
- [ ] Changelog entry added
```
