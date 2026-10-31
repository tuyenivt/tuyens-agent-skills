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

- Classify on observable evidence (metrics, logs, error messages, the code the incident names, prior review findings on that code), not speculation. Evidence is what the incident names plus the code it points at; history outside the repository that bears on the classification (parameter groups, container env changes) is named in `Missing Evidence`, not searched for. When the incident report's stated cause contradicts the code or migration history, classify from the code and cite the contradiction in Evidence as `reported: <claim> - code shows: <fact>` inside the group of the type it bears on. A contradiction the code resolves is not a candidate.
- A failure may have several types. List the **root type first** - the one whose fix prevents recurrence under a larger version of the same trigger; when two fixes each prevent this incident, the one that also survives a bigger trigger is root. Subsequent entries are the trigger, then symptoms, in causal order; a type with no evidence of its own is not listed. The `Layer` line is the root type's layer. When a deploy shipped the defect, the defect's own type is root; list `Deployment / config drift` after it.
- When evidence cannot discriminate between types, list plausible candidates root-first by likelihood (at most three, at any position in the list), mark each `(candidate)`, and add a `Missing Evidence` line naming what would discriminate them. A single matching signal word is not a classification (intermittent alone does not imply Concurrency issue). The root-position candidates are the leading Failure Type entries marked `(candidate)`. When they originate in different layers, the `Layer` line lists each of their layers in Failure Type order, each marked `(candidate)`, with the type each belongs to in the rationale; when they share one layer, the `Layer` line names it once, unmarked.
- Identify the layer where the failure **originates**, not where the symptom appears.

## Patterns

### Failure Types

| Type                                 | Signals                                                                              |
| ------------------------------------ | ------------------------------------------------------------------------------------ |
| Logic bug                            | Wrong output, incorrect state transition, failed assertion                           |
| Concurrency issue                    | Data race, deadlock, lost update, isolation anomaly (phantom or non-repeatable read), intermittent failure that reproduces under load |
| Transaction boundary error           | Partial writes, rollback failures, side effect committed before or without the write, work done outside the transaction |
| DB performance degradation           | Slow queries, lock contention, plan regression, replication lag                      |
| N+1 / query overload                 | Latency scales with data size, high query count                                      |
| External dependency failure          | Timeout, 5xx downstream, certificate expiry on the dependency's endpoint, the dependency's own status page |
| Misconfiguration                     | Wrong env value, missing property, feature flag mismatch, a config the code ignores  |
| Resource exhaustion                  | OOM, thread pool full, connection pool exhausted (an application-side pool, or the database's connection ceiling filled by one workload's own demand), FD limit, disk full, carrier-thread starvation (virtual threads pinned by `synchronized` on JDK 21-23 or by native frames on any JDK 21+, or carriers monopolized by CPU-bound virtual threads, which are not time-sliced) |
| Deployment / config drift            | Works in staging not prod, recent deploy correlates with failure                     |
| Architectural boundary violation     | Unexpected coupling, layer bypass causing cascading failure                          |
| Resource contention / noisy neighbor | Two workloads competing on a shared pool, a shared store's memory (broker, cache), or the database's connection ceiling (batch vs OLTP, new feature vs main traffic) |
| Infrastructure failure               | Node or zone loss, network partition, caller-side DNS resolver or egress failure, load balancer misrouting |
| Silent contract loss                 | No failed request to rate: empty results, zero-record polls, dropped messages, a consumer subscribed to a topic or endpoint that no longer exists. Detected by absence - throughput that went to zero, a job that stopped producing output |

A saturated pool or shared store (connections, broker or cache memory) is split by cause: `Resource exhaustion` when one workload's own demand filled it, even if sharing workloads starve; `Resource contention` when only a second workload's added demand fills it; a saturated connection pool is `DB performance degradation` only when the database itself slowed and held connections longer. DNS resolution failures on the caller's resolver or egress path are `Infrastructure failure`; an expired domain registration, a deleted or wrong record, or an authoritative-nameserver outage on the dependency's own zone is `External dependency failure`. An expired certificate the service itself presents (ingress, mTLS client cert) is `Infrastructure failure`, or `Misconfiguration` when a renewal setting is wrong. A transaction held open across an external call is `Architectural boundary violation` (the call crosses a layer the transaction should not reach); `Transaction boundary error` is reserved for a wrong commit or rollback scope. Lock waits are `DB performance degradation` when a slow or long transaction holds the lock, `Concurrency issue` when two application paths take locks in conflicting order (deadlock victims) or race on one row. A wrong value is `Misconfiguration`; `Deployment / config drift` is for a value that differs between environments, or for any deploy (code or config) that introduced the defect - when both a wrong value and drift hold, `Misconfiguration` is the defect's type and drift follows it. A defect the code shows but the incident does not exhibit is not a type of this failure: it goes in `Missing Evidence` when it could explain an unexplained signal.

