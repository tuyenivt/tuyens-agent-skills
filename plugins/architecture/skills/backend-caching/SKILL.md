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

- Cache reads, not writes; cache reflects source of truth
- Every cache entry has a TTL
- Define invalidation strategy before adding a cache
- Cache DTOs / response objects, never ORM entities or mutable objects
- Hit rate below 80% means the cache may not be effective
- Address stampede protection for popular keys

---

## Strategies

**Cache-aside (lazy loading)** - default. App checks cache; on miss, fetch from source, store with TTL, return.

**Write-through** - write to cache and source together. Always fresh; adds write latency.

**Invalidation** - TTL (simplest), event-based (fresher, more complex), or version-based (new version = new key).

### Cache Stampede Prevention

When a popular key expires, many concurrent requests all miss and simultaneously hit the backend - this is the thundering herd / cache stampede problem. Two concrete prevention patterns:

**1. Lock-based refresh (singleflight)**
Only one request fetches from the backend; others wait and reuse the result. Use the ecosystem's singleflight primitive (Go `golang.org/x/sync/singleflight`, Java `ConcurrentHashMap.computeIfAbsent`, Redis `SET NX` distributed lock):

```
on cache miss:
  acquire lock(key, ttl=fetch_timeout)
  if lock acquired:
    fetch from backend -> write to cache -> release lock
  else:
    wait for lock release -> read from cache (now populated)
```

**2. Probabilistic early expiry (XFetch)**
Randomly refresh a cache entry before it expires, with probability increasing as TTL approaches zero. No locking needed:

```
remaining_ttl = key_expires_at - now()
if random() < (fetch_cost / remaining_ttl):
  refresh cache entry early  # only one of many concurrent callers will trigger this
```

Use lock-based for correctness-critical data; use probabilistic for read-heavy/staleness-tolerant data.

### Cache Key Design

Well-designed cache keys prevent collisions, enable targeted invalidation, and survive deployments:

```
// Pattern: {service}:{entity}:{id}:{version}
"order-service:order:12345:v2"

// Pattern: {service}:{query}:{hash-of-params}
"product-service:search:sha256(category=electronics&sort=price)"
```

**Key design rules:**

- **Namespace by service** -- prevents collisions between services sharing a cache cluster
- **Include a version segment** -- bump when the cached structure changes (avoids deserialization errors after deploys)
- **Use deterministic hashing for query keys** -- sort parameters before hashing so `?a=1&b=2` and `?b=2&a=1` produce the same key
- **Keep keys under 250 bytes** -- some cache backends truncate or reject longer keys
- **Never embed user-controlled input directly** -- sanitize or hash to prevent key injection

**Bad** - Non-deterministic or opaque cache key:
```
product.toString()    // "Product@3f2a1b" - collisions between instances
JSON.stringify(query) // key order not guaranteed across runs
```

**Good** - Structured, deterministic key:
```
`catalog:product:${productId}:v1`
`catalog:search:${sha256(sortedParams)}`
```

### Cache Warming

For predictable traffic spikes (flash sales, launches), preload known-hot keys before the event:
- Run a background job that pre-fetches and caches the N most-likely-accessed items
- Stagger TTLs to avoid synchronized expiration (add jitter)
- Verify cache population before opening traffic to the event

### TTL Sizing Guidance

| Data change frequency        | Suggested TTL range | Examples                          |
| ---------------------------- | ------------------- | --------------------------------- |
| Near-real-time               | 1-10 seconds        | Inventory counts, live prices     |
| Infrequent changes           | 5-60 minutes        | Product catalog, user profiles    |
| Rarely changes               | 1-24 hours          | Reference data, feature flags     |
| Static until explicit change | Event-based invalidation | Config, CMS content          |

Stagger TTLs to avoid synchronized expiration storms: add jitter (TTL +/- random 10%).

### Cache Levels

- **In-process cache**: Fastest, but per-instance only (not shared across replicas)
- **Distributed cache (Redis, Memcached)**: Shared across instances, slightly higher latency
- **CDN / edge cache**: For static assets and public API responses

## Stack-Specific Guidance

After loading stack-detect, apply caching patterns using the libraries and idioms of the detected ecosystem:

- Use the framework's cache abstraction if available (e.g., Spring Cache annotations, Rails.cache, Django cache framework, Laravel Cache facade)
- For in-process caching, use the ecosystem's standard bounded cache library with eviction policies
- For distributed caching, use Redis or Memcached with the ecosystem's standard client
- For view/fragment caching, use the framework's built-in template caching if available
- Apply stampede protection using the ecosystem's singleflight or locking mechanism

If the detected stack is unfamiliar, apply the universal principles above and recommend the user consult their framework's caching documentation.

---

## Output Format

Consuming workflow skills depend on this structure to surface caching gaps and opportunities consistently.

```
## Caching Assessment

**Stack:** {detected language / framework}

### Opportunities

- {component or endpoint} - {what to cache and why}
  - Strategy: {Cache-aside | Write-through}
  - Level: {In-process | Distributed | CDN}
  - TTL: {recommended duration and rationale}
  - Invalidation: {TTL-based | Event-based | Version-based} - {trigger condition}
  - Stampede risk: {Low | Medium | High} - {mitigation if Medium/High}

### Gaps (Existing Caches Missing Required Properties)

- [Severity: High | Medium | Low] {cache name or component} - {description of gap}
  - Missing: {TTL | invalidation strategy | stampede protection}
  - Risk: {unbounded growth | stale data | thundering herd}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if caching is adequate - do not omit this section silently}
```

Omit Opportunities if no caching additions are recommended. Omit "No Issues Found" if gaps were listed.

---

## Response Payload

Smaller responses cache faster and consume less memory. Cache DTOs (records/dataclasses/structs), never ORM entities. Project at the query layer (select only needed columns; avoid eager-loading everything). Use the framework's serialization mechanism (DTOs, serializer classes, response structs) to drop nulls and control field visibility per context.

For full REST payload conventions (pagination, field selection, errors) see `backend-api-guidelines`.

---

## Avoid

- Caching mutable objects or ORM entities (stale shared state)
- Cache without TTL (unbounded memory)
- Cache without invalidation strategy (indefinite staleness)
- Caching write-heavy data (low hit rate, high invalidation churn)
- Ignoring stampede on popular keys
- Exposing ORM entities in API responses
