---
name: task-code-perf-review
description: Performance review for backend services and frontend applications - N+1 queries, missing indexes, slow endpoints, unnecessary re-renders, bundle size, Core Web Vitals, memory leaks, and concurrency anti-patterns. Use when an endpoint is slow, a page loads slowly, a batch job takes too long, memory grows unbounded, or you want a dedicated perf pass before a release.
metadata:
  category: review
  tags: [performance, optimization, profiling, database, multi-stack]
  type: workflow
user-invocable: true
---

# Performance Review

## When to Use

- Performance issue identification
- Backend optimization (database, caching, concurrency)
- Frontend optimization (rendering, bundle size, Core Web Vitals)
- Database query optimization
- Caching strategy review

**Not for:** General code review (use `task-code-review`), security review (use `task-code-secure`), pre-implementation risk planning (use `task-design-risk-analysis`).

## Depth Levels

| Depth      | When to Use                                             | What Runs                                   |
| ---------- | ------------------------------------------------------- | ------------------------------------------- |
| `quick`    | Single endpoint or focused change ("is this query ok?") | DB performance + top findings only          |
| `standard` | Default - full performance review                       | All steps                                   |
| `deep`     | Profiling-driven review or known hot path investigation | All steps + capacity and load test guidance |

Default: `standard`. Use `quick` when user targets a specific query or method.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 - Database Performance (Backend and Fullstack)

Skip this step if `Stack Type: frontend`.

- [ ] N+1 queries detected and resolved
- [ ] Missing indexes on WHERE/ORDER BY columns
- [ ] Over-fetching (select only needed columns)
- [ ] No pagination for large datasets
- [ ] Connection pool sizing appropriate
- [ ] Query timeout configured
- [ ] Batch operations for bulk inserts/updates

### Step 3 - Framework-Specific Backend Review (Backend and Fullstack)

Skip this step if `Stack Type: frontend`.

After loading stack-detect, apply performance checks specific to the detected ecosystem:

**Concurrency and Threading:**

- [ ] Concurrency primitives are appropriate for the runtime's threading model
- [ ] No blocking operations in lightweight/cooperative concurrency contexts (e.g., sync SQLAlchemy in async Python handlers, blocking I/O in Node.js event loop, sync JDBC in Kotlin coroutines, long-running sync operations in Laravel queue workers)
- [ ] Thread/worker pool sizing matches the runtime's recommendations
- [ ] Connection pool sized appropriately for the concurrency model

**Database and ORM:**

- [ ] N+1 queries addressed using the ORM's eager loading mechanism (e.g., `joinedload`/`selectinload` in SQLAlchemy, `includes`/`eager_load` in Rails, `fetch = EAGER` in JPA, `Include()` in EF Core, `with()`/`load()` in Eloquent)
- [ ] Multi-level N+1 patterns caught (nested loops each issuing queries - 2N+1, 3N+1)
- [ ] Read-only transactions or query hints used where applicable
- [ ] The ORM's batch processing API used for large record sets

**Caching:**

- [ ] Cache-aside pattern applied for read-heavy data using the framework's cache abstraction
- [ ] Cache invalidation strategy defined
- [ ] TTL configured appropriately

**Memory and I/O:**

- [ ] Streaming used for large file/payload processing (not loading fully into memory)
- [ ] Timeouts configured on all external calls
- [ ] Circuit breakers for external service dependencies
- [ ] HTTP client instances reused (not created per request)

**Common Performance Anti-Patterns:**

- [ ] No hidden expensive queries in framework hooks/callbacks/middleware
- [ ] Serializers/response shaping not loading unnecessary associations
- [ ] Background processing used for heavy operations where appropriate

If the detected stack is unfamiliar, apply the database and universal I/O checks and recommend profiling with the ecosystem's standard tools.

### Step 4 - Caching Deep Dive (Backend and Fullstack)

Skip this step if `Stack Type: frontend`.

Use skill: `backend-caching` for cache strategy patterns (key design, invalidation, local vs distributed).
Use skill: `architecture-concurrency` to validate thread/worker pool sizing and concurrency primitive choices.

