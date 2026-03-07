---
name: task-debt-triage
description: Prioritize technical debt items by risk-adjusted ROI - blast radius, change frequency, and team pain. Produces a ranked backlog ready for sprint planning. Not for general code review (use task-code-review) and not for refactoring planning (use task-code-refactor).
metadata:
  category: planning
  tags: [tech-debt, prioritization, planning, risk, maintainability]
  type: workflow
user-invocable: true
---

# Technical Debt Triage

## Purpose

Risk-adjusted technical debt prioritization for tech leads and senior engineers:

- **Blast radius weighting** -- debt in high-traffic or high-coupling code costs more than equivalent debt in isolated modules
- **Change frequency signal** -- debt that slows every change is more urgent than debt in rarely-touched code
- **Team pain calibration** -- explicit cost signal from the people who feel the debt daily
- **Actionable ranking** -- output is a prioritized backlog with effort estimates, not a general quality report

This skill produces a ranked debt backlog. It does not fix debt or write refactoring plans (use `task-code-refactor` for that).

## When to Use

- Before a planning session to decide which debt to address this quarter
- When debt has accumulated and the team needs to triage what matters most
- When making the case to stakeholders for debt reduction investment
- When onboarding to a codebase and identifying the highest-leverage improvement areas
- After an incident reveals systemic weakness worth tracking as debt

## Inputs

| Input          | Required | Description                                                               |
| -------------- | -------- | ------------------------------------------------------------------------- |
| Debt items     | Yes      | List of debt items - free text, ticket IDs, or file/module names          |
| Team pain data | No       | Explicit developer pain ratings or recent complaints about specific areas |
| Change log     | No       | Recent git log or list of frequently-changed files                        |
| Constraints    | No       | Timeline, team capacity, upcoming feature work that constrains debt work  |

Handle partial inputs gracefully. When team pain data or change log is missing, state assumptions and apply heuristics based on the debt item descriptions.

## Rules

- Score every debt item on all three axes (blast radius, change frequency, team pain)
- Produce a ranked list - do not deliver unordered findings
- Every top-5 item must have a recommended action (fix now / spike / defer / accept)
- Never treat all debt as must-fix - explicit deferral or acceptance is a valid outcome
- Distinguish debt that blocks feature work from debt that is only cosmetic
- Size estimates are relative (S/M/L/XL) - never calendar time unless asked
- Omit empty sections in output

## Triage Model

### Step 1 - Stack and Context

Use skill: `stack-detect` to identify the project stack.

This shapes:

- Which complexity thresholds apply for the detected ecosystem
- Which tooling signals are relevant (coverage reports, linter output, build times)

### Step 2 - Blast Radius Assessment

For each debt item, assess its blast radius:

Use skill: `blast-radius-analysis` to determine how many callers, consumers, or downstream components are affected if this debt causes a failure or requires a change.

| Blast Radius | Definition                                           |
| ------------ | ---------------------------------------------------- |
| Narrow       | Isolated module, single consumer, no shared state    |
| Moderate     | 2-5 consumers, shared data access, or cross-service  |
| Wide         | Core shared library, auth/payment path, high-traffic |

### Step 3 - Change Frequency Signal

For each debt item, assess how often the affected code changes:

If a git log is provided, count commits to the file or module in the last 90 days.

If no log is provided, use these heuristics based on debt item descriptions:

- Debt in API handlers, request processing, or business logic: assume high
- Debt in configuration, infrastructure code, or migration scripts: assume low
- Debt in shared utilities or base classes: assume medium

| Change Frequency  | Signal                                             |
| ----------------- | -------------------------------------------------- |
| High (>10/90d)    | Changed multiple times per sprint - debt compounds |
| Medium (3-10/90d) | Changed a few times per quarter                    |
| Low (<3/90d)      | Rarely touched - debt is latent, not blocking      |

### Step 4 - Team Pain Signal

Assess the human cost of each debt item:

If team pain data is provided (explicit ratings or complaints), use it directly.

If not provided, estimate pain from debt item descriptions:

- "Slow builds", "hard to test", "causes flaky tests": High pain
- "Confusing naming", "missing comments", "inconsistent patterns": Medium pain
- "Old library version", "deprecated API", "unused code": Low pain (unless security risk)

| Pain Level | Signal                                                    |
| ---------- | --------------------------------------------------------- |
| High       | Slows every sprint, causes incidents, or blocks new hires |
| Medium     | Occasional friction but workable                          |
| Low        | Annoying but rarely blocking                              |

### Step 5 - Scoring and Ranking

Score each debt item using a simple weighted formula:

**Risk-Adjusted Priority Score** = (Blast Radius x 3) + (Change Frequency x 2) + (Team Pain x 1)

Scoring scale for each axis: Narrow/Low = 1, Medium = 2, Wide/High = 3

Rank by descending score. For ties, break by blast radius (higher blast radius wins).

### Step 6 - Recommended Action

For each ranked item, assign a recommended action:

