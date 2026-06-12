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

- Distinguish "missed in review" from "not catchable by review" - the second needs a different quality gate. A failure is reviewable if its trigger is visible in the diff, even when the consequence only manifests under load; Non-Reviewable is reserved for failures with no diff-visible trigger.
- Collapse gaps only when they share one causal mechanism (e.g., PR size drove both the rubber-stamp and the skipped checklist). Keep separate rows when mechanisms are distinct - one gap let the defect ship, another made it invisible to CI, another delayed detection. Two rows may share a Type when their mechanisms differ; a shared organizational cause (e.g., team offsite) may legitimately recur across rows' Why-It-Existed cells.
- Every finding is exactly one row in the Gaps table - including non-reviewable ones, which use Type `Non-Reviewable` and a Fix naming the missing quality gate. Cap at 3-5 rows; when more qualify, keep the highest-priority rows. The Highest-Leverage Fix is always the load-bearing output and may be a missing quality gate.
- When composed by `task-postmortem`, the Highest-Leverage Fix plus the top 1-2 P0/P1 rows are what gets surfaced upward.

## Patterns

### Gap Categories

| Category               | Question                                                                                             |
| ---------------------- | ---------------------------------------------------------------------------------------------------- |
| Review-attention       | Was the risky path reviewed at all, or with enough context to assess risk? (absorbs rubber-stamp, under-informed, and PR-size/cognitive-load causes) |
| Checklist              | Was there a human prompt (checklist item, PR template question) that would have surfaced this risk?   |
| Expertise              | Did the reviewer have domain knowledge for this failure type?                                         |
| Automated-gate         | Would a machine-enforced check have caught it - lint, static analysis, EXPLAIN, integration/load test, monitoring/alerting, canary? Missing alerts and missing tests belong here, not in Checklist. |
| Resilience-pattern     | Were timeouts, retries, circuit breakers, bulkheads, deadlines checked for all external calls and shared resources? |

### Step 1 - Trace Failure to Introduction Point

Identify the introducing change (PR, commit, config, deploy). Map the causal chain from the change to the production failure: *"PR added retry → retry holds connections longer → pool exhausted under load → cascading timeouts."* This shows what a reviewer would have needed to reason about.

**No-PR path** (config drift, traffic/data growth, latent bug): write the causal chain in condition form - *"{latent condition} → {accumulating effect} → {failure}"*, naming accelerants in parentheses. Skip the diff-dependent categories (Review-attention, Expertise) in Step 2; still evaluate Checklist and Automated-gate. The absence of any gate covering this failure class becomes a `Non-Reviewable` row (Step 3). Steps 3 and 4 always run.

### Step 2 - Evaluate Each Category

Walk every applicable category, then collapse same-mechanism overlaps so each distinct finding appears once. For each gap:

1. **Type** - which category
2. **Causal link** - how this gap connects to the production failure (closing it would have prevented or reduced the incident)
3. **Why it existed** - structural reason, not individual blame; name organizational causes (no CODEOWNERS, team absent) and knowledge causes (wrong-domain reviewer) separately when both apply
4. **Fix** - specific process or tooling change
5. **Enforcement** - how the fix is made unskippable (CI check, PR template, policy); for checklist gaps, Fix and Enforcement may legitimately be one line

### Step 3 - Identify Non-Reviewable Aspects

Some failures cannot be caught by code review regardless of skill: latent bugs surfaced by later traffic/data growth, config drift, emergent behavior between independently correct components, load-dependent failures with no diff-visible trigger, or feedback that was overruled.

For these, the question shifts from "why didn't review catch it?" to "what quality gate should exist?" (load test, config validation, chaos test, canary, trend alerting). Each becomes a Gaps-table row with Type `Non-Reviewable` whose Fix names the missing gate; the Non-Reviewable Factors output section is prose explaining why review could not catch the class, referencing those rows by # - it does not duplicate them.

### Step 4 - Prioritize by Leverage

| Priority | Criteria                                                               |
| -------- | ---------------------------------------------------------------------- |
| P0       | Closing this gap alone would have prevented the incident               |
| P1       | Closing this gap significantly reduces blast radius                    |
| P2       | Closing this gap catches this failure class earlier                    |
| P3       | Improves general review quality, not specific to this class            |

When multiple gaps qualify as P0, pick the Highest-Leverage Fix by: (1) prevention beats detection - prefer the closure that stops the failure class from shipping over one that catches it later; (2) on a tie, prefer the machine-enforced fix; (3) on a further tie, the closure covering the widest failure class (which usually also closes the most other P0/P1 gaps). Focus recommendations on P0 and P1.

### Bad vs Good

Bad: blame-shaped ("Reviewer should have been more careful") or untestable ("Add more tests"). Bad: misclassifying a failure with a diff-visible trigger as Non-Reviewable just because it only manifests under load.

Good: structural and enforceable - names the failure class, points to a specific check, and ties the fix to a target file or CI step. Example:
- Gap: Automated-gate (P0). Causal link: unbatched UPDATE on a 40M-row table → lock queue → app-wide timeouts. Fix: migration linter requiring batched writes; EXPLAIN gate on migration PRs in CI.

## Output

```
## Review Gap Analysis

### Causal Chain
{Code change or latent condition} → {intermediate effect} → {production failure}

### Gaps Identified

(3-5 rows, Non-Reviewable rows included; same-mechanism overlaps collapsed)

| # | Type | Priority | Causal Link | Why It Existed | Fix | Enforcement |
| - | ---- | -------- | ----------- | -------------- | --- | ----------- |

### Highest-Leverage Fix
{Single closure with greatest prevention impact, and why it wins the tie-break.}

### Non-Reviewable Factors
{Prose: why review could not catch this class, referencing `Non-Reviewable` rows by #. Primary for no-PR incidents. Omit when no row is Non-Reviewable.}
```

## Avoid

- Blame ("be more careful", "the reviewer should have caught it") - not a structural fix
- Treating review as the only quality gate when CI, integration tests, monitoring, canary, or load tests would catch the class
- Listing gaps without causal connection to the specific incident
- Ignoring non-reviewable failure modes (config drift, load-dependent, emergent, overruled feedback)
- Collapsing distinct-mechanism gaps into one row, losing a remediation path
