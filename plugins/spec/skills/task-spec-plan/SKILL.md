---
name: task-spec-plan
description: SDD planning phase - reads spec.md, produces plan.md with architecture, data model, API contract, alternatives, NFR mapping, risks. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, plan, architecture, design]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Spec - Plan

Translates the **what** in `spec.md` into the **how**: a stack-aware implementation plan (`plan.md`) with architecture, data model, API contract, NFR mapping, alternatives, and risks. Stops short of code - that is `task-spec-implement`'s job.

## When to Use

After `task-spec-specify` (and ideally `task-spec-clarify`). To re-plan a feature whose plan has drifted from the spec. Not for: requirements (`task-spec-specify`), Q&A (`task-spec-clarify`), task generation (`task-spec-tasks`), code (`task-spec-implement`).

## Inputs

- `<slug>` (required). Aborts if `spec.md` missing or has unresolved blockers (recommends `task-spec-clarify`).
- `--replan` to regenerate when `plan.md` exists; default mode is amend (preserve, append revisions).

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

If unknown, proceed but flag the plan `Stack Type: unknown` and avoid framework-specific structure.

### STEP 3 - Detect Mode

Use skill: speckit-detect

### STEP 4 - Resolve Paths

Use skill: spec-artifact-paths

If `plan.md` exists, default to **amend**; offer replace/abort.

### STEP 5 - Read the Spec

Read `spec.md` and (if present) `clarifications.md`. Extract problem, users, stories, ACs, NFRs, out-of-scope, open questions. If any open question is tagged blocker/major, stop and recommend `task-spec-clarify`.

Do not invent requirements. Gaps surface as **Proposed Spec Amendments** in the output - never edit `spec.md`.

### STEP 6 - Branch on Mode

**speckit-installed:** pre-process by running `Use skill: tradeoff-analysis` over implied decisions and `Use skill: nfr-specification` to verify NFRs are plan-actionable. Bundle as a brief, instruct user to run `/speckit.plan`. Post-process by running the cross-check (STEP 9) and surface gaps as suggestions. Skip to STEP 11.

**standalone:** continue.

### STEP 7 - Compose the Plan

| Section                       | How to populate                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **Architecture overview**     | Components, boundaries, data ownership. Stack-aware. Reference any joined system.                                     |
| **Data model**                | Entities, key fields, relationships, indexes. Migration approach if existing schema is touched.                       |
| **API contract**              | Endpoints, request/response shapes, error model. Frontend: component contracts, state shape.                          |
| **NFR mapping**               | `Use skill: nfr-specification` - every spec NFR has a concrete plan element (or explicit waiver).                     |
| **Alternatives considered**   | `Use skill: tradeoff-analysis` for every significant decision. At least one rejected option each.                     |
| **Risks and mitigations**     | Failure modes, rollback strategy, data-loss surfaces. Cross-reference NFRs.                                           |
| **Decisions worth recording** | Candidate ADRs - actual creation is the user's call (via `task-adr-create` if `architecture` plugin installed).        |
| **Out of scope (reaffirmed)** | Restate spec's out-of-scope verbatim - prevents tasks from re-introducing exclusions.                                 |

Composition rules:
- Stay at contract level. No class names, no SQL syntax. Senior-reviewer sign-off level.
- Every plan element traces to at least one AC or NFR. Flag orphans.
- Fullstack: one plan with labeled backend/frontend sections (not two plans).
- If `architecture` plugin is installed and the feature is non-trivial, soft-suggest `task-design-architecture`. Do not auto-run.

### STEP 8 - NFR Feasibility Sanity Check

Catch arithmetically infeasible NFRs *before* tasks are written. Common failure: a budget that passes inspection but loses to physics (e.g., "p95 upload-to-visible < 2s for 5MB on 10Mbps" - raw transfer is `5MB * 8 / 10Mbps ≈ 4s`, infeasible regardless of plan).

For each quantitative NFR:

| NFR pattern                              | Sanity formula                                                            | If it fails                                                          |
| ---------------------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Upload/download latency                  | `file_bits / bandwidth_bps` is the floor                                  | Flag in **Proposed Spec Amendments**: server-side-only? typical files? bandwidth assumption? |
| Throughput (RPS, writes/sec)             | per-request cost (CPU ms, DB latency) * target vs single-instance capacity | Flag if multi-instance scaling not in plan, or per-request cost too high |
| Storage volume                           | `users * avg_size * retention` vs budget                                  | Flag if growth conflicts with retention/cost                         |
| Read latency under cache miss            | storage round-trip + serialization floor                                  | Flag if target is below the floor                                    |

