---
name: ops-resiliency
description: Circuit breakers, retries with backoff, timeouts, bulkheads, and graceful fallbacks across stacks.
metadata:
  category: ops
  tags: [resilience, circuit-breaker, retry, timeout, bulkhead, fallback, multi-stack]
user-invocable: false
---

# Resiliency

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Calling external services or APIs that may fail or be slow
- Designing fault-tolerant service-to-service communication
- Protecting internal services from cascading failures

## Rules

- Every external call has a timeout; no unbounded waits.
- Retries use exponential backoff with jitter, max attempts capped (typically 3).
- Retry only transient errors (5xx, timeouts, connection errors). Never retry 4xx (won't succeed) or non-idempotent operations without an idempotency key.
- Circuit breakers define explicit thresholds (failure rate, open duration, half-open probes) and are monitored - a silent breaker is useless.
- Independent failure domains use bulkhead isolation (separate pools per downstream).
- Every dependency has a defined fallback. Every fallback logs the original failure at WARN; silent fallbacks hide degradation until it compounds.

## Patterns

### Circuit Breaker

- **Closed** - normal; track failure rate.
- **Open** - reject calls immediately; return fallback.
- **Half-Open** - allow limited test calls; close on success, reopen on failure.

Configure: failure-rate threshold over a sliding window (e.g., 50%), open duration before half-open (e.g., 30s), permitted probes in half-open (e.g., 3-10).

### Retry with Backoff

- Start backoff at ~500 ms, multiply by 2, cap at a reasonable maximum.
- Add jitter to prevent thundering herd.
- Pair retries with idempotency keys for non-idempotent ops.

### Timeout

- External calls: 3-5 s typical. Internal calls: 1-2 s typical.
- Total request timeout = sum of downstream timeouts + buffer.
- Propagate timeout context (deadline / request context) to downstream calls.

### Timeout Budget

A request calling multiple downstream services shares one budget.

```
Total budget: 5s
  Service A timeout: 2s
  Service B timeout: 2s
  Local processing buffer: 1s

If A takes 1.8s -> remaining for B = 5 - 1.8 - 1 = 2.2s
If A times out at 3s -> fail fast; do not call B
```

Pass remaining budget as a deadline to each downstream call. Without a shared budget, a slow first call leaves no time for subsequent calls, producing cascading timeouts.

### Retry Budget

Retries amplify load. Three services chained with 3 retries each turn one failed request into `3*3*3 = 27` downstream calls. Cap retries per request (e.g., 5 total across the chain), decrement on each retry at any layer, and pass the remaining budget downstream.

### Bulkhead

Separate thread / connection pools per downstream dependency. One slow dependency cannot consume the pool used by other dependencies.

### Fallback Patterns

| Pattern           | Use When                                     | Example                                                       |
| ----------------- | -------------------------------------------- | ------------------------------------------------------------- |
| Cached fallback   | Stale data is acceptable                     | Cached product catalog when catalog-service is down           |
| Default value     | A reasonable default exists                  | Default shipping estimate when shipping-service times out     |
| Partial response  | Some data is better than none                | Order without recommendations when reco-service fails         |
| Queue for later   | Operation can be deferred                    | Queue notification for retry instead of failing the order     |
| Provider failover | Multiple providers for same capability       | Route to secondary payment gateway when primary's circuit opens |
| Fail fast         | No safe degradation                          | Return 503 immediately rather than waiting for a timeout      |

For provider failover, run a per-provider circuit breaker and try providers in order (primary -> secondary -> tertiary -> fail fast).

### Parallel vs Sequential Calls

| Shape                          | Total time          | Use For                                  |
| ------------------------------ | ------------------- | ---------------------------------------- |
| Sequential                     | Sum of timeouts     | Calls that depend on each other          |
| Parallel, all-must-succeed     | Slowest call        | All results required                     |
| Parallel, first-success        | Fastest call        | Provider failover with speed priority    |

### Stack Adaptation

After `stack-detect`, apply the patterns using the ecosystem's standard library: Resilience4j (Java), Polly (.NET), gobreaker (Go), tenacity (Python), retriable / stoplight (Ruby), Guzzle retry middleware (PHP), or equivalent. Use the framework's decorator, middleware, or annotation mechanism; rely on background-job retry-with-backoff where built in. If the stack is unfamiliar, apply the rules above and recommend the user verify against their ecosystem's resilience library docs.

## Output Format

Consuming workflow skills parse this structure to surface resilience gaps.

```
## Resiliency Assessment

**Stack:** {detected language / framework}

### Gaps

- [Severity: High | Medium | Low] {integration point or component} - {description of gap}
  - Missing: {timeout | retry | circuit breaker | bulkhead | fallback | timeout budget | retry budget}
  - Risk: {failure mode this gap enables}
  - Recommendation: {concrete pattern and library for the detected stack}

### No Gaps Found

{State explicitly if resilience is adequate - do not omit silently.}
```

**Severity:**

- **High**: missing timeout or retry on an external call with no circuit breaker.
- **Medium**: retry without jitter, circuit breaker without monitoring, missing timeout/retry budget on a chained call path.
- **Low**: missing bulkhead isolation where one exists elsewhere in the codebase.

Omit "No Gaps Found" if gaps were listed.

## Avoid

- Retrying non-idempotent ops without idempotency keys.
- Retrying on 4xx (won't succeed on retry).
- Circuit breakers with no monitoring - you cannot react to a trip you cannot see.
- Fallbacks that swallow errors silently.
- Chained retries with no per-request retry budget (amplification).
