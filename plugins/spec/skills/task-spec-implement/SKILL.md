---
name: task-spec-implement
description: Execution phase of Spec-Driven Development. Reads `tasks.md` and implements tasks one at a time, delegating each to the appropriate stack workflow (`task-spring-new`, `task-react-new`, ...) in spec-aware mode. Updates task `Status:` markers as work progresses. Resumes from the first `[ ]` task on re-invocation. Speckit-aware - delegates to `/speckit.implement` when Spec Kit is installed.
metadata:
  category: spec
  tags: [spec, sdd, implement, execution, orchestration]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spec - Implement

Drives a feature from `tasks.md` to working code, one task at a time. Each task is delegated to the appropriate stack workflow (running in spec-aware mode so it consumes `spec.md` + `plan.md` rather than re-eliciting). Task status is updated in `tasks.md` after each step so the workflow is **resumable** - re-invoking picks up at the first `[ ]` task. Stops on the first failure or blocker; never silently continues past a broken task.

## When to Use

- After `task-spec-tasks` for a feature whose `tasks.md` exists and is stable
- To resume an interrupted implementation (workflow auto-detects the next `[ ]` task)
- When the user wants the spec pipeline to run end-to-end execution after `task-spec-plan` and `task-spec-tasks`

**Not for:** Authoring requirements (use `task-spec-specify`), generating the plan or task list (use `task-spec-plan`, `task-spec-tasks`), one-off feature implementation outside the SDD pipeline (use `task-implement` or stack-specific `task-*-new` directly), bug fixes (use `task-code-debug`).

## Inputs

- The feature slug (required) - workflow reads `.specs/<slug>/{spec,plan,tasks}.md`
- Optional `--task <ID>` to implement a single specific task instead of resuming from the first `[ ]`
- Optional `--dry-run` to print the planned delegation per task without executing
- Optional `--stop-after <ID>` to halt after a specific task completes (useful for staged review)

**Insufficient input handling:** If `tasks.md` is missing, abort and recommend `task-spec-tasks`. If `plan.md` is missing, abort and recommend `task-spec-plan`. If `spec.md` is missing, abort and recommend `task-spec-specify`. If every task is already `[x]`, print "all tasks complete" and exit.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

Capture the detected stack so STEP 6's delegation table can pick the right stack workflow.

### STEP 3 - Detect Mode

Use skill: speckit-detect

Capture `mode`. Subsequent steps branch on it.

### STEP 4 - Resolve Artifact Paths

Use skill: spec-artifact-paths

Capture `spec`, `plan`, and `tasks` paths plus existence flags. Abort cleanly if any of the three is missing, with a recommendation pointing at the upstream workflow that produces it.

### STEP 5 - Branch on Mode

#### Mode: speckit-installed

1. Pre-process: read `tasks.md` to surface what is about to run; read `plan.md` for context.
2. Delegate by instructing the user to run `/speckit.implement` (or invoke programmatically). Spec Kit owns task execution and status tracking.
3. Post-process: re-read Spec Kit's task output and reconcile any status markers with our `tasks.md` schema if the user wants this plugin's artifacts kept in sync. Do not silently overwrite Spec Kit's state.
4. Skip to STEP 11.

#### Mode: standalone

Continue to STEP 6.

### STEP 6 - Pick the Next Task

Read `tasks.md` and select the task to execute next:

| Input flag    | Selection rule                                                             |
| ------------- | -------------------------------------------------------------------------- |
| `--task <ID>` | Use that specific task ID. Error if not found or already `[x]`.            |
| (default)     | First task whose `Status:` is `[ ]` AND whose `Depends on:` are all `[x]`. |

If the next available task has unfinished dependencies, stop and surface them - do not skip ahead and do not silently start a task whose prerequisites are incomplete. The dependency graph is the contract.

If `--dry-run` is set, print the chosen task plus its planned delegation (STEP 7) and exit without executing.

### STEP 7 - Resolve Delegation Target

Map the task's `Type` and the detected stack to a stack workflow:

| Task Type                  | Stack -> Workflow                                                                                                                                                                                                                           |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `data` / `service` / `api` | Java -> `task-spring-new`; Kotlin -> `task-kotlin-new`; .NET -> `task-dotnet-new`; Python -> `task-python-new`; Rails -> `task-rails-new`; Node -> `task-node-new`; Go -> `task-go-new`; Rust -> `task-rust-new`; PHP -> `task-laravel-new` |
| `frontend`                 | React -> `task-react-new`; Vue -> `task-vue-new`; Angular -> `task-angular-new`                                                                                                                                                             |
| `validation`               | Same stack workflow as the task it validates (each `task-*-new` covers tests for its stack). For pure cross-cutting test work, soft-suggest `task-code-test` if it has gained spec-aware mode.                                              |
| `ops`                      | No single stack workflow. Run inline using core atomics (`ops-observability`, `ops-feature-flags`, `ops-release-safety`) and the relevant per-stack `<stack>-*` atomics. Do not invent a missing workflow.                                  |
| Unknown stack              | Fall back to `task-implement` (which itself delegates or runs the universal fallback).                                                                                                                                                      |

For polyglot or fullstack features where the task is ambiguous (`api` task in a fullstack repo could mean backend API or frontend client), read the task description and the plan's API contract to decide. If still ambiguous, ask the user once and remember for the rest of this workflow run.

### STEP 8 - Mark Task In Progress

Update `tasks.md`: change the chosen task's `Status:` from `[ ]` to `[~]`. Append (or extend) a Revisions entry naming the task ID, timestamp, and `task-spec-implement` as the actor. Bump `Last updated`.

