---
name: root-cause-hypothesis
description: Generate ranked root cause hypotheses with calibrated confidence, contributing factors, evidence balance, and verification steps.
metadata:
  category: ops
  tags: [incident, root-cause, hypothesis, diagnosis]
user-invocable: false
---

# Root Cause Hypothesis

## When to Use

Whenever ranked hypotheses with calibrated confidence are needed; typically after failure classification and propagation analysis.

## Rules

- Confidence percentages plus a "remaining" bucket sum to 100%
- For intermittent failures, the mechanism must explain why the failure only sometimes occurs (threshold, race, load-dependent trigger, cache expiry, replication lag accumulation)
- Timeline field is required when there is a deploy-to-symptom lag; omit otherwise

## Patterns

### Evidence Value

High-value: stack traces, metric timelines, resource metrics at the failure point. Medium: deploy correlation, config diffs, topology context. Low: log patterns, user reports.

### Confidence Calibration

| Range    | Evidence Profile                                                                                                     |
| -------- | -------------------------------------------------------------------------------------------------------------------- |
| 70-90%   | Direct causal evidence: stack trace at failure point, metric showing threshold breach, deploy correlation + mechanism |
| 40-69%   | Strong correlation with plausible mechanism but no direct proof                                                      |
| 15-39%   | Circumstantial / speculative: pattern matches a known mode but key evidence is missing or contradictory              |

Start at 50% for correlation + plausible mechanism. +20-30% for a resource metric or stack trace at the failure point. Cap at 90% without a fix-and-confirm test.

### When Evidence Is Thin

Propose a causal mechanism, not just the correlation. Consider multiple causal directions: A→B, B→A, or C→both. List the 2-3 specific evidence items that would raise confidence and where to get them.

## Output

```
Primary Hypothesis ({confidence}% confidence):
Suspect: {component} - {resource or module}
Mechanism: {how the failure occurs; for intermittent, explain trigger condition}
Evidence for: {observations with specific values}
Evidence against: {observations that weaken it}
Contributing factors: {conditions that made the system vulnerable - distinct from root cause}
Triggering change: {PR, deploy, config, traffic shift, or "None identified"}
Timeline: {if lag between trigger and symptom, explain why}
Verification: {one concrete action to confirm or reject}

Secondary Hypothesis ({confidence}% confidence):
Suspect:
Mechanism:
Evidence for:
Evidence against:
Contributing factors:
Verification:

Remaining ({remaining}%): unexplained.
{If remaining > 40%, list specific missing evidence that would enable better hypotheses.}
```

## Avoid

- Anchoring on the first hypothesis without considering alternatives
- Restating a correlation as a mechanism (e.g., "high CPU correlates with 503s" is a correlation, not a mechanism)
- Generic debugging suggestions instead of specific suspects
- Ignoring topology context (DB primary/replica, cache tiers, regional routing, sharded queues) when signals point to a layered subsystem
- Hypotheses spanning multiple system layers without tracing the causal chain between layers
