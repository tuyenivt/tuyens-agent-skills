---
name: task-spec-specify
description: SDD foundation phase - elicit feature requirements (problem, users, stories, AC, NFRs) and write spec.md to .specs/<slug>/. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, requirements, specification, foundation]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Spec - Specify

Captures the **what** and **why** of a feature as a persistent artifact (`spec.md`) before any architecture work. Downstream phases (`task-spec-clarify/plan/tasks/implement`) consume it; stack workflows can also consume it via `--spec`.

## When to Use

For new features, re-specs of drifted features, or producing a portable handoff artifact. Not for: technical design (`task-spec-plan`), system architecture or API design (`task-design-architecture`), bug reports (`task-code-debug`).

## Inputs

- Feature name or short description (required). If only a one-word name with no context, ask for the problem and primary user before proceeding. Do not fabricate stories.
- Optional explicit slug override.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

If `spec.md` already exists, ask: **replace**, **amend** (preserve, append revision), or **abort**.

### STEP 4 - Branch on Mode

**speckit-installed:** consolidate context into a brief, instruct the user to run `/speckit-specify <brief>` (any `before_specify` / `after_specify` hooks registered in `.specify/extensions.yml` will fire as part of that call - do not bypass them). After the user runs it, read the resolved feature directory from `.specify/feature.json` (Spec Kit writes it there) and load the produced `spec.md`. Post-process by running `Use skill: nfr-specification` and present any missing NFR coverage as additions for user merge - do not silently edit Spec Kit output. Skip to STEP 7.

**standalone:** continue.

### STEP 5 - Elicit Requirements

Ask only what is not already in context. Cover:

| Section                 | What to elicit                                                                                                                                  |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Problem statement**   | User-facing pain or business gap. Plain language, no implementation hints.                                                                      |
| **Target users**        | Primary and (if any) secondary roles. Internal/external, authn/anon.                                                                            |
| **User stories**        | "As a <role>, I want <capability>, so that <value>." One per outcome.                                                                           |
| **Acceptance criteria** | Falsifiable, measurable. Every story has at least one AC.                                                                                       |
| **Non-functional**      | Run `Use skill: nfr-specification`. Include only categories with a real requirement; **omit** categories that do not apply (no placeholders).   |
| **Out of scope**        | Explicit non-goals. Empty out-of-scope is almost always wrong.                                                                                  |
| **Open questions**      | Items the user could not answer; flagged for `task-spec-clarify`.                                                                               |

Rules:
- Surface ambiguity rather than guess. "Fast" -> ask for a number.
- Never invent stories the user did not ask for.
- Conflicting answers ("must work offline" + "real-time collaboration") -> stop, surface.
- If the domain implies a regulatory standard (payments, health, PII), name it and ask.

### STEP 6 - Write spec.md

Write the document using the template in **Output Format**. Set the declared name to the slug input.

For materially-uncertain answers, embed inline `[NEEDS CLARIFICATION: <question>]` markers. **Cap at 3 markers**, priority: scope > security/privacy > UX > technical detail. Lower-priority candidates go in `Open Questions` (unbounded), with reasonable defaults recorded as assumptions.

### STEP 7 - Inline Quality Validation

1. Write `<checklists_dir>/requirements.md` with standard items: no implementation details, user-value focused, mandatory sections present, no `[NEEDS CLARIFICATION]` left, every AC testable + measurable, every story has ACs, edge cases identified, scope bounded, dependencies/assumptions noted.
2. Mark each pass/fail by re-reading the spec.
3. Failures (other than `[NEEDS CLARIFICATION]`) -> edit spec, re-check. **Max 3 iterations**, then record remaining issues in checklist Notes and warn the user.
4. `[NEEDS CLARIFICATION]` markers -> ask one at a time, update spec verbatim, re-validate.

The checklist is lightweight here; for the full themed pass, users run `task-spec-checklist <slug>` next.

### STEP 8 - Summarize

Print: paths written, story/AC/open-question/marker counts, validation iterations, mode, next command (`task-spec-clarify <slug>` if markers/questions remain, else `task-spec-checklist` or `task-spec-plan`).

## Output Format

`spec.md` template (standalone mode):

```markdown
# Spec - <Feature Name>

- **Slug:** <slug>
- **Status:** draft | clarified | planned | implementing | complete
- **Created:** <YYYY-MM-DD>
- **Last updated:** <YYYY-MM-DD>

## Problem Statement
<One paragraph.>

## Target Users
- **Primary:** <role> - <description>
- **Secondary:** <role> - <description>          # omit if none

## User Stories
- **S1.** As a <role>, I want <capability>, so that <value>.

## Acceptance Criteria
- **AC1 (S1):** <falsifiable, measurable>
- **AC2 (S1):** ...

## Non-Functional Requirements
<NFR table from nfr-specification. Only categories that apply.>

## Out of Scope
- <Explicit non-goal>

## Open Questions
- **Q1:** <text> - to be resolved in `task-spec-clarify`.

## Revisions
(Empty on first write; amend mode appends dated entries.)
- <YYYY-MM-DD>: <change> (by `task-spec-clarify` | `task-spec-specify` amend | manual)
```

## Self-Check

- [ ] Loaded `behavioral-principles` and `speckit-detect` first
- [ ] Paths via `spec-artifact-paths`
- [ ] In speckit mode, presented NFR additions for user merge (no silent edits)
- [ ] Every story has >=1 AC; every AC falsifiable + measurable
- [ ] NFR section omits categories that do not apply (no "not required for v1" stubs)
- [ ] Out-of-scope is non-empty
- [ ] Conflicts surfaced, not silently resolved
- [ ] `[NEEDS CLARIFICATION]` markers <=3, prioritized correctly
- [ ] Inline validation ran; `checklists/requirements.md` written
- [ ] Summary includes counts, validation results, next command

## Avoid

- Generating code, schemas, API contracts, or technology choices (those belong in `task-spec-plan`).
- Inventing stories or ACs the user did not request.
- Vague AC verbs without measurable thresholds.
- Overwriting `spec.md` without offering replace/amend/abort.
- NFR subsections like "not required for v1" - omit the category entirely.
