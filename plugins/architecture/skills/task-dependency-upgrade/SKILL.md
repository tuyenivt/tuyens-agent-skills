---
name: task-dependency-upgrade
description: "Plan or review library/platform upgrade: changelog analysis, breaking change detection, effort estimate (S/M/L/XL), Go/No-Go."
metadata:
  category: planning
  tags: [dependencies, upgrade, migration, breaking-changes, risk]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Dependency Upgrade Assessment

## Purpose

Structured upgrade assessment: breaking change detection, compatibility analysis, effort estimate (S/M/L/XL), rollback plan, and Go/No-Go recommendation. Produces an assessment; no migration code (use `/task-implement` after).

## When to Use

- Before upgrading a major framework version (e.g., Spring Boot 3.4 to 3.5, Rails 7 to 8, .NET 8 to .NET 9)
- Before upgrading a library with a major version bump
- When a dependency has known security vulnerabilities requiring an upgrade
- When evaluating whether an upgrade is worth the disruption relative to the benefit
- Before upgrading a build tool, runtime, or language version

Not for writing migration code (use `task-implement` after this assessment) or whole-system tech stack modernization (use `task-modernize-legacy`).

## Inputs

| Input            | Required | Description                                                              |
| ---------------- | -------- | ------------------------------------------------------------------------ |
| Dependency name  | Yes      | Library or platform name (e.g., "Spring Boot", "Rails", "Node.js")       |
| Current version  | Yes      | Version currently in use                                                 |
| Target version   | Yes      | Version to upgrade to                                                    |
| Codebase context | No       | How the dependency is used - key integration points, patterns, APIs used |
| Constraints      | No       | Timeline, team capacity, freeze windows, other concurrent upgrades       |

Handle partial inputs gracefully. When codebase context is missing, surface likely impact areas based on typical usage patterns for the detected stack.

## Rules

- Surface breaking changes and compatibility conflicts before estimating effort
- Every breaking change has a migration action (update / replace / workaround / defer)
- Effort estimates are relative S/M/L/XL - no calendar time unless asked
- Every assessment ends with a Go/No-Go recommendation and a rollback plan
- Omit empty sections

## Assessment Model

### Step 1 - Stack Detection

Use skill: `stack-detect` to identify the project's language, framework, build tool, and ecosystem. If it finds nothing, use the stack stated in the request.

This shapes:

- Which dependency management conventions apply
- Which compatibility concerns are relevant (e.g., Jakarta EE namespace, transitive dependency resolution)
- Which testing approach validates the upgrade

### Step 2 - Breaking Change Analysis

Do not assume minor version bumps are safe. Ecosystems like Spring Boot, Django, and Rails regularly ship breaking changes in minor releases. Read the full changelog and migration guide for every version in the path, including intermediates - assess per hop, then merge into one inventory with per-hop labels. When changelogs cannot be fetched (offline), work from known-version knowledge, tag every unverified claim **[VERIFY]**, and put "verify changelog/migration guide" first in Recommended Next Steps - never present unverified changes as confirmed.

Categorize breaking changes by type:

| Change Type            | Examples                                                       | Migration Effort             |
| ---------------------- | -------------------------------------------------------------- | ---------------------------- |
| API removal            | Deleted class, method, or endpoint                             | Code change required         |
| API rename / move      | Package rename, method rename, class rename                    | Automated refactor possible  |
| Behavior change        | Different default, changed semantics, new required param       | Logic review and test update |
| Configuration change   | New property name, removed property, changed default value     | Config file update           |
| Transitive dep upgrade | Pulled-in dependency version change causing indirect conflicts | Dependency resolution        |
| Runtime requirement    | New minimum JVM version, OS library, or build tool version     | Infrastructure change        |

Per change relevant to the codebase: change, migration action, effort (S/M/L/XL).

Use skill: `ops-backward-compatibility` for API and data contract impact.

### Step 3 - Compatibility Check

