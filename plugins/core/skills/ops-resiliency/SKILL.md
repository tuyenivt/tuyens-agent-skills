---
name: ops-resiliency
description: Assess resilience gaps - circuit breakers, retries with backoff, timeouts, bulkheads, graceful fallbacks - across stacks.
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

Incident history counts as evidence: a timeout that looks bounded in isolation but exhausted a pool in production is rated by what happened.

## Rules

- Every external call has a timeout; no unbounded waits.
- Retries use exponential backoff with jitter, with attempts capped (typically 3 attempts - the first call plus two retries; this file counts attempts, not retries). More than 3 in-process attempts is `retry (misconfigured)` unless the timeout budget shows the room for them.
- Retry only transient errors: 500, 502, 503, 504, connection errors, timeouts, and the retryable 4xx - `429 Too Many Requests`, `408 Request Timeout`, `425 Too Early`. No other 4xx (nor 501/505) is retried unless the response says otherwise: a `409` carrying `Retry-After` (the in-flight-duplicate response), a `401` after one token refresh, `412`/`423` after re-reading the state. Never retry a non-idempotent operation without an idempotency key - `Use skill: backend-idempotency` for key strategy and atomic dedup; in this skill's output the gap is `Missing: idempotency key`, never the sibling's block.
- A `Retry-After` header (seconds, or an HTTP-date) replaces computed backoff, capped at the remaining deadline: a value beyond the deadline means abandon, not wait.
- One circuit breaker per external dependency, with explicit thresholds (failure rate, open duration, half-open probes) and monitoring - a silent or shared breaker is useless.
- Independent failure domains use bulkhead isolation (separate pools per downstream).
- Each external dependency has exactly one client module owning its timeout, retry, breaker, and fallback configuration. Settings spread across call sites cannot be reviewed or changed coherently. A configuration knob the code never reads is a gap, not a setting.
- Every dependency has a defined fallback. Every fallback logs the original failure at WARN; silent fallbacks hide degradation until it compounds.

## Patterns

### Circuit Breaker

- **Closed** - normal; track failure rate.
- **Open** - reject calls immediately; return fallback.
- **Half-Open** - allow a limited number of probe calls; close when their failure rate is below the threshold, reopen when it is not (some libraries reopen on the first failed probe).

Configure: failure-rate threshold over a sliding window (e.g., 50%), open duration before half-open (e.g., 30s), permitted probes in half-open (e.g., 3-10).

### Retry with Backoff

- Start backoff at ~500 ms, multiply by 2, cap at a reasonable maximum.
- Add jitter to prevent thundering herd.
- Non-idempotent ops need an idempotency key before retry is safe.

### Timeout

- External calls: 3-5 s typical. Internal calls: 1-2 s typical. Typical values yield to the budget below.
- The caller's deadline (its SLA or its own client's timeout) sets the total budget; downstream timeouts are allocated from it, never summed into it. With several callers on one endpoint the tightest deadline governs, unless the endpoint can tell them apart (a header, a separate route).
- Propagate timeout context (deadline / request context) to downstream calls.

### Timeout Budget

A request calling multiple downstream services shares one budget.

```
Total budget: 5s (the caller times out at 5s)
  Service A timeout: 3s
  Service B timeout: 3s
  Local processing buffer: 1s

If A takes 1.8s -> remaining for B = min(B's timeout 3s, 5 - 1.8 - 1 = 2.2s) = 2.2s
If A takes 3s   -> remaining for B = 5 - 3 - 1 = 1s: fail fast unless B answers in 1s
```

Pass remaining budget as a deadline to each downstream call. Downstream timeouts that sum past the budget (3 + 3 > 5 - 1) are what makes a slow first call leave no time for the second - the budget, not the individual timeouts, is what the caller can actually wait.

### Retry Budget

Retries amplify load. Three services chained with 3 attempts each turn one failed request into 27 calls at the deepest hop (39 across the chain). Cap attempts per request (e.g., 6 total across the chain), decrement on each attempt at any layer, and pass the remaining budget downstream.

### Per-Dependency Client Wrapper

