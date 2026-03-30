---
name: review-blast-radius
description: Scope of a proposed change - what breaks if this goes wrong, which modules and services are affected. Not for tracing an existing live failure (use failure-propagation-analysis for that).
metadata:
  category: review
  tags: [blast-radius, impact-analysis, change-scope]
user-invocable: false
---

# Blast Radius Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Alongside PR risk analysis to assess impact scope
- When evaluating changes to shared libraries or core modules
- When changes touch data persistence, messaging, or API contracts

## Rules

- Focus on what breaks if this change is wrong, not on whether it is wrong
- Consider both direct consumers and transitive dependents
- Assess data impact separately from code impact
- Keep the assessment brief -- one to two sentences per dimension

## Pattern

Evaluate blast radius across three dimensions:

### 1. Code Scope

Who directly depends on the changed code?

- **Narrow** -- Single feature, single consumer, no shared code paths
- **Moderate** -- Multiple features or consumers within the same service
- **Wide** -- Shared library, core module, or cross-service contract

### 2. Data Scope

What happens to data if this change has a bug?

- **Narrow** -- Read-only or isolated writes, easily correctable
- **Moderate** -- Writes to shared state, but recoverable (soft deletes, audit trail)
- **Wide** -- Irreversible writes, data corruption risk, no rollback path

For schema changes classified as Wide data scope, consult `ops-backward-compatibility` for expand-contract migration mechanics and `backend-db-migration` for lock risk assessment.

When the changed component is a core model that appears in API responses, the data scope change implies a code scope expansion on every API that serializes the model. Assess both dimensions together.

### 3. User Scope

How many users or systems are affected?

- **Narrow** -- Internal tool, single team
- **Moderate** -- Single product surface, subset of users
- **Wide** -- All users, public API, external integrations

### Classification

Take the **maximum** across all three dimensions.

### Good: Scoped assessment

```
Blast Radius: Moderate
Code: Moderate (shared OrderService used by 3 controllers)
Data: Narrow (read-only endpoint)
User: Narrow (admin panel only)
```

### Bad: Vague or inflated assessment

```
Blast Radius: Wide
This change could potentially affect many parts of the system.
```

## Output Format

This is the contract that consuming workflow skills depend on. Produce output in this exact structure - callers parse the `Blast Radius:` line to make decisions.

```
Blast Radius: {Narrow | Moderate | Wide | Critical}
Code: {Narrow | Moderate | Wide} ({1-sentence rationale})
Data: {Narrow | Moderate | Wide} ({1-sentence rationale})
User: {Narrow | Moderate | Wide} ({1-sentence rationale})
```

**Classification rules:**

- Overall `Blast Radius` = maximum across all three dimensions
- **Critical** = Wide data scope with no rollback path, OR public API break affecting external consumers
- **Wide** = Shared library, core module, or all-user impact
- **Moderate** = Multi-feature or multi-consumer, bounded to one service
- **Narrow** = Single feature, single consumer, easily correctable

### Reversibility and Mitigation

After classifying, assess:

**Reversibility:**
- **Recoverable** - can roll back the change (schema migration, code deploy)
- **Conditional** - recoverable within a time window (e.g., database PITR retention, recent backup)
- **Irreversible** - data destruction, dropped table, purged records - no programmatic rollback path

**Mitigations that reduce effective blast radius:**
- Feature flag guarding the change: Wide code scope becomes Narrow if flag is off
- Backup/PITR available: reduces Irreversible data scope to Conditional
- Soft delete instead of hard delete: Recoverable until purge job runs

Include mitigations in the output when they materially change the risk profile:

```
Blast Radius: Critical (unmitigated) -> Wide (with feature flag off)
Reversibility: Conditional (PITR available for 7 days)
Mitigation: Gate behind feature flag; verify PITR backup before proceeding
```

Always produce all four lines. Use "N/A" for a dimension only if it genuinely does not apply (e.g., Data: N/A for a read-only, stateless change).

## Avoid

- Inflating blast radius without specific evidence
- Ignoring data impact (the most dangerous dimension)
- Assessing blast radius without understanding module dependencies
- Using blast radius to justify blocking low-risk changes
