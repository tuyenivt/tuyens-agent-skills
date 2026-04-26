---
name: task-spec-analyze
description: Quality gate that cross-checks `spec.md`, `plan.md`, and `tasks.md` for consistency. Surfaces missing acceptance-criterion coverage, untested stories, plan elements with no spec source, tasks with no plan source, NFR gaps, and dangling out-of-scope violations. Writes `analysis.md` and recommends remediation. Speckit-aware - delegates to `/speckit.analyze` when Spec Kit is installed.
metadata:
  category: spec
  tags: [spec, sdd, analyze, quality, consistency]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spec - Analyze

Audits the SDD pipeline's three core artifacts (`spec.md`, `plan.md`, `tasks.md`) for cross-artifact consistency. The check is forward and reverse: every spec acceptance criterion must trace into the plan and the task list; every plan element and every task must trace back to the spec. Output is `analysis.md` - a structured findings list with severities and remediation routes.

## When to Use

- After `task-spec-tasks` and before `task-spec-implement`, as a quality gate
- After implementation completes, to verify nothing in spec or plan was left behind
- Whenever the user suspects spec/plan/tasks have drifted from each other
- As input to a stakeholder review of "are we ready to implement?"

**Not for:** Reviewing the requirements themselves for quality (use `task-spec-checklist`), reviewing code (use `task-code-review`), reviewing architecture proposals (use `task-design-architecture` review mode).

## Inputs

- The feature slug (required) - workflow reads `.specs/<slug>/{spec,plan,tasks}.md`
- Optional `--scope spec-plan` to skip tasks-level checks (useful pre-tasks); default checks all three artifacts when present
- Optional `--non-interactive` to emit findings and exit without recommending next commands

**Insufficient input handling:** If `spec.md` is missing, abort and recommend `task-spec-specify`. If `plan.md` is missing, abort and recommend `task-spec-plan`. If `tasks.md` is missing, run in `--scope spec-plan` mode and note the limitation in the output.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

Capture `mode`. Subsequent steps branch on it.

### STEP 3 - Resolve Artifact Paths

Use skill: spec-artifact-paths

Capture `spec`, `plan`, `tasks`, and `analysis` paths plus existence flags. If `analysis.md` already exists, ask the user whether to **replace**, **amend**, or **abort** - default to amend (analyses are an audit trail; preserve history).

### STEP 4 - Branch on Mode

#### Mode: speckit-installed

1. Pre-process: nothing - speckit owns the analysis logic.
2. Delegate by instructing the user to run `/speckit.analyze` (or invoke programmatically).
3. Post-process: read Spec Kit's analysis output and run our reverse-traceability check (STEP 6) over it. Surface any gaps Spec Kit did not catch as additional findings; do not silently edit.
4. Skip to STEP 9.

#### Mode: standalone

Continue to STEP 5.

### STEP 5 - Read All Three Artifacts

Read `spec.md`, `plan.md`, and (if present) `tasks.md`. Build three indexed maps in memory:

- **Spec index:** acceptance criterion IDs (`AC1`, `AC2`, ...), NFR categories with targets, out-of-scope items, open questions still tagged blocker/major
- **Plan index:** every architecture component, API endpoint, data model entity, NFR mapping row, alternative-considered entry, candidate ADR, proposed spec amendment
- **Tasks index:** every task ID with its `Type`, `Satisfies`, `Depends on`, `Status`, plus the dependency graph and the proposed plan amendments

If `spec.md` has unresolved blocker findings (per `spec-review`), stop and recommend `task-spec-clarify` before continuing - analyzing against a structurally broken spec produces noise, not signal.

### STEP 6 - Run Cross-Artifact Checks

Apply each check below, classifying each finding by **severity** (`blocker`, `major`, `minor`) and **direction** (forward = downstream is missing something, reverse = downstream has something with no upstream source).

**Forward checks (spec -> plan -> tasks):**

| ID  | Check                                                                                                          | Severity if failing |
| --- | -------------------------------------------------------------------------------------------------------------- | ------------------- |
| F1  | Every acceptance criterion in `spec.md` is referenced by at least one plan element                             | blocker             |
| F2  | Every acceptance criterion in `spec.md` is `Satisfies`-targeted by at least one task in `tasks.md`             | blocker             |
| F3  | Every NFR category in `spec.md` has a plan NFR-mapping row OR an explicit waiver with reason                   | major               |
| F4  | Every NFR with a verification step in `plan.md` has a matching `validation`-type task in `tasks.md`            | major               |
| F5  | Every plan API endpoint has at least one implementation task and at least one validation task                  | major               |
| F6  | Every plan data-model change has a corresponding `data`-type task                                              | major               |
| F7  | Every user story in `spec.md` is addressed by at least one architecture component or API endpoint in `plan.md` | major               |

**Reverse checks (tasks -> plan -> spec):**

| ID  | Check                                                                                           | Severity if failing |
| --- | ----------------------------------------------------------------------------------------------- | ------------------- |
| R1  | Every task has a non-empty `Satisfies` field that resolves to an existing AC ID or NFR category | blocker             |
| R2  | Every plan element traces to at least one acceptance criterion or NFR (no orphan plan content)  | major               |
| R3  | No task touches an out-of-scope item from `spec.md`                                             | blocker             |
| R4  | No plan element conflicts with another (e.g., "stateless service" + "in-memory session cache")  | major               |

