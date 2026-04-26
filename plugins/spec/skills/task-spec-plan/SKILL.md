---
name: task-spec-plan
description: Planning phase of Spec-Driven Development. Reads `spec.md` (and `clarifications.md` if present), detects the project stack, and produces a structured `plan.md` covering architecture, data model, API contract, alternatives considered, NFR mapping, and risks. Speckit-aware - delegates to `/speckit.plan` when Spec Kit is installed.
metadata:
  category: spec
  tags: [spec, sdd, plan, architecture, design]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spec - Plan

Translates the **what** captured in `spec.md` into the **how**: a stack-aware implementation plan that downstream phases (`task-spec-tasks`, `task-spec-implement`) consume. Output is `plan.md`: architecture overview, data model, API contract, NFR mapping, alternatives considered, risks, and decisions worth recording as ADRs. The plan stops short of code - that is `task-spec-implement`'s job.

## When to Use

- After `task-spec-specify` (and ideally `task-spec-clarify`) for a feature whose `spec.md` exists
- When a feature's requirements are stable but no implementation plan exists yet
- When re-planning an existing feature whose plan has drifted from the current spec

**Not for:** Authoring requirements (use `task-spec-specify`), resolving spec ambiguity (use `task-spec-clarify`), generating tasks from an existing plan (use `task-spec-tasks`), writing code (use `task-spec-implement` or stack-specific `task-*-new`).

## Inputs

- The feature slug (required) - workflow reads `.specs/<slug>/spec.md` and (if present) `.specs/<slug>/clarifications.md`
- Optional `--replan` to regenerate when `plan.md` already exists; defaults to amend mode (preserve, append revision)

**Insufficient input handling:** If the slug has no `spec.md`, abort and recommend `task-spec-specify`. If the spec contains unresolved blockers (open questions tagged blocker/major), recommend `task-spec-clarify` first rather than planning on shaky ground.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

Capture the detected stack so subsequent steps and downstream atomics can adapt. If stack is unknown, proceed but flag the plan as `Stack Type: unknown` and avoid prescribing framework-specific structure.

### STEP 3 - Detect Mode

Use skill: speckit-detect

Capture `mode`. Subsequent steps branch on it.

### STEP 4 - Resolve Artifact Paths

Use skill: spec-artifact-paths

Capture `spec`, `clarifications`, and `plan` paths plus existence flags. If `spec.md` does not exist, abort with a clear message recommending `task-spec-specify`. If `plan.md` already exists, ask the user whether to **replace**, **amend** (preserve and add a revision section), or **abort** - default to amend.

### STEP 5 - Read the Spec

Read `spec.md` and (if present) `clarifications.md`. Extract:

- Problem statement and target users (frame the plan around them)
- User stories and acceptance criteria (each AC must be reachable from the plan)
- NFRs (performance, availability, scalability, security, compliance, observability, accessibility)
- Out-of-scope items (treat as hard fences during planning)
- Open questions still tagged blocker/major - if any remain, stop and recommend `task-spec-clarify` before continuing

Do not invent requirements not present in the spec. If planning surfaces a missing requirement, mark it as a **proposed spec amendment** in the output, do not edit the spec from this workflow.

### STEP 6 - Branch on Mode

#### Mode: speckit-installed

1. Pre-process: run `Use skill: tradeoff-analysis` against any non-trivial decision the spec already implies (e.g., sync vs async, monolith vs split). Run `Use skill: nfr-specification` to verify NFR coverage is plan-actionable. Bundle these as a brief Spec Kit can consume.
2. Delegate by instructing the user to run `/speckit.plan` (or invoke programmatically). Spec Kit owns artifact writing.
3. Post-process: read Spec Kit's plan output and run the **Plan-Spec Cross-Check** in STEP 8 over it. Surface gaps as suggestions; do not silently edit Spec Kit's output.
4. Skip to STEP 9.

#### Mode: standalone

Continue to STEP 7.

### STEP 7 - Compose the Plan

Build `plan.md` section by section. Reuse atomic skills rather than re-deriving their output.

| Plan Section                  | How to populate                                                                                                          |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Architecture overview**     | Describe components, boundaries, data ownership. Stack-aware. Reference any existing system the feature joins.           |
| **Data model**                | Entities, key fields, relationships, indexes. Migration approach if existing schema is touched.                          |
| **API contract**              | Endpoints, request/response shapes, error model. For frontend features: component contracts and state shape.             |
| **NFR mapping**               | Run `Use skill: nfr-specification` to verify each spec NFR has a concrete plan element satisfying it.                    |
| **Alternatives considered**   | Run `Use skill: tradeoff-analysis` for every significant decision (storage, sync/async, framework choice, ...).          |
| **Risks and mitigations**     | Failure modes, rollback strategy, data-loss surfaces. Cross-reference NFRs.                                              |
| **Decisions worth recording** | List candidate ADRs - actual ADR creation is the user's call (via `task-adr-create` if `architecture` plugin installed). |
| **Out-of-scope reaffirmed**   | Restate the spec's out-of-scope list verbatim - prevents downstream tasks from re-introducing what was excluded.         |

Rules during composition:

- Never specify implementation details below the contract level (no class names, no SQL syntax). Stay at the level a senior reviewer would sign off on.
- Every plan element must trace back to at least one acceptance criterion or NFR. Flag orphan elements.
- For polyglot or fullstack features, produce one plan with clearly labeled backend / frontend sections rather than two separate plans.
- If `architecture` plugin is installed and the feature is non-trivial, soft-suggest invoking `task-design-architecture` for a deeper design pass; do not run it automatically.

