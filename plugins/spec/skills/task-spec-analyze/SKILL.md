---
name: task-spec-analyze
description: Cross-check spec.md / plan.md / tasks.md consistency - AC coverage, untested stories, NFR gaps, out-of-scope violations; writes analysis.md.
metadata:
  category: spec
  tags: [spec, sdd, analyze, quality, consistency]
  type: workflow
user-invocable: true
---

# Spec - Analyze

Cross-check `spec.md`, `plan.md`, `tasks.md` for forward traceability (every AC reaches plan and tasks) and reverse traceability (every plan element and task traces back to spec). Appends a findings session to `.specs/<slug>/analysis.md`.

## When to Use

After `task-spec-tasks` (pre-implementation gate), after implementation, or when drift is suspected.

**Inputs:**

- `<slug>` (required). Aborts if `spec.md` or `plan.md` missing. If only `tasks.md` is missing, auto-runs `--scope spec-plan` and records the limitation in `Notes`.
- `--scope spec-plan` to skip task-level checks even when `tasks.md` exists.
- `--non-interactive` to skip the next-command suggestion.

Not for: requirements quality (use `task-spec-checklist`), code review (`task-code-review`), architecture review (`task-design-architecture`).

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

If `analysis.md` exists, default to **amend** (preserve audit trail); offer replace/abort.

### STEP 4 - Branch on Mode

**speckit-installed:** tell the user to run `/speckit-analyze` (registered `before_analyze` / `after_analyze` hooks fire as part of that call - do not bypass). Post-process: run the reverse-traceability checks (STEP 6) against Spec Kit's output and append additions in a labeled subsection. Skip to STEP 9.

**standalone:** continue.

### STEP 5 - Index Artifacts

Build three indices:

- **Spec:** AC IDs (regex `^AC\d+`), NFR categories with targets, user story IDs, out-of-scope items, unresolved `spec-review` blockers.
- **Plan:** components, API endpoints, data-model entities, NFR mapping rows, alternatives (rejected items become an out-of-scope mirror), candidate ADRs, proposed spec amendments, all section headers and anchors.
- **Tasks:** tasks with `Type`, `Satisfies`, `Depends on`, `Status`; dependency graph; proposed plan amendments.

If unresolved `spec-review` blockers exist on `spec.md`, stop and recommend `task-spec-clarify`.

### STEP 6 - Run Checks

Run every check below. A `Satisfies` value is valid only if it matches `AC<n>` or `NFR-<category>`; anything else (e.g., `US-future`) is an R1 blocker with message "unknown satisfies target: <value>".

| ID  | Direction  | Check                                                                                            | Severity |
| --- | ---------- | ------------------------------------------------------------------------------------------------ | -------- |
| F1  | forward    | Every AC is referenced in a plan API row, data-model row, NFR mapping row, or explicit AC table  | blocker  |
| F2  | forward    | Every AC is the `Satisfies` target of at least one task                                          | blocker  |
| F3  | forward    | Every NFR has a plan NFR-mapping row OR an explicit waiver with reason                           | major    |
| F4  | forward    | Every NFR has at least one task with `Type: validation` whose `Satisfies` names that NFR         | major    |
| F5  | forward    | Every plan API endpoint has an implementation task and a `Type: test` or `validation` task       | major    |
| F6  | forward    | Every plan data-model change has a `Type: data` task                                              | major    |
| F7  | forward    | Every user story ID is named in plan architecture, API, or data-model sections                   | major    |
| F8  | forward    | Every user story with no AC is flagged (story exists but is untestable)                          | major    |
| R1  | reverse    | Every task `Satisfies` value parses as `AC<n>` or `NFR-<category>` and resolves to a spec entry  | blocker  |
| R2  | reverse    | Every plan component/endpoint/entity traces to at least one AC or NFR                            | major    |
| R3  | reverse    | No task touches a spec out-of-scope item or a plan-rejected alternative                          | blocker  |
| R4  | reverse    | No plan element contradicts another (e.g., "stateless service" + "in-memory session cache")     | major    |
| S1  | structural | Tasks dependency graph is acyclic                                                                | blocker  |
| S2  | structural | Every `Depends on:` task ID exists in `tasks.md`                                                  | blocker  |
| S3  | structural | At least one task has `Depends on: none`                                                          | major    |
| S4  | structural | Every cross-artifact reference (e.g., "plan section X.Y", "AC<n>") resolves to a real anchor    | major    |
| S5  | structural | Proposed spec amendments in `plan.md` and proposed plan amendments in `tasks.md` have an owner  | minor    |

