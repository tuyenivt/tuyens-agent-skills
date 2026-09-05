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

**Not for:** General code review (`task-code-review`), security (`task-code-review-security`), perf with a known bottleneck (`task-code-review-perf`).

## Invocation

`/task-code-review-observability [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack (the full stack-detect output, including `Stack Type`), precondition handle, read-once diff/log, and active depth: skip Steps 2-3 (Step 1 still applies), run Step 4 on the supplied diff, return the subagent envelope defined in Output Format, and skip Step 5 - the parent owns the report. Read-once covers the diff and log; at `deep`, touched files may still be read in full.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to                         |
| -------------------- | ----------------------------------- |
| Java / Spring Boot   | `task-spring-review-observability`  |
| Python               | `task-python-review-observability`  |
| Ruby / Rails         | `task-rails-review-observability`   |
| Node.js / TypeScript | `task-node-review-observability`    |
| Go / Gin             | `task-go-review-observability`      |
| React / Next.js / Vite | `task-react-review-observability` |

A row matches only when the detected framework matches it (Java / Micronaut does not match Java / Spring Boot - use the fallback); a row named by language alone (Python) matches that language under any framework. Forward arguments and stop. **If matched, skip Steps 4-5.** If the matched workflow does not resolve (stack plugin not installed), tell the user which plugin provides it, then run Steps 4-5 as fallback. A detected stack matching no row at all falls through to the Step 4 generic fallback - say so in one line, then run it.

### Step 4 - Generic Fallback (no dispatch match)

Use skill: `review-precondition-check` with the invocation's target and any `--base` override when running standalone (skip if the parent supplied a handle). Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full and include the SLO category below.

**Round gate (standalone only).** Before reviewing, check `review-observability-<branch>.md` (`<branch>` = head short name, for `head_ref: HEAD` the handle's `current_branch`, sanitised as the writer does - every character outside `[A-Za-z0-9_-]` replaced by `-`, runs of `-` collapsed, leading and trailing `-` stripped; the handle's `prior_checkpoint` is keyed to the general review report - never use it here). If it exists with valid frontmatter, its `head_sha` equals the current head, and the requested depth does not exceed its `depth` (`deep` exceeds `standard`), print `No new commits since prior observability review.` and stop - no review, no report. Otherwise set `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; absent file, or frontmatter missing/unparseable (legacy - the Step 5 write overwrites it) -> `round: 1`, no `prior_head_sha`. The gate turns on `head_sha` and `depth` alone; when this run detects a different `stack` than the checkpoint frontmatter records, or a different `Scope` than its Summary line shows, proceed on the fresh detection and fill the Summary's `Detection change:` slot. Then read the diff and commit log once.

Use skill: `ops-observability`. This is the primary source of findings - it covers structured logging, RED metrics, distributed tracing, correlation propagation, and SLO design. The list below names the categories the fallback must explicitly cover; rely on `ops-observability` for the patterns, except where a row states something it does not carry - the Frontend observability row (no browser-side material there) and the Metrics row's high-cardinality-label rule; for those the row text is the pattern.

| Category                  | Scope            | Must cover                                                                            |
| ------------------------- | ---------------- | ------------------------------------------------------------------------------------- |
| Structured logging        | all              | JSON/structured format, mandatory fields, log levels, no PII/secrets, no hot-loop spam |
| Metrics                   | backend          | RED on inbound interfaces, latency histograms, no high-cardinality labels             |
| Distributed tracing       | backend          | Entry spans, DB/HTTP child spans with template attributes, W3C `traceparent` propagation, sampling policy |
| Context propagation       | all              | Framework request context, background-job context extraction, async carry-forward     |
| Frontend observability    | frontend         | Error tracking with source maps, global handlers, Core Web Vitals, no PII             |
| SLO and alerting          | deep depth only  | SLI per critical service, SLO target + window, burn-rate alerts on symptoms not causes; triggered when the diff adds or changes a critical surface. Definitions only - a missing error signal belongs to Metrics |

Determine `Scope` (`backend` / `frontend` / `fullstack`) from `stack-detect`'s `Stack Type` field; `fullstack` activates both the backend- and frontend-scoped rows. Server-rendered UI (Phoenix LiveView, Hotwire/Turbo, Blade, Django or Rails templates) activates the frontend-scoped rows too, even under `backend`. Severity follows the Findings section definitions in Output Format; `ops-observability`'s own ratings inform but do not override. Flag services with no SLO as Medium severity -> `[Recommend]` at deep depth. Every finding states what becomes invisible without the missing signal. Severity assigns each finding an initial intent (High -> `[Must]`, Medium/Low -> `[Recommend]`); where `review-finding-verify` publishes a different `Label`, the published label governs every slot naming one. Next Steps carry each finding published label and tag each step `[Implement]` (localized fix) or `[Delegate]` (cross-cutting, platform, or infra-owned).

