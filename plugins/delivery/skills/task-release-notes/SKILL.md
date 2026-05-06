---
name: task-release-notes
description: Generate stakeholder-ready release notes from a git commit range or PR list. Categorizes changes (features / fixes / breaking / internal), summarizes user-visible impact, and folds in a per-release rollback and risk section so the same artifact serves both stakeholders and on-call. Use when cutting a release, drafting a changelog, or preparing a deploy announcement.
metadata:
  category: planning
  tags: [release, changelog, release-notes, rollout, rollback, communication]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Release Notes

## Purpose

Turn a commit range or PR list into a release artifact that serves two audiences in one document:

- **Stakeholders** -- a categorized, plain-language changelog they can quote in announcements, sales decks, or support handoffs
- **On-call and deploy operators** -- a rollback and risk section that names what could break, how to detect it, and how to revert

This skill produces a single Markdown document. It does not push tags, edit `CHANGELOG.md` files in place, or send announcements - those are the user's call.

## When to Use

- Cutting a release (weekly train, sprint release, or one-off deploy)
- Drafting a changelog entry from merged PRs since the last tag
- Preparing a deploy announcement for an internal channel
- Producing release notes for an external customer-facing changelog

Not for incident postmortems (use `task-postmortem`) or for planning what to build next (use `task-scope-breakdown`). When the release contains many unrelated high-risk changes, prefer running this workflow per logical batch rather than producing one giant note.

## Inputs

| Input               | Required | Description                                                                                 |
| ------------------- | -------- | ------------------------------------------------------------------------------------------- |
| Commit range or tag | Yes      | e.g. `v1.4.0..HEAD`, `main..release/2026-05-06`, or a list of PR numbers                    |
| Audience            | No       | `internal` (default), `external`, or `both` - controls tone and how much detail is exposed  |
| Previous release    | No       | Tag or date - used to bound "what's new" if the commit range is open-ended                  |
| Deploy target       | No       | Environment(s) the release ships to - shapes the rollback section                           |
| Known follow-ups    | No       | Work intentionally deferred to the next release - included as a "Known limitations" section |

Handle partial inputs gracefully. If only a tag range is supplied, infer audience as `internal` and surface assumptions explicitly.

## Rules

- Every change must land in exactly one category - no "Other" bucket
- User-visible impact is described in plain language; never paste raw commit messages or PR titles unedited
- Breaking changes are called out at the top, never buried inside Features
- Every release note must include a rollback section, even if rollback is trivial - "Revert deploy, no data steps required" is a valid entry
- Risk and rollback content is grounded in the actual diff, not generic advice
- For `external` audience, omit internal refactors, dependency bumps without behavior change, and CI-only changes
- Do not invent versioning - if the user did not supply a version, leave the placeholder explicit (`<version>`)
- Omit empty sections in the final output

## Workflow

### STEP 1 - Behavioral and Stack Setup

Use skill: `behavioral-principles` before any other delegation.

Use skill: `stack-detect` to identify project stack - shapes which rollback patterns apply (e.g., Rails migration phasing, container image rollback, schema-level concerns).

### STEP 2 - Gather the Change Set

From the supplied commit range or PR list, collect:

- Commit subjects + bodies
- Changed file paths (for risk classification)
- PR titles, labels, and linked issues if available

If the range is empty or unresolvable, stop and ask the user to clarify rather than producing an empty note.

### STEP 3 - Categorize Each Change

Place every change in exactly one bucket:

| Category         | Includes                                                                                    | Excludes                                      |
| ---------------- | ------------------------------------------------------------------------------------------- | --------------------------------------------- |
| **Breaking**     | Removed/renamed public APIs, schema removals, behavior changes that require consumer action | Internal-only refactors                       |
| **Features**     | New user-facing capability, new endpoints, new UI surfaces                                  | Bug fixes phrased as features                 |
| **Improvements** | Performance, UX polish, observability, expanded capability of existing features             | New features                                  |
| **Fixes**        | Bug fixes - user-visible incorrect behavior corrected                                       | Refactors with no behavior change             |
| **Security**     | Security fixes, dependency CVE patches, hardening                                           | General dep bumps                             |
| **Internal**     | Refactors, test additions, CI, tooling, dependency bumps without behavior change            | Anything users will notice                    |
| **Deprecations** | Features marked deprecated, slated for removal in a future release                          | Already-removed features (those are Breaking) |

For `external` audience, drop **Internal**.

### STEP 4 - Risk and Rollback Assessment

For each change in **Breaking**, **Features**, **Improvements**, **Fixes**, and **Security**, classify the rollout risk.

