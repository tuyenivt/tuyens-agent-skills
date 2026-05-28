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

Decompose `plan.md` into an ordered `tasks.md` that `task-spec-implement` (or stack `task-*-implement` in `--spec` mode) executes one task at a time.

## When to Use

After `task-spec-plan`, or before `task-spec-implement`. Requires `<slug>`; abort if `plan.md` or `spec.md` is missing. If `plan.md` carries unresolved Proposed Spec Amendments, ask: task against current plan or pause for `task-spec-clarify`. Pass `--retask` to regenerate; default is amend.

Not for sprint planning (`task-breakdown-story` in `delivery`), requirements, architecture, or code.

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

Read `plan.md`'s Risks and Alternatives sections first to avoid duplicate complexity analysis in STEP 5. Map:
- Plan API contract entry -> ACs it satisfies.
- Data-model change -> migration phase (expand / backfill / contract).
- NFR with verification -> validation task.
- Spec out-of-scope -> hard fence.

If `analysis.md` exists for this slug, read its Traceability Matrix; reuse it and flag deltas only.

### STEP 5 - Complexity Signal Scan

Skip atomics whose findings `plan.md` already recorded (rerun only if plan is >7 days old or marked stale).

Use skill: review-change-risk
Use skill: review-blast-radius
Use skill: dependency-impact-analysis
Use skill: ops-backward-compatibility

Conditional:
- Use skill: backend-db-migration (plan touches schema)
- Use skill: ops-feature-flags (high risk or gradual rollout)

### STEP 6 - Mode Branch

- **speckit-installed**: bundle STEP 5 signals as a brief, instruct user to run `/speckit-tasks`. After upstream runs, perform STEP 9 (traceability gate) against Spec Kit's `tasks.md` and surface gaps as suggestions. Skip to STEP 10.
- **standalone**: continue to STEP 7.

### STEP 7 - Generate Tasks

Organize by user story:

| Phase                       | Contents                                                                                                  | Story label |
| --------------------------- | --------------------------------------------------------------------------------------------------------- | ----------- |
| **1. Setup**                | Project init, deps, lint/test scaffolding                                                                 | none        |
| **2. Foundational**         | Blocks ALL stories: expand-phase migrations, shared interfaces, feature-flag scaffolding                  | none        |
| **3+. User Story `<n>`**    | One phase per story (P1, P2, ...). Order within: data -> service -> api/frontend -> validation. Independent. | `[USn]`     |
| **Final. Polish**           | Cross-cutting: observability, runbooks, perf tuning, contract-phase migrations, flag cleanup              | none        |

MVP = Setup + Foundational + US1. A prerequisite hoists to Foundational iff >=2 story phases import or extend it; single-story prerequisites stay in that story phase.

Per task (one-line format - the ONLY rendering):

```
- [ ] T<NNN> [P?] [US?] <Name with exact target file path> - <type>, <size>, <scope>. Satisfies <ACs/NFRs>. Deps: <ids|none>.
  <Optional single sentence; only if name+path do not convey what to build.>
```

Fields:
- **type**: `data | service | api | frontend | validation | ops`
- **size**: `S | M | L | XL` (relative within this feature; XL flags for further breakdown)
- **scope**: `must-have` (blocks an AC) | `nice-to-have` (improves UX/perf without blocking an AC) | `risk-reduction` (mitigates a risk/NFR, e.g., load test, rollback drill)
- **`[P]`**: target files do not overlap with any other `[P]` task in the same phase, AND all Deps are in earlier phases (not same-phase peers)

Rules:
- Every task carries `Satisfies` (AC IDs or `NFR-<category>`). No traceability -> plan bug or scope creep; flag.
- Validation tasks pair with the code they cover, in the same phase.
- If `delivery` is installed AND the breakdown exceeds one sprint (>10 must-have tasks or >2 story phases sized L+), STOP and recommend the user run `task-breakdown-story` first; this workflow consumes that output.

### STEP 8 - Critical Path and MVP

