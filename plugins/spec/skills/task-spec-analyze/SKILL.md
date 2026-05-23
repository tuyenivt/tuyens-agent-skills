---
name: task-spec-analyze
description: Cross-check spec.md / plan.md / tasks.md consistency - AC coverage, untested stories, NFR gaps, out-of-scope violations; writes analysis.md.
metadata:
  category: spec
  tags: [spec, sdd, analyze, quality, consistency]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Spec - Analyze

Cross-check the SDD pipeline's three artifacts (`spec.md`, `plan.md`, `tasks.md`) for consistency. Forward: every spec AC traces into plan and tasks. Reverse: every plan element and every task traces back to the spec. Output is `analysis.md` - an append-only findings log with severities and remediation routes.

## When to Use

After `task-spec-tasks` (pre-implementation gate), after implementation completes, or whenever drift between artifacts is suspected. Not for: requirements quality (`task-spec-checklist`), code review (`task-code-review`), architecture review (`task-design-architecture`).

## Inputs

- `<slug>` (required). Aborts if `spec.md` or `plan.md` missing. If `tasks.md` missing, runs `--scope spec-plan` automatically and notes the limitation.
- `--scope spec-plan` to skip tasks-level checks even when `tasks.md` exists.
- `--non-interactive` to skip next-command suggestion.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

If `analysis.md` exists, default to **amend** (preserve audit trail); offer replace/abort.

### STEP 4 - Branch on Mode

**speckit-installed:** instruct the user to run `/speckit-analyze` (any `before_analyze` / `after_analyze` hooks registered in `.specify/extensions.yml` will fire as part of that call - do not bypass them). Post-process by running our reverse-traceability check (STEP 6) over Spec Kit's output and append additional findings in a labeled section. Do not silently edit. Skip to STEP 9.

**standalone:** continue.

### STEP 5 - Index Artifacts

Read all three files; build:

- **Spec index:** AC IDs, NFR categories with targets, out-of-scope items, unresolved blocker/major open questions.
- **Plan index:** components, API endpoints, data-model entities, NFR mapping rows, alternatives, candidate ADRs, proposed spec amendments.
- **Tasks index:** tasks with `Type`, `Satisfies`, `Depends on`, `Status`; dependency graph; proposed plan amendments.

If `spec.md` has unresolved `spec-review` blockers, stop and recommend `task-spec-clarify`. Analyzing against a structurally broken spec produces noise.

### STEP 6 - Cross-Artifact Checks

Forward (spec -> plan -> tasks):

| ID  | Check                                                                                       | Severity |
| --- | ------------------------------------------------------------------------------------------- | -------- |
| F1  | Every AC is referenced by at least one plan element                                         | blocker  |
| F2  | Every AC is `Satisfies`-targeted by at least one task                                       | blocker  |
| F3  | Every NFR has a plan NFR-mapping row OR an explicit waiver with reason                      | major    |
| F4  | Every NFR with a verification step in plan has a matching `validation` task                 | major    |
| F5  | Every plan API endpoint has implementation + validation tasks                               | major    |
| F6  | Every plan data-model change has a `data` task                                              | major    |
| F7  | Every user story is addressed by an architecture component or API endpoint                  | major    |

Reverse (tasks -> plan -> spec):

| ID  | Check                                                                                          | Severity |
| --- | ---------------------------------------------------------------------------------------------- | -------- |
| R1  | Every task `Satisfies` resolves to an existing AC ID or NFR category                           | blocker  |
| R2  | Every plan element traces to at least one AC or NFR (no orphans)                               | major    |
| R3  | No task touches an out-of-scope item                                                           | blocker  |
| R4  | No plan element conflicts with another (e.g., "stateless service" + "in-memory session cache")| major    |

Structural:

| ID  | Check                                                                                       | Severity |
| --- | ------------------------------------------------------------------------------------------- | -------- |
| S1  | Tasks dependency graph is acyclic                                                           | blocker  |
| S2  | Every `Depends on:` reference exists                                                        | blocker  |
| S3  | At least one task has `Depends on: none` (entry point exists)                               | major    |
| S4  | Proposed spec amendments in `plan.md` are resolved or have an owner                         | minor    |
| S5  | Proposed plan amendments in `tasks.md` are resolved or have an owner                        | minor    |

Each finding records: `id` (`A-NNN`), `check` (F2, R3, ...), `severity`, `location` (`spec.md#AC3`, `tasks.md#T07`), `message`, `remediation` (workflow that fixes it, or "manual edit").

### STEP 7 - Roll Up Status

- `pass` - no blockers, no majors
- `needs-attention` - majors only
- `needs-rework` - any blocker

`pass` means the artifacts are internally consistent, not that the requirements are good (that is `task-spec-checklist`).

### STEP 8 - Write analysis.md

Append-only. Each invocation adds a new `## Session <timestamp>` block; never delete prior sessions.

### STEP 9 - Summarize

Print path, counts (per severity, per direction), status, top three findings, next command:

- `pass` -> `task-spec-implement <slug>` or `task-spec-checklist <slug>`.
- `needs-attention` -> address majors, re-run.
- `needs-rework` -> route to the top blocker's `remediation`.

`--non-interactive` skips the next-command suggestion.

## Output Format

```markdown
# Analysis - <Feature Name>

- **Slug:** <slug>
- **Last analyzed:** <YYYY-MM-DD HH:MM>

## Session <YYYY-MM-DD HH:MM>

- **Artifacts:** spec.md, plan.md, tasks.md   # note which were missing
- **Status:** pass | needs-attention | needs-rework
- **Counts:** blockers=<n> majors=<n> minors=<n>

### Findings

| ID    | Check | Severity | Location        | Message                                       | Remediation     |
| ----- | ----- | -------- | --------------- | --------------------------------------------- | --------------- |
| A-001 | F2    | blocker  | spec.md#AC3     | AC3 has no task in tasks.md that satisfies it | task-spec-tasks |
| A-002 | R2    | major    | plan.md#caching | Caching layer has no AC or NFR source         | task-spec-plan  |

### Notes
<Required when tasks.md was missing or when speckit mode contributed additional findings.>
```

## Self-Check

- [ ] Loaded `behavioral-principles` and `speckit-detect` first
- [ ] Aborted if `spec.md`/`plan.md` missing; ran spec-plan scope if only `tasks.md` was missing
- [ ] In speckit mode, additions appended in a labeled section (no silent edits)
- [ ] Stopped on unresolved spec-review blockers
- [ ] Ran every F1-F7, R1-R4, S1-S5 check
- [ ] Every finding has all six fields (id/check/severity/location/message/remediation)
- [ ] Status rollup matches highest severity present
- [ ] `analysis.md` is append-only
- [ ] Summary includes counts, status, top findings, next command

## Avoid

- Treating `pass` as "requirements are good" - that is `task-spec-checklist`'s job.
- Inventing findings to seem thorough.
- Editing `spec.md`/`plan.md`/`tasks.md` (this workflow is read-only against them).
- Auto-routing to remediation workflows.
- Discarding prior analysis sessions.
