---
name: review-blast-radius
description: Classify scope of impact if a change goes wrong across code, data, user dimensions, with reversibility and mitigation.
metadata:
  category: review
  tags: [blast-radius, impact-analysis, change-scope]
user-invocable: false
---

# Blast Radius Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Alongside PR risk to size the impact dimension
- Changes to shared libraries, core modules, or cross-service contracts
- Changes touching persistence, messaging, or API schemas

## Rules

- Focus on what breaks if the change is wrong, not on whether it is wrong.
- Assess code, data, and user dimensions independently.
- Overall classification is the maximum across dimensions.
- One sentence per dimension. No prose padding.
- If a feature flag or backup materially reduces the effective radius, state both the unmitigated and mitigated levels.
- When the consumer set cannot be enumerated (shared library or engine, callers in repos you cannot see), classify at the highest plausible level and mark the rationale `(unverified)`.

## Patterns

### Dimensions

**Code Scope** - who directly or transitively depends on the changed code.
- Narrow: single feature, single consumer
- Moderate: multiple features or consumers within one service
- Wide: shared library, core module, or cross-service contract

**Data Scope** - what happens to data if the change has a bug. Includes wrong values that downstream consumers persist (e.g., a contract change misread by a consumer that stores the result).
- Narrow: read-only or isolated writes, easily corrected
- Moderate: writes to shared state but recoverable (soft delete, audit trail, message replay)
- Wide: irreversible writes, corruption risk, no rollback path

**User Scope** - how many users or systems are affected.
- Narrow: internal tool, single team, or one feature's small user subset
- Moderate: one product surface, subset of users
- Wide: all users, public API, external integrations

Wide data scope on a core model implies code scope expansion across every API that serializes it - assess both.

### Overall Classification

- **Critical** - Wide data with no rollback, OR a break in an externally consumed contract (public API, published events, exports)
- **Wide** - any single dimension is Wide
- **Moderate** - any single dimension is Moderate
- **Narrow** - all dimensions Narrow

### Reversibility

- **Recoverable** - rolled back by redeploy or schema rollback
- **Conditional** - recoverable within a window (PITR retention, recent backup, message replay within topic retention)
- **Irreversible** - data destruction or corruption with no programmatic rollback (includes mis-attributed writes with no source to backfill from)

### Mitigations

Mitigations may reduce the effective radius:
- Feature flag off: Wide code becomes Narrow until flipped
- Backup/PITR: Irreversible becomes Conditional
- Soft delete: Recoverable until purge job runs

### Good

```
Blast Radius: Moderate
Code: Moderate (shared OrderService used by 3 controllers)
Data: Narrow (read-only endpoint)
User: Narrow (admin panel only)
Reversibility: Recoverable
```

### Bad

```
Blast Radius: Wide
This change could potentially affect many parts of the system.
```

## Output Format

Callers parse the `Blast Radius:` line.

```
Blast Radius: {Narrow | Moderate | Wide | Critical}
Code: {Narrow | Moderate | Wide} ({1-sentence rationale})
Data: {Narrow | Moderate | Wide} ({1-sentence rationale})
User: {Narrow | Moderate | Wide} ({1-sentence rationale})
Reversibility: {Recoverable | Conditional | Irreversible} ({1-sentence rationale})
```

When a mitigation materially changes the level, rewrite the affected lines in that same block and append a `Mitigation:` line naming the existing safeguard or the single action that achieves the mitigated level:

```
Blast Radius: Critical (unmitigated) -> Wide (with feature flag off)
Reversibility: Conditional (PITR available for 7 days)
Mitigation: Gate behind feature flag; verify PITR backup before proceeding
```

In the two-state form, callers gate on the mitigated (second) value only when the `Mitigation:` line names a safeguard already in place; if it prescribes an action not yet taken, gate on the unmitigated (first) value.

Read-only changes are Data: Narrow. Use "N/A" only when a dimension genuinely has no path to impact (e.g., Data: N/A for a docs-only or pure copy change). Always produce all five lines.

For Wide data on schema changes, consult `ops-backward-compatibility` for expand-contract and `backend-db-migration` for lock risk.

## Avoid

- Inflating radius without specific evidence
- Ignoring data impact - the most dangerous dimension
- Classifying without understanding module dependencies
- Using blast radius to block low-risk changes
