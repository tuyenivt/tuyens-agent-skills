---
name: task-spec-tasks
description: Tasking phase of Spec-Driven Development. Reads `plan.md` and produces `tasks.md` - a dependency-ordered, phase-grouped task list (data -> service -> API -> tests -> ops) consumable by `task-spec-implement`. Reuses core complexity-scan atomics directly. Speckit-aware - delegates to `/speckit.tasks` when Spec Kit is installed.
metadata:
  category: spec
  tags: [spec, sdd, tasks, breakdown, planning]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spec - Tasks

Decomposes a feature plan into an ordered task list that `task-spec-implement` (or stack-specific `task-*-new` workflows in `--spec` mode) can execute one task at a time. Output is `tasks.md`: phase-grouped tasks, dependency order, sizes, scope flags, and explicit traceability back to acceptance criteria. Each task is small enough to be implemented and reviewed independently.

## When to Use

- After `task-spec-plan` for a feature whose `plan.md` exists and is stable
- When re-tasking a feature whose plan has materially changed
- Before invoking `task-spec-implement` (the implement workflow consumes `tasks.md` directly)

**Not for:** Sprint-level scope breakdown across multiple features (use `task-scope-breakdown` from the `delivery` plugin if installed), feature requirement capture (use `task-spec-specify`), architecture or API design (use `task-spec-plan`), code generation (use `task-spec-implement`).

## Inputs

- The feature slug (required) - workflow reads `.specs/<slug>/plan.md` (and `spec.md` for traceability)
- Optional `--retask` to regenerate when `tasks.md` already exists; defaults to amend mode (preserve, append revision)

**Insufficient input handling:** If `plan.md` does not exist, abort and recommend `task-spec-plan`. If `spec.md` is missing (an unusual state), abort and recommend `task-spec-specify`. If the plan has unresolved **Proposed Spec Amendments**, surface them and ask the user whether to task against the current plan or pause for `task-spec-clarify`.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

Capture the detected stack so task naming and phase emphasis can adapt (e.g., a frontend-only feature has no DB phase).

### STEP 3 - Detect Mode

Use skill: speckit-detect

Capture `mode`. Subsequent steps branch on it.

### STEP 4 - Resolve Artifact Paths

Use skill: spec-artifact-paths

Capture `spec`, `plan`, and `tasks` paths plus existence flags. If `plan.md` does not exist, abort with a recommendation to run `task-spec-plan`. If `tasks.md` already exists, ask the user whether to **replace**, **amend**, or **abort** - default to amend.

### STEP 5 - Read Plan and Spec

Read `plan.md` end-to-end. Cross-reference `spec.md` to keep traceability:

- For every API contract entry in the plan, mark which acceptance criteria it satisfies
- For every data model change, identify the migration phase (expand, backfill, contract)
- For every NFR with a verification step, prepare a corresponding validation task
- Read the Out-of-Scope section - tasks must not re-introduce excluded items

### STEP 6 - Branch on Mode

#### Mode: speckit-installed

1. Pre-process: run the Complexity Signal Scan (STEP 7) so Spec Kit has the same hidden-cost coverage. Bundle the scan output as a brief.
2. Delegate by instructing the user to run `/speckit.tasks` (or invoke programmatically). Spec Kit owns artifact writing.
3. Post-process: read Spec Kit's task output and run the Traceability Check (STEP 9) over it. Surface gaps as suggestions; do not silently edit.
4. Skip to STEP 11.

#### Mode: standalone

Continue to STEP 7.

### STEP 7 - Complexity Signal Scan

Before generating any task, scan for hidden complexity that inflates effort or introduces risk. Reuse the same atomics that `task-scope-breakdown` (delivery plugin) reuses, so output quality is consistent regardless of which workflow the user invokes:

Use skill: review-change-risk
Use skill: review-blast-radius
Use skill: dependency-impact-analysis
Use skill: ops-backward-compatibility

Conditionally:

- Use skill: backend-db-migration - if the plan touches database schema
- Use skill: ops-feature-flags - if the plan flags high risk or gradual rollout
- Use skill: failure-propagation-analysis - if the plan introduces new cross-service calls

Capture which signals apply. The signals drive task size and reveal tasks that would otherwise be missed (migrations, observability, rollback verification, contract tests).

### STEP 8 - Generate Tasks

**Primary organization is by user story** so each story phase is an independently testable, shippable increment. Phase 1 (Setup) and Phase 2 (Foundational) are shared prerequisites; Phase 3+ is one phase per user story in priority order (P1, P2, P3...) from `spec.md`. The final phase is Polish / cross-cutting concerns. **MVP = User Story 1 alone.**

For each task:

