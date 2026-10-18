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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows. Delegated skills supply analysis method, not structure: this skill's Output template is the only output contract - absorb their findings into its sections and never emit their own Output blocks. Review Mode is the one exception: it emits `architecture-review-lens`'s structure, as its section says.

# Dependency Upgrade Assessment

## Purpose

Structured upgrade assessment: breaking change detection, compatibility analysis, effort estimate (S/M/L/XL), rollback plan, and Go/No-Go recommendation. Produces an assessment; no migration code.

## When to Use

- Before upgrading a framework across a version that ships breaking changes, major or minor (e.g., Spring Boot 4.0 to 4.1, Rails 7 to 8, .NET 8 to .NET 10)
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

### Step 1 - Behavioral Rules, then Stack Detection

Use skill: `behavioral-principles`. Then use skill: `stack-detect` to identify the project's language, framework, build tool, and ecosystem. If it finds nothing, use the stack stated in the request. Where the upgrade targets one module of a polyglot repo, take that module's stack from stack-detect's `Additional` entry for it, or from the module's own manifest when stack-detect does not surface it, and name the module on the Summary's `Stack:` line; a platform component that is no code module (a broker cluster) is named as `component <name>` beside the repo's stack.

This shapes:

- Which dependency management conventions apply
- Which compatibility concerns are relevant (e.g., Jakarta EE namespace, transitive dependency resolution)
- Which testing approach validates the upgrade

### Step 2 - Breaking Change Analysis

Do not assume minor version bumps are safe. Ecosystems like Spring Boot, Django, and Rails regularly ship breaking changes in minor releases. Read the full changelog and migration guide for every version in the path, including intermediates - assess per hop (a hop is each version in the path that ships a breaking change; a patch release that ships none is not one), then merge into one inventory with per-hop labels. When changelogs cannot be fetched (offline), work from known-version knowledge, tag every unverified claim **[VERIFY]**, and put "verify changelog/migration guide" in the verification slot that heads Recommended Next Steps (Step 8) - never present unverified changes as confirmed.

Categorize breaking changes by type:

| Change Type            | Examples                                                       | Typical Action               |
| ---------------------- | -------------------------------------------------------------- | ---------------------------- |
| API removal            | Deleted class, method, or endpoint                             | Code change required         |
| API rename / move      | Package rename, method rename, class rename                    | Automated refactor possible  |
| Behavior change        | Different default, changed semantics, new required param       | Logic review and test update |
| Configuration change   | New property name, removed property, changed default value     | Config file update           |
| Transitive dep upgrade | Pulled-in dependency whose new version changes behaviour your code relies on | Logic review and test update; a version conflict with no code change is a Step 3 row |
| Runtime requirement    | A new runtime or build-tool minimum that forces a code change (removed JDK API, changed language semantics) | Code change; a minimum with no code change is a Step 3 row |

Per change relevant to the codebase: change, migration action, effort (S/M/L/XL). A version-forced API relocation (a package move) is `rename`; `transitive` is a pulled-in dependency whose new version changes behaviour in your code. A pin conflict with no code change, like a runtime or build-tool minimum with none, is a Step 3 compatibility row, not a breaking change.

Use skill: `ops-backward-compatibility` for API and data contract impact.

### Step 3 - Compatibility Check

