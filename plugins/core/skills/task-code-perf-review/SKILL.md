---
name: task-code-perf-review
description: Performance review for backend and frontend. Auto-detects project stack from CLAUDE.md and adapts performance checks to the detected language and framework.
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

## Key Skills Reference

**Backend Performance:**

- Use skill: `concurrency-model` for thread-safe locking
- Use skill: `caching` for cache strategy patterns
- Use skill: `db-indexing` for index strategy
- Use skill: `observability` for metrics and monitoring
- Use skill: `resiliency` for timeout and circuit breaker patterns

**Frontend Performance:**

- Use skill: `payload-optimization` for response size optimization

## Principle

> Measure first. No optimization without profiling.

## Rules

- Always profile before optimizing
- Focus on the critical path
- Measure improvement after each change
- Consider trade-offs (complexity vs performance)
- Do not apply performance patterns from one framework to another

## Output

```markdown
## Summary

**Stack Detected:** [language / framework]
[Performance assessment]

## Findings

### Critical | High | Medium

- **Location:** [file:line]
- **Issue:** [description]
- **Impact:** [expected improvement]

## Database Issues

[N+1, missing indexes, connection pool]

## Caching Opportunities

[What to cache, invalidation strategy]

## Observability Gaps

[Missing logging, metrics, correlation IDs]

## Measurements Needed

| Issue | How to Measure |

## Recommendations

[Prioritized with trade-offs]
```

## Success Criteria

A well-executed performance review passes all of these. Use as a self-check before presenting findings.

### Completeness

- [ ] Database performance checks are applied - N+1, missing indexes, over-fetching, connection pool
- [ ] Framework-specific checks for the detected stack are applied (concurrency, ORM, caching)
- [ ] Every Critical or High finding includes a concrete measurement path - not just "profile this"
- [ ] Caching opportunities include both what to cache and an invalidation strategy

### Signal Quality

- [ ] Findings are ordered Critical > High > Medium - no severity mixing
- [ ] Every finding states expected impact - not just "this is slow"
- [ ] No findings for non-critical paths without profiling evidence to justify them
- [ ] Recommendations state the trade-off (complexity added vs performance gained)

### Staff-Level Signal (for tech lead review)

- [ ] The "measure first" principle is upheld - optimization recommendations cite the bottleneck evidence
- [ ] The highest-impact finding is clearly identified and presented first
- [ ] Observability gaps are called out if the affected path lacks the metrics needed to validate improvements
- [ ] No performance patterns from a different stack are applied to the detected stack

## Avoid

- Optimizing without profiling data
- Premature optimization of non-critical paths
- Adding complexity for marginal gains
- Caching without an invalidation strategy
- Applying performance patterns from one stack to another

## After This Skill

If the output needed significant adjustment - wrong bottlenecks identified, caching advice lacked invalidation strategy, or stack-specific patterns were missed - run `/task-skill-feedback` to log what changed and why.
