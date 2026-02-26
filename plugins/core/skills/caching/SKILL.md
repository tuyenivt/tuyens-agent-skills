---
name: caching
description: Caching patterns — cache strategy, invalidation, and anti-patterns. Auto-detects project stack and adapts caching guidance to the detected ecosystem.
metadata:
  category: ops
  tags: [caching, performance, redis, multi-stack]
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

- Cache reads, not writes — cache should reflect source of truth
- Every cache entry must have a TTL — no indefinite caching
- Define an invalidation strategy before adding a cache
- Cache DTOs / response objects, never ORM entities or mutable objects
- Monitor cache hit rate — below 80% means the cache may not be effective
- Consider thundering herd on cache eviction (use cache stampede protection)

---

## Caching Strategies

### Cache-Aside (Lazy Loading)

The most common pattern — application checks cache first, falls back to source:

1. Check cache for key
2. On hit: return cached value
3. On miss: fetch from source, store in cache with TTL, return value

### Write-Through

Write to cache and source simultaneously — ensures cache is always fresh but adds write latency.

### Cache Invalidation

- **TTL-based**: Set expiration time; simplest approach
- **Event-based**: Invalidate on write/update events; more complex but fresher
- **Version-based**: Include version in cache key; new version = new key

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

## Avoid (All Stacks)

- Caching mutable objects or ORM entities (stale shared state)
- Cache without TTL (unbounded memory growth)
- Cache without invalidation strategy (stale data served indefinitely)
- Caching write-heavy data (low hit rate, high invalidation churn)
- Ignoring cache stampede on popular keys (use locking or singleflight)