Surface conflicts: transitive dependency version mismatches, build-tool minimums (Gradle/Maven/Bundler/npm), runtime minimums (JDK, Node, Python, Ruby), test library compatibility, and an unpinned dependency the deploy relies on (the app server) - a row here even when absent from the manifest. Mark each Resolvable, Needs own upgrade, Needs own upgrade [VERIFY], or Blocker (the Output's Severity enum). `Blocker` here means no compatible release exists at all; `Needs own upgrade` means one exists and must ship first; neither is the lens severity of the same name that Review Mode uses. Offline, a third-party plugin whose compatible release cannot be confirmed is `Needs own upgrade [VERIFY]`, not Blocker; a pin the target release itself moves (its migration tool, its test containers) is a `Resolvable` row riding the forcing PR (Per-Dependency: `with <forcing dependency>`), not a `Needs own upgrade` row.

Use skill: `dependency-impact-analysis` for deployment ordering when separately deployed components must upgrade together, and for its blocker strategies (wait / swap / shim / fork) on every `Blocker` row - a Blocker with a viable strategy keeps `Blocker` as its Severity, carries the strategy and its removal condition in its Resolution cell, and becomes a prerequisite Next Step - a multi-PR shape for rung 5 when the strategy ships its own PR. Several packages inside one manifest are not the ordering case - order them in the Sequence column, the one the other's target requires first.

**Multi-dependency upgrades.** A request is multi-dependency when it names more than one dependency, or when the manifest pins transitive versions the target release moves - a framework bump that forces new pins for its migration tool, API docs or test containers is multi-dependency even though one dependency was named. When bumping several deps at once (framework + runtime + type system), check pairwise compatibility - individually safe upgrades can conflict when combined. Sequence across separate PRs unless the batched changes are inseparable - one cannot build or run without the other - so that each deploy carries one risky change whose rollback is attributable (`ops-release-safety`'s rule); a framework bump batched with a runtime bump never qualifies. Inseparable pins ride in the PR of the dependency that forces them.

### Step 4 - Security Assessment

State the security status of both versions regardless of whether the upgrade is security-motivated: the current version's EOL status, CVEs open on it, which of them the target fixes, and the risk of staying. Offline, a version whose support dates are not known reads `Unknown [VERIFY]`; `Supported` is written only when the dates are. A target in `Maintenance` is a Go with the next-target date as a Next Step; `Unknown [VERIFY]` on the target puts verifying its support in the verification slot that heads Next Steps. Check the target's own support status too - a target already past EOL is `No-Go - Block` unless a later supported version is out of scope for a stated reason - a named constraint such as a larger migration deferred to a later quarter, not merely the requester having named this version. If listing CVEs, cite source rather than speculating; offline, name known CVEs tagged [VERIFY] - never invent IDs.

### Step 5 - Migration Effort Estimate

Aggregate the effort from Step 2 and any compatibility work from Step 3. Total = the largest component effort, bumped one size when two or more components share that size **and that size is M or above**; `None` components are skipped, not counted toward the bump - three S components stay S, since a small config change does not become medium by having three parts - and XL never bumps further. The Size guidance below profiles the upgrade as a whole and sets a floor for the Total only when the change class it names is actually present - a runtime *major* upgrade is XL; a minor or feature release of the same runtime takes the size its inventory earns; a patch bump is not. It does not classify individual components. Per-dependency verdicts use each dependency's own effort with the batch Risk Level. For multi-dependency requests, and for each dependency a `Needs own upgrade` row ships first, render one breakdown table per dependency, then a batch total aggregated from the per-dependency totals by the same rule (XL does not bump further):

| Component                | Effort   | Notes                                          |
| ------------------------ | -------- | ---------------------------------------------- |
| Breaking change fixes    | None/S/M/L/XL | Per change or aggregate                   |
| Compatibility resolution | None/S/M/L/XL | Transitive conflicts, build tool          |
| Test and validation      | S/M/L/XL | Test library compat, integration + smoke tests |
| **Total**                | S/M/L/XL | Combined estimate                              |

Size guidance:

- **S**: Config changes only, no API changes, well-supported migration path
- **M**: A few API changes, one compatibility fix, low test surface impact
- **L**: Multiple API changes, behavior changes requiring logic review, significant test updates
- **XL**: Architectural changes, namespace migrations, runtime major upgrade - should be a dedicated epic

### Step 6 - Risk Assessment

Use skill: `review-blast-radius` for upgrade risk: affected features and flows, and the blast radius of a regression. Exposure control - canary, feature flag, staged rollout - comes from `ops-release-safety` in Step 7, not from this skill.

| Risk Factor         | Level             | Notes                                     |
| ------------------- | ----------------- | ----------------------------------------- |
| Breaking changes    | None/Low/High     | High = removals, behavior changes, or a runtime major in the path (whether or not it forced code changes); Low = renames, config, or a minor runtime bump that forced a code change (a transitive bump or runtime minimum that resolves with none is a Step 3 row and does not level this factor; a `transitive` inventory row changes behaviour and is High); None = none in the inventory and no runtime major |
| Test coverage       | Good/Partial/Poor | Confidence level for catching regressions |
| Rollback complexity | Easy/Hard         | Whether rollback requires data changes    |
| Blast radius        | Narrow/Wide       | Scope of affected functionality (review-blast-radius Moderate or above maps to Wide; in its two-state mitigated form, read the mitigated value on `in-place:` and the unmitigated one on `required:`) |

Summary Risk Level: High when 2+ factors sit at their worst level (High/Poor/Hard/Wide), Medium when exactly one does, Low otherwise. Test coverage unverifiable from the given context is Partial, recorded in Assumptions. Partial or Poor test coverage on an upgrade with behavior changes adds a prerequisite (backfill tests on affected flows) to Recommended Next Steps.

### Step 7 - Rollback Plan

Use skill: `ops-release-safety` for rollback patterns.

Define before the upgrade starts: trigger (specific signal - error rate, latency, failed smoke), procedure, data compatibility (schema/config/message-format changes complicate rollback), time window, exposure control (`ops-release-safety`'s rollout strategy - feature flag, canary, blue-green, rolling update - or `one-shot script` for a run-once data or config step, or `big bang (as proposed) - {why the topology allows nothing finer}` - never selected on a Wide blast radius, where the missing finer control becomes a prerequisite Next Step - Wide already puts Risk at Medium or above, so the Step 8 ladder never lands on rung 5), deploy order (from `dependency-impact-analysis` when separately deployed components upgrade together), and the point of no return past which the plan rolls forward instead. A rate trigger carries `ops-release-safety`'s sample requirement: enough requests in the window to tell the trigger from the baseline (thousands for a sub-percent gap), or an absolute count where the slice cannot reach it.

If the upgrade changes schema or message format, an expand-contract strategy is required - "just revert" no longer works. A config-property rename reverts with the deploy that introduced it, unless its value is persisted or read by another system.

### Step 8 - Go / No-Go Recommendation

Produce a clear recommendation, then the Recommended Next Steps in this order: the verification slot (Step 2's changelog verification, Step 4's target-support verification - offline only), the first action the recommendation implies, then every prerequisite Steps 3, 4, 6 and 7 raised (a `Needs own upgrade` row's own PR first among them); and the Assumptions list (every default taken for missing context). Apply these tests in order and stop at the first that fires, so every value stays reachable:

1. An unresolved compatibility `Blocker`, or a target version that is itself unsupported with no Step 4 reason a later supported one is out of scope -> **No-Go - Block**.
2. The upgrade is feasible but its benefit does not justify the disruption now -> **No-Go - Defer**, naming what would change that and the signal to reassess on.
3. Effort XL, or cross-team coordination or an infrastructure change (a runtime or build-tool *major*, new OS libraries, a datastore the target requires - not a minor or patch bump) is required -> **Go - Epic**.
4. Effort L, or risk Medium/High -> **Go - Planned**.
5. Effort S/M and risk Low, one PR -> **Go - Now**. Any multi-PR shape - a `Needs own upgrade` row shipping first, or a batch sequenced by Step 3 - is **Go - Planned** whatever the sizes, since the shape needs scheduling.

The ladder is total: every assessment lands on exactly one rung.

State the primary reason, weighing stated constraints (deadlines, freeze windows, team rotation) - name them in it. A stated deadline, quarter, freeze, or a named gate on one deployable (a squad holding its module until a milestone) counts as "asked" for calendar time: map the PR sequence to it on the Summary's `Window fit` line - a gate on one deployable of a shared build holds that deployable's deploy, not the merge; a third party's own notice period is a constraint on one code path, not a window. An infrastructure prerequisite that is no dependency of the manifest (a datastore the target requires) is a Next Step and a deploy-order step of the Rollback Plan (its own row when sequenced), not a Per-Dependency row. For multi-dependency requests, give a per-dependency verdict plus a batch verdict. Sequencing is a shape, not a verdict: when the deps are individually fine but unsafe batched, the Summary Recommendation stays a single enum value (`Go - Planned`, or `Go - Epic` at XL - rung 5 defers to this), the Primary Reason says the batch was rejected in favour of sequenced PRs, and the Sequence column carries the order. `No-Go - Block` is reserved for deps that cannot ship at all. The Risk Assessment table covers the batch; the Rollback Plan follows the shipped shape - one plan for a batched upgrade, or one row per PR carrying every field the bullet form carries when sequenced.

## Review Mode

When reviewing an upgrade assessment authored by someone else:

Use skill: `architecture-review-lens` for severity taxonomy, intake, completeness audit, internal-consistency check, assumptions audit, per-factor findings, criteria scoring, questions for the author, and verdict.

Reviews run the full lens (standalone formatting defaults; the lens's skip rule covers steps that do not fit). Step 1's `stack-detect` still runs: in Review Mode it grounds ecosystem-specific breaking-change expectations and names the compatibility concerns a complete assessment should have covered, and it lands in the lens's Review Context as a `Stack:` line this workflow adds after the lens's depth line, never as its own block. Where the assessment covers one module of a polyglot repo, detect that module's stack and say so on the same line. A Present-but-wrong factor reads Present in the Completeness table with the later step's F-number in its `F{n}` column and `-` in the other two; a finding bearing on two factors is recorded under the first and its F-number referenced in the second's `F{n}` column. Review Mode does not re-run the Step 2-7 delegations; their tables are the bar the artifact must meet - cite them as review evidence, and load one only when a finding's severity turns on it. The Assessment Model's tables (change taxonomy, size guidance, Go/No-Go criteria, Step 3's batching rule) apply the same way. The reviewer may state a corrected value inside a finding's recommendation ("expect L-XL, not S") but does not author a replacement assessment.

Supply this upgrade-assessment-specific factor list to the completeness audit. The `Required` column names the factors the verdict turns on; a factor the artifact's scope does not reach reads `N/A` with its reason, Required or not, and is not a gap. Every other factor is Present, Under-specified (partial coverage), or Missing, and the lens's own floors set severity - Under-specified Minor at least, Missing Major at least, Blocker when the decision cannot be made without it.

| Factor                       | Required | What "Present" Looks Like                                                         |
| ---------------------------- | -------- | --------------------------------------------------------------------------------- |
| Version path                 | Yes      | Current and target versions stated; intermediate versions assessed                |
| Breaking changes             | Yes      | Categorized by type (removal / rename / behavior / config / transitive / runtime) with migration action |
| Risk assessment              | Yes      | All four factors levelled (breaking changes, test coverage, rollback complexity, blast radius) and a summary level derived |
| Compatibility conflicts      | Yes      | Transitive, build tool, runtime conflicts surfaced, each marked Resolvable / Needs own upgrade{ [VERIFY]} / Blocker |
| Multi-dependency interaction | Yes*     | When upgrading multiple deps, interaction effects and required ordering assessed  |
| Security status              | Yes      | Current version EOL/CVE status stated, even when upgrade is not security-driven   |
| Effort estimate              | Yes      | S/M/L/XL per component (breaking changes, compatibility, test and validation)     |
| Rollback plan                | Yes      | Trigger, procedure, data compatibility, time window, exposure control, deploy order - not just "revert version" |
| Recommendation               | Yes      | Go - Now / Go - Planned / Go - Epic / No-Go - Defer / No-Go - Block, with primary reason, fitting any stated window |

*Required whenever the request is multi-dependency by Step 3's definition - including a single named dependency whose target release moves pinned transitives.

Specific quality checks beyond the standard lens:

- **Upgrade assumed safe without changelog review** (any version distance): Blocker for ecosystems known to break in minor versions (Spring Boot, Django, Rails); Major otherwise; Minor on a patch bump
- **Effort estimate without breaking change inventory**: Major; the estimate is unbacked
- **"Just revert" rollback plan**: Major when the upgrade changes schema or message format - or when the assessment never established that it does not
- **No security status for an EOL or vulnerable current version**: Major minimum
- **Recommendation not actionable for a spike ticket**: Minor; promote to Major when blast radius is Wide (per the artifact, or the reviewer's assessment when the artifact omits it - flag it as reviewer context)

Record each quality-check hit once, in the lens step that owns it (Missing or Under-specified factor -> Completeness; internal contradiction -> Internal Consistency; Present-but-wrong content -> Per-Factor Findings). A check's preset severity is a floor, not a ceiling. Reviewer-known but unverifiable facts follow the same [VERIFY] convention as Step 2.

Output header: `# Upgrade Assessment Review` and use the output structure defined in `architecture-review-lens`. Skip the assessment Output template below - the lens's required-changes checklist is the review's action list, so no separate Recommended Next Steps section is emitted. The lens emits that checklist only on a non-Approve verdict; an Approve review closes with one line stating that nothing must change before adoption. An author document that uses none of this skill's vocabulary is still audited against the factor list on substance; say so in Intake rather than marking every factor Missing on wording. In this mode the Review Self-Check replaces the authoring Self-Check (self-checks are applied internally, never emitted in the deliverable):

- [ ] Step 1: behavioral-principles loaded, then stack detected and carried on the review's context line, scoped to the module under review in a polyglot repo
- [ ] All factors audited with Required marking applied; verdict driven by highest severity
- [ ] Quality-check hits recorded once in the correct lens step and numbered
- [ ] Every finding cites the assessment's section; non-Approve verdict lists required changes

## Output

```markdown
# Dependency Upgrade Assessment: {Dependency} {Current} -> {Target}   <!-- multi-dep: name the batch, e.g. "Node 22->24 + Express 4->5" -->

## Summary

- **Stack:** {detected language / framework}{, module <name> | , component <name>}
- **Recommendation:** {Go - Now | Go - Planned | Go - Epic | No-Go - Defer | No-Go - Block}  <!-- multi-dep: the batch verdict -->
- **Overall Effort:** {S | M | L | XL}
- **Risk Level:** {Low | Medium | High}
- **Primary Reason:** {one sentence}
- **Window fit:** {the PR sequence mapped to the stated deadline, freeze, or per-deployable gate}  <!-- only when one was stated -->

## Per-Dependency Verdicts  <!-- multi-dependency requests, and any single-dependency request whose Needs-own-upgrade row ships first: one row per dependency (one upgraded across several modules in one PR is still one row); a dependency riding another's PR reads "with X"; a Needs-own-upgrade row's Effort is its own Step 5 total -->

| Dependency | Recommendation | Effort | Sequence (PR order) |
| ---------- | -------------- | ------ | ------------------- |
| {name}     | {verdict}      | {size} | {1st/2nd/with X}    |

## Breaking Changes

| Change                            | Hop (version)   | Type                             | Migration Action | Effort     |
| --------------------------------- | --------------- | -------------------------------- | ---------------- | ---------- |
| {API or behavior removed/changed}{ [VERIFY]} | {e.g., 3.4}     | {removal \| rename \| behavior \| config \| transitive \| runtime} | {what to do}     | {S/M/L/XL} |

## Compatibility Issues

| Conflict              | Severity                                  | Resolution       |
| --------------------- | ----------------------------------------- | ---------------- |
| {dependency conflict} | {Blocker / Needs own upgrade / Needs own upgrade [VERIFY] / Resolvable} | {how to resolve} |

## Security Assessment  <!-- multi-dep: one block per dependency -->

- Current version status: {Supported | Maintenance | End-of-life | Unknown [VERIFY]}, target version status: {Supported | Maintenance | End-of-life | Unknown [VERIFY]}
- Open CVEs on the current version: {list with source, "none identified", or "none identified [VERIFY]"}
- CVEs addressed by target version: {list with source, "none identified", or "none identified [VERIFY]"}
- Risk of staying: {one sentence}

## Migration Effort Breakdown

<!-- multi-dep: one `### {Dependency}` subheading carrying this table per dependency, then a final `### Batch total` line: one size aggregated from the per-dependency totals by the Step 5 rule -->

| Component                | Effort         | Notes                                          |
| ------------------------ | -------------- | ---------------------------------------------- |
| Breaking change fixes    | {None/S/M/L/XL} | {count of changes}                             |
| Compatibility resolution | {None/S/M/L/XL} | {what needs resolving; None when the table is empty} |
| Test and validation      | {S/M/L/XL}     | {scope of test + integration/smoke test plan}  |
| **Total**                | **{S/M/L/XL}** | {largest component, bumped by the Step 5 rule; never None since Test and validation is always sized} |

## Risk Assessment

| Risk Factor         | Level               | Notes                             |
| ------------------- | ------------------- | --------------------------------- |
| Breaking changes    | {None/Low/High}     | {count, and the type or runtime major that set the level} |
| Test coverage       | {Good/Partial/Poor} | {confidence level}                |
| Rollback complexity | {Easy/Hard}         | {data or config impact}           |
| Blast radius        | {Narrow/Wide}       | {scope of affected functionality} |

## Rollback Plan

<!-- sequenced multi-dep: replace the bullets with one table: | PR | Trigger | Procedure | Data compatibility | Exposure control | Deploy order | Point of no return | Window | -->

- **Trigger**: {observable threshold with the sample the window will hold, or an absolute count where the slice cannot reach it}
- **Procedure**: {steps to revert}
- **Data compatibility**: {whether rollback is clean or requires data handling}
- **Window**: {how long rollback is feasible post-deploy}
- **Exposure control**: {feature flag | canary | blue-green | rolling update | one-shot script | big bang (as proposed) - {why nothing finer exists}}
- **Deploy order**: {component order from dependency-impact-analysis | single deployable}
- **Point of no return**: {the step after which the plan rolls forward, or none}

## Recommended Next Steps

1. {verification items when offline, else the first action based on recommendation - e.g., "Create spike ticket to validate migration path"}
2. {Second action}
3. {Third action}

## Assumptions

- {Assumption made due to missing codebase context}
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded, then stack detected or the request-stated stack used
- [ ] Step 2: breaking changes categorized by type and migration action, per hop, before any effort estimate; unverified claims tagged [VERIFY]
- [ ] Step 3: compatibility conflicts surfaced (transitive, build tool, runtime), each marked Resolvable / Needs own upgrade{ [VERIFY]} / Blocker; multi-dependency requests checked pairwise
- [ ] Step 4: security status of both current and target versions stated, with the risk of staying
- [ ] Step 5: per-component efforts aggregated by the stated rule; one table per dependency plus a batch total on multi-dependency requests
- [ ] Step 6: all four risk factors levelled and the Summary Risk Level derived from them
- [ ] Step 7: rollback plan addresses data compatibility and exposure control, not just "revert the version"
- [ ] Step 8: Go/No-Go recommendation is a single enum value, actionable for a spike ticket; per-dependency verdicts and PR sequence given when multi-dependency; Recommended Next Steps and Assumptions filled

## Avoid

- Producing a changelog summary instead of a focused impact analysis
