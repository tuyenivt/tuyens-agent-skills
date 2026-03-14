---
name: failure-propagation-analysis
description: Trace failure propagation paths across service and system boundaries
metadata:
  category: ops
  tags: [incident, failure-propagation, cascading, dependencies]
user-invocable: false
---

# Failure Propagation Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- When a failure in one component causes degradation in others
- When the blast radius is moderate or wider
- When multiple services report errors simultaneously
- When determining whether a failure is primary or a downstream consequence

## Rules

- Trace from the earliest observable symptom backward to the origin
- Distinguish primary failures from cascading consequences
- Identify every shared resource on the propagation path
- Map both synchronous and asynchronous propagation channels

## Pattern

### Propagation Channels

Failures propagate through:

| Channel                    | Mechanism                                                    |
| -------------------------- | ------------------------------------------------------------ |
| Synchronous call           | HTTP/gRPC timeout or error cascading up the call chain       |
| Connection pool            | Exhaustion in one consumer starves others sharing the pool   |
| Message queue              | Poison message, consumer lag, dead letter overflow           |
| Shared database            | Lock contention, connection exhaustion, slow query blocking  |
| Cache                      | Stampede on eviction, stale data causing logic errors        |
| Circuit breaker            | Open circuit redirecting load to fallback or alternate paths |
| Thread/virtual thread pool | Exhaustion blocking unrelated work on shared executor        |
| Event bus                  | Failed event handler blocking downstream consumers           |

### Sync/Async Boundary Transitions

When a propagation path crosses a sync/async boundary, the failure mechanism changes:

- **Sync -> async**: The producing service continues operating; failure manifests as queue backlog accumulation. The consumer's backlog eventually causes memory pressure or back-pressure on the producer's send buffer.
- **Async -> sync**: Consumers may block waiting for a response from a downstream sync service. If the downstream is slow, consumers accumulate, depleting the worker pool.
- **Queue backlog as secondary blast radius**: A down consumer (Service C) does not immediately affect the producer (Service B), but if the queue is unbounded, Service B's memory or send buffer will eventually exhaust - trace this path explicitly.

Example mixed-boundary trace:
```
1. Service C (consumer) is down
2. -> Message queue: backlog grows (messages accumulate, no consumer)
3. -> Queue send buffer: Service B cannot enqueue new messages (back-pressure)
4. -> Service B: request handlers block waiting to enqueue, thread pool exhausted
5. -> HTTP call: Service A gets 503s from Service B
```

### Propagation Map

Trace the failure path as a directed chain:

```
[Origin] -> [Channel] -> [Affected Component] -> [Channel] -> [Further Impact]
```

### Good: Specific propagation trace

```
Propagation Path:
1. payment-gateway timeout (30s, baseline 500ms)
2. -> HTTP call: order-service blocked waiting for payment response
3. -> Connection pool: order-service HikariCP exhausted (40/40 active)
4. -> Synchronous callers: cart-service and checkout-service getting connection timeout
5. -> User impact: all checkout flows returning 503

Shared Resources Affected: HikariCP pool (order-service), payment-gateway circuit breaker (stayed closed)
Primary Failure: payment-gateway latency spike
Cascading: order-service, cart-service, checkout-service
```

### Bad: Listing failures without tracing connections

```
Errors seen in: order-service, cart-service, checkout-service, payment-service.
All services have issues.
```

## Output Format

Consuming workflow skills depend on this structure to understand failure origin and cascading scope. The propagation path is the primary output callers use for containment decisions.

```
## Failure Propagation Analysis

**Primary failure:** {component and failure type}
**Cascading components:** {list, or "none - failure is contained"}

### Propagation Path

{numbered chain from origin to observed impact}
1. {origin component} - {failure mechanism, e.g., "timeout 30s, baseline 500ms"}
2. -> {channel}: {affected component} - {how it was impacted}
3. -> {channel}: {further component} - {user-visible impact}

### Shared Resources on Path

- {resource name}: {how it amplified the propagation}

### Containment Assessment

{What stopped the propagation or what would have stopped it earlier}
```

Always produce all sections. Use "none" for Cascading components only when the failure is demonstrably contained. Never skip Shared Resources - shared resources are often the key to containment recommendations.

## Avoid

- Listing affected components without tracing the propagation mechanism
- Assuming temporal correlation equals causal relationship
- Ignoring asynchronous propagation paths (events, queues)
- Treating every error as a primary failure rather than a consequence
