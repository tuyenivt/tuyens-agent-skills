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

- `<slug>` (required). Aborts if `spec.md` or `plan.md` is missing. If only `tasks.md` is missing, auto-runs `--scope spec-plan` and records the limitation in `Notes`.
- `--scope spec-plan` to skip task-level checks.
- `--non-interactive` to skip the next-command suggestion.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

If `analysis.md` exists, default to **amend** (preserve audit trail); offer replace/abort.

### STEP 4 - Branch on Mode

**speckit-installed**: instruct the user to run `/speckit-analyze`. Post-process: run reverse-traceability checks (STEP 6) against Spec Kit's output and append additions in a labeled `### Marketplace Additions` subsection. Skip to STEP 9.

**standalone**: continue.

### STEP 5 - Index Artifacts

- **Spec**: AC IDs (regex `^AC\d+`), NFR categories with targets, user story IDs, out-of-scope items, unresolved `spec-review` blockers.
- **Plan**: components, API endpoints, data-model entities, NFR mapping rows, alternatives (rejected items become out-of-scope mirror), all section headers and anchors.
- **Tasks**: tasks with `Type`, `Satisfies`, `Deps`, `Status`; dependency graph.

If unresolved `spec-review` blockers exist on `spec.md`, stop and recommend `task-spec-clarify`.

### STEP 6 - Run Checks

A `Satisfies` value is valid iff it matches `AC<n>`, `NFR-<category>`, or the literal `bootstrap (no AC)`; anything else (e.g., `US-future`) is an R1 blocker with message "unknown satisfies target: <value>".

| ID  | Direction  | Check                                                                                            | Severity |
| --- | ---------- | ------------------------------------------------------------------------------------------------ | -------- |
| F1  | forward    | Every AC is referenced in a plan API row, data-model row, NFR mapping row, or explicit AC table  | blocker  |
| F2  | forward    | Every AC is the `Satisfies` target of at least one task                                          | blocker  |
| F3  | forward    | Every NFR has a plan NFR-mapping row OR an `n-a-because-<reason>` waiver                         | major    |
| F4  | forward    | Every NFR has at least one `Type: validation` task with matching `Satisfies`                     | major    |
| F5  | forward    | Every plan API endpoint has an implementation task and a `Type: validation` task                 | major    |
| F6  | forward    | Every plan data-model change has a `Type: data` task                                              | major    |
| F7  | forward    | Every user story ID is named in plan architecture, API, or data-model sections                   | major    |
| F8  | forward    | Every user story has at least one AC                                                              | major    |
| R1  | reverse    | Every task `Satisfies` value parses to a valid target and resolves to a spec entry               | blocker  |
| R2  | reverse    | Every plan component/endpoint/entity traces to at least one AC or NFR                            | major    |
| R3  | reverse    | No task touches a spec out-of-scope item or a plan-rejected alternative                          | blocker  |
| R4  | reverse    | No plan element contradicts another                                                              | major    |
| S1  | structural | Tasks dependency graph is acyclic                                                                | blocker  |
| S2  | structural | Every `Deps:` task ID exists in `tasks.md`                                                        | blocker  |
| S3  | structural | At least one task has `Deps: none`                                                                | major    |
| S4  | structural | Every cross-artifact reference resolves to a Markdown heading slug, task ID (`T\d+`), AC ID (`AC\d+`), or `NFR-<category>` in the target file | major |

**Finding record** (every field required):

- `id`: `<check>-<NNN>` (3-digit counter scoped to that check), assigned in document order of `location` within each artifact (spec.md, plan.md, tasks.md).
- `check`: F1-F8, R1-R4, S1-S4
- `severity`: blocker | major | minor
- `location`: artifact + anchor, e.g., `spec.md#AC3`, `tasks.md#T07`
- `message`: one sentence
- `remediation`: `task-spec-tasks` | `task-spec-plan` | `task-spec-clarify` | `manual edit`

### STEP 7 - Roll Up Status

- `pass` - zero blockers, zero majors
- `needs-attention` - majors only
- `needs-rework` - any blocker

`pass` means internally consistent, not "requirements are good" (use `task-spec-checklist` for that).

### STEP 8 - Write analysis.md

Append a new `## Session <timestamp>` block; never delete prior sessions.

### STEP 9 - Summarize

Print: file path, per-severity counts, per-direction counts, status, top three findings (severity desc; tie-break by check ID then location), next command (skipped on `--non-interactive`).

- `pass` -> `task-spec-checklist <slug>` if requirements quality has not been gated, else `task-spec-implement <slug>`
- `needs-attention` -> address majors, re-run
- `needs-rework` -> route to top blocker's `remediation`

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
| F2-001 | F2    | blocker  | spec.md#AC3     | No task Satisfies AC3                                              | task-spec-tasks   |
| R1-001 | R1    | blocker  | tasks.md#T06    | unknown satisfies target: US-future                                | task-spec-tasks   |
| R3-001 | R3    | blocker  | tasks.md#T08    | Task touches out-of-scope item "partial refunds"                   | task-spec-tasks   |
| F4-001 | F4    | major    | spec.md#NFR-perf | No validation task for NFR "p95 < 200ms"                          | task-spec-tasks   |

### Notes

<Required when tasks.md was missing, scope was reduced, or speckit mode contributed additions.>
```

## Self-Check

- [ ] STEP 1-3: behavioral-principles loaded; mode detected; paths resolved; existing `analysis.md` handled
- [ ] STEP 4: speckit-mode branch appended additions in labeled subsection
- [ ] STEP 5: aborted on missing `spec.md`/`plan.md`; stopped on unresolved `spec-review` blockers
- [ ] STEP 6: every F1-F8, R1-R4, S1-S4 ran; every finding has all six fields with stable `<check>-<NNN>` IDs
- [ ] STEP 7: status matches highest severity present
- [ ] STEP 8: appended a new session; prior sessions intact
- [ ] STEP 9: summary prints counts, status, top three findings (severity then check-id), next command unless `--non-interactive`

## Avoid

- Treating `pass` as "requirements are good".
- Inventing findings to seem thorough; if a check passes, do not record it.
- Editing `spec.md` / `plan.md` / `tasks.md` (this workflow is read-only against them).
- Renumbering or removing prior session findings.
