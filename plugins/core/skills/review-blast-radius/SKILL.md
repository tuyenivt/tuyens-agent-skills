---
name: review-blast-radius
description: Classify scope of impact if a change goes wrong across code, data, user dimensions, with reversibility and mitigation.
metadata:
  category: review
  tags: [blast-radius, impact-analysis, change-scope]
user-invocable: false
---

# Blast Radius Analysis

> Load `Use skill: stack-detect` first to determine the project stack (used to trace module dependencies; its block is not part of this deliverable).

## When to Use

- Alongside PR risk to size the impact dimension
- Changes to shared libraries, core modules, or cross-service contracts
- Changes touching persistence, messaging, or API schemas

## Rules

- Focus on what breaks if the change is wrong, not on whether it is wrong.
- Assess code, data, and user dimensions independently. A diff carrying several unrelated changes is still one assessment: each dimension takes the highest level any change in the diff reaches, and the rationale names the change that set it (both, when two changes tie).
- Overall classification: `Critical` when either Critical condition holds (see Overall Classification), otherwise the maximum across dimensions.
- One sentence per dimension. No prose padding.
- If a feature flag or backup materially reduces the effective radius, state both the unmitigated and mitigated levels.
- When the consumer set cannot be enumerated (shared library or engine, callers in repos you cannot see, a third-party package whose behaviour you cannot read), classify each affected dimension at the highest level a named failure mode supports and mark that rationale `(unverified)`. "Plausible" requires a mechanism you can state in the rationale, not mere possibility; the overall line still reaches Critical only through one of its two conditions. A control proven unreachable (the value is read by no code) is not unenumerable: the dimension is `N/A`.
- A contract is behavior as well as shape: changing defaults, semantics, or error behavior of a surface consumed outside the repository is a contract break for Critical purposes when existing callers relying on the documented or long-standing behavior would misbehave without a code change on their side; when those callers cannot be inspected, the break is `(unverified)` and still counts for Critical.

## Patterns

### Dimensions

**Code Scope** - who directly or transitively depends on the changed code.
- Narrow: single feature, single consumer
- Moderate: multiple features or consumers within one service
- Wide: shared library, core module, or cross-service contract

**Data Scope** - what happens to data if the change has a bug. Includes wrong values that downstream consumers persist (e.g., a contract change misread by a consumer that stores the result).
- Narrow: read-only or isolated writes, easily corrected
- Moderate: writes to shared state that a rollback path recovers, in full or within a window (soft delete, audit trail, message replay, a verified backup or PITR)
- Wide: irreversible writes or corruption with no rollback path

**User Scope** - how many users or systems are affected. Breadth, not severity: a trivially wrong but universally visible change is still Wide. Internal systems consuming the changed surface count as users.
- Narrow: internal tool, single team, or one feature's small user subset
- Moderate: one product surface, subset of users, or a bounded set of internal consumer systems
- Wide: all users, public API, external integrations

Wide data scope on a core model implies code scope expansion across every API that serializes it - assess both.

### Overall Classification

- **Critical** - Wide data (which is Irreversible by definition), OR a break in a contract you cannot fix in one deploy: anything consumed outside this repository (public API, published events, exports, and internal libraries or shared schemas whose callers ship on their own schedule)
- **Wide** - any single dimension is Wide
- **Moderate** - any single dimension is Moderate
- **Narrow** - all dimensions Narrow

### Reversibility

- **Recoverable** - rolled back by redeploy or schema rollback, or repairable by deterministic backfill from surviving source data
- **Conditional** - recoverable within a window (PITR retention, recent backup, message replay within topic retention, soft delete until the purge job runs)
- **Irreversible** - data destruction or corruption with no programmatic rollback (includes mis-attributed writes with no source to backfill from)

### Mitigations

A mitigation is a safeguard that changes a printed level, now or once its required action is done; a safeguard that would change no level is not a mitigation and is not listed:
- Feature flag off: Wide code becomes Narrow until flipped - only when code reads the flag; a flag defined but never read is a `required:` mitigation until wired
- A backup taken, or PITR archiving confirmed to cover the change, before it runs: Data Wide becomes Moderate and Irreversible becomes Conditional (PITR yields a clone at a timestamp to copy the old values back from - a manual repair, not a row-level undo)
- A mitigation covering one change in a multi-change diff moves only the levels that change set

## Output Format

Callers parse the `Blast Radius:` line. Always produce all five lines, blank-line separated; add the `Mitigation:` line only when a mitigation exists.

```
Blast Radius: {Narrow | Moderate | Wide | Critical}{ (contract break: <surface consumed outside the repo>{, unverified})}

Code: {Narrow | Moderate | Wide | N/A} ({1-sentence rationale}{ (unverified)})

Data: {Narrow | Moderate | Wide | N/A} ({1-sentence rationale}{ (unverified)})

User: {Narrow | Moderate | Wide | N/A} ({1-sentence rationale}{ (unverified)})

Reversibility: {Recoverable | Conditional | Irreversible} ({1-sentence rationale}{ (unverified)})

Mitigation: {in-place: | required:} {the safeguard and, for required:, the action that makes it count}    {only when a mitigation exists}
```

Any of the level slots may take the two-state form `{level} (unmitigated) -> {level} (with {mitigation})` described below. The overall line's parenthetical is present exactly when Critical comes from a contract break, so the reader can trace a Critical that no dimension line shows.

`N/A` dimensions are skipped when taking the maximum; when every dimension is `N/A`, the overall line is `Narrow`. Read-only changes are Data: Narrow unless a downstream consumer persists the returned values. Use `N/A` only when a dimension genuinely has no path to impact (Data: N/A for a docs-only or pure copy change).

When a mitigation changes a level, write every line it changes - each affected dimension line, the Reversibility line, and the overall line - in the two-state form, so the mitigated overall value is re-derivable from the printed mitigated values (Critical-by-contract-break survives mitigation unless the mitigation removes the break). Lines the mitigation does not change stay single-state. The `Mitigation:` tag is `in-place:` (the safeguard already works) or `required:` (an action must be taken first); with several mitigations, list each with its own tag, and the line's leading tag is `required:` until every required action is done. Callers gate on the mitigated (second) value only when the leading tag is `in-place:`; on `required:`, gate on the unmitigated (first) value - the printed mitigated value states what completing the actions buys.

```
Blast Radius: Critical (unmitigated) -> Moderate (with feature flag off and verified PITR)

Code: Wide (unmitigated) -> Narrow (with feature flag off) (the new checkout path lives in the shared checkout library both storefront services use; every caller reads checkout_v2_enabled)

Data: Wide (unmitigated) -> Moderate (with verified PITR) (the backfill overwrites order totals and nothing else holds the old values; a verified PITR clone gives a copy to restore from within 7 days)

User: Moderate (all checkout users of one storefront)

Reversibility: Irreversible (unmitigated) -> Conditional (with verified PITR) (restore from the clone is the only undo)

Mitigation: required: verify PITR archiving covers the backfill window before running it; in-place: feature flag off
```

For Wide data on schema changes, consult `ops-backward-compatibility` for expand-contract and `backend-db-migration` for lock risk.

## Avoid

- Inflating radius without specific evidence
- Ignoring data impact - the most dangerous dimension
- Classifying without understanding module dependencies
- Using blast radius to block low-risk changes
