---
name: task-code-review-perf
description: Performance review entry point: DB perf, concurrency, caching, frontend rendering. Detects stack and dispatches perf review workflow.
metadata:
  category: review
  tags: [performance, optimization, profiling, database, multi-stack, router]
  type: workflow
user-invocable: true
---

# Performance Review (Router)

Detects the project stack and delegates to the matching stack-specific perf review (`task-{stack}-review-perf`). For unknown stacks, runs a minimal generic perf review.

## When to Use

- Slow endpoint / page / batch job / memory growth investigation
- Pre-release dedicated perf pass
- Database query, caching, or rendering optimization

**Not for:** General review (`task-code-review`), security (`task-code-review-security`), observability gaps (`task-code-review-observability`).

## Invocation

`/task-code-review-perf [<branch> | pr-<N>] [quick | standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review`, the parent passes the precondition handle and read-once diff/log; forward to the dispatched stack workflow.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

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

Forward arguments and stop. **If matched, skip Steps 4-5.**

### Step 4 - Generic Fallback (unknown stack only)

Use skill: `review-precondition-check` when running standalone (skip if the parent supplied a handle). Read diff and commit log once.

Determine `Scope` (`backend` / `frontend` / `fullstack`) from `stack-detect`'s `Stack Type` field, then cover the applicable categories:

**Database (backend / fullstack).** N+1 detection (recommend the ORM's eager-load mechanism), missing indexes on WHERE/ORDER BY, over-fetching, no leading-wildcard LIKE on large tables, pagination, query timeouts, connection-pool sizing. Use skill: `backend-db-indexing`.

**Concurrency (backend / fullstack).** Primitives appropriate for the runtime's threading model, no blocking I/O in cooperative async contexts, thread/worker pool sizing. Use skill: `architecture-concurrency`.

**Caching (backend / fullstack).** Cache-aside via framework abstraction, TTL on every entry with jitter, explicit invalidation strategy, deterministic key scheme, stampede protection on hot keys, DTOs cached (never ORM entities).

**Memory and I/O.** Streaming for large payloads, timeouts and circuit breakers on external calls, reused HTTP clients.

**Frontend (frontend / fullstack).** Unnecessary re-renders / change-detection cycles, heavy computation in render path, virtualization for long lists (>100), client-side caching, image optimization, lazy loading, route-level code splitting. Use skill: `frontend-performance`.

**Observability cross-check.** RED metrics on critical paths, correlation IDs propagated, latency histograms. Use skill: `ops-observability`.

Every finding states estimated impact (e.g., "N+1 adds ~200ms per request at 1K rows"), not just "this is slow". Separate quick wins from structural changes.

### Step 5 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`.

## Output Format

When Step 3 dispatched: the stack workflow owns the output. When fallback ran:

```markdown
## Performance Review Summary

**Stack Detected:** unknown (generic fallback applied)
**Scope:** Backend | Frontend | Fullstack
**Overall:** Clean | Issues Found - [High/Medium/Low counts]

## Findings

### High Impact

- **Location:** [file:line or component]
- **Issue:**
- **Impact:** [estimated effect with numbers]
- **Fix:** [specific change with code example if applicable]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: schema] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: if matched, stack workflow ran with arguments forwarded; Steps 4-5 skipped
- [ ] Step 4: if no match, every applicable category (DB / concurrency / caching / I/O / frontend / observability) covered; every finding states estimated impact; quick wins separated from structural changes
- [ ] Step 5: report written via `review-report-writer` (fallback path only)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Performance findings without estimated impact
- Premature optimization on cold paths
- Recommending caching without addressing invalidation
- Treating the fallback as equivalent to a stack workflow
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
