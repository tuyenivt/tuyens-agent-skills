---
name: review-prior-findings-reconcile
description: Classify each finding from prior review report as Addressed, Still open, Obsolete, or Needs re-check by checking whether the specific smell persists.
metadata:
  category: review
  tags: [review, incremental, re-review, reconciliation, checkpoint]
user-invocable: false
---

# Prior Findings Reconciliation

## When to Use

- Round 2+ of a `task-*-review*` workflow when the prior `review-<branch>.md` report has valid checkpoint frontmatter.
- After the workflow has loaded the prior report content and computed the incremental diff range (`prior_head_sha...head_sha`).

Not for round 1 (no prior findings exist) or when `prior_checkpoint: legacy` (no parseable findings to reconcile).

## Inputs

The consuming workflow passes:

| Field            | Source                                                                  |
| ---------------- | ----------------------------------------------------------------------- |
| `prior_report`   | Full Markdown body of `review-<branch>.md` (frontmatter already parsed) |
| `incremental_diff` | Output of `git diff <prior_head_sha>...<head_sha>` (already read)      |
| `name_status`    | Output of `git diff --name-status <prior_head_sha>...<head_sha>`        |
| `head_files`     | Optional. File list at the new head: output of `git ls-tree -r --name-only <head_ref>`. Cross-check deleted/renamed paths; when absent, `name_status` alone decides touch state. |

To read file content at the new head (Steps 3-4), use `git show <head_sha>:<path>` - after the workflow's auto-fetch, `head_sha` may not be the checked-out working tree.

## Rules

- **Reconciliation is binary per finding: is the specific smell at the cited location still present?** Yes -> `Still open`. No -> `Addressed`. Cannot tell -> `Needs re-check`. File or symbol gone -> `Obsolete`.
- **A fix attempt that does not remove the cited smell is `Still open`**, regardless of whether the file was touched. The commenter may have been addressing another reviewer's feedback or doing unrelated work; only the smell itself decides.
- **Do not infer causation.** Never link a new finding to a prior one (no "Addressed-incorrectly", no "regression introduced by fix"). New smells appear in the workflow's New Findings section with no back-reference.
- **Parse every row under the prior report's `## High-Impact Findings` heading**, regardless of label (`[Must]`, `[Recommend]`, `[Question]`, `[Blocker]`, `[High]`, `[Suggestion]`). A `[Suggestion]` row placed inside High-Impact is still in scope. Architecture / Maintainability sections are not - they carry over implicitly via the next round's full Phase E pass on touched files.
- **Treat `[Question]` rows as a smell defined by the answer the reviewer expected.** Reduce the question to its implicit smell ("Why X instead of Y?" -> "X used where Y expected"). Same Addressed / Still open / Obsolete / Needs re-check decision as any other row.
- **One row per prior finding.** Preserve original severity label and `file:line` exactly as written in the prior report.

## Pattern

### Step 1 - Extract prior findings

Parse the prior report's `## High-Impact Findings` section. Each finding has a heading like `### [<Label>] file:line`. Accept both label vocabularies:

- **Current (intent-based):** `[Must]`, `[Recommend]`, `[Question]`
- **Legacy (severity-based):** `[Blocker]`, `[High]`, `[Suggestion]`, `[Nitpick]`, `[Praise]`

Collect `(label, file, line, smell_summary)` where `label` is preserved **verbatim** as it appeared in the prior report (do not translate `[Blocker]` to `[Must]` - the reconciliation table reflects what was actually written). `smell_summary` is the first sentence of the `Issue:` or `Improvement:` line.

If the section is empty or absent, return an empty reconciliation table and stop.

### Step 2 - Determine file touch state

For each prior finding, check `name_status`:

| `name_status` entry for the file | Touch state |
| -------------------------------- | ----------- |
| `A` (added since prior round)    | Impossible for a prior finding; treat as `Needs re-check` and note. |
| `M` (modified)                   | `touched` |
| `D` (deleted)                    | `file-gone` |
| `R<score>` (renamed)             | `renamed` - record new path |
| not listed                       | `untouched` |