### STEP 8 - Plan-Spec Cross-Check

Before writing, verify:

- Every user story in `spec.md` is addressed by at least one architecture component or API endpoint
- Every acceptance criterion has a plan element it can be tested against
- Every NFR category has a corresponding plan section entry (or an explicit waiver with reason)
- No plan element touches an out-of-scope item
- No plan element conflicts with another (e.g., "stateless service" + "in-memory session cache")

For each gap, do **one** of:

- Add the missing plan element (preferred when the spec is clear)
- Stop and ask the user (when the gap implies a spec change)
- Mark as a **proposed spec amendment** in the plan's revisions section (when minor, defer to `task-spec-clarify`)

### STEP 9 - Write plan.md

Write to the resolved path using the template in **Output Format** below. In amend mode, preserve prior text and append a dated revision section; never delete prior content.

### STEP 10 - Summarize

Print a short summary to chat:

- Path written
- Sections populated, alternatives recorded, candidate ADRs flagged
- Mode used (speckit-installed or standalone)
- Any proposed spec amendments
- Suggested next command: `task-spec-tasks <slug>`

## Output Format

`plan.md` template (standalone mode; speckit-installed mode defers to Spec Kit's template):

```markdown
# Plan - <Feature Name>

- **Slug:** <slug>
- **Status:** draft | reviewed | tasked | implementing | complete
- **Stack:** <detected stack> (or `unknown`)
- **Created:** <YYYY-MM-DD>
- **Last updated:** <YYYY-MM-DD>

## Summary

<Two or three sentences: what is being built, the chosen shape at a high level, and why.>

## Architecture Overview

<Components, boundaries, data ownership. Diagram-friendly prose; ASCII diagram optional.>

## Data Model

<Entities, key fields, relationships, indexes, migration approach if schema is touched.>

## API Contract

<Endpoints / interfaces / component contracts. Include request/response shapes and error model.>

## NFR Mapping

| NFR Category | Spec Target         | Plan Element                           | Verification                 |
| ------------ | ------------------- | -------------------------------------- | ---------------------------- |
| Performance  | <e.g., p95 < 200ms> | <e.g., read-through cache on hot path> | <e.g., load test in Phase 4> |
| ...          | ...                 | ...                                    | ...                          |

## Alternatives Considered

(Populated by `tradeoff-analysis` per significant decision. Minimum one rejected alternative each.)

### Decision: <short title>

- **Context:** <one paragraph>
- **Chosen:** <option>
- **Rejected:** <option> - <why not>
- **Trade-off accepted:** <what is sacrificed>
- **Reversibility:** Easy | Moderate | Hard - <one-line reason>

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation | Rollback |
| ---- | ---------- | ------ | ---------- | -------- |
| ...  | ...        | ...    | ...        | ...      |

## Decisions Worth Recording (Candidate ADRs)

- **<title>** - <one-line rationale for capturing as an ADR>

(If the `architecture` plugin is installed, the user can run `task-adr-create` for any of the above.)

## Out of Scope (Reaffirmed)

<Verbatim from spec.md - downstream tasks must not re-introduce these.>

## Proposed Spec Amendments

<List any gaps surfaced during planning that imply the spec should be updated. Empty if none. Do NOT edit spec.md from this workflow.>

## Revisions

(Empty on first write. Amend mode appends dated entries; nothing is deleted.)

- <YYYY-MM-DD>: <summary of change> (by `task-spec-plan` | manual)
```

## Self-Check

- [ ] Loaded `behavioral-principles`, `stack-detect`, and `speckit-detect` before any other work
- [ ] Resolved artifact paths through `spec-artifact-paths` (no hardcoded `.specs/` strings)
- [ ] Aborted cleanly if `spec.md` did not exist or had unresolved blocker findings
- [ ] In speckit-installed mode, did not silently edit Spec Kit's output - cross-check surfaced as suggestions
- [ ] Every user story is addressed by at least one architecture component or API endpoint
- [ ] Every acceptance criterion has a plan element testable against it
- [ ] Every NFR category has a plan entry or explicit waiver with reason
- [ ] Every significant decision has an Alternatives Considered entry from `tradeoff-analysis`
- [ ] No plan element touches an out-of-scope item
- [ ] Proposed spec amendments listed (or empty section retained); spec.md not edited from this workflow
- [ ] Final summary printed with sections, alternatives, ADR candidates, and next-command suggestion

## Avoid

- Writing implementation code, class skeletons, or SQL syntax - those belong in `task-spec-implement`
- Invented requirements not in `spec.md` - propose amendments instead of silently inserting
- Editing `spec.md` from this workflow - amendments are proposals, not changes
- Skipping the Alternatives Considered section because "the choice was obvious" - record at least one rejected option
- Overwriting an existing `plan.md` without offering replace/amend/abort
- Auto-running `task-adr-create` or `task-design-architecture` - both are user-driven decisions

## Notes

- `task-spec-plan` is the bridge between intent (`spec.md`) and execution (`tasks.md`). Keep it stack-aware but contract-level.
- For fullstack features, prefer one plan with labeled sections over two parallel plans - downstream phases need a single source of truth.
- If the same decision shows up twice across features in the same repo, that is a hint to promote it to a project-level ADR via `task-adr-create` rather than duplicating the trade-off analysis in each plan.