- **Critical path**: longest dependent chain.
- **MVP scope**: Setup + Foundational + US1.

### STEP 9 - Traceability Gate

- Every AC is `Satisfies`-targeted by >=1 task.
- Every NFR with a verification has a matching validation task.
- Every plan endpoint has implementation + validation tasks.
- No task touches out-of-scope.
- Dependency graph is acyclic; >=1 task has `Deps: none`.

Fix gaps by: adding the missing task (preferred), stopping to ask (if it implies a plan change), or recording a Proposed Plan Amendment.

### STEP 10 - Write tasks.md and Summarize

Amend mode is append-only and preserves completed-task markers. Self-Check covers what to print.

## Output Format

```markdown
# Tasks - <Feature Name>

- **Slug:** <slug>
- **Stack:** <detected stack> (or `unknown`)
- **Created:** <YYYY-MM-DD>
- **Last updated:** <YYYY-MM-DD>

## Complexity Signals Detected
- <Signal>: <impact>

## Phase 1 - Setup
- [ ] T001 Create project structure per implementation plan - ops, S, must-have. Satisfies bootstrap (no AC). Deps: none.

## Phase 2 - Foundational
- [ ] T005 Apply expand-phase migration in db/migrations/2026XX_add_users.sql - data, S, must-have. Satisfies AC1, AC3. Deps: T001.

## Phase 3 - User Story 1 (P1) - <Story Title>
**Story goal:** <one line>
**Independent test criteria:** <how to verify US1 alone>

- [ ] T010 [P] [US1] Create User model in src/models/user.<ext> - data, S, must-have. Satisfies AC1, AC3. Deps: T005.
- [ ] T011 [US1] Implement UserService in src/services/user_service.<ext> - service, M, must-have. Satisfies AC1, AC4. Deps: T010.
      Coordinates validation, persistence, and password hashing.

## Phase N - Polish
- [ ] T040 [P] Add p95 latency load test in tests/perf/checkout_load.<ext> - validation, M, risk-reduction. Satisfies NFR-performance. Deps: T020.

**Critical path:** T001 -> T005 -> T010 -> T011 -> T020
**MVP scope:** Phase 1 + Phase 2 + Phase 3 (US1).

## Traceability Matrix
| AC / NFR                    | Tasks                |
| --------------------------- | -------------------- |
| AC1                         | T010, T011           |
| NFR-performance (p95 200ms) | T011, T040           |

## Proposed Plan Amendments
<Empty if none.>

## Revisions
- <YYYY-MM-DD>: <change> (by `task-spec-tasks` | `task-spec-implement` | manual)
```

## Self-Check

- [ ] STEP 1-3: behavioral-principles, stack-detect, mode, paths loaded; replace/amend confirmed if `tasks.md` exists
- [ ] STEP 4: aborted on missing plan/spec; traceability map built; reused `analysis.md` matrix if present
- [ ] STEP 5: skipped atomics already recorded in plan; conditional atomics ran when conditions matched
- [ ] STEP 6: in speckit mode, gaps surfaced as suggestions only
- [ ] STEP 7: phases by story; `[USn]` only on story-phase tasks; `[P]` per disjoint-files rule; every task has file path and all fields; validation pairs with code; XL flagged
- [ ] STEP 8: critical path and MVP scope identified
- [ ] STEP 9: every AC covered; every NFR validation present; graph acyclic; no out-of-scope touched
- [ ] STEP 10: amend-mode append-only; summary prints task count, phase breakdown, XL count, must-have count, critical path, mode, amendments, next command (`task-spec-implement <slug>`)

## Avoid

- Duplicating each task as one-line checkbox AND a `### T<NNN>` detail block.
- Implementation code in task descriptions (what, not how).
- Tasks without `Satisfies` traceability or without an exact file path.
- Fabricating NFR IDs (e.g., `NFR-Setup`) when none exist in spec.
- Treating tests as a single trailing task.
- Editing `plan.md` from this workflow.
- Auto-running `task-breakdown-story`.
