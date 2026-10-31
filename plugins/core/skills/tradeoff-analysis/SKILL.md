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
- Reversibility is mandatory: Easy / Moderate / Hard, with the work required to change later; a row's grade prices moving off that row's option, so two options that are each other's reversal carry comparable costs
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

In the Output Format, the chosen option is the first Alternatives row (for a phased decision, the phase rows in order, then the rejected rows); every row carries items 3, 5, 6, and 7. Every risk in a non-phased chosen row (each `;`-separated clause of its Risk cell is one risk, so the cell is written as one failure mode per clause) gets one Revisit line that makes it observable, sitting on the earlier-warning side of the risk threshold (below it for a metric where higher is worse, above it where higher is better) - the trigger is the leading indicator. A trigger whose threshold the record does not establish (the metric is an `Unknown:`, or the risk names no number) carries a provisional threshold marked `(provisional until <fact> is known)` - the nearest round figure beyond an established baseline when one exists (a 420 ms p99 -> `exceeds 500 ms`), else a round figure of the metric's unit; a threshold derived by arithmetic from established figures is established, and a trigger never cites an unmarked threshold the record does not establish. A phased decision instead gets one `Revisit Phase {N} if:` line per phase, as Hybrid and Phased Decisions defines; the last phase's line sits on the earlier-warning side of that phase's risk threshold, like a non-phased Revisit line.

`Status` is `proposed` while the record awaits approval, `rejected` if approval is refused, `accepted` once approved or already shipped (a decision written up after the fact is `accepted`), `trigger fired on {date} - {what was found}` once a Revisit condition has been met, `deprecated` once the decision is retired with no replacement, and `superseded by {record}` once any later record replaces this one; a prior record this decision overrides is cited in Context and takes `superseded by` this one.

### Hybrid and Phased Decisions

When the answer is phased, record each phase as its own Alternatives row (`Phase 1: {option} (chosen)`, `Phase 2: {option} (chosen)`), each with its own reversibility and risk, plus at least one rejected row - every option the request named keeps its row even when a phase absorbs it - and one Revisit line per phase: the trigger that ends Phase 1 is usually what starts Phase 2, and the last phase's trigger is the leading indicator of the condition that would make that phase wrong, since nothing follows it. A phase not yet due is not disqualified; only a hard constraint is. A disqualified-now option that a later phase would adopt is that phase's row, with the constraint's lifting (as an observable) as the trigger that starts it.

### Hard Constraints and Incomplete Inputs

- **Hard constraint disqualifies an option:** keep the option in the Alternatives table, lead its Risk cell with `Disqualified: {constraint}; ` and follow it with the risk the option would carry if adopted, and fill its remaining cells like any evaluated option - the completed row is the evidence of evaluation.
- **Decision already made ("write it up"; a proposal awaiting approval is an open decision, not this case):** analyze as if open, with the chosen row, a row for every other option the request named, and one to three further rejected rows (include the status quo or simplest option) when it named no option besides the chosen one, documenting genuine costs and risks. The chosen row records the decision as made; when the analysis favors a rejected option, or an option that was never on the table, that option gets a row marked `(recommended, not decided)` and the mismatch is stated in Rationale instead of justified backwards; when the decision stands but its implementation must change, Rationale says which change and the chosen row's cells reflect the hardened form on that row itself - never a second row - with only the changed cells ending `(as hardened)`.
- **Materialized risk:** when a recorded risk has fired or a trigger condition is already met, the record carries `**Status:** trigger fired on {date} - {what was found}`, the revisit's conclusion goes in Rationale, and a decision that changes gets a new record that this one names in `**Status:** superseded by {record}` - until that record exists the Status stays `trigger fired`; when the revisit confirms the decision, Status returns to `accepted` and the fired Revisit line is replaced by a new leading-indicator trigger; when it confirms the decision but hardens its implementation, Rationale says which change and only the chosen row's changed cells end `(as hardened)`; otherwise the Decision section and the original rows keep the decision as made, never rewritten to look right in hindsight.
- **Options not yet known:** derive candidates from the constraints before analyzing; include at least one simple option and one hybrid or phased option. For an open decision the first row is the recommended option (a hybrid the request did not name may be it), Status `proposed`, with a row for every option the request named and further rows only as the decision-already-made case counts them (a status quo row only when it named no option besides one).
- **Missing context (volume, team, constraints):** ask for the facts that drive the decision, or record `Unknown: {fact}` in Context. Never fabricate numbers to make the Rationale look evidence-based.

