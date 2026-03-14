---
name: caching
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

## Universal Principles (All Stacks)

- Cache reads, not writes - cache should reflect source of truth
- Every cache entry must have a TTL - no indefinite caching
- Define an invalidation strategy before adding a cache
- Cache DTOs / response objects, never ORM entities or mutable objects
- Monitor cache hit rate - below 80% means the cache may not be effective
- Consider thundering herd on cache eviction (use cache stampede protection)

---

## Caching Strategies

### Cache-Aside (Lazy Loading)

The most common pattern - application checks cache first, falls back to source:

1. Check cache for key
2. On hit: return cached value
3. On miss: fetch from source, store in cache with TTL, return value

### Write-Through

Write to cache and source simultaneously - ensures cache is always fresh but adds write latency.

### Cache Invalidation

- **TTL-based**: Set expiration time; simplest approach
- **Event-based**: Invalidate on write/update events; more complex but fresher
- **Version-based**: Include version in cache key; new version = new key

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

### Cache Levels

- **In-process cache**: Fastest, but per-instance only (not shared across replicas)
- **Distributed cache (Redis, Memcached)**: Shared across instances, slightly higher latency
- **CDN / edge cache**: For static assets and public API responses

## Stack-Specific Guidance

After loading stack-detect, apply caching patterns using the libraries and idioms of the detected ecosystem:

- Use the framework's cache abstraction if available (e.g., Spring Cache annotations, Rails.cache, Django cache framework)
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

## Response Optimization

Reducing payload size complements caching - smaller responses mean faster cache reads and lower bandwidth.

### Response Shaping

- Use dedicated response objects separate from data layer entities - never expose ORM entities directly
- Include only the fields the consumer needs
- Exclude internal fields (audit timestamps, soft-delete flags, internal IDs) unless explicitly needed
- Control field visibility per response context (list view vs detail view)

### Query-Level Projection

- Select only needed columns in database queries (not `SELECT *`)
- Load only required associations/relationships (avoid eager-loading everything)
- Use the ORM's projection capabilities to fetch partial records

### Serialization Control

- Exclude null or empty fields from JSON output when appropriate
- Use conditional serialization for fields that are only relevant in certain contexts
- Use the framework's serialization mechanism for response shaping (DTOs/records, serializer classes, response structs with field tags, etc.)

### Stack-Specific Response Optimization

After loading stack-detect, apply response optimization using the idioms of the detected ecosystem:

- Use the framework's serialization mechanism for response shaping
- Use the ORM's projection or select API for query-level optimization
- Apply the framework's conditional serialization features (e.g., JSON views, serializer contexts, field exclusion tags)

---

## Avoid (All Stacks)

- Caching mutable objects or ORM entities (stale shared state)
- Cache without TTL (unbounded memory growth)
- Cache without invalidation strategy (stale data served indefinitely)
- Caching write-heavy data (low hit rate, high invalidation churn)
- Ignoring cache stampede on popular keys (use locking or singleflight)
- Exposing ORM entities / model objects in API responses
- Deep nesting in response schemas
- Unpaginated collection endpoints
- Over-fetching from the database when only a subset of fields is needed
