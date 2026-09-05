---
name: task-dependency-upgrade
description: "Plan or review library/platform upgrade: changelog analysis, breaking change detection, effort estimate (S/M/L/XL), Go/No-Go."
agent: architecture-planner
metadata:
  category: planning
  tags: [dependencies, upgrade, migration, breaking-changes, risk]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows. Delegated skills supply analysis method, not structure: this skill's Output template is the only output contract - absorb their findings into its sections and never emit their own Output blocks.

# Dependency Upgrade Assessment

## Purpose

Structured upgrade assessment: breaking change detection, compatibility analysis, effort estimate (S/M/L/XL), rollback plan, and Go/No-Go recommendation. Produces an assessment; no migration code.

## When to Use

- Before upgrading a framework across a version that ships breaking changes, major or minor (e.g., Spring Boot 3.4 to 3.5, Rails 7 to 8, .NET 8 to .NET 10)
- Before upgrading a library with a major version bump
- When a dependency has known security vulnerabilities requiring an upgrade
- When evaluating whether an upgrade is worth the disruption relative to the benefit
- Before upgrading a build tool, runtime, or language version

Not for writing migration code or whole-system tech stack modernization (use `task-migrate-architecture`, Shape: Modernize).

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

Use skill: `stack-detect` to identify the project's language, framework, build tool, and ecosystem. If it finds nothing, use the stack stated in the request. Where the upgrade targets one module of a polyglot repo, detect that module's stack rather than the repo's primary one, and record which you used.

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

