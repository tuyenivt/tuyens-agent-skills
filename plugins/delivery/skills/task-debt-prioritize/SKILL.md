---
name: task-debt-prioritize
description: Prioritize technical debt by risk-adjusted ROI (blast radius, change frequency, pain); ranked backlog with effort and fix/spike/defer/accept calls.
metadata:
  category: planning
  tags: [tech-debt, prioritization, planning, risk, maintainability]
  type: workflow
user-invocable: true
---

# Technical Debt Triage

Produce a ranked debt backlog with explicit fix/spike/defer/accept calls. Audience: tech leads sizing the next quarter's debt budget. Not for writing the refactor itself (use `task-code-refactor`).

## When to Use

- Quarterly planning, post-incident reviews, codebase onboarding, or making the case for debt investment
- When debt has accumulated and needs triage rather than blanket "fix everything"
- Inputs: a list of debt items (free text, ticket IDs, or file/module names). Optional: team pain ratings, recent git log of changed files, capacity constraints

## Workflow

### STEP 1 - Setup

Use skill: `behavioral-principles`.
Use skill: `stack-detect` (shapes which tooling signals are relevant).

### STEP 2 - Score Each Item on Three Axes

For every item, assign a level on each axis. The "If no data, infer from" column applies only when the input is silent on that axis.

| Axis | Narrow / Low | Moderate / Medium | Wide / High | If no data, infer from |
| --- | --- | --- | --- | --- |
| **Blast Radius** | Isolated module, single consumer | 2-5 consumers or shared data | Core lib, auth/payment path, high-traffic | Module name and described scope; auth/payment/billing default to Wide |
| **Change Frequency** | <3 commits/90d - rarely touched | 3-10 - few times a quarter | >10 - debt compounds every sprint | API handlers / business logic → High; shared utilities → Medium; config / migrations / dead UI → Low |
| **Team Pain** | Annoying but rarely blocking | Occasional friction, workable | Slows every sprint, causes incidents, blocks onboarding | "Slow builds", "flaky tests", "incidents" → High; "confusing", "inconsistent" → Medium; "old", "deprecated", "unused" → Low (unless security) |

Use `Use skill: review-blast-radius` only when coupling is non-obvious from the description. If it returns `Critical`, map to **Wide** here and tag the item `critical-data-risk` in Assumptions.

**Time-sensitive boost.** Mark an item `time-sensitive` and force action to **Fix now** when any apply:
- Unpatched CVE on a runtime/library/transitive dep
- Vendor or LTS EOL within 6 months
- Public API deprecation cutoff with a published date
- Compliance or contractual deadline

### STEP 3 - Rank

Sort by `(Blast Radius, Change Frequency, Team Pain)` lexicographically (Wide > Moderate > Narrow, then High > Medium > Low). Tiebreaks in order:

1. Time-sensitive items rank above non-time-sensitive peers
2. Cheaper effort (S before L/XL)

If an item bundles two workstreams (e.g., "fix flakes" + "speed up build", or "deprecate API" + "remove API"), split into separately-ranked entries and note the split in Assumptions.

### STEP 4 - Recommend Action

| Action | When |
| --- | --- |
| **Fix now** | Time-sensitive, OR Wide blast radius with either Change Frequency or Pain at Medium-or-higher, OR High Change Frequency with Medium-or-higher Pain |
| **Spike** | Impact unclear; needs investigation before committing to a fix size |
| **Defer** | Workable now but will degrade; revisit next quarter. Includes Wide-blast-radius items currently low on both other axes (e.g., framework upgrades with no deadline) |
| **Accept** | Stable code, no functional or security risk - document and move on |

Defer means "will revisit"; Accept means "will not fix unless conditions change". Pick Accept when there's no plausible future trigger.

### STEP 5 - Effort for Top Picks

For every **Fix now** and **Spike** item, give an effort:

- **S** (<half day): rename, extract, dep bump
- **M** (1-2 days): refactor a module, add coverage to a class
- **L** (3-5 days): redesign a component, migrate a pattern
- **XL** (>5 days): architectural change - emit as a `split epic` flag, not an entry in this backlog

## Output Format

```markdown
# Technical Debt Triage

**Stack:** {detected} | **Items:** {count} | **Date:** {today}

## Ranked Backlog

| Rank | Debt Item | Blast Radius | Change Freq | Team Pain | Action | Effort |
| ---- | --------- | ------------ | ----------- | --------- | ------ | ------ |
| 1    | …         | Wide         | High        | High      | Fix now | M      |

## Top Priorities

### 1. {Item}

- **Location:** {file/module}
- **Type:** complexity | coverage | coupling | dependency | security | performance | docs
- **Axes:** Wide / High / High - {one-line rationale per axis}
- **Action:** Fix now (effort: M)
- **Why now:** {one sentence on why this beats #2}

[repeat for top 5; or fewer if the backlog is small]

## Deferred

| Item | Why deferred |
| ---- | ------------ |

## Accepted (will not fix)

| Item | Why |
| ---- | --- |

## Split as Separate Epic

- {XL item} - {one-line scope}

## Assumptions

- {Anything inferred because input was incomplete}
- {Bundled items split; critical-data-risk tags}
```

Every input must appear in exactly one of: ranked backlog, deferred, accepted, or split-as-epic. Silent drops are the cardinal error.

## Self-Check

- [ ] **Setup:** behavioral-principles + stack-detect loaded
- [ ] **Score:** every item scored on all three axes; missing data filled from the inference column with the source noted
- [ ] **Rank:** lex order on (BR, CF, Pain); tiebreaks applied in declared order; time-sensitive items forced to Fix now
- [ ] **Action:** every item has Fix now / Spike / Defer / Accept; Defer vs Accept distinction respected
- [ ] **Effort:** every Fix-now and Spike has an effort tier; XL items routed to Split as Separate Epic, not the backlog
- [ ] No item silently dropped

## Avoid

- Estimating in calendar days unless asked
- Recommending fixes for everything - Accept and Defer are valid
- Generating refactoring code (use `task-code-refactor`)
- Ranking on code aesthetics when functional risk is absent
- Numeric scoring - the three axes already encode priority
