---
name: review-prior-findings-reconcile
description: Classify each finding from prior review report as Addressed, Still open, Obsolete, or Needs re-check by checking whether the specific smell persists.
metadata:
  category: review
  tags: [review, re-review, reconciliation, checkpoint]
user-invocable: false
---

# Prior Findings Reconciliation

## When to Use

- Round 2+ of a `task-*-review*` workflow when the prior `review-<head>.md` report has valid checkpoint frontmatter.
- After the workflow has loaded the prior report content and read the full `base_ref...head_ref` diff. Every round analyzes the whole PR range, so reconciliation compares prior findings against the current head, not against a slice of commits since the prior round.

Not for round 1 (no prior findings exist) or when `prior_checkpoint: legacy` (no parseable findings to reconcile).

## Inputs

The consuming workflow passes:

| Field            | Source                                                                  |
| ---------------- | ----------------------------------------------------------------------- |
| `prior_report`   | Full Markdown body of `review-<head>.md` (frontmatter already parsed) |
| `diff`           | Output of `git diff <base_ref>...<head_ref>` (already read) - the full PR range |
| `name_status`    | Output of `git diff --name-status <base_ref>...<head_ref>` - the same full range |
| `head_sha`       | `git rev-parse <head_ref>` - every file read in Steps 2-4 uses `git show <head_sha>:<path>` (after the workflow's auto-fetch the checked-out tree may differ) |
| `head_files`     | Optional. `git ls-tree -r --name-only <head_sha>`. When absent, probe a single path with `git cat-file -e <head_sha>:<path>`. |

## Rules

- **Reconciliation is binary per finding: is the specific smell at the cited site still present?** The site is the logical construct the prior line pointed at (the function, the annotation position), not the literal line number - lines shift; a shifted line is noted, the cited `file:line` stays verbatim. Yes -> `Still open`. No -> `Addressed`. Cannot tell -> `Needs re-check`. File gone, or the row carries no smell -> `Obsolete`.
- **A fix attempt that does not remove the cited smell is `Still open`**, regardless of whether the file was touched. The commenter may have been addressing another reviewer's feedback or doing unrelated work; only the smell itself decides.
- **Do not infer causation.** Never link a new finding to a prior one (no "Addressed-incorrectly", no "regression introduced by fix"). New smells appear in the workflow's New Findings section with no back-reference.
- **Parse every row under the prior report's `## High-Impact Findings` heading**, whatever its label. Architecture / Maintainability sections are not - they carry over implicitly via the next round's full Phase E pass on touched files.
- **Treat `[Question]` rows as a smell defined by the answer the reviewer expected.** Reduce the question to its implicit smell ("Why X instead of Y?" -> "X used where Y expected"). Same Addressed / Still open / Obsolete / Needs re-check decision as any other row.
- **One row per prior finding.** Preserve original severity label and `file:line` exactly as written in the prior report.

## Pattern

### Step 1 - Extract prior findings

Parse the prior report's `## High-Impact Findings` section, matching the heading by prefix so decorations like a count suffix (`## High-Impact Findings (3)`) still match - an exact-string match would silently discard every prior finding over a cosmetic difference. Each finding has a heading like `### [<Label>] file:line`. Every row is parsed whatever its label, and the label is preserved verbatim, never translated. The recognised vocabulary is current `[Must]`, `[Recommend]` and legacy `[Blocker]`, `[High]`, `[Suggestion]`, `[Nitpick]`, `[Question]`, `[Praise]`; an unrecognised label is parsed like any other and noted `unrecognised label` in the row. `[Praise]` rows carry no smell: classify `Obsolete` with note `praise - nothing to reconcile`; never carry them forward. A count suffix that disagrees with the rows parsed is noted after the table (`heading says 8, 9 rows parsed`).

Collect `(label, file, line, smell_summary, provenance)` where `smell_summary` is a noun phrase naming the smell, drawn from the `Issue:` or `Improvement:` line (`check-then-act idempotency`, not the full sentence), and `provenance` is the heading's `_(pre-existing)_` annotation when present.

If the section is present but empty, emit the empty table and the zeroed tally. If no heading matches at all, emit the empty table, the note line ``Prior report has no High-Impact Findings section (found: <the report's ## headings, comma-separated>); nothing reconciled``, and the zeroed tally - a report that should have had findings and a report that genuinely had none look identical otherwise.

### Step 2 - Determine file touch state

For each prior finding, check `name_status`. It spans the full `base_ref...head_ref` range, so touch state answers "does this PR change the file at all", not "did the author change it since the prior round":

| `name_status` entry for the file | Touch state |
| -------------------------------- | ----------- |
| `A` (added by this PR)           | `touched` - the PR created the file, so a prior finding on it is ordinary, not a contradiction |
| `M` (modified) / `T` (type changed) | `touched` |
| `D` (deleted)                    | `file-gone` - but when exactly one `A` row in `name_status` has the same basename (an undetected `D`+`A` move), treat as `renamed` to that path; with several `A` candidates, `ambiguous-move` |
| `R<score>` (renamed)             | `renamed` - record new path |
| not listed, and the path exists at `head_sha` | `untouched` - the PR does not touch this file at all, which is normal for a finding attributed to pre-existing code |
| not listed, absent at `head_sha`, present at `base_ref` (`git cat-file -e <base_ref>:<path>`) | impossible - a file present at base and absent at head is a `D` row; re-check the inputs |
| not listed, absent at `head_sha` and at `base_ref`, and the path appears in the PR's commit history (`git log --diff-filter=A -- <path>` over the range) | `pr-internal` - the file existed only inside the PR (added and removed within the range, so it never reaches `name_status`) |
| not listed, absent at `head_sha` and at `base_ref`, never in the range's history | `unknown-path` - the prior report cited a path that never existed |

### Step 3 - Classify per finding

| Touch state   | Classification logic                                                                                                                                                              |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `untouched`   | Split on provenance. Annotated `_(pre-existing)_`: `Still open`, no file read needed - the PR still does not touch the code carrying the smell (line numbers may have shifted; the logical site persists). Not annotated (the PR introduced it): the file now matches base, so the change that carried the smell was reverted - `Addressed` with note `reverted to base state`. |
| `pr-internal` | `Obsolete` with note `file existed only inside the PR; a relocated smell is the new-findings pass's to find`. |
| `ambiguous-move` | `Needs re-check` with the candidate paths in Notes. |
| `unknown-path` | `Needs re-check` with note `path not found at base or head; verify the cited location`. |
| `touched`     | Read the file at `head_sha`. Search for the specific smell described in the prior finding. Present -> `Still open`. Absent -> `Addressed`. If the surrounding code restructured enough that presence cannot be determined without speculation -> `Needs re-check`. |
| `renamed`     | Treat as `touched`; reconcile against the new path. Record original and new path in the row.                                                                                       |
| `file-gone`   | `Obsolete`. Note in the row.                                                                                                                                                       |

### Step 4 - Smell-presence check (for touched files)

This is the only judgment-heavy step. The prior finding cites a named smell (e.g., `@Transactional self-invocation`, `N+1 in listAll`, `missing @PreAuthorize`, `hardcoded credential`). Use the smell summary plus the file content at the new head:

- **Specific tokens** (annotations, function names, literal values): look for the token at the cited site (the same function or construct, wherever it now sits in the file). Present -> `Still open`. Absent -> `Addressed`. For absence smells (`missing @PreAuthorize`, `no rate limit`), the greppable token belongs to the fix, so the mapping inverts: construct now present at the cited site -> `Addressed`, still absent -> `Still open`.
- **Behavioral smells** (N+1, race condition, transaction misuse): inspect the relevant section of the file. If the pattern that produced the prior finding is structurally still there -> `Still open`. If the code was refactored such that the pattern no longer applies -> `Addressed`. If you cannot decide without running the code -> `Needs re-check`.
- **Do not check whether the fix is correct.** A wrong-but-it-removed-the-smell change is still `Addressed`. New problems introduced by that change surface as new findings in the workflow's regular Phase A-E pass; they are not this skill's concern.

## Output Format

Emit a single Markdown table, then the tally line - this is what the workflow inserts under its own `## Prior Round Reconciliation` heading in the round-2+ report; the heading is the workflow's, not part of this output. Paths are repo-relative, as `name_status` prints them.

```markdown
| Round N-1 Finding                          | file:line                | Status         | Notes                          |
| ------------------------------------------ | ------------------------ | -------------- | ------------------------------ |
| [Must] @Transactional self-invocation      | src/main/java/acme/order/OrderService.java:42 | Addressed |                     |
| [Must] Missing @PreAuthorize               | src/main/java/acme/admin/AdminController.java:15 | Still open | File touched (other changes); smell persists. |
| [Recommend] N+1 in listAll                 | src/main/java/acme/catalog/ProductRepo.java:88 | Still open | File untouched; prior finding marked pre-existing. |
| [Blocker] Hardcoded credential             | src/main/java/acme/legacy/Legacy.java:12 | Addressed | Legacy label preserved verbatim from round 1. |
| [Recommend] Race on counter                | src/main/java/acme/tally/TallyService.java:31 | Needs re-check | File restructured; verify manually. |
| [Must] Missing rate limit                  | api/Gateway.java:60 -> edge/Gateway.java:60 | Still open | Renamed since round 1. |

Reconciliation: 2 addressed, 3 still open, 0 obsolete, 1 needs re-check.
```

Status column is one of exactly: `Addressed`, `Still open`, `Obsolete`, `Needs re-check`. Notes column is optional per row; keep to one short sentence. An empty result is the header row, the Step 1 note line when one applies, and `Reconciliation: 0 addressed, 0 still open, 0 obsolete, 0 needs re-check.`

A renamed file's cell carries `<prior path>:<line> -> <new path>:<line>`, preserving the prior path and line verbatim on the left so rounds stay comparable while the reader sees where the code lives now. The right-side line is where the smell check landed at the new path - the cited construct's current line, or for absence smells the site inspected; repeat the prior line only when no such line can be pinned.

`Still open` and `Needs re-check` rows are unresolved: the workflow carries them into the round's `## High-Impact Findings` so the next round reconciles them again. `Addressed` and `Obsolete` rows are settled and appear only in this table.

Labels in the first column appear **exactly as they were in the prior report**. Round-2 *new* findings use the current intent vocabulary (`[Must]`, `[Recommend]`); mixing in one report during the transition is expected and correct.

## Avoid

- Inventing `Addressed-incorrectly` or any "fix is wrong" status - that conflates reconciliation with new-finding detection.
- Linking new smells back to prior findings - they are independent.
- Reconciling rows from the Architecture / Maintainability sections - only rows under `## High-Impact Findings`, whatever their label.
- Reading file content for an `untouched` finding - the classification keys on the provenance annotation and the path's existence at head, never on content.
- Speculating when restructuring makes the smell's presence unclear - mark `Needs re-check` and move on.
- Changing the original label or `file:line` text - preserve exactly so the user can compare rounds at a glance.
