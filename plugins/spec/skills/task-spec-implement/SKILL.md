---
name: task-spec-implement
description: SDD execution phase - reads tasks.md, delegates each task to stack workflow in spec-aware mode, updates status, resumable. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, implement, execution, orchestration]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Spec - Implement

Drives a feature from `tasks.md` to working code, one task at a time. Each task is delegated to the appropriate stack workflow in spec-aware mode (so it consumes `spec.md` + `plan.md` rather than re-eliciting). Status is updated in `tasks.md` after every step, making the workflow **resumable** - re-invocation picks up at the first `[ ]` task. Stops on the first failure or blocker.

## When to Use

After `task-spec-tasks`, or to resume an interrupted run. Not for: requirements (`task-spec-specify`), planning (`task-spec-plan`), one-off implementation outside SDD (`task-implement` / `task-*-new`), or bug fixes (`task-code-debug`).

## Inputs

- `<slug>` (required) - reads `.specs/<slug>/{spec,plan,tasks}.md`. Abort with the upstream workflow's name if any of the three is missing.
- `--task <ID>` to run a single task instead of resuming.
- `--dry-run` to print planned delegations without executing.
- `--stop-after <ID>` to halt after a specific task (staged review).

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

### STEP 3 - Detect Mode

Use skill: speckit-detect

### STEP 4 - Resolve Paths

Use skill: spec-artifact-paths

Abort cleanly if `spec.md`, `plan.md`, or `tasks.md` is missing.

### STEP 5 - Branch on Mode

**speckit-installed:** read `tasks.md` and `plan.md` for context, instruct the user to run `/speckit.implement`, then reconcile Spec Kit's task output with our schema if they want artifacts kept in sync. Do not silently overwrite Spec Kit's state. Skip to STEP 11.

**standalone:** continue.

### STEP 6 - Pick Next Task

| Flag          | Selection                                                                  |
| ------------- | -------------------------------------------------------------------------- |
| `--task <ID>` | That task. Error if missing or already `[x]`.                              |
| (default)     | First `[ ]` whose `Depends on:` are all `[x]`.                             |

If dependencies are unfinished, stop and surface them. The dependency graph is the contract.
On `--dry-run`, print the chosen task and planned delegation, then exit.
If every task is `[x]`, print "all tasks complete" and exit.

### STEP 7 - Resolve Delegation Target

Map task `Type` to a stack workflow. The convention is `task-<stack>-implement`.

| Task Type                   | Workflow                                                                                                |
| --------------------------- | ------------------------------------------------------------------------------------------------------- |
| `data` / `service` / `api`  | `task-<backend-stack>-implement` (spring/kotlin/dotnet/python/rails/node/go/rust/laravel)              |
| `frontend`                  | `task-<frontend-stack>-implement` (react/vue/angular)                                                   |
| `validation`                | Same stack workflow as the task it validates. Stack tests are owned by `task-*-implement`.              |
| `ops`                       | No single workflow. Run inline using `ops-*` and per-stack atomics. Do not invent a missing workflow.   |
| Unknown stack               | Fall back to `task-implement` (universal).                                                              |

For fullstack ambiguity (e.g., `api` could mean backend or frontend client), read the plan's API contract. If still ambiguous, ask once and remember.

### STEP 8 - Mark In Progress (BEFORE delegation)

Update `tasks.md`: `[ ]` -> `[~]`. Append a Revisions entry naming the task ID, timestamp, and `task-spec-implement`. Bump `Last updated`. The `[~]` is the resumable breadcrumb if the run is interrupted.

### STEP 9 - Delegate in Spec-Aware Mode

Invoke the chosen workflow with `--spec <slug>`. Pass only the task's slice (description, satisfies, dependencies) plus the relevant `plan.md` sections. **Do not** pass the entire `tasks.md`.

The delegated workflow:
- Skips its own GATHER/DESIGN.
- Constrains implementation to the task's `Satisfies` ACs.
- Refuses any change that touches an out-of-scope item.
- Returns control after local validation.

Surface clarifying questions to the user; do not answer on their behalf.

### STEP 10 - Mark Outcome

| Outcome              | Action                                                                                                |
| -------------------- | ----------------------------------------------------------------------------------------------------- |
| Clean completion     | `[~]` -> `[x]`. Revisions entry.                                                                      |
| Blocked / errored    | Leave `[~]`. Revisions entry captures the blocker. Stop the loop. Surface to user.                    |
| Spec gap surfaced    | Leave `[~]`. Append **Proposed Spec Amendment** to revisions. Stop the loop.                          |
| User aborted mid-task| Leave `[~]`. Revisions notes the abort. Re-invocation resumes here.                                   |

Bump `Last updated` on every change. Then loop to STEP 6 unless `--task` or `--stop-after` says otherwise.

### STEP 11 - Final Summary

Print: slug, mode, run counts, overall counts, blockers, spec gaps, next command:

- Tasks remain, no blocker -> `task-spec-implement <slug>` (resume).
- Blocker raised -> address, then resume.
- Spec amendment proposed -> `task-spec-clarify <slug>` -> `task-spec-plan <slug>` -> resume.
- All `[x]` -> `task-spec-analyze <slug>`.

## Output Format

Primary output is the mutated `tasks.md`. Chat summary:

```
Spec implement - <slug> (<mode>)
  This run:    completed=<n> in_progress=<n> blocked=<n>
  Overall:     [x]=<n> [~]=<n> [ ]=<n>
  Stack:       <detected stack>
  Blockers:    <list of T<NN>: reason  or "none">
  Spec gaps:   <list of T<NN>: proposed amendment  or "none">
  Next:        task-spec-implement <slug>  |  task-spec-clarify <slug>  |  task-spec-analyze <slug>
```

## Self-Check

- [ ] Loaded `behavioral-principles`, `stack-detect`, `speckit-detect` first
- [ ] Resolved paths through `spec-artifact-paths`
- [ ] Aborted if any of spec/plan/tasks missing
- [ ] In speckit mode, did not overwrite Spec Kit state
- [ ] Picked next task by Status + Dependencies, not file order
- [ ] Marked `[~]` BEFORE delegation
- [ ] Delegated with `--spec <slug>`; passed only the task's slice
- [ ] Marked `[x]` only on clean completion
- [ ] Did not edit `spec.md`/`plan.md` (amendments surfaced as proposals)
- [ ] Final summary includes counts, blockers, next command

## Avoid

- Looping past a blocker.
- Editing `spec.md` or `plan.md` from this workflow.
- Bulk-flipping `[~]` -> `[x]` after the fact (status mutates at the transition moment).
- Re-running GATHER/DESIGN inside the delegated workflow.
- Silent guesses for fullstack ambiguity (ask once, remember).
- Inventing an `ops` workflow when none exists.