**Structural checks:**

| ID  | Check                                                                                                  | Severity if failing |
| --- | ------------------------------------------------------------------------------------------------------ | ------------------- |
| S1  | Tasks dependency graph is acyclic                                                                      | blocker             |
| S2  | Every task referenced in another task's `Depends on:` exists                                           | blocker             |
| S3  | At least one task has `Depends on: none` (an entry point exists)                                       | major               |
| S4  | Proposed spec amendments in `plan.md` are either resolved (in spec revisions) or still open with owner | minor               |
| S5  | Proposed plan amendments in `tasks.md` are either resolved or still open with owner                    | minor               |

For each finding, record:

- `id`: stable identifier within this analysis (e.g., `A-001`)
- `check`: the check ID from the tables above (`F1`, `R3`, ...)
- `severity`: `blocker` | `major` | `minor`
- `location`: precise pointer (`spec.md#AC3`, `tasks.md#T07`, ...)
- `message`: one sentence describing the gap
- `remediation`: which workflow can fix it (`task-spec-clarify`, `task-spec-plan`, `task-spec-tasks`, manual edit)

### STEP 7 - Roll Up Status

Compute `summary.status`:

- `pass` - no blockers, no majors
- `needs-attention` - majors but no blockers
- `needs-rework` - any blocker

A `pass` status means the artifacts are internally consistent. It does NOT mean the requirements themselves are good - that is `task-spec-checklist`'s job.

### STEP 8 - Write analysis.md

Write to the resolved path using the template in **Output Format** below. In amend mode, append a new `## Session <timestamp>` block; never delete prior sessions. The file is an audit trail.

### STEP 9 - Summarize

Print a short summary to chat:

- Path written
- Findings: count per severity, count per direction (forward/reverse/structural)
- Status (`pass` / `needs-attention` / `needs-rework`)
- Top three findings by severity (blockers first)
- Suggested next command:
  - `pass` -> `task-spec-implement <slug>` (if not yet started) or `task-spec-checklist <slug>`
  - `needs-attention` -> address majors, then re-run `task-spec-analyze`
  - `needs-rework` -> route to the remediation workflow named in the top blocker

In `--non-interactive` mode, skip the next-command suggestion.

## Output Format

`analysis.md` template (standalone mode; speckit-installed mode defers to Spec Kit's template, with our additional findings appended in a clearly labeled section):

```markdown
# Analysis - <Feature Name>

- **Slug:** <slug>
- **Last analyzed:** <YYYY-MM-DD HH:MM>

## Session <YYYY-MM-DD HH:MM>

- **Artifacts:** spec.md, plan.md, tasks.md (or note which were missing)
- **Status:** pass | needs-attention | needs-rework
- **Counts:** blockers=<n> majors=<n> minors=<n>

### Findings

| ID    | Check | Severity | Location        | Message                                       | Remediation     |
| ----- | ----- | -------- | --------------- | --------------------------------------------- | --------------- |
| A-001 | F2    | blocker  | spec.md#AC3     | AC3 has no task in tasks.md that satisfies it | task-spec-tasks |
| A-002 | R2    | major    | plan.md#caching | Caching layer has no AC or NFR source         | task-spec-plan  |
| ...   | ...   | ...      | ...             | ...                                           | ...             |

### Notes

<Free-form. Required when `tasks.md` was missing (analysis ran in spec-plan scope only) or when speckit-installed mode contributed additional findings.>
```

## Self-Check

- [ ] Loaded `behavioral-principles` and `speckit-detect` before any other work
- [ ] Resolved artifact paths through `spec-artifact-paths` (no hardcoded `.specs/` strings)
- [ ] Aborted cleanly if `spec.md` or `plan.md` was missing
- [ ] In speckit-installed mode, did not silently edit Spec Kit's analysis output - additions appended in a labeled section
- [ ] Stopped on unresolved spec-review blockers rather than analyzing against a broken spec
- [ ] Ran every forward check (F1-F7) and every reverse check (R1-R4) and every structural check (S1-S5)
- [ ] Each finding has id, check, severity, location, message, and remediation
- [ ] Status rollup matches the highest severity present (blocker -> needs-rework, major -> needs-attention, otherwise pass)
- [ ] `analysis.md` is append-only - prior sessions preserved
- [ ] Final summary printed with counts, status, top findings, and next-command suggestion

## Avoid

- Treating `pass` as "requirements are good" - it only means artifacts are consistent. Use `task-spec-checklist` for requirements quality.
- Inventing findings to seem thorough - a clean cross-check is a valid outcome
- Editing `spec.md`, `plan.md`, or `tasks.md` directly - this workflow is read-only against those files
- Auto-routing to remediation workflows - the user decides when to run them
- Discarding prior analysis sessions - the audit trail is the point
- Conflating blocker and major findings - the severity table drives remediation routing

## Notes

- Run `task-spec-analyze` after every meaningful change to spec, plan, or tasks. Drift accumulates silently otherwise.
- A feature with `tasks.md` already partially implemented (`[~]` or `[x]` markers) can still be analyzed - `Status` markers are ignored by the cross-checks; only `Satisfies` and `Depends on` matter.
- The check ID convention (F1, R1, S1) is stable across runs - downstream tooling can grep `analysis.md` for specific check failures.
