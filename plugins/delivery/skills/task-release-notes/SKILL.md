---
name: task-release-notes
description: Compose dual-audience release notes from a commit range or PR list; categorize changes, classify risk, produce risk register and rollback.
metadata:
  category: planning
  tags: [release, changelog, release-notes, rollout, rollback, communication]
  type: workflow
user-invocable: true
---

# Release Notes

Turn a commit range or PR list into a single Markdown document for two audiences:

- **Stakeholders** - categorized, plain-language changelog
- **On-call and deploy operators** - rollback and risk section grounded in the actual diff

Does not push tags, edit `CHANGELOG.md` in place, or send announcements.

## When to Use

- Cutting a release (weekly train, sprint, one-off deploy)
- Drafting a changelog entry from PRs since the last tag
- Producing notes for an internal channel or external customer changelog

When the release contains many unrelated high-risk changes, run per logical batch instead of one giant note.

## Inputs

| Input | Required | Notes |
| --- | --- | --- |
| Commit range or PR list | Yes | e.g. `v1.4.0..HEAD` or PR numbers |
| Version | No | Leave `<version>` placeholder if missing - never invent. Note in Assumptions. |
| Audience | No | `internal` (default), `external`, or `both`. `external` drops Internal and CI-only items. `both` keeps Internal but writes Highlights for a non-engineer reader. |
| Previous release | No | Bounds "what's new" if the range is open-ended |
| Deploy target | No | Shapes rollback. Mobile (iOS/Android) requires app-store-aware rollback. |
| Known follow-ups | No | Surfaced as "Known Limitations" |

Stop and ask when:
- The range is empty or unresolvable
- The range has no previous tag and no caller-supplied lower bound
- PR numbers don't resolve (list which); partial resolution is acceptable only on caller confirmation

## Workflow

### STEP 1 - Behavioral Setup

Use skill: `behavioral-principles`.

### STEP 2 - Stack Detect

Use skill: `stack-detect`. If the deploy target spans multiple stacks (e.g., web + iOS + Android), record each and apply per-stack rollback patterns in Step 4. When CWD has no stack signal but the input names one, trust the input.

### STEP 3 - Categorize

Place every change in exactly one bucket. No "Other". Precedence (highest first) when a PR matches multiple buckets: **Breaking > Security > Deprecations > Features > Fixes > Improvements > Internal**.

| Category | Includes |
| --- | --- |
| **Breaking** | Removed/renamed public APIs, schema removals, required fields, behavior changes needing consumer action |
| **Security** | CVE patches, security hardening, vuln fixes. A dep bump that names a CVE is Security, not Internal. |
| **Features** | New user-facing capability, endpoints, or UI (including flag-gated) |
| **Fixes** | User-visible bugs corrected. `fix(internal)` or admin-only fixes go to Internal. |
| **Improvements** | Performance, UX polish, observability, expanded capability. Pure schema/data changes with no API surface (e.g., index add, NOT NULL backfill) land here and always trigger Risk Register evaluation. |
| **Deprecations** | Marked for removal in a future release (already-removed features go in Breaking) |
| **Internal** | Refactors, tests, CI, dep bumps with no behavior change and no CVE. Drop entirely for `external` audience. |

### STEP 4 - Risk, Rollout, and Rollback

Load `Use skill: ops-release-safety` to ground the rollout strategy and detection signals.

For each change touching data, auth, money, or external contracts, load `Use skill: review-blast-radius`. When blast radius is Wide or Critical, load `Use skill: review-change-risk` and use its `Reversibility` as authoritative for the Risk Register row.

Conditional deep-dives:

- Migration present → `Use skill: backend-db-migration` (covers reverse-migration availability)
- API contract or protocol change → `Use skill: ops-backward-compatibility`
- Security or dependency change → `Use skill: dependency-impact-analysis`
- Flag-gated rollout → `Use skill: ops-feature-flags`. A flag with no expiry goes to **Known Limitations**.

**Risk Register inclusion rule.** A row is required for:
- Every Wide or Critical blast-radius change
- Every Moderate change that carries any of: a migration, a feature flag, a table-locking operation, a third-party-contract change, mobile-side breaking behavior

Narrow changes are covered by the Default Rollback paragraph.

Each row needs: What could break, Detection signal, Rollback step, Data impact, Owner. Detection signal must name a concrete dashboard/metric/log; if unknown, emit `<dashboard: TBD>` and add an Assumption. Owner unknown → `TBD` and add an Assumption.

