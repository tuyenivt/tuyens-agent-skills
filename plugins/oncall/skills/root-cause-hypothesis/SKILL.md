---
name: root-cause-hypothesis
description: Generate ranked root cause hypotheses with confidence levels and evidence
metadata:
  category: ops
  tags: [incident, root-cause, hypothesis, diagnosis]
user-invocable: false
---

# Root Cause Hypothesis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- After failure classification and propagation analysis are complete
- When forming structured hypotheses to guide investigation
- When communicating incident status to stakeholders

## Rules

- Every hypothesis must cite specific evidence
- Assign confidence as a percentage based on evidence strength (see calibration guide below)
- Always identify a primary and at least one secondary suspect
- Link hypotheses to a likely triggering change when evidence exists
- Never present a hypothesis without a testable verification step
- Correlation is not causation -- when two signals co-occur (e.g., high CPU + 503s), the hypothesis must propose a causal mechanism, not just note the correlation
- For intermittent failures, the mechanism must explain the intermittency (threshold, race condition, load-dependent trigger, cache expiry, etc.)

## Pattern

### Evidence Categories

Rate each evidence type by diagnostic value:

| Evidence         | Diagnostic Value | Notes                                                                            |
| ---------------- | ---------------- | -------------------------------------------------------------------------------- |
| Stack trace      | High             | Points to exact failure location                                                 |
| Metric timeline  | High             | Correlates failure with system state change over time                            |
| Resource metric  | High             | CPU, memory, connection pool, disk - quantifies resource state                   |
| Recent deploy    | Medium-High      | Strong temporal correlation                                                      |
| Log pattern      | Medium           | Depends on log quality and coverage                                              |
| Config diff      | Medium           | Often overlooked, high impact when relevant                                      |
| Topology context | Medium           | Replica roles, routing rules, failover state - explains why only some paths fail |
| User report      | Low-Medium       | Useful for symptoms, unreliable for cause                                        |

### Hypothesis Structure

For each hypothesis, provide:

1. **Suspect component** -- the specific module, service, or resource
2. **Mechanism** -- how the failure occurs (not just where). For intermittent failures, explain what condition triggers the failure and why it only sometimes occurs (e.g., "CPU exceeds 90% threshold only under read-heavy query mix, causing replica lag > 5s, which triggers connection timeout on read-routed queries")
3. **Evidence for** -- observations supporting this hypothesis, with specific values
4. **Evidence against** -- observations that weaken it
5. **Contributing factors** -- conditions that made the system vulnerable but are distinct from the root cause (e.g., no connection pool limits, missing circuit breaker, no replica health check)
6. **Triggering change** -- recent PR, deploy, config change, or traffic pattern
7. **Timeline interpretation** -- if there is a lag between trigger and symptom onset, explain why (load-dependent threshold, gradual resource leak, cache expiry, replication lag accumulation)
8. **Confidence** -- percentage based on evidence balance (see calibration guide)
9. **Verification step** -- one concrete action to confirm or reject

### Confidence Calibration

Anchor confidence percentages to evidence strength:

| Confidence Range | Evidence Profile                                                                                                                            |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 70-90%           | Direct causal evidence: stack trace at failure point, metric showing threshold breach, confirmed deploy correlation + mechanism explanation |
| 40-69%           | Strong correlation with plausible mechanism but no direct proof: co-occurring metrics, temporal correlation without confirmed causation     |
| 15-39%           | Circumstantial: pattern matches a known failure mode but key evidence is missing or contradictory                                           |
| Below 15%        | Speculative: possible but minimal supporting evidence; include only if no stronger hypotheses exist                                         |

Correlation without a causal mechanism caps confidence at 50%. A stack trace or resource metric at the exact failure point adds 20-30% over correlation alone.

### Good: Structured hypothesis with evidence

```
Primary Hypothesis (75% confidence):
Suspect: OrderService.processPayment() -- connection pool exhaustion
Mechanism: Payment gateway latency spike (30s) holds connections, exhausting HikariCP pool.
  Intermittent because exhaustion only occurs when concurrent payment requests exceed pool size (40), which happens during peak order bursts.
Evidence for: HikariCP active=40/40, payment-gateway p99=12s (deployed 2h ago: PR #482 added retry logic)
Evidence against: No code change in OrderService itself
Contributing factors: No connection pool timeout configured, no circuit breaker on payment gateway calls
Triggering change: PR #482 added 3x retry to payment calls without adjusting timeout budget
Timeline: Deploy at 14:00, first 503s at 14:15 -- 15min lag because retry amplification only exhausts the pool once peak traffic starts (~200 orders/min)
Verification: Check payment-gateway response times and PR #482 retry config; correlate 503 timing with concurrent request count exceeding 40

Secondary Hypothesis (20% confidence):
Suspect: Database connection limits
Mechanism: RDS max_connections reached due to leaked connections from incomplete transactions
Evidence for: Some connection timeout errors in logs
Evidence against: CloudWatch RDS connections metric shows 60% utilization
Contributing factors: No idle-in-transaction timeout configured
Verification: Query pg_stat_activity for idle-in-transaction connections
```

### Good: Multi-layer hypothesis (app symptom + DB resource correlation)

