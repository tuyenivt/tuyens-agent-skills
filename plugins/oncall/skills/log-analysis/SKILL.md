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
- Skip when the failing error class and its cause are already confirmed - go straight to fix

## Rules

- Isolate the time window before reading log volume; alert fire time is not the failure start
- When multiple error classes interleave, establish first-appearance ordering - one is almost always causing the other
- Label each Key Evidence entry `confirmed by logs`, `contradicted by logs`, or `requires non-log evidence`; entries in the third category are also listed in Log Gaps. Exception: the Likely trigger entry carries the trigger-confidence label from Step 4 instead
- Logs do not outrank metrics: when metric evidence pre-dates the first anomalous log line, the metric becomes the earliest anomaly and the saturation signal in the causal chain

## Inputs

Required: a known failure window OR a log/trace/issue URL the fetch step can use. Use skill: `ops-observability-fetch` to obtain `log_window` and `trace` blocks - plus `metric_series` when the Step 4 saturation check or the metric-precedence rule needs a resource metric. In paste mode (no MCP transport), analyze the pasted logs directly - do not re-emit normalized blocks.

## Patterns

Bad: "Errors started around 2pm and there were lots of timeouts."
Good: "Errors started 14:23:22 UTC (8 min before alert). 47 timeouts in 3 min on `/api/orders`, all EU users; concurrent pool-exhaustion errors starting 40s later."

### Step 1 - Time-Window Isolation

- **Failure start**: timestamp of first anomalous log (NOT alert fire time - alert lag is common)
- **Failure end**: when logs returned to baseline (if resolved)
- **Comparison window**: equivalent healthy period (same time of day, same day of week). If none was provided and none can be fetched, set `Comparison Window: unavailable`, skip Step 5, and record the absence in Log Gaps - do not invent a baseline.

Default window: 5-10 min around onset. If either threshold is met (>2000 lines, or span >10 min), sample strategically: first 30s of anomaly (root signal), peak (saturation pattern), last 30s before recovery (resolution pattern).

When `query_logs` is available, run two passes: full window for the comparison baseline (Step 5), then the narrowed anomaly window for detail. Server-side filtering beats fetching everything and grepping.

### Step 2 - Correlation Tracing

When a trace ID is present in the logs or input URL, prefer `fetch_trace` over reconstructing the path from logs - APM returns the span tree directly.

- **Full IDs present**: extract from the failing case, follow chronologically across services, identify where the chain breaks (missing span = likely failure point).
- **Partial IDs** (some lines lack them - probes, dependencies, DB queries, or infra components like pools, even within one service): trace what exists; the boundary where IDs drop IS the observability gap - name it.
- **No IDs**: flag as observability gap (also list it in Log Gaps); fall back to timestamp + endpoint co-occurrence, plus user-id when logs carry one.

### Step 3 - Frequency and Distribution

For errors in the window, characterize rate (per minute, constant/spiking/tapering), affected users (one / segment / all - extract distinct IDs and cross-reference attributes like region, plan, cohort; `unknown` when logs carry no user identifiers), affected endpoints, error classes (single or mixed), and service distribution. Fill the Error Distribution block in the output template.

### Step 4 - Multi-Error Sequencing and Trigger

When multiple error classes interleave, determine causation direction:

1. **First-appearance ordering**: which class logged first? Earliest type is the likely upstream cause
2. **Saturation signals**: if an error is a resource-exhaustion type (pool exhausted, queue full, OOM, FD limit, thread pool rejected), check the resource metric leading up - gradual climb confirms exhaustion, sudden jump suggests a burst
3. **Timing correlation**: does onset coincide with a deploy, traffic spike, cron job, external dependency event, or an infra/config change (which may precede onset by hours to days - state the lag)? "Onset" here and in the output means the first anomalous signal, log or metric.

Common upstream → downstream chains:

| Upstream                  | Downstream                | Mechanism                                                                |
| ------------------------- | ------------------------- | ------------------------------------------------------------------------ |
| Dependency timeout        | Connection pool exhausted | Slow responses hold connections, starving the pool                       |
| Slow DB query             | App pool exhausted        | Long-held connections not freed for next request                         |
| Connection pool exhausted | Request timeout / 503     | New requests cannot acquire a connection                                 |
| Memory pressure           | GC pause → timeouts       | Long pauses look like dependency failures                                |
| Rate limit on dependency  | Cascading retries         | Backoff amplifies load on the limited resource                           |
| Deploy rollout            | Mixed-version errors      | New code-path errors absent from old replicas during canary              |

State the chain link by link: *"{upstream} causes {downstream} because {mechanism}, confirmed by {evidence}."* Chains may have more than two links (e.g., dependency timeout → pool exhausted → 503); state each link's mechanism. A single error class can still have a multi-link resource chain behind it (e.g., heap pressure → GC pauses → query timeouts) - state that chain rather than writing "Single class".

Label the trigger's confidence: `confirmed` (mechanism + timing both fit), `candidate` (timing fits, mechanism unproven), or `unknown`. An external-dependency trigger stays `candidate` until evidence from the dependency itself (status page, its own metrics) confirms it - caller-side timeouts alone do not.

### Step 5 - Healthy vs Unhealthy Comparison

Compare windows on volume change, new error classes (absent in healthy), missing expected entries (e.g., "payment processed" gone = payments not completing; list these under Missing logs), and latency signals (duration/elapsed fields shifted - use coarse durations or threshold-breach counts when percentiles are unavailable).

Missing expected entries observable from the unhealthy window alone still belong in Key Evidence when the comparison window is unavailable.

## Output

```
## Log Analysis

Time Window: {start} to {end | "ongoing at window end"} ({duration})
Comparison Window: {healthy period | "unavailable"}

### Correlation Trace
{Traced path, or "No correlation IDs - observability gap"}

### Error Distribution
- Rate: {errors/minute, spike pattern}
- Scope: {users (or "unknown") / endpoints / services}
- Classes: {type and count for each}
- Causal chain: {link-by-link chain + mechanisms; "Single class" only when no chain exists behind it}
- Trigger: {deploy / traffic spike / cron / external dep degradation / infra or config change / unknown} ({confirmed | candidate | unknown}, timestamp, lag to onset if any)

### Healthy vs Unhealthy
(omit when Comparison Window is unavailable)
- Error rate: {healthy} → {failing} ({delta})
- New classes: {list}
- Missing logs: {list, or "None notable"}
- Latency shift: {p50/p99 baseline → failing, coarse durations if no percentiles, or "None notable"}

### Key Evidence
Each entry labeled {confirmed by logs | contradicted by logs | requires non-log evidence}; the Likely trigger entry carries the trigger-confidence label instead.
- Earliest anomaly: {timestamp + signal, log or metric; when a metric precedes the first log line, list both}
- Likely trigger: {event, with timestamp and {confirmed | candidate | unknown}}
- Confirmed scope: {affected users/endpoints/services}

### Log Gaps
- {Signal missing that would resolve ambiguity, incl. all "requires non-log evidence" items and a missing comparison window, or "None identified"}
```

## Avoid

- Skipping the healthy comparison when a baseline exists - patterns only have meaning relative to baseline
- Inventing a baseline when none exists - mark it unavailable instead
- Concluding root cause from logs alone without linking to code, config, or deploy evidence
