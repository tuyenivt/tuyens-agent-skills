---
name: task-code-perf-review
description: Performance review for backend services and React frontends - N+1 queries, missing indexes, slow endpoints, memory leaks, connection pool sizing, and concurrency anti-patterns. Use when an endpoint is slow, a batch job takes too long, memory grows unbounded, or you want a dedicated perf pass before a release.
metadata:
  category: review
  tags: [performance, optimization, profiling, database, multi-stack]
  type: workflow
user-invocable: true
---

# Performance Review

## When to Use

- Performance issue identification
- Backend optimization
- Frontend optimization (React)
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

### Step 2 - Database Performance (All Backend Stacks)

- [ ] N+1 queries detected and resolved
- [ ] Missing indexes on WHERE/ORDER BY columns
- [ ] Over-fetching (select only needed columns)
- [ ] No pagination for large datasets
- [ ] Connection pool sizing appropriate
- [ ] Query timeout configured
- [ ] Batch operations for bulk inserts/updates

### Step 3 - Framework-Specific Backend Review

After loading stack-detect, apply performance checks specific to the detected ecosystem:

**Concurrency and Threading:**

- [ ] Concurrency primitives are appropriate for the runtime's threading model
- [ ] No blocking operations in lightweight/cooperative concurrency contexts (e.g., sync SQLAlchemy in async Python handlers, blocking I/O in Node.js event loop, sync JDBC in Kotlin coroutines)
- [ ] Thread/worker pool sizing matches the runtime's recommendations
- [ ] Connection pool sized appropriately for the concurrency model

**Database and ORM:**

- [ ] N+1 queries addressed using the ORM's eager loading mechanism (e.g., `joinedload`/`selectinload` in SQLAlchemy, `includes`/`eager_load` in Rails, `fetch = EAGER` in JPA, `Include()` in EF Core)
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

### Step 4 - Caching Deep Dive (All Stacks)

Use skill: `caching` for cache strategy patterns (key design, invalidation, local vs distributed).
Use skill: `concurrency-model` to validate thread/worker pool sizing and concurrency primitive choices.

Verify (beyond the basic cache checks in Step 3):

- [ ] Cache key design avoids collisions and hot keys
- [ ] Local cache vs distributed cache decision made explicitly
- [ ] Cache stampede protection considered for high-traffic keys

### Step 5 - Frontend (React, if applicable)

Skip this step if the review target is backend-only.

**Rendering:**

- [ ] Unnecessary re-renders (missing `React.memo`, `useMemo`, `useCallback`)
- [ ] Inline objects or functions in JSX causing re-renders
- [ ] Heavy computations in render path (move to `useMemo` or worker)

**Data:**

- [ ] Over-fetching (requesting more data than rendered)
- [ ] No client-side caching (consider React Query / SWR)
- [ ] Waterfall requests (parallelize with `Promise.all` or `Suspense`)

**Assets:**

- [ ] Unoptimized images (missing `next/image` or equivalent)
- [ ] No lazy loading for below-the-fold components
- [ ] Large bundle (check for unintentional full-library imports)

### Step 6 - Stateless Design (All Stacks)

- [ ] No server-side session state (use JWT/tokens)
- [ ] Externalized session if needed (Redis)
- [ ] No static mutable state
- [ ] Idempotent operations where possible

### Step 7 - Observability (All Stacks)

Use skill: `observability` for metrics and monitoring patterns.

Verify:

- [ ] Structured logging in place for affected paths
- [ ] Correlation ID propagation across service boundaries
- [ ] Metrics instrumented for custom operations
- [ ] Health indicators exist for critical dependencies

## Self-Check

- [ ] Database performance checked: N+1 queries, missing indexes, pagination, pool sizing
- [ ] Framework-specific concurrency and ORM checks applied for the detected stack
- [ ] Caching strategy assessed: TTL, invalidation, key design
- [ ] Frontend step applied if React is in scope; skipped with note if backend-only
- [ ] Every finding states estimated impact (latency/throughput/memory) not just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes

## Output Format

```markdown
## Performance Review Summary

**Stack Detected:** [language / framework]
**Scope:** Backend | Backend + React frontend
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
