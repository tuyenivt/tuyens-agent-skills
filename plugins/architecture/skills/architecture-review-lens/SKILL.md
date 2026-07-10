---
name: architecture-review-lens
description: Review lens for architecture artifacts: severity taxonomy, completeness audit, consistency check, assumptions audit, criteria scoring, verdict.
metadata:
  category: architecture
  tags: [architecture, review, critique, findings, verdict, severity]
user-invocable: false
---

# Architecture Review Lens

> Composed by workflow skills in review mode; not invoked directly. The workflow supplies the **artifact-specific factor list**; this skill supplies the **lens** (how to audit, score, judge). When a workflow names atomic skills for deeper checks and they are unavailable (standalone use), proceed on the lens's own judgment and say so in Review Context.

## Rules

- Review the artifact as written, not the artifact you would have authored. Facts the reviewer knows that the artifact omits (regulatory scope, hidden consumers) enter as reviewer assumptions in Review Context and may ground findings - cite them as "reviewer context"
- Every finding cites a specific section, claim, or omission
- Every finding carries a severity: Blocker | Major | Minor | Nit
- Distinguish **Missing** (not present) from **Under-specified** (vague) from **Wrong** (incorrect on the facts). An author-acknowledged TODO is still Missing or Under-specified, at full severity
- Record each finding once, in the earliest lens step that captures it; number findings (F1, F2, ...) so later steps reference rather than restate them
- The verdict is driven by the highest-severity findings, not their count
- Recommend the smallest concrete change that resolves each finding; do not propose a redesign

## Severity

| Severity | Meaning                                                                                |
| -------- | -------------------------------------------------------------------------------------- |
| Blocker  | Decision cannot be made or the artifact is fundamentally wrong on a load-bearing axis  |
| Major    | Significant gap, contradiction, or risk that must be addressed before adoption         |
| Minor    | Weak spot the author should improve but does not block adoption                        |
| Nit      | Wording, formatting, or style preference                                               |

Lead with the highest severity present. Do not pad a Blocker review with Nits.

## Lens

Apply in order. A step that does not fit the artifact (e.g., Section 6 scoring on a one-page ADR) may be skipped - name the skipped step and the reason in one line.

### 1. Intake

State in one sentence each: the problem (per the artifact), stated scope and non-goals, stated NFRs/constraints, the author's recommendation. For multiple artifacts on the same problem - or a single artifact with three or more considered alternatives (an ADR) - run `architecture-proposal-compare` first, then apply the rest of the lens to the recommended option.

### 2. Completeness Audit

The workflow provides the factor list; standalone, use the Section 6 criteria as the factor list, all required (the Section 5/6 overlap rule then applies). For each factor mark **Present** (explicit, specific), **Under-specified** (mentioned but vague), or **Missing**. A factor irrelevant to the artifact is N/A with a one-line reason (mirrors Section 6), not Missing.

- Missing -> Major minimum; Blocker if the decision cannot be made without it (e.g., rollback for a high-blast-radius change) - a distinct test from workflow-marked required, which gates the Approve verdict in Section 8
- Under-specified -> Minor minimum; Major if the gap forces guesswork on a load-bearing decision
- A factor can be Present yet **Wrong**: mark it Present here and raise the error once - in Section 3 if it contradicts the artifact, otherwise in Section 5 - Major minimum, Blocker if load-bearing. Arithmetic on the artifact's own numbers counts as artifact evidence, not reviewer context

### 3. Internal Consistency

Find contradictions inside the artifact. Quote both sides with section references and state which is correct (or that the author must resolve). Severity: Major by default, Blocker if it flips the verdict.

Common patterns:

- Section claims async/stateless/strong-consistency but a later section assumes the opposite
- Stated NFR conflicts with capacity ceiling or failure mode
- "Easy to reverse" contradicted by a multi-step migration
- Rollback contradicts migration/deploy ordering
- Backward-compat claim contradicted by an explicit field rename or type change

### 4. Assumptions Audit

