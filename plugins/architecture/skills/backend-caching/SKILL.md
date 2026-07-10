---
name: backend-caching
description: Caching patterns, response optimization, and serialization efficiency. Auto-detects project stack and adapts guidance to the detected ecosystem.
metadata:
  category: ops
  tags: [caching, performance, redis, payload, serialization, multi-stack]
user-invocable: false
---

# Caching

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Read-heavy endpoints with infrequently changing data
- Expensive computations or slow external service calls
- Reducing database load for frequently accessed queries
- Improving response latency for hot paths

## Rules

- Cache reads only; the cache must reflect the source of truth, never override it
- Every cache entry has a TTL and a defined invalidation strategy. Indefinite TTL is legitimate only for static-until-changed data with event-based invalidation plus a memory bound; otherwise missing TTL is a gap
- Cache DTOs or response objects, never ORM entities or other mutable references
- Invalidate after the DB commit, never before - an eviction before commit can be refilled with stale data by a concurrent read
- Never bare-delete a hot key; overwrite with the recomputed value or bump a version segment, or the delete itself triggers a stampede
- Measure hit rate in production; target >80% for read caches - persistently below ~50% means the cache is misapplied

## Strategies

- **Cache-aside (lazy)** - default. App checks cache; on miss, fetch, store with TTL, return.
- **Write-through** - write to cache and source together. Always fresh; adds write latency.
- **Invalidation** - TTL (simplest), event-based (fresher, more complex), or version-based (new version segment in key). Layering is normal: state the primary mechanism plus any backstop (e.g., event-based with TTL backstop).
- **Negative caching** - cache "not found" results with a short TTL (seconds) to stop miss storms on absent IDs.

### Cache Stampede Prevention

When a popular key expires, many concurrent requests miss together and stampede the backend.

**Risk rubric:** High = expensive recompute (>100ms) AND hot enough for concurrent misses (tens of requests per TTL window on one key); Medium = one of the two; Low = neither.

- **Lock-based (singleflight)** - one fetcher; others wait and reuse. Use the ecosystem primitive: Go `golang.org/x/sync/singleflight`, Java `ConcurrentHashMap.computeIfAbsent`, Rails `race_condition_ttl`, Redis `SET NX` for distributed coordination. Choose for correctness-critical data.
- **Probabilistic early expiry (XFetch)** - randomly refresh before expiry with probability rising as TTL approaches zero (`random() < fetch_cost / remaining_ttl`). No locking. Choose for read-heavy, staleness-tolerant data.

### Cache Key Design

```
// {service}:{entity}:{id}:{version}
"order-service:order:12345:v2"

// {service}:{query}:{hash-of-sorted-params}
"product-service:search:sha256(category=electronics&sort=price)"
```

- **Namespace by service** to prevent collisions in a shared cache cluster
- **Version segment** bumped when cached structure changes - avoids post-deploy deserialization errors
- **Deterministic hashing** for query keys - sort params before hashing so `?a=1&b=2` and `?b=2&a=1` collide
- **Cap key length** under 250 bytes - many backends truncate or reject longer keys
- **Never embed user input directly** - sanitize or hash to prevent key injection

**Bad** - non-deterministic or opaque:

```
product.toString()    // "Product@3f2a1b" - changes between instances
JSON.stringify(query) // property order is not guaranteed
```

**Good** - structured, deterministic:

```
`catalog:product:${productId}:v1`
`catalog:search:${sha256(sortedParams)}`
```

### TTL Sizing

| Change frequency             | TTL                                   | Examples                       |
| ---------------------------- | ------------------------------------- | ------------------------------ |
| Near-real-time               | 1-10 seconds                          | Inventory counts, live prices  |
| Infrequent                   | 5-60 minutes                          | Product catalog, user profiles |
| Rare                         | 1-24 hours                            | Reference data, feature flags  |
| Static until explicit change | Indefinite (event-based invalidation + memory bound) | Config, CMS content            |

When a staleness budget is stated, TTL = budget minus a safety margin (e.g., 4s for a 5s budget); otherwise pick within the band by change frequency. Stagger TTLs with jitter (+/- 10%) to avoid synchronized expiration storms. For predictable spikes (flash sales, launches), pre-warm hot keys with a background job before opening traffic. Bound distributed-cache memory explicitly (e.g., Redis `maxmemory` + `allkeys-lru`) - TTL alone does not bound key cardinality for query caches.

### Cache Levels

- **In-process** - fastest, per-instance only. With multiple replicas, use only for data that tolerates per-node staleness or that you invalidate via broadcast (pub/sub); otherwise use the distributed tier
- **Distributed** (Redis, Memcached) - shared, slightly higher latency
- **CDN / edge** - static assets and public API responses

### Stack-Specific Adapter

Use the framework's cache abstraction (Spring Cache annotations, Rails.cache, Django cache framework, Laravel Cache facade, Elixir Cachex/ETS, etc.) for cache-aside. For distributed caching, use Redis or Memcached via the ecosystem's standard client. Apply stampede protection via the ecosystem's singleflight or distributed-lock primitive. If the stack is unfamiliar, apply the universal principles above and name the closest primitives you can verify; flag unverified suggestions.

## Output Format

```
## Caching Assessment

**Stack:** {detected language / framework}

### Opportunities

- {component or endpoint} - {what to cache and why}
  - Strategy: {Cache-aside | Write-through}
  - Level: {In-process | Distributed | CDN}
  - Key: {key pattern, with version segment}
  - TTL: {duration and rationale; jitter/pre-warm if spike-prone}
  - Invalidation: {primary: TTL-based | Event-based | Version-based} {+ backstop if layered} - {trigger condition}
  - Stampede risk: {Low | Medium | High per rubric} - {mitigation if Medium/High}

### Excluded from Caching

- {component} - {reason: write-heavy, correctness-critical, low reuse}

### Gaps

Gaps cover existing caches only; safeguards for proposed caches belong inside their Opportunity entry. One row per missing element; group rows by component, order components by their highest severity.
Severity: High = active correctness or outage risk; Medium = degradation or cost; Low = hygiene. A realized incident makes the gap High.

- [Severity: High | Medium | Low] {cache name or component} - {description}
  - Missing: {TTL | invalidation strategy | stampede protection | safe key design | safe value type | memory bound | hit-rate observability | other (name it)}
  - Risk: {unbounded growth | stale data | thundering herd | key collision/injection | stale shared state | other (name it)}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if existing caching is adequate. If no caching exists yet, write "No existing caches - see Opportunities" instead}
```

Omit Opportunities if no additions are recommended. Omit Excluded from Caching if nothing was assessed and rejected. Omit Gaps when no caching exists yet. Omit "No Issues Found" if gaps were listed.

## Response Payload

Cache DTOs (records/dataclasses/structs), never ORM entities. Project at the query layer (select only needed columns). For full REST payload conventions (pagination, field selection, error format) see `backend-api-guidelines`.

## Avoid

- Caching mutable objects or ORM entities (stale shared state)
- Cache without TTL or event-based invalidation (unbounded memory and staleness)
- Cache without invalidation strategy (indefinite staleness)
- Caching write-heavy data (low hit rate, high invalidation churn)
- Ignoring stampede on popular keys
- Evicting before the DB commit, or bare-deleting hot keys
- Exposing ORM entities in API responses
