---
name: root-cause-hypothesis
description: Generate ranked root cause hypotheses with calibrated confidence, contributing factors, evidence balance, and verification steps.
metadata:
  category: ops
  tags: [incident, root-cause, hypothesis, diagnosis]
user-invocable: false
---

# Root Cause Hypothesis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- After failure classification and propagation analysis
- Forming structured hypotheses to guide investigation
- Communicating incident status to stakeholders

## Rules

- Every hypothesis cites specific evidence and includes a verification step
- Always produce a primary plus at least one secondary
- Confidence percentages plus a "remaining" bucket sum to 100%
- For intermittent failures, the mechanism must explain why the failure only sometimes occurs (threshold, race, load-dependent trigger, cache expiry, replication lag accumulation)

## Pattern

### Evidence Categories

| Evidence         | Diagnostic Value | Notes                                                                            |
| ---------------- | ---------------- | -------------------------------------------------------------------------------- |
| Stack trace      | High             | Points to exact failure location                                                 |
| Metric timeline  | High             | Correlates failure with system state change                                      |
| Resource metric  | High             | CPU, memory, pool, disk - quantifies state                                       |
| Recent deploy    | Medium-High      | Strong temporal correlation                                                      |
| Log pattern      | Medium           | Depends on log quality                                                           |
| Config diff      | Medium           | Often overlooked; high impact when relevant                                      |
| Topology context | Medium           | Replica roles, routing, failover - explains why only some paths fail             |
| User report      | Low-Medium       | Useful for symptoms, unreliable for cause                                        |

### Confidence Calibration

| Range    | Evidence Profile                                                                                                     |
| -------- | -------------------------------------------------------------------------------------------------------------------- |
| 70-90%   | Direct causal evidence: stack trace at failure point, metric showing threshold breach, deploy correlation + mechanism |
| 40-69%   | Strong correlation with plausible mechanism but no direct proof                                                      |
| 15-39%   | Circumstantial / speculative: pattern matches a known mode but key evidence is missing or contradictory              |

Correlation without a causal mechanism caps confidence at 50%. A stack trace or resource metric at the exact failure point adds 20-30% over correlation alone.

### When Evidence Is Thin

When the input is only a correlation or sparse signals:

1. Generate hypotheses that propose a causal mechanism explaining the correlation - do not restate it
2. Consider multiple causal directions: A→B, B→A, or C→both
3. Cap confidence at 50% for correlation-only hypotheses
4. List the 2-3 specific evidence items that would raise confidence and where to get them (dashboard, log query, CLI command)

This is more useful than a low-confidence guess - it directs the next step.

### Micro-example

```
Primary (75%): OrderService payment pool exhaustion
Mechanism: PR #482 added 3x retry without timeout adjustment. Retry holds connections,
  pool (size 40) drains in 4 min under peak load. Intermittent because exhaustion only
  occurs once concurrent payment requests exceed pool size.
Evidence for: HikariCP active=40/40, payment-gateway p99=12s, deploy 2h before onset
Evidence against: No code change in OrderService itself
Contributing factors: No pool acquisition timeout, no circuit breaker on payment calls
Triggering change: PR #482 (retry logic without timeout budget)
Timeline: 15-min lag deploy→symptom because retry amplification only saturates at peak (~200 req/min)
Verification: Diff payment p99 and pool active count vs deploy time

Secondary (15%): RDS connection limit
Mechanism: Leaked connections from incomplete transactions hit max_connections
Evidence for: Some connection timeout errors; no idle-in-transaction timeout configured
Evidence against: RDS connections metric at 60% utilization
Verification: Query pg_stat_activity for idle-in-transaction connections

Remaining 10%: unaccounted - missing slow-query log evidence on replica
```

## Output

Always produce one primary, at least one secondary, plus a remaining bucket.

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
- Hypotheses without verification steps
- Generic debugging suggestions instead of specific suspects
- Ignoring DB topology (primary vs replica, read routing, replication lag) when DB signals are present
- Hypotheses spanning multiple system layers without tracing the causal chain between layers
