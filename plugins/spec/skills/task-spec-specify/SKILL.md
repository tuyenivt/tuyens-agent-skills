---
name: task-spec-specify
description: Foundation phase of Spec-Driven Development. Elicit feature requirements (problem, users, stories, acceptance criteria, NFRs) and write a structured `spec.md` to `.specs/<feature-slug>/spec.md`. Speckit-aware - delegates to `/speckit.specify` when Spec Kit is installed, otherwise drives the elicitation itself.
metadata:
  category: spec
  tags: [spec, sdd, requirements, specification, foundation]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spec - Specify

Captures the **what** and **why** of a feature as a persistent artifact, before any architecture or code work begins. Output is `spec.md`: problem statement, target users, user stories, acceptance criteria, non-functional requirements, and explicit out-of-scope items. Downstream phases (`task-spec-clarify`, `task-spec-plan`, `task-spec-tasks`, `task-spec-implement`) all consume this document; stack workflows can also consume it directly via `--spec`.

## When to Use

- Starting a new feature where requirements live only in chat or a ticket title
- Re-specifying an existing feature whose original requirements have drifted
- Producing a portable artifact for handoff between contributors or sessions

**Not for:** Architecture or technical design (use `task-spec-plan`), API-only specifications (use `task-design-api`), system-level architecture (use `task-design-architecture`), bug reports (use `task-debug`).

## Inputs

- A feature name or short description (required)
- Any existing context: ticket text, design notes, related code paths, prior conversations
- Optional explicit slug override (otherwise derived from the feature name)

**Insufficient input handling:** If the user provides only a one-word name with no surrounding context, ask for at least the problem being solved and the primary user before proceeding. Do not fabricate stories.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

Capture `mode`. Subsequent steps branch on it.

### STEP 3 - Resolve Artifact Paths

Use skill: spec-artifact-paths

Derive the slug from the feature name (or use the user-supplied override). Capture the resolved `spec` path. If `spec.md` already exists, ask the user whether to **replace**, **amend** (preserve and add a revision section), or **abort**.

### STEP 4 - Branch on Mode

#### Mode: speckit-installed

1. Pre-process: gather any context (ticket, prior chat, related files) into a brief Spec Kit can consume.
2. Delegate by instructing the user to run `/speckit.specify <brief>` (or invoke it if Spec Kit exposes a programmatic interface). Spec Kit owns artifact writing.
3. Post-process: once `/speckit.specify` produces its spec, run `Use skill: nfr-specification` over the result and append any missing NFR coverage as suggested additions. Do not silently edit Spec Kit's output - present the additions and let the user merge.
4. Skip to STEP 7.

#### Mode: standalone

Continue to STEP 5.

### STEP 5 - Elicit Requirements

Drive a structured elicitation. Ask only the questions whose answers are not already in the provided context. Cover:

| Section                 | What to elicit                                                                                        |
| ----------------------- | ----------------------------------------------------------------------------------------------------- |
| **Problem statement**   | The user-facing pain or business gap. One paragraph, plain language, no implementation hints.         |
| **Target users**        | Primary user role(s) and any secondary roles. Internal vs external, authenticated vs anonymous.       |
| **User stories**        | "As a <role>, I want <capability>, so that <value>." One per distinct outcome.                        |
| **Acceptance criteria** | Falsifiable, testable conditions. Every story must have at least one. Use measurable thresholds.      |
| **Non-functional**      | Run `Use skill: nfr-specification` to populate performance, availability, scalability, security, etc. |
| **Out of scope**        | Explicit list of things this feature deliberately does NOT do. Prevents scope creep in later phases.  |
| **Open questions**      | Items the user could not answer; flagged for `task-spec-clarify` to resolve.                          |

**Rules during elicitation:**

- Surface ambiguity rather than guess. If the user says "fast", ask for a number.
- Never invent stories the user did not ask for.
- If the user's answers conflict (e.g., "must work offline" + "real-time collaboration"), stop and surface the conflict.
- If the domain implies a regulatory standard (payments, health, PII), name it and ask for confirmation.

### STEP 6 - Write spec.md

Write the document to the resolved path using the template in **Output Format** below. Create parent directories as needed (via `spec-artifact-paths` write semantics). Set the document's declared name to match the slug input so future workflows can detect collisions.

When the user could not give a confident answer to a question whose answer materially affects scope, embed a **`[NEEDS CLARIFICATION: <specific question>]`** marker inline at the relevant location in `spec.md`. Cap markers at **3 total**, prioritized **scope > security/privacy > UX > technical detail**. If more than three candidates exist, fold the lower-priority ones into `Open Questions` (which is unbounded) and pick reasonable defaults for them, recording the assumption in the relevant section.

