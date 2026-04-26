---
name: task-spec-clarify
description: Resolve ambiguities in an existing `spec.md` before planning. Runs `spec-review` to surface a structured findings list, asks the user the resulting questions, appends Q&A to `clarifications.md`, and updates `spec.md` with revisions. Speckit-aware - delegates to `/speckit.clarify` when Spec Kit is installed.
metadata:
  category: spec
  tags: [spec, sdd, clarify, ambiguity, requirements]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spec - Clarify

Re-reads an existing `spec.md`, identifies ambiguous, conflicting, missing, or unmeasurable requirements, and works with the user to resolve them. Produces a `clarifications.md` Q&A log and a revised `spec.md`. The structured findings list is the high-value output - it converts vague feedback ("the spec feels incomplete") into a punch list the user can answer one item at a time.

## When to Use

- After `task-spec-specify` reports open questions or uncertainty
- When `task-spec-plan` or downstream phases stall because the spec is ambiguous
- When the spec has aged and a fresh pass will surface drift between text and current intent
- Before a feature handoff between contributors, to ensure shared understanding

**Not for:** Authoring a spec from scratch (use `task-spec-specify`), reviewing code (use `task-code-review`), architectural decision-making (use `task-spec-plan`).

## Inputs

- The feature slug (required) - the workflow reads `.specs/<slug>/spec.md`
- Optional scope: `--blockers-only` to ask only about `blocker`-severity findings; default asks blockers + majors
- Optional `--non-interactive` for environments where the workflow should produce the findings list and stop without Q&A

**Insufficient input handling:** If no slug is provided, list available slugs under `.specs/` and ask which one. If the slug exists but has no `spec.md`, stop and suggest `task-spec-specify` instead.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Artifact Paths

Use skill: spec-artifact-paths

Capture `spec` and `clarifications` paths and their existence flags. If `spec.md` does not exist, abort with a clear message recommending `task-spec-specify`.

### STEP 4 - Branch on Mode

#### Mode: speckit-installed

1. Pre-process: read `spec.md` and run `Use skill: spec-review` to produce a findings list.
2. Delegate by instructing the user to run `/speckit.clarify` (or invoke it programmatically). Spec Kit owns the Q&A log and spec updates.
3. Post-process: re-run `spec-review` after `/speckit.clarify` completes. If new findings remain, surface them as residual gaps; do not loop automatically.
4. Skip to STEP 8.

#### Mode: standalone

Continue to STEP 5.

### STEP 5 - Review the Spec

Use skill: spec-review

Capture the findings list. Filter by the requested scope:

| Scope flag        | Findings asked about          |
| ----------------- | ----------------------------- |
| (default)         | `blocker` + `major`           |
| `--blockers-only` | `blocker` only                |
| `--all`           | `blocker` + `major` + `minor` |

If `summary.status == pass` (no blockers, no majors), print a short "spec looks clean at requested scope" message and skip to STEP 8 - do not invent questions to fill space.

If `summary.status == needs-rewrite` (any blocker), present the blockers and stop. Recommend the user either restructure the spec manually or re-run `task-spec-specify` in amend mode. Do not attempt Q&A on a spec that has structural blockers.

### STEP 6 - Ask, Capture, Resolve

For each finding in the filtered list, in severity order (blockers first, then majors, then minors):

1. Read the finding's `location`, `excerpt`, and `suggested_clarification`.
2. Ask the user the suggested clarification question (or a refined version if context allows). One question at a time. Do not batch.
3. Record the answer verbatim in memory.
4. If the answer reveals a conflict with another part of the spec, surface it immediately rather than appending silently.
5. If the user defers an item ("don't know yet", "skip"), mark it as `deferred` and keep it in `Open Questions` rather than removing it.

In `--non-interactive` mode, skip the asking and emit the findings list as the workflow output without modifying any files.

### STEP 7 - Write clarifications.md and Update spec.md

**`clarifications.md`** - append-only Q&A log. Never delete prior entries.

```markdown
# Clarifications - <Feature Name>

## Session <YYYY-MM-DD HH:MM>

- **Q1 (F-001, location: <location>):** <question>
  **A:** <user's answer verbatim>
  **Disposition:** resolved | deferred | declined

- **Q2 (F-002, ...):** ...
```

If `clarifications.md` does not yet exist, create it with a top-level header. If it does exist, append a new `## Session <timestamp>` block.

**`spec.md`** - apply each `resolved` answer to the corresponding section. Then append a `## Revisions` entry summarizing what changed:

```markdown
- <YYYY-MM-DD>: Resolved <N> findings via task-spec-clarify session. Updated sections: <list>. (See clarifications.md for Q&A.)
```

Bump the `Last updated` field at the top.

For `deferred` items, ensure they are present in the `Open Questions` section of `spec.md` (add if missing, do not duplicate). For `declined` items, leave the spec untouched and note the decline in the revision entry.

### STEP 8 - Re-Review and Summarize

Run `Use skill: spec-review` once more on the updated `spec.md`. Print a short summary:

- Findings asked, resolved, deferred, declined
- New `summary.status` after the pass
- If `status` is still `needs-clarification`, recommend another `task-spec-clarify` run
- If `status == pass`, recommend `task-spec-plan <slug>` as the next command

## Output Format

The workflow produces (or updates) two artifacts and prints a chat summary.

**Chat summary:**

```
Spec clarify - <slug> (<mode>)
  Findings:   asked=<n> resolved=<n> deferred=<n> declined=<n>
  Status:     <pass | needs-clarification | needs-rewrite>
  Updated:    spec.md (revisions appended), clarifications.md (session appended)
  Next:       task-spec-plan <slug>   |   task-spec-clarify <slug> --all   |   manual rewrite
```

## Self-Check

- [ ] Loaded `behavioral-principles` and `speckit-detect` before any other work
- [ ] Aborted cleanly if `spec.md` did not exist (recommended `task-spec-specify` instead)
- [ ] Used `spec-review` to drive the question list - did not invent ad-hoc ambiguities
- [ ] Stopped on `needs-rewrite` status rather than papering over blockers with Q&A
- [ ] Asked questions one at a time; recorded answers verbatim
- [ ] `clarifications.md` is append-only - prior sessions preserved
- [ ] `spec.md` revision entry summarizes the change and references `clarifications.md`
- [ ] Deferred items remain in `Open Questions`; declined items left spec untouched with revision note
- [ ] Re-ran `spec-review` after updates and reported new status
- [ ] In speckit-installed mode, did not duplicate Spec Kit's edits

## Avoid

- Inventing ambiguities to seem thorough - a clean spec is a valid outcome
- Asking multiple questions in one prompt - one finding at a time keeps answers crisp
- Editing `spec.md` without a revision entry - the audit trail is the point
- Resolving conflicts silently when the user's answer contradicts another part of the spec
- Looping `task-spec-clarify` automatically - the user decides when to run it again
- Treating `minor` findings as urgent - default scope is blocker + major

## Notes

- `clarifications.md` accumulates across sessions. It is the durable record of how the spec evolved.
- A spec that needs another clarify pass after one round is normal - complex features often take 2-3 rounds before `status: pass`.
- If the user repeatedly defers the same finding, that is a signal the requirement is genuinely undecided and probably belongs in `Out of Scope` for the current iteration.
