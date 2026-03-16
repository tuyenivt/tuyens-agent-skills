---
name: review-gap-analysis
description: Analyze why existing review processes failed to catch a production failure
metadata:
  category: governance
  tags: [review, gap-analysis, incident, quality-gate]
user-invocable: false
---

# Review Gap Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During postmortem to understand why safeguards failed
- When a production failure should have been caught during code review
- When evaluating review process effectiveness after an incident
- When identifying systemic review blind spots across multiple incidents

## Inputs

| Input                     | Required | Description                                                           |
| ------------------------- | -------- | --------------------------------------------------------------------- |
| Incident summary          | Yes      | What failed, severity, and user impact                                |
| Root cause                | Yes      | Confirmed or suspected root cause from investigation                  |
| PR diff or change history | No       | The code change that introduced the failure (if traceable to a PR)    |
| Review history            | No       | Who reviewed, what feedback was given, whether concerns were raised   |
| CI/CD pipeline details    | No       | What automated checks ran (lint, static analysis, tests, security)    |
| Test coverage context     | No       | What tests existed for the affected path, what scenarios were covered |
| Deploy pipeline details   | No       | Canary, feature flags, progressive rollout, or direct deploy          |

Handle partial inputs gracefully. When input is missing, state what additional data would strengthen the analysis and where to find it.

## Rules

- Focus on process gaps, not individual reviewer blame
- Every gap must identify what structural change would close it
- Distinguish between "missed in review" and "not reviewable with current process"
- Consider cognitive load as a legitimate contributing factor
- Prioritize gaps by how much blast radius reduction the fix would provide
- When multiple gaps exist, identify which single fix would have highest prevention leverage

## Pattern

### Gap Categories

| Category               | Question                                                                                             |
| ---------------------- | ---------------------------------------------------------------------------------------------------- |
| Coverage gap           | Was the risky code path reviewed at all?                                                             |
| Context gap            | Did the reviewer have enough context to assess the risk?                                             |
| Checklist gap          | Was there a checklist item that would have caught this?                                              |
| Tooling gap            | Would automated analysis (lint, static analysis, CI) have caught it?                                 |
| Expertise gap          | Did the reviewer have domain knowledge for this failure type?                                        |
| Cognitive load gap     | Was the PR too large or complex for effective review?                                                |
| Architecture gap       | Was architectural drift visible in the diff?                                                         |
| Test gap               | Were test scenarios sufficient to exercise the failure path?                                         |
| Monitoring gap         | Would pre-deploy monitoring checks have flagged the risk?                                            |
| Resilience pattern gap | Were resilience patterns (circuit breaker, timeout, retry, bulkhead) checked for all external calls? |

### Step 1 - Trace the Failure to Its Introduction Point

Before evaluating gaps, establish what happened and when:

1. **Identify the introducing change** - which PR, commit, config change, or deploy introduced the failure?
2. **Determine if a PR existed** - was this a code change (PR reviewable) or something else (config drift, traffic growth, latent bug triggered by external conditions)?
3. **If no PR exists** - the failure is "not reviewable with current process." Classify it as a process coverage gap (no review gate exists for this change type) and skip to Step 4.
4. **Map the causal chain** - trace from the code change to the production failure. Example: "PR added retry logic -> retry holds connections longer -> connection pool exhausted under load -> cascading timeout to all callers."

The causal chain is critical - it shows what a reviewer would have needed to reason about to catch the issue.

### Step 2 - Evaluate Each Gap Category

For each category in the table, ask the associated question against the specific incident. Apply all categories - do not stop at the first gap found.

For each gap found:

1. **Gap type** - which category from above
2. **Causal link** - how this gap connects to the production failure (not just that it exists, but how closing it would have prevented the incident)
3. **Why it existed** - structural reason (not individual blame)
4. **What would close it** - specific process or tooling change
5. **Enforcement** - how to make the fix stick (automated check, checklist item, policy)

### Step 3 - Assess Non-Reviewable Failures

Some failures cannot be caught by code review regardless of reviewer skill. Identify whether the failure falls into a non-reviewable category:

- **Latent bugs** - code was correct when written but a later change (dependency upgrade, traffic growth, data volume) triggered the failure
- **Config drift** - production config diverged from what was reviewed
- **Emergent behavior** - interaction between independently correct components
- **Load-dependent failures** - only manifests at production scale (connection pool sizing, memory pressure, lock contention)
- **Overruled feedback** - reviewer flagged the concern but feedback was dismissed or deprioritized

For non-reviewable failures, the question shifts from "why didn't review catch it?" to "what quality gate should exist for this failure type?" (load test, config validation, chaos test, canary analysis).

### Step 4 - Prioritize Gaps by Prevention Leverage

When multiple gaps are identified, rank them:

| Priority | Criteria                                                               |
| -------- | ---------------------------------------------------------------------- |
| P0       | Closing this gap alone would have prevented the incident               |
| P1       | Closing this gap significantly reduces the blast radius of the failure |
| P2       | Closing this gap would catch this failure class earlier in the process |
| P3       | Closing this gap improves general review quality but is not specific   |

Focus recommendations on P0 and P1. P2 and P3 are supplementary improvements.

### Good: Specific gap with causal chain and structural fix

```
Gap: Resilience pattern gap (P0 - would have prevented the incident)
Causal link: PR #482 added 3x retry to payment calls without adjusting timeout budget.
  Retry holds connection for 30s x 3 = 90s -> pool (max 40) exhausted in 4 minutes
  under normal load -> cascading timeout to all callers.
Why: No review checklist item requires verifying timeout budget when retry logic is
  added. Reviewer reviewed business logic correctness but not resource impact.
Fix: Add review checklist item: "When retry/timeout logic changes, verify connection
  pool sizing and total timeout budget under expected concurrency."
Enforcement: CI lint rule that flags retry config changes without corresponding pool
  config review. Mandatory load test for PRs touching resilience config.

Gap: Test gap (P1 - would have reduced blast radius)
Causal link: Integration tests used a pool of size 100 (default) vs production pool
  of size 40. Test passed because pool was never exhausted.
Why: Test environment pool config does not match production constraints.
Fix: Integration tests must use production-equivalent resource limits for connection
  pools, thread pools, and queue sizes.
Enforcement: CI check that validates test resource configs match production baselines.
```

### Bad: Blame-oriented or vague analysis

```
The reviewer should have caught the missing null check on line 142.
```

```
Gap: Tooling gap
Why: We don't have good enough tools.
Fix: Get better tools.
```

## Output Format

Consuming workflow skills depend on this structure to surface actionable review process changes.

```
## Review Gap Analysis

### Causal Chain

{Code change or condition} -> {intermediate effect} -> {production failure}

### Gaps Identified

| # | Gap Type | Priority | Causal Link | Why It Existed | What Would Close It | Enforcement |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | {category} | {P0/P1/P2/P3} | {how this gap connects to the failure} | {structural reason} | {specific fix} | {automated check / checklist / policy} |

### Highest-Leverage Fix

{Which single gap closure would have the greatest prevention impact, and why}

### Non-Reviewable Factors

{If any aspect of the failure was not catchable by code review, state what quality gate
should exist instead (load test, config validation, canary, chaos test). Omit if all
gaps were reviewable.}

### No Gaps Found

{State explicitly if review process was adequate for the failure that occurred.
Explain why the failure was not reasonably catchable given the information available
at review time. Do not omit silently.}
```

Omit "No Gaps Found" if gaps were listed. Omit "Non-Reviewable Factors" if all gaps were reviewable. Every gap must have a specific structural fix - "be more careful" and "do a better review" are not valid fixes.

## Avoid

- Blaming individual reviewers
- Assuming "more careful review" is a fix (it is not scalable)
- Ignoring cognitive load and PR size as contributing factors
- Proposing only manual process changes without automation support
- Treating review as the only quality gate (consider CI, testing, monitoring, canary, load testing)
- Listing gaps without causal connection to the specific incident
- Flat gap lists without priority ranking (not all gaps are equal)
- Ignoring non-reviewable failure modes (config drift, load-dependent, emergent behavior)
- Dismissing cases where reviewer feedback was overruled or deprioritized
