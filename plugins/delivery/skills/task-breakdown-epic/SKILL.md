---
name: task-breakdown-epic
description: Break epic into vertically-sliced user stories with acceptance criteria and demoable value; for sprint planning and backlog refinement.
metadata:
  category: planning
  tags: [planning, user-stories, vertical-slice, acceptance-criteria, sprint-planning]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Story Slicing

## Purpose

Produce a list of vertically-sliced user stories ready for sprint commitment:

- **Vertical slices, not layers** -- every story delivers user-visible value end-to-end (UI to data), never "just the backend"
- **Explicit acceptance criteria** -- each story carries Given/When/Then ACs that QA, dev, and PM agree mean "done"
- **Independent and shippable** -- stories can be delivered, demoed, and merged without waiting on a sibling
- **Small** -- target half a sprint or less; flag anything bigger as needing further slicing

This skill complements `task-breakdown-story`. Use this when the audience is the sprint board (PM, QA, devs committing) and the artifact is stories. Use `task-breakdown-story` when the audience is engineering planning and the artifact is a phased task graph with hidden-complexity surfacing.

## When to Use

- Refining an epic before sprint commitment
- Slicing a story that turned out larger than expected
- Building a sprint backlog from a feature spec
- Splitting work between two devs who need independent stories

Not for system design (use `task-design-architecture`), not for engineering task decomposition with phases and dependencies (use `task-breakdown-story`), not for triaging existing debt (use `task-debt-prioritize`).

## Inputs

| Input                | Required | Description                                                               |
| -------------------- | -------- | ------------------------------------------------------------------------- |
| Feature or epic      | Yes      | What needs to be built and why. Free text, ticket link, or spec document  |
| Primary user         | No       | Who the feature is for - if missing, ask before slicing                   |
| Existing constraints | No       | Tech stack, team capacity, must-ship-by date, dependencies on other teams |
| Out of scope         | No       | What is explicitly not part of this feature                               |
| Spike findings       | No       | Outputs from prior discovery work that constrain or unblock slicing       |

If primary user is missing, do not invent one - ask. A "user" can be an engineer, an internal admin, an external API consumer, or an end customer; the slicing pattern depends on which.

## Rules

- Every story must have at least one user-visible outcome - if there is nothing to demo, it is not a vertical slice
- Every story has 1-5 acceptance criteria in Given/When/Then form (or equivalent), covering happy path + at least one negative or edge case
- Stories are independent by default - if one story blocks another, name the blocker explicitly and justify why splitting differently is not better
- Story size is relative (XS / S / M) - anything bigger gets split further before output
- Use one of the recognized slicing patterns (see Patterns below); name the pattern used per slice
- Do not produce stories that are pure infrastructure, refactor, or "set up the database" - those are tasks inside a story or belong on the engineering board, not the product backlog
- Do not generate implementation code or technical design

## Slicing Patterns

When a feature is too big for one story, slice along one of these axes. Pick the one that produces the most independent, demoable slices:

| Pattern              | Cut along...                                        | Use when                                                                                   |
| -------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **Workflow steps**   | Steps in a multi-step flow                          | Feature is a wizard, checkout, or multi-step process; each step has standalone value       |
| **User roles**       | Different users (admin / member / guest)            | Same capability behaves differently per role; ship for one role first                      |
| **Happy path first** | Happy path -> error handling -> edge cases          | Feature has rich error paths; demo happy path early, then harden                           |
| **Data variations**  | Single record -> bulk -> filtered -> exported       | CRUD-style feature where bulk operations come later                                        |
| **Interface**        | API first -> UI -> mobile, or one channel at a time | Multi-surface feature (web + mobile + API) where one surface unblocks downstream consumers |
| **Rules**            | Simplest rule -> add rule variations                | Feature has business rules that can be staged (flat fee first, tiered pricing next)        |
| **CRUD ops**         | Read -> Create -> Update -> Delete                  | Standard resource management; read-only is often demoable on its own                       |
| **Defer the wow**    | Functional plain version -> styled / polished       | Visual polish should not block functional value                                            |

**Anti-pattern: layered slicing.** Do not slice as "Story 1: backend, Story 2: frontend". This produces non-demoable, blocked slices. If the only way to slice feels layered, the feature may be too small to slice at all.

## Workflow

### STEP 1 - Behavioral and Stack Setup

Use skill: `behavioral-principles` before any other delegation.

Use skill: `stack-detect` to identify project stack - shapes which slicing patterns apply (e.g., Rails feature flags vs frontend-only feature toggles, mobile/web split).

### STEP 2 - Frame the Feature

Restate the feature in one sentence: **"As a <user>, I want to <capability>, so that <outcome>."**

