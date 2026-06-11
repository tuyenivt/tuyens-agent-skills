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

Produce a ranked debt backlog with explicit fix/spike/defer/accept calls. Audience: tech leads sizing the next quarter's debt budget. Not for writing the refactor itself.

## When to Use

- Quarterly planning, post-incident reviews, codebase onboarding, making the case for debt investment
- When debt has accumulated and needs triage rather than blanket "fix everything"

## Inputs

Required: a list of debt items (free text, ticket IDs, or file/module names).
Optional: team pain ratings, recent git log of changed files, capacity constraints.

## Workflow

### STEP 1 - Setup

Use skill: `behavioral-principles`.
Use skill: `stack-detect`. Stack output shapes the inference column (frontend vs backend vs infra) and the effort tiers.

### STEP 2 - Score Each Item on Three Axes

For every item, assign a level on each axis. The "If no data, infer from" column applies only when the input is silent on that axis.

| Axis | Narrow / Low | Moderate / Medium | Wide / High | If no data, infer from |
| --- | --- | --- | --- | --- |
| **Blast Radius** | Isolated module, single consumer | 2-5 consumers or shared data | Core lib, auth/payment/billing path, high-traffic | Module name and described scope; auth/payment/billing default to Wide; checkout → Wide; CI/build pipeline and cross-cutting config (flags, shared settings) → Moderate, Wide if it blocks every team |
| **Change Frequency** | <3 commits/90d - rarely touched | 3-10 - few times a quarter | >10 - debt compounds every sprint | Actively developed business logic → High; shared utilities, CI/build → Medium; admin UI / frozen or deprecated code / dead UI → Low |
| **Team Pain** | Annoying but rarely blocking | Occasional friction, workable | Slows every sprint, causes incidents, blocks onboarding | "Slow builds", "flaky", "incidents", "blocks merges", "takes hours" → High; "confusing", "inconsistent" → Medium; "old", "deprecated", "unused" → Low (the security inference below may still force Fix now; it does not raise Pain) |

Use `Use skill: review-blast-radius` only when coupling is non-obvious. If it returns `Critical`, map to **Wide** and tag the item `critical-data-risk` in Assumptions.

**Security inference.** Mark `time-sensitive` (forces Fix now) and treat as Wide blast radius when any apply, including via reasonable inference from item text:
- Named CVE or "vulnerability"
- Deprecated runtime/library/framework version with publicly documented CVEs (e.g., Log4j 1.x, jQuery <3.5, EOL Node majors, EOL Postgres) - even if input doesn't name the CVE
- Vendor or LTS EOL within 6 months of today's date (inclusive)
- Public API deprecation cutoff with a published date
- Compliance or contractual deadline

When inferring a CVE without explicit mention, note the assumption: `Assumed time-sensitive: <library> has documented CVEs at this version; ask if you want it reclassified.`

### STEP 3 - Rank

Sort by `(Blast Radius, Change Frequency, Team Pain)` lexicographically (Wide > Moderate > Narrow, then High > Medium > Low). Tiebreaks apply between items with identical axis tuples, in order:

1. Time-sensitive items rank above non-time-sensitive peers
2. Cheaper effort (S < M < L < XL); skip for items without an effort tier
3. Input order - note the unresolved tie in Assumptions

If an item bundles two workstreams (e.g., "fix flakes" + "speed up build", or "deprecate API" + "remove API"), split into separately-ranked entries and note the split in Assumptions.

### STEP 4 - Recommend Action

| Action | When |
| --- | --- |
| **Fix now** | Time-sensitive, OR Wide blast radius with Change Frequency or Pain at Medium+, OR High Change Frequency with Medium+ Pain |
| **Spike** | Impact or sizing unclear; investigation must precede commitment |
| **Defer** | Workable now but will degrade; revisit next quarter. Includes Wide-blast-radius items currently low on both other axes (e.g., framework upgrades with no deadline) |
| **Accept** | Stable code, no functional or security risk - document and move on |

