---
name: architecture-review-lens
description: Review lens for architecture artifacts: severity taxonomy, completeness audit, consistency check, assumptions audit, criteria scoring, verdict.
metadata:
  category: architecture
  tags: [architecture, review, critique, findings, verdict, severity]
user-invocable: false
---

# Architecture Review Lens

> This atomic is composed by workflow skills - do not invoke directly. It provides the review framework (severity, audits, scoring, verdict) that workflow skills apply to artifact-specific factor lists.

## When to Use

Compose this skill from any architecture workflow operating in **review mode** - reviewing an artifact authored by someone else (design doc, API contract, ADR, DB migration plan, upgrade assessment, decomposition plan, consolidation plan, modernization plan).

The consuming workflow supplies the **artifact-specific factor list** (what "complete" means for that artifact type). This skill supplies the **lens** (how to audit, score, and judge).

## Rules

- Review the artifact as written, not the artifact you would have authored
- Every finding cites a specific section, claim, or omission in the artifact
- Every finding carries a severity: Blocker | Major | Minor | Nit
- Distinguish **not present** (missing) from **present but weak** (under-specified) from **present and wrong** (incorrect)
- An assumption becomes a finding only when it materially affects a decision
- The verdict is supported by the highest-severity findings, not a count
- Recommend the smallest concrete change that resolves each finding; do not propose a redesign

## Severity Taxonomy

| Severity   | Meaning                                                                                       | Blocks Merge / Approval |
| ---------- | --------------------------------------------------------------------------------------------- | ----------------------- |
| Blocker    | Decision cannot be made or the artifact is fundamentally wrong on a load-bearing dimension    | Yes                     |
| Major      | A significant gap, contradiction, or risk that must be addressed before adoption              | Yes (must be resolved)  |
| Minor      | A weak spot the author should improve but does not block adoption                             | No                      |
| Nit        | Wording, formatting, or stylistic preference                                                  | No                      |

Lead with the highest severity present. Do not pad a Blocker review with Nits.

## Review Lens

Apply the lens in this order. Skip a step when it does not fit the artifact (e.g., a one-page ADR may not need a Section 6 capacity rubric).

### 1. Intake and Scope Check

Determine before auditing:

- **Problem being solved** - restate in one sentence; flag if unclear from the artifact
- **Stated scope** - in-scope, out-of-scope, explicit non-goals
- **Stated constraints** - NFRs, compliance, timeline, dependencies the author surfaced
- **Author's recommendation** - what the artifact advocates for (or the decision/plan it commits to)
- **Artifact count** - single artifact or comparing 2-3 competing artifacts

If multiple artifacts on the same problem are provided, use `architecture-proposal-compare` first, then apply the rest of the lens to the recommended artifact.

### 2. Completeness Audit

The consuming workflow provides the **factor list** for the artifact type. For each factor, mark:

- **Present** - explicit, specific, actionable
- **Under-specified** - mentioned but vague, hand-waved, or missing required substructure
- **Missing** - not addressed at all

Severity rules:

- **Missing** factor → Major minimum; promote to Blocker if the factor is required to make the approval decision (e.g., a rollback plan for a high-blast-radius change)
- **Under-specified** factor → Minor minimum; promote to Major if the gap forces guesswork on a load-bearing decision

### 3. Internal Consistency Check

Find contradictions inside the artifact itself.

Common contradiction patterns:

- Section claims one mode (async, stateless, strong consistency) but a later section assumes another
- Stated NFR conflicts with the design's capacity ceiling or failure mode
- Trade-off section claims "easy to reverse" but the change implies a multi-step migration
- Rollback plan contradicts the migration or deploy ordering
- Backward-compat claim contradicts an explicit field rename or type change

For each contradiction:

- Quote both sides with section references
- State which is more likely correct, or that the author must resolve
- Severity: Major by default; Blocker if it flips the verdict

### 4. Assumptions Audit

Surface load-bearing assumptions the author treats as facts.

Distinguish:

- **Stated assumptions** - explicit; verify they remain plausible
- **Implicit assumptions** - the artifact only works if X is true, but the author did not say so

Audit categories (apply those relevant to the artifact):

- Traffic volume, growth, burst profile
- Dependency availability and SLOs
- Data volume, distribution, access patterns
- Team capacity, skills, timeline
- Existing infrastructure (DB capacity, broker, deploy pipeline)
- Regulatory or compliance scope being unchanged

For each load-bearing assumption: state the assumption, state what fails if it is wrong, assign severity.

### 5. Per-Factor Findings

For each factor marked Present or Under-specified in Section 2, evaluate quality. The consuming workflow supplies the quality bar per factor and the atomic skills to compose for deeper checks (e.g., `architecture-guardrail` for boundary rigor, `ops-backward-compatibility` for contract evolution).

Findings format:

```
{Factor}
- {Severity}: {Specific finding referencing the section/claim}. Recommendation: {Smallest concrete change}.
```

Treat the factors authors typically hand-wave (performance, deployment, trade-offs, rollback) as first-class, not "flag only if obvious gap."

### 6. Criteria Scoring

Score the artifact against the standard rubric. Apply even for a single artifact review.

Score each: **Strong** / **Adequate** / **Weak** / **Not addressed**. Each score cites artifact evidence, not impressions.

| Criterion               | What to Assess                                                                                               |
| ----------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Boundary clarity**    | Are scope, responsibilities, and ownership explicit?                                                         |
| **Failure containment** | Are failure modes identified? Is blast radius assessed? Is isolation guaranteed?                             |
| **Consistency model**   | Where applicable: is the consistency or compatibility strategy stated, with partial-failure behavior?        |
| **Operability**         | Is deployment / rollout strategy defined? Is observability planned? Is rollback feasible?                    |
| **Reversibility**       | How hard is it to change key decisions later? Are one-way doors identified?                                  |
| **Cost and complexity** | Is operational and implementation cost stated? Is complexity proportional to the problem?                    |

For artifacts where a criterion does not apply (e.g., consistency model on an ADR), mark **Not applicable** with a one-line reason instead of forcing a score.

### 7. Questions for the Author

Unresolved questions the author should answer before approval. Group by category:

- **Clarification** - ambiguous statements that need to be made specific
- **Justification** - decisions stated without a reason
- **Evidence** - claims that need data (capacity estimates, dependency SLOs, CVE references)
- **Scope** - in/out of scope statements that need confirmation
- **Risk** - failure scenarios the author should think through

Each question is answerable. Prefer "what happens if X" over "have you thought about X."

### 8. Verdict

| Verdict                  | Criteria                                                                                              |
| ------------------------ | ----------------------------------------------------------------------------------------------------- |
| **Approve**              | No Blocker findings; at most one Major addressable post-merge; all required factors Present           |
| **Approve with changes** | No Blocker findings; one or more Major findings bounded and specifically addressable before merge     |
| **Needs rework**         | One or more Blocker findings, or structural issues spanning multiple factors                          |

The verdict references the findings that drove it. "Approve with changes" lists the required changes as a checkbox list.

## Output Format

The consuming workflow shapes the final output but must include these sections, in this order:

```markdown
# Review: {Artifact name or description}

## Review Context

- Artifact(s) reviewed: {what was provided}
- Depth: {workflow-specific: quick | standard | deep}
- Reviewer assumptions: {inputs assumed because not provided}

## 1. Intake

- Problem solved: {one sentence}
- Stated scope:
- Stated constraints / NFRs:
- Author's recommendation:

## 2. Completeness Audit

| Factor              | Status                                |
| ------------------- | ------------------------------------- |
| {Factor 1}          | Present / Under-specified / Missing   |
| ...                 | ...                                   |

## 3. Internal Consistency

| Contradiction       | Sections     | Resolution Needed                          | Severity |
| ------------------- | ------------ | ------------------------------------------ | -------- |
| {What contradicts}  | {§X vs §Y}   | {Which is correct or author must resolve}  | Major    |

## 4. Assumptions Audit

| Assumption  | Stated / Implicit | What Fails if Wrong | Severity |
| ----------- | ----------------- | ------------------- | -------- |
| {...}       | Implicit          | {Failure mode}      | Major    |

## 5. Per-Factor Findings

### {Factor 1}
- {Severity}: {Finding}. Recommendation: {Concrete change}.

### {Factor 2}
- ...

## 6. Criteria Scoring

| Criterion             | Score                                       | Evidence    |
| --------------------- | ------------------------------------------- | ----------- |
| Boundary clarity      | Strong / Adequate / Weak / Not addressed / N/A | {citation} |
| Failure containment   | ...                                         | ...         |
| Consistency model     | ...                                         | ...         |
| Operability           | ...                                         | ...         |
| Reversibility         | ...                                         | ...         |
| Cost and complexity   | ...                                         | ...         |

## 7. Questions for the Author

**Clarification**: {questions}
**Justification**: {questions}
**Evidence**: {questions}
**Scope**: {questions}
**Risk**: {questions}

## 8. Verdict

**{Approve | Approve with changes | Needs rework}**

Driven by:
- {Top finding with severity}
- {Top finding with severity}

Required before approval (if not Approve):
- [ ] {Specific change}
- [ ] {Specific change}
```

## Avoid

- Reviewing the artifact you wish the author had written
- Generic critique ("needs more detail") without naming the section
- Padding findings with Nits when Blockers exist
- Recommending a redesign when a targeted change resolves the gap
- Issuing "Approve with changes" without stating the changes
- Treating verbosity as quality; a concise artifact can outscore a long one
- Scoring criteria that do not apply to the artifact; mark Not applicable instead
