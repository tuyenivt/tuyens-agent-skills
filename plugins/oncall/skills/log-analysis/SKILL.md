---
name: log-analysis
description: Structured log analysis for oncall investigation - time-window isolation, correlation ID tracing, frequency analysis, and healthy/unhealthy comparison
metadata:
  category: ops
  tags: [logs, investigation, tracing, correlation, oncall]
user-invocable: false
---

# Log Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During active incident investigation to find the root cause in logs
- When tracing a specific request across multiple services
- When investigating a user report or support ticket using log evidence
- When comparing behavior between a healthy and unhealthy time window

## Rules

- Always isolate the time window before reading log volume
- Lead with correlation ID tracing when available - this is the fastest path to truth
- Distinguish signal (meaningful patterns) from noise (expected errors, health checks)
- Quantify frequency and distribution - "many errors" is not useful; "47 errors in 3 minutes all from user ID 8821" is
- When multiple error classes appear together, establish temporal ordering to determine causation direction - which error type appeared first matters more than which is most frequent
- State what the logs confirm, what they contradict, and what remains unresolved
- If logs are insufficient, state exactly what additional log signal is needed

## Pattern

### Step 1 - Time-Window Isolation

Identify the relevant time window before reading log volume:

- **Failure start**: When did the first anomalous log appear? (not when the alert fired)
- **Failure end** (if resolved): When did logs return to normal?
- **Comparison window**: Identify an equivalent "healthy" window (same time of day, same day of week) for contrast

Narrow the window to 5-10 minutes around the failure onset unless the issue is intermittent or slow-burn.

**High-volume windows**: If the failure window contains thousands of log lines, sample strategically rather than reading everything. Focus on: (1) the first 30 seconds of the anomaly for root signal, (2) a sample from peak error rate, (3) the last 30 seconds before recovery (if resolved). This avoids drowning in repetitive error lines while capturing onset, peak, and resolution patterns.

### Step 2 - Correlation ID Tracing

If correlation IDs / trace IDs / request IDs are present:

1. Extract the ID(s) from the failing request or reported case
2. Trace all log lines with that ID across services in chronological order
3. Identify where the chain breaks (missing span = likely failure point)
4. Note any ID propagation gaps (correlation ID present in service A but not service B)

If no correlation IDs are present, note this as an observability gap.

### Step 3 - Frequency and Distribution Analysis

For error logs in the window:

| Dimension            | What to Check                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rate                 | Errors per minute - is it constant, spiking, or tapering?                                                                                                                                                                                                                                                                                                                       |
| Affected users       | Is it one user, a segment, or all users? To identify a segment: extract distinct user IDs from error logs, then cross-reference with user attributes (e.g., users with no billing address, users in a specific region, users on a specific plan). Query pattern: `SELECT attribute, COUNT(*) FROM error_logs JOIN users USING (user_id) GROUP BY attribute ORDER BY COUNT DESC` |
| Affected endpoints   | Is it one route or many?                                                                                                                                                                                                                                                                                                                                                        |
| Error type           | Are all errors the same class or mixed?                                                                                                                                                                                                                                                                                                                                         |
| Service distribution | Which services are logging errors - one or many?                                                                                                                                                                                                                                                                                                                                |
| Timing correlation   | Does the error rate correlate with a deploy, traffic spike, or cron job?                                                                                                                                                                                                                                                                                                        |

State the distribution as a sentence: "47 timeout errors in 3 minutes, all on `/api/orders`, all from users in the EU region, starting at 14:23 UTC immediately after deploy v2.4.1."

### Step 3b - Multi-Error-Class Sequencing

When multiple distinct error types appear in the same window (e.g., "connection timeout" and "pool exhausted" interleaved), determine causation direction:

