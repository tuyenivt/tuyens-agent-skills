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

### Queue Depth Estimation

For async workloads, estimate whether consumers can keep up with producers during sustained peaks:

```
Producer rate (peak): 2000 msg/s for 60s burst
Consumer rate: 500 msg/s per consumer x 3 consumers = 1500 msg/s
Deficit during peak: 2000 - 1500 = 500 msg/s
Backlog after 60s peak: 500 x 60 = 30,000 messages
Recovery time: 30,000 / (1500 - 500) = 30 seconds (assuming producer drops to 500 msg/s steady)
```

If the backlog exceeds the queue's memory/disk limit, the producer blocks or drops messages. Size the queue to hold at least one full peak burst. If recovery time exceeds the interval between peaks, the system cannot keep up and requires more consumers or producer-side throttling.

### Cost Awareness

For each scaling decision, note:

- Resource type and unit cost (compute, storage, network)
- Cost growth model (linear, super-linear, step function)
- Cost optimization opportunity (reserved instances, spot, right-sizing)

## Output Format

Consuming workflow skills depend on this structure. Always produce all fields.

```
## Capacity Model

**Traffic profile:** {steady-state RPS} steady / {peak RPS} peak ({burst factor}x)
**Bottleneck component:** {name} - saturates at {N} RPS/TPS
**Headroom target:** {2-3x peak = N RPS; current capacity = N RPS}

### Component Saturation Points

| Component | Capacity | Per-Request Cost | Saturates At | Bottleneck? |
| --------- | -------- | ---------------- | ------------ | ----------- |
| {name}    | {limit}  | {cost/request}   | {N RPS}      | Yes / No    |

### Scaling Recommendation

{Primary recommendation with rationale - horizontal / vertical / sharding / async offload}

### Queue Depth (if async workload)

- Producer rate: {N/s}
- Consumer rate: {N/s per consumer} x {consumer count} = {total consumer rate/s}
- Steady-state queue depth: 0 (if consumer rate > producer rate)
- Peak backlog accumulation: ({peak producer rate} - {total consumer rate}) x {peak duration seconds} = {N messages}
- Time to clear backlog after peak: {backlog} / ({total consumer rate} - {steady producer rate}) = {duration}
- Max queue depth before back-pressure: {N messages}

### Assumptions

- {stated assumption 1}
- {stated assumption 2}
```

Omit "Queue Depth" for synchronous workloads. Always state assumptions explicitly so the model can be updated when traffic patterns change.

## Avoid

- Capacity estimates without stated assumptions
- Ignoring the bottleneck ("just add more instances")
- Planning for exactly current peak with no headroom
- Conflating throughput with latency (high throughput does not mean low latency)
- Ignoring burst patterns that exceed steady-state by 5-10x
