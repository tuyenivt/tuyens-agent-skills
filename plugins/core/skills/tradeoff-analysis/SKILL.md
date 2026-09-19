---
name: tradeoff-analysis
description: Document an architectural decision as a trade-off record - chosen option, rejected alternatives, costs, reversibility, risk, review triggers.
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
- Recording ADR-style decisions for future review, including after a recorded risk has materialized

## Rules

- Every significant decision documents at least one rejected alternative with reasoning - a phased decision too, since every phase row is chosen
- State what is sacrificed, not only what is gained
- Reversibility is mandatory: Easy / Moderate / Hard, with the work required to change later; the work is priced in both directions, so two options that are each other's reversal carry comparable costs
- State the conditions under which this decision would be wrong (risk)
- Define a concrete review trigger - an observable condition, not a date; a phase boundary is an observable condition too ("when sustained write rate exceeds N/s"), never a quarter. A constraint whose lifting is a date is restated as the observable it stands for ("when the platform team's committed project count drops below N")
- Reject false dichotomies - consider hybrid or phased options

## Patterns

### Decision Structure

For each decision, capture:

1. **Context** - what situation requires the decision, the evidence the Rationale will cite, and `Unknown: {fact}` lines for facts that drive it and were not supplied
2. **Decision** - what was chosen and its scope
3. **Alternatives** - what else was considered (minimum one rejected), each with what it provides and what it costs
4. **Rationale** - why this option over alternatives, citing evidence that appears in Context
5. **Trade-Off** - what is sacrificed: per option in the table's cost column, and the single consequence a future reader most needs in the Trade-Off Accepted section
6. **Reversibility** - Easy / Moderate / Hard, with the cost to reverse
7. **Risk** - the conditions under which this decision becomes wrong
8. **Review Trigger** - an observable signal that says revisit now

In the Output Format, the chosen option is the first Alternatives row (for a phased decision, the phase rows in order, then the rejected rows); every row carries items 3, 5, 6, and 7. Every risk in a chosen row gets one Revisit line that makes it observable, sitting on the earlier-warning side of the risk threshold (below it for a metric where higher is worse, above it where higher is better) - the trigger is the leading indicator. A trigger whose threshold the record does not establish (the metric is an `Unknown:`, or the risk names no number) carries a provisional threshold marked `(provisional until <fact> is known)`; a trigger never cites a threshold the record does not contain.

`Status` is `proposed` while the record awaits approval, `accepted` once approved or already shipped (a decision written up after the fact is `accepted`), `trigger fired on {date} - {what was found}` once a Revisit condition has been met, and `superseded by {record}` once any later record replaces this one.

### Hybrid and Phased Decisions

When the answer is phased, record each phase as its own Alternatives row (`Phase 1: {option} (chosen)`, `Phase 2: {option} (chosen)`), each with its own reversibility and risk, plus at least one rejected row - every option the request named keeps its row even when a phase absorbs it - and one Revisit line per phase: the trigger that ends Phase 1 is usually what starts Phase 2, and the last phase's trigger is the condition that would make that phase wrong, since nothing follows it. A phase not yet due is not disqualified; only a hard constraint is. A disqualified-now option that a later phase would adopt is that phase's row, with the constraint's lifting (as an observable) as the trigger that starts it.

### Hard Constraints and Incomplete Inputs

- **Hard constraint disqualifies an option:** keep the option in the Alternatives table, lead its Risk cell with `Disqualified: {constraint}; ` and follow it with the risk the option would carry if adopted, and fill its remaining cells like any evaluated option - the completed row is the evidence of evaluation.
- **Decision already made ("write it up"):** analyze as if open, with the chosen row plus one to three rejected rows (include the status quo or simplest option), documenting genuine costs and risks. The chosen row records the decision as made; when the analysis favors a rejected option, or an option that was never on the table, that option gets a row marked `(recommended, not decided)` and the mismatch is stated in Rationale instead of justified backwards; when the decision stands but its implementation must change, Rationale says which change and the chosen row's cells reflect the hardened form with `(as hardened)` after the values that changed.
- **Materialized risk:** when a recorded risk has fired or a trigger condition is already met, the record carries `**Status:** trigger fired on {date} - {what was found}`, the revisit's conclusion goes in Rationale, and a decision that changes gets a new record that this one names in `**Status:** superseded by {record}`; the original rows are never rewritten to look right in hindsight.
- **Options not yet known:** derive candidates from the constraints before analyzing; include at least one simple option and one hybrid or phased option. For an open decision, a hybrid the request did not name may be the chosen row.
- **Missing context (volume, team, constraints):** ask for the facts that drive the decision, or record `Unknown: {fact}` in Context. Never fabricate numbers to make the Rationale look evidence-based.

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