```
Primary Hypothesis (55% confidence):
Suspect: DB read replica -- CPU saturation causing query timeout on read-routed order queries
Mechanism: Unoptimized analytics query (full table scan on orders table) runs on the read replica, consuming CPU and starving order-creation read queries routed to the same replica.
  Intermittent because the analytics query runs every 5 minutes and takes 30-90s depending on load.
  503s only occur during the scan window when other queries queue behind it.
Evidence for: Replica CPU at 95% during 503 windows, order-read query p99 jumps from 50ms to 8s during same windows, 503s correlate with analytics cron schedule
Evidence against: Primary DB CPU is normal (40%), no 503s on write path
Contributing factors: No query timeout on replica, no separate replica for analytics workload, read routing does not check replica health/load
Triggering change: PR #310 added new analytics dashboard query 3 days ago; 503 reports started same day
Timeline: Analytics query deployed 3 days ago but 503s were initially rare because order volume was low on weekends; became frequent on Monday with normal weekday traffic
Verification: Check replica slow query log for full-scan queries during 503 windows; temporarily disable analytics cron and observe if 503s stop

Secondary Hypothesis (30% confidence):
Suspect: Connection pool exhaustion on order service due to replica timeout
Mechanism: Read queries to the overloaded replica hold connections waiting for response, eventually exhausting the application connection pool, blocking new order creation requests
Evidence for: 503 is a connection timeout error (not a query error), connection pool metrics unavailable
Evidence against: If pool exhaustion were the cause, write-path orders would also fail
Contributing factors: No connection pool saturation alerting configured
Verification: Check application connection pool active/idle counts during 503 window

Remaining confidence (15%): unexplained by current hypotheses.
  Missing evidence: connection pool metrics, replica replication lag metric, detailed slow query log.
```

### Bad: Vague hypothesis without evidence

```
Root Cause: Probably a database issue.
We should check the database.
```

### Bad: Correlation without causal mechanism

```
Primary Hypothesis (80% confidence):
Suspect: Database replica
Mechanism: High CPU on replica correlates with 503s
Evidence for: CPU is high when 503s happen
```

This is bad because it restates the correlation as the mechanism. It assigns 80% confidence without explaining why high CPU causes 503s (query timeout? connection exhaustion? replication lag?). Correlation without mechanism should be capped at 50%.

### Insufficient Evidence

When available evidence is too thin to form a meaningful hypothesis (no stack trace, no metrics, no deploy correlation), do not guess. Instead:

1. State the strongest signal available and what failure class it suggests
2. List the 2-3 specific evidence items that would enable a hypothesis (e.g., "need connection pool metrics for the last hour", "need the deploy diff from the last 4 hours")
3. For each missing item, state where to get it (dashboard, log query, CLI command)

This is more useful than a low-confidence hypothesis - it tells the team exactly what to gather next rather than sending them chasing a weak lead.

### Correlation-Only Input

When the input provides only a correlation (e.g., "503s correlate with high CPU on DB replica") without direct causal evidence:

1. Generate hypotheses that propose a causal mechanism explaining the correlation - do not simply restate it
2. Consider multiple causal directions: does A cause B, does B cause A, or does C cause both?
3. Cap confidence at 50% for any hypothesis based on correlation alone
4. List what evidence would elevate the strongest hypothesis above 50% (e.g., slow query log showing full scans during CPU spikes, connection pool metrics showing exhaustion during 503 windows)

## Output Format

Produce one primary hypothesis and at least one secondary. Use this structure:

```
Primary Hypothesis ({confidence}% confidence):
Suspect: {component} -- {resource or module}
Mechanism: {how the failure occurs, not just where; for intermittent failures, explain the trigger condition}
Evidence for: {observations supporting, with specific values}
Evidence against: {observations that weaken it}
Contributing factors: {conditions that made the system vulnerable, distinct from root cause}
Triggering change: {PR, deploy, config change, or "None identified"}
Timeline: {if lag between trigger and symptom, explain why}
Verification: {one concrete action to confirm or reject}

Secondary Hypothesis ({confidence}% confidence):
Suspect: {component}
Mechanism: {how}
Evidence for: {what supports it}
Evidence against: {what weakens it}
Contributing factors: {vulnerability conditions}
Verification: {action}

Remaining confidence ({remaining}%): unexplained by current hypotheses.
{If remaining > 40%, list the specific missing evidence that would enable better hypotheses.}
```

Confidence percentages across all hypotheses plus the remaining share should sum to 100%. The "remaining" bucket acknowledges unknown unknowns - if it exceeds 40%, explicitly state what evidence is missing.

## Avoid

- Anchoring on the first hypothesis without considering alternatives
- Presenting hypotheses without actionable verification steps
- Assigning high confidence without strong corroborating evidence
- Restating a correlation as a mechanism (e.g., "high CPU correlates with 503s" is not a mechanism)
- Ignoring recent changes as potential triggers
- Generic debugging suggestions instead of specific hypotheses
- Treating intermittent failures as constant ones -- the mechanism must explain why the failure only sometimes occurs
- Ignoring database topology (primary vs. replica, read routing, replication lag) when DB-related signals are present
- Proposing hypotheses that span multiple system layers without tracing the causal chain between layers
