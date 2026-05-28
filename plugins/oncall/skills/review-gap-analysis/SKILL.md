---
name: review-gap-analysis
description: Analyze why review and quality gates failed to catch a production failure: process gaps with priority, causal links, and structural fixes - not blame.
metadata:
  category: governance
  tags: [review, gap-analysis, incident, quality-gate]
user-invocable: false
---

# Review Gap Analysis

## When to Use

- During postmortem to understand why safeguards failed
- After a production failure that should have been caught at review or pre-deploy
- Identifying systemic review blind spots across multiple incidents

## Inputs

Required: incident summary, root cause. Optional: PR diff, review history, CI/CD details, test coverage, deploy pipeline.

## Rules

- Distinguish "missed in review" from "not catchable by review" - the second needs a different quality gate
- Categories overlap on common shapes (fast review of large PR hits Review-attention + Cognitive-load + Checklist); pick the dominant category and fold the others into its causal link, do not produce duplicate rows
- Cap output at 3-5 distinct gaps; single highest-leverage fix is the load-bearing output

## Patterns

### Gap Categories

| Category               | Question                                                                                             |
| ---------------------- | ---------------------------------------------------------------------------------------------------- |
| Review-attention       | Was the risky path reviewed at all, or with enough context to assess risk? (rubber-stamp / under-informed; absorbs Cognitive-load when PR size/speed drove the inattention) |
| Checklist              | Was there a prompt that would have surfaced this risk?                                                |
| Expertise              | Did the reviewer have domain knowledge for this failure type?                                         |
| Automated-gate         | Would automation (lint, static analysis, EXPLAIN, integration test, monitoring, canary) have caught it? |
| Resilience-pattern     | Were timeouts, retries, circuit breakers, bulkheads checked for all external calls and shared resources (timeouts, retries, breakers, bulkheads, deadlines, contexts depending on stack)? |

### Step 1 - Trace Failure to Introduction Point

Identify the introducing change (PR, commit, config, deploy). If no PR exists (config drift, traffic growth, latent bug), classify as a process coverage gap and skip to Step 3 (non-reviewable identification).

Map the causal chain: from the change to the production failure. Example: *"PR added retry → retry holds connections longer → pool exhausted under load → cascading timeouts."* This shows what a reviewer would have needed to reason about.

### Step 2 - Evaluate Each Category

Walk every category, then collapse overlaps so each distinct finding appears once. For each gap:

1. **Type** - which category
2. **Causal link** - how this gap connects to the production failure (closing it would have prevented or reduced the incident)
3. **Why it existed** - structural reason, not individual blame
4. **Fix** - specific process or tooling change
5. **Enforcement** - automated check, checklist item, or policy

### Step 3 - Identify Non-Reviewable Aspects

Some failures cannot be caught by code review regardless of skill: latent bugs surfaced by later traffic/data growth, config drift, emergent behavior between independently correct components, load-dependent failures (only manifest at production scale), or feedback that was overruled.

For these, the question shifts from "why didn't review catch it?" to "what quality gate should exist?" (load test, config validation, chaos test, canary). Name the missing gate.

### Step 4 - Prioritize by Leverage

| Priority | Criteria                                                               |
| -------- | ---------------------------------------------------------------------- |
| P0       | Closing this gap alone would have prevented the incident               |
| P1       | Closing this gap significantly reduces blast radius                    |
| P2       | Closing this gap catches this failure class earlier                    |
| P3       | Improves general review quality, not specific to this class            |

If multiple gaps qualify as P0, the one named in **Highest-Leverage Fix** is the single closure that closes the most other P0/P1 gaps as a side effect. Focus recommendations on P0 and P1.

### Bad vs Good

Bad: blame-shaped ("Reviewer should have been more careful") or untestable ("Add more tests"). Bad: misclassifying a load-dependent failure as Review-attention when it is actually Non-Reviewable.

Good: structural and enforceable - names the failure class, points to a specific check, and ties the fix to a target file or CI step. Example:
- Gap: Resilience-pattern (P0). Causal link: retry change without timeout budget → pool drain. Fix: CI lint flagging retry config changes without pool config review; mandatory load test for resilience-config PRs.

## Output

```
## Review Gap Analysis

### Causal Chain
{Code change or condition} → {intermediate effect} → {production failure}

### Gaps Identified

3-5 distinct rows; overlapping signals collapsed into one row.

| # | Type | Priority | Causal Link | Why It Existed | Fix | Enforcement |
| - | ---- | -------- | ----------- | -------------- | --- | ----------- |

### Highest-Leverage Fix
{Single gap closure with greatest prevention impact, and why. When composed by task-postmortem, this row plus the top 1-2 P0/P1 rows are what gets surfaced upward.}

### Non-Reviewable Factors
For load-dependent, config-drift, emergent, or overruled-feedback failures, this section is the load-bearing output - name the missing quality gate (load test, config validation, canary, chaos test). Omit only if every gap was catchable from a diff.
```

## Avoid

- Blame ("be more careful", "the reviewer should have caught it") - not a structural fix
- Treating review as the only quality gate when CI, integration tests, monitoring, canary, or load tests would catch the class
- Listing gaps without causal connection to the specific incident
- Ignoring non-reviewable failure modes (config drift, load-dependent, emergent, overruled feedback)
