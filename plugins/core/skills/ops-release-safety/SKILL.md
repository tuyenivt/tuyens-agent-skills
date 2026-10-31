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
- Rollback triggers are observable thresholds (error rate, latency, saturation), not judgement calls. A rate threshold needs enough traffic inside its evaluation window to mean anything: size the sample against the gap between baseline and trigger (telling 0.5% from 0.1% takes thousands of requests in the window, not hundreds), and where the canary slice cannot reach it - internal tools, low-traffic services - trigger on absolute counts (`>= 3 errors`) and extend the window or the slice until the sample exists; unknown baseline traffic is this small-sample case, and with volume unknown the window is written `until <N> events`, not as a duration; a batch job counts failed items per batch. A precondition (`do not start until <X>`) is a Rollout Plan gate, never a Rollback Trigger. A 5% canary on a service serving 40 requests an hour proves nothing. When the whole audience is the canary (an internal tool whose every user is in the slice), the canary is a time slice: the full audience runs on absolute counts for a window long enough to hold them (`>= 3 errors` at 40 requests an hour and a 0.5% trigger needs about a day: 15 h for three expected errors). The canary slice must also carry the traffic the change is for: an internal tool cannot canary a storefront path.
- Destructive migrations (the contract-phase DROP) deploy **after** the code that stops reading and writing the column is live and verified. A rename never issues a RENAME: it is the expand-contract row below.
- Code that requires populated data in a new column deploys **after** the backfill is verified complete.
- One risky change per deploy. Do not bundle schema migrations, config changes, and features in a single release - split so a triggered rollback is attributable and each piece reverts independently.
- Irreversible steps (in-place backfill, third-party writes, sent emails) get a verification gate and a backup/export **before** execution, and a roll-forward plan instead of a rollback plan past that point. A replay of third-party writes checks each item against the provider's record (idempotency key or provider id) and skips those already applied.
- A declared scope that the code contradicts ("no schema change in this slice" for a path that reads a column the same release adds) is a Risk, never accepted silently.

## Patterns

### Rollout Strategies

