---
name: review-change-intent
description: Check a change against its stated requirement: change brief, acceptance-criteria traceability, unmet criteria, unrequested scope.
metadata:
  category: review
  tags: [review, requirements, acceptance-criteria, traceability, scope, pull-request]
user-invocable: false
---

# Review Change Intent

Reconstructs what the change was asked to do and what it actually delivered, before any defect hunting. Acceptance criteria decide what counts as a defect downstream, so this runs first.

## When to Use

- Phase 0 of an umbrella review (`task-code-review` generic fallback, every `task-<stack>-review`), after the diff resolves and before risk scoring.
- Runs even when the low-risk short-circuit fires: an unmet criterion or an unrequested schema change is what a small, low-risk-looking diff hides.

Not for single-lens reviews (`*-review-perf` / `-security` / `-observability` / `-reliability`) - they judge one dimension of how the change is built, not whether it is the change that was asked for.

## Inputs

| Field                | Required | Source                                                                       |
| -------------------- | -------- | ---------------------------------------------------------------------------- |
| `diff`               | yes      | `git diff <base_ref>...<head_ref>` - the full PR range, on every round |
| `commit_log`         | yes      | `git log <base_ref>..<head_ref>` over the same range                         |
| `requirement_source` | no       | `--req <path>` forwarded by the workflow, or requirement text already in context |
| `prior_report_path`  | no       | `review-target.report_path` from the precondition handle, when round > 1     |

Repository context outside these inputs (deploy plans, architecture docs) may inform Watch points and may be cited there by path; it becomes a traceability source only when the diff, commit log, or context names it (source row 3).

## Rules

- **Never derive criteria from the diff.** Reading requirements off the change is circular and always concludes the change meets them. With no qualifying source, emit the Change Brief and omit the traceability block entirely.
- **A source qualifies only when it enumerates at least one criterion stating an observable outcome.** A commit subject (`fix pagination`), a branch name, or prose with no sentence stating an observable outcome is Brief material, not traceability material - without this bar the commit log makes every review look sourced. In a qualifying prose source, each sentence stating one observable outcome is one criterion, two sentences stating the same outcome are one criterion quoted at the more precise wording, a criterion that states an outcome and defers a further part is two rows (the outcome, and a `Deferred` row for the deferred part), and sentences stating no outcome are Brief material (the `Untraceable` status is for enumerated criteria only).
- **`Met` requires two anchors: an implementation `file:line` and a proof.** Exactly one anchor is `Partial`, unless the implementation contradicts the stated outcome (`Unmet`). The implementation is never its own proof.
- **Anchors may cite unchanged code**, annotated `(pre-existing)`. A criterion the system already satisfied is `Met`, and the annotation tells the reader this change is not what satisfied it.
- **Disclose source authority, never infer it.** `Specified` = written independently of the change. `Self-attested` = written by the author alongside it (pasted PR body, commit messages). Self-attested criteria still gate - a change that does not do what its own description claims is a defect - but the reader is told which kind they are reading. A self-attested statement never changes the status of a Specified criterion: a PR body deferring a criterion the spec still requires never makes it `Deferred` - it keeps the status its anchors give, with the claimed deferral recorded under Watch points.
- **Describe in the Brief, judge in the findings.** Every unrequested change is a finding (the label depends on its risk); the Brief's author decisions carry only the choices that are not unrequested scope. Never both. A change that contradicts a criterion's stated outcome is that criterion's `Unmet`, not unrequested scope; code that delivers the outcome under an identifier the criterion spells differently is not a contradiction, and the identifier change is judged as scope. Unrequested scope is a change on the Counts list that no criterion (or, with no source, the inferred request) addresses.
- **Local reads only.** No `gh`, no platform API, no network.

## Patterns

### Source resolution (first row that resolves wins)