**Mobile rollback.** When deploy target includes iOS or Android, name the mobile-specific rollback path (staged rollout pause, server-side flag flip, force-update fallback) - native rollback via redeploy is not available.

### STEP 5 - Compose

Highlights (1-3): pick by user impact magnitude, then by breaking/security status. Write for the audience.

For **Breaking**, lead with the consumer's migration step: "Callers must now pass `reason` on `POST /api/v2/refunds` ([#1495])." Not "Added required `reason` field."

Never paste raw commit messages or PR titles unedited:
- Bad: `feat: add /api/v2/orders/bulk endpoint for bulk order creation (max 100 per request)`
- Good: `Bulk order creation - POST up to 100 orders in a single /api/v2/orders/bulk request ([#1421])`

Cite by PR number, not SHA. `[#1421]` renders as a literal token unless your CHANGELOG renderer auto-links it.

## Output Format

```markdown
# Release Notes - <version> - <YYYY-MM-DD>

> **Audience:** internal | external | both
> **Range:** `<previous-tag>..<this-tag>` (<N> PRs)
> **Deploy target:** <env(s) and platforms>

## Highlights

- 1-3 bullets - highest user-impact items. Non-engineer phrasing for `external` or `both`.

## Breaking Changes

- **<change>** ([#PR]) - consumer action required. Omit section if none.

## Security

- **<change>** ([#PR]) - severity if known; do not disclose unpatched details.

## Features

- **<change>** ([#PR]) - one-sentence user-visible impact.

## Improvements

- **<change>** ([#PR]) - one-sentence impact.

## Fixes

- **<change>** ([#PR]) - the bug, in user terms.

## Deprecations

- **<feature>** ([#PR]) - removal target release.

## Internal

- One-line entries. Drop section entirely for `external` audience.

## Known Limitations

- Deferred items the team intentionally did not ship; flags without expiry. Omit if none.

## Rollout & Rollback

**Rollout strategy:** <e.g. blue/green, canary 10%→100%, flag-gated to internal then GA, mobile staged rollout 1%→10%→100%>

### Risk Register

| Change | Blast Radius | What Could Break | Detection Signal | Rollback Step | Data Impact | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| <change> | Wide / Critical (or Moderate w/ material context) | <failure mode> | <dashboard / metric / log> | <revert / flag-flip / reverse-migration / staged-rollout pause> | clean \| dirty - <one-line> | <team or TBD> |

### Default Rollback

<one paragraph per stack in the deploy target. Server: e.g., "Redeploy previous image; no data steps required." Mobile: e.g., "Pause Play Console staged rollout; flip `webhooks.dual_secret` to false; force-update not required.">

### Migration Notes

<only when migrations ship: expand/contract phase, reverse-migration availability per `backend-db-migration`, ordering vs deploy>

## Assumptions

- Anything inferred because input was incomplete. Omit if none.
```

Omit empty categories. Rollout & Rollback is mandatory.

## Self-Check

- [ ] **Setup:** behavioral-principles + stack-detect loaded
- [ ] **Categorize:** every change in exactly one bucket via precedence; no "Other"; Internal dropped for `external`
- [ ] **Highlights:** 1-3 by user impact; non-engineer phrasing for `external` or `both`
- [ ] **Risk inclusion:** ops-release-safety loaded; rollout strategy chosen; every Wide/Critical row present; every Moderate-with-material-context row present
- [ ] **Risk content:** Reversibility sourced from review-change-risk for Wide/Critical; Detection signal concrete or `TBD` with Assumption; Owner present or `TBD` with Assumption
- [ ] **Rollback:** Default Rollback paragraph per deploy-target stack; Mobile path named when iOS/Android present; Migration Notes present iff migrations ship
- [ ] **Compose:** Breaking entries lead with consumer action; PR numbers (not SHAs); no raw commit messages; Known Limitations populated for flags-without-expiry
- [ ] **Placeholders:** `<version>` and date placeholders kept literal when not supplied; Assumption noted

## Avoid

- "Other" or "Miscellaneous" - force a real category
- Generic rollback advice - name the dashboard, name the metric
- Treating rollback as optional for "small" releases
- Inventing a version string or release date
- Burying breaking changes inside Features
- Listing every Narrow change in the Risk Register
- Server-only rollback when the deploy target includes mobile
- Routing a CVE-named dep bump to Internal
