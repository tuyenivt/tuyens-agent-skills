---
name: ops-release-safety
description: Plan rollout strategy, rollback triggers, and schema-deploy ordering for safe production releases.
metadata:
  category: ops
  tags: [deployment, rollout, rollback, canary, schema-deploy, multi-service]
user-invocable: false
---

# Release Safety

## When to Use

- Designing deployment strategy for a new feature or risky change
- Planning rollback capability and triggers before ship
- Evaluating deploy risk for schema changes, data migrations, one-shot scripts, or multi-service rollouts

## Rules

- Every deployment ships with a rollback plan, defined before merge.
- Old and new code must both run against both the old and the new schema during a rolling deploy - new code on the old schema while it rolls out, old instances on the new schema after the migration.
- Changes with wide blast radius use canary or progressive rollout, not big-bang.
- Rollback triggers are observable thresholds (error rate, latency, saturation), not judgement calls. A rate threshold needs enough traffic inside its evaluation window to mean anything: size the sample against the gap between baseline and trigger (telling 0.5% from 0.1% takes thousands of requests in the window, not hundreds), and where the canary slice cannot reach it - internal tools, low-traffic services - trigger on absolute counts (`>= 3 errors`) and extend the window or the slice until the sample exists. A 5% canary on a service serving 40 requests an hour proves nothing. When the whole audience is the canary (an internal tool built for that tool), the canary is a time slice: the full audience runs on absolute counts for a window long enough to hold them (`>= 3 errors` at 40 requests an hour needs several hours). The canary slice must also carry the traffic the change is for: an internal tool cannot canary a storefront path.
- Destructive migrations (the contract-phase DROP) deploy **after** the code that stops reading and writing the column is live and verified. A rename never issues a RENAME: it is the expand-contract row below.
- Code that requires populated data in a new column deploys **after** the backfill is verified complete.
- One risky change per deploy. Do not bundle schema migrations, config changes, and features in a single release - split so a triggered rollback is attributable and each piece reverts independently.
- Irreversible steps (in-place backfill, third-party writes, sent emails) get a verification gate and a backup/export **before** execution, and a roll-forward plan instead of a rollback plan past that point. A replay of third-party writes checks each item against the provider's record (idempotency key or provider id) and skips those already applied.
- A declared scope that the code contradicts ("no schema change in this slice" for a path that reads a column the same release adds) is a Risk, never accepted silently.

## Patterns

### Rollout Strategies

| Strategy        | Use When                                | Rollback Speed | Risk |
| --------------- | --------------------------------------- | -------------- | ---- |
| Feature flag    | High-risk logic, gradual user exposure  | Instant        | Low  |
| Canary          | Infrastructure or performance changes   | Fast (minutes) | Low  |
| Blue-green      | Full environment swap needed            | Fast (minutes) | Med  |
| Rolling update  | Low-risk, stateless services            | Moderate       | Med  |
| One-shot script | A batch write or replay run once        | None past the point of no return | High |
| Big bang        | Never (avoid)                           | Slow           | High |

`Use skill: ops-feature-flags` for flag-gated rollouts: stage sequencing, promotion criteria, rollback triggers, and cleanup.

### Schema Deploy Sequencing

Verify deploy order explicitly for any change that combines a migration with code changes. Each arrow is a separate release.

| Change         | Correct order                                              | Wrong order (flag as High)                        |
| -------------- | ---------------------------------------------------------- | ------------------------------------------------- |
| Add column     | Migration -> code, in separate releases                    | Code first (references non-existent column), or both in one release |
| Drop column    | Code stops reading and writing -> verify -> migration      | Migration first (code breaks on missing column)   |
| Rename column  | Expand (add new) -> dual-write code -> backfill -> read-new code -> contract; never single-step | Rename + code change in same deploy |
| Add index      | Online build as its own step; a unique index only after duplicates are cleared | A blocking build on a live table; a unique index while writers still produce duplicates |
| Backfill-read  | Migration -> dual-write code (or trigger) -> backfill -> verify drift zero -> read code | Code deployed before backfill verified, or backfill started before dual-write so new rows stay empty |

`Use skill: ops-backward-compatibility` for the full compatibility matrix and dual-write/dual-read assessment.
`Use skill: backend-db-migration` for expand-contract phasing, lock-risk analysis, and backfill mechanics.

### Multi-Service Schema Changes

When multiple services read or write the same table, schema changes require coordination:

