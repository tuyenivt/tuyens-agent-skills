---
name: tradeoff-analysis
description: Structured architectural decision and trade-off documentation
metadata:
  category: architecture
  tags: [architecture, decisions, trade-offs, adr]
user-invocable: false
---

# Trade-Off Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During architecture design to document significant decisions
- When choosing between multiple valid approaches
- When justifying a non-obvious architectural choice
- When recording decisions for future reference (ADR-style)

## Rules

- Every significant decision must document at least one rejected alternative
- Trade-offs must state what is sacrificed, not just what is gained
- Reversibility assessment is mandatory -- how hard is it to change later
- Risk assessment must state what could make the decision wrong
- Avoid false dichotomies -- consider hybrid or phased approaches

## Pattern

### Decision Structure

For each architectural decision:

1. **Context** -- what situation requires this decision
2. **Decision** -- what was chosen
3. **Alternatives** -- what else was considered (minimum one)
4. **Rationale** -- why this option over alternatives
5. **Trade-off** -- what is sacrificed (be specific)
6. **Reversibility** -- Easy / Moderate / Hard, with explanation
7. **Risk** -- what conditions would make this decision wrong
8. **Review trigger** -- when to revisit this decision

### Good: Specific trade-off with reversibility

```
Context: Order processing requires payment confirmation before fulfillment
Decision: Async event-driven flow (OrderCreated -> PaymentProcessed -> FulfillmentStarted)
Alternatives:
  - Synchronous REST chain (Order -> Payment -> Fulfillment in one request)
  - Saga with orchestrator service
Rationale: Async decouples services, allows independent scaling and deployment
Trade-off: Eventual consistency -- user sees "processing" state for 2-5 seconds; adds operational complexity for event monitoring
Reversibility: Hard -- switching to sync requires redesigning all three services and their data models
Risk: If payment processing latency exceeds 30s, user experience degrades; if event broker fails, orders stall
Review trigger: If p99 payment latency exceeds 10s or event broker availability drops below 99.9%
```

### Bad: Decision without trade-off

```
Decision: Use events for order processing
Reason: Events are better than REST for this
```

### Common Trade-Off Dimensions

| Dimension      | One End               | Other End           |
| -------------- | --------------------- | ------------------- |
| Consistency    | Strong (simple)       | Eventual (scalable) |
| Coupling       | Tight (simple)        | Loose (flexible)    |
| Complexity     | Simple (now)          | Flexible (later)    |
| Performance    | Optimized (brittle)   | General (adaptable) |
| Cost           | Cheap (limited)       | Expensive (capable) |
| Time to market | Fast (technical debt) | Thorough (slower)   |
| Build vs buy   | Build (control)       | Buy (speed)         |

## Avoid

- Decisions without stated alternatives
- Trade-offs that only list benefits ("we get X and Y") without costs
- Stating "no alternative" without evidence of evaluation
- Conflating preference with technical justification
- Ignoring reversibility -- some decisions are one-way doors
- Documenting trivial decisions that do not affect system structure