Record each check in the NFR Mapping table's `Feasibility` column. **Do not silently weaken an infeasible NFR** - surface as a Proposed Spec Amendment.

### STEP 9 - Plan-Spec Cross-Check

Verify before writing:

- Every story addressed by an architecture component or API endpoint.
- Every AC has a plan element testable against it.
- Every NFR has a plan entry or explicit waiver.
- Every quantitative NFR survived STEP 8 (or its failure is recorded).
- No plan element touches out-of-scope.
- No plan element conflicts with another (e.g., "stateless service" + "in-memory session cache").

For each gap: add the missing element (preferred), stop and ask (if it implies a spec change), or mark as a Proposed Spec Amendment (minor, defer to clarify).

### STEP 10 - Write plan.md

Append-only in amend mode (new revision section, never delete prior content).

### STEP 11 - Summarize

Print path, sections populated, alternatives recorded, ADR candidates, mode, proposed amendments, next command (`task-spec-tasks <slug>`).

## Output Format

```markdown
# Plan - <Feature Name>

- **Slug:** <slug>
- **Status:** draft | reviewed | tasked | implementing | complete
- **Stack:** <detected stack> (or `unknown`)
- **Created:** <YYYY-MM-DD>
- **Last updated:** <YYYY-MM-DD>

## Summary
<Two or three sentences: what is being built, chosen shape, why.>

## Architecture Overview
<Components, boundaries, data ownership.>

## Data Model
<Entities, fields, relationships, indexes, migrations.>

## API Contract
<Endpoints / interfaces / component contracts. Request/response shapes, error model.>

## NFR Mapping

| NFR Category | Spec Target | Plan Element | Feasibility | Verification |
| ------------ | ----------- | ------------ | ----------- | ------------ |
| Performance  | p95 < 200ms | read-through cache on hot path | transfer floor 4s @ 10Mbps for 5MB - INFEASIBLE; flagged | load test in Phase 4 |

## Alternatives Considered

### Decision: <title>
- **Context:** <one paragraph>
- **Chosen:** <option>
- **Rejected:** <option> - <why not>
- **Trade-off accepted:** <what is sacrificed>
- **Reversibility:** Easy | Moderate | Hard - <reason>

## Risks and Mitigations
| Risk | Likelihood | Impact | Mitigation | Rollback |
| ---- | ---------- | ------ | ---------- | -------- |

## Decisions Worth Recording (Candidate ADRs)
- **<title>** - <one-line rationale>

## Out of Scope (Reaffirmed)
<Verbatim from spec.md.>

## Proposed Spec Amendments
<Gaps surfaced during planning. Empty if none. Do NOT edit spec.md from this workflow.>

## Revisions
- <YYYY-MM-DD>: <change> (by `task-spec-plan` | manual)
```

## Self-Check

- [ ] Loaded `behavioral-principles`, `stack-detect`, `speckit-detect` first
- [ ] Paths via `spec-artifact-paths`
- [ ] Aborted on missing `spec.md` or unresolved blockers
- [ ] In speckit mode, cross-check surfaced as suggestions (no silent edits)
- [ ] Every story addressed by an architecture component or API endpoint
- [ ] Every AC has a testable plan element
- [ ] Every NFR has a plan entry or explicit waiver
- [ ] Every quantitative NFR ran through STEP 8; infeasible budgets are Proposed Spec Amendments (not silently absorbed)
- [ ] Every significant decision has an Alternatives Considered entry from `tradeoff-analysis`
- [ ] No plan element touches out-of-scope
- [ ] `spec.md` not edited from this workflow
- [ ] Summary includes sections, alternatives, ADR candidates, next command

## Avoid

- Writing code, class skeletons, or SQL syntax (those belong in implement).
- Inventing requirements not in `spec.md` - propose amendments instead.
- Editing `spec.md`.
- Skipping Alternatives Considered because "the choice was obvious" - record at least one rejected option.
- Overwriting `plan.md` without offering replace/amend/abort.
- Auto-running `task-adr-create` or `task-design-architecture`.
- Silently absorbing an arithmetically infeasible NFR.
