---
name: blast-radius-analysis
description: Failure propagation and change impact scope assessment
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

## Avoid

- Inflating blast radius without specific evidence
- Ignoring data impact (the most dangerous dimension)
- Assessing blast radius without understanding module dependencies
- Using blast radius to justify blocking low-risk changes