### Good

```markdown
## Trade-Off Record

**Status:** accepted

### Context

Order processing needs payment confirmation before fulfillment. The last two checkout outages (INC-1987, INC-2104) were payment-provider latency spikes propagating through the synchronous chain.

Unknown: payment provider p99 under Black Friday load

Unknown: broker availability SLO

### Decision

Async event flow (OrderCreated -> PaymentProcessed or PaymentFailed -> FulfillmentStarted; FulfillmentFailed -> payment service refunds) for all order types.

### Alternatives Considered

| Option | What It Provides | What It Costs | Reversibility | Risk |
| ------ | ---------------- | ------------- | ------------- | ---- |
| Async event flow | Independent scaling and deploy per service; checkout responds before payment completes | Eventual consistency (the order shows "processing" until payment completes); a broker, event contracts, idempotent consumers, a FulfillmentFailed compensation path, event monitoring | Hard - switching to sync redesigns three services and their data models | Broker unavailability stalls every order; order confirmation is delayed by payment latency |
| Synchronous REST chain | One request, immediate answer | Fulfillment latency bound to payment latency; one slow provider blocks all | Hard - moving to events needs the broker, contracts, and consumer idempotency the async row lists | Payment provider slowness becomes a checkout outage (INC-1987, INC-2104) |
| Saga with central orchestrator | Central sequencing of compensations, with timeout and retry handling | Everything the async row costs, plus an orchestrator service with its own state store and one compensating transaction per participant | Hard - participants' command handlers become event publishers and subscribers, and compensation ordering redistributes into each | Disqualified: platform team has no capacity for a new service while its committed project count is above 3; a second stateful dependency (the saga store) to operate and back up |

### Rationale

Async decouples checkout from payment latency, which INC-1987 and INC-2104 show is the dominant failure. Only one step, payment capture, is compensatable, and its refund lives in the payment service under either option; with no multi-step compensation ordering to own, the orchestrator adds a service without adding a guarantee.

### Trade-Off Accepted

Customers see an order as "processing" until payment completes - the system trades an immediate answer for isolation from the payment provider.

### Review Trigger

Revisit this decision if: broker-caused order stalls exceed 5 minutes in a month (provisional until broker availability SLO is known)

Revisit this decision if: order confirmation p99 exceeds 10s (provisional until payment provider p99 under Black Friday load is known)
```

Bad - no trade-off, no alternative:

```
Decision: Use events for order processing
Reason: Events are better than REST for this
```

## Output Format

The rejected-row form below is used as written; for a disqualified option its Risk cell is `Disqualified: {constraint}; {what makes it wrong}`. `Unknown:` lines are one per missing driver, blank-line separated, omitted when none. Revisit lines are one per risk in the chosen row, blank-line separated; for a phased decision they are `Revisit Phase {N} if:` lines, one per phase. A phase row's Option cell is `Phase {N}: {option} (chosen)`; a chosen row hardened after the fact ends its changed cells with `(as hardened)`.

```markdown
## Trade-Off Record

**Status:** {proposed | accepted | trigger fired on {date} - {what was found} | superseded by {record}}

### Context

{What situation requires this decision, and the evidence the Rationale cites}

Unknown: {fact}

### Decision

{What was chosen and its scope}

### Alternatives Considered

| Option | What It Provides | What It Costs | Reversibility | Risk |
| ------ | ---------------- | ------------- | ------------- | ---- |
| {chosen, first; Phase {N}: {option} (chosen) rows in order for a phased decision} | {benefits} | {costs} | {Easy \| Moderate \| Hard} - {work to reverse} | {what makes it wrong} |
| {rejected, or (recommended, not decided)} | {benefits} | {costs} | {Easy \| Moderate \| Hard} - {work to reverse} | {what makes it wrong} |

### Rationale

{Why the chosen option over alternatives - specific, citing Context evidence, not preference; any mismatch between the analysis and a decision already made; the conclusion of a revisit when the Status says a trigger fired}

### Trade-Off Accepted

{The single consequence you would most want a future reader to know you accepted knowingly - drawn from the chosen row's costs, stated as what it means for the system rather than restated as a cost; for a phased decision, the consequence that spans the phases}

### Review Trigger

Revisit this decision if: {specific observable condition}{ (provisional until <fact> is known)}
```

## Avoid

- Decisions with no stated alternative
- Trade-offs that list only benefits
- "No alternative exists" without evidence of evaluation
- Conflating preference with technical justification
- Skipping reversibility - some decisions are one-way doors
- Recording trivial choices that do not affect system structure
