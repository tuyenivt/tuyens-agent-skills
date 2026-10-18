---
name: backend-caching
description: Caching strategy, invalidation, stampede protection, key design, TTL sizing, and response payload shaping. Adapts to the detected project stack.
metadata:
  category: ops
  tags: [caching, performance, redis, payload, serialization, multi-stack]
user-invocable: false
---

# Caching

> Load `Use skill: stack-detect` first to determine the project stack. Its `Language` and `Framework` pick the cache abstraction and the stampede primitive in the Stack-Specific Adapter; the distributed engine is the `Additional` line `Cache: <engine>` when the project declares one, otherwise Redis. Those choices fill each Opportunity's stampede mitigation and each gap's `Fix`; the `Stack:` line carries the detected Language / Framework. When Language and Framework are `unknown`, apply the universal guidance and mark primitives unverified. The strategies, TTL bands and key rules are stack-agnostic.

## When to Use

- Read-heavy endpoints with infrequently changing data
- Expensive computations or slow external service calls
- Reducing database load for frequently accessed queries
- Improving response latency for hot paths

## Rules

- The cache serves reads and never becomes the source of truth; a write-through strategy still writes through to the store in the same operation
- Every cache entry has a TTL and a defined invalidation strategy. Indefinite TTL is legitimate only for static-until-changed data with event-based invalidation plus a memory bound; otherwise missing TTL is a gap
- Cache DTOs or response objects, never ORM entities or other mutable references
- Invalidate after the DB commit, never before - an eviction before commit can be refilled with stale data by a concurrent read
- Delete on write. On a hot key, pair the delete with singleflight repopulation or bump a version segment, so the miss storm the delete creates is absorbed. Overwriting with the recomputed value avoids that storm but reopens a write-write race - two writers can land out of order and pin stale data for a full TTL - so use it only where writes to the key are serialized
- Measure hit rate in production. Above ~80% the cache is doing its job; 50-80% is worth tuning (key cardinality, TTL, what is cached); persistently below ~50% means the cache is misapplied: remove it, or redesign it as an Opportunity when the data fits a different tier or key

## Strategies

- **Cache-aside (lazy)** - default. App checks cache; on miss, fetch, store with TTL, return.
- **Write-through** - write to source and cache in the same operation. Fresh only where writes to the key are serialized (see Rules); adds write latency.
- **Invalidation** - TTL (simplest), event-based (fresher, more complex), or version-based (new version segment in key). Layering is normal: state the primary mechanism plus any backstop (e.g., event-based with TTL backstop).
- **Negative caching** - cache "not found" results with a short TTL (seconds) to stop miss storms on absent IDs.

### Cache Stampede Prevention

When a popular key expires, many concurrent requests miss together and stampede the backend.

**Risk rubric:** High = expensive recompute (>100ms) AND hot enough for concurrent misses (multiple requests expected within one recompute duration when the key expires); Medium = one of the two; Low = neither.

- **Lock-based (singleflight)** - one fetcher recomputes; the others wait and reuse its result. Per-process: Go `golang.org/x/sync/singleflight`, Java a Caffeine or Guava `LoadingCache`, which admits one in-flight load per key and blocks concurrent callers on it; Python an `asyncio.Lock` per key, where each waiter re-checks the cache after acquiring the lock, or every waiter recomputes in turn. Across processes: a Redis lock taken with `SET key val NX PX <ttl>` - the expiry is required, or a crashed holder blocks the key forever - with losers polling the cache rather than recomputing. Choose when the recompute must run exactly once per expiry (expensive or rate-limited source) and no caller may be served a value past its TTL.
- **Serve-stale-while-recomputing** - the first caller past expiry recomputes while every other caller is served the previous value. Rails `Rails.cache.fetch(key, expires_in: ..., race_condition_ttl: ...)` implements exactly this; it is not a lock and callers do get stale data. Choose when a few seconds of staleness beats a stampede.
- **Probabilistic early expiry (XFetch)** - each read may refresh early, with probability rising as expiry nears: recompute when `now - delta * beta * ln(rand()) >= expiry`, where `delta` is the measured recompute duration, `rand()` is uniform on (0,1], and `beta` defaults to 1 - above 1 refreshes earlier, below 1 later. No locking, no stale reads; an occasional duplicate recompute is possible. Choose for read-heavy hot keys where a duplicate recompute is cheap.

