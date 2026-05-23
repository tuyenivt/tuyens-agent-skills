---
name: log-analysis
description: Structured log analysis: time-window isolation, correlation tracing, frequency distribution, multi-error sequencing, healthy/unhealthy comparison.
metadata:
  category: ops
  tags: [logs, investigation, tracing, correlation, oncall]
user-invocable: false
---

# Log Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Active incident investigation
- Tracing a specific request across services
- Investigating a user report or support ticket via log evidence
- Comparing healthy vs unhealthy time windows

## Rules

- Isolate the time window before reading log volume; alert fire time is not the failure start
- Quantify - "many errors" is useless; "47 timeouts in 3 min, all on /api/orders, all EU users" is signal
- When multiple error classes interleave, establish first-appearance ordering - one is almost always causing the other
- State what logs confirm, contradict, and cannot resolve

## Pattern

### Step 1 - Time-Window Isolation

- **Failure start**: timestamp of first anomalous log (NOT alert fire time - alert lag is common)
- **Failure end**: when logs returned to baseline (if resolved)
- **Comparison window**: equivalent healthy period (same time of day, same day of week)

Default window: 5-10 min around onset. If the window has >2000 lines or spans >10 min, sample strategically: first 30s of anomaly (root signal), peak (saturation pattern), last 30s before recovery (resolution pattern).

### Step 2 - Correlation Tracing

If trace/request IDs are present: extract from the failing case, follow chronologically across services, identify where the chain breaks (missing span = likely failure point), note ID propagation gaps.

If absent: flag as observability gap.

### Step 3 - Frequency and Distribution

For errors in the window, characterize rate (per minute, constant/spiking/tapering), affected users (one / segment / all - extract distinct IDs and cross-reference attributes like region, plan, cohort), affected endpoints, error classes (single or mixed), and service distribution.

Report as a single sentence: *"47 timeout errors in 3 min, all on `/api/orders`, all EU users, starting 14:23 UTC."*

### Step 4 - Multi-Error Sequencing and Trigger

When multiple error classes interleave, determine causation direction:

1. **First-appearance ordering**: which class logged first? Earliest type is the likely upstream cause
2. **Saturation signals**: if an error is a resource-exhaustion type (pool exhausted, queue full, OOM, FD limit, thread pool rejected), check the resource metric leading up - gradual climb confirms exhaustion, sudden jump suggests a burst
3. **Timing correlation**: does onset coincide with a deploy, traffic spike, cron job, or external dependency event?

Common upstream → downstream chains:

| Upstream                  | Downstream                | Mechanism                                                                |
| ------------------------- | ------------------------- | ------------------------------------------------------------------------ |
| Dependency timeout        | Connection pool exhausted | Slow responses hold connections, starving the pool                       |
| Connection pool exhausted | Request timeout / 503     | New requests cannot acquire a connection                                 |
| Memory pressure           | GC pause → timeouts       | Long pauses look like dependency failures                                |

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
- Trigger: {what correlates with onset}

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
