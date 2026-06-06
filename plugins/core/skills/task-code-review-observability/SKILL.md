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

Detects the project stack and delegates to the matching stack-specific observability review (`task-{stack}-review-observability`). For unknown stacks, runs a minimal generic review driven by `ops-observability`.

## When to Use

- Pre-release observability check for a new service or major feature
- Post-incident review when diagnosis was slow or evidence missing
- OpenTelemetry / structured logging / SLO-based alerting adoption
- Audit of a service whose production behavior is opaque

**Not for:** General code review (`task-code-review`), security (`task-code-review-security`), perf with a known bottleneck (`task-code-review-perf`), active incidents (use the oncall plugin's `incident-root-cause`).

## Invocation

`/task-code-review-observability [<branch> | pr-<N>] [quick | standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review`, the parent passes the precondition handle and read-once diff/log; forward to the dispatched stack workflow.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to                         |
| -------------------- | ----------------------------------- |
| Java / Spring Boot   | `task-spring-review-observability`  |
| Kotlin / Spring Boot | `task-kotlin-review-observability`  |
| Python               | `task-python-review-observability`  |
| Ruby / Rails         | `task-rails-review-observability`   |
| Node.js / TypeScript | `task-node-review-observability`    |
| Go / Gin             | `task-go-review-observability`      |
| Rust / Axum          | `task-rust-review-observability`    |
| .NET / ASP.NET Core  | `task-dotnet-review-observability`  |
| PHP / Laravel        | `task-laravel-review-observability` |
| React                | `task-react-review-observability`   |
| Vue                  | `task-vue-review-observability`     |
| Angular              | `task-angular-review-observability` |

Forward arguments and stop. **If matched, skip Steps 4-5.**

### Step 4 - Generic Fallback (unknown stack only)

Use skill: `review-precondition-check` when running standalone (skip if the parent supplied a handle). Read diff and commit log once.

Use skill: `ops-observability`. This is the primary source of findings - it covers structured logging, RED metrics, distributed tracing, correlation propagation, and SLO design. The list below names the categories the fallback must explicitly cover; rely on `ops-observability` for the patterns.

| Category                  | Scope            | Must cover                                                                            |
| ------------------------- | ---------------- | ------------------------------------------------------------------------------------- |
| Structured logging        | all              | JSON/structured format, mandatory fields, log levels, no PII/secrets, no hot-loop spam |
| Metrics                   | backend          | RED on inbound interfaces, latency histograms, no high-cardinality labels             |
| Distributed tracing       | backend          | Entry spans, DB/HTTP child spans with template attributes, W3C `traceparent` propagation, sampling policy |
| Context propagation       | all              | Framework request context, background-job context extraction, async carry-forward     |
| Frontend observability    | frontend         | Error tracking with source maps, global handlers, Core Web Vitals, no PII             |
| SLO and alerting          | deep depth only  | SLI per critical service, SLO target + window, burn-rate alerts on symptoms not causes |

Determine `Scope` (`backend` / `frontend` / `fullstack`) from `stack-detect`'s `Stack Type` field. Flag services with no SLO as **Recommend** at deep depth. Every finding states what becomes invisible without the missing signal.

### Step 5 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`.

## Output Format

When Step 3 dispatched: the stack workflow owns the output. When fallback ran:

```markdown
## Observability Review Summary

**Stack Detected:** unknown (generic fallback applied)
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

_Omit sections with no findings._

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: if matched, stack workflow ran with arguments forwarded; Steps 4-5 skipped
- [ ] Step 4: if no match, every applicable category in the table covered; every finding states what becomes invisible
- [ ] Step 5: report written via `review-report-writer` (fallback path only)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- "Missing log" findings without stating what becomes invisible
- Recommending more logging without considering volume cost and alert noise
- Suggesting metrics with high-cardinality labels
- Treating the fallback as equivalent to a stack workflow
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
