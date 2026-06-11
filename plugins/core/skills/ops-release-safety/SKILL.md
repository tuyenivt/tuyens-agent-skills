---
name: ops-release-safety
description: Plan rollout strategy, rollback triggers, and schema-deploy ordering for safe production releases.
metadata:
  category: ops
  tags: [deployment, rollout, rollback, canary, schema-deploy, multi-service]
user-invocable: false
---

# Release Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing deployment strategy for a new feature or risky change
- Planning rollback capability and triggers before ship
- Evaluating deploy risk for schema changes, data migrations, or multi-service rollouts

## Rules

- Every deployment ships with a rollback plan, defined before merge.
- Code must run against both the previous and the new schema during rolling deploy.
- Changes with wide blast radius use canary or progressive rollout, not big-bang.
- Rollback triggers are observable thresholds (error rate, latency, saturation), not judgement calls.
- Destructive migrations (DROP / RENAME) deploy **after** the code that stops reading the column is live and verified.
- Code that requires populated data in a new column deploys **after** the backfill is verified complete.
- One risky change per deploy. Do not bundle schema migrations, config changes, and features in a single release - split so a triggered rollback is attributable and each piece reverts independently.
- Irreversible steps (in-place backfill, third-party writes, sent emails) get a verification gate and a backup/export **before** execution, and a roll-forward plan instead of a rollback plan past that point.

## Patterns

### Rollout Strategies

| Strategy       | Use When                                | Rollback Speed | Risk |
| -------------- | --------------------------------------- | -------------- | ---- |
| Feature flag   | High-risk logic, gradual user exposure  | Instant        | Low  |
| Canary         | Infrastructure or performance changes   | Fast (minutes) | Low  |
| Blue-green     | Full environment swap needed            | Fast (minutes) | Med  |
| Rolling update | Low-risk, stateless services            | Moderate       | Med  |
| Big bang       | Never (avoid)                           | Slow           | High |

For flag-gated rollouts, use skill: `ops-feature-flags` for stage sequencing, promotion criteria, rollback triggers, and cleanup.

### Schema Deploy Sequencing

Verify deploy order explicitly for any change that combines a migration with code changes.

| Change         | Correct order                            | Wrong order (flag as High)                        |
| -------------- | ---------------------------------------- | ------------------------------------------------- |
| Add column     | Migration -> code                        | Code first (references non-existent column)       |
| Drop column    | Code stops reading -> migration          | Migration first (code breaks on missing column)   |
| Rename column  | Expand-contract; never single-step       | Rename + code change in same deploy               |
| Add index      | Migration first; additive                | N/A                                               |
| Backfill-read  | Migration -> backfill -> verify -> code  | Code deployed before backfill verified            |

Use skill: `ops-backward-compatibility` for the full compatibility matrix and dual-write/dual-read assessment.
Use skill: `backend-db-migration` for expand-contract phasing, lock-risk analysis, and backfill mechanics.

### Multi-Service Schema Changes

When multiple services read from the same table, schema changes require coordination:

- **Additive** (nullable column, new table): migration first; readers ignore. No coordination needed.
- **Behavioral** (new NOT NULL, new default): verify every reader tolerates the new behavior before applying.
- **Destructive** (drop, rename): deploy all readers to stop using the column, verify zero reads/writes, then migrate.
- **Document affected services** in the rollout plan: list every service that touches the table and its required deploy order.

### Good

```
Rollout: Canary to 5% for 30 min
Monitor: p99 latency < 500 ms, error rate < 0.1%
Rollback trigger: error rate > 0.5% OR p99 > 2 s for 5 min
Rollback action: revert to previous deployment version
DB migration: additive only (new nullable column), backward compatible
Feature flag: ENABLE_NEW_PRICING - internal -> 10% -> 50% -> 100% over 3 days
```

### Bad

```
Deploy to all instances. If something breaks, we will fix it.
```

## Output Format

Consuming workflow skills parse this structure to produce actionable rollout and rollback plans.

```
## Release Safety Assessment

**Rollout strategy:** {Feature flag | Canary | Blue-green | Rolling update}
**Rollback speed:** {Instant | Fast (minutes) | Moderate | Slow}
**DB migration backward compatible:** Yes / No / N/A

### Rollout Plan

1. {step} - {rationale}
2. {step} - {monitor: metric and threshold}

### Rollback Triggers

- {observable condition, e.g., "error rate > 0.5% for 5 minutes"} -> {rollback action}

### Rollback Plan

1. {step} - {data safety note if applicable}
2. {mark irreversible steps "Point of no return" and give the roll-forward action instead}

### Risks

- [Severity: High | Medium | Low] {description of deployment risk}
  - Mitigation: {concrete action}

### No Risks Found

{State explicitly if no safety risks are identified - do not omit silently.}
```

Rollout Plan, Rollback Triggers, and Rollback Plan are mandatory. Omit "No Risks Found" if risks were listed.

- **Rollback speed:** report the fastest available control layer (flag kill switch > traffic shift > redeploy); note slower layers in the Rollback Plan.
- **Bundled releases:** assess each part separately, recommend the split in the Rollout Plan, and report the strategy of the riskiest part.
- **Irreversible releases:** the Rollback Plan states the roll-forward plan and the verification gate that precedes the point of no return - never fabricate rollback steps for state that cannot be restored.

## Avoid

- Deploying without a rollback plan, or with one that requires data migration to undo.
- Schema migrations that break the previous code version.
- Destructive migrations applied before the code that stops referencing them is live.
- Code that assumes a column is populated before backfill is verified.
- Multi-service schema changes without an explicit, documented service deploy order.
- Big-bang deploys for high-blast-radius changes.
