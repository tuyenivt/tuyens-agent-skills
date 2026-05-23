---
name: task-breakdown-epic
description: Break epic into vertically-sliced user stories with acceptance criteria and demoable value; for sprint planning and backlog refinement.
metadata:
  category: planning
  tags: [planning, user-stories, vertical-slice, acceptance-criteria, sprint-planning]
  type: workflow
user-invocable: true
---

# Story Slicing

Produce vertically-sliced, demoable user stories ready for sprint commitment. For engineering task graphs with phases and dependencies, use `task-breakdown-story` instead.

## When to Use

- Refining an epic before sprint planning
- Splitting a story that turned out larger than expected
- Splitting work between two devs who need independent stories

## Inputs

Required: a feature or epic description.
Ask before slicing if **primary user** or **outcome** is missing - inventing them produces useless stories. A "user" can be an engineer, internal admin, API consumer, or end customer; the slicing pattern depends on which.

## Workflow

### STEP 1 - Behavioral Setup

Use skill: `behavioral-principles`.

This workflow is stack-agnostic and does not load `stack-detect`.

### STEP 2 - Frame the Feature

Restate as one sentence: **"As a <user>, I want to <capability>, so that <outcome>."** State assumptions explicitly when input was thin.

### STEP 3 - Pick a Slicing Pattern

Pick the **primary** axis and optionally a **secondary** cut (most multi-actor or multi-surface features need both). Name each axis; briefly note why others were rejected.

| Pattern | Cut along… | Use when |
| --- | --- | --- |
| **Workflow steps** | Steps in a multi-step flow | Wizard, checkout, lifecycle - each step has standalone value |
| **User roles** | admin / member / guest | Same capability differs per role; ship one role first |
| **Happy path first** | Happy → errors → edges | Demo happy early, harden later |
| **Data variations** | Single → bulk → filtered → exported | CRUD where bulk comes later |
| **Interface** | API → UI → mobile | Multi-surface; one channel unblocks others |
| **Rules** | Simplest rule → variations | Stage business rules (flat fee → tiered) |
| **CRUD ops** | Read → Create → Update → Delete | Read-only is often demoable on its own |
| **Defer the wow** | Functional → polished | Visual polish must not block functional value |

If the only honest slicing feels layered (backend-only / frontend-only), the feature may already be one story - see Avoid.

### STEP 4 - Produce the Slices

Each story:

- **Title** - imperative, user-facing ("Member can save a draft order", not "Add draft persistence")
- **Story** - As a <user>, I want to <capability>, so that <outcome>
- **Acceptance Criteria** - 1-3 Given/When/Then bullets. Include at least one edge-case AC unless the story is genuinely single-path (size XS).
- **Demo** - one sentence on what's shown in sprint review
- **Size** - XS (<1d) / S (1-2d) / M (3-5d). No L/XL - re-slice instead.
- **Depends on** - story #N, external (<what>), or none (default and preferred)
- **Out of scope** - what is intentionally deferred (prevents scope drift)
- **Safety** - only when a slice carries irreversible side effects or rides a feature flag; one line summarizing the risk and gating

If any story has a Safety line, load `Use skill: review-blast-radius` (irreversible side effects) or `Use skill: ops-feature-flags` (flagged rollout) to ground the note.

### STEP 5 - Sequence and INVEST Pass

Order so the highest-value slices come first. For each story confirm it can ship and demo without later siblings; if not, name the blocker or re-slice.

INVEST is the validation rubric - **I**ndependent, **N**egotiable, **V**aluable, **E**stimable, **S**mall, **T**estable. Flag any story failing one and re-slice or document the exception as: `#N fails <axis> (<reason>); accepted because <justification>`.

## Output Format

```markdown
# Story Slicing: <Feature>

> As a <user>, I want to <capability>, so that <outcome>.

**Primary axis:** <pattern> - <why; one sentence>
**Secondary axis:** <pattern or none>
**Rejected:** <pattern> (<reason>); <pattern> (<reason>)

## Stories

### 1. <Imperative title>

- **Story:** As a <user>, I want to <capability>, so that <outcome>
- **AC:**
  - Given <state> when <action> then <result>
  - [edge-case AC]
- **Demo:** <one sentence>
- **Size:** XS / S / M
- **Depends on:** none | #N | external (<what>)
- **Out of scope:** <list>
- **Safety:** <only when irreversible or flag-gated>

[repeat per story]

## Sequencing

1. #1 (no deps)
2. #2 (parallel with #1)
3. #3 (after #1)

**First demoable slice:** #N - the smallest story that proves the concept end-to-end.

## INVEST Exceptions

- #N fails <axis> (<reason>); accepted because <justification>

Omit if all pass.

## Assumptions and Open Questions

- Assumptions made due to missing input
- Questions whose answers would change slicing
```

## Self-Check

- [ ] **Setup:** behavioral-principles loaded
- [ ] **Frame:** primary user named (asked, not invented); one-sentence frame produced
- [ ] **Pattern:** primary axis named; secondary or "none" stated; rejected alternatives listed
- [ ] **Slices:** every story has Title, Story, AC, Demo, Size (XS/S/M), Depends-on, Out-of-scope; Safety line present iff slice is irreversible or flag-gated
- [ ] **Sequence + INVEST:** first demoable slice identified; INVEST exceptions documented (or none)

## Avoid

- Layered slices (backend-only / frontend-only) - not demoable
- "Setup" or "infrastructure" stories - those are tasks inside a story
- ACs as implementation hints ("Use Redis") instead of observable behavior
- Treating ACs as test cases - ACs are agreement of done; tests verify them
- Inventing a primary user