| Action  | When to Use                                                                 |
| ------- | --------------------------------------------------------------------------- |
| Fix now | Score >= 7, or any Wide blast radius item with High change frequency        |
| Spike   | Impact unclear - needs investigation before committing to a fix             |
| Defer   | Score 4-6, or low change frequency - schedule for a future quarter          |
| Accept  | Score <= 3, or cosmetic debt with no functional risk - document and move on |

### Step 7 - Effort Sizing

For top-5 items marked "Fix now" or "Spike", provide a relative effort estimate:

- **S** (< half day): Rename, extract method, update dependency
- **M** (1-2 days): Refactor a single module, add test coverage to a class
- **L** (3-5 days): Redesign a component, migrate a data pattern, split a large class
- **XL** (> 5 days): Architectural change, cross-service refactor - must be scoped as its own epic

Use skill: `complexity-review` to calibrate effort estimates for high-complexity debt items.

## Output

```markdown
# Technical Debt Triage

## Context

**Stack:** {detected language / framework}
**Items Evaluated:** {count}
**Date:** {today}

## Ranked Debt Backlog

| Rank | Debt Item | Blast Radius | Change Freq | Team Pain | Score | Action  | Effort |
| ---- | --------- | ------------ | ----------- | --------- | ----- | ------- | ------ |
| 1    | Name      | Wide         | High        | High      | 14    | Fix now | M      |
| 2    | Name      | Moderate     | High        | Medium    | 11    | Fix now | L      |
| ...  | ...       | ...          | ...         | ...       | ...   | ...     | ...    |

## Top Priority Details

### 1. {Debt Item Name}

- **Location**: {file, module, or component}
- **Debt type**: {complexity | test coverage | coupling | outdated dependency | security | performance | documentation}
- **Blast radius**: {Narrow | Moderate | Wide} - {brief reason}
- **Change frequency**: {High | Medium | Low} - {brief reason or data point}
- **Team pain**: {High | Medium | Low} - {brief reason}
- **Recommended action**: {Fix now | Spike | Defer | Accept}
- **Effort**: {S | M | L | XL}
- **Why now**: {one sentence on why this ranks above the next item}

[Repeat for top 5]

## Deferred Items

| Debt Item | Score | Reason for Deferral                                  |
| --------- | ----- | ---------------------------------------------------- |
| Name      | 4     | Low change frequency - not blocking any current work |

## Accepted Items (Will Not Fix)

| Debt Item | Reason                                         |
| --------- | ---------------------------------------------- |
| Name      | Cosmetic only, stable code, no functional risk |

## Assumptions

- {Assumption made due to missing input - e.g., "No git log provided; change frequency estimated from debt descriptions"}

## Next Steps

1. Add top-priority items to the sprint backlog with their effort estimates
2. Create spike tickets for "Spike" items before committing to fix effort
3. Document "Accept" decisions so future engineers know the debt is intentional
4. Re-run this triage after each significant incident or quarter boundary
```

### Output Constraints

- Ranked table must include all evaluated items
- Top-5 "Fix now" and "Spike" items must have full detail sections
- Every "Accept" decision must state the reason
- Assumptions from missing inputs must be listed
- No refactoring code or implementation plans in this output

## Success Criteria

A well-executed debt triage passes all of these.

### Completeness

- [ ] Every item scored on all three axes (blast radius, change frequency, team pain)
- [ ] All items ranked - no unordered findings
- [ ] Every top-5 item has a recommended action and effort estimate
- [ ] Deferred and accepted items are explicit - not silently dropped
- [ ] Assumptions from missing inputs are listed

### Signal Quality

- [ ] Blast radius reflects actual coupling and consumer count, not just code quality
- [ ] Change frequency reflects git activity or reasonable heuristics, not guessing
- [ ] Top-ranked items are clearly higher-leverage than lower-ranked items
- [ ] "Accept" decisions are defensible - cosmetic or stable code, not avoidance

### Tech Lead Utility

- [ ] Output can be copied directly into a sprint planning doc or ticket tracker
- [ ] Stakeholders can see why item A ranks above item B without asking
- [ ] Effort estimates are relative (S/M/L/XL) - no false precision in hours

## Avoid

- Treating all debt equally regardless of blast radius or change frequency
- Recommending fixes for everything - acceptance and deferral are valid outcomes
- Estimating in hours or days without being asked
- Generating refactoring code or implementation plans (use `task-code-refactor` for that)
- Ranking by code quality aesthetics alone when functional risk is absent
- Silently dropping items - every input must appear in ranked, deferred, or accepted buckets

## Key Skills Reference

- Use skill: `stack-detect` for ecosystem context
- Use skill: `blast-radius-analysis` for coupling and consumer impact assessment
- Use skill: `complexity-review` for effort calibration on high-complexity items

## After This Skill

If the output needed significant adjustment - items were ranked incorrectly, blast radius was miscalibrated, or key debt was missed - run `/task-skill-feedback` to log what changed and why.
