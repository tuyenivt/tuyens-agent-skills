---
name: task-spec-clarify
description: Resolve spec.md ambiguities via spec-review + one-question-at-a-time Q&A; append to clarifications.md, revise spec.md. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, clarify, ambiguity, requirements]
  type: workflow
user-invocable: true
---

# Spec - Clarify

Surface ambiguous, conflicting, missing, or unmeasurable items in an existing `spec.md`; resolve them via one-question-at-a-time Q&A; append the session to `clarifications.md`; revise `spec.md`.

Invocation: `/task-spec-clarify <slug> [--blockers-only | --all] [--non-interactive]`

## When to Use

- After `task-spec-specify` reports open questions, or before `task-spec-plan` if the spec feels ambiguous.
- When a spec has aged and may have drifted from current intent.
- Not for: authoring from scratch (use `task-spec-specify`), code review, architectural decisions.

Scope flags:

| Flag              | Findings asked          |
| ----------------- | ----------------------- |
| (default)         | blocker + major         |
| `--blockers-only` | blocker                 |
| `--all`           | blocker + major + minor |

`--non-interactive` emits the findings list and exits without Q&A or file writes.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode and Resolve Paths

Use skill: speckit-detect
Use skill: spec-artifact-paths

If `.specs/<slug>/spec.md` is missing, abort and recommend `task-spec-specify`.

If mode is **speckit-installed**: run `spec-review` (pre-pass), instruct the user to run `/speckit-clarify` (any `before_clarify`/`after_clarify` hooks in `.specify/extensions.yml` fire as part of that call -- do not bypass), then jump to STEP 6 with `spec-review` re-run as the post-pass.

### STEP 3 - Review

Use skill: spec-review

Filter findings by the scope flag (table above). Each finding must carry a stable `id` (e.g., `F-001`) emitted by `spec-review`; questions reference it.

- `summary.status == pass`: print "spec clean at requested scope", jump to STEP 6. Do not invent questions.
- `summary.status == needs-rewrite` (any blocker): present blockers and stop. Recommend manual restructuring or `task-spec-specify` in amend mode. Do not Q&A around structural blockers.

If `--non-interactive`: emit the filtered findings list and exit. Do not modify files.

### STEP 4 - Ask, Capture, Resolve

For each finding, severity order, **one question at a time, no batching**:

1. Ask the finding's `suggested_clarification` (refine wording if it reads awkwardly).
2. Record the answer verbatim.
3. Classify the answer:
   - `resolved` - concrete, applicable to the spec.
   - `deferred` - user explicitly defers ("don't know yet").
   - `declined` - user rejects the question as out-of-scope or wrong premise.
4. If a `resolved` answer contradicts another section of `spec.md`, stop the loop, present both texts, and ask which wins before continuing. Do not silently append.

### STEP 5 - Write Artifacts

**`clarifications.md`** (append-only; create if absent):

```markdown
# Clarifications - <Feature Name>

## Session <YYYY-MM-DD HH:MM>

- **Q1 (<finding-id>, location: <section>):** <question>
  **A:** <answer verbatim>
  **Disposition:** resolved | deferred | declined
```

**`spec.md`**:

- Apply each `resolved` answer to its target section.
- `deferred` -> `Open Questions` (add the section if missing; do not duplicate).
- `declined` -> leave the spec untouched.
- Bump `Last updated`.
- Append a `## Revisions` entry: `<YYYY-MM-DD>: Resolved <N> findings via task-spec-clarify. Updated: <sections>. Deferred: <N>. Declined: <N>. (See clarifications.md.)`

### STEP 6 - Re-Review and Recommend

Re-run `spec-review`. Use the post-pass status as the final status:

- `pass` -> recommend `task-spec-plan <slug>`.
- `needs-clarification` -> recommend another clarify pass (suggest `--all` if previous was default).
- `needs-rewrite` -> recommend manual restructuring.

## Output Format

```
Spec clarify - <slug> (<mode>)
  Findings:   asked=<n> resolved=<n> deferred=<n> declined=<n>
  Status:     <pass | needs-clarification | needs-rewrite>
  Updated:    spec.md (revisions appended), clarifications.md (session appended)
  Next:       task-spec-plan <slug>   |   task-spec-clarify <slug> --all   |   manual rewrite
```

In `--non-interactive` mode, omit the `Updated:` line and replace `Status:` with the pre-pass status.

## Self-Check

- [ ] STEP 1: loaded `behavioral-principles`.
- [ ] STEP 2: detected mode, resolved paths, aborted cleanly if `spec.md` missing; speckit mode did not duplicate Spec Kit edits.
- [ ] STEP 3: drove questions from `spec-review` findings; stopped on `needs-rewrite`; honored `--non-interactive`.
- [ ] STEP 4: one question at a time; verbatim answers; surfaced contradictions before appending.
- [ ] STEP 5: `clarifications.md` append-only; `spec.md` carries a `Revisions` entry referencing `clarifications.md`.
- [ ] STEP 6: re-ran `spec-review` and reported the post-pass status.

## Avoid

- Inventing ambiguities not present in `spec-review` output.
- Batching questions.
- Editing `spec.md` without a `Revisions` entry.
- Auto-looping `task-spec-clarify` on `needs-clarification` -- the user decides.
