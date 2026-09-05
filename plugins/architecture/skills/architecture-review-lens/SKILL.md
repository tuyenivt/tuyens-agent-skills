---
name: architecture-review-lens
description: Review lens for architecture artifacts: severity taxonomy, completeness audit, consistency check, assumptions audit, criteria scoring, verdict.
metadata:
  category: architecture
  tags: [architecture, review, critique, findings, verdict, severity]
user-invocable: false
---

# Architecture Review Lens

> Composed by workflow skills in review mode; not invoked directly. The workflow supplies the **artifact-specific factor list**; this skill supplies the **lens** (how to audit, score, judge). When a referenced skill or workflow mode is unavailable (standalone use), proceed on the lens's own judgment and say so in Review Context.

## Rules

- Review the artifact as written, not the artifact you would have authored. Facts the reviewer knows that the artifact omits (regulatory scope, hidden consumers) enter as reviewer assumptions in Review Context and may ground findings - cite them as "reviewer context"
- Every finding cites a specific section, claim, or omission, and carries `F{n}`, a severity, and a recommendation wherever it is raised. Steps that default to a table add three columns for them rather than dropping them
- Every finding carries a severity: Blocker | Major | Minor | Nit. A finding is a Blocker when the decision cannot be made until it is resolved - that single test covers a load-bearing gap, a contradiction that changes the recommendation, and a Major nobody can bound into a specific pre-adoption change
- Distinguish **Missing** (not present) from **Under-specified** (vague) from **Wrong** (incorrect on the facts). An author-acknowledged TODO is still Missing or Under-specified, at full severity
- Record each finding once, in the earliest lens step that captures it; number findings (F1, F2, ...) so later steps reference rather than restate them. Assumptions carry their own series (A1, A2, ...); an assumption whose severity-if-wrong is Major or Blocker also becomes a numbered finding at that severity, or it never reaches the verdict
- The verdict is driven by the highest-severity findings, not their count. Breadth reaches the verdict through one mechanism only: when findings across three or more factors together mean the decision cannot be made, open one Blocker citing them, and let that Blocker drive the verdict
- Recommend the smallest concrete change that resolves each finding. Propose a redesign only when no targeted change resolves it, and say why

## Severity

| Severity | Meaning                                                                                |
| -------- | -------------------------------------------------------------------------------------- |
| Blocker  | Decision cannot be made or the artifact is fundamentally wrong on a load-bearing axis  |
| Major    | Significant gap, contradiction, or risk that must be addressed before adoption         |
| Minor    | Weak spot the author should improve but does not block adoption                        |
| Nit      | Wording, formatting, or style preference                                               |

Lead with the highest severity present. Do not pad a Blocker review with Nits.

## Lens

Apply in order, recording Review Context as you go - artifacts, depth, reviewer assumptions, any step skipped - and finalize it before emitting. A step that does not fit the artifact (e.g., Step 6 scoring on a one-page ADR) may be skipped; name it and the reason in one line. Depth is whatever the workflow supplies, or `full` standalone, meaning every step runs.

### 1. Intake

State in one sentence each: the problem (per the artifact), stated scope and non-goals, stated NFRs/constraints, the author's recommendation. For multiple artifacts on the same problem - or a single artifact weighing two or more considered alternatives - compare them first (see `task-design-architecture` Review Mode; standalone, a table of option x problem fit, top risk, reversibility), then apply the rest of the lens to the recommended option. With one option and no alternatives, note that in a line and continue.

### 2. Completeness Audit

The workflow provides the factor list; standalone, use the Step 6 criteria as the factor list, all required (the Step 5/6 overlap rule then applies). For each factor mark **Present** (explicit, specific), **Under-specified** (the artifact addresses part of the factor, or addresses it without the specifics a decision needs), or **Missing** (the artifact does not address it at all). Partial coverage is Under-specified, not Missing; name the part that is covered so the severity floor is judged against the remaining gap. A factor irrelevant to the artifact is N/A with a one-line reason, not Missing.

Where a factor is also scored in Step 6, the two vocabularies must agree: Missing scores Not addressed, Under-specified scores Weak at best, N/A scores N/A, and only a Present factor can score Adequate or Strong.

Presence is settled here and quality in Step 5, so a Missing or Under-specified factor is recorded once, here, at the severity floors below; Step 5 then evaluates only what is Present.

- Missing -> Major minimum; Blocker if the decision cannot be made without it (e.g., rollback for a high-blast-radius change) - a distinct test from workflow-marked required, which gates the Approve verdict in Step 8
- Under-specified -> Minor minimum; Major if the gap forces guesswork on a load-bearing decision
- A factor can be Present yet **Wrong**: mark it Present here and raise the error once - in Step 3 if it contradicts the artifact, otherwise in Step 5, or in Step 6 when Step 5 has collapsed - Major minimum, Blocker if load-bearing. Arithmetic on the artifact's own numbers counts as artifact evidence, not reviewer context

