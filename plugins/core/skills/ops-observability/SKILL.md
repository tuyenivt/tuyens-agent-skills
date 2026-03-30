---
name: ops-observability
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

- Use the framework's standard or recommended logging library (e.g., SLF4J, log/slog, Rails.logger, Python logging, Elixir Logger, Laravel Log facade / Monolog)
- **Go**: `log/slog` with `slog.JSONHandler` for structured logging, `context.Context` for request-scoped values and trace propagation, `go.opentelemetry.io/otel` for distributed tracing, `prometheus/client_golang` or OTel metrics for Prometheus-compatible metrics
- Use the framework's mechanism for request-scoped context propagation (e.g., MDC, context.Context, CurrentAttributes, contextvars, Laravel middleware context)
- Configure JSON output formatting using the ecosystem's standard encoder or formatter

## Metrics

Instrument **RED metrics** (Rate, Errors, Duration) at every service boundary:

```
// Rate: request count by endpoint and status
http_requests_total{method="POST", endpoint="/api/orders", status="201"}

// Errors: error count by endpoint and error type
http_errors_total{method="POST", endpoint="/api/orders", error="validation"}

// Duration: latency histogram by endpoint
http_request_duration_seconds{method="POST", endpoint="/api/orders"}
  -> track p50, p95, p99 from histogram buckets
```

**Metric types and when to use each:**

| Type      | Use For                                 | Example                         |
| --------- | --------------------------------------- | ------------------------------- |
| Counter   | Cumulative totals that only go up       | Total requests, total errors    |
| Histogram | Distribution of values (latency, sizes) | Request duration, response size |
| Gauge     | Values that go up and down              | Active connections, queue depth |

**Business metrics** -- define at least one metric per critical business operation (e.g., `orders_completed_total`, `payment_success_rate`). These detect revenue-impacting issues that RED metrics alone may miss.

Use the metrics library standard for the detected ecosystem (e.g., Micrometer, Prometheus client, Yabeda, StatsD).

## Distributed Tracing

Add trace spans for key operations to make the request lifecycle visible:

- **Service entry point** -- automatic span from framework middleware
- **Database queries** -- span per query with query template (not parameters) as span attribute
- **External HTTP calls** -- span per outbound request with target service name
- **Message publish/consume** -- span linking producer to consumer across async boundaries
- **Cache operations** -- span for cache reads/writes on hot paths

**Sampling strategy** -- tracing every request is expensive at scale. Choose based on traffic volume:

| Strategy   | Use When                                         | Trade-off                             |
| ---------- | ------------------------------------------------ | ------------------------------------- |
| Head-based | Moderate traffic; decision made at request start | Simple; may miss rare errors          |
| Tail-based | High traffic; decision made after request ends   | Captures errors/slow requests; costly |
| Always-on  | Low traffic or debugging                         | Full visibility; high storage cost    |

Start with head-based sampling at 10-20% for high-traffic services. Always sample 100% of errored or slow requests regardless of strategy.

Use OpenTelemetry or the ecosystem's standard tracing library. Ensure trace context propagation across service boundaries (see trace context headers above).

## SLO Definition

For every critical service, define at minimum:

- **SLI (Service Level Indicator)**: the measurable signal (e.g., request success rate, p99 latency)
- **SLO target**: the threshold (e.g., 99.9% success rate over 30 days, p99 < 500ms)
- **Error budget**: `1 - SLO` expressed as allowable downtime/failures per window (e.g., 43.8 min/month for 99.9%)

Flag services with no defined SLO as a **High** observability gap - without an SLO, alerting thresholds are arbitrary and error budget burn goes undetected.

If the detected stack is unfamiliar, apply the universal principles above and recommend the user consult their ecosystem's observability tooling documentation.

### Alerting Principles

Observability signals are only valuable if someone acts on them. Define alerts for:

- **Error rate:** Alert when error rate exceeds SLO burn rate (not on individual errors)
- **Latency:** Alert when p99 latency exceeds threshold for sustained period (e.g., > 500ms for 5 minutes)
- **Saturation:** Alert when resource utilization approaches limits (connection pool > 80%, disk > 90%)
- Page for **symptoms** (error rate spike, latency degradation), not **causes** (CPU high, memory high)
- Use multi-window burn rate alerting for SLO-based alerts to reduce false positives

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
- Observability signals (metrics, logs, traces) without corresponding alerting rules (nobody sees the signals until manual investigation)
