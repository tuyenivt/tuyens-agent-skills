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
- A change may trigger multiple primary and secondary domains; both count toward the overall level (primary/secondary marks confidence, not weight).
- Every domain triggered must cite the evidence that triggered it.
- Classify Low only when no domain is triggered.
- Underspecified proposal: classify from stated facts, mark inferred domains "(assumed)" in their evidence, and record unknowns that could change the level under Open Questions. Never fail silently into a confident classification.

## Patterns

### Risk Domain Table

| Domain                   | Trigger Signals                                                                              | Default Severity |
| ------------------------ | -------------------------------------------------------------------------------------------- | ---------------- |
| Data                     | Schema migration, model change, new entity, column type change                               | High             |
| Concurrency              | Shared mutable state, new locking, thread pool change, concurrency model migration           | High             |
| Transaction boundary     | Scope change, new distributed transaction, isolation level change, retry of a non-idempotent operation (money movement, external writes) | High             |
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
2. Mark each as primary (direct, high-confidence) or secondary (indirect, lower-confidence, or assumed).
3. Determine the base level from the first matching row:

| Condition (first match wins)                      | Overall Level |
| -------------------------------------------------- | ------------- |
| Two or more high-severity domains                  | Critical      |
| One high-severity domain, OR three or more medium  | High          |
| One or two medium domains                          | Medium        |
| No domain triggered                                | Low           |

4. Amplify: if a shared mutable resource is written by two or more flows touched by the change, raise the level one tier (caps at Critical). Count shared state once - skip amplification when that resource is the sole reason Concurrency triggered.
5. Assess reversibility: Irreversible when any triggered domain includes a destructive or non-reversible step (data loss, irreversible migration); Partially reversible when rollback needs manual or multi-step action; Reversible otherwise.

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
Reversibility: Partially reversible - additive column reverts cleanly; processed webhook events do not

Overall Risk Level: Critical
Evidence: One high plus three medium domains (base High), amplified by shared writes to orders
Open Questions: none
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
Reversibility: {Reversible | Partially reversible | Irreversible} - {1-sentence rollback path or blocker}

Evidence: {key signals driving the overall classification}
Open Questions: {unknowns that could change the level, or "none"}
```

Always produce all sections. Use "none" for an empty domain list (Primary or Secondary), Shared State, and Open Questions. Never omit Evidence.

## Avoid

- Classifying without stating evidence
- Treating all schema changes as equal risk regardless of traffic
- Ignoring shared mutable state as an amplifier
- Conflating code-quality concerns with systemic risk
- Classifying as Low when any domain is triggered
- Producing a confident classification from an underspecified proposal without Open Questions