Surface conflicts: transitive dependency version mismatches, build-tool minimums (Gradle/Maven/Bundler/npm), runtime minimums (JDK, Node, Python, Ruby), test library compatibility. Mark each Resolvable, Needs own upgrade, or Blocker (the Output's Severity enum).

Use skill: `dependency-impact-analysis` for deployment ordering when multiple components must upgrade together.

**Multi-dependency upgrades:** When bumping several deps at once (framework + runtime + type system), check pairwise compatibility - individually safe upgrades can conflict when combined. If interaction risk is high, sequence across separate PRs rather than one batch.

### Step 4 - Security Assessment

State the security status of the current version regardless of whether the upgrade is security-motivated: EOL status, named CVEs the target version fixes, risk of staying. If listing CVEs, cite source rather than speculating; offline, name known CVEs tagged [VERIFY] - never invent IDs.

### Step 5 - Migration Effort Estimate

Aggregate the effort from Step 2 and any compatibility work from Step 3. Total = the largest component effort, bumped one size when two or more components share that size; the Size guidance below sets a floor per component when it names the change class (e.g., runtime upgrade = XL). For multi-dependency requests, render one breakdown table per dependency, then a batch total aggregated from the per-dependency totals by the same rule (XL does not bump further):

| Component                | Effort   | Notes                                          |
| ------------------------ | -------- | ---------------------------------------------- |
| Breaking change fixes    | S/M/L/XL | Per change or aggregate                        |
| Compatibility resolution | S/M/L/XL | Transitive conflicts, build tool               |
| Test and validation      | S/M/L/XL | Test library compat, integration + smoke tests |
| **Total**                | S/M/L/XL | Combined estimate                              |

Size guidance:

- **S**: Config changes only, no API changes, well-supported migration path
- **M**: A few API changes, one compatibility fix, low test surface impact
- **L**: Multiple API changes, behavior changes requiring logic review, significant test updates
- **XL**: Architectural changes, namespace migrations, runtime version upgrade - should be a dedicated epic

### Step 6 - Risk Assessment

Use skill: `review-blast-radius` for upgrade risk: affected features/flows, blast radius of a regression, canary or feature-flag options for limited rollout exposure.

| Risk Factor         | Level             | Notes                                     |
| ------------------- | ----------------- | ----------------------------------------- |
| Breaking changes    | None/Low/High     | High = removals or behavior changes present; Low = renames/config only |
| Test coverage       | Good/Partial/Poor | Confidence level for catching regressions |
| Rollback complexity | Easy/Hard         | Whether rollback requires data changes    |
| Blast radius        | Narrow/Wide       | Scope of affected functionality           |

Summary Risk Level: High when 2+ factors sit at their worst level (High/Poor/Hard/Wide), Medium when exactly one does, Low otherwise. Partial or Poor test coverage on an upgrade with behavior changes adds a prerequisite (backfill tests on affected flows) to Recommended Next Steps.

### Step 7 - Rollback Plan

Use skill: `ops-release-safety` for rollback patterns.

Define before the upgrade starts: trigger (specific signal - error rate, latency, failed smoke), procedure, data compatibility (schema/config/message-format changes complicate rollback), time window.

If the upgrade changes schema, config, or message format, an expand-contract strategy is required - "just revert" no longer works.

### Step 8 - Go / No-Go Recommendation

Produce a clear recommendation:

| Recommendation | When                                                                             |
| -------------- | -------------------------------------------------------------------------------- |
| Go - Now       | Effort S/M and risk Low, no unresolved conflicts                                 |
| Go - Planned   | Effort M/L or risk Medium - schedule as a dedicated sprint item with testing     |
| Go - Epic      | Effort XL, or cross-team coordination or infrastructure change required          |
| No-Go - Defer  | Benefit does not justify disruption at this time; reassess in N months           |
| No-Go - Block  | Compatibility blockers, unresolved conflicts, or critical breaking changes       |

State the primary reason, weighing stated constraints (deadlines, freeze windows, team rotation) - name them in it. A stated deadline or window counts as "asked" for calendar time: map the PR sequence to the window. For multi-dependency requests, give a per-dependency verdict plus a batch verdict; when the batch is rejected but a sequenced plan works, the Summary Recommendation reads "No-Go - Block (batch); Go - sequenced PRs".

## Review Mode

When reviewing an upgrade assessment authored by someone else:

Use skill: `architecture-review-lens` for severity taxonomy, completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and verdict.

Reviews run the full lens (standalone formatting defaults; the lens's skip rule covers steps that do not fit). The Assessment Model's tables (change taxonomy, size guidance, Go/No-Go criteria, Step 3's batching rule) are the bar the artifact must meet - cite them as review evidence. The reviewer may state a corrected value inside a finding's recommendation ("expect L-XL, not S") but does not author a replacement assessment.

Supply this upgrade-assessment-specific factor list to the completeness audit. Required = Blocker-eligible when Missing; advisory (No) factors cap at Major:

| Factor                       | Required | What "Present" Looks Like                                                         |
| ---------------------------- | -------- | --------------------------------------------------------------------------------- |
| Version path                 | Yes      | Current and target versions stated; intermediate versions assessed                |
| Breaking changes             | Yes      | Categorized by type (removal/rename/behavior/config) with migration action        |
| Compatibility conflicts      | Yes      | Transitive, build tool, runtime conflicts surfaced; blockers vs warnings          |
| Multi-dependency interaction | Yes*     | When upgrading multiple deps, interaction effects and required ordering assessed  |
| Security status              | No       | Current version EOL/CVE status stated, even when upgrade is not security-driven   |
| Effort estimate              | No       | S/M/L/XL per component (breaking changes, compatibility, tests, validation)       |
| Blast radius                 | No       | Which features/flows depend on the dependency; canary/feature-flag options        |
| Rollback plan                | Yes      | Trigger, procedure, data compatibility, time window - not just "revert version"   |
| Recommendation               | Yes      | Go-Now / Go-Planned / Go-Epic / No-Go-Defer / No-Go-Block with primary reason     |

*Required only when the assessment covers more than one dependency.

Specific quality checks beyond the standard lens:

- **Upgrade assumed safe without changelog review** (any version distance): Blocker for ecosystems known to break in minor versions (Spring Boot, Django, Rails); Major otherwise
- **Effort estimate without breaking change inventory**: Major; the estimate is unbacked
- **"Just revert" rollback plan**: Major when the upgrade changes schema, config, or message format
- **No security status for an EOL or vulnerable current version**: Major minimum
- **Recommendation not actionable for a spike ticket**: Minor; promote to Major when blast radius is Wide (per the artifact, or the reviewer's assessment when the artifact omits it - flag it as reviewer context)

Record each quality-check hit once, in the lens step that owns it (Missing factor -> Completeness; internal contradiction -> Internal Consistency; Present-but-wrong or Under-specified content -> Per-Factor Findings). A check's preset severity overrides the advisory cap - the cap binds only completeness-status findings. Reviewer-known but unverifiable facts follow the same [VERIFY] convention as Step 2.

Output header: `# Upgrade Assessment Review` and use the output structure defined in `architecture-review-lens`. Skip the assessment Output template below. In this mode the Review Self-Check replaces the authoring Self-Check (self-checks are applied internally, never emitted in the deliverable):

- [ ] All factors audited with Required marking applied; verdict driven by highest severity
- [ ] Quality-check hits recorded once in the correct lens step and numbered
- [ ] Every finding cites the assessment's section; non-Approve verdict lists required changes

## Output

```markdown
# Dependency Upgrade Assessment: {Dependency} {Current} -> {Target}   <!-- multi-dep: name the batch, e.g. "Node 16->22 + Express 4->5" -->

## Summary

**Stack:** {detected language / framework}
**Recommendation:** {Go - Now | Go - Planned | Go - Epic | No-Go - Defer | No-Go - Block}  <!-- multi-dep: the batch verdict -->
**Overall Effort:** {S | M | L | XL}
**Risk Level:** {Low | Medium | High}
**Primary Reason:** {one sentence}

## Per-Dependency Verdicts (multi-dependency requests only)

| Dependency | Recommendation | Effort | Sequence (PR order) |
| ---------- | -------------- | ------ | ------------------- |
| {name}     | {verdict}      | {size} | {1st/2nd/with X}    |

## Breaking Changes

| Change                            | Hop (version)   | Type                             | Migration Action | Effort     |
| --------------------------------- | --------------- | -------------------------------- | ---------------- | ---------- |
| {API or behavior removed/changed} | {e.g., 3.4}     | {removal/rename/behavior/config} | {what to do}     | {S/M/L/XL} |

## Compatibility Issues

| Conflict              | Severity                                  | Resolution       |
| --------------------- | ----------------------------------------- | ---------------- |
| {dependency conflict} | {Blocker / Needs own upgrade / Resolvable} | {how to resolve} |

## Security Assessment

- Current version security status: {Supported | End-of-life | Has known CVEs}
- CVEs addressed by target version: {list or "none identified"}

## Migration Effort Breakdown

| Component                | Effort         | Notes                                          |
| ------------------------ | -------------- | ---------------------------------------------- |
| Breaking change fixes    | {S/M/L/XL}     | {count of changes}                             |
| Compatibility resolution | {S/M/L/XL}     | {what needs resolving}                         |
| Test and validation      | {S/M/L/XL}     | {scope of test + integration/smoke test plan}  |
| **Total**                | **{S/M/L/XL}** |                                                |

## Risk Assessment

| Risk Factor         | Level               | Notes                             |
| ------------------- | ------------------- | --------------------------------- |
| Breaking changes    | {None/Low/High}     | {count and severity}              |
| Test coverage       | {Good/Partial/Poor} | {confidence level}                |
| Rollback complexity | {Easy/Hard}         | {data or config impact}           |
| Blast radius        | {Narrow/Wide}       | {scope of affected functionality} |

## Rollback Plan

- **Trigger**: {error rate threshold or failure condition}
- **Procedure**: {steps to revert}
- **Data compatibility**: {whether rollback is clean or requires data handling}
- **Window**: {how long rollback is feasible post-deploy}

## Recommended Next Steps

1. {First action based on recommendation - e.g., "Create spike ticket to validate migration path"}
2. {Second action}
3. {Third action}

## Assumptions

- {Assumption made due to missing codebase context}
```

## Self-Check

- [ ] Breaking changes categorized by type and migration action before effort estimate
- [ ] Compatibility conflicts surfaced (transitive, build tool, runtime); blockers vs warnings
- [ ] Security status of current version stated
- [ ] Rollback plan addresses data/config compatibility, not just "revert the version"
- [ ] Go/No-Go recommendation is actionable and usable for a spike ticket

## Avoid

- Producing a changelog summary instead of a focused impact analysis
- Vague rollback plans ("just revert the version")
- Writing migration code