### Failure Scope

Two independent axes:

| Axis      | Values                                                                              |
| --------- | ----------------------------------------------------------------------------------- |
| Requests  | `Total` (all requests affected), `Partial X%` (a subset - from metrics at the incident's peak; `Partial ~X%` when only a qualitative estimate exists, its source in Evidence; `Partial (unquantified)` when the record gives counts but no denominator, the counts in Evidence; `Partial X% aggregate, not split` when one rate spans several signatures), `Absent` (a silent failure: no requests exist to rate, the signal is the missing output) |
| Spread    | `Isolated` (stays within one component; rolling through replicas of one service is still Isolated), `Cascading` (a *different* component fails - identify the propagation path) |

### System Layers

- **Infrastructure**: VM, container, network, DNS, load balancer
- **Platform**: Database, cache, message broker, object storage
- **Application**: Service logic, controllers, scheduled tasks, application-side pools
- **Integration**: External APIs, event consumers, webhooks
- **Configuration**: Environment variables, feature flags, secrets

A `Deployment / config drift` type originates in Configuration when a value drifted and in Application when a code deploy shipped the defect.

Bad - `Failure Type: System error` / "something is wrong with the database": no type from the table, no layer, no evidence to test a hypothesis against.

### Good

```
Failure Type: Architectural boundary violation, External dependency failure, Resource exhaustion

Scope: Partial 38% + Cascading (gateway latency -> checkout holds pooled DB connections across the external call -> unrelated endpoints starve)

Layer: Application (the checkout path holds a pooled connection across the gateway call; a bulkhead survives a larger gateway outage, fixing the gateway does not; gateway p99 9s in Integration was the trigger)

Evidence: checkout in `orders.py` calls the gateway inside the request's DB session; gateway p99 9s (baseline 400ms); api pods `QueuePool limit of size 10 overflow 5 reached` with 6 threads awaiting a connection, GET /orders (no gateway call) returning 503
```

## Output Format

Consuming workflow skills parse the `Failure Type` and `Layer` lines to drive hypothesis generation. The four unconditional lines are `Failure Type`, `Scope`, `Layer`, `Evidence`; `Missing Evidence` appears when any type is marked `(candidate)`, history outside the repository bears on the classification, or a code defect the incident does not exhibit could explain an unexplained signal. Blank lines between lines.

```
### {failure identifier: operation and symptom, e.g. `payout double credit`}        {only when more than one block is emitted}

Failure Type: {one or more types from the table, root first, comma-separated; each candidate suffixed (candidate)}

Scope: {Total | Partial X% | Partial ~X% | Partial (unquantified) | Partial X% aggregate, not split | Absent} + {Isolated | Cascading (<propagation path>)}

Layer: {Infrastructure | Platform | Application | Integration | Configuration}{ (candidate)}{, <further root-candidate layer> (candidate), ...} ({1-sentence rationale: why the root originates here; with candidates, the type each layer belongs to})

Evidence: {observable signals - metrics, log lines, error messages, code the incident names, prior review findings on that code - one `;`-separated group per type, in Failure Type order}

Missing Evidence: {what would discriminate the candidates; history outside the repository that was not searched; a code defect the incident does not exhibit that could explain an unexplained signal}
```

When triaging multiple concurrent failures, emit one block per independent failure, each under its own `###` heading; failures whose evidence points at one shared root share a single block listing that root type first. Two failures share a root when one fix removes both; a shared trigger alone keeps them separate. A shared-root block's Scope is `Partial X% aggregate, not split` when its failures' rates come from one aggregate (a Total signature inside it stated in Evidence); otherwise `Total` if any failure is Total, else the largest `Partial X%` / `Partial ~X%`, else `Partial (unquantified)`, and `Absent` only when every failure is Absent; Spread is `Cascading` if any failure cascades; each failure's own Scope goes in Evidence. One aggregate error rate spanning several signatures is written as `Partial X% aggregate, not split`; a signature that was Total inside a Partial aggregate is stated in Evidence, not in Scope.

Never omit Evidence. For a silent failure, Evidence cites the absent signal and when it stopped (`zero records polled since 03-14 09:00, previously ~4k/hour`) - absence is observable. A contributing factor that did not cause the failure (a hard-coded value that defeated a mitigation), whether or not it fits a row, is cited in Evidence under the type it aggravated, not given an entry of its own.

## Avoid

- Stopping at the first matching type without checking for compound failures.
