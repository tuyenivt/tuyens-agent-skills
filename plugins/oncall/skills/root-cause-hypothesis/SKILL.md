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

- Produce Primary + Secondary by default. Primary alone is allowed when all evidence supports one mechanism and nothing contradicts it. Add a Tertiary only when a third candidate is mechanistically distinct and scores ≥15%; otherwise fold it into Remaining.
- Hypotheses may share a triggering change when the mechanisms differ (e.g., two distinct failure modes of the same upgrade) - rank them independently.
- Score each hypothesis independently with the scoring procedure, then reduce non-primary scores proportionally until hypotheses + Remaining (min 5%) sum to 100%; never reduce the primary. Round to 5%.
- For intermittent failures, the mechanism must explain why the failure only sometimes occurs (threshold, race, load-dependent trigger, cache expiry, replication lag accumulation)
- A contributing factor is a condition that amplified the failure; if removing the condition alone would have prevented the incident, it is part of the mechanism, not a contributing factor
- Timeline field is required whenever trigger and symptom are not simultaneous - state the lag and why, or "lag unknown"

## Patterns

### Confidence Scoring

Score each hypothesis with this procedure; the table below is a sanity band, not a second method.

- Start at 50% for correlation + plausible mechanism
- +15 for direct evidence at the failure point (stack trace there, or resource metric showing saturation)
- +10 per additional independent direct signal, counting at most two (+20 max)
- +10 when an independent pattern matches the mechanism's prediction (e.g., regional error distribution matches a canary rollout order)
- +10, applied once regardless of how many alternatives it rules out, when negative evidence eliminates an alternative class (the alternative would have produced errors/signals that are absent)
- -10 when key discriminating evidence is missing or contradictory
- Cap at 90% without a fix-and-confirm test

| Range    | Sanity check                                                                                          |
| -------- | ------------------------------------------------------------------------------------------------------ |
| 70-90%   | Direct causal evidence at the failure point plus corroborating signals (deploy correlation, mechanism) |
| 40-69%   | Strong correlation with plausible mechanism but no direct proof                                        |
| 15-39%   | Circumstantial: pattern matches a known mode but key evidence is missing or contradictory              |

Evidence value for "direct": stack traces, metric timelines, resource metrics at the failure point. Deploy correlation, config diffs, and topology context corroborate but are not direct. Log patterns and user reports are weak.

### Remaining Bucket

Remaining = probability mass on causes not yet considered. Always present, even at 5%. If Remaining > 40%, list the specific missing evidence that would enable better hypotheses and where to get it.

### When Evidence Is Thin

Applies when every hypothesis scores below 40%. Propose a causal mechanism, not just the correlation. Consider multiple causal directions: A→B, B→A, or C→both. The Verification field still names the single most discriminating action; the 2-3 evidence items that would raise confidence go under Remaining.

## Output

All hypotheses use the same fields; `Triggering change` and `Timeline` may be omitted on non-primary hypotheses when identical to the primary or unknown.

```
Primary Hypothesis ({confidence}% confidence):
Suspect: {component} - {resource or module}
Mechanism: {how the failure occurs; for intermittent, explain trigger condition}
Evidence for: {observations with specific values}
Evidence against: {observations that weaken it, or "none - no contradicting signal" (distinct from unexamined)}
Contributing factors: {amplifying conditions - distinct from root cause}
Triggering change: {PR, deploy, config, infra/platform change, traffic shift, or "None identified"}
Timeline: {trigger-to-symptom lag + why; "lag unknown" plus the mechanism's implied lag when the mechanism predicts one; omit when simultaneous}
Verification: {one concrete action to confirm or reject}

Secondary Hypothesis ({confidence}% confidence):
{same fields}

Remaining ({remaining}%): unexplained.
{If > 40%: missing evidence items + where to get them.}
```

## Avoid

- Anchoring on the first hypothesis without considering alternatives
- Restating a correlation as a mechanism (e.g., "high CPU correlates with 503s" is a correlation, not a mechanism)
- Generic debugging suggestions instead of specific suspects
- Ignoring topology context (DB primary/replica, cache tiers, regional routing, sharded queues) when signals point to a layered subsystem
- Hypotheses spanning multiple system layers without tracing the causal chain between layers
- Scoring from the sanity-band table directly instead of the scoring procedure
