---
name: architecture-proposal-compare
description: Compare 2-3 architecture proposals against a fixed criteria set and produce a ranked recommendation
metadata:
  category: architecture
  tags: [architecture, comparison, proposals, trade-offs, decision, recommendation]
user-invocable: false
---

# Architecture Proposal Compare

> Composed by workflows; not invoked directly. Primary consumer: `task-design-architecture` review mode (multiple proposals).

## When to Use

Two or more proposals exist for the same problem space, including:

- A new proposal vs. an existing design doc
- A team deciding between architecture styles (event-driven vs request-driven) - treat each option as a proposal
- An ADR with three or more considered alternatives

## Rules

- Apply the same criteria to every proposal; missing information scores **Not addressed**, not skipped - the citation is the omission itself ("no rollback section")
- Every score cites proposal evidence: stated mechanisms and their direct implications count as evidence; performance promises without a mechanism are assertions - score the mechanism, not the promised numbers
- Weight criteria by the problem's stated constraints and NFRs (team capacity, volume, timeline). The matrix stays unweighted; weighting happens in the Recommendation by naming the decisive criteria - decisive = the criteria the stated constraints make non-negotiable
- A tie is not a valid output - declare a winner with reasoning
- Distinguish scope mismatch (proposals solving different problems) from coverage gap (proposal omits criteria) - flag scope mismatch in the Scope Check, then compare against the full underlying problem. If the proposals are complementary (each solves a different real problem), the winner is what to fund first; record the other as a follow-up under Conditions for Adoption
- If the artifact contains an explicit author recommendation (e.g., an ADR author's pick among alternatives), explicitly agree with or overturn it in the Recommendation, with reasoning. Proposals advocating themselves do not count as a recommendation
- Constraint/NFR fit is not a seventh criterion: the Scope Check states the binding constraints, each proposal's conflicts with them surface in its Per-Proposal Profile, and the Recommendation may name constraint fit as decisive alongside criteria
- More than three candidates: pre-screen to the strongest three against the binding constraints, recording each elimination in one line under Proposals Evaluated; only survivors enter the matrix

## Pattern

Score each proposal on the six criteria from `architecture-review-lens` Section 6 (Boundary clarity, Failure containment, Consistency model, Operability, Reversibility, Cost and complexity) at **Strong / Adequate / Weak / Not addressed / N/A**, each with a 1-2 sentence evidence citation. Matrix cells carry one clause of evidence; longer reasoning belongs in the Per-Proposal Profile. Drop the Proposal C column when only two proposals exist.

## Output Format

```markdown
## Proposal Comparison

### Proposals Evaluated

- **Proposal A**: {title} - {author/team; where it lives: doc link, PR, or "inline"}
- **Proposal B**: {title} - {source}
- **Proposal C**: {title} - {source, if applicable}

### Scope Check

{The shared problem and its binding constraints (NFRs, team capacity, volume, timeline). Are all proposals addressing the same problem and constraints? If not, state the scope difference and what the comparison is judged against.}

### Comparison Matrix

| Criterion           | Proposal A          | Proposal B          | Proposal C          |
| ------------------- | ------------------- | ------------------- | ------------------- |
| Boundary clarity    | Strong - {evidence} | Weak - {evidence}   | Adequate - ...      |
| Failure containment | ...                 | ...                 | ...                 |
| Consistency model   | ...                 | ...                 | ...                 |
| Operability         | ...                 | ...                 | ...                 |
| Reversibility       | ...                 | ...                 | ...                 |
| Cost and complexity | ...                 | ...                 | ...                 |

### Per-Proposal Profile

- **Proposal A**: strongest on {criterion}; weakest on {criterion}; assumptions that conflict with the problem constraints or other proposals: {or "none"}
- **Proposal B**: ...

### Recommendation

**Recommended: Proposal {X}** {If the artifact had an author recommendation: "- agreeing with the author" or "- overturning the author's choice of {Y} because ..."}

- Decisive criteria for this problem: {criteria, and why the stated constraints make them decisive}
- {Criterion where the winner is strongest and why that matters most here}

Key trade-off accepted: {what Proposal X is weaker on, and why that is acceptable in context}

### Conditions for Adoption

{Gaps in the recommended proposal that must be addressed before adoption; follow-up work deferred from complementary proposals. Omit if none.}

### What to Take from Rejected Proposals

{Specific element worth incorporating, per rejected proposal; entries may be omitted per proposal if nothing carries over. Omit the whole section if no proposal contributes.}
```

## Avoid

- Recommending a hybrid when one proposal is clearly stronger - hybrids dodge the decision
- Treating "more detail" as "stronger" - a concise proposal can outrank a verbose one
- Defaulting to the most recent or polished proposal; evaluate substance
