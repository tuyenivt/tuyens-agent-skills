---
name: architecture-capacity
description: Throughput estimation, scaling analysis, and bottleneck prediction
metadata:
  category: performance
  tags: [capacity, scaling, throughput, bottleneck, performance]
user-invocable: false
---

# Capacity Modeling

> Load `Use skill: stack-detect` first to determine the project stack. The math is stack-agnostic; stack only changes which named tools apply.

## When to Use

- Estimating resource requirements during architecture design
- Predicting which component saturates first under load
- Choosing between horizontal, vertical, and partitioning strategies
- Justifying infrastructure cost or capacity decisions

## Rules

- State traffic assumptions explicitly (steady-state and peak). When no numbers exist, derive them from business facts (seats x active share x actions per active user-hour, plus a burst factor; e.g., B2B: 10-20% of seats active per hour) and attach a validation action to every derived number. When infra specs are missing, state a baseline configuration as an assumption and validate it the same way
- Identify the bottleneck (lowest saturation point) - it sets system capacity. If it saturates below current (or projected, when pre-launch) steady traffic, lead with that: the system is already over capacity
- Usable capacity is ~75% of theoretical saturation; queueing effects dominate above that
- Plan headroom at 2-3x peak: 2x minimum, 3x when growth is expected - name the multiplier used. For queue-absorbed workloads, apply the multiplier to long-run average demand, not the instantaneous burst peak
- External rate limits (payment gateways, SaaS APIs) are hard ceilings - no internal scaling lifts them. If a ceiling sits below the headroom target, the recommendation is demand shaping (queue, cache, dedupe, negotiate the limit), not more instances
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

- **Pool throughput**: `pool_size / avg_query_duration`. Apply at every constraining level - the per-instance pool AND the server's global limit each get a component row. Check aggregate config: `pool_size x max_instances` must stay under the server limit (e.g., HikariCP 50 x 12 pods vs max_connections=200) - horizontal scaling multiplies client demand. Saturated pools queue or reject - increase pool size (up to the server max), reduce query time, offload reads, or add a connection pooler (PgBouncer, ProxySQL, equivalent for the stack).
- **Async backlog**: effective consumer rate = `min(worker throughput, rate limits of downstream dependencies on the consumption path)`, derated to ~75% usable. Peak backlog: `(producer_rate - effective_consumer_rate) x burst_duration`. Recovery time: `backlog / (effective_consumer_rate - steady_producer_rate)`; if steady production >= effective consumption, recovery is never - report the divergence rate instead. Consumers cannot keep up if recovery (measured from burst end) exceeds the time to the next burst (start-to-start interval minus burst duration), or if long-run production per interval exceeds long-run consumption.

### Anti-pattern

> "The system should scale to handle high traffic. We can add more instances if needed."

No bottleneck named, no saturation point, no scaling model. Unverifiable.

## Output Format

Consuming workflow skills depend on this structure. Always produce all fields.

```
## Capacity Model

**Traffic profile:** {steady-state RPS} steady / {peak RPS} peak ({burst factor}x) {- mark derived numbers "(derived)"}
**Bottleneck component:** {name} - saturates at {N} RPS/TPS; usable ~{0.75 x N}
**Next bottleneck once mitigated:** {name} - saturates at {N}
**Headroom target:** {2 or 3}x peak = {N} RPS vs usable capacity {N} RPS

### Component Saturation Points

| Component | Limit (native unit) | Per-Request Cost (native unit) | Saturates At        | Bottleneck? |
| --------- | ------------------- | ------------------------------ | ------------------- | ----------- |
| {name}    | {limit}             | {cost/request}                 | {N RPS, or N/A (not limiting)} | Yes / No |

State limits and costs in each component's native unit (ms, connections, ops, external calls). Every constrained component shows its computed saturation; N/A is only for effectively unlimited components.

### Scaling Recommendation

{Primary recommendation - horizontal / vertical / sharding / caching / async offload - with rationale citing the bottleneck, and the next bottleneck it exposes}

### Queue Depth (any queue- or batch-fed component, existing or proposed)

- Producer rate (peak): {N/s}
- Effective consumer rate: min({N/s/consumer} x {consumers}, {downstream limit}) = {total/s}
- Peak backlog: ({peak} - {total}) x {burst seconds} = {N messages}
- Recovery time: {backlog} / ({total} - {steady producer}) = {duration} vs {burst interval, start-to-start}
- Max queue depth before back-pressure: {configured limit, or "unbounded - recommend ~2x expected peak backlog"}

Repeat the block for the recommended configuration when the recommendation changes consumer capacity.

### Assumptions

- {assumption} - validate by: {measurement or source}
```

Omit "Queue Depth" only when the entire flow is synchronous.

## Avoid

- Estimates without stated assumptions
- "Just add more instances" without naming the bottleneck
- Sizing for current peak with no headroom for burst or growth
- Sizing to raw saturation - usable capacity is ~75% of it
