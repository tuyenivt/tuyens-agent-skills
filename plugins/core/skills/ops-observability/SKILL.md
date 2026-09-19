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

Incident history is input: a signal whose absence let an incident run is a gap with its evidence already written.

## Rules

- Logs are structured (JSON), with mandatory fields `level`, `service`, `trace_id`, `span_id`.
- Trace context propagates across every service boundary using a standard header; receiving services create child spans, never new trace IDs. An internal call is a boundary too.
- Never log secrets or personal data (passwords, tokens, names, contact details, card data). Opaque identifiers (`user_id`, `order_id`) are correlation fields, safe to log because they carry no directly identifying value. Deliberate logging is rarely the leak - check the indirect carriers: full URLs with query strings, request/response body dumps in error handlers, exception messages quoting the offending value (a leak whether or not a log statement currently prints them - they will be logged the first time someone adds one), and header dumps carrying `Authorization` or `Cookie`. Log the route template (`/users/search`), not the resolved URL.
- Every entry point (API endpoint, queue consumer, scheduled job) has RED metrics: **R**ate, **E**rrors, **D**uration - measured per unit of work. Every critical operation has a business-metric counter; every scheduled or event-driven job has an absence alert.
- Log levels carry meaning: `info` for state changes, `debug` for per-item detail. Never log per-iteration at `info` in hot loops - aggregate or sample.
- Every critical service has an SLO; alerting thresholds without an SLO are arbitrary.
- Alert on **symptoms** (error rate, latency, saturation), not causes (CPU, memory growth).
- Every metric and log signal has a corresponding alert or dashboard; unwatched signals are dead. A business metric on a critical flow has an alert, not only a dashboard.

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
  trace_id: ctx.traceId,    // the trace-id field of the W3C traceparent header, or equivalent
  span_id:  ctx.spanId,
  user_id:  user.id,        // opaque identifier - correlation, not personal data
  duration_ms: elapsed
})
```

### Trace Context Propagation

Use a standard propagation header end-to-end:

- **W3C `traceparent`** (`00-<trace-id>-<parent-id>-<flags>`) with `tracestate` - recommended; OpenTelemetry default
- **B3** - Zipkin and Brave; single header `b3: <trace-id>-<span-id>-<sampled>` or the multi-header set `X-B3-TraceId`, `X-B3-SpanId`, `X-B3-ParentSpanId`, `X-B3-Sampled` (forward the whole set, never the trace id alone); Micrometer Tracing configured for B3 on Spring Boot 3
- **`uber-trace-id`** - Jaeger

A service mesh forwards whichever family its tracing provider uses; it cannot carry context through the application's own in-process hops, so the application propagates regardless.

The receiving service extracts incoming context and creates a child span. Use the ecosystem's standard propagator and request-scoped context mechanism (MDC, `context.Context`, contextvars, framework middleware) so trace IDs reach every log line. Across async boundaries (queues, jobs) the carrier is message headers or attributes, not HTTP headers; the consumer extracts context from the message before starting its span.

### RED Metrics

```
http_requests_total{method, route, status}                       // Rate; Errors = the 5xx share of the same counter
http_request_duration_seconds_bucket{method, route, le}          // Duration histogram
  p99 = histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))

queue_messages_processed_total{queue, result}                    // consumer Rate + Errors
job_runs_total{task, result} / job_duration_seconds_bucket{task, le} // scheduled job Rate + Errors + Duration (`job` is Prometheus's scrape-target label; an exposed `job` is renamed `exported_job`)
```

One counter with a `status`/`result` label carries both rate and errors; a separate errors counter counts the same events twice and drifts.

| Type      | Use For                                 | Example                         |
| --------- | --------------------------------------- | ------------------------------- |
| Counter   | Cumulative totals that only go up       | Total requests, total errors    |
| Histogram | Distribution of values; percentiles are computed at query time from the buckets | Request duration, response size |
| Gauge     | Values that go up and down              | Active connections, queue depth |

Define at least one **business metric** per critical operation, exported as a counter (`orders_completed_total`, `payments_total{outcome}`) and computed into a rate at query time; RED alone misses revenue-impacting issues.

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
| Head-based | Decide at trace start; simple       | A fixed rate cannot guarantee capture of errors or slow traces |
| Tail-based | Decide after the trace ends         | Captures every error and slow trace the policy names, when every span of a trace reaches one collector (trace-id-aware load balancing); costs buffering |
| Always-on  | Low traffic, debugging              | Full visibility; high storage   |

Head-based at a fixed rate set by span volume and retention cost is the usual baseline for high-traffic services; keeping 100% of errored or slow requests requires tail-based sampling, or local tail sampling that records every span in process and decides when the root span ends.

### SLOs and Alerting

Each critical service defines:

- **SLI** - the measurable signal (success rate, p99 latency)
- **SLO target** - a proportion over a window (99.9% success over 30 days; 99% of requests under 500 ms over 30 days) - a bare threshold (`p99 < 500 ms`) is an alert rule, not an SLO, and has no budget
- **Error budget** - `1 - SLO` per window, in the SLI's own unit: 0.1% of requests for a request-based SLI (43.2 min for a time-based availability SLI over 30 days)

Alert on:

- **Error rate** - SLO burn rate over multi-window (reduces false positives), not individual errors; the standard pairs are 14.4x over 1 h with 5 min, 6x over 6 h with 30 min (page), 3x over 24 h (ticket), against a 30-day window. A path with fewer than a few hundred events per window (a daily job, a 40-requests-an-hour tool) alerts on absolute counts instead.
- **Latency** - sustained p99 breach (e.g., > 500ms for 5 min)
- **Saturation** - resources that hard-fail requests when exhausted (connection pool > 80%, disk > 90%, FD limit, memory at the OOM boundary). CPU and gradual memory growth degrade slowly and page poorly - they are the "causes" the symptom rule excludes.
- **Absence** - for scheduled and event-driven work, the failure is silence: alert when a job has not completed within its expected interval, or when throughput drops to zero on a stream that normally flows. Rate and latency alerts cannot fire for work that never started, so a job with only RED metrics is unmonitored against its most likely failure. The signal is a heartbeat or last-success timestamp with a staleness threshold set above the normal interval plus expected runtime.

### Stack Adaptation

After `stack-detect`, apply the patterns using the ecosystem's standard libraries: the framework's logging library configured for JSON output, an OpenTelemetry-compatible tracing library, a Prometheus-compatible metrics library, and the framework's request-scoped context mechanism for trace propagation. When `Language` is `unknown`, apply the universal patterns above and recommend the user verify against their ecosystem's observability docs.

### Good

```
## Observability Assessment