If the diff touches no instrumentable code (docs, tests, comments only - check this right after the round gate, before loading any atomic), skip the category review and the verify skill: report `Overall: Adequate - diff contains no instrumentable surface`, render `## Findings` containing only that same note, set `Findings verified: 0 confirmed, 0 reattributed, 0 dropped`, omit Next Steps, and still write the report in Step 5. Subagent runs return the envelope with no findings and that note instead.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and fill the Summary's `Findings verified:` line as `<N> confirmed, <M> reattributed, <K> dropped` from its counts, appending its `(<F> false positive, <R> resolved by diff)` split and `; <U> of these unverified` suffix when it emits them - the verify table itself stays internal. On round 2+, after verification, re-project the prior report's findings into reconcile's parse shape - a `## High-Impact Findings` section, one `### [Label] file:line` heading per finding (from its label and Location lines) and an `Issue:` line carrying that finding's `Missing:` text, since reconcile reads the smell from `Issue:` or `Improvement:` only - then Use skill: `review-prior-findings-reconcile` with that projection, the diff, and `git diff --name-status <base_ref>...<head_ref>`. Its table and tally render as `## Prior Round Reconciliation` between Findings and Next Steps; unresolved rows carry into their prior severity sections at their prior label, noted `carried from round <N>` on the label line. A prior label outside `[Must]` / `[Recommend]` (`[Blocker]`, `[High]`, `[Question]` in a legacy report) stays verbatim in that table, which reconcile owns, and maps into this lens's two labels before it is published in a findings section. A carried finding this round's own pass re-derives publishes once, in the findings sections, not twice. The table preserves each prior citation exactly; the published finding carries the corrected `file:line` when verification found the prior cite stale. Subagent runs skip both - the parent verifies and reconciles its own merged set once.

### Step 5 - Write Report

Standalone only - subagent runs return findings to the parent instead. Use skill: `review-report-writer` with `report_type: review-observability` and every required input: `report_body`, `branch` (head short name from the handle - for `head_ref: HEAD`, the handle's `current_branch`), the handle's refs, `base_sha` / `head_sha` via `git rev-parse`, `scope: +obs`, `depth` as invoked (default `standard`), `stack` from `stack-detect` (kebab-case language-framework, versions dropped, or `unknown`), `mode: full`, and `round` plus `prior_head_sha` from the Step 4 round gate.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

When Step 3 dispatched: the stack workflow owns the output. Subagent runs return the `## Findings` heading and its severity sections only - Summary, Prior Round Reconciliation, Next Steps, and the report file are standalone-only. In every mode each finding block opens with its label on its own line, `**[Must]**` or `**[Recommend]**`, before `Location`, and empty severity sections are omitted. A finding sits in the section matching its **severity**; its label line and its Next Steps entry carry its **published label**. The two diverge whenever verification de-escalated a pre-existing finding - a `**[Recommend]**` inside a High section is correct, not a mismatch to fix. A defect outside this lens that would break the build, or corrupt or expose data gets one line at the end of `## Findings` marked `out of lens`, so it is not silently dropped; anything else outside the lens is left to `task-code-review`. Verify annotations (`_(pre-existing)_`, `(unverified ...)`) sit on the `Location` line (standalone only - subagent runs skip verification). A run that reviewed and found nothing returns `## Findings` containing `No observability gaps found.` in either mode; a docs/tests-only diff returns the no-instrumentable-surface note instead, per Step 4. Standalone runs emit the report body in chat, then the writer's confirmation line. When fallback ran standalone:

```markdown
## Observability Review Summary

- **Stack Detected:** [kebab-case `<language>-<framework>`, versions dropped - the same string passed as the writer `stack` input; or `unknown`] (generic fallback applied)
- **Scope:** Backend | Frontend | Fullstack
- **Overall:** Adequate [- reason, e.g. `diff contains no instrumentable surface`] | Gaps Found - [High/Medium/Low counts]
- **Detection change:** [what differs from the checkpoint, and any category it adds or drops - omit on round 1 or when unchanged]
- **Findings verified:** [`<N> confirmed, <M> reattributed, <K> dropped` from `review-finding-verify`, plus its false-positive/resolved split and unverified suffix when emitted]

## Findings

### High Severity (would prevent detection of a production failure)

**[Must]**
- **Location:** [file:line - required, so verification, the reconcile projection and Next Steps can all consume it; name the component or boundary after it when that helps]
- **Missing:** [absent signal - log field, metric, trace span, context propagation, alert, or SLO; or `removal - secret/PII in logs`, or `replacement - <wrong signal> -> <right signal>`]
- **Impact:** [what becomes invisible or undetectable; for a removal, who can read the exposed value and at what scale]
- **Fix:** [concrete instrumentation change]

### Medium Severity (reduces diagnosis speed)

[Same structure]

### Low Severity (nice-to-have, no current blind spot)

[Same structure]

_Omit sections with no findings. If all are omitted after a review ran, state "No observability gaps found." and omit Next Steps._

[one `out of lens` line, when a defect outside this lens would break the build or corrupt or expose data]


## Prior Round Reconciliation

[table and tally from `review-prior-findings-reconcile` - round 2+ standalone runs only; omit the section otherwise]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran (subagent runs: parent-supplied detection accepted instead)
- [ ] Step 3: if matched, stack workflow ran with arguments forwarded; Steps 4-5 skipped (unless the workflow did not resolve; skipped entirely on subagent runs)
- [ ] Step 4: if no match, round gate decided before any review; every applicable category in the table covered; every finding states what becomes invisible; prior findings reconciled on round 2+; the round gate, `review-finding-verify` (whose tally fills the `Findings verified:` Summary line) and reconciliation are standalone-only - subagent runs skip all three; docs/tests-only diff reported as Adequate
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the round-gate stop line printed, or a precondition failure surfaced verbatim with no report written (standalone fallback only; subagent runs return findings to the parent)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Writing a report when invoked as a subagent - the parent owns it
- "Missing log" findings without stating what becomes invisible
- Recommending more logging without considering volume cost and alert noise
- Suggesting metrics with high-cardinality labels
- Treating the fallback as equivalent to a stack workflow
- Emitting labels outside `[Must]` / `[Recommend]` in the findings sections (the reconciliation table preserves prior labels verbatim)