### Cache Key Design

```
// {service}:{entity}:{id}:{version}
"order-service:order:12345:v2"

// {service}:{query}:{hash of the sorted params, never the params themselves}
"product-service:search:9f2b41c8e0a7..."
```

- **Namespace by service** to prevent collisions in a shared cache cluster
- **Version segment** bumped when cached structure changes - avoids post-deploy deserialization errors
- **Deterministic hashing** for query keys - sort params before hashing so `?a=1&b=2` and `?b=2&a=1` map to one key
- **Bound key length** - Memcached rejects keys over 250 bytes outright; Redis allows far longer but every byte is stored per entry, so hash anything unbounded
- **Never embed user input directly** - sanitize or hash to prevent key injection

**Bad** - collides or varies for equal inputs:

```js
`catalog:product:${product}`  // "[object Object]" - every product shares one key
JSON.stringify(query)         // key order follows insertion, so equal queries differ
```

**Good** - structured, deterministic at every depth:

```js
import { createHash } from "node:crypto";

const stable = (v) =>
  Array.isArray(v) ? v.map(stable)
  : v instanceof Date ? v.toISOString()
  : v && typeof v === "object" ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, stable(v[k])]))
  : v;

const hash = (o) => createHash("sha256").update(JSON.stringify(stable(o))).digest("hex");

`catalog:product:${productId}:v1`
`catalog:search:${hash(queryParams)}`
```

Sorting only the top level leaves a nested filter object serializing in insertion order, and skipping arrays leaves an object inside a list unsorted - both are the Bad line again. Rebuilding an object as an array of pairs makes `{a:1}` collide with `[["a",1]]`, which is why `Object.fromEntries` keeps it an object. Hash plain data only: a `Map` or `Set` serializes as `{}` and collides with an empty object, so convert it to an array or object first.

### TTL Sizing

| Change frequency             | TTL                                   | Examples                       |
| ---------------------------- | ------------------------------------- | ------------------------------ |
| Near-real-time               | 1-30 seconds                          | Inventory counts, live prices  |
| Infrequent                   | 30 seconds - 60 minutes               | Product catalog, user profiles |
| Rare                         | 1-24 hours                            | Reference data, feature flags  |
| Static until explicit change | Indefinite (event-based invalidation + memory bound) | Config, CMS content            |

When a staleness budget is stated, TTL = budget minus a safety margin (e.g., 4s for a 5s budget); otherwise pick within the band by change frequency. Stagger TTLs with jitter (+/- 10%) to avoid synchronized expiration storms - downward only (0 to -10%) when a staleness budget is stated, so no entry outlives it. For predictable spikes (flash sales, launches), pre-warm hot keys with a background job before opening traffic. Bound distributed-cache memory explicitly - in Redis, set `maxmemory` and a `maxmemory-policy` such as `allkeys-lru` - because TTL alone does not bound key cardinality for query caches. Redis defaults to `maxmemory 0` with `noeviction`: unset, memory grows until the host kills the process; capped but still `noeviction`, every command that adds data fails with `OOM command not allowed` once the cap is hit (deletes still succeed), for every service sharing it - so the bound is a correctness concern, not housekeeping.

### Cache Levels

- **In-process** - fastest, per-instance only. With multiple replicas, use only for data that tolerates per-node staleness or that you invalidate via broadcast (pub/sub); otherwise use the distributed tier
- **Distributed** (Redis, Memcached) - shared, slightly higher latency
- **CDN** - static assets and public API responses, cached at the edge

### Stack-Specific Adapter

Use the framework's cache abstraction for cache-aside: Spring Cache annotations, `Rails.cache`, Django's cache framework, Laravel's Cache facade, Elixir Cachex (raw ETS has no TTL or eviction policy, so it does not satisfy the TTL rule on its own). Where the framework ships none (FastAPI, Express), use the client the project already holds rather than adding a library. For distributed caching, use the declared engine, else Redis, via the ecosystem's standard client. Apply stampede protection with the ecosystem's primitive for the mechanism chosen above - singleflight or `LoadingCache`, a distributed lock (Redis `SET NX PX`; Memcached `add` with an expiry), Rails `race_condition_ttl`, or XFetch. Invalidate after commit through the framework's hook: Spring `@TransactionalEventListener(phase = AFTER_COMMIT)`, Rails `after_commit`, Django `transaction.on_commit`. If the stack is unfamiliar, apply the universal principles above and name the closest primitives you can verify; flag unverified suggestions.

