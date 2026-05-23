---
name: task-spec-plan
description: SDD planning phase - reads spec.md, produces plan.md with architecture, data model, API contract, alternatives, NFR mapping, risks. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, plan, architecture, design]
  type: workflow
user-invocable: true
---

# Spec - Plan

Translates the **what** in `spec.md` into the **how**: a stack-aware implementation plan (`plan.md`) with architecture, data model, API contract, NFR mapping, alternatives, and risks. Stops short of code - that is `task-spec-implement`'s job.

## When to Use

After `task-spec-specify` (and ideally `task-spec-clarify`). Re-plan when `plan.md` has drifted from the spec. Requires `<slug>`. Pass `--replan` to regenerate instead of amend (default is amend: preserve, append revisions). Not for: requirements (`task-spec-specify`), Q&A (`task-spec-clarify`), task generation (`task-spec-tasks`), code (`task-spec-implement`).

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

If unknown, proceed but flag the plan `Stack Type: unknown` and avoid framework-specific structure.

### STEP 3 - Detect Mode

Use skill: speckit-detect

### STEP 4 - Resolve Paths

Use skill: spec-artifact-paths

If `plan.md` exists, default to **amend**; offer replace/abort.

### STEP 5 - Read the Spec

Read `spec.md` and (if present) `clarifications.md`. Extract problem, users, stories, ACs, NFRs, out-of-scope, open questions. Abort if `spec.md` is missing or any open question is tagged blocker/major (recommend `task-spec-clarify`).

Do not invent requirements. Gaps surface as **Proposed Spec Amendments** in the output - never edit `spec.md`.

### STEP 6 - Branch on Mode

- **speckit-installed:** apply STEP 7 composition rules as a brief, hand to `/speckit-plan` (any `before_plan` / `after_plan` hooks in `.specify/extensions.yml` fire as part of that call - do not bypass), post-process with STEP 9 cross-check as suggestions, skip to STEP 11.
- **standalone:** continue.

### STEP 7 - Compose the Plan

| Section                       | How to populate                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **Architecture overview**     | Components, boundaries, data ownership. Stack-aware. Reference any joined system.                                     |
| **Data model**                | Entities, key fields, relationships, indexes. Migration approach if existing schema is touched.                       |
| **API contract**              | Endpoints, request/response shapes, error model. Frontend: component contracts, state shape.                          |
| **NFR mapping**               | `Use skill: nfr-specification`. Every spec NFR maps to a plan element (or explicit waiver). For quantitative NFRs, run the floor formula (`bits / bandwidth`, `per-request cost * target vs capacity`, `users * size * retention`, storage round-trip floor); flag infeasible budgets as Proposed Spec Amendments. |
| **Alternatives considered**   | Every significant decision: 2-3 viable options, compared on dimensions that differ (cost, latency, complexity, lock-in, reversibility), chosen option with rationale, at least one rejected option with reason. |
| **Risks and mitigations**     | Failure modes, rollback strategy, data-loss surfaces. Cross-reference NFRs.                                           |
| **Decisions worth recording** | Candidate ADRs - list each with rationale; actual ADR authoring is the user's call (typically using the project's ADR template). |
| **Out of scope (reaffirmed)** | Restate spec's out-of-scope verbatim - prevents tasks from re-introducing exclusions.                                 |

Composition rules:
- Stay at contract level. No class names, no SQL syntax. Senior-reviewer sign-off level.
- Every plan element traces to at least one AC or NFR. Flag orphans.
- Fullstack: one plan with labeled backend/frontend sections (not two plans).
- If `architecture` plugin is installed and the feature is non-trivial, soft-suggest `task-design-architecture`. Do not auto-run.

### STEP 8 - Plan-Spec Cross-Check

Gate before writing:

- Every story addressed by an architecture component or API endpoint.
- Every AC has a plan element testable against it.
- No plan element touches out-of-scope.
- No plan element conflicts with another (e.g., "stateless service" + "in-memory session cache").

For each gap: add the missing element (preferred), stop and ask (if it implies a spec change), or mark as a Proposed Spec Amendment (minor, defer to clarify).

### STEP 9 - Write plan.md

Append-only in amend mode (new revision section, never delete prior content).

### STEP 10 - Summarize

Print path, sections populated, alternatives recorded, ADR candidates, mode, proposed amendments, next command (`task-spec-tasks <slug>`).

## Output Format

```markdown
# Plan - <Feature Name>

- **Slug:** <slug>
- **Status:** draft | reviewed | tasked | implementing | complete
- **Stack:** <detected stack> (or `unknown`)
- **Created:** <YYYY-MM-DD>
- **Last updated:** <YYYY-MM-DD>

## Summary
<Two or three sentences: what is being built, chosen shape, why.>

## Architecture Overview
<Components, boundaries, data ownership.>

## Data Model
<Entities, fields, relationships, indexes, migrations.>

## API Contract
<Endpoints / interfaces / component contracts. Request/response shapes, error model.>

## NFR Mapping

| NFR Category | Spec Target | Plan Element | Feasibility | Verification |
| ------------ | ----------- | ------------ | ----------- | ------------ |
| Performance  | p95 < 200ms | read-through cache on hot path | transfer floor 4s @ 10Mbps for 5MB - INFEASIBLE; flagged | load test in Phase 4 |

## Alternatives Considered

### Decision: <title>
- **Context:** <one paragraph>
- **Chosen:** <option>
- **Rejected:** <option> - <why not>
- **Trade-off accepted:** <what is sacrificed>
- **Reversibility:** Easy | Moderate | Hard - <reason>

## Risks and Mitigations

| Risk | Likelihood: {Low\|Med\|High} | Impact: {Low\|Med\|High} | Mitigation | Rollback |
| ---- | ---------------------------- | ------------------------ | ---------- | -------- |

## Decisions Worth Recording (Candidate ADRs)
- **<title>** - <one-line rationale>

## Out of Scope (Reaffirmed)
<Verbatim from spec.md.>

## Proposed Spec Amendments
<Gaps surfaced during planning. Empty if none. Do NOT edit spec.md from this workflow.>

## Revisions
- <YYYY-MM-DD>: <change> (by `task-spec-plan` | manual)
```

## Self-Check

- [ ] STEP 1: Loaded `behavioral-principles`
- [ ] STEP 2: Loaded `stack-detect`; flagged `Stack Type: unknown` if undetermined
- [ ] STEP 3: Loaded `speckit-detect`
- [ ] STEP 4: Paths resolved via `spec-artifact-paths`; existing `plan.md` triage offered
- [ ] STEP 5: Aborted on missing `spec.md` or unresolved blockers
- [ ] STEP 6: Mode branch followed (speckit pre/post-process, or standalone continuation)
- [ ] STEP 7: Plan composed per table; NFR feasibility floor run on quantitative NFRs; infeasible budgets surfaced as Proposed Spec Amendments
- [ ] STEP 8: Cross-check passed (stories, ACs, out-of-scope, no internal conflicts)
- [ ] STEP 9: `plan.md` written; `spec.md` not edited
- [ ] STEP 10: Summary includes sections, alternatives, ADR candidates, mode, amendments, next command

## Avoid

- Writing code, class skeletons, or SQL syntax (those belong in implement).
- Inventing requirements not in `spec.md` - propose amendments instead.
- Editing `spec.md`.
- Skipping Alternatives Considered because "the choice was obvious" - record at least one rejected option.
- Overwriting `plan.md` without offering replace/amend/abort.
- Auto-running `task-design-architecture`.
- Silently absorbing an arithmetically infeasible NFR.