1. **First-appearance ordering**: Which error class logged first? The earliest error type is the likely upstream cause
2. **Frequency crossover**: Plot both error types by minute - does one consistently precede the other, or do they start simultaneously?
3. **Request-level correlation**: For requests that produce both error types, which appears first in the request lifecycle? (e.g., timeout at 14:30:01 on request R1, then pool exhausted at 14:30:02 on request R2 because R1 held the last connection)
4. **Saturation signals**: If one error is a resource exhaustion type (pool exhausted, queue full, memory limit, file descriptor limit, thread pool rejected), check the resource metric leading up to the spike - gradual climb to limit confirms exhaustion, sudden jump suggests a burst

Common causal chains to check:

| Upstream Error            | Downstream Effect          | Mechanism                                                                |
| ------------------------- | -------------------------- | ------------------------------------------------------------------------ |
| Dependency timeout        | Connection pool exhausted  | Slow responses hold connections open, starving the pool                  |
| Connection pool exhausted | Request timeout / HTTP 503 | New requests cannot acquire a connection and time out or get rejected    |
| Memory pressure           | GC pauses, then timeouts   | Long GC pauses cause request timeouts that look like dependency failures |
| DNS resolution failure    | Connection timeout         | Connections hang waiting for DNS, then time out                          |
| TLS handshake failure     | Connection timeout         | Handshake stalls consume connection slots                                |

State the causal chain as: "{upstream error} causes {downstream error} because {mechanism}, confirmed by {evidence}."

### Step 4 - Healthy vs. Unhealthy Comparison

Compare the failing window against the healthy comparison window:

- **Volume change**: Is log volume higher or lower than normal?
- **New error classes**: What error types appear in the failing window that don't appear in healthy?
- **Missing log lines**: Are expected log lines absent (e.g., "payment processed" logs gone = payments not completing)?
- **Latency signals**: Are duration/elapsed fields higher in the failing window?
- **Stack trace evolution**: Did a new exception class appear, or did an existing one increase in frequency?

### Step 5 - Key Evidence Extraction

Produce a focused evidence set for downstream analysis:

- **Earliest anomalous log**: Exact timestamp and message
- **Highest-frequency error**: Error class, count, and time distribution
- **Causal chain** (when multiple error types): Which error class appeared first and caused the others, with mechanism
- **Correlation chain**: Traced request path (or gap where tracing breaks)
- **Likely trigger**: What changed just before the first anomalous log?
- **Affected scope**: Users, endpoints, or services confirmed affected by log evidence

## Output Format

```
## Log Analysis

Time Window: {start} to {end} ({duration})
Comparison Window: {healthy period used for contrast}

### Correlation Trace

{Traced request path, or "No correlation IDs present - observability gap"}

### Error Distribution

- Rate: {errors/minute, spike pattern}
- Affected scope: {users / endpoints / services}
- Error classes: {type and count for each distinct error type}
- Causal chain: {upstream error -> downstream error with mechanism, or "Single error class" if only one type}
- Timing trigger: {what correlates with onset}

### Healthy vs. Unhealthy Delta

| Dimension     | Healthy Window | Failing Window | Delta       |
| ------------- | -------------- | -------------- | ----------- |
| Error rate    | {value}        | {value}        | {change}    |
| New errors    | -              | {list}         | -           |
| Missing logs  | {expected log} | absent         | -           |
| Latency (p99) | {value}        | {value}        | {change}    |

### Key Evidence

- Earliest anomaly: {timestamp} - {log message}
- Primary signal: {most diagnostic finding}
- Causal chain: {error A -> error B because mechanism, or "Single error class"}
- Likely trigger: {what changed before onset}
- Confirmed scope: {affected users/endpoints/services}

### Log Gaps

- {Signal missing that would resolve ambiguity, or "None identified"}
```

## Avoid

- Reading raw log volume without time-window isolation first
- Treating alert firing time as failure start time (alert lag is common)
- Reporting individual log lines without frequency context
- Skipping the healthy comparison - patterns only have meaning relative to baseline
- Concluding root cause from logs alone without linking to code or config evidence
- Treating interleaved error types as independent problems - when two error classes spike together, one is almost always causing the other
- Reading all log lines in a high-volume spike - sample onset, peak, and recovery instead
