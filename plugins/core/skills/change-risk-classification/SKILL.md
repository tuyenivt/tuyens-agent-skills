---
name: change-risk-classification
description: Pre-implementation risk domain classification for proposed changes
metadata:
  category: governance
  tags: [risk-assessment, change-analysis, pre-implementation, classification]
user-invocable: false
---

# Change Risk Classification

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Before implementation, when classifying risk domains for a proposed change
- When evaluating architecture proposals, migration plans, or refactor plans that do not yet have a PR
- When `pr-risk-analysis` is insufficient because no code diff exists yet
- As the first step in `task-design-risk-analysis` to frame the risk assessment

## Rules

- Classify by risk domain, not by code signal -- this skill works on proposals, not diffs
- A change may have multiple primary and secondary risk domains
- Risk level is determined by the highest-severity domain, adjusted by domain count
- Every classification must state the evidence or signal that supports it
- Do not classify risk as Low unless no high-impact domain is triggered
- Shared mutable state amplifies risk level by one tier

## Pattern

### Risk Domain Table

| Domain               | Trigger Signals                                                                    | Default Severity |
| -------------------- | ---------------------------------------------------------------------------------- | ---------------- |
| Data                 | Schema migration, data model change, new entity, column type change                | High             |
| Concurrency          | Shared mutable state, new locking, thread pool change, concurrency model migration | High             |
| Transaction boundary | Transaction scope change, new distributed transaction, isolation level change      | High             |
| Async/event          | New event flow, new consumer, event schema change, ordering assumption             | Medium           |
| External integration | New third-party API, modified integration contract, new outbound dependency        | Medium           |
| Dependency upgrade   | Major version bump, framework upgrade, transitive dependency change                | Medium           |
| Performance          | New hot path, query pattern change, cache invalidation change, connection pool     | Medium           |
| Security             | Auth change, new endpoint exposure, data access scope change, secret management    | High             |
| Architecture drift   | Boundary erosion, layer violation, new cross-module dependency, ownership shift    | Medium           |
| Deployment           | Non-reversible migration, multi-step deploy, config-dependent rollout              | Medium           |

### Classification Rules

1. Identify all triggered domains with supporting evidence
2. Separate into primary (direct, high-confidence signals) and secondary (indirect, lower-confidence)
3. Determine overall risk level:

| Condition                                       | Overall Risk Level |
| ----------------------------------------------- | ------------------ |
| No high-severity domain triggered               | Low                |
| One medium-severity domain triggered            | Medium             |
| One high-severity domain or 3+ medium triggered | High               |
| 2+ high-severity domains or shared state + any  | Critical           |

4. Adjust upward by one tier if shared mutable state is involved across domains

### Good

```
Change: Add payment_intent_id column to orders table and integrate Stripe webhook

Primary Risk Domains:
- Data (High) -- schema migration on orders table, high-traffic write path
- External integration (Medium) -- new Stripe webhook dependency with retry semantics

Secondary Risk Domains:
- Async/event (Medium) -- webhook introduces async flow with ordering assumptions
- Deployment (Medium) -- migration must precede code deployment

Shared State: orders table (written by order service and webhook handler)
Shared State Amplification: Yes -- upgrades overall risk

Overall Risk Level: Critical
Evidence: Two high-severity domains (Data + External integration amplified by shared state)
```

### Bad

```
Change: Add payment_intent_id column to orders table

Risk: Medium
Reason: It's just a column addition
```

Why bad: Ignores integration context, does not identify shared state, does not classify domains, does not provide evidence.

## Avoid

- Classifying risk without stating supporting evidence
- Treating all schema changes as equal risk regardless of table traffic
- Ignoring shared mutable state as a risk amplifier
- Conflating code quality concerns with systemic risk domains
- Classifying as Low when multiple medium-severity domains are triggered
- Using this skill as a replacement for `pr-risk-analysis` when a code diff exists -- use both for complete coverage