One module per external dependency is the unit that owns resilience configuration. Scattering timeout and retry settings across call sites makes them impossible to audit, and guarantees the third caller added later has none.

Bad - each call site decides for itself, and two of the three deviate, each in its own way:

```
chargeCard()    -> http.post(url, { timeoutMs: 3000, attempts: 3 })
refundCard()    -> http.post(url, { timeoutMs: 3000 })
lookupCard(id)  -> http.get(url + "/cards/" + id)
```

Good - one wrapper owns the policy; retries are per operation, and a write without a key is never retried:

```
paymentClient = client({ baseUrl, timeoutMs: 3000, deadlineFrom: ctx, retry: { backoff: exponentialJitter, baseMs: 500 },
                         breaker: perDependency("payments", { failureRate: 0.5, openMs: 30000, halfOpenProbes: 5 }), fallback: failFast, onFallback: warnWithCause })
chargeCard()    -> paymentClient.post('/charges', body, { idempotencyKey, attempts: 3 })
refundCard()    -> paymentClient.post('/refunds', body, { idempotencyKey, attempts: 3 })
lookupCard(id)  -> paymentClient.get('/cards/' + id, { attempts: 3 })   // safe method
```

The wrapper is also where the breaker instance lives, which is what makes "one breaker per dependency" enforceable rather than aspirational.

### Where the Retry Lives

Retrying in-process and retrying via a job queue are different budgets, and spending both on the same failure multiplies them.

| Retry location  | Use when                                                     | Bound                                            |
| --------------- | -------------------------------------------------------------- | -------------------------------------------------- |
| In-process      | The caller is waiting and the failure is likely transient    | Small, capped (2-3 attempts), inside the request timeout |
| Deferred to queue | The caller does not need the result now, or recovery may take minutes | The job's own retry policy; in-process attempts drop to 1 |
| Neither         | The operation is not safe to repeat and has no idempotency key | Fail fast and surface it                        |

Choose one owner per operation. A request that makes 3 attempts in-process and then enqueues a job that makes 5 more, each of which re-runs the in-process loop, has a budget of 18 calls, which is not what anyone intended when they configured either number. Callers in front (a browser client retrying twice, a gateway retrying) multiply the same way and are part of the chain's budget.

### Bulkhead

Separate thread / connection pools per downstream dependency. In single-threaded or shared-threadpool runtimes (Node, FastAPI sync handlers, Ruby threads), bound concurrent in-flight requests per dependency with a semaphore instead. One slow dependency cannot consume the capacity used by other dependencies.

### Fallback Patterns

| Pattern           | Use When                                     | Example                                                       |
| ----------------- | -------------------------------------------- | ------------------------------------------------------------- |
| Cached fallback   | Stale data is acceptable                     | Cached product catalog when catalog-service is down           |
| Default value     | A reasonable default exists                  | Default shipping estimate when shipping-service times out     |
| Partial response  | Some data is better than none                | Order without recommendations when reco-service fails         |
| Queue for later   | Operation can be deferred                    | Queue notification for retry instead of failing the order     |
| Provider failover | Multiple providers for same capability       | Route to secondary payment gateway when primary's circuit opens |
| Fail fast         | No safe degradation                          | Return 503 immediately rather than waiting for a timeout      |

For provider failover, run a per-provider circuit breaker and try providers in order (primary -> secondary -> tertiary -> fail fast) - for reads and reconcilable operations, or once the primary's outcome is settled; an idempotency key is provider-scoped, so a charge that timed out on the primary is never re-issued to the secondary.

### Parallel vs Sequential Calls

| Shape                          | Total time                                  | Use For                                  |
| ------------------------------ | ------------------------------------------- | ---------------------------------------- |
| Sequential                     | Sum of timeouts (worst case)                | Calls that depend on each other          |
| Parallel, all-must-succeed     | Slowest call (worst case)                   | All results required                     |
| Parallel, first-success        | Fastest successful call; slowest call or the timeout when all fail | Provider failover with speed priority |

### Stack Adaptation

