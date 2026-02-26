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
// Bad — unstructured, missing context
log("User processed: " + userId)

// Good — structured with context
log({
  message: "User processed",
  userId: user.id,
  correlationId: requestContext.correlationId,
  durationMs: elapsed
})
```

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
- Ensure trace context propagation across service boundaries
- Add trace spans for key operations (database queries, external calls, message processing)

If the detected stack is unfamiliar, apply the universal principles above and recommend the user consult their ecosystem's observability tooling documentation.

---

## Avoid (All Stacks)

- Logging sensitive data (passwords, tokens, PII)
- Unstructured logs without context
- Logging too much (noise) or too little (blind spots)
- Missing correlation IDs across service boundaries
- Metrics without alerting thresholds defined
