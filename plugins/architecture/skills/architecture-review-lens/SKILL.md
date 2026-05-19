---
name: architecture-review-lens
description: Review lens for architecture artifacts: severity taxonomy, completeness audit, consistency check, assumptions audit, criteria scoring, verdict.
metadata:
  category: architecture
  tags: [architecture, review, critique, findings, verdict, severity]
user-invocable: false
---

# Architecture Review Lens

> Composed by workflow skills in review mode; not invoked directly. The workflow supplies the **artifact-specific factor list**; this skill supplies the **lens** (how to audit, score, judge).

## Rules

- Review the artifact as written, not the artifact you would have authored
- Every finding cites a specific section, claim, or omission
- Every finding carries a severity: Blocker | Major | Minor | Nit
- Distinguish **Missing** (not present) from **Under-specified** (vague) from **Wrong** (incorrect)
- An assumption becomes a finding only when wrong-it would change the verdict
- The verdict is supported by the highest-severity findings, not a count
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

Apply in order. Skip a step that does not fit the artifact (e.g., consistency scoring on a one-page ADR).

### 1. Intake

State, in one sentence each: the problem being solved (per the artifact), stated scope and non-goals, stated NFRs/constraints, the author's recommendation. If multiple artifacts on the same problem are supplied, run `architecture-proposal-compare` first, then apply the rest of the lens to the recommended artifact.

### 2. Completeness Audit

The workflow provides the factor list. For each factor mark **Present** (explicit, specific), **Under-specified** (mentioned but vague), or **Missing**.

- Missing → Major minimum; Blocker if the factor is required to make the approval decision (e.g., rollback for a high-blast-radius change)
- Under-specified → Minor minimum; Major if the gap forces guesswork on a load-bearing decision

### 3. Internal Consistency

Find contradictions inside the artifact. Quote both sides with section references and state which is correct (or that the author must resolve). Severity: Major by default, Blocker if it flips the verdict.

Common patterns:

- Section claims async/stateless/strong-consistency but a later section assumes the opposite
- Stated NFR conflicts with capacity ceiling or failure mode
- "Easy to reverse" claim contradicted by multi-step migration
- Rollback contradicts migration/deploy ordering
- Backward-compat claim contradicted by an explicit field rename or type change

### 4. Assumptions Audit

Surface load-bearing assumptions, distinguishing **Stated** (explicit; verify still plausible) from **Implicit** (the artifact only works if X is true, but the author did not say so). For each: assumption, what fails if wrong, severity.

Audit categories (apply those relevant): traffic volume and growth; dependency availability/SLOs; data volume and access patterns; team capacity/skills/timeline; existing infrastructure; regulatory scope.

### 5. Per-Factor Findings

For each factor marked Present or Under-specified, evaluate quality. The workflow names the atomic skills to compose for deeper checks (e.g., `architecture-guardrail` for boundary rigor, `ops-backward-compatibility` for contract evolution).

Findings format:

```
{Factor}
- {Severity}: {Specific finding referencing the section/claim}. Recommendation: {Smallest concrete change}.
```

Treat the factors authors typically hand-wave (performance, deployment, trade-offs, rollback) as first-class, not "flag only if obvious gap."

### 6. Criteria Scoring

Score the artifact against this rubric (applies even for a single artifact). Score each **Strong** / **Adequate** / **Weak** / **Not addressed** / **N/A**, citing artifact evidence:

| Criterion           | What to Assess                                                                                       |
| ------------------- | ---------------------------------------------------------------------------------------------------- |
| Boundary clarity    | Scope, responsibilities, and ownership explicit?                                                     |
| Failure containment | Failure modes identified? Blast radius assessed? Isolation guaranteed?                               |
| Consistency model   | Consistency or compatibility strategy stated with partial-failure behavior? (Mark N/A if irrelevant) |
| Operability         | Deployment/rollout defined? Observability planned? Rollback feasible?                                |
| Reversibility       | How hard to change key decisions later? Are one-way doors identified?                                |
| Cost and complexity | Operational and implementation cost stated? Complexity proportional to the problem?                  |

### 7. Questions for the Author

Unresolved, answerable questions grouped by category: **Clarification** (ambiguities), **Justification** (decisions without reasons), **Evidence** (claims that need data), **Scope** (confirm in/out), **Risk** (failure scenarios). Prefer "what happens if X" over "have you thought about X."

### 8. Verdict

| Verdict                  | Criteria                                                                                              |
| ------------------------ | ----------------------------------------------------------------------------------------------------- |
| **Approve**              | No Blockers; at most one Major addressable post-merge; all required factors Present                   |
| **Approve with changes** | No Blockers; Major findings bounded and specifically addressable before merge                         |
| **Needs rework**         | One or more Blockers, or structural issues spanning multiple factors                                  |

The verdict references the driving findings. "Approve with changes" lists the required changes as a checkbox list.

## Output Structure

The workflow shapes formatting (tables vs. lists) but must produce sections in this order:

1. **Review Context** - artifacts reviewed, depth, reviewer assumptions
2. **Intake** - from Section 1
3. **Completeness Audit** - factor table from Section 2
4. **Internal Consistency** - contradiction table from Section 3
5. **Assumptions Audit** - assumption table from Section 4
6. **Per-Factor Findings** - per-factor lists from Section 5
7. **Criteria Scoring** - rubric table from Section 6
8. **Questions for the Author** - from Section 7
9. **Verdict** - from Section 8, with required-changes checklist if not Approve

## Avoid

- Reviewing the artifact you wish the author had written
- Generic critique ("needs more detail") without naming the section
- Padding findings with Nits when Blockers exist
- Recommending a redesign when a targeted change resolves the gap
- Issuing "Approve with changes" without naming the changes
- Treating verbosity as quality; a concise artifact can outscore a long one
- Scoring criteria that do not apply; mark N/A with a one-line reason instead
