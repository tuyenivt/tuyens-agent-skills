---
name: task-code-review-perf
description: Performance review entry point: DB perf, concurrency, caching, frontend rendering. Detects stack and dispatches perf review workflow.
metadata:
  category: review
  tags: [performance, optimization, profiling, database, multi-stack, router]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Performance Review (Router)

This skill is a thin dispatcher. It detects the project stack and delegates to the matching stack-specific skill (e.g., `task-spring-review-perf`, `task-rails-review-perf`, `task-react-review-perf`). The stack workflow names framework-specific perf anti-patterns directly (Rails: N+1 with `includes`/`eager_load`; Spring: `@Transactional(readOnly)` and JPA fetch strategies; React: `React.memo`/`useMemo`/list virtualization).

For unknown stacks, this skill falls back to a minimal generic perf review.

## When to Use

- Performance issue identification (slow endpoint, slow page, batch job too long, memory growth)
- Pre-release dedicated perf pass
- Database query, caching, or rendering optimization

**Not for:** General code review (use `task-code-review`), security review (use `task-code-review-security`), observability gaps (use `task-code-review-observability`).

## Invocation

Accepts the same diff-targeting arguments as `task-code-review`. Depth flags (`quick`, `standard`, `deep`) compose. When invoked as a subagent of `task-code-review`, the parent passes the precondition handle plus the read-once diff/log; this is forwarded to the dispatched stack workflow.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect`.

### Step 2 - Dispatch to Stack Workflow

| Detected stack       | Delegate to                |
| -------------------- | -------------------------- |
| Java / Spring Boot   | `task-spring-review-perf`  |
| Kotlin / Spring Boot | `task-kotlin-review-perf`  |
| Python               | `task-python-review-perf`  |
| Ruby / Rails         | `task-rails-review-perf`   |
| Node.js / TypeScript | `task-node-review-perf`    |
| Go / Gin             | `task-go-review-perf`      |
| Rust / Axum          | `task-rust-review-perf`    |
| .NET / ASP.NET Core  | `task-dotnet-review-perf`  |
| PHP / Laravel        | `task-laravel-review-perf` |
| React                | `task-react-review-perf`   |
| Vue                  | `task-vue-review-perf`     |
| Angular              | `task-angular-review-perf` |

If matched, forward arguments and stop. Do not run Step 3.

### Step 3 - Generic Fallback (unknown stack only)

Use skill: `review-precondition-check` if running standalone (skip if invoked as subagent and parent passed the handle). Read diff and commit log once.

**Database performance** (Backend / Fullstack):

- N+1 queries detected; use the ORM's eager-load mechanism to fix
- Missing indexes on WHERE / ORDER BY columns
- Over-fetching (select only needed columns); no leading-wildcard LIKE on large tables
- Pagination present for large datasets; query timeout configured
- Connection pool sized appropriately
- Use skill: `backend-db-indexing` for detailed index analysis

**Concurrency and threading** (Backend / Fullstack):

- Concurrency primitives appropriate for the runtime's threading model
- No blocking I/O inside cooperative async contexts
- Thread/worker pool sizing matches recommendations
- Use skill: `architecture-concurrency`

**Caching** (Backend / Fullstack):

- Cache-aside applied for read-heavy data via the framework's cache abstraction
- Every cache entry has a TTL (no indefinite caching); jitter applied to avoid synchronized expiry
- Invalidation strategy defined (TTL-based, event-based, or version-keyed)
- Cache key design: `{service}:{entity}:{id}:{version}`, deterministic hashing for query params, no user-controlled input
- Stampede protection on high-traffic keys (singleflight / lock-based or probabilistic early expiry)
- DTOs cached, never ORM entities or mutable objects

**Memory and I/O:**

- Streaming for large file/payload processing (not buffering in memory)
- Timeouts on all external calls; circuit breakers for external services
- HTTP client instances reused, not created per request

**Frontend performance** (Frontend / Fullstack):

- Unnecessary re-renders or change-detection cycles
- Heavy computation in render path (move to memoization or workers)
- Missing virtualization for long lists (>100 items)
- Over-fetching, waterfall requests; client-side caching missing
- Unoptimized images; no lazy loading; no route-level code splitting
- Use skill: `frontend-performance`

**Stateless design:** no server-side session state; idempotent operations where possible.

**Observability:** RED metrics on critical paths; correlation IDs propagated; histograms for latency. Use skill: `ops-observability`.

**Step 4 - Write Report:** Use skill: `review-report-writer` with `report_type: review-perf`.

## Output Format

When dispatched (Step 2 matched): the stack-specific workflow owns the output.

When fallback runs (Step 3):

```markdown
## Performance Review Summary

**Stack Detected:** unknown (generic fallback applied)
**Scope:** Backend | Frontend | Fullstack
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line or component]
- **Issue:** [what the problem is]
- **Impact:** [estimated effect, e.g., "N+1 adds ~200ms per request at 1K rows"]
- **Fix:** [specific change with code example if applicable]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Next Steps

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: schema] - [one-line action]
```

## Self-Check

- [ ] `behavioral-principles` loaded before any other step
- [ ] `stack-detect` ran at Step 1
- [ ] If a stack matched, the dispatched workflow ran and Step 3 was skipped
- [ ] If no stack matched, fallback covered DB / concurrency / caching / I/O / frontend (as applicable to Stack Type)
- [ ] Every finding states estimated impact, not just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Review report written to file via `review-report-writer`

## Avoid

- Running both Step 2 dispatch and Step 3 fallback
- Reporting performance issues without estimated impact
- Premature optimization on cold paths
- Recommending caching without addressing invalidation
- Treating the fallback as a full equivalent of a stack workflow - install the matching language plugin when one exists
