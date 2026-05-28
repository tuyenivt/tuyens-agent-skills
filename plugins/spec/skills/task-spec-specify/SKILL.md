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

Captures the **what** and **why** of a feature as a persistent `spec.md`.

## When to Use

New features, re-specs of drifted features, or producing a portable handoff artifact. Requires a feature argument; if the argument does not convey a target user and an outcome, ask for both before STEP 5.

Not for technical design (`task-spec-plan`), system architecture (`task-design-architecture`), or bug reports (`task-code-debug`).

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

If `spec.md` already exists, prompt: **replace** / **amend** (preserve, append revision entry) / **abort**.

### STEP 4 - Branch on Mode

**speckit-installed**: summarize the feature into one paragraph, instruct the user to run `/speckit-specify <paragraph>`. After it returns, read `.specify/feature.json`, load the produced `spec.md`. Run `Use skill: nfr-specification` and present missing NFR coverage as a diff for user merge. Skip to STEP 6.

**standalone**: continue to STEP 5.

### STEP 5 - Elicit and Write

Interview the user on the sections below, asking only what is not already in chat history, CLAUDE.md, or related specs.

| Section                 | Elicit                                                                                                |
| ----------------------- | ----------------------------------------------------------------------------------------------------- |
| **Problem statement**   | User-facing pain or business gap. Plain language, no implementation hints.                            |
| **Target users**        | Primary and (if any) secondary roles. Internal vs external, authn vs anon.                            |
| **User stories**        | "As a \<role>, I want \<capability>, so that \<value>." One per outcome.                              |
| **Acceptance criteria** | Falsifiable, measurable. Every story has >=1 AC. Numeric thresholds where applicable.                 |
| **Non-functional**      | `Use skill: nfr-specification`. Include only categories with a real requirement.                      |
| **Domain triggers**     | If the feature touches payments, health data, or PII, name the applicable regulation and ask before assuming scope. |
| **Out of scope**        | Required. List explicit non-goals.                                                                    |
| **Open questions**      | Items the user could not answer; resolved later by `task-spec-clarify`.                               |

Ambiguity routing:
- `[NEEDS CLARIFICATION: <question>]` only when no reasonable default exists and downstream planning would pick arbitrarily.
- Open Question with `Assumed default: <value>` when a reasonable default can be recorded for later override.

Open Question entry format (shared with `task-spec-clarify`):

```
**Q<N>:** <text>
   Assumed default: <value | none>
   Source: specify | clarify
```

### STEP 6 - Summarize

Print: paths written, counts (stories, ACs, open questions, clarification markers), mode, next command - `task-spec-clarify <slug>` if any markers or open questions remain, else `task-spec-checklist <slug>` then `task-spec-plan <slug>`.

## Output Format

```markdown
# Spec - <Feature Name>

- **Slug:** <slug>
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
- **Q1:** <text>
   Assumed default: <value | none>
   Source: specify

## Revisions
- <YYYY-MM-DD>: <change> (by `task-spec-clarify` | `task-spec-specify` amend | manual)
```

## Self-Check

- [ ] STEP 1-3: behavioral-principles loaded; mode resolved; existing `spec.md` handled via replace/amend/abort
- [ ] STEP 4: in speckit mode, NFR additions surfaced as a diff (no silent edits)
- [ ] STEP 5a: every story has >=1 measurable AC
- [ ] STEP 5b: NFR section omits inapplicable categories
- [ ] STEP 5c: Out of Scope non-empty
- [ ] STEP 5d: `[NEEDS CLARIFICATION]` used only for blocking ambiguity; defaultable items go to Open Questions
- [ ] STEP 6: summary includes counts, mode, and the correct next command

## Avoid

- Generating code, schemas, API contracts, or technology choices (belongs in `task-spec-plan`).
- Vague AC verbs ("fast", "easy") without a measurable threshold.
- NFR placeholders like "not required for v1" - omit the category instead.
- Editing Spec Kit output silently in speckit-installed mode.
