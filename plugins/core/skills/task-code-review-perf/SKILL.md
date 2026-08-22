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

`/task-code-review-perf [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack (the full stack-detect output, including `Stack Type`), precondition handle, read-once diff/log, and active depth: skip Steps 2-3 (Step 1 still applies), run Step 4 on the supplied diff, return the subagent envelope defined in Output Format, and skip Step 5 - the parent owns the report. Read-once covers the diff and log; at `deep`, touched files may still be read in full.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to                |
| -------------------- | -------------------------- |
| Java / Spring Boot   | `task-spring-review-perf`  |
| Python               | `task-python-review-perf`  |
| Ruby / Rails         | `task-rails-review-perf`   |
| Node.js / TypeScript | `task-node-review-perf`    |
| Go / Gin             | `task-go-review-perf`      |
| React / Next.js      | `task-react-review-perf`   |

A row matches only when the detected framework matches it (Java / Micronaut does not match Java / Spring Boot - use the fallback); a row named by language alone (Python) matches that language under any framework. Forward arguments and stop. **If matched, skip Steps 4-5.** If the matched workflow is unavailable (stack plugin not installed), tell the user which plugin provides it, then run Steps 4-5.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` with the invocation's target and any `--base` override when running standalone (skip if the parent supplied a handle). Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full.

