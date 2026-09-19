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

**Not for:** General review (`task-code-review`), security (`task-code-review-security`), observability gaps (`task-code-review-observability`), reliability (`task-code-review-reliability`).

## Invocation

`/task-code-review-perf [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack (the full stack-detect output, including `Stack Type`), precondition handle, read-once diff/log, and active depth: skip Steps 2-3 (Step 1 still applies), run Step 4 on the supplied diff, return the subagent envelope defined in Output Format, and skip Step 5 - the parent owns the report. Read-once covers the diff and log; at `deep`, touched files may still be read in full.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to                | Plugin   |
| -------------------- | -------------------------- | -------- |
| Java / Spring Boot   | `task-spring-review-perf`  | `java`   |
| Python               | `task-python-review-perf`  | `python` |
| Ruby / Rails         | `task-rails-review-perf`   | `ruby`   |
| Node.js / TypeScript | `task-node-review-perf`    | `node`   |
| Go / Gin             | `task-go-review-perf`      | `go`     |
| React / Next.js / Vite | `task-react-review-perf` | `react`  |

A row matches only when the detected framework matches it (Java / Micronaut does not match Java / Spring Boot - use the fallback); a row named by language alone (Python) matches that language under any framework; the Node.js / TypeScript row matches Language `JavaScript` or `TypeScript` with a server framework (NestJS, Express, Fastify, Koa, Hono) or none; `React (...)` takes the React row, and another frontend framework (Vue, Angular, Svelte) matches no row. Dispatch keys on the detection's primary `Language`/`Framework` pair; a secondary stack in `Additional` never dispatches. Announce the dispatch in one line (`Dispatching to task-rails-review-perf.` - substitute the target), forward the arguments unchanged, and stop. **If matched, skip Steps 4-5.** If the matched workflow is unavailable (stack plugin not installed), announce it in one line (`task-rails-review-perf is provided by the ruby plugin, which is not installed - running the generic perf review.` - substitute the row's target and plugin), then run Steps 4-5. A detected stack matching no row at all falls through to the Step 4 generic fallback - announce it in one line (`No stack perf workflow for <stack> - running the generic perf review.`, `<stack>` = the detection's Language / Framework pair), then run it.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` with the invocation's target, any `--base` override, and `report_type: review-perf` when running standalone (skip if the parent supplied a handle); on failure, surface its message verbatim and stop. Standalone, capture `base_sha` / `head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`. Depth `standard` (default): review diff hunks plus immediate context - an untouched file may be read to confirm a figure a finding depends on (a pool size, a row count); `deep`: read each touched file in full.

**Round gate (standalone only).** Before reviewing, decide the round from the handle: with `report_type: review-perf` passed, its `report_path` is this lens's checkpoint (`review-perf-<sanitized head_short_name>.md`) and its `prior_checkpoint` is that file's frontmatter - or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch. If `prior_checkpoint` is a valid block, its `head_sha` equals the captured `head_sha`, and the requested depth does not exceed its `depth` (`deep` exceeds `standard`), print `No new commits since prior perf review.` and stop - no review, no report. Otherwise set `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 5 write overwrites the file) -> `round: 1`, no `prior_head_sha`. Then read the diff and commit log once.

If the diff touches no application code (docs, tests, comments only - check right after the round gate, or first thing on a subagent run, before loading any category atomic), skip the category review and the verify skill: report `Overall: Clean - diff contains no performance surface`, render `## Findings` containing only the line `Diff contains no performance surface.`, set `Findings verified: 0 confirmed, 0 reattributed, 0 unverified, 0 dropped`, omit Next Steps, and still write the report in Step 5. On round 2+ the prior report is still reconciled: with nothing carried the report is as above; with carried rows they publish in their sections and Next Steps, `Overall` reads `Issues Found - <counts>`, and the no-surface note is the last line of `## Findings`. Subagent runs return the envelope with no findings and that note instead.

Determine `Scope` from `stack-detect`'s `Stack Type` field (`backend` / `frontend` / `fullstack`, displayed capitalised), then cover the applicable categories; when the diff carries server-rendered UI under `backend`, Scope displays `Backend + server-rendered UI` and the Frontend category runs. Atomics loaded here feed findings into this skill's template; their own output blocks are not emitted, and atomic-mandated content (lock-risk lines, the `(unverified - <confirm with EXPLAIN | callers outside the reviewed files | both>)` suffix, `architecture-concurrency`'s `Risk:` values, `ops-observability`'s `Signal:` value) folds into the finding's Issue/Impact/Fix fields. An atomic's severity does not carry over: every finding is re-rated on this file's Impact rubric (a `backend-db-indexing` High on a table too small for the miss to be user-visible is Medium here; an `ops-observability` gap is Medium at most, High only when it hides a resource-exhaustion path). A defect spanning categories (one restructure fixing concurrency and caching at once) publishes once, in the section of its dominant cost, its Fix owning all of them.

