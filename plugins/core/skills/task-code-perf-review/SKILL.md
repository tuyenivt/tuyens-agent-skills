---
name: task-code-perf-review
description: Performance review for backend and frontend. Auto-detects project stack and adapts performance checks to the detected language and framework.
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
- [ ] No blocking operations in lightweight/cooperative concurrency contexts
- [ ] Thread/worker pool sizing matches the runtime's recommendations
- [ ] Connection pool sized appropriately for the concurrency model

**Database and ORM:**

- [ ] N+1 queries addressed using the ORM's eager loading mechanism
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

### Step 4 - Frontend (React)

**Rendering:**

- [ ] Unnecessary re-renders
- [ ] Missing memoization
- [ ] Inline objects in JSX
- [ ] Heavy computations in render

**Data:**

- [ ] Over-fetching
- [ ] No caching
- [ ] Waterfall requests

**Assets:**

- [ ] Unoptimized images
- [ ] No lazy loading
- [ ] Large bundle

### Step 5 - Caching Strategy (All Stacks)

Use skill: `caching` for cache strategy patterns.
Use skill: `concurrency-model` to validate thread/worker pool sizing and concurrency primitive choices.

Verify:

- [ ] Cache-aside pattern applied for read-heavy data
- [ ] Cache invalidation strategy defined
- [ ] TTL configured appropriately
- [ ] Cache key design avoids collisions
- [ ] Local cache vs distributed cache decision made explicitly

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