**Finding record** (every field required):

- `id`: `<check>-<NNN>` where `<NNN>` is a 3-digit counter scoped to that check, assigned in lexicographic order of `location`. Stable across re-runs as long as artifacts don't change.
- `check`: F1-F8, R1-R4, S1-S5
- `severity`: blocker | major | minor
- `location`: artifact + anchor, e.g., `spec.md#AC3`, `tasks.md#T07`
- `message`: one sentence stating what is wrong
- `remediation`: workflow that fixes it (`task-spec-tasks`, `task-spec-plan`, `task-spec-clarify`) or `manual edit`

### STEP 7 - Roll Up Status

- `pass` - zero blockers, zero majors
- `needs-attention` - majors only
- `needs-rework` - any blocker

`pass` means artifacts are internally consistent, not that requirements are good (use `task-spec-checklist` for that).

### STEP 8 - Write analysis.md

Append a new `## Session <timestamp>` block. Never delete prior sessions. If amending, the file already has a `# Analysis - <Feature>` header; only append the session block.

### STEP 9 - Summarize

Print: file path, per-severity counts, per-direction counts, status, top three findings (highest severity first), next command. `--non-interactive` skips the next-command line.

- `pass` -> `task-spec-implement <slug>` or `task-spec-checklist <slug>`
- `needs-attention` -> address majors, re-run
- `needs-rework` -> route to the top blocker's `remediation`

## Output Format

```markdown
# Analysis - <Feature Name>

- **Slug:** <slug>
- **Last analyzed:** <YYYY-MM-DD HH:MM>

## Session <YYYY-MM-DD HH:MM>

- **Artifacts:** spec.md, plan.md, tasks.md   # mark any missing
- **Scope:** full | spec-plan
- **Status:** pass | needs-attention | needs-rework
- **Counts:** blockers=<n> majors=<n> minors=<n> (forward=<n> reverse=<n> structural=<n>)

### Findings

| ID     | Check | Severity | Location        | Message                                                            | Remediation       |
| ------ | ----- | -------- | --------------- | ------------------------------------------------------------------ | ----------------- |
| R3-001 | R3    | blocker  | tasks.md#T06    | Task touches out-of-scope item "partial refunds"                   | task-spec-tasks   |
| S2-001 | S2    | blocker  | tasks.md#T07    | Depends on T08 which does not exist                                | task-spec-tasks   |
| F4-001 | F4    | major    | spec.md#NFR-pii | No validation task for NFR "PII-free audit log"                    | task-spec-tasks   |
| F7-001 | F7    | major    | spec.md#US3     | User story not named in plan architecture, API, or data-model     | task-spec-plan    |

### Notes

<Required when tasks.md was missing, scope was reduced, or speckit mode contributed additions.>
```

## Self-Check

- [ ] STEP 1: `behavioral-principles` loaded
- [ ] STEP 2: `speckit-detect` ran and mode is recorded
- [ ] STEP 3: paths resolved; existing `analysis.md` handled (amend default)
- [ ] STEP 4: speckit-mode branch appended additions in labeled subsection (no silent edits)
- [ ] STEP 5: aborted on missing `spec.md`/`plan.md`; stopped on unresolved `spec-review` blockers
- [ ] STEP 6: every F1-F8, R1-R4, S1-S5 ran; every finding has all six fields with stable `<check>-<NNN>` IDs
- [ ] STEP 7: status matches highest severity present
- [ ] STEP 8: appended a new session; prior sessions intact
- [ ] STEP 9: summary includes counts, status, top three findings, next command (unless `--non-interactive`)

## Avoid

- Treating `pass` as "requirements are good" (that is `task-spec-checklist`).
- Inventing findings to seem thorough; if a check passes, do not record it.
- Editing `spec.md` / `plan.md` / `tasks.md` (this workflow is read-only against them).
- Auto-routing to remediation workflows.
- Renumbering or removing prior session findings.
