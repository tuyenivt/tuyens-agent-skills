---
name: review-change-risk
description: Classify risk domains for a proposed change before code exists. Use for architecture proposals, migration plans, refactor plans.
metadata:
  category: governance
  tags: [risk-assessment, change-analysis, pre-implementation, classification]
user-invocable: false
---

# Change Risk Classification

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Pre-implementation: architecture proposals, migration plans, refactor plans, design docs
- When no diff exists yet, so `review-pr-risk` cannot apply
- As the framing step for downstream design and review

If a diff exists, use `review-pr-risk` instead; use both when both apply.

## Rules

- Classify by risk domain, not code signal - this skill works on proposals.
- A change may trigger multiple primary and secondary domains.
- Every domain triggered must cite the evidence that triggered it.
- Shared mutable state amplifies the overall level by one tier.
- Never classify Low when any high-severity domain is triggered.

## Patterns

### Risk Domain Table

| Domain                   | Trigger Signals                                                                              | Default Severity |
| ------------------------ | -------------------------------------------------------------------------------------------- | ---------------- |
| Data                     | Schema migration, model change, new entity, column type change                               | High             |
| Concurrency              | Shared mutable state, new locking, thread pool change, concurrency model migration           | High             |
| Transaction boundary     | Scope change, new distributed transaction, isolation level change                            | High             |
| Security                 | Auth change, new exposure, access scope change, secret management, TLS/cert config           | High             |
| Configuration            | Config shared across environments, env-var pollution, prod-derived config                    | High             |
| Async/event              | New event flow, new consumer, event schema change, ordering assumption                       | Medium           |
| External integration     | New third-party API, modified contract, new outbound dependency                              | Medium           |
| Dependency upgrade       | Major version bump, framework upgrade, transitive change                                     | Medium           |
| Performance              | New hot path, query pattern change, cache invalidation change, pool change                   | Medium           |
| Architecture drift       | Boundary erosion, layer violation, new cross-module dependency, ownership shift              | Medium           |
| Deployment               | Non-reversible migration, multi-step deploy, config-dependent rollout                        | Medium           |

### Classification Rules

1. Identify triggered domains with evidence.
2. Mark each as primary (direct, high-confidence) or secondary (indirect, lower-confidence).
3. Determine overall level:

| Condition                                                          | Overall Level |
| ------------------------------------------------------------------ | ------------- |
| No high-severity domain triggered                                  | Low           |
| One medium domain                                                  | Medium        |
| One high domain, OR three or more medium domains                   | High          |
| Two or more high domains, OR shared mutable state plus any domain  | Critical      |

4. Apply +1 tier amplification if shared mutable state is involved across domains (caps at Critical).

### Good

```
Change: Add payment_intent_id column to orders and integrate Stripe webhook

Primary:
- Data (High) - schema migration on a high-traffic write table
- External integration (Medium) - new Stripe webhook with retry semantics

Secondary:
- Async/event (Medium) - webhook introduces ordering assumption
- Deployment (Medium) - migration must precede code

Shared State: orders table (order-service + webhook handler)
Shared State Amplification: Yes

Overall Risk Level: Critical
Evidence: Two high-severity domains amplified by shared mutable state
```

### Bad

```
Change: Add payment_intent_id column to orders table
Risk: Medium
Reason: It's just a column addition
```

Why bad: ignores integration context, no shared-state assessment, no domains, no evidence.

## Output Format

Callers parse the `Overall Risk Level` line.

```
Overall Risk Level: {Low | Medium | High | Critical}

Primary Risk Domains:
- {Domain} ({Severity}) - {1-sentence evidence}

Secondary Risk Domains:
- {Domain} ({Severity}) - {1-sentence evidence}

Shared State: {what shared resource is involved, or "none"}
Shared State Amplification: Yes / No

Evidence: {key signals driving the overall classification}
```

Always produce all sections. Use "none" for Secondary and Shared State when not applicable. Never omit Evidence.

## Avoid

- Classifying without stating evidence
- Treating all schema changes as equal risk regardless of traffic
- Ignoring shared mutable state as an amplifier
- Conflating code-quality concerns with systemic risk
- Classifying as Low when several medium domains are triggered