Verify (beyond the basic cache checks in Step 3):

- [ ] Cache key design avoids collisions and hot keys
- [ ] Local cache vs distributed cache decision made explicitly
- [ ] Cache stampede protection considered for high-traffic keys

### Step 5 - Frontend Performance (Frontend and Fullstack)

Skip this step if `Stack Type: backend`.

Use skill: `frontend-performance` for Core Web Vitals, bundle analysis, and rendering optimization.

**Rendering (all frontend frameworks):**

- [ ] Unnecessary re-renders or change detection cycles
- [ ] Heavy computations in render/template path (move to memoization or web workers)
- [ ] Missing virtualization for long lists (> 100 items)

**Framework-specific rendering checks:**

- **React**: Missing `React.memo`, `useMemo`, `useCallback`; inline objects/functions in JSX causing re-renders; missing Suspense boundaries for code splitting
- **Vue**: Expensive operations in computed without caching benefit; reactive dependencies triggering unnecessary updates; missing `v-once` or `v-memo` for static content; `v-for` without `key`
- **Angular**: Components not using `OnPush` change detection; missing `trackBy` on `@for` loops; large eagerly-loaded modules (use `@defer` or lazy routes); excessive Zone.js change detection cycles

**Data Fetching:**

- [ ] Over-fetching (requesting more data than rendered)
- [ ] No client-side caching (React Query / SWR, Vue Query, Angular HttpClient with cache)
- [ ] Waterfall requests (parallelize with `Promise.all`, `Suspense`, or framework-specific patterns)
- [ ] No stale-while-revalidate or prefetching for navigation-critical data

**Assets and Bundle:**

- [ ] Unoptimized images (missing `next/image`, `nuxt-img`, or `NgOptimizedImage`)
- [ ] No lazy loading for below-the-fold components
- [ ] Large bundle (check for unintentional full-library imports, missing tree-shaking)
- [ ] No code splitting at route level

### Step 6 - Stateless Design (All Stacks)

- [ ] No server-side session state (use JWT/tokens)
- [ ] Externalized session if needed (Redis)
- [ ] No static mutable state
- [ ] Idempotent operations where possible

### Step 7 - Observability (All Stacks)

Use skill: `ops-observability` for metrics and monitoring patterns.

Verify:

- [ ] Structured logging in place for affected paths
- [ ] Correlation ID propagation across service boundaries
- [ ] Metrics instrumented for custom operations
- [ ] Health indicators exist for critical dependencies

## Self-Check

- [ ] Stack Type determined; backend steps skipped for frontend-only, frontend steps skipped for backend-only
- [ ] **Backend/fullstack**: Database performance checked: N+1 queries, missing indexes, pagination, pool sizing
- [ ] **Backend/fullstack**: Framework-specific concurrency and ORM checks applied for the detected stack
- [ ] **Backend/fullstack**: Caching strategy assessed: TTL, invalidation, key design
- [ ] **Frontend/fullstack**: Rendering performance checked with framework-specific patterns (React/Vue/Angular)
- [ ] **Frontend/fullstack**: Bundle size and code splitting assessed
- [ ] **Frontend/fullstack**: Data fetching patterns reviewed (caching, waterfalls, over-fetching)
- [ ] Every finding states estimated impact (latency/throughput/memory/CWV) not just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes

## Output Format

```markdown
## Performance Review Summary

**Stack Detected:** [language / framework]
**Scope:** Backend | Frontend | Fullstack
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line or component]
- **Issue:** [what the problem is]
- **Impact:** [estimated effect - e.g., "N+1 query adds ~200ms per request at 1K rows"]
- **Fix:** [specific change with code example if applicable]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Add query result caching for the product catalog endpoint", "Enable connection pool monitoring"]
```

## Avoid

- Reporting performance issues without estimated impact ("this is slow" vs "adds ~200ms per request")
- Premature optimization on cold paths - focus on hot paths and measured bottlenecks
- Recommending caching without addressing invalidation strategy
- Suggesting async/concurrent solutions without considering the runtime's threading model
- Conflating performance review with general code review - stay focused on perf