### Step 3 - Classify per finding

| Touch state | Classification logic                                                                                                                                                              |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `untouched` | `Still open`. No file read needed - the smell at `file:line` cannot have changed if the file was not modified. Note: line number references the prior commit; current line may differ if other commits shifted things, but the smell persists at the same logical site. |
| `touched`   | Read the file at the new head (`git show <head_sha>:<path>`). Search for the specific smell described in the prior finding. Present -> `Still open`. Absent -> `Addressed`. If the surrounding code restructured enough that presence cannot be determined without speculation -> `Needs re-check`. |
| `renamed`   | Treat as `touched`; reconcile against the new path. Record original and new path in the row.                                                                                       |
| `file-gone` | `Obsolete`. Note in the row.                                                                                                                                                       |

### Step 4 - Smell-presence check (for touched files)

This is the only judgment-heavy step. The prior finding cites a named smell (e.g., `@Transactional self-invocation`, `N+1 in listAll`, `missing @PreAuthorize`, `hardcoded credential`). Use the smell summary plus the file content at the new head:

- **Specific tokens** (annotations, function names, literal values): grep at the file level. Present -> `Still open`. Absent -> `Addressed`.
- **Behavioral smells** (N+1, race condition, transaction misuse): inspect the relevant section of the file. If the pattern that produced the prior finding is structurally still there -> `Still open`. If the code was refactored such that the pattern no longer applies -> `Addressed`. If you cannot decide without running the code -> `Needs re-check`.
- **Do not check whether the fix is correct.** A wrong-but-it-removed-the-smell change is still `Addressed`. New problems introduced by that change surface as new findings in the workflow's regular Phase A-E pass; they are not this skill's concern.

## Output Format

Emit a single Markdown table - this is what the workflow inserts under `## Prior Round Reconciliation` in the round-2+ report.

```markdown
| Round N-1 Finding                          | file:line                | Status         | Notes                          |
| ------------------------------------------ | ------------------------ | -------------- | ------------------------------ |
| [Must] @Transactional self-invocation      | OrderService.java:42     | Addressed      |                                |
| [Must] Missing @PreAuthorize               | AdminController.java:15  | Still open     | File touched (other changes); smell persists. |
| [Recommend] N+1 in listAll                 | ProductRepo.java:88      | Still open     | File untouched.                |
| [Blocker] Hardcoded credential             | Legacy.java:12           | Addressed      | Legacy label preserved verbatim from round 1. |
| [Recommend] Race on counter                | TallyService.java:31     | Needs re-check | File restructured; verify manually. |
```

Status column is one of exactly: `Addressed`, `Still open`, `Obsolete`, `Needs re-check`. Notes column is optional per row; keep to one short sentence.

Labels in the first column appear **exactly as they were in the prior report**. If round 1 used the legacy severity vocabulary (`[Blocker]`, `[High]`, `[Suggestion]`), those rows keep those labels; round-2 *new* findings use the current intent vocabulary (`[Must]`, `[Recommend]`, `[Question]`). Mixing in one report during the transition is expected and correct.

After the table, emit a one-line tally the workflow uses for the Round History row:

```
Reconciliation: <addressed_count> addressed, <still_open_count> still open, <obsolete_count> obsolete, <needs_recheck_count> needs re-check.
```

## Avoid

- Inventing `Addressed-incorrectly` or any "fix is wrong" status - that conflates reconciliation with new-finding detection.
- Linking new smells back to prior findings - they are independent.
- Reconciling Suggestions or notes from Architecture / Maintainability sections - only the `## High-Impact Findings` section.
- Re-reading the file when the touch state is `untouched` - wastes tokens, the answer is `Still open`.
- Speculating when restructuring makes the smell's presence unclear - mark `Needs re-check` and move on.
- Changing the original label or `file:line` text - preserve exactly so the user can compare rounds at a glance.
- Translating legacy severity labels (`[Blocker]`/`[High]`/`[Suggestion]`) into intent labels (`[Must]`/`[Recommend]`) when surfacing prior findings - the table shows what was actually written.