| Strategy        | Use When                                | Rollback Speed | Risk |
| --------------- | --------------------------------------- | -------------- | ---- |
| Feature flag    | High-risk logic, gradual user exposure  | Instant to Moderate (the flag's propagation bound) | Low  |
| Canary          | Infrastructure or performance changes   | Fast (minutes) | Low  |
| Blue-green      | Full environment swap needed            | Fast (minutes) | Med  |
| Rolling update  | Low-risk, stateless services            | Moderate       | Med  |
| One-shot script | A batch write or replay run once        | None past the point of no return | High |
| Big bang        | Never (avoid)                           | Slow           | High |

`Use skill: ops-feature-flags` for flag-gated rollouts: stage sequencing, promotion criteria, rollback triggers, and cleanup; the plan references that design and never embeds it: the flag-gated part's Rollout Plan step names the flag and points to its Feature Flag Design for stages, criteria, and triggers, and its Rollback Triggers line reads `flag <name>: per its Feature Flag Design -> disable the flag (<part>)`. A dependency bump's consumer impact is `dependency-impact-analysis`'s.

### Schema Deploy Sequencing

Verify deploy order explicitly for any change that combines a migration with code changes. Each code or migration step is a separate release; backfill and verify steps run between releases and gate the next one.

| Change         | Correct order                                              | Wrong order (flag as High)                        |
| -------------- | ---------------------------------------------------------- | ------------------------------------------------- |
| Add column     | Migration -> code, in separate releases                    | Code first (references non-existent column), or both in one release |
| Drop column    | Old column made nullable if NOT NULL without a default -> code stops reading and writing -> verify -> migration | Migration first (code breaks on missing column)   |
| Rename column  | Expand (add new) -> dual-write code -> backfill -> read-new code -> old column made nullable if NOT NULL without a default -> code stops writing old -> verify zero reads/writes of old -> contract; never single-step | Rename + code change in same deploy |
| Add index      | Online build as its own step; a unique index only after writers stop producing duplicates and existing duplicates are cleared | A blocking build on a live table; a unique index while writers still produce duplicates |
| Backfill-read  | Migration -> dual-write code (or trigger) -> backfill -> verify drift zero -> read code | Code deployed before backfill verified, or backfill started before dual-write so new rows stay empty |

`Use skill: ops-backward-compatibility` for the full compatibility matrix and dual-write/dual-read assessment.
`Use skill: backend-db-migration` for expand-contract phasing, lock-risk analysis, and backfill mechanics.

### Multi-Service Schema Changes

When multiple services read or write the same table, schema changes require coordination:

- **Additive** (nullable column, new table): migration first; verify readers that select `*` into strict mappings, and schema-validating CDC subscribers - "no coordination needed" is a claim about other teams' code and needs their confirmation.
- **Behavioral** (new NOT NULL, new default): a NOT NULL without a default breaks every writer that omits the column - add it nullable, deploy writers that populate it, backfill, then add the constraint (PostgreSQL rejects `ADD COLUMN ... NOT NULL` without a default on a non-empty table; MySQL 8.0 fills the type's implicit default - or rejects the ALTER for `DATE`/`DATETIME` under the default `NO_ZERO_DATE` - then, in strict SQL mode (the 8.0 default), rejects every insert that omits the column); with a constant default, old writers take the default; a changed default changes what readers see.
- **Destructive** (drop): the Drop column row above, with every service's readers and writers stopped first.
- **Affected services** are listed in the assessment with their required deploy order.

## Output Format

Consuming workflow skills parse this structure to produce actionable rollout and rollback plans. The header describes the riskiest part of a bundled release - the part whose failure is hardest to undo: irreversible steps (third-party writes, in-place backfill, a drop of data that exists nowhere else, a schema step whose undo needs a data migration), then other destructive schema, then other data backfill, then code; every other slot names the part it applies to, and each part's own rollback speed goes on its Rollout Plan step; a bundle's opening split recommendation and a precondition gate (`gate: <X>`) are steps that omit the part and the `rollback:` suffix. The strategy value is the mechanism the code implements to expose users to the change: `Feature flag` only when the flag toggles at runtime, otherwise the deployment's own mechanism (`Rolling update` for an ECS or Kubernetes rolling deploy), and `Big bang` for a cutover with no gradual exposure at all; `(plan proposed <mechanism>)` follows it when the plan names a different one. Rollback speed is the fastest control layer that reverts the riskiest part (flag kill switch > traffic shift > redeploy; a backup or snapshot restore is not a control layer - it is the Point of no return's `backup`, and the speed stays `None past the point of no return`); a flag is `Instant` when its recorded propagation bound is under a minute (a streaming SDK, or a server SDK polling every few tens of seconds), `Fast (minutes)` when the bound is minutes (a longer poll or a cache TTL), and `Moderate` when longer (a mobile background poll of up to an hour); a layer that exists but does not work (an unwired flag, a flag read once at process start) does not count, and a part no layer can revert (an event already consumed, an external client already broken) is `None past the point of no return`.

```
## Release Safety Assessment

**Rollout strategy:** {Feature flag | Canary | Blue-green | Rolling update | One-shot script | Big bang}{ (plan proposed <mechanism>)}

**Rollback speed:** {Instant | Fast (minutes) | Moderate | Slow | None past the point of no return} - {the control layer that reverts the riskiest part named above; a bundle's other parts carry theirs on their Rollout Plan steps}

**DB migration backward compatible:** {Yes | No | N/A - no schema change} - {reason; for a bundle, the worst schema part; ops-backward-compatibility's `No (unverified)` is written `No`, naming what would clear it; lock risk is a Risk, not this line}

**Affected services:** {every service that touches the changed surface, with its deploy position - a party with no deploy of its own (a replica, a CDC connector, a library consumer shipping in the same image) reads `no deploy - <how it picks up the change>`; or "none beyond this service"}

### Rollout Plan

1. {step, naming the part it ships} - {rationale} - rollback: {Instant | Fast (minutes) | Moderate | Slow | None past the point of no return}
2. {step} - {monitor: metric and threshold, with the sample the window will hold} - rollback: {speed}

### Rollback Triggers

- {observable condition with its sample requirement, or an absolute count | flag <name>: per its Feature Flag Design} -> {rollback action and the part it reverts}

### Rollback Plan

1. {step, naming the part it reverts} - {data safety note if applicable}      {one numbered line per revert step, in order}
N. Leave in place: {<layer not being reverted> - <reason> | none - every part reverts}
N. Point of no return: {the irreversible step} - gate: {verification before it} - backup: {export taken before it} - roll forward: {the action}      {only when an irreversible step exists}

### Risks                                        {when at least one risk}

- [Severity: High | Medium | Low] {description of deployment risk, naming the part}
  - Mitigation: {concrete action}

### No Risks Found                               {instead, when none: one sentence}
```

Every slot above the Risks pair is mandatory; `Point of no return` exists only when an irreversible step does. Rollback Plan lines are numbered consecutively: the revert steps, then `Leave in place`, then `Point of no return`. Risk severity: High = a wrong deploy order from the sequencing table or the Multi-Service order, a High or Very High lock risk (`backend-db-migration`'s grades: High for a blocking index build or a direct `SET NOT NULL`, Very High for a rewrite that blocks all traffic such as a PostgreSQL column type change that is not binary-coercible; an online rebuild that admits concurrent DML is Low) or an unbatched full-table update (which backend-db-migration forbids rather than grades), a missing rollback path, or an irreversible step without a gate; Medium = a trigger or criterion the stage's traffic cannot sample, a mechanism the code lacks, an unconfirmed consumer; Low = everything else. A bundled release gets one assessment whose Rollout Plan opens with the split recommendation, then sequences each part with its own monitors. An irreversible release states the verification gate that precedes the point of no return and the roll-forward plan - never fabricated rollback steps for state that cannot be restored. When the plan names a mechanism the code lacks (a "canary" that is really a global boolean flag), report the mechanism that exists and the gap as a Risk.

## Avoid

- A rollback plan whose undo step is itself a data migration - it is a roll-forward; plan it as one.