- **Additive** (nullable column, new table): migration first; readers that select named columns ignore it. Verify readers that select `*` into strict mappings, and schema-validating CDC subscribers - "no coordination needed" is a claim about other teams' code and needs their confirmation.
- **Behavioral** (new NOT NULL, new default): a NOT NULL without a default breaks every writer that omits the column - verify every writer supplies a value before applying (with a constant default, old writers take the default); a changed default changes what readers see.
- **Destructive** (drop): deploy all readers and writers to stop using the column, verify zero reads/writes, then migrate. A rename is the expand-contract sequence, never a coordinated single step.
- **Affected services** are listed in the assessment with their required deploy order.

### Good

```
## Release Safety Assessment

**Rollout strategy:** Feature flag

**Rollback speed:** Instant - flag kill switch

**DB migration backward compatible:** Yes - additive nullable column

**Affected services:** orderflow-api (1: migration, 2: code behind the flag), storefront-web (3: reads the new field after 100%; tolerates absence until then)

### Rollout Plan

1. Deploy migration adding `orders.pricing_version` (nullable) - separate release, no code reads it yet
2. Deploy code behind `pricing_v2_enabled` = off - monitor: deploy error rate < 0.1% over 30 min (about 12,000 requests at baseline traffic)
3. Flag to internal cohort, then 5% -> 25% -> 100% (Medium ladder) - monitor per stage: cohort error rate <= 1.1x baseline and p99 <= 1.2x baseline with at least 3,000 cohort requests in the window, `orders_completed_total` held; the internal stage on absolute counts (0 errors, no request over 2 s)

### Rollback Triggers

- Cohort error rate > 0.5% over 5 min, with at least 3,000 cohort requests in the window -> flag off
- p99 > 2 s for 5 min in the cohort, with at least 1,000 cohort requests in the window -> flag off
- Any pricing mismatch found by the reconciliation job -> flag off and reconcile

### Rollback Plan

1. Flag off - within the recorded propagation bound (streaming SDK, about 1 s); no data written by the new path that the old path cannot read
2. Leave in place: the migration - nullable column, harmless to old code
3. Redeploy previous version only if the flag fails to disable

### Risks

- [Severity: Medium] The 5% stage on a weekday morning may not reach 3,000 cohort requests in 5 min
  - Mitigation: widen the window to 30 min for that stage; the internal stage already runs on absolute counts
```

### Bad

```
Deploy to all instances. If something breaks, we will fix it.
```

## Output Format

Consuming workflow skills parse this structure to produce actionable rollout and rollback plans. The header describes the riskiest part of a bundled release - the part whose failure is hardest to undo: irreversible third-party writes, then destructive schema, then data backfill, then code; every other slot names the part it applies to. The strategy value is the mechanism the code implements; `(as proposed)` follows it when the plan names a different one. Rollback speed is the fastest control layer that reverts the riskiest part (flag kill switch > traffic shift > redeploy); a layer that exists but does not work (an unwired flag, a flag read once at process start) does not count.

```
## Release Safety Assessment

**Rollout strategy:** {Feature flag | Canary | Blue-green | Rolling update | One-shot script | Big bang}{ (as proposed)}

**Rollback speed:** {Instant | Fast (minutes) | Moderate | Slow | None past the point of no return} - {the control layer that reverts the riskiest part}

**DB migration backward compatible:** {Yes | No | N/A - no schema change} - {reason; for a bundle, the worst part}

**Affected services:** {every service that touches the changed surface, with its deploy position, or "none beyond this service"}

### Rollout Plan

1. {step, naming the part it ships} - {rationale}
2. {step} - {monitor: metric and threshold, with the sample the window will hold}

### Rollback Triggers

- {observable condition with its sample requirement, or an absolute count} -> {rollback action and the part it reverts}

### Rollback Plan

1. {step, naming the part it reverts} - {data safety note if applicable}
2. Leave in place: {layer not being reverted} - {reason}
3. Point of no return: {the irreversible step} - gate: {verification before it} - backup: {export taken before it} - roll forward: {the action}      {only when an irreversible step exists}

### Risks                                        {when at least one risk}

- [Severity: High | Medium | Low] {description of deployment risk, naming the part}
  - Mitigation: {concrete action}

### No Risks Found                               {instead, when none: one sentence}
```

Every slot above the Risks pair is mandatory. A bundled release gets one assessment whose Rollout Plan opens with the split recommendation, then sequences each part with its own monitors. An irreversible release states the verification gate that precedes the point of no return and the roll-forward plan - never fabricated rollback steps for state that cannot be restored. When the plan names a mechanism the code lacks (a "canary" that is really a global boolean flag), report the mechanism that exists and the gap as a Risk.

## Avoid

- Deploying without a rollback plan, or with one that requires data migration to undo.
- Schema migrations that break the previous code version.
- Destructive migrations applied before the code that stops referencing them is live.
- Code that assumes a column is populated before backfill is verified.
- Multi-service schema changes without an explicit, documented service deploy order.
- Big-bang deploys for high-blast-radius changes.