Defer means "will revisit"; Accept means "will not fix unless conditions change". Pick Accept only when there is no plausible future trigger.

### STEP 5 - Effort

For every **Fix now** and **Spike** item, assign an effort tier. For Spikes, the tier sizes the investigation, not the eventual fix.

- **S** (<half day): rename, extract, dep bump
- **M** (1-2 days): refactor a module, add coverage to a class, add structured logging to a service
- **L** (3-5 days): redesign a component, migrate a pattern, runtime upgrade
- **XL** (>5 days): architectural change

XL Fix-now items stay in the **Top Priorities** list (do not silently drop) and additionally appear in **Split as Separate Epic** with a scoping note. Their presence in both sections is intentional: the ranking shows urgency, the split section shows the planning unit.

**Capacity.** When the input states available capacity, walk the ranked Fix-now and Spike items top-down, accumulate effort, and state in Assumptions where the capacity line falls (which items fit). Calendar arithmetic is allowed here because the caller supplied it.

## Output Format

```markdown
# Technical Debt Triage

**Stack:** <detected> | **Items:** <count> | **Date:** <YYYY-MM-DD>

## Ranked Backlog

| Rank | Debt Item | Blast Radius | Change Freq | Team Pain | Action | Effort |
| ---- | --------- | ------------ | ----------- | --------- | ------ | ------ |
| 1    | …         | Wide         | High        | High      | Fix now | M      |
| 2    | …         | Wide         | High        | High      | Fix now | XL → split |
| 3    | …         | Moderate     | Medium      | High      | Fix now | M      |
| 4    | …         | Narrow       | Low         | Low       | Accept  | -      |

## Top Priorities

### 1. <Item>

- **Location:** <file/module>
- **Type:** complexity | coverage | coupling | dependency | security | performance | observability | docs
- **Axes:** Wide / High / High - <one-line rationale per axis>
- **Action:** Fix now (effort: M)
- **Why now:** <one sentence on why this beats the next item>

[repeat for the top 5 (or fewer) ranked Fix-now and Spike items]

## Deferred

| Item | Why deferred |
| ---- | ------------ |

## Accepted (will not fix)

| Item | Why |
| ---- | --- |

## Split as Separate Epic

- <XL item> - <scoping note: what carve-out makes this plannable>

## Assumptions

- <inferences made because input was incomplete, e.g., assumed CVE on deprecated library>
- <bundled items split; critical-data-risk tags>
```

Type enum is derived from the item's nature: tests/coverage gaps and flaky tests → `coverage`; god classes/cycles/duplicated code or config → `coupling`; library/runtime → `dependency`; vulnerable code/CVE → `security`; slow code → `performance`; missing logs/metrics → `observability`; high cyclomatic / unclear / dead code → `complexity`; missing docs → `docs`.

Every input appears once in the Ranked Backlog with its action (incl. XL Fix-now). Deferred, Accepted, and Split as Separate Epic restate those subsets with rationale - intentional restatement, not duplication. An item missing from the Ranked Backlog is the cardinal error. Omit sections with no items.

## Self-Check

- [ ] **Score:** every item scored on all three axes; missing data filled from the inference column with the source noted; security inferences flagged in Assumptions
- [ ] **Rank:** lex order on (BR, CF, Pain) with declared tiebreaks; time-sensitive forced to Fix now
- [ ] **Action and Effort:** every item has Fix-now / Spike / Defer / Accept; Fix-now and Spike carry effort; XL Fix-now appears in both Top Priorities and Split as Separate Epic; capacity line stated when capacity was given
- [ ] **Coverage:** no item silently dropped

## Avoid

- Estimating in calendar days unless asked
- Recommending fixes for everything - Accept and Defer are valid
- Generating refactoring code
- Ranking on code aesthetics when functional risk is absent
- Numeric scoring - the three axes already encode priority