Surface conflicts: transitive dependency version mismatches, build-tool minimums (Gradle/Maven/Bundler/npm), runtime minimums (JDK, Node, Python, Ruby), test library compatibility. Mark each Resolvable, Needs own upgrade, or Blocker (the Output's Severity enum). `Blocker` here means the conflict has no resolution short of another upgrade; it is not the lens severity of the same name that Review Mode uses.

Use skill: `dependency-impact-analysis` for deployment ordering when separately deployed components must upgrade together. Several packages inside one manifest are not that case - order them in the Sequence column instead.

**Multi-dependency upgrades.** A request is multi-dependency when it names more than one dependency, or when the manifest pins transitive versions the target release moves - a framework bump that forces new pins for its migration tool, API docs or test containers is multi-dependency even though one dependency was named. When bumping several deps at once (framework + runtime + type system), check pairwise compatibility - individually safe upgrades can conflict when combined. If interaction risk is high, sequence across separate PRs rather than one batch.

### Step 4 - Security Assessment

State the security status of both versions regardless of whether the upgrade is security-motivated: the current version's EOL status, named CVEs the target version fixes, and the risk of staying. Check the target's own support status too - a target already past EOL is `No-Go - Block` unless a later supported version is out of scope for a stated reason - a named constraint such as a larger migration deferred to a later quarter, not merely the requester having named this version. If listing CVEs, cite source rather than speculating; offline, name known CVEs tagged [VERIFY] - never invent IDs.

### Step 5 - Migration Effort Estimate

Aggregate the effort from Step 2 and any compatibility work from Step 3. Total = the largest component effort, bumped one size when two or more components share that size **and that size is M or above**; `None` components are skipped, not counted toward the bump - three S components stay S, since a small config change does not become medium by having three parts - and XL never bumps further. The Size guidance below profiles the upgrade as a whole and sets a floor for the Total only when the change class it names is actually present - a runtime *major* upgrade is XL, a patch bump of the same runtime is not. It does not classify individual components. For multi-dependency requests, render one breakdown table per dependency, then a batch total aggregated from the per-dependency totals by the same rule (XL does not bump further):

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

Use skill: `review-blast-radius` for upgrade risk: affected features and flows, and the blast radius of a regression. Exposure control - canary, feature flag, staged rollout - comes from `ops-release-safety` in Step 7, not from this skill.

| Risk Factor         | Level             | Notes                                     |
| ------------------- | ----------------- | ----------------------------------------- |
| Breaking changes    | None/Low/High     | High = removals, behavior changes, or a new runtime requirement; Low = renames, config, or transitive bumps that resolve cleanly; None = none in the inventory |
| Test coverage       | Good/Partial/Poor | Confidence level for catching regressions |
| Rollback complexity | Easy/Hard         | Whether rollback requires data changes    |
| Blast radius        | Narrow/Wide       | Scope of affected functionality (review-blast-radius Moderate or above maps to Wide; in its two-state mitigated form, read the mitigated value on `in-place:` and the unmitigated one on `required:`) |

Summary Risk Level: High when 2+ factors sit at their worst level (High/Poor/Hard/Wide), Medium when exactly one does, Low otherwise. Test coverage unverifiable from the given context is Partial, recorded in Assumptions. Partial or Poor test coverage on an upgrade with behavior changes adds a prerequisite (backfill tests on affected flows) to Recommended Next Steps.

### Step 7 - Rollback Plan

Use skill: `ops-release-safety` for rollback patterns.

Define before the upgrade starts: trigger (specific signal - error rate, latency, failed smoke), procedure, data compatibility (schema/config/message-format changes complicate rollback), time window, and exposure control (Step 6's canary/flag option, or "full deploy").

If the upgrade changes schema or message format, an expand-contract strategy is required - "just revert" no longer works. A config-property rename reverts with the deploy that introduced it, unless its value is persisted or read by another system.

### Step 8 - Go / No-Go Recommendation

Produce a clear recommendation. Apply these tests in order and stop at the first that fires, so every value stays reachable:

1. An unresolved compatibility `Blocker`, or a target version that is itself unsupported -> **No-Go - Block**.
2. The upgrade is feasible but its benefit does not justify the disruption now -> **No-Go - Defer**, naming what would change that and the signal to reassess on.
3. Effort XL, or cross-team coordination or an infrastructure change is required -> **Go - Epic**.
4. Effort L, or risk Medium/High -> **Go - Planned**.
5. Otherwise - effort S/M, risk Low, nothing unresolved -> **Go - Now**.

The table restates the same tests:

| Recommendation | When                                                                             |
| -------------- | -------------------------------------------------------------------------------- |
| Go - Now       | Effort S/M, risk Low, nothing left unresolved in the Compatibility table |
| Go - Planned   | Effort L, or risk Medium/High - schedule as a dedicated sprint item with testing |
| Go - Epic      | Effort XL, or cross-team coordination or infrastructure change required          |
| No-Go - Defer  | Feasible, but the benefit does not justify the disruption now; name what would change that and the signal to reassess on |
| No-Go - Block  | An unresolved `Blocker` in the Compatibility table, or a target version that is itself unsupported |

State the primary reason, weighing stated constraints (deadlines, freeze windows, team rotation) - name them in it. A stated deadline or window counts as "asked" for calendar time: map the PR sequence to the window. For multi-dependency requests, give a per-dependency verdict plus a batch verdict. Sequencing is a shape, not a verdict: when the deps are individually fine but unsafe batched, the Summary Recommendation stays a single enum value (usually `Go - Planned`, or `Go - Epic` at XL), the Primary Reason says the batch was rejected in favour of sequenced PRs, and the Sequence column carries the order. `No-Go - Block` is reserved for deps that cannot ship at all. The Risk Assessment table covers the batch; the Rollback Plan follows the shipped shape - one plan for a batched upgrade, or one row per PR carrying every field the bullet form carries when sequenced.

## Review Mode

When reviewing an upgrade assessment authored by someone else:

Use skill: `architecture-review-lens` for severity taxonomy, intake, completeness audit, internal-consistency check, assumptions audit, per-factor findings, criteria scoring, questions for the author, and verdict.

Reviews run the full lens (standalone formatting defaults; the lens's skip rule covers steps that do not fit). Step 1's `stack-detect` still runs: in Review Mode it grounds ecosystem-specific breaking-change expectations and names the compatibility concerns a complete assessment should have covered, and it lands on the review's context line, never as its own block. Where the assessment covers one module of a polyglot repo, detect that module's stack and say so on the same line. Review Mode does not re-run the Step 2-7 delegations; their tables are the bar the artifact must meet - cite them as review evidence, and load one only when a finding's severity turns on it. The Assessment Model's tables (change taxonomy, size guidance, Go/No-Go criteria, Step 3's batching rule) apply the same way. The reviewer may state a corrected value inside a finding's recommendation ("expect L-XL, not S") but does not author a replacement assessment.

Supply this upgrade-assessment-specific factor list to the completeness audit. The `Required` column gates the Approve verdict; it does not bound severity. The lens's own floors apply to every factor, Required or not - a Missing factor is Blocker when the decision cannot be made without it.

| Factor                       | Required | What "Present" Looks Like                                                         |
| ---------------------------- | -------- | --------------------------------------------------------------------------------- |
| Version path                 | Yes      | Current and target versions stated; intermediate versions assessed                |
| Breaking changes             | Yes      | Categorized by type (removal / rename / behavior / config / transitive / runtime) with migration action |
| Compatibility conflicts      | Yes      | Transitive, build tool, runtime conflicts surfaced, each marked Resolvable / Needs own upgrade / Blocker |
| Multi-dependency interaction | Yes*     | When upgrading multiple deps, interaction effects and required ordering assessed  |
| Security status              | No       | Current version EOL/CVE status stated, even when upgrade is not security-driven   |
| Effort estimate              | No       | S/M/L/XL per component (breaking changes, compatibility, test and validation)     |
| Blast radius                 | No       | Which features/flows depend on the dependency; canary/feature-flag options        |
| Rollback plan                | Yes      | Trigger, procedure, data compatibility, time window, exposure control - not just "revert version" |
| Recommendation               | Yes      | Go - Now / Go - Planned / Go - Epic / No-Go - Defer / No-Go - Block, with primary reason |

*Required whenever the request is multi-dependency by Step 3's definition - including a single named dependency whose target release moves pinned transitives.

Specific quality checks beyond the standard lens:

- **Upgrade assumed safe without changelog review** (any version distance): Blocker for ecosystems known to break in minor versions (Spring Boot, Django, Rails); Major otherwise
- **Effort estimate without breaking change inventory**: Major; the estimate is unbacked
- **"Just revert" rollback plan**: Major when the upgrade changes schema or message format - or when the assessment never established that it does not
- **No security status for an EOL or vulnerable current version**: Major minimum
- **Recommendation not actionable for a spike ticket**: Minor; promote to Major when blast radius is Wide (per the artifact, or the reviewer's assessment when the artifact omits it - flag it as reviewer context)

Record each quality-check hit once, in the lens step that owns it (Missing or Under-specified factor -> Completeness; internal contradiction -> Internal Consistency; Present-but-wrong content -> Per-Factor Findings). A check's preset severity is a floor, not a ceiling. Reviewer-known but unverifiable facts follow the same [VERIFY] convention as Step 2.

Output header: `# Upgrade Assessment Review` and use the output structure defined in `architecture-review-lens`. Skip the assessment Output template below - the lens's required-changes checklist is the review's action list, so no separate Recommended Next Steps section is emitted. The lens emits that checklist only on a non-Approve verdict; an Approve review closes with one line stating that nothing must change before adoption. An author document that uses none of this skill's vocabulary is still audited against the factor list on substance; say so in Intake rather than marking every factor Missing on wording. In this mode the Review Self-Check replaces the authoring Self-Check (self-checks are applied internally, never emitted in the deliverable):

- [ ] Step 1's stack detected and carried on the review's context line, scoped to the module under review in a polyglot repo
- [ ] All factors audited with Required marking applied; verdict driven by highest severity
- [ ] Quality-check hits recorded once in the correct lens step and numbered
- [ ] Every finding cites the assessment's section; non-Approve verdict lists required changes

## Output

```markdown
# Dependency Upgrade Assessment: {Dependency} {Current} -> {Target}   <!-- multi-dep: name the batch, e.g. "Node 22->24 + Express 4->5" -->

## Summary

- **Stack:** {detected language / framework}
- **Recommendation:** {Go - Now | Go - Planned | Go - Epic | No-Go - Defer | No-Go - Block}  <!-- multi-dep: the batch verdict -->
- **Overall Effort:** {S | M | L | XL}
- **Risk Level:** {Low | Medium | High}
- **Primary Reason:** {one sentence}

## Per-Dependency Verdicts (multi-dependency requests only)

| Dependency | Recommendation | Effort | Sequence (PR order) |
| ---------- | -------------- | ------ | ------------------- |
| {name}     | {verdict}      | {size} | {1st/2nd/with X}    |

## Breaking Changes

| Change                            | Hop (version)   | Type                             | Migration Action | Effort     |
| --------------------------------- | --------------- | -------------------------------- | ---------------- | ---------- |
| {API or behavior removed/changed} | {e.g., 3.4}     | {removal \| rename \| behavior \| config \| transitive \| runtime} | {what to do}     | {S/M/L/XL} |

## Compatibility Issues

| Conflict              | Severity                                  | Resolution       |
| --------------------- | ----------------------------------------- | ---------------- |
| {dependency conflict} | {Blocker / Needs own upgrade / Resolvable} | {how to resolve} |

## Security Assessment

- Current version status: {Supported | Maintenance | End-of-life | Unknown [VERIFY]}, target version status: {Supported | Maintenance | End-of-life | Unknown [VERIFY]}
- Open CVEs on the current version: {list with source, "none identified", or "none identified [VERIFY]"}
- CVEs addressed by target version: {list with source, "none identified", or "none identified [VERIFY]"}
- Risk of staying: {one sentence}

## Migration Effort Breakdown

<!-- multi-dep: one `### {Dependency}` subheading carrying this table per dependency, then a final `### Batch total` table aggregated by the Step 5 rule -->

| Component                | Effort         | Notes                                          |
| ------------------------ | -------------- | ---------------------------------------------- |
| Breaking change fixes    | {None/S/M/L/XL} | {count of changes}                             |
| Compatibility resolution | {None/S/M/L/XL} | {what needs resolving; None when the table is empty} |
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

<!-- sequenced multi-dep: replace the bullets with one table: | PR | Trigger | Procedure | Data compatibility | Exposure control | Window | -->

- **Trigger**: {error rate threshold or failure condition}
- **Procedure**: {steps to revert}
- **Data compatibility**: {whether rollback is clean or requires data handling}
- **Window**: {how long rollback is feasible post-deploy}
- **Exposure control**: {canary | feature flag | staged rollout | full deploy}

## Recommended Next Steps

1. {First action based on recommendation - e.g., "Create spike ticket to validate migration path"}
2. {Second action}
3. {Third action}

## Assumptions

- {Assumption made due to missing codebase context}
```

## Self-Check

- [ ] behavioral-principles loaded before any step; Step 1: stack detected, or the request-stated stack used
- [ ] Step 2: breaking changes categorized by type and migration action, per hop, before any effort estimate; unverified claims tagged [VERIFY]
- [ ] Step 3: compatibility conflicts surfaced (transitive, build tool, runtime), each marked Resolvable / Needs own upgrade / Blocker; multi-dependency requests checked pairwise
- [ ] Step 4: security status of both current and target versions stated, with the risk of staying
- [ ] Step 5: per-component efforts aggregated by the stated rule; one table per dependency plus a batch total on multi-dependency requests
- [ ] Step 6: all four risk factors levelled and the Summary Risk Level derived from them
- [ ] Step 7: rollback plan addresses data compatibility and exposure control, not just "revert the version"
- [ ] Step 8: Go/No-Go recommendation is a single enum value, actionable for a spike ticket; per-dependency verdicts and PR sequence given when multi-dependency

## Avoid

- Producing a changelog summary instead of a focused impact analysis
- Vague rollback plans ("just revert the version")
- Writing migration code
