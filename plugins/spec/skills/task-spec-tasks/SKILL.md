---
name: task-spec-tasks
description: SDD tasking - read plan.md and emit phase-grouped, dependency-ordered tasks.md (data/service/api/validation/ops) with AC traceability. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, tasks, breakdown, planning]
  type: workflow
user-invocable: true
---

# Spec - Tasks

Decompose a stable `plan.md` into an ordered `tasks.md` that `task-spec-implement` (or stack `task-*` workflows in `--spec` mode) executes one task at a time.

## When to Use

After `task-spec-plan`, to re-task a plan that changed materially, or before `task-spec-implement`. Requires `<slug>`; abort with the upstream recommendation if `plan.md` or `spec.md` is missing. If plan carries unresolved Proposed Spec Amendments, ask: task against current plan or pause for `task-spec-clarify`. Pass `--retask` to regenerate; default is amend.

Not for: sprint planning (`task-breakdown-story` in `delivery`), requirements (`task-spec-specify`), architecture (`task-spec-plan`), code (`task-spec-implement`).

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

### STEP 3 - Detect Mode and Resolve Paths

Use skill: speckit-detect
Use skill: spec-artifact-paths

If `tasks.md` exists, default to amend; offer replace/abort. Replacing a `tasks.md` containing non-`[ ]` Status markers requires explicit confirmation.

### STEP 4 - Read Plan and Spec; Build Traceability Map

Map plan -> spec:
- Plan API contract entry -> ACs it satisfies.
- Data-model change -> migration phase (expand / backfill / contract).
- NFR with verification -> validation task.
- Spec out-of-scope -> hard fence; tasks must not re-introduce.

### STEP 5 - Complexity Signal Scan

Use skill: review-change-risk
Use skill: review-blast-radius
Use skill: dependency-impact-analysis
Use skill: ops-backward-compatibility

Conditional:
- Use skill: backend-db-migration (if plan touches schema)
- Use skill: ops-feature-flags (if high risk or gradual rollout)

Signals drive task size and surface tasks otherwise missed (migrations, observability, rollback verification, contract tests).

### STEP 6 - Mode Branch

- **speckit-installed:** bundle the STEP 5 signals as a brief, instruct user to run `/speckit-tasks` (any `before_tasks`/`after_tasks` hooks in `.specify/extensions.yml` fire as part of that call; do not bypass). After upstream runs, perform STEP 7 (traceability) against Spec Kit's `tasks.md` and surface gaps as suggestions; no silent edits. Skip to STEP 9.
- **standalone:** continue to STEP 7.

### STEP 7 - Generate Tasks

Organize by user story:

| Phase                       | Contents                                                                                                  | Story label |
| --------------------------- | --------------------------------------------------------------------------------------------------------- | ----------- |
| **1. Setup**                | Project init, deps, lint/test scaffolding                                                                 | none        |
| **2. Foundational**         | Blocks ALL stories: expand-phase migrations, shared interfaces, feature-flag scaffolding                  | none        |
| **3+. User Story `<n>`**    | One phase per story (P1, P2, ...). Order within: data -> service -> api/frontend -> validation. Independent. | `[USn]`     |
| **Final. Polish**           | Cross-cutting: observability, runbooks, perf tuning, contract-phase migrations, flag cleanup              | none        |

MVP = Setup + Foundational + US1. Cross-story prerequisites hoist to Foundational. Each story phase must be independently completable.

Per task (one-line format - the ONLY rendering; never duplicate as a `### T<NNN>` detail block):

```
- [ ] T<NNN> [P?] [US?] <Name with exact target file path> - <type>, <size>, <scope>. Satisfies <ACs/NFRs>. Deps: <ids|none>.
  <Optional single sentence; only if name+path do not convey what to build.>
```

Fields:
- **type:** `data | service | api | frontend | validation | ops`
- **size:** `S | M | L | XL` (relative; XL flags for further breakdown)
- **scope:** `must-have | nice-to-have | risk-reduction`
- **`[P]`:** parallel-safe (disjoint files AND no incomplete dependencies)

Rules:
- Every task carries `Satisfies` (AC IDs or NFR category). No traceability -> plan bug or scope creep; flag, do not silently include.
- Validation tasks pair with the code they cover, in the same phase. Tests are not a trailing afterthought.
- If `delivery` is installed and the breakdown spans sprints, soft-suggest `task-breakdown-story`; do not auto-run.

### STEP 8 - Critical Path and MVP

- **Critical path:** longest dependent chain across the feature.
- **MVP scope:** explicit Setup + Foundational + US1 so the user can ship before starting US2.

### STEP 9 - Traceability Gate

