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

- Apply the same criteria to every proposal; missing information scores **Not addressed**, not skipped
- Every score cites proposal evidence, not assumption
- A tie is not a valid output - declare a winner with reasoning
- Distinguish scope mismatch (proposals solving different problems) from coverage gap (proposal omits criteria) - flag scope mismatch before comparing

## Pattern

Score each proposal on the six criteria from `architecture-review-lens` Section 6 (Boundary clarity, Failure containment, Consistency model, Operability, Reversibility, Cost and complexity) at **Strong / Adequate / Weak / Not addressed / N/A**, each with a 1-2 sentence evidence citation.

Identify per proposal: the criterion it is strongest and weakest on, and any conflicting assumptions (different scope, different constraints).

## Output Format

```markdown
## Proposal Comparison

### Proposals Evaluated

- **Proposal A**: {title} - {source}
- **Proposal B**: {title} - {source}
- **Proposal C**: {title} - {source, if applicable}

### Scope Check

{Are all proposals addressing the same problem and constraints? If not, state the scope difference before proceeding.}

### Comparison Matrix

| Criterion           | Proposal A          | Proposal B          | Proposal C          |
| ------------------- | ------------------- | ------------------- | ------------------- |
| Boundary clarity    | Strong - {evidence} | Weak - {evidence}   | Adequate - ...      |
| Failure containment | ...                 | ...                 | ...                 |
| Consistency model   | ...                 | ...                 | ...                 |
| Operability         | ...                 | ...                 | ...                 |
| Reversibility       | ...                 | ...                 | ...                 |
| Cost and complexity | ...                 | ...                 | ...                 |

### Recommendation

**Recommended: Proposal {X}**

- {Criterion where it is strongest and why that matters most for this problem}
- {Second differentiator}

Key trade-off accepted: {what Proposal X is weaker on, and why that is acceptable in context}

### Conditions for Adoption

{Gaps in the recommended proposal that must be addressed before adoption. Omit if none.}

### What to Take from Rejected Proposals

{Specific element worth incorporating, per rejected proposal. Omit the section if nothing is worth carrying over.}
```

## Avoid

- Recommending a hybrid when one proposal is clearly stronger - hybrids dodge the decision
- Treating "more detail" as "stronger" - a concise proposal can outrank a verbose one
- Defaulting to the most recent or polished proposal; evaluate substance
