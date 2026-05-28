---
name: architecture-capacity
description: Throughput estimation, scaling analysis, and bottleneck prediction
metadata:
  category: performance
  tags: [capacity, scaling, throughput, bottleneck, performance]
user-invocable: false
---

# Capacity Modeling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Estimating resource requirements during architecture design
- Predicting which component saturates first under load
- Choosing between horizontal, vertical, and partitioning strategies
- Justifying infrastructure cost or capacity decisions

## Rules

- State traffic assumptions explicitly (steady-state and peak); estimates without assumptions are unverifiable
- Identify the bottleneck (lowest saturation point) - it sets system capacity
- Plan headroom at 2-3x peak; sizing for current peak leaves no margin for growth or burst
- External rate limits (payment gateways, SaaS APIs) are hard ceilings - no internal scaling lifts them
- Throughput and latency are independent; a system can be high-throughput and high-latency simultaneously

## Pattern

### Scaling Models

| Model                   | Use When                                 | Limitation                        |
| ----------------------- | ---------------------------------------- | --------------------------------- |
| Horizontal (instances)  | Stateless services, read-heavy workloads | Shared state becomes bottleneck   |
| Vertical (bigger box)   | DB, single-writer, license-limited       | Hard ceiling, expensive           |
| Partitioning (sharding) | Write-heavy, data-parallel workloads     | Cross-partition queries expensive |
| Caching                 | Read-heavy, staleness acceptable         | Invalidation complexity           |
| Async offload           | Work can be deferred                     | Eventual consistency              |

### Saturation Math

- **Pool throughput**: `pool_size / avg_query_duration`. Saturated pools queue or reject - increase pool size (up to DB max), reduce query time, offload reads, or add a connection pooler (PgBouncer, ProxySQL, equivalent for the stack).
- **Async backlog**: `(producer_rate - consumer_rate) x burst_duration` = peak backlog. Recovery time: `backlog / (consumer_rate - steady_producer_rate)`. If recovery exceeds the interval between peaks, consumers cannot keep up.

### Anti-pattern

> "The system should scale to handle high traffic. We can add more instances if needed."

No bottleneck named, no saturation point, no scaling model. Unverifiable.

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

{Primary recommendation - horizontal / vertical / sharding / async offload - with rationale citing the bottleneck}

### Queue Depth (async workloads only)

- Producer rate (peak): {N/s}
- Consumer rate: {N/s/consumer} x {consumers} = {total/s}
- Peak backlog: ({peak} - {total}) x {burst seconds} = {N messages}
- Recovery time: {backlog} / ({total} - {steady producer}) = {duration}
- Max queue depth before back-pressure: {N messages}

### Assumptions

- {stated assumption 1}
- {stated assumption 2}
```

Omit "Queue Depth" for synchronous workloads.

## Avoid

- Estimates without stated assumptions
- "Just add more instances" without naming the bottleneck
- Sizing for current peak with no headroom for burst or growth