After `stack-detect`, apply the patterns with the ecosystem's usual third-party libraries - none of these is a standard library, and most cover one pattern: Resilience4j (Java/Kotlin - all patterns), Polly (.NET - all), cockatiel (Node - all; opossum is breaker, timeout, and fallback - no retry or bulkhead), tenacity (Python - retry only; pybreaker for the breaker, the HTTP client's own timeouts), gobreaker (Go - breaker only; `context.WithTimeout` for timeouts, cenkalti/backoff or retry-go for jittered retry, a semaphore for the bulkhead), retriable plus stoplight (Ruby - retry plus breaker), Guzzle retry middleware (PHP - retry, with a custom delay for jitter; ganesha for the breaker), tower (Rust - timeout, retry plumbing, concurrency limit; failsafe-rs for the breaker). Use the framework's decorator, middleware, or annotation mechanism; rely on background-job retry-with-backoff where built in. When `Language` is `unknown`, apply the rules above and recommend the user verify against their ecosystem's resilience library docs.

## Output Format

Consuming workflow skills parse this structure to surface resilience gaps. One gap per integration point or per chain: an operation is its own integration point when its policy differs from its siblings (a write without a key beside a safe read), otherwise the dependency's client is the point; a `client ownership` gap is one per dependency, naming the call sites; a budget or retry-ownership defect that spans several hops is one gap keyed to the chain, naming the hops. A caller outside the repository is cited with its source (its code, or the document that states its behaviour). Order gaps by severity, High first.

```
## Resiliency Assessment

**Stack:** {language / framework | unknown}{; other services in the chain: <name> (detected | from <document> | assumed)}

### Gaps                                        {when at least one gap}

- [Severity: High | Medium | Low] {integration point, component, or chain; in design mode the proposed hop} - {description of gap}
  - Missing: {one or more, comma-separated, each optionally `(misconfigured)`: timeout, retry, circuit breaker, breaker monitoring, bulkhead, fallback, fallback logging, timeout budget, retry budget, retry owner, retry-after handling, client ownership, idempotency key}
  - Risk: {failure mode this gap enables}
  - Recommendation: {concrete pattern and library for the detected stack, or the docs to verify against when unknown}

### No Gaps Found                               {instead, when none: one sentence stating resilience is adequate}
```

A pattern that is present but misconfigured is listed with the `(misconfigured)` qualifier: `retry (misconfigured)` for no cap, no backoff or jitter, or retrying non-transient errors; `circuit breaker (misconfigured)` for a shared breaker or one with no thresholds; `timeout (misconfigured)` for a fixed value that ignores the caller's deadline. Rate it by what the configuration actually permits, not by the value written down: a 5s budget whose downstream timeouts sum to 12s permits 12s of downstream work and held resources against a 5s promise.

**Severity** - by the worst plausible failure mode the gap enables; the tiers below name typical cases, and a gap escalates to High when the failure it permits is unbounded or financial or irreversible - the gap whose failure permits that outcome, not every gap on the same hop:

- **High**: unbounded blocking or load (missing timeout, uncapped retry, a missing or exceeded budget on a chained path), or unsafe retry of a non-idempotent op without a key when the duplicate is financial or irreversible (a recoverable database write is Medium, as `backend-idempotency` rates it).
- **Medium**: failure is bounded but recovery or containment is impaired - retry without jitter, breaker absent or unmonitored where a timeout exists, no fallback for a critical dependency, a fallback that does not log the original failure, `Retry-After` ignored.
- **Low**: hardening gaps with no immediate failure path - missing bulkhead isolation where every call is bounded, fallback that fails fast where stale data would serve.

For design tasks (no implementation yet), use the same format: list the proposed design's unaddressed failure modes as Gaps, naming the proposed hop as the integration point; the timeout budget goes in the chain gap's Recommendation as `deadline <ms>: <hop> <ms>, <hop> <ms>, buffer <ms>`.

## Avoid

- Retrying non-idempotent ops without idempotency keys.
- Retrying client-error 4xx (won't succeed on retry) - 429, 408, 425, and a 409 carrying `Retry-After` are the exceptions.
- Circuit breakers with no monitoring - you cannot react to a trip you cannot see.
- Fallbacks that swallow errors silently.
- Chained retries with no per-request retry budget (amplification).
