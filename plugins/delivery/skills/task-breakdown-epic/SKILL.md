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

Ask before slicing when **primary user** or **outcome** is missing or generic ("so users are happy"). A "user" can be an engineer, internal admin, API consumer, or end customer; the slicing pattern depends on which. When the epic spans multiple primary users, name them all and either slice per-user (User roles pattern) or pick one as primary and defer the others to Out-of-scope.

Echo the user's vocabulary ("customer" stays "customer", not silently promoted to "member") unless the user states the mapping.

## Workflow

### STEP 1 - Behavioral Setup

Use skill: `behavioral-principles`.

### STEP 2 - Frame the Feature

Restate as one sentence: **"As a <user>, I want to <capability>, so that <outcome>."** State assumptions explicitly when input was thin.

### STEP 3 - Pick a Slicing Pattern

Pick a **primary** axis. Add a **secondary** axis only when the primary alone produces stories that still cover multiple actors or surfaces. Name each axis; briefly note why others were rejected.

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

- **Title** - imperative, user-facing. Example: "Member can save a draft order" (good); "Add draft persistence" (bad - implementation framing)
- **Story** - `As a <user>, I want to <capability>, so that <outcome>`
- **Acceptance Criteria** - 1-3 Given/When/Then bullets describing observable behavior, not implementation. Include at least one edge-case AC unless the story is single-path (size XS).
- **Demo** - one sentence on what's shown in sprint review
- **Size** - XS (<1d) / S (1-2d) / M (3-5d), focused engineering effort. No L/XL - re-slice instead. If your team estimates in story points, map XS=1, S=2-3, M=5.
- **Depends on** - story #N (sequencing only), external (<what>), or none. Sequencing deps do not violate Independence.
- **Out of scope** - what is intentionally deferred
- **Safety** - one line, only when the slice carries an irreversible side effect (data loss, money movement, external notification) AND is not gated by an existing safety net. Pure flag-gating without an irreversible action does not require a Safety line.

When any story has a Safety line: load `Use skill: review-blast-radius` to ground the risk wording; load `Use skill: ops-feature-flags` if a flag is the proposed gate.

Micro-example of one slice:

```
### 1. Member can save a draft order

- **Story:** As a member, I want to save my cart as a draft, so that I can finish ordering later.
- **AC:**
  - Given a cart with items, when the member taps "Save draft", then the draft appears under "My drafts" with all items preserved
  - Given a saved draft, when the member resumes it, then the cart is restored exactly as saved
- **Demo:** Add items, save draft, log out, log in, resume - cart restored.
- **Size:** S
- **Depends on:** none
- **Out of scope:** sharing drafts; auto-save; expiry
```

### STEP 5 - Sequence and INVEST Pass

Order stories so highest-value lands first, but identify the **first demoable slice** as the smallest story that proves the concept end-to-end - it may sequence before higher-value stories when those need it as a foundation.

INVEST validation - **I**ndependent (no semantic coupling; pure sequencing is fine), **N**egotiable, **V**aluable, **E**stimable, **S**mall, **T**estable. Flag any story failing one and re-slice or document: `#N fails <axis> (<reason>); accepted because <justification>`.

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
- **Safety:** <only when irreversible and ungated>

[repeat per story]

## Sequencing

1. #1 (no deps)
2. #2 (parallel with #1)
3. #3 (after #1)

**First demoable slice:** #N - <why this is the smallest end-to-end proof>

## INVEST Exceptions

- #N fails <axis> (<reason>); accepted because <justification>

Omit if all pass.

## Assumptions and Open Questions

- Assumptions made due to missing input
- Questions whose answers would change slicing
```

## Self-Check

- [ ] **Setup:** behavioral-principles loaded
- [ ] **Frame:** primary user named (asked, not invented); user vocabulary preserved; one-sentence frame produced
- [ ] **Pattern:** primary axis named; secondary or "none" stated; rejected alternatives listed
- [ ] **Slices:** every story has Title, Story, AC (observable behavior), Demo, Size (XS/S/M), Depends-on, Out-of-scope; Safety line present iff irreversible AND ungated
- [ ] **Sequence + INVEST:** first demoable slice identified; INVEST exceptions documented (or none)
- [ ] **Assumptions and Open Questions** section populated when input was thin

## Avoid

- Layered slices (backend-only / frontend-only) - not demoable
- "Setup" or "infrastructure" stories - those are tasks inside a story
- ACs written as implementation hints ("Use Redis") instead of observable behavior
- Treating Given/When/Then ACs as test cases - ACs are the agreement of done; tests verify them
- Inventing or silently renaming the primary user
