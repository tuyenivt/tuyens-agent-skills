---
name: task-code-review-observability
description: Observability review entry point: structured logging, RED metrics, distributed tracing, SLOs. Detects stack and dispatches workflow.
metadata:
  category: review
  tags: [observability, logging, metrics, tracing, slo, multi-stack, router]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Observability Review (Router)

This skill is a thin dispatcher. It detects the project stack and delegates to the matching stack-specific skill (e.g., `task-spring-review-observability`, `task-rails-review-observability`, `task-react-review-observability`). The stack workflow names library-specific idioms directly (Rails: `ActiveSupport::Notifications`, lograge, Sidekiq middleware; Spring: Micrometer, Sleuth/Brave; Node: pino, OpenTelemetry SDK).

For unknown stacks, this skill falls back to a minimal generic observability review.

## When to Use

- Pre-release observability check for a new service or major feature
- Post-incident review when diagnosis was slow or evidence missing
- Adopting / migrating to OpenTelemetry, structured logging, or SLO-based alerting
- Audit of an existing service whose production behavior is opaque

**Not for:** General code review (use `task-code-review`), security review (use `task-code-review-security`), perf with a known bottleneck (use `task-code-review-perf`), active incidents (use oncall plugin's `incident-root-cause`).

## Invocation

Accepts the same diff-targeting arguments as `task-code-review`. Depth flags (`quick`, `standard`, `deep`) compose. When invoked as a subagent of `task-code-review`, the parent passes the precondition handle plus the read-once diff/log; this is forwarded to the dispatched stack workflow.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect`.

### Step 2 - Dispatch to Stack Workflow

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

If matched, forward arguments and stop. Do not run Step 3.

### Step 3 - Generic Fallback (unknown stack only)

Use skill: `review-precondition-check` if running standalone. Read diff and commit log once.

Use skill: `ops-observability` to assess structured logging, RED metrics, distributed tracing, correlation ID propagation, and SLO definition. This is the primary source of findings; the items below complement it.

**Structured logging** (all stacks):

- Logs are structured (JSON or framework structured format) - no concatenated string `printf`/`console.log` on hot paths
- Mandatory fields present: `level`, `service`, `trace_id`, `span_id`
- No sensitive data logged (passwords, tokens, full PII, full request bodies on auth endpoints)
- Log levels used correctly: `error` for actionable failures, `warn` for recoverable anomalies, `info` for state transitions
- No log spam in hot loops

**Metrics coverage** (Backend / Fullstack):

- RED metrics (Rate, Errors, Duration) on every external API endpoint and inbound interface
- Custom business metrics for revenue-impacting / SLO-tracked operations
- Histograms for latency (not gauges or averages); p50/p95/p99 derivable from buckets
- No high-cardinality labels (user ID, request ID, raw URL with parameters)
- DB query and external HTTP latency tracked separately from total request duration

**Distributed tracing** (Backend / Fullstack):

- Service entry points produce spans (framework middleware enabled)
- DB queries produce spans with the query template (not parameterized values) as attribute
- External HTTP calls produce spans with target service name
- Message publish/consume produces linked spans across async boundaries
- Trace context propagated via standard headers (W3C `traceparent`, `b3`, `uber-trace-id`); receiving service extracts and creates child spans
- Sampling: head-based 10-20% for high traffic; always sample errors and slow requests at 100%

**Frontend observability** (Frontend / Fullstack):

- Error tracking installed (Sentry, Rollbar, or equivalent); source maps uploaded for production
- Unhandled promise rejections and global error handlers wired
- Core Web Vitals reported (LCP, INP, CLS)
- User journey / funnel events instrumented for critical flows
- No PII in analytics or error reports
- Trace context propagated from frontend to backend via W3C `traceparent` when full-stack tracing exists

**SLO and alerting** (deep depth, or on request):

- At least one SLI per critical service with a measurable signal
- SLO target stated with window (e.g., 99.9% over 30 days)
- Error budget derived; burn-rate alerting configured
- Alerts page on **symptoms** (error rate, latency, saturation), not **causes** (CPU, memory)
- Multi-window burn-rate alerts to reduce false positives

Flag services with no SLO as a **High** observability gap.

**Correlation and context propagation** (all stacks):

- Request-scoped context propagated through framework mechanism (MDC, `context.Context`, `CurrentAttributes`, `contextvars`, middleware context)
- Background jobs and queue consumers extract trace context from message envelope
- Async operations (goroutines, threads, promises) carry context forward; no orphaned spans

**Step 4 - Write Report:** Use skill: `review-report-writer` with `report_type: review-observability`.

## Output Format

When dispatched (Step 2 matched): the stack-specific workflow owns the output.

When fallback runs (Step 3):

```markdown
## Observability Review Summary

**Stack Detected:** unknown (generic fallback applied)
**Scope:** Backend | Frontend | Fullstack
**Overall:** Adequate | Gaps Found - [count by severity: High/Medium/Low]

## Findings

### High Severity (would prevent detection of a production failure)

- **Location:** [file:line, component, or service boundary]
- **Missing:** [absent signal - log field, metric, trace span, alert rule]
- **Impact:** [what becomes invisible or undetectable]
- **Fix:** [concrete instrumentation change]

### Medium Severity (reduces diagnosis speed)

[Same structure]

### Low Severity (nice-to-have, no current blind spot)

[Same structure]

_Omit sections with no findings._

## Next Steps

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
```

## Self-Check

- [ ] `behavioral-principles` loaded before any other step
- [ ] `stack-detect` ran at Step 1
- [ ] If a stack matched, the dispatched workflow ran and Step 3 was skipped
- [ ] If no stack matched, fallback covered logging, metrics (backend), tracing (backend), frontend observability (frontend), context propagation, and SLO at deep depth
- [ ] Every finding states what becomes invisible without the missing signal
- [ ] Review report written to file via `review-report-writer`

## Avoid

- Running both Step 2 dispatch and Step 3 fallback
- Reporting "missing log" findings without stating what becomes invisible
- Recommending more logging without considering volume cost and alerting noise
- Suggesting metrics with high-cardinality labels
- Treating the fallback as a full equivalent of a stack workflow - install the matching language plugin when one exists
