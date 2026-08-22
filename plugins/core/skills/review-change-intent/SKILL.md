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
| `prior_report_path`  | no       | `prior_checkpoint.report_path` from the precondition handle, when round > 1  |

## Rules

- **Never derive criteria from the diff.** Reading requirements off the change is circular and always concludes the change meets them. With no qualifying source, emit the Change Brief and omit the traceability block entirely.
- **A source qualifies only when it enumerates at least one criterion stating an observable outcome.** A commit subject (`fix pagination`), a branch name, or a prose PR body with no criteria list is Brief material, not traceability material - without this bar the commit log makes every review look sourced.
- **`Met` requires two anchors: an implementation `file:line` and a proof.** Exactly one anchor is `Partial`. The implementation is never its own proof.
- **Anchors may cite unchanged code**, annotated `(pre-existing)`. A criterion the system already satisfied is `Met`, and the annotation tells the reader this change is not what satisfied it.
- **Disclose source authority, never infer it.** `Specified` = written independently of the change. `Self-attested` = written by the author alongside it (pasted PR body, commit messages). Self-attested criteria still gate - a change that does not do what its own description claims is a defect - but the reader is told which kind they are reading.
- **Describe in the Brief, judge in the findings.** An author decision is orientation; it becomes a finding only when it meets the risk bar below. Never both.
- **Local reads only.** No `gh`, no platform API, no network. When the target is a PR and no body was pasted, the ladder moves to the next row.

## Patterns

### Source resolution (first row that resolves wins)

| Order | Source                                                                                     | Authority     |
| ----- | ------------------------------------------------------------------------------------------ | ------------- |
| 1     | The file at `--req <path>`                                                                  | Specified     |
| 2     | Requirement text or file already in context (pasted ticket, PRD, spec)                      | Specified     |
| 3     | An in-tree spec the change names - a path or ticket ID appearing in the diff, commit log, or context. Follow the reference; never guess a likely path | Specified     |
| 4     | The `Requirement Source` recorded in the prior report at `prior_report_path`, re-read at its path; a recorded source with no re-readable path (pasted text, PR body) does not resolve | carry the prior authority |
| 5     | Pasted PR/MR body, or commit messages in the range, when either enumerates criteria         | Self-attested |
| 6     | Nothing resolves                                                                            | omit the block |

### Criterion status

| Status        | Fill when                                                                                     |
| ------------- | ---------------------------------------------------------------------------------------------- |
| `Met`         | An implementation anchor and a proof anchor both resolve                                       |
| `Partial`     | Exactly one anchor resolves, or the implementation covers part of the stated outcome           |
| `Unmet`       | Neither anchor resolves, in the change or in the existing tree                                 |
| `Deferred`    | The source or the change explicitly places the criterion outside this change (`part 1 of 3`, `follow-up`, a criterion marked out of scope) |
| `Untraceable` | The criterion states no observable outcome (`improve UX`, `clean this up`) - no anchor is possible either way |

### What counts as a proof anchor

```
Bad  - AC-2 "rate limit returns 429 with Retry-After" | Met | limiter.ts:40 | limiter.ts:40
       the implementation cited as its own proof

Bad  - AC-2 | Met | limiter.ts:40 | test/limiter.spec.ts:12 "describe('rate limiting')"
       a test that names the feature but asserts nothing about 429 or Retry-After

Good - AC-2 | Met | limiter.ts:40 | test/limiter.spec.ts:31 asserts status 429 + Retry-After header
```

A proof must assert the criterion's stated outcome, not just a mechanism component: a test proving the counter reaches Redis leaves "limits hold across instances" unproven - one anchor, `Partial`. A manual-verification note counts when the source or the change states the check that was performed (`verified against staging: 61st request returns 429`). CI passing, type-checking, and a reviewer's own reading do not.

### Unrequested scope

Both lists scope Brief bullets and findings alike. Counts: a new or major-bumped dependency, a schema or migration change, a changed public contract, an auth/authz surface change, a changed default or config value, a behavior change to a feature no criterion names, a refactor outside the criteria's footprint.

Does not count: renames and formatting inside files the work already touched, added tests, comments and docs, a dependency a criterion names or implies, and edits mechanically forced by the requested work (call sites updated for a changed signature).

### Findings raised

| Condition                                                                                   | Label         |
| ------------------------------------------------------------------------------------------- | ------------- |
| `Unmet` criterion                                                                            | `[Must]`      |
| `Partial` criterion                                                                          | `[Recommend]` |
| Unrequested scope that is itself high-risk: destructive migration, auth/authz surface, public API contract, new or major-bumped dependency, changed shared default | `[Must]`      |
| Any other unrequested scope                                                                  | `[Recommend]` |
| `Deferred` or `Untraceable` criterion                                                        | none - table row only |

Anchor every finding to a production `file:line`, never to the requirement document. An `Unmet` criterion has no implementation to cite: anchor it to the construct that would hold the missing behavior - the handler, module, or config the criterion concerns - and name the criterion in the claim.

**With no requirement source, unrequested-scope findings cap at `[Recommend]`.** The only baseline is the intent inferred from commits, and that is not a specification: a bundled migration is still worth naming, but `[Must]` asserts the work was not asked for, which an inferred baseline cannot establish. Most changes arrive without a ticket - this path is the common one, and it does not manufacture merge blockers.

## Output Format

Emit the lines and blocks below in this order. `Requirement Source`, `Requirement Fit`, and `## Requirement Traceability` appear together or not at all: all three are present when a source resolved, all three omitted when none did. The consuming workflow copies the two lines into its report Summary and the `## Change Brief` block into the report body verbatim; findings feed its finding set.

```
Requirement Source: <path or origin> (Specified | Self-attested)
Requirement Fit: <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable

## Change Brief

**Requested:** <what the change was asked to do, 1-2 sentences, citing the source; with no source, the intent the commit log states, marked `(inferred from commits)`>

**Delivered:** <the mechanism actually implemented and where, 1-2 sentences naming the primary files>

**Author decisions:** <one bullet per choice the request did not imply, each with its consequence, excluding choices already raised as findings; `None observed` when nothing remains>

**Watch points:** <what the reviewer should confirm by hand before reading findings - untested behavior, an assumption the change rests on, what it deliberately does not do; `None` when there are none>

## Requirement Traceability

| Criterion | Status | Implementation | Proof |
| --------- | ------ | -------------- | ----- |
| <id or quoted outcome> | Met \| Partial \| Unmet \| Deferred \| Untraceable | <file:line, or `-`> | <file:line or verification note, or `-`> |

### Requirement Findings

- [Must | Recommend] <file:line> - <claim naming the criterion or the unrequested change>

### No Requirement Findings
```

Emit exactly one of `### Requirement Findings` and `### No Requirement Findings` - the consuming workflow uses its presence to confirm the phase ran. It sits under the traceability block when that renders, directly under the Change Brief when it does not: unrequested scope needs no criteria list to be visible, so a sourceless run still reports it.

## Avoid

- Concluding `Met` from the implementation alone
- Reverse-engineering criteria from the change, then reporting that the change satisfies them
- Treating a one-line commit subject or a branch name as a criteria list
- Reporting the same author decision as both a Brief line and a finding
- Judging whether the requirement was a good idea - that is design review, not fit
- Anchoring a finding to the ticket, the PR body, or the requirement file
