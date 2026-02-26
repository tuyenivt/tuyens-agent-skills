---
name: failure-classification
description: Classify production failures by type, mechanism, and system layer
metadata:
  category: ops
  tags: [incident, failure, classification, root-cause]
user-invocable: false
---

# Failure Classification

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- As the first step in any incident investigation
- When a production failure needs structured categorization before diagnosis
- When triaging multiple concurrent failures to identify shared root causes

## Rules

- Classify based on observable evidence, not speculation
- A failure may have multiple classifications -- list all that apply
- Always identify the system layer where the failure originates
- Do not confuse symptoms with failure type

## Pattern

### Failure Types

| Type                             | Signals                                                              |
| -------------------------------- | -------------------------------------------------------------------- |
| Logic bug                        | Wrong output, incorrect state transition, failed assertion           |
| Concurrency issue                | Intermittent failures, data races, deadlocks, pinned virtual threads |
| Transaction boundary error       | Partial writes, phantom reads, rollback failures, lost updates       |
| DB performance degradation       | Slow queries, lock contention, connection pool exhaustion            |
| N+1 or query overload            | Request latency spike proportional to data size, high query count    |
| External dependency failure      | Timeout, 5xx from downstream, DNS failure, certificate expiry        |
| Misconfiguration                 | Wrong env value, missing property, feature flag mismatch             |
| Resource exhaustion              | OOM, thread pool full, file descriptor limit, disk full              |
| Deployment/config drift          | Works in staging not prod, recent deploy correlates with failure     |
| Architectural boundary violation | Unexpected coupling, layer bypass causing cascading failure          |

### System Layers

Identify which layer the failure originates from:

- **Infrastructure** -- VM, container, network, DNS, load balancer
- **Platform** -- Database, cache, message broker, object storage
- **Application** -- Service logic, controllers, scheduled tasks
- **Integration** -- External APIs, event consumers, webhooks
- **Configuration** -- Environment variables, feature flags, secrets

### Good: Specific classification with evidence

```
Failure Type: Resource exhaustion + External dependency failure
Layer: Platform (connection pool) triggered by Integration (payment gateway timeout)
Evidence: HikariCP active connections at max (40/40), payment-service p99 latency 12s (baseline 200ms)
```

### Bad: Vague classification

```
Failure Type: System error
Something is wrong with the database.
```

## Avoid

- Classifying without citing observable evidence
- Stopping at the first matching type without checking for compound failures
- Confusing the symptom layer with the origin layer
- Using classifications as root cause conclusions
