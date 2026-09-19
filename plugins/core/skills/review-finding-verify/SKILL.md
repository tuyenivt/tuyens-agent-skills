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
- Runs on every newly drafted finding the workflow is about to publish, including findings merged back from sub-scope subagents.

Not for prior-round findings carried forward - `review-prior-findings-reconcile` owns those.

## Inputs

| Field           | Required | Source                                                                    |
| --------------- | -------- | ------------------------------------------------------------------------- |
| `findings`      | yes      | Draft findings, each with label, `file:line`, and claim                    |
| `diff`          | yes      | The diff already read by the workflow (`base...head`) |
| `base_ref`      | yes      | From `review-precondition-check` handle - the PR's original base, on every round |
| `head_ref`      | yes      | From `review-precondition-check` handle - the post-change side             |

When `findings` is empty, return the empty table and the tally `0 verified, 0 reattributed, 0 unverified, 0 dropped`. Do not invent findings to verify. Every judgement compares `head_ref` with `base_ref`; intermediate commits inside the range (including a prior round's head) are never the reference, so a defect introduced and fixed inside the range never held at `base_ref`.

## Rules

- **Verify against code, not against the diff summary.** Read the cited `file:line` at `head_ref` (`git show <head_ref>:<path>`). A claim that does not hold at `head_ref` is `Dropped`: `resolved by diff` when it held at `base_ref` and the diff removed or corrected the construct (a deleted line, a constraint the diff added), otherwise `false positive`; the reason opens the row's Evidence. No other verdict removes a finding.
- **Absence claims are verified by reading the definition, not by a failed search.** A finding that something is missing - no validation, no guard, a field that does not exist, a case not handled - is confirmed only by reading the construct that would hold it: the DTO or model where the field would be declared, the middleware chain the route passes through, the switch that would carry the case - in whichever file defines it. "I searched for the name and found nothing" is not evidence. When the defining construct cannot be located, the claim is `Unverified`. Reachability is judged by tracing the construct's callers across the repository, not only the files the finding names.
- **Attribution is not validity.** Whether the diff introduced a problem and whether the problem is real are separate questions, resolved in that order: confirm the claim first, then attribute. Never drop a confirmed finding solely because the diff did not introduce it.
- **Reachability changes attribution, not the label.** A pre-existing defect the diff makes newly reachable, newly exploitable, or newly load-bearing keeps its label and is attributed `Pre-existing (newly reachable)`. Name what the diff changed about its reachability.
- **De-escalate untouched pre-existing findings once, never below `[Recommend]`.** A `Pre-existing` finding on code the diff neither changed nor made newly reachable drops `[Must]` -> `[Recommend]`. It is context for the author, not a merge blocker for this PR. Severity of the defect does not exempt it - a crash or vulnerability the PR did not introduce and did not make newly reachable still de-escalates, because blocking this PR would not fix it. The label tracks "must fix before merging this," not "how bad is it."
- **One verdict per finding.** Verdicts are `Confirmed`, `Pre-existing`, `Pre-existing (newly reachable)`, `Unverified`, and `Dropped`. The published finding keeps its drafted claim wording; the table's Finding column abbreviates it. A claim whose defect is real but whose stated mechanism is wrong keeps its verdict and gets the actual mechanism in Evidence and in the annotation (`_(mechanism: <actual>)_`, the one annotation a `Confirmed` row can carry); a claim with no defect behind it is `Dropped`.
- **Uncertainty does not delete.** When the cited code cannot be read (path not in the repo, generated), the construct that would settle the claim lives outside the tree (a schema for a missing index, an infra manifest, a package the repo only depends on), or the claim cannot be settled either way, the verdict is `Unverified`: the finding keeps its drafted label and is published with `_(unverified: <reason>)_`. An in-tree document that states the out-of-tree fact (a deploy manifest mirrored into the repo) is evidence for what it states. Blame on a related line attributes the code that is present; it does not confirm an absence.

## Pattern

### Step 1 - Confirm the claim (POV: the author)

For each finding, read the cited code at `head_ref` and ask what an author defending this change would ask:

- Does the code actually do what the finding says it does?
- Is the fault already handled somewhere the first pass did not read - a guard clause, a caller-side check, a framework default, a decorator or middleware?
- Does the finding assume a call path that cannot occur?

A cited line that no longer holds the construct is usually a stale cite - the diff shifted lines. Search the cited file, then the construct's defining file, at `head_ref`; when found, verify there, correct the finding's `file:line` (across files if needed), and open the row's Evidence with `cite corrected from <old>;`. A claim that names a present token (`FOR UPDATE` without `SKIP LOCKED`) is corrected to that token's line; an absence claim cited anywhere inside the construct that would hold the missing thing keeps its drafted line.

Claim contradicted by the code -> `Dropped`, with the reason. Construct that would settle the claim not locatable or not readable -> `Unverified`, skip Step 2. Otherwise continue to Step 2.

```
Dropped (false positive) - drafted:  [Must] handler.go:42 - user input reaches the query unvalidated
                           `r.Use(validate.Body[SearchReq])` (router.go:12) - validation middleware runs before the handler

Confirmed                - drafted:  [Must] handler.go:42 - user input reaches the query unvalidated
                           `query := "SELECT ... WHERE " + req.Filter` (handler.go:42) - no validation call between bind and query
```

### Step 2 - Attribute the finding

| Evidence                                                                   | Verdict                          |
| -------------------------------------------------------------------------- | -------------------------------- |
| The claim names an acceptance criterion or states that something requested was not delivered (`review-change-intent` findings, or a paraphrase) - the gap is what the change failed to add, whatever the anchored line's age | `Confirmed`                      |
| Construct appears in the diff's added lines                                | `Confirmed`                      |
| Construct unchanged and older than the base, and the diff changes how it can be reached: first live caller, untrusted data it never received before, guard removed, exposure widened, a config it depends on made load-bearing | `Pre-existing (newly reachable)` |
| Construct unchanged and older than the base, and the diff does not change how it is reached | `Pre-existing`                    |

Age test for an unchanged line: `git blame -L <n>,<n> <head_ref> -- <path>` gives commit `C`; `git merge-base --is-ancestor C <base_ref>` succeeding means the line predates the base (a commit merged in from upstream is such an ancestor and stays `Pre-existing`), failing means the PR range introduced it (`Confirmed`). When the diff shows the file as added (`A`), blame with `-C -C` so content moved in by the creating commit keeps its original commit. Read-only git commands only.

A finding split across changed and unchanged code (new call into an old unguarded helper) is `Pre-existing (newly reachable)`, cited at the unchanged defect with the new call site named as the trigger. Reachability must change in kind, not in count: one more caller passing data the construct already receives from existing paths leaves it `Pre-existing`.

### Step 3 - Apply the label adjustment

`Confirmed`, `Pre-existing (newly reachable)`, and `Unverified` keep their label. `Pre-existing` de-escalates `[Must]` to `[Recommend]` once. `Dropped` leaves the report.

Every surviving non-`Confirmed` finding carries an inline annotation so the author sees provenance without opening git; it is written in the table's Annotation column and appended to the published heading (`Confirmed` rows write `-`, or the mechanism annotation above):

```
### [Recommend] auth/session.go:88 _(pre-existing)_
### [Must] auth/session.go:88 _(pre-existing; newly reachable via handler.go:42)_
### [Recommend] vendor/pool.go:88 _(unverified: path not in repo)_
```

## Output Format

```
| Finding | file:line | Verdict | Label | Annotation | Evidence |
| ------- | --------- | ------- | ----- | ---------- | -------- |
| <claim, abbreviated> | <path:line> | Confirmed \| Pre-existing \| Pre-existing (newly reachable) \| Unverified \| Dropped | <final label, or `-` when Dropped> | <`_(...)_` text to publish, or `-`> | <quoted code plus what it settles> |

<N> verified, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}
```

`N` counts `Confirmed` rows, `M` both `Pre-existing` verdicts, `U` `Unverified`, `K` `Dropped`. The parenthetical splits `K` and is omitted when `K` is 0. Consuming workflows publish only rows whose Verdict is not `Dropped`, carrying the `Label` and `Annotation` columns. The tally line goes in the report Summary as `Findings verified: <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`.

The table holds one row per finding received, `Dropped` rows included - it is the audit trail of what was ruled on. Two findings that resolve to the same `file:line` stay separate rows when they make different claims; exact duplicates (the same claim at the same line, merged from two subagents) collapse to one row and count once. When every finding drops, emit the full table and the tally with `N`, `M`, `U` at zero.

**Evidence is quoted code plus what it settles.** Every row cites source read at the relevant ref: the verbatim line the finding turns on, or - for an absence claim - the construct that would hold the missing thing, quoted at the point where it is absent. Then one clause on what that text settles, never a restatement of the claim. `Dropped` rows open with `false positive:` or `resolved by diff:` (the tally's `F`/`R` are counted from these); `resolved by diff` rows quote the base-side line the diff removed; `Unverified` rows carry the reason alone.

```
Confirmed      | `query := "SELECT ... WHERE " + req.Filter` (search.go:42) - value interpolated after bind, no validation call between
Confirmed      | `type ExportReq struct { Filter string }` (dto.go:8) - absence read at the declaring struct, no validate tag and no middleware on its route
Pre-existing   | `session.Refresh(tok)` (session.go:88), blame a1b2c3d predates base - diff adds no caller of it
Dropped        | false positive: `r.Use(validate.Body[SearchReq])` (router.go:12) - validation middleware runs before the handler
```

## Avoid

- Dropping a confirmed defect because the diff did not introduce it
- Treating "I could not verify it" as a false positive
- Re-deriving findings or adding new ones - this pass only rules on what it was given
- Re-running the first pass's checklists instead of reading the cited code
- De-escalating below `[Recommend]`
- Attributing a round 2+ review against the prior round's head instead of the PR's original base
- State-changing git commands - `git show` and `git blame` are read-only