Surface load-bearing assumptions: **Stated** (explicit; verify still plausible) and **Implicit** (the artifact only works if X, but the author did not say so). For each: assumption, what fails if wrong, severity if wrong.

Assumptions live here; a verdict-driving assumption is cited by the finding it undermines (Section 2, 3, or 5), not restated there.

Audit categories to consider: traffic volume and growth; dependency availability/SLOs; data volume and access patterns; team capacity/skills/timeline; existing infrastructure; regulatory scope.

### 5. Per-Factor Findings

For each factor marked Present or Under-specified, evaluate quality - one or more findings per factor. The workflow names the atomic skills to compose for deeper checks (e.g., `architecture-guardrail` for boundary rigor, `ops-backward-compatibility` for contract evolution). If a supplied factor names the same axis as a Section 6 criterion (Reversibility = Reversibility; partial overlap does not count), evaluate it once - in Section 6, or here when Section 6 is skipped - and reference it from the other.

Format (repeat per finding):

```
{Factor}
- {Severity}: {Specific finding referencing the section/claim}. Recommendation: {Smallest concrete change}.
```

Example:

```
Failure containment
- Major: Section 5 lists three failure scenarios but no mitigation for "Payment provider 5xx storm". Recommendation: add circuit breaker on PaymentClient with fallback to retry queue.
```

Treat factors authors typically hand-wave (performance, deployment, trade-offs, rollback) as first-class.

### 6. Criteria Scoring

Score each as **Strong** / **Adequate** / **Weak** / **Not addressed** / **N/A**, citing artifact evidence:

| Criterion           | What to Assess                                                                                       |
| ------------------- | ---------------------------------------------------------------------------------------------------- |
| Boundary clarity    | Scope, responsibilities, and ownership explicit?                                                     |
| Failure containment | Failure modes identified? Blast radius assessed? Isolation guaranteed?                               |
| Consistency model   | Consistency or compatibility strategy stated with partial-failure behavior? (Mark N/A if irrelevant) |
| Operability         | Deployment/rollout defined? Observability planned? Rollback feasible?                                |
| Reversibility       | How hard to change key decisions later? Are one-way doors identified?                                |
| Cost and complexity | Operational and implementation cost stated? Complexity proportional to the problem?                  |

### 7. Questions for the Author

Unresolved, answerable questions grouped by purpose (**Clarification**, **Justification**, **Evidence**, **Scope**, **Risk**). Prefer "what happens if X" over "have you thought about X".

### 8. Verdict

| Verdict                  | Criteria                                                                                              |
| ------------------------ | ----------------------------------------------------------------------------------------------------- |
| **Approve**              | No Blockers, no Major findings; all required factors Present                                          |
| **Approve with changes** | No Blockers; Major findings bounded and specifically addressable before merge                         |
| **Needs rework**         | One or more Blockers, or structural issues spanning multiple factors                                  |

Required factors are those the workflow marks required; if unmarked, treat every supplied factor as required. The verdict references the driving findings. Any non-Approve verdict lists its required changes as a checkbox list (for Needs rework, the items that drive the Blockers).

## Output Structure

The workflow shapes formatting (tables vs. lists); standalone, default to tables for audits and lists for findings. Produce sections in this order:

1. **Review Context** - artifacts reviewed; depth (workflow-supplied; "full" when standalone); reviewer assumptions, including reviewer-context facts and any unavailable composed skills
2. **Intake** (Section 1)
3. **Completeness Audit** (Section 2)
4. **Internal Consistency** (Section 3)
5. **Assumptions Audit** (Section 4)
6. **Per-Factor Findings** (Section 5)
7. **Criteria Scoring** (Section 6)
8. **Questions for the Author** (Section 7)
9. **Verdict** (Section 8), with required-changes checklist if not Approve

## Avoid

- Reviewing the artifact you wish the author had written
- Generic critique ("needs more detail") without naming the section
- Padding findings with Nits when Blockers exist
- Recommending a redesign when a targeted change resolves the gap
- Issuing "Approve with changes" without naming the changes
- Scoring criteria that do not apply; mark N/A with a one-line reason instead
- Duplicating one root cause as separate findings across sections