| Order | Source                                                                                     | Authority     |
| ----- | ------------------------------------------------------------------------------------------ | ------------- |
| 1     | The file at `--req <path>`; a file with no criterion stating an observable outcome does not resolve this row, and resolution continues at row 2 | Specified; Self-attested when the diff adds or edits it, or it is the change's own PR description |
| 2     | Requirement text or file already in context and written independently of the change (pasted ticket, PRD, spec) - author-written text is row 5 | Specified     |
| 3     | An in-tree spec the change names - a path appearing in the diff, commit log, or context, or a ticket ID resolved through an in-tree file named alongside it or naming the ID itself (a ticket ID with no such file leaves the row unresolved and is recorded under Watch points, as is a ticket ID that disagrees with the resolved source). Follow the reference; never guess a likely path. A referenced document with no criterion stating an observable outcome does not resolve this row | Specified; Self-attested when the diff adds or edits it |
| 4     | The `Requirement Source` recorded in the prior report at `prior_report_path`, re-read at its path and evaluated at its current content; a recorded source with no re-readable path (pasted text, PR body) does not resolve | the authority the row that first resolved it assigns at the current range: Self-attested when the current diff adds or edits it, otherwise the prior authority |
| 5     | Pasted PR/MR body, other author-written requirement text in context, or commit messages in the range, when any enumerates at least one criterion stating an observable outcome - an unfetched PR body leaves the other sources of this row live | Self-attested |
| 6     | Nothing resolves                                                                            | omit the block |

### Criterion status

| Status        | Fill when                                                                                     |
| ------------- | ---------------------------------------------------------------------------------------------- |
| `Met`         | An implementation anchor and a proof anchor both resolve and together cover the full stated outcome |
| `Partial`     | Exactly one anchor resolves, or the anchors together cover part of the stated outcome          |
| `Unmet`       | Neither anchor resolves, in the change or in the existing tree, or the implementation contradicts the stated outcome (a flag shipped on where the criterion says off) - a contradiction is `Unmet` whichever anchors resolve |
| `Deferred`    | The source itself places the criterion outside this change (`part 1 of 3`, `follow-up`, a criterion marked out of scope) |
| `Untraceable` | An enumerated criterion states no observable outcome (`improve UX`, `clean this up`) - no anchor is possible either way |

### What counts as a proof anchor

```
Bad  - AC-2 "rate limit returns 429 with Retry-After" | Met | limiter.ts:40 | test/limiter.spec.ts:12 "describe('rate limiting')"
       a test that names the feature but asserts nothing about 429 or Retry-After

Good - AC-2 | Met | limiter.ts:40 | test/limiter.spec.ts:31 asserts status 429 + Retry-After header
```

A proof must assert the criterion's stated outcome, not just a mechanism component: a test proving the counter reaches Redis leaves "limits hold across instances" unproven - one anchor, `Partial`. A manual-verification note counts when the source or the change states the check performed (`verified against staging: 61st request returns 429`); CI passing, type-checking, and the reviewer's own reading do not.

### Unrequested scope

Counts: a new or major-bumped dependency, a schema or migration change, a changed or added public contract (a new externally reachable endpoint counts), an auth/authz surface change, a new or changed default or config value (a flag key added with no code reading it still counts), a behavior change to a feature no criterion names, a refactor outside the criteria's footprint.

Does not count: renames and formatting inside files the work already touched, added tests, comments and docs, a dependency a criterion names or implies, and edits mechanically forced by the requested work (call sites updated for a changed signature). Implying a dependency implies adding it at whatever version satisfies the criterion; a major bump of a dependency the project already had is implied only when the criterion names that major version or a feature only it ships, and otherwise stays on the counts list. Scope is judged on the net `base...head` diff: a change added and reverted inside the range is not unrequested scope. With no source, the intent the commit log, non-qualifying pasted prose, or a non-qualifying requirement file states is the inferred request, not unrequested scope.

High-risk unrequested scope: a destructive migration (drop, rename, type change, or backfill against an existing table), an auth/authz surface change, a changed or added public contract (including a new externally reachable endpoint), a new or major-bumped dependency, a changed shared default.

### Findings raised

