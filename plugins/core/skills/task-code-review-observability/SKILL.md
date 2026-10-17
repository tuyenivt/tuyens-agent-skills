---
name: task-code-review-observability
description: Observability review entry point: structured logging, RED metrics, distributed tracing, SLOs. Detects stack and dispatches workflow.
metadata:
  category: review
  tags: [observability, logging, metrics, tracing, slo, multi-stack, router]
  type: workflow
user-invocable: true
---

# Observability Review (Router)

Detects the project stack and delegates to the matching stack-specific observability review (`task-{stack}-review-observability`). When no stack workflow matches, runs a minimal generic review driven by `ops-observability`.

## When to Use

- Pre-release observability check for a new service or major feature
- Post-incident review when diagnosis was slow or evidence missing
- OpenTelemetry / structured logging / SLO-based alerting adoption
- Audit of a service whose production behavior is opaque

**Not for:** General code review (`task-code-review`), security (`task-code-review-security`), perf with a known bottleneck (`task-code-review-perf`), reliability (`task-code-review-reliability`).

## Invocation

`/task-code-review-observability [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack (the full stack-detect output, including `Stack Type`), precondition handle, read-once diff/log, and active depth: skip Steps 2-3 (Step 1 still applies), run Step 4 on the supplied diff, return the subagent envelope defined in Output Format, and skip Step 5 - the parent owns the report. Read-once covers the diff and log; at `deep`, touched files may still be read in full.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to                         | Plugin   |
| -------------------- | ----------------------------------- | -------- |
| Java / Spring Boot   | `task-spring-review-observability`  | `java`   |
| Python               | `task-python-review-observability`  | `python` |
| Ruby / Rails         | `task-rails-review-observability`   | `ruby`   |
| Node.js / TypeScript | `task-node-review-observability`    | `node`   |
| Go / Gin             | `task-go-review-observability`      | `go`     |
| React / Next.js      | `task-react-review-observability`   | `react`  |

Dispatch keys on the detection's primary `Language` / `Framework` pair; a secondary stack in `Additional` never dispatches. A row matches when both its language and its framework match - a trailing version never blocks a match (`Spring Boot 4.1`), while another language or framework does (Kotlin / Spring Boot and Java / Micronaut take the fallback). Python matches under any framework; Node.js / TypeScript matches Language `JavaScript` or `TypeScript` with a server framework (NestJS, Express, Fastify, Koa, Hono) or `unknown`; a Framework naming Next.js (`React (Next.js)`, `Next.js 16.3 (App Router)`) takes the React row, and every other frontend framework (Vite, CRA, React Router, Remix, Vue, Angular, Svelte) matches no row. Exactly one outcome follows, its one-line announcement printed in chat before anything else and never part of `report_body`:

- Matched and installed: `Dispatching to task-rails-review-observability.` (substitute the target); invoke it with the arguments unchanged and stop - Steps 4-5 do not run.
- Matched, plugin not installed: `task-rails-review-observability is provided by the ruby plugin, which is not installed - running the generic observability review.` (substitute target and plugin); run Steps 4-5.
- No row: `No stack observability workflow for <Language> / <Framework> - running the generic observability review.`; run Steps 4-5.

### Step 4 - Generic Fallback (no dispatch match)

Use skill: `review-precondition-check` with `argument` (the invocation's target, if any), `base` (from `--base`, if given), and `report_type: review-observability` when running standalone (skip it when the parent supplied a handle); on failure, surface its message verbatim and stop; on success, print each handle `notes` entry in chat, one line each, before the report body. Standalone, capture `base_sha` / `head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`. Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full and include the SLO category below. A defect the diff did not introduce, found in that read, is drafted like any other and verification attributes it; a file the diff does not touch is read only to confirm what a finding depends on, and a defect in it is drafted only when the diff newly reaches it.

**Scope** comes from `stack-detect`'s `Stack Type` (`backend` / `frontend` / `fullstack`, displayed capitalised); `fullstack` activates both the backend- and frontend-scoped rows. When `git diff --name-only <base_ref>...<head_ref>` lists server-rendered UI under `backend` - view templates (`*.erb`, `*.heex`, `*.blade.php`, Django or Jinja templates) or Hotwire/Turbo or LiveView code - the frontend-scoped rows run too and Scope displays `Backend + server-rendered UI`.

**Round gate (standalone only).** The handle's `prior_checkpoint` is this lens's checkpoint (`review-observability-<sanitized head_short_name>.md`) frontmatter, or `legacy` when that is missing, unparseable, or another lens's or branch's. Stop with `No new commits since prior observability review.` - no review, no report - only when it is a valid block whose `head_sha` equals the captured `head_sha`, whose `base_ref` equals the handle's, whose `depth` the requested depth does not exceed (`deep` exceeds `standard`), and whose `stack` equals this run's writer `stack` string while the prior report's Summary `Scope` equals this run's. A differing `stack` or `Scope` alone is new work: proceed and fill `Detection change:`. Otherwise a valid block gives `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; absent or `legacy` gives `round: 1` and no `prior_head_sha` (Step 5 overwrites a legacy file). Then read `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>` once.

