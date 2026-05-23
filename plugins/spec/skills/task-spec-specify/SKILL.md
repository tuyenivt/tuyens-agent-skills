---
name: task-spec-specify
description: Elicit feature requirements and write spec.md (problem, users, stories, AC, NFRs, out-of-scope) to .specs/<slug>/. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, requirements, specification, foundation]
  type: workflow
user-invocable: true
---

# Spec - Specify

Captures the **what** and **why** of a feature as a persistent `spec.md` before any architecture work. Downstream phases (`task-spec-clarify/plan/tasks/implement`) consume it; stack workflows consume it via `--spec`.

## When to Use

For new features, re-specs of drifted features, or producing a portable handoff artifact. Requires a feature name or short description as argument; if only a one-word name is supplied, ask for the problem and primary user before proceeding. Not for: technical design (`task-spec-plan`), system architecture (`task-design-architecture`), bug reports (`task-code-debug`).

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

If `spec.md` already exists, prompt the user: **replace** / **amend** (preserve, append revision entry) / **abort**. Do not overwrite without this choice.

### STEP 4 - Branch on Mode

**speckit-installed:** summarize the feature request into one paragraph, instruct the user to run `/speckit-specify <paragraph>`, then read the resolved feature path from `.specify/feature.json` and load the produced `spec.md`. Run `Use skill: nfr-specification` and present any missing NFR coverage as a diff for user merge - do not silently edit Spec Kit output. Skip to STEP 6.

**standalone:** continue.

### STEP 5 - Elicit and Write

Interview the user on the sections below, asking only what is not already in context. Stack-agnostic; do not load `stack-detect`.

| Section                 | Elicit                                                                                                |
| ----------------------- | ----------------------------------------------------------------------------------------------------- |
| **Problem statement**   | User-facing pain or business gap. Plain language, no implementation hints.                            |
| **Target users**        | Primary and (if any) secondary roles. Internal vs external, authn vs anon.                            |
| **User stories**        | "As a \<role>, I want \<capability>, so that \<value>." One per outcome.                              |
| **Acceptance criteria** | Falsifiable, measurable. Every story has >=1 AC. Numeric thresholds where applicable.                 |
| **Non-functional**      | `Use skill: nfr-specification`. Include only categories with a real requirement; omit the rest.       |
| **Out of scope**        | Required. List explicit non-goals.                                                                    |
| **Open questions**      | Items the user could not answer; resolved later by `task-spec-clarify`.                               |

Write `spec.md` using the template in **Output Format**. For blocking ambiguity (cannot write the AC at all), embed inline `[NEEDS CLARIFICATION: <question>]`. Everything else goes to **Open Questions** with the assumed default recorded.

Domain triggers: if the feature touches payments, health data, or PII, name the applicable regulatory standard and ask before assuming scope.

### STEP 6 - Summarize

Print: paths written, counts (stories, ACs, open questions, clarification markers), mode, next command - `task-spec-clarify <slug>` if any markers or open questions remain, else `task-spec-checklist <slug>` for the full requirements-quality pass, then `task-spec-plan <slug>`.

## Output Format

`spec.md` (standalone mode):

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

- [ ] STEP 1: behavioral-principles loaded
- [ ] STEP 2: mode resolved via `speckit-detect`
- [ ] STEP 3: paths via `spec-artifact-paths`; existing `spec.md` handled via replace/amend/abort
- [ ] STEP 4: in speckit mode, NFR additions surfaced as a diff (no silent edits)
- [ ] STEP 5: every story has >=1 measurable AC; NFR section omits inapplicable categories; Out of Scope non-empty; `[NEEDS CLARIFICATION]` used only for blocking ambiguity
- [ ] STEP 6: summary includes counts, mode, and the correct next command

## Avoid

- Generating code, schemas, API contracts, or technology choices (belongs in `task-spec-plan`).
- Vague AC verbs ("fast", "easy", "robust") without a measurable threshold.
- NFR placeholders like "not required for v1" - omit the category instead.
- Editing Spec Kit output silently in speckit-installed mode.
