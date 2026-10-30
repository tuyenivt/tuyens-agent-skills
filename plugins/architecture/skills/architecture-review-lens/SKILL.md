---
name: architecture-review-lens
description: Review lens for architecture artifacts: severity taxonomy, completeness audit, consistency check, assumptions audit, criteria scoring, verdict.
metadata:
  category: architecture
  tags: [architecture, review, critique, findings, verdict, severity]
user-invocable: false
---

# Architecture Review Lens

> Composed by workflow skills in review mode, or invoked standalone. The workflow supplies the **artifact-specific factor list**; this skill supplies the **lens** (how to audit, score, judge). When a referenced skill or workflow mode is unavailable (standalone use), proceed on the lens's own judgment and say so in Review Context.

## Rules

- Review the artifact as written, not the artifact you would have authored. Facts the reviewer knows that the artifact omits (regulatory scope, hidden consumers) enter as reviewer assumptions in Review Context and may ground findings - cite them as "reviewer context"
- Every finding cites a specific section, claim, or omission, and carries `F{n}`, a severity, and a recommendation wherever it is raised. Step 2's table carries each of its findings whole in three added columns (`F{n}`, severity, recommendation), `-` in each on a row with no Step 2 finding and several findings on one row joined with `; `, nothing repeated below the table; Step 4's and Step 6's tables cite a finding by `F{n}` only; a finding written in the Step 5 format sits under its step's table as a list
- Every finding carries a severity: Blocker | Major | Minor | Nit. A finding is a Blocker when the decision cannot be made until it is resolved - that single test covers a load-bearing gap, a contradiction that changes the recommendation, a load-bearing factual error, and a Major or a required-factor gap nobody can bound into a specific pre-adoption change
- Distinguish **Missing** (not present) from **Under-specified** (vague) from **Wrong** (incorrect on the facts). An author-acknowledged TODO is still Missing or Under-specified, at full severity
- Record each finding once, numbered F1, F2, ... in the order raised across steps (Step 2's table first, then Step 3, and so on), so later steps reference rather than restate. A factor whose claim the artifact contradicts is Present, and the contradiction is its Wrong finding. Placement, in precedence order: a Missing or Under-specified factor's gap is a Step 2 finding; a Wrong claim goes to Step 3 when it contradicts the artifact; a finding opened by an assumption that undermines no Step 2 or Step 3 finding goes to Step 4; any other Wrong claim goes to Step 6 when Step 6 runs and its factor names the same axis as a Step 6 criterion or Step 5 has collapsed, otherwise to Step 5; any other finding on an overlapping factor goes to Step 6, or to Step 5 when Step 6 is skipped; everything else goes to the earliest step that captures it. Assumptions carry their own series (A1, A2, ...); an assumption whose severity-if-wrong is Major or Blocker reaches the verdict only through a finding - a new one, or an existing one raised to that severity, per Step 4
- The verdict is driven by the highest-severity findings, not their count. Breadth reaches the verdict through one mechanism only: when no finding is itself a Blocker but findings across three or more factors together mean the decision cannot be made, open one Blocker citing them at the top of the Verdict section, and let it drive the verdict
- Recommend the smallest concrete change that resolves each finding. Propose a redesign only when no targeted change resolves it, and say why

## Severity

| Severity | Meaning                                                                                |
| -------- | -------------------------------------------------------------------------------------- |
| Blocker  | The single test in Rules: the decision cannot be made until this is resolved           |
| Major    | Significant gap, contradiction, or risk that must be addressed before adoption         |
| Minor    | Weak spot the author should improve; on its own does not block adoption (the required-factor gate in Step 8 is separate) |
| Nit      | Wording, formatting, or style preference                                               |

Lead with the highest severity present. Do not pad a Blocker review with Nits.

## Lens

Apply in order, recording Review Context as you go - artifacts, depth, reviewer assumptions, any step skipped - and finalize it before emitting. A step that does not fit the artifact may be skipped - never Step 2, and never Step 6 standalone, since they carry the factor list; name it and the reason in one line. Depth is whatever the workflow supplies, or `full` standalone, meaning no depth-based reduction; the fit-based skip still applies.

### 1. Intake

State in one sentence each: the problem (per the artifact), stated scope and non-goals, stated NFRs/constraints, the author's recommendation. For multiple artifacts on the same problem - or a single artifact weighing two or more considered alternatives - compare them first (see `task-design-architecture` Review Mode; standalone, a table of option x problem fit, top risk, reversibility), then apply the rest of the lens to the recommended option. With one option, or alternatives dismissed in a line rather than weighed, note that and continue.

### 2. Completeness Audit

The workflow provides the factor list; standalone, use the Step 6 criteria as the factor list, all required (the Step 5/6 overlap rule then applies). For each factor mark **Present** (explicit, specific), **Under-specified** (the artifact addresses part of the factor, or addresses it without the specifics a decision needs), or **Missing** (the artifact does not address it at all). Partial coverage is Under-specified, not Missing; name the covered part and the remaining gap; the gap is the finding's statement, and its severity floor is judged against it. A factor irrelevant to the artifact is N/A with a one-line reason, not Missing. A Present or Under-specified factor whose Wrong finding sits in another step appends ` - see F{n}` to its mark (`Present - see F{n}`).

Where a factor is also scored in Step 6, the two vocabularies must agree: Missing scores Not addressed, Under-specified scores Weak, N/A scores N/A, and a Present factor scores Adequate or Strong, or Weak when it carries a Wrong finding of Major or above.

Presence is settled here and quality in Step 5, so a Missing or Under-specified factor's gap is recorded once, here, at the severity floors below; Step 5 then evaluates what is Present, plus any Wrong claim in the covered part of an Under-specified factor.

- Missing -> Major minimum; Blocker if the decision cannot be made without it (e.g., rollback for a high-blast-radius change) - a distinct test from workflow-marked required, which gates the Approve verdict in Step 8
- Under-specified -> Minor minimum; Major if the gap forces guesswork on a load-bearing decision; Blocker by the single test
- A reviewer-context fact bearing on a factor already Missing or Under-specified enters that finding's text, not a second finding
- A factor can be Present (or Under-specified) yet **Wrong**: keep its mark here and raise the error once, where the Rules placement order sends it - Major minimum, Blocker by the single test. Arithmetic on the artifact's own numbers counts as artifact evidence, not reviewer context

### 3. Internal Consistency

Find contradictions inside the artifact - an appendix or numbers file the author supplies is part of it. Quote both sides with section references and state which is correct (or that the author must resolve). Severity: Major by default, Blocker when the decision cannot be made until the author resolves it. With none found, the section reads `No internal contradictions found` and nothing more.

Common patterns:

- Section claims async/stateless/strong-consistency but a later section assumes the opposite
- Stated NFR conflicts with capacity ceiling or failure mode
- "Easy to reverse" contradicted by a multi-step migration
- Rollback contradicts migration/deploy ordering
- Backward-compat claim contradicted by an explicit field rename or type change

### 4. Assumptions Audit

Surface load-bearing assumptions: **Stated** (explicit; verify still plausible) and **Implicit** (the artifact only works if X, but the author did not say so). One table row per assumption: `A{n}` | Stated or Implicit | the assumption | what fails if wrong | severity if wrong (Blocker, Major, Minor or Nit) | the finding it cites or opens, or `-`.

Assumptions live here. Because this step runs after Steps 2 and 3, an assumption that undermines a finding already written cites that finding's number and adds nothing further, except that the cited finding's severity rises to the assumption's severity-if-wrong when that is higher. One that undermines no existing finding and is itself Major or Blocker if wrong opens a finding here, in the Step 5 format with the assumption's own `A{n}` in place of a factor name.

Audit categories to consider: traffic volume and growth; dependency availability/SLOs; data volume and access patterns; team capacity/skills/timeline; existing infrastructure; regulatory scope.

### 5. Per-Factor Findings

For each factor marked Present, evaluate quality - the factor exists, but is it right? - and check the covered part of each Under-specified factor for a Wrong claim. Zero or more findings per factor. The workflow names the atomic skills to compose for deeper checks (e.g., `architecture-guardrail` for boundary rigor, `ops-backward-compatibility` for contract evolution). If a supplied factor names the same axis as a Step 6 criterion (Reversibility = Reversibility; partial overlap does not count), evaluate it once - in Step 6, or here when Step 6 is skipped - and reference it from the other. Standalone (factor list = the Step 6 criteria), this collapses Step 5: attach findings in this section's format under each scored criterion in Step 6 and leave Step 5 as the one line `Collapsed into Step 6 - findings sit under each criterion`.

Raise a finding when it would change what the author does; stop when the remaining observations would not. A Present factor with no defect gets one line - `{Factor} - no findings` - and no manufactured Nit; an Under-specified factor with no Wrong claim gets no line.

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

Score each as **Strong** / **Adequate** / **Weak** / **Not addressed** / **N/A**, citing artifact evidence. A score is not a finding: a criterion scoring below Adequate opens a finding in the Step 5 format, attached under the criterion here, unless its gap is already a numbered finding from an earlier step, which it references instead - this is also where the overlap rule sends a factor that names the same axis as a criterion, and where the standalone collapse puts all per-factor findings. In workflow mode a criterion absent from the supplied factor list that scores Not addressed opens its finding at the Step 2 Missing floor.

| Criterion           | What to Assess                                                                                       |
| ------------------- | ---------------------------------------------------------------------------------------------------- |
| Boundary clarity    | Scope, responsibilities, and ownership explicit?                                                     |
| Failure containment | Failure modes identified? Blast radius assessed? Isolation guaranteed?                               |
| Consistency model   | Consistency or compatibility strategy stated with partial-failure behavior? (Mark N/A if irrelevant) |
| Operability         | Deployment/rollout defined? Observability planned? Rollback feasible?                                |
| Reversibility       | How hard to change key decisions later? Are one-way doors identified? (Operability asks whether a rollback path exists; this asks what changing the decision costs) |
| Cost and complexity | Operational and implementation cost stated? Complexity proportional to the problem?                  |

### 7. Questions for the Author

Unresolved, answerable questions grouped by purpose (**Clarification**, **Justification**, **Evidence**, **Scope**, **Risk**); a group with nothing to ask is omitted. Prefer "what happens if X" over "have you thought about X". With none at all, the section reads `No open questions` and nothing more.

### 8. Verdict

| Verdict                  | Criteria                                                                                              |
| ------------------------ | ----------------------------------------------------------------------------------------------------- |
| **Approve**              | No Blockers, no Major findings; every required factor is Present or N/A                               |
| **Approve with changes** | No Blockers; every Major finding, and every required factor that is Under-specified or Missing, is bounded and specifically addressable before the artifact is adopted |
| **Needs rework**         | One or more Blockers                                                                                  |

Required factors are those the workflow marks required; if unmarked, treat every supplied factor as required. An N/A factor satisfies Approve - it was ruled irrelevant with a stated reason, which is a completed judgment, not a gap. The verdict opens with the breadth Blocker when one was raised, then references the driving findings. Any non-Approve verdict lists its required changes as a checkbox list: for Needs rework the items that clear the Blockers, followed as a second group by the items that close each open Major and each unmet required factor; for Approve with changes the items that close each Major and each unmet required factor.

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
- Opening a breadth Blocker when a finding is already a Blocker
- Scoring a criterion Weak or Not addressed without opening or referencing a numbered finding
