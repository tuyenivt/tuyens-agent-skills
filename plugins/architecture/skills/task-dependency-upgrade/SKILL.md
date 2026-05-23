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

Use skill: `stack-detect` to identify the project's language, framework, build tool, and ecosystem.

This shapes:

- Which dependency management conventions apply
- Which compatibility concerns are relevant (e.g., Jakarta EE namespace, transitive dependency resolution)
- Which testing approach validates the upgrade

### Step 2 - Breaking Change Analysis

Do not assume minor version bumps are safe. Ecosystems like Spring Boot, Django, and Rails regularly ship breaking changes in minor releases. Read the full changelog and migration guide for every version in the path, including intermediates.

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

Surface conflicts: transitive dependency version mismatches, build-tool minimums (Gradle/Maven/Bundler/npm), runtime minimums (JDK, Node, Python, Ruby), test library compatibility. Mark each as resolvable, needs-its-own-upgrade, or blocker.

Use skill: `dependency-impact-analysis` for deployment ordering when multiple components must upgrade together.

**Multi-dependency upgrades:** When bumping several deps at once (framework + runtime + type system), check pairwise compatibility - individually safe upgrades can conflict when combined. If interaction risk is high, sequence across separate PRs rather than one batch.

### Step 4 - Security Assessment

State the security status of the current version regardless of whether the upgrade is security-motivated: EOL status, named CVEs the target version fixes, risk of staying. If listing CVEs, cite source rather than speculating.

### Step 5 - Migration Effort Estimate

Aggregate the effort from Step 2 and any compatibility work from Step 3:

| Component                | Effort   | Notes                             |
| ------------------------ | -------- | --------------------------------- |
| Breaking change fixes    | S/M/L/XL | Per change or aggregate           |
| Compatibility resolution | S/M/L/XL | Transitive conflicts, build tool  |
| Test update              | S/M/L/XL | Test library compat, new patterns |
| Validation               | S/M/L/XL | Integration tests, smoke tests    |
| **Total**                | S/M/L/XL | Combined estimate                 |

Size guidance:

- **S**: Config changes only, no API changes, well-supported migration path
- **M**: A few API changes, one compatibility fix, low test surface impact
- **L**: Multiple API changes, behavior changes requiring logic review, significant test updates
- **XL**: Architectural changes, namespace migrations, runtime version upgrade - should be a dedicated epic

### Step 6 - Risk Assessment

Use skill: `review-blast-radius` for upgrade risk: affected features/flows, blast radius of a regression, canary or feature-flag options for limited rollout exposure.

| Risk Factor         | Level             | Notes                                     |
| ------------------- | ----------------- | ----------------------------------------- |
| Breaking changes    | None/Low/High     | Count and severity of changes             |
| Test coverage       | Good/Partial/Poor | Confidence level for catching regressions |
| Rollback complexity | Easy/Hard         | Whether rollback requires data changes    |
| Blast radius        | Narrow/Wide       | Scope of affected functionality           |

### Step 7 - Rollback Plan

Use skill: `ops-release-safety` for rollback patterns.

Define before the upgrade starts: trigger (specific signal - error rate, latency, failed smoke), procedure, data compatibility (schema/config/message-format changes complicate rollback), time window.

If the upgrade changes schema, config, or message format, an expand-contract strategy is required - "just revert" no longer works.

### Step 8 - Go / No-Go Recommendation

Produce a clear recommendation:

| Recommendation | When                                                                             |
| -------------- | -------------------------------------------------------------------------------- |
| Go - Now       | Breaking changes are minor, effort is S/M, risk is low, security benefit is high |
| Go - Planned   | Effort is L, schedule as a dedicated sprint item with proper testing             |
| Go - Epic      | Effort is XL, requires its own epic, cross-team coordination, or infrastructure  |
| No-Go - Defer  | Benefit does not justify disruption at this time; reassess in N months           |
| No-Go - Block  | Compatibility blockers, unresolved conflicts, or critical breaking changes       |

State the primary reason for the recommendation.

## Review Mode

When reviewing an upgrade assessment authored by someone else:

Use skill: `architecture-review-lens` for severity taxonomy, completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and verdict.

Supply this upgrade-assessment-specific factor list to the completeness audit:

| Factor                       | What "Present" Looks Like                                                         |
| ---------------------------- | --------------------------------------------------------------------------------- |
| Version path                 | Current and target versions stated; intermediate minor versions assessed          |
| Breaking changes             | Categorized by type (removal/rename/behavior/config) with migration action        |
| Compatibility conflicts      | Transitive, build tool, runtime conflicts surfaced; blockers vs warnings          |
| Multi-dependency interaction | When upgrading multiple deps, interaction effects and required ordering assessed  |
| Security status              | Current version EOL/CVE status stated, even when upgrade is not security-driven   |
| Effort estimate              | S/M/L/XL per component (breaking changes, compatibility, tests, validation)       |
| Blast radius                 | Which features/flows depend on the dependency; canary/feature-flag options        |
| Rollback plan                | Trigger, procedure, data compatibility, time window - not just "revert version"   |
| Recommendation               | Go-Now / Go-Planned / Go-Epic / No-Go-Defer / No-Go-Block with primary reason     |

Specific quality checks beyond the standard lens:

- **Minor-version upgrade assumed safe without changelog review**: Blocker for ecosystems known to break in minor versions (Spring Boot, Django, Rails)
- **Effort estimate without breaking change inventory**: Major; the estimate is unbacked
- **"Just revert" rollback plan**: Major when the upgrade changes schema, config, or message format
- **No security status for an EOL or vulnerable current version**: Major minimum
- **Recommendation not actionable for a spike ticket**: Minor; promote to Major when blast radius is Wide

Output header: `# Upgrade Assessment Review` and use the output structure defined in `architecture-review-lens`. Skip the New Assessment output template.

## Output

```markdown
# Dependency Upgrade Assessment: {Dependency} {Current} -> {Target}

## Summary

**Stack:** {detected language / framework}
**Recommendation:** {Go - Now | Go - Planned | Go - Epic | No-Go - Defer | No-Go - Block}
**Overall Effort:** {S | M | L | XL}
**Risk Level:** {Low | Medium | High}
**Primary Reason:** {one sentence}

## Breaking Changes

| Change                            | Type                             | Migration Action | Effort     |
| --------------------------------- | -------------------------------- | ---------------- | ---------- |
| {API or behavior removed/changed} | {removal/rename/behavior/config} | {what to do}     | {S/M/L/XL} |

## Compatibility Issues

| Conflict              | Severity | Resolution |
| --------------------- | -------- | ---------- | ---------------- |
| {dependency conflict} | {Blocker | Warning}   | {how to resolve} |

## Security Assessment

- Current version security status: {Supported | End-of-life | Has known CVEs}
- CVEs addressed by target version: {list or "none identified"}

## Migration Effort Breakdown

| Component                | Effort         | Notes                           |
| ------------------------ | -------------- | ------------------------------- |
| Breaking change fixes    | {S/M/L/XL}     | {count of changes}              |
| Compatibility resolution | {S/M/L/XL}     | {what needs resolving}          |
| Test updates             | {S/M/L/XL}     | {scope of test impact}          |
| Validation               | {S/M/L/XL}     | {integration / smoke test plan} |
| **Total**                | **{S/M/L/XL}** |                                 |

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
