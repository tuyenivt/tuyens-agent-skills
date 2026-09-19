---
name: ops-failure-classification
description: Classify production failures by type, scope, and originating system layer to drive structured incident investigation.
metadata:
  category: ops
  tags: [incident, failure, classification, root-cause]
user-invocable: false
---

# Failure Classification

## When to Use

- First step in any incident investigation
- When triaging multiple concurrent failures to find shared root cause

## Rules

- Classify on observable evidence (metrics, logs, error messages, the code the incident names, prior review findings on that code), not speculation. Evidence is what the incident names plus the code it points at; history outside the repository (parameter groups, container env changes) is named in `Missing Evidence`, not searched for. When the incident report's stated cause contradicts the code or migration history, classify from the code and cite the contradiction in Evidence as `reported: <claim>; code shows: <fact>`. A contradiction the code resolves is not a candidate.
- A failure may have several types. List the **root type first** - the one whose fix prevents recurrence under a larger version of the same trigger; when two fixes each prevent this incident, the one that also survives a bigger trigger is root. Subsequent entries are the trigger, then symptoms, in causal order; a type with no evidence of its own is not listed. The `Layer` line is the root type's layer. When a deploy shipped the defect, the defect's own type is root; list `Deployment / config drift` after it.
- When evidence cannot discriminate between types, list plausible candidates root-first by likelihood (at most three, at any position in the list), mark each `(candidate)`, and add a `Missing Evidence` line naming what would discriminate them. A single matching signal word is not a classification (intermittent alone does not imply Concurrency issue). When the candidates originate in different layers, the `Layer` line carries the same uncertainty, in the same order, marked `(candidate)`, with the type each belongs to in the rationale.
- Identify the layer where the failure **originates**, not where the symptom appears.
- Classification is a starting point for investigation, not a root cause conclusion.

## Patterns

### Failure Types

| Type                                 | Signals                                                                              |
| ------------------------------------ | ------------------------------------------------------------------------------------ |
| Logic bug                            | Wrong output, incorrect state transition, failed assertion                           |
| Concurrency issue                    | Data race, deadlock, lost update, isolation anomaly (phantom or non-repeatable read), intermittent failure that reproduces under load |
| Transaction boundary error           | Partial writes, rollback failures, side effect committed before or without the write, work done outside the transaction |
| DB performance degradation           | Slow queries, lock contention, plan regression, replication lag                      |
| N+1 / query overload                 | Latency scales with data size, high query count                                      |
| External dependency failure          | Timeout, 5xx downstream, certificate expiry, the dependency's own status page        |
| Misconfiguration                     | Wrong env value, missing property, feature flag mismatch, a config the code ignores  |
| Resource exhaustion                  | OOM, thread pool full, connection pool exhausted (an application-side pool), FD limit, disk full, carrier-thread starvation (virtual threads) |
| Deployment / config drift            | Works in staging not prod, recent deploy correlates with failure                     |
| Architectural boundary violation     | Unexpected coupling, layer bypass causing cascading failure                          |
| Resource contention / noisy neighbor | Two workloads competing on a shared pool or the database's connection ceiling (batch vs OLTP, new feature vs main traffic) |
| Silent contract loss                 | No failed request to rate: empty results, zero-record polls, dropped messages, a consumer subscribed to a topic or endpoint that no longer exists. Detected by absence - throughput that went to zero, a job that stopped producing output |

A saturated pool is three rows apart by cause: `Resource exhaustion` when one workload's own demand filled it, `Resource contention` when a second workload competed for it, `DB performance degradation` only when the database itself slowed and held connections longer. DNS resolution failures on the caller's resolver or egress path originate in Infrastructure; an expired record or authoritative outage on the dependency's own zone is `External dependency failure`. Lock waits are `DB performance degradation` when a slow or long transaction holds the lock, `Concurrency issue` when two application paths take locks in conflicting order (deadlock victims) or race on one row. A wrong value is `Misconfiguration`; `Deployment / config drift` is for a value that differs between environments or that a deploy changed - when both hold, `Misconfiguration` is the defect's type and drift follows it.

### Failure Scope

Two independent axes:

| Axis      | Values                                                                              |
| --------- | ----------------------------------------------------------------------------------- |
| Requests  | `Total` (all requests affected), `Partial X%` (a subset - from metrics at the incident's peak; `Partial ~X%` when only a qualitative estimate exists, its source in Evidence; `Partial X% aggregate, not split` when one rate spans several signatures), `Absent` (a silent failure: no requests exist to rate, the signal is the missing output) |
| Spread    | `Isolated` (stays within one component; rolling through replicas of one service is still Isolated), `Cascading` (a *different* component fails - identify the propagation path) |

### System Layers

- **Infrastructure**: VM, container, network, DNS, load balancer
- **Platform**: Database, cache, message broker, object storage
- **Application**: Service logic, controllers, scheduled tasks, application-side pools
- **Integration**: External APIs, event consumers, webhooks
- **Configuration**: Environment variables, feature flags, secrets

### Good

```
Failure Type: Architectural boundary violation, External dependency failure, Resource exhaustion

Scope: Partial 38% + Cascading (gateway latency -> checkout holds pooled DB connections across the external call -> unrelated endpoints starve)

Layer: Application (the checkout path holds a pooled connection across the gateway call; a bulkhead survives a larger gateway outage, fixing the gateway does not; gateway p99 9s in Integration was the trigger)

Evidence: checkout in `orders.py` calls the gateway inside the request's DB session; gateway p99 9s (baseline 400ms); api pods `QueuePool limit of size 10 overflow 5 reached` with 6 threads awaiting a connection, GET /orders (no gateway call) returning 503
```

### Bad

```
Failure Type: System error
Something is wrong with the database.
```

## Output Format

Consuming workflow skills parse the `Failure Type` and `Layer` lines to drive hypothesis generation. The four unconditional lines are `Failure Type`, `Scope`, `Layer`, `Evidence`; `Missing Evidence` appears only when any type is marked `(candidate)`. Blank lines between lines.

```
### {failure identifier}                        {only when more than one block is emitted}

Failure Type: {one or more types from the table, root first, comma-separated; each candidate suffixed (candidate)}

Scope: {Total | Partial X% | Partial ~X% | Partial X% aggregate, not split | Absent} + {Isolated | Cascading (<propagation path>)}

Layer: {Infrastructure | Platform | Application | Integration | Configuration}{, further candidate layers (candidate), in Failure Type order} ({1-sentence rationale: why the root originates here; with candidates, the type each layer belongs to})

Evidence: {observable signals - metrics, log lines, error messages, code the incident names - one `;`-separated group per type, in Failure Type order}

Missing Evidence: {what would discriminate the candidates}
```

When triaging multiple concurrent failures, emit one block per independent failure, each under its own `###` heading; failures whose evidence points at one shared root share a single block listing that root type first. Two failures share a root when one fix removes both; when the evidence only shows a shared trigger, they are separate blocks. One aggregate error rate spanning several signatures is written as `Partial X% aggregate, not split`; a signature that was Total inside a Partial aggregate is stated in Evidence, not in Scope.

Never omit Evidence; unsupported classifications mislead investigation. For a silent failure, Evidence cites the absent signal and when it stopped (`zero records polled since 03-14 09:00, previously ~4k/hour`) - absence is observable. A contributing factor that fits no row (a hard-coded value that defeated a mitigation) is cited in Evidence under the type it aggravated, not given a row of its own.

## Avoid

- Classifying without citing observable evidence.
- Stopping at the first matching type without checking for compound failures.
- Confusing the symptom layer with the origin layer.
- Treating the classification as a root cause.
