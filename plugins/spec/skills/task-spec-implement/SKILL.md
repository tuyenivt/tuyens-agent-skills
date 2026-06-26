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

Drives `tasks.md` to working code one task at a time, delegating to stack workflows in `--spec` mode. Status mutates at every transition so the workflow is resumable: re-invocation reopens an in-progress `[~]` or picks the next ready `[ ]`.

## When to Use

After `task-spec-tasks`, or to resume an interrupted run.

**Inputs**

- `<slug>` (required) - reads `.specs/<slug>/{spec,plan,tasks}.md`.
- `--task <ID>` - run one task and exit.
- `--dry-run` - print the planned delegation, do not mutate. With `--task`, prints only that one.
- `--stop-after <ID>` - halt after that task completes.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

### STEP 3 - Mode Detection

Use skill: speckit-detect

### STEP 4 - Resolve Paths

Use skill: spec-artifact-paths

Abort if any of `spec.md`, `plan.md`, `tasks.md` is missing, naming the missing file and the upstream workflow that produces it.

### STEP 5 - Checklist Gate

If `.specs/<slug>/checklists/` exists, count `- [ ]` vs `- [x]/[X]` per file and render `Checklist | Total | Completed | Incomplete | Status` (PASS when Incomplete=0). Any FAIL halts the run and asks "Proceed with incomplete checklists?" - only an explicit yes continues.

### STEP 6 - Branch on Mode

**speckit-installed**: instruct the user to run `/speckit-implement`. Replace STEP 12 with: "Delegated to /speckit-implement; no state mutated here."

**standalone**: continue.

### STEP 7 - Pick Next Task

| Flag             | Pick                                                            |
| ---------------- | --------------------------------------------------------------- |
| `--task <ID>`    | That task. Error if missing or already `[x]`. If a different task is `[~]`, warn and continue; the resume breadcrumb survives. |
| (default)        | First `[~]`; else first `[ ]` whose `Deps:` are all `[x]`. |

If nothing is selectable, list unfinished deps and stop. If every task is `[x]`, exit. On `--dry-run`, print and exit.

### STEP 8 - Resolve Delegation Target

Stack-name -> workflow mapping:

| Stack         | Workflow                  |
| ------------- | ------------------------- |
| `java`        | `task-spring-implement`   |
| `kotlin`      | `task-kotlin-implement`   |
| `dotnet`      | `task-dotnet-implement`   |
| `python`      | `task-python-implement`   |
| `ruby`        | `task-rails-implement`    |
| `node`        | `task-node-implement`     |
| `go`          | `task-go-implement`       |
| `rust`        | `task-rust-implement`     |
| `php`         | `task-laravel-implement`  |
| `react`       | `task-react-implement`    |
| `vue`         | `task-vue-implement`      |
| `angular`     | `task-angular-implement`  |

By task `Type`:

| Type                        | Delegate                                                                              |
| --------------------------- | ------------------------------------------------------------------------------------- |
| `data` / `service` / `api`  | Backend workflow per the table above.                                                 |
| `frontend`                  | Frontend workflow per the table above.                                                |
| `validation`                | Same workflow as the task it validates: read its `Validates:` field (else last `Deps:` entry), look up that task's `Type` in this table. |
| `ops`                       | No workflow. Run inline with `ops-*` and per-stack atomics.                           |

For fullstack ambiguity, read `plan.md`'s API contract section. If still ambiguous, ask once and remember for the rest of the run. If the detected stack has no implement workflow, stop and surface the gap.

### STEP 9 - Mark In Progress

Mutate `tasks.md`: `[ ]` -> `[~]` (first run on this task) OR append a `resume` Revisions entry (re-run on an existing `[~]`). Never append a duplicate `[~]` entry. Bump `Last updated`.

Every Revisions entry (here and in STEP 11) uses this grammar:
```
<YYYY-MM-DD HH:MM>: T<NN> -> <marker> (<reason>) (by task-spec-implement)
```
Here `<marker>` is `[~]` and `<reason>` is `start` or `resume`.

### STEP 10 - Delegate

If `Type: ops`, execute inline using the listed `ops-*` skills; do not invoke a delegate workflow. Otherwise, invoke the chosen workflow with `--spec <slug>`, passing only the task's slice (description, `Satisfies`, `Deps`) and the relevant `plan.md` sections - not the full `tasks.md`. The delegate's spec-aware behavior is contracted by `spec-aware-preamble`. Surface clarifying questions to the user; do not answer for them.

### STEP 11 - Mark Outcome

| Outcome              | Action                                                                              |
| -------------------- | ----------------------------------------------------------------------------------- |
| Clean completion     | `[~]` -> `[x]`. Revisions reason `complete`.                                        |
| Blocked / errored    | Leave `[~]`. Revisions reason `blocked: <cause>`. Stop the loop.                    |
| Spec gap surfaced    | Leave `[~]`. Revisions reason `spec-gap`; append **Proposed Spec Amendment** below. Stop the loop. |
| User aborted         | Leave `[~]`. Revisions reason `aborted`.                                            |

Bump `Last updated` on every mutation. Never edit `spec.md` or `plan.md` (amendments are proposals only). Never add or reword downstream tasks.

Loop to STEP 7 unless `--task` ran or `--stop-after` matched.

### STEP 12 - Final Summary

```
Spec implement - <slug> (<mode>)
  This run:    completed=<n> in_progress=<n> blocked=<n>
  Overall:     [x]=<n> [~]=<n> [ ]=<n>
  Stack:       <stack-detect name>  (workflow: <task-*-implement>)
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

Example `tasks.md` row:
```
- [ ] T03 [US1] Add OrderRepository in src/repo/order_repo.<ext> - data, S, must-have. Satisfies AC1. Deps: T02. Validates: -
```

## Self-Check

- [ ] STEP 1-4: behavioral-principles, stack-detect, speckit-detect, paths loaded; aborted with upstream name if any artifact missing
- [ ] STEP 5: checklist gate ran; FAIL required explicit yes
- [ ] STEP 6: in speckit mode, delegated to `/speckit-implement` and skipped STEP 12
- [ ] STEP 7: picked `[~]` before `[ ]`; respected dependencies
- [ ] STEP 8: resolved a real workflow via the stack table, or ran inline for `ops`
- [ ] STEP 9: marked `[~]` (or appended `resume` entry on re-run; no duplicate `[~]`)
- [ ] STEP 10: passed `--spec <slug>` and only the task's slice; ops ran inline
- [ ] STEP 11: marked `[x]` only on clean completion; did not edit spec/plan or reword tasks
- [ ] STEP 12: summary includes counts, blockers, spec gaps, next command

## Avoid

- Skipping `[~]` tasks when resuming.
- Editing `spec.md`, `plan.md`, or downstream task descriptions.
- Bulk-flipping status after the fact (mutate at the transition).
- Re-running GATHER/DESIGN inside the delegate.
- Silent guesses for fullstack ambiguity.
- Inventing a workflow when the stack has none.