**Round gate (standalone only).** Before reviewing, check `review-perf-<branch>.md` (writer filename rules; the handle's `prior_checkpoint` is keyed to the general review report - never use it here). If it exists with valid frontmatter, its `head_sha` equals the current head, and the requested depth does not exceed its `depth` (`deep` exceeds `standard`), print `No new commits since prior perf review.` and stop - no review, no report. Otherwise set `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; absent file -> `round: 1`, no `prior_head_sha`. Then read the diff and commit log once.

Determine `Scope` (`backend` / `frontend` / `fullstack`) from `stack-detect`'s `Stack Type` field, then cover the applicable categories. Atomics loaded here feed findings into this skill's template; their own output blocks are not emitted, and atomic-mandated content (lock-risk lines, `(unverified - confirm with EXPLAIN)` markers) folds into the finding's Impact/Fix fields. A defect spanning categories (one restructure fixing concurrency and caching at once) publishes once, its Fix owning all of them.

**Database (backend / fullstack).** N+1 detection (recommend the ORM's eager-load mechanism), missing indexes on WHERE/ORDER BY, over-fetching, no leading-wildcard LIKE on large tables, pagination, query timeouts, connection-pool sizing. Use skill: `backend-db-indexing`.

**Concurrency (backend / fullstack).** Primitives appropriate for the runtime's threading model, no blocking I/O in cooperative async contexts, thread/worker pool sizing. Use skill: `architecture-concurrency`.

**Caching (backend / fullstack).** Cache-aside via framework abstraction, TTL on every entry with jitter, explicit invalidation strategy, deterministic key scheme, stampede protection on hot keys, DTOs cached (never ORM entities).

**Memory and I/O (all scopes).** Streaming for large payloads, timeouts and circuit breakers on external calls, reused HTTP clients.

**Frontend (frontend / fullstack).** Unnecessary re-renders / change-detection cycles, heavy computation in render path, virtualization for long lists (>100), client-side caching, image optimization, lazy loading, route-level code splitting. Use skill: `frontend-performance`.

**Observability cross-check (backend / fullstack).** RED metrics on critical paths, correlation IDs propagated, latency histograms. Use skill: `ops-observability`. Runs in subagent mode too - the parent dedups overlaps with `+obs`.

Every finding states estimated impact derived from diff-visible quantities (row counts, loop bounds, call counts) with assumptions stated - e.g., "N+1 adds ~200ms per request at 1K rows"; unit costs are declared assumptions, not measurements - the scaling claim is what must hold. When no quantity is derivable, state the scaling shape (per row, per request) instead of inventing numbers; observability cross-check findings state the diagnostic gap in the Impact slot instead of a perf estimate. Tag each finding's Fix `(quick win)` (localized, a few lines) or `(structural)` (restructures a flow, moves work, or changes schema/infra) - sections order by impact alone. Next Steps map impact to intent (High -> `[Must]`, Medium/Low -> `[Recommend]`) and tag each step `[Implement]` (localized fix) or `[Delegate]` (cross-cutting, schema, platform, or infra-owned).

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and fill the Summary's `Findings verified:` line with its tally - the verify table itself stays internal. On round 2+, after verification, re-project the prior report's findings into reconcile's parse shape - a `## High-Impact Findings` section, one `### [Label] file:line` heading per finding with its Issue line as the smell - then Use skill: `review-prior-findings-reconcile` with that projection, the diff, and `git diff --name-status <base_ref>...<head_ref>`. Its table and tally render as `## Prior Round Reconciliation` between Findings and Next Steps; unresolved rows carry into this lens's Findings sections at their prior label, noted `carried from round <N>` on the label line. Subagent runs skip both - the parent verifies and reconciles its own merged set once.

### Step 5 - Write Report

Standalone only - subagent runs return findings to the parent instead. Use skill: `review-report-writer` with `report_type: review-perf` and every required input: `report_body`, `branch` (from the handle), the handle's refs, `base_sha` / `head_sha` via `git rev-parse`, `scope: +perf`, `depth` as invoked (default `standard`), `stack` from `stack-detect` (kebab-case language-framework, versions dropped, or `unknown`), `mode: full`, and `round` plus `prior_head_sha` from the Step 4 round gate.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

When Step 3 dispatched: the stack workflow owns the output. Subagent runs return the `## Findings` heading and its impact sections only - Summary, Prior Round Reconciliation, Next Steps, and the report file are standalone-only. In every mode each finding block opens with its label on its own line, `**[Must]**` (High) or `**[Recommend]**` (Medium/Low), before `Location`, and empty impact sections are omitted. Verify annotations (`_(pre-existing)_`, `(unverified ...)`) sit on the `Location` line (standalone only - subagent runs skip verification). A clean run in either mode returns `## Findings` containing `No performance issues found.`. Standalone runs emit the report body in chat, then the writer's confirmation line. When fallback ran standalone:

```markdown
## Performance Review Summary

- **Stack Detected:** [detected stack, or unknown] (generic fallback applied)
- **Scope:** Backend | Frontend | Fullstack
- **Overall:** Clean | Issues Found - [High/Medium/Low counts]
- **Findings verified:** [N] confirmed, [M] reattributed, [K] dropped

## Findings

### High Impact

**[Must]**
- **Location:** [file:line or component]
- **Issue:**
- **Impact:** [estimated effect with numbers or stated scaling shape]
- **Fix:** [specific change, tagged (quick win) or (structural)]

### Medium Impact

[Same structure]

### Low Impact

[Same structure]

_Omit sections with no findings. If all are omitted, state "No performance issues found." and omit Next Steps._

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: schema] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran (subagent runs: parent-supplied detection accepted instead)
- [ ] Step 3: if matched and installed, stack workflow ran with arguments forwarded; Steps 4-5 skipped (skipped entirely on subagent runs)
- [ ] Step 4: if no dispatch, round gate decided before any review; every applicable category (DB / concurrency / caching / I/O / frontend / observability) covered; every finding states estimated impact and a (quick win)/(structural) tag; prior findings reconciled on round 2+
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the round-gate stop line printed (standalone fallback only; subagent runs return findings to the parent)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Writing a report when invoked as a subagent - the parent owns it
- Performance findings without estimated impact
- Premature optimization on cold paths
- Recommending caching without addressing invalidation
- Treating the fallback as equivalent to a stack workflow - install the matching stack plugin when one exists
- Emitting labels outside `[Must]` / `[Recommend]`