| Condition                                                                                   | Label         |
| ------------------------------------------------------------------------------------------- | ------------- |
| `Unmet` criterion                                                                            | `[Must]`      |
| `Partial` criterion                                                                          | `[Recommend]` |
| High-risk unrequested scope, with a requirement source resolved                              | `[Must]`      |
| High-risk unrequested scope, with no requirement source                                      | `[Recommend]` - an inferred baseline cannot establish that work was not asked for |
| Any other unrequested scope                                                                  | `[Recommend]` |
| `Deferred` or `Untraceable` criterion                                                        | none - table row only |

Every round derives this phase's findings from the full current range; prior-round findings carry forward through `review-prior-findings-reconcile`, never through this phase. Anchor every finding to a production `file:line` (a dependency finding to the manifest line that adds the dependency or changes its version; a `Partial` criterion's finding to its implementation anchor when one resolved, otherwise to the construct that would hold the missing behavior, as for an `Unmet` criterion with no implementation), never to the requirement document. An `Unmet` criterion with no implementation is anchored to the construct that would hold the missing behavior - the handler, module, or config the criterion concerns; a contradicted criterion is anchored to the contradicting `file:line`; either way the claim names the criterion, and two criteria failing on one line are two findings at that line. A rename with no changed lines anchors at the renamed file's first line. One finding per unrequested change; the same kind of change repeated across files (a restructure, a sweeping rename, two unpaginated list endpoints) is one finding anchored to one representative changed `file:line`, stating the extent in the claim (`part of a 14-file email-module restructure`), while two changes of different kinds, in one file (a rename and a backfill in one migration) or across files (a contract change and a dependency pin), are two findings. Order findings `[Must]` first.

## Output Format

Emit the lines and blocks below in this order. `Requirement Source`, `Requirement Fit`, and `## Requirement Traceability` appear together or not at all: all three are present when a source resolved, all three omitted when none did. The consuming workflow copies the two lines into its report Summary and the four `## Change Brief` fields into the report body verbatim; findings feed its finding set and are not copied with the Brief.

```
Requirement Source: <path for rows 1, 3, 4 and a row-2 file in context; `pasted <ticket ID or document title>` for row-2 pasted text; `PR body (pasted)`, `pasted <document title> (author-written)`, or `commit messages <base_ref>..<head_ref>` for row 5> (Specified | Self-attested)

Requirement Fit: <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable

## Change Brief

**Requested:** <what the change was asked to do, 1-2 sentences, citing the source; with no source, the intent the commit log, non-qualifying pasted prose, or a non-qualifying requirement file states, marked `(inferred from commits)`, `(inferred from PR body)`, or `(inferred from <path or document title>)`, whichever it came from>

**Delivered:** <the mechanism actually implemented and where, 1-2 sentences naming the primary files>

**Author decisions:** <one bullet per choice the request did not imply and that is not unrequested scope, each with its consequence; `None observed` when nothing remains>

**Watch points:** <what the reviewer should confirm by hand before reading findings - untested behavior, an assumption the change rests on, what it deliberately does not do, a self-attested deferral of a Specified criterion, an unresolved ticket ID or one that disagrees with the resolved source; never a defect, which is another lens's finding; `None` when there are none>

## Requirement Traceability

| Criterion | Status | Implementation | Proof |
| --------- | ------ | -------------- | ----- |
| <id or quoted outcome> | Met \| Partial \| Unmet \| Deferred \| Untraceable | <file:line, `file:line (pre-existing)`, or `-`> | <file:line or verification note, optionally `(pre-existing)`, or `-`> |

### Requirement Findings                 {when at least one finding}

- {[Must] | [Recommend]} <file:line> - <claim naming the criterion or the unrequested change>

### No Requirement Findings              {instead, when none}
```

Exactly one of the two `###` headings is emitted - the consuming workflow uses its presence to confirm the phase ran. It sits under the traceability block when that renders, directly under the Change Brief when it does not, so a sourceless run still reports unrequested scope.

## Avoid

- Judging whether the requirement was a good idea - that is design review, not fit