This must happen **before** delegation so an interrupted run leaves a visible breadcrumb.

### STEP 9 - Delegate in Spec-Aware Mode

Invoke the chosen workflow with `--spec <slug>` so its `spec-aware-preamble` step loads `spec.md` + `plan.md` + the specific task's scope from `tasks.md`. The delegated workflow will:

- Skip its own GATHER and DESIGN
- Constrain its implementation to the task's `Satisfies` acceptance criteria
- Refuse any change that touches an out-of-scope item (per spec-aware-preamble's hard fences)
- Return control once the task's deliverable is built and validated by the stack's local checks

Pass through the relevant slice of `plan.md` and the single task's spec (description, satisfies, dependencies). Do NOT pass the entire `tasks.md` - the delegated workflow should not see siblings or sequencing.

If the delegated workflow asks a clarifying question, surface it to the user. Do not answer on the user's behalf.

### STEP 10 - Mark Task Complete or Blocked

After the delegation returns:

| Outcome                               | Action                                                                                                          |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Delegated workflow completed cleanly  | Update `Status:` `[~]` -> `[x]`. Append Revisions entry naming the task ID and outcome.                         |
| Delegated workflow blocked or errored | Leave `Status:` as `[~]`. Append Revisions entry capturing the blocker. Stop the loop. Surface to user.         |
| Delegated workflow flagged a spec gap | Leave `Status:` as `[~]`. Append a **Proposed Spec Amendment** to `tasks.md`'s revision section. Stop the loop. |
| User aborted mid-task                 | Leave `Status:` as `[~]`. Note the abort in Revisions. Re-invocation will resume at this task.                  |

Bump `Last updated` on every status change.

After a successful task, decide whether to continue:

- If `--stop-after <ID>` matches the just-completed task, stop and summarize
- If `--task <ID>` was set, stop after that single task
- Otherwise loop back to STEP 6 to pick the next task

### STEP 11 - Final Summary

Print to chat:

- Slug and mode used (speckit-installed or standalone)
- Tasks completed this run, tasks already complete, tasks remaining (`[ ]` count)
- Any blockers or proposed spec amendments encountered
- Suggested next command:
  - If unfinished tasks remain and no blocker -> `task-spec-implement <slug>` (resume)
  - If a blocker was raised -> address blocker, then resume
  - If a spec amendment was proposed -> `task-spec-clarify <slug>` then `task-spec-plan <slug>` then resume
  - If all tasks complete -> `task-spec-analyze <slug>` (cross-artifact consistency check)

## Output Format

The workflow's primary output is **mutated `tasks.md`** (status updates, revisions). The chat summary is the secondary output:

```
Spec implement - <slug> (<mode>)
  This run:    completed=<n> in_progress=<n> blocked=<n>
  Overall:     [x]=<n> [~]=<n> [ ]=<n>
  Stack:       <detected stack>
  Blockers:    <list of T<NN>: reason - or "none">
  Spec gaps:   <list of T<NN>: proposed amendment - or "none">
  Next:        task-spec-implement <slug>   |   task-spec-clarify <slug>   |   task-spec-analyze <slug>
```

## Self-Check

- [ ] Loaded `behavioral-principles`, `stack-detect`, and `speckit-detect` before any other work
- [ ] Resolved artifact paths through `spec-artifact-paths` (no hardcoded `.specs/` strings)
- [ ] Aborted cleanly if any of `spec.md`, `plan.md`, `tasks.md` was missing
- [ ] In speckit-installed mode, did not silently overwrite Spec Kit's state
- [ ] Selected the next task by Status + Dependencies, not by file order
- [ ] Refused to start a task whose dependencies are not yet `[x]`
- [ ] Marked task `[~]` BEFORE delegating (resumable breadcrumb)
- [ ] Delegated with `--spec <slug>` so the stack workflow runs in spec-aware mode
- [ ] Did not pass full `tasks.md` to delegated workflow - only the single task's scope
- [ ] Marked task `[x]` only on clean completion; left `[~]` on block/abort/error
- [ ] Did NOT edit `spec.md` or `plan.md` from this workflow - amendments surfaced as proposals
- [ ] Final summary printed with run counts, overall counts, blockers, and next-command suggestion

## Avoid

- Looping past a blocker - the user decides whether to fix and resume
- Editing `spec.md` or `plan.md` from this workflow - they are upstream artifacts
- Skipping a task because its dependencies seem complete by description (read the actual `[x]` markers)
- Bulk-flipping status markers from `[~]` to `[x]` after the fact - status mutation belongs at the moment of the actual transition
- Re-running GATHER/DESIGN inside the delegated stack workflow - that defeats the purpose of spec-aware mode
- Silent stack guesses for ambiguous fullstack tasks - ask the user once, remember the answer
- Inventing an `ops`-type workflow - run those tasks inline using core atomics, do not pretend a missing workflow exists

## Notes

- The unit of progress is the task, not the file. A single task may touch many files; many tasks may touch the same file. The status marker is the source of truth for "done", not the diff.
- Re-invocation is the design - users should feel safe interrupting and resuming. The `[~]` marker is the breadcrumb that makes this safe.
- For fullstack features, alternate backend and frontend tasks by dependency, not by stack. The dependency graph in `tasks.md` already encodes the right order.
- If the same blocker shows up across multiple tasks, that is a signal the plan or spec is wrong - stop the implement loop and route the user to `task-spec-plan` or `task-spec-clarify`.
