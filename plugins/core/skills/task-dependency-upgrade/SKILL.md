---
name: task-dependency-upgrade
description: Assess a library or platform version upgrade - changelog analysis, breaking change detection, migration effort estimate, and rollback plan. Not for writing migration code (use task-feature-implement for that).
metadata:
  category: planning
  tags: [dependencies, upgrade, migration, breaking-changes, risk]
  type: workflow
user-invocable: true
---

# Dependency Upgrade Assessment

## Purpose

Structured upgrade assessment for tech leads deciding whether and how to upgrade a library or platform version:

- **Breaking change detection** -- identify API removals, behavior changes, and configuration renames that require code changes
- **Migration effort estimate** -- size the work before committing to the upgrade
- **Compatibility analysis** -- detect conflicts with other dependencies in the dependency graph
- **Rollback plan** -- define rollback criteria and procedure before the upgrade starts
- **Go / No-Go recommendation** -- a clear recommendation with reasoning, not just a list of findings

This skill produces an upgrade assessment. It does not write migration code (use `/task-feature-implement` for the implementation phase).

## When to Use

- Before upgrading a major framework version (e.g., Spring Boot 3.4 to 3.5, Rails 7 to 8, .NET 8 to .NET 9)
- Before upgrading a library with a major version bump
- When a dependency has known security vulnerabilities requiring an upgrade
- When evaluating whether an upgrade is worth the disruption relative to the benefit
- Before upgrading a build tool, runtime, or language version

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

- Always surface breaking changes before migration effort - breaking changes determine feasibility
- Every breaking change must have a migration action (update / replace / workaround / defer)
- Compatibility conflicts with other dependencies must be surfaced before the effort estimate
- Effort estimates are relative (S/M/L/XL) - never calendar time unless asked
- Every assessment must produce a Go / No-Go recommendation with reasoning
- Rollback plan must be defined even for low-risk upgrades
- Omit empty sections in output

## Assessment Model

### Step 1 - Stack Detection

Use skill: `stack-detect` to identify the project's language, framework, build tool, and ecosystem.

This shapes:

- Which dependency management conventions apply
- Which compatibility concerns are relevant (e.g., Jakarta EE namespace, transitive dependency resolution)
- Which testing approach validates the upgrade

### Step 2 - Breaking Change Analysis

Analyze the changelog and migration guide for the target version:

Categorize breaking changes by type:

| Change Type            | Examples                                                       | Migration Effort             |
| ---------------------- | -------------------------------------------------------------- | ---------------------------- |
| API removal            | Deleted class, method, or endpoint                             | Code change required         |
| API rename / move      | Package rename, method rename, class rename                    | Automated refactor possible  |
| Behavior change        | Different default, changed semantics, new required param       | Logic review and test update |
| Configuration change   | New property name, removed property, changed default value     | Config file update           |
| Transitive dep upgrade | Pulled-in dependency version change causing indirect conflicts | Dependency resolution        |
| Runtime requirement    | New minimum JVM version, OS library, or build tool version     | Infrastructure change        |

For each breaking change relevant to this codebase:

- State the change
- State the migration action
- State the effort (S/M/L/XL per change)

Use skill: `backward-compatibility-analysis` to assess API and data contract impact.

### Step 3 - Compatibility Check

Identify conflicts with other dependencies in the graph:

- Transitive dependency version conflicts (A requires X 2.x, B requires X 3.x)
- Build tool version requirements (new version requires newer Gradle/Maven/Bundler/npm)
- Runtime version requirements (new JDK, Ruby, Node.js, Python version needed)
- Test library compatibility (test framework may need a version bump too)

State each conflict and whether it can be resolved, needs its own upgrade, or is a blocker.

Use skill: `dependency-impact-analysis` to assess deployment ordering if multiple components must upgrade together.

### Step 4 - Security Assessment

Assess whether this upgrade addresses known vulnerabilities:

- List CVEs addressed by the target version (if this is a security-motivated upgrade)
- Assess whether staying on the current version introduces unacceptable security risk
- Note if the current version has reached end-of-life (no security patches)

If the upgrade is not security-motivated, note the security status of the current version.

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

Use skill: `blast-radius-analysis` to assess upgrade risk:

- Which features and flows depend on this dependency?
- What is the blast radius if the upgrade introduces a regression?
- Are there canary or feature-flag options to limit rollout exposure?

| Risk Factor         | Level             | Notes                                     |
| ------------------- | ----------------- | ----------------------------------------- |
| Breaking changes    | None/Low/High     | Count and severity of changes             |
| Test coverage       | Good/Partial/Poor | Confidence level for catching regressions |
| Rollback complexity | Easy/Hard         | Whether rollback requires data changes    |
| Blast radius        | Narrow/Wide       | Scope of affected functionality           |

### Step 7 - Rollback Plan

Define the rollback procedure before the upgrade starts:

- **Rollback trigger**: What signals indicate the upgrade should be rolled back (error rate, latency, failed smoke tests)
- **Rollback procedure**: Steps to revert to the previous version
- **Data compatibility**: Whether the upgrade changes any persistent data format that makes rollback complex
- **Time window**: How long after deploy is rollback still feasible

If the upgrade changes database schema, configuration format, or message format, note the expand-contract strategy needed.

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

### Output Constraints

- Breaking changes must be categorized by type and migration action
- Every Go recommendation must include a rollback plan
- Every No-Go must state the blocker or reason
- Effort estimates are relative - no false precision in days or hours
- Omit sections with no content (e.g., no compatibility issues found)

## Success Criteria

A well-executed upgrade assessment passes all of these.

### Completeness

- [ ] Breaking changes identified and categorized before effort estimate
- [ ] Compatibility conflicts surfaced (transitive deps, build tool, runtime)
- [ ] Security status of current version stated
- [ ] Rollback plan defined
- [ ] Go / No-Go recommendation with reasoning

### Signal Quality

- [ ] Migration effort is grounded in the count and type of breaking changes, not guessing
- [ ] Compatibility blockers are distinguished from warnings
- [ ] Rollback plan addresses data and config compatibility, not just "revert the version bump"

### Tech Lead Utility

- [ ] Recommendation is clear and actionable - no "it depends" without a tiebreaker
- [ ] Output can be used to create a spike or implementation ticket
- [ ] Stakeholders can see why the recommendation was made

## Avoid

- Recommending an upgrade without identifying breaking changes first
- Estimating effort before surfacing compatibility blockers
- Vague rollback plans ("just revert the version")
- Producing a changelog summary instead of a focused impact analysis
- Writing migration code (use `task-feature-implement` after this assessment)

## Key Skills Reference

- Use skill: `stack-detect` for ecosystem context
- Use skill: `backward-compatibility-analysis` for API and contract impact
- Use skill: `dependency-impact-analysis` for deployment ordering
- Use skill: `blast-radius-analysis` for upgrade risk scope

## After This Skill

If the output needed significant adjustment - breaking changes were missed, effort was miscalibrated, or the recommendation was wrong - run `/task-skill-feedback` to log what changed and why.
