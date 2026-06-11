---
name: ops-observability
description: Structured logging, RED metrics, distributed tracing, SLOs, and symptom-based alerting across stacks.
metadata:
  category: ops
  tags: [logging, metrics, tracing, monitoring, slo, alerting, multi-stack]
user-invocable: false
---

# Observability

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing logging, metrics, and tracing coverage on a service
- Identifying gaps that would prevent detecting or diagnosing a production failure
- Defining SLOs and alerting strategy for a critical path

## Rules

- Logs are structured (JSON), with mandatory fields `level`, `service`, `trace_id`, `span_id`.
- Trace context propagates across every service boundary using a standard header; receiving services create child spans, never new trace IDs.
- Never log secrets or PII (passwords, tokens, personal data).
- Every entry point (API endpoint, queue consumer, scheduled job) has RED metrics: **R**ate, **E**rrors, **D**uration - measured per unit of work.
- Log levels carry meaning: `info` for state changes, `debug` for per-item detail. Never log per-iteration at `info` in hot loops - aggregate or sample.
- Every critical service has an SLO; alerting thresholds without an SLO are arbitrary.
- Alert on **symptoms** (error rate, latency, saturation), not causes (CPU, memory).
- Every metric and log signal has a corresponding alert or dashboard; unwatched signals are dead.

## Patterns

### Structured Logging

```
// Bad - unstructured, no context
log("User processed: " + userId)

// Good - structured, correlatable
log({
  message: "User processed",
  level: "info",
  service: "order-service",
  trace_id: ctx.traceId,    // W3C traceparent or equivalent
  span_id:  ctx.spanId,
  user_id:  user.id,
  duration_ms: elapsed
})
```

### Trace Context Propagation

Use a standard propagation header end-to-end:

- **W3C `traceparent`** - recommended; OpenTelemetry default
- **`b3` / `x-b3-traceid`** - Zipkin; common in older Spring Cloud / Istio
- **`uber-trace-id`** - Jaeger

The receiving service extracts incoming context and creates a child span. Use the ecosystem's standard propagator and request-scoped context mechanism (MDC, `context.Context`, contextvars, framework middleware) so trace IDs reach every log line. Across async boundaries (queues, jobs) the carrier is message headers or attributes, not HTTP headers; the consumer extracts context from the message before starting its span.

### RED Metrics

```
http_requests_total{method, endpoint, status}                    // Rate
http_errors_total{method, endpoint, error_type}                  // Errors
http_request_duration_seconds{method, endpoint}  -> p50/p95/p99  // Duration
```

| Type      | Use For                                 | Example                         |
| --------- | --------------------------------------- | ------------------------------- |
| Counter   | Cumulative totals that only go up       | Total requests, total errors    |
| Histogram | Distribution of values                  | Request duration, response size |
| Gauge     | Values that go up and down              | Active connections, queue depth |

Define at least one **business metric** per critical operation (e.g., `orders_completed_total`, `payment_success_rate`); RED alone misses revenue-impacting issues.

### Distributed Tracing

Span the key segments of a request:

- Service entry point (framework middleware)
- Database queries (span per query, attribute = query template, never parameters)
- External HTTP calls (span per outbound request, attribute = target service)
- Message publish/consume (link producer to consumer span across async boundaries)
- Cache reads/writes on hot paths

**Sampling:**

| Strategy   | Use When                            | Trade-off                       |
| ---------- | ----------------------------------- | ------------------------------- |
| Head-based | Moderate traffic; decide at start   | Simple; may miss rare errors    |
| Tail-based | High traffic; decide after end      | Captures errors/slow; costly    |
| Always-on  | Low traffic, debugging              | Full visibility; high storage   |

Start head-based at 10-20% for high-traffic services; always sample 100% of errored or slow requests regardless of strategy.

### SLOs and Alerting

Each critical service defines:

- **SLI** - the measurable signal (success rate, p99 latency)
- **SLO target** - the threshold (e.g., 99.9% success over 30 days, p99 < 500ms)
- **Error budget** - `1 - SLO` as allowable failures per window (e.g., 43.8 min/month at 99.9%)

Alert on:

- **Error rate** - SLO burn rate over multi-window (reduces false positives), not individual errors
- **Latency** - sustained p99 breach (e.g., > 500ms for 5 min)
- **Saturation** - resource utilization approaching limits (pool > 80%, disk > 90%)

### Stack Adaptation

After `stack-detect`, apply the patterns using the ecosystem's standard libraries: the framework's logging library configured for JSON output, an OpenTelemetry-compatible tracing library, a Prometheus-compatible metrics library, and the framework's request-scoped context mechanism for trace propagation. If the detected stack is unfamiliar, apply the universal patterns above and recommend the user verify against their ecosystem's observability docs.

## Output Format

Consuming workflow skills parse this structure to surface observability gaps.

```
## Observability Assessment

**Stack:** {detected language / framework}

### Gaps

- [Severity: High | Medium | Low] {component or layer} - {description of gap}
  - Missing: {signal absent - log field, metric, trace span, SLO}
  - Impact: {what becomes invisible or undetectable}
  - Recommendation: {concrete addition with library/mechanism for the detected stack}

### No Gaps Found

{State explicitly if observability is adequate - do not omit silently.}
```

**Severity:**

- **High**: gap prevents detecting a production failure (no error rate on critical path, no SLO on critical service, missing trace propagation across boundary).
- **Medium**: gap slows diagnosis (missing correlation ID on internal calls, no business metric on key flow).
- **Low**: nice-to-have signal with no current blind spot.

Omit "No Gaps Found" if gaps were listed.

## Avoid

- Logging secrets or PII.
- Unstructured logs, or logs without `trace_id` / `span_id`.
- Generating a new trace ID at a service boundary instead of propagating the incoming one.
- Metrics or traces with no corresponding alert or dashboard.
- Paging on causes (CPU high, memory high) instead of symptoms (error rate, latency).
- Defining SLOs in name only, without burn-rate alerting.