If the diff touches no instrumentable code (docs, tests, comments only - checked right after the round gate, or first thing on a subagent run, before loading any category atomic), skip the category review and verification: `Overall: Adequate - diff contains no instrumentable surface`, `## Findings` containing only `Diff contains no instrumentable surface.`, `Findings verified: 0 confirmed, 0 reattributed, 0 unverified, 0 dropped`, no Next Steps, and the report is still written in Step 5. Round 2+ still reconciles: with nothing carried the report is as above; carried rows publish in their sections and Next Steps, `Overall` reads `Gaps Found - <counts>`, and the no-surface note is the last line of `## Findings`. Subagent runs return the envelope with that note and no findings.

Use skill: `ops-observability`, naming the axes of the rows active for this run's Scope and depth (SLO and alerting only at `deep`) - the primary source of findings and of the patterns behind every row below, except where a row states something it does not carry (the Frontend observability row, the Context propagation row's browser `traceparent` clause, and the Metrics row's high-cardinality-label rule); there the row text is the pattern. Each `ops-observability` gap is one finding; two Signal values at one site are two findings.

| Category                  | Scope            | Must cover                                                                            |
| ------------------------- | ---------------- | ------------------------------------------------------------------------------------- |
| Structured logging        | all              | JSON/structured format, mandatory fields, log levels, no PII/secrets, no hot-loop spam |
| Metrics                   | backend          | RED on every entry point (API endpoint, queue consumer, scheduled job), latency histograms, a business-metric counter per critical operation, an absence alert on scheduled or event-driven work, no high-cardinality labels |
| Distributed tracing       | backend          | Entry spans, DB child spans carrying the query template and HTTP child spans the target service, one propagation family carried end-to-end (W3C `traceparent`, forwarding `tracestate` when received; B3 single or multi-header; or `uber-trace-id`), sampling policy |
| Context propagation       | all              | Framework request context, background-job context extraction, async carry-forward; under frontend scope, `traceparent` on the browser's outbound API calls |
| Frontend observability    | frontend         | Error tracking with source maps, global handlers, Core Web Vitals, no PII             |
| SLO and alerting          | backend, deep only | SLI per critical path (one user-facing journey end to end, not each hop), SLO target + window + error budget, burn-rate alerts on symptoms not causes (absolute-count alerts for a path below a few hundred events per window); triggered when the diff adds or changes a critical path. Definitions only - a missing error signal belongs to Metrics |

Severity follows the Findings section definitions in Output Format; `ops-observability`'s ratings inform but do not override, except that a gap the definitions do not name takes the tier `ops-observability` gives it. A critical path with no SLO is High -> `[Must]` at deep depth (its failure goes undetected); a non-critical path raises none. Every finding states what becomes invisible without the missing signal (a `removal` finding states who can read the exposed value; a `misuse` or `replacement` finding states the noise or the missed symptom it causes). Severity sets the initial intent: High -> `[Must]`, Medium/Low -> `[Recommend]`; where `review-finding-verify` publishes a different `Label`, the published label governs every slot naming one.