If the user did not supply primary user or outcome, ask before slicing - inventing them produces useless stories. State explicitly what you understood and what you assumed.

### STEP 3 - Identify Slicing Axes

List 2-4 candidate slicing patterns from the table above that fit this feature, then pick the one that produces the most independent, demoable slices. Name the pattern chosen and why the alternatives were rejected.

### STEP 4 - Produce Story Slices

Generate the story list. Each story includes:

- **Title**: imperative, user-facing - "Member can save a draft order", not "Add draft persistence"
- **Story**: As a <user>, I want to <capability>, so that <outcome>
- **Acceptance Criteria**: 1-5 Given/When/Then bullets covering happy path + at least one edge case
- **Demo**: one sentence describing what is shown in sprint review when this story is done
- **Size**: XS (< 1 day), S (1-2 days), M (3-5 days). Anything larger gets re-sliced before output.
- **Slicing pattern used**: which pattern from the table above
- **Depends on**: another story in this list, an external dependency, or "none" - default should be "none"
- **Out of scope for this story**: what is intentionally deferred to a later slice (prevents stakeholder scope drift)

### STEP 5 - Sequence and Independence Check

Order the stories so the earliest stories deliver the highest user value. For each story:

- Confirm it can be merged and demoed without any later story
- If it cannot, explicitly name the blocker; consider whether re-slicing eliminates the dependency

Use skill: `review-blast-radius` if a slice involves auth, payments, or data migration - to confirm the slice is small enough to ship safely.
Use skill: `ops-feature-flags` if any slice ships behind a flag - to document the gating and rollout plan per slice.

### STEP 6 - Validation Pass

For every story, validate against the INVEST checklist:

- **I**ndependent - can ship without siblings
- **N**egotiable - not over-specified; leaves room for technical judgment
- **V**aluable - demoable user outcome
- **E**stimable - team can size it
- **S**mall - XS/S/M; never L/XL
- **T**estable - ACs are concrete enough to verify

Flag any story failing INVEST and either re-slice or document the exception.

### STEP 7 - Self-Check

Walk the Self-Check list before returning the slice plan.

## Output Format

```markdown
# Story Slicing: <Feature Name>

## Feature Frame

> As a <primary user>, I want to <capability>, so that <outcome>.

**Slicing pattern chosen:** <pattern from table>
**Why this pattern:** <one sentence>
**Patterns rejected and why:** <one sentence each, optional>

## Stories

### 1. <Imperative title>

- **Story**: As a <user>, I want to <capability>, so that <outcome>
- **Acceptance Criteria**:
  - **Given** <state> **when** <action> **then** <observable result>
  - **Given** <state> **when** <action> **then** <observable result>
  - [edge case AC]
- **Demo**: <one sentence>
- **Size**: XS / S / M
- **Slicing pattern**: <pattern>
- **Depends on**: none | story #N | external (<what>)
- **Out of scope for this story**: <list>

[repeat per story]

## Sequencing

1. Story #1 (no deps)
2. Story #2 (no deps, parallel with #1)
3. Story #3 (after #1)
   ...

**First demoable slice:** Story #<N> - the smallest story that proves the feature concept end-to-end.

## INVEST Findings

- Stories failing any INVEST axis, with chosen action (re-slice / accept exception with rationale).
- Omit if all stories pass.

## Assumptions and Open Questions

- Assumptions made due to missing input
- Questions that, if answered, would change the slicing
```

### Output Constraints

- No story may be sized L or XL - slice further or split into a separate epic
- Every story has at least one Given/When/Then AC
- Layered (backend-only / frontend-only) stories are not allowed
- Omit empty sections

## Self-Check

- [ ] Behavioral-principles loaded as the first step
- [ ] Primary user is named (or explicitly asked for, never invented)
- [ ] Slicing pattern named per slice; alternatives considered
- [ ] Every story has a one-sentence demo and a sized estimate (XS/S/M only)
- [ ] Every story has 1-5 Given/When/Then ACs covering happy path + one edge case
- [ ] No layered (backend-only or frontend-only) stories
- [ ] Each story passes INVEST or has a documented exception
- [ ] Sequencing identifies the first demoable slice
- [ ] Out of scope is named per story to prevent scope drift

## Avoid

- Layered slices (backend story / frontend story / database story) - they are not demoable on their own
- "Setup" or "infrastructure" stories - those are tasks inside a story, not stories
- Acceptance criteria written as implementation hints ("Use a Redis cache") instead of observable behavior
- Stories sized L or XL - if you cannot get to M or smaller, the slicing pattern is wrong
- Inventing a primary user when the input did not supply one
- Repeating `task-breakdown-story`'s phased output - this skill produces stories, not engineering tasks
- Treating ACs as test cases - ACs are agreement of done, tests verify them
