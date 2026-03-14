---
name: observability
description: Structured logging, metrics, and distributed tracing patterns. Auto-detects project stack and adapts observability guidance to the detected ecosystem.
metadata:
  category: ops
  tags: [logging, metrics, tracing, monitoring, multi-stack]
user-invocable: false
---

# Observability

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Debugging production issues
- Monitoring application health and performance
- Understanding distributed system behavior

## Universal Principles (All Stacks)

- Use structured logs (JSON) with consistent fields
- Include correlation ID in all logs for request tracing
- Never log sensitive data (passwords, tokens, PII)
- Implement RED metrics for APIs: Rate, Errors, Duration
- Track key business metrics
- Enable distributed tracing and propagate trace context
- Alert on symptoms, not causes

---

## Structured Logging

Every ecosystem has a recommended structured logging approach. The universal pattern is:

```
// Bad - unstructured, missing context
log("User processed: " + userId)

// Good - structured with mandatory fields
log({
  message: "User processed",
  level: "info",
  service: "order-service",
  trace_id: traceContext.traceId,       // W3C traceparent or equivalent
  span_id: traceContext.spanId,
  user_id: user.id,
  duration_ms: elapsed
})
```

**Mandatory fields for every log entry:** `level`, `service`, `trace_id`, `span_id`. Without `trace_id`/`span_id`, log correlation across services in a distributed trace is impossible.

### Distributed Trace Context Propagation

Propagate trace context across service boundaries using standard headers:
- **W3C `traceparent`** (recommended, OpenTelemetry default)
- **`b3` / `x-b3-traceid`** (Zipkin, still common in older Spring Cloud deployments)
- **`uber-trace-id`** (Jaeger)

The receiving service must extract the incoming trace context and create child spans - not generate a new trace ID. Use the ecosystem's standard propagator (e.g., `W3CTraceContextPropagator` in OTel, Spring Cloud Sleuth/Micrometer Tracing).

### Stack-Specific Guidance

After loading stack-detect, apply structured logging using the libraries and patterns of the detected ecosystem:

- Use the framework's standard or recommended logging library (e.g., SLF4J, log/slog, Rails.logger, Python logging, Elixir Logger)
- Use the framework's mechanism for request-scoped context propagation (e.g., MDC, context.Context, CurrentAttributes, contextvars)
- Configure JSON output formatting using the ecosystem's standard encoder or formatter

## Metrics

- Instrument RED metrics (Rate, Errors, Duration) at every service boundary
- Use the metrics library standard for the detected ecosystem (e.g., Micrometer, Prometheus client, Yabeda, StatsD)
- Define custom metrics for business-critical operations

## Distributed Tracing

- Use OpenTelemetry or the ecosystem's standard tracing library
- Ensure trace context propagation across service boundaries (see trace context headers above)
- Add trace spans for key operations (database queries, external calls, message processing)

## SLO Definition

For every critical service, define at minimum:

- **SLI (Service Level Indicator)**: the measurable signal (e.g., request success rate, p99 latency)
- **SLO target**: the threshold (e.g., 99.9% success rate over 30 days, p99 < 500ms)
- **Error budget**: `1 - SLO` expressed as allowable downtime/failures per window (e.g., 43.8 min/month for 99.9%)

Flag services with no defined SLO as a **High** observability gap - without an SLO, alerting thresholds are arbitrary and error budget burn goes undetected.

If the detected stack is unfamiliar, apply the universal principles above and recommend the user consult their ecosystem's observability tooling documentation.

---

## Output Format

Consuming workflow skills depend on this structure to surface observability gaps consistently.

```
## Observability Assessment

**Stack:** {detected language / framework}

### Gaps

- [Severity: High | Medium | Low] {component or layer} - {description of gap}
  - Missing: {what signal is absent - log field, metric, trace span}
  - Impact: {what becomes invisible or undetectable without it}
  - Recommendation: {concrete addition with library/mechanism for the detected stack}

### No Gaps Found

{State explicitly if observability is adequate - do not omit this section silently}
```

**Severity guidance:**

- **High**: Gap that would prevent detection of a production failure (e.g., no error rate metric on a critical path)
- **Medium**: Gap that reduces diagnosis speed (e.g., missing correlation ID on internal calls)
- **Low**: Nice-to-have signal with no current blind spot (e.g., missing business metric)

Omit "No Gaps Found" if gaps were listed.

## Avoid (All Stacks)

- Logging sensitive data (passwords, tokens, PII)
- Unstructured logs without context
- Logging too much (noise) or too little (blind spots)
- Missing correlation IDs across service boundaries
- Metrics without alerting thresholds defined
