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

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack (the full stack-detect output, including `Stack Type`), precondition handle, read-once diff/log, and active depth: skip Steps 2-3 (Step 1 still applies: load behavioral-principles unless the spawning prompt inlined its whole Rules section and the disclosure block), run Step 4 on the supplied diff, return the subagent envelope defined in Output Format (a defect in a file the diff does not touch is drafted plain - the parent's verify attributes it), and skip Step 5 - the parent owns the report. Read-once covers the diff and log; at `deep`, touched files may still be read in full.

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
| React / Next.js      | `task-react-review-perf`   | `react`  |
| C# / Unity           | `task-unity-review-perf`   | `unity`  |
| Dart / Flutter       | `task-flutter-review-perf` | `flutter` |

Dispatch keys on the detection's primary `Language` / `Framework` pair; a secondary stack in `Additional` never dispatches. A row matches when both its language and its framework match - a trailing version never blocks a match (`Spring Boot 4.1`, `Unity 6000.3.21f1`) and the Ruby row matches `Rails` or `Ruby on Rails`, while another language or framework does (Kotlin / Spring Boot and Java / Micronaut take the fallback). Python matches under any framework; Node.js / TypeScript matches Language `JavaScript` or `TypeScript` with a server framework (NestJS, Express, Fastify, Koa, Hono) or `unknown`; a Framework naming Next.js (`React (Next.js)`, `Next.js 16.3 (App Router)`) takes the React row, and every other frontend framework (Vite, CRA, React Router, Remix, Vue, Angular, Svelte) matches no row. Exactly one outcome follows, its one-line announcement printed in chat before anything else (Step 4's precondition prompts and the user's answers follow it) and never part of `report_body`:

- Matched and installed: `Dispatching to task-rails-review-perf.` (substitute the target); invoke it with the arguments unchanged and stop - Steps 4-5 do not run.
- Matched, plugin not installed: `task-rails-review-perf is provided by the ruby plugin, which is not installed - running the generic perf review.` (substitute target and plugin); run Steps 4-5.
- No row: `No stack perf workflow for <Language> / <Framework> - running the generic perf review.`; run Steps 4-5.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` with `argument` (the invocation's target, if any), `base` (from `--base`, if given), and `report_type: review-perf` when running standalone (skip it when the parent supplied a handle); on failure, surface its message verbatim and stop; on success, print each handle `notes` entry in chat, one line each, before the report body (nothing when it has none; the handle itself stays internal). Standalone, capture `base_sha` / `head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`. Depth `standard` (default): review diff hunks plus immediate context - an untouched file may be read to confirm a figure a finding depends on (a pool size, a row count); `deep`: read each touched file in full. A defect the diff did not introduce, found in that read, is drafted like any other and verification attributes it; a file the diff does not touch is read only to confirm what a finding depends on, and a defect in it is drafted only when the diff newly reaches it. A requirement or acceptance criterion the diff's spec or commits name is evidence for a finding's Impact, never a finding by itself - criterion gaps belong to `task-code-review --req`.

**Round gate (standalone only).** The handle's `prior_checkpoint` is this lens's checkpoint (`review-perf-<sanitized head_short_name>.md`) frontmatter (omitted from the handle when the file does not exist), or `legacy` when its frontmatter is missing, unparseable, or another lens's or branch's. When it is a valid block whose `head_sha` equals the captured `head_sha`, whose `base_ref` equals the handle's, and whose `depth` the requested depth does not exceed (`deep` exceeds `standard`), print `No new commits since prior perf review.` and stop - no review, no report. Otherwise (a passing gate prints nothing) a valid block gives `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; absent or `legacy` gives `round: 1` and no `prior_head_sha` (Step 5 overwrites a legacy file). Then read `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>` once.

If the diff touches no application code (docs, tests, comments only - a comment-only hunk in application code counts - checked right after the round gate, or first thing on a subagent run, before loading any category atomic), skip the category review and verification: `Overall: Clean - diff contains no performance surface`, `## Findings` containing only `Diff contains no performance surface.`, `Findings verified: 0 confirmed, 0 reattributed, 0 unverified, 0 dropped`, no Next Steps, and the report is still written in Step 5. Round 2+ still reconciles: with nothing carried the report is as above; carried rows publish in their sections and Next Steps, `Overall` reads `Issues Found - <counts>`, and the no-surface note is the last line of `## Findings`. Subagent runs return the envelope with that note and no findings.

**Scope** comes from `stack-detect`'s `Stack Type` (`backend` / `frontend` / `fullstack`, displayed capitalised); a category scoped to a half the diff touches no file of goes N/A silently, and Scope still displays the `Stack Type`. When `git diff --name-only <base_ref>...<head_ref>` lists server-rendered UI under `backend` - view templates (`*.erb`, `*.heex`, `*.blade.php`, Django or Jinja templates) or Hotwire/Turbo or LiveView code - Scope displays `Backend + server-rendered UI` and the Frontend category runs. Atomics loaded below feed findings into this skill's template; their own output blocks are not emitted, and their mandated content folds into the finding's Issue/Impact/Fix: lock-risk lines, `backend-db-indexing`'s `(unverified - confirm with EXPLAIN)` and `(unverified - callers outside the reviewed files)` suffixes (either or both), `ops-observability`'s `(unverified - <file to check>)` suffix and `Signal:` value, `architecture-concurrency`'s `Risk:` values, and `backend-connection-pooling`'s `Verdict` with its `(assumed)` suffix and every assumption note its lines carry (`(assumed: <what>)` on Engine, Boundary and Surge, `(assumed)` on Pooler tier, an assumed `MaxConnectionsPercent` on Pooler backend). Every finding is re-rated on this file's Impact rubric - High when the cost is a user-visible slowdown on a request path or reaches a resource ceiling at the diff-visible scale, Medium when it is measurable but within the request budget, Low when it is theoretical at that scale (a `backend-db-indexing` High on a table too small for the miss to be user-visible is Medium here; an `ops-observability` gap is Medium at most, High only when it hides a resource-exhaustion path; a pooling `Unbounded` or `Breaches ...` verdict is High, `Over target at steady state` Medium, `Fits` no capacity finding; under any Verdict, each non-capacity Action (worker check, hazards, config drift, drain) is drafted as its own finding). A defect spanning categories publishes once, in the section of its dominant cost, its Fix owning all of them; one construct carrying several defects (a migration that both rewrites rows and builds an index under lock) likewise publishes once: each defect goes to verify as its own draft, and the rows verify keeps merge into one finding at the worst surviving impact, published at the first kept row's `file:line` with the highest kept `Label` and every kept row's distinct Annotation groups - provenance groups (`pre-existing`, `unverified`) first, then `mechanism` groups, each set in row order, its Issue naming each surviving defect, its Fix covering each and tagged `(structural)` when any part of it is.

**Database (backend / fullstack).** N+1 detection (recommend the ORM's eager-load mechanism), missing indexes on WHERE/ORDER BY, over-fetching, no leading-wildcard LIKE on large tables, pagination, query timeouts, connection-pool sizing. Use skill: `backend-db-indexing`; Use skill: `backend-connection-pooling` when the diff touches pool configuration, replica or autoscaler counts, worker concurrency, deploy surge settings, a pooler, or a per-request runtime's database access; a connection held across new I/O inside a transaction is drafted once, directly as a Database finding - a pooling `Hazards` entry and its `commit before the external call` Action for the same transaction fold into it rather than drafting a second.

**Concurrency (backend / fullstack).** Primitives appropriate for the runtime's threading model, no blocking I/O in cooperative async contexts, thread/worker pool sizing. Use skill: `architecture-concurrency`. A concurrency risk whose consequence is wrong data (a lost update, a double booking) is an `out of lens` line; one whose consequence is capacity (a stranded lock, a held connection) stays here.

**Caching (backend / fullstack).** Cache-aside via framework abstraction, TTL on every entry with jitter, explicit invalidation strategy, deterministic key scheme, stampede protection on hot keys, DTOs cached (never ORM entities).

**Memory and I/O (all scopes).** Streaming for large payloads, timeouts and circuit breakers on external calls, reused HTTP clients.

**Frontend (frontend / fullstack, or server-rendered UI).** Unnecessary re-renders / change-detection cycles and heavy computation in the render path; virtualization for long lists (>100); route-level code splitting and lazy loading of below-the-fold or modal-only components; images without dimensions, modern format, or lazy loading; render-blocking third-party scripts (analytics, chat, tag managers - routinely heavier than first-party code); client-side caching of repeated fetches. State impact against Core Web Vitals (LCP <= 2.5s, INP <= 200ms, CLS <= 0.1) where the diff supports it, and note in the Fix when a dedicated frontend pass is warranted. A Next.js project reaching this step (react plugin absent, or a subagent run): note in the Fix that `task-react-review-perf` owns the deeper frontend lens when installed.

**Observability cross-check (backend / fullstack).** RED metrics on critical paths, correlation IDs propagated, latency histograms. Use skill: `ops-observability`, scoped to those three; a finding it raises outside them (PII or secrets in logs) becomes an `out of lens` line owned by `task-code-review-security` or `task-code-review-observability`. Runs in subagent mode too - the parent dedups overlaps with `+obs`.

Every finding states estimated impact derived from diff-visible quantities (row counts, loop bounds, call counts) with assumptions stated - e.g., "N+1 adds ~200ms per request at 1K rows"; unit costs are declared assumptions, the scaling claim is what must hold. With no derivable quantity, state the scaling shape (per row, per request); observability cross-check findings state the diagnostic gap instead. Tag each Fix `(quick win)` (localized: a few lines, or one additive migration such as a new index) or `(structural)` (restructures a flow, moves work, or changes an existing schema, contract or infra topology). Impact sets the initial intent: High -> `[Must]`, Medium/Low -> `[Recommend]`; where `review-finding-verify` publishes a different `Label`, the published label governs every slot naming one.

**Verify findings (standalone only).** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, taking each row's `file:line` (a `no cite` row - its cell a bare file path or a construct name, not `path:line` - publishes at `<path>:1` of that file when the cell is a path, else of the touched file whose hunk raised it, keeping `_(unverified: no cite)_`; never a directory or a bare construct name - this `path:line` form replaces verify's bare-path heading, since reconcile parses only `path:line`), `Label`, and `Annotation` columns. The Summary's `Findings verified:` line is the atomic's Summary form of its tally, which counts its table only; the verify table stays internal.

**Reconcile (round 2+, standalone only).** After verification, project the prior report (the file at the handle's `report_path`) into reconcile's parse shape: a `## High-Impact Findings` section, one `### [Label] file:line` heading per finding - the label from its label line (with none, the label its impact section maps to under this lens's rule), the bare `file:line` prefix of its Location line, then its annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` splits into `_(pre-existing)_ _(newly reachable via X)_`; a label line's `_(carried from round <N>)_` follows as its own group) - each followed by an `Issue:` line with its Issue text. Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff -M --name-status <base_ref>...<head_ref>`, and `head_sha`; its output (table, any note lines, tally) renders verbatim as `## Prior Round Reconciliation`. A `Still open` or `Needs re-check` row this round's pass did not re-derive publishes in its prior impact section at its prior label - `[Blocker]`, `[High]`, `[Critical]` map to `[Must]`, any other label outside `[Must]` / `[Recommend]` to `[Recommend]`, and `[Praise]` is never carried - noted `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the label line's label, its Location the right side of reconcile's cell when that cell extends the prior cite with ` -> <new path>:<line>` (reconcile's rename form), else the prior `file:line`, its prior annotations kept except a prior `_(carried from round ...)_`, which this note replaces; its other block lines are copied from the prior report. A row this round re-derives - this round's pass drafted a finding on the same construct - publishes once, as this round's finding. The table keeps prior labels and citations verbatim.

### Step 5 - Write Report

Standalone only. Use skill: `review-report-writer` with `report_type: review-perf`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 4, `scope: +perf`, `depth` (default `standard`), `stack` (`<language>-<framework>` from `stack-detect`, versions dropped, lowercased, `#` written `sharp` and `+` written `p`, then each run of characters outside `[a-z0-9]` one `-`, leading and trailing `-` stripped (`python-fastapi`, `Vue (Nuxt)` on TypeScript -> `typescript-vue-nuxt`, `C#` / `Unity 6000.3.21f1` -> `csharp-unity`); a segment reported `unknown` dropped; `unknown` when both are), `mode: full`, `round` plus `prior_head_sha` from the round gate, and `pr_url` when the request carried a PR/MR URL, else `prior_checkpoint.pr_url` when present.

## Output Format

The fence delimits the template for display only; emit `report_body` as raw Markdown, never wrapped in a code fence. When Step 3 dispatched, the stack workflow owns the output.

Subagent runs return only `## Findings` with its impact sections and `out of lens` lines - no Summary, reconciliation, Next Steps, or file - and their Locations carry no verify annotation; the parent verifies and reconciles its merged set once.

Each finding block opens with its label line, `**[Must]**` or `**[Recommend]**`, before `Location`. A finding sits in the section of its **impact**; its label line and Next Steps entry carry its **published label** - a `**[Recommend]**` inside High after verify de-escalated a pre-existing finding is correct. Empty sections are omitted; within a section, `[Must]` first, then by `file:line`. Location is required (verify, the reconcile projection and Next Steps consume it); a multi-line construct cites its first line, and a two-site finding cites its first site and names the other after it. A standalone finding on a file absent from `git diff -M --name-status <base_ref>...<head_ref>` gets `_(pre-existing)_`, written first, unless its Annotation has a group opening `pre-existing` or `unverified` (a verify row whose Verdict is `Unverified`, a carried row keeping a prior `_(unverified: ...)_`, or a merged finding whose kept groups include one, gets no attribution) - the next round's reconcile reads it as provenance. A run with no new finding and no carried row returns `## Findings` containing `No performance issues found.` (any `out of lens` lines follow it) and omits Next Steps; carried rows with no new finding publish in their sections and Next Steps with no note; a docs/tests-only diff returns the no-surface note instead.

An `out of lens` line closes `## Findings` - after whichever section is last, with no line and no placeholder when there is no such defect - for each defect outside this lens that would break the build, or corrupt or expose data, naming its owner (`task-code-review-<lens>` for a sibling lens, `task-code-review` when no lens owns it); anything else outside the lens is left to `task-code-review`. These lines count in no Summary tally; `Overall` counts every published finding, carried ones included.

Next Steps (standalone only): one entry per published finding, `[Must]` first, then by `file:line`. `[Implement]` when the fix is local to the change; `[Delegate]` with `[scope: <owner>]` when another owner (schema, platform, infra, a dependency) must act. Either tag takes either label, and both keep the `file:line`.

Standalone runs emit the report body in chat, then the writer's confirmation line. When fallback ran standalone:

```markdown
## Performance Review Summary

- **Stack:** [`<Language> / <Framework>` as stack-detect's Stack slot renders it, versions kept as detected (`Python 3.12 / FastAPI 0.115`)] (generic fallback: no stack workflow | generic fallback: `<plugin>` plugin not installed)
- **Depth:** standard | deep
- **Scope:** Backend | Backend + server-rendered UI | Frontend | Fullstack
- **Overall:** Clean | Clean - diff contains no performance surface | Issues Found - <H> High / <M> Medium / <L> Low
- **Round:** [N]   {round 2+ only}
- **Findings verified:** [`review-finding-verify`'s Summary form: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`]

## Findings

### High Impact (a user-visible slowdown, or a resource-exhaustion path under expected load)

**[Must | Recommend]**{ _(carried from round <N>)_}
- **Location:** [file:line, then the component or boundary when that helps]{ the verify Annotation groups, standalone only}
- **Issue:**
- **Impact:** [estimated effect with numbers or stated scaling shape; for an observability cross-check finding, the diagnostic gap]
- **Fix:** [specific change, tagged (quick win) or (structural)]

### Medium Impact (measurable cost that does not yet threaten the request budget)

[Same structure]

### Low Impact (waste worth fixing when the area is next touched)

[Same structure]

- **out of lens:** file:line - [the defect in one sentence] - owner: [`task-code-review-<lens>` or `task-code-review`]   {one per such defect}

## Prior Round Reconciliation   {round 2+ standalone runs only}

[reconcile's output verbatim - table, any note lines, tally]

## Next Steps   {when at least one published finding}

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] file:line [scope: schema] - [one-line action]
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: `stack-detect` ran (subagent runs: parent-supplied detection accepted instead)
- [ ] Step 3: exactly one announcement printed before any output; on dispatch the arguments were forwarded and Steps 4-5 skipped (skipped entirely on subagent runs)
- [ ] Step 4: precondition called with `argument` / `base` / `report_type`; SHAs captured and the round gate decided (head, base and depth compared) before the diff was read; docs/tests/comments-only diff reported `Clean - diff contains no performance surface`, or `Issues Found` with carried rows on round 2+; every applicable category covered with a rubric-based impact and a (quick win)/(structural) tag; qualifying `out of lens` lines emitted; findings published with verify's `file:line`, `Label`, `Annotation`; round 2+ prior findings projected, reconciled, and carried; precondition, SHA capture, gate, verify and reconcile skipped on subagent runs
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the round-gate stop line printed, or a precondition failure surfaced verbatim with no report written (standalone fallback only)

## Avoid

- Writing a report when invoked as a subagent - the parent owns it
- Performance findings without estimated impact
- Premature optimization on cold paths
- Recommending caching without addressing invalidation
- Treating the fallback as equivalent to a stack workflow - install the matching stack plugin when one exists
- Emitting labels outside `[Must]` / `[Recommend]` in the findings sections (the reconciliation table preserves prior labels verbatim)