Bad - `Decision: use events` / `Reason: events are better than REST`: no alternative, no cost accepted, no trigger to revisit.

### Example

```markdown
## Trade-Off Record

**Status:** accepted

### Context

Order processing needs payment confirmation before fulfillment. The last two checkout outages (INC-1987, INC-2104) were payment-provider latency spikes propagating through the synchronous chain. Each compensation stays in its own service: the order service cancels the order on PaymentFailed, and the payment service, where the refund already lives, refunds on FulfillmentFailed. The platform team has no capacity for a new service while its committed project count is above 3.

Unknown: payment provider p99 under Black Friday load

Unknown: broker availability SLO

### Decision

Async event flow (OrderCreated -> PaymentProcessed -> FulfillmentStarted; OrderCreated -> PaymentFailed -> order cancelled; FulfillmentFailed -> payment service refunds) for all order types.

### Alternatives Considered

| Option | What It Provides | What It Costs | Reversibility | Risk |
| ------ | ---------------- | ------------- | ------------- | ---- |
| Async event flow | Independent scaling and deploy per service; checkout responds before payment completes | Eventual consistency (the order shows "processing" until payment completes); a broker, event contracts, idempotent consumers, a PaymentFailed cancellation path and a FulfillmentFailed refund path, event monitoring | Hard - switching to sync redesigns three services and their data models | Broker unavailability stalls every order; order confirmation delay under payment latency grows past what checkout can tolerate |
| Synchronous REST chain | One request, immediate answer | Fulfillment latency bound to payment latency; one slow provider blocks all | Hard - moving to events needs the broker, contracts, and consumer idempotency the async row lists | Payment provider slowness becomes a checkout outage (INC-1987, INC-2104) |
| Hybrid: sync payment authorization, async fulfillment | Immediate payment answer; fulfillment decoupled | Checkout still bound to provider latency for authorization, plus the broker for fulfillment | Moderate - moving authorization onto events reuses the fulfillment broker and contracts | Provider latency spikes still become checkout outages (INC-1987, INC-2104) |
| Saga with central orchestrator | Central sequencing of compensations, with timeout and retry handling | Everything the async row costs, plus an orchestrator service with its own state store that sequences every step and commands both compensations | Hard - participants' command handlers become event publishers and subscribers, and the orchestrator's sequencing and timeout handling redistribute into each | Disqualified: platform team has no capacity for a new service while its committed project count is above 3; orchestrator or saga-store unavailability stalls every order in flight, and its owning team gates every flow change |

### Rationale

Async decouples checkout from payment latency, which INC-1987 and INC-2104 show is the dominant failure; the hybrid keeps that failure on the authorization path. Both compensations stay in their own services under both the async and the orchestrated option, so the orchestrator adds a service without adding a guarantee.

### Trade-Off Accepted

Customers see an order as "processing" until payment completes - an immediate answer traded for isolation from the payment provider.

### Review Trigger

Revisit this decision if: broker-caused order stalls exceed 5 minutes in a month (provisional until broker availability SLO is known)

Revisit this decision if: order confirmation p99 exceeds 10s (provisional until payment provider p99 under Black Friday load is known)
```

## Output Format

The rejected-row form below is used as written; for a disqualified option its Risk cell is `Disqualified: {constraint}; {what makes it wrong}`. `Unknown:` lines are one per missing driver, blank-line separated, omitted when none. Revisit lines follow Decision Structure: one per risk in a non-phased chosen row, or one `Revisit Phase {N} if:` line per phase, blank-line separated. A phase row's Option cell is `Phase {N}: {option} (chosen)`; a chosen row hardened after the fact ends its changed cells with `(as hardened)`.

```markdown
## Trade-Off Record

**Status:** {proposed | rejected | accepted | trigger fired on {date} - {what was found} | deprecated | superseded by {record}}

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

{Why the chosen option over alternatives - specific, citing Context evidence, not preference; any mismatch between the analysis and a decision already made; the conclusion of any revisit, whether its trigger is still fired or the decision was confirmed}

### Trade-Off Accepted

{The single consequence you would most want a future reader to know you accepted knowingly - drawn from the chosen row's costs, stated as what it means for the system rather than restated as a cost; for a phased decision, the consequence that spans the phases}

### Review Trigger

Revisit this decision if: {specific observable condition}{ (provisional until <fact> is known)}
```

## Avoid

- Recording trivial choices that do not affect system structure