- **ID:** `T<NNN>` - stable identifier referenced by `task-spec-implement` and progress markers
- **Story label:** `[US1]` / `[US2]` / ... - REQUIRED for tasks inside a user-story phase; NO label for Setup, Foundational, or Polish phases
- **Parallel marker:** `[P]` - include ONLY if the task touches different files than its peers and has no incomplete dependencies
- **Name:** Short, action-oriented (`Implement <X>`, `Add <Y>`, `Migrate <Z>`) - MUST include the exact target file path
- **Type:** `data` | `service` | `api` | `frontend` | `validation` | `ops`
- **Description:** One or two sentences - what to build, not how
- **Satisfies:** Acceptance criterion IDs from `spec.md` (e.g., `AC1, AC3`) or NFR category
- **Depends on:** Other task IDs (or `none`)
- **Size:** S (half day), M (1-2 days), L (3-5 days), XL (>5 days - flag for breakdown)
- **Scope:** `must-have` | `nice-to-have` | `risk-reduction`
- **Status:** `[ ]` (set by `task-spec-implement` as it progresses; always `[ ]` on first write)

**Checklist line format (the one-line rendering of each task block's header):**

```text
- [ ] T<NNN> [P?] [US?] <Name with file path>
```

Examples:

- `- [ ] T001 Create project structure per implementation plan` (Setup, no story label)
- `- [ ] T005 [P] Implement authentication middleware in src/middleware/auth.ts` (Foundational, parallelizable)
- `- [ ] T012 [P] [US1] Create User model in src/models/user.ts` (User Story 1, parallelizable)
- `- [ ] T014 [US1] Implement UserService in src/services/user_service.ts` (User Story 1, sequential)

Phase structure (omit empty phases):

| Phase                             | Typical contents                                                                                                                                   |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Setup**                      | Project init, dependency setup, lint/test scaffolding (no story label)                                                                             |
| **2. Foundational**               | Blocking prerequisites for ALL stories: migrations (expand phase), shared interfaces, feature-flag scaffolding (no story label)                    |
| **3+. User Story `<n>` (P`<n>`)** | One phase per story in priority order. Within: data → service → api/frontend → validation, all tagged `[USn]`. Each phase = independent increment. |
| **Final. Polish**                 | Cross-cutting: observability hooks, runbooks, perf tuning, deprecation removals, contract-phase migrations (no story label)                        |

Rules:

- Every story phase must be independently completable - do not let US2 silently depend on US3 work. Cross-story dependencies belong in Foundational.
- Every task must trace to a spec acceptance criterion or NFR via `Satisfies`. A task with no traceability is either a bug in the plan or scope creep - flag it, do not silently include it.
- XL tasks must be flagged with a recommendation to break down further.
- Tests are **tasks**, not an afterthought. Every api/service task should have a paired validation task in the same story phase.
- Mark `[P]` only when the task is truly safe to parallelize: different files AND no `Depends on` ahead of it in the queue.
- If `delivery` plugin is installed and the breakdown spans multiple sprints, soft-suggest invoking `task-scope-breakdown` for cross-feature sequencing - do not run it automatically.

### STEP 9 - Traceability Check

Verify before writing:

- Every acceptance criterion in `spec.md` is the `Satisfies` target of at least one task
- Every NFR with a verification step in `plan.md` has a matching validation task
- Every plan API endpoint has at least one implementation task and one validation task
- No task touches an out-of-scope item
- The dependency graph is acyclic and has at least one task with `Depends on: none` to start

For each gap:

- Add the missing task (preferred when plan is clear)
- Stop and ask the user (when the gap implies a plan change)
- Record as a **proposed plan amendment** in the output (when minor, the user can re-run `task-spec-plan` later)

### STEP 10 - Critical Path and MVP

Identify two things:

- **Critical path:** the longest chain of dependent tasks across the whole feature. Drives `task-spec-implement` ordering and reveals where to focus risk reduction.
- **MVP scope:** Setup + Foundational + User Story 1 (P1) only. This is the smallest shippable slice. Surface this explicitly in the summary so the user can choose to ship US1 before starting US2.

### STEP 11 - Write tasks.md and Summarize

Write to the resolved path using the template in **Output Format** below. In amend mode, preserve prior text and append a dated revision section; never delete prior content (especially completed-task markers).

Print a short summary:

- Path written
- Task count, breakdown by phase, XL count, must-have count
- Critical path
- Mode used (speckit-installed or standalone)
- Any proposed plan amendments
- Suggested next command: `task-spec-implement <slug>`

## Output Format

`tasks.md` template (standalone mode; speckit-installed mode defers to Spec Kit's template):

```markdown
# Tasks - <Feature Name>

- **Slug:** <slug>
- **Status:** draft | implementing | complete
- **Stack:** <detected stack> (or `unknown`)
- **Created:** <YYYY-MM-DD>
- **Last updated:** <YYYY-MM-DD>

## Complexity Signals Detected

- <Signal>: <impact in one line>
- ...

## Phase 1 - Setup

- [ ] T001 Create project structure per implementation plan
- [ ] T002 [P] Configure linting and formatting in tooling/

(detail blocks for each task follow the same format as story-phase tasks below)

## Phase 2 - Foundational

(blocking prerequisites for ALL user stories - migrations, shared interfaces, flag scaffolding)

- [ ] T005 Apply expand-phase migration in db/migrations/
- [ ] T006 [P] Add feature-flag scaffolding in src/flags/

## Phase 3 - User Story 1 (P1) - <Story Title>

**Story goal:** <one line - what value US1 delivers on its own>
**Independent test criteria:** <how to verify US1 works without US2/US3>

- [ ] T010 [P] [US1] Create User model in src/models/user.ts
- [ ] T011 [US1] Implement UserService in src/services/user_service.ts
- [ ] T012 [US1] Add validation tests for UserService in tests/services/user_service.test.ts

### T010 - Create User model

- **Type:** data
- **Description:** <what to build>
- **Satisfies:** AC1, AC3
- **Depends on:** T005
- **Size:** S | M | L | XL
- **Scope:** must-have | nice-to-have | risk-reduction
- **Status:** [ ]

### T011 - ...

## Phase 4 - User Story 2 (P2) - <Story Title>

**Story goal:** ...
**Independent test criteria:** ...

(same task block layout, all tagged `[US2]`)

## Phase N - Polish

(cross-cutting: observability, runbooks, contract-phase migrations, deprecation removals)

- [ ] T040 Wire structured logging in src/observability/

## Dependency Order

1. T001 (Setup, no deps)
2. T002 [P] (Setup, parallel with T001)
3. T005 (Foundational, requires T001)
4. T010 [US1] (requires T005)
5. ...

**Critical path:** T001 → T005 → T010 → T011 → T020 (estimated: M + L + M + S)

**MVP scope (ship US1 alone):** Phase 1 + Phase 2 + Phase 3 (User Story 1).

## Traceability Matrix

| Acceptance Criterion / NFR  | Tasks                |
| --------------------------- | -------------------- |
| AC1                         | T03, T07             |
| AC2                         | T05                  |
| NFR-Performance (p95 200ms) | T07, T11 (load test) |
| ...                         | ...                  |

## Proposed Plan Amendments

<Empty if none. Otherwise list gaps that imply plan.md should be updated.>

## Revisions

- <YYYY-MM-DD>: <summary of change> (by `task-spec-tasks` | `task-spec-implement` | manual)
```

## Self-Check

- [ ] Loaded `behavioral-principles`, `stack-detect`, and `speckit-detect` before any other work
- [ ] Resolved artifact paths through `spec-artifact-paths` (no hardcoded `.specs/` strings)
- [ ] Aborted cleanly if `plan.md` did not exist
- [ ] In speckit-installed mode, did not silently edit Spec Kit's output - traceability gaps surfaced as suggestions
- [ ] Complexity signal scan completed before task generation
- [ ] Tasks organized primarily by user story (Phase 3+ = one phase per US in priority order)
- [ ] Every story-phase task carries a `[USn]` label; Setup/Foundational/Polish tasks do not
- [ ] `[P]` markers applied only to tasks with no `Depends on` ahead of them and disjoint file scope
- [ ] Every task line includes an exact target file path
- [ ] Every task has ID, type, description, Satisfies, Depends on, Size, Scope, and Status fields
- [ ] Every acceptance criterion in `spec.md` has at least one task referencing it
- [ ] Every NFR verification step in `plan.md` has a matching validation task
- [ ] No task touches an out-of-scope item
- [ ] No story-phase task silently depends on another story's work (cross-story prereqs hoisted to Foundational)
- [ ] XL tasks flagged for further breakdown
- [ ] Dependency graph acyclic; critical path identified; MVP scope (Setup + Foundational + US1) called out
- [ ] Traceability matrix produced
- [ ] Final summary printed with task count, phase breakdown, critical path, MVP scope, next-command suggestion

## Avoid

- Generating implementation code in task descriptions - describe what to build, not how
- Tasks without `Satisfies` traceability - either fix the plan, ask the user, or drop the task
- Calendar-time estimates ("3 hours") instead of relative sizes (S/M/L/XL) unless explicitly requested
- Treating tests as a single trailing task - validation work belongs alongside the code it covers
- Editing `plan.md` from this workflow - amendments are proposals, not changes
- Auto-running `task-scope-breakdown` from delivery plugin - soft-suggest only
- Overwriting an existing `tasks.md` without offering replace/amend/abort, especially when tasks have non-`[ ]` Status markers (in-progress implementation work)

## Notes

- `tasks.md` is the unit of progress in `task-spec-implement`. Keep task IDs stable across revisions; renaming an ID breaks the implement workflow's resume semantics.
- For fullstack features, interleave backend and frontend tasks by dependency, not by stack. The user can still filter by `Type` if they want a single-stack pass.
- If the user has the `delivery` plugin installed and is sprint-planning across multiple specs, point them at `task-scope-breakdown` for the cross-feature view - this workflow is per-feature.
