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
- Label each Key Evidence entry `confirmed`, `contradicted`, or `requires evidence not yet held`, and name the source that settled it in the entry itself (logs, metric, trace, or several). Only the third is listed in Log Gaps - evidence in hand settles an entry whatever its source. Exception: the Likely trigger entry carries the trigger-confidence label from Step 4 instead, and a trigger left `candidate` or `unknown` also names in Log Gaps the evidence that would settle it
- Logs do not outrank metrics: when metric evidence pre-dates the first anomalous log line, the metric is the earliest anomaly. Time Window still opens at the first anomalous LOG line, since the window bounds what you read; the earlier metric is recorded in Key Evidence and leads the causal chain

## Inputs

Required: a known failure window OR a log/trace/issue URL. Use skill: `ops-observability-fetch` to obtain `log_window` and `trace`, plus `metric_series` when the Step 4 saturation check or the metric-precedence rule needs a resource metric (name the project's actual metric - that capability has no URL trigger), plus `deploy_event` whenever a deploy is a candidate trigger, since nothing else can settle that row. An issue URL alone anchors only `error_event`: to get `log_window` from one, supply the service and window it names.

Where the skill is invoked without that fetch and the logs are simply pasted into the request, analyze the text directly. The normalized blocks are the fetch skill's output shape; this skill consumes them but never re-emits them.

## Patterns

Bad: "Errors started around 2pm and there were lots of timeouts." Good: "Errors started 14:23:22 UTC (8 min before alert). 47 timeouts in 3 min on `/api/orders`, all EU users; concurrent pool-exhaustion errors starting 40s later."

### Step 1 - Time-Window Isolation

Decide the mode first. A system-wide investigation isolates a time window; a single-request investigation (one ticket, one trace, one customer) skips window isolation entirely, sets `Time Window: n/a - single request {id}`, and takes its comparison from a sibling request per Step 5. Where the request carries no timestamp of its own, anchor it to the reporter's stated time and mark it approximate.

For a time-window investigation:

- **Failure start**: timestamp of the first log line that would not appear in a healthy window - an explicit WARN or ERROR, or a success line whose latency has left its normal band. NOT alert fire time; alert lag is common
- **Failure end**: when logs returned to baseline (if resolved). Evidence outranks framing: where the logs show recovery after the time the requester called it ongoing, take the evidenced recovery and note the discrepancy in Key Evidence
- **Comparison window**: equivalent healthy period (same time of day, same day of week). If none was provided and none can be fetched, set `Comparison Window: unavailable`, run only the Step 5 checks marked single-window, and record the absence in Log Gaps - do not invent a baseline.

Default window: 5-10 minutes either side of onset. Judge size by the block's `of {total matched}` count, not by the sample you received: above 2000 matched lines, or a span over 20 minutes, ask for three narrow windows instead of one - first 30s of anomaly (root signal), ~30s at peak (saturation pattern), last 30s before recovery, or the most recent 30s while ongoing. Narrowing happens in the fetch, since a returned sample cannot be re-sampled. Record on the Time Window line that the analysis saw segments rather than the whole span.

Prefer two passes - the full window for the baseline, then the narrowed anomaly window for detail - filtering server-side rather than pulling everything and grepping.

### Step 2 - Correlation Tracing

When a trace ID is present in the logs or input URL, fetch the trace: it gives the services traversed, the error spans and the slowest span without reconstructing them from log lines. It does not give a span tree, so parent/child structure and per-span timing still come from the logs when you need them.

- **Full IDs present**: extract from the failing case, follow chronologically across services, and identify where the chain breaks - the last service that logged, with nothing after it, is the likely failure point.
- **Partial IDs** (some lines lack them - probes, dependencies, DB queries, or infra components like pools, even within one service): trace what exists; the boundary where IDs drop IS the observability gap - name it.
- **No IDs**: flag as observability gap (also list it in Log Gaps); fall back to timestamp + endpoint co-occurrence, plus user-id when logs carry one.

### Step 3 - Frequency and Distribution

For errors in the window, characterize rate (per minute, constant/spiking/tapering), affected users (one / segment / all - extract distinct IDs and cross-reference attributes like region, plan, cohort; `unknown` when logs carry no user identifiers), affected endpoints, error classes (single or mixed), and service distribution. Fill the Error Distribution block in the output template.

Lines you hold are a sample unless the block says otherwise, so derive Rate from a metric where one exists and label a count taken off the sample as such. A sample can show that a segment IS affected; only a filtered count or a metric can show that a segment is the ONLY one affected, so claim "all" or a segment boundary only on that evidence and write `unknown` otherwise.

### Step 4 - Multi-Error Sequencing and Trigger

When multiple error classes interleave, determine causation direction:

1. **First-appearance ordering**: which class logged first? Earliest type is the likely upstream cause
2. **Saturation signals**: if an error is a resource-exhaustion type (pool exhausted, queue full, OOM, FD limit, thread pool rejected), the error line already proves exhaustion - read the resource metric leading up to it to tell a slow leak or creeping hold time (gradual climb) from a demand burst (sudden jump). These are gauges sampled at the scrape interval, so any saturation faster than one interval reads flat: a flat series never disproves exhaustion, it only fails to characterise it
3. **Timing correlation**: does onset coincide with a deploy, traffic spike, cron job, external dependency event, or an infra/config change (which may precede onset by hours to days - state the lag)? "Onset" here and in the output means the first anomalous signal, log or metric.

Common upstream -> downstream chains:

| Upstream                  | Downstream                | Mechanism                                                                |
| ------------------------- | ------------------------- | ------------------------------------------------------------------------ |
| Dependency timeout        | Connection pool exhausted | Slow responses hold connections, starving the pool                       |
| Slow DB query             | App pool exhausted        | Long-held connections not freed for next request                         |
| Connection pool exhausted | Request timeout / 503     | New requests cannot acquire a connection                                 |
| Memory pressure           | Request timeouts          | Reclaim competes with the request path - stop-the-world pauses on a generational collector, GC-assist CPU steal on a concurrent one, swap thrash on a native runtime - until in-flight requests exceed their deadlines |
| Rate limit on dependency  | Cascading retries         | Each layer reissues its own retries, and unjittered backoff synchronises them into waves |
| Deploy rollout            | Mixed-version errors      | Old and new replicas disagree on a contract (schema, serialization, flag default) while both serve traffic, so failures track which version handled the request |

State the chain link by link: *"{upstream} causes {downstream} because {mechanism}, confirmed by {evidence}."* Chains may have more than two links (e.g., dependency timeout -> pool exhausted -> 503); state each link's mechanism. A single error class can still have a multi-link resource chain behind it (e.g., heap pressure -> GC pauses -> query timeouts) - state that chain rather than writing "Single class".

Label the trigger's confidence: `confirmed` (mechanism + timing both fit), `candidate` (timing fits, mechanism unproven), or `unknown`. An external-dependency trigger stays `candidate` until evidence from the dependency itself (status page, its own metrics) confirms it - caller-side timeouts alone do not.

### Step 5 - Healthy vs Unhealthy Comparison

Compare windows on volume change, new error classes (absent in healthy), missing expected entries (e.g., "payment processed" gone = payments not completing; list these under Missing logs), and latency signals (duration/elapsed fields shifted - use coarse durations or threshold-breach counts when percentiles are unavailable).

Two of these are single-window checks and run even with no baseline: missing expected entries (a success line the flow should emit and does not) and absolute latency (durations breaching a stated threshold). Run them and record the results in Key Evidence when `Comparison Window` is unavailable; the Healthy vs Unhealthy block is what gets omitted, not the observations.

Single-request investigations compare against a successful request of the same type (a sibling trace or log sequence) instead of a time window; set `Comparison Window: sibling request {id}` and run the same four checks on the two sequences, reading "volume change" as which steps the failing sequence never reached.

### Step 6 - Assemble Key Evidence

Pull the three fixed entries from the steps that produced them: earliest anomaly from Step 1 (or the metric, per the precedence rule), likely trigger from Step 4, confirmed scope from Step 3. Add any single-window observation from Step 5 that has no home in Healthy vs Unhealthy. Label each entry by what settles it, then list every `requires evidence not yet held` entry in Log Gaps.

## Output

```
## Log Analysis

Time Window: {start} to {end | "ongoing at window end"} ({duration}){, segments only: <which>} | "n/a - single request {id}" | "unavailable - log fetch returned nothing"

Comparison Window: {healthy period {start} to {end} | sibling request {id} | "unavailable"}

### Correlation Trace
{Traced path | "IDs present to {component/boundary}, absent beyond it - observability gap" | "No correlation IDs - observability gap" | "unavailable - no logs or trace retrieved"}

### Error Distribution
- Rate: {errors/minute, spike pattern | "n/a - single-request investigation"}
- Scope: {users (or "unknown") / endpoints / services}
- Classes: {type and count for each}
- Causal chain: {link-by-link chain + mechanisms; "Single class" only when no chain exists behind it}
- Trigger: {deploy / traffic spike / cron / external dep degradation / infra or config change / "not identified"} ({confirmed | candidate | unknown}{, timestamp}{, lag to onset})
- Amplifier: {a second change that widened the failure without starting it, same fields; "none identified"}

### Healthy vs Unhealthy
(omit when Comparison Window is unavailable; the single-window observations still appear in Key Evidence)
- Error rate: {healthy} -> {failing} ({delta}) | {for a sibling comparison: the step the failing sequence never reached}
- New classes: {list}
- Missing logs: {list, or "None notable"}
- Latency shift: {p50/p99 baseline -> failing, coarse durations if no percentiles, single-request durations against the sibling, or "None notable"}

### Key Evidence
Each entry labeled {confirmed by logs | confirmed by metric | confirmed by trace | contradicted by logs | requires evidence not yet held}; the Likely trigger entry carries the trigger-confidence label instead.
- Earliest anomaly: {timestamp + signal, log or metric; when a metric precedes the first log line, list both}
- Likely trigger: {event, with timestamp and {confirmed | candidate | unknown}}
- Confirmed scope: {affected users/endpoints/services, or "unknown - logs carry no user identifier"}
- {any single-window observation surfaced when no baseline exists}

### Log Gaps
- {Signal missing that would resolve ambiguity, incl. all "requires evidence not yet held" items and a missing comparison window, or "None identified"}
```

## Avoid

- Skipping the healthy comparison when a baseline exists - patterns only have meaning relative to baseline
- Inventing a baseline when none exists - mark it unavailable instead
- Concluding root cause from logs alone without linking to code, config, or deploy evidence
