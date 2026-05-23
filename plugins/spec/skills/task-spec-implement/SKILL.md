---
name: task-spec-implement
description: SDD execute phase - read tasks.md, delegate each task to its stack workflow in --spec mode, mutate status, resume from [~]. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, implement, execution, orchestration]
  type: workflow
user-invocable: true
---

# Spec - Implement

Drives `tasks.md` to working code one task at a time, delegating to stack workflows in `--spec` mode. Status mutates in `tasks.md` at every transition, so the workflow is resumable: re-invocation reopens an in-progress `[~]` or picks the next ready `[ ]`. Stops on the first failure, blocker, or surfaced spec gap.

## When to Use

After `task-spec-tasks`, or to resume an interrupted run. Not for: requirements (`task-spec-specify`), planning (`task-spec-plan`), one-off feature work outside SDD, or bug fixes (`task-code-debug`).

**Inputs**

- `<slug>` (required) - reads `.specs/<slug>/{spec,plan,tasks}.md`.
- `--task <ID>` - run one task and exit.
- `--dry-run` - print the planned delegation, do not mutate.
- `--stop-after <ID>` - halt after that task completes (staged review).

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

### STEP 3 - Mode Detection

Use skill: speckit-detect

### STEP 4 - Resolve Paths

Use skill: spec-artifact-paths

Abort cleanly if any of `spec.md`, `plan.md`, `tasks.md` is missing, naming the missing file and the upstream workflow that produces it.

### STEP 5 - Checklist Gate

If `.specs/<slug>/checklists/` exists, count `- [ ]` vs `- [x]/[X]` per file and render a table with columns: `Checklist | Total | Completed | Incomplete | Status` (PASS when Incomplete=0). Any FAIL halts the run and asks: "Proceed with incomplete checklists?" - only an explicit yes continues. No `checklists/` directory: proceed silently.

### STEP 6 - Branch on Mode

**speckit-installed:** instruct the user to run `/speckit-implement` (its registered hooks and checklist gate fire there - do not duplicate or bypass them). Reconcile Spec Kit's task state into our schema only if asked. Skip to STEP 12.

**standalone:** continue.

### STEP 7 - Pick Next Task

Selection order:

| Flag             | Pick                                                            |
| ---------------- | --------------------------------------------------------------- |
| `--task <ID>`    | That task. Error if missing or already `[x]`.                   |
| (default)        | First `[~]`; else first `[ ]` whose `Depends on:` are all `[x]`. |

If nothing is selectable because dependencies are unfinished, list them and stop. If every task is `[x]`, print "all tasks complete" and exit. On `--dry-run`, print the chosen task and planned delegation, then exit.

### STEP 8 - Resolve Delegation Target

Map task `Type` to `task-<stack>-implement`:

| Task Type                  | Workflow                                                                              |
| -------------------------- | ------------------------------------------------------------------------------------- |
| `data` / `service` / `api` | `task-<backend>-implement` (spring, kotlin, dotnet, python, rails, node, go, rust, laravel) |
| `frontend`                 | `task-<frontend>-implement` (react, vue, angular)                                     |
| `validation`               | Same workflow as the task it validates.                                               |
| `ops`                      | No workflow. Run inline with `ops-*` and per-stack atomics. Do not invent one.        |

For fullstack ambiguity, read `plan.md`'s API contract section. If still ambiguous, ask once and remember for the rest of the run. If the detected stack has no `task-<stack>-implement`, stop and surface the gap - do not silently substitute.

### STEP 9 - Mark In Progress

Mutate `tasks.md`: `[ ]` -> `[~]`. Append a Revisions entry (task ID, timestamp, `task-spec-implement`). The `[~]` is the resume breadcrumb.

### STEP 10 - Delegate

Invoke the chosen workflow with `--spec <slug>`, passing only the task's slice (description, `Satisfies`, `Depends on`) and the relevant `plan.md` sections - not the full `tasks.md`. The delegate's spec-aware behavior is contracted by `spec-aware-preamble`; trust it. Surface clarifying questions to the user; do not answer for them.

### STEP 11 - Mark Outcome

| Outcome              | Action                                                                              |
| -------------------- | ----------------------------------------------------------------------------------- |
| Clean completion     | `[~]` -> `[x]`.                                                                     |
| Blocked / errored    | Leave `[~]`. Revisions captures the blocker. Stop the loop.                         |
| Spec gap surfaced    | Leave `[~]`. Append **Proposed Spec Amendment** to revisions. Stop the loop.        |
| User aborted         | Leave `[~]`. Revisions notes the abort.                                             |

Every mutation in STEP 9 or STEP 11 also bumps `Last updated`. Never edit `spec.md` or `plan.md` from here; amendments are proposals only. Never add or reword downstream tasks - that is `task-spec-tasks`'s job.

Loop to STEP 7 unless `--task` ran or `--stop-after` matched.

### STEP 12 - Final Summary

```
Spec implement - <slug> (<mode>)
  This run:    completed=<n> in_progress=<n> blocked=<n>
  Overall:     [x]=<n> [~]=<n> [ ]=<n>
  Stack:       <detected stack>
  Blockers:    <T<NN>: reason  |  none>
  Spec gaps:   <T<NN>: proposed amendment  |  none>
  Next:        <command>
```

Next-command rules:

- Tasks remain, no blocker: `task-spec-implement <slug>` (resume).
- Blocker: address, then resume.
- Spec amendment: `task-spec-clarify <slug>` -> `task-spec-plan <slug>` -> resume.
- All `[x]`: `task-spec-analyze <slug>`.

## Output Format

Primary output is the mutated `tasks.md` (status flips + Revisions entries + `Last updated`). Chat output is the STEP 12 summary block verbatim.

## Self-Check

- [ ] STEP 1-3: loaded `behavioral-principles`, `stack-detect`, `speckit-detect`
- [ ] STEP 4: aborted with the upstream workflow name if any artifact missing
- [ ] STEP 5: ran checklist gate; FAIL required explicit user yes
- [ ] STEP 6: in speckit mode, delegated to `/speckit-implement` without overwriting its state
- [ ] STEP 7: picked `[~]` before `[ ]`; respected dependencies
- [ ] STEP 8: chose a real `task-<stack>-implement`; surfaced gap if none exists
- [ ] STEP 9: marked `[~]` before delegating
- [ ] STEP 10: passed `--spec <slug>` and only the task's slice
- [ ] STEP 11: marked `[x]` only on clean completion; did not edit spec/plan or reword tasks
- [ ] STEP 12: summary includes counts, blockers, spec gaps, next command

## Avoid

- Skipping `[~]` tasks when resuming.
- Looping past a blocker.
- Editing `spec.md`, `plan.md`, or downstream task descriptions.
- Bulk-flipping status after the fact (mutate at the transition).
- Re-running GATHER/DESIGN inside the delegate.
- Silent guesses for fullstack ambiguity.
- Inventing a workflow when the stack has none.
