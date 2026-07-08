---
name: task-breakdown-review
description: Review a task or work breakdown for design coverage, dependency and critical-path soundness, sizing, missing ops-readiness, and scope creep.
metadata:
  category: planning
  tags: [review, task-breakdown, critique, findings, verdict, critical-path]
  type: workflow
user-invocable: true
---

# Task Breakdown Review

Critique an engineering task breakdown authored by another architect or engineer. Produces severity-tagged findings and a verdict, grounded in the source design when one is supplied. Reviews a plan; does not rewrite it. To author a breakdown from a design, use `task-breakdown-design`.

## When to Use

- A colleague's task plan needs sign-off before the team commits
- Checking a breakdown against the design it claims to implement
- Sanity-checking dependency order, critical path, and sizing before a timeline is set

## Inputs

| Input | Required | Notes |
| --- | --- | --- |
| Task breakdown | Yes | The plan under review - phases, tasks, dependencies, sizes |
| Source design | No | The HLD/LLD the plan implements. When present, coverage is checked against it; when absent, coverage is judged against the plan's own stated scope, and the missing design is noted in Review Context |
| Constraints | No | Capacity, deadlines, team boundaries that bound feasibility |

Review the plan as written, not the plan you would have authored. Facts you know that the plan omits (a hidden consumer, a compliance deadline) enter as reviewer assumptions in Review Context and may ground findings - cite them as "reviewer context". When neither a design nor a stated scope is present, say so and review only internal soundness (dependencies, sizing, structure).

## Workflow

### STEP 1 - Setup

Use skill: `behavioral-principles`.
Use skill: `stack-detect`. Stack output grounds sizing sanity and names the stack-specific tasks a complete plan should contain (migration tool, test framework). If unknown, review stack-agnostic.

### STEP 2 - Intake

State in one sentence each: what the plan builds, its stated scope/exclusions, the source design (or "none supplied"), and the plan's task count and critical path as the author states them.

### STEP 3 - Coverage Audit

Does the plan cover the work the design (or stated scope) implies? For each design area, mark **Covered** (a task implements it), **Under-specified** (named but no real task), or **Missing** (no task). When a source design is supplied, walk its sections:

| Design area | A complete plan has |
| --- | --- |
| Module boundaries / components | A Foundation/Build task per new or changed component |
| Data and consistency model | Schema, migration, and backfill tasks; rollback data handling |
| API contracts | Endpoint implementation + contract-test tasks |
| Communication / events | Integration tasks for each cross-component call, queue, consumer |
| Failure and risk analysis | Ops-readiness tasks for the design's mitigations (breakers, retries, idempotency) |
| Observability | Metrics/traces/alerts/SLO tasks |
| Deployment and rollback | Rollout, migration-order, rollback-drill, flag-config tasks |
| Guardrails | Validation tasks that enforce each guardrail |

The most common defect is a plan that tasks out the happy-path build and omits migration, backward-compat, rollback, and observability the design calls for. A Missing item for a high-blast-radius area (rollback, migration for a Wide change) is a Blocker; other Missing items are Major minimum; Under-specified is Minor minimum, Major if it forces guesswork on a load-bearing task.

Load `Use skill: review-blast-radius` when a coverage gap's severity hinges on how wide the affected change is; a Critical/Wide verdict lifts a Missing rollback/migration gap to Blocker.

### STEP 4 - Structural Soundness

Check the plan's internal mechanics. Record each as a finding with severity.

- **Dependency graph:** every task states dependencies; no cycles; no task depends on work sequenced after it; another team's deliverable is `external`, not a task the plan owns
- **Critical path:** correctly identified (longest chain by hop count, not summed sizes; externals are not hops); the named chain matches the dependency graph
- **Sizing:** L/XL tasks justify their size; XL tasks carry a `split` note and are not silently dropped; sizes are engineering effort, not calendar time
- **Scope creep:** tasks with no design trace and not in stated scope; must-have framing on work that was never agreed
- **Phasing:** foundation work precedes the build that needs it; ops-readiness is not deferred past the risky launch

When a contract/migration/flag gap drives a finding, cite the relevant atomic's verdict inline (`ops-backward-compatibility`, `backend-db-migration`, `ops-feature-flags`) rather than pasting its block; load it only when the finding's severity depends on it.

### STEP 5 - Findings and Verdict

Number findings (F1, F2, ...). Each cites a specific task, phase, or omission, carries a severity, and recommends the smallest concrete change - do not redesign the plan. Distinguish **Missing** (absent), **Under-specified** (vague), and **Wrong** (incorrect on the facts, e.g., a miscomputed critical path). Record each root cause once; the verdict is driven by the highest severity, not the count.

| Severity | Meaning |
| --- | --- |
| Blocker | Plan cannot be committed - a load-bearing area is untasked (rollback for a Wide change) or the critical path is wrong |
| Major | Significant coverage gap, dependency error, or unjustified XL that must be fixed before commitment |
| Minor | Weak spot to improve; does not block commitment |
| Nit | Naming, formatting, phrasing |

| Verdict | Criteria |
| --- | --- |
| **Approve** | No Blockers, no Majors; all design areas Covered |
| **Approve with changes** | No Blockers; Majors bounded and specifically addressable |
| **Needs rework** | One or more Blockers, or gaps spanning multiple areas |

Any non-Approve verdict lists its required changes as a checkbox list (for Needs rework, the items driving the Blockers).

## Output Format

```markdown
# Task Breakdown Review: <Feature / System>

## Review Context

- **Plan reviewed:** <one line>
- **Source design:** <supplied | none - coverage judged against stated scope | none and no scope - internal soundness only>
- **Stack:** <detected | unknown>
- **Reviewer assumptions:** <reviewer-context facts; unavailable composed skills, if any>

## Intake

<what it builds; scope/exclusions; author-stated task count and critical path>

## Coverage Audit

| Design area | Status | Note |
| --- | --- | --- |
| <area> | Covered / Under-specified / Missing | <task name or gap> |

## Structural Soundness

- **Dependency graph:** <finding or "sound">
- **Critical path:** <finding or "correct">
- **Sizing:** <finding or "sound">
- **Scope creep:** <finding or "none">
- **Phasing:** <finding or "sound">

## Findings

- **F1 (<Blocker | Major | Minor | Nit>):** <finding citing the task/phase/omission>. Recommendation: <smallest concrete change>.
- **F2 ...**

## Verdict

**<Approve | Approve with changes | Needs rework>** - <driving findings>.

Required changes (omit if Approve):
- [ ] <change tied to a finding>
```

## Self-Check

- [ ] **Setup:** behavioral-principles + stack-detect loaded
- [ ] **Intake:** plan, stated scope, and source-design status stated
- [ ] **Coverage:** each design area (or stated-scope area) marked Covered/Under-specified/Missing; high-blast-radius Missing items are Blockers; blast-radius atomic loaded when a gap's severity depends on it
- [ ] **Structure:** dependency graph, critical path, sizing, scope creep, and phasing each assessed
- [ ] **Findings:** each numbered, cites a specific task/omission, carries a severity, recommends the smallest change; each root cause once
- [ ] **Verdict:** driven by highest severity; non-Approve lists required changes as a checklist

## Avoid

- Reviewing the plan you wish the author had written
- Rewriting the breakdown instead of naming the smallest fix
- Generic critique ("needs more tasks") without naming the design area or task
- Padding a Blocker review with Nits
- Approving with changes without listing the changes
- Treating a missing rollback/migration task on a Wide change as Minor
- Recomputing the critical path by summing sizes instead of counting hops