### STEP 7 - Inline Quality Validation

Before reporting completion, run a self-validation pass against `spec.md`:

1. Write a sibling checklist file at `<checklists_dir>/requirements.md` (resolved via `spec-artifact-paths`; create the directory if needed) listing the standard quality items: no implementation details, focused on user value, all mandatory sections present, no `[NEEDS CLARIFICATION]` left, every AC testable + measurable, every story has acceptance criteria, edge cases identified, scope bounded, dependencies and assumptions noted.
2. Mark each item pass/fail by re-reading the spec you just wrote.
3. **If items fail (other than `[NEEDS CLARIFICATION]`):** edit the spec to address them. Re-run the check. **Maximum 3 iterations.** After 3, record remaining issues in the checklist's Notes section and warn the user.
4. **If `[NEEDS CLARIFICATION]` markers remain:** print them to chat (max 3) and ask the user one at a time, then update the spec verbatim with each answer. Re-run validation after all are resolved.
5. The checklist file is created here in lightweight form; users who want the full themed checklist run `task-spec-checklist <slug>` next.

### STEP 8 - Summarize

Print a short summary to chat:

- Path written (and `checklists/requirements.md` path)
- Story count, acceptance-criteria count, open-question count, `[NEEDS CLARIFICATION]` count
- Validation iterations run; checklist pass/fail counts
- Mode used (speckit-installed or standalone)
- Suggested next command: `task-spec-clarify <slug>` if open questions or markers remain, otherwise `task-spec-checklist <slug>` (full quality pass) or `task-spec-plan <slug>`

## Output Format

`spec.md` template (standalone mode; speckit-installed mode defers to Spec Kit's template):

```markdown
# Spec - <Feature Name>

- **Slug:** <slug>
- **Status:** draft | clarified | planned | implementing | complete
- **Created:** <YYYY-MM-DD>
- **Last updated:** <YYYY-MM-DD>

## Problem Statement

<One paragraph. The user-facing pain or business gap.>

## Target Users

- **Primary:** <role> - <one-line description>
- **Secondary:** <role> - <one-line description> (omit section if none)

## User Stories

- **S1.** As a <role>, I want <capability>, so that <value>.
- **S2.** ...

## Acceptance Criteria

Each criterion references a story and is independently testable.

- **AC1 (S1):** <falsifiable condition with measurable threshold>
- **AC2 (S1):** ...
- **AC3 (S2):** ...

## Non-Functional Requirements

<NFR table populated by `nfr-specification` - performance, availability, scalability, security, compliance, observability, accessibility>

## Out of Scope

- <Explicit non-goal>
- <Explicit non-goal>

## Open Questions

- **Q1:** <question text> - to be resolved in `task-spec-clarify`.
- **Q2:** ...

## Revisions

(Empty on first write. Amend mode appends dated entries; nothing is deleted.)

- <YYYY-MM-DD>: <summary of change> (by `task-spec-clarify` | `task-spec-specify` amend | manual)
```

## Self-Check

- [ ] Loaded `behavioral-principles` and `speckit-detect` before any other work
- [ ] Resolved artifact paths through `spec-artifact-paths` (no hardcoded `.specs/` strings)
- [ ] In speckit-installed mode, did not silently edit Spec Kit's output - additions presented for user merge
- [ ] Every user story has at least one acceptance criterion
- [ ] Every acceptance criterion is falsifiable with a measurable threshold
- [ ] NFR section populated via `nfr-specification` (or explicitly waived per category with reason)
- [ ] Out-of-scope section is non-empty (an empty out-of-scope list is almost always wrong)
- [ ] Conflicts between user answers were surfaced, not silently resolved
- [ ] `[NEEDS CLARIFICATION]` markers capped at 3, prioritized scope > security/privacy > UX > tech
- [ ] Inline quality validation ran (max 3 iterations); `checklists/requirements.md` written alongside spec
- [ ] Final summary printed with story/AC/open-question/marker counts, validation results, and next-command suggestion

## Avoid

- Generating code, schemas, API contracts, or technology choices - those belong in `task-spec-plan`
- Inventing user stories or acceptance criteria the user did not request
- Using vague verbs in acceptance criteria ("fast", "scalable", "user-friendly") without measurable thresholds
- Overwriting an existing `spec.md` without offering replace/amend/abort
- Treating "no open questions" as a goal - genuine ambiguity should be captured rather than papered over

## Notes

- The slug is the contract for every downstream phase. Once chosen, do not rename it casually - downstream artifacts reference it by path.
- Amend mode preserves prior text and appends a dated revision section. This keeps spec history auditable.
- For polyglot or fullstack features, the spec is stack-agnostic. Stack details are captured later in `task-spec-plan`.
