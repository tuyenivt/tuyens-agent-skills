---
name: resiliency
description: Resilience patterns — circuit breakers, retries, timeouts, bulkheads. Auto-detects project stack and adapts patterns to the detected ecosystem.
metadata:
  category: ops
  tags: [resilience, circuit-breaker, retry, timeout, multi-stack]
user-invocable: false
---

# Resiliency

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Calling external services or APIs that may fail or be slow
- Designing fault-tolerant service communication
- Protecting internal services from cascading failures
- Implementing retry logic for transient errors

## Universal Principles (All Stacks)

- Every external call must have a timeout — no unbounded waits
- Retries must use exponential backoff with jitter
- Circuit breakers must define open/half-open/closed thresholds
- Bulkhead isolation for independent failure domains
- Always define a fallback behavior (degrade gracefully, not catastrophically)

---

## Resilience Patterns

### Circuit Breaker

Prevents cascading failures by stopping calls to a failing dependency:

- **Closed** → Normal operation; track failure rate
- **Open** → Reject calls immediately; return fallback
- **Half-Open** → Allow limited test calls; transition to closed if successful

Configuration principles:

- Failure rate threshold (e.g., 50% over a sliding window)
- Wait duration in open state before transitioning to half-open (e.g., 30s)
- Number of permitted calls in half-open state (e.g., 3-10)

### Retry with Backoff

For transient failures only (5xx, timeouts, connection errors):

- Max attempts: 3 (typical)
- Exponential backoff: start at 500ms, multiply by 2, cap at a reasonable maximum
- Add jitter to prevent thundering herd
- Never retry non-idempotent operations without idempotency keys
- Never retry client errors (400, 401, 403) — these will not succeed on retry

### Timeout

- External calls: 3-5s (typical)
- Internal calls: 1-2s (typical)
- Total request timeout = sum of downstream timeouts + buffer
- Always propagate timeout context (e.g., via request context or deadline)

### Bulkhead

- Isolate failure domains with separate thread/connection pools per downstream service
- Limit concurrent calls to each downstream dependency independently
- Prevents one slow dependency from consuming all resources

## Stack-Specific Guidance

After loading stack-detect, apply resilience patterns using the libraries and idioms of the detected ecosystem:

- Use the ecosystem's standard resilience library (e.g., Resilience4j for Java, Polly for .NET, retriable/stoplight for Ruby, gobreaker for Go, tenacity for Python)
- Apply circuit breaker, retry, and timeout patterns using the framework's decorator, middleware, or annotation mechanism
- For background job frameworks, leverage built-in retry with exponential backoff where available
- For HTTP clients, use middleware-based timeout and retry configuration native to the ecosystem

If the detected stack is unfamiliar, apply the universal principles above and recommend the user consult their ecosystem's resilience library documentation.

---

## Avoid (All Stacks)

- External calls without timeouts (unbounded resource consumption)
- Retrying non-idempotent operations without safety guarantees
- Circuit breakers without monitoring (you need to know when they trip)
- Retrying on non-transient errors (400, 401, 403 — these won't succeed on retry)
- Fallbacks that silently swallow errors without logging or alerting
