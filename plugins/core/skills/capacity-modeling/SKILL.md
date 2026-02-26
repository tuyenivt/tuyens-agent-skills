---
name: capacity-modeling
description: Throughput estimation, scaling analysis, and bottleneck prediction
metadata:
  category: performance
  tags: [capacity, scaling, throughput, bottleneck, performance]
user-invocable: false
---

# Capacity Modeling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During architecture design to estimate resource requirements
- When predicting which component saturates first under load
- When choosing between horizontal and vertical scaling strategies
- When justifying infrastructure cost or capacity decisions

## Rules

- Base estimates on stated traffic assumptions, not guesses
- Identify the bottleneck -- the component that saturates first determines system capacity
- State assumptions explicitly so estimates can be updated when assumptions change
- Distinguish steady-state load from burst load
- Account for headroom -- plan for 2-3x current peak, not exactly current peak

## Pattern

### Capacity Estimation Steps

1. **Traffic profile** -- requests per second (RPS) at steady state and peak
2. **Per-request cost** -- CPU time, memory, DB queries, network calls per request type
3. **Resource budget** -- available CPU, memory, connections, throughput per component
4. **Saturation point** -- at what RPS does each component hit its limit
5. **Bottleneck** -- the component with the lowest saturation point
6. **Scaling strategy** -- how to increase the bottleneck's capacity

### Good: Specific estimation with bottleneck identification

```
Traffic: 500 RPS steady, 2000 RPS peak (flash sale)
Order creation path:
  - API gateway: 10000 RPS capacity -> not bottleneck
  - OrderService: 1 DB write + 1 event publish per request, ~50ms each -> 800 RPS per instance
  - PostgreSQL: 40 connection pool, ~50ms per write -> 800 writes/sec -> saturates at 800 RPS
  - Kafka: 50000 messages/sec -> not bottleneck
Bottleneck: PostgreSQL write throughput at 800 RPS
Scaling: Read replicas do not help (write-heavy). Options: connection pool tuning, write batching, or DB sharding
Headroom: 2x peak = 4000 RPS; need 5 OrderService instances + DB write optimization
```

### Bad: Vague capacity statement

```
The system should scale to handle high traffic. We can add more instances if needed.
```

### Scaling Models

| Model                   | Use When                                 | Limitation                        |
| ----------------------- | ---------------------------------------- | --------------------------------- |
| Horizontal (instances)  | Stateless services, read-heavy workloads | Shared state becomes bottleneck   |
| Vertical (bigger box)   | DB, single-writer, license-limited       | Hard ceiling, expensive           |
| Partitioning (sharding) | Write-heavy, data-parallel workloads     | Cross-partition queries expensive |
| Caching                 | Read-heavy, staleness acceptable         | Invalidation complexity           |
| Async offload           | Work can be deferred                     | Eventual consistency              |

### Cost Awareness

For each scaling decision, note:

- Resource type and unit cost (compute, storage, network)
- Cost growth model (linear, super-linear, step function)
- Cost optimization opportunity (reserved instances, spot, right-sizing)

## Avoid

- Capacity estimates without stated assumptions
- Ignoring the bottleneck ("just add more instances")
- Planning for exactly current peak with no headroom
- Conflating throughput with latency (high throughput does not mean low latency)
- Ignoring burst patterns that exceed steady-state by 5-10x