## Output Format

`Opportunities` covers caches to add, `Gaps` covers caches that already exist. Safeguards for a proposed cache belong inside its Opportunity entry, never in Gaps. `Missing` takes one value, so a component with several distinct gaps gets one entry per gap, listed together under that component and ordered by severity: High = active correctness or outage risk, Medium = degradation or cost, Low = hygiene. A gap that has already caused an incident is High. A fix that replaces the cache tier (in-process to distributed) is an Opportunity for the new tier, with the old tier's defects listed as Gaps, each `Fix` pointing at that Opportunity. Every existing cache appears under Gaps - a clean one as the second row form below, with no sub-slots - so the Assessment's existing-cache count is verifiable and its gap count excludes those rows; a manager-level default (a cache config with no TTL) is reported on each cache it governs, not as a row of its own.

Emit `Assessment` always, and every section that has content. Omit a section only when it would be empty, and write the one-line closing statement that names what was empty.

```
## Caching Assessment

**Stack:** {detected language / framework; "unknown - universal guidance" when stack-detect reports Language and Framework as unknown}

### Opportunities

- {component or endpoint} - {what to cache and why}
  - Strategy: {Cache-aside | Write-through}{ + Negative (short-TTL not-found)}
  - Level: {In-process | Distributed | CDN}
  - Key: {key pattern, with version segment}
  - TTL: {duration and rationale; jitter/pre-warm if spike-prone}
  - Invalidation: {primary: TTL-based | Event-based | Version-based} {+ backstop if layered} - {trigger condition}
  - Memory bound: {eviction policy and cap for a distributed tier | max entries or max weight for an in-process tier, e.g. "maximumSize 10_000" | "n/a - CDN, bounded by the provider"; where the policy is owned by another team and cannot be changed, bound the key space instead - cap cardinality and TTL - and name the owner the footprint must be agreed with}
  - Stampede risk: {Low | Medium | High per rubric} - {mitigation, or "none needed" when Low}

### Excluded from Caching

- {component} - {write-heavy | correctness-critical | low reuse | other (name it)}

### Gaps

- [Severity: High | Medium | Low] {cache name or component} - {description}
  - Missing: {TTL | invalidation strategy | invalidation ordering | write-write race guard | stampede protection | safe key design | safe value type | memory bound | hit-rate observability | other (name it)}
  - Measured: {hit rate and what it implies per the Rules band, or "not measured"}
  - Risk: {unbounded growth | stale data | thundering herd | key collision/injection | stale shared state | wasted capacity | other (name it)}
  - Fix: {concrete correction, named in the detected stack's own primitives; when the stack is unknown, give the universal correction and mark it "(primitive unverified)"}
- {cache name} - no gaps

### Assessment

{One line, always present, naming all four counts so an omitted section is still accounted for: "{N existing caches | No existing caches}; {N gaps found | no gaps}; {N opportunities proposed | no additions recommended}{; nothing excluded | ; {N} excluded}". Where no caches exist and none are recommended, add why caching does not fit this workload.}
```

An uncapped in-process cache (a plain map or dict, raw ETS) is a `memory bound` Gap; `correctness-critical` under Excluded is data that cannot tolerate any cache staleness, which is distinct from data that is cached under a lock. A writer and reader that disagree on a key is `safe key design` with Risk `stale data`, High when it makes an invalidation a no-op. A distributed cache whose cap is owned by another team and unseen is not a memory-bound Gap; name the owner on its row. A figure the source does not give (a vendor quote's validity, a hit rate) is written with `(assumed)` where it is used.

## Response Payload

Cache DTOs (records/dataclasses/structs), never ORM entities. Project at the query layer (select only needed columns). For full REST payload conventions (pagination, field selection, error format) see `backend-api-guidelines`.

## Avoid

- Calling a bare per-key lock "singleflight" when each waiter recomputes after acquiring it
- Jittering a TTL upward past a stated staleness budget
- Caching write-heavy data (low hit rate, high invalidation churn)
