---
name: log-analysis
description: Structured log analysis: time-window isolation, correlation tracing, frequency distribution, multi-error sequencing, healthy/unhealthy comparison.
metadata:
  category: ops
  tags: [logs, investigation, tracing, correlation, oncall]
user-invocable: false
---

# Log Analysis

## When to Use

- Active incident investigation
- Tracing a specific request across services
- Investigating a user report or support ticket via log evidence
- Comparing healthy vs unhealthy time windows
- Skip when a single error class with obvious cause is already known - go straight to fix

## Rules

- Isolate the time window before reading log volume; alert fire time is not the failure start
- When multiple error classes interleave, establish first-appearance ordering - one is almost always causing the other
- For each finding, mark it `confirmed by logs`, `contradicted by logs`, or `requires non-log evidence` - the third category populates the Log Gaps output section

## Inputs

Required: a known failure window OR a log/trace/issue URL the fetch step can use. Use skill: `ops-observability-fetch` to obtain `log_window` and `trace` blocks; fall back to user-pasted logs when no MCP transport is available.

## Patterns

Bad: "Errors started around 2pm and there were lots of timeouts."
Good: "Errors started 14:23:22 UTC (8 min before alert). 47 timeouts in 3 min on `/api/orders`, all EU users; concurrent pool-exhaustion errors starting 40s later."

### Step 1 - Time-Window Isolation

- **Failure start**: timestamp of first anomalous log (NOT alert fire time - alert lag is common)
- **Failure end**: when logs returned to baseline (if resolved)
- **Comparison window**: equivalent healthy period (same time of day, same day of week)

Default window: 5-10 min around onset. If the window has >2000 lines or spans >10 min, sample strategically: first 30s of anomaly (root signal), peak (saturation pattern), last 30s before recovery (resolution pattern).

When `query_logs` is available, run two passes: full window for the comparison baseline (Step 5), then the narrowed anomaly window for detail. Server-side filtering beats fetching everything and grepping.

### Step 2 - Correlation Tracing

When a trace ID is present in the logs or input URL, prefer `fetch_trace` over reconstructing the path from logs - APM returns the span tree directly.

- **Full IDs present**: extract from the failing case, follow chronologically across services, identify where the chain breaks (missing span = likely failure point).
- **Partial IDs** (e.g., on app logs but missing on probes, dependencies, or DB queries): trace what exists; the boundary where IDs drop IS the observability gap - name it.
- **No IDs**: flag as observability gap; fall back to timestamp + user-id + endpoint co-occurrence.

### Step 3 - Frequency and Distribution

For errors in the window, characterize rate (per minute, constant/spiking/tapering), affected users (one / segment / all - extract distinct IDs and cross-reference attributes like region, plan, cohort), affected endpoints, error classes (single or mixed), and service distribution. Fill the Error Distribution block in the output template.

### Step 4 - Multi-Error Sequencing and Trigger

When multiple error classes interleave, determine causation direction:

1. **First-appearance ordering**: which class logged first? Earliest type is the likely upstream cause
2. **Saturation signals**: if an error is a resource-exhaustion type (pool exhausted, queue full, OOM, FD limit, thread pool rejected), check the resource metric leading up - gradual climb confirms exhaustion, sudden jump suggests a burst
3. **Timing correlation**: does onset coincide with a deploy, traffic spike, cron job, or external dependency event?

Common upstream → downstream chains:

| Upstream                  | Downstream                | Mechanism                                                                |
| ------------------------- | ------------------------- | ------------------------------------------------------------------------ |
| Dependency timeout        | Connection pool exhausted | Slow responses hold connections, starving the pool                       |
| Slow DB query             | App pool exhausted        | Long-held connections not freed for next request                         |
| Connection pool exhausted | Request timeout / 503     | New requests cannot acquire a connection                                 |
| Memory pressure           | GC pause → timeouts       | Long pauses look like dependency failures                                |
| Rate limit on dependency  | Cascading retries         | Backoff amplifies load on the limited resource                           |
| Deploy rollout            | Mixed-version errors      | New code-path errors absent from old replicas during canary              |

State the chain as: *"{upstream} causes {downstream} because {mechanism}, confirmed by {evidence}."*

### Step 5 - Healthy vs Unhealthy Comparison

Compare windows on volume change, new error classes (absent in healthy), missing expected entries (e.g., "payment processed" gone = payments not completing), and latency signals (duration/elapsed fields shifted).

## Output

```
## Log Analysis

Time Window: {start} to {end} ({duration})
Comparison Window: {healthy period}

### Correlation Trace
{Traced path, or "No correlation IDs - observability gap"}

### Error Distribution
- Rate: {errors/minute, spike pattern}
- Scope: {users / endpoints / services}
- Classes: {type and count for each}
- Causal chain: {upstream → downstream + mechanism, or "Single class"}
- Trigger: {deploy / traffic spike / cron / external dep degradation / config change / unknown, with timestamp}

### Healthy vs Unhealthy
- Error rate: {healthy} → {failing} ({delta})
- New classes: {list}
- Missing logs: {list, or "None notable"}
- Latency shift: {p50/p99 baseline → failing, or "None notable"}

### Key Evidence
- Earliest anomaly: {timestamp + message}
- Likely trigger: {deploy / spike / cron / dep event, with timestamp}
- Confirmed scope: {affected users/endpoints/services}

### Log Gaps
- {Signal missing that would resolve ambiguity, or "None identified"}
```

## Avoid

- Skipping the healthy comparison - patterns only have meaning relative to baseline
- Concluding root cause from logs alone without linking to code, config, or deploy evidence
