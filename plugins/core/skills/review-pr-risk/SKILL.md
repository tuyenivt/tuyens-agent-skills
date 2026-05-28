---
name: review-pr-risk
description: Score PR risk in under 30 seconds from diff signals: cross-module, schema, API, security, size. Heuristic framing for code review.
metadata:
  category: review
  tags: [risk-assessment, pull-request, change-analysis]
user-invocable: false
---

# PR Risk Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- First step in any code review to frame scope and attention
- Triaging review priority across multiple PRs
- Deciding whether a PR needs extra reviewers, tests, or splitting

If no diff exists yet (architecture proposal, migration plan), use `review-change-risk` instead.

## Rules

- Heuristic, not a guarantee. Use as framing, not a gate.
- Run before line-by-line review.
- Spend at most 30 seconds.
- When in doubt, round up.

## Patterns

### Risk Signals

| Signal                         | Weight | Trigger                                                     |
| ------------------------------ | ------ | ----------------------------------------------------------- |
| Cross-module changes           | High   | 2+ modules or packages                                      |
| Shared state mutation          | High   | Global state, singletons, shared caches                     |
| Database/schema changes        | High   | Migrations, index changes, entity modifications             |
| Public API changes             | High   | Endpoint signatures, request/response contracts             |
| Transaction boundary changes   | High   | New/modified transaction scope or isolation level           |
| Security-adjacent changes      | High   | Auth, authorization, input validation, crypto               |
| Async/event flow changes       | Medium | New publishers, listeners, message handlers                 |
| Config or feature flag changes | Medium | Application properties, environment config                  |
| New external dependencies      | Medium | New libraries or external service integrations              |
| PR size (lines changed)        | Medium | > 500 lines increases miss rate                             |
| Missing test changes           | Medium | High-risk change with no corresponding tests                |
| Author unfamiliarity           | Low    | Author's first PR to these modules or the repo              |
| Test-only changes              | Low    | Only test files modified                                    |
| Documentation-only changes     | Low    | Only docs/comments modified                                 |

### Classification

- **Low** - single module, no shared state, no schema or API change, tests adequate
- **Medium** - cross-module OR shared state OR config changes, bounded scope
- **High** - one high-weight signal affecting multiple consumers
- **Critical** - 2+ high-weight signals, OR migration on a high-traffic table + any high, OR breaking API change + security change

### Good

```
Risk Level: Medium
Signals: Cross-module change (order-service, payment-service), new async event flow.
```

### Bad

```
Risk Level: Medium
After careful analysis of all 47 files changed, considering the dependency graph
between modules, evaluating the transitive closure of affected components...
[200 more words]
```

## Output Format

Callers parse the `Risk Level:` line. Keep to 2-3 lines (4 max).

```
Risk Level: {Low | Medium | High | Critical}
Signals: {comma-separated triggered signals, 1-2 sentences max}
Action: {split PR | add tests before merge | require additional reviewer}
```

`Action:` is optional - include only when a specific action is warranted.

### Examples

```
Risk Level: High
Signals: Public API contract change (POST /orders), schema migration on orders table.
Action: require additional reviewer
```

```
Risk Level: Low
Signals: Test-only changes, no shared state or API modification.
```

Never exceed four lines. Never omit `Signals:`.

## Avoid

- Treating this as a formal risk assessment
- Spending significant time
- Letting Low risk become an excuse to skip review
- Conflating risk level with code quality
