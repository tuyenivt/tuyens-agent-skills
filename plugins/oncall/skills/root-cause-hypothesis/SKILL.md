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
- Assign confidence as a percentage based on evidence strength
- Always identify a primary and at least one secondary suspect
- Link hypotheses to a likely triggering change when evidence exists
- Never present a hypothesis without a testable verification step

## Pattern

### Evidence Categories

Rate each evidence type by diagnostic value:

| Evidence        | Diagnostic Value | Notes                                       |
| --------------- | ---------------- | ------------------------------------------- |
| Stack trace     | High             | Points to exact failure location            |
| Metric timeline | High             | Correlates failure with system state change |
| Recent deploy   | Medium-High      | Strong temporal correlation                 |
| Log pattern     | Medium           | Depends on log quality and coverage         |
| Config diff     | Medium           | Often overlooked, high impact when relevant |
| User report     | Low-Medium       | Useful for symptoms, unreliable for cause   |

### Hypothesis Structure

For each hypothesis, provide:

1. **Suspect component** -- the specific module, service, or resource
2. **Mechanism** -- how the failure occurs (not just where)
3. **Evidence for** -- observations supporting this hypothesis
4. **Evidence against** -- observations that weaken it
5. **Triggering change** -- recent PR, deploy, config change, or traffic pattern
6. **Confidence** -- percentage based on evidence balance
7. **Verification step** -- one concrete action to confirm or reject

### Good: Structured hypothesis with evidence

```
Primary Hypothesis (75% confidence):
Suspect: OrderService.processPayment() -- connection pool exhaustion
Mechanism: Payment gateway latency spike (30s) holds connections, exhausting HikariCP pool
Evidence for: HikariCP active=40/40, payment-gateway p99=12s (deployed 2h ago: PR #482 added retry logic)
Evidence against: No code change in OrderService itself
Triggering change: PR #482 added 3x retry to payment calls without adjusting timeout budget
Verification: Check payment-gateway response times and PR #482 retry config

Secondary Hypothesis (20% confidence):
Suspect: Database connection limits
Mechanism: RDS max_connections reached due to leaked connections
Evidence for: Some connection timeout errors in logs
Evidence against: CloudWatch RDS connections metric shows 60% utilization
Verification: Query pg_stat_activity for idle-in-transaction connections
```

### Bad: Vague hypothesis without evidence

```
Root Cause: Probably a database issue.
We should check the database.
```

## Avoid

- Anchoring on the first hypothesis without considering alternatives
- Presenting hypotheses without actionable verification steps
- Assigning high confidence without strong corroborating evidence
- Ignoring recent changes as potential triggers
- Generic debugging suggestions instead of specific hypotheses
