---
name: architecture-proposal-compare
description: Compare 2-3 architecture proposals against a fixed criteria set and produce a ranked recommendation
metadata:
  category: architecture
  tags: [architecture, comparison, proposals, trade-offs, decision, recommendation]
user-invocable: false
---

# Architecture Proposal Compare

> This atomic is composed by workflows - do not invoke directly. Primary consumers: `task-design-architecture` review mode (multiple proposals), `task-architecture-docs-audit` (conflicting design docs).

## When to Use

- When 2 or more architecture proposals exist for the same problem space
- When an architecture review reveals a conflict between an existing design doc and a newer proposal
- When a team needs a structured recommendation, not just a list of pros and cons
- When the decision involves choosing between architecture styles or patterns (e.g., event-driven vs request-driven) even if no authored proposal documents exist -- treat the options as Proposal A and Proposal B

## Rules

- Apply the same criteria set to every proposal; missing information scores lower, not skipped
- Every score must cite proposal evidence, not assumptions
- A tie is not a valid output - state a winner with reasoning
- State scope mismatches before comparing; if one proposal addresses fewer than three criteria, flag the asymmetry and weight the recommendation accordingly

## Pattern

### Evaluation Criteria

Evaluate each proposal on these six criteria. Score each: **Strong** / **Adequate** / **Weak** / **Not addressed**.

| Criterion               | What to Assess                                                                                               |
| ----------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Boundary clarity**    | Are module/service boundaries explicit? Is data ownership stated?                                            |
| **Failure containment** | Are failure modes identified? Is blast radius assessed? Does a failure in one component isolate from others? |
| **Consistency model**   | Is the consistency strategy stated for each data boundary? Are partial failure behaviors addressed?          |
| **Operability**         | Is deployment strategy defined? Is observability planned? Is rollback feasible?                              |
| **Reversibility**       | How hard is it to change the key decisions later? Are one-way-door decisions identified?                     |
| **Cost and complexity** | What is the operational and implementation cost? Is complexity proportional to the problem?                  |

### Comparison Process

1. Read each proposal fully before scoring any
2. Score each proposal per criterion with a 1-2 sentence evidence citation
3. Identify which criteria each proposal is strongest and weakest on
4. Identify if proposals make conflicting assumptions (different problem scope, different constraints)
5. Produce the comparison matrix
6. State the recommendation with primary reasoning

### Output Format

```markdown
## Proposal Comparison

### Proposals Evaluated

- **Proposal A**: {title or short description} - {source: doc name, section, or date}
- **Proposal B**: {title or short description} - {source}
- **Proposal C**: {title or short description} - {source, if applicable}

### Scope Check

{Are all proposals addressing the same problem? If not, state the scope difference before proceeding.}

### Comparison Matrix

| Criterion           | Proposal A            | Proposal B            | Proposal C            |
| ------------------- | --------------------- | --------------------- | --------------------- |
| Boundary clarity    | Strong - {evidence}   | Weak - {evidence}     | Adequate - {evidence} |
| Failure containment | Adequate - {evidence} | Strong - {evidence}   | Not addressed         |
| Consistency model   | Strong - {evidence}   | Adequate - {evidence} | Weak - {evidence}     |
| Operability         | Weak - {evidence}     | Strong - {evidence}   | Adequate - {evidence} |
| Reversibility       | Strong - {evidence}   | Adequate - {evidence} | Weak - {evidence}     |
| Cost and complexity | Adequate - {evidence} | Weak - {evidence}     | Strong - {evidence}   |

### Recommendation

**Recommended: Proposal {X}**

Primary reasons:

- {Criterion where it is strongest and why that matters most for this problem}
- {Second key differentiator}

Key trade-off accepted:

- {What Proposal X is weaker on, and why that is acceptable given the context}

Conditions:

- {Any gaps in the recommended proposal that must be addressed before adoption}

### What to Take from Rejected Proposals

- From Proposal {Y}: {specific element worth incorporating into the recommended proposal}
- From Proposal {Z}: {specific element, if applicable}
```

## Avoid

- Recommending a hybrid when one proposal is clearly stronger - hybrids dodge the decision
- Treating "more detail" as "stronger" - a concise proposal may outrank a verbose one
- Recommending the most recent or polished proposal by default; evaluate substance
