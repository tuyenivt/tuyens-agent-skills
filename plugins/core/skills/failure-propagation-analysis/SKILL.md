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

## Avoid

- Listing affected components without tracing the propagation mechanism
- Assuming temporal correlation equals causal relationship
- Ignoring asynchronous propagation paths (events, queues)
- Treating every error as a primary failure rather than a consequence
