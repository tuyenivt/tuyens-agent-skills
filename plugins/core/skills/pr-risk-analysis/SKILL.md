---
name: pr-risk-analysis
description: Lightweight heuristic PR risk classification based on change signals
metadata:
  category: review
  tags: [risk-assessment, pull-request, change-analysis]
user-invocable: false
---

# PR Risk Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- As the first step in any code review to frame the review scope
- When evaluating whether a PR needs additional reviewers or testing
- When triaging review priority across multiple PRs

## Rules

- This is a heuristic, not a guarantee -- use as a framing tool
- Run before line-level review to calibrate attention
- Do not spend more than 30 seconds on this assessment
- When in doubt, round up (Medium over Low, High over Medium)

## Pattern

Evaluate these risk signals from the diff:

### Risk Signals

| Signal                         | Weight | Description                                           |
| ------------------------------ | ------ | ----------------------------------------------------- |
| Cross-module changes           | High   | Changes spanning 2+ modules or packages               |
| Shared state mutation          | High   | Modifying global state, singletons, or shared caches  |
| Database/schema changes        | High   | Migrations, index changes, entity modifications       |
| Public API changes             | High   | Endpoint signatures, request/response contracts       |
| Transaction boundary changes   | High   | New/modified transaction boundaries, isolation levels |
| Async/event flow changes       | Medium | New event publishers, listeners, message handlers     |
| Config or feature flag changes | Medium | Application properties, environment config            |
| New external dependencies      | Medium | New libraries, external service integrations          |
| Security-adjacent changes      | High   | Auth, authorization, input validation, crypto         |
| Test-only changes              | Low    | Only test files modified                              |
| Documentation-only changes     | Low    | Only docs/comments modified                           |

### Classification

**Low** -- Single module, no shared state, no API/schema changes, adequate tests.

**Medium** -- Cross-module OR shared state OR config changes, but bounded scope.

**High** -- API/schema changes OR transaction boundary changes OR security-adjacent, affecting multiple consumers.

**Critical** -- Database migration on high-traffic table OR breaking public API change OR security mechanism modification.

### Good: Concise risk output

```
Risk Level: Medium
Signals: Cross-module change (order-service, payment-service), new async event flow.
```

### Bad: Over-detailed risk analysis

```
Risk Level: Medium
After careful analysis of all 47 files changed, considering the dependency graph
between modules, evaluating the transitive closure of affected components...
[200 more words]
```

## Avoid

- Treating this as a formal risk assessment process
- Spending significant time on the classification
- Letting Low risk become an excuse to skip review
- Conflating risk level with code quality