**Verify findings (standalone only).** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, taking each row's `file:line` (a `-` cell - verify's `no cite` row - publishes at `<path>:1` of the file the drafted claim names, else of the touched file whose hunk raised it, keeping `_(unverified: no cite)_`; never a directory), `Label`, and `Annotation` columns. The Summary's `Findings verified:` line is the atomic's Summary form of its tally, which counts its table only; the verify table stays internal.

**Reconcile (round 2+, standalone only).** After verification, project the prior report (the file at the handle's `report_path`) into reconcile's parse shape: a `## High-Impact Findings` section, one `### [Label] file:line` heading per finding - the label from its label line (with none, the label its severity section maps to under this lens's rule), the bare `file:line` prefix of its Location line, then its annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` splits into `_(pre-existing)_ _(newly reachable via X)_`; a label line's `_(carried from round <N>)_` follows as its own group) - each followed by an `Issue:` line carrying its `Missing:` text, since reconcile reads the smell from `Issue:` or `Improvement:` only. Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, and `head_sha`; its output (table, any note lines, tally) renders verbatim as `## Prior Round Reconciliation`. A `Still open` or `Needs re-check` row this round's pass did not re-derive publishes in its prior severity section at its prior label - `[Blocker]`, `[High]`, `[Critical]` map to `[Must]`, any other label outside `[Must]` / `[Recommend]` to `[Recommend]`, and `[Praise]` is never carried - noted `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the label line's label, its Location the right side of reconcile's cell when that cell extends the prior cite with ` -> <new path>:<line>` (reconcile's rename form), else the prior `file:line`, its prior annotations kept except a prior `_(carried from round ...)_`, which this note replaces. A row this round re-derives - this round's pass drafted a finding on the same construct - publishes once, as this round's finding. The table keeps prior labels and citations verbatim.

### Step 5 - Write Report

Standalone only. Use skill: `review-report-writer` with `report_type: review-observability`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 4, `scope: +obs`, `depth` (default `standard`), `stack` (`<language>-<framework>` from `stack-detect`, versions dropped, lowercased, `#` written `sharp` and `+` written `p`, then each run of characters outside `[a-z0-9]` one `-`, leading and trailing `-` stripped (`python-fastapi`, `Vue (Nuxt)` on TypeScript -> `typescript-vue-nuxt`, `C#` / `Unity 6000.3.21f1` -> `csharp-unity`); a segment reported `unknown` dropped; `unknown` when both are), `mode: full`, `round` plus `prior_head_sha` from the round gate, and `pr_url` when the request carried a PR/MR URL, else `prior_checkpoint.pr_url` when present.

## Output Format

The fence delimits the template for display only; emit `report_body` as raw Markdown, never wrapped in a code fence. When Step 3 dispatched, the stack workflow owns the output.

Subagent runs return only `## Findings` with its severity sections and `out of lens` lines - no Summary, reconciliation, Next Steps, or file - and their Locations carry no verify annotation; the parent verifies and reconciles its merged set once.

Each finding block opens with its label line, `**[Must]**` or `**[Recommend]**`, before `Location`. A finding sits in the section of its **severity**; its label line and Next Steps entry carry its **published label** - a `**[Recommend]**` inside High after verify de-escalated a pre-existing finding is correct. Empty sections are omitted; within a section, `[Must]` first, then by `file:line`. Location is required (verify, the reconcile projection and Next Steps consume it); a multi-line construct cites its first line, and a multi-site gap cites `ops-observability`'s anchor (the entry point) with the other sites in parentheses. A standalone finding on a file absent from `git diff --name-status <base_ref>...<head_ref>` whose Annotation has no group opening `pre-existing` gets `_(pre-existing)_`, written first - the next round's reconcile reads it as provenance. A run that reviewed and found nothing returns `## Findings` containing `No observability gaps found.` and omits Next Steps; a docs/tests-only diff returns the no-surface note instead.

An `out of lens` line closes `## Findings` for each defect outside this lens that would break the build, or corrupt or expose data, naming its owner (`task-code-review` when no lens owns it); anything else outside the lens is left to `task-code-review`. These lines count in no Summary tally; `Overall` counts every published finding, carried ones included.

