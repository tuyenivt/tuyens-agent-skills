---
name: ops-resiliency
description: Resilience patterns - circuit breakers, retries, timeouts, bulkheads. Auto-detects project stack and adapts patterns to the detected ecosystem.
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

- Every external call must have a timeout - no unbounded waits
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
- Never retry client errors (400, 401, 403) - these will not succeed on retry

### Timeout

- External calls: 3-5s (typical)
- Internal calls: 1-2s (typical)
- Total request timeout = sum of downstream timeouts + buffer
- Always propagate timeout context (e.g., via request context or deadline)

### Timeout Budget

When a request calls multiple downstream services, use a timeout budget to prevent cascading delays:

```
Total request budget: 5s
  -> Service A timeout: 2s
  -> Service B timeout: 2s
  -> Local processing buffer: 1s

If Service A takes 1.8s, remaining budget for Service B = 5s - 1.8s - 1s = 2.2s
If Service A takes 3s (timeout), fail fast - do not call Service B
```

Pass the remaining budget as a deadline/context to each downstream call. Without a budget, a slow first call can leave insufficient time for subsequent calls, causing cascading timeouts.

### Retry Budget

Retries amplify load. Without a budget, a 3-retry policy across 3 services in a chain can turn 1 failed request into 27 downstream calls (3 x 3 x 3). Limit total retries across the request lifecycle:

- Set a **request-level retry budget** (e.g., max 5 total retry attempts per incoming request)
- Decrement the budget on each retry at any level in the chain
- When the budget is exhausted, fail fast with no further retries
- Pass the remaining retry budget as context/header to downstream calls

### Bulkhead

- Isolate failure domains with separate thread/connection pools per downstream service
- Limit concurrent calls to each downstream dependency independently
- Prevents one slow dependency from consuming all resources

### Fallback Patterns

When a dependency fails, degrade gracefully rather than propagating the failure:

| Pattern           | Use When                                                     | Example                                                                |
| ----------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------- | -------------------------------------------- |
| Cached fallback   | Stale data is acceptable                                     | Return cached product catalog when catalog-service is down             |
| Default value     | A reasonable default exists                                  | Return default shipping estimate when shipping-service times out       |
| Partial response  | Some data is better than none                                | Return order without recommendations when recommendation-service fails |
| Queue for later   | Operation can be deferred                                    | Queue the notification for retry instead of failing the order          |
| Provider failover | Multiple providers for same capability (payment, SMS, email) | Route to secondary when primary circuit breaks                         | Payment gateways, notification services, CDN |
| Fail fast         | No safe degradation exists                                   | Return 503 immediately rather than waiting for a timeout               |

Every fallback must log the original failure at WARN level - silent fallbacks hide degradation until it compounds.

### Provider Failover

When multiple providers exist for the same capability, configure circuit breakers per provider and a routing layer that falls back to the next provider when the current one's circuit is open:

1. Try primary provider
2. If primary circuit is open, route to secondary
3. If secondary circuit is open, route to tertiary
4. If all circuits are open, fail fast with clear error to the user

### Parallel vs Sequential External Calls

When calling multiple independent external services, consider the timeout budget:

- **Sequential:** Total time = sum of all timeouts. Use only when calls depend on each other.
- **Parallel with all-must-succeed:** Total time = slowest call. Use when all results are needed.
- **Parallel with first-success:** Total time = fastest call. Use for provider failover with speed priority.

## Stack-Specific Guidance

After loading stack-detect, apply resilience patterns using the libraries and idioms of the detected ecosystem:

- Use the ecosystem's standard resilience library (e.g., Resilience4j for Java, Polly for .NET, retriable/stoplight for Ruby, gobreaker for Go, tenacity for Python, Guzzle retry middleware for PHP)
- Apply circuit breaker, retry, and timeout patterns using the framework's decorator, middleware, or annotation mechanism
- For background job frameworks, leverage built-in retry with exponential backoff where available
- For HTTP clients, use middleware-based timeout and retry configuration native to the ecosystem

If the detected stack is unfamiliar, apply the universal principles above and recommend the user consult their ecosystem's resilience library documentation.

---

## Output Format

Consuming workflow skills depend on this structure to surface resilience gaps consistently.

```
## Resiliency Assessment

**Stack:** {detected language / framework}

### Gaps

- [Severity: High | Medium | Low] {integration point or component} - {description of gap}
  - Missing: {timeout | retry | circuit breaker | bulkhead | fallback}
  - Risk: {what failure mode this gap enables}
  - Recommendation: {concrete pattern and library for the detected stack}

### No Gaps Found

{State explicitly if resilience patterns are adequate - do not omit this section silently}
```

**Severity guidance:**

- **High**: Missing timeout or retry on an external call with no circuit breaker
- **Medium**: Retry without jitter, or circuit breaker without monitoring
- **Low**: Missing bulkhead isolation where one exists elsewhere in the codebase

Omit "No Gaps Found" if gaps were listed.

## Avoid (All Stacks)

- External calls without timeouts (unbounded resource consumption)
- Retrying non-idempotent operations without safety guarantees
- Circuit breakers without monitoring (you need to know when they trip)
- Retrying on non-transient errors (400, 401, 403 - these won't succeed on retry)
- Fallbacks that silently swallow errors without logging or alerting
