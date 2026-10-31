---
name: failure-propagation-analysis
description: Trace cascading failures across services: identify primary failure, propagation channels, shared resources, amplification loops.
metadata:
  category: ops
  tags: [incident, failure-propagation, cascading, dependencies]
user-invocable: false
---

# Failure Propagation Analysis

## When to Use

- Failure in one component is degrading others
- Multiple services report errors simultaneously and the origin is unclear
- Distinguishing a primary failure from downstream consequences
- Blast radius is moderate or wider during an incident
- What-if analysis of a hypothetical failure ("what happens if X dies?") - trace forward from the assumed failure; phrase Containment as what would stop propagation. Mode is `what-if` when the failure is assumed and nothing has been observed; symptoms reported as having occurred, however the request is framed, are `incident`, including a question about whether an observed incident would recur

## Rules

- Investigate backward from the earliest observable symptom to the origin; present the path forward from the origin.
- Distinguish primary failures from cascading consequences. Temporal correlation is not causation. A scheduled job or traffic shift can be the primary - it need not be a component fault.
- Two conditions are co-primary (`A + B`) only when both changed at incident time and removing either would have prevented the incident. A standing weakness that the trigger exposed (a design flaw, a missing breaker) is not co-primary: it belongs in Containment as what would have stopped propagation.
- Identify every shared resource on the propagation path, whether it amplified or absorbed the failure - these are the containment points. Quantify each on its Shared Resources line with the numbers the topology gives (pool sizes, connection ceilings), marked `(unverified)` when no metric confirms them in incident mode, or when neither the topology nor the code (its libraries' defaults included) states them in what-if mode.
- When components degrade together with no call-graph edge between them, suspect a hidden shared resource (database instance, connection pool, broker, executor, in-process lock, host) - the call graph understates coupling.
- Map both synchronous and asynchronous channels, and check for cycles.
- Components are named at the granularity the topology names them (services, pools, brokers), not files; when one component's endpoints fail differently, the component stays the name and the endpoint goes in the impact text.
- A branch or hop is included only when the record, the topology, or the code puts the failure on that path; a mechanism that is merely possible (a rate limiter that never engaged, a queue nothing in the timeline touched) is omitted. In incident mode, an included hop whose mechanism no evidence confirms is marked `(unverified)` - including one plausible but not the mechanism the record states, and one resting on a brief fact the repository contradicts; in what-if mode the marker follows the predicate under Output Format.

## Patterns

### Propagation Channels

| Channel                  | Mechanism                                                            |
| ------------------------ | -------------------------------------------------------------------- |
| Synchronous call         | HTTP/gRPC timeout or error cascading up the call chain               |
| Connection pool          | A per-process pool exhausts; every request in that process that needs a connection waits, whether or not it touches the slow dependency |
| Message queue            | Poison message, consumer lag, dead-letter overflow                   |
| Shared database          | Lock contention, connection-slot exhaustion across all clients' pools, slow query blocking |
| Cache                    | Stampede on expiry, eviction, or cold start; stale data driving logic errors |
| Circuit breaker          | Open circuit redirecting load to fallback or alternate paths         |
| Thread/worker pool       | Exhaustion blocking unrelated work on a shared executor              |
| Event bus                | Failed handler blocking downstream consumers                         |
| Scheduler                | A periodic run re-entering the failing path, or firing again while the previous run still holds its resources |
| Infrastructure feedback  | Health-check failure triggering container restarts or endpoint removal; the survivors absorb the load, and autoscaling keyed to request rate, latency, or queue depth adds instances whose fresh pools multiply pressure on the shared ceiling (CPU-keyed autoscaling does not fire while threads block on a slow dependency) |

### Sync/Async Boundaries

Failure mechanism changes when the path crosses a boundary:

- **Sync to async**: producer keeps working while the backlog grows on the broker; pressure reaches the producer only through a bounded channel (a full producer buffer, a broker memory alarm, a bounded in-process queue) - with an unbounded broker the only signal is consumer lag.
- **Async to sync**: consumers waiting on a slow sync downstream pile up, depleting the worker pool.

Trace the path explicitly across the boundary - the secondary blast radius often appears here.

### Amplification Loops

Propagation can be circular and prevent self-healing:

- Pool exhaustion -> liveness probe that needs a connection fails -> the kubelet kills and restarts the container in place (SIGTERM, then SIGKILL after the termination grace period), dropping every in-flight request still unfinished when the process exits - at SIGTERM when it has no drain handler, at the grace period otherwise (repeat restarts back off under CrashLoopBackOff) -> the fresh pool exhausts again on the same slow dependency -> the probe fails again
- Timeout -> client retries -> more load on failing service -> more timeouts
- Memory pressure -> GC pauses -> request timeouts -> retry storm -> more pressure

When a cycle exists, containment must break the loop (circuit breaker, retry budget, load shedding), not just mitigate a single link. A human or runbook action that made things worse (a manual scale-up that hit the connection ceiling) is a path step annotated `(response action)`; an automatic autoscaler scale-up is an Infrastructure feedback hop with no annotation; an action that helped belongs in Containment.

Bad - "errors seen in order-, cart-, checkout- and payment-service; all have issues": a list of failing services, with no origin, no mechanism per hop, and no shared resource.

Good - the Propagation Path, Shared Resources, and Containment sections in the Output Format's shape:

```
### Propagation Path

1. payment-gateway - p99 latency 30s, baseline 500ms
2. -> Synchronous call: order-service - threads blocked on the payment call
3. -> Connection pool: order-service HikariCP - handlers hold their JDBC connection across the payment call (open transaction), 40/40 checked out, requests wait
4a. -> Synchronous call: cart-service and checkout-service - connection timeouts from order-service, 503 to users
4b. -> Synchronous call: search-service - catalog refresh call times out, serves the cached catalog (degraded)
4c. -> Infrastructure feedback: order-service - liveness probe needs a connection, fails, the container restarts in place -> loops to step 3

### Shared Resources on Path

- order-service HikariCP (40 connections): one slow dependency consumed every connection, so requests with no payment dependency failed too
- order-service request thread pool (unverified): threads waiting on the payment call or a pooled connection filled the executor, so callers got connection timeouts and the liveness probe timed out

### Containment Assessment

Nothing stopped it; the loop at step 4c kept it going until the gateway recovered. A circuit breaker on the payment client (none configured) would have failed fast at step 2; a bulkhead pool for gateway calls would have kept step 3 from reaching cart and checkout; a liveness probe that needs neither a connection nor a request thread (a separate management port) would break the loop.
```

## Output Format

```
## Failure Propagation Analysis

**Mode:** {incident | what-if}

**Primary failure:** {component and failure type; `A + B` when two conditions are co-primary; suffixed (assumed) in what-if mode, (unverified) in incident mode when the record does not confirm the origin}

**Cascading components:** {each component with (failed), (failed: wrong output - <what it served>) when it kept answering with incorrect data, (failed: lost - <what was dropped>) when data was lost rather than delayed, or (degraded: <fallback or what still works>), prefixed `predicted` in what-if mode, suffixed (branch <N><letter> only) when it exists on only one outcome of a configuration-decided branch (fan-out branches, where both outcomes happen, take no suffix), or, in incident mode only, (exposed, not reported) when the topology puts it on the shared resource but the record does not name it - its path hop is marked (unverified); or "none - failure is contained"}

### Propagation Path

1. {origin} - {mechanism, e.g., "p99 latency 30s, baseline 500ms"}{ (unverified)}
2. -> {channel}: {affected component} - {impact}{ (unverified)}{ (response action)}
3a. -> {channel}: {component on one branch} - {impact}{ (unverified)}{ (response action)}
3b. -> {channel}: {component on the other branch} - {impact}{ (unverified)}{ (response action)}
N. -> {channel}: {component} - {impact}{ (unverified)}{ (response action)} -> loops to step {M}

### Shared Resources on Path

- {resource}{ (<size or ceiling>)}{ (unverified)}{ (suspected - <evidence>)}{ (branch <N><letter> only)}: {how it amplified or absorbed propagation; `consumers unenumerated` when the topology does not name who else uses it}

{or the single line `none on path - failure did not cross a shared resource`}

### Containment Assessment

{What stopped propagation, or what would have stopped it earlier; for a what-if, what would stop it. When a cycle was found, name the loop-breaker. When Primary is `A + B`, name the reversal for each condition and which to reverse first. When a branch depends on a configuration you cannot read, one line per branch naming the config that decides it.}
```

Always produce all sections; the loop step appears only when a cycle exists - a response action that re-triggers an earlier step once is a separate step, `-> loops to step M` only when it recurs. Number branch steps `<N>a`/`<N>b`/`<N>c`, N being the step after the fork, one letter per branch kept on that branch's later steps (`5a`, `6a`); a fork inside a branch continues the letter sequence at the step after it (a fork inside `3a` yields `4c`, `4d`); give a step every branch reaches the next whole number. Branch when the failure fans out, or when the evidence reaches a component whose unreadable configuration (a rate limiter's fail-open setting, a retry budget) decides which way it goes - each config-decided outcome stays on the path because the evidence reaches the deciding component, its hops carry `(unverified)`, and a single path would assert a fact you do not have. In what-if mode every hop is a prediction; mark `(unverified)` a hop whose mechanism neither the topology nor the code (its libraries' defaults included) states, or whose topology statement the code contradicts.

Components that absorbed the failure through a working fallback are listed and annotated `(degraded: <fallback>)` - containment is visible in the annotations, not in an empty list; a shared resource that absorbed load without failing appears under Shared Resources only. Reserve `none - failure is contained` for a failure no other component observed, or in what-if mode would observe, at all.

Shared Resources lists every shared resource on the path, amplifying or absorbing, its size or ceiling suffixed `(unverified)` when no metric confirms it in incident mode, or when neither the topology nor the code (its libraries' defaults included) states it in what-if mode, and suffixed `(branch <N><letter> only)` when it sits on one outcome of a configuration-decided branch; a resource the no-call-graph-edge rule makes you suspect but no record confirms carries `(suspected - <evidence>)`; a resource with no stated size whose role on the path no metric confirms takes `(unverified)` alone. Write `none on path - failure did not cross a shared resource` when there is genuinely none, since that absence is itself the finding: the failure had no amplification lever. A control that was never configured or never activated (a breaker that never opened) is not a shared resource; it is a missing containment lever and belongs in Containment.

## Avoid

- Listing affected components without tracing the mechanism between them
