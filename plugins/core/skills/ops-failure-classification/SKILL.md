---
name: ops-failure-classification
description: Classify production failures by type, scope, and originating system layer to drive structured incident investigation.
metadata:
  category: ops
  tags: [incident, failure, classification, root-cause]
user-invocable: false
---

# Failure Classification

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- First step in any incident investigation
- When triaging multiple concurrent failures to find shared root cause

## Rules

- Classify on observable evidence (metrics, logs, error messages), not speculation.
- A failure may have several types. List the **root type first** (the one whose resolution would resolve the others); subsequent entries are symptom or trigger types. When a deploy shipped the defect, the defect's own type is root; list `Deployment / config drift` after it.
- When evidence cannot discriminate between types, list plausible candidates root-first by likelihood, mark each `(candidate)`, and add a `Missing Evidence` line naming what would discriminate them. A single matching signal word is not a classification (intermittent alone does not imply Concurrency issue).
- Identify the layer where the failure **originates**, not where the symptom appears.
- Classification is a starting point for investigation, not a root cause conclusion.

## Patterns

### Failure Types

| Type                                 | Signals                                                                              |
| ------------------------------------ | ------------------------------------------------------------------------------------ |
| Logic bug                            | Wrong output, incorrect state transition, failed assertion                           |
| Concurrency issue                    | Intermittent failure, data race, deadlock, pinned virtual thread                     |
| Transaction boundary error           | Partial writes, phantom reads, rollback failures, lost updates                       |
| DB performance degradation           | Slow queries, lock contention, connection pool exhaustion                            |
| N+1 / query overload                 | Latency scales with data size, high query count                                      |
| External dependency failure          | Timeout, 5xx downstream, DNS failure, certificate expiry                             |
| Misconfiguration                     | Wrong env value, missing property, feature flag mismatch                             |
| Resource exhaustion                  | OOM, thread pool full, FD limit, disk full                                           |
| Deployment / config drift            | Works in staging not prod, recent deploy correlates with failure                     |
| Architectural boundary violation     | Unexpected coupling, layer bypass causing cascading failure                          |
| Resource contention / noisy neighbor | Two workloads competing on shared pool (batch vs OLTP, new feature vs main traffic)  |

### Failure Scope

| Scope     | Definition                          | Example                                                            |
| --------- | ----------------------------------- | ------------------------------------------------------------------ |
| Total     | All requests affected               | Service returns 503 for 100% of traffic                            |
| Partial   | Subset of requests affected         | 15% of checkout requests timeout; rest succeed                     |
| Isolated  | Failure stays within one component  | Single service OOM, no downstream impact                           |
| Cascading | Failure spreads to other components | Payment timeout exhausts pool, blocks checkout and cart            |

For partial failures, estimate the affected percentage from metrics. For cascading, identify the propagation path.

### System Layers

- **Infrastructure**: VM, container, network, DNS, load balancer
- **Platform**: Database, cache, message broker, object storage
- **Application**: Service logic, controllers, scheduled tasks
- **Integration**: External APIs, event consumers, webhooks
- **Configuration**: Environment variables, feature flags, secrets

### Good

```
Failure Type: Resource exhaustion, External dependency failure
Scope: Partial 15% + Cascading
Layer: Platform (connection pool exhausted) triggered by Integration (payment gateway timeout)
Evidence: HikariCP active 40/40, payment-service p99 12s (baseline 200ms)
```

### Bad

```
Failure Type: System error
Something is wrong with the database.
```

## Output Format

Consuming workflow skills parse the `Failure Type` and `Layer` lines to drive hypothesis generation. Always produce all four lines.

```
Failure Type: {one or more types from the table, root first, comma-separated}
Scope: {Total | Partial X%} + {Isolated | Cascading}
Layer: {Infrastructure | Platform | Application | Integration | Configuration} ({1-sentence rationale})
Evidence: {observable signals - metrics, log lines, error messages}
```

Never omit Evidence; unsupported classifications mislead investigation.

## Avoid

- Classifying without citing observable evidence.
- Stopping at the first matching type without checking for compound failures.
- Confusing the symptom layer with the origin layer.
- Treating the classification as a root cause.
