---
name: task-spec-tasks
description: SDD tasking phase - reads plan.md, produces dependency-ordered, phase-grouped tasks.md (data / service / API / tests / ops). Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, tasks, breakdown, planning]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Spec - Tasks

Decomposes a feature plan into an ordered task list that `task-spec-implement` (or stack `task-*-new` workflows in `--spec` mode) can execute one task at a time. Output is `tasks.md`: phase-grouped, dependency-ordered, sized, scope-flagged, with explicit traceability back to ACs/NFRs.

## When to Use

After `task-spec-plan` (plan must be stable), to re-task a feature whose plan changed materially, or before `task-spec-implement`. Not for: cross-feature sprint planning (`task-breakdown-story` from `delivery`), requirements (`task-spec-specify`), architecture (`task-spec-plan`), code (`task-spec-implement`).

## Inputs

- `<slug>` (required). Aborts if `plan.md` or `spec.md` missing (recommends the upstream workflow). If plan has unresolved Proposed Spec Amendments, ask whether to task against current plan or pause for `task-spec-clarify`.
- `--retask` to regenerate when `tasks.md` exists; default mode is amend.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

### STEP 3 - Detect Mode

Use skill: speckit-detect

### STEP 4 - Resolve Paths

Use skill: spec-artifact-paths

If `tasks.md` exists, default to **amend**; offer replace/abort. Replacing a tasks.md with non-`[ ]` Status markers needs explicit confirmation.

### STEP 5 - Read Plan + Spec

Map plan to spec for traceability:
- Each plan API contract entry -> ACs it satisfies.
- Each data-model change -> migration phase (expand / backfill / contract).
- Each NFR with verification -> a validation task.
- Out-of-scope -> hard fence; tasks must not re-introduce.

### STEP 6 - Branch on Mode

**speckit-installed:** run STEP 7 first so Spec Kit gets the same complexity coverage. Bundle as a brief, instruct user to run `/speckit-tasks` (any `before_tasks` / `after_tasks` hooks registered in `.specify/extensions.yml` will fire as part of that call - do not bypass them). Post-process by running STEP 9 traceability check; surface gaps as suggestions, no silent edits. Skip to STEP 11.

**standalone:** continue.

### STEP 7 - Complexity Signal Scan

Reuse the same atomics that `task-breakdown-story` uses, so output quality is consistent across workflows:

Use skill: review-change-risk
Use skill: review-blast-radius
Use skill: ops-backward-compatibility

Inline scans:
- **Dependency impact** - for each plan element, list upstream callers and downstream services. Flag deployment ordering (consumer-before-producer for new fields; producer-before-consumer for removals) and shared-library bumps that cross service boundaries.
- **Failure propagation** (if plan adds cross-service calls) - for each new call edge, name the upstream blast radius on timeout/error, the fallback (cached value / degraded response / fail-closed), and whether a circuit breaker or bulkhead is required.

Conditional:
- `backend-db-migration` if plan touches schema.
- **Feature flags** (if high risk or gradual rollout) - add a flag with: ramp plan (% buckets or cohorts), kill-switch path, success metric, and cleanup task (remove flag + dead branch after full rollout). No indefinite flags.

Signals drive task size and surface tasks otherwise missed (migrations, observability, rollback verification, contract tests).

### STEP 8 - Generate Tasks

**Organize by user story.** Phase 1 (Setup) and Phase 2 (Foundational) are shared prerequisites; Phase 3+ is one phase per story in priority order; final phase is Polish. **MVP = User Story 1 alone.**

Per task:
- **ID:** `T<NNN>` - stable identifier.
- **Story label:** `[US1]`/`[US2]`/... required for story-phase tasks; not used for Setup/Foundational/Polish.
- **Parallel marker:** `[P]` ONLY if disjoint files AND no incomplete dependencies.
- **Name:** action-oriented, with the **exact target file path**.
- **Type:** `data | service | api | frontend | validation | ops`.
- **Size:** S / M / L / XL (relative t-shirt; convert to time only if asked). XL flags for further breakdown.
- **Scope:** `must-have | nice-to-have | risk-reduction`.
- **Satisfies:** AC IDs or NFR category.
- **Depends on:** task IDs or `none`.
- **Status:** `[ ]` on first write.

**One-line format (the only rendering - never duplicate as a detail block):**

```text
- [ ] T<NNN> [P?] [US?] <Name with file path> - <type>, <size>, <scope>. Satisfies <ACs/NFRs>. Deps: <ids or none>.
  <One sentence ONLY when name + path do not convey what to build.>
```

The most common bloat in spec-driven `tasks.md` files is duplicating each task as a `### T<NNN>` heading block repeating the same fields - **do not** do this; the one-line form carries every required field.

