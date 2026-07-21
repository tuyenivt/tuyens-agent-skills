---
name: review-finding-verify
description: Second pass over draft review findings: confirm each against the code, attribute to the diff or pre-existing code, drop false positives.
metadata:
  category: review
  tags: [review, verification, false-positive, provenance, self-correction]
user-invocable: false
---

# Review Finding Verification

Second point of view over findings the review already drafted. The first pass reads as a reviewer looking for problems; this pass reads as the author defending the code, and keeps only what survives.

## When to Use

- After findings are assembled, before the report is written, in any `task-*-review*` workflow.
- Runs on every finding the workflow is about to publish, including findings merged back from sub-scope subagents.

Not for prior-round findings carried forward - `review-prior-findings-reconcile` owns those.

## Inputs

| Field           | Required | Source                                                                    |
| --------------- | -------- | ------------------------------------------------------------------------- |
| `findings`      | yes      | Draft findings, each with label, `file:line`, and claim                    |
| `diff`          | yes      | The diff already read by the workflow (`base...head`, or the incremental range) |
| `base_ref`      | yes      | From `review-precondition-check` handle - the pre-change side              |
| `head_ref`      | yes      | From `review-precondition-check` handle - the post-change side             |

When `findings` is empty, return the empty table and the tally `0 verified, 0 reattributed, 0 dropped`. Do not invent findings to verify.

## Rules

- **Verify against code, not against the diff summary.** Read the cited `file:line` at `head_ref` (`git show <head_ref>:<path>`). A finding whose claim does not match what the code actually does is a false positive - drop it. Cited code the diff itself deletes is also `Dropped` (evidence: `resolved by diff`) - removed code is not a false positive, but it is nothing to report either. No other verdict removes a finding.
- **Attribution is not validity.** Whether the diff introduced a problem and whether the problem is real are separate questions, resolved in that order: confirm the claim first, then attribute. Never drop a confirmed finding solely because the diff did not introduce it.
- **Attribute from evidence, not impression.** A finding is `Confirmed` (introduced by this diff) only when the cited construct appears in the diff's added lines. When the construct is unchanged, confirm with `git blame -L <line>,<line> <base_ref> -- <path>`; a commit older than the diff means `Pre-existing`, and blame that cannot resolve the path or line at `base_ref` means the construct postdates the base - `Confirmed`. `base_ref` is always the PR's original base, on incremental rounds too - code this PR added in an earlier round is `Confirmed`, never `Pre-existing`. Read-only git commands only.
- **Reachability changes severity, not existence.** A pre-existing defect the diff makes newly reachable, newly exploitable, or newly load-bearing stays at its original label and is attributed `Pre-existing (newly reachable)`. Name what the diff changed about its reachability.
- **De-escalate untouched pre-existing findings once, never below `[Recommend]`.** A `Pre-existing` finding on code the diff neither changed nor made newly reachable drops `[Must]` -> `[Recommend]`. It is context for the author, not a merge blocker for this PR. `[Recommend]` findings keep their label.
- **One verdict per finding.** Verdicts are `Confirmed`, `Pre-existing`, `Pre-existing (newly reachable)`, and `Dropped`. Preserve the original claim wording; this skill re-labels and annotates, it does not rewrite findings. Correcting a stale `file:line` (Step 1) is the one exception.
- **Uncertainty does not delete.** When the cited code cannot be read (path not in the repo, vendored, generated) or the claim cannot be settled either way, keep the finding at its drafted label with verdict `Confirmed` - the conservative default: what cannot be read is never de-escalated or dropped - and append `(unverified: <reason>)` both to its Evidence and to the published finding's inline annotation. Silence is not a false positive.

## Pattern

### Step 1 - Confirm the claim (POV: the author)

For each finding, read the cited code at `head_ref` and ask what an author defending this change would ask:

- Does the code actually do what the finding says it does?
- Is the fault already handled somewhere the first pass did not read - a guard clause, a caller-side check, a framework default, a decorator or middleware?
- Does the finding assume a call path that cannot occur?

A cited line that no longer holds the construct is usually a stale cite - the diff shifted lines. Search the file at `head_ref` for the claimed construct; when found, verify there and correct the finding's `file:line`. Only a construct found nowhere in the file is unsupported.

Claim unsupported -> `Dropped`, with the reason. Otherwise continue to Step 2.

```
Bad  - drafted:  [Must] handler.go:42 - user input reaches the query unvalidated
     - dropped after reading line 12: the router binds through a validated DTO; the claim is false

Good - drafted:  [Must] handler.go:42 - user input reaches the query unvalidated
     - confirmed: line 42 interpolates req.Filter, no validation between bind and query
```

### Step 2 - Attribute the finding

Locate the cited construct in the diff.

| Evidence at the cited line                                       | Verdict                          |
| ---------------------------------------------------------------- | -------------------------------- |
| Construct appears in the diff's added lines                       | `Confirmed`                      |
| Construct unchanged, but the diff changes how it can be reached: first live caller, untrusted data it never received before, guard removed, exposure widened | `Pre-existing (newly reachable)` |
| Construct unchanged and the diff does not change how it is reached | `Pre-existing`                    |

A finding split across changed and unchanged code (new call into an old unguarded helper) is `Pre-existing (newly reachable)`, cited at the unchanged defect with the new call site named as the trigger. Reachability must change in kind, not in count: one more caller passing data the construct already receives from existing paths leaves it `Pre-existing`.

### Step 3 - Apply the label adjustment

`Confirmed` and `Pre-existing (newly reachable)` keep their label. `Pre-existing` de-escalates `[Must]` to `[Recommend]` once. `Dropped` leaves the report.

Annotate every surviving non-`Confirmed` finding - and every unverified one - inline so the author sees provenance without opening git:

```
### [Recommend] auth/session.go:88 _(pre-existing)_
### [Must] auth/session.go:88 _(pre-existing; newly reachable via handler.go:42)_
### [Recommend] vendor/pool.go:88 _(unverified: path not in repo)_
```

## Output Format

```
| Finding | file:line | Verdict | Label | Evidence |
| ------- | --------- | ------- | ----- | -------- |
| <claim, abbreviated> | <path:line> | Confirmed \| Pre-existing \| Pre-existing (newly reachable) \| Dropped | <final label, or `-` when Dropped> | <what settled it: diff hunk, blame commit, or the guard that disproves it> |

<N> verified, <M> reattributed, <K> dropped
```

`N` counts `Confirmed` rows, `M` both `Pre-existing` verdicts, `K` `Dropped`. Consuming workflows publish only rows whose Verdict is not `Dropped`, carrying the `Label` column as the finding's label. The tally line goes in the report Summary as `Findings verified: <N> confirmed, <M> reattributed, <K> dropped`.

## Avoid

- Dropping a confirmed defect because the diff did not introduce it
- Treating "I could not verify it" as a false positive
- Re-deriving findings or adding new ones - this pass only rules on what it was given
- Re-running the first pass's checklists instead of reading the cited code
- De-escalating below `[Recommend]`, or de-escalating twice across rounds
- Attributing an incremental round against the prior round's head instead of the PR's original base
- State-changing git commands - `git show` and `git blame` are read-only
