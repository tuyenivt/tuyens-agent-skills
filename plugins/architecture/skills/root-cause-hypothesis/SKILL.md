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

- Produce Primary + Secondary by default. Any hypothesis that survives normalization at 10% or more is reported; one that does not is folded into Remaining and named there in one clause. A Primary strong enough to squeeze every rival below 10% therefore stands alone, which is the intended outcome, not a failure to consider alternatives.
- Hypotheses may share a triggering change when the mechanisms differ (e.g., two distinct failure modes of the same upgrade) - rank them independently.
- Report only mechanistically distinct hypotheses; two framings of one mechanism are one hypothesis.
- For intermittent failures, the mechanism must explain why the failure only sometimes occurs (threshold, race, load-dependent trigger, cache expiry, replication lag accumulation)
- A contributing factor is a condition that amplified the failure; if removing the condition alone would have prevented the incident, it is part of the mechanism, not a contributing factor. Where that counterfactual cannot be settled on the evidence, call it a contributing factor and say the counterfactual is untested - the weaker claim is the honest one
- Timeline field is required whenever trigger and symptom are not simultaneous - state the lag and why, or "lag unknown"

## Patterns

### Confidence Scoring

This procedure is the only method; there is no second scale to reconcile it against. Score each hypothesis independently, then normalize.

**Raw score.** Start, then apply every modifier that fits:

- Start at 50 for observed correlation + plausible mechanism; start at 25 when either is speculative (pattern-match without observed linkage). Score each hypothesis on evidence bearing on its OWN distinguishing claim, not on the shared symptom every candidate explains equally: a pool-exhaustion metric that fits all three candidates discriminates none of them and scores for none
- +15 for the first piece of direct evidence at the failure point (stack trace there, or a resource metric showing saturation)
- +10 for each further independent direct signal, at most two (+20). Independent means a different subsystem or a different kind of measurement, not one fact read twice
- +10 when an independent pattern matches the mechanism's prediction (e.g., regional error distribution matches a canary rollout order)
- +10, applied once regardless of how many alternatives it rules out, when negative evidence eliminates an alternative class (the alternative would have produced errors/signals that are absent)
- -10, applied once, when key discriminating evidence is missing or contradictory
- Cap at 90; a fix applied with the symptom confirmed to stop raises that hypothesis's cap to 95 and no higher

Raw scores land between 15 and 95, in steps of 5. If a score looks wrong for the evidence, the error is in how the evidence was classified - re-check which signals are genuinely direct - not in the arithmetic; never nudge the number by feel. Where two hypotheses tie on raw score, the one with direct evidence at the failure point ranks higher; if they tie on that too, the order is arbitrary and the output says so.

Evidence value for "direct": stack traces, metric timelines, resource metrics at the failure point. Deploy correlation, config diffs, and topology context corroborate but are not direct. Log patterns and user reports are weak.

**Normalization.** Reported confidences and Remaining always sum to 100, in steps of 5.

1. Let `S` be the sum of the raw scores. If `S <= 95`, every hypothesis keeps its raw score and Remaining is `100 - S`.
2. Otherwise scale every hypothesis - the primary included - by `95 / S`, so they total 95 and Remaining is 5. Scaling every hypothesis by the same factor preserves their relative strength, which pinning the primary would destroy.
3. Round each hypothesis to the nearest 5, halves up, then set Remaining to `100 - (sum of the rounded hypotheses)`. While Remaining is under 5, take 5 off the largest hypothesis and recompute; each pass lowers the sum by 5, so this ends.
4. Move any hypothesis now under 10 into Remaining, adding its value there and naming it in one clause with its raw score, so a reader can see it was scored rather than skipped. This only ever grows Remaining, so no survivor's number changes and no second pass is needed.

A primary at 90 leaves 10, enough for one rival at 10 or for a named candidate in Remaining.

### Remaining Bucket

Remaining = probability mass not carried by a reported hypothesis: causes not yet considered, plus any candidate that was scored and fell below the 10% floor. Always present, minimum 5%. List the specific missing evidence that would enable better hypotheses, and where to get it, whenever Remaining exceeds 40% or every raw score is under 40.

Score every mechanism anyone has actually argued for, plus any the evidence points at directly. A mechanism you would have to invent facts to state is not a candidate - say so in one clause under Remaining rather than scoring it.

### When Evidence Is Thin

Applies when every RAW score is under 40 - the raw score, not the normalized confidence, since normalization can push a well-evidenced hypothesis down for reasons unrelated to its evidence. Propose a causal mechanism, not just the correlation. Consider multiple causal directions: A→B, B→A, or C→both. The Verification field still names the single most discriminating action; the 2-3 evidence items that would raise confidence go under Remaining, which lists them in this case regardless of its own value.

## Output

All hypotheses use the same fields. `Triggering change` may be omitted on a non-primary hypothesis when identical to the primary. Fields are blank-line separated: this block is reproduced verbatim into callers' documents, where consecutive bare label lines would collapse into one paragraph.

```
Primary Hypothesis ({confidence}% confidence, raw {raw}):

Suspect: {component} - {resource or module}

Mechanism: {how the failure occurs; for intermittent, explain the trigger condition}

Evidence for: {observations with specific values}

Evidence against: {observations that weaken it | "none - no contradicting signal" | "not examined - {what was not checked}"}

Contributing factors: {amplifying conditions, distinct from root cause | "none identified"}

Triggering change: {PR, deploy, config, infra/platform change, traffic shift, or "None identified"}{ - risk score {score} where the caller supplied one}

Timeline: {trigger-to-symptom lag + why | "lag unknown", plus the mechanism's implied lag when the mechanism predicts one | "simultaneous"}

Verification: {one concrete action to confirm or reject; where a rival hypothesis is reported, the action that discriminates between them}

Secondary Hypothesis ({confidence}% confidence, raw {raw}):

{same fields}

{repeat the block, ranked, for every further hypothesis surviving normalization at 10% or more}

Remaining ({remaining}%): {unexplained}{, plus <candidate> - <why it fell below the floor>, one clause per dropped candidate}

{2-3 evidence items that would raise confidence, with where to get them, whenever Remaining exceeds 40% or every raw score is under 40}
```

## Avoid

- Anchoring on the first hypothesis without considering alternatives
- Restating a correlation as a mechanism (e.g., "high CPU correlates with 503s" is a correlation, not a mechanism)
- Generic debugging suggestions instead of specific suspects
- Ignoring topology context (DB primary/replica, cache tiers, regional routing, sharded queues) when signals point to a layered subsystem
- Hypotheses spanning multiple system layers without tracing the causal chain between layers
- Reporting a confidence that was judged rather than scored
