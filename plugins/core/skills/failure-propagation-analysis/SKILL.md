---
name: failure-propagation-analysis
description: Trace cascading failures across services: identify primary failure, propagation channels, shared resources, amplification loops.
metadata:
  category: ops
  tags: [incident, failure-propagation, cascading, dependencies]
user-invocable: false
---

# Failure Propagation Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Failure in one component is degrading others
- Multiple services report errors simultaneously and the origin is unclear
- Distinguishing a primary failure from downstream consequences
- Blast radius is moderate or wider during an incident

## Rules

- Trace from the earliest observable symptom backward to the origin.
- Distinguish primary failures from cascading consequences. Temporal correlation is not causation.
- Identify every shared resource on the propagation path - these are the containment points.
- Map both synchronous and asynchronous channels, and check for cycles.

## Patterns

### Propagation Channels

| Channel                  | Mechanism                                                            |
| ------------------------ | -------------------------------------------------------------------- |
| Synchronous call         | HTTP/gRPC timeout or error cascading up the call chain               |
| Connection pool          | Exhaustion in one consumer starves others sharing the pool           |
| Message queue            | Poison message, consumer lag, dead-letter overflow                   |
| Shared database          | Lock contention, connection exhaustion, slow query blocking          |
| Cache                    | Stampede on eviction, stale data driving logic errors                |
| Circuit breaker          | Open circuit redirecting load to fallback or alternate paths         |
| Thread/worker pool       | Exhaustion blocking unrelated work on a shared executor              |
| Event bus                | Failed handler blocking downstream consumers                         |
| Infrastructure feedback  | Health-check failure triggering restart/scaling that amplifies cause |

### Sync/Async Boundaries

Failure mechanism changes when the path crosses a boundary:

- **Sync to async**: producer keeps working; consumer queue grows until back-pressure or memory pressure surfaces at the producer.
- **Async to sync**: consumers waiting on a slow sync downstream pile up, depleting the worker pool.

Trace the path explicitly across the boundary - the secondary blast radius often appears here.

### Amplification Loops

Propagation can be circular and prevent self-healing:

- Pool exhaustion -> health-check fail -> autoscale -> more instances contending for same pool -> faster exhaustion
- Timeout -> client retries -> more load on failing service -> more timeouts
- Memory pressure -> GC pauses -> request timeouts -> retry storm -> more pressure

When a cycle exists, containment must break the loop (circuit breaker, retry budget, load shedding), not just mitigate a single link.

### Good

```
1. payment-gateway timeout (30s, baseline 500ms)
2. -> HTTP: order-service blocked on payment call
3. -> Connection pool: order-service HikariCP exhausted (40/40)
4. -> HTTP: cart-service and checkout-service hitting connection timeouts
5. -> User: all checkout flows returning 503

Shared resources: order-service HikariCP, payment-gateway circuit breaker (stayed closed)
Primary: payment-gateway latency spike
Cascading: order-service, cart-service, checkout-service
```

### Bad

```
Errors seen in: order-service, cart-service, checkout-service, payment-service.
All services have issues.
```

## Output Format

```
## Failure Propagation Analysis

**Primary failure:** {component and failure type}
**Cascading components:** {list, or "none - failure is contained"}

### Propagation Path

1. {origin} - {mechanism, e.g., "timeout 30s, baseline 500ms"}
2. -> {channel}: {affected component} - {impact}
3. -> {channel}: {further component} - {user-visible impact}

### Shared Resources on Path

- {resource}: {how it amplified propagation}

### Containment Assessment

{What stopped propagation, or what would have stopped it earlier. Name the loop-breaker if a cycle was found.}
```

Always produce all sections. Use "none" for Cascading only when the failure is demonstrably contained. Never skip Shared Resources - they are the containment levers.

## Avoid

- Listing affected components without tracing the mechanism between them
- Treating temporal correlation as causation
- Ignoring asynchronous propagation (events, queues, back-pressure)
- Treating every error as a primary failure rather than a consequence
