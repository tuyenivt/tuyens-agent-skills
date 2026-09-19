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
- What-if analysis of a hypothetical failure ("what happens if X dies?") - trace forward from the assumed failure; phrase Containment as what would stop propagation. Mode is `what-if` when the failure is assumed and nothing has been observed; symptoms reported as having occurred, however the request is framed, are `incident`

## Rules

- Investigate backward from the earliest observable symptom to the origin; present the path forward from the origin.
- Distinguish primary failures from cascading consequences. Temporal correlation is not causation. A scheduled job or traffic shift can be the primary - it need not be a component fault.
- Two conditions are co-primary (`A + B`) only when both changed at incident time and removing either would have prevented the incident. A standing weakness that the trigger exposed (a design flaw, a missing breaker) is not co-primary: it belongs in Containment as what would have stopped propagation.
- Identify every shared resource on the propagation path, whether it amplified or absorbed the failure - these are the containment points. Quantify one with the numbers the topology gives (pool sizes, connection ceilings), marked `(unverified)` when no metric confirms them.
- When components degrade together with no call-graph edge between them, suspect a hidden shared resource (database instance, connection pool, broker, executor, host) - the call graph understates coupling.
- Map both synchronous and asynchronous channels, and check for cycles.
- Mark hops you cannot verify `(unverified)` rather than guessing or omitting them - including a hop whose mechanism is plausible but not the one the incident record states, and any hop resting on a brief fact the repository contradicts.
- Components are named at the granularity the topology names them (services, pools, brokers), not files; when one component's endpoints fail differently, the component stays the name and the endpoint goes in the impact text.
- A branch or hop is included only when the record, the topology, or the code puts the failure on that path; a mechanism that is merely possible (a rate limiter that never engaged, a queue nothing in the timeline touched) is omitted, not marked `(unverified)`.

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
| Infrastructure feedback  | Health-check failure triggering container restarts or endpoint removal; the survivors absorb the load, and autoscaling keyed to request rate, latency, or queue depth adds instances whose fresh pools multiply pressure on the shared ceiling (CPU-keyed autoscaling does not fire while threads block on a slow dependency) |

### Sync/Async Boundaries

Failure mechanism changes when the path crosses a boundary:

- **Sync to async**: producer keeps working while the backlog grows on the broker; pressure reaches the producer only through a bounded channel (a full producer buffer, a broker memory alarm, a bounded in-process queue) - with an unbounded broker the only signal is consumer lag.
- **Async to sync**: consumers waiting on a slow sync downstream pile up, depleting the worker pool.

Trace the path explicitly across the boundary - the secondary blast radius often appears here.

### Amplification Loops

Propagation can be circular and prevent self-healing:

- Pool exhaustion -> liveness probe that opens a connection fails -> the container restarts in place -> its fresh pool refills against the same database ceiling -> faster exhaustion
- Timeout -> client retries -> more load on failing service -> more timeouts
- Memory pressure -> GC pauses -> request timeouts -> retry storm -> more pressure

When a cycle exists, containment must break the loop (circuit breaker, retry budget, load shedding), not just mitigate a single link. A response action that made things worse (a scale-up that hit the connection ceiling) is a path step annotated `(response action)`.

### Good

```
## Failure Propagation Analysis

**Mode:** incident

**Primary failure:** payment-gateway latency spike (p99 30s, baseline 500ms)

**Cascading components:** order-service (failed), cart-service (failed), checkout-service (failed), search-service (degraded: cached catalog)

### Propagation Path

1. payment-gateway - timeout 30s, baseline 500ms
2. -> Synchronous call: order-service - threads blocked on the payment call
3. -> Connection pool: order-service HikariCP - handlers hold their JDBC connection across the payment call (open transaction), 40/40 checked out, requests wait
4a. -> Synchronous call: cart-service and checkout-service - connection timeouts from order-service, 503 to users
4b. -> Cache: search-service - catalog refresh times out, serves stale (degraded)
5. -> Infrastructure feedback: order-service - liveness probe opens a connection, fails, the container restarts -> loops to step 3

### Shared Resources on Path

- order-service HikariCP: one slow dependency consumed every connection, so requests with no payment dependency failed too
- search-service catalog cache: absorbed the failure - served stale rather than failing

### Containment Assessment

Nothing stopped it; the loop at step 5 kept it going until the gateway recovered. A circuit breaker on the payment client (none configured) would have failed fast at step 2; a bulkhead pool for gateway calls would have kept step 3 from reaching cart and checkout; a liveness probe that does not open a connection would break the loop.
```

### Bad

```
Errors seen in: order-service, cart-service, checkout-service, payment-service.
All services have issues.
```

## Output Format

```
## Failure Propagation Analysis

**Mode:** {incident | what-if}

**Primary failure:** {component and failure type; `A + B` when two conditions are co-primary; suffixed (assumed) in what-if mode}

**Cascading components:** {each component with (failed) or (degraded: <fallback or what still works>), prefixed `predicted` in what-if mode, suffixed (branch Nb only) when it exists on one branch, or (exposed, not reported) when the topology puts it on the shared resource but the record does not name it; or "none - failure is contained"}

### Propagation Path

1. {origin} - {mechanism, e.g., "timeout 30s, baseline 500ms"}
2. -> {channel}: {affected component} - {impact}{ (unverified)}{ (response action)}
3a. -> {channel}: {component on one branch} - {impact}
3b. -> {channel}: {component on the other branch} - {impact}
N. -> {channel}: {component} - {impact} -> loops to step {M}

### Shared Resources on Path

- {resource}{ (suspected - <evidence>)}{ (branch Nb only)}: {how it amplified or absorbed propagation}

{or the single line `none on path - failure did not cross a shared resource`}

### Containment Assessment

{What stopped propagation, or what would have stopped it earlier; for a what-if, what would stop it. When a cycle was found, name the loop-breaker. When Primary is `A + B`, name which condition is the actionable one. When a branch depends on a configuration you cannot read, one line per branch naming the config that decides it.}
```

Always produce all sections; the loop step appears only when a cycle exists. Branch steps as `2a`/`2b` when the failure fans out or when an unreadable configuration (a rate limiter's fail-open setting, a retry budget) decides which way it goes - both outcomes are real, and a single path would assert a fact you do not have. In what-if mode every hop is a prediction; mark only hops with no evidence at all `(unverified)`.

Components that absorbed the failure through a working fallback are listed and annotated `(degraded: <fallback>)` - containment is visible in the annotations, not in an empty list. Reserve `none - failure is contained` for a failure no other component observed, or in what-if mode would observe, at all.

Shared Resources lists every shared resource on the path, amplifying or absorbing; a resource the no-call-graph-edge rule makes you suspect but no record confirms carries `(suspected - <evidence>)`. Write `none on path - failure did not cross a shared resource` when there is genuinely none, since that absence is itself the finding: the failure had no amplification lever. A control that was never configured or never activated (a breaker that never opened) is not a shared resource; it is a missing containment lever and belongs in Containment.

## Avoid

- Listing affected components without tracing the mechanism between them
- Treating temporal correlation as causation
- Ignoring asynchronous propagation (events, queues, back-pressure)
- Treating every error as a primary failure rather than a consequence