Before writing, verify and resolve:
- Every AC is `Satisfies`-targeted by >=1 task.
- Every NFR with a verification has a matching validation task.
- Every plan endpoint has implementation + validation tasks.
- No task touches out-of-scope.
- Dependency graph is acyclic; >=1 task has `Deps: none`.

Fix gaps by: adding the missing task (preferred), stopping to ask (if it implies a plan change), or recording a Proposed Plan Amendment.

### STEP 10 - Write tasks.md and Summarize

Amend mode is append-only and preserves completed-task markers. Print: path, task count, phase breakdown, XL count, must-have count, critical path, mode, proposed plan amendments, next command (`task-spec-implement <slug>`).

## Output Format

```markdown
# Tasks - <Feature Name>

- **Slug:** <slug>
- **Status:** draft | implementing | complete
- **Stack:** <detected stack> (or `unknown`)
- **Created:** <YYYY-MM-DD>
- **Last updated:** <YYYY-MM-DD>

## Complexity Signals Detected
- <Signal>: <impact>

## Phase 1 - Setup
- [ ] T001 Create project structure per implementation plan - ops, S, must-have. Satisfies NFR-Setup. Deps: none.
- [ ] T002 [P] Configure linting in tooling/ - ops, S, must-have. Satisfies NFR-Setup. Deps: none.

## Phase 2 - Foundational
(blocking prerequisites for ALL user stories)
- [ ] T005 Apply expand-phase migration in db/migrations/2026XX_add_users.sql - data, S, must-have. Satisfies AC1, AC3. Deps: T001.
- [ ] T006 [P] Add feature-flag scaffolding in src/flags/ - ops, S, risk-reduction. Satisfies NFR-Rollout. Deps: T001.

## Phase 3 - User Story 1 (P1) - <Story Title>
**Story goal:** <one line>
**Independent test criteria:** <how to verify US1 alone>

- [ ] T010 [P] [US1] Create User model in src/models/user.ts - data, S, must-have. Satisfies AC1, AC3. Deps: T005.
- [ ] T011 [US1] Implement UserService in src/services/user_service.ts - service, M, must-have. Satisfies AC1, AC4. Deps: T010.
      Coordinates validation, persistence, and password hashing.
- [ ] T012 [US1] Add validation tests in tests/services/user_service.test.ts - validation, S, must-have. Satisfies AC1, AC4. Deps: T011.

## Phase N - Polish
(observability, runbooks, contract-phase migrations, deprecations, flag cleanup)

## Dependency Order
1. T001 (Setup, no deps)
2. T002 [P] (parallel with T001)
3. T005 (requires T001)
...

**Critical path:** T001 -> T005 -> T010 -> T011 -> T020
**MVP scope:** Phase 1 + Phase 2 + Phase 3 (US1).

## Traceability Matrix
| AC / NFR                    | Tasks                |
| --------------------------- | -------------------- |
| AC1                         | T010, T011           |
| NFR-Performance (p95 200ms) | T011, T020 (load)    |

## Proposed Plan Amendments
<Empty if none.>

## Revisions
- <YYYY-MM-DD>: <change> (by `task-spec-tasks` | `task-spec-implement` | manual)
```

## Self-Check

- [ ] STEP 1-2: behavioral-principles and stack-detect loaded
- [ ] STEP 3: speckit-detect + spec-artifact-paths resolved; replace/amend confirmed if tasks.md exists
- [ ] STEP 4: aborted on missing plan.md/spec.md; traceability map built; out-of-scope fenced
- [ ] STEP 5: complexity atomics ran (migration/flag atomics ran when conditions matched)
- [ ] STEP 6: in speckit mode, gaps surfaced as suggestions only - no silent edits
- [ ] STEP 7: phases organized by story; `[USn]` only on story-phase tasks; `[P]` only on disjoint-file + no-dep-ahead tasks; every task has file path and all fields; validation pairs with code; XL flagged
- [ ] STEP 8: critical path and MVP scope identified
- [ ] STEP 9: every AC has >=1 task; every NFR verification has validation task; graph acyclic; no out-of-scope touched; no cross-story deps (hoist to Foundational)
- [ ] STEP 10: amend-mode append-only; summary prints counts, critical path, MVP, next command

## Avoid

- Duplicating each task as one-line checkbox AND `### T<NNN>` detail block.
- Implementation code in task descriptions (what, not how).
- Tasks without `Satisfies` traceability or without an exact file path.
- Calendar-time estimates instead of S/M/L/XL unless asked.
- Treating tests as a single trailing task.
- Editing `plan.md` from this workflow.
- Auto-running `task-breakdown-story` (soft-suggest only).
- Overwriting a `tasks.md` containing non-`[ ]` markers without explicit confirmation.
