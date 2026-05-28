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
- Every cache entry has a TTL and a defined invalidation strategy
- Cache DTOs or response objects, never ORM entities or other mutable references
- Address stampede protection for keys that any individual request would notably degrade by missing
- Measure hit rate in production; persistently low rates mean the cache is misapplied

## Strategies

- **Cache-aside (lazy)** - default. App checks cache; on miss, fetch, store with TTL, return.
- **Write-through** - write to cache and source together. Always fresh; adds write latency.
- **Invalidation** - TTL (simplest), event-based (fresher, more complex), or version-based (new version segment in key).

### Cache Stampede Prevention

When a popular key expires, many concurrent requests miss together and stampede the backend.

- **Lock-based (singleflight)** - one fetcher; others wait and reuse. Use the ecosystem primitive: Go `golang.org/x/sync/singleflight`, Java `ConcurrentHashMap.computeIfAbsent`, Redis `SET NX` for distributed coordination. Choose for correctness-critical data.
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

| Change frequency             | TTL                              | Examples                          |
| ---------------------------- | -------------------------------- | --------------------------------- |
| Near-real-time               | 1-10 seconds                     | Inventory counts, live prices     |
| Infrequent                   | 5-60 minutes                     | Product catalog, user profiles    |
| Rare                         | 1-24 hours                       | Reference data, feature flags     |
| Static until explicit change | Indefinite (event-based invalidation) | Config, CMS content          |

Stagger TTLs with jitter (+/- 10%) to avoid synchronized expiration storms. For predictable spikes (flash sales, launches), pre-warm hot keys with a background job before opening traffic.

### Cache Levels

- **In-process** - fastest, per-instance only (not shared across replicas)
- **Distributed** (Redis, Memcached) - shared, slightly higher latency
- **CDN / edge** - static assets and public API responses

### Stack-Specific Adapter

Use the framework's cache abstraction (Spring Cache annotations, Rails.cache, Django cache framework, Laravel Cache facade, etc.) for cache-aside. For distributed caching, use Redis or Memcached via the ecosystem's standard client. Apply stampede protection via the ecosystem's singleflight or distributed-lock primitive. If the stack is unfamiliar, fall back to the universal principles above and consult framework docs.

## Output Format

```
## Caching Assessment

**Stack:** {detected language / framework}

### Opportunities

- {component or endpoint} - {what to cache and why}
  - Strategy: {Cache-aside | Write-through}
  - Level: {In-process | Distributed | CDN}
  - TTL: {duration and rationale}
  - Invalidation: {TTL-based | Event-based | Version-based} - {trigger condition}
  - Stampede risk: {Low | Medium | High} - {mitigation if Medium/High}

### Gaps

- [Severity: High | Medium | Low] {cache name or component} - {description}
  - Missing: {TTL | invalidation strategy | stampede protection}
  - Risk: {unbounded growth | stale data | thundering herd}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if caching is adequate - do not omit silently}
```

Omit Opportunities if no additions are recommended. Omit "No Issues Found" if gaps were listed.

## Response Payload

Cache DTOs (records/dataclasses/structs), never ORM entities. Project at the query layer (select only needed columns). For full REST payload conventions (pagination, field selection, error format) see `backend-api-guidelines`.

## Avoid

- Caching mutable objects or ORM entities (stale shared state)
- Cache without TTL (unbounded memory)
- Cache without invalidation strategy (indefinite staleness)
- Caching write-heavy data (low hit rate, high invalidation churn)
- Ignoring stampede on popular keys
- Exposing ORM entities in API responses
