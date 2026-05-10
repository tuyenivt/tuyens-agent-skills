---
name: task-release-notes
description: Generate stakeholder release notes from git commits or PR list: features/fixes/breaking/internal, user impact, rollback and risk section.
metadata:
  category: planning
  tags: [release, changelog, release-notes, rollout, rollback, communication]
  type: workflow
user-invocable: true
---

# Release Notes

Turn a commit range or PR list into a single Markdown document that serves two audiences:

- **Stakeholders** - categorized, plain-language changelog
- **On-call and deploy operators** - rollback and risk section grounded in the actual diff

Does not push tags, edit `CHANGELOG.md` files in place, or send announcements.

## When to Use

- Cutting a release (weekly train, sprint, or one-off deploy)
- Drafting a changelog entry from PRs since the last tag
- Producing notes for an internal channel or external customer changelog

When the release contains many unrelated high-risk changes, run per logical batch rather than producing one giant note.

## Inputs

| Input | Required | Notes |
| --- | --- | --- |
| Commit range or PR list | Yes | e.g. `v1.4.0..HEAD` or PR numbers |
| Version | No | Leave `<version>` placeholder explicit if not supplied - never invent one |
| Audience | No | `internal` (default), `external`, or `both`. `external` drops Internal and CI-only items. `both` keeps Internal but writes Highlights for a non-engineer reader. |
| Previous release | No | Bounds "what's new" if the range is open-ended |
| Deploy target | No | Shapes rollback section |
| Known follow-ups | No | Surfaced as "Known Limitations" |

If the range is empty or unresolvable, stop and ask - don't produce an empty note.

## Workflow

### STEP 1 - Setup

Use skill: `behavioral-principles`.
Use skill: `stack-detect` (shapes which rollback patterns apply).

### STEP 2 - Categorize

Place every change in exactly one bucket. No "Other" - force a real category.

| Category | Includes |
| --- | --- |
| **Breaking** | Removed/renamed public APIs, schema removals, behavior changes requiring consumer action |
| **Features** | New user-facing capability, endpoints, or UI |
| **Improvements** | Performance, UX polish, observability, expanded existing capability |
| **Fixes** | User-visible bugs corrected |
| **Security** | Security fixes, CVE patches, hardening |
| **Internal** | Refactors, tests, CI, dep bumps with no behavior change. Drop entirely for `external` audience. |
| **Deprecations** | Marked for removal in a future release (already-removed features go in Breaking) |

### STEP 3 - Risk and Rollback

Classify rollout risk for changes in Breaking / Features / Improvements / Fixes / Security. Use `Use skill: review-blast-radius` and `review-change-risk` for changes that touch data, auth, money, or external contracts.

Load the deep-dive only when relevant:
- Migrations present → `Use skill: backend-db-migration`
- API contract or schema changes → `Use skill: ops-backward-compatibility`
- Cross-service contracts → `Use skill: dependency-impact-analysis`
- Flag-gated → `Use skill: ops-feature-flags` (rollback-via-flag-flip)
- For higher-risk changes → `Use skill: ops-release-safety` to map to a rollback strategy and detection signal

**Risk Register rule.** Each Wide or Critical blast-radius change gets a row. Moderate changes get a row only when they carry material rollout context (migration, flag, large table). Narrow changes are covered by the Default Rollback paragraph - listing them dilutes the signal.

Each Risk Register row needs:
- **What could break** - failure mode in user-visible terms
- **Detection signal** - specific dashboard/alert/log filter (not "monitor for issues")
- **Rollback step** - revert deploy / flip flag / reverse migration
- **Data impact** - does rollback restore prior state cleanly, or does new-code data persist
- **Owner** - team or individual

### STEP 4 - Compose

For **Breaking**, lead with the consumer's migration step ("Callers must now pass `region` on `POST /orders`"), not the internal change. Cite by PR number, not SHA.

Never paste raw commit messages or PR titles unedited:
- Bad: `feat: add /api/v2/orders/bulk endpoint for bulk order creation (max 100 per request)`
- Good: `Bulk order creation - POST up to 100 orders in a single /api/v2/orders/bulk request ([#1421])`

## Output Format

```markdown
# Release Notes - <version> - <date>

> **Audience:** internal | external | both
> **Range:** `<previous-tag>..<this-tag>` (<N> PRs)
> **Deploy target:** <env(s)>

## Highlights

- 1-3 bullets - most important things this release ships. For `external` or `both`, write for a non-engineer.

## Breaking Changes

- **<change>** ([#PR]) - what consumers must do to adopt. Omit section if none.

## Features

- **<change>** ([#PR]) - one-sentence user-visible impact.

## Improvements

- **<change>** ([#PR]) - one-sentence impact.

## Fixes

- **<change>** ([#PR]) - the bug, in user terms.

## Security

- **<change>** ([#PR]) - severity if known; do not disclose unpatched details.

## Deprecations

- **<feature>** ([#PR]) - removal target release.

## Internal

- One-line summary. Drop section entirely for `external` audience.

## Known Limitations

- Deferred items the team intentionally did not ship. Omit if none.

## Rollout & Rollback

**Rollout strategy:** <e.g. blue/green, canary 10%→100%, flag-gated to internal then GA>

### Risk Register

| Change | Blast Radius | What Could Break | Detection Signal | Rollback Step | Data Impact | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| <change> | Wide / Critical (or Moderate w/ context) | <failure mode> | <metric / alert / log> | <revert / flag-flip / reverse-migration> | clean \| dirty - <one-line> | <team> |

### Default Rollback

<one paragraph: how to revert if no specific risk fires - e.g. "Redeploy previous image; no data steps required" or "Flip `feature.x.enabled` to false; pending rows in `outbox` drain on the next worker run">

### Migration Notes

<only when migrations ship: expand/contract phase status, reverse migration availability, ordering vs deploy>

## Assumptions

- Anything inferred because input was incomplete. Omit if none.
```

Omit empty categories from the final document. Rollout & Rollback is mandatory - even "Revert deploy, no data steps required" is a valid Default Rollback.

## Self-Check

- [ ] Every change categorized exactly once; no "Other" bucket
- [ ] Breaking changes at the top, leading with consumer action
- [ ] Wide/Critical (and material Moderate) changes have a Risk Register row with all six columns
- [ ] Default Rollback paragraph present
- [ ] Migration Notes present iff migrations ship
- [ ] `external` audience: Internal and CI-only items dropped; Highlights written for non-engineer
- [ ] No raw commit messages or unedited PR titles

## Avoid

- "Other" or "Miscellaneous" - force a real category
- Generic rollback advice - name the dashboard, name the metric
- Treating rollback as optional for "small" releases - small releases still ship to prod
- Inventing a version string
- Burying breaking changes inside Features
- Listing every Narrow change in the Risk Register
