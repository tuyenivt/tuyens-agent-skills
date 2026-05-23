---
name: task-spec-clarify
description: Resolve spec.md ambiguities via Q&A before planning - runs spec-review, asks questions, appends to clarifications.md, updates spec. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, clarify, ambiguity, requirements]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Spec - Clarify

Re-reads an existing `spec.md`, surfaces ambiguous / conflicting / missing / unmeasurable requirements, and resolves them via one-question-at-a-time Q&A. Produces an append-only `clarifications.md` log and a revised `spec.md`.

## When to Use

- After `task-spec-specify` reports open questions, or before `task-spec-plan` if the spec feels ambiguous.
- When a spec has aged and may have drifted from current intent.
- Not for: authoring from scratch (`task-spec-specify`), code review, architectural decisions.

## Inputs

- `<slug>` (required) - reads `.specs/<slug>/spec.md`. If missing, list available slugs and ask.
- Scope flags: `--blockers-only`, default `blocker + major`, `--all` adds `minor`.
- `--non-interactive` emits findings list and stops without Q&A or file writes.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

If `spec.md` does not exist, abort and recommend `task-spec-specify`.

### STEP 4 - Branch on Mode

**speckit-installed:** pre-process by running `spec-review`, instruct the user to run `/speckit-clarify` (any `before_clarify` / `after_clarify` hooks registered in `.specify/extensions.yml` will fire as part of that call - do not bypass them), then re-run `spec-review` post-clarify and report residual findings. Skip to STEP 8.

**standalone:** continue.

### STEP 5 - Review

Use skill: spec-review

Filter findings by scope:

| Flag              | Findings asked       |
| ----------------- | -------------------- |
| (default)         | blocker + major      |
| `--blockers-only` | blocker              |
| `--all`           | blocker + major + minor |

- `summary.status == pass`: print "spec looks clean at requested scope", skip to STEP 8. Do not invent questions.
- `summary.status == needs-rewrite` (any blocker): present blockers and stop. Recommend manual restructuring or `task-spec-specify` in amend mode. Do not Q&A around structural blockers.

### STEP 6 - Ask, Capture, Resolve

For each finding in severity order:

1. Ask the `suggested_clarification` (or a refined version). One at a time. No batching.
2. Record the answer verbatim.
3. If the answer contradicts another part of the spec, surface immediately - do not silently append.
4. Deferred ("don't know yet") -> mark `deferred`, keep in `Open Questions`.

In `--non-interactive` mode, emit the findings list and stop. Do not modify files.

### STEP 7 - Write Artifacts

**`clarifications.md`** (append-only):

```markdown
# Clarifications - <Feature Name>

## Session <YYYY-MM-DD HH:MM>

- **Q1 (F-001, location: <location>):** <question>
  **A:** <user's answer verbatim>
  **Disposition:** resolved | deferred | declined
```

Create if absent; otherwise append a new session block.

**`spec.md`**:

- Apply each `resolved` answer to the matching section.
- Append a `## Revisions` entry: `<YYYY-MM-DD>: Resolved <N> findings via task-spec-clarify. Updated: <sections>. (See clarifications.md.)`.
- Bump `Last updated`.
- `deferred` items go in `Open Questions` (add if missing; do not duplicate).
- `declined` items leave the spec untouched; the revision entry notes the decline.

### STEP 8 - Re-Review and Summarize

Re-run `spec-review`. Report new status, then:

- `status == pass` -> recommend `task-spec-plan <slug>`.
- `status == needs-clarification` -> recommend another clarify pass.

## Output Format

```
Spec clarify - <slug> (<mode>)
  Findings:   asked=<n> resolved=<n> deferred=<n> declined=<n>
  Status:     <pass | needs-clarification | needs-rewrite>
  Updated:    spec.md (revisions appended), clarifications.md (session appended)
  Next:       task-spec-plan <slug>   |   task-spec-clarify <slug> --all   |   manual rewrite
```

## Self-Check

- [ ] Loaded `behavioral-principles` and `speckit-detect` first
- [ ] Aborted cleanly if `spec.md` missing
- [ ] Drove questions from `spec-review`, not ad-hoc invention
- [ ] Stopped on `needs-rewrite` rather than Q&A around blockers
- [ ] One question at a time; verbatim answers
- [ ] `clarifications.md` append-only
- [ ] `spec.md` revision entry references `clarifications.md`
- [ ] Re-ran `spec-review` after updates
- [ ] In speckit mode, did not duplicate Spec Kit edits

## Avoid

- Inventing ambiguities to seem thorough.
- Batching questions.
- Editing `spec.md` without a revision entry.
- Silently resolving a conflict when the user's answer contradicts another section.
- Auto-looping `task-spec-clarify`.