**Database (backend / fullstack).** N+1 detection (recommend the ORM's eager-load mechanism), missing indexes on WHERE/ORDER BY, over-fetching, no leading-wildcard LIKE on large tables, pagination, query timeouts, connection-pool sizing. Use skill: `backend-db-indexing`; Use skill: `backend-connection-pooling` when the diff touches pool configuration or per-request connection use.

**Concurrency (backend / fullstack).** Primitives appropriate for the runtime's threading model, no blocking I/O in cooperative async contexts, thread/worker pool sizing. Use skill: `architecture-concurrency`.

**Caching (backend / fullstack).** Cache-aside via framework abstraction, TTL on every entry with jitter, explicit invalidation strategy, deterministic key scheme, stampede protection on hot keys, DTOs cached (never ORM entities).

**Memory and I/O (all scopes).** Streaming for large payloads, timeouts and circuit breakers on external calls, reused HTTP clients.

**Frontend (frontend / fullstack).** Unnecessary re-renders / change-detection cycles and heavy computation in the render path; virtualization for long lists (>100); route-level code splitting and lazy loading of below-the-fold or modal-only components; images without dimensions, modern format, or lazy loading; render-blocking third-party scripts (analytics, chat, tag managers - routinely heavier than first-party code); client-side caching of repeated fetches. State impact against Core Web Vitals (LCP <= 2.5s, INP <= 200ms, CLS <= 0.1) where the diff supports it, and note in the Fix when a dedicated frontend pass is warranted. Server-rendered UI (Phoenix LiveView, Hotwire/Turbo, Blade, Django or Rails templates) is frontend surface: cover these categories for it even when `Stack Type` is `backend`. A React project reaching this step did not dispatch (no row matched, or the plugin is absent), so cover these categories here and note in the Fix that `task-react-review-perf` owns the deeper frontend lens when installed.

**Observability cross-check (backend / fullstack).** RED metrics on critical paths, correlation IDs propagated, latency histograms. Use skill: `ops-observability`, scoped to those three - a finding it raises outside them (PII or secrets in logs) is not a perf finding - it becomes an `out of lens` line owned by `+sec` or `+obs`. Runs in subagent mode too - the parent dedups overlaps with `+obs`.

Every finding states estimated impact derived from diff-visible quantities (row counts, loop bounds, call counts) with assumptions stated - e.g., "N+1 adds ~200ms per request at 1K rows"; unit costs are declared assumptions, not measurements - the scaling claim is what must hold. When no quantity is derivable, state the scaling shape (per row, per request) instead of inventing numbers; observability cross-check findings state the diagnostic gap in the Impact slot instead of a perf estimate. Tag each finding's Fix `(quick win)` (localized: a few lines, or one additive migration such as a new index) or `(structural)` (restructures a flow, moves work, or changes an existing schema, contract or infra topology) - sections order by impact alone. Impact assigns each finding an initial intent (High -> `[Must]`, Medium/Low -> `[Recommend]`); where `review-finding-verify` publishes a different `Label`, the published label governs every slot naming one. A defect outside this lens that would break the build, or corrupt or expose data, becomes an `out of lens` line (shape in Output Format). Next Steps carry each finding published label and tag each step `[Implement]` (localized fix) or `[Delegate]` (cross-cutting, schema, platform, or infra-owned).

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns; the Summary's `Findings verified:` line is the Summary form the atomic prescribes, filled from its tally (`<N> confirmed, <M> reattributed, <U> unverified, <K> dropped`, plus its false-positive/resolved split when emitted) - the verify table itself stays internal. On round 2+, after verification, re-project the prior report's findings (the file at the handle's `report_path`) into reconcile's parse shape - a `## High-Impact Findings` section, one `### [Label] file:line` heading per finding from its label line (or, when the prior report wrote no label line, the label its severity section maps to under this lens's severity rule - reconcile's verbatim rule has nothing to preserve there) and the `file:line` prefix of its Location line (trailing component prose stays out of the heading), keeping a `_(pre-existing)_` annotation on the heading (reconcile splits untouched files on it; verify's combined `_(pre-existing; newly reachable via ...)_` is written as two groups, `_(pre-existing)_ _(newly reachable via ...)_`), with its Issue line as the smell - then Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, and `head_sha`. Its table and tally render as `## Prior Round Reconciliation` between Findings and Next Steps; unresolved rows carry into their prior impact sections at their prior label, noted `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the label on its label line, its prior Location annotation kept; the reconciliation table row and its Next Steps entry are its only other appearances. A prior label outside `[Must]` / `[Recommend]` (`[Blocker]`, `[High]`, `[Question]` in a legacy report) stays verbatim in that table, which reconcile owns, and maps before it is published in a findings section: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; `[Suggestion]`, `[Nitpick]`, `[Question]`, `[Medium]`, `[Low]`, and any unrecognised label -> `[Recommend]`; `[Praise]` rows are never carried. A carried finding this round's own pass re-derives publishes once, in the findings sections, not twice. The table preserves each prior citation exactly; the published finding carries the corrected `file:line` when verification found the prior cite stale. Subagent runs skip both - the parent verifies and reconciles its own merged set once.

### Step 5 - Write Report

Standalone only - subagent runs return findings to the parent instead. Use skill: `review-report-writer` with `report_type: review-perf` and every required input: `report_body`, `branch` (the handle's `head_short_name`), the handle's refs, `base_sha` / `head_sha` from Step 4, `pr_url` when the request text carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present, `scope: +perf`, `depth` as invoked (default `standard`), `stack` from `stack-detect` (kebab-case `<language>-<framework>`, versions dropped; drop a segment reported unknown; `unknown` only when detection failed entirely), `mode: full`, and `round` plus `prior_head_sha` from the Step 4 round gate.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

When Step 3 dispatched: the stack workflow owns the output. Subagent runs return the `## Findings` heading, its impact sections, and any `out of lens` lines only - Summary, Prior Round Reconciliation, Next Steps, and the report file are standalone-only. In every mode each finding block opens with its label on its own line, `**[Must]**` or `**[Recommend]**`, before `Location`, and empty impact sections are omitted. A finding sits in the section matching its **impact**; its label line and its Next Steps entry carry its **published label**. The two diverge whenever verification de-escalated a pre-existing finding - a `**[Recommend]**` inside a High section is correct, not a mismatch to fix. A defect outside this lens that would break the build, or corrupt or expose data gets one `out of lens` line each at the end of `## Findings`, so it is not silently dropped; anything else outside the lens is left to `task-code-review`. Verify annotations (the Annotation column: `_(pre-existing)_`, `_(pre-existing; newly reachable via ...)_`, `_(unverified: ...)_`, `_(mechanism: ...)_`) sit on the `Location` line (standalone only - subagent runs skip verification). A run that reviewed and found nothing returns `## Findings` containing `No performance issues found.` in either mode; a docs/tests-only diff returns the no-surface note instead, per Step 4. Standalone runs emit the report body in chat, then the writer's confirmation line. When fallback ran standalone:

```markdown
## Performance Review Summary

- **Stack Detected:** [kebab-case `<language>-<framework>`, versions dropped - the same string passed as the writer `stack` input; or `unknown`] (generic fallback: no stack workflow) | (generic fallback: `<plugin>` plugin not installed)
- **Depth:** standard | deep
- **Scope:** Backend | Backend + server-rendered UI | Frontend | Fullstack
- **Overall:** Clean [- reason, e.g. `diff contains no performance surface`] | Issues Found - <H> High / <M> Medium / <L> Low
- **Round:** [N]   {round 2+ only}
- **Findings verified:** [from `review-finding-verify`'s tally, in its Summary form: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`]

## Findings

### High Impact (a user-visible slowdown, or a resource-exhaustion path under expected load)

**[Must | Recommend]**{ _(carried from round <N>)_}
- **Location:** [file:line - required, so verification, the reconcile projection and Next Steps can all consume it; name the component or boundary after it when that helps]{ the verify Annotation, standalone only}
- **Issue:**
- **Impact:** [estimated effect with numbers or stated scaling shape]
- **Fix:** [specific change, tagged (quick win) or (structural)]

### Medium Impact (measurable cost that does not yet threaten the request budget)

[Same structure]

### Low Impact (waste worth fixing when the area is next touched)

[Same structure]

_Omit sections with no findings. If all are omitted, state "No performance issues found." (before any `out of lens` line) and omit Next Steps._

- **out of lens:** file:line - [the defect in one sentence, and the lens that owns it]   {one per such defect, only when it would break the build or corrupt or expose data}


## Prior Round Reconciliation

[table and tally from `review-prior-findings-reconcile` - round 2+ standalone runs only; omit the section otherwise]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: schema] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent runs: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: `stack-detect` ran (subagent runs: parent-supplied detection accepted instead)
- [ ] Step 3: if matched and installed, dispatch announced and stack workflow ran with arguments forwarded, Steps 4-5 skipped; if not installed or no row matched, the announcement printed and fallback ran (skipped entirely on subagent runs)
- [ ] Step 4: if no dispatch, SHAs captured; round gate decided from the handle (`report_type: review-perf`) before the diff was read; `out of lens` lines emitted for qualifying defects outside the lens; docs/tests-only diff reported Clean; every applicable category (DB / concurrency / caching / I/O / frontend / observability) covered; every finding states a rubric-based impact and a (quick win)/(structural) tag; prior findings projected into reconcile's parse shape and reconciled on round 2+; the round gate, `review-finding-verify` (whose tally fills the `Findings verified:` Summary line) and reconciliation are standalone-only - subagent runs skip all three
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the round-gate stop line printed, or a precondition failure surfaced verbatim with no report written (standalone fallback only; subagent runs return findings to the parent)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Writing a report when invoked as a subagent - the parent owns it
- Performance findings without estimated impact
- Premature optimization on cold paths
- Recommending caching without addressing invalidation
- Treating the fallback as equivalent to a stack workflow - install the matching stack plugin when one exists
- Emitting labels outside `[Must]` / `[Recommend]` in the findings sections (the reconciliation table preserves prior labels verbatim)
