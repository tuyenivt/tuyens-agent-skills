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

## Inputs

Required: a list of debt items (free text, ticket IDs, or file/module names).
Optional: team pain ratings, recent git log of changed files, capacity constraints.

If pain or change-frequency data is missing, infer from the debt description and surface the assumption.

## Workflow

### STEP 1 - Behavioral and Stack Setup

Use skill: `behavioral-principles`.
Use skill: `stack-detect` (shapes which tooling signals are relevant).

### STEP 2 - Score Each Item on Three Axes

For every item, assign a level on each axis. Use `review-blast-radius` only for items where coupling is non-obvious from the description.

| Axis | Narrow / Low | Moderate / Medium | Wide / High |
| --- | --- | --- | --- |
| **Blast Radius** | Isolated module, single consumer | 2-5 consumers or shared data | Core lib, auth/payment path, high-traffic |
| **Change Frequency** (commits/90d if log given; else infer from description) | <3 - rarely touched | 3-10 - few times a quarter | >10 - debt compounds every sprint |
| **Team Pain** | Annoying but rarely blocking | Occasional friction, workable | Slows every sprint, causes incidents, blocks onboarding |

**Inference shortcuts when data is missing:**
- API handlers / business logic → high frequency; config / migrations → low; shared utilities → medium
- "Slow builds", "flaky tests", "blocks onboarding" → high pain
- "Confusing", "inconsistent" → medium pain
- "Old version", "deprecated", "unused" → low pain (unless security)

**Time-sensitive boost.** If an item has a hard external deadline (CVE with known exploit window, vendor EOL, API deprecation cutoff), mark it `time-sensitive` and force its action to **Fix now** regardless of axis scores.

### STEP 3 - Rank

Sort by `(Blast Radius, Change Frequency, Team Pain)` lexicographically (Wide > Moderate > Narrow, then High > Medium > Low). Time-sensitive items rank above same-priority peers. When one item is S and another is L/XL at the same lex position, the cheaper item ranks first - small fixes shouldn't wait behind structural rewrites.

No numeric score is needed - the three axes already encode priority and a numeric sum tends to invent precision that doesn't exist.

If an item bundles two distinct workstreams (e.g., test-suite "fix flakes" + "speed up", or "deprecate API" + "remove API"), split it into separately-ranked entries and note the split in Assumptions.

### STEP 4 - Recommend Action

| Action | When |
| --- | --- |
| **Fix now** | Time-sensitive, OR High change frequency + Medium-or-higher pain, OR Wide blast radius with any non-Low secondary signal |
| **Spike** | Impact unclear; needs investigation before committing to a fix size |
| **Defer** | Workable now; revisit next quarter - including Wide blast radius items that are currently low-pain and low-frequency (e.g., framework upgrades with no deadline) |
| **Accept** | Cosmetic, stable code, no functional risk - document and move on |

Acceptance and deferral are valid outcomes. Treating all debt as must-fix discredits the triage.

### STEP 5 - Effort for Top Picks

For every "Fix now" and "Spike" item, give an effort:

- **S** (<half day): rename, extract, dep bump
- **M** (1-2 days): refactor a module, add coverage to a class
- **L** (3-5 days): redesign a component, migrate a pattern
- **XL** (>5 days): architectural change - scope as a separate epic, do not commit inline

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

## Assumptions

- {Anything inferred because input was incomplete}
```

Every input must appear in exactly one of: ranked backlog, deferred, or accepted. Silent drops are the cardinal error.

## Self-Check

- [ ] Every item scored on all three axes
- [ ] Time-sensitive items flagged and forced to Fix now
- [ ] Ranking follows lex order on (BR, CF, Pain); ties broken by time-sensitivity
- [ ] Top picks have an action + effort; XL items recommended as separate epics
- [ ] No item silently dropped

## Avoid

- Estimating in calendar days unless asked
- Recommending fixes for everything - accept and defer are valid
- Generating refactoring code (use `task-code-refactor`)
- Ranking on code aesthetics when functional risk is absent