**Stack:** Python 3.12 / FastAPI

### Gaps

- [Severity: High] refund request path, `app/api/refunds.py:18` (also `app/workers/receipts.py:9`) - no trace context enters the request or crosses the Celery boundary
  - Signal: absent - context propagation
  - Impact: a refund cannot be followed from the API call to the receipt task; retries and duplicates are uncorrelated
  - Recommendation: opentelemetry-instrumentation-fastapi at the entry point and opentelemetry-instrumentation-celery, which injects `traceparent` into task headers
- [Severity: High] payment gateway client, `app/services/payment_gateway.py:37` - the gateway response body, which echoes card details, is embedded in the exception message
  - Signal: removal - secret/personal data in logs or exception messages
  - Impact: card data reaches every log sink the first time the exception is logged
  - Recommendation: raise with the status code and a gateway error code only; keep the body out of the exception
```

## Output Format

Consuming workflow skills parse this structure to surface observability gaps. One gap per fix: the sites one change closes are one gap anchored at the entry point, naming the other sites (a missing tracer at three files); three leaks under one rule with three fix sites are three gaps. Gaps cover the axes the caller named, every rule when none is named. Order gaps by severity, High first.

```
## Observability Assessment

**Stack:** {language / framework | unknown - verify against ecosystem docs}

### Gaps                                        {when at least one gap}

- [Severity: High | Medium | Low] {entry point or layer, file:line, other sites in parentheses} - {description of gap}
  - Signal: {absent - <log field | metric | trace span | context propagation | alert | dashboard | SLO> | removal - secret/personal data in logs or exception messages | replacement - cause-based page -> <symptom alert> | misuse - <per-iteration info log | cause-based page beside an existing symptom alert>}
  - Impact: {what becomes invisible or undetectable; for a removal, what is disclosed}
  - Recommendation: {concrete addition with library/mechanism for the detected stack, or the ecosystem docs to verify against when the stack is unknown}

### No Gaps Found                               {instead, when none: one sentence stating observability is adequate}
```

**Severity:**

- **High**: gap prevents detecting a production failure - no error rate on a critical path, no SLO on a critical service, an SLO with no burn-rate alerting, no saturation alert on a resource that hard-fails, no absence alert on scheduled work, missing trace propagation across any boundary, no business metric on a flow whose failure RED cannot see, a cause-based page with no symptom alert (`replacement`) - or a secret/personal-data value reaching logs or exception messages
- **Medium**: gap slows diagnosis - a business metric with a dashboard but no alert, a span missing on a hot path, every `misuse` signal
- **Low**: nice-to-have signal with no current blind spot

In definition mode (designing SLOs or alerting rather than reviewing), emit the same heading and Stack line, then one block per critical path; one trailing `### Gaps` for all paths follows for signals the design still lacks, `### No Gaps Found` otherwise.

```
### {critical path}

SLI: {measurable signal}; {second SLI when there is one}

SLO: {proportion over window, per SLI}

Error budget: {1 - SLO in the SLI's unit per window, per SLI}

Alerts:
- burn rate: {multi-window rule, or "n/a - fewer than a few hundred events per window; alert on absolute counts: <count>"}
- latency: {sustained breach rule, or "n/a - no latency SLI on this path"}
- saturation: {hard-fail resource thresholds, or "n/a - no hard-fail resource on this path"}
- absence: {heartbeat/staleness rule, or "n/a - no scheduled or event-driven work on this path"}
```

## Avoid

- Logging secrets or personal data.
- Unstructured logs, or logs without `trace_id` / `span_id`.
- Generating a new trace ID at a service boundary instead of propagating the incoming one.
- Metrics or traces with no corresponding alert or dashboard.
- Paging on causes (CPU high, memory growing) instead of symptoms (error rate, latency, saturation).
- Defining SLOs in name only, without burn-rate alerting.