Use skill: `review-blast-radius` to assess scope of each change.
Use skill: `review-change-risk` to identify risk domains touched (data, auth, money, external contracts).
Use skill: `ops-release-safety` to map each higher-risk change to a rollback strategy and detection signal.
Use skill: `ops-backward-compatibility` if API contracts or schemas changed - to confirm forward/backward compat or flag the gap.
Use skill: `backend-db-migration` if migrations are present - to surface lock risk, expand-contract phasing, and rollback steps.
Use skill: `ops-feature-flags` if any change is gated by a flag - to document rollback-via-flag-flip.
Use skill: `dependency-impact-analysis` if cross-service or cross-package contracts changed.

For each change scored **Wide** or **Critical** blast radius, produce a rollback line item containing:

- **What could break**: the failure mode, in user-visible terms
- **Detection signal**: the metric, log, or alarm that catches it (be specific - dashboard name, alert name, log filter)
- **Rollback step**: revert deploy / flip flag / run reverse migration / both - whichever applies
- **Data impact**: whether rollback restores prior state cleanly, or whether data written under the new code remains
- **Owner**: team or individual on point if rollback is invoked

Narrow-blast-radius changes get a single combined rollback line ("Revert deploy") - do not pad the section with low-signal entries.

### STEP 5 - Compose the Release Note

Assemble the categorized changelog and the rollback section into the output template below.

For **Breaking**, lead each item with the migration step a consumer must take, not the internal change ("Callers must now pass `region` on `POST /orders`" beats "Add region param to orders endpoint").

For **Features** and **Fixes**, write one sentence of user-visible impact, then optionally one line of context. Cite the PR or commit by number, not by SHA.

### STEP 6 - Self-Check

Walk the Self-Check list before returning the note. If any item fails, fix and re-verify.

## Output Format

```markdown
# Release Notes - <version> - <date>

> **Audience:** internal | external | both
> **Range:** `<previous-tag>..<this-tag>` (<N> commits / <M> PRs)
> **Deploy target:** <env(s)>

## Highlights

- [1-3 bullets - the most important things this release ships, written for a non-engineer]

## Breaking Changes

- **<change>** ([#PR]) - what consumers must do to adopt. Omit section if none.

## Features

- **<change>** ([#PR]) - one-sentence user-visible impact. Optional second line of context.

## Improvements

- **<change>** ([#PR]) - one-sentence impact.

## Fixes

- **<change>** ([#PR]) - the bug, in user terms.

## Security

- **<change>** ([#PR]) - severity if known; do not disclose unpatched details.

## Deprecations

- **<feature>** ([#PR]) - removal target release.

## Internal

- One-line summary of refactor/dependency/CI work. Omit for `external` audience.

## Known Limitations

- Deferred items the team intentionally did not ship in this release. Omit if none.

## Rollout & Rollback

**Rollout strategy:** <e.g. blue/green, canary 10% then 100%, flag-gated to internal then GA>

### Risk Register

| Change   | Blast Radius                        | What Could Break            | Detection Signal              | Rollback Step                            | Data Impact                | Owner  |
| -------- | ----------------------------------- | --------------------------- | ----------------------------- | ---------------------------------------- | -------------------------- | ------ |
| <change> | Narrow / Moderate / Wide / Critical | <user-visible failure mode> | <metric / alert / log filter> | <revert / flag-flip / reverse-migration> | <clean / dirty - describe> | <team> |

### Default Rollback

<one paragraph: how to revert the release if no specific risk fires - e.g. "Redeploy previous image; no data steps required" or "Flip `feature.x.enabled` to false; pending rows in `outbox` will drain on the next worker run">

### Migration Notes

<only when migrations ship: expand/contract phase status, whether reverse migration exists, ordering relative to deploy>

## Assumptions

- [Anything inferred because input was incomplete - e.g. "Audience defaulted to internal; flag any items that should be cut for external use"]
```

### Output Constraints

- Every change must appear in exactly one category
- The Rollout & Rollback section is mandatory - never omit, even if trivial
- Every Wide/Critical change must have a Risk Register row
- Omit empty categories from the final document

## Self-Check

- [ ] Behavioral-principles loaded as the first step
- [ ] Every change in the supplied range is accounted for in exactly one category
- [ ] Breaking changes are at the top and lead with the consumer action
- [ ] Each Wide/Critical-blast-radius change has a Risk Register row with all six columns filled
- [ ] Rollout & Rollback section present, with a Default Rollback paragraph
- [ ] Migration Notes present iff migrations ship in this release
- [ ] For `external` audience, Internal category and CI-only items are dropped
- [ ] No raw commit messages or unedited PR titles in the output
- [ ] Assumptions section lists every inferred input

## Avoid

- Padding the changelog with internal refactors when audience is `external`
- "Other" or "Miscellaneous" buckets - force a real category
- Generic rollback advice ("monitor dashboards, revert if needed") - name the dashboard, name the metric
- Treating the rollback section as optional when the release looks "small" - small releases still ship to prod
- Inventing a version string the user did not supply
- Burying breaking changes inside Features or Improvements
- Listing every Narrow change in the Risk Register - it dilutes the signal for Wide/Critical entries
