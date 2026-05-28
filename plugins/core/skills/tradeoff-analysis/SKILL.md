---
name: tradeoff-analysis
description: Structured trade-off record for an architectural decision - chosen option, rejected alternatives, costs, reversibility, risk, review triggers.
metadata:
  category: architecture
  tags: [architecture, decisions, trade-offs, adr]
user-invocable: false
---

# Trade-Off Analysis

## When to Use

- Documenting a significant architectural decision
- Choosing between multiple valid approaches
- Justifying a non-obvious technical choice
- Recording ADR-style decisions for future review

## Rules

- Every significant decision documents at least one rejected alternative with reasoning
- State what is sacrificed, not only what is gained
- Reversibility is mandatory: Easy / Moderate / Hard, with the work required to change later
- State the conditions under which this decision would be wrong (risk)
- Define a concrete review trigger - an observable condition, not a date
- Reject false dichotomies - consider hybrid or phased options

## Patterns

### Decision Structure

For each decision, capture:

1. **Context** - what situation requires the decision
2. **Decision** - what was chosen and its scope
3. **Alternatives** - what else was considered (minimum one)
4. **Rationale** - why this option over alternatives, with evidence
5. **Trade-Off** - what is sacrificed, specifically
6. **Reversibility** - Easy / Moderate / Hard, with the cost to reverse
7. **Risk** - the conditions under which this decision becomes wrong
8. **Review Trigger** - an observable signal that says revisit now

Good - specific, reversible-aware:

```
Context: Order processing needs payment confirmation before fulfillment
Decision: Async event flow (OrderCreated -> PaymentProcessed -> FulfillmentStarted)
Alternatives:
  - Synchronous REST chain in one request
  - Saga with central orchestrator
Rationale: Async decouples services; allows independent scaling and deploy
Trade-Off: Eventual consistency - user sees "processing" 2-5s; adds event monitoring cost
Reversibility: Hard - switching to sync requires redesigning three services and their data models
Risk: If payment p99 exceeds 30s the UX degrades; if broker fails, orders stall
Review Trigger: Revisit if payment p99 > 10s or broker availability < 99.9%
```

Bad - no trade-off, no alternative:

```
Decision: Use events for order processing
Reason: Events are better than REST for this
```

### Hybrid and Phased Decisions

When the answer is phased (e.g. "sync now, async in Q3") record each phase as its own row in the Alternatives table, with its own reversibility and review trigger. Do not collapse phases into a single ambiguous decision.

### Common Trade-Off Dimensions

| Dimension      | One End               | Other End           |
| -------------- | --------------------- | ------------------- |
| Consistency    | Strong (simple)       | Eventual (scalable) |
| Coupling       | Tight (simple)        | Loose (flexible)    |
| Complexity     | Simple now            | Flexible later      |
| Performance    | Optimized (brittle)   | General (adaptable) |
| Cost           | Cheap (limited)       | Expensive (capable) |
| Time to market | Fast (technical debt) | Thorough (slower)   |
| Build vs buy   | Build (control)       | Buy (speed)         |

## Output Format

```markdown
## Trade-Off Record

### Context

{What situation requires this decision}

### Decision

{What was chosen and its scope}

### Alternatives Considered

| Option     | What It Provides | What It Costs | Reversibility          | Risk                  |
| ---------- | ---------------- | ------------- | ---------------------- | --------------------- |
| {chosen}   | {benefits}       | {costs}       | Easy / Moderate / Hard | {what makes it wrong} |
| {rejected} | {benefits}       | {costs}       | {level}                | {risk}                |

### Rationale

{Why the chosen option over alternatives - specific, evidence-based, not preference}

### Trade-Off Accepted

{What is sacrificed - the specific negative consequence}

### Review Trigger

Revisit this decision if: {specific observable condition}
```

## Avoid

- Decisions with no stated alternative
- Trade-offs that list only benefits
- "No alternative exists" without evidence of evaluation
- Conflating preference with technical justification
- Skipping reversibility - some decisions are one-way doors
- Recording trivial choices that do not affect system structure
