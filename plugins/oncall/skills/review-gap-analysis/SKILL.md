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

Required: incident summary, root cause. Optional: PR diff, review history, CI/CD details, test coverage, deploy pipeline. Handle partial inputs - state what is missing if it weakens analysis.

## Rules

- Focus on process gaps, not individual reviewer blame
- Every gap names a structural fix - "be more careful" is not a fix
- Distinguish "missed in review" from "not catchable by review"
- Cognitive load (PR size, time spent) is a legitimate contributing factor
- Prioritize by prevention leverage; identify the single highest-leverage fix

## Pattern

### Gap Categories

| Category               | Question                                                                                             |
| ---------------------- | ---------------------------------------------------------------------------------------------------- |
| Review-attention       | Was the risky path reviewed at all, or with enough context to assess risk? (rubber-stamp / under-informed) |
| Checklist              | Was there a prompt that would have surfaced this risk?                                                |
| Expertise              | Did the reviewer have domain knowledge for this failure type?                                         |
| Cognitive load         | Was the PR too large or fast to review effectively?                                                   |
| Automated-gate         | Would automation (lint, static analysis, EXPLAIN, integration test, monitoring, canary) have caught it? |
| Resilience-pattern     | Were timeouts, retries, circuit breakers, bulkheads checked for all external calls and shared resources? |

### Step 1 - Trace Failure to Introduction Point

Identify the introducing change (PR, commit, config, deploy). If no PR exists (config drift, traffic growth, latent bug), classify as a process coverage gap and skip to Step 4 with the appropriate non-reviewable category.

Map the causal chain: from the change to the production failure. Example: *"PR added retry → retry holds connections longer → pool exhausted under load → cascading timeouts."* This shows what a reviewer would have needed to reason about.

### Step 2 - Evaluate Each Category

Apply every category in the table - do not stop at the first gap. For each gap:

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

Focus recommendations on P0 and P1.

### Good vs Bad

```
Good:
Gap: Resilience-pattern (P0 - prevents incident)
Causal link: PR added 3x retry without timeout adjustment. Retry holds connection 90s
  → pool of 40 exhausted in 4 min under load → cascading timeouts.
Why: No checklist item requires verifying timeout budget when retry logic changes.
Fix: Checklist item: "When retry/timeout changes, verify pool sizing and total budget
  under expected concurrency."
Enforcement: CI lint flagging retry config changes without pool config review;
  mandatory load test for resilience-config PRs.
```

```
Bad: "Gap: Test gap. Fix: add more tests."
```
The fix is not enforceable, names no scenario or gate, and could be written without reading the incident.

## Output

```
## Review Gap Analysis

### Causal Chain
{Code change or condition} → {intermediate effect} → {production failure}

### Gaps Identified

| # | Type | Priority | Causal Link | Why It Existed | Fix | Enforcement |
| - | ---- | -------- | ----------- | -------------- | --- | ----------- |

### Highest-Leverage Fix
{Single gap closure with greatest prevention impact, and why}

### Non-Reviewable Factors
{If any aspect was not catchable from a diff, name the missing quality gate (load test, config validation, canary, chaos test). Omit if all gaps were reviewable.}
```

If review process was demonstrably adequate and the failure was not reasonably catchable, state that under Non-Reviewable Factors. Every gap must have a structural fix.

## Avoid

- Blaming individual reviewers
- "More careful review" as a fix - not scalable, not enforceable
- Treating review as the only quality gate (consider CI, testing, monitoring, canary, load testing)
- Listing gaps without causal connection to the specific incident
- Flat gap lists without priority ranking
- Ignoring non-reviewable failure modes (config drift, load-dependent, emergent, overruled feedback)
