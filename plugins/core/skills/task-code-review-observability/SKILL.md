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
| React / Next.js | `task-react-review-observability` | `react`  |

A row matches only when the detected framework matches it (Java / Micronaut does not match Java / Spring Boot - use the fallback); a row named by language alone (Python) matches that language under any framework; the Node.js / TypeScript row matches Language `JavaScript` or `TypeScript` with a server framework (NestJS, Express, Fastify, Koa, Hono) or none; a Framework naming Next.js takes the React row: `React (Next.js)` from detection or a declared value such as `Next.js 16.3 (App Router)`. Any other React framework (Vite, CRA, React Router, Remix) and any other frontend framework (Vue, Angular, Svelte) match no row. Dispatch keys on the detection's primary `Language`/`Framework` pair; a secondary stack in `Additional` never dispatches. Announce the dispatch in one line (`Dispatching to task-rails-review-observability.` - substitute the target), forward the arguments unchanged, and stop. **If matched, skip Steps 4-5.** If the matched workflow does not resolve (stack plugin not installed), announce it in one line (`task-rails-review-observability is provided by the ruby plugin, which is not installed - running the generic observability review.` - substitute the row's target and plugin), then run Steps 4-5 as fallback. A detected stack matching no row at all falls through to the Step 4 generic fallback - announce it in one line (`No stack observability workflow for <stack> - running the generic observability review.`, `<stack>` = the detection's Language / Framework pair), then run it.

### Step 4 - Generic Fallback (no dispatch match)

Use skill: `review-precondition-check` with the invocation's target, any `--base` override, and `report_type: review-observability` when running standalone (skip if the parent supplied a handle); on failure, surface its message verbatim and stop. Standalone, capture `base_sha` / `head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`. Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full and include the SLO category below.

**Round gate (standalone only).** Before reviewing, decide the round from the handle: with `report_type: review-observability` passed, its `report_path` is this lens's checkpoint (`review-observability-<sanitized head_short_name>.md`) and its `prior_checkpoint` is that file's frontmatter - or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch. If `prior_checkpoint` is a valid block, its `head_sha` equals the captured `head_sha`, and the requested depth does not exceed its `depth` (`deep` exceeds `standard`), print `No new commits since prior observability review.` and stop - no review, no report. Otherwise set `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 5 write overwrites the file) -> `round: 1`, no `prior_head_sha`. When this run detects a different `stack` than the checkpoint frontmatter records, or a different `Scope` than the Summary line in the file at `report_path` shows, that is new work: proceed on the fresh detection even at the same `head_sha` and depth, and fill the Summary's `Detection change:` slot. Then read the diff and commit log once.

Use skill: `ops-observability`. This is the primary source of findings - it covers structured logging, RED metrics, distributed tracing, correlation propagation, and SLO design. The list below names the categories the fallback must explicitly cover; rely on `ops-observability` for the patterns, except where a row states something it does not carry - the Frontend observability row (no browser-side material there) and the Metrics row's high-cardinality-label rule; for those the row text is the pattern.

| Category                  | Scope            | Must cover                                                                            |
| ------------------------- | ---------------- | ------------------------------------------------------------------------------------- |
| Structured logging        | all              | JSON/structured format, mandatory fields, log levels, no PII/secrets, no hot-loop spam |
| Metrics                   | backend          | RED on every entry point (API endpoint, queue consumer, scheduled job), latency histograms, a business-metric counter per critical operation, an absence alert on scheduled or event-driven work, no high-cardinality labels |
| Distributed tracing       | backend          | Entry spans, DB child spans carrying the query template and HTTP child spans the target service, one propagation family carried end-to-end (W3C `traceparent`, forwarding `tracestate` when received; B3 single or multi-header; or `uber-trace-id`), sampling policy |
| Context propagation       | all              | Framework request context, background-job context extraction, async carry-forward; under frontend scope, `traceparent` on the browser's outbound API calls |
| Frontend observability    | frontend         | Error tracking with source maps, global handlers, Core Web Vitals, no PII             |
| SLO and alerting          | backend, deep only | SLI per critical service, SLO target + window + error budget, burn-rate alerts on symptoms not causes; triggered when the diff adds or changes a critical surface. Definitions only - a missing error signal belongs to Metrics |

Determine `Scope` from `stack-detect`'s `Stack Type` field (`backend` / `frontend` / `fullstack`, displayed capitalised); `fullstack` activates both the backend- and frontend-scoped rows. Server-rendered UI (Phoenix LiveView, Hotwire/Turbo, Blade, Django or Rails templates) activates the frontend-scoped rows too, even under `backend` - Scope then displays `Backend + server-rendered UI`. Severity follows the Findings section definitions in Output Format; `ops-observability`'s own ratings inform but do not override, except that a gap the section definitions do not name takes the tier `ops-observability` gives it. A critical service with no SLO is High -> `[Must]` at deep depth (its failure goes undetected); `ops-observability` requires no SLO elsewhere, so a non-critical service raises none. Every finding states what becomes invisible without the missing signal (a `removal` finding states who can read the exposed value; a `misuse` or `replacement` finding states the noise or the missed symptom it causes). Severity assigns each finding an initial intent (High -> `[Must]`, Medium/Low -> `[Recommend]`); where `review-finding-verify` publishes a different `Label`, the published label governs every slot naming one. A defect outside this lens that would break the build, or corrupt or expose data, becomes an `out of lens` line (shape in Output Format). Next Steps carry each finding published label and tag each step `[Implement]` (localized fix) or `[Delegate]` (cross-cutting, platform, or infra-owned).

If the diff touches no instrumentable code (docs, tests, comments only - check this right after the round gate, or first thing on a subagent run, before loading any category atomic), skip the category review and the verify skill: report `Overall: Adequate - diff contains no instrumentable surface`, render `## Findings` containing only the line `Diff contains no instrumentable surface.`, set `Findings verified: 0 confirmed, 0 reattributed, 0 unverified, 0 dropped`, omit Next Steps, and still write the report in Step 5. On round 2+ the prior report is still reconciled: with nothing carried the report is as above; with carried rows they publish in their sections and Next Steps, `Overall` reads `Gaps Found - <counts>`, and the no-surface note is the last line of `## Findings`. Subagent runs return the envelope with no findings and that note instead.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns; the Summary's `Findings verified:` line is the Summary form the atomic prescribes, filled from its tally (`<N> confirmed, <M> reattributed, <U> unverified, <K> dropped`, plus its false-positive/resolved split when emitted) - the verify table itself stays internal. On round 2+, after verification, re-project the prior report's findings (the file at the handle's `report_path`) into reconcile's parse shape - a `## High-Impact Findings` section, one `### [Label] file:line` heading per finding from its label line (or, when the prior report wrote no label line, the label its severity section maps to under this lens's severity rule - reconcile's verbatim rule has nothing to preserve there) and the `file:line` prefix of its Location line (trailing component prose stays out of the heading), keeping a `_(pre-existing)_` annotation on the heading (reconcile splits untouched files on it; verify's combined `_(pre-existing; newly reachable via ...)_` is written as two groups, `_(pre-existing)_ _(newly reachable via ...)_`), and an `Issue:` line carrying that finding's `Missing:` text, since reconcile reads the smell from `Issue:` or `Improvement:` only - then Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, and `head_sha`. Its table and tally render as `## Prior Round Reconciliation` between Findings and Next Steps; unresolved rows (`Still open`, `Needs re-check`) carry into their prior severity sections at their prior label, noted `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the label on its label line, its prior Location annotation kept; the reconciliation table row and its Next Steps entry are its only other appearances. A prior label outside `[Must]` / `[Recommend]` (`[Blocker]`, `[High]`, `[Question]` in a legacy report) stays verbatim in that table, which reconcile owns, and maps before it is published in a findings section: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; `[Suggestion]`, `[Nitpick]`, `[Question]`, `[Medium]`, `[Low]`, and any unrecognised label -> `[Recommend]`; `[Praise]` rows are never carried. A carried finding this round's own pass re-derives publishes once, in the findings sections, not twice. The table preserves each prior citation exactly; the published finding carries the corrected `file:line` when verification found the prior cite stale. Subagent runs skip both - the parent verifies and reconciles its own merged set once.

### Step 5 - Write Report

Standalone only - subagent runs return findings to the parent instead. Use skill: `review-report-writer` with `report_type: review-observability` and every required input: `report_body`, `branch` (the handle's `head_short_name`), the handle's refs, `base_sha` / `head_sha` from Step 4, `pr_url` when the request text carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present, `scope: +obs`, `depth` as invoked (default `standard`), `stack` from `stack-detect` (kebab-case `<language>-<framework>`, versions dropped; drop a segment reported unknown; `unknown` only when detection failed entirely), `mode: full`, and `round` plus `prior_head_sha` from the Step 4 round gate.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

When Step 3 dispatched: the stack workflow owns the output. Subagent runs return the `## Findings` heading, its severity sections, and any `out of lens` lines only - Summary, Prior Round Reconciliation, Next Steps, and the report file are standalone-only. In every mode each finding block opens with its label on its own line, `**[Must]**` or `**[Recommend]**`, before `Location`, and empty severity sections are omitted. A finding sits in the section matching its **severity**; its label line and its Next Steps entry carry its **published label**. The two diverge whenever verification de-escalated a pre-existing finding - a `**[Recommend]**` inside a High section is correct, not a mismatch to fix. A defect outside this lens that would break the build, or corrupt or expose data gets one `out of lens` line each at the end of `## Findings`, so it is not silently dropped; anything else outside the lens is left to `task-code-review`. Verify annotations (the Annotation column: `_(pre-existing)_`, `_(pre-existing; newly reachable via ...)_`, `_(unverified: ...)_`, `_(mechanism: ...)_`) sit on the `Location` line (standalone only - subagent runs skip verification). A run that reviewed and found nothing returns `## Findings` containing `No observability gaps found.` in either mode; a docs/tests-only diff returns the no-instrumentable-surface note instead, per Step 4. Standalone runs emit the report body in chat, then the writer's confirmation line. When fallback ran standalone:

```markdown
## Observability Review Summary

- **Stack Detected:** [kebab-case `<language>-<framework>`, versions dropped - the same string passed as the writer `stack` input; or `unknown`] (generic fallback: no stack workflow) | (generic fallback: `<plugin>` plugin not installed)
- **Depth:** standard | deep
- **Scope:** Backend | Backend + server-rendered UI | Frontend | Fullstack
- **Overall:** Adequate [- reason, e.g. `diff contains no instrumentable surface`] | Gaps Found - <H> High / <M> Medium / <L> Low
- **Round:** [N]   {round 2+ only}
- **Detection change:** [what differs from the checkpoint, and any category it adds or drops - omit on round 1 or when unchanged]
- **Findings verified:** [from `review-finding-verify`'s tally, in its Summary form: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`]

## Findings

### High Severity (would prevent detection of a production failure, or exposes secret or personal data to log readers)

**[Must | Recommend]**{ _(carried from round <N>)_}
- **Location:** [file:line - required, so verification, the reconcile projection and Next Steps can all consume it; name the component or boundary after it when that helps]{ the verify Annotation, standalone only}
- **Missing:** [`ops-observability`'s Signal value: `absent - <log field | metric | trace span | context propagation | alert | dashboard | SLO>`, `removal - secret/personal data in logs or exception messages`, `replacement - cause-based page -> <symptom alert>`, or `misuse - <per-iteration info log | cause-based page beside an existing symptom alert>`; the two row-owned patterns use `misuse - high-cardinality label` and `absent - <browser error tracking | source maps | global error handler | Web Vitals>`; two kinds missing at one site join with `;`]
- **Impact:** [what becomes invisible or undetectable; for a removal, who can read the exposed value and at what scale; for a misuse or replacement, the noise or the missed symptom]
- **Fix:** [concrete instrumentation change]

### Medium Severity (reduces diagnosis speed)

[Same structure]

### Low Severity (nice-to-have, no current blind spot)

[Same structure]

_Omit sections with no findings. If all are omitted after a review ran, state "No observability gaps found." (before any `out of lens` line) and omit Next Steps._

- **out of lens:** file:line - [the defect in one sentence, and the lens that owns it]   {one per such defect, only when it would break the build or corrupt or expose data}


## Prior Round Reconciliation

[table and tally from `review-prior-findings-reconcile` - round 2+ standalone runs only; omit the section otherwise]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent runs: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: `stack-detect` ran (subagent runs: parent-supplied detection accepted instead)
- [ ] Step 3: if matched and installed, dispatch announced and stack workflow ran with arguments forwarded, Steps 4-5 skipped; if not installed or no row matched, the announcement printed and fallback ran (skipped entirely on subagent runs)
- [ ] Step 4: if no match, SHAs captured; round gate decided from the handle (`report_type: review-observability`) before the diff was read; `out of lens` lines emitted for qualifying defects outside the lens; `ops-observability` loaded and every applicable category in the table covered; every finding states what becomes invisible (or the exposure, noise, or missed symptom for the other Signal kinds); prior findings projected into reconcile's parse shape and reconciled on round 2+; the round gate, `review-finding-verify` (whose tally fills the `Findings verified:` Summary line) and reconciliation are standalone-only - subagent runs skip all three; docs/tests-only diff reported as Adequate
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the round-gate stop line printed, or a precondition failure surfaced verbatim with no report written (standalone fallback only; subagent runs return findings to the parent)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Writing a report when invoked as a subagent - the parent owns it
- "Missing log" findings without stating what becomes invisible
- Recommending more logging without considering volume cost and alert noise
- Suggesting metrics with high-cardinality labels
- Treating the fallback as equivalent to a stack workflow
- Emitting labels outside `[Must]` / `[Recommend]` in the findings sections (the reconciliation table preserves prior labels verbatim)