### 3. Internal Consistency

Find contradictions inside the artifact. Quote both sides with section references and state which is correct (or that the author must resolve). Severity: Major by default, Blocker when the decision cannot be made until the author resolves it. With none found, the section reads `No internal contradictions found` and nothing more.

Common patterns:

- Section claims async/stateless/strong-consistency but a later section assumes the opposite
- Stated NFR conflicts with capacity ceiling or failure mode
- "Easy to reverse" contradicted by a multi-step migration
- Rollback contradicts migration/deploy ordering
- Backward-compat claim contradicted by an explicit field rename or type change

### 4. Assumptions Audit

Surface load-bearing assumptions: **Stated** (explicit; verify still plausible) and **Implicit** (the artifact only works if X, but the author did not say so). For each: `A{n}`, the assumption, what fails if wrong, severity if wrong.

Assumptions live here. Because this step runs after Steps 2 and 3, an assumption that undermines a finding already written cites that finding's number and adds nothing further. One that undermines no existing finding and is itself Major or Blocker if wrong opens a finding here, in the Step 5 format with the assumption's own `A{n}` in place of a factor name.

Audit categories to consider: traffic volume and growth; dependency availability/SLOs; data volume and access patterns; team capacity/skills/timeline; existing infrastructure; regulatory scope.

### 5. Per-Factor Findings

For each factor marked Present, evaluate quality - the factor exists, but is it right? One or more findings per factor. The workflow names the atomic skills to compose for deeper checks (e.g., `architecture-guardrail` for boundary rigor, `ops-backward-compatibility` for contract evolution). If a supplied factor names the same axis as a Step 6 criterion (Reversibility = Reversibility; partial overlap does not count), evaluate it once - in Step 6, or here when Step 6 is skipped - and reference it from the other. Standalone (factor list = the Step 6 criteria), this collapses Step 5: attach findings in this section's format under each scored criterion in Step 6 and leave Step 5 as a one-line pointer.

Raise a finding when it would change what the author does; stop when the remaining observations would not. A factor with no defect gets one line - `{Factor} - no findings` - and no manufactured Nit. Where this step and Step 6 both cover a factor, the more specific rule wins: the overlap rule places the finding in Step 6, overriding "earliest step".

Format (repeat per finding):

```
{Factor}
- F{n} {Severity}: {Specific finding referencing the section/claim}. Recommendation: {Smallest concrete change}.
```

Example - a factor marked Present in Step 2, found wrong on its own terms here:

```
Idempotency of retried writes
- F4 Major: the retry section specifies dedupe on a per-attempt request ID, which is regenerated on each retry, so a redelivered OrderPlaced still charges twice. Recommendation: key the dedupe on the order ID, which is stable across attempts.
```

Treat factors authors typically hand-wave (performance, deployment, trade-offs, rollback) as first-class.

### 6. Criteria Scoring

Score each as **Strong** / **Adequate** / **Weak** / **Not addressed** / **N/A**, citing artifact evidence. A score is not a finding: anything below Adequate that the verdict should feel opens a finding in the Step 5 format, attached under the criterion here - which is also where the overlap rule sends a factor that names the same axis as a criterion, and where the standalone collapse puts all per-factor findings.

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
| **Approve**              | No Blockers, no Major findings; every required factor is Present or N/A                               |
| **Approve with changes** | No Blockers; every Major finding, and every required factor that is Under-specified or Missing, is bounded and specifically addressable before the artifact is adopted |
| **Needs rework**         | One or more Blockers                                                                                  |

Required factors are those the workflow marks required; if unmarked, treat every supplied factor as required. An N/A factor satisfies Approve - it was ruled irrelevant with a stated reason, which is a completed judgment, not a gap. The verdict references the driving findings. Any non-Approve verdict lists its required changes as a checkbox list: for Needs rework the items that clear the Blockers, for Approve with changes the items that close each Major and each unmet required factor.

## Output Structure

The workflow shapes formatting (tables vs. lists); standalone, default to tables for audits and lists for findings. Produce sections in this order:

1. **Review Context** - artifacts reviewed; depth (workflow-supplied, or `full` standalone); the single highest severity present, or `no findings`, so the reader meets it before the audits; any lens step skipped, with its one-line reason; reviewer assumptions, including reviewer-context facts and any unavailable composed skills
2. **Intake** (Step 1)
3. **Completeness Audit** (Step 2)
4. **Internal Consistency** (Step 3)
5. **Assumptions Audit** (Step 4)
6. **Per-Factor Findings** (Step 5)
7. **Criteria Scoring** (Step 6)
8. **Questions for the Author** (Step 7)
9. **Verdict** (Step 8), with required-changes checklist if not Approve

## Avoid

- Reviewing the artifact you wish the author had written
- Generic critique ("needs more detail") without naming the section
- Issuing "Approve with changes" without naming the changes
- Scoring criteria that do not apply; mark N/A with a one-line reason instead
