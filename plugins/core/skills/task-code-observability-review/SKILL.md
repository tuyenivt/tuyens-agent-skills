---
name: task-code-observability-review
description: Observability review for backend services and frontend applications - structured logging, RED metrics, distributed tracing, correlation ID propagation, SLO definition, alerting coverage, and error tracking instrumentation. Use when an outage was hard to diagnose, before a release of a new service, when adopting OpenTelemetry, or when production behavior is invisible to the team.
metadata:
  category: review
  tags: [observability, logging, metrics, tracing, monitoring, slo, multi-stack]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Observability Review

## Purpose

Identify and prioritize observability gaps across backend services and frontend applications. Produces findings ordered by severity with concrete instrumentation additions. Focuses on whether production behavior is visible, diagnosable, and alertable - not on application correctness.

## When to Use

- Pre-release observability check for a new service or major feature
- Post-incident review when diagnosis was slow or evidence was missing
- Adopting or migrating to OpenTelemetry / structured logging / SLO-based alerting
- Audit of an existing service whose production behavior is opaque
- Reviewing instrumentation added by AI-generated code (often missing trace context, logging-only without metrics)

**Not for:** General code review (use `task-code-review`), security review (use `task-code-secure-review`), performance issues with a known bottleneck (use `task-code-perf-review`), active incident investigation (use oncall plugin's `incident-root-cause`).

## Depth Levels

| Depth      | When to Use                                                | What Runs                                           |
| ---------- | ---------------------------------------------------------- | --------------------------------------------------- |
| `quick`    | Single endpoint, handler, or focused change                | Logging + metrics check on the targeted code only   |
| `standard` | Default - full observability review                        | All steps                                           |
| `deep`     | Pre-release of a critical service, or post-incident review | All steps + SLO definition + alerting rule coverage |

Default: `standard`. Use `quick` when the user targets a specific file or endpoint.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 - Run Observability Atomic

Use skill: `ops-observability` to assess structured logging, RED metrics, distributed tracing, correlation ID propagation, and SLO definition for the detected stack.

This is the primary source of findings. The remaining steps complement it with cross-cutting concerns the atomic does not own.

### Step 3 - Structured Logging Review (All Stacks)

Verify the code under review:

- [ ] Logs are structured (JSON or framework's structured format) - no `printf`/`console.log` of concatenated strings on hot paths
- [ ] Mandatory fields present: `level`, `service`, `trace_id`, `span_id` (or framework equivalent)
- [ ] No sensitive data logged: passwords, tokens, full PII, full request bodies on auth endpoints
- [ ] Log levels used correctly: `error` for actionable failures, `warn` for recoverable anomalies, `info` for state transitions, `debug` for verbose diagnostics
- [ ] No log spam in hot loops or per-request inner functions

### Step 4 - Metrics Coverage (Backend and Fullstack)

Skip this step if `Stack Type: frontend`.

- [ ] RED metrics (Rate, Errors, Duration) present on every external API endpoint and inbound interface
- [ ] Custom business metrics defined for revenue-impacting or SLO-tracked operations (e.g., `orders_completed_total`, `payment_success_rate`)
- [ ] Histograms used for latency (not gauges or averages); p50/p95/p99 derivable from buckets
- [ ] Counters used for cumulative totals; gauges only for instantaneous values that go up and down
- [ ] No high-cardinality labels (user ID, request ID, raw URL with parameters) - these blow up storage and break aggregation
- [ ] Database query and external HTTP call latency tracked separately from total request duration

### Step 5 - Distributed Tracing (Backend and Fullstack)

Skip this step if `Stack Type: frontend` and the application has no backend-for-frontend or server-side rendering.

- [ ] Service entry points produce a span automatically (framework middleware enabled)
- [ ] Database queries produce spans with the query template (not the parameterized values) as an attribute
- [ ] External HTTP calls produce spans with the target service name attribute
- [ ] Message publish/consume produces linked spans across the async boundary
- [ ] Trace context is **propagated** across service boundaries via standard headers (W3C `traceparent`, `b3`, or `uber-trace-id`) - the receiving service must extract and create child spans, not generate a new trace ID
- [ ] Sampling strategy is appropriate for traffic volume (head-based 10-20% for high traffic; always sample errors and slow requests at 100%)

### Step 6 - Frontend Observability (Frontend and Fullstack)

Skip this step if `Stack Type: backend`.

- [ ] Error tracking installed (Sentry, Rollbar, or framework equivalent) and source maps uploaded for production builds
- [ ] Unhandled promise rejections and global error handlers wired to the error tracker
- [ ] Core Web Vitals reported (LCP, INP, CLS) via the framework's reporting mechanism or `web-vitals` library
- [ ] User journey / funnel events instrumented for critical flows (signup, checkout, key feature usage)
- [ ] No PII in analytics events or error reports (sanitize before send)
- [ ] Trace context propagated from frontend to backend on outbound API calls (W3C `traceparent` header) when distributed tracing spans the full stack

### Step 7 - SLO and Alerting Coverage (All Stacks, Deep Depth)

Run this step at `deep` depth or when the user explicitly requests SLO/alert coverage. At `standard` depth, summarize gaps without exhaustive enumeration.

- [ ] At least one SLI defined per critical service with a measurable signal (e.g., success rate, p99 latency)
- [ ] SLO target stated with window (e.g., 99.9% over 30 days)
- [ ] Error budget derived and burn-rate alerting configured
- [ ] Alerts page on **symptoms** (error rate, latency, saturation), not **causes** (CPU, memory)
- [ ] Multi-window burn-rate alerts used to reduce false positives on SLO-based alerts
- [ ] Every metric has at least one corresponding alert rule, or is explicitly documented as informational-only

Flag services with no defined SLO as a **High** observability gap - without an SLO, alerting thresholds are arbitrary.

### Step 8 - Correlation and Context Propagation (All Stacks)

- [ ] Request-scoped context (correlation ID, trace ID, user ID where appropriate) propagated through the framework's mechanism (MDC, `context.Context`, `CurrentAttributes`, `contextvars`, middleware context)
- [ ] Background jobs and queue consumers extract trace context from the message envelope - not generate a new trace
- [ ] Async operations (goroutines, threads, promises) carry context forward; no orphaned spans

## Self-Check

- [ ] Stack Type determined; backend steps skipped for frontend-only, frontend steps skipped for backend-only
- [ ] **All stacks**: Structured logging assessed: mandatory fields, no sensitive data, correct log levels
- [ ] **Backend/fullstack**: RED metrics coverage checked; cardinality concerns flagged
- [ ] **Backend/fullstack**: Distributed tracing reviewed: spans on key operations, context propagation across services, sampling strategy
- [ ] **Frontend/fullstack**: Error tracking, Core Web Vitals, and user journey instrumentation reviewed
- [ ] **Deep depth**: SLOs and alerting rules audited; symptom-based alerting verified
- [ ] **All stacks**: Context propagation across async boundaries and service boundaries verified
- [ ] Every finding states the missing signal AND what becomes invisible without it - not just "add a log here"
- [ ] Findings ordered by severity; quick wins separated from structural changes

## Output Format

```markdown
## Observability Review Summary

**Stack Detected:** [language / framework]
**Scope:** Backend | Frontend | Fullstack
**Overall:** Adequate | Gaps Found - [count by severity: High/Medium/Low]

## Findings

### High Severity (would prevent detection of a production failure)

- **Location:** [file:line, component, or service boundary]
- **Missing:** [the absent signal - log field, metric, trace span, alert rule]
- **Impact:** [what becomes invisible or undetectable]
- **Fix:** [concrete instrumentation change with library/mechanism for the detected stack]

### Medium Severity (reduces diagnosis speed)

[Same structure]

### Low Severity (nice-to-have, no current blind spot)

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Adopt OpenTelemetry for tracing across all services", "Define SLOs for the checkout service", "Replace homegrown correlation ID with W3C traceparent"]

## No Gaps Found

[State explicitly if observability is adequate - do not omit this section silently when no findings exist]
```

## Avoid

- Reporting "missing log" findings without stating what becomes invisible
- Recommending more logging without considering log volume cost and alerting noise
- Suggesting metrics with high-cardinality labels (request ID, user ID, raw URL) - these break aggregation and cost
- Treating logging, metrics, and tracing as interchangeable - they answer different questions (what happened / how often / why this specific request)
- Conflating observability review with general code review or performance review - stay focused on production visibility
- Recommending observability tooling without addressing alerting - signals nobody acts on are wasted