Next Steps (standalone only): one entry per published finding, `[Must]` first, then by `file:line`. `[Implement]` when the fix is local to the change; `[Delegate]` with `[scope: <owner>]` when another owner (platform, infra, another service) must act. Either tag takes either label, and both keep the `file:line`.

Standalone runs emit the report body in chat, then the writer's confirmation line. When fallback ran standalone:

```markdown
## Observability Review Summary

- **Stack Detected:** [the writer `stack` string] (generic fallback: no stack workflow | generic fallback: `<plugin>` plugin not installed)
- **Depth:** standard | deep
- **Scope:** Backend | Backend + server-rendered UI | Frontend | Fullstack
- **Overall:** Adequate | Adequate - diff contains no instrumentable surface | Gaps Found - <H> High / <M> Medium / <L> Low
- **Round:** [N]   {round 2+ only}
- **Detection change:** [the checkpoint's `stack` or the prior Summary's `Scope` -> this run's, and any category it adds or drops]   {round 2+ only, when either differs}
- **Findings verified:** [`review-finding-verify`'s Summary form: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`]

## Findings

### High Severity (would prevent detection of a production failure, or puts secret or personal data in logs or exception messages)

**[Must | Recommend]**{ _(carried from round <N>)_}
- **Location:** [file:line, then the component or boundary when that helps, then `ops-observability`'s other sites in parentheses]{ the verify Annotation groups, standalone only}
- **Missing:** [`ops-observability`'s Signal value: `absent - <log field | metric | trace span | context propagation | alert | dashboard | SLO>`, `removal - secret/personal data in logs or exception messages`, `replacement - cause-based page -> <symptom alert>`, or `misuse - <per-iteration info log | cause-based page beside an existing symptom alert | unstructured (non-JSON) log>`; the two row-owned patterns use `misuse - high-cardinality label` and `absent - <browser error tracking | source maps | global error handler | Web Vitals>`]
- **Impact:** [what becomes invisible or undetectable; for a removal, who can read the exposed value and at what scale; for a misuse or replacement, the noise or the missed symptom; for an `absent` signal, where it was searched for; ending `(unverified - <file to check>)` when `ops-observability` marked the deciding file unread]
- **Fix:** [concrete instrumentation change]

### Medium Severity (reduces diagnosis speed)

[Same structure]

### Low Severity (nice-to-have, no current blind spot)

[Same structure]

- **out of lens:** file:line - [the defect in one sentence] - owner: [lens or `task-code-review`]   {one per such defect}

## Prior Round Reconciliation

[reconcile's output verbatim - table, any note lines, tally]   {round 2+ standalone runs only}

## Next Steps   {when at least one published finding}

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] file:line [scope: platform] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent runs: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: `stack-detect` ran (subagent runs: parent-supplied detection accepted instead)
- [ ] Step 3: exactly one announcement printed before any output; on dispatch the arguments were forwarded and Steps 4-5 skipped (skipped entirely on subagent runs)
- [ ] Step 4: precondition called with `argument` / `base` / `report_type`; SHAs captured and the round gate decided (head, base, depth, stack and Scope compared) before the diff was read; docs/tests-only diff reported with the no-surface note (`Adequate`, or `Gaps Found` with carried rows); `ops-observability` loaded and every applicable category covered, one finding per gap; every finding states what becomes invisible (or the exposure, noise, or missed symptom); qualifying `out of lens` lines emitted; findings published with verify's `file:line`, `Label`, `Annotation`; round 2+ prior findings projected, reconciled, and carried; precondition, SHA capture, gate, verify and reconcile skipped on subagent runs
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the round-gate stop line printed, or a precondition failure surfaced verbatim with no report written (standalone fallback only)

## Avoid

- Writing a report when invoked as a subagent - the parent owns it
- "Missing log" findings without stating what becomes invisible
- Recommending more logging without considering volume cost and alert noise
- Suggesting metrics with high-cardinality labels
- Treating the fallback as equivalent to a stack workflow
- Emitting labels outside `[Must]` / `[Recommend]` in the findings sections (the reconciliation table preserves prior labels verbatim)
