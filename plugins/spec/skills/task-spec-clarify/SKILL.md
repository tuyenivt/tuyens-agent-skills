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

Invocation: `/task-spec-clarify <slug> [--blockers-only | --all] [--non-interactive]`

## When to Use

After `task-spec-specify` reports open questions, before `task-spec-plan` if the spec feels ambiguous, or when a spec has aged. Not for authoring from scratch.

Scope flags:

| Flag              | Findings asked          |
| ----------------- | ----------------------- |
| (default)         | blocker + major         |
| `--blockers-only` | blocker                 |
| `--all`           | blocker + major + minor |

`--non-interactive` emits the filtered findings list and exits without Q&A or writes.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode and Resolve Paths

Use skill: speckit-detect
Use skill: spec-artifact-paths

If `.specs/<slug>/spec.md` is missing, abort and recommend `task-spec-specify`.

If mode is **speckit-installed**: run `spec-review` (pre-pass), instruct the user to run `/speckit-clarify`. The Revisions entry on `spec.md` is owned by `/speckit-clarify`. Jump to STEP 6 (re-run `spec-review` as the post-pass).

### STEP 3 - Review

Use skill: spec-review

Filter findings by the scope flag. Each finding carries a stable `id` from `spec-review`.

- `summary.status == pass`: print "spec clean at requested scope", jump to STEP 6.
- `summary.status == needs-rewrite` (any blocker): present blockers and stop. Recommend manual restructuring or `task-spec-specify` amend.

If `--non-interactive`: emit the filtered findings list and exit.

### STEP 4 - Ask, Capture, Resolve

For each finding (severity order; within tier, by finding id ascending), **one question at a time**:

1. Ask the finding's `suggested_clarification`.
2. Record the answer verbatim.
3. Classify:
   - `resolved` - answer is specific enough to drop into the spec verbatim (a number, an enum value, a named actor, a defined term). Hedges ("maybe", "around", "TBD") -> treat as `deferred`.
   - `deferred` - user defers, hedges, or answers "depends on X" where X is unresolved.
   - `declined` - user rejects premise or marks out-of-scope.
4. Before classifying `resolved`, scan spec sections referenced by the finding's `location` neighborhood (same heading + any AC/NFR mentioning the same noun). If the answer negates or narrows an existing statement, pause: quote both texts and ask "which wins?". Record the chosen text; mark the loser for revision.

Examples:

```
Q: "What is the max upload size for AC4 ('fast' uploads)?"
A: "5MB"           -> resolved
A: "depends on plan tier" -> deferred
A: "not a concern for this feature" -> declined
```

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

- Apply each `resolved` answer to its target section. When a contradiction was resolved in STEP 4.4, also edit or remove the losing text so the spec no longer contradicts itself.
- `deferred` -> append to `## Open Questions` (create at H2 immediately above `## Revisions` if absent; do not duplicate), using the entry format shared with `task-spec-specify`:
  ```
  **Q<N>:** <text>
     Assumed default: <user's hedge | none>
     Source: clarify
  ```
- `declined` -> spec untouched.
- Bump `Last updated: YYYY-MM-DD`.
- Append a `## Revisions` entry:
  ```
  <YYYY-MM-DD>: task-spec-clarify session. Resolved=<N> (IDs: F-00x, F-00y -> sections <heading or AC-id>). Deferred=<N> (IDs). Declined=<N> (IDs). See clarifications.md session <timestamp>.
  ```

### STEP 6 - Re-Review and Recommend

Re-run `spec-review`. Final status = post-pass status.

- `pass` -> `task-spec-plan <slug>`.
- `needs-clarification` -> another clarify pass (suggest `--all` if previous was default).
- `needs-rewrite` -> manual restructuring.

## Output Format

```
Spec clarify - <slug> (<mode>)
  Findings:   asked=<n> resolved=<n> deferred=<n> declined=<n>
  Status:     <pass | needs-clarification | needs-rewrite>
  Updated:    spec.md (revisions appended), clarifications.md (session appended)
  Next:       task-spec-plan <slug>   |   task-spec-clarify <slug> --all   |   manual rewrite
```

`--non-interactive` omits `Updated:` and reports the pre-pass status.

## Self-Check

- [ ] STEP 1-2: behavioral-principles loaded; mode detected; aborted if `spec.md` missing
- [ ] STEP 3: drove questions from `spec-review` findings; stopped on `needs-rewrite`; honored `--non-interactive`
- [ ] STEP 4: one question at a time, severity then id order; verbatim answers; surfaced contradictions before appending
- [ ] STEP 5: `clarifications.md` append-only; resolved contradictions edit the losing text; deferred items use the shared Open Question format (`Source: clarify`); `spec.md` `Revisions` entry references `clarifications.md` session
- [ ] STEP 6: re-ran `spec-review`; reported post-pass status

## Avoid

- Inventing ambiguities not present in `spec-review` output.
- Batching questions.
- Editing `spec.md` without a `Revisions` entry.
- Auto-looping `task-spec-clarify` on `needs-clarification` - the user decides.