Examples:
```
- [ ] T001 Create project structure per implementation plan - ops, S, must-have. Satisfies NFR-Setup. Deps: none.
- [ ] T005 [P] Implement auth middleware in src/middleware/auth.ts - service, M, must-have. Satisfies AC5. Deps: T001.
- [ ] T012 [P] [US1] Create User model in src/models/user.ts - data, S, must-have. Satisfies AC1, AC3. Deps: T005.
- [ ] T014 [US1] Implement UserService in src/services/user_service.ts - service, M, must-have. Satisfies AC1, AC4. Deps: T012.
  Coordinates validation, persistence, and external storage calls; thin wrapper over the repository.
```

**Phases (omit empty):**

| Phase                       | Contents                                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **1. Setup**                | Project init, dependency setup, lint/test scaffolding (no story label).                                                   |
| **2. Foundational**         | Blocking for ALL stories: migrations (expand), shared interfaces, feature-flag scaffolding (no story label).              |
| **3+. User Story `<n>`**    | One phase per story (P1, P2, ...). Within: data -> service -> api/frontend -> validation, all `[USn]`. Independent increment. |
| **Final. Polish**           | Cross-cutting: observability, runbooks, perf tuning, deprecation removals, contract-phase migrations.                     |

Rules:
- Each story phase is independently completable. Cross-story prereqs hoist to Foundational.
- Every task traces to an AC or NFR via `Satisfies`. No traceability -> plan bug or scope creep; flag, do not silently include.
- Tests are tasks, not afterthoughts. Each api/service task gets a paired `validation` task in the same phase.
- If `delivery` plugin is installed and the breakdown spans sprints, soft-suggest `task-breakdown-story`. Do not auto-run.

### STEP 9 - Traceability Check

Verify before writing:
- Every AC is `Satisfies`-targeted by at least one task.
- Every NFR with a verification has a matching `validation` task.
- Every plan API endpoint has implementation + validation tasks.
- No task touches out-of-scope.
- Dependency graph is acyclic; at least one task has `Depends on: none`.

For each gap: add the missing task (preferred), stop and ask (if it implies a plan change), or record as Proposed Plan Amendment.

### STEP 10 - Critical Path and MVP

- **Critical path:** longest dependent chain across the whole feature. Drives implement ordering and risk focus.
- **MVP:** Setup + Foundational + US1. Surface explicitly so the user can ship US1 before starting US2.

### STEP 11 - Write tasks.md and Summarize

Append-only in amend mode (preserve completed-task markers). Print: path, task count, phase breakdown, XL count, must-have count, critical path, mode, proposed plan amendments, next command (`task-spec-implement <slug>`).

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
- [ ] T002 [P] Configure linting and formatting in tooling/ - ops, S, must-have. Satisfies NFR-Setup. Deps: none.

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
- [ ] T012 [US1] Add validation tests for UserService in tests/services/user_service.test.ts - validation, S, must-have. Satisfies AC1, AC4. Deps: T011.

## Phase 4 - User Story 2 (P2) - <Story Title>
(same one-line layout, all `[US2]`)

## Phase N - Polish
(cross-cutting: observability, runbooks, contract-phase migrations, deprecations)

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

- [ ] Loaded `behavioral-principles`, `stack-detect`, `speckit-detect` first
- [ ] Aborted on missing `plan.md`/`spec.md`
- [ ] In speckit mode, traceability gaps surfaced (no silent edits)
- [ ] Complexity scan ran before task generation
- [ ] Tasks organized by user story (Phase 3+ = one phase per US)
- [ ] `[USn]` labels on story-phase tasks only; not on Setup/Foundational/Polish
- [ ] `[P]` only when disjoint files + no `Depends on` ahead
- [ ] Every task line carries the exact target file path
- [ ] Every task has all metadata fields (type, size, scope, satisfies, deps, status)
- [ ] Every AC has >=1 task; every NFR verification has a validation task
- [ ] No task touches out-of-scope; no story task depends on another story (hoist to Foundational)
- [ ] XL tasks flagged for breakdown
- [ ] Dependency graph acyclic; critical path + MVP scope identified
- [ ] Traceability matrix written
- [ ] Summary includes counts, critical path, MVP, next command

## Avoid

- Implementation code in task descriptions (describe what, not how).
- Duplicating each task as one-line checkbox AND `### T<NNN>` detail block - the most common reason `tasks.md` becomes unreadable.
- Tasks without `Satisfies` traceability.
- Calendar-time estimates instead of S/M/L/XL unless asked.
- Treating tests as a single trailing task - validation pairs with the code it covers.
- Editing `plan.md` from this workflow.
- Auto-running `task-breakdown-story` (soft-suggest only).
- Overwriting `tasks.md` without offering replace/amend/abort, especially when non-`[ ]` markers exist.
