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

- State traffic assumptions explicitly (steady-state and peak). When no numbers exist, derive them from business facts (seats x active share x actions per active user-hour, plus a burst factor; defaults when no data: B2B 10-20% of seats active per hour; 2-5 actions per active user-hour, counting actions on the flow being modelled rather than all site activity - where the flow has a stated volume (orders or returns per month) derive from that volume and its stated concentration instead; burst 2-4x for working-hours B2B, 5-10x for consumer or event-driven traffic - name each pick). Convert actions to load via two fan-out factors - HTTP calls per action (sets RPS) and queries per action (divided by HTTP calls per action, sets each datastore row's per-request cost) - measure them, or state them as assumptions; a stated concentration ("most returns land Monday 9-11") is data and replaces the burst default; attach a validation action to every derived number. When infra specs are missing, state a baseline configuration as an assumption and validate it the same way
- Identify the bottleneck (lowest usable capacity, after the derate below) - it sets system capacity. If it saturates below current (or projected, when pre-launch) steady traffic, lead with that: the system is already over capacity
- Usable capacity is ~75% of theoretical saturation; queueing effects dominate above that. The derate applies to components you operate; contractual external ceilings are consumed at face value
- Plan headroom at 2-3x peak: 2x minimum, 3x when growth is expected - name the multiplier used. A stated growth figure is modelled as its own load case, not folded into the multiplier. For queue-absorbed workloads, apply the multiplier to long-run average demand, not the instantaneous burst peak
- External rate limits (payment gateways, SaaS APIs) are hard ceilings - no internal scaling lifts them. If a ceiling sits below the headroom target, the recommendation is demand shaping (queue, cache, dedupe, negotiate the limit), not more instances
- Throughput and latency are distinct measures: a system can be high-throughput and high-latency at once, and latency climbs with utilization well before throughput caps

## Pattern

### Scaling Models

| Model                   | Use When                                 | Limitation                        |
| ----------------------- | ---------------------------------------- | --------------------------------- |
| Horizontal (instances)  | Stateless services, read-heavy workloads | Shared state becomes bottleneck   |
| Vertical (bigger box)   | DB, single-writer, license-limited       | Hard ceiling, expensive           |
| Partitioning (sharding) | Write-heavy, data-parallel workloads     | Cross-partition queries expensive |
| Caching                 | Read-heavy, staleness acceptable         | Invalidation complexity           |
| Async offload           | Work can be deferred                     | Eventual consistency              |
| Demand shaping          | An external ceiling binds below target   | Cuts or defers demand instead of raising capacity |

### Saturation Math

- **Pool throughput**: `pool_size / avg_query_duration`, with the duration in seconds, gives queries per second - where a connection is held across downstream calls (a transaction wrapping an HTTP call, open-in-view), the duration is the hold time, not the query time; - a 20-connection pool at 8ms gives 20 / 0.008 = 2,500 queries/s; divide by queries per request to land in RPS (625 RPS at 4 queries per request). Apply at every constraining level - the per-instance pool AND the server's global limit each get a component row. Check aggregate config: `pool_size x max_instances` must stay under the server limit (e.g., HikariCP 50 x 12 pods vs max_connections=200) - horizontal scaling multiplies client demand. Saturated pools queue or reject - increase pool size (up to the server max), reduce query time, offload reads, or add a connection pooler (PgBouncer, ProxySQL, equivalent for the stack).
- **Async backlog**: effective consumer rate = `min(worker throughput x 0.75, downstream limit on the consumption path)`, where the downstream limit takes the 0.75 derate too when you operate that downstream, and face value when it is a contractual external ceiling. Peak backlog: `max(0, producer_rate - effective_consumer_rate) x burst_duration`. Recovery time: `backlog / (effective_consumer_rate - steady_producer_rate)`; if steady production >= effective consumption, recovery is never - report the divergence rate instead. Consumers cannot keep up if recovery (measured from burst end) exceeds the time to the next burst (start-to-start interval minus burst duration), or if long-run production per interval exceeds long-run consumption.

### Anti-pattern

> "The system should scale to handle high traffic. We can add more instances if needed."

No bottleneck named, no saturation point, no scaling model. Unverifiable.

## Output Format

Consuming workflow skills depend on this structure. Produce every field. `Queue Depth` is the only section with an omit rule, stated below it. Assess one case per block - when current and proposed configurations, or current and projected load, are both in scope, emit the whole block once per case under a `## Capacity Model - {configuration or load case}` heading.

```
## Capacity Model

**Verdict:** {Within capacity and headroom met | Within capacity, headroom short | Over capacity at current steady load | Over capacity at current peak | Over capacity at projected steady load | Over capacity at projected peak} - {the bottleneck and the number that decides it}

**Traffic profile:** {steady-state RPS} steady / {peak RPS} peak ({burst factor}x), system-wide - sub-flows enter as per-request cost; "n/a - async flow only, see Queue Depth" when no synchronous flow is in scope {- mark derived numbers "(derived)"; name which peak when measured and scenario peaks differ; for queue-absorbed workloads add: / {long-run average demand} long-run avg. A system with both a synchronous and an async flow reports the synchronous flow here and the async one in Queue Depth}

**Stated vs derived:** {"consistent" | "n/a - every figure stated, none derived" | the source's own figure, this model's figure, and which one the model uses}

**Bottleneck component:** {name} - saturates at {N system RPS, as in its table row, or "0 above current load" for a configuration collision}; usable {0.75 x N for a component you operate | N at face value for a contractual external ceiling | 0}

**Next bottleneck once mitigated:** {name, next-lowest usable} - saturates at {N system RPS}; "n/a - nothing to mitigate" when the verdict is Within capacity and headroom met

**Headroom target:** {2 or 3}x {peak | long-run average demand, for queue-absorbed workloads} = {N} RPS vs usable capacity {N} RPS

### Component Saturation Points

| Component | Limit (native unit) | Per-Request Cost (native unit) | Saturates At        | Bottleneck? |
| --------- | ------------------- | ------------------------------ | ------------------- | ----------- |
| {name}    | {limit}             | {cost/request}                 | {N RPS, or "0 above current load", or N/A (not limiting)} | Yes / No / Also below demand |

State limits and costs in each component's native unit (ms, connections, ops, external calls); convert durations to seconds before dividing. Every constrained component shows its computed saturation; N/A is only for effectively unlimited components. A component already over its limit at current load through configuration alone - an aggregate pool exceeding the server maximum - saturates at "0 above current load" rather than an RPS figure, and names the collision. Model autoscaled fleets at max scale-out, with scale-up lag as an assumption. Express a ceiling that binds only a sub-flow (e.g., gateway TPS on the checkout fraction of traffic) as a fractional per-request cost, so its saturation lands in system RPS. When one shared component serves flows with different costs, state the traffic-weighted cost and show the mix it came from.

### Scaling Recommendation

{Primary recommendation - horizontal / vertical / sharding / caching / async offload / demand shaping / no change required - with rationale citing the bottleneck, and the next bottleneck it exposes. Demand shaping is the recommendation whenever an external ceiling sits below the headroom target, since no internal scaling lifts it}

### Queue Depth (any queue- or batch-fed component, existing or proposed)

- Producer rate (peak): {N/s}
- Effective consumer rate: min({N/s/consumer} x {consumers} x 0.75, {downstream limit} x {0.75 when you operate it | 1 for a contractual ceiling}) = {total/s}
- Peak backlog: max(0, {peak} - {total}) x {burst seconds} = {N messages}
- Recovery time: {backlog} / ({total} - {steady producer}) = {duration} vs {time to next burst = start-to-start interval minus burst duration}; when steady production meets or exceeds effective consumption, write "never - backlog diverges at {N}/s"
- Max queue depth before back-pressure: {configured limit, or "unbounded - recommend ~2x expected peak backlog"}

### Assumptions

- {assumption} - validate by: {measurement or source}
```

Omit "Queue Depth" only when the flow that block assesses is synchronous end to end. With one block per configuration, that test runs per block, so a synchronous current configuration omits it while a proposed queue-absorbed one carries it.

## Avoid

- Estimates without stated assumptions
- "Just add more instances" without naming the bottleneck
- Sizing for current peak with no headroom for burst or growth
- Sizing to raw saturation - usable capacity is ~75% of it
