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

**Not for:** General code review (`task-code-review`), security (`task-code-review-security`), perf with a known bottleneck (`task-code-review-perf`), active incidents (use the oncall plugin's `incident-root-cause`).

## Invocation

`/task-code-review-observability [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack, precondition handle, and read-once diff/log: skip Steps 2-3, run Step 4 on the supplied diff, return findings per Output Format, and skip Step 5 - the parent owns the report.

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

Forward arguments and stop. **If matched, skip Steps 4-5.** If the matched workflow does not resolve (stack plugin not installed), tell the user which plugin provides it, then run Steps 4-5 as fallback.

### Step 4 - Generic Fallback (no dispatch match)

Use skill: `review-precondition-check` when running standalone (skip if the parent supplied a handle). Read diff and commit log once. Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full and include the SLO category below.

Use skill: `ops-observability`. This is the primary source of findings - it covers structured logging, RED metrics, distributed tracing, correlation propagation, and SLO design. The list below names the categories the fallback must explicitly cover; rely on `ops-observability` for the patterns.

| Category                  | Scope            | Must cover                                                                            |
| ------------------------- | ---------------- | ------------------------------------------------------------------------------------- |
| Structured logging        | all              | JSON/structured format, mandatory fields, log levels, no PII/secrets, no hot-loop spam |
| Metrics                   | backend          | RED on inbound interfaces, latency histograms, no high-cardinality labels             |
| Distributed tracing       | backend          | Entry spans, DB/HTTP child spans with template attributes, W3C `traceparent` propagation, sampling policy |
| Context propagation       | all              | Framework request context, background-job context extraction, async carry-forward     |
| Frontend observability    | frontend         | Error tracking with source maps, global handlers, Core Web Vitals, no PII             |
| SLO and alerting          | deep depth only  | SLI per critical service, SLO target + window, burn-rate alerts on symptoms not causes |

Determine `Scope` (`backend` / `frontend` / `fullstack`) from `stack-detect`'s `Stack Type` field. Flag services with no SLO as **Recommend** at deep depth. Every finding states what becomes invisible without the missing signal. Next Steps map severity to intent: High -> `[Must]`, Medium/Low -> `[Recommend]`; `[Question]` only when the fix depends on the author's answer.

If the diff touches no instrumentable code (docs, tests, comments only), skip the category review and report `Overall: Adequate` with the note "diff contains no instrumentable surface" - still write the report in Step 5.

### Step 5 - Write Report

Standalone only - subagent runs return findings to the parent instead. Use skill: `review-report-writer` with `report_type: review-observability` and every required input: `report_body`, `branch` (from the handle), the handle's refs, `base_sha` / `head_sha` via `git rev-parse`, `scope: +obs`, `depth` as invoked (default `standard`), `stack` from `stack-detect` (kebab-case language-framework, or `unknown`), and `mode: full`, `round: 1` - unless `review-observability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`.

## Output Format

When Step 3 dispatched: the stack workflow owns the output. When fallback ran:

```markdown
## Observability Review Summary

**Stack Detected:** [detected stack, or unknown] (generic fallback applied)
**Scope:** Backend | Frontend | Fullstack
**Overall:** Adequate | Gaps Found - [High/Medium/Low counts]

## Findings

### High Severity (would prevent detection of a production failure)

- **Location:** [file:line, component, or service boundary]
- **Missing:** [absent signal - log field, metric, trace span, alert]
- **Impact:** [what becomes invisible or undetectable]
- **Fix:** [concrete instrumentation change]

### Medium Severity (reduces diagnosis speed)

[Same structure]

### Low Severity (nice-to-have, no current blind spot)

[Same structure]

_Omit sections with no findings. If all are omitted, state "No observability gaps found." and omit Next Steps._

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: if matched, stack workflow ran with arguments forwarded; Steps 4-5 skipped (unless the workflow did not resolve)
- [ ] Step 4: if no match, every applicable category in the table covered; every finding states what becomes invisible; docs/tests-only diff reported as Adequate
- [ ] Step 5: report written via `review-report-writer` with all required inputs (standalone fallback only; subagent runs return findings to the parent)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Writing a report when invoked as a subagent - the parent owns it
- "Missing log" findings without stating what becomes invisible
- Recommending more logging without considering volume cost and alert noise
- Suggesting metrics with high-cardinality labels
- Treating the fallback as equivalent to a stack workflow
- Emitting labels outside `[Must]` / `[Recommend]` / `[Question]`
